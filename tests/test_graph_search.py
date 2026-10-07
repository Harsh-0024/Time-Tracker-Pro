from conftest import add_log, make_user
from time_tracker_pro.web.api import parse_graph_search


def test_comma_is_or_with_or_without_spaces():
    expected = ("or", ("term", "sleep"), ("term", "rest"))
    # 'sleep, rest' is the search box's own placeholder example; the comma used to
    # stick to 'sleep,' and the query matched nothing.
    for query in ("sleep, rest", "sleep,rest", "sleep , rest"):
        assert parse_graph_search(query) == expected


def test_quoted_term_keeps_its_comma():
    assert parse_graph_search('"a, b"') == ("term", "a, b")


def test_graph_data_comma_search_matches_both(db_path, login):
    uid = make_user(db_path)
    add_log(db_path, uid, "2026-10-01", "08:00:00", "2026-10-01", "09:00:00", task="Sleep", tags="Rest")
    add_log(db_path, uid, "2026-10-01", "09:00:00", "2026-10-01", "10:00:00", task="Nap", tags="Rest")
    add_log(db_path, uid, "2026-10-01", "10:00:00", "2026-10-01", "11:00:00", task="Gym", tags="Soul")
    data = login(uid).get("/api/graph-data?days=7&end=2026-10-02&search=sleep, gym&include_tasks=1").get_json()
    assert sorted(t["task"] for t in data["tasks"]) == ["Gym", "Sleep"]
