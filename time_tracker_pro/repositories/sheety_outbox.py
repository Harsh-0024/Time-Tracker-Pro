from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from ..db import get_db_connection


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_rewrite_state_row(conn, user_id: int) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO sheet_rewrite_state (user_id, in_progress) VALUES (?, 0)",
        (int(user_id),),
    )


def is_rewrite_in_progress(db_name: str, user_id: int) -> bool:
    conn = get_db_connection(db_name)
    _ensure_rewrite_state_row(conn, int(user_id))
    row = conn.execute(
        "SELECT in_progress FROM sheet_rewrite_state WHERE user_id = ?",
        (int(user_id),),
    ).fetchone()
    conn.close()
    if not row:
        return False
    return bool(row["in_progress"])


def try_begin_rewrite(db_name: str, user_id: int) -> bool:
    conn = get_db_connection(db_name)
    _ensure_rewrite_state_row(conn, int(user_id))
    now = _utc_now_iso()
    cursor = conn.execute(
        """
        UPDATE sheet_rewrite_state
        SET in_progress = 1,
            started_at = ?
        WHERE user_id = ?
          AND (in_progress IS NULL OR in_progress = 0)
        """,
        (now, int(user_id)),
    )
    conn.commit()
    conn.close()
    return bool(cursor.rowcount)


def end_rewrite(db_name: str, user_id: int) -> None:
    conn = get_db_connection(db_name)
    _ensure_rewrite_state_row(conn, int(user_id))
    now = _utc_now_iso()
    conn.execute(
        "UPDATE sheet_rewrite_state SET in_progress = 0, finished_at = ? WHERE user_id = ?",
        (now, int(user_id)),
    )
    conn.commit()
    conn.close()


def sunday_week_key(now: datetime) -> str:
    current = now.astimezone(timezone.utc).date()
    days_since_sunday = (current.weekday() + 1) % 7
    sunday = current - timedelta(days=days_since_sunday)
    return sunday.isoformat()


def claim_weekly_run(db_name: str, user_id: int, week_key: str) -> bool:
    conn = get_db_connection(db_name)
    _ensure_rewrite_state_row(conn, int(user_id))
    now = _utc_now_iso()
    cursor = conn.execute(
        """
        UPDATE sheet_rewrite_state
        SET last_weekly_week = ?,
            last_weekly_run = ?
        WHERE user_id = ?
          AND (last_weekly_week IS NULL OR last_weekly_week != ?)
        """,
        (str(week_key), now, int(user_id), str(week_key)),
    )
    conn.commit()
    conn.close()
    return bool(cursor.rowcount)


def enqueue_outbox_operation(
    conn,
    user_id: int,
    method: str,
    endpoint: str,
    sheet_key: Optional[str],
    json_obj: Dict[str, Any],
    queued_during_rewrite: bool,
) -> int:
    now = _utc_now_iso()
    cursor = conn.execute(
        """
        INSERT INTO sheety_outbox (
            user_id, method, endpoint, json_data, sheet_key,
            queued_during_rewrite, attempts, status, last_error, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, 0, 'pending', NULL, ?, ?)
        """,
        (
            int(user_id),
            str(method or "").upper(),
            str(endpoint or ""),
            json.dumps(json_obj, separators=(",", ":"), ensure_ascii=False),
            (str(sheet_key) if sheet_key else None),
            1 if queued_during_rewrite else 0,
            now,
            now,
        ),
    )
    return int(cursor.lastrowid)


def fetch_pending_outbox(db_name: str, user_id: int, limit: int = 200) -> List[Dict[str, Any]]:
    conn = get_db_connection(db_name)
    rows = conn.execute(
        """
        SELECT id, method, endpoint, json_data, sheet_key, attempts
        FROM sheety_outbox
        WHERE user_id = ? AND status = 'pending'
        ORDER BY id ASC
        LIMIT ?
        """,
        (int(user_id), int(limit)),
    ).fetchall()
    conn.close()
    pending: List[Dict[str, Any]] = []
    for row in rows:
        pending.append(
            {
                "id": int(row["id"]),
                "method": row["method"],
                "endpoint": row["endpoint"] or "",
                "json_data": row["json_data"] or "{}",
                "sheet_key": row["sheet_key"],
                "attempts": int(row["attempts"] or 0),
            }
        )
    return pending


def mark_outbox_done(db_name: str, outbox_id: int) -> None:
    conn = get_db_connection(db_name)
    now = _utc_now_iso()
    conn.execute(
        """
        UPDATE sheety_outbox
        SET status = 'done',
            last_error = NULL,
            updated_at = ?
        WHERE id = ?
        """,
        (now, int(outbox_id)),
    )
    conn.commit()
    conn.close()


def mark_outbox_failed(db_name: str, outbox_id: int, error: str) -> None:
    conn = get_db_connection(db_name)
    now = _utc_now_iso()
    row = conn.execute(
        "SELECT attempts FROM sheety_outbox WHERE id = ?",
        (int(outbox_id),),
    ).fetchone()
    attempts = int(row["attempts"] if row else 0) + 1
    status = "failed" if attempts >= 5 else "pending"
    conn.execute(
        """
        UPDATE sheety_outbox
        SET attempts = ?,
            status = ?,
            last_error = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (attempts, status, (error or "")[:500], now, int(outbox_id)),
    )
    conn.commit()
    conn.close()


def update_local_sheety_id_for_created(
    db_name: str,
    user_id: int,
    match_fields: Dict[str, Any],
    sheety_id: int,
) -> bool:
    start_date = str(match_fields.get("start_date") or "").strip()
    start_time = str(match_fields.get("start_time") or "").strip()
    end_date = str(match_fields.get("end_date") or "").strip()
    end_time = str(match_fields.get("end_time") or "").strip()
    task = str(match_fields.get("task") or "").strip()

    if not (start_date and start_time and end_date and end_time and task):
        return False

    conn = get_db_connection(db_name)
    cursor = conn.execute(
        """
        UPDATE logs
        SET sheety_id = ?
        WHERE id = (
            SELECT id
            FROM logs
            WHERE user_id = ?
              AND sheety_id IS NULL
              AND start_date = ?
              AND start_time = ?
              AND end_date = ?
              AND end_time = ?
              AND task = ?
            ORDER BY id DESC
            LIMIT 1
        )
        """,
        (
            int(sheety_id),
            int(user_id),
            start_date,
            start_time,
            end_date,
            end_time,
            task,
        ),
    )
    conn.commit()
    conn.close()
    return bool(cursor.rowcount)
