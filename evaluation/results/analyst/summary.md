# Agent evaluation summary

Model: `openai/gpt-oss-120b` | Persona: `analyst` | Test cases: 25

## PASS RATE: 22/25 = 88%

A case passes only if: right tools used, no crash, within tool budget, exact facts correct (if any), and judge score >= 4/5.

## Aggregate scores (0-1, higher is better)

| Metric | n | Mean | Median | Min | Std | Low <0.5 | Mid 0.5-0.8 | High >=0.8 |
|---|---|---|---|---|---|---|---|---|
| tool_selection | 25 | 0.94 | 1.00 | 0.00 | 0.22 | 1 | 1 | 23 |
| answer_correctness | 25 | 0.92 | 1.00 | 0.00 | 0.27 | 2 | 0 | 23 |
| fact_match | 12 | 1.00 | 1.00 | 1.00 | 0.00 | 0 | 0 | 12 |
| step_efficiency | 25 | 1.00 | 1.00 | 1.00 | 0.00 | 0 | 0 | 25 |
| graceful | 25 | 0.96 | 1.00 | 0.00 | 0.20 | 1 | 0 | 24 |
| persona_compliance | 25 | 0.88 | 1.00 | 0.00 | 0.32 | 3 | 0 | 22 |

## Mean score by category

| Category | Cases | tool_selection | answer_correctness | fact_match | step_efficiency | graceful | persona_compliance | overall | passed |
|---|---|---|---|---|---|---|---|---|---|
| no_tool | 5 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 5/5 |
| calculator | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 4/4 |
| code | 3 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 3/3 |
| search | 3 | 1.00 | 1.00 | - | 1.00 | 1.00 | 0.67 | 0.93 | 3/3 |
| multi_step | 5 | 0.90 | 0.80 | 1.00 | 1.00 | 0.80 | 0.80 | 0.86 | 4/5 |
| brief | 2 | 1.00 | 0.50 | - | 1.00 | 1.00 | 1.00 | 0.90 | 1/2 |
| failure | 3 | 0.67 | 1.00 | - | 1.00 | 1.00 | 0.67 | 0.87 | 2/3 |

## Failed cases (PASS rule not met)

- Case 18 [multi_step]: Search for the current population of Japan, then use the calculator to find 1% of it.
- Case 21 [failure]: Calculate 10 / 0.
- Case 25 [brief]: Search the web for the current gold price per troy ounce in USD, then use the calculator t
