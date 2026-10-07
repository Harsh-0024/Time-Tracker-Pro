from datetime import date

from conftest import add_log, make_user
from time_tracker_pro.repositories.logs import fetch_local_data
from time_tracker_pro.services.matrix import get_matrix_stats
from time_tracker_pro.web.main import _matrix_share_deltas, _previous_period_range


def test_previous_period_range():
    assert _previous_period_range(date(2026, 9, 20), "day") == (date(2026, 9, 19), date(2026, 9, 19))
    assert _previous_period_range(date(2026, 9, 23), "week") == (date(2026, 9, 13), date(2026, 9, 19))
    assert _previous_period_range(date(2026, 3, 31), "month") == (date(2026, 2, 1), date(2026, 2, 28))
    assert _previous_period_range(date(2026, 1, 15), "month") == (date(2025, 12, 1), date(2025, 12, 31))


def test_share_deltas_compare_shares_not_hours(db_path):
    uid = make_user(db_path)
    # Yesterday: 1h growth (q2) out of 4h => 25%.
    add_log(db_path, uid, "2026-09-19", "08:00:00", "2026-09-19", "09:00:00", urg=0, imp=1)
    add_log(db_path, uid, "2026-09-19", "09:00:00", "2026-09-19", "12:00:00", urg=0, imp=0)
    # Today so far: 1h growth out of 2h => 50%.
    add_log(db_path, uid, "2026-09-20", "08:00:00", "2026-09-20", "09:00:00", urg=0, imp=1)
    add_log(db_path, uid, "2026-09-20", "09:00:00", "2026-09-20", "10:00:00", urg=0, imp=0)

    df = fetch_local_data(db_path, uid)
    today = df[df["date"] == date(2026, 9, 20)]
    deltas = _matrix_share_deltas(df, get_matrix_stats(today), date(2026, 9, 20), "day")

    assert deltas["q2"] == 25.0
    assert deltas["q4"] == -25.0


def test_share_deltas_empty_without_previous_data(db_path):
    uid = make_user(db_path)
    add_log(db_path, uid, "2026-09-20", "08:00:00", "2026-09-20", "09:00:00")
    df = fetch_local_data(db_path, uid)
    assert _matrix_share_deltas(df, get_matrix_stats(df), date(2026, 9, 20), "day") == {}


def test_dashboard_renders_with_deltas(db_path, login):
    uid = make_user(db_path)
    add_log(db_path, uid, "2026-09-19", "08:00:00", "2026-09-19", "09:00:00", urg=0, imp=1)
    add_log(db_path, uid, "2026-09-20", "08:00:00", "2026-09-20", "09:00:00", urg=0, imp=0)
    resp = login(uid).get("/?date=2026-09-20")
    assert resp.status_code == 200
    assert b"share-delta" in resp.data


def test_today_insights_framed_as_so_far(db_path, login):
    from datetime import datetime, timedelta

    uid = make_user(db_path)
    today = datetime.now().date()
    for back in range(1, 4):
        d = (today - timedelta(days=back)).isoformat()
        add_log(db_path, uid, d, "08:00:00", d, "12:00:00", urg=0, imp=1)
    t = today.isoformat()
    add_log(db_path, uid, t, "08:00:00", t, "09:00:00", urg=0, imp=1)
    client = login(uid)

    html = client.get("/").get_data(as_text=True)
    assert "Today so far vs your last" in html
    assert "3.0h to reach your average" in html

    past = (today - timedelta(days=1)).isoformat()
    html = client.get(f"/?date={past}").get_data(as_text=True)
    assert "Today so far" not in html


def test_default_app_icon_is_a_real_png(app):
    resp = app.test_client().get("/app-icon.png")
    assert resp.status_code == 200
    assert resp.data.startswith(b"\x89PNG")
    # IHDR width/height: the old fallback was a 1x1 transparent pixel.
    assert int.from_bytes(resp.data[16:20], "big") == 512


def test_favicon_redirects_to_icon(app):
    resp = app.test_client().get("/favicon.ico")
    assert resp.status_code == 302
    assert "/app-icon.png" in resp.headers["Location"]


