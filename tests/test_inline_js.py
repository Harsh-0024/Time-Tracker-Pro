"""Syntax-check every inline <script> on the rendered pages (needs Node; skipped without it).

Templates mix Jinja and JavaScript, so a stray brace or quote in an edit can silently break a
whole page's interactivity while every server-side test still passes.
"""
import os
import re
import shutil
import subprocess
import tempfile

import pytest

from conftest import add_log, make_user

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node not installed")

SCRIPT_RE = re.compile(r'<script(?![^>]*\bsrc=)(?![^>]*type="application/json")[^>]*>(.*?)</script>', re.S)

LOGGED_IN_PAGES = [
    "/?date=2026-09-20",
    "/?date=2026-09-20&period=week",
    "/?date=2026-09-20&period=month",
    "/graphs",
    "/settings",
    "/admin/users",
    "/no-such-page",
]
ANON_PAGES = ["/login", "/register", "/forgot-password"]


def _check(html: str, label: str) -> None:
    scripts = SCRIPT_RE.findall(html)
    assert scripts or label.startswith("/no-such"), f"no inline scripts found on {label}"
    for i, body in enumerate(scripts):
        fd, path = tempfile.mkstemp(suffix=".js")
        try:
            with os.fdopen(fd, "w") as fh:
                fh.write(body)
            result = subprocess.run([NODE, "--check", path], capture_output=True, text=True, timeout=30)
        finally:
            os.remove(path)
        assert result.returncode == 0, f"{label} script #{i}: {result.stderr[:500]}"


def test_inline_scripts_parse(db_path, login, app):
    uid = make_user(db_path, role="admin")
    add_log(db_path, uid, "2026-09-20", "09:00:00", "2026-09-20", "10:00:00", task="Work")
    client = login(uid)
    for url in LOGGED_IN_PAGES:
        _check(client.get(url).get_data(as_text=True), url)
    anon = app.test_client()
    for url in ANON_PAGES:
        _check(anon.get(url).get_data(as_text=True), url)
