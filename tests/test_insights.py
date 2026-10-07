from datetime import date

from conftest import add_log, make_user
from time_tracker_pro.repositories.logs import fetch_local_data
from time_tracker_pro.services.insights import build_insights, top_activities


def _df(db_path, uid):
    return fetch_local_data(db_path, uid)


def test_top_activities_groups_case_insensitively(db_path):
    uid = make_user(db_path)
    add_log(db_path, uid, "2026-09-20", "00:00:00", "2026-09-20", "06:00:00", task="Sleep")
    add_log(db_path, uid, "2026-09-20", "06:00:00", "2026-09-20", "07:00:00", task="sleep ")
    add_log(db_path, uid, "2026-09-20", "07:00:00", "2026-09-20", "09:00:00", task="Gym")
    tops = top_activities(_df(db_path, uid))
    assert [t["name"] for t in tops] == ["Sleep", "Gym"]
    assert tops[0]["hours"] == 7.0
    assert tops[0]["bar"] == 100.0
    assert tops[1]["share"] == round(2 / 9 * 100, 1)


def test_top_activities_ignores_trailing_punctuation(db_path):
    uid = make_user(db_path)
    add_log(db_path, uid, "2026-09-20", "00:00:00", "2026-09-20", "02:00:00", task="Instagram .")
    add_log(db_path, uid, "2026-09-20", "02:00:00", "2026-09-20", "03:00:00", task="Instagram .")
    add_log(db_path, uid, "2026-09-20", "03:00:00", "2026-09-20", "04:00:00", task="Instagram")
    tops = top_activities(_df(db_path, uid))
    assert [(t["name"], t["hours"]) for t in tops] == [("Instagram", 4.0)]


def test_day_insights_compare_with_previous_week(db_path):
    uid = make_user(db_path)
    # Two previous days with 2h growth each, today 4h growth.
    for day in ("2026-09-18", "2026-09-19"):
        add_log(db_path, uid, day, "08:00:00", day, "10:00:00", urg=0, imp=1)
    add_log(db_path, uid, "2026-09-20", "08:00:00", "2026-09-20", "12:00:00", urg=0, imp=1)
    df = _df(db_path, uid)
    day = df[df["date"] == date(2026, 9, 20)]
    ins = build_insights(df, day, "day", date(2026, 9, 20), date(2026, 9, 20), today=date(2026, 9, 20))
    assert ins["vs_week"] == {"days": 2, "growth_hours": 4.0, "growth_avg": 2.0, "waste_hours": 0.0, "waste_avg": 0.0}


def test_week_insights_ignore_future_days(db_path):
    uid = make_user(db_path)
    add_log(db_path, uid, "2026-09-13", "00:00:00", "2026-09-14", "00:00:00", urg=0, imp=0)  # full day of waste
    add_log(db_path, uid, "2026-09-14", "08:00:00", "2026-09-14", "11:00:00", urg=0, imp=1)
    df = _df(db_path, uid)
    week = df[(df["date"] >= date(2026, 9, 13)) & (df["date"] <= date(2026, 9, 19))]
    ins = build_insights(df, week, "week", date(2026, 9, 13), date(2026, 9, 19), today=date(2026, 9, 15))
    assert ins["completeness"] == {"complete": 1, "days": 3}
    assert ins["best_growth_day"] == {"date": date(2026, 9, 14), "hours": 3.0}
    assert ins["most_waste_day"] == {"date": date(2026, 9, 13), "hours": 24.0}
    assert ins["daily_avg"] == {"growth": 1.5, "waste": 12.0, "days": 2}


def test_insights_empty_period(db_path):
    uid = make_user(db_path)
    df = _df(db_path, uid)
    assert build_insights(df, df, "day", date(2026, 9, 20), date(2026, 9, 20)) == {"top_activities": []}


def test_day_timeline_clips_overnight_and_reports_coverage(db_path):
    from time_tracker_pro.services.insights import build_day_timeline

    uid = make_user(db_path)
    add_log(db_path, uid, "2026-09-19", "22:00:00", "2026-09-20", "06:00:00", task="Sleep", tags="Necessity")
    add_log(db_path, uid, "2026-09-20", "06:00:00", "2026-09-20", "12:00:00", task="Work", tags="Work")
    add_log(db_path, uid, "2026-09-20", "23:00:00", "2026-09-21", "02:00:00", task="Late", tags="Waste")
    tl = build_day_timeline(_df(db_path, uid), date(2026, 9, 20))

    assert [s["task"] for s in tl["segments"]] == ["Sleep", "Work", "Late"]
    sleep, work, late = tl["segments"]
    assert (sleep["left"], sleep["width"], sleep["start"]) == (0.0, 25.0, "12:00 AM")
    assert (work["left"], work["width"], work["color"]) == (25.0, 25.0, "#10B981")
    assert late["end"] == "12:00 AM" and round(late["width"], 3) == round(100 / 24, 3)
    assert tl["logged_pct"] == round(13 / 24 * 100, 1)
    assert tl["logged_hours"] == 13.0


