from __future__ import annotations

from typing import Any, Dict, List

from ..db import get_db_connection


MAX_QUERY_LENGTH = 200  # same cap as saved graph views
MAX_FOCUS_LENGTH = 32
MAX_HISTORY_ROWS_PER_USER = 1000


def record_graph_search_combo(db_name: str, user_id: int, focus: str, search_query: str) -> None:
    focus_value = ((focus or "").strip().lower() or "total")[:MAX_FOCUS_LENGTH]
    query_value = " ".join(str(search_query or "").strip().split())[:MAX_QUERY_LENGTH]
    if not query_value:
        return

    conn = get_db_connection(db_name)
    try:
        conn.execute(
            """
            INSERT INTO graph_search_history (user_id, focus, search_query)
            VALUES (?, ?, ?)
            """,
            (int(user_id), focus_value, query_value),
        )
        # Suggestions only need recent history; don't let one user grow the table without bound.
        conn.execute(
            """
            DELETE FROM graph_search_history
            WHERE user_id = ? AND id NOT IN (
                SELECT id FROM graph_search_history WHERE user_id = ? ORDER BY id DESC LIMIT ?
            )
            """,
            (int(user_id), int(user_id), MAX_HISTORY_ROWS_PER_USER),
        )
        conn.commit()
    finally:
        conn.close()


def list_top_graph_search_combos(
    db_name: str,
    user_id: int,
    limit: int = 7,
) -> List[Dict[str, Any]]:
    safe_limit = max(1, min(int(limit or 7), 20))
    conn = get_db_connection(db_name)
    try:
        rows = conn.execute(
            """
            SELECT
                focus,
                search_query,
                COUNT(*) AS usage_count,
                MAX(created_at) AS last_used_at
            FROM graph_search_history
            WHERE user_id = ?
              AND COALESCE(TRIM(search_query), '') <> ''
            GROUP BY focus, search_query
            ORDER BY usage_count DESC, last_used_at DESC
            LIMIT ?
            """,
            (int(user_id), int(safe_limit)),
        ).fetchall()
    finally:
        conn.close()

    suggestions: List[Dict[str, Any]] = []
    for row in rows or []:
        suggestions.append(
            {
                "focus": str(row["focus"] or "").strip().lower(),
                "search": str(row["search_query"] or "").strip(),
                "count": int(row["usage_count"] or 0),
                "last_used_at": str(row["last_used_at"] or ""),
            }
        )
    return suggestions
