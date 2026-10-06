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
