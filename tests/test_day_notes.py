import json
import re
from datetime import date

from conftest import add_log, make_user
from time_tracker_pro.repositories.day_notes import get_day_note, get_day_notes


def _summary(html):
    m = re.search(r'id="periodSummaryText">(.*?)</script>', html, re.S)
    return json.loads(m.group(1)) if m else None


def test_put_day_note_saves_updates_and_clears(db_path, login):
    uid = make_user(db_path)
    client = login(uid)
    resp = client.put("/api/day-notes/2026-09-15", json={"note": "  Good focus.\r\nGym after.  "})
    assert resp.status_code == 200 and resp.get_json() == {"day": "2026-09-15", "note": "Good focus.\nGym after."}
    assert get_day_note(db_path, uid, date(2026, 9, 15)) == "Good focus.\nGym after."
    client.put("/api/day-notes/2026-09-15", json={"note": "Edited"})
    assert get_day_note(db_path, uid, date(2026, 9, 15)) == "Edited"
    client.put("/api/day-notes/2026-09-15", json={"note": "   "})
    assert get_day_note(db_path, uid, date(2026, 9, 15)) is None


def test_put_day_note_validation_and_isolation(db_path, login, app):
    uid = make_user(db_path)
    other = make_user(db_path, username="bob", email="bob@example.com")
    client = login(uid)
    assert client.put("/api/day-notes/2026-13-01", json={"note": "x"}).status_code == 400
    assert client.put("/api/day-notes/yesterday", json={"note": "x"}).status_code == 400
    assert client.put("/api/day-notes/2026-09-15", json={"note": "x" * 1001}).status_code == 400
    assert client.put("/api/day-notes/2026-09-15", json=["not", "an", "object"]).status_code == 200  # empty note
    assert client.put("/api/day-notes/2026-09-15", json={"note": 42}).get_json()["note"] == "42"
    login(other).put("/api/day-notes/2026-09-15", json={"note": "Bob's day"})
    assert get_day_note(db_path, uid, date(2026, 9, 15)) == "42"
    assert get_day_note(db_path, other, date(2026, 9, 15)) == "Bob's day"
    # Not logged in: no access.
    assert app.test_client().put("/api/day-notes/2026-09-15", json={"note": "x"}).status_code == 401


def test_dashboard_day_shows_note_box_and_summary(db_path, login):
    uid = make_user(db_path)
    add_log(db_path, uid, "2026-09-15", "08:00:00", "2026-09-15", "10:00:00", task="Study", tags="Work", urg=0, imp=1)
    client = login(uid)
    client.put("/api/day-notes/2026-09-15", json={"note": "Slept badly <b>but</b> studied"})
    html = client.get("/?date=2026-09-15&period=day").get_data(as_text=True)
    assert 'id="dayNoteInput"' in html and 'data-day="2026-09-15"' in html
    assert "Slept badly &lt;b&gt;but&lt;/b&gt; studied</textarea>" in html
    assert _summary(html).endswith("Note: Slept badly <b>but</b> studied")


def test_dashboard_week_lists_notes(db_path, login):
    uid = make_user(db_path)
    add_log(db_path, uid, "2026-09-15", "08:00:00", "2026-09-15", "10:00:00", task="Study", tags="Work", urg=0, imp=1)
    client = login(uid)
    client.put("/api/day-notes/2026-09-16", json={"note": "Second"})
    client.put("/api/day-notes/2026-09-14", json={"note": "First"})
    client.put("/api/day-notes/2026-09-21", json={"note": "Next week"})
    html = client.get("/?date=2026-09-15&period=week").get_data(as_text=True)
    assert 'id="dayNoteInput"' not in html
    first, second = html.index(">Mon 14 Sep</a>"), html.index(">Wed 16 Sep</a>")
    assert first < second and "Next week" not in html.split('id="periodSummaryText"')[0]
    assert "Notes:\n- Mon 14 Sep: First\n- Wed 16 Sep: Second" in _summary(html)
    assert list(get_day_notes(db_path, uid, date(2026, 9, 13), date(2026, 9, 19))) == [date(2026, 9, 14), date(2026, 9, 16)]


def test_deleting_user_removes_notes(db_path, login):
    from time_tracker_pro.repositories.admin import delete_user_cascade

    uid = make_user(db_path)
    login(uid).put("/api/day-notes/2026-09-15", json={"note": "x"})
    delete_user_cascade(db_path, uid)
    assert get_day_note(db_path, uid, date(2026, 9, 15)) is None
