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
#    (A subprocess + timeout is fine for a learning project, but it is NOT a security sandbox.)
# ----------------------------------------------------------------------------------------------
def run_python(code: str, timeout: int = 10) -> str:
    """Run Python code and return what it printed (stdout), or 'ERROR: ...'."""
    path = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write(code)
            path = f.name
        proc = subprocess.run([sys.executable, "-I", path], capture_output=True, text=True,
                              timeout=timeout, cwd=tempfile.gettempdir())
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
def web_search(query: str, max_results: int = 5) -> str:
    """Search the web. Returns numbered results, 'NO_RESULTS ...' or 'ERROR: ...'."""
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
    lines = []
    for i, h in enumerate(hits, 1):
        lines.append(f"{i}. {h.get('title', '')}\n   {h.get('body', '')}\n   {h.get('href', '')}")
    return "\n".join(lines)
