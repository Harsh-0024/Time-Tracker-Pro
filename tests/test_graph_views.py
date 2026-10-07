from conftest import make_user


def test_graph_views_crud(db_path, login):
    uid = make_user(db_path)
    client = login(uid)
    assert client.get("/api/graph-views").get_json() == {"views": []}

    resp = client.post("/api/graph-views", json={"name": "  Deep   work ", "focus": "work", "search": "deep", "range": "90", "ma": 14})
    assert resp.status_code == 201
    view = resp.get_json()["view"]
    assert view == {"id": view["id"], "name": "Deep work", "focus": "work", "search": "deep", "range": "90", "ma": 14}

    resp = client.post("/api/graph-views", json={"name": "Everything", "focus": "total", "range": "all", "ma": 30})
    assert resp.get_json()["view"]["range"] == "all"

    assert [v["name"] for v in client.get("/api/graph-views").get_json()["views"]] == ["Deep work", "Everything"]
    assert client.delete(f"/api/graph-views/{view['id']}").status_code == 200
    assert [v["name"] for v in client.get("/api/graph-views").get_json()["views"]] == ["Everything"]


def test_graph_views_validation(db_path, login):
    uid = make_user(db_path)
    client = login(uid)
    bad = [
        {"name": "", "focus": "work", "range": "30", "ma": 7},
        {"name": "x", "focus": "nope", "range": "30", "ma": 7},
        {"name": "x", "focus": "work", "range": "-3", "ma": 7},
        {"name": "x", "focus": "work", "range": "30", "ma": 9},
        {"name": "x", "focus": "search_only", "search": "", "range": "30", "ma": 7},
    ]
    for payload in bad:
        resp = client.post("/api/graph-views", json=payload)
        assert resp.status_code == 400, payload


def test_graph_views_are_private(db_path, login):
    alice = make_user(db_path)
    bob = make_user(db_path, username="bob", email="bob@example.com")
    view = login(alice).post("/api/graph-views", json={"name": "Mine", "focus": "work", "range": "30", "ma": 7}).get_json()["view"]
    bob_client = login(bob)
    assert bob_client.get("/api/graph-views").get_json() == {"views": []}
    assert bob_client.delete(f"/api/graph-views/{view['id']}").status_code == 404


def test_graph_views_limit(db_path, login):
    from time_tracker_pro.repositories.graph_views import MAX_VIEWS_PER_USER

    uid = make_user(db_path)
    client = login(uid)
    for i in range(MAX_VIEWS_PER_USER):
        assert client.post("/api/graph-views", json={"name": f"v{i}", "focus": "work", "range": "30", "ma": 7}).status_code == 201
    resp = client.post("/api/graph-views", json={"name": "one more", "focus": "work", "range": "30", "ma": 7})
    assert resp.status_code == 400


def test_infinite_ma_window_is_400_not_500(db_path, login):
    from conftest import make_user

    client = login(make_user(db_path, username="inf", email="inf@example.com"))
    resp = client.post(
        "/api/graph-views",
        data='{"name": "x", "focus": "total", "range": "30", "ma": Infinity}',
        content_type="application/json",
    )
    assert resp.status_code == 400


def test_graph_search_history_is_capped(db_path, monkeypatch):
    import sqlite3

    from conftest import make_user
    from time_tracker_pro.repositories import graph_search_history as gsh

    uid = make_user(db_path, username="hist", email="hist@example.com")
    monkeypatch.setattr(gsh, "MAX_HISTORY_ROWS_PER_USER", 5)
    for i in range(8):
        gsh.record_graph_search_combo(db_path, uid, "total", f"q{i}")
    gsh.record_graph_search_combo(db_path, uid, "total", "x" * 5000)
    rows = sqlite3.connect(db_path).execute(
        "SELECT search_query FROM graph_search_history WHERE user_id = ? ORDER BY id", (uid,)
    ).fetchall()
    assert [r[0] for r in rows[:4]] == ["q4", "q5", "q6", "q7"]
    assert len(rows) == 5 and len(rows[-1][0]) == gsh.MAX_QUERY_LENGTH
