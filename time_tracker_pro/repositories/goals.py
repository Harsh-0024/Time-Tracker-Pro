from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

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


# Per-category goals: "at least" (min) or "at most" (max) hours a day for one of
# the five special tags, judged on each log's primary tag (like the category chart).
GOAL_TAGS = ("Work", "Soul", "Rest", "Necessity", "Waste")
GOAL_KINDS = ("min", "max")


def get_tag_goals(db_name: str, user_id: int) -> List[Dict[str, object]]:
    conn = get_db_connection(db_name)
    try:
        rows = conn.execute(
            "SELECT tag, kind, hours FROM user_tag_goals WHERE user_id = ?",
            (int(user_id),),
        ).fetchall()
    finally:
        conn.close()
    order = {tag: i for i, tag in enumerate(GOAL_TAGS)}
    goals = [
        {"tag": r["tag"], "kind": r["kind"], "hours": float(r["hours"])}
        for r in rows
        if r["tag"] in order and r["kind"] in GOAL_KINDS
    ]
    return sorted(goals, key=lambda g: order[g["tag"]])


def parse_tag_goals(form) -> List[Dict[str, object]]:
    """Read ``tag_goal_kind_<Tag>`` / ``tag_goal_hours_<Tag>`` fields.

    A blank kind means no goal for that tag. Raises ValueError (user-facing
    message) for a kind without hours or hours outside 0-24.
    """
    goals: List[Dict[str, object]] = []
    for tag in GOAL_TAGS:
        kind = (form.get(f"tag_goal_kind_{tag}") or "").strip().lower()
        raw_hours = (form.get(f"tag_goal_hours_{tag}") or "").strip()
        if not kind:
            continue
        if kind not in GOAL_KINDS:
            raise ValueError(f"Unknown goal type for {tag}.")
        if not raw_hours:
            raise ValueError(f"Enter the hours for your {tag} goal (or set it to Off).")
        try:
            hours = parse_goal_hours(raw_hours)
        except ValueError:
            raise ValueError("Goals must be numbers of hours between 0 and 24.") from None
        goals.append({"tag": tag, "kind": kind, "hours": hours})
    return goals


def replace_tag_goals(db_name: str, user_id: int, goals: List[Dict[str, object]]) -> None:
    conn = get_db_connection(db_name)
    try:
        conn.execute("DELETE FROM user_tag_goals WHERE user_id = ?", (int(user_id),))
        conn.executemany(
            "INSERT INTO user_tag_goals (user_id, tag, kind, hours) VALUES (?, ?, ?, ?)",
            [(int(user_id), g["tag"], g["kind"], float(g["hours"])) for g in goals],
        )
        conn.commit()
    finally:
        conn.close()
