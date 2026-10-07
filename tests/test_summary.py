import json
import re

from conftest import add_log, make_user
from time_tracker_pro.services.summary import build_period_summary_text


def _summary(html):
    m = re.search(r'id="periodSummaryText">(.*?)</script>', html, re.S)
    return json.loads(m.group(1)) if m else None


def test_summary_text_empty_period_is_blank():
    assert build_period_summary_text("Tue 6 Oct 2026", "day", {"total_hours": 0}, 0.0, {}) == ""


def test_week_page_summary_matches_numbers(db_path, login):
    uid = make_user(db_path)
    add_log(db_path, uid, "2026-09-28", "08:00:00", "2026-09-28", "10:00:00", task="Gym", tags="Work", urg=0, imp=1)
    add_log(db_path, uid, "2026-10-05", "08:00:00", "2026-10-05", "11:00:00", task="Gym .", tags="Work", urg=0, imp=1)
    add_log(db_path, uid, "2026-10-05", "11:00:00", "2026-10-05", "12:00:00", task="Scrolling", tags="Waste", urg=0, imp=0)
    html = login(uid).get("/?period=week&date=2026-10-05").get_data(as_text=True)
    assert 'id="copySummaryBtn"' in html
    text = _summary(html)
    assert text.splitlines()[0] == "Time Tracker Pro · Oct 4 – 10, 2026"
    assert "Growth 3.0h (75%) · Critical 0.0h (0%) · Drudgery 0.0h (0%) · Waste 1.0h (25%)" in text
    assert "- Gym: 3.0h (75%)" in text
    assert "(+1.0h growth, +1.0h waste vs last week)" in text
    assert "Best growth day: Mon 5 Oct (3.0h)" in text


def test_day_page_summary_and_empty_day(db_path, login):
    uid = make_user(db_path)
    add_log(db_path, uid, "2026-10-04", "08:00:00", "2026-10-04", "10:00:00", task="Read", tags="Soul", urg=0, imp=1)
    add_log(db_path, uid, "2026-10-05", "08:00:00", "2026-10-05", "09:00:00", task="Read", tags="Soul", urg=0, imp=1)
    client = login(uid)
    text = _summary(client.get("/?period=day&date=2026-10-05").get_data(as_text=True))
    assert text.startswith("Time Tracker Pro · Mon 5 Oct 2026\nLogged 1.0h (4% of the day)")
    assert "vs your last 1 day: growth 1.0h (avg 2.0h), waste 0.0h (avg 0.0h)" in text
    html = client.get("/?period=day&date=2026-10-06").get_data(as_text=True)
    assert 'id="copySummaryBtn"' not in html and _summary(html) is None


def test_summary_json_is_script_safe(db_path, login):
    uid = make_user(db_path)
    add_log(db_path, uid, "2026-10-05", "08:00:00", "2026-10-05", "09:00:00", task="x</script><img src=x onerror=alert(1)>", tags="Soul")
    html = login(uid).get("/?period=day&date=2026-10-05").get_data(as_text=True)
    block = re.search(r'id="periodSummaryText">(.*?)</script>', html, re.S).group(1)
    assert "<" not in block
    assert "x</script><img src=x onerror=alert(1)>" in json.loads(block)


def test_day_summary_mentions_goal_streak(db_path, login):
    from time_tracker_pro.repositories.goals import upsert_user_goals

    uid = make_user(db_path)
    for d in ("2026-09-14", "2026-09-15"):
        add_log(db_path, uid, d, "08:00:00", d, "13:00:00", task="Study", tags="Work", urg=0, imp=1)
    upsert_user_goals(db_path, uid, 4.0, 2.0)
    text = _summary(login(uid).get("/?date=2026-09-15&period=day").get_data(as_text=True))
    assert "Growth goal: 5.0h of 4.0h (2-day streak)" in text
    assert "Waste limit: 0.0h of 2.0h (2 days in a row under)" in text
