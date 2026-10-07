from conftest import add_log, make_user


def test_tasks_with_and_without_sheety_id(db_path, login):
    uid = make_user(db_path)
    add_log(db_path, uid, "2026-09-20", "09:00:00", "2026-09-20", "10:00:00", task="Synced", sheety_id=42)
    add_log(db_path, uid, "2026-09-20", "10:00:00", "2026-09-20", "11:30:00", task="Local only", sheety_id=None)

    resp = login(uid).get("/api/tasks?date=2026-09-20&period=day&filter=all")

    assert resp.status_code == 200
    data = resp.get_json()
    by_task = {t["task"]: t for t in data["tasks"]}
    assert by_task["Synced"]["sheety_id"] == 42
    assert by_task["Local only"]["sheety_id"] is None
    assert data["total_minutes"] == 150


def test_tasks_are_scoped_to_user(db_path, login):
    alice = make_user(db_path)
    bob = make_user(db_path, username="bob", email="bob@example.com")
    add_log(db_path, alice, "2026-09-20", "09:00:00", "2026-09-20", "10:00:00", task="Alice task")
    add_log(db_path, bob, "2026-09-20", "09:00:00", "2026-09-20", "10:00:00", task="Bob task")

    data = login(bob).get("/api/tasks?date=2026-09-20&period=day").get_json()

    assert [t["task"] for t in data["tasks"]] == ["Bob task"]


def test_tasks_requires_login(app):
    resp = app.test_client().get("/api/tasks")
    assert resp.status_code == 401


def test_find_task_row_respects_id_kind(app, db_path):
    import sqlite3

    from time_tracker_pro.db import get_db_connection
    from time_tracker_pro.web.api import _find_task_row

    uid = make_user(db_path)
    add_log(db_path, uid, "2026-09-20", "09:00:00", "2026-09-20", "10:00:00", task="First", sheety_id=500)
    add_log(db_path, uid, "2026-09-20", "10:00:00", "2026-09-20", "11:00:00", task="Second", sheety_id=1)
    conn = sqlite3.connect(db_path)
    first_local_id = conn.execute("SELECT id FROM logs WHERE task = 'First'").fetchone()[0]
    conn.close()
    assert first_local_id == 1  # local id 1 collides with Second's sheety_id 1

    conn = get_db_connection(db_path)
    try:
        with app.test_request_context("/api/tasks/1?by=sheety"):
            assert _find_task_row(conn, 1, uid)["task"] == "Second"
        with app.test_request_context("/api/tasks/1?by=local"):
            assert _find_task_row(conn, 1, uid)["task"] == "First"
        with app.test_request_context("/api/tasks/500"):
            assert _find_task_row(conn, 500, uid)["task"] == "First"
        with app.test_request_context("/api/tasks/1?by=sheety"):
            assert _find_task_row(conn, 1, uid + 1) is None
    finally:
        conn.close()


def test_graph_data_allows_more_than_a_year(db_path, login):
    uid = make_user(db_path)
    add_log(db_path, uid, "2025-01-05", "09:00:00", "2025-01-05", "10:00:00")
    add_log(db_path, uid, "2026-09-20", "09:00:00", "2026-09-20", "10:00:00")
    data = login(uid).get("/api/graph-data?days=700&end=2026-09-20").get_json()
    assert len(data["labels"]) == 700
    assert data["labels"][0] == "2024-10-21"  # 2026-09-20 minus 699 days
    assert data["total_hours"] == 2.0


def test_create_task_rejects_non_numeric_duration(db_path, login):
    uid = make_user(db_path)
    resp = login(uid).post(
        "/api/tasks",
        json={"task": "x", "date": "2026-09-20", "start_time": "09:00", "duration_minutes": "abc"},
    )
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "Duration must be a number"


def test_update_task_rejects_non_numeric_duration(db_path, login):
    uid = make_user(db_path)
    add_log(db_path, uid, "2026-09-20", "09:00:00", "2026-09-20", "10:00:00", task="Synced", sheety_id=7)
    resp = login(uid).put("/api/tasks/7?by=sheety", json={"duration": "soon"})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "Duration must be a number"


def test_create_task_rejects_non_object_json(db_path, login):
    client = login(make_user(db_path))
    for body in ([1, 2], "task", 5):
        resp = client.post("/api/tasks", json=body)
        assert resp.status_code == 400, body


def test_create_task_tolerates_non_string_fields(db_path, login):
    client = login(make_user(db_path))
    resp = client.post("/api/tasks", json={"task": 123, "date": 20260920, "start_time": "09:00", "duration": 1})
    assert resp.status_code == 400  # bad date, but no crash
    resp = client.post("/api/tasks", json={"task": "x", "date": "2026-09-20", "start_time": "09:00", "duration": "inf"})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "Duration must be a number"


def test_update_task_infinite_duration_is_400(db_path, login):
    uid = make_user(db_path)
    add_log(db_path, uid, "2026-09-20", "09:00:00", "2026-09-20", "10:00:00", task="Synced", sheety_id=7)
    resp = login(uid).put("/api/tasks/7?by=sheety", json={"duration": "inf", "task": 5})
    assert resp.status_code == 400


def test_sheety_account_url_must_be_public_https(db_path, login):
    client = login(make_user(db_path))
    for bad in ("javascript:alert(1)", "http://api.sheety.co/x", "https://127.0.0.1/x",
                "https://169.254.169.254/latest", "https://localhost/x", "https://10.0.0.5/x"):
        resp = client.post("/api/sheety-accounts", json={"api_base_url": bad})
        assert resp.status_code == 400, bad
    resp = client.post("/api/sheety-accounts", json={"api_base_url": "https://api.sheety.co/abc/timeLogs/sheet1"})
    assert resp.status_code == 201
    resp = client.post("/api/sheety-accounts", json={"api_base_url": "https://api.sheety.co/" + "a" * 600})
    assert resp.status_code == 400


def test_import_csv_without_valid_rows_keeps_existing_logs(db_path, login):
    import sqlite3

    uid = make_user(db_path)
    add_log(db_path, uid, "2026-09-20", "09:00:00", "2026-09-20", "10:00:00", task="Keep me")
    client = login(uid)
    for csv_data in ("a,b\n1,2", "5", "Log Entry\n\n"):
        resp = client.post("/api/import-csv", json={"csv_data": csv_data})
        assert resp.status_code in (400, 500), csv_data
    conn = sqlite3.connect(db_path)
    count = conn.execute("SELECT COUNT(*) FROM logs WHERE user_id = ?", (uid,)).fetchone()[0]
    conn.close()
    assert count == 1
