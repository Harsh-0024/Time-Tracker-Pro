"""Saved graph views (focus + search + range + moving-average window).

Stored in the ``graph_bookmarks`` table; ``days`` = 0 means the "All" range.
"""
from __future__ import annotations

from typing import Any, Dict, List

from ..db import get_db_connection

ALLOWED_FOCUS = {
    "search_only", "work", "necessity", "soul", "rest", "waste",
    "important", "urgent", "q1", "q2", "q3", "q4", "total", "sleep",
}
ALLOWED_MA = {7, 14, 30, 48}
MAX_VIEWS_PER_USER = 20
MAX_NAME_LENGTH = 60
MAX_SEARCH_LENGTH = 200


def _row_to_view(row) -> Dict[str, Any]:
    days = int(row["days"] or 0)
    return {
        "id": int(row["id"]),
        "name": row["name"],
        "focus": row["focus"],
        "search": row["search_query"] or "",
        "range": "all" if days <= 0 else str(days),
        "ma": int(row["ma_window"] or 14),
    }


def list_graph_views(db_name: str, user_id: int) -> List[Dict[str, Any]]:
    conn = get_db_connection(db_name)
    try:
        rows = conn.execute(
            "SELECT * FROM graph_bookmarks WHERE user_id = ? ORDER BY id ASC LIMIT ?",
            (int(user_id), MAX_VIEWS_PER_USER),
        ).fetchall()
    finally:
        conn.close()
    return [_row_to_view(r) for r in rows]


def create_graph_view(
    db_name: str,
    user_id: int,
    name: str,
    focus: str,
    search: str,
    range_value: str,
    ma_window: int,
) -> Dict[str, Any]:
    """Validate and store a view. Raises ValueError with a user-facing message."""
    clean_name = " ".join(str(name or "").split())[:MAX_NAME_LENGTH]
    if not clean_name:
        raise ValueError("Give the view a name.")
    focus_value = str(focus or "").strip().lower()
    if focus_value not in ALLOWED_FOCUS:
        raise ValueError("Unknown graph focus.")
    search_value = " ".join(str(search or "").split())[:MAX_SEARCH_LENGTH]
    if focus_value == "search_only" and not search_value:
        raise ValueError("A search-only view needs a search.")
    raw_range = str(range_value or "").strip().lower()
    if raw_range == "all":
        days = 0
    else:
        try:
            days = int(raw_range)
        except ValueError:
            raise ValueError("Unknown time range.") from None
        if days <= 0 or days > 3660:
            raise ValueError("Unknown time range.")
    try:
        ma_value = int(ma_window)
    except (TypeError, ValueError, OverflowError):
        raise ValueError("Unknown moving-average window.") from None
    if ma_value not in ALLOWED_MA:
        raise ValueError("Unknown moving-average window.")

    conn = get_db_connection(db_name)
    try:
        count = conn.execute("SELECT COUNT(*) AS c FROM graph_bookmarks WHERE user_id = ?", (int(user_id),)).fetchone()["c"]
        if int(count) >= MAX_VIEWS_PER_USER:
            raise ValueError(f"You can keep up to {MAX_VIEWS_PER_USER} saved views. Delete one first.")
        cur = conn.execute(
            """
            INSERT INTO graph_bookmarks (user_id, name, focus, search_query, combo_enabled, days, ma_window)
            VALUES (?, ?, ?, ?, 0, ?, ?)
            """,
            (int(user_id), clean_name, focus_value, search_value or None, days, ma_value),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM graph_bookmarks WHERE id = ?", (cur.lastrowid,)).fetchone()
    finally:
        conn.close()
    return _row_to_view(row)


def delete_graph_view(db_name: str, user_id: int, view_id: int) -> bool:
    conn = get_db_connection(db_name)
    try:
        cur = conn.execute(
            "DELETE FROM graph_bookmarks WHERE id = ? AND user_id = ?",
            (int(view_id), int(user_id)),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()
