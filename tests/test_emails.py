import sqlite3

from conftest import make_user


def _user_row(db_path, uid):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    finally:
        conn.close()


def test_emails_escape_the_users_name(db_path, monkeypatch):
    """Anyone can register with someone else's address, so the chosen name must not
    be able to inject links/markup into a genuine email from the app."""
    from time_tracker_pro.services import verification, welcome_email

    sent = []
    fake_send = lambda to, subject, body, html: sent.append(html) or True
    monkeypatch.setattr(verification, "send_email", fake_send)
    monkeypatch.setattr(welcome_email, "send_email", fake_send)

    uid = make_user(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE users SET name = ? WHERE id = ?", ('<a href="https://evil.example">Secure your account</a>', uid))
    conn.commit()
    conn.close()
    row = _user_row(db_path, uid)

    verification.send_verification_email(db_path, row)
    welcome_email.send_welcome_email(row)
    assert len(sent) == 2
    for html in sent:
        assert '<a href="https://evil.example">' not in html
        assert "&lt;a href=" in html
