"""Step 1 of the task: test each tool on its own, with no LLM.  Run:  python -m toolagent.test_tools"""
from toolagent import tools as T


def test_calculator():
    assert T.calculate("98765432123 * 12345678987") == str(98765432123 * 12345678987)
    assert T.calculate("2**100") == str(2 ** 100)
    assert T.calculate("sqrt(144)") == "12"
    assert T.calculate("8,450 * 0.15") == "1267.5"
    assert T.calculate("factorial(17)") == "355687428096000"


def test_calculator_errors_do_not_raise():
    assert T.calculate("10 / 0").startswith("ERROR")
    assert T.calculate("5 +* 3").startswith("ERROR")
    assert T.calculate("__import__('os').system('echo hacked')").startswith("ERROR")  # no code injection
    assert T.calculate("9 ** 99999999").startswith("ERROR")


def test_python_executor():
    assert T.run_python("print(sum(range(10)))") == "45"
    assert "ZeroDivisionError" in T.run_python("print(1/0)")
    assert T.run_python("while True: pass", timeout=1).startswith("ERROR: code timed out")
    assert "printed nothing" in T.run_python("x = 1")


def test_safe_mode_blocks_dangerous_code():
    assert "blocked for safety" in T.run_python("import os\nprint(os.environ)")
    assert "blocked for safety" in T.run_python("print(open('x').read())")
    assert "blocked for safety" in T.run_python("print(().__class__)")
    assert "blocked for safety" in T.run_python("import subprocess")
    assert T.run_python("import math\nprint(math.sqrt(16))") == "4.0"
    assert T.run_python("import hashlib\nprint(hashlib.sha256(b'hello world').hexdigest()[:16])") == "b94d27b9934d3e08"


def test_search_results_are_short():
    hits = [{"title": "T" * 500, "body": "B" * 5000, "href": "https://x.com/" + "h" * 500}] * 3
    out = T._format_hits(hits)
    assert len(out) < 1600, len(out)


def test_search_never_raises():
    assert isinstance(T.web_search("python latest version"), str)  # results, NO_RESULTS or ERROR


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    print("All tool tests passed.")
