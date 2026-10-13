"""Plain-language highlights for the dashboard's Insights card.

Everything here is derived from the already-loaded logs DataFrame (see
``repositories.logs.fetch_local_data``); durations are used as-is.
"""
from __future__ import annotations

import math
import re
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from ..core.numbers import round_half_up

FULL_DAY_MINUTES = 23.5 * 60  # treat a day as fully logged from 23.5h


def _growth_mask(df: pd.DataFrame) -> pd.Series:
    return (~df["urgent"]) & (df["important"])


def _waste_mask(df: pd.DataFrame) -> pd.Series:
    return (~df["urgent"]) & (~df["important"])


def top_activities(period_df: pd.DataFrame, limit: int = 5) -> List[Dict[str, Any]]:
    """Largest tasks by total time, grouping names case-insensitively."""
    if period_df.empty:
        return []
    # Sheet entries often end in a stray " ." ("Instagram ." vs "Instagram"): same activity.
    names = period_df["task"].fillna("").astype(str).str.replace(r"[\s.,;:]+$", "", regex=True).str.strip()
    work = pd.DataFrame({"key": names.str.lower(), "name": names, "minutes": period_df["duration"]})
    work = work[work["key"] != ""]
    if work.empty:
        return []
    totals = work.groupby("key")["minutes"].sum().sort_values(ascending=False).head(limit)
    # Display the most frequently used spelling of each task.
    display = work.groupby("key")["name"].agg(lambda s: s.value_counts().index[0])
    period_total = float(period_df["duration"].sum()) or 1.0
    top_minutes = float(totals.iloc[0]) or 1.0
    return [
        {
            "name": display[key],
            "hours": round_half_up(float(minutes) / 60.0, 1),
            "share": round_half_up(float(minutes) / period_total * 100.0, 1),
            "bar": round_half_up(float(minutes) / top_minutes * 100.0, 1),
        }
        for key, minutes in totals.items()
    ]


def _activity_keys(tasks: pd.Series) -> pd.Series:
    return tasks.fillna("").astype(str).str.replace(r"[\s.,;:]+$", "", regex=True).str.strip().str.lower()


def _add_activity_trends(
    activities: List[Dict[str, Any]],
    period_df: pd.DataFrame,
    days: int,
    prev_df: pd.DataFrame,
    prev_days: int,
) -> None:
    """Per logged day, how much each top activity changed vs the previous period
    (same basis as the Daily average comparison, so a half-finished week compares fairly)."""
    if not activities or not days or not prev_days:
        return
    current = period_df.groupby(_activity_keys(period_df["task"]))["duration"].sum()
    previous = prev_df.groupby(_activity_keys(prev_df["task"]))["duration"].sum()
    for item in activities:
        key = re.sub(r"[\s.,;:]+$", "", item["name"]).strip().lower()
        now_per_day = float(current.get(key, 0.0)) / days / 60.0
        prev_per_day = float(previous.get(key, 0.0)) / prev_days / 60.0
        item["per_day"] = round_half_up(now_per_day, 1)
        item["prev_per_day"] = round_half_up(prev_per_day, 1)
        item["delta_per_day"] = round_half_up(now_per_day - prev_per_day, 1)


def biggest_changes(
    period_df: pd.DataFrame,
    days: int,
    prev_df: pd.DataFrame,
    prev_days: int,
    skip: List[str],
    limit: int = 3,
    min_hours_per_day: float = 0.3,
) -> List[Dict[str, Any]]:
    """Activities (outside ``skip``, e.g. the top five, which show their own trend) whose
    time per logged day moved the most vs the previous period."""
    if not days or not prev_days or period_df.empty or prev_df.empty:
        return []
    current = period_df.groupby(_activity_keys(period_df["task"]))["duration"].sum() / days / 60.0
    previous = prev_df.groupby(_activity_keys(prev_df["task"]))["duration"].sum() / prev_days / 60.0
    both = pd.concat([current.rename("now"), previous.rename("prev")], axis=1).fillna(0.0)
    skip_keys = {re.sub(r"[\s.,;:]+$", "", name).strip().lower() for name in skip}
    both = both[(both.index != "") & (~both.index.isin(skip_keys))]
    both["delta"] = both["now"] - both["prev"]
    both = both[both["delta"].abs() >= min_hours_per_day]
    if both.empty:
        return []
    both = both.reindex(both["delta"].abs().sort_values(ascending=False).index).head(limit)
    names = pd.concat([period_df["task"], prev_df["task"]]).fillna("").astype(str)
    names = names.str.replace(r"[\s.,;:]+$", "", regex=True).str.strip()
    display = names.groupby(names.str.lower()).agg(lambda s: s.value_counts().index[0])
    return [
        {
            "name": display.get(key, key),
            "per_day": round_half_up(float(row["now"]), 1),
            "prev_per_day": round_half_up(float(row["prev"]), 1),
            "delta_per_day": round_half_up(float(row["delta"]), 1),
        }
        for key, row in both.iterrows()
    ]


