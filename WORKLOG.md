# Overnight Worklog (branch: overnight-improvements)

Started: 2026-10-07. Owner asked: improve anything (bugs > UX > aesthetics > features),
work until told to stop. DO NOT touch the time-passing logic. Do not push/deploy/merge.
Do not touch untracked *.db files. Commit small, focused changes locally on this branch.

Note: *.md is gitignored; this file is force-added (git add -f WORKLOG.md).

## Status / last heartbeat
- 2026-10-07 08:31 IST: session active (resumed 06:22).

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
- matrix cards keyboard-accessible; Chart.js pinned 4.5.1; _is_admin refactor
- mobile nav Insights item; goal/limit reference line on q2/q4 graphs
- a11y: settings/task-modal/admin inputs labelled; autocomplete + one-time-code hints
- category doughnut hides % labels <5%; graphs 'Last 7 days' -> 'none since <date>' when empty
- settings profile tabs fit on phones (tablist semantics)
- api: non-object JSON / non-string fields / 'inf' duration no longer 500
- ?date= with year 0001/9999 no longer 500 (guard in web/utils.request_date_param)
- security: Sheety base URL must be public https (server fetches it -> SSRF)
- DATA LOSS fix: /api/import-csv with no valid rows deleted all the user's logs
- graphs: stale graph-data responses ignored (chart could show 30d under 'All')
- dashboard: latest matrix click wins; removed debug console.logs
- login redirect next= without dangling '?'; graphs shortcuts (/ 1-6 ?); graphs y-axis from 0
- empty-state copy names the period
- admin icon upload checks PNG bytes; goals '-0' -> 0
- task modals (dashboard+graphs): wider on phones, names wrap, single-day lists drop repeated date
- graphs: 'Review tasks'/Export crashed on empty task list
- matrix Total card: '% of <period> logged' (was constant 100%); close buttons named
- feat: graphs 'By weekday' card (avg per weekday for focus/range)
- week strip fits 7 days at md; admin pages keep next= on login redirect (and POSTs no longer bounce to a 405)
- admin delete-user: no default selection + named confirm
- auth: user ID format rule (no '@'/spaces, 3-32) on register+change; email can't equal another's user ID;
  identifier lookup prefers email owner; friendlier email-failure copy (no 'Check SMTP settings')
- privacy: email masked in 'code sent to' for forgot-password / login-OTP (both accept a public user ID)
- security: 60s resend cooldown on OTP/forgot/resend (VERIFICATION_RESEND_COOLDOWN_SECONDS)

## Questions for owner (not changed, need your call)
- dashboard.html (end of main script): every dashboard load fires a *forced* background sync
  (`runManualSync({reload:false})` -> /sync-now, force=True) 2s after load. That bypasses the
  server-side SYNC_INTERVAL throttle, so each page view costs a Sheety request (quota!), and the
  result isn't shown until the next navigation. Consider dropping it or making it non-forced.
- instance/pwa/app-icon.png (the uploaded icon) is actually a JPEG (394x394); manifest claims 512x512 PNG.
  It now gets served with the right content type, but a real 512x512 PNG would be better for PWA installs.
- Tailwind is loaded from cdn.tailwindcss.com (the in-browser JIT "play" build, ~300KB JS, not meant for
  production; dashboard loads it with `defer`, which can flash unstyled content). Compiling a static CSS file
  with the Tailwind CLI would be faster, but classes built in JS strings need care, so I left it.

## Ideas / TODO queue
- (question) forgot-password / login-OTP say "No account found" -> account enumeration. Kept for UX; consider generic copy.
- (question) manifest declares the icon as 512x512 PNG; the uploaded one is a 394x394 JPEG. Uploads are now PNG-checked; re-upload a real 512 PNG.
- (question) /api/import-csv REPLACES all of a user's logs with the CSV contents (by design?). A 1-row CSV
  would wipe thousands of rows. No UI calls it today. Consider append/merge or a confirm flag.
- (question) /api/tasks has no upper bound on duration (e.g. 500h accepted if it overlaps nothing). Cap at 24h? Left for owner.
- UX polish: keyboard shortcuts, empty states, a11y labels
- Feature ideas: streaks / goals, weekly summary insights

## Dev notes
- Prod runtime is python 3.12 (runtime.txt): also test with ~/.local/bin/python3.12 venv.
- Test venv: python3 -m venv <scratch>/venv && pip install -r requirements.txt pytest (project venv/ is broken: points at old path)
- Run dev server safely: copy productivity_demo_data.db, blank sheety creds in the copy, set DISABLE_CLOUD_SYNC=1,
  SMTP/BREVO empty, HTTP(S)_PROXY=http://127.0.0.1:9, LOCAL_AUTH_BYPASS=1 LOCAL_AUTH_USER_ID=3 (user with most data)
