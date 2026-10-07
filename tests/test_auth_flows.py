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


def _register(client, user_id, email="new@example.com"):
    return client.post(
        "/register",
        data={"name": "New Person", "email": email, "user_id": user_id,
              "password": "password123", "confirm_password": "password123"},
    )


def test_register_rejects_user_ids_that_look_like_emails_or_have_spaces(app, db_path, monkeypatch):
    import time_tracker_pro.web.auth as auth_mod

    monkeypatch.setattr(auth_mod, "send_verification_email", lambda *a, **k: True)
    make_user(db_path)
    client = app.test_client()
    for bad in ("someone@example.com", "has space", "ab", "x" * 33, "semi;colon"):
        resp = _register(client, bad)
        assert resp.status_code == 200, bad
        assert b"User ID must be 3-32" in resp.data, bad
    assert _register(client, "good.id-1_x").status_code == 302


def test_register_rejects_email_equal_to_existing_user_id(app, db_path, monkeypatch):
    import sqlite3
    import time_tracker_pro.web.auth as auth_mod

    monkeypatch.setattr(auth_mod, "send_verification_email", lambda *a, **k: True)
    uid = make_user(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE users SET user_id = 'taken@example.com', username = 'taken@example.com' WHERE id = ?", (uid,))
    conn.commit()
    conn.close()
    resp = _register(app.test_client(), "freshid", email="taken@example.com")
    assert b"An account with that email already exists." in resp.data


def test_profile_user_id_change_enforces_format(db_path, login):
    alice = make_user(db_path)
    _set_password(db_path, alice, "password123")
    client = login(alice)
    client.post("/profile/update", data={"action": "update_username", "new_user_id": "a@b.co", "current_password": "password123"})
    with client.session_transaction() as sess:
        assert sess.get("profile_error", "").startswith("User ID must be 3-32")


def test_identifier_lookup_prefers_the_email_owner(db_path):
    import sqlite3

    from time_tracker_pro.repositories.users import get_user_by_username_or_id_or_email

    squatter = make_user(db_path, username="sq", email="sq@example.com")
    owner = make_user(db_path, username="owner", email="owner@example.com")
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE users SET user_id = 'owner@example.com' WHERE id = ?", (squatter,))
    conn.commit()
    conn.close()
    assert get_user_by_username_or_id_or_email(db_path, "OWNER@example.com")["id"] == owner


def test_mask_email():
    from time_tracker_pro.web.utils import mask_email

    assert mask_email("harsh@gmail.com") == "h•••h@gmail.com"
    assert mask_email("ab@x.io") == "a•••@x.io"
    assert mask_email("") == ""


def test_forgot_password_by_user_id_does_not_reveal_email(app, db_path, monkeypatch):
    import time_tracker_pro.web.auth as auth_mod

    monkeypatch.setattr(auth_mod, "send_verification_email", lambda *a, **k: True)
    make_user(db_path, username="alice", email="alice.secret@example.com")
    client = app.test_client()
    resp = client.post("/forgot-password", data={"identifier": "alice"}, follow_redirects=True)
    assert b"alice.secret@example.com" not in resp.data
    assert "a•••t@example.com".encode() in resp.data


def test_resend_cooldown_blocks_rapid_otp_emails(app, db_path, monkeypatch):
    import time_tracker_pro.services.verification as ver
    import time_tracker_pro.web.auth as auth_mod

    sent = []
    monkeypatch.setattr(ver, "send_email", lambda *a, **k: sent.append(a[0]) or True)
    make_user(db_path, username="alice", email="alice@example.com")
    client = app.test_client()

    client.post("/login", data={"identifier": "alice", "action": "login_otp"})
    client.post("/login", data={"identifier": "alice", "action": "login_otp"})
    assert len(sent) == 1
    resp = client.post("/verify-email", data={"action": "resend"})
    assert b"Please wait" in resp.data
    assert len(sent) == 1

    monkeypatch.setattr(ver, "VERIFICATION_RESEND_COOLDOWN_SECONDS", 0)
    client.post("/verify-email", data={"action": "resend"})
    assert len(sent) == 2