def task_name_suggestions(df: pd.DataFrame, limit: int = 60, recent: int = 1500) -> List[Dict[str, Any]]:
    """Most-used task names among the latest ``recent`` logs, each with the tags and
    priority of its newest entry (Add task autocompletes and pre-fills from these)."""
    if df.empty or "task" not in df.columns:
        return []
    latest = df.sort_values("start_datetime").tail(recent) if "start_datetime" in df.columns else df.tail(recent)
    names = latest["task"].fillna("").astype(str).str.replace(r"[\s.,;:]+$", "", regex=True).str.strip()
    latest = latest.assign(_name=names, _key=names.str.lower())
    latest = latest[latest["_key"] != ""]
    if latest.empty:
        return []
    counts = latest.groupby("_key").size().sort_values(ascending=False).head(limit)
    newest = latest.groupby("_key").tail(1).set_index("_key")
    result = []
    for key in counts.index:
        row = newest.loc[key]
        tags = row.get("special_tags") if isinstance(row.get("special_tags"), list) else []
        result.append(
            {
                "name": str(row["_name"]),
                "tags": ", ".join(tags),
                "important": bool(row.get("important")),
                "urgent": bool(row.get("urgent")),
            }
        )
    return result


def _daily_minutes(df: pd.DataFrame, mask: Optional[pd.Series] = None) -> pd.Series:
    data = df if mask is None else df[mask]
    if data.empty:
        return pd.Series(dtype=float)
    return data.groupby("date")["duration"].sum()


def _days(start: date, end: date) -> List[date]:
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def longest_growth_block(period_df: pd.DataFrame) -> Optional[Dict[str, Any]]:
    """The single longest Growth (important, not urgent) log in the period."""
    if period_df.empty:
        return None
    growth = period_df[_growth_mask(period_df)]
    growth = growth[growth["duration"] > 0]
    if growth.empty:
        return None
    row = growth.loc[growth["duration"].idxmax()]
    name = re.sub(r"[\s.,;:]+$", "", str(row.get("task") or "")).strip() or "Untitled"
    return {
        "task": name,
        "date": row["date"],
        "start_time": str(row.get("start_time") or ""),
        "hours": round_half_up(float(row["duration"]) / 60.0, 1),
    }


