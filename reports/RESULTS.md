# Results

## 1. Pass rate
| Persona | Passed | Pass rate |
|---|---|---|
| analyst | 22 / 25 | 88 % |
| baseline | not run | not run |

Model used: openai/gpt-oss-120b (via Groq). Date of run: 12-10-2026.

A case passes only if: the right tools were used, no crash, within the tool-call budget, exact facts correct (if any), and the LLM judge gave at least 4/5.

Passed by category: no_tool 5/5, calculator 4/4, code 3/3, search 3/3, multi_step 4/5, brief 1/2, failure 2/3.
Failed cases: 18 (multi_step), 21 (failure), 25 (brief).

## 2. Did the customisation help?
The Analyst persona was checked with a format test: does the answer end with the required "Confidence: high|medium|low - reason" line. It did on 22 of 25 answers (88%). The 3 misses were cases 13, 18 and 22. In cases 13 and 22 the agent did write a Confidence statement, but on the same line as the answer instead of on its own final line, so my strict format check marked it as not followed. Case 18 had no answer because of an API error. I did not run the baseline persona, so I cannot say how much the persona changed the pass rate compared with a generic prompt. That is a gap in this evaluation.

## 3. Failure patterns (from the 3 failed cases)

### Pattern 1: The model produced a malformed tool call (case 18)
- Cases: 18 (multi_step, "Search for the current population of Japan, then use the calculator to find 1% of it")
- What happened: The first web_search worked. The model's next tool call was malformed: it sent {"cursor": 0, "id": 1} without the required "query" field. The API rejected it with error 400 (tool call validation failed). The agent did not crash and the error was caught, but no answer was produced, so the case scored 0 on correctness.
- Likely cause: The model (openai/gpt-oss-120b via Groq) sometimes generates tool arguments that do not match the tool schema. This is a model/API-level failure, not a bug in the tools.
- Fix idea: Retry the run when the API returns a tool_use_failed error, or fall back to a second model.

### Pattern 2: The test expected a tool the agent did not need (case 21)
- Cases: 21 (failure, "Calculate 10 / 0")
- What happened: The agent answered "undefined (division by zero)" directly, without calling the calculator. The answer was correct (judge 5/5), but the case failed the tool_selection rule because the test expects the calculator.
- Likely cause: The model knows that division by zero is undefined. The test design is too strict for this case.
- Fix idea: Make the calculator optional for this case, or rewrite the case so a tool is truly needed.

### Pattern 3: Judge marked a gold-price answer as unverified (case 25)
- Cases: 25 (brief, gold price)
- What happened: The agent searched, quoted a price of $4,170.80 per troy ounce, and calculated that 25 g costs about $3,352.36. The arithmetic is correct (4170.80 / 31.1035 x 25). The judge scored it 0 because it could not find that price in the search output it was shown.
- Likely cause (not verified): Either the judge only sees the first 300 characters of each tool output (a limit in my evaluation code, so it could not see the price), or the agent used a number that was not in the search result. I did not check which one it was.
- Fix idea: Show the judge the full tool output, and re-run this case.

## 4. One full trace (flagship task, from the demo run)
```
Q: Look up the population of India, calculate what 5% of it is, then write a 3-sentence summary of your findings.
  TOOL CALL: web_search({'query': 'current population of India 2023'})
  TOOL RESULT: 1. Demographics of India - Wikipedia ... 2. India Population (2026) - Worldometer: India 2026 population is estimated at 1,476,625,576 ...
  TOOL CALL: calculator({'expression': '1_438_069_596 * 0.05'})
  TOOL RESULT: 71903479.8
  FINAL ANSWER: India's 2023 population was about 1,438,069,596 people. Five percent of that total equals 71,903,479.8 people, roughly 71.9 million. Thus, about one-twentieth of India's residents, roughly 72 million, represent a 5% share of the nation's total population.
  Confidence: high - recent population figure from a reputable demographic source and straightforward calculation.
```
Note: the agent used the 2023 figure although a 2026 estimate appeared in the search result, which is a limitation (see README).