def test_day_timeline_empty(db_path):
    from time_tracker_pro.services.insights import build_day_timeline

    uid = make_user(db_path)
    add_log(db_path, uid, "2026-09-18", "08:00:00", "2026-09-18", "09:00:00")
    assert build_day_timeline(_df(db_path, uid), date(2026, 9, 20)) == {"segments": [], "logged_pct": 0.0, "logged_hours": 0.0}


def test_daily_breakdown(db_path):
    from time_tracker_pro.services.insights import build_daily_breakdown

    uid = make_user(db_path)
    add_log(db_path, uid, "2026-09-14", "00:00:00", "2026-09-14", "06:00:00", tags="Necessity")
    add_log(db_path, uid, "2026-09-14", "06:00:00", "2026-09-14", "12:00:00", tags="Work")
    add_log(db_path, uid, "2026-09-15", "06:00:00", "2026-09-15", "09:00:00", tags="nonsense")  # -> Waste
    df = _df(db_path, uid)
    days = build_daily_breakdown(df, date(2026, 9, 13), date(2026, 9, 19))

    assert [d["date"].day for d in days] == [13, 14, 15, 16, 17, 18, 19]
    assert days[0] == {"date": date(2026, 9, 13), "total": 0.0, "segments": []}
    assert [(s["tag"], s["hours"], s["pct"]) for s in days[1]["segments"]] == [("Work", 6.0, 25.0), ("Necessity", 6.0, 25.0)]
    assert days[1]["total"] == 12.0
    assert days[2]["segments"][0]["tag"] == "Waste"


def test_longest_growth_block_picks_longest_q2_log(db_path):
    uid = make_user(db_path)
    add_log(db_path, uid, "2026-09-20", "06:00:00", "2026-09-20", "08:00:00", task="Reading .", urg=0, imp=1)
    add_log(db_path, uid, "2026-09-20", "08:00:00", "2026-09-20", "13:00:00", task="Netflix", urg=0, imp=0)
    add_log(db_path, uid, "2026-09-21", "09:00:00", "2026-09-21", "12:30:00", task="Deep work", urg=0, imp=1)
    add_log(db_path, uid, "2026-09-21", "13:00:00", "2026-09-21", "18:00:00", task="Urgent thing", urg=1, imp=1)
    df = _df(db_path, uid)
    week = build_insights(df, df, "week", date(2026, 9, 20), date(2026, 9, 26), today=date(2026, 9, 26))
    block = week["longest_growth_block"]
    assert (block["task"], block["hours"], block["date"]) == ("Deep work", 3.5, date(2026, 9, 21))
    assert block["start_time"] == "09:00 AM"
    day = df[df["date"] == date(2026, 9, 20)]
    assert build_insights(df, day, "day", date(2026, 9, 20), date(2026, 9, 20))["longest_growth_block"]["task"] == "Reading"


def test_longest_growth_block_absent_without_growth(db_path):
    uid = make_user(db_path)
    add_log(db_path, uid, "2026-09-20", "08:00:00", "2026-09-20", "13:00:00", task="Netflix", urg=0, imp=0)
    df = _df(db_path, uid)
    assert "longest_growth_block" not in build_insights(df, df, "day", date(2026, 9, 20), date(2026, 9, 20))


def test_week_daily_average_compares_with_previous_week():
    from datetime import date as _d
    import pandas as _pd
    from time_tracker_pro.services.insights import build_insights

    def row(day, minutes, urgent, important):
        return {"date": day, "duration": minutes, "urgent": urgent, "important": important, "task": "x"}

    rows = [
        row(_d(2026, 9, 28), 120, False, True),  # previous week: 2h growth, 1h waste over 1 day
        row(_d(2026, 9, 28), 60, False, False),
        row(_d(2026, 10, 5), 180, False, True),  # this week: 3h growth, 0.5h waste
        row(_d(2026, 10, 5), 30, False, False),
    ]
    df = _pd.DataFrame(rows)
    period_df = df[df["date"] >= _d(2026, 10, 4)]
    ins = build_insights(df, period_df, "week", _d(2026, 10, 4), _d(2026, 10, 10),
                         today=_d(2026, 10, 7), previous=(_d(2026, 9, 27), _d(2026, 10, 3)))
    prev = ins["daily_avg"]["prev"]
    assert prev["growth_delta"] == 1.0 and prev["waste_delta"] == -0.5 and prev["days"] == 1
    # No previous data -> no comparison.
    ins = build_insights(period_df, period_df, "week", _d(2026, 10, 4), _d(2026, 10, 10),
                         today=_d(2026, 10, 7), previous=(_d(2026, 9, 27), _d(2026, 10, 3)))
    assert "prev" not in ins["daily_avg"]
