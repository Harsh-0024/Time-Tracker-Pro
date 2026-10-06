import sqlite3

from conftest import add_log, make_user
from time_tracker_pro.repositories.admin import delete_user_cascade


def _count(db_path, sql, params=()):
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(sql, params).fetchone()[0]
    finally:
        conn.close()


def test_delete_user_cascade_removes_all_owned_rows(db_path):
    keep = make_user(db_path)
    gone = make_user(db_path, username="bob", email="bob@example.com")
    for uid in (keep, gone):
        add_log(db_path, uid, "2026-09-20", "09:00:00", "2026-09-20", "10:00:00")
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO sheety_api_accounts (user_id, account_email, api_base_url, api_token, priority) VALUES (?, 'a@b.c', 'https://x', 'secret', 1)",
            (uid,),
        )
        conn.execute("INSERT INTO user_settings (user_id, sheety_endpoint, sheety_token) VALUES (?, 'e', 't')", (uid,))
        conn.commit()
        conn.close()

    delete_user_cascade(db_path, gone)

    assert _count(db_path, "SELECT COUNT(*) FROM users WHERE id = ?", (gone,)) == 0
    assert _count(db_path, "SELECT COUNT(*) FROM logs WHERE user_id = ?", (gone,)) == 0
    assert _count(db_path, "SELECT COUNT(*) FROM sheety_api_accounts WHERE user_id = ?", (gone,)) == 0
    assert _count(db_path, "SELECT COUNT(*) FROM user_settings WHERE user_id = ?", (gone,)) == 0
    # Other users are untouched.
    assert _count(db_path, "SELECT COUNT(*) FROM logs WHERE user_id = ?", (keep,)) == 1
    assert _count(db_path, "SELECT COUNT(*) FROM sheety_api_accounts WHERE user_id = ?", (keep,)) == 1


def test_non_admin_cannot_open_admin_page(db_path, login):
    uid = make_user(db_path)
    resp = login(uid).get("/admin/users")
    assert resp.status_code == 403


def test_session_of_deleted_user_is_dropped(db_path, login):
    keep = make_user(db_path, username="keeper", email="keeper@example.com")
    gone = make_user(db_path, username="bob", email="bob@example.com")
    client = login(gone)
    assert client.get("/settings").status_code == 200

    delete_user_cascade(db_path, gone)

    resp = client.get("/settings")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]
    with client.session_transaction() as sess:
        assert "user_id" not in sess
    assert keep  # other accounts unaffected
