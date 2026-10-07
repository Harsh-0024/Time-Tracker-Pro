from __future__ import annotations

from typing import List, Optional

import sqlite3

from ..db import get_db_connection


def list_users(db_name: str) -> List[sqlite3.Row]:
    conn = get_db_connection(db_name)
    users = conn.execute(
        """
        SELECT u.id, u.name, u.user_id, u.email, u.role, u.is_verified, u.created_at,
               COALESCE(l.log_count, 0) AS log_count, l.last_log_date
        FROM users u
        LEFT JOIN (
            SELECT user_id, COUNT(*) AS log_count, MAX(start_date) AS last_log_date
            FROM logs GROUP BY user_id
        ) l ON l.user_id = u.id
        ORDER BY u.created_at DESC
        """
    ).fetchall()
    conn.close()
    return list(users or [])


# Tables whose ``user_id`` column references ``users.id``. (``users.user_id`` itself is the
# public handle, so ``users`` is deleted separately by primary key.)
_USER_OWNED_TABLES = (
    "logs",
    "graph_search_history",
    "graph_bookmarks",
    "user_settings",
    "email_verifications",
    "sheety_api_accounts",
    "sheety_outbox",
    "sheet_rewrite_state",
    "user_goals",
)


def _existing_tables(conn: sqlite3.Connection) -> set:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {row[0] for row in rows}


def delete_user_cascade(db_name: str, target_id: int) -> None:
    uid = int(target_id)
    conn = get_db_connection(db_name)
    try:
        tables = _existing_tables(conn)
        if "sheety_sync_snapshots" in tables:
            if "sheety_sync_snapshot_rows" in tables:
                conn.execute(
                    "DELETE FROM sheety_sync_snapshot_rows WHERE snapshot_id IN "
                    "(SELECT id FROM sheety_sync_snapshots WHERE user_id = ?)",
                    (uid,),
                )
            conn.execute("DELETE FROM sheety_sync_snapshots WHERE user_id = ?", (uid,))
        for table in _USER_OWNED_TABLES:
            if table in tables:
                conn.execute(f"DELETE FROM {table} WHERE user_id = ?", (uid,))
        conn.execute("DELETE FROM users WHERE id = ?", (uid,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
