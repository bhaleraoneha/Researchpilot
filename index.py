"""Web app for Vercel (FastAPI). Vercel finds the object named `app` in this file.

Local test:  pip install fastapi uvicorn  then  uvicorn index:app --reload   (open http://127.0.0.1:8000)
"""
import collections
import os
import time

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from toolagent.agent import run_agent
from webpage import HTML

app = FastAPI(title="ResearchPilot")

# Shown on the "Evaluation results" tab if evaluation/results/analyst/summary.md is not in the deployment.
RESULTS_FALLBACK = """Evaluation of the agent (persona: analyst, model: openai/gpt-oss-120b, 25 test cases, run 12-10-2026)

PASS RATE: 22/25 = 88%

A case passes only if: right tools used, no crash, within the tool-call budget,
exact facts correct (if any), and the LLM judge scored it at least 4/5.

Category      Passed
no_tool       5/5
calculator    4/4
code          3/3
search        3/3
multi_step    4/5
brief         1/2
failure       2/3

Failed cases: 18 (malformed tool call from the model), 21 (correct answer but the calculator was not used),
25 (judge could not verify the quoted gold price).

Mean scores: tool_selection 0.94 | answer_correctness 0.92 | fact_match 1.00 | step_efficiency 1.00 |
graceful 0.96 | persona_compliance 0.88
Full details are in the GitHub repo (evaluation/results/analyst/ and reports/RESULTS.md)."""

_recent = collections.deque()   # request times, best-effort rate limit for this server instance
MAX_PER_MINUTE = 20


class Ask(BaseModel):
    question: str
    persona: str = "analyst"


def _limited() -> bool:
    now = time.time()
    while _recent and now - _recent[0] > 60:
        _recent.popleft()
    if len(_recent) >= MAX_PER_MINUTE:
        return True
    _recent.append(now)
    return False


@app.get("/", response_class=HTMLResponse)
def home():
    return HTML


@app.get("/api/health")
def health():
    return {"status": "ok", "model_configured": bool(os.getenv("LLM_API_KEY") and os.getenv("LLM_MODEL"))}


@app.get("/api/results")
def results():
    path = os.path.join(os.path.dirname(__file__), "evaluation", "results", "analyst", "summary.md")
    try:
        with open(path, encoding="utf-8") as f:
            return {"markdown": f.read()}
    except OSError:
        return {"markdown": RESULTS_FALLBACK}


@app.post("/api/ask")
def ask(body: Ask):
    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Please type a question.")
    if len(question) > 500:
        raise HTTPException(status_code=400, detail="Question too long (max 500 characters).")
    if not (os.getenv("LLM_API_KEY") and os.getenv("LLM_MODEL")):
        raise HTTPException(status_code=500, detail="Server is missing LLM_API_KEY / LLM_MODEL settings.")
    if _limited():
        raise HTTPException(status_code=429, detail="Too many requests. Please wait a minute and try again.")
    persona = body.persona if body.persona in ("analyst", "baseline") else "analyst"
    res = run_agent(question, verbose=False, max_steps=8, persona=persona)
    trace = [{"kind": t["kind"], "text": t["text"][:700]} for t in res["trace"]]
    return {"answer": res["answer"], "n_tool_calls": res["n_tool_calls"], "trace": trace,
            "error": res["error"], "seconds": res["seconds"], "persona": persona}
