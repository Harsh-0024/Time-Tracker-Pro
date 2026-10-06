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
