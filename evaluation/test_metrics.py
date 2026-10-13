"""Tests for the metric functions (no LLM needed).   python -m evaluation.test_metrics"""
from evaluation import metrics as M


def res(tools, answer="x", error=None):
    return {"tool_calls": [{"name": t, "args": {}, "result": "r"} for t in tools], "n_tool_calls": len(tools),
            "answer": answer, "error": error}


def test_tool_selection():
    assert M.tool_selection({"expected_tools": []}, res([])) == 1.0
    assert M.tool_selection({"expected_tools": []}, res(["calculator"])) == 0.0
    assert M.tool_selection({"expected_tools": ["web_search", "calculator"]}, res(["web_search"])) == 0.5
    assert M.tool_selection({"expected_tools": ["calculator"]}, res(["calculator", "calculator"])) == 1.0


def test_fact_match():
    assert M.fact_match({"must_contain": []}, res([])) is None
    assert M.fact_match({"must_contain": ["43710"]}, res([], "The result is 43,710.")) == 1.0
    assert M.fact_match({"must_contain": ["1", "2"]}, res([], "only 1")) == 0.5


def test_efficiency_and_graceful():
    assert M.step_efficiency({"max_tool_calls": 2}, res(["a", "a", "a"])) == 0.0
    assert M.graceful({}, res([], "ok")) == 1.0
    assert M.graceful({}, res([], "ok", error="boom")) == 0.0


def test_persona_and_pass_rule():
    ok = res([], "Paris.\nConfidence: high - well known")
    assert M.persona_compliance({}, ok, "analyst") == 1.0
    assert M.persona_compliance({}, res([], "Paris."), "analyst") == 0.0
    assert M.persona_compliance({}, ok, "baseline") is None
    good = {"tool_selection": 1.0, "graceful": 1.0, "step_efficiency": 1.0, "fact_match": None, "answer_correctness": 0.75}
    assert M.passed(good) is True
    assert M.passed({**good, "fact_match": 0.5}) is False
    assert M.passed({**good, "answer_correctness": 0.5}) is False
    assert M.passed({**good, "tool_selection": 0.5}) is False


def test_judge_parsing():
    case = {"question": "q", "reference": "r"}
    s, _ = M.answer_correctness(case, res([], "a"), lambda p: 'Sure! {"score": 5, "reason": "good"}')
    assert s == 1.0
    s, _ = M.answer_correctness(case, res([], "a"), lambda p: "garbage")
    assert s is None


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f()
            print("PASS", n)
