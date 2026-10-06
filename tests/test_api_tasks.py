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
