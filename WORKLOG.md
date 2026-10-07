# Overnight Worklog (branch: overnight-improvements)

Started: 2026-10-07. Owner asked: improve anything (bugs > UX > aesthetics > features),
work until told to stop. DO NOT touch the time-passing logic. Do not push/deploy/merge.
Do not touch untracked *.db files. Commit small, focused changes locally on this branch.

Note: *.md is gitignored; this file is force-added (git add -f WORKLOG.md).

## Status / last heartbeat
- 2026-10-07 22:33 IST: 22:20 resume session ACTIVE.

## 21:20 run summary - most important first
1. Feature: Insights 'Top activities' now show a trend per activity (week/month: per-day change vs last period; day: 'usually Xh/day').
2. Feature: 'Copy summary' button (+ C shortcut) copies a plain-text recap of the period.
3. Feature: installed-app icon shortcuts (Add task / This week / Graphs) via /#add-task deep link, which also survives a login.
4. Fixes: Daily Goals kept typed values on error; graphs export picker is a proper keyboard dialog; friendlier login error.
5. Audits with no findings: eslint over all inline JS, axe structural rules on 7 pages, None/nan sweep over 27 period/date combos.
Note: starting a dev server in the browser pane was declined (unattended), and copying the demo DB was blocked - all checks used synthetic data via the Flask test client + jsdom.
All tests pass (187, py3.14 + 3.12). Nothing pushed.

