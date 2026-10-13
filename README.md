# Time Tracker Pro

A multi-user Flask app that reads a day log from a Google Sheet (through [Sheety](https://sheety.co))
and shows where your time went: by category (Work, Necessity, Soul, Rest, Waste) and by the
Eisenhower matrix (urgent × important).

## Features

- **Dashboard** with Day, Week and Month views:
  - Summary cards: how much of the period is logged, the top category and the dominant quadrant.
  - Priority Breakdown (extended Eisenhower matrix), with each quadrant's change vs the previous period.
  - **Day view:** an hour-by-hour 24h timeline.
  - **Week and Month views:** a "Day by day" stacked chart.
  - **Insights:** top activities (each with its change vs the previous period, or vs your usual day), the biggest
    changes among the other activities, the day vs your
    7-day average (week/month: vs the previous period), best and worst days, fully-logged days, and
    sleep (day: last night vs your previous 7 nights; week/month: hours a night and typical bed/wake times; from tasks named "Sleep").
  - **Copy summary:** a plain-text recap of the period for a journal or message; **Export Summary** downloads its rows.
  - **Day notes:** a private line or two about the day (autosaved, `J`); week/month views, the full log and graphs show them, and Copy summary / JSON export include them (the JSON export also carries your goals). API: `GET /api/day-notes?start=YYYY-MM-DD&end=YYYY-MM-DD`, `PUT /api/day-notes/YYYY-MM-DD` with `{"note": "..."}`.
  - **Daily goals:** a Growth target, a Waste limit and a sleep goal (hours a night), plus optional per-category goals (e.g. Soul ≥ 1h, Rest ≤ 2h),
    with progress, streaks, and a met/missed dot per day.
  - **Full log modal:** search (`gym, reading` · `only lunch` · `-waste` · `note:tired` for days whose note mentions it), sort, export, and create/edit/delete entries
    (written back to the sheet), with task-name autocomplete, "Again" to re-log a task, and tap-a-gap to fill missing time.
  - On phones, swipe the week strip or the day-by-day chart to move between periods.
- **Graphs:** trends for any category, quadrant, search expression or sleep per night over time, with a moving average,
  goal/limit reference lines, a 'vs previous period' overlay, saved views, by-weekday and by-time-of-day breakdowns,
  and a calendar heatmap. Link to a view with `/graphs?focus=sleep&range=90` or `/graphs?search=gym`.
- **Accounts:**
  - Email-verified registration and password or email-code (OTP) login.
  - "Remember me" sessions, password reset, login throttling, and a resend cooldown on email codes.
- **Admin:** user list (with each user's log count and last logged day) and account removal with an emailed reason.
  Admins cannot see other users' data.
- **Interface:** light, dark and system themes; installable as a PWA (long-press the icon for Add task / This week / Graphs; pull down to sync; a friendly offline page); keyboard shortcuts (press `?`).

## Running locally

```bash
python3.12 -m venv venv
venv/bin/pip install -r requirements.txt
cp .env.example .env   # then fill in the values (see Configuration)
FLASK_ENV=development venv/bin/flask --app wsgi:app run
```

The app creates and migrates its SQLite database (`productivity.db` by default) on start.

Production uses gunicorn (`Procfile`: `web: gunicorn wsgi:app`) on Python 3.12 (`runtime.txt`).

## Configuration

| Variable | Purpose |
| --- | --- |
| `SECRET_KEY` | **Required in production.** Flask session signing key. |
| `DB_PATH` | SQLite file (default `productivity.db`). |
| `ADMIN_EMAILS` | Comma-separated emails that get the admin role. |
| `SESSION_COOKIE_SECURE`, `SESSION_LIFETIME_DAYS` | Cookie hardening and how long "Remember me" lasts (default 30 days). |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_SENDER`, `SMTP_USE_TLS` | Email over SMTP. |
| `BREVO_API_KEY`, `EMAIL_MODE` | Email through the Brevo API instead. |
| `VERIFICATION_CODE_TTL_MINUTES`, `VERIFICATION_MAX_ATTEMPTS` | Email-code lifetime and attempts (default 10 min / 5). |
| `VERIFICATION_RESEND_COOLDOWN_SECONDS` | Minimum gap between email codes for the same account and purpose (default 60). |
| `MAX_CONTENT_LENGTH_MB` | Largest accepted request body (uploads, CSV import); bigger requests get a 413 (default 16). |
| `DISABLE_CSP` | Set to `1` to drop the Content-Security-Policy header (only if a deployment needs extra script/style origins). |
| `DISABLE_GZIP` | Set to `1` if a proxy in front already compresses responses (the app gzips HTML/JSON itself otherwise). |
| `LOGIN_MAX_FAILURES`, `LOGIN_FAILURE_WINDOW_MINUTES` | Password-login throttling per account (default 10 per 15 min). |
| `SHEETY_ENDPOINT` | Fallback Sheety URL (single-user setups). Users normally add theirs under Settings → API Keys. |
| `TIME_TRACKER_API_TOKEN` | Token for scripted access to the JSON API (`X-API-Token` header). |
| `DISABLE_CLOUD_SYNC` | Skip automatic syncs, e.g. for a local demo database. |
| `SYNC_*` | Fine-tuning for the Sheety sync (intervals, write budgets, flagging). See `time_tracker_pro/services/sync.py`. |

### Local development helpers

- `LOCAL_AUTH_BYPASS=1` with `FLASK_ENV=development` skips login.
  It signs you in as `LOCAL_AUTH_USER_ID`, or the first user.
- `LOG_VERIFICATION_CODES=1` writes email codes to the log when sending fails.

### Styles

Tailwind is precompiled into `static/css/tailwind.css` (no in-browser CDN). After adding Tailwind classes to a
template or script, rebuild it:

```bash
npx tailwindcss@3.4.17 -c tailwind.config.js -i static/css/tailwind.src.css -o static/css/tailwind.css --minify
```

## Tests

```bash
venv/bin/pip install pytest
venv/bin/python -m pytest -q
```

Tests use a temporary database and never contact Sheety or send email.

## Project layout

```
time_tracker_pro/
  core/          small pure helpers (dates, tags, admin emails)
  repositories/  SQLite access (users, logs, settings, goals, Sheety accounts, …)
  services/      sync, parser, insights, email, matrix stats
  web/           Flask blueprints: auth, main (pages), api (JSON), admin
templates/       Jinja pages; per-request values are passed to page scripts in a JSON <script id=...Config> block
static/          theme.css, tailwind.css (prebuilt), js/pages/*.js + css/pages/*.css (per-page code), icons
tests/           pytest suite
```
