# ResearchPilot

A tool-using research-and-calculation agent (LangChain `create_agent`) with a specialised persona, full step-by-step
tracing, and an automatic evaluation harness that reports a **pass rate**.

## What it can do (capabilities)
| Tool | Purpose |
|---|---|
| `web_search` | live facts (DuckDuckGo, no key needed) |
| `calculator` | exact arithmetic on big numbers, percentages, powers |
| `python_executor` | runs real Python code (10 s time limit) |

Flagship multi-step task: *"Look up the population of India, calculate what 5% of it is, then write a 3-sentence summary."*
The agent decides by itself which tools to call, in what order, and feeds one result into the next.

## Customisation (AI-6): the "Analyst" persona
The agent runs with one of two system prompts (`toolagent/personas.py`):
- `baseline`: generic assistant + tool rules
- `analyst` (the customisation): a specialised persona with fixed style rules: lead with the answer, name the source
  page used, show calculation inputs, write exactly the requested number of sentences, never state unverified numbers, and
  end **every** answer with `Confidence: high|medium|low - reason`.

The effect is measured, not assumed: `python -m evaluation.run_eval --persona both` compares the two on the same test set
(pass rate + a `persona_compliance` metric that checks the required Confidence line).

## Tracing (what tool, what input, why)
Every run prints and logs `THOUGHT` (why) -> `TOOL CALL` (tool + input) -> `TOOL RESULT` -> `FINAL ANSWER`.
Demo traces are saved to `logs/demo_trace.jsonl`; evaluation traces for all 25 cases are inside `evaluation/results/<persona>/eval_results.json`.

## Evaluation (AI-7)
25 test cases in `evaluation/test_cases.json` (no-tool, calculator, code, search, multi-step, flagship "brief", failure handling),
each with expected tools, a tool-call budget and an expected outcome.
**A case PASSES only if all hold:** right tools used, no crash and an answer, within the tool budget, exact facts correct
(when the case has them), and the LLM judge scored it at least 4/5.
Other metrics: tool_selection, answer_correctness (LLM judge), fact_match, step_efficiency, graceful, persona_compliance.

## How to run
```bash
python -m venv .venv
.venv\Scripts\activate                 # Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env                 # then edit .env: API key, model, base URL (free: Groq, see .env.example)

python -m toolagent.test_tools         # 1. tools work on their own (no LLM)
python -m evaluation.test_metrics      # 2. metric code works (no LLM)
python -m toolagent.run_demo           # 3. watch the agent think and use tools
python -m evaluation.run_eval --persona both --sleep 2    # 4. full evaluation, both personas
```
Results appear in `evaluation/results/` (`comparison.md`, and `analyst/` + `baseline/` with `summary.md`, `worst_cases.md`).
Then fill in `reports/RESULTS.md`. The model must support tool calling.

## Evaluation results
Run date: 12-10-2026. Model: `openai/gpt-oss-120b` (via Groq). Persona: `analyst`. 25 test cases.

**PASS RATE: 22/25 = 88%**

| Category | Passed |
|---|---|
| no_tool | 5/5 |
| calculator | 4/4 |
| code | 3/3 |
| search | 3/3 |
| multi_step | 4/5 |
| brief | 1/2 |
| failure | 2/3 |

| Metric | Mean |
|---|---|
| tool_selection | 0.94 |
| answer_correctness | 0.92 |
| fact_match (12 cases with exact numbers) | 1.00 |
| step_efficiency | 1.00 |
| graceful | 0.96 |
| persona_compliance | 0.88 |

All 12 cases with exact numbers were answered correctly. The baseline persona was not run, so this README does not claim how much the Analyst persona improved the results.
Full tables: `evaluation/results/analyst/summary.md`. Details of the worst cases: `evaluation/results/analyst/worst_cases.md`.

## Failure patterns observed
- **Case 18 (Japan population):** the model sent a malformed tool call (the required `query` field was missing). The API rejected it with error 400 and no answer was produced. The error was caught, so the program did not crash.
- **Case 21 (10 / 0):** the agent correctly answered that division by zero is undefined, without calling the calculator. It failed only because the test expects the calculator.
- **Case 25 (gold price):** the arithmetic was correct, but the judge scored it 0 because it could not see the quoted price in the search output it was given (see `reports/RESULTS.md`, Pattern 3).
- **Persona format:** in 2 answers the `Confidence:` text was on the same line as the answer instead of its own final line, so the strict format check failed.

Full analysis: `reports/RESULTS.md`.

## Known limitations
- `python_executor` uses a subprocess with a timeout. It is not a security sandbox; do not run untrusted prompts.
- Web search quality depends on DuckDuckGo results, so search-based cases can change between runs.
- The LLM judge can be wrong or lenient, and the same model is used as agent and judge. Exact-number cases are the most reliable.
- 25 test cases is a small sample, so small differences in pass rate are noise.
- The agent has no memory between questions, and no tools for email, files or databases.
- The model sometimes produces an invalid tool call, which the API rejects. That run then ends without an answer.
- The LLM judge only sees the first 300 characters of each tool output, so it can wrongly fail a correct answer.
- Each test case requires specific tools, which can fail a correct answer that did not need a tool (case 21).
- DuckDuckGo sometimes returns "No results found" or unrelated results, so the agent sometimes needs a retry.
- In the demo run, the agent searched for "population of India 2023" and used the 2023 figure even though a newer 2026 estimate appeared in the results. It does not always pick the most recent number.
