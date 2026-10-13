"""Run a few pure helpers from the page scripts in Node, so their logic is tested
(test_inline_js.py only checks that the scripts parse)."""
import json
import os
import shutil
import subprocess

import pytest

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node not installed")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _function_source(rel_path: str, name: str) -> str:
    """Source of `function name(...) {...}` from a static script (brace matching)."""
    with open(os.path.join(ROOT, "static", rel_path), encoding="utf-8") as fh:
        text = fh.read()
    start = text.index(f"function {name}(")
    depth = 0
    for i in range(text.index("{", start), len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    raise AssertionError(f"unbalanced braces in {name}")


def _run(sources, expression):
    script = "\n".join(sources) + f"\nprocess.stdout.write(JSON.stringify({expression}));"
    out = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_moving_average_skips_missing_nights_only_when_asked():
    src = _function_source("js/pages/graphs.js", "movingAverage")
    assert _run([src], "movingAverage([2, 4, 0, 6], 2)") == [2, 3, 2, 3]
    # Sleep: zeros are missing nights, a window with none left is a gap (null).
    assert _run([src], "movingAverage([8, 0, 6, 0, 0], 2, true)") == [8, 8, 6, 6, None]


def test_tag_badge_text_colour_is_lightened_only_in_dark_mode():
    src = _function_source("js/pages/dashboard.js", "tagBadgeTextColor")
    stub = "const document = { documentElement: { getAttribute: () => globalThis.__theme } };"
    assert _run([stub, src], "(globalThis.__theme = 'light', tagBadgeTextColor('#DC2626'))") == "#DC2626"
    assert _run([stub, src], "(globalThis.__theme = 'dark', tagBadgeTextColor('#DC2626'))") == "rgb(236, 136, 136)"
    assert _run([stub, src], "(globalThis.__theme = 'dark', tagBadgeTextColor('not-a-colour'))") == "not-a-colour"