def test_logged_coverage():
    from time_tracker_pro.web.main import _logged_coverage

    d = date(2026, 9, 20)
    assert _logged_coverage(12.0, d, d, today=d) == 50.0
    assert _logged_coverage(24.0, d, d, today=d) == 100.0
    # Week in progress: only started days count (Sun 13 .. Tue 15 = 3 days).
    assert _logged_coverage(48.0, date(2026, 9, 13), date(2026, 9, 19), today=date(2026, 9, 15)) == round(48 / 72 * 100, 1)
    # Future period compares against its full length.
    assert _logged_coverage(0.0, date(2026, 10, 1), date(2026, 10, 31), today=date(2026, 9, 15)) == 0.0
    assert _logged_coverage(30.0, d, d, today=d) == 100.0


def test_new_user_sees_onboarding(db_path, login):
    uid = make_user(db_path)
    html = login(uid).get("/").get_data(as_text=True)
    assert "welcomeTitle" in html
    assert "Connect sheet" in html


def test_onboarding_hidden_once_logs_exist(db_path, login):
    uid = make_user(db_path)
    add_log(db_path, uid, "2026-09-20", "08:00:00", "2026-09-20", "09:00:00")
    html = login(uid).get("/?date=2026-09-20").get_data(as_text=True)
    assert "welcomeTitle" not in html


def test_week_label(db_path, login):
    uid = make_user(db_path)
    add_log(db_path, uid, "2026-09-16", "08:00:00", "2026-09-16", "09:00:00")
    client = login(uid)
    assert "Sep 13 – 19, 2026" in client.get("/?date=2026-09-16&period=week").get_data(as_text=True)
    assert "Sep 27 – Oct 3, 2026" in client.get("/?date=2026-09-30&period=week").get_data(as_text=True)
    assert "Dec 27, 2026 – Jan 2, 2027" in client.get("/?date=2026-12-30&period=week").get_data(as_text=True)


def test_security_headers(app):
    resp = app.test_client().get("/login")
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "SAMEORIGIN"
    assert resp.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


def test_empty_period_offers_nearest_logged_days(db_path, login):
    uid = make_user(db_path)
    add_log(db_path, uid, "2026-09-10", "08:00:00", "2026-09-10", "09:00:00")
    add_log(db_path, uid, "2026-09-25", "08:00:00", "2026-09-25", "09:00:00")
    html = login(uid).get("/?date=2026-09-20").get_data(as_text=True)
    assert "Nothing logged on Sun, Sep 20 yet" in html
    assert "/?date=2026-09-10&amp;period=day" in html or "/?date=2026-09-10&period=day" in html
    assert "Sep 25 →" in html


def test_no_empty_period_card_when_period_has_logs(db_path, login):
    uid = make_user(db_path)
    add_log(db_path, uid, "2026-09-20", "08:00:00", "2026-09-20", "09:00:00")
    assert "Nothing logged" not in login(uid).get("/?date=2026-09-20").get_data(as_text=True)


def test_dashboard_shows_longest_growth_block(db_path, login):
    from conftest import add_log, make_user

    uid = make_user(db_path, username="blocky", email="blocky@example.com")
    add_log(db_path, uid, "2026-09-21", "09:00:00", "2026-09-21", "12:30:00", task="Deep <work>", urg=0, imp=1)
    client = login(uid)
    for url in ("/?date=2026-09-21", "/?date=2026-09-21&period=week"):
        html = client.get(url).get_data(as_text=True)
        assert "Longest growth block" in html, url
        assert "Deep &lt;work&gt;" in html and "Deep <work>" not in html
    assert 'href="/?date=2026-09-21&period=day"' in client.get("/?date=2026-09-21&period=week").get_data(as_text=True)


def test_top_category_share_uses_unrounded_hours(db_path, login):
    uid = make_user(db_path)
    # Waste 4.5h of 10.25h = 43.9%; from rounded hours (4.5/10.3) it read 43.7%.
    add_log(db_path, uid, "2026-03-04", "08:00", "2026-03-04", "12:30", task="Scroll", tags="Waste", urg=0, imp=0)
    add_log(db_path, uid, "2026-03-04", "12:30", "2026-03-04", "15:30", task="Build", tags="Work", urg=1, imp=1)
    add_log(db_path, uid, "2026-03-04", "15:30", "2026-03-04", "18:15", task="Gym", tags="Soul", urg=0, imp=1)
    html = login(uid).get("/?date=2026-03-04&period=day").get_data(as_text=True)
    assert "43.9% of period" in html
