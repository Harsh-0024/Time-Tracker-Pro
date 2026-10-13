"""Small helpers shared by the insight services."""
from __future__ import annotations

from datetime import date, timedelta
from typing import List

import pandas as pd


def activity_keys(tasks: pd.Series) -> pd.Series:
    """Task names as one activity: case-insensitive, trailing " ." etc. ignored."""
    return tasks.fillna("").astype(str).str.replace(r"[\s.,;:]+$", "", regex=True).str.strip().str.lower()


def days_between(start: date, end: date) -> List[date]:
    """Every date from start to end, inclusive."""
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]
