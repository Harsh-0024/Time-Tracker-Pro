# Overnight Worklog (branch: overnight-improvements)

Started: 2026-10-07. Owner asked: improve anything (bugs > UX > aesthetics > features),
work until told to stop. DO NOT touch the time-passing logic. Do not push/deploy/merge.
Do not touch untracked *.db files. Commit small, focused changes locally on this branch.

Note: *.md is gitignored; this file is force-added (git add -f WORKLOG.md).

## Status / last heartbeat
- 2026-10-07 04:48 IST: empty states + dark-mode fixes; 105 tests green.

## Done
- fix /api/tasks 500 on NULL sheety_id (+ pytest harness tests/conftest.py)
- escape task names in innerHTML (XSS) + day-log error state with retry
- password reset logged user out (missing ua_hash); min password length 8 everywhere
- admin delete-user now cascades to all user-owned tables
- edit/delete send ?by=sheety to avoid local/sheety id ambiguity
- week strip clipping fixed, per-day logged bars, tablet header no overflow
- perf: vectorised fetch_local_data (1s -> 35ms), verified identical output
- login throttling (login_failures table) + single-use verification codes
- matrix cards: share delta vs previous period
- dark mode contrast + water-fill wash fix + dividers
- date navigation month overflow + UTC/local fixes (dashboard + graphs)
- real default app icon + /favicon.ico
- Insights section (top activities, vs-7-day avg, best/worst day, completeness)
- 'Log in via OTP' + 'Resend code' buttons were broken (disabled submitter) -> fixed
- graphs: a11y pressed states; All range no longer capped at 365 days
- 24h day timeline strip; Period Total badge/bar show real logged coverage
- Daily goals (Settings > Daily Goals; user_goals table; dashboard progress)
- Settings: 'AI Keys' -> 'API Keys'; shortcuts 3/4
- deleted-user sessions now dropped (login_required/admin_required)
- first-run welcome card, 'None yet' empty quadrant, register email-failure warning
- auth page labels linked to inputs (a11y)
- goal streaks on day view
- 'Day by day' stacked columns (week/month); compact week label
- graphs pill layout; security headers; README + .env.example
- graphs 'Last 7 days' card; F = full log shortcut; smoke tests (tests/test_smoke.py)
- API Keys panel auto-expands; verify-page copy; error toast escapes text
- category legend shows hours; doughnut dark mode; admin join dates/count
- non-numeric durations -> 400 (create/update)
- Saved graph views (graph_bookmarks table, /api/graph-views)
- prefers-reduced-motion; empty-period card (sync / jump to nearest logged day)
- dark: bg-white/65-75 surfaces; period-aware subtitle copy

## Questions for owner (not changed, need your call)
- dashboard.html (end of main script): every dashboard load fires a *forced* background sync
  (`runManualSync({reload:false})` -> /sync-now, force=True) 2s after load. That bypasses the
  server-side SYNC_INTERVAL throttle, so each page view costs a Sheety request (quota!), and the
  result isn't shown until the next navigation. Consider dropping it or making it non-forced.
- instance/pwa/app-icon.png (the uploaded icon) is actually a JPEG (394x394); manifest claims 512x512 PNG.
  It now gets served with the right content type, but a real 512x512 PNG would be better for PWA installs.

## Ideas / TODO queue
- UX polish: keyboard shortcuts, empty states, a11y labels
- Feature ideas: streaks / goals, weekly summary insights

## Dev notes
- Prod runtime is python 3.12 (runtime.txt): also test with ~/.local/bin/python3.12 venv.
- Test venv: python3 -m venv <scratch>/venv && pip install -r requirements.txt pytest (project venv/ is broken: points at old path)
- Run dev server safely: copy productivity_demo_data.db, blank sheety creds in the copy, set DISABLE_CLOUD_SYNC=1,
  SMTP/BREVO empty, HTTP(S)_PROXY=http://127.0.0.1:9, LOCAL_AUTH_BYPASS=1 LOCAL_AUTH_USER_ID=3 (user with most data)
