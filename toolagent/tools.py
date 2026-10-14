"""Plain-Python tools (no LangChain here, so each one can be tested on its own).

Rule: a tool NEVER raises. On failure it returns a string starting with "ERROR" or "NO_RESULTS",
so the agent can read it and recover instead of crashing.
"""
import ast
import math
import operator
import os
import re
import subprocess
import sys
import tempfile

# ----------------------------------------------------------------------------------------------
# 1) Calculator: exact arithmetic with a safe expression evaluator (no eval()).
# ----------------------------------------------------------------------------------------------
_BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
        ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod, ast.Pow: operator.pow}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FUNCS = {"sqrt": math.sqrt, "log": math.log, "log10": math.log10, "sin": math.sin,
          "cos": math.cos, "tan": math.tan, "factorial": math.factorial, "abs": abs, "round": round}
_CONSTS = {"pi": math.pi, "e": math.e}


def _eval(node):
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) \
            and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.Name) and node.id in _CONSTS:
        return _CONSTS[node.id]
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_eval(node.operand))
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow):
            if abs(right) > 10_000:
                raise ValueError("exponent too large")
            if isinstance(left, int) and isinstance(right, int) and right > 0 \
                    and left.bit_length() * right > 200_000:
                raise ValueError("result would be too large")
        return _BIN[type(node.op)](left, right)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
            and node.func.id in _FUNCS and not node.keywords:
        args = [_eval(a) for a in node.args]
        if node.func.id == "factorial" and (not isinstance(args[0], int) or args[0] > 5000):
            raise ValueError("factorial needs an integer <= 5000")
        return _FUNCS[node.func.id](*args)
    raise ValueError("unsupported syntax")


def _fmt(x):
    if isinstance(x, int):
        return str(x)
    if isinstance(x, float):
        if x.is_integer() and abs(x) < 1e15:
            return str(int(x))
        return f"{x:.12g}"
    return str(x)


def calculate(expression: str) -> str:
    """Evaluate a math expression exactly. Returns the result as text, or 'ERROR: ...'."""
    try:
        expr = expression.strip().replace("^", "**")
        expr = re.sub(r"(?<=\d),(?=\d{3}(?!\d))", "", expr)  # 8,450 -> 8450
        return _fmt(_eval(ast.parse(expr, mode="eval")))
    except ZeroDivisionError:
        return "ERROR: division by zero (the result is undefined)"
    except SyntaxError:
        return f"ERROR: could not parse the expression {expression!r}. Use plain math like '12 * (3 + 4)'."
    except Exception as e:  # ValueError, OverflowError, TypeError ...
        return f"ERROR: {type(e).__name__}: {e}"


# ----------------------------------------------------------------------------------------------
# 2) Python executor: actually runs code in a separate process with a time limit.
#    SAFE MODE (default ON, needed because the app is public): the code is checked first and may only
#    import harmless modules (math, hashlib, itertools ...). No files, network, os/sys or dunder tricks.
#    The child process also gets NO secret environment variables (API keys). This reduces risk but it is
#    still NOT a perfect sandbox. Set PY_SAFE_MODE=0 to turn the checks off for local experiments.
# ----------------------------------------------------------------------------------------------
_ALLOWED_IMPORTS = {"math", "itertools", "functools", "collections", "statistics", "hashlib", "random", "re",
                    "string", "decimal", "fractions", "datetime", "json", "heapq", "bisect", "operator",
                    "typing", "array", "base64", "textwrap", "numbers", "cmath"}
_BLOCKED_NAMES = {"open", "exec", "eval", "compile", "__import__", "input", "breakpoint", "globals", "locals",
                  "vars", "getattr", "setattr", "delattr", "memoryview", "exit", "quit", "help"}


def _check_code(code: str) -> None:
    """Raise ValueError if the code uses anything outside the small safe subset."""
    tree = ast.parse(code)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0] not in _ALLOWED_IMPORTS:
                    raise ValueError(f"import of '{a.name}' is not allowed")
        elif isinstance(node, ast.ImportFrom):
            if node.level or (node.module or "").split(".")[0] not in _ALLOWED_IMPORTS:
                raise ValueError(f"import from '{node.module}' is not allowed")
        elif isinstance(node, ast.Name) and node.id in _BLOCKED_NAMES:
            raise ValueError(f"'{node.id}' is not allowed")
        elif isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            raise ValueError("attribute names starting with '__' are not allowed")


def _clean_env() -> dict:
    bad = ("KEY", "TOKEN", "SECRET", "PASSWORD", "LLM_", "AWS_", "VERCEL")
    return {k: v for k, v in os.environ.items() if not any(b in k.upper() for b in bad)}


def run_python(code: str, timeout: int = 10) -> str:
    """Run Python code and return what it printed (stdout), or 'ERROR: ...'."""
    path = None
    try:
        if os.getenv("PY_SAFE_MODE", "1") != "0":
            try:
                _check_code(code)
            except SyntaxError as e:
                return f"ERROR: SyntaxError: {e.msg} (line {e.lineno})"
            except ValueError as e:
                return f"ERROR: blocked for safety: {e}. Only simple computations with modules like math, hashlib, itertools are allowed."
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write(code)
            path = f.name
        proc = subprocess.run([sys.executable, "-I", path], capture_output=True, text=True,
                              timeout=timeout, cwd=tempfile.gettempdir(), env=_clean_env())
        out = (proc.stdout or "").strip()
        if proc.returncode != 0:
            err = (proc.stderr or "").strip()[-1500:]
            return f"ERROR (exit code {proc.returncode}):\n{err}"
        if not out:
            return "(code ran fine but printed nothing; use print() to show the result)"
        return out[:3000]
    except subprocess.TimeoutExpired:
        return f"ERROR: code timed out after {timeout}s"
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"
    finally:
        if path and os.path.exists(path):
            os.remove(path)


# ----------------------------------------------------------------------------------------------
# 3) Web search: real-time information via DuckDuckGo (no API key needed).
# ----------------------------------------------------------------------------------------------
def _tavily(query: str, max_results: int):
    """Optional: used only if TAVILY_API_KEY is set (more reliable than DuckDuckGo on cloud servers)."""
    key = os.getenv("TAVILY_API_KEY")
    if not key:
        return None
    import json
    import urllib.request
    req = urllib.request.Request(
        "https://api.tavily.com/search",
        data=json.dumps({"query": query, "max_results": max_results}).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.load(r)
    return [{"title": h.get("title", ""), "body": h.get("content", ""), "href": h.get("url", "")}
            for h in data.get("results", [])]


def _format_hits(hits) -> str:
    """Short on purpose: long results burn the model's tokens-per-minute limit on free plans."""
    cut = lambda text, n: (text or "").replace("\n", " ").strip()[:n]
    return "\n".join(f"{i}. {cut(h.get('title'), 100)}\n   {cut(h.get('body'), 280)}\n   {cut(h.get('href'), 90)}"
                     for i, h in enumerate(hits, 1))


def web_search(query: str, max_results: int = 3) -> str:
    """Search the web. Returns numbered results, 'NO_RESULTS ...' or 'ERROR: ...'."""
    try:
        hits = _tavily(query, max_results)
        if hits:
            return _format_hits(hits)
    except Exception:
        pass  # fall back to DuckDuckGo below
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS
    except ImportError:
        return "ERROR: search package missing. Run: pip install ddgs"
    try:
        hits = list(DDGS().text(query, max_results=max_results))
    except Exception as e:
        return f"ERROR: search failed ({type(e).__name__}: {e})"
    if not hits:
        return f"NO_RESULTS for query {query!r}. Try rephrasing the query."
    return _format_hits(hits)
