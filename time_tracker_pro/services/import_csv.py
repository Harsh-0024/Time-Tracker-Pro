from __future__ import annotations

import re
from datetime import datetime
from io import StringIO
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from ..core.tags import normalize_tag
from ..repositories.logs import replace_logs_for_user
from .parser import TimeLogParser


def import_csv_content(db_name: str, user_id: int, csv_content: str) -> int:
    df = pd.read_csv(StringIO(csv_content))

    log_entry_col = None
    logged_time_col = None

    for col in df.columns:
        col_lower = col.lower().strip()
        if "logged" in col_lower and "time" in col_lower:
            logged_time_col = col
        elif (
            "log entry" in col_lower
            or "entry" in col_lower
            or "task" in col_lower
            or "details" in col_lower
            or "raw" in col_lower
            or col_lower == "colb"
        ):
            log_entry_col = col

    if log_entry_col is None:
        for col in df.columns:
            if col != logged_time_col:
                log_entry_col = col
                break

    if log_entry_col is None:
        raise ValueError("Could not identify log entry column in CSV")

    if logged_time_col:
        try:
            df["__logged_dt"] = pd.to_datetime(
                df[logged_time_col],
                errors="coerce",
                dayfirst=True,
            )
            df = df.sort_values(["__logged_dt"], kind="mergesort", na_position="last")
        except Exception:
            pass

    parser = TimeLogParser()
    parsed_rows: List[Dict[str, Any]] = []
    previous_end: Optional[datetime] = None
    seen_source_rows = set()

    def normalize_task_name(raw: Any) -> str:
        s = re.sub(r"\s+", " ", str(raw or "").strip())
        if not s:
            return "Unspecified"
        return s.title()

    for _, row in df.iterrows():
        log_entry_val = str(row.get(log_entry_col, "") or "")
        client_now = str(row.get(logged_time_col, "")) if logged_time_col else None

        if not log_entry_val or log_entry_val.strip() == "":
            continue

        logged_key = str(client_now or "").strip()
        logged_dt_value = row.get("__logged_dt")
        if logged_dt_value is not None and not pd.isna(logged_dt_value):
            try:
                if isinstance(logged_dt_value, pd.Timestamp):
                    logged_key = logged_dt_value.isoformat()
                else:
                    logged_key = pd.to_datetime(logged_dt_value, errors="coerce", dayfirst=True).isoformat()  # type: ignore[union-attr]
            except Exception:
                pass

        source_key = (str(log_entry_val or "").strip(), logged_key)
        if source_key in seen_source_rows:
            continue
        seen_source_rows.add(source_key)

        parsed = parser.parse_row(log_entry_val, client_now, previous_end)
        parsed["task"] = normalize_task_name(parsed.get("task"))
        parsed["tag"] = normalize_tag(parsed.get("tag")) or "Waste"
        parsed_rows.append(parsed)
        if previous_end is None:
            previous_end = parsed["end_dt"]
        elif parsed.get("end_dt") is not None:
            previous_end = parsed["end_dt"]

    final_rows: List[Dict[str, Any]] = []
    for p in parsed_rows:
        if p["start_dt"].date() < p["end_dt"].date():
            midnight = datetime.combine(p["end_dt"].date(), datetime.min.time())
            part1 = p.copy()
            part1["end_dt"] = midnight
            part2 = p.copy()
            part2["start_dt"] = midnight
            final_rows.append(part1)
            final_rows.append(part2)
        else:
            final_rows.append(p)

    return replace_logs_for_user(db_name, int(user_id), final_rows)