def build_insights(
    df: pd.DataFrame,
    period_df: pd.DataFrame,
    period: str,
    start_date: date,
    end_date: date,
    today: Optional[date] = None,
    previous: Optional[Tuple[date, date]] = None,
) -> Dict[str, Any]:
    """``previous`` is the (start, end) of the period before this one; week/month
    views compare their daily averages with it."""
    today = today or date.today()
    insights: Dict[str, Any] = {"top_activities": top_activities(period_df)}
    if period_df.empty:
        return insights
    block = longest_growth_block(period_df)
    if block:
        insights["longest_growth_block"] = block

    if period == "day":
        # Compare the day with the 7 days before it.
        window_start = start_date - timedelta(days=7)
        window = df[(df["date"] >= window_start) & (df["date"] < start_date)] if not df.empty else df
        if not window.empty:
            logged_days = window["date"].nunique() or 1
            day_growth = float(period_df[_growth_mask(period_df)]["duration"].sum())
            day_waste = float(period_df[_waste_mask(period_df)]["duration"].sum())
            insights["vs_week"] = {
                "days": int(logged_days),
                "growth_hours": round_half_up(day_growth / 60.0, 1),
                "growth_avg": round_half_up(float(window[_growth_mask(window)]["duration"].sum()) / logged_days / 60.0, 1),
                "waste_hours": round_half_up(day_waste / 60.0, 1),
                "waste_avg": round_half_up(float(window[_waste_mask(window)]["duration"].sum()) / logged_days / 60.0, 1),
            }
            _add_activity_trends(insights["top_activities"], period_df, 1, window, int(logged_days))
        night = sleep_last_night(df, start_date)
        if night:
            insights["sleep_night"] = night
        return insights

    # Week / month: only count days that have started.
    last_day = min(end_date, today)
    if last_day < start_date:
        return insights
    days = _days(start_date, last_day)
    totals = _daily_minutes(period_df)
    growth = _daily_minutes(period_df, _growth_mask(period_df))
    waste = _daily_minutes(period_df, _waste_mask(period_df))

    complete = sum(1 for d in days if float(totals.get(d, 0.0)) >= FULL_DAY_MINUTES)
    insights["completeness"] = {"complete": complete, "days": len(days)}

    if not growth.empty:
        best_day = growth.idxmax()
        insights["best_growth_day"] = {"date": best_day, "hours": round_half_up(float(growth.max()) / 60.0, 1)}
    if not waste.empty:
        worst_day = waste.idxmax()
        insights["most_waste_day"] = {"date": worst_day, "hours": round_half_up(float(waste.max()) / 60.0, 1)}

    logged_days = max(1, len([d for d in days if float(totals.get(d, 0.0)) > 0]))
    insights["daily_avg"] = {
        "growth": round_half_up(float(growth.sum()) / logged_days / 60.0, 1) if not growth.empty else 0.0,
        "waste": round_half_up(float(waste.sum()) / logged_days / 60.0, 1) if not waste.empty else 0.0,
        "days": logged_days,
    }
    if previous is not None and not df.empty:
        prev_df = df[(df["date"] >= previous[0]) & (df["date"] <= previous[1])]
        prev_days = int(prev_df["date"].nunique()) if not prev_df.empty else 0
        if prev_days:
            prev_growth = float(prev_df[_growth_mask(prev_df)]["duration"].sum()) / prev_days / 60.0
            prev_waste = float(prev_df[_waste_mask(prev_df)]["duration"].sum()) / prev_days / 60.0
            insights["daily_avg"]["prev"] = {
                "growth": round_half_up(prev_growth, 1),
                "waste": round_half_up(prev_waste, 1),
                "growth_delta": round_half_up(float(growth.sum()) / logged_days / 60.0 - prev_growth, 1),
                "waste_delta": round_half_up(float(waste.sum()) / logged_days / 60.0 - prev_waste, 1),
                "days": prev_days,
            }
            _add_activity_trends(insights["top_activities"], period_df, logged_days, prev_df, prev_days)
            changes = biggest_changes(
                period_df, logged_days, prev_df, prev_days, [a["name"] for a in insights["top_activities"]]
            )
            if changes:
                insights["biggest_changes"] = changes
    sleep = sleep_summary(df, start_date, last_day)
    if sleep:
        insights["sleep"] = sleep
    return insights


TAG_COLORS = {
    "Work": "#10B981",
    "Necessity": "#F59E0B",
    "Soul": "#6366F1",
    "Rest": "#C4B5FD",
    "Waste": "#DC2626",
}


def build_day_timeline(df: pd.DataFrame, day: date) -> Dict[str, Any]:
    """Segments for a 24h strip: every log overlapping ``day`` (including ones that
    started the evening before), clipped to the day, positioned in percent."""
    if df.empty or "start_datetime" not in df.columns:
        return {"segments": [], "logged_pct": 0.0, "logged_hours": 0.0}
    day_start = pd.Timestamp(day)
    day_end = day_start + pd.Timedelta(days=1)
    overlapping = df[(df["start_datetime"] < day_end) & (df["end_datetime"] > day_start)]
    if overlapping.empty:
        return {"segments": [], "logged_pct": 0.0, "logged_hours": 0.0}

    total = 24 * 60.0
    segments: List[Dict[str, Any]] = []
    covered: List[List[float]] = []
    for row in overlapping.sort_values("start_datetime").itertuples(index=False):
        start = max(row.start_datetime, day_start)
        end = min(row.end_datetime, day_end)
        start_min = (start - day_start).total_seconds() / 60.0
        end_min = (end - day_start).total_seconds() / 60.0
        if end_min <= start_min:
            continue
        tag = row.primary_tag if getattr(row, "primary_tag", None) else "Waste"
        segments.append(
            {
                "task": str(row.task or "").strip() or "Untitled",
                "tag": tag,
                "color": TAG_COLORS.get(tag, "#9CA3AF"),
                "left": round_half_up(start_min / total * 100.0, 3),
                "width": round_half_up((end_min - start_min) / total * 100.0, 3),
                "start": start.strftime("%I:%M %p").lstrip("0"),
                "end": "12:00 AM" if end == day_end else end.strftime("%I:%M %p").lstrip("0"),
                "hours": round_half_up((end_min - start_min) / 60.0, 2),
                "important": bool(row.important),
                "urgent": bool(row.urgent),
            }
        )
        if covered and start_min <= covered[-1][1]:
            covered[-1][1] = max(covered[-1][1], end_min)
        else:
            covered.append([start_min, end_min])
    logged = sum(e - s for s, e in covered)
    return {
        "segments": segments,
        "logged_pct": round_half_up(logged / total * 100.0, 1),
        "logged_hours": round_half_up(logged / 60.0, 1),
    }