## 19:20 run summary - most important first
1. SECURITY: verification/welcome emails injected the registrant's name as raw HTML (phishing via someone else's address). Escaped.
2. BUG: search 'sleep, rest' (graphs placeholder example) matched nothing; graphs chart vs Review list disagreed for 'only X' and quoted phrases ("Deep work ." rows). All aligned + tests.
3. BUG: one unsynced log anywhere blocked editing every task ('must be linked to Sheety'). Fixed. Also: 'Missing time' mishandled logs crossing midnight.
4. BUG: stale session (browser update changes UA) made /login drop ?next= -> you landed on the dashboard. Fixed.
5. UX: Insights Top-activity rows now list exactly what they counted; Settings export toasts for empty range/errors instead of raw JSON / empty file.
6. Features: Add-task name autocomplete w/ tag prefill; week/month 'vs last week/month' daily averages; graphs 'By time of day' card; 'Again' on task cards; swipe week strip / day-by-day chart on phones; admin log counts.
7. Perf: responses gzipped (dashboard 292KB -> 53KB); graph search ~10x faster (vectorised, equivalence-tested); task lists/exports iterate records (~300ms saved at 22k logs).
8. a11y: skip links, date-picker + graphs focus-menu keyboard support.
All tests pass (178, py3.14 + 3.12). Nothing pushed.

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
- [12:06 run] dark a11y (axe): active Day/Week/Month pill was cream-on-amber 1.3:1 -> dark text; matrix-card sub-labels + share % lifted from 2.5-4:1 to >=5.5:1
- [12:06 run] a11y: day timeline / day-by-day columns used role=listitem on buttons/links (invalid) -> labelled groups
- [12:06 run] contrast: dark rose-700/900 text (graphs 'vs avg' delta, waste numbers, load-error card) + settings goal 'h / day' suffix
- [12:06 run] feat: week/month full log (time sort) groups cards under day headers ('Tue 6 Oct · 17 tasks · 21.5 hr'); other sorts keep per-card dates
- [12:06 run] feat: same day headers in graphs 'Review tasks'
- [12:06 run] phones: month title no longer wraps ('September 2026' + 'View Full Month' button) -> button reads 'Full Month' (aria-label keeps full text); server renders the right period label (was 'View Full Day' until JS ran)
- [12:06 run] a11y: visible keyboard focus rings on day-by-day columns, 24h timeline segments, Insights activity rows (outline was removed)
- [14:21 run] BUG: X-API-Token header auth never matched (dict(request.headers) spells it 'X-Api-Token'); only ?token= worked
- [14:21 run] SECURITY: /sync-now, /hard-reset refuse cookie-session GET (405); dashboard POSTs; API-token GET still OK
- [14:21 run] UX: global error boundary - offline/network failures showed a red toast per request and, after 3, a full-screen 'unstable' overlay; now one connection hint; also removed beacon to non-existent /api/log-error
- [14:21 run] phones: bottom nav highlighted the wrong section (Insights never lit, 'Tags' shown while reading Insights) - IntersectionObserver threshold 0.4 can't fire for sections taller than ~2.5 screens; replaced by a scroll-position spy (+ aria-current)
- [14:21 run] dark mode: task-modal pie charts (dashboard full log, graphs Review tasks) had glaring white slice borders -> surface colour
- [14:21 run] numbers: server rounded halves to even (3.25h -> 3.2h) while JS views show 3.3h - common with 15-min logs; core/numbers.round_half_up used in matrix/insights/dashboard. Day timeline '6.7h of 24h' (rounded % converted back) -> real hours
- [14:21 run] BUG: creating a task while a sheet rewrite was in progress (Sheety write queued, no row id) saved the row and then 500'd (int(None)) -> user would re-add = duplicate. Now 200 + queued flag. No-Sheety error copy now says where to connect a sheet.
- [14:21 run] api: absurd task durations (1e19) overflowed datetime -> 500; now 400 above a 1-year sanity bound (24h cap question still open). JSON/query fuzz of all write endpoints: 0 server errors now
- [14:21 run] feat: dashboard shortcut N = add a task (opens the full log with the Add-task form focused); listed under '?'
- [14:21 run] graphs on phones: no way to Settings/Logout (desktop-only group) -> name pill links to Settings like the dashboard; 'Back to Dashboard' reads 'Dashboard' on phones so the row fits 320px
- [14:21 run] UX: Escape in a task modal with the Add/Edit/Delete panel open closed the whole modal (losing typed input); now it closes the panel first (dashboard + graphs)
- [14:21 run] settings API Keys: add/delete/test used blocking alert() boxes and Save had no busy state (double click saved the account twice) -> toasts + 'Saving...' guard
- [16:20 run] dashboard: day-view summary caption said 'October 2026 · Day view totals.' -> names the day; Top-category card no longer prints its % twice
- [16:20 run] settings/admin: Logout was the black primary CTA -> secondary pill; settings 'Back' -> 'Dashboard'
- [16:20 run] Insights on today: 'Today so far vs your last 7 days'; Growth shortfall reads 'Xh to reach your average' (not a red miss mid-day)
- [16:20 run] BUG: Back after 'Log in via OTP' restored the login page from bfcache with disabled buttons + the hidden action=login_otp, so 'Log In' then sent an OTP. _form_busy.html (markFormBusy + pageshow restore) on all auth forms + settings. Settings email/OTP busy handlers never ran (selectors matched endpoint names, not URLs) and labelled the wrong button.
- [16:20 run] BUG: full-log stat tiles showed Growth/Drudgery/Waste only (Critical missing, didn't add up to the total) -> 4 tiles, 2x2 on phones
- [16:20 run] dashboard loaded Tailwind with defer -> unstyled first paint (blue default buttons); other pages had already dropped defer
- [16:20 run] verify page said 'We sent a 6-digit code' + expiry right above 'We couldn't send the email' -> honest header when the send failed (+ test)
- [16:20 run] export: dismissing the CSV/JSON picker still toasted 'Summary exported successfully'; Export Summary file named after the exported day, not today
- [16:20 run] week 'Day by day': each column shows its hours (were tooltip-only, invisible on touch)
- [16:20 run] header: 'September 2026' wrapped at every width (fixed 240px column); week/month titles take free space; 768-1023px day strip showed ~5 of 7 days -> fits (button 'Full Day' there); summary cards p-6 below lg
- [16:20 run] exports: overnight logs had end date = start date -> /api/tasks + graph-data rows carry end_date (+ test)
- [16:20 run] register / forgot-password errors kept nothing typed -> name/email/user ID (never passwords) preserved (+ tests)
- [16:20 run] register note: stock blue box -> cream/amber like the rest of the app
- [16:20 run] fuzzed ~2000 GETs on graph-data/search/tasks/tags/export/dashboard params: 0 server errors
- [16:20 run] a11y: total/avg + consistency stat toggles (dashboard full log, graphs Review) keyboard-operable; 'Time by Category' card reachable (heading button); pie legend toggles are buttons w/ aria-pressed on both pages
- [16:20 run] charts: a single-slice pie/doughnut showed its rim as a white seam -> no border when only one slice has data
- [16:20 run] week strip: today gets a gold ring when another day is selected; day links have full names ('Wednesday 7 October, today, 6.8 hours logged') + aria-current
- [16:20 run] graphs saved views: delete failures were silent/unhandled -> toast; 404 drops it
- [16:20 run] dashboard edit-panel neighbour lookup cached failed fetches forever and rejected unhandled offline -> best-effort, uncached on failure
- [16:20 run] dashboard tab title names the period ('Tue 6 Oct · Time Tracker Pro') - history/tabs were indistinguishable
- [16:20 run] a11y: toasts announced (polite live region, errors role=alert); toast colours deepened so white text >= 4.5:1 (success/warning were 2.5/2.2:1); error-boundary overlay is a labelled alertdialog with focus on Reload
- [16:20 run] privacy: Settings > API Keys URL placeholder showed a real-looking Sheety project ID (1a861cfa...) to every user -> 'your-project-id'; bearer token input masked with Show/Hide
- [16:20 run] feat: 'Missing time' gap chips are buttons that open Add task prefilled with the gap (end left blank when the gap runs to midnight). Not browser-verified yet (needs a Sheety account to submit).
- [19:20 run] dashboard: Top category % came from rounded per-tag hours (same 4.5h Waste read 43.3% vs 43.9% on Dominant quadrant) -> raw minutes (+ test)
- [19:20 run] feat: week/month Insights 'Daily average' shows 'vs last week: +0.4h growth · −0.8h waste' (per logged day; hidden when previous period empty) (+ test)
- [19:20 run] perf: dashboard tilt (deviceorientation) water animation rAF-coalesced, cached nodes, off with reduced motion
- [19:20 run] BUG: search 'sleep, rest' (the graphs placeholder example!) matched nothing - comma stuck to 'sleep,'. Fixed in server parser + graphs + dashboard full-log search (+ tests)
- [19:20 run] perf: graph-data include_tasks / export-csv iterate records not iterrows (~600 -> ~330ms at 22k logs; byte-identical output)
- [19:20 run] perf: graph search filter vectorised (~10x; equivalence test vs the row matcher)
- [19:20 run] feat: phones - swipe the week strip (±1 week, same weekday) or the week/month 'Day by day' chart (±1 period); arrow keys share the same shiftPeriod()
- [19:20 run] feat: full-log task cards have 'Again' (Add task prefilled with name/tags/priority; focus on End). Phones: card actions on their own row (3 buttons squeezed the times)
- [19:20 run] chore: removed dead promptAddTaskAfterDelete (blocking confirm) from dashboard + graphs
- [19:20 run] graphs Review-task cards: actions on their own row on phones (same as dashboard)
- [19:20 run] config: SESSION_COOKIE_SECURE=0/false no longer enables Secure cookies (+ test)
- [19:20 run] feat: graphs 'By time of day' card (avg minutes/day per hour slot for the focus; peak hour; /api/graph-data by_hour) (+ test)
- [19:20 run] BUG: /login (and /register, /forgot-password) checked the raw session: after a UA change (browser update) the stale session bounced /login?next=/graphs -> dashboard -> /login?next=/ so you landed on the dashboard. Also logged-in /login?next=X now goes to X (+ tests)
- [19:20 run] a11y: 'Skip to content' link (first Tab) on dashboard, graphs, settings, admin
- [19:20 run] settings export: fetched first - empty range -> 'No logs in that range' (was a header-only file), errors/expired session -> toast/login (was raw JSON page), success toast with count; server sends X-Export-Rows (+ test)
- [19:20 run] feat: admin users list shows each user's log count + last logged date (+ test)
- [19:20 run] Insights Top activities: clicking a row listed every task containing the name ('Lunch with team' under Lunch) -> full-log search gains 'only <name>' (exact, ignores trailing '.'), rows use it; list total = row hours
- [19:20 run] graphs: server 'only X' (chart) didn't ignore trailing ' .' while the Review list did -> aligned (+ test)
- [19:20 run] graphs: quoted phrase '"deep work"' - server required the whole task to equal it (chart dropped 'Deep work .') while the list used consecutive words -> server uses the list's rule (+ test)
- [19:20 run] full-log search placeholder shows syntax ('gym, reading · only lunch · -waste')
- [19:20 run] a11y: dashboard date button named 'Choose date (showing ...)', aria-expanded synced, Escape closes the calendar
- [19:20 run] a11y: graphs focus menu - arrow keys/Home/End/Escape, aria-expanded, aria-current on selected option
- [19:20 run] graphs shortcuts: R = Review tasks, S = Settings
- [19:20 run] SECURITY: verification + welcome emails put the registrant's free-text name into HTML unescaped -> anyone could register with someone else's address and a name like <a href=evil>Secure your account</a> (phishing inside a genuine app email). Escaped (+ test)
- [19:20 run] fuzz: 3,920 graph-data param combos incl. overnight/zero/negative logs - 0 errors, by_hour always 24 non-negative
- [19:20 run] perf: app gzips HTML/JSON/CSS/JS (dashboard 292KB -> 53KB per load; files/static/streams untouched; DISABLE_GZIP=1 to opt out; README/.env.example) (+ test, 3.12 ok)
- [19:20 run] perf: static URLs get ?v=<mtime> (url_defaults) and versioned requests are cached 1 year; unversioned keep revalidating. Auth/error pages switched from hard-coded /static/ to url_for (+ test)
- [19:20 run] perf: Google Fonts preconnect on all pages
- [19:20 run] audit (no change needed): rendered pages have no duplicate ids, no dangling label-for / aria-labelledby / describedby / controls; no |safe in templates; API token compare is constant-time
- [19:20 run] feat: Add task name autocomplete (60 most-used recent names); picking one pre-fills its usual tags/priority if untouched (+ tests)
- [19:20 run] Edit-task name field uses the same suggestions
- [19:20 run] BUG: after add/edit/delete in the full log, closing it left the dashboard totals/matrix/timeline/insights stale -> reloads on close after a successful change (not verified end-to-end: needs Sheety)
- [19:20 run] 320px pass: full log (Again/Edit/Delete row) and graphs fit with no sideways scroll; time-of-day caption shortened on phones; README features updated
- [19:20 run] graphs phone nav: Insights item (-> dashboard#insights), matching the dashboard's five items
- [19:20 run] dashboard shortcut '/' = search the full log (as on graphs)
- [19:20 run] feat: graphs reopens with last focus/range/MA (localStorage, validated; search intentionally not restored)
- [19:20 run] perf: Add-task overlap check only reads logs whose dates touch the entry (115ms -> 2ms at 22k; new overlap test incl. overnight)
- [19:20 run] BUG: editing ANY task failed with 'Overlapping tasks must be linked to Sheety' if the user had a single unsynced log anywhere (check ran before the overlap test). Now only overlapping logs are checked; scan date-limited (+ tests)
- [19:20 run] BUG: full-log 'Missing time' wrapped tonight's overnight log onto this morning and ignored logs carried in from the previous evening -> /api/tasks day returns carry_in_minutes; overnight logs cover only the rest of the day (+ test). Display only; no stored times touched. (The 'future hours of today count as missing' question remains yours.)
- [21:20 run] feat: Insights Top activities show trend - week/month: 'X.Xh/day · ▲ 0.4h vs last week' (per logged day, same basis as Daily average); day: 'usually Xh/day' from the last 7 days (+ ▲/▼ on past days, not today). Neutral colour (+ tests)
- [21:20 run] audit: eslint (no-undef etc.) over every page's inline JS - only window.* globals flagged, no real issues; rendered 27 dashboard period/date combos: no None/nan leaks
- [21:20 run] copy: login failure 'Invalid credentials.' -> 'That login and password don’t match. Check both and try again.' (still non-enumerating)
- [21:20 run] settings: Daily Goals keeps the typed values after a validation error (was reset to saved values) (+ test)
- [21:20 run] feat(PWA): manifest shortcuts - long-press the installed icon for Add task / This week / Graphs; '/#add-task' opens the full log with Add task focused (shared with the N shortcut; hash cleared). jsdom-verified (+ test)
- [21:20 run] a11y: graphs export-format picker -> dialog role/label, focus to CSV, Escape closes only the picker, Tab trap, focus returns (jsdom-verified). axe (structural rules) on dashboard (incl. Add-task open), graphs, settings, login, register, forgot: no other findings
- [21:20 run] feat: dashboard 'Copy summary' (next to Export Summary) copies a plain-text recap of the day/week/month: logged hours + %, four quadrants, top activities, daily avg vs last period / vs recent days, best day, longest growth block, goals. services/summary.py, built from the page's own numbers; clipboard fallback + error toast; hidden for empty periods; 'Copy' on phones. jsdom-verified (+ tests incl. </script> in task names)
- [21:20 run] fix(login): '#add-task' survives a login (login page appends a simple #hash to 'next'; was lost so an expired session + PWA shortcut landed on the plain dashboard). jsdom-verified (+ test)
- [21:20 run] feat: dashboard shortcut C = Copy summary (in '?' help)
- [21:20 run] README: activity trends, Copy summary, PWA shortcuts. Tests also pass on python 3.12 (187)
- [22:20 run] feat: week/month 'Goals this week/month' show one dot per day under each goal (met = green, below goal = amber, over Waste limit = red, nothing logged = dashed, not started = faint); dots link to that day; tooltips/labels give hours (+ test). Browser-checked light/dark
- [22:20 run] BUG: Settings > Update Profile showed NEITHER 'Current password' nor 'Email code' on load (setAuthMode for the Password form hid the User ID form's fields) -> each form's switch only touches its own fields; aria-pressed on toggles. Browser-verified
- [22:20 run] SECURITY: Settings mirrored the typed NEW PASSWORD + confirmation into sessionStorage in plaintext (to survive the 'Send code' reload). 'Send code' (User ID/Password forms) now posts in the background (/profile/request-otp returns JSON for Accept: application/json; toast + focus the code box), nothing is stored, stale keys purged on load; falls back to a normal submit if the fetch fails (+ tests)
- [22:20 run] feat: day view Daily goals show the last 7 days as dots under each bar (oldest -> selected day); today's Growth below target is an amber ring 'so far', not a miss (also in the current week/month row; counts unchanged) (+ test)
- [22:20 run] feat: graphs 'Calendar' card - GitHub-style heatmap of the focus metric over the plotted days (53 weeks; 26 on phones, re-renders on breakpoint change), 5 levels in the focus colour, month labels, 'N of M days active · longest run X days', click a day -> dashboard day view; hidden under 28 days. Browser-checked desktop/phone/dark (+ smoke test)
- [22:20 run] BUG (phones): verify-email page refocused + scrolled the code box on EVERY tap, so a tap on 'Resend code'/links could miss as the page moved. Only empty-space taps refocus now (no scroll). Browser-verified
- [22:20 run] BUG: forgot-password ('Email or user ID') turned a user ID into '<id>@gmail.com' on blur -> only a trailing '@' is completed (as on login). Browser-verified
- [22:20 run] login: Enter in the password field used form.submit() (no busy state, double Enter = double POST, no validation) -> requestSubmit(Log In). Browser-verified
- [22:20 run] README: goal dots, calendar heatmap

## Questions for owner (not changed, need your call)
- (IMPORTANT) The Sheety URL placeholder in settings.html used project ID 1a861cfa9dca4f459ca9c1bf60ca2e09 (now replaced on this branch). If that is your real Sheety project, it is still in git history and in the currently deployed page; if the sheet has no Bearer auth enabled, anyone who saw it could read/write it. Consider enabling Sheety auth or rotating the project.
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
- (note) Chart.js (pinned 4.5.1 on jsdelivr) could get an SRI integrity hash, but cdn.tailwindcss.com (unpinnable, loaded on every page) makes that moot until Tailwind is compiled locally.
- (question) DISABLE_CLOUD_SYNC is truthy-checked (sync.py, __init__.py): DISABLE_CLOUD_SYNC=0 or =false DISABLES sync. Not changed: if a deployment sets =0 today, fixing it would switch background sync on. Check your env, then parse it like SESSION_COOKIE_SECURE.
- (question) graph/full-log search: '-' is the NOT operator even inside words, so 'deep-work' = deep AND NOT work and a date like 2026-10-05 searches '2026 NOT 10 NOT 05'. Quoting ("e-mail") works. Could treat '-' as NOT only after whitespace/start - left as is since it changes query semantics.
- (question) Full Day Log 'Missing time' for TODAY lists the rest of the day (e.g. '2:00 PM - 12:00 AM') as unlogged, including hours that haven't happened yet. Graphs 'Last 7 days' also includes today's partial day. Both are time-handling, so left for you.
- (question) Adding a task REQUIRES a connected Sheety account (create_task posts to Sheety first; local-only users get an error). Update/delete of local-only rows work. If you want local-only users to add tasks, create_task needs a local path - left alone since it touches the sync model.
- (question) Sessions are bound to the User-Agent (ua_hash). Every browser auto-update (UA version bump) or Safari 'Request Desktop Website' logs the user out. Consider hashing only the browser family/OS, not the full UA.
- (note) dark --text-faint (#6E6045) is 3.2:1 - axe flags ~10 small labels (timeline axis, insight labels). Earlier session chose it for hierarchy; bump to ~#877858 for AA if you prefer.
- (question) /sync-status answers anonymous callers with config booleans (sheety configured, db exists). Harmless-ish; could 401.
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
- Live dev server on synthetic data (no real DB): build a temp DB via create_app({'DB_NAME': tmp}) + insert a verified user and logs, app.run on a free port (5055/5077 may hold leftovers from older sessions - don't kill those). Use tags Work/Necessity/Soul/Rest/Waste only (others count as Waste). Browser-pane viewport/UA changes log you out (ua_hash).
- Visual checks without the app server: serve those rendered HTML files with `python3 -m http.server` (symlink static/) and open in the browser pane (mobile/dark via resize_window).
- Gotcha: when the browser pane is hidden, requestAnimationFrame is paused, so Chart.js defers resizes forever and charts look oversized/overflowing. Not a real bug.
- JS behaviour checks without a server: render pages via the Flask test client with synthetic data, then load the HTML in jsdom (npm i jsdom in the scratchpad; stub IntersectionObserver/matchMedia/fetch/Chart).
- Prod runtime is python 3.12 (runtime.txt): also test with ~/.local/bin/python3.12 venv.
- Test venv: python3 -m venv <scratch>/venv && pip install -r requirements.txt pytest (project venv/ is broken: points at old path)
- Run dev server safely: copy productivity_demo_data.db, blank sheety creds in the copy, set DISABLE_CLOUD_SYNC=1,
  SMTP/BREVO empty, HTTP(S)_PROXY=http://127.0.0.1:9, LOCAL_AUTH_BYPASS=1 LOCAL_AUTH_USER_ID=3 (user with most data)
