"""The single web page (plain HTML + JavaScript, no build step), served by index.py at '/'."""
HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ResearchPilot - tool-using AI agent</title>
<style>
  :root { --bg:#f6f7fb; --card:#fff; --ink:#1c2230; --muted:#667085; --brand:#4f46e5; --line:#e4e7ec; --ok:#067647; --bad:#b42318; }
  * { box-sizing:border-box; }
  body { margin:0; font-family:system-ui,Segoe UI,Arial,sans-serif; background:var(--bg); color:var(--ink); }
  main { max-width:860px; margin:0 auto; padding:24px 16px 60px; }
  h1 { margin:0 0 4px; font-size:28px; } .sub { color:var(--muted); margin:0 0 18px; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:16px; margin-bottom:16px; }
  textarea { width:100%; min-height:80px; padding:10px; border:1px solid var(--line); border-radius:8px; font:inherit; resize:vertical; }
  select, button { font:inherit; padding:9px 14px; border-radius:8px; border:1px solid var(--line); background:#fff; cursor:pointer; }
  button.primary { background:var(--brand); color:#fff; border-color:var(--brand); }
  button:disabled { opacity:.5; cursor:wait; }
  .row { display:flex; gap:10px; flex-wrap:wrap; align-items:center; margin-top:10px; }
  .chips button { font-size:13px; padding:6px 10px; background:#eef2ff; border-color:#e0e7ff; color:#3730a3; }
  .step { border-left:3px solid var(--line); padding:6px 10px; margin:8px 0; background:#fafafa; border-radius:0 8px 8px 0; font-size:14px; white-space:pre-wrap; word-break:break-word; }
  .step b { display:block; font-size:12px; color:var(--muted); letter-spacing:.04em; }
  .step.call { border-color:#f79009; } .step.result { border-color:#2e90fa; } .step.final { border-color:var(--ok); } .step.thought { border-color:#7a5af8; }
  .answer { white-space:pre-wrap; font-size:16px; line-height:1.5; }
  .err { color:var(--bad); } .muted { color:var(--muted); font-size:13px; }
  .tabs { display:flex; gap:8px; margin-bottom:12px; } .tabs button.active { background:var(--ink); color:#fff; }
  pre { white-space:pre-wrap; font-size:13px; line-height:1.45; overflow-x:auto; }
  .hidden { display:none; }
</style>
</head>
<body>
<main>
  <h1>ResearchPilot</h1>
  <p class="sub">An AI agent that decides by itself when to use tools: <b>web search</b>, <b>calculator</b> and <b>Python code runner</b>. Every step it takes is shown below.</p>

  <div class="tabs">
    <button id="tabAgent" class="active" onclick="show('agent')">Try the agent</button>
    <button id="tabEval" onclick="show('eval')">Evaluation results</button>
    <button id="tabAbout" onclick="show('about')">About &amp; limits</button>
  </div>

  <section id="agent">
    <div class="card">
      <textarea id="q" maxlength="500" placeholder="Ask something, for example: Look up the population of India, calculate 5% of it, then write a 3-sentence summary."></textarea>
      <div class="row">
        <select id="persona" title="Which system prompt the agent uses">
          <option value="analyst">Persona: Analyst (customised)</option>
          <option value="baseline">Persona: Baseline (generic)</option>
        </select>
        <button class="primary" id="go" onclick="ask()">Ask the agent</button>
        <span id="status" class="muted"></span>
      </div>
      <div class="row chips">
        <span class="muted">Try:</span>
        <button onclick="ex(0)">No tool needed</button>
        <button onclick="ex(1)">Big multiplication</button>
        <button onclick="ex(2)">Run code</button>
        <button onclick="ex(3)">Search + calculate</button>
        <button onclick="ex(4)">Flagship task</button>
        <button onclick="ex(5)">Tool failure</button>
      </div>
    </div>
    <div id="out" class="hidden">
      <div class="card"><h3 style="margin-top:0">Answer</h3><div id="answer" class="answer"></div><p id="meta" class="muted"></p></div>
      <div class="card"><h3 style="margin-top:0">Agent steps (thought, tool call, tool result)</h3><div id="steps"></div></div>
    </div>
  </section>

  <section id="eval" class="hidden"><div class="card"><pre id="evalText">Loading...</pre></div></section>

  <section id="about" class="hidden"><div class="card">
    <h3 style="margin-top:0">Capabilities</h3>
    <p>Three tools: <b>web_search</b> (live facts), <b>calculator</b> (exact arithmetic), <b>python_executor</b> (runs small, safe Python programs). The agent chooses tools itself, can chain them, and recovers from tool errors.</p>
    <h3>Known limitations</h3>
    <ul>
      <li>Web search can fail or return unrelated pages; the agent then retries or says it could not find anything.</li>
      <li>The model occasionally produces an invalid tool call, which ends that run with an error message.</li>
      <li>The code runner only allows simple computations (no files, network or system access).</li>
      <li>It may pick an older figure even when a newer one appears in search results.</li>
      <li>Answers can take 10-40 seconds. The first request after idle time is slower.</li>
    </ul>
  </div></section>
</main>
<script>
const EXAMPLES = [
  "What is the capital of France?",
  "What is 98765432123 * 12345678987?",
  "Run Python to find how many prime numbers are below 100000.",
  "Search the web for the height of Mount Everest in metres, then use the calculator to convert it to feet (multiply by 3.28084).",
  "Look up the population of India, calculate what 5% of it is, then write a 3-sentence summary of your findings.",
  "Calculate 10 / 0."
];
const ICON = {thought:"THOUGHT (why)", call:"TOOL CALL (tool + input)", result:"TOOL RESULT", final:"FINAL ANSWER"};
function ex(i){ document.getElementById('q').value = EXAMPLES[i]; }
function show(name){
  for (const n of ['agent','eval','about']) {
    document.getElementById(n).classList.toggle('hidden', n !== name);
    document.getElementById('tab' + n[0].toUpperCase() + n.slice(1)).classList.toggle('active', n === name);
  }
  if (name === 'eval') loadEval();
}
async function loadEval(){
  const el = document.getElementById('evalText');
  try { const r = await fetch('/api/results'); el.textContent = (await r.json()).markdown; }
  catch(e){ el.textContent = 'Could not load results.'; }
}
async function ask(){
  const q = document.getElementById('q').value.trim();
  if (!q) return;
  const go = document.getElementById('go'), st = document.getElementById('status');
  go.disabled = true; st.textContent = 'The agent is working (10-40 seconds)...';
  document.getElementById('out').classList.add('hidden');
  try {
    const r = await fetch('/api/ask', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({question:q, persona:document.getElementById('persona').value})});
    const raw = await r.text();
    let data;
    try { data = JSON.parse(raw); }
    catch (e) { throw new Error('The server did not finish in time or crashed. Server said: ' + raw.slice(0, 200) + ' (please try again)'); }
    if (!r.ok) throw new Error(data.detail || 'Request failed');
    const ans = document.getElementById('answer');
    ans.textContent = data.answer || '(no answer)';
    ans.classList.toggle('err', !!data.error);
    document.getElementById('meta').textContent =
      data.n_tool_calls + ' tool call(s) | ' + data.seconds + ' s' + (data.error ? ' | handled error: ' + data.error : '');
    const steps = document.getElementById('steps'); steps.innerHTML = '';
    if (!data.trace.length) steps.textContent = 'No tools were used. The agent answered directly.';
    for (const s of data.trace) {
      const d = document.createElement('div'); d.className = 'step ' + s.kind;
      const b = document.createElement('b'); b.textContent = ICON[s.kind] || s.kind;
      d.appendChild(b); d.appendChild(document.createTextNode(s.text)); steps.appendChild(d);
    }
    document.getElementById('out').classList.remove('hidden');
  } catch(e) {
    document.getElementById('answer').textContent = 'Error: ' + e.message;
    document.getElementById('answer').classList.add('err');
    document.getElementById('steps').innerHTML = '';
    document.getElementById('meta').textContent = '';
    document.getElementById('out').classList.remove('hidden');
  } finally { go.disabled = false; st.textContent = ''; }
}
</script>
</body>
</html>"""