def build_goal_progress(
    period_df: pd.DataFrame,
    period: str,
    start_date: date,
    end_date: date,
    goals: Dict[str, Optional[float]],
    today: Optional[date] = None,
) -> Optional[Dict[str, Any]]:
    """Progress against the user's daily Growth target and Waste limit.

    Day view: today's hours vs the goal. Week/month view: on how many logged days
    (that have started) each goal was met. ``None`` when no goals are set.
    """
    target = goals.get("growth_hours")
    limit = goals.get("waste_limit_hours")
    if target is None and limit is None:
        return None
    today = today or date.today()
    result: Dict[str, Any] = {"period": period}

    if period_df.empty:
        growth_by_day = pd.Series(dtype=float)
        waste_by_day = pd.Series(dtype=float)
        logged_days: List[date] = []
    else:
        growth_by_day = _daily_minutes(period_df, _growth_mask(period_df)) / 60.0
        waste_by_day = _daily_minutes(period_df, _waste_mask(period_df)) / 60.0
        logged_days = sorted(d for d in period_df["date"].unique() if d <= max(today, start_date))

    if period == "day":
        growth = float(growth_by_day.sum()) if not growth_by_day.empty else 0.0
        waste = float(waste_by_day.sum()) if not waste_by_day.empty else 0.0
        if target is not None:
            result["growth"] = {
                "actual": round_half_up(growth, 1),
                "target": target,
                "pct": round_half_up(min(100.0, growth / target * 100.0), 1) if target else 100.0,
                "met": growth >= target,
            }
        if limit is not None:
            result["waste"] = {
                "actual": round_half_up(waste, 1),
                "limit": limit,
                "pct": round_half_up(min(100.0, waste / limit * 100.0), 1) if limit else (100.0 if waste else 0.0),
                "over": waste > limit,
            }
        return result

    days = len(logged_days)
    if target is not None:
        met = sum(1 for d in logged_days if float(growth_by_day.get(d, 0.0)) >= target)
        result["growth"] = {"target": target, "met_days": met, "days": days}
    if limit is not None:
        kept = sum(1 for d in logged_days if float(waste_by_day.get(d, 0.0)) <= limit)
        result["waste"] = {"limit": limit, "kept_days": kept, "days": days}

    # One entry per calendar day so the view can draw a met/missed dot row.
    # Same rules as the counts above: unlogged days and days that haven't
    # started are neither met nor missed; today's Growth isn't 'missed' yet.
    logged = set(logged_days)
    calendar = []
    for d in _days(start_date, end_date):
        entry: Dict[str, Any] = {"date": d}
        state = "future" if d > max(today, start_date) else ("none" if d not in logged else None)
        growth_h = float(growth_by_day.get(d, 0.0))
        waste_h = float(waste_by_day.get(d, 0.0))
        if target is not None:
            entry["growth"] = state or ("met" if growth_h >= target else ("open" if d == today else "missed"))
            entry["growth_hours"] = round_half_up(growth_h, 1)
        if limit is not None:
            entry["waste"] = state or ("met" if waste_h <= limit else "missed")
            entry["waste_hours"] = round_half_up(waste_h, 1)
        calendar.append(entry)
    result["calendar"] = calendar
    return result


