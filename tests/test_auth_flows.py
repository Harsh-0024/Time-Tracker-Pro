from werkzeug.security import generate_password_hash

from conftest import TEST_UA, make_user


def test_password_reset_keeps_user_logged_in(app, db_path):
    uid = make_user(db_path)
    client = app.test_client()
    client.environ_base["HTTP_USER_AGENT"] = TEST_UA
    with client.session_transaction() as sess:
        sess["password_reset_user_id"] = uid

    resp = client.post("/reset-password", data={"password": "newpassword1", "confirm_password": "newpassword1"})
    assert resp.status_code == 302

    # The session must survive the next request (it used to be dropped for lacking ua_hash).
    dash = client.get("/settings")
    assert dash.status_code == 200


def test_password_reset_enforces_min_length(app, db_path):
    uid = make_user(db_path)
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["password_reset_user_id"] = uid
    resp = client.post("/reset-password", data={"password": "short1", "confirm_password": "short1"})
    assert resp.status_code == 200
    assert b"at least 8 characters" in resp.data


def test_username_change_rejects_another_users_username(db_path, login):
    import sqlite3

    alice = make_user(db_path)
    make_user(db_path, username="bob", email="bob@example.com")
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (generate_password_hash("password123"), alice))
    conn.commit()
    conn.close()

    client = login(alice)
    resp = client.post(
        "/profile/update",
        data={"action": "update_username", "new_user_id": "BOB", "current_password": "password123"},
    )
    assert resp.status_code == 302
    with client.session_transaction() as sess:
        assert sess.get("profile_error") == "That user ID is already taken."
