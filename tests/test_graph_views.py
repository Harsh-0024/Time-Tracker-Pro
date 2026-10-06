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
