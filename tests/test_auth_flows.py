import time
from werkzeug.security import generate_password_hash

from conftest import TEST_UA, make_user


def test_password_reset_keeps_user_logged_in(app, db_path):
    uid = make_user(db_path)
    client = app.test_client()
    client.environ_base["HTTP_USER_AGENT"] = TEST_UA
    with client.session_transaction() as sess:
        sess["password_reset_user_id"] = uid
        sess["password_reset_started"] = int(time.time())

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
        sess["password_reset_started"] = int(time.time())
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


def test_password_reset_lifts_login_lockout(app, db_path):
    from time_tracker_pro.repositories import login_throttle

    uid = make_user(db_path)
    for _ in range(login_throttle.MAX_FAILURES):
        login_throttle.record_failure(db_path, "alice@example.com")
    assert login_throttle.is_locked_out(db_path, "alice@example.com")
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["password_reset_user_id"] = uid
        sess["password_reset_started"] = int(time.time())
    client.post("/reset-password", data={"password": "brand-new-pass", "confirm_password": "brand-new-pass"})
    assert not login_throttle.is_locked_out(db_path, "alice@example.com")


def test_reset_session_expires_after_code_ttl(app, db_path):
    from time_tracker_pro.services.verification import VERIFICATION_CODE_TTL_MINUTES

    uid = make_user(db_path)
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["password_reset_user_id"] = uid
        sess["password_reset_started"] = int(time.time()) - VERIFICATION_CODE_TTL_MINUTES * 60 - 5
    resp = client.post("/reset-password", data={"password": "newpassword1", "confirm_password": "newpassword1"})
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/forgot-password")
    with client.session_transaction() as sess:
        assert "password_reset_user_id" not in sess and "user_id" not in sess
    assert "reset session expired" in client.get("/forgot-password").get_data(as_text=True)


def test_reset_session_without_start_time_is_rejected(app, db_path):
    uid = make_user(db_path)
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["password_reset_user_id"] = uid
    assert client.get("/reset-password").headers["Location"].endswith("/forgot-password")


def test_profile_change_with_wrong_password_says_so(db_path, login):
    uid = make_user(db_path)
    _set_password(db_path, uid, "password123")
    client = login(uid)
    client.post("/profile/update", data={"action": "update_username", "new_name": "Al", "current_password": "nope-nope"})
    with client.session_transaction() as sess:
        assert sess.get("profile_error") == "Current password is incorrect."
    client.post("/profile/update", data={"action": "update_username", "new_name": "Al"})
    with client.session_transaction() as sess:
        assert sess.get("profile_error") == "Provide your current password or a verification code."


def test_register_and_profile_length_caps(app, db_path, login, monkeypatch):
    client = app.test_client()
    base = {"email": "long@example.com", "user_id": "longname", "password": "password123", "confirm_password": "password123"}
    html = client.post("/register", data={**base, "name": "N" * 81}).get_data(as_text=True)
    assert "Name must be at most 80 characters." in html
    huge = "p" * 1025
    html = client.post("/register", data={**base, "name": "Ok", "password": huge, "confirm_password": huge}).get_data(as_text=True)
    assert "at most 1024 characters" in html

    uid = make_user(db_path)
    _set_password(db_path, uid, "password123")
    c = login(uid)
    c.post("/profile/update", data={"action": "update_username", "new_name": "N" * 81, "current_password": "password123"})
    with c.session_transaction() as sess:
        assert sess.get("profile_error") == "Name must be at most 80 characters."


def test_login_with_huge_password_is_rejected_without_hashing(app, db_path, monkeypatch):
    import time_tracker_pro.web.auth as auth_module

    uid = make_user(db_path)
    _set_password(db_path, uid, "password123")
    called = []
    monkeypatch.setattr(auth_module, "check_password_hash", lambda *a: called.append(1) or False)
    html = app.test_client().post("/login", data={"identifier": "alice", "password": "x" * 5000}).get_data(as_text=True)
    assert "Invalid credentials." in html and not called


def test_profile_current_password_is_throttled(db_path, login):
    from time_tracker_pro.repositories import login_throttle

    uid = make_user(db_path)
    _set_password(db_path, uid, "correct-horse")
    client = login(uid)
    for _ in range(login_throttle.MAX_FAILURES):
        client.post("/profile/update", data={"action": "update_username", "new_name": "X", "current_password": "nope"})
        with client.session_transaction() as sess:
            assert sess.pop("profile_error") == "Current password is incorrect."

    # Locked: even the right password is refused.
    client.post("/profile/update", data={"action": "update_username", "new_name": "X", "current_password": "correct-horse"})
    with client.session_transaction() as sess:
        assert "Too many incorrect password attempts" in sess.pop("profile_error")

    # Login throttling for the account's user ID is a separate bucket.
    assert not login_throttle.is_locked_out(db_path, "alice")


def test_profile_correct_password_clears_failures(db_path, login):
    from time_tracker_pro.repositories import login_throttle

    uid = make_user(db_path)
    _set_password(db_path, uid, "correct-horse")
    client = login(uid)
    for _ in range(login_throttle.MAX_FAILURES - 1):
        client.post("/profile/update", data={"action": "update_username", "new_name": "X", "current_password": "nope"})
    client.post("/profile/update", data={"action": "update_username", "new_name": "Y", "current_password": "correct-horse"})
    with client.session_transaction() as sess:
        assert sess.get("profile_success") == "Profile updated."
    assert not login_throttle.is_locked_out(db_path, f"profile #{uid}")


def test_verify_page_does_not_claim_a_code_was_sent_when_email_failed(app, db_path, monkeypatch):
    import time_tracker_pro.services.verification as ver

    make_user(db_path, username="alice", email="alice@example.com")
    client = app.test_client()

    monkeypatch.setattr(ver, "send_email", lambda *a, **k: False)
    resp = client.post("/login", data={"identifier": "alice", "action": "login_otp"}, follow_redirects=True)
    assert b"couldn&#39;t send the email" in resp.data
    assert b"We sent a 6-digit code" not in resp.data
    assert b"Code expires" not in resp.data

    monkeypatch.setattr(ver, "send_email", lambda *a, **k: True)
    monkeypatch.setattr(ver, "VERIFICATION_RESEND_COOLDOWN_SECONDS", 0)
    resp = client.post("/verify-email", data={"action": "resend"})
    assert b"We sent a 6-digit code" in resp.data
    assert b"Code expires" in resp.data
