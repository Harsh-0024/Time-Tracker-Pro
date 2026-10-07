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


def test_vectorised_search_matches_row_by_row(db_path):
    from time_tracker_pro.repositories.logs import fetch_local_data
    from time_tracker_pro.web.api import graph_row_matches, graph_search_mask

    uid = make_user(db_path)
    rows = [
        ("Gym", "Soul", 0, 1), ("Sleep", "Rest", 1, 1), ("Instagram .", "Waste", 0, 0),
        ("Deep work", "Work, Soul", 1, 1), ("  Spaced   Out ", "Rest,Sleep", 0, 0), ("Call", "urgent stuff", 1, 0),
    ]
    for i, (task, tags, urg, imp) in enumerate(rows):
        add_log(db_path, uid, f"2026-10-0{i + 1}", "08:00:00", f"2026-10-0{i + 1}", "09:00:00", task=task, tags=tags, urg=urg, imp=imp)
    df = fetch_local_data(db_path, uid)
    for query in ["gym", "sleep, rest", "important and not work", "only sleep", "spaced out", "stuff",
                  "2026", "(gym or call) and not important", "NOT waste", "work+waste-urgent", "urgent"]:
        expr = parse_graph_search(query)
        expected = [bool(graph_row_matches(row, expr)) for _, row in df.iterrows()]
        assert graph_search_mask(df, expr).tolist() == expected, query


def test_graph_data_by_hour(db_path, login):
    uid = make_user(db_path)
    # Two days plotted; 08:30-10:00 on day 1 and an overnight 23:00-01:00 into day 2.
    add_log(db_path, uid, "2026-10-01", "08:30:00", "2026-10-01", "10:00:00", task="Gym", tags="Soul")
    add_log(db_path, uid, "2026-10-01", "23:00:00", "2026-10-02", "01:00:00", task="Read", tags="Soul")
    data = login(uid).get("/api/graph-data?days=2&end=2026-10-02").get_json()
    by_hour = data["by_hour"]
    assert len(by_hour) == 24
    assert by_hour[8] == 15.0 and by_hour[9] == 30.0  # 30 and 60 minutes over 2 days
    assert by_hour[23] == 30.0 and by_hour[0] == 30.0
    assert sum(by_hour) == 105.0
    empty = login(uid).get("/api/graph-data?days=2&end=2026-09-01").get_json()
    assert empty["by_hour"] == [0] * 24


def test_only_ignores_trailing_sheet_punctuation(db_path, login):
    uid = make_user(db_path)
    add_log(db_path, uid, "2026-10-01", "08:00:00", "2026-10-01", "09:00:00", task="Instagram .", tags="Waste")
    add_log(db_path, uid, "2026-10-01", "09:00:00", "2026-10-01", "10:00:00", task="Instagram", tags="Waste")
    add_log(db_path, uid, "2026-10-01", "10:00:00", "2026-10-01", "11:00:00", task="Instagram reels", tags="Waste")
    data = login(uid).get("/api/graph-data?days=3&end=2026-10-02&search=only instagram&include_tasks=1").get_json()
    assert sorted(t["task"] for t in data["tasks"]) == ["Instagram", "Instagram ."]
