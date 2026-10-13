"""Demo of every requirement.   python -m toolagent.run_demo            (all scenarios, persona "analyst")
                               python -m toolagent.run_demo --persona baseline
                               python -m toolagent.run_demo "your own question"
Saves the full reasoning trace to logs/demo_trace.jsonl"""
import json
import os
import sys

from toolagent.agent import run_agent

SCENARIOS = [
    ("NO TOOL needed (should answer directly)", "What is the capital of France?"),
    ("TOOL needed: calculator", "What is 98765432123 * 12345678987?"),
    ("TOOL needed: code execution", "Run Python to find how many prime numbers are below 100000."),
    ("TOOL needed: web search", "What is the latest stable version of Python? Search the web."),
    ("MULTI-STEP: search, then calculate",
     "Search the web for the height of Mount Everest in metres, then use the calculator to convert it to feet (multiply by 3.28084)."),
    ("MULTI-STEP: same tool twice / code then calculator",
     "Use Python to compute the sum of squares of 1 to 1000, then use the calculator to divide that sum by 7."),
    ("FLAGSHIP TASK: look up, compute, draft a summary",
     "Look up the population of India, calculate what 5% of it is, then write a 3-sentence summary of your findings."),
    ("REGRESSION: query that failed in review (malformed tool call)",
     "Look up the population of Pune India, Calculate 10% of it & add 100 to it"),
    ("TOOL FAILURE: calculator error", "Calculate 10 / 0."),
    ("TOOL FAILURE: search finds nothing", "Search the web for 'qzxv wlmrtp blorf 99172 zzkq' and tell me what it is."),
]


def main():
    argv, persona = sys.argv[1:], "analyst"
    if "--persona" in argv:
        i = argv.index("--persona")
        persona = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    print(f"Persona: {persona}")
    scenarios = [("CUSTOM QUESTION", " ".join(argv))] if argv else SCENARIOS
    os.makedirs("logs", exist_ok=True)
    rows = []
    with open("logs/demo_trace.jsonl", "w", encoding="utf-8") as f:
        for title, q in scenarios:
            print(f"\n=== {title} ===\nQ: {q}")
            res = run_agent(q, verbose=True, persona=persona)
            f.write(json.dumps({"scenario": title, **res}, ensure_ascii=False) + "\n")
            rows.append((title, res["n_tool_calls"], ", ".join(c["name"] for c in res["tool_calls"]) or "-"))
    print("\n=== SUMMARY: did the agent use tools only when needed? ===")
    for title, n, names in rows:
        print(f"{n} tool call(s)  [{names}]  <-  {title}")
    print("\nFull trace saved to logs/demo_trace.jsonl")


if __name__ == "__main__":
    main()
