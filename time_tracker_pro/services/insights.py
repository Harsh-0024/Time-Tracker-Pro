"""Plain-language highlights for the dashboard's Insights card.

Everything here is derived from the already-loaded logs DataFrame (see
``repositories.logs.fetch_local_data``); durations are used as-is.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import pandas as pd

FULL_DAY_MINUTES = 23.5 * 60  # treat a day as fully logged from 23.5h


def _growth_mask(df: pd.DataFrame) -> pd.Series:
    return (~df["urgent"]) & (df["important"])


def _waste_mask(df: pd.DataFrame) -> pd.Series:
    return (~df["urgent"]) & (~df["important"])


def top_activities(period_df: pd.DataFrame, limit: int = 5) -> List[Dict[str, Any]]:
    """Largest tasks by total time, grouping names case-insensitively."""
    if period_df.empty:
        return []
    names = period_df["task"].fillna("").astype(str).str.strip()
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
            "hours": round(float(minutes) / 60.0, 1),
            "share": round(float(minutes) / period_total * 100.0, 1),
            "bar": round(float(minutes) / top_minutes * 100.0, 1),
        }
        for key, minutes in totals.items()
    ]


def _daily_minutes(df: pd.DataFrame, mask: Optional[pd.Series] = None) -> pd.Series:
    data = df if mask is None else df[mask]
    if data.empty:
        return pd.Series(dtype=float)
    return data.groupby("date")["duration"].sum()


def _days(start: date, end: date) -> List[date]:
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def build_insights(
    df: pd.DataFrame,
    period_df: pd.DataFrame,
    period: str,
    start_date: date,
    end_date: date,
    today: Optional[date] = None,
) -> Dict[str, Any]:
    today = today or date.today()
    insights: Dict[str, Any] = {"top_activities": top_activities(period_df)}
    if period_df.empty:
        return insights

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
                "growth_hours": round(day_growth / 60.0, 1),
                "growth_avg": round(float(window[_growth_mask(window)]["duration"].sum()) / logged_days / 60.0, 1),
                "waste_hours": round(day_waste / 60.0, 1),
                "waste_avg": round(float(window[_waste_mask(window)]["duration"].sum()) / logged_days / 60.0, 1),
            }
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
        insights["best_growth_day"] = {"date": best_day, "hours": round(float(growth.max()) / 60.0, 1)}
    if not waste.empty:
        worst_day = waste.idxmax()
        insights["most_waste_day"] = {"date": worst_day, "hours": round(float(waste.max()) / 60.0, 1)}

    logged_days = max(1, len([d for d in days if float(totals.get(d, 0.0)) > 0]))
    insights["daily_avg"] = {
        "growth": round(float(growth.sum()) / logged_days / 60.0, 1) if not growth.empty else 0.0,
        "waste": round(float(waste.sum()) / logged_days / 60.0, 1) if not waste.empty else 0.0,
        "days": logged_days,
    }
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
        return {"segments": [], "logged_pct": 0.0}
    day_start = pd.Timestamp(day)
    day_end = day_start + pd.Timedelta(days=1)
    overlapping = df[(df["start_datetime"] < day_end) & (df["end_datetime"] > day_start)]
    if overlapping.empty:
        return {"segments": [], "logged_pct": 0.0}

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
                "left": round(start_min / total * 100.0, 3),
                "width": round((end_min - start_min) / total * 100.0, 3),
                "start": start.strftime("%I:%M %p").lstrip("0"),
                "end": "12:00 AM" if end == day_end else end.strftime("%I:%M %p").lstrip("0"),
                "hours": round((end_min - start_min) / 60.0, 2),
                "important": bool(row.important),
                "urgent": bool(row.urgent),
            }
        )
        if covered and start_min <= covered[-1][1]:
            covered[-1][1] = max(covered[-1][1], end_min)
        else:
            covered.append([start_min, end_min])
    logged = sum(e - s for s, e in covered)
    return {"segments": segments, "logged_pct": round(logged / total * 100.0, 1)}


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
                "actual": round(growth, 1),
                "target": target,
                "pct": round(min(100.0, growth / target * 100.0), 1) if target else 100.0,
                "met": growth >= target,
            }
        if limit is not None:
            result["waste"] = {
                "actual": round(waste, 1),
                "limit": limit,
                "pct": round(min(100.0, waste / limit * 100.0), 1) if limit else (100.0 if waste else 0.0),
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
    return result


def goal_streaks(
    df: pd.DataFrame,
    day: date,
    goals: Dict[str, Optional[float]],
    max_days: int = 366,
) -> Dict[str, int]:
    """Consecutive days, ending on ``day``, on which each goal was met.

    ``day`` itself only breaks a streak once it has data (an unlogged or
    in-progress day shouldn't zero out yesterday's run). A day with no logs at
    all ends the streak.
    """
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

    def run(is_met) -> int:
        count = 0
        current = day
        if current in logged and not is_met(current):
            return 0
        if current not in logged or not is_met(current):
            current -= timedelta(days=1)
        else:
            count, current = 1, current - timedelta(days=1)
        while current in logged and is_met(current):
            count += 1
            current -= timedelta(days=1)
        return count

    if target is not None:
        streaks["growth"] = run(lambda d: float(growth.get(d, 0.0)) >= target)
    if limit is not None:
        streaks["waste"] = run(lambda d: float(waste.get(d, 0.0)) <= limit)
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
                "hours": round(tags[tag], 1),
                "color": TAG_COLORS.get(tag, "#9CA3AF"),
                "pct": round(min(tags[tag], 24.0) / 24.0 * 100.0, 2),
            }
            for tag in TAG_ORDER + sorted(set(tags) - set(TAG_ORDER))
            if tags.get(tag)
        ]
        result.append({"date": d, "total": round(total, 1), "segments": segments})
    return result
