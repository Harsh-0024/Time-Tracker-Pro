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
