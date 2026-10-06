import os
import shutil
import sqlite3
import tempfile

import pytest

# Never reach real external services from tests.
os.environ.setdefault("FLASK_ENV", "development")
os.environ.setdefault("ALLOW_INSECURE_SECRET", "1")
os.environ["DISABLE_CLOUD_SYNC"] = "1"
os.environ["SHEETY_ENDPOINT"] = ""
os.environ["SMTP_HOST"] = ""
os.environ["BREVO_API_KEY"] = ""
os.environ["LOCAL_AUTH_BYPASS"] = "0"

TEST_UA = "pytest-client"


@pytest.fixture()
def app():
    from time_tracker_pro import create_app

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    application = create_app({"DB_NAME": path, "TESTING": True, "LOCAL_AUTH_BYPASS": False})
    instance_dir = tempfile.mkdtemp()
    application.instance_path = instance_dir  # never read/write the real instance/ folder
    yield application
    os.remove(path)
    shutil.rmtree(instance_dir, ignore_errors=True)


@pytest.fixture()
def db_path(app):
    return app.config["DB_NAME"]


def make_user(db_path, username="alice", email="alice@example.com", verified=1, role="user"):
    conn = sqlite3.connect(db_path)
    cur = conn.execute(
        "INSERT INTO users (username, user_id, name, email, password_hash, role, is_verified, created_at) "
        "VALUES (?, ?, ?, ?, 'x', ?, ?, '2026-01-01')",
        (username, username, username.title(), email, role, verified),
    )
    conn.commit()
    uid = cur.lastrowid
    conn.close()
    return uid


def add_log(db_path, user_id, start_date, start_time, end_date, end_time, task="Task", tags="Work", urg=0, imp=1, sheety_id=None):
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO logs (sheety_id, start_date, start_time, end_date, end_time, task, duration, tags, urg, imp, user_id) "
        "VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?)",
        (sheety_id, start_date, start_time, end_date, end_time, task, tags, urg, imp, user_id),
    )
    conn.commit()
    conn.close()


@pytest.fixture()
def login(app):
    """Return a helper that yields a test client logged in as the given user id."""
    from time_tracker_pro.web.utils import _ua_hash

    def _login(user_id):
        client = app.test_client()
        client.environ_base["HTTP_USER_AGENT"] = TEST_UA
        with client.session_transaction() as sess:
            sess["user_id"] = int(user_id)
            sess["ua_hash"] = _ua_hash(TEST_UA)
        return client

    return _login
