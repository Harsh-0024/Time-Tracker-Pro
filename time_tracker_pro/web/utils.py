from __future__ import annotations

import hashlib
import re
from typing import Optional

from flask import request, session


_VERSION_NUMBERS = re.compile(r"\d+(?:[._]\d+)*")


def _ua_family(value: str) -> str:
    """The User-Agent without version numbers ('Chrome/131.0.6778.86' -> 'Chrome/').

    Sessions are bound to the browser + OS, not its exact version, so an automatic
    browser update doesn't log everyone out; a different browser or device still does.
    """
    return _VERSION_NUMBERS.sub("", value or "")


def _ua_hash(value: str) -> str:
    return hashlib.sha256(("v2:" + _ua_family(value)).encode("utf-8")).hexdigest()


def _legacy_ua_hash(value: str) -> str:
    # Sessions created before versions were ignored hashed the full User-Agent.
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


def safe_next_url(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    # Browsers treat '\\' like '/' and drop tabs/newlines, so '/\\evil.com' or '/\t/evil.com'
    # would become the protocol-relative '//evil.com' (open redirect).
    if any(ch == "\\" or ord(ch) < 32 or ord(ch) == 127 for ch in raw):
        return None
    if raw.startswith("/") and not raw.startswith("//"):
        return raw
    return None


def get_current_user_id() -> Optional[int]:
    uid = session.get("user_id")
    if uid is None:
        return None
    expected = session.get("ua_hash")
    user_agent = request.headers.get("User-Agent") or ""
    current = _ua_hash(user_agent)
    if expected and expected != current and expected == _legacy_ua_hash(user_agent):
        session["ua_hash"] = current  # upgrade an old session in place
        expected = current
    if not expected or expected != current:
        session.clear()
        return None
    try:
        return int(uid)
    except Exception:
        return None


def request_date_param(name: str = "date"):
    """parse_date_param for a query arg, but treat absurd years (0001, 9999) like a bad
    value: they overflow pandas timestamps / month arithmetic and 500 the page."""
    from ..core.dates import parse_date_param

    value = parse_date_param(request.args.get(name))
    if not 1900 <= value.year <= 2200:
        return parse_date_param(None)
    return value


def mask_email(email: Optional[str]) -> str:
    """'harsh@gmail.com' -> 'h•••h@gmail.com'. Forgot-password takes a public user ID,
    so showing the full address would reveal anyone's email."""
    value = (email or "").strip()
    local, sep, domain = value.partition("@")
    if not sep:
        return value
    if len(local) <= 2:
        masked = local[:1] + "•••"
    else:
        masked = local[0] + "•••" + local[-1]
    return f"{masked}@{domain}"
