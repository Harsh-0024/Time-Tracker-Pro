# Overnight Worklog (branch: overnight-improvements)

Started: 2026-10-07. Owner asked: improve anything (bugs > UX > aesthetics > features),
work until told to stop. DO NOT touch the time-passing logic. Do not push/deploy/merge.
Do not touch untracked *.db files. Commit small, focused changes locally on this branch.

Note: *.md is gitignored; this file is force-added (git add -f WORKLOG.md).

## Status / last heartbeat
- 2026-10-07 ~05:15 IST: UX/dark-mode/date fixes done; building Insights card next.

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

## Ideas / TODO queue
- UX polish: keyboard shortcuts, empty states, a11y labels
- Feature ideas: streaks / goals, weekly summary insights

## Dev notes
- Test venv: python3 -m venv <scratch>/venv && pip install -r requirements.txt pytest (project venv/ is broken: points at old path)
- Run dev server safely: copy productivity_demo_data.db, blank sheety creds in the copy, set DISABLE_CLOUD_SYNC=1,
  SMTP/BREVO empty, HTTP(S)_PROXY=http://127.0.0.1:9, LOCAL_AUTH_BYPASS=1 LOCAL_AUTH_USER_ID=3 (user with most data)
