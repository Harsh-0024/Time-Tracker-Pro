from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from ..db import get_db_connection

# Password attempts are throttled per account identifier (not per IP: behind a proxy
# every client shares one address). Email-code login is not throttled here, so a
# locked-out owner can still get in.
MAX_FAILURES = int(os.getenv("LOGIN_MAX_FAILURES", "10"))
WINDOW_MINUTES = int(os.getenv("LOGIN_FAILURE_WINDOW_MINUTES", "15"))


def _key(identifier: str) -> str:
    return (identifier or "").strip().lower()


def _window_start() -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=WINDOW_MINUTES)).isoformat()


def is_locked_out(db_name: str, identifier: str) -> bool:
    key = _key(identifier)
    if not key or MAX_FAILURES <= 0:
        return False
    conn = get_db_connection(db_name)
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM login_failures WHERE identifier = ? AND created_at >= ?",
            (key, _window_start()),
        ).fetchone()
    finally:
        conn.close()
    return int(row["c"] if row else 0) >= MAX_FAILURES


def record_failure(db_name: str, identifier: str) -> None:
    key = _key(identifier)
    if not key:
        return
    conn = get_db_connection(db_name)
    try:
        conn.execute(
            "INSERT INTO login_failures (identifier, created_at) VALUES (?, ?)",
            (key, datetime.now(timezone.utc).isoformat()),
        )
        # Keep the table small: drop anything outside the window.
        conn.execute("DELETE FROM login_failures WHERE created_at < ?", (_window_start(),))
        conn.commit()
    finally:
        conn.close()


def clear_failures(db_name: str, identifier: str) -> None:
    key = _key(identifier)
    if not key:
        return
    conn = get_db_connection(db_name)
    try:
        conn.execute("DELETE FROM login_failures WHERE identifier = ?", (key,))
        conn.commit()
    finally:
        conn.close()
