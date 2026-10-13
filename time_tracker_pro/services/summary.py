"""Plain-text recap of a dashboard period (the 'Copy summary' button).

Built only from numbers the dashboard already shows, so the copy always
matches the page.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

from ..core.numbers import round_half_up


def _h(value: Any) -> str:
    try:
        return f"{float(value or 0):.1f}h"
    except (TypeError, ValueError):
        return "0.0h"


def _day(value: Any) -> str:
    if isinstance(value, date):
        return f"{value.strftime('%a')} {value.day} {value.strftime('%b')}"
    return str(value or "")


def build_period_summary_text(
    title: str,
    period: str,
    matrix: Dict[str, Any],
    logged_coverage: Optional[float],
    insights: Optional[Dict[str, Any]],
    goal_progress: Optional[Dict[str, Any]] = None,
    notes: Optional[Dict[Any, str]] = None,
) -> str:
    total = float(matrix.get("total_hours") or 0.0)
    if total <= 0:
        return ""
    lines: List[str] = [f"Time Tracker Pro · {title}"]
    logged = f"Logged {_h(total)}"
    if logged_coverage is not None:
        logged += f" ({round_half_up(float(logged_coverage), 0):g}% of the {period})"  # as the page shows it
    lines.append(logged)

    def quad(key: str) -> str:
        q = matrix.get(key) or {}
        return f"{_h(q.get('hours'))} ({float(q.get('pct') or 0):g}%)"

    lines.append(
        f"Growth {quad('q2')} · Critical {quad('q1')} · Drudgery {quad('q3')} · Waste {quad('q4')}"
    )

    insights = insights or {}
    tops = insights.get("top_activities") or []
    if tops:
        lines.append("")
        lines.append("Top activities:")
        for item in tops:
            lines.append(f"- {item['name']}: {_h(item['hours'])} ({item['share']:g}%)")

    extra: List[str] = []
    vw = insights.get("vs_week")
    if vw:
        days = vw["days"]
        extra.append(
            f"vs your last {days} day{'' if days == 1 else 's'}: growth {_h(vw['growth_hours'])} (avg {_h(vw['growth_avg'])}),"
            f" waste {_h(vw['waste_hours'])} (avg {_h(vw['waste_avg'])})"
        )
    avg = insights.get("daily_avg")
    if avg:
        line = f"Daily average: {_h(avg.get('growth'))} growth, {_h(avg.get('waste'))} waste"
        prev = avg.get("prev")
        if prev:
            def signed(v: float) -> str:
                return ("+" if v > 0 else "−" if v < 0 else "±") + f"{abs(v):.1f}h"
            line += f" ({signed(prev['growth_delta'])} growth, {signed(prev['waste_delta'])} waste vs last {period})"
        extra.append(line)
    best = insights.get("best_growth_day")
    if best:
        extra.append(f"Best growth day: {_day(best['date'])} ({_h(best['hours'])})")
    block = insights.get("longest_growth_block")
    if block:
        where = "" if period == "day" else f", {_day(block['date'])}"
        extra.append(f"Longest growth block: {block['task']} ({_h(block['hours'])}{where})")
    gp = goal_progress or {}
    streaks = gp.get("streaks") or {}
    if gp.get("growth"):
        g = gp["growth"]
        if period == "day":
            streak = f" ({streaks['growth']}-day streak)" if (streaks.get("growth") or 0) > 1 else ""
            extra.append(f"Growth goal: {_h(g['actual'])} of {_h(g['target'])}{streak}")
        elif g.get("days"):
            extra.append(f"Growth goal met on {g['met_days']} of {g['days']} days")
    if gp.get("waste"):
        w = gp["waste"]
        if period == "day":
            streak = f" ({streaks['waste']} days in a row under)" if (streaks.get("waste") or 0) > 1 else ""
            extra.append(f"Waste limit: {_h(w['actual'])} of {_h(w['limit'])}{streak}")
        elif w.get("days"):
            extra.append(f"Under the waste limit on {w['kept_days']} of {w['days']} days")
    for tg in gp.get("tags") or []:
        sign = "≥" if tg["kind"] == "min" else "≤"
        if period == "day":
            mark = "✓" if tg.get("ok") else "✗"
            extra.append(f"{tg['tag']} {sign} {_h(tg['hours'])}: {_h(tg['actual'])} {mark}")
        elif tg.get("days"):
            extra.append(f"{tg['tag']} {sign} {_h(tg['hours'])} on {tg['met_days']} of {tg['days']} days")
    if extra:
        lines.append("")
        lines.extend(extra)
    if notes:
        lines.append("")
        if period == "day":
            lines.append(f"Note: {next(iter(notes.values()))}")
        else:
            lines.append("Notes:")
            lines.extend(f"- {_day(day)}: {text}" for day, text in sorted(notes.items()))
    return "\n".join(lines)
