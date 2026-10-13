"""Tool-using agent built with LangChain's current `create_agent` (which runs on LangGraph).

run_agent(question) returns the final answer AND a full trace of every thought / tool call / tool result.
"""
import os
import time
from functools import lru_cache

from langchain.agents import create_agent
from langchain.tools import tool

from toolagent import tools as T
from toolagent.llm import get_llm
from toolagent.personas import PERSONAS


# ---- Tool wrappers. The DOCSTRING is what the LLM reads to decide when to use each tool. ----------
@tool
def calculator(expression: str = "") -> str:
    """Exactly evaluate a math expression and return the result.
    Use it for arithmetic with big numbers or many digits, powers, roots, factorials, percentages.
    Do NOT use it for trivial math (like 12*9) or for non-math questions.
    Input must be plain math such as '98765432123 * 12345678987' or 'sqrt(144) + 2**10'."""
    if not expression or not str(expression).strip():
        return "ERROR: calculator needs an 'expression' text, for example calculator(expression='1000000 * 0.1 + 100'). Call it again with an expression."
    return T.calculate(expression)


@tool
def python_executor(code: str = "") -> str:
    """Run Python code and return everything it prints.
    Use it when a task needs real computation or running a program (loops over millions of
    numbers, hashing, primes, simulations). The code MUST use print() to show its result."""
    if not code or not str(code).strip():
        return "ERROR: python_executor needs a 'code' text that uses print(). Call it again with code."
    return T.run_python(code)


@tool
def web_search(query: str = "") -> str:
    """Search the web for current or real-time facts the model may not know or may have wrong
    (recent events, latest versions, current office holders, up-to-date measurements).
    Do NOT use it for timeless general knowledge. Input is a short search query."""
    if not query or not str(query).strip():
        return "ERROR: web_search needs a 'query' text, for example web_search(query='population of Pune India'). Call it again with a query."
    return T.web_search(query)


TOOLS = [calculator, python_executor, web_search]

@lru_cache(maxsize=None)
def get_agent(persona: str = "analyst", temperature: float = 0.0, model: str = None):
    return create_agent(model=get_llm(temperature, model), tools=TOOLS, system_prompt=PERSONAS[persona])


def _text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in content)
    return str(content)


def _short(s: str, n: int = 300) -> str:
    s = s.replace("\n", " ")
    return s if len(s) <= n else s[:n] + " ..."


def _run_once(question: str, verbose: bool, max_steps: int, persona: str, temperature: float, model) -> dict:
    """One attempt. Never raises: any failure is returned in result['error']."""
    t0 = time.time()
    trace, calls_by_id, tool_calls = [], {}, []
    answer, error, seen = "", None, 0

    def log(kind, text):
        trace.append({"kind": kind, "text": text})
        if verbose:
            icon = {"thought": "💭 THOUGHT", "call": "🔧 TOOL CALL", "result": "📥 TOOL RESULT",
                    "final": "✅ FINAL ANSWER"}[kind]
            print(f"  {icon}: {_short(text, 400)}")

    def process(msgs, start):
        """Log every message after index `start`; remember the final answer."""
        nonlocal answer
        for msg in msgs[start:]:
            kind = getattr(msg, "type", "")
            if kind == "ai":
                text = _text(msg.content).strip()
                calls = getattr(msg, "tool_calls", None) or []
                if text and calls:
                    log("thought", text)
                for c in calls:
                    rec = {"name": c["name"], "args": c["args"], "result": None}
                    calls_by_id[c["id"]] = rec
                    tool_calls.append(rec)
                    log("call", f"{c['name']}({c['args']})")
                if not calls:
                    answer = text
                    if text:
                        log("final", text)
            elif kind == "tool":
                result = _text(msg.content)
                rec = calls_by_id.get(getattr(msg, "tool_call_id", None))
                if rec is not None:
                    rec["result"] = result
                log("result", result)

    nudge_text = ("You stopped without writing a final answer. Continue now: if a step is still missing "
                  "(for example the calculator), call that tool, then write the final answer in text.")
    try:
        agent = get_agent(persona, temperature, model)
        messages = [{"role": "user", "content": question}]
        for round_no in range(3):            # round 0 = normal run; rounds 1-2 = "please finish" nudges
            last = None
            for state in agent.stream({"messages": messages}, config={"recursion_limit": max_steps * 2 + 1},
                                      stream_mode="values"):
                last = state["messages"]
                process(last, seen)
                seen = len(last)
            if answer.strip() or last is None:
                break
            if round_no < 2:                 # the model ended with an EMPTY message: ask it to continue
                log("thought", "[system] The model ended without a final answer. Asking it to continue.")
                messages = list(last) + [{"role": "user", "content": nudge_text}]
                seen = len(last)
        if not answer.strip():
            error = "EmptyAnswer: the model returned no final text"
            answer = "(The model returned an empty answer. Please try asking again.)"
    except (Exception, SystemExit) as e:  # network error, rate limit, recursion limit ... never crash the caller
        error = f"{type(e).__name__}: {e}"
        answer = answer or f"(The agent stopped because of an error: {error})"
        if verbose:
            print(f"  ⚠️  AGENT ERROR (handled): {error}")

    return {"question": question, "persona": persona, "answer": answer, "tool_calls": tool_calls,
            "n_tool_calls": len(tool_calls), "trace": trace, "error": error,
            "seconds": round(time.time() - t0, 2)}


# Errors where the MODEL (not our code) misbehaved: invalid tool call or an empty final message. A fresh attempt usually works.
RETRYABLE = ("tool_use_failed", "Tool call validation failed", "Failed to call a function", "failed_generation", "EmptyAnswer")


def run_agent(question: str, verbose: bool = True, max_steps: int = 10, persona: str = "analyst") -> dict:
    """Run the agent. If the model sends a malformed tool call (HTTP 400 from the API), retry automatically:
    attempt 1 at temperature 0, attempts 2-3 at higher temperature (different output), and a final attempt
    with LLM_FALLBACK_MODEL if that variable is set. Never raises."""
    t0 = time.time()
    attempts = [(0.0, None), (0.3, None), (0.6, None)]
    fallback = os.getenv("LLM_FALLBACK_MODEL")
    if fallback:
        attempts.append((0.0, fallback))
    notes = []
    res = None
    for n, (temp, model) in enumerate(attempts, 1):
        res = _run_once(question, verbose, max_steps, persona, temp, model)
        err = res["error"] or ""
        if not err or not any(k in err for k in RETRYABLE):
            break
        if n < len(attempts):
            notes.append(f"[system] Attempt {n} failed because the model sent an invalid tool call or an empty answer. Retrying automatically (attempt {n + 1}).")
            if verbose:
                print(f"  🔁 {notes[-1]}")
    if notes and res["error"] is None:
        res["trace"] = [{"kind": "thought", "text": n_} for n_ in notes] + res["trace"]
    res["attempts"] = n
    res["seconds"] = round(time.time() - t0, 2)
    return res
