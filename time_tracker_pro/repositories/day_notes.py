from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Dict, Optional

from ..db import get_db_connection

MAX_NOTE_LENGTH = 1000


def clean_note(text: Optional[str]) -> str:
    """Trim, normalise line endings and cap the length. Raises ValueError if too long."""
    value = str(text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if len(value) > MAX_NOTE_LENGTH:
        raise ValueError(f"Notes can be up to {MAX_NOTE_LENGTH} characters.")
    return value


def get_day_note(db_name: str, user_id: int, day: date) -> Optional[str]:
    conn = get_db_connection(db_name)
    try:
        row = conn.execute(
            "SELECT note FROM day_notes WHERE user_id = ? AND day = ?",
            (int(user_id), day.isoformat()),
        ).fetchone()
    finally:
        conn.close()
    return row["note"] if row else None


def get_day_notes(db_name: str, user_id: int, start: date, end: date) -> Dict[date, str]:
    """Notes for every day in [start, end], keyed by date."""
    conn = get_db_connection(db_name)
    try:
        rows = conn.execute(
            "SELECT day, note FROM day_notes WHERE user_id = ? AND day >= ? AND day <= ? ORDER BY day",
            (int(user_id), start.isoformat(), end.isoformat()),
        ).fetchall()
    finally:
        conn.close()
    notes: Dict[date, str] = {}
    for row in rows:
        try:
            notes[date.fromisoformat(row["day"])] = row["note"]
        except ValueError:
            continue
    return notes


def set_day_note(db_name: str, user_id: int, day: date, note: str) -> None:
    """Store the note for a day; an empty note deletes it."""
    conn = get_db_connection(db_name)
    try:
        if note:
            conn.execute(
                """
                INSERT INTO day_notes (user_id, day, note, updated_at) VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, day) DO UPDATE SET note = excluded.note, updated_at = excluded.updated_at
                """,
                (int(user_id), day.isoformat(), note, datetime.now(timezone.utc).isoformat()),
            )
        else:
            conn.execute("DELETE FROM day_notes WHERE user_id = ? AND day = ?", (int(user_id), day.isoformat()))
        conn.commit()
    finally:
        conn.close()
