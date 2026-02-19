from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from ..db import get_db_connection


logger = logging.getLogger(__name__)


def create_sheety_sync_snapshot(
    db_name: str,
    user_id: int,
    sheet_key: str,
    rows: List[Dict[str, Any]],
    keep_latest: int = 5,
) -> int:
    conn = get_db_connection(db_name)
    snapshot_id = 0
    try:
        cursor = conn.execute(
            "INSERT INTO sheety_sync_snapshots (user_id, sheet_key) VALUES (?, ?)",
            (int(user_id), str(sheet_key)),
        )
        snapshot_id = int(cursor.lastrowid)

        for pos, row in enumerate(rows):
            sheety_id = None
            if isinstance(row, dict) and row.get("id") is not None:
                raw_id = row.get("id")
                if isinstance(raw_id, float):
                    try:
                        if raw_id == raw_id:  # not NaN
                            sheety_id = int(raw_id)
                    except Exception:
                        sheety_id = None
                else:
                    try:
                        sheety_id = int(raw_id)
                    except Exception:
                        sheety_id = None

            json_data = json.dumps(row, separators=(",", ":"), ensure_ascii=False)
            conn.execute(
                """
                INSERT INTO sheety_sync_snapshot_rows (snapshot_id, position, sheety_id, json_data)
                VALUES (?, ?, ?, ?)
                """,
                (int(snapshot_id), int(pos), sheety_id, json_data),
            )

        if keep_latest and keep_latest > 0:
            stale_rows = conn.execute(
                """
                SELECT id
                FROM sheety_sync_snapshots
                WHERE user_id = ? AND sheet_key = ?
                ORDER BY created_at DESC, id DESC
                LIMIT -1 OFFSET ?
                """,
                (int(user_id), str(sheet_key), int(keep_latest)),
            ).fetchall()
            stale_ids = [int(r["id"]) for r in stale_rows if r and r["id"] is not None]
            for stale_id in stale_ids:
                conn.execute(
                    "DELETE FROM sheety_sync_snapshot_rows WHERE snapshot_id = ?",
                    (int(stale_id),),
                )
                conn.execute(
                    "DELETE FROM sheety_sync_snapshots WHERE id = ?",
                    (int(stale_id),),
                )

        conn.commit()
        return int(snapshot_id)
    finally:
        conn.close()


def get_latest_sheety_sync_snapshot_id(db_name: str, user_id: int, sheet_key: str) -> Optional[int]:
    conn = get_db_connection(db_name)
    try:
        row = conn.execute(
            """
            SELECT id
            FROM sheety_sync_snapshots
            WHERE user_id = ? AND sheet_key = ?
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (int(user_id), str(sheet_key)),
        ).fetchone()
        if not row:
            return None
        try:
            return int(row["id"])
        except Exception:
            return None
    finally:
        conn.close()


def fetch_sheety_sync_snapshot_rows(db_name: str, snapshot_id: int) -> List[Dict[str, Any]]:
    conn = get_db_connection(db_name)
    try:
        rows = conn.execute(
            """
            SELECT position, json_data
            FROM sheety_sync_snapshot_rows
            WHERE snapshot_id = ?
            ORDER BY position ASC
            """,
            (int(snapshot_id),),
        ).fetchall()
        result: List[Dict[str, Any]] = []
        for row in rows:
            raw = row["json_data"] if row and "json_data" in row.keys() else None
            if not raw:
                continue
            try:
                parsed = json.loads(raw)
            except Exception as exc:
                logger.warning("Failed to parse snapshot row json snapshot_id=%s error=%s", int(snapshot_id), exc)
                continue
            if isinstance(parsed, dict):
                result.append(parsed)
        return result
    finally:
        conn.close()
