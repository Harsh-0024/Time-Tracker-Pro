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
    assert get_user_goals(db_path, uid) == {"growth_hours": None, "waste_limit_hours": None, "sleep_hours": None}
    upsert_user_goals(db_path, uid, 4.0, 3.0)
    upsert_user_goals(db_path, uid, 5.0, None)
    assert get_user_goals(db_path, uid) == {"growth_hours": 5.0, "waste_limit_hours": None, "sleep_hours": None}


def test_update_goals_route(db_path, login):
    uid = make_user(db_path)
    client = login(uid)
    resp = client.post("/settings/goals", data={"growth_hours": "4", "waste_limit_hours": "2.5"})
    assert resp.status_code == 302 and resp.headers["Location"].endswith("#goals-settings")
    assert get_user_goals(db_path, uid) == {"growth_hours": 4.0, "waste_limit_hours": 2.5, "sleep_hours": None}

    resp = client.post("/settings/goals", data={"growth_hours": "99", "waste_limit_hours": ""})
    assert get_user_goals(db_path, uid) == {"growth_hours": 4.0, "waste_limit_hours": 2.5, "sleep_hours": None}  # unchanged
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

    assert goal_streaks(df, date(2026, 9, 19), goals) == {"growth": 2, "growth_best": 2, "waste": 5, "waste_best": 5}
    # An unlogged "today" doesn't break yesterday's streak.
    assert goal_streaks(df, date(2026, 9, 20), goals) == {"growth": 2, "growth_best": 2, "waste": 5, "waste_best": 5}
    assert goal_streaks(df, date(2026, 9, 17), goals) == {"growth": 0, "growth_best": 2, "waste": 3, "waste_best": 3}
    assert goal_streaks(df, date(2026, 9, 16), {"growth_hours": 4.0, "waste_limit_hours": None}) == {"growth": 2, "growth_best": 2}


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


def test_goal_streak_survives_todays_partial_growth(db_path):
    from time_tracker_pro.services.insights import goal_streaks

    uid = make_user(db_path)
    for day in ("2026-09-15", "2026-09-16"):
        add_log(db_path, uid, day, "06:00:00", day, "11:00:00", urg=0, imp=1)  # 5h growth (met)
    add_log(db_path, uid, "2026-09-17", "06:00:00", "2026-09-17", "07:00:00", urg=0, imp=1)  # 1h so far
    add_log(db_path, uid, "2026-09-17", "07:00:00", "2026-09-17", "11:00:00", urg=0, imp=0)  # 4h waste
    df = fetch_local_data(db_path, uid)
    goals = {"growth_hours": 4.0, "waste_limit_hours": 2.0}
    # Today (17th) is in progress: Growth keeps yesterday's run, an exceeded Waste limit is final.
    assert goal_streaks(df, date(2026, 9, 17), goals, today=date(2026, 9, 17)) == {"growth": 2, "growth_best": 2, "waste": 0, "waste_best": 2}
    # Once the day is over, the shortfall is a miss.
    assert goal_streaks(df, date(2026, 9, 17), goals, today=date(2026, 9, 18)) == {"growth": 0, "growth_best": 2, "waste": 0, "waste_best": 2}


def test_goal_best_streak_skips_gaps(db_path):
    from time_tracker_pro.services.insights import goal_streaks

    uid = make_user(db_path)
    # Met on 1-3 (run of 3), unlogged 4th, met 5-6, missed 7th, met 8th.
    for day, h in {1: 5, 2: 5, 3: 5, 5: 5, 6: 5, 7: 1, 8: 5}.items():
        d = f"2026-09-{day:02d}"
        add_log(db_path, uid, d, "06:00:00", d, f"{6 + h:02d}:00:00", urg=0, imp=1)
    df = fetch_local_data(db_path, uid)
    s = goal_streaks(df, date(2026, 9, 8), {"growth_hours": 4.0, "waste_limit_hours": None}, today=date(2026, 10, 1))
    assert s == {"growth": 1, "growth_best": 3}


