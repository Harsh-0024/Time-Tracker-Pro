from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional

from ..db import get_db_connection

# kind -> (label, short label)
FEEDBACK_KINDS = {
    "like": ("Something I like", "Like"),
    "dislike": ("Something I don't like", "Don't like"),
    "improve": ("Could be better", "Improve"),
    "idea": ("A feature idea", "Idea"),
}
FEEDBACK_STATUSES = ("new", "seen", "done")
MAX_FEEDBACK_LENGTH = 2000


def clean_feedback(kind: Optional[str], message: Optional[str]) -> tuple:
    """Validate what was sent. Raises ValueError with a message for the person."""
    kind = str(kind or "").strip().lower()
    text = str(message or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if kind not in FEEDBACK_KINDS:
        raise ValueError("Choose what kind of feedback this is.")
    if not text:
        raise ValueError("Write a few words first.")
    if len(text) > MAX_FEEDBACK_LENGTH:
        raise ValueError(f"Please keep it under {MAX_FEEDBACK_LENGTH} characters.")
    return kind, text


def _as_dict(row) -> Dict:
    item = dict(row)
    label, short = FEEDBACK_KINDS.get(item.get("kind"), FEEDBACK_KINDS["idea"])
    item["kind_label"] = label
    item["kind_short"] = short
    return item


def add_feedback(db_name: str, user_id: int, kind: str, message: str) -> int:
    conn = get_db_connection(db_name)
    try:
        cur = conn.execute(
            "INSERT INTO feedback (user_id, kind, message, status, created_at) VALUES (?, ?, ?, 'new', ?)",
            (int(user_id), kind, message, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def list_user_feedback(db_name: str, user_id: int, limit: int = 20) -> List[Dict]:
    conn = get_db_connection(db_name)
    try:
        rows = conn.execute(
            "SELECT id, kind, message, status, created_at FROM feedback WHERE user_id = ? "
            "ORDER BY created_at DESC, id DESC LIMIT ?",
            (int(user_id), int(limit)),
        ).fetchall()
    finally:
        conn.close()
    return [_as_dict(row) for row in rows]


def list_all_feedback(db_name: str) -> List[Dict]:
    """Everyone's feedback with who sent it, newest first (for admins)."""
    conn = get_db_connection(db_name)
    try:
        rows = conn.execute(
            """
            SELECT f.id, f.kind, f.message, f.status, f.created_at, f.user_id,
                   u.name, u.username, u.user_id AS handle, u.email
            FROM feedback f
            JOIN users u ON u.id = f.user_id
            ORDER BY f.created_at DESC, f.id DESC
            """
        ).fetchall()
    finally:
        conn.close()
    return [_as_dict(row) for row in rows]


def feedback_counts(db_name: str) -> Dict[str, int]:
    conn = get_db_connection(db_name)
    try:
        by_status = dict(conn.execute("SELECT status, COUNT(*) FROM feedback GROUP BY status").fetchall())
        by_kind = dict(conn.execute("SELECT kind, COUNT(*) FROM feedback GROUP BY kind").fetchall())
    finally:
        conn.close()
    counts = {"total": sum(by_status.values())}
    counts.update({status: by_status.get(status, 0) for status in FEEDBACK_STATUSES})
    counts.update({kind: by_kind.get(kind, 0) for kind in FEEDBACK_KINDS})
    return counts


def mark_feedback_seen(db_name: str, ids: Iterable[int]) -> None:
    ids = [int(i) for i in ids]
    if not ids:
        return
    conn = get_db_connection(db_name)
    try:
        conn.execute(
            f"UPDATE feedback SET status = 'seen' WHERE status = 'new' AND id IN ({','.join('?' * len(ids))})",
            ids,
        )
        conn.commit()
    finally:
        conn.close()


def set_feedback_status(db_name: str, feedback_id: int, status: str) -> bool:
    if status not in FEEDBACK_STATUSES:
        raise ValueError("Unknown status.")
    conn = get_db_connection(db_name)
    try:
        cur = conn.execute("UPDATE feedback SET status = ? WHERE id = ?", (status, int(feedback_id)))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def delete_feedback(db_name: str, feedback_id: int) -> bool:
    conn = get_db_connection(db_name)
    try:
        cur = conn.execute("DELETE FROM feedback WHERE id = ?", (int(feedback_id),))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()
