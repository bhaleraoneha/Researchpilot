"""Tool-using agent built with LangChain's current `create_agent` (which runs on LangGraph).

run_agent(question) returns the final answer AND a full trace of every thought / tool call / tool result.
"""
import time
from functools import lru_cache

from langchain.agents import create_agent
from langchain.tools import tool

from toolagent import tools as T
from toolagent.llm import get_llm
from toolagent.personas import PERSONAS


# ---- Tool wrappers. The DOCSTRING is what the LLM reads to decide when to use each tool. ----------
@tool
def calculator(expression: str) -> str:
    """Exactly evaluate a math expression and return the result.
    Use it for arithmetic with big numbers or many digits, powers, roots, factorials, percentages.
    Do NOT use it for trivial math (like 12*9) or for non-math questions.
    Input must be plain math such as '98765432123 * 12345678987' or 'sqrt(144) + 2**10'."""
    return T.calculate(expression)


@tool
def python_executor(code: str) -> str:
    """Run Python code and return everything it prints.
    Use it when a task needs real computation or running a program (loops over millions of
    numbers, hashing, primes, simulations). The code MUST use print() to show its result."""
    return T.run_python(code)


@tool
def web_search(query: str) -> str:
    """Search the web for current or real-time facts the model may not know or may have wrong
    (recent events, latest versions, current office holders, up-to-date measurements).
    Do NOT use it for timeless general knowledge. Input is a short search query."""
    return T.web_search(query)


TOOLS = [calculator, python_executor, web_search]

@lru_cache(maxsize=None)
def get_agent(persona: str = "analyst"):
    return create_agent(model=get_llm(), tools=TOOLS, system_prompt=PERSONAS[persona])


def _text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in content)
    return str(content)


def _short(s: str, n: int = 300) -> str:
    s = s.replace("\n", " ")
    return s if len(s) <= n else s[:n] + " ..."


def run_agent(question: str, verbose: bool = True, max_steps: int = 10, persona: str = "analyst") -> dict:
    """Run the agent once. Never raises: any failure is returned in result['error']."""
    t0 = time.time()
    trace, calls_by_id, tool_calls = [], {}, []
    answer, error, seen = "", None, 0

    def log(kind, text):
        trace.append({"kind": kind, "text": text})
        if verbose:
            icon = {"thought": "💭 THOUGHT", "call": "🔧 TOOL CALL", "result": "📥 TOOL RESULT",
                    "final": "✅ FINAL ANSWER"}[kind]
            print(f"  {icon}: {_short(text, 400)}")

    try:
        stream = get_agent(persona).stream({"messages": [{"role": "user", "content": question}]},
                                    config={"recursion_limit": max_steps * 2 + 1},
                                    stream_mode="values")
        for state in stream:
            msgs = state["messages"]
            for msg in msgs[seen:]:
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
                        log("final", text)
                elif kind == "tool":
                    result = _text(msg.content)
                    rec = calls_by_id.get(getattr(msg, "tool_call_id", None))
                    if rec is not None:
                        rec["result"] = result
                    log("result", result)
            seen = len(msgs)
    except Exception as e:  # network error, rate limit, recursion limit ... never crash the caller
        error = f"{type(e).__name__}: {e}"
        answer = answer or f"(The agent stopped because of an error: {error})"
        if verbose:
            print(f"  ⚠️  AGENT ERROR (handled): {error}")

    return {"question": question, "persona": persona, "answer": answer, "tool_calls": tool_calls,
            "n_tool_calls": len(tool_calls), "trace": trace, "error": error,
            "seconds": round(time.time() - t0, 2)}
