"""Run the full evaluation of the agent:   python -m evaluation.run_eval
Options: --persona analyst|baseline|both   (default analyst = your customised agent; both = A/B comparison)
         --sleep 2   (seconds between questions, for free-tier rate limits)
         --mock      (fake agent + fake judge, ONLY to test that this script runs; numbers are meaningless)
Outputs: evaluation/results/<persona>/eval_results.json, summary.md, worst_cases.md  (+ comparison.md for 'both')"""
import argparse
import json
import os
import statistics as st
import time
import zlib

from evaluation import metrics as M

HERE = os.path.dirname(__file__)
METRIC_NAMES = ["tool_selection", "answer_correctness", "fact_match", "step_efficiency", "graceful", "persona_compliance"]


def _mock_agent(case, persona="analyst"):
    h = zlib.crc32(case["question"].encode()) % 4
    used = list(case["expected_tools"]) if h else []
    ans = " ".join(case["must_contain"]) or "mock answer"
    return {"question": case["question"], "answer": ans + ("\nConfidence: high - mock" if persona == "analyst" else ""), "n_tool_calls": len(used), "error": None,
            "tool_calls": [{"name": n, "args": {}, "result": "mock"} for n in used], "trace": [], "seconds": 0}


def _mock_judge(prompt):
    return '{"score": %d, "reason": "mock"}' % (3 + zlib.crc32(prompt.encode()) % 3)


def build_judge():
    from toolagent.llm import get_llm
    llm = get_llm(temperature=0)
    return lambda prompt: llm.invoke([("system", M.JUDGE_SYSTEM), ("human", prompt)]).content


def stats(vals):
    v = [x for x in vals if x is not None]
    if not v:
        return None
    return {"n": len(v), "mean": st.mean(v), "median": st.median(v), "min": min(v), "std": st.pstdev(v),
            "low": sum(x < 0.5 for x in v), "mid": sum(0.5 <= x < 0.8 for x in v), "high": sum(x >= 0.8 for x in v)}


def evaluate(persona="analyst", mock=False, sleep=0.0):
    cases = json.load(open(os.path.join(HERE, "test_cases.json"), encoding="utf-8"))
    if mock:
        run, judge = (lambda c: _mock_agent(c, persona)), _mock_judge
    else:
        from toolagent.agent import run_agent
        run, judge = (lambda c: run_agent(c["question"], verbose=False, persona=persona)), build_judge()
    rows = []
    for i, case in enumerate(cases, 1):
        print(f"[{i}/{len(cases)}] ({case['category']}) {case['question'][:80]}")
        res = run(case)
        score, why = M.answer_correctness(case, res, judge)
        scores = {"tool_selection": M.tool_selection(case, res), "answer_correctness": score,
                  "fact_match": M.fact_match(case, res), "step_efficiency": M.step_efficiency(case, res),
                  "graceful": M.graceful(case, res), "persona_compliance": M.persona_compliance(case, res, persona)}
        rows.append({"case": case, "answer": res["answer"], "tools_used": [c["name"] for c in res["tool_calls"]],
                     "tool_calls": res["tool_calls"], "error": res["error"], "scores": scores,
                     "judge_reason": why, "overall": M.overall(scores), "passed": M.passed(scores),
                     "trace": res.get("trace", [])})
        if sleep:
            time.sleep(sleep)
    return rows


