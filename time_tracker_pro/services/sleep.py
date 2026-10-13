"""Sleep from the day log: tasks named "Sleep", merged into nights.

A night is consecutive Sleep rows (up to 15 minutes apart, so a night split at
midnight is one), counted on the day you woke up; blocks under 3 hours are naps
and left out. A day without a logged night is missing data, not 0h of sleep.
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import pandas as pd

from ..core.numbers import round_half_up
from .activity import activity_keys as _activity_keys, days_between as _days

SLEEP_MIN_NIGHT_MINUTES = 3 * 60  # shorter sleep blocks are naps, not nights
SLEEP_JOIN_GAP_MINUTES = 15  # e.g. "Sleep 23:20-00:00" + "Sleep 00:00-06:30" is one night
SLEEP_MIN_CLOCK_CONSISTENCY = 0.6  # mean resultant length below this: bedtimes too scattered to average


def _sleep_nights(df: pd.DataFrame, first_wake: date, last_wake: date) -> List[Dict[str, Any]]:
    """Sleep logs merged into nights, for nights that end on [first_wake, last_wake]."""
    if df.empty or "start_datetime" not in df.columns:
        return []
    window = df[(df["date"] >= first_wake - timedelta(days=1)) & (df["date"] <= last_wake)]
    if window.empty:
        return []
    sleep = window[_activity_keys(window["task"]) == "sleep"].sort_values("start_datetime")
    blocks: List[List[Any]] = []  # [start, end, minutes]
    for row in sleep.itertuples(index=False):
        if pd.isna(row.start_datetime) or pd.isna(row.end_datetime):
            continue
        gap = (row.start_datetime - blocks[-1][1]).total_seconds() / 60.0 if blocks else None
        if gap is not None and gap <= SLEEP_JOIN_GAP_MINUTES:
            blocks[-1][1] = max(blocks[-1][1], row.end_datetime)
            blocks[-1][2] += float(row.duration or 0)
        else:
            blocks.append([row.start_datetime, row.end_datetime, float(row.duration or 0)])
    return [
        {"start": start, "end": end, "minutes": minutes, "date": end.date()}
        for start, end, minutes in blocks
        if minutes >= SLEEP_MIN_NIGHT_MINUTES and first_wake <= end.date() <= last_wake
    ]


def _clock_label(minutes: float) -> str:
    minutes = int(round(minutes)) % (24 * 60)
    hour, minute = divmod(minutes, 60)
    return f"{(hour % 12) or 12:02d}:{minute:02d} {'AM' if hour < 12 else 'PM'}"


def _typical_clock(times: List[pd.Timestamp]) -> Optional[str]:
    """Circular mean of clock times (23:30 and 00:30 average to midnight).

    ``None`` when the times are too spread out for an average to mean anything.
    """
    angles = [2 * math.pi * (t.hour * 60 + t.minute + t.second / 60.0) / 1440.0 for t in times]
    x = sum(math.cos(a) for a in angles) / len(angles)
    y = sum(math.sin(a) for a in angles) / len(angles)
    if math.hypot(x, y) < SLEEP_MIN_CLOCK_CONSISTENCY:
        return None
    return _clock_label((math.atan2(y, x) % (2 * math.pi)) * 1440.0 / (2 * math.pi))


def _clock_spread_minutes(times: List[pd.Timestamp]) -> int:
    """Circular standard deviation of clock times, in minutes (rounded to 5)."""
    angles = [2 * math.pi * (t.hour * 60 + t.minute + t.second / 60.0) / 1440.0 for t in times]
    r = math.hypot(sum(math.cos(a) for a in angles), sum(math.sin(a) for a in angles)) / len(angles)
    spread = math.sqrt(-2.0 * math.log(max(min(r, 1.0), 1e-9))) * 1440.0 / (2 * math.pi)
    return int(round(spread / 5.0) * 5)


def sleep_summary(
    df: pd.DataFrame,
    start_date: date,
    end_date: date,
) -> Optional[Dict[str, Any]]:
    """Sleep per night (tasks named "Sleep") for nights ending in the range.

    Each wake-up day counts once: its sleep is every block of 3h+ ending that day,
    and bed/wake times come from its longest block. ``None`` with fewer than 2 nights.
    """
    def per_day(nights: List[Dict[str, Any]]) -> Dict[date, Dict[str, Any]]:
        days: Dict[date, Dict[str, Any]] = {}
        for night in nights:
            day = days.setdefault(night["date"], {"minutes": 0.0, "longest": night})
            day["minutes"] += night["minutes"]
            if night["minutes"] > day["longest"]["minutes"]:
                day["longest"] = night
        return days

    days = per_day(_sleep_nights(df, start_date, end_date))
    if len(days) < 3:
        return None
    avg_minutes = sum(d["minutes"] for d in days.values()) / len(days)
    shortest_day = min(days, key=lambda d: days[d]["minutes"])
    result: Dict[str, Any] = {
        "nights": len(days),
        "avg_hours": round_half_up(avg_minutes / 60.0, 1),
        "bedtime": _typical_clock([d["longest"]["start"] for d in days.values()]),
        "wake": _typical_clock([d["longest"]["end"] for d in days.values()]),
        "shortest": {"date": shortest_day, "hours": round_half_up(days[shortest_day]["minutes"] / 60.0, 1)},
    }
    if result["bedtime"]:
        result["bedtime_spread_min"] = _clock_spread_minutes([d["longest"]["start"] for d in days.values()])
    return result


def sleep_last_night(df: pd.DataFrame, day: date) -> Optional[Dict[str, Any]]:
    """The night that ended on ``day`` (see ``sleep_summary``), vs the 7 nights before."""
    nights = _sleep_nights(df, day - timedelta(days=7), day)
    tonight = [n for n in nights if n["date"] == day]
    if not tonight:
        return None
    longest = max(tonight, key=lambda n: n["minutes"])
    minutes = sum(n["minutes"] for n in tonight)
    result: Dict[str, Any] = {
        "hours": round_half_up(minutes / 60.0, 1),
        "bedtime": _clock_label(longest["start"].hour * 60 + longest["start"].minute),
        "wake": _clock_label(longest["end"].hour * 60 + longest["end"].minute),
    }
    before: Dict[date, float] = {}
    for night in nights:
        if night["date"] < day:
            before[night["date"]] = before.get(night["date"], 0.0) + night["minutes"]
    if len(before) >= 3:
        avg = sum(before.values()) / len(before)
        result["avg_hours"] = round_half_up(avg / 60.0, 1)
        result["delta_hours"] = round_half_up((minutes - avg) / 60.0, 1) + 0.0
        result["avg_nights"] = len(before)
    return result


def sleep_minutes_by_night(df: pd.DataFrame, start_date: date, end_date: date) -> Dict[date, float]:
    """Minutes slept per wake-up day (3h+ "Sleep" blocks, midnight splits merged)."""
    totals: Dict[date, float] = {}
    for night in _sleep_nights(df, start_date, end_date):
        totals[night["date"]] = totals.get(night["date"], 0.0) + night["minutes"]
    return totals


def is_sleep_task(tasks: pd.Series) -> pd.Series:
    return _activity_keys(tasks) == "sleep"


SLEEP_GOAL_COLOR = "#8B5CF6"


def build_sleep_goal_progress(
    df: pd.DataFrame,
    period: str,
    start_date: date,
    end_date: date,
    target_hours: float,
    today: Optional[date] = None,
) -> Optional[Dict[str, Any]]:
    """An "at least N hours a night" goal, shaped like a category goal (see
    ``build_tag_goal_progress``) so the dashboard renders it the same way.

    Nights count on the day you woke up. ``calendar`` maps each day of
    [start_date, end_date] to its dot (``sleep`` / ``sleep_hours`` keys); a day
    without a logged night is "none". Day view: ``None`` if that night isn't logged.
    """
    today = today or date.today()
    target = float(target_hours)
    nights = sleep_minutes_by_night(df, start_date, end_date)
    hours = {d: minutes / 60.0 for d, minutes in nights.items()}
    item: Dict[str, Any] = {"tag": "Sleep", "kind": "min", "hours": target, "color": SLEEP_GOAL_COLOR, "key": "sleep"}
    if period == "day":
        if end_date not in hours:
            return None
        actual = hours[end_date]
        item["actual"] = round_half_up(actual, 1)
        item["ok"] = actual >= target
        item["pct"] = round_half_up(min(100.0, actual / target * 100.0), 1) if target else 100.0
        # Streaks over the past year: consecutive wake-up days whose night met the goal
        # (a night that wasn't logged ends a run).
        year = sleep_minutes_by_night(df, end_date - timedelta(days=365), end_date)
        met = {d for d, minutes in year.items() if minutes / 60.0 >= target}
        current, cursor = 0, end_date
        while cursor in met:
            current += 1
            cursor -= timedelta(days=1)
        best = run = 0
        previous: Optional[date] = None
        for d in sorted(met):
            run = run + 1 if previous is not None and d - previous == timedelta(days=1) else 1
            best = max(best, run)
            previous = d
        item["streak"], item["streak_best"] = current, best
    else:
        item["met_days"] = sum(1 for h in hours.values() if h >= target)
        item["days"] = len(hours)
    calendar: Dict[date, Dict[str, Any]] = {}
    for d in _days(start_date, end_date):
        if d > max(today, start_date):
            state = "future"
        elif d not in hours:
            state = "none"
        else:
            state = "met" if hours[d] >= target else "missed"
        calendar[d] = {"sleep": state, "sleep_hours": round_half_up(hours.get(d, 0.0), 1)}
    return {"item": item, "calendar": calendar}


def sleep_debt(df: pd.DataFrame, start_date: date, end_date: date, goal_hours: float) -> Dict[str, Any]:
    """How far the logged nights in the range fell short of the goal, in total."""
    nights = sleep_minutes_by_night(df, start_date, end_date)
    short = [goal_hours - minutes / 60.0 for minutes in nights.values() if minutes / 60.0 < goal_hours]
    return {"hours": round_half_up(sum(short), 1), "nights": len(short)}
