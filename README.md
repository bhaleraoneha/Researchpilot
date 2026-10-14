# ResearchPilot

**Live demo:** https://researchpilot-one.vercel.app
(web app built with FastAPI, deployed on Vercel)

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

## Reliability fix after reviewer feedback
A reviewer tested the live app with: *"Look up the population of Pune India, Calculate 10% of it & add 100 to it"* and got
`Tool call validation failed ... missing properties: 'query'` (HTTP 400). Cause: the model (openai/gpt-oss-120b on Groq)
sometimes sends a malformed tool call, `web_search` with `{"cursor": 0, "id": 0}` instead of `{"query": ...}`. This is the same
failure as case 18 in my evaluation. What I changed (`toolagent/agent.py`, `toolagent/personas.py`):
1. **Automatic retry:** if the API rejects a tool call, the agent run is repeated up to 3 times (temperature 0, then 0.3, then 0.6), plus one run with
   a fallback model if `LLM_FALLBACK_MODEL` is set. The web page shows a "[system] ... Retrying" note in the steps.
2. **Tolerant tools:** each tool's argument now has a default, so a missing argument no longer causes an API error. The tool returns a clear
   `ERROR: web_search needs a 'query' ...` message and the model corrects itself.
3. **Clearer prompt rule:** each tool takes exactly one text argument; never pass `id`, `cursor` or `url`; and always finish with a written answer.
4. **Empty-answer guard:** in a second review test the model searched twice and then ended with a blank message (the page showed "(no answer)").
   Now, if the model ends without a final answer, the agent asks it to continue (up to 2 nudges) so it can use the calculator and write the
   answer; if that still fails the whole run is retried, and finally a clear message is shown instead of a blank box.
The retry logic was tested with simulated failures (recovers on attempt 2 or 3, gives up cleanly after all attempts, does not retry rate-limit errors).
Retries reduce the problem but cannot remove it, because the model's behaviour is random.

5. **Time budget:** Vercel stops a request after 60 s, which showed up as a plain-text error in the browser. The agent now has a 40 s budget
   (each model call also has a 20 s timeout); if time runs out it returns a clear message instead of crashing, and the web page shows the
   server's real error text.

6. **Token limit (Groq free plan = 8,000 tokens per minute per model):** one run with 7 tool calls exceeded it and returned a 429 error.
   Fixes: search results are cut to 3 short results, the prompts are shorter, the prompt allows at most 2 searches, each model call is limited to
   1,000 output tokens, and when Groq answers 429 the agent automatically switches to a backup model (`openai/gpt-oss-20b`, or the models in
   `LLM_FALLBACK_MODEL`), because Groq counts the limit per model. If both are busy, a friendly "wait a minute" message is shown.

## Web app and deployment
`index.py` is a FastAPI app (page + API) that exposes the agent in the browser: you type a question, and the page shows the
answer plus every step (thought, tool call with input, tool result). The "Evaluation results" tab shows the pass rate.
It is deployed on Vercel (`vercel.json`, `.python-version` and `requirements.txt` configure it).

Run it locally:
```bash
pip install fastapi uvicorn
uvicorn index:app --reload          # open http://127.0.0.1:8000
```
Deploy on Vercel: push this repo to GitHub, import it at vercel.com, and set these environment variables
(never commit them): `LLM_API_KEY`, `LLM_MODEL`, `LLM_BASE_URL`. Optional: `TAVILY_API_KEY` for more reliable web search.

Safety for a public app: `python_executor` runs in SAFE MODE (only harmless modules such as math/hashlib, no files,
network or system access, no secret environment variables, 10 s time limit), questions are limited to 500 characters,
and requests are rate-limited. This lowers the risk but is not a perfect sandbox.

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
- `python_executor` uses a subprocess with a timeout plus an allow-list of safe modules. It is not a perfect security sandbox.
- Web search quality depends on DuckDuckGo results, so search-based cases can change between runs.
- The LLM judge can be wrong or lenient, and the same model is used as agent and judge. Exact-number cases are the most reliable.
- 25 test cases is a small sample, so small differences in pass rate are noise.
- The agent has no memory between questions, and no tools for email, files or databases.
- The evaluation numbers above (22/25) were measured BEFORE the code-runner "safe mode" and the retry/tolerant-tool fixes were added, so the current app may score differently.
- On Vercel, DuckDuckGo search may be blocked or rate-limited more often than on a home computer; the agent then reports that search failed.
- The free Groq plan limits tokens per minute (8,000 for openai/gpt-oss-120b), shared by everyone using the app. The agent switches to a backup model when one is full, but if several people ask questions in the same minute, some requests may still be told to wait about a minute.
- The model sometimes produces an invalid tool call, which the API rejects. The app now retries automatically (up to 3 times), but if every attempt fails the run ends with an error message.
- The LLM judge only sees the first 300 characters of each tool output, so it can wrongly fail a correct answer.
- Each test case requires specific tools, which can fail a correct answer that did not need a tool (case 21).
- DuckDuckGo sometimes returns "No results found" or unrelated results, so the agent sometimes needs a retry.
- In the demo run, the agent searched for "population of India 2023" and used the 2023 figure even though a newer 2026 estimate appeared in the results. It does not always pick the most recent number.
