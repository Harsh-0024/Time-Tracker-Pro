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


def _set_password(db_path, uid, password):
    import sqlite3

    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (generate_password_hash(password), uid))
    conn.commit()
    conn.close()


def test_login_locks_out_after_repeated_failures(app, db_path):
    from time_tracker_pro.repositories import login_throttle

    uid = make_user(db_path)
    _set_password(db_path, uid, "correct-horse")
    client = app.test_client()
    for _ in range(login_throttle.MAX_FAILURES):
        resp = client.post("/login", data={"identifier": "alice", "password": "wrong"})
        assert b"Invalid credentials" in resp.data

    # Even the right password is refused while locked out.
    resp = client.post("/login", data={"identifier": "ALICE", "password": "correct-horse"})
    assert resp.status_code == 200
    assert b"Too many failed attempts" in resp.data


def test_successful_login_clears_failures(app, db_path):
    uid = make_user(db_path)
    _set_password(db_path, uid, "correct-horse")
    client = app.test_client()
    for _ in range(3):
        client.post("/login", data={"identifier": "alice", "password": "wrong"})
    resp = client.post("/login", data={"identifier": "alice", "password": "correct-horse"})
    assert resp.status_code == 302

    from time_tracker_pro.repositories.login_throttle import is_locked_out
    import sqlite3

    conn = sqlite3.connect(db_path)
    assert conn.execute("SELECT COUNT(*) FROM login_failures").fetchone()[0] == 0
    conn.close()
    assert not is_locked_out(db_path, "alice")


def test_verification_codes_are_single_use(db_path, monkeypatch):
    from time_tracker_pro.services import verification

    uid = make_user(db_path)
    code = verification.create_verification_code(db_path, uid, purpose="change_password")
    ok, _ = verification.verify_email_code(db_path, uid, code, purpose="change_password")
    assert ok
    ok, message = verification.verify_email_code(db_path, uid, code, purpose="change_password")
    assert not ok
    assert "already been used" in message


def test_unconsumed_check_can_be_repeated(db_path):
    from time_tracker_pro.services import verification

    uid = make_user(db_path)
    code = verification.create_verification_code(db_path, uid, purpose="change_email_old")
    assert verification.verify_email_code(db_path, uid, code, purpose="change_email_old", consume=False)[0]
    assert verification.verify_email_code(db_path, uid, code, purpose="change_email_old", consume=False)[0]
    verification.consume_verification(db_path, uid, "change_email_old")
    assert not verification.verify_email_code(db_path, uid, code, purpose="change_email_old")[0]
