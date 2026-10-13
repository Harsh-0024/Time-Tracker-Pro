from datetime import date

import pytest
from werkzeug.datastructures import MultiDict

from conftest import add_log, make_user
from time_tracker_pro.repositories.goals import get_tag_goals, parse_tag_goals, replace_tag_goals
from time_tracker_pro.repositories.logs import fetch_local_data
from time_tracker_pro.services.insights import build_tag_goal_progress


def test_parse_tag_goals():
    form = MultiDict({
        "tag_goal_kind_Soul": "min", "tag_goal_hours_Soul": "1",
        "tag_goal_kind_Rest": "max", "tag_goal_hours_Rest": "2.5",
        "tag_goal_kind_Work": "", "tag_goal_hours_Work": "6",  # Off: hours ignored
    })
    assert parse_tag_goals(form) == [
        {"tag": "Soul", "kind": "min", "hours": 1.0},
        {"tag": "Rest", "kind": "max", "hours": 2.5},
    ]
    for bad in (
        {"tag_goal_kind_Soul": "min", "tag_goal_hours_Soul": ""},
        {"tag_goal_kind_Soul": "min", "tag_goal_hours_Soul": "30"},
        {"tag_goal_kind_Soul": "sometimes", "tag_goal_hours_Soul": "1"},
        {"tag_goal_kind_Soul": "min", "tag_goal_hours_Soul": "abc"},
    ):
        with pytest.raises(ValueError):
            parse_tag_goals(MultiDict(bad))


def test_tag_goals_round_trip_and_order(db_path):
    uid = make_user(db_path)
    replace_tag_goals(db_path, uid, [{"tag": "Waste", "kind": "max", "hours": 3.0}, {"tag": "Work", "kind": "min", "hours": 6.0}])
    assert [g["tag"] for g in get_tag_goals(db_path, uid)] == ["Work", "Waste"]
    replace_tag_goals(db_path, uid, [])
    assert get_tag_goals(db_path, uid) == []


def test_tag_goal_progress_day_and_week(db_path):
    uid = make_user(db_path)
    add_log(db_path, uid, "2026-09-14", "08:00:00", "2026-09-14", "10:00:00", tags="Soul")
    add_log(db_path, uid, "2026-09-14", "10:00:00", "2026-09-14", "11:00:00", tags="Rest")
    add_log(db_path, uid, "2026-09-15", "08:00:00", "2026-09-15", "08:30:00", tags="Soul")
    add_log(db_path, uid, "2026-09-15", "09:00:00", "2026-09-15", "13:00:00", tags="Rest")
    df = fetch_local_data(db_path, uid)
    goals = [{"tag": "Soul", "kind": "min", "hours": 1.0}, {"tag": "Rest", "kind": "max", "hours": 2.0}]

    day = df[df["date"] == date(2026, 9, 15)]
    p = build_tag_goal_progress(day, "day", date(2026, 9, 15), date(2026, 9, 15), goals, today=date(2026, 9, 20))
    soul, rest = p["items"]
    assert (soul["actual"], soul["pct"], soul["ok"]) == (0.5, 50.0, False)
    assert (rest["actual"], rest["pct"], rest["ok"]) == (4.0, 100.0, False)

    week = df[(df["date"] >= date(2026, 9, 13)) & (df["date"] <= date(2026, 9, 19))]
    p = build_tag_goal_progress(week, "week", date(2026, 9, 13), date(2026, 9, 19), goals, today=date(2026, 9, 15))
    assert [(i["met_days"], i["days"]) for i in p["items"]] == [(1, 2), (1, 2)]
    cal = {c["date"].day: c for c in p["calendar"]}
    assert cal[13]["tag_Soul"] == "none"
    assert cal[14]["tag_Soul"] == "met" and cal[14]["tag_Rest"] == "met"
    assert cal[15]["tag_Soul"] == "open"  # today, 'at least' not missed yet
    assert cal[15]["tag_Rest"] == "missed"  # 'at most' already exceeded
    assert cal[16]["tag_Soul"] == "future"


def test_settings_and_dashboard_show_tag_goals(db_path, login):
    uid = make_user(db_path)
    add_log(db_path, uid, "2026-09-20", "08:00:00", "2026-09-20", "10:00:00", tags="Soul")
    client = login(uid)
    resp = client.post("/settings/goals", data={"tag_goal_kind_Soul": "min", "tag_goal_hours_Soul": "1"})
    assert resp.status_code == 302
    assert get_tag_goals(db_path, uid) == [{"tag": "Soul", "kind": "min", "hours": 1.0}]
    settings = client.get("/settings").get_data(as_text=True)
    assert 'name="tag_goal_kind_Soul"' in settings
    html = client.get("/?date=2026-09-20").get_data(as_text=True)
    assert "Daily goals" in html and "2.0h" in html and "/ 1h" in html

    # A bad value keeps what was typed and leaves saved goals alone.
    client.post("/settings/goals", data={"tag_goal_kind_Rest": "max", "tag_goal_hours_Rest": ""})
    assert get_tag_goals(db_path, uid) == [{"tag": "Soul", "kind": "min", "hours": 1.0}]
    with client.session_transaction() as sess:
        assert "Rest" in sess["goals_error"]
        assert sess["goals_form"]["tag_goal_kind_Rest"] == "max"


def test_copy_summary_mentions_tag_goals(db_path, login):
    uid = make_user(db_path)
    add_log(db_path, uid, "2026-09-20", "08:00:00", "2026-09-20", "10:00:00", tags="Soul")
    replace_tag_goals(db_path, uid, [{"tag": "Soul", "kind": "min", "hours": 1.0}])
    import json
    import re

    html = login(uid).get("/?date=2026-09-20").get_data(as_text=True)
    raw = re.search(r'id="periodSummaryText">(.*?)</script>', html, re.S).group(1)
    assert "Soul ≥ 1.0h: 2.0h ✓" in json.loads(raw)


def test_graphs_page_exposes_tag_goals(db_path, login):
    uid = make_user(db_path)
    replace_tag_goals(db_path, uid, [{"tag": "Soul", "kind": "min", "hours": 1.0}])
    html = login(uid).get("/graphs").get_data(as_text=True)
    assert 'const USER_TAG_GOALS = [{"hours": 1.0, "kind": "min", "tag": "Soul"}];' in html
