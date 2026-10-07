from datetime import date

import pytest

from conftest import add_log, make_user
from time_tracker_pro.repositories.goals import get_user_goals, parse_goal_hours, upsert_user_goals
from time_tracker_pro.repositories.logs import fetch_local_data
from time_tracker_pro.services.insights import build_goal_progress


def test_parse_goal_hours():
    assert parse_goal_hours("") is None
    assert parse_goal_hours(" 4.5 ") == 4.5
    for bad in ("-1", "25", "nan", "abc"):
        with pytest.raises(ValueError):
            parse_goal_hours(bad)


def test_goals_round_trip(db_path):
    uid = make_user(db_path)
    assert get_user_goals(db_path, uid) == {"growth_hours": None, "waste_limit_hours": None}
    upsert_user_goals(db_path, uid, 4.0, 3.0)
    upsert_user_goals(db_path, uid, 5.0, None)
    assert get_user_goals(db_path, uid) == {"growth_hours": 5.0, "waste_limit_hours": None}


def test_update_goals_route(db_path, login):
    uid = make_user(db_path)
    client = login(uid)
    resp = client.post("/settings/goals", data={"growth_hours": "4", "waste_limit_hours": "2.5"})
    assert resp.status_code == 302 and resp.headers["Location"].endswith("#goals-settings")
    assert get_user_goals(db_path, uid) == {"growth_hours": 4.0, "waste_limit_hours": 2.5}

    resp = client.post("/settings/goals", data={"growth_hours": "99", "waste_limit_hours": ""})
    assert get_user_goals(db_path, uid) == {"growth_hours": 4.0, "waste_limit_hours": 2.5}  # unchanged
    with client.session_transaction() as sess:
        assert "between 0 and 24" in sess["goals_error"]
    html = client.get("/settings").get_data(as_text=True)
    assert 'name="growth_hours"' in html and 'value="99"' in html  # typed value kept for correction
    html = client.get("/settings").get_data(as_text=True)
    assert 'value="99"' not in html and 'value="4"' in html  # one-shot: back to the saved goal


def test_goal_progress_day_and_week(db_path):
    uid = make_user(db_path)
    add_log(db_path, uid, "2026-09-14", "08:00:00", "2026-09-14", "13:00:00", urg=0, imp=1)  # 5h growth
    add_log(db_path, uid, "2026-09-14", "13:00:00", "2026-09-14", "15:00:00", urg=0, imp=0)  # 2h waste
    add_log(db_path, uid, "2026-09-15", "08:00:00", "2026-09-15", "10:00:00", urg=0, imp=1)  # 2h growth
    add_log(db_path, uid, "2026-09-15", "10:00:00", "2026-09-15", "16:00:00", urg=0, imp=0)  # 6h waste
    df = fetch_local_data(db_path, uid)
    goals = {"growth_hours": 4.0, "waste_limit_hours": 3.0}

    day = df[df["date"] == date(2026, 9, 15)]
    p = build_goal_progress(day, "day", date(2026, 9, 15), date(2026, 9, 15), goals, today=date(2026, 9, 15))
    assert p["growth"] == {"actual": 2.0, "target": 4.0, "pct": 50.0, "met": False}
    assert p["waste"] == {"actual": 6.0, "limit": 3.0, "pct": 100.0, "over": True}

    week = df[(df["date"] >= date(2026, 9, 13)) & (df["date"] <= date(2026, 9, 19))]
    p = build_goal_progress(week, "week", date(2026, 9, 13), date(2026, 9, 19), goals, today=date(2026, 9, 16))
    assert p["growth"] == {"target": 4.0, "met_days": 1, "days": 2}
    assert p["waste"] == {"limit": 3.0, "kept_days": 1, "days": 2}

    assert build_goal_progress(week, "week", date(2026, 9, 13), date(2026, 9, 19), {"growth_hours": None, "waste_limit_hours": None}) is None


def test_dashboard_renders_goals(db_path, login):
    uid = make_user(db_path)
    add_log(db_path, uid, "2026-09-20", "08:00:00", "2026-09-20", "10:00:00", urg=0, imp=1)
    upsert_user_goals(db_path, uid, 4.0, 3.0)
    html = login(uid).get("/?date=2026-09-20").get_data(as_text=True)
    assert "Daily goals" in html
    assert "2.0h" in html and "/ 4h" in html


