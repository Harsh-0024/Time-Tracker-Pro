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

        source_key = (str(log_entry_val or "").strip(), str(client_now or "").strip())
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
            previous_end = max(previous_end, parsed["end_dt"])

    parsed_rows.sort(
        key=lambda row: (
            row["start_dt"],
            row["end_dt"],
            row.get("task") or "",
            row.get("tag") or "",
            bool(row.get("urg")),
            bool(row.get("imp")),
        )
    )
    deduped_rows: List[Dict[str, Any]] = []
    seen_rows = set()
    for row in parsed_rows:
        key = (
            row["start_dt"],
            row["end_dt"],
            row.get("task") or "",
            row.get("tag") or "",
            bool(row.get("urg")),
            bool(row.get("imp")),
        )
        if key in seen_rows:
            continue
        seen_rows.add(key)
        deduped_rows.append(row)
    parsed_rows = deduped_rows

    for i in range(1, len(parsed_rows)):
        current = parsed_rows[i]
        prev = parsed_rows[i - 1]
        if current["start_dt"] < prev["end_dt"]:
            parsed_rows[i - 1]["end_dt"] = current["start_dt"]

    merged_rows: List[Dict[str, Any]] = []
    for row in parsed_rows:
        if (
            merged_rows
            and row.get("task") == merged_rows[-1].get("task")
            and row.get("tag") == merged_rows[-1].get("tag")
            and bool(row.get("urg")) == bool(merged_rows[-1].get("urg"))
            and bool(row.get("imp")) == bool(merged_rows[-1].get("imp"))
            and row["start_dt"] == merged_rows[-1]["end_dt"]
        ):
            if row["end_dt"] > merged_rows[-1]["end_dt"]:
                merged_rows[-1]["end_dt"] = row["end_dt"]
            continue
        merged_rows.append(row)
    parsed_rows = merged_rows

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
