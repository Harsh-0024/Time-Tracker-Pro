import pytest

from conftest import add_log, make_user

DASHBOARD_URLS = [
    "/",
    "/?date=2026-09-20",
    "/?date=2026-09-20&period=week",
    "/?date=2026-09-20&period=month",
    "/?date=2028-02-29&period=month",
    "/?date=2026-12-31&period=week",
    "/?date=2099-01-01",
    "/?date=not-a-date&period=bogus",
]


@pytest.fixture()
def client_with_data(db_path, login):
    uid = make_user(db_path, role="admin")
    add_log(db_path, uid, "2026-09-19", "22:00:00", "2026-09-20", "06:00:00", task="Sleep", tags="Necessity", urg=0, imp=1)
    add_log(db_path, uid, "2026-09-20", "06:00:00", "2026-09-20", "09:30:00", task="Deep work", tags="Work", urg=0, imp=1)
    add_log(db_path, uid, "2026-09-20", "09:30:00", "2026-09-20", "10:00:00", task="Scrolling", tags="Waste", urg=0, imp=0)
    add_log(db_path, uid, "2026-09-21", "10:00:00", "2026-09-21", "11:00:00", task="Errand", tags="Necessity", urg=1, imp=0)
    return login(uid)


@pytest.mark.parametrize("url", DASHBOARD_URLS)
def test_dashboard_renders(client_with_data, url):
    resp = client_with_data.get(url)
    assert resp.status_code == 200, url


@pytest.mark.parametrize(
    "url",
    [
        "/graphs",
        "/settings",
        "/admin/users",
        "/manifest.webmanifest",
        "/api/tasks?date=2026-09-20&period=week&filter=q2",
        "/api/tasks?date=2026-09-20&period=month&filter=tag&tag=Work",
        "/api/graph-data?metric=waste&days=30&end=2026-09-30",
        "/api/graph-data?metric=total&days=7&search=deep",
        "/api/graph-data?metric=q2&days=abc",
        "/api/tags",
        "/api/export-csv",
        "/api/export-csv?mode=range&start_date=2026-09-20&end_date=2026-09-20&format=json",
        "/sync-status",
    ],
)
def test_pages_and_apis_respond(client_with_data, url):
    resp = client_with_data.get(url)
    assert resp.status_code == 200, (url, resp.status_code, resp.data[:200])


def test_export_csv_contents(client_with_data):
    resp = client_with_data.get("/api/export-csv?mode=range&start_date=2026-09-20&end_date=2026-09-20")
    text = resp.get_data(as_text=True)
    assert text.splitlines()[0].startswith("start date,start time")
    assert "Deep work" in text and "Errand" not in text


def test_out_of_range_dates_do_not_500(db_path, login):
    client = login(make_user(db_path))
    for url in (
        "/?date=0001-01-01",
        "/?date=9999-12-31&period=month",
        "/api/tasks?date=9999-12-31&period=month",
        "/api/tags?date=9999-12-31&period=month",
    ):
        assert client.get(url).status_code == 200, url


def test_login_redirect_next_has_no_dangling_question_mark(app, db_path):
    make_user(db_path)
    client = app.test_client()
    assert client.get("/graphs").headers["Location"].endswith("next=/graphs")
    assert client.get("/?period=week").headers["Location"].endswith("next=/?period%3Dweek")


def test_admin_page_login_redirect_comes_back(app, db_path):
    make_user(db_path)
    client = app.test_client()
    assert client.get("/admin/users").headers["Location"].endswith("next=/admin/users")
    # POST-only targets just go to /login
    assert client.post("/admin/delete-user").headers["Location"].endswith("/login")


def test_error_pages_html_and_json(app, db_path, login):
    client = app.test_client()
    resp = client.get("/no-such-page")
    assert resp.status_code == 404
    assert b"Page not found" in resp.data and b"Go to dashboard" in resp.data
    resp = client.get("/api/no-such-endpoint")
    assert resp.status_code == 404
    assert resp.get_json() == {"error": "That page doesn't exist or has moved."}
    resp = login(make_user(db_path)).get("/admin/users")
    assert resp.status_code == 403
    assert b"Not allowed" in resp.data


