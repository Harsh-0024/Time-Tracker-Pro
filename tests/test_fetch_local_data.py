"""fetch_local_data was vectorised for speed; it must match the original row-by-row version."""
import sqlite3
from typing import Any, Dict, List

import pandas as pd
from pandas.testing import assert_frame_equal

from conftest import make_user
from time_tracker_pro.core.tags import filter_special_tags
from time_tracker_pro.repositories.logs import fetch_local_data


def _reference_fetch_local_data(db_name: str, user_id: int) -> pd.DataFrame:
    conn = sqlite3.connect(db_name)
    df = pd.read_sql_query(
        "SELECT * FROM logs WHERE user_id = ? ORDER BY start_date ASC, start_time ASC",
        conn,
        params=(int(user_id),),
    )
    conn.close()
    if df.empty:
        return pd.DataFrame()
    final_rows: List[Dict[str, Any]] = []
    for _, row in df.iterrows():
        start = pd.to_datetime(f"{row['start_date']} {row['start_time']}")
        end = pd.to_datetime(f"{row['end_date']} {row['end_time']}")
        duration_minutes = max(0.0, (end - start).total_seconds() / 60.0)
        sheety_id = row.get("sheety_id")
        if isinstance(sheety_id, float) and pd.isna(sheety_id):
            sheety_id = None
        elif sheety_id is not None:
            try:
                sheety_id = int(sheety_id)
            except (TypeError, ValueError):
                sheety_id = None
        special_tags = filter_special_tags(row["tags"])
        final_rows.append(
            {
                "id": row["id"],
                "sheety_id": sheety_id,
                "date": start.date(),
                "start_time": start.strftime("%I:%M %p"),
                "end_time": end.strftime("%I:%M %p"),
                "start_datetime": start,
                "end_datetime": end,
                "task": row["task"],
                "duration": duration_minutes,
                "tag": ", ".join(special_tags) if special_tags else "Waste",
                "raw_tag": row["tags"],
                "primary_tag": special_tags[0] if special_tags else "Waste",
                "special_tags": special_tags,
                "urgent": bool(row["urg"]),
                "important": bool(row["imp"]),
            }
        )
    return pd.DataFrame(final_rows)


def _insert(db_path, uid, rows):
    conn = sqlite3.connect(db_path)
    for r in rows:
        conn.execute(
            "INSERT INTO logs (sheety_id, start_date, start_time, end_date, end_time, task, duration, tags, urg, imp, user_id) "
            "VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?)",
            (*r, uid),
        )
    conn.commit()
    conn.close()


def test_matches_reference_on_edge_cases(db_path):
    uid = make_user(db_path)
    _insert(
        db_path,
        uid,
        [
            (12, "2026-09-20", "09:00:00", "2026-09-20", "10:30:00", "Normal", "Work", 0, 1),
            (None, "2026-09-20", "23:00:00", "2026-09-21", "01:15:00", "Overnight", "rest, soul", 1, 1),
            (13, "2026-09-21", "10:00:00", "2026-09-21", "09:00:00", "Negative", None, None, 0),
            (14, "2026-09-21", "07:05", "2026-09-21", "08:10", "No seconds", "necessity.", 0, None),
            (15, "2026-09-22", "12:00:00", "2026-09-22", "12:00:00", "Zero", "waste,work", 1, 0),
        ],
    )
    assert_frame_equal(_reference_fetch_local_data(db_path, uid), fetch_local_data(db_path, uid), check_exact=True)


def test_matches_reference_when_all_rows_synced(db_path):
    uid = make_user(db_path)
    _insert(
        db_path,
        uid,
        [
            (1, "2026-09-20", "09:00:00", "2026-09-20", "10:00:00", "A", "Work", 0, 1),
            (2, "2026-09-20", "10:00:00", "2026-09-20", "11:00:00", "B", "Soul", 1, 0),
        ],
    )
    assert_frame_equal(_reference_fetch_local_data(db_path, uid), fetch_local_data(db_path, uid), check_exact=True)


def test_empty(db_path):
    uid = make_user(db_path)
    assert fetch_local_data(db_path, uid).empty