def goal_streaks(
    df: pd.DataFrame,
    day: date,
    goals: Dict[str, Optional[float]],
    max_days: int = 366,
    today: Optional[date] = None,
) -> Dict[str, int]:
    """Consecutive days, ending on ``day``, on which each goal was met.

    ``day`` itself only breaks a streak once it has data (an unlogged or
    in-progress day shouldn't zero out yesterday's run). Today's Growth below
    target doesn't break it either - the day isn't over (same as the goal
    dots' 'so far'); a Waste limit already exceeded does. A day with no logs at
    all ends the streak.
    """
    today = today or date.today()
    target = goals.get("growth_hours")
    limit = goals.get("waste_limit_hours")
    streaks: Dict[str, int] = {}
    if df.empty or (target is None and limit is None):
        return streaks
    window = df[(df["date"] <= day) & (df["date"] > day - timedelta(days=max_days))]
    if window.empty:
        return {key: 0 for key, goal in (("growth", target), ("waste", limit)) if goal is not None}
    logged = set(window["date"].unique())
    growth = _daily_minutes(window, _growth_mask(window)) / 60.0
    waste = _daily_minutes(window, _waste_mask(window)) / 60.0

    def run(is_met, open_today: bool = False) -> int:
        count = 0
        current = day
        if current in logged and not is_met(current) and not (open_today and current == today):
            return 0
        if current not in logged or not is_met(current):
            current -= timedelta(days=1)
        else:
            count, current = 1, current - timedelta(days=1)
        while current in logged and is_met(current):
            count += 1
            current -= timedelta(days=1)
        return count

    def best_run(is_met) -> int:
        # Longest run of consecutive logged days meeting the goal in the window.
        best = length = 0
        previous = None
        for d in sorted(logged):
            if is_met(d):
                length = length + 1 if previous is not None and d - previous == timedelta(days=1) else 1
                best = max(best, length)
                previous = d
            else:
                length, previous = 0, None
        return best

    if target is not None:
        growth_met = lambda d: float(growth.get(d, 0.0)) >= target  # noqa: E731
        streaks["growth"] = run(growth_met, open_today=True)
        streaks["growth_best"] = max(best_run(growth_met), streaks["growth"])
    if limit is not None:
        waste_kept = lambda d: float(waste.get(d, 0.0)) <= limit  # noqa: E731
        streaks["waste"] = run(waste_kept)
        streaks["waste_best"] = max(best_run(waste_kept), streaks["waste"])
    return streaks


TAG_ORDER = ["Work", "Soul", "Rest", "Necessity", "Waste"]


def build_daily_breakdown(period_df: pd.DataFrame, start_date: date, end_date: date) -> List[Dict[str, Any]]:
    """Per-day hours by primary tag for a stacked-column chart (week/month views)."""
    days = _days(start_date, end_date)
    by_day: Dict[date, Dict[str, float]] = {d: {} for d in days}
    if not period_df.empty:
        grouped = period_df.groupby(["date", "primary_tag"])["duration"].sum()
        for (d, tag), minutes in grouped.items():
            if d in by_day:
                by_day[d][tag] = float(minutes) / 60.0
    result = []
    for d in days:
        tags = by_day[d]
        total = sum(tags.values())
        segments = [
            {
                "tag": tag,
                "hours": round_half_up(tags[tag], 1),
                "color": TAG_COLORS.get(tag, "#9CA3AF"),
                "pct": round_half_up(min(tags[tag], 24.0) / 24.0 * 100.0, 2),
            }
            for tag in TAG_ORDER + sorted(set(tags) - set(TAG_ORDER))
            if tags.get(tag)
        ]
        result.append({"date": d, "total": round_half_up(total, 1), "segments": segments})
    return result