def test_export_csv_neutralises_formula_cells(db_path, login):
    uid = make_user(db_path)
    add_log(db_path, uid, "2026-09-20", "06:00:00", "2026-09-20", "07:00:00", task="=HYPERLINK(\"http://x\")")
    text = login(uid).get("/api/export-csv").get_data(as_text=True)
    assert "'=HYPERLINK" in text
    assert ",=HYPERLINK" not in text
    # numbers (duration) are left alone
    assert ",1.0," in text


def test_oversized_request_is_rejected_with_413(app, db_path, login):
    app.config["MAX_CONTENT_LENGTH"] = 1024
    client = login(make_user(db_path))
    resp = client.post("/api/import-csv", data="x" * 4096, content_type="application/json")
    assert resp.status_code == 413
    assert resp.is_json and "too large" in resp.get_json()["error"]


def test_non_ascii_api_token_is_401_not_500(app, monkeypatch):
    monkeypatch.setenv("TIME_TRACKER_API_TOKEN", "secret-token")
    resp = app.test_client().get("/api/tags?token=s%C3%A9cret")
    assert resp.status_code in (401, 302)


def test_safe_next_url_rejects_browser_normalised_external_urls():
    from time_tracker_pro.web.utils import safe_next_url

    for bad in ("//evil.com", "/\\evil.com", "/\t/evil.com", "/\n/evil.com", "https://evil.com", "evil.com"):
        assert safe_next_url(bad) is None, bad
    assert safe_next_url("/graphs?x=1") == "/graphs?x=1"


def test_sync_now_error_does_not_echo_exception(db_path, login, monkeypatch):
    from time_tracker_pro.web import api

    def boom(*a, **k):
        raise RuntimeError("/secret/path/productivity.db is locked")

    monkeypatch.setattr(api, "sync_cloud_data", boom)
    client = login(make_user(db_path))
    for path in ("/sync-now", "/hard-reset"):
        resp = client.post(path)
        assert resp.status_code == 500
        assert b"secret" not in resp.data


def test_sync_endpoints_refuse_cookie_get(db_path, login, monkeypatch):
    """A cross-site link (top-level GET carries Lax cookies) must not force a sync."""
    from time_tracker_pro.web import api

    calls = []
    monkeypatch.setattr(api, "sync_cloud_data", lambda *a, **k: calls.append(a))
    client = login(make_user(db_path))
    for path in ("/sync-now", "/hard-reset"):
        assert client.get(path).status_code == 405
    assert calls == []
    assert client.post("/sync-now").status_code == 200
    assert len(calls) == 1


def test_sync_now_get_still_allowed_with_api_token(app, db_path, monkeypatch):
    from time_tracker_pro.web import api

    calls = []
    monkeypatch.setattr(api, "sync_cloud_data", lambda *a, **k: calls.append(a))
    monkeypatch.setenv("TIME_TRACKER_API_TOKEN", "secret-token")
    uid = make_user(db_path)
    resp = app.test_client().get("/sync-now", headers={"X-API-Token": "secret-token", "X-User-Id": str(uid)})
    assert resp.status_code == 200, resp.data
    assert len(calls) == 1


def test_api_token_header_is_accepted(app, db_path, monkeypatch):
    monkeypatch.setenv("TIME_TRACKER_API_TOKEN", "secret-token")
    uid = make_user(db_path)
    client = app.test_client()
    ok = client.get("/api/tags", headers={"X-API-Token": "secret-token", "X-User-Id": str(uid)})
    assert ok.status_code == 200
    bad = client.get("/api/tags", headers={"X-API-Token": "wrong", "X-User-Id": str(uid)})
    assert bad.status_code in (401, 302)


def test_session_cookie_secure_flag_parsing(monkeypatch):
    from time_tracker_pro import create_app

    for value, expected in (("1", True), ("true", True), ("0", False), ("false", False), ("", False)):
        monkeypatch.setenv("SESSION_COOKIE_SECURE", value)
        app = create_app({"DB_NAME": ":memory:", "TESTING": True})
        assert bool(app.config.get("SESSION_COOKIE_SECURE")) is expected, value
