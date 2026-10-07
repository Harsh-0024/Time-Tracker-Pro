from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Optional

from ..db import get_db_connection

MAX_GOAL_HOURS = 24.0


def get_user_goals(db_name: str, user_id: int) -> Dict[str, Optional[float]]:
    conn = get_db_connection(db_name)
    try:
        row = conn.execute(
            "SELECT growth_hours, waste_limit_hours FROM user_goals WHERE user_id = ?",
            (int(user_id),),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return {"growth_hours": None, "waste_limit_hours": None}
    return {"growth_hours": row["growth_hours"], "waste_limit_hours": row["waste_limit_hours"]}


def parse_goal_hours(raw: Optional[str]) -> Optional[float]:
    """'' -> None (no goal). Raises ValueError for anything outside 0-24 hours."""
    text = (raw or "").strip()
    if not text:
        return None
    value = float(text)
    if value != value or value < 0 or value > MAX_GOAL_HOURS:  # NaN or out of range
        raise ValueError("Goals must be between 0 and 24 hours.")
    return round(value, 2) + 0.0  # + 0.0 turns "-0" into 0.0 (else the form shows "-0")


def upsert_user_goals(
    db_name: str,
    user_id: int,
    growth_hours: Optional[float],
    waste_limit_hours: Optional[float],
) -> None:
    conn = get_db_connection(db_name)
    try:
        conn.execute(
            """
            INSERT INTO user_goals (user_id, growth_hours, waste_limit_hours, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                growth_hours = excluded.growth_hours,
                waste_limit_hours = excluded.waste_limit_hours,
                updated_at = excluded.updated_at
            """,
            (int(user_id), growth_hours, waste_limit_hours, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()
