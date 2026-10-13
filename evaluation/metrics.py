"""The five metrics. Each returns a number from 0 to 1 (or None when it does not apply).
Programmatic metrics need no LLM; only `answer_correctness` uses an LLM judge."""
import json
import re

JUDGE_SYSTEM = "You are a strict, fair evaluator. Reply with JSON only."


def tool_selection(case: dict, result: dict):
    """Did the agent use the RIGHT tools? No-tool cases: score 1 only if it used NO tool.
    Tool cases: fraction of the expected tools that were actually called."""
    used = {c["name"] for c in result["tool_calls"]}
    expected = set(case["expected_tools"])
    if not expected:
        return 1.0 if not used else 0.0
    return len(expected & used) / len(expected)


def fact_match(case: dict, result: dict):
    """Programmatic check: fraction of the required strings (e.g. the exact number) found in the answer.
    Commas, spaces and case are ignored. None for cases that have no exact facts."""
    need = case.get("must_contain") or []
    if not need:
        return None
    norm = lambda s: re.sub(r"[,\s]", "", str(s)).lower()
    ans = norm(result["answer"])
    return sum(norm(n) in ans for n in need) / len(need)


def step_efficiency(case: dict, result: dict):
    """1 if the agent used no more tool calls than allowed (stops runaway loops), else 0."""
    return 1.0 if result["n_tool_calls"] <= case["max_tool_calls"] else 0.0


def graceful(case: dict, result: dict):
    """1 if the run finished without an unhandled error and produced a non-empty answer."""
    return 1.0 if (result["error"] is None and result["answer"].strip()) else 0.0


def persona_compliance(case: dict, result: dict, persona: str):
    """Customisation check (analyst persona only): does the answer end with the required
    'Confidence: high|medium|low - reason' line? None for the baseline persona."""
    if persona != "analyst":
        return None
    lines = [l.strip() for l in result["answer"].strip().splitlines() if l.strip()]
    ok = bool(lines) and re.match(r"(?i)^\**confidence\**\s*:\s*(high|medium|low)\b", lines[-1]) is not None
    return 1.0 if ok else 0.0


def passed(scores: dict) -> bool:
    """PASS RULE (a case passes only if ALL of these hold):
    right tools used, no crash and an answer, within the tool-call budget, exact facts correct (when the
    case has them), and the LLM judge gave at least 4/5 (score >= 0.75)."""
    c = scores["answer_correctness"]
    return (scores["tool_selection"] == 1.0 and scores["graceful"] == 1.0 and scores["step_efficiency"] == 1.0
            and scores["fact_match"] in (None, 1.0) and c is not None and c >= 0.75)


def _parse_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    try:
        return json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        return {}


def answer_correctness(case: dict, result: dict, ask_llm):
    """LLM-as-judge: rate 1-5 against the reference / success criterion, then (score-1)/4.
    The judge also sees the tool outputs so it can punish invented facts."""
    tools_seen = "\n".join(f"- {c['name']}({c['args']}) -> {str(c['result'])[:300]}"
                           for c in result["tool_calls"]) or "(no tools used)"
    prompt = (f"QUESTION: {case['question']}\n"
              f"REFERENCE / SUCCESS CRITERION: {case['reference']}\n"
              f"TOOL OUTPUTS THE AGENT SAW:\n{tools_seen}\n"
              f"AGENT'S FINAL ANSWER: {result['answer']}\n\n"
              "Rate 1-5: 5 = fully correct and satisfies the criterion; 3 = partly correct or vague; "
              "1 = wrong, contradicts the criterion, or invents facts not supported by the tool outputs.\n"
              'Reply ONLY with JSON: {"score": <1-5>, "reason": "<one sentence>"}')
    data = _parse_json(ask_llm(prompt))
    s = data.get("score")
    if not isinstance(s, (int, float)):
        return None, "judge returned invalid JSON"
    s = max(1, min(5, s))
    return (s - 1) / 4, data.get("reason", "")


def overall(scores: dict) -> float:
    vals = [v for v in scores.values() if v is not None]
    return sum(vals) / len(vals) if vals else 0.0
