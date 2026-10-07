# Overnight Worklog (branch: overnight-improvements)

Started: 2026-10-07. Owner asked: improve anything (bugs > UX > aesthetics > features),
work until told to stop. DO NOT touch the time-passing logic. Do not push/deploy/merge.
Do not touch untracked *.db files. Commit small, focused changes locally on this branch.

Note: *.md is gitignored; this file is force-added (git add -f WORKLOG.md).

## Status / last heartbeat
- 2026-10-07 12:06 IST: resume session ACTIVE (scheduled run).

## Morning summary (06:22-09:00 session) - most important first
1. DATA LOSS: /api/import-csv with a CSV that had no valid rows deleted ALL of the user's logs. Fixed + test.
2. Security/privacy: Sheety URL must be public https (SSRF); email masked when a code is requested by user ID;
   60s cooldown on OTP/forgot/resend emails; user IDs can't look like emails (login shadowing).
3. Crashes: graphs 'Review tasks'/Export on an empty list; /api/tasks 500s on odd JSON; ?date=0001/9999 500s.
4. Races: graphs chart could show the wrong range; dashboard modal could open the wrong card's tasks.
5. UX: Necessity tag chip was missing from Add task; tabs/modals/week strip fit small screens; 'By weekday' card.
6. Dark mode: summary badges/progress tracks were light (broken CSS selectors); chips' selected state invisible.
Also: styled error pages, Edit-task tag chips. All 124 tests pass (3.14 and 3.12). Nothing pushed.

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
- security: 60s resend cooldown on OTP/forgot/resend (VERIFICATION_RESEND_COOLDOWN_SECONDS) + UI countdown
- password reset clears login lockout
- 'Name .' and 'Name' grouped together in Insights + modal charts (display only)
- Add-task Necessity chip; full-log quadrant names match the matrix (Growth/Drudgery)
- Edit-task tag chips; dark-mode selected chips were invisible; Missing-time card dark-mode contrast
- dark mode: 12 CSS rules never matched (unescaped '#' in .bg-\[#hex\]) -> summary badges/tracks now dark
- a11y: theme buttons + Day/Week/Month aria-pressed; calendar arrows labelled
- styled 403/404/405/500 pages (JSON for /api/*)
- [08:22 run] CSV export: cells starting with = + - @ quote-prefixed (spreadsheet formula injection)
- [08:22 run] toasts render text by default (server errors/account emails were innerHTML); html opt-in
- [08:22 run] 16MB request body cap (MAX_CONTENT_LENGTH_MB) + 413 page/JSON
- [08:22 run] non-ASCII API token -> 401 (was 500)
- [08:22 run] login next= rejects '/\\evil.com' and control chars (open redirect)
- [08:22 run] Insights: 'Longest growth block' (day/week/month; links to the day)
- [08:22 run] password show/hide toggles: aria-pressed
- [08:22 run] admin: ADMIN_EMAILS admins shown as admin and can't be deleted
- [08:22 run] graph-views ma=Infinity -> 400 (was 500)
- [08:22 run] dashboard shortcuts (arrows/T/G/S) no longer navigate behind an open task/export dialog; <select> ignored
- [08:22 run] settings export modal: dialog semantics, focus in/out, Tab trap; shortcuts paused while open
- [08:22 run] dashboard export-format picker: Escape closed the task modal underneath -> now closes picker only
- [08:22 run] docs: MAX_CONTENT_LENGTH_MB in README/.env.example
- [08:22 run] dark mode: primary black-pill buttons (Log In, Export, Add task, active toggles) were invisible shapes -> gold/emerald tint + ring
- [08:22 run] login/forgot/user-ID inputs: autocapitalize/autocorrect off
- [08:22 run] week strip: all 7 days fit on phones (was 4 + scroll) and at 1024-1279px (7th day was clipped)
- [08:22 run] 320px: 'View Full Month' header no longer overflows
- [08:22 run] SECURITY: password-reset session now expires after the code TTL (was unlimited); verify/reset pages show the configured TTL
- [08:22 run] settings: wrong current password -> 'Current password is incorrect.'
- [08:22 run] input caps: graph search history (200 chars, 1000 rows/user), Sheety account fields, name 80 / email 254 / password 1024 (no slow hash on huge passwords)
- [08:22 run] perf: tag strings parsed once per distinct value in fetch_local_data (~30ms/request at 22k logs). Remaining cost is pandas strftime for display times (left alone: time formatting).
- [08:22 run] client-side Review exports (dashboard/graphs) also guard formula cells
- [12:06 run] a11y: dashboard 'Time Tracker Pro' sync title is a real <button> (keyboard-focusable) inside the h1
- [12:06 run] SECURITY: Settings current-password check throttled (login_failures, key 'profile #<id>'); OTP still works when locked
- [12:06 run] api: /sync-now, /hard-reset, Sheety test-connection no longer echo raw exception text
- [12:06 run] reset-password: visible 8-char hint (was placeholder only) + live 'do not match' check; register hints tied via aria-describedby
- [12:06 run] settings: Sheety summary reads 'No accounts yet' / 'N saved · none active' instead of 'No active account · Priority -'
- [12:06 run] full-log modal stat tiles: quadrant explainer moved to a sub-line shown from sm up (wrapped to 5 lines on phones)
- [12:06 run] task lists (dashboard full log, graphs Review tasks): dates read 'Wed 7 Oct' (locale-aware; ISO in tooltip) instead of '2026-10-07'
- [12:06 run] graphs Review-tasks pie: slice colours picked for distinct hues (green schemes coloured the top 3 slices green)
- [12:06 run] Add/Edit task panels: stray 'Close' text -> labelled x icon button; copy no longer implies Sheety is always on
- [12:06 run] admin: 'Remove a User' hides the message box + dead button when nobody is removable

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
- (question) /sync-status answers anonymous callers with config booleans (sheety configured, db exists). Harmless-ish; could 401.
- (question) /sync-now and /hard-reset are GET with side effects; SameSite=Lax lets another site trigger a forced Sheety sync via a top-level link. Low impact (quota). Consider POST.
- (note) a dev server with LOCAL_AUTH_BYPASS was blocked by the session's permission classifier; verification done via pytest/Flask test client.
- (question) ~174 distinct task names are stored with a trailing ' .' (e.g. 'Instagram .' x396 vs 'Instagram' x14) -
  looks like the parser keeps the sentence-ending dot. I only merged them for display; the parser is yours.
- (question) forgot-password / login-OTP say "No account found" -> account enumeration. Kept for UX; consider generic copy.
- (question) manifest declares the icon as 512x512 PNG; the uploaded one is a 394x394 JPEG. Uploads are now PNG-checked; re-upload a real 512 PNG.
- (question) /api/import-csv REPLACES all of a user's logs with the CSV contents (by design?). A 1-row CSV
  would wipe thousands of rows. No UI calls it today. Consider append/merge or a confirm flag.
- (question) /api/tasks has no upper bound on duration (e.g. 500h accepted if it overlaps nothing). Cap at 24h? Left for owner.
- UX polish: keyboard shortcuts, empty states, a11y labels
- Feature ideas: streaks / goals, weekly summary insights

## Dev notes
- Visual checks without the app server: serve those rendered HTML files with `python3 -m http.server` (symlink static/) and open in the browser pane (mobile/dark via resize_window).
- Gotcha: when the browser pane is hidden, requestAnimationFrame is paused, so Chart.js defers resizes forever and charts look oversized/overflowing. Not a real bug.
- JS behaviour checks without a server: render pages via the Flask test client with synthetic data, then load the HTML in jsdom (npm i jsdom in the scratchpad; stub IntersectionObserver/matchMedia/fetch/Chart).
- Prod runtime is python 3.12 (runtime.txt): also test with ~/.local/bin/python3.12 venv.
- Test venv: python3 -m venv <scratch>/venv && pip install -r requirements.txt pytest (project venv/ is broken: points at old path)
- Run dev server safely: copy productivity_demo_data.db, blank sheety creds in the copy, set DISABLE_CLOUD_SYNC=1,
  SMTP/BREVO empty, HTTP(S)_PROXY=http://127.0.0.1:9, LOCAL_AUTH_BYPASS=1 LOCAL_AUTH_USER_ID=3 (user with most data)