def test_goal_streaks(db_path):
    from time_tracker_pro.services.insights import goal_streaks

    uid = make_user(db_path)
    # 15th: growth 5h (met), 16th: 5h (met), 17th: 1h (missed), 18th..19th: 4h (met), 20th: not logged yet
    hours = {"2026-09-15": 5, "2026-09-16": 5, "2026-09-17": 1, "2026-09-18": 4, "2026-09-19": 4}
    for day, h in hours.items():
        add_log(db_path, uid, day, "06:00:00", day, f"{6 + h:02d}:00:00", urg=0, imp=1)
        add_log(db_path, uid, day, "12:00:00", day, "14:00:00", urg=0, imp=0)  # 2h waste every day
    df = fetch_local_data(db_path, uid)
    goals = {"growth_hours": 4.0, "waste_limit_hours": 2.0}

    assert goal_streaks(df, date(2026, 9, 19), goals) == {"growth": 2, "waste": 5}
    # An unlogged "today" doesn't break yesterday's streak.
    assert goal_streaks(df, date(2026, 9, 20), goals) == {"growth": 2, "waste": 5}
    assert goal_streaks(df, date(2026, 9, 17), goals) == {"growth": 0, "waste": 3}
    assert goal_streaks(df, date(2026, 9, 16), {"growth_hours": 4.0, "waste_limit_hours": None}) == {"growth": 2}


def test_goal_calendar_week(db_path, login):
    uid = make_user(db_path)
    add_log(db_path, uid, "2026-09-14", "08:00:00", "2026-09-14", "13:00:00", urg=0, imp=1)  # 5h growth
    add_log(db_path, uid, "2026-09-15", "08:00:00", "2026-09-15", "10:00:00", urg=0, imp=1)  # 2h growth
    add_log(db_path, uid, "2026-09-15", "10:00:00", "2026-09-15", "16:00:00", urg=0, imp=0)  # 6h waste
    df = fetch_local_data(db_path, uid)
    goals = {"growth_hours": 4.0, "waste_limit_hours": 3.0}
    week = df[(df["date"] >= date(2026, 9, 13)) & (df["date"] <= date(2026, 9, 19))]
    p = build_goal_progress(week, "week", date(2026, 9, 13), date(2026, 9, 19), goals, today=date(2026, 9, 16))
    cal = p["calendar"]
    assert [c["date"] for c in cal] == [date(2026, 9, d) for d in range(13, 20)]
    assert [c["growth"] for c in cal] == ["none", "met", "missed", "none", "future", "future", "future"]
    assert [c["waste"] for c in cal] == ["none", "met", "missed", "none", "future", "future", "future"]
    assert cal[2]["growth_hours"] == 2.0 and cal[2]["waste_hours"] == 6.0

    only_growth = build_goal_progress(week, "week", date(2026, 9, 13), date(2026, 9, 19),
                                      {"growth_hours": 4.0, "waste_limit_hours": None}, today=date(2026, 9, 16))
    assert "waste" not in only_growth["calendar"][1]

    upsert_user_goals(db_path, uid, 4.0, 3.0)
    html = login(uid).get("/?date=2026-09-15&period=week").get_data(as_text=True)
    assert 'aria-label="Growth goal by day"' in html and 'aria-label="Waste limit by day"' in html
    assert 'href="/?date=2026-09-14&period=day" tabindex="-1" title="Mon 14 Sep: goal met (5h)"' in html
    assert 'title="Tue 15 Sep: over limit (6h)"' in html
    assert html.count('class="goal-dot is-') == 14


def test_goal_calendar_today_is_open_and_day_view_shows_last_7_days(db_path, login):
    uid = make_user(db_path)
    add_log(db_path, uid, "2026-09-15", "08:00:00", "2026-09-15", "10:00:00", urg=0, imp=1)  # 2h growth
    df = fetch_local_data(db_path, uid)
    goals = {"growth_hours": 4.0, "waste_limit_hours": None}
    week = df[(df["date"] >= date(2026, 9, 13)) & (df["date"] <= date(2026, 9, 19))]
    p = build_goal_progress(week, "week", date(2026, 9, 13), date(2026, 9, 19), goals, today=date(2026, 9, 15))
    assert p["calendar"][2]["growth"] == "open"  # today, below goal so far: not a miss yet
    assert p["growth"] == {"target": 4.0, "met_days": 0, "days": 1}

    upsert_user_goals(db_path, uid, 4.0, 3.0)
    html = login(uid).get("/?date=2026-09-15&period=day").get_data(as_text=True)
    assert 'aria-label="Growth goal, last 7 days by day"' not in html  # label reads naturally
    assert 'aria-label="Growth goal, last 7 days"' in html
    assert 'title="Tue 15 Sep: below goal (2h)"' in html  # a past day, so a real miss
    assert 'title="Wed 9 Sep: nothing logged"' in html
    assert html.count('class="goal-dot is-') == 14
