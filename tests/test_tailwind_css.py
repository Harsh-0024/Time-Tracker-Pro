"""static/css/tailwind.css is prebuilt; fail if a template uses a Tailwind class it doesn't contain.

If this fails after adding classes, rebuild (see README > Styles):
    npx tailwindcss@3.4.17 -c tailwind.config.js -i static/css/tailwind.src.css -o static/css/tailwind.css --minify
"""
import glob
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

UTILITY = re.compile(
    r"^(?:[a-z0-9-]+:)*-?(?:"
    r"bg|text|border|p[xytrbl]?|m[xytrbl]?|w|h|min-w|min-h|max-w|max-h|gap|gap-[xy]|space-[xy]|rounded(?:-[a-z]+)?|"
    r"shadow|font|leading|tracking|items|justify|content|self|place|top|left|right|bottom|inset|z|opacity|"
    r"overflow(?:-[xy])?|whitespace|grid-cols|grid-rows|col|row|order|basis|grow|shrink|flex|ring|ring-offset|"
    r"translate-[xy]|scale|rotate|duration|ease|delay|cursor|select|divide|outline|backdrop|blur|animate|"
    r"pointer-events|break|line-clamp|list|object|aspect|decoration|underline-offset|accent|fill|stroke|from|via|to"
    r")(?:-.+)?$"
    r"|^(?:[a-z0-9-]+:)*(?:flex|grid|block|inline|inline-block|inline-flex|hidden|contents|table|absolute|relative|"
    r"fixed|sticky|truncate|uppercase|lowercase|capitalize|italic|underline|sr-only|not-sr-only|transition|"
    r"transform|grow|shrink|tabular-nums|antialiased|resize|border|rounded|shadow|ring|outline-none|invisible|visible|"
    r"tracking-tight|tracking-wide)$"
)


def _escape(token: str) -> str:
    out = []
    for i, ch in enumerate(token):
        if ch.isalnum() or ch in "-_":
            out.append(f"\\3{ch} " if i == 0 and ch.isdigit() else ch)
        elif ch == ",":
            out.append("\\2c ")
        else:
            out.append("\\" + ch)
    return "".join(out)


def test_template_classes_are_compiled():
    with open(os.path.join(ROOT, "static", "css", "tailwind.css"), encoding="utf-8") as fh:
        css = fh.read()
    missing = {}
    sources = glob.glob(os.path.join(ROOT, "templates", "*.html")) + glob.glob(
        os.path.join(ROOT, "static", "js", "**", "*.js"), recursive=True
    )
    for path in sources:
        with open(path, encoding="utf-8") as fh:
            source = fh.read()
        for match in re.finditer(r'class="([^"]*)"', source):
            value = re.sub(r"\{\{.*?\}\}|\{%.*?%\}|\$\{.*?\}", " ", match.group(1))
            for token in value.split():
                if not UTILITY.match(token) or token.endswith("-"):
                    continue
                if "." + _escape(token) not in css:
                    missing.setdefault(token, set()).add(os.path.basename(path))
    assert not missing, (
        "Tailwind classes used in templates but missing from static/css/tailwind.css "
        "(rebuild it, see README > Styles): " + ", ".join(sorted(missing))
    )
