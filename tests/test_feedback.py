import sqlite3

from conftest import make_user
from time_tracker_pro.repositories.admin import delete_user_cascade


def _rows(db_path, sql, params=()):
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def test_user_sends_feedback_and_sees_it_in_settings(db_path, login):
    uid = make_user(db_path)
    client = login(uid)
    resp = client.post("/settings/feedback", data={"kind": "idea", "message": "A weekly summary email"})
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/settings#feedback-settings")
    assert _rows(db_path, "SELECT user_id, kind, message, status FROM feedback") == [
        (uid, "idea", "A weekly summary email", "new")
    ]
    page = client.get("/settings").get_data(as_text=True)
    assert "went straight to the developer" in page
    assert "A weekly summary email" in page
    assert 'data-state="new"' in page


def test_bad_feedback_is_refused_and_kept_for_correction(db_path, login):
    client = login(make_user(db_path))
    client.post("/settings/feedback", data={"kind": "idea", "message": "   "})
    assert "Write a few words first" in client.get("/settings").get_data(as_text=True)
    client.post("/settings/feedback", data={"kind": "rant", "message": "keep me please"})
    page = client.get("/settings").get_data(as_text=True)
    assert "Choose what kind" in page
    assert "keep me please" in page
    client.post("/settings/feedback", data={"kind": "idea", "message": "x" * 2001})
    assert "under 2000 characters" in client.get("/settings").get_data(as_text=True)
    assert _rows(db_path, "SELECT COUNT(*) FROM feedback") == [(0,)]


def test_admin_reads_feedback_with_the_sender_and_works_through_it(db_path, login):
    asha = make_user(db_path, username="asha", email="asha@example.com")
    login(asha).post("/settings/feedback", data={"kind": "dislike", "message": "Graphs load slowly"})
    admin = make_user(db_path, username="boss", email="boss@example.com", role="admin")
    client = login(admin)

    console = client.get("/admin/users").get_data(as_text=True)
    assert "1 new" in console

    page = client.get("/admin/feedback").get_data(as_text=True)
    assert "Graphs load slowly" in page
    assert "asha@example.com" in page
    assert ">New<" in page
    (fid, status), = _rows(db_path, "SELECT id, status FROM feedback")
    assert status == "seen"  # the sender now sees it was read

    client.post(f"/admin/feedback/{fid}/status", data={"status": "done"})
    assert _rows(db_path, "SELECT status FROM feedback") == [("done",)]
    assert 'data-state="done"' in login(asha).get("/settings").get_data(as_text=True)

    client = login(admin)
    resp = client.post(f"/admin/feedback/{fid}/status", data={"status": "bogus"})
    assert "error=" in resp.headers["Location"]
    client.post(f"/admin/feedback/{fid}/delete")
    assert _rows(db_path, "SELECT COUNT(*) FROM feedback") == [(0,)]


def test_only_admins_can_read_or_change_feedback(db_path, login):
    client = login(make_user(db_path))
    assert client.get("/admin/feedback").status_code == 403
    assert client.post("/admin/feedback/1/status", data={"status": "done"}).status_code == 403
    assert client.post("/admin/feedback/1/delete").status_code == 403


def test_deleting_a_user_deletes_their_feedback(db_path, login):
    gone = make_user(db_path, username="bob", email="bob@example.com")
    login(gone).post("/settings/feedback", data={"kind": "like", "message": "Love the matrix"})
    delete_user_cascade(db_path, gone)
    assert _rows(db_path, "SELECT COUNT(*) FROM feedback") == [(0,)]