def build_tag_goal_progress(
    period_df: pd.DataFrame,
    period: str,
    start_date: date,
    end_date: date,
    tag_goals: List[Dict[str, Any]],
    today: Optional[date] = None,
) -> Optional[Dict[str, Any]]:
    """Per-category goals ("Soul >= 1h", "Waste <= 3h") on each log's primary tag.

    Same rules as the Growth/Waste goals: day view shows today's hours vs the
    goal; week/month count the logged days (that have started) that met it.
    ``calendar`` has one entry per day keyed ``tag_<Tag>`` for the dot rows; an
    "at least" goal isn't missed today while the day is still going.
    """
    if not tag_goals:
        return None
    today = today or date.today()
    if period_df.empty:
        by_day_tag: Dict[Any, float] = {}
        logged_days: List[date] = []
    else:
        grouped = period_df.groupby(["date", "primary_tag"])["duration"].sum() / 60.0
        by_day_tag = {key: float(value) for key, value in grouped.items()}
        logged_days = sorted(d for d in period_df["date"].unique() if d <= max(today, start_date))

    def hours_on(d: date, tag: str) -> float:
        return by_day_tag.get((d, tag), 0.0)

    def ok(goal: Dict[str, Any], hours: float) -> bool:
        return hours >= goal["hours"] if goal["kind"] == "min" else hours <= goal["hours"]

    items: List[Dict[str, Any]] = []
    for goal in tag_goals:
        tag = goal["tag"]
        item: Dict[str, Any] = {
            "tag": tag,
            "kind": goal["kind"],
            "hours": goal["hours"],
            "color": TAG_COLORS.get(tag, "#9CA3AF"),
            "key": f"tag_{tag}",
        }
        if period == "day":
            actual = sum(h for (d, t), h in by_day_tag.items() if t == tag)
            target = float(goal["hours"])
            item["actual"] = round_half_up(actual, 1)
            item["ok"] = ok(goal, actual)
            item["pct"] = round_half_up(min(100.0, actual / target * 100.0), 1) if target else (100.0 if actual else 0.0)
        else:
            item["met_days"] = sum(1 for d in logged_days if ok(goal, hours_on(d, tag)))
            item["days"] = len(logged_days)
        items.append(item)

    logged = set(logged_days)
    calendar = []
    for d in _days(start_date, end_date):
        entry: Dict[str, Any] = {"date": d}
        state = "future" if d > max(today, start_date) else ("none" if d not in logged else None)
        for goal in tag_goals:
            key = f"tag_{goal['tag']}"
            h = hours_on(d, goal["tag"])
            if state:
                entry[key] = state
            elif ok(goal, h):
                entry[key] = "met"
            else:
                entry[key] = "open" if (goal["kind"] == "min" and d == today) else "missed"
            entry[f"{key}_hours"] = round_half_up(h, 1)
        calendar.append(entry)
    return {"items": items, "calendar": calendar}


def find_overlaps(df: pd.DataFrame, start_date: date, end_date: date, limit: int = 20) -> Dict[str, Any]:
    """Logs that overlap an earlier log, for entries starting in [start_date, end_date].

    Each overlapping pair is time counted twice in every total. Read-only:
    nothing is changed, the list just points at rows to fix in the sheet.
    """
    empty = {"pairs": [], "count": 0, "minutes": 0}
    if df.empty or "start_datetime" not in df.columns:
        return empty
    # Include the day before so a late-night log can be caught overlapping.
    window = df[(df["date"] >= start_date - timedelta(days=1)) & (df["date"] <= end_date)]
    if window.empty:
        return empty
    window = window.sort_values(["start_datetime", "end_datetime"])
    pairs: List[Dict[str, Any]] = []
    total_minutes = 0.0
    latest = None  # the row reaching furthest so far
    for row in window.itertuples(index=False):
        if latest is not None and row.start_datetime < latest.end_datetime and row.date >= start_date:
            overlap_end = min(row.end_datetime, latest.end_datetime)
            minutes = (overlap_end - row.start_datetime).total_seconds() / 60.0
            if minutes > 0:
                total_minutes += minutes
                pairs.append(
                    {
                        "date": row.date,
                        "first": {"task": str(latest.task or "").strip(), "start": latest.start_time, "end": latest.end_time},
                        "second": {"task": str(row.task or "").strip(), "start": row.start_time, "end": row.end_time},
                        "minutes": int(round(minutes)),
                    }
                )
        if latest is None or row.end_datetime > latest.end_datetime:
            latest = row
    return {"pairs": pairs[:limit], "count": len(pairs), "minutes": int(round(total_minutes))}


def logging_streak(df: pd.DataFrame, day: date, today: Optional[date] = None, max_days: int = 366) -> Dict[str, int]:
    """Consecutive fully-logged days (>= 23.5h) ending on ``day``, plus the best run in the window.

    ``day`` only counts if it's complete; if it isn't (e.g. today, still in progress)
    the run is counted up to the day before instead of being broken.
    """
    today = today or date.today()
    if df.empty:
        return {"current": 0, "best": 0}
    window = df[(df["date"] <= day) & (df["date"] > day - timedelta(days=max_days))]
    if window.empty:
        return {"current": 0, "best": 0}
    totals = window.groupby("date")["duration"].sum()
    complete = {d for d, minutes in totals.items() if float(minutes) >= FULL_DAY_MINUTES}

    current = 0
    cursor = day if day in complete else day - timedelta(days=1)
    if day not in complete and day != today:
        # A past day that isn't fully logged ends the run.
        cursor = None
    while cursor is not None and cursor in complete:
        current += 1
        cursor -= timedelta(days=1)

    best = run = 0
    previous = None
    for d in sorted(complete):
        run = run + 1 if previous is not None and d - previous == timedelta(days=1) else 1
        best = max(best, run)
        previous = d
    return {"current": current, "best": max(best, current)}


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
