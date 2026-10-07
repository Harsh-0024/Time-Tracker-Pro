from __future__ import annotations

from datetime import datetime, date
from typing import Any, Dict, List

import pandas as pd

from ..db import get_db_connection
from ..core.tags import filter_special_tags


def get_first_log_date(db_name: str, user_id: int) -> date | None:
    conn = get_db_connection(db_name)
    try:
        row = conn.execute(
            "SELECT MIN(start_date) AS min_date FROM logs WHERE user_id = ?",
            (int(user_id),),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    try:
        value = row["min_date"]
    except Exception:
        value = None
    if not value:
        return None
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except Exception:
        return None


def _combine_datetimes(dates: pd.Series, times: pd.Series) -> pd.Series:
    """Parse ``"<date> <time>"`` strings exactly like a per-row ``pd.to_datetime`` call.

    The canonical stored format is parsed in one vectorised pass; anything else falls
    back to the scalar parser so unusual values behave (and fail) as they always have.
    """
    combined = dates.astype(str) + " " + times.astype(str)
    parsed = pd.to_datetime(combined, format="%Y-%m-%d %H:%M:%S", errors="coerce")
    unparsed = parsed.isna()
    if unparsed.any():
        parsed = parsed.astype(object)
        for idx in parsed.index[unparsed]:
            parsed.at[idx] = pd.to_datetime(f"{dates.at[idx]} {times.at[idx]}")
        parsed = pd.to_datetime(parsed)
    return parsed


def _clock_labels(values: pd.Series) -> List[Any]:
    """Same as ``list(values.dt.strftime("%I:%M %p"))``, but each distinct clock time
    (at most 1440) is formatted once - per-row strftime was ~40% of a dashboard request.
    """
    if values.empty or values.isna().any():
        return list(values.dt.strftime("%I:%M %p"))
    minutes = (values.dt.hour * 60 + values.dt.minute).tolist()
    distinct = sorted(set(minutes))
    samples = pd.Series(pd.Timestamp(2000, 1, 1) + pd.to_timedelta(distinct, unit="m"))
    labels = dict(zip(distinct, samples.dt.strftime("%I:%M %p")))
    return [labels[m] for m in minutes]


def _clean_sheety_id(value: Any):
    if isinstance(value, float) and pd.isna(value):
        return None
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def fetch_local_data(db_name: str, user_id: int) -> pd.DataFrame:
    conn = get_db_connection(db_name)
    df = pd.read_sql_query(
        "SELECT * FROM logs WHERE user_id = ? ORDER BY start_date ASC, start_time ASC",
        conn,
        params=(int(user_id),),
    )
    conn.close()
    if df.empty:
        return pd.DataFrame()

    # Vectorised (this used to iterate with iterrows, ~1s per request for a few
    # thousand logs). Output columns, values and dtypes are unchanged.
    start = _combine_datetimes(df["start_date"], df["start_time"])
    end = _combine_datetimes(df["end_date"], df["end_time"])
    duration_minutes = ((end - start).dt.total_seconds() / 60.0).clip(lower=0.0)
    # Only a handful of distinct tag strings exist, so parse each once (was ~40% of this function).
    parsed_tags: Dict[Any, List[str]] = {}
    special_tags = []
    for raw in df["tags"]:
        if raw not in parsed_tags:
            parsed_tags[raw] = filter_special_tags(raw)
        special_tags.append(list(parsed_tags[raw]))

    final_rows: Dict[str, List[Any]] = {
        "id": list(df["id"]),
        "sheety_id": [_clean_sheety_id(v) for v in df["sheety_id"]] if "sheety_id" in df.columns else [None] * len(df),
        "date": list(start.dt.date),
        "start_time": _clock_labels(start),
        "end_time": _clock_labels(end),
        "start_datetime": list(start),
        "end_datetime": list(end),
        "task": list(df["task"]),
        "duration": [float(v) for v in duration_minutes],
        "tag": [", ".join(tags) if tags else "Waste" for tags in special_tags],
        "raw_tag": list(df["tags"]),
        "primary_tag": [tags[0] if tags else "Waste" for tags in special_tags],
        "special_tags": special_tags,
        "urgent": [bool(v) for v in df["urg"]],
        "important": [bool(v) for v in df["imp"]],
    }
    return pd.DataFrame(final_rows)


def replace_logs_for_user(db_name: str, user_id: int, final_rows: List[Dict[str, Any]]) -> int:
    if not final_rows:
        return 0

    conn = get_db_connection(db_name)
    inserted_count = 0
    try:
        conn.execute("DELETE FROM logs WHERE user_id = ?", (int(user_id),))

        for p in final_rows:
            duration = int((p["end_dt"] - p["start_dt"]).total_seconds() / 60)
            if duration <= 0:
                continue
            conn.execute(
                """
                INSERT INTO logs (
                    sheety_id, start_date, start_time, end_date, end_time,
                    task, duration, tags, urg, imp, user_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    p.get("sheety_id"),
                    p["start_dt"].strftime("%Y-%m-%d"),
                    p["start_dt"].strftime("%H:%M:%S"),
                    p["end_dt"].strftime("%Y-%m-%d"),
                    p["end_dt"].strftime("%H:%M:%S"),
                    p["task"],
                    duration,
                    p["tag"],
                    1 if p.get("urg") else 0,
                    1 if p.get("imp") else 0,
                    int(user_id),
                ),
            )
            inserted_count += 1

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return inserted_count
