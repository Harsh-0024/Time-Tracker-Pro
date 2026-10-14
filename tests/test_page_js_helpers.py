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


def test_tag_badge_text_colours_reach_aa_contrast_in_both_themes():
    src = _function_source("js/pages/dashboard.js", "tagBadgeTextColor")
    stub = "const document = { documentElement: { getAttribute: () => globalThis.__theme } };"
    helpers = """
    const lum = (c) => { const [r, g, b] = c.map(v => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
    const ratio = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
    const parse = (s) => s.startsWith('#') ? [1, 3, 5].map(i => parseInt(s.slice(i, i + 2), 16)) : s.match(/\\d+/g).map(Number);
    const tags = ['#10B981', '#F59E0B', '#6366F1', '#C4B5FD', '#DC2626'];
    const check = (theme, bg) => { globalThis.__theme = theme; return tags.map(t => Math.round(ratio(parse(tagBadgeTextColor(t)), bg) * 10) / 10); };
    """
    light = _run([stub, src, helpers], "check('light', [252, 250, 245])")
    dark = _run([stub, src, helpers], "check('dark', [22, 19, 16])")
    assert min(light) >= 4.5 and min(dark) >= 4.5, (light, dark)
    # A colour that already passes is left as it is; junk passes through.
    assert _run([stub, src], "(globalThis.__theme = 'light', tagBadgeTextColor('#111827'))") == "#111827"
    assert _run([stub, src], "(globalThis.__theme = 'dark', tagBadgeTextColor('not-a-colour'))") == "not-a-colour"