def test_dashboard_shows_best_streak(db_path, login):
    uid = make_user(db_path)
    for day, h in {1: 5, 2: 5, 3: 5, 5: 5, 6: 5, 7: 1}.items():
        d = f"2026-09-{day:02d}"
        add_log(db_path, uid, d, "06:00:00", d, f"{6 + h:02d}:00:00", urg=0, imp=1)
    upsert_user_goals(db_path, uid, 4.0, None)
    client = login(uid)
    html = client.get("/?date=2026-09-06&period=day").get_data(as_text=True)
    assert "🔥 2-day Growth streak" in html and "· best 3" in html
    html = client.get("/?date=2026-09-07&period=day").get_data(as_text=True)
    assert "Growth streak" in html and "Best Growth streak: 3 days" in html and "🔥" not in html.split("Best Growth streak")[0][-300:]


def _sleep_nights(db_path, uid):
    # Nights ending Sep 14 (8h), Sep 15 (6h), Sep 16 (7.5h, split at midnight).
    add_log(db_path, uid, "2026-09-13", "23:00:00", "2026-09-14", "07:00:00", task="Sleep")
    add_log(db_path, uid, "2026-09-15", "01:00:00", "2026-09-15", "07:00:00", task="Sleep")
    add_log(db_path, uid, "2026-09-15", "23:30:00", "2026-09-16", "00:00:00", task="Sleep")
    add_log(db_path, uid, "2026-09-16", "00:00:00", "2026-09-16", "07:00:00", task="Sleep")


def test_sleep_goal_saved_and_shown(db_path, login):
    import json
    import re

    uid = make_user(db_path)
    _sleep_nights(db_path, uid)
    client = login(uid)
    client.post("/settings/goals", data={"growth_hours": "", "waste_limit_hours": "", "sleep_hours": "7"})
    assert get_user_goals(db_path, uid)["sleep_hours"] == 7.0
    assert 'name="sleep_hours"' in client.get("/settings").get_data(as_text=True)

    week = client.get("/?date=2026-09-15&period=week").get_data(as_text=True)
    assert "Sleep ≥ 7h" in week and ">2</span> / 3 nights" in week
    assert "goal met (8h)" in week and "below goal (6h)" in week

    day = client.get("/?date=2026-09-16").get_data(as_text=True)
    assert "7.5h <span" in day and "Sleep goal" in day
    summary = json.loads(re.search(r'id="periodSummaryText">(.*?)</script>', day, re.S).group(1))
    assert "Sleep ≥ 7.0h: 7.5h ✓" in summary
    # A day whose night isn't logged: no Sleep goal row (rather than "0h / 7h").
    assert "Sleep goal" not in client.get("/?date=2026-09-17").get_data(as_text=True)


def test_sleep_goal_column_added_to_old_databases(tmp_path):
    import sqlite3

    from time_tracker_pro.db import init_db

    path = str(tmp_path / "old.db")
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE user_goals (user_id INTEGER PRIMARY KEY, growth_hours REAL, waste_limit_hours REAL, updated_at TEXT)")
    conn.execute("INSERT INTO user_goals VALUES (1, 4, 2, 'x')")
    conn.commit()
    conn.close()
    init_db(path)
    assert get_user_goals(path, 1) == {"growth_hours": 4.0, "waste_limit_hours": 2.0, "sleep_hours": None}


def test_json_export_includes_goals(db_path, login):
    import json

    uid = make_user(db_path)
    client = login(uid)
    client.post("/settings/goals", data={"growth_hours": "4", "waste_limit_hours": "", "sleep_hours": "7.5",
                                          "tag_goal_kind_Soul": "min", "tag_goal_hours_Soul": "1"})
    data = json.loads(client.get("/api/export-csv?mode=all&format=json").get_data(as_text=True))
    assert data["goals"] == {"growth_hours": 4.0, "waste_limit_hours": None, "sleep_hours": 7.5}
    assert data["category_goals"] == [{"tag": "Soul", "kind": "min", "hours": 1.0}]