def write_reports(rows, mock, persona):
    out = os.path.join(HERE, "results", persona)
    os.makedirs(out, exist_ok=True)
    json.dump(rows, open(os.path.join(out, "eval_results.json"), "w", encoding="utf-8"), indent=1)
    L = ["# Agent evaluation summary", ""]
    if mock:
        L += ["> WARNING: --mock was used. These numbers are FAKE and only prove the script runs.", ""]
    n_pass = sum(r["passed"] for r in rows)
    L += [f"Model: `{os.getenv('LLM_MODEL', '?')}` | Persona: `{persona}` | Test cases: {len(rows)}", "",
          f"## PASS RATE: {n_pass}/{len(rows)} = {n_pass / len(rows):.0%}", "",
          "A case passes only if: right tools used, no crash, within tool budget, exact facts correct (if any), and judge score >= 4/5.", "",
          "## Aggregate scores (0-1, higher is better)", "",
          "| Metric | n | Mean | Median | Min | Std | Low <0.5 | Mid 0.5-0.8 | High >=0.8 |", "|---|---|---|---|---|---|---|---|---|"]
    for m in METRIC_NAMES:
        s = stats([r["scores"][m] for r in rows])
        if s:
            L.append(f"| {m} | {s['n']} | {s['mean']:.2f} | {s['median']:.2f} | {s['min']:.2f} | {s['std']:.2f} | {s['low']} | {s['mid']} | {s['high']} |")
    L += ["", "## Mean score by category", "", "| Category | Cases | " + " | ".join(METRIC_NAMES) + " | overall | passed |", "|---|---|" + "---|" * (len(METRIC_NAMES) + 2)]
    for cat in ["no_tool", "calculator", "code", "search", "multi_step", "brief", "failure"]:
        sub = [r for r in rows if r["case"]["category"] == cat]
        if not sub:
            continue
        cells = []
        for m in METRIC_NAMES:
            s = stats([r["scores"][m] for r in sub])
            cells.append(f"{s['mean']:.2f}" if s else "-")
        L.append(f"| {cat} | {len(sub)} | " + " | ".join(cells) + f" | {st.mean(r['overall'] for r in sub):.2f} | {sum(r['passed'] for r in sub)}/{len(sub)} |")
    open(os.path.join(out, "summary.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")

    L2 = ["", "## Failed cases (PASS rule not met)", ""] + [f"- Case {r['case']['id']} [{r['case']['category']}]: {r['case']['question'][:90]}" for r in rows if not r["passed"]]
    open(os.path.join(out, "summary.md"), "a", encoding="utf-8").write("\n".join(L2) + "\n")
    W = ["# Worst 5 cases (use these for your failure analysis)", ""]
    for r in sorted(rows, key=lambda r: r["overall"])[:5]:
        c = r["case"]
        W += [f"## Case {c['id']} [{c['category']}] overall={r['overall']:.2f}", f"**Question:** {c['question']}",
              f"**Expected tools:** {c['expected_tools']}  |  **Used:** {r['tools_used']}",
              f"**Reference:** {c['reference']}", f"**Agent answer:** {r['answer']}",
              f"**Scores:** {r['scores']}", f"**Judge:** {r['judge_reason']}", f"**Error:** {r['error']}",
              "**Tool calls:**"] + [f"- {t['name']}({t['args']}) -> {str(t['result'])[:200]}" for t in r["tool_calls"]] + [""]
    open(os.path.join(out, "worst_cases.md"), "w", encoding="utf-8").write("\n".join(W))
    print("\n" + "\n".join(L + L2) + f"\n\nSaved to evaluation/results/{persona}/")


def write_comparison(results):
    L = ["# Customisation A/B: baseline vs analyst persona", "", "| Persona | Pass rate | Mean tool_selection | Mean answer_correctness |", "|---|---|---|---|"]
    for p, rows in results.items():
        ts = st.mean(r["scores"]["tool_selection"] for r in rows)
        ac = st.mean(r["scores"]["answer_correctness"] for r in rows if r["scores"]["answer_correctness"] is not None)
        L.append(f"| {p} | {sum(r['passed'] for r in rows)}/{len(rows)} ({sum(r['passed'] for r in rows) / len(rows):.0%}) | {ts:.2f} | {ac:.2f} |")
    if "analyst" in results:
        pc = [r["scores"]["persona_compliance"] for r in results["analyst"]]
        L += ["", f"Analyst persona followed the required 'Confidence:' ending on {sum(pc):.0f}/{len(pc)} answers."]
    open(os.path.join(HERE, "results", "comparison.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("\n" + "\n".join(L))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--persona", default="analyst", choices=["analyst", "baseline", "both"])
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--sleep", type=float, default=0.0)
    a = ap.parse_args()
    personas = ["baseline", "analyst"] if a.persona == "both" else [a.persona]
    allrows = {}
    for p in personas:
        print(f"\n##### Persona: {p} #####")
        allrows[p] = evaluate(p, a.mock, a.sleep)
        write_reports(allrows[p], a.mock, p)
    if len(personas) == 2:
        write_comparison(allrows)
