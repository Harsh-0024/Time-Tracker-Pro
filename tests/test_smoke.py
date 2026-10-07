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