def test_settings_shows_recent_averages_next_to_goals(db_path, login):
    from datetime import timedelta

    from time_tracker_pro.services.insights import recent_goal_averages

    uid = make_user(db_path)
    today = date(2026, 9, 20)
    for offset in (1, 2):  # two logged days, 3h growth + 1h waste each, 7h sleep each night
        day = today - timedelta(days=offset)
        prev = day - timedelta(days=1)
        add_log(db_path, uid, str(prev), "23:00:00", str(day), "06:00:00", task="Sleep", urg=0, imp=1)
        add_log(db_path, uid, str(day), "09:00:00", str(day), "12:00:00", task="Study", urg=0, imp=1)
        add_log(db_path, uid, str(day), "20:00:00", str(day), "21:00:00", task="Scrolling", urg=0, imp=0)
    averages = recent_goal_averages(fetch_local_data(db_path, uid), today=today)
    # Logged days: Sep 17 (the first night's start), 18, 19 -> 2h waste over 3 days.
    assert averages["sleep"] == 7.0 and averages["waste"] == 0.7
    assert averages["tags"] == {"Work": 7.3}  # add_log tags everything Work: (14 + 6 + 2) h / 3 days
    assert recent_goal_averages(fetch_local_data(db_path, uid), today=date(2027, 1, 1)) == {
        "growth": None, "waste": None, "sleep": None, "tags": {},
    }
    html = login(uid).get("/settings").get_data(as_text=True)
    assert 'name="sleep_hours"' in html


def test_sleep_goal_streak_on_day_view(db_path, login):
    uid = make_user(db_path)
    # 8h nights ending Sep 14, 15, 16; 5h night ending Sep 17; 8h ending Sep 18 and 19.
    # Split at midnight like real logs, so each wake-up day has its own rows.
    for wake in ("14", "15", "16", "18", "19"):
        add_log(db_path, uid, f"2026-09-{int(wake) - 1:02d}", "23:00:00", f"2026-09-{wake}", "00:00:00", task="Sleep")
        add_log(db_path, uid, f"2026-09-{wake}", "00:00:00", f"2026-09-{wake}", "07:00:00", task="Sleep")
    add_log(db_path, uid, "2026-09-17", "02:00:00", "2026-09-17", "07:00:00", task="Sleep")
    client = login(uid)
    client.post("/settings/goals", data={"growth_hours": "", "waste_limit_hours": "", "sleep_hours": "7"})
    day16 = client.get("/?date=2026-09-16").get_data(as_text=True)
    assert "3 nights in a row" in day16
    import json
    import re

    summary = json.loads(re.search(r'id="periodSummaryText">(.*?)</script>', day16, re.S).group(1))
    assert "Sleep ≥ 7.0h: 8.0h ✓ (3 nights in a row)" in summary
    html = client.get("/?date=2026-09-19").get_data(as_text=True)
    assert "2 nights in a row" in html and "best 3" in html
    assert "Best sleep streak: 3 nights" in client.get("/?date=2026-09-17").get_data(as_text=True)


def test_week_sleep_insight_shows_debt_against_goal(db_path, login):
    from datetime import date as _date

    from time_tracker_pro.services.sleep import sleep_debt

    uid = make_user(db_path)
    _sleep_nights(db_path, uid)  # 8h, 6h, 7.5h nights ending Sep 14-16
    df = fetch_local_data(db_path, uid)
    assert sleep_debt(df, _date(2026, 9, 13), _date(2026, 9, 19), 7.0) == {"hours": 1.0, "nights": 1}
    assert sleep_debt(df, _date(2026, 9, 13), _date(2026, 9, 19), 9.0) == {"hours": 5.5, "nights": 3}
    client = login(uid)
    client.post("/settings/goals", data={"growth_hours": "", "waste_limit_hours": "", "sleep_hours": "7"})
    assert "1.0h short of your 7h goal over 1 night" in client.get("/?date=2026-09-15&period=week").get_data(as_text=True)
