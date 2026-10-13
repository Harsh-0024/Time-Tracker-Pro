// Graphs page script (moved out of templates/graphs.html so browsers cache it).
// Per-request values come from the JSON block #graphsConfig rendered by the template.
const GRAPHS_CONFIG = JSON.parse(document.getElementById('graphsConfig').textContent || '{}');
        const metricColors = {
            total: '#111827',
            important: '#2563EB',
            urgent: '#F97316',
            q1: '#F59E0B',
            q2: '#10B981',
            q3: '#94A3B8',
            q4: '#EF4444',
            work: '#10B981',
            necessity: '#F59E0B',
            soul: '#6366F1',
            rest: '#C4B5FD',
            waste: '#DC2626',
            sleep: '#8B5CF6'
        };

        const metricLabels = {
            total: 'Total time',
            important: 'Important',
            urgent: 'Urgent',
            q1: 'Important & Urgent',
            q2: 'Important & Not Urgent',
            q3: 'Urgent & Not Important',
            q4: 'Not Urgent & Not Important',
            work: 'Work',
            necessity: 'Necessity',
            soul: 'Soul',
            rest: 'Rest',
            waste: 'Waste',
            sleep: 'Sleep per night'
        };

        const TAG_COLOR_MAP = {
            Work: '#10B981',
            Necessity: '#F59E0B',
            Soul: '#6366F1',
            Rest: '#C4B5FD',
            Waste: '#DC2626'
        };

        const SPECIAL_TAGS = Object.keys(TAG_COLOR_MAP);

        function extractSpecialTags(tag) {
            if (!tag) return [];
            return String(tag)
                .split(',')
                .map(part => {
                    let clean = String(part || '').trim();
                    clean = clean.replace(/[^A-Za-z\s]+$/g, '').replace(/\s+/g, ' ').trim();
                    if (!clean || /^(undefined|null|none|nan|urg|urgent|imp|important)$/i.test(clean)) return '';
                    return clean.toLowerCase().replace(/\b\w/g, c => c.toUpperCase());
                })
                .filter(Boolean)
                .filter(tagName => SPECIAL_TAGS.includes(tagName));
        }

        function normalizeTagName(tag) {
            const tags = extractSpecialTags(tag);
            return tags[0] || 'Waste';
        }

        function formatTagNames(tag) {
            const tags = extractSpecialTags(tag);
            return tags.length ? tags.join(', ') : 'Waste';
        }

        const firstLogDateStr = GRAPHS_CONFIG.firstLogDate || '';
        const USER_GOALS = GRAPHS_CONFIG.goals || {};
        const USER_TAG_GOALS = GRAPHS_CONFIG.tagGoals || [];

        // Daily goal shown as a reference line: Growth target on the Growth (q2) graph,
        // Waste limit on the Waste-quadrant (q4) graph. Not drawn for filtered/search views.
        function goalLineFor(metricKey) {
            if (graphSearchQuery) return null;
            if (metricKey === 'q2' && USER_GOALS.growth_hours != null) {
                return { value: Number(USER_GOALS.growth_hours), label: 'Goal', color: '#10B981' };
            }
            if (metricKey === 'q4' && USER_GOALS.waste_limit_hours != null) {
                return { value: Number(USER_GOALS.waste_limit_hours), label: 'Limit', color: '#E11D48' };
            }
            if (metricKey === 'sleep' && USER_GOALS.sleep_hours != null) {
                return { value: Number(USER_GOALS.sleep_hours), label: 'Goal', color: '#10B981' };
            }
            // Category goals (Settings > Daily Goals) on the matching category graph.
            const tagGoal = USER_TAG_GOALS.find(g => String(g.tag || '').toLowerCase() === metricKey);
            if (tagGoal) {
                const isMin = tagGoal.kind === 'min';
                return { value: Number(tagGoal.hours), label: isMin ? 'Goal' : 'Limit', color: isMin ? '#10B981' : '#E11D48' };
            }
            return null;
        }

        function parseIsoDate(value) {
            const clean = String(value || '').trim();
            if (!clean) return null;
            const parts = clean.split('-').map(p => parseInt(p, 10));
            if (parts.length !== 3 || parts.some(p => Number.isNaN(p))) return null;
            return new Date(parts[0], parts[1] - 1, parts[2]);
        }

        function daysBetween(startDate, endDate) {
            if (!startDate || !endDate) return 0;
            const startUtc = Date.UTC(startDate.getFullYear(), startDate.getMonth(), startDate.getDate());
            const endUtc = Date.UTC(endDate.getFullYear(), endDate.getMonth(), endDate.getDate());
            const diff = Math.floor((endUtc - startUtc) / (24 * 60 * 60 * 1000));
            return Math.max(0, diff);
        }

        function getAllDaysDefault() {
            const first = parseIsoDate(firstLogDateStr);
            if (!first) return 30;
            const today = new Date();
            const days = daysBetween(first, today) + 1;
            return Math.max(1, days);
        }

        function normalizeRangeValue(value) {
            const raw = String(value || '').trim().toLowerCase();
            if (raw === 'all') return 'all';
            const parsed = Number(raw);
            return Number.isFinite(parsed) && parsed > 0 ? String(parsed) : '30';
        }

        function pickDefaultMAWindowForDays(days) {
            const span = Number(days) || 0;
            if (span <= 30) return 7;
            if (span <= 90) return 14;
            if (span <= 365) return 30;
            return 48;
        }

        function syncRangePills() {
            document.querySelectorAll('.range-pill').forEach(btn => {
                const isActive = normalizeRangeValue(btn.dataset.range) === currentRange;
                btn.classList.toggle('active', isActive);
                btn.setAttribute('aria-pressed', isActive ? 'true' : 'false');
            });
        }

        function syncMAPills() {
            document.querySelectorAll('.ma-pill').forEach(btn => {
                const isActive = Number(btn.dataset.ma || 0) === maWindow;
                btn.classList.toggle('active', isActive);
                btn.setAttribute('aria-pressed', isActive ? 'true' : 'false');
            });
        }

        function labelsSpanDays(labels) {
            const arr = Array.isArray(labels) ? labels : [];
            if (!arr.length) return 0;
            if (arr.length === 1) return 1;
            const first = parseIsoDate(arr[0]);
            const last = parseIsoDate(arr[arr.length - 1]);
            if (!first || !last) return arr.length;
            return daysBetween(first, last) + 1;
        }

        function getDisplayedSpanDaysForRange(labels, values = [], rangeValue = currentRange) {
            const arr = Array.isArray(labels) ? labels : [];
            if (!arr.length) return 0;
            const normalized = normalizeRangeValue(rangeValue);
            if (normalized === 'all') {
                const rawValues = Array.isArray(values) ? values : [];
                if (rawValues.length === arr.length) {
                    const firstActiveIndex = rawValues.findIndex(v => Number(v || 0) > 0);
                    if (firstActiveIndex > 0) {
                        return labelsSpanDays(arr.slice(firstActiveIndex));
                    }
                }
                return labelsSpanDays(arr);
            }
            const numeric = Number(normalized);
            if (!Number.isFinite(numeric) || numeric <= 0) return labelsSpanDays(arr);
            const startIndex = Math.max(0, arr.length - numeric);
            return labelsSpanDays(arr.slice(startIndex));
        }

        function trimLeadingInactiveForAllRange(labels, values, rangeValue = currentRange) {
            const arrLabels = Array.isArray(labels) ? labels : [];
            const arrValues = Array.isArray(values) ? values : [];
            if (normalizeRangeValue(rangeValue) !== 'all') {
                return { labels: arrLabels, values: arrValues };
            }
            if (!arrLabels.length || arrValues.length !== arrLabels.length) {
                return { labels: arrLabels, values: arrValues };
            }
            const firstActiveIndex = arrValues.findIndex(v => Number(v || 0) > 0);
            if (firstActiveIndex <= 0) {
                return { labels: arrLabels, values: arrValues };
            }
            return {
                labels: arrLabels.slice(firstActiveIndex),
                values: arrValues.slice(firstActiveIndex),
            };
        }

        function getRangeDaysFromSelection() {
            if (currentRange === 'all') {
                return getAllDaysDefault();
            }
            const numeric = Number(currentRange);
            if (Number.isFinite(numeric) && numeric > 0) {
                return numeric;
            }
            return 30;
        }

        function isDarkTheme() {
            return document.documentElement.getAttribute('data-theme') === 'dark';
        }

        let currentRange = 'all';
        let currentDays = getAllDaysDefault();
        let chartInstance = null;
        let lastGraphPayload = null;
        let lastGraphDays = 0;
        let currentMetric = 'work';
        let graphFocusValue = 'work';
        let maWindow = 14;
        let shouldAutoMAOnNextRender = true;
        let graphSearchQuery = '';
        let graphExcludedIds = new Set();
        let graphTasks = [];
        let graphColorScheme = null;
        let graphSavedSuggestions = [];
        let graphSuggestionActiveIndex = -1;

        const chartTitle = document.getElementById('chartTitle');
        const chartSubtitle = document.getElementById('chartSubtitle');
        const totalHoursEl = document.getElementById('totalHours');
        const avgHoursEl = document.getElementById('avgHours');
        const maxHoursEl = document.getElementById('maxHours');
        const graphFocusBtn = document.getElementById('graphFocusBtn');
        const graphFocusLabel = document.getElementById('graphFocusLabel');
        const graphFocusMenu = document.getElementById('graphFocusMenu');
        const graphSearchInput = document.getElementById('graphSearchInput');
        const graphSearchSuggestions = document.getElementById('graphSearchSuggestions');
        const graphSearchApply = document.getElementById('graphSearchApply');
        const graphSearchClear = document.getElementById('graphSearchClear');
        const reviewGraphTasks = document.getElementById('reviewGraphTasks');
        const graphHelpBtn = document.getElementById('graphHelpBtn');
        const graphHelpTooltip = document.getElementById('graphHelpTooltip');
        const graphHelpWrapper = document.getElementById('graphHelpWrapper');
        const graphTaskModal = document.getElementById('graphTaskModal');
        const graphTasksList = document.getElementById('graphTasksList');
        const graphTaskStats = document.getElementById('graphTaskStats');
        const graphTaskChart = document.getElementById('graphTaskChart');
        const graphTaskTools = document.getElementById('graphTaskTools');
        const closeGraphTasks = document.getElementById('closeGraphTasks');
        const graphExportFormatModal = document.getElementById('graphExportFormatModal');
        const graphCanvasWrap = document.getElementById('graphCanvasWrap');
        const graphPointDetail = document.getElementById('graphPointDetail');
        const graphPointDetailTitle = document.getElementById('graphPointDetailTitle');
        const graphPointDetailBody = document.getElementById('graphPointDetailBody');
        let graphTaskChartInstance = null;
        let graphTaskQuery = '';
        let graphTaskSort = 'time_desc';
        let graphTaskSortLabel = 'Time ↓';
        let graphHiddenTags = {};
        let graphPendingDeleteTaskId = null;
        let graphTaskStatsMode = 'avg';
        let graphTaskConsistencyMode = 'weekly';
        let graphRawDates = [];
        let graphRawValues = [];
        let graphMaValues = [];
        let graphDetailIndex = null;

        function formatHours(value, decimals = 1, suffix = true) {
            const num = Number(value) || 0;
            const formatted = num.toFixed(decimals);
            return suffix ? `${formatted}h` : formatted;
        }

        function getValueScale(values, totals) {
            const allValues = [];
            if (Array.isArray(values)) allValues.push(...values);
            if (Array.isArray(totals)) allValues.push(...totals);
            const maxValue = allValues.length ? Math.max(...allValues.map(v => Number(v) || 0), 0) : 0;
            return maxValue > 0 && maxValue < 1 ? 'minutes' : 'hours';
        }

        function updateRecentAverage(values, rangeAvg, scale, labels) {
            const avgEl = document.getElementById('recentAvgHours');
            const deltaEl = document.getElementById('recentAvgDelta');
            if (!avgEl || !deltaEl) return;
            const series = Array.isArray(values) ? values.map(v => Number(v) || 0) : [];
            const recent = series.slice(-7);
            if (!recent.length) {
                avgEl.textContent = formatGraphValue(0, scale, 1);
                deltaEl.innerHTML = '&nbsp;';
                return;
            }
            const recentAvg = recent.reduce((a, b) => a + b, 0) / recent.length;
            avgEl.textContent = `${formatGraphValue(recentAvg, scale, 1)}/day`;
            if (recentAvg === 0 && series.length > 7) {
                // Nothing in the window: "▼ x vs avg" would read like a slump, so say when it last happened.
                let lastIdx = -1;
                for (let i = series.length - 1; i >= 0; i--) { if (series[i] > 0) { lastIdx = i; break; } }
                const lastLabel = lastIdx >= 0 && Array.isArray(labels) ? labels[lastIdx] : null;
                const lastDate = lastLabel ? new Date(`${lastLabel}T00:00:00`) : null;
                deltaEl.textContent = lastDate && !Number.isNaN(lastDate.getTime())
                    ? `none since ${lastDate.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}`
                    : 'none logged';
                deltaEl.className = 'text-[11px] mt-0.5 text-gray-500';
                return;
            }
            const delta = recentAvg - (Number(rangeAvg) || 0);
            if (series.length <= 7 || Math.abs(delta) < 0.05) {
                deltaEl.textContent = series.length <= 7 ? 'whole range' : 'same as average';
                deltaEl.className = 'text-[11px] mt-0.5 text-gray-500';
                return;
            }
            deltaEl.textContent = `${delta > 0 ? '▲' : '▼'} ${formatGraphValue(Math.abs(delta), scale, 1)} vs avg`;
            // Colour by whether the move is good for this focus (more Work is good, more Waste isn't).
            const lowerIsBetter = ['waste', 'q3', 'q4', 'urgent'].includes(currentMetric);
            const neutral = ['total', 'necessity', 'rest', 'q1', 'sleep'].includes(currentMetric) || graphFocusValue === 'search_only';
            const good = lowerIsBetter ? delta < 0 : delta > 0;
            deltaEl.className = 'text-[11px] mt-0.5 font-medium ' + (neutral ? 'text-gray-600' : (good ? 'text-emerald-700' : 'text-rose-700'));
        }

        // Average per weekday over the plotted days: shows which days the focus actually happens on.
        function updateWeekdayPattern(labels, values, scale) {
            const wrap = document.getElementById('weekdayBars');
            const caption = document.getElementById('weekdayCaption');
            if (!wrap) return;
            const names = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
            const sums = new Array(7).fill(0);
            const counts = new Array(7).fill(0);
            (Array.isArray(labels) ? labels : []).forEach((label, i) => {
                const d = parseIsoDate(label);
                if (!d) return;
                sums[d.getDay()] += Number(values?.[i]) || 0;
                counts[d.getDay()] += 1;
            });
            const avgs = sums.map((sum, i) => (counts[i] ? sum / counts[i] : 0));
            const max = Math.max(...avgs, 0);
            const best = max > 0 ? avgs.indexOf(max) : -1;
            const color = (graphColorScheme && graphColorScheme.primary) || metricColors[currentMetric] || '#111827';
            wrap.innerHTML = names.map((name, i) => {
                const pct = max > 0 ? Math.max(3, Math.round((avgs[i] / max) * 100)) : 3;
                const value = formatGraphValue(avgs[i], scale, 1);
                const isBest = i === best;
                return `<div class="flex flex-col items-center gap-1.5 min-w-0" role="listitem" aria-label="${name}: ${value} per day">
                    <span class="text-[10px] md:text-xs tabular-nums ${isBest ? 'font-semibold text-gray-900' : 'text-gray-500'}">${value}</span>
                    <div class="w-full h-20 md:h-24 rounded-lg bg-[rgba(148,126,86,0.10)] flex items-end overflow-hidden">
                        <div class="w-full rounded-lg" style="height:${pct}%;background:${color};opacity:${isBest ? 1 : 0.45}"></div>
                    </div>
                    <span class="text-[10px] md:text-xs ${isBest ? 'font-semibold text-gray-900' : 'text-gray-500'}">${name}</span>
                </div>`;
            }).join('');
            if (caption) {
                caption.textContent = best >= 0
                    ? `Average per day · most on ${names[best]}`
                    : 'Nothing logged in this range';
            }
        }

        // Average minutes per day in each hour of the day (server 'by_hour'): when the focus happens.
        function hourLabel(hour) {
            const h = ((hour % 24) + 24) % 24;
            return `${h % 12 === 0 ? 12 : h % 12} ${h < 12 ? 'AM' : 'PM'}`;
        }

        // '2–3 PM', '11 AM–12 PM'
        function hourRange(hour) {
            const [from, fromHalf] = hourLabel(hour).split(' ');
            const to = hourLabel(hour + 1);
            return to.endsWith(fromHalf) ? `${from}–${to}` : `${hourLabel(hour)}–${to}`;
        }

        function updateHourPattern(byHour) {
            const wrap = document.getElementById('hourBars');
            const caption = document.getElementById('hourCaption');
            if (!wrap) return;
            const minutes = Array.from({ length: 24 }, (_, i) => Number(byHour?.[i]) || 0);
            const max = Math.max(...minutes, 0);
            const best = max > 0 ? minutes.indexOf(max) : -1;
            const color = (graphColorScheme && graphColorScheme.primary) || metricColors[currentMetric] || '#111827';
            wrap.innerHTML = minutes.map((value, hour) => {
                const pct = max > 0 ? Math.max(2, Math.round((value / max) * 100)) : 2;
                const isBest = hour === best;
                const text = `${hourLabel(hour)}: ${formatGraphValue(value / 60, 'minutes')} per day`;
                return `<div class="h-full flex items-end min-w-0" role="listitem" aria-label="${text}" title="${text}">
                    <div class="w-full rounded-sm md:rounded" style="height:${pct}%;background:${color};opacity:${isBest ? 1 : (value > 0 ? 0.45 : 0.15)}"></div>
                </div>`;
            }).join('');
            if (caption) {
                caption.textContent = '';
                if (best >= 0) {
                    // Phones: just 'Peak 2–3 PM' so the header stays on one line.
                    const lead = document.createElement('span');
                    lead.className = 'hidden sm:inline';
                    lead.textContent = 'Average per day · peak ';
                    const short = document.createElement('span');
                    short.className = 'sm:hidden';
                    short.textContent = 'Peak ';
                    caption.append(lead, short, document.createTextNode(hourRange(best)));
                } else {
                    caption.textContent = 'Nothing logged in this range';
                }
            }
        }

        // GitHub-style calendar of the plotted days (last 53 weeks; 26 on phones).
        // Cells are plain spans: one summary label for screen readers, click opens the day.
        let calendarLast = null;
        let graphNotes = {};  // 'YYYY-MM-DD' -> the user's day note (from graph-data)
        function isoDay(d) {
            return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
        }

        function updateCalendarHeatmap(labels, values, scale) {
            calendarLast = [labels, values, scale];
            const card = document.getElementById('calendarCard');
            const grid = document.getElementById('calendarGrid');
            const monthsRow = document.getElementById('calendarMonths');
            const caption = document.getElementById('calendarCaption');
            if (!card || !grid) return;
            const byDay = new Map();
            (Array.isArray(labels) ? labels : []).forEach((label, i) => {
                const d = parseIsoDate(label);
                if (d) byDay.set(isoDay(d), Math.max(0, Number(values?.[i]) || 0));
            });
            const keys = [...byDay.keys()].sort();
            if (keys.length < 28) {
                card.classList.add('hidden');
                return;
            }
            card.classList.remove('hidden');
            const weeks = isGraphMobile() ? 26 : 53;
            const first = parseIsoDate(keys[0]);
            const last = parseIsoDate(keys[keys.length - 1]);
            const start = new Date(last.getFullYear(), last.getMonth(), last.getDate() - last.getDay() - (weeks - 1) * 7);
            const firstSunday = new Date(first.getFullYear(), first.getMonth(), first.getDate() - first.getDay());
            const from = start < firstSunday ? firstSunday : start;
            const shown = [];
            for (let d = new Date(from); d <= last; d = new Date(d.getFullYear(), d.getMonth(), d.getDate() + 1)) {
                shown.push(d);
            }
            const columns = Math.ceil(shown.length / 7) || 1;
            const shownValues = shown.map(d => byDay.get(isoDay(d)) || 0);
            const max = Math.max(...shownValues, 0);
            const level = (v) => (v <= 0 || max <= 0 ? 0 : Math.min(4, Math.ceil((v / max) * 4)));
            const color = (graphColorScheme && graphColorScheme.primary) || metricColors[currentMetric] || '#111827';
            card.style.setProperty('--calendar-color', color);
            // Cells stay small squares (max 18px) when only a few weeks are shown.
            grid.style.gridTemplateColumns = `repeat(${columns}, minmax(0, 18px))`;
            monthsRow.style.gridTemplateColumns = grid.style.gridTemplateColumns;
            const fmt = { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' };
            grid.innerHTML = shown.map((d, i) => {
                const key = isoDay(d);
                const inRange = byDay.has(key);
                const note = inRange && graphNotes[key] ? String(graphNotes[key]) : '';
                const noteText = note ? ` · “${note.length > 80 ? note.slice(0, 79) + '…' : note}”` : '';
                const text = escapeSuggestionHtml(`${d.toLocaleDateString(undefined, fmt)}: ${inRange ? formatGraphValue(shownValues[i], scale, 1) : 'outside range'}${noteText}`);
                return `<span class="calendar-cell${inRange ? '' : ' is-out'}${note ? ' has-note' : ''}" data-level="${inRange ? level(shownValues[i]) : 0}" data-day="${inRange ? key : ''}" title="${text}" style="grid-row:${(i % 7) + 1};grid-column:${Math.floor(i / 7) + 1}"></span>`;
            }).join('');
            // Month names above the first column that starts in a new month.
            let lastMonth = -1;
            monthsRow.innerHTML = Array.from({ length: columns }, (_, c) => {
                const d = shown[c * 7];
                if (!d || d.getMonth() === lastMonth) return '<span></span>';
                const label = c === 0 && d.getDate() > 14 ? '' : d.toLocaleDateString(undefined, { month: 'short' });
                lastMonth = d.getMonth();
                return `<span class="whitespace-nowrap overflow-visible">${label}</span>`;
            }).join('');
            // Summary: active days and longest run of active days in what's drawn.
            let active = 0, run = 0, best = 0, counted = 0;
            shown.forEach((d, i) => {
                if (!byDay.has(isoDay(d))) return;
                counted += 1;
                if (shownValues[i] > 0) { active += 1; run += 1; best = Math.max(best, run); } else { run = 0; }
            });
            const summary = active
                ? `${active} of ${counted} days active · longest run ${best} day${best === 1 ? '' : 's'}`
                : 'Nothing logged in this range';
            if (caption) caption.textContent = summary;
            grid.setAttribute('aria-label', `Calendar of ${counted} days: ${summary}`);
        }

        (function wireCalendarHeatmap() {
            const grid = document.getElementById('calendarGrid');
            if (grid) {
                // Touch has no hover tooltip: the first tap shows the day in the caption,
                // a second tap on the same day opens it. Mouse clicks open straight away.
                let lastPointer = 'mouse';
                let armed = null;
                grid.addEventListener('pointerdown', (event) => { lastPointer = event.pointerType || 'mouse'; });
                grid.addEventListener('click', (event) => {
                    const cell = event.target.closest('.calendar-cell[data-day]');
                    if (!cell || !cell.dataset.day) return;
                    if (lastPointer === 'touch' && armed !== cell) {
                        if (armed) armed.classList.remove('is-armed');
                        armed = cell;
                        cell.classList.add('is-armed');
                        const caption = document.getElementById('calendarCaption');
                        if (caption) caption.textContent = `${cell.title} · tap again to open`;
                        return;
                    }
                    window.location.href = `${GRAPHS_CONFIG.dashboardUrl}?date=${cell.dataset.day}&period=day`;
                });
            }
            const mq = window.matchMedia('(max-width: 767px)');
            const rerender = () => { if (calendarLast) updateCalendarHeatmap(...calendarLast); };
            if (mq.addEventListener) mq.addEventListener('change', rerender);
        })();

        function formatGraphValue(value, scale, decimals = 1) {
            const num = Number(value) || 0;
            if (scale === 'minutes') {
                return `${Math.round(num * 60)}m`;
            }
            return formatHours(num, decimals);
        }

        function isGraphMobile() {
            return window.matchMedia('(max-width: 767px)').matches;
        }

        function formatGraphDetailDate(dateStr) {
            const raw = String(dateStr || '').trim();
            if (!raw) return '';
            const date = new Date(`${raw}T00:00:00`);
            if (Number.isNaN(date.getTime())) return raw;
            return date.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' });
        }

        function navigateToGraphDate(dateStr) {
            const raw = String(dateStr || '').trim();
            if (!raw) return;
            window.location.href = `/?date=${encodeURIComponent(raw)}&period=day`;
        }

        function closeGraphPointDetail() {
            if (!graphPointDetail) return;
            graphPointDetail.classList.add('hidden');
            graphPointDetail.style.left = '';
            graphPointDetail.style.top = '';
            graphPointDetail.dataset.date = '';
            graphDetailIndex = null;
        }

        function showGraphPointDetail(chart, pointIndex, activePoint) {
            if (!graphPointDetail || !graphCanvasWrap) return;
            const dateStr = graphRawDates[pointIndex];
            if (!dateStr) return;
            const actual = graphRawValues[pointIndex];
            const ma = graphMaValues[pointIndex];
            const scale = getValueScale(graphRawValues, graphMaValues);
            if (graphPointDetailTitle) graphPointDetailTitle.textContent = formatGraphDetailDate(dateStr);
            if (graphPointDetailBody) {
                graphPointDetailBody.textContent = `Day: ${formatGraphValue(actual, scale, 2)} · MA (${maWindow}d): ${formatGraphValue(ma, scale, 2)}`;
            }
            graphPointDetail.dataset.date = dateStr;
            graphDetailIndex = pointIndex;

            const element = activePoint?.element || null;
            const position = element && typeof element.tooltipPosition === 'function'
                ? element.tooltipPosition()
                : null;
            const wrapRect = graphCanvasWrap.getBoundingClientRect();
            const canvasRect = chart?.canvas?.getBoundingClientRect?.();
            const offsetLeft = (canvasRect ? canvasRect.left : wrapRect.left) - wrapRect.left;
            const offsetTop = (canvasRect ? canvasRect.top : wrapRect.top) - wrapRect.top;
            const anchorX = position ? position.x + offsetLeft : wrapRect.width / 2;
            const anchorY = position ? position.y + offsetTop : wrapRect.height / 2;

            graphPointDetail.classList.remove('hidden');
            const boxRect = graphPointDetail.getBoundingClientRect();
            const boxWidth = boxRect.width || 260;
            const boxHeight = boxRect.height || 90;

            const padding = 12;
            let left = anchorX - boxWidth / 2;
            let top = anchorY - boxHeight - 14;
            left = Math.max(padding, Math.min(left, wrapRect.width - boxWidth - padding));
            top = Math.max(padding, Math.min(top, wrapRect.height - boxHeight - padding));

            graphPointDetail.style.left = `${left}px`;
            graphPointDetail.style.top = `${top}px`;
        }

        const parseColor = (value) => {
            if (!value) return null;
            const raw = String(value).trim();
            const hex = raw.match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/i);
            if (hex) {
                const hexValue = hex[1];
                const full = hexValue.length === 3
                    ? hexValue.split('').map(c => c + c).join('')
                    : hexValue;
                const intVal = parseInt(full, 16);
                return [(intVal >> 16) & 255, (intVal >> 8) & 255, intVal & 255];
            }
            const rgb = raw.match(/^rgba?\((\d+),\s*(\d+),\s*(\d+)/i);
            if (rgb) return [Number(rgb[1]), Number(rgb[2]), Number(rgb[3])];
            return null;
        };

        const getContrastColor = (value, darkColor, lightColor) => {
            const rgb = parseColor(value);
            if (!rgb) return darkColor;
            const [r, g, b] = rgb;
            const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
            return luminance > 0.62 ? darkColor : lightColor;
        };

        const percentLabelPlugin = {
            id: 'percentLabelPlugin',
            afterDraw(chart, args, pluginOptions) {
                if (!pluginOptions || pluginOptions.display === false) return;
                const dataset = chart.data.datasets[0];
                if (!dataset) return;
                const data = dataset.data || [];
                const total = data.reduce((sum, v, idx) => {
                    const visible = typeof chart.getDataVisibility === 'function'
                        ? chart.getDataVisibility(idx) !== false
                        : true;
                    return visible ? sum + (Number(v) || 0) : sum;
                }, 0);
                if (!total) return;
                const ctx = chart.ctx;
                const fontSize = pluginOptions.fontSize || 11;
                const fontFamily = pluginOptions.fontFamily || 'Inter';
                const fontWeight = pluginOptions.fontWeight || '600';
                const minPercent = typeof pluginOptions.minPercent === 'number'
                    ? pluginOptions.minPercent
                    : 0;
                const precision = Number.isFinite(pluginOptions.precision)
                    ? pluginOptions.precision
                    : 0;
                ctx.save();
                ctx.font = `${fontWeight} ${fontSize}px ${fontFamily}`;
                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';
                const meta = chart.getDatasetMeta(0);
                const darkColor = pluginOptions.color || '#111827';
                const lightColor = pluginOptions.lightColor || '#FFFFFF';
                const useAutoColor = pluginOptions.autoColor === true;
                const shadowEnabled = pluginOptions.shadow !== false;
                meta.data.forEach((element, idx) => {
                    if (!element) return;
                    if (typeof chart.getDataVisibility === 'function' && !chart.getDataVisibility(idx)) return;
                    const value = Number(data[idx] || 0);
                    if (!value) return;
                    const percent = (value / total) * 100;
                    if (percent < minPercent) return;
                    const position = element.tooltipPosition();
                    const bgColor = Array.isArray(dataset.backgroundColor)
                        ? dataset.backgroundColor[idx]
                        : dataset.backgroundColor;
                    ctx.fillStyle = useAutoColor
                        ? getContrastColor(bgColor, darkColor, lightColor)
                        : darkColor;
                    if (shadowEnabled) {
                        ctx.shadowColor = 'rgba(15, 23, 42, 0.35)';
                        ctx.shadowBlur = 6;
                        ctx.shadowOffsetY = 2;
                    }
                    ctx.fillText(`${percent.toFixed(precision)}%`, position.x, position.y);
                    ctx.shadowColor = 'transparent';
                });
                ctx.restore();
            }
        };

        const currentProjectionPlugin = {
            id: 'currentProjectionPlugin',
            afterDatasetsDraw(chart) {
                const projection = chart && chart.$currentProjection;
                if (!projection || !Number.isFinite(Number(projection.value))) return;
                const yScale = chart.scales && chart.scales.y;
                const area = chart.chartArea;
                if (!yScale || !area) return;
                const y = yScale.getPixelForValue(Number(projection.value));
                if (!Number.isFinite(y) || y < area.top - 2 || y > area.bottom + 2) return;

                const datasetIndex = Number.isInteger(projection.datasetIndex) ? projection.datasetIndex : 0;
                const pointIndex = Number.isInteger(projection.pointIndex) ? projection.pointIndex : null;
                let xTo = area.right;
                const meta = typeof chart.getDatasetMeta === 'function' ? chart.getDatasetMeta(datasetIndex) : null;
                const point = (meta && Array.isArray(meta.data) && pointIndex !== null) ? meta.data[pointIndex] : null;
                if (point && Number.isFinite(point.x)) {
                    xTo = point.x;
                }
                xTo = Math.max(area.left + 2, Math.min(area.right, xTo));

                const ctx = chart.ctx;
                ctx.save();
                ctx.strokeStyle = projection.lineColor || 'rgba(148,126,86,0.45)';
                ctx.lineWidth = Number(projection.lineWidth) || 1.3;
                ctx.setLineDash(Array.isArray(projection.dash) ? projection.dash : [4, 5]);
                ctx.beginPath();
                ctx.moveTo(area.left, y);
                ctx.lineTo(xTo, y);
                ctx.stroke();
                ctx.setLineDash([]);

                const labelText = String(projection.label || '').trim();
                if (labelText) {
                    const tickPadding = Number(yScale.options && yScale.options.ticks && yScale.options.ticks.padding) || 10;
                    ctx.font = projection.font || '600 11px Inter, sans-serif';
                    const boxPaddingX = 7;
                    const boxHeight = 18;
                    const boxWidth = ctx.measureText(labelText).width + (boxPaddingX * 2);
                    const boxRight = area.left - tickPadding - 8;
                    const boxX = Math.max(4, boxRight - boxWidth);
                    const boxY = Math.min(area.bottom - boxHeight, Math.max(area.top, y - (boxHeight / 2)));

                    if (typeof ctx.roundRect === 'function') {
                        ctx.beginPath();
                        ctx.roundRect(boxX, boxY, boxWidth, boxHeight, 9);
                    } else {
                        ctx.beginPath();
                        ctx.moveTo(boxX + 9, boxY);
                        ctx.lineTo(boxX + boxWidth - 9, boxY);
                        ctx.quadraticCurveTo(boxX + boxWidth, boxY, boxX + boxWidth, boxY + 9);
                        ctx.lineTo(boxX + boxWidth, boxY + boxHeight - 9);
                        ctx.quadraticCurveTo(boxX + boxWidth, boxY + boxHeight, boxX + boxWidth - 9, boxY + boxHeight);
                        ctx.lineTo(boxX + 9, boxY + boxHeight);
                        ctx.quadraticCurveTo(boxX, boxY + boxHeight, boxX, boxY + boxHeight - 9);
                        ctx.lineTo(boxX, boxY + 9);
                        ctx.quadraticCurveTo(boxX, boxY, boxX + 9, boxY);
                    }
                    ctx.fillStyle = projection.labelBackground || 'rgba(255, 253, 248, 0.95)';
                    ctx.fill();
                    if (projection.labelBorder) {
                        ctx.strokeStyle = projection.labelBorder;
                        ctx.lineWidth = 1;
                        ctx.stroke();
                    }

                    ctx.fillStyle = projection.labelColor || '#5A4A2D';
                    ctx.textAlign = 'left';
                    ctx.textBaseline = 'middle';
                    ctx.fillText(labelText, boxX + boxPaddingX, boxY + (boxHeight / 2));
                }
                ctx.restore();
            }
        };

        function hoursToHuman(h) {
            const total = Math.max(0, Math.round(Number(h || 0) * 60));
            const hrs = Math.floor(total / 60);
            const mins = total % 60;
            if (hrs === 0) return `${mins} min`;
            if (mins === 0) return `${hrs} hr`;
            if (mins === 30) return `${hrs}.5 hr`;
            return `${hrs} hr ${mins} min`;
        }

        function attachHoverSwap() {
            document.querySelectorAll('.js-hover-hours').forEach(el => {
                if (el.__hoverBound) return;
                const raw = el.getAttribute('data-hours') || el.textContent;
                const h = Number(raw);
                if (isNaN(h)) return;
                const decimalText = formatHours(h, 1);
                const humanText = hoursToHuman(h);
                el.classList.add('hover-swap', 'cursor-default');
                el.addEventListener('mouseenter', () => {
                    el.style.opacity = '0';
                    el.style.transform = 'scale(0.98)';
                    setTimeout(() => {
                        el.textContent = humanText;
                        el.style.opacity = '1';
                        el.style.transform = 'scale(1)';
                    }, 100);
                });
                el.addEventListener('mouseleave', () => {
                    el.style.opacity = '0';
                    el.style.transform = 'scale(0.98)';
                    setTimeout(() => {
                        el.textContent = decimalText;
                        el.style.opacity = '1';
                        el.style.transform = 'scale(1)';
                    }, 100);
                });
                el.__hoverBound = true;
            });
        }

        function getNetworkErrorMessage(error, action) {
            const raw = String(error?.message || '').trim();
            const lower = raw.toLowerCase();
            // 'HTTP 404' and 'HTTP error! status: 404' are both thrown in this page.
            const status = (lower.match(/\b(?:http|status)\D{0,12}(\d{3})\b/) || [])[1] || '';
            if (lower.includes('failed to fetch') || lower.includes('network') || lower.includes('load failed')) {
                return `Network error: Unable to ${action}. Check your internet connection and refresh the page.`;
            }
            if (status === '401' || lower.includes('unauthorized')) {
                return 'Session expired. Please log in again to continue.';
            }
            if (status === '403') {
                return 'Access denied. Verify your account permissions or contact support.';
            }
            if (status === '404') {
                return /\btask\b/.test(action)
                    ? `Task not found. It may have been deleted. Try syncing or refreshing the page.`
                    : `Couldn't ${action} (not found). Refresh the page and try again.`;
            }
            if (status.startsWith('5') || lower.includes('server error')) {
                return `Server error while trying to ${action}. Wait a moment and try again.`;
            }
            if (lower.includes('timeout')) {
                return `Request timed out. Check your connection and try again.`;
            }
            return raw ? `Failed to ${action}: ${raw}` : `Unable to ${action}. Refresh the page and try again.`;
        }

        let lastGraphModalFocus = null;
        function getFocusableElements(container) {
            if (!container) return [];
            return Array.from(
                container.querySelectorAll(
                    'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'
                )
            ).filter(el => el.offsetParent !== null);
        }

        function focusModal(modal) {
            lastGraphModalFocus = document.activeElement;
            const focusable = getFocusableElements(modal);
            if (focusable.length) {
                focusable[0].focus();
            }
        }

        function trapModalFocus(modal, event) {
            const focusable = getFocusableElements(modal);
            if (!focusable.length) return;
            const first = focusable[0];
            const last = focusable[focusable.length - 1];
            if (event.shiftKey && document.activeElement === first) {
                event.preventDefault();
                last.focus();
            } else if (!event.shiftKey && document.activeElement === last) {
                event.preventDefault();
                first.focus();
            }
        }

        function normalizeGraphTaskName(value) {
            // "Instagram ." and "Instagram" are the same activity (stray sheet punctuation).
            const raw = String(value || '').replace(/[\s.,;:]+$/, '').trim();
            if (!raw || /^(undefined|null|none|nan)$/i.test(raw)) {
                return 'Untitled';
            }
            return raw;
        }

        function normalizeGraphTaskKey(value) {
            return normalizeGraphTaskName(value).toLowerCase();
        }

        function parseGraphTaskTime(value) {
            const raw = String(value || '').trim();
            if (!raw) return '00:00:00';
            const match = raw.match(/^(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(am|pm)?$/i);
            if (!match) return raw;
            let hours = Number(match[1]);
            const minutes = Number(match[2]);
            const seconds = Number(match[3] || 0);
            const meridian = (match[4] || '').toLowerCase();
            if (meridian === 'pm' && hours < 12) hours += 12;
            if (meridian === 'am' && hours === 12) hours = 0;
            return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
        }

        function graphTimeToMinutes(value) {
            const parsed = parseGraphTaskTime(value);
            const match = String(parsed || '').match(/^(\d{2}):(\d{2})/);
            if (!match) return null;
            return (Number(match[1]) * 60) + Number(match[2]);
        }

        function formatGraphTaskDateTime(dateStr, timeStr) {
            const date = String(dateStr || '').trim();
            const parsed = parseGraphTaskTime(timeStr);
            const match = String(parsed || '').match(/^(\d{2}):(\d{2})/);
            const hhmm = match ? `${match[1]}:${match[2]}` : String(timeStr || '').trim();
            return date && hhmm ? `${date} ${hhmm}` : '';
        }

        function getGraphTaskTimestamp(task) {
            const date = String(task.date || '').trim();
            if (!date) return 0;
            const time = parseGraphTaskTime(task.start_time);
            const stamp = Date.parse(`${date}T${time}`);
            return Number.isNaN(stamp) ? 0 : stamp;
        }

        function getGraphTaskNeighbors(task) {
            if (!task) return { prev: null, next: null };
            const date = String(task.date || '').trim();
            if (!date) return { prev: null, next: null };
            const dayTasks = graphTasks.filter(t => String(t.date || '').trim() === date);
            const sorted = dayTasks.slice().sort((a, b) => {
                const aStart = graphTimeToMinutes(a.start_time);
                const bStart = graphTimeToMinutes(b.start_time);
                if (aStart == null && bStart == null) return 0;
                if (aStart == null) return 1;
                if (bStart == null) return -1;
                if (aStart !== bStart) return aStart - bStart;
                const aId = Number(a.sheety_id || a.id || 0);
                const bId = Number(b.sheety_id || b.id || 0);
                return aId - bId;
            });
            const targetId = Number(task.sheety_id || task.id || 0);
            let idx = sorted.findIndex(t => Number(t.sheety_id || t.id || 0) === targetId);
            if (idx < 0) {
                const startMin = graphTimeToMinutes(task.start_time);
                if (startMin != null) {
                    idx = sorted.findIndex(t => graphTimeToMinutes(t.start_time) === startMin);
                }
            }
            return {
                prev: idx > 0 ? sorted[idx - 1] : null,
                next: idx >= 0 && idx < sorted.length - 1 ? sorted[idx + 1] : null
            };
        }

        const GRAPH_QUERY_TOKEN_RE = /"[^"]*"|'[^']*'|\(|\)|,|\+|\-|\*|\bAND\b|\bOR\b|\bNOT\b|[^\s()+*\-,]+/gi;

        function tokenizeGraphQuery(raw) {
            const cleaned = String(raw || '').trim();
            if (!cleaned) return [];
            const matches = cleaned.match(GRAPH_QUERY_TOKEN_RE) || [];
            const tokens = [];
            matches.forEach(match => {
                const token = String(match || '').trim();
                if (!token) return;
                if (token === ',') {
                    tokens.push({ type: 'OR' });
                    return;
                }
                if (token === '+') {
                    tokens.push({ type: 'OR' });
                    return;
                }
                if (token === '*') {
                    tokens.push({ type: 'AND' });
                    return;
                }
                if (token === '-') {
                    tokens.push({ type: 'MINUS' });
                    return;
                }
                if (token === '(' || token === ')') {
                    tokens.push({ type: token });
                    return;
                }
                const upper = token.toUpperCase();
                if (upper === 'AND' || upper === 'OR' || upper === 'NOT' || upper === 'ONLY') {
                    tokens.push({ type: upper });
                    return;
                }
                let term = token;
                if ((term.startsWith('"') && term.endsWith('"')) || (term.startsWith("'") && term.endsWith("'"))) {
                    term = term.slice(1, -1);
                }
                term = term.trim().toLowerCase();
                if (term) {
                    tokens.push({ type: 'TERM', value: term });
                }
            });
            return tokens;
        }

        function parseGraphTaskQuery(raw) {
            const tokens = tokenizeGraphQuery(raw);
            if (!tokens.length) return null;
            let index = 0;

            const peek = () => tokens[index];
            const consume = () => tokens[index++];

            const parsePrimary = () => {
                const token = peek();
                if (!token) return null;
                if (token.type === 'TERM') {
                    consume();
                    return { type: 'term', value: token.value };
                }
                if (token.type === 'ONLY') {
                    consume();
                    const next = parsePrimary();
                    if (next && next.type === 'term') {
                        return { type: 'only', value: next.value };
                    }
                    return next;
                }
                if (token.type === '(') {
                    consume();
                    const expr = parseOr();
                    if (peek() && peek().type === ')') consume();
                    return expr;
                }
                return null;
            };

            const parseNot = () => {
                const token = peek();
                if (token && (token.type === 'NOT' || token.type === 'MINUS')) {
                    consume();
                    const expr = parseNot();
                    return expr ? { type: 'not', expr } : null;
                }
                return parsePrimary();
            };

            const parseAnd = () => {
                let left = parseNot();
                if (!left) return null;
                while (true) {
                    const token = peek();
                    if (!token) break;
                    if (token.type === 'AND') {
                        consume();
                        const right = parseNot();
                        if (!right) break;
                        left = { type: 'and', left, right };
                        continue;
                    }
                    if (token.type === 'MINUS') {
                        consume();
                        const right = parseNot();
                        if (!right) break;
                        left = { type: 'and', left, right: { type: 'not', expr: right } };
                        continue;
                    }
                    if (token.type === 'TERM' || token.type === '(' || token.type === 'NOT' || token.type === 'ONLY') {
                        const right = parseNot();
                        if (!right) break;
                        left = { type: 'and', left, right };
                        continue;
                    }
                    break;
                }
                return left;
            };

            const parseOr = () => {
                let left = parseAnd();
                if (!left) return null;
                while (true) {
                    const token = peek();
                    if (token && token.type === 'OR') {
                        consume();
                        const right = parseAnd();
                        if (!right) break;
                        left = { type: 'or', left, right };
                        continue;
                    }
                    break;
                }
                return left;
            };

            return parseOr();
        }

        function normalizeGraphValue(value) {
            return String(value || '').toLowerCase().replace(/\s+/g, ' ').trim();
        }

        function splitGraphTokens(value) {
            const clean = normalizeGraphValue(value);
            if (!clean) return [];
            return clean.split(/[^a-z0-9]+/).filter(Boolean);
        }

        function hasTokenSequence(tokens, sequence) {
            if (!tokens.length || !sequence.length || sequence.length > tokens.length) return false;
            for (let i = 0; i <= tokens.length - sequence.length; i += 1) {
                let match = true;
                for (let j = 0; j < sequence.length; j += 1) {
                    if (tokens[i + j] !== sequence[j]) {
                        match = false;
                        break;
                    }
                }
                if (match) return true;
            }
            return false;
        }

        function getGraphTaskTagPhrases(task) {
            const raw = String(task.tag || task.raw_tag || '');
            const directTags = raw
                .split(',')
                .map(tag => normalizeGraphValue(tag))
                .filter(Boolean);
            const displayTags = formatTagNames(raw)
                .split(',')
                .map(tag => normalizeGraphValue(tag))
                .filter(Boolean);
            const primaryTag = normalizeTagName(raw);
            const normalizedPrimary = primaryTag ? normalizeGraphValue(primaryTag) : '';
            return Array.from(new Set([...directTags, ...displayTags, normalizedPrimary].filter(Boolean)));
        }

        function graphTaskTermMatches(task, term) {
            const clean = normalizeGraphValue(term);
            if (!clean) return false;
            if (clean === 'urgent') return Boolean(task.urgent);
            if (clean === 'important') return Boolean(task.important);

            const termTokens = splitGraphTokens(clean);
            if (!termTokens.length) return false;

            const tokenGroups = [];
            const taskTokens = splitGraphTokens(task.task);
            if (taskTokens.length) tokenGroups.push(taskTokens);
            const dateTokens = splitGraphTokens(task.date);
            if (dateTokens.length) tokenGroups.push(dateTokens);

            getGraphTaskTagPhrases(task).forEach(tag => {
                const tagTokens = splitGraphTokens(tag);
                if (tagTokens.length) tokenGroups.push(tagTokens);
            });

            if (termTokens.length === 1) {
                const token = termTokens[0];
                return tokenGroups.some(tokens => tokens.includes(token));
            }

            return tokenGroups.some(tokens => hasTokenSequence(tokens, termTokens));
        }

        function graphTaskExactMatch(task, term) {
            const clean = normalizeGraphValue(term);
            if (!clean) return false;
            const taskName = normalizeGraphValue(normalizeGraphTaskName(task.task));
            return taskName === clean;
        }

        function evaluateGraphTaskQuery(expr, task) {
            if (!expr) return true;
            if (expr.type === 'term') return graphTaskTermMatches(task, expr.value);
            if (expr.type === 'only') return graphTaskExactMatch(task, expr.value);
            if (expr.type === 'not') return !evaluateGraphTaskQuery(expr.expr, task);
            if (expr.type === 'and') return evaluateGraphTaskQuery(expr.left, task) && evaluateGraphTaskQuery(expr.right, task);
            if (expr.type === 'or') return evaluateGraphTaskQuery(expr.left, task) || evaluateGraphTaskQuery(expr.right, task);
            return true;
        }

        function graphTaskMatchesQuery(task, expr) {
            if (!expr) return true;
            return evaluateGraphTaskQuery(expr, task);
        }

        function renderGraphTaskStats() {
            const searchExpr = parseGraphTaskQuery(graphTaskQuery);
            const activeTasks = graphTasks.filter(task => {
                if (!graphTaskMatchesQuery(task, searchExpr)) return false;
                return true;
            });
            const totalMinutes = activeTasks.reduce((sum, task) => sum + Number(task.duration_minutes || 0), 0);
            const taskCount = activeTasks.length;
            const avgMinutes = taskCount ? totalMinutes / taskCount : 0;
            const activeDates = new Set(
                activeTasks.map(task => String(task.date || '').trim()).filter(Boolean)
            );
            const activeDays = Math.max(activeDates.size, 1);
            const consistencyDays = activeDates.size;
            const activeDateList = Array.from(activeDates)
                .map(date => Date.parse(`${date}T00:00:00`))
                .filter(Number.isFinite);
            const spanDays = activeDateList.length
                ? Math.round((Math.max(...activeDateList) - Math.min(...activeDateList)) / 86400000) + 1
                : 0;
            const canAverage = activeDays > 1;
            if (!canAverage && graphTaskStatsMode === 'avg') {
                graphTaskStatsMode = 'total';
            }
            const statItem = (value, label, extraClass = '', extraAttrs = '') => `
                <div class="rounded-xl border border-slate-100 bg-white/80 px-3 py-3 text-center ${extraClass}" ${extraAttrs}>
                    <div class="text-xl md:text-2xl font-light text-gray-900">${value}</div>
                    <div class="text-[10px] md:text-xs text-gray-500 mt-1 uppercase tracking-wider">${label}</div>
                </div>
            `;
            const useAverage = graphTaskStatsMode === 'avg' && canAverage;
            const totalHours = totalMinutes / 60;
            const avgDayHours = totalHours / activeDays;
            const avgTaskHours = avgMinutes / 60;
            const totalLabel = useAverage ? 'Avg/day' : 'Total hours';
            const displayHours = useAverage ? avgDayHours : totalHours;
            const perWeek = spanDays ? (consistencyDays / spanDays) * 7 : 0;
            const perWeekRounded = Math.round(perWeek * 10) / 10;
            const perWeekText = Number.isInteger(perWeekRounded)
                ? String(perWeekRounded)
                : perWeekRounded.toFixed(1);
            const consistencyValue = graphTaskConsistencyMode === 'weekly'
                ? `${perWeekText}<span class="text-[10px] md:text-xs text-gray-400 ml-0.5">days/week</span>`
                : `${consistencyDays}<span class="text-[10px] md:text-xs text-gray-400 ml-0.5">/ ${spanDays || 0} days</span>`;
            const consistencyTitle = graphTaskConsistencyMode === 'weekly'
                ? 'Click to show total days'
                : 'Click to show days/week';
            const stats = [
                statItem(
                    consistencyValue,
                    'Consistency',
                    'cursor-pointer',
                    `data-stat="consistency" role="button" tabindex="0" title="${consistencyTitle}"`
                ),
                statItem(
                    `<span class="js-hover-hours hover-swap" data-hours="${displayHours}">${formatHours(displayHours, 1)}</span>`,
                    totalLabel,
                    canAverage ? 'cursor-pointer' : '',
                    `data-stat="hours" ${canAverage ? 'role="button" tabindex="0" title="Click to toggle total/avg"' : ''}`
                ),
                statItem(
                    `<span class="js-hover-hours hover-swap" data-hours="${avgTaskHours}">${formatHours(avgTaskHours, 1)}</span>`,
                    'Avg/task'
                )
            ];
            if (graphTaskStats) {
                graphTaskStats.innerHTML = stats.join('');
                graphTaskStats.dataset.canAverage = canAverage ? '1' : '0';
                if (!graphTaskStats.__toggleBound) {
                    graphTaskStats.addEventListener('click', (event) => {
                        const tile = event.target.closest('[data-stat]');
                        if (!tile) return;
                        const stat = tile.dataset.stat;
                        if (stat === 'hours' && graphTaskStats.dataset.canAverage === '1') {
                            graphTaskStatsMode = graphTaskStatsMode === 'avg' ? 'total' : 'avg';
                            renderGraphTaskStats();
                            renderGraphTaskList();
                            return;
                        }
                        if (stat === 'consistency') {
                            graphTaskConsistencyMode = graphTaskConsistencyMode === 'weekly' ? 'total' : 'weekly';
                            renderGraphTaskStats();
                            renderGraphTaskList();
                        }
                    });
                    graphTaskStats.addEventListener('keydown', (event) => {
                        if (event.key !== 'Enter' && event.key !== ' ') return;
                        const tile = event.target.closest('[data-stat][role="button"]');
                        if (!tile) return;
                        event.preventDefault();
                        const stat = tile.dataset.stat;
                        tile.click();
                        // The tiles were re-rendered: keep focus on the same one.
                        graphTaskStats.querySelector(`[data-stat="${stat}"][role="button"]`)?.focus();
                    });
                    graphTaskStats.__toggleBound = true;
                }
                attachHoverSwap();
            }
        }

        function renderGraphTaskChart() {
            if (!graphTaskChart) return;
            const searchExpr = parseGraphTaskQuery(graphTaskQuery);
            const activeTasks = graphTasks.filter(task => {
                if (!graphTaskMatchesQuery(task, searchExpr)) return false;
                const taskNameNormalized = normalizeGraphTaskKey(task.task);
                for (const hiddenKey in graphHiddenTags) {
                    if (hiddenKey.toLowerCase() === taskNameNormalized) return false;
                }
                return true;
            });
            if (!activeTasks.length) {
                graphTaskChart.innerHTML = '';
                return;
            }
            const taskGroups = {};
            const taskDisplayNames = {};
            activeTasks.forEach(task => {
                const rawKey = normalizeGraphTaskName(task.task);
                const normalizedKey = normalizeGraphTaskKey(task.task);
                const hours = Number(task.duration_hours || 0);
                taskGroups[normalizedKey] = (taskGroups[normalizedKey] || 0) + hours;
                if (!taskDisplayNames[normalizedKey]) {
                    taskDisplayNames[normalizedKey] = rawKey;
                }
            });
            const entries = Object.entries(taskGroups).sort((a, b) => b[1] - a[1]);
            const baseColor = (graphColorScheme && graphColorScheme.primary) || metricColors[currentMetric] || '#111827';
            const accentColor = (graphColorScheme && graphColorScheme.secondary) || null;
            // Neighbouring slices must be distinguishable: the fallback list starts with a green, so a
            // green scheme used to colour the top three slices green. Keep a colour only if its hue is
            // far enough from every colour already picked (greys always pass).
            const hexHue = (hex) => {
                const m = /^#?([0-9a-f]{6})$/i.exec(String(hex || '').trim());
                if (!m) return null;
                const n = parseInt(m[1], 16);
                const r = (n >> 16 & 255) / 255, g = (n >> 8 & 255) / 255, b = (n & 255) / 255;
                const max = Math.max(r, g, b), min = Math.min(r, g, b), d = max - min;
                if (d < 0.08) return null;
                const h = max === r ? ((g - b) / d) % 6 : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
                return (h * 60 + 360) % 360;
            };
            const palette = [];
            [baseColor, accentColor, '#16A34A', '#A16207', '#7C3AED', '#0EA5A4', '#9F1239', '#2563EB', '#F59E0B', '#9CA3AF']
                .filter(Boolean)
                .forEach(color => {
                    const hue = hexHue(color);
                    const clash = hue !== null && palette.some(picked => {
                        const other = hexHue(picked);
                        if (other === null) return false;
                        const diff = Math.abs(hue - other);
                        return Math.min(diff, 360 - diff) < 30;
                    });
                    if (!clash && !palette.includes(color)) palette.push(color);
                });
            const allEntries = entries.map(([key, value]) => ({
                key,
                label: taskDisplayNames[key] || key,
                value: Number(value || 0)
            }));
            const colorMap = {};
            allEntries.forEach((entry, idx) => {
                colorMap[entry.key] = palette[idx % palette.length];
            });

            const getMaxChartSlots = () => window.matchMedia('(max-width: 767px)').matches ? 4 : 6;
            const getExpandedSlots = (entries) => {
                const total = entries.reduce((sum, entry) => sum + entry.value, 0);
                const baseSlots = getMaxChartSlots();
                if (!total) return baseSlots;
                const minOtherShare = 0.02;
                const aboveThreshold = entries.filter(entry => (entry.value / total) >= minOtherShare).length;
                return Math.max(baseSlots, aboveThreshold);
            };
            const buildChartView = () => {
                const visible = allEntries.filter(e => !graphHiddenTags[e.key]);
                const maxSlots = getExpandedSlots(visible);
                const top = visible.slice(0, maxSlots);
                const rest = visible.slice(maxSlots);
                const labels = top.map(e => e.label);
                const values = top.map(e => e.value);
                let otherValue = 0;
                if (rest.length) {
                    otherValue = rest.reduce((sum, e) => sum + e.value, 0);
                    labels.push('Other');
                    values.push(otherValue);
                }
                const colors = labels.map(label => {
                    if (label === 'Other') return '#9CA3AF';
                    const key = top.find(e => e.label === label)?.key || normalizeGraphTaskKey(label);
                    return colorMap[key] || baseColor;
                });
                const keyMap = {};
                top.forEach(e => { keyMap[e.label] = e.key; });
                return { labels, values, colors, keyMap, otherValue };
            };
            const view = buildChartView();
            let labels = view.labels;
            let values = view.values;
            let colors = view.colors;
            let labelToKey = view.keyMap;
            const isModalMobile = window.matchMedia('(max-width: 767px)').matches;
            graphTaskChart.innerHTML = '<div class="relative w-full px-4 md:px-8" style="height: 300px;"><canvas id="graphTaskChartCanvas" class="w-full h-full"></canvas></div><div id="graphTaskMobileLegend" class="mt-6 mb-2 md:hidden flex flex-wrap gap-2 justify-center text-[11px] text-gray-700 px-2"></div><div id="graphTaskDesktopLegend" class="mt-4 hidden md:flex flex-wrap gap-3 justify-center text-[11px] text-gray-700 px-4"></div>';
            const mobileLegendEl = document.getElementById('graphTaskMobileLegend');
            const desktopLegendEl = document.getElementById('graphTaskDesktopLegend');
            const buildLegendItems = () => {
                const view = buildChartView();
                const keyMap = view.keyMap || {};
                const visibleItems = view.labels.map(label => {
                    if (label === 'Other') {
                        return {
                            key: '__other__',
                            label: 'Other',
                            color: '#9CA3AF',
                            hidden: false,
                            disabled: true
                        };
                    }
                    const key = keyMap[label];
                    if (!key) return null;
                    return {
                        key,
                        label,
                        color: colorMap[key] || baseColor,
                        hidden: false,
                        disabled: false
                    };
                }).filter(Boolean);
                const hiddenItems = allEntries
                    .filter(entry => graphHiddenTags[entry.key])
                    .map(entry => ({
                        key: entry.key,
                        label: entry.label,
                        color: colorMap[entry.key] || baseColor,
                        hidden: true,
                        disabled: false
                    }));
                return visibleItems.concat(hiddenItems);
            };
            // Toggleable legend entries are buttons (keyboard + screen readers); 'Other' stays a span.
            const legendTag = (item) => item.disabled
                ? 'span'
                : `button type="button" aria-pressed="${item.hidden ? 'false' : 'true'}" title="${item.hidden ? 'Show' : 'Hide'} ${escapeSuggestionHtml(item.label)}"`;
            const updateMobileLegend = (chart) => {
                if (mobileLegendEl && isModalMobile) {
                    const legendItems = buildLegendItems();
                    mobileLegendEl.innerHTML = legendItems.map(item => {
                        const color = item.color || '#9CA3AF';
                        const isHidden = item.hidden;
                        const textDecoration = isHidden ? 'line-through' : 'none';
                        const opacity = isHidden ? '0.5' : '1';
                        const cursor = item.disabled ? 'cursor-default' : 'cursor-pointer hover:opacity-70';
                        return `<${legendTag(item)} class="inline-flex items-center gap-1 ${cursor} transition-opacity" data-legend-key="${escapeSuggestionHtml(item.key)}" style="opacity:${opacity}">
                            <span class="inline-block w-2.5 h-2.5 rounded-full" style="background:${color}"></span>
                            <span style="text-decoration:${textDecoration}">${escapeSuggestionHtml(item.label)}</span>
                        </${item.disabled ? 'span' : 'button'}>`;
                    }).join('');
                } else if (mobileLegendEl) {
                    mobileLegendEl.innerHTML = '';
                }
            };
            const updateDesktopLegend = (chart) => {
                if (!desktopLegendEl) return;
                if (isModalMobile) {
                    desktopLegendEl.innerHTML = '';
                    return;
                }
                const legendItems = buildLegendItems();
                desktopLegendEl.innerHTML = legendItems.map(item => {
                    const color = item.color || '#9CA3AF';
                    const isHidden = item.hidden;
                    const textDecoration = isHidden ? 'line-through' : 'none';
                    const opacity = isHidden ? '0.5' : '1';
                    const cursor = item.disabled ? 'cursor-default' : 'cursor-pointer hover:opacity-70';
                    return `<${legendTag(item)} class="inline-flex items-center gap-1 ${cursor} transition-opacity" data-legend-key="${escapeSuggestionHtml(item.key)}" style="opacity:${opacity}">
                        <span class="inline-block w-2.5 h-2.5 rounded-full" style="background:${color}"></span>
                        <span style="text-decoration:${textDecoration}" class="max-w-[160px] truncate">${escapeSuggestionHtml(item.label)}</span>
                    </${item.disabled ? 'span' : 'button'}>`;
                }).join('');
            };
            updateMobileLegend(null);
            updateDesktopLegend(null);
            const ctx = document.getElementById('graphTaskChartCanvas').getContext('2d');
            if (graphTaskChartInstance) {
                graphTaskChartInstance.destroy();
            }
            graphTaskChartInstance = new Chart(ctx, {
                type: 'pie',
                data: {
                    labels: labels,
                    datasets: [{
                        data: values,
                        backgroundColor: colors,
                        // A lone slice would show its rim as a seam at 12 o'clock.
                        borderWidth: (c) => (c.chart.data.datasets[0].data.filter(v => Number(v) > 0).length > 1 ? 2 : 0),
                        // Slice gaps take the surface colour (white rims glare in dark mode).
                        borderColor: isDarkTheme() ? '#0E0C08' : '#FFFFFF',
                        hoverOffset: 10,
                        hoverBorderWidth: (c) => (c.chart.data.datasets[0].data.filter(v => Number(v) > 0).length > 1 ? 3 : 0)
                    }]
                },
                plugins: [percentLabelPlugin],
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    spacing: 3,
                    plugins: {
                        percentLabelPlugin: {
                            display: true,
                            fontSize: isModalMobile ? 10 : 11,
                            fontFamily: 'Inter',
                            fontWeight: '600',
                            color: '#111827',
                            lightColor: '#FFFFFF',
                            autoColor: true,
                            shadow: true,
                            minPercent: 3,
                            precision: 0
                        },
                        legend: {
                            display: false
                        },
                        tooltip: {
                            backgroundColor: isDarkTheme() ? 'rgba(22,19,14,0.98)' : 'rgba(17, 24, 39, 0.96)',
                            padding: 14,
                            titleFont: { family: 'Inter', size: 13, weight: '600' },
                            bodyFont: { family: 'Inter', size: 12, weight: '400' },
                            cornerRadius: 10,
                            displayColors: true,
                            boxWidth: 10,
                            boxHeight: 10,
                            boxPadding: 6,
                            callbacks: {
                                label: function(context) {
                                    const raw = context.label;
                                    const label = String(raw ?? '').trim() || 'Unspecified';
                                    const value = Number(context.parsed || 0);
                                    const total = context.dataset.data.reduce((sum, v, idx) => {
                                        const visible = typeof context.chart.getDataVisibility === 'function'
                                            ? context.chart.getDataVisibility(idx) !== false
                                            : true;
                                        return visible ? sum + (Number(v) || 0) : sum;
                                    }, 0);
                                    const percent = total > 0 ? ((value / total) * 100).toFixed(1) : 0;
                                    return `${label}: ${value.toFixed(1)}h (${percent}%)`;
                                }
                            }
                        }
                    },
                    onClick: function(evt, elements) {
                        if (!elements || !elements.length) return;
                        const index = elements[0].index;
                        const label = graphTaskChartInstance.data.labels[index];
                        if (label === 'Other') return;
                        const key = labelToKey[label] || normalizeGraphTaskKey(label);
                        if (graphHiddenTags[key]) delete graphHiddenTags[key];
                        else graphHiddenTags[key] = true;
                        const next = buildChartView();
                        labels = next.labels;
                        values = next.values;
                        colors = next.colors;
                        labelToKey = next.keyMap;
                        graphTaskChartInstance.data.labels = labels;
                        graphTaskChartInstance.data.datasets[0].data = values;
                        graphTaskChartInstance.data.datasets[0].backgroundColor = colors;
                        graphTaskChartInstance.update();
                        updateMobileLegend(graphTaskChartInstance);
                        updateDesktopLegend(graphTaskChartInstance);
                        renderGraphTaskStats();
                        renderGraphTaskList();
                    }
                }
            });
            updateMobileLegend(graphTaskChartInstance);
            updateDesktopLegend(graphTaskChartInstance);
            const legendClickHandler = (event) => {
                const legendItem = event.target.closest('[data-legend-key]');
                if (!legendItem) return;
                const key = legendItem.dataset.legendKey;
                if (!key || key === '__other__') return;
                if (graphHiddenTags[key]) delete graphHiddenTags[key];
                else graphHiddenTags[key] = true;
                const next = buildChartView();
                labels = next.labels;
                values = next.values;
                colors = next.colors;
                labelToKey = next.keyMap;
                graphTaskChartInstance.data.labels = labels;
                graphTaskChartInstance.data.datasets[0].data = values;
                graphTaskChartInstance.data.datasets[0].backgroundColor = colors;
                graphTaskChartInstance.update();
                updateMobileLegend(graphTaskChartInstance);
                updateDesktopLegend(graphTaskChartInstance);
                renderGraphTaskStats();
                renderGraphTaskList();
                // The legend was re-rendered: keep keyboard focus on the entry just toggled.
                const container = event.currentTarget;
                const again = Array.from(container.querySelectorAll('button[data-legend-key]')).find(el => el.dataset.legendKey === key);
                if (again) again.focus();
            };
            if (mobileLegendEl) {
                mobileLegendEl.addEventListener('click', legendClickHandler);
            }
            if (desktopLegendEl) {
                desktopLegendEl.addEventListener('click', legendClickHandler);
            }
        }

        function getVisibleGraphTasks() {
            const searchExpr = parseGraphTaskQuery(graphTaskQuery);
            let filteredTasks = graphTasks.filter(task => {
                if (!graphTaskMatchesQuery(task, searchExpr)) return false;
                const taskNameNormalized = normalizeGraphTaskKey(task.task);
                for (const hiddenKey in graphHiddenTags) {
                    if (hiddenKey.toLowerCase() === taskNameNormalized) return false;
                }
                return true;
            });
            if (!filteredTasks.length) return [];
            const sortKey = graphTaskSort || 'time_desc';
            if (sortKey === 'time_desc') {
                filteredTasks.sort((a, b) => {
                    return getGraphTaskTimestamp(b) - getGraphTaskTimestamp(a);
                });
            } else if (sortKey === 'time_asc') {
                filteredTasks.sort((a, b) => {
                    return getGraphTaskTimestamp(a) - getGraphTaskTimestamp(b);
                });
            } else if (sortKey === 'duration_desc') {
                filteredTasks.sort((a, b) => Number(b.duration_hours || 0) - Number(a.duration_hours || 0));
            } else if (sortKey === 'duration_asc') {
                filteredTasks.sort((a, b) => Number(a.duration_hours || 0) - Number(b.duration_hours || 0));
            } else if (sortKey === 'task_az') {
                filteredTasks.sort((a, b) => normalizeGraphTaskName(a.task).localeCompare(normalizeGraphTaskName(b.task)));
            } else if (sortKey === 'task_za') {
                filteredTasks.sort((a, b) => normalizeGraphTaskName(b.task).localeCompare(normalizeGraphTaskName(a.task)));
            } else if (sortKey === 'imp_desc') {
                filteredTasks.sort((a, b) => Number(Boolean(b.important)) - Number(Boolean(a.important)));
            } else if (sortKey === 'urg_desc') {
                filteredTasks.sort((a, b) => Number(Boolean(b.urgent)) - Number(Boolean(a.urgent)));
            }
            return filteredTasks;
        }

        function toExportCsv(rows, headers) {
            const escape = (value) => {
                let raw = String(value == null ? '' : value);
                // Spreadsheets run text starting with = + - @ as a formula (CSV injection).
                if (typeof value === 'string' && /^[=+\-@\t\r]/.test(raw)) raw = `'${raw}`;
                const escaped = raw.replace(/"/g, '""');
                return /[",\n]/.test(escaped) ? `"${escaped}"` : escaped;
            };
            const lines = [headers.join(',')];
            rows.forEach((row) => {
                lines.push(headers.map((header) => escape(row[header])).join(','));
            });
            return lines.join('\n');
        }

        function showGraphExportFormatPicker() {
            return new Promise((resolve) => {
                if (!graphExportFormatModal) {
                    resolve('csv');
                    return;
                }
                const opener = document.activeElement;
                graphExportFormatModal.classList.remove('hidden');
                graphExportFormatModal.querySelector('[data-export-format]')?.focus();
                // Capture phase: Escape must close the picker, not the task modal underneath it.
                const onKey = (event) => {
                    if (event.key === 'Escape') {
                        event.preventDefault();
                        event.stopImmediatePropagation();
                        close();
                        resolve(null);
                    } else if (event.key === 'Tab') {
                        event.stopImmediatePropagation();
                        const items = Array.from(graphExportFormatModal.querySelectorAll('button'));
                        const first = items[0];
                        const last = items[items.length - 1];
                        if (event.shiftKey && document.activeElement === first) {
                            event.preventDefault();
                            last.focus();
                        } else if (!event.shiftKey && document.activeElement === last) {
                            event.preventDefault();
                            first.focus();
                        }
                    }
                };
                document.addEventListener('keydown', onKey, true);
                const close = () => {
                    document.removeEventListener('keydown', onKey, true);
                    graphExportFormatModal.classList.add('hidden');
                    if (opener && document.body.contains(opener)) opener.focus();
                    graphExportFormatModal.querySelectorAll('[data-export-format]').forEach(btn => {
                        btn.onclick = null;
                    });
                    graphExportFormatModal.querySelectorAll('[data-close-graph-export="true"]').forEach(btn => {
                        btn.onclick = null;
                    });
                };
                graphExportFormatModal.querySelectorAll('[data-export-format]').forEach(btn => {
                    btn.onclick = () => {
                        const format = btn.getAttribute('data-export-format') || 'csv';
                        close();
                        resolve(format);
                    };
                });
                graphExportFormatModal.querySelectorAll('[data-close-graph-export="true"]').forEach(btn => {
                    btn.onclick = () => {
                        close();
                        resolve(null);
                    };
                });
            });
        }

        async function exportGraphModalTasks() {
            const visibleTasks = getVisibleGraphTasks();
            if (!visibleTasks.length) {
                if (window.showWarningToast) {
                    window.showWarningToast('No visible tasks to export');
                }
                return;
            }
            const format = await showGraphExportFormatPicker();
            if (!format) return;
            const headers = ['start date', 'start time', 'end date', 'end time', 'task', 'duration', 'special tags', 'urgent', 'important'];
            const rows = visibleTasks.map(task => ({
                'start date': String(task.date || ''),
                'start time': String(task.start_time || ''),
                'end date': String(task.end_date || task.date || ''),
                'end time': String(task.end_time || ''),
                'task': normalizeGraphTaskName(task.task),
                'duration': Number(task.duration_hours || 0),
                'special tags': String(task.tag || task.raw_tag || ''),
                'urgent': task.urgent ? 'Yes' : 'No',
                'important': task.important ? 'Yes' : 'No',
            }));
            const exportPayload = format === 'json'
                ? JSON.stringify({ columns: headers, rows }, null, 2)
                : toExportCsv(rows, headers);
            const mimeType = format === 'json' ? 'application/json' : 'text/csv';
            const extension = format === 'json' ? 'json' : 'csv';
            const blob = new Blob([exportPayload], { type: mimeType });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `time-tracker-graph-review-${(() => { const n = new Date(); return `${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, '0')}-${String(n.getDate()).padStart(2, '0')}`; })()}.${extension}`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
            if (window.showSuccessToast) {
                window.showSuccessToast('Graph review exported successfully');
            }
        }

        function renderGraphTaskList() {
            if (!graphTasksList) return;
            const filteredTasks = getVisibleGraphTasks();
            if (!filteredTasks.length) {
                graphTasksList.innerHTML = '<div class="text-center py-8 text-gray-400">No tasks found</div>';
                return;
            }
            // Multi-day lists in time order get a header per day instead of a date on every card.
            const groupByDay = new Set(filteredTasks.map(t => t.date)).size > 1
                && String(graphTaskSort || 'time_desc').startsWith('time');
            const dayTotals = {};
            if (groupByDay) {
                filteredTasks.forEach(t => {
                    const key = String(t.date || '');
                    const entry = dayTotals[key] || (dayTotals[key] = { count: 0, hours: 0 });
                    entry.count += 1;
                    entry.hours += Number(t.duration_hours || 0) || 0;
                });
            }
            let lastDay = null;
            const html = filteredTasks.map((task, index) => {
                let dayHeader = '';
                if (groupByDay && String(task.date || '') !== lastDay) {
                    lastDay = String(task.date || '');
                    const totals = dayTotals[lastDay] || { count: 0, hours: 0 };
                    dayHeader = `
                        <div class="flex items-baseline justify-between gap-3 px-1 ${index ? 'pt-4' : 'pt-1'} pb-2">
                            <h4 class="text-xs font-semibold uppercase tracking-[0.14em] text-gray-600" title="${escapeSuggestionHtml(lastDay)}">${escapeSuggestionHtml(friendlyTaskDate(lastDay))}</h4>
                            <span class="text-xs text-gray-500 tabular-nums">${totals.count} ${totals.count === 1 ? 'task' : 'tasks'} · ${hoursToHuman(totals.hours)}</span>
                        </div>${graphNotes[lastDay] ? `
                        <p class="px-1 pb-2 -mt-1 text-xs text-gray-600 italic whitespace-pre-line">“${escapeSuggestionHtml(graphNotes[lastDay])}”</p>` : ''}`;
                }
                const dur = Number(task.duration_hours || 0);
                const durText = hoursToHuman(dur);
                const badges = [];
                if (task.important) badges.push('<span class="px-2 py-1 bg-emerald-50 text-emerald-700 text-xs rounded-full">Important</span>');
                if (task.urgent) badges.push('<span class="px-2 py-1 bg-red-50 text-red-700 text-xs rounded-full">Urgent</span>');
                const displayTag = formatTagNames(task.tag || task.raw_tag || '');
                const primaryTag = normalizeTagName(task.tag || task.raw_tag || '');
                let tagBadge = '';
                if (displayTag) {
                    const tagColor = TAG_COLOR_MAP[primaryTag] || '#6B7280';
                    const tagStyle = `background-color: ${tagColor}15; color: ${tagColor}; border: 1px solid ${tagColor}30;`;
                    tagBadge = `<span class="px-2 py-0.5 rounded-full text-xs font-medium" style="${tagStyle}">${displayTag}</span>`;
                }
                const taskId = Number(task.sheety_id || task.id || 0);
                const actionButtons = (taskId && task.sheety_id != null)
                    ? `<div class="flex items-center gap-2">
                            <button class="px-2.5 py-1 rounded-full border border-slate-200 text-[11px] font-semibold text-gray-600 hover:bg-white" data-action="edit-task" data-task-id="${taskId}">Edit</button>
                            <button class="px-2.5 py-1 rounded-full border border-red-200 text-[11px] font-semibold text-red-600 hover:bg-white" data-action="delete-task" data-task-id="${taskId}">Delete</button>
                        </div>`
                    : '';
                return `${dayHeader}
                    <div class="luxury-card rounded-2xl p-4 md:p-5 mb-3 shadow-lg">
                        <div class="flex items-center justify-between gap-3">
                            <div class="flex-1 min-w-0">
                                <div class="font-medium text-gray-900 mb-1 line-clamp-2 break-words">${escapeSuggestionHtml(normalizeGraphTaskName(task.task) || 'Untitled task')}</div>
                                <div class="flex flex-wrap items-center gap-2 text-[13px] text-gray-600">
                                    ${groupByDay ? '' : `<span class="text-gray-500" title="${escapeSuggestionHtml(task.date)}">${escapeSuggestionHtml(friendlyTaskDate(task.date))}</span>`}
                                    <span class="text-gray-500">${escapeSuggestionHtml(task.start_time)} - ${escapeSuggestionHtml(task.end_time)}</span>
                                    ${tagBadge}
                                    ${badges.join('')}
                                </div>
                            </div>
                            <div class="shrink-0 flex flex-col items-end gap-2">
                                <span class="inline-flex px-2.5 py-1 rounded-full bg-white border border-slate-200 text-xs font-semibold text-gray-700 js-hover-hours hover-swap" data-hours="${dur}">${durText}</span>
                                ${actionButtons ? `<div class="hidden sm:block">${actionButtons}</div>` : ''}
                            </div>
                        </div>
                        ${actionButtons ? `<div class="sm:hidden mt-3 flex justify-end">${actionButtons}</div>` : ''}
                    </div>
                `;
            });
            graphTasksList.innerHTML = html.join('');
            attachHoverSwap();
        }

        function getGraphTaskById(taskId) {
            return graphTasks.find(task => {
                const localId = Number(task.id || 0);
                const remoteId = Number(task.sheety_id || 0);
                return localId === Number(taskId) || (remoteId && remoteId === Number(taskId));
            });
        }

        function closeGraphEditPanel() {
            const panel = document.getElementById('graphTaskEditPanel');
            if (panel) panel.classList.add('hidden');
        }

        function openGraphEditPanel(task) {
            if (!task) return;
            if (task.sheety_id == null) {
                if (window.showWarningToast) {
                    window.showWarningToast('This task is not linked to Sheety yet. Sync with full API access to edit it.');
                } else {
                    alert('This task is not linked to Sheety yet.');
                }
                return;
            }
            closeGraphDeleteConfirm();
            const panel = document.getElementById('graphTaskEditPanel');
            if (!panel) return;
            const nameInput = document.getElementById('graphEditTaskName');
            const startMode = document.getElementById('graphEditStartMode');
            const startRaw = document.getElementById('graphEditStartRaw');
            const endMode = document.getElementById('graphEditEndMode');
            const endRaw = document.getElementById('graphEditEndRaw');
            const tagInput = document.getElementById('graphEditTaskTags');
            const importantInput = document.getElementById('graphEditTaskImportant');
            const urgentInput = document.getElementById('graphEditTaskUrgent');
            const idInput = document.getElementById('graphEditTaskId');
            const resolvedTaskId = task.sheety_id ?? task.id ?? '';
            if (idInput) idInput.value = resolvedTaskId;
            if (nameInput) nameInput.value = String(task.task || '').trim();
            if (tagInput) {
                const displayTag = formatTagNames(task.tag || task.raw_tag || '');
                tagInput.value = displayTag === 'Waste' ? '' : displayTag;
            }
            if (importantInput) importantInput.checked = Boolean(task.important);
            if (urgentInput) urgentInput.checked = Boolean(task.urgent);
            window.__graphEditingTask = task;
            if (startMode) startMode.value = 'manual';
            if (endMode) endMode.value = 'manual';
            if (startRaw) startRaw.value = formatGraphTaskDateTime(task.date, task.start_time);
            if (endRaw) endRaw.value = formatGraphTaskDateTime(task.date, task.end_time);
            panel.classList.remove('hidden');
            try {
                panel.scrollIntoView({ behavior: 'smooth', block: 'center' });
            } catch (e) {
                panel.scrollIntoView();
            }
        }

        function closeGraphDeleteConfirm() {
            const panel = document.getElementById('graphTaskDeleteConfirm');
            if (panel) panel.classList.add('hidden');
            graphPendingDeleteTaskId = null;
        }

        function openGraphDeleteConfirm(task) {
            if (!task) return;
            if (task.sheety_id == null) {
                if (window.showWarningToast) {
                    window.showWarningToast('This task is not linked to Sheety yet. Sync with full API access to delete it.');
                } else {
                    alert('This task is not linked to Sheety yet.');
                }
                return;
            }
            closeGraphEditPanel();
            const panel = document.getElementById('graphTaskDeleteConfirm');
            if (!panel) return;
            graphPendingDeleteTaskId = task.sheety_id ?? task.id ?? null;
            const label = document.getElementById('graphDeleteTaskLabel');
            if (label) {
                const taskName = String(task.task || '').trim() || 'this task';
                label.textContent = `Delete "${taskName}"? This action cannot be undone.`;
            }
            panel.classList.remove('hidden');
            try {
                panel.scrollIntoView({ behavior: 'smooth', block: 'center' });
            } catch (e) {
                panel.scrollIntoView();
            }
        }

        async function refreshGraphTaskModal() {
            await fetchGraphData({ includeTasks: true });
            renderGraphTaskStats();
            renderGraphTaskChart();
            renderGraphTaskList();
        }

        function getEndDate() {
            const now = new Date();
            const yyyy = now.getFullYear();
            const mm = String(now.getMonth() + 1).padStart(2, '0');
            const dd = String(now.getDate()).padStart(2, '0');
            return `${yyyy}-${mm}-${dd}`;
        }

        function movingAverage(values, windowSize = 7) {
            const result = [];
            for (let i = 0; i < values.length; i++) {
                const start = Math.max(0, i - windowSize + 1);
                const slice = values.slice(start, i + 1);
                const sum = slice.reduce((acc, v) => acc + v, 0);
                const avg = slice.length ? sum / slice.length : 0;
                result.push(Number(avg.toFixed(2)));
            }
            return result;
        }

        function hexToRgba(hex, alpha) {
            if (!hex || typeof hex !== 'string' || !hex.startsWith('#')) {
                return `rgba(17, 24, 39, ${alpha})`;
            }
            const clean = hex.replace('#', '');
            const bigint = parseInt(clean, 16);
            const r = (bigint >> 16) & 255;
            const g = (bigint >> 8) & 255;
            const b = bigint & 255;
            return `rgba(${r}, ${g}, ${b}, ${alpha})`;
        }

        function deriveSearchColors(tasks) {
            if (!Array.isArray(tasks) || !tasks.length) return null;
            const totals = {};
            const priorityTotals = { q1: 0, q2: 0, q3: 0, q4: 0 };
            tasks.forEach(task => {
                const duration = Number(task.duration_minutes || 0);
                const tags = String(task.tag || task.raw_tag || '')
                    .split(',')
                    .map(t => t.trim())
                    .filter(Boolean);
                const usableTags = tags.length ? tags : ['Waste'];
                usableTags.forEach(tag => {
                    if (TAG_COLOR_MAP[tag]) {
                        totals[tag] = (totals[tag] || 0) + duration;
                    }
                });
                if (task.urgent && task.important) {
                    priorityTotals.q1 += duration;
                } else if (task.important) {
                    priorityTotals.q2 += duration;
                } else if (task.urgent) {
                    priorityTotals.q3 += duration;
                } else {
                    priorityTotals.q4 += duration;
                }
            });
            const sortedTags = Object.entries(totals).sort((a, b) => b[1] - a[1]);
            if (sortedTags.length) {
                const primary = TAG_COLOR_MAP[sortedTags[0][0]];
                const secondary = sortedTags[1] ? TAG_COLOR_MAP[sortedTags[1][0]] : null;
                return { primary, secondary };
            }
            const priorityPick = Object.entries(priorityTotals).sort((a, b) => b[1] - a[1])[0];
            if (priorityPick && priorityPick[1] > 0) {
                return { primary: metricColors[priorityPick[0]] || '#111827', secondary: null };
            }
            return null;
        }

        function getFocusLabel(value) {
            if (value === 'search_only') return 'Search only';
            return metricLabels[value] || value;
        }

        function updateSearchInputState() {
            graphSearchInput.removeAttribute('disabled');
            graphSearchInput.classList.remove('opacity-60', 'cursor-not-allowed');
        }

        function getSuggestionLabel(suggestion) {
            const focus = getFocusLabel(String(suggestion?.focus || 'total'));
            const search = String(suggestion?.search || '').trim();
            if (!search) return focus;
            return `${focus} and (${search})`;
        }

        // 'YYYY-MM-DD' -> 'Wed, Oct 7' for display (built from parts so it never shifts a day via UTC).
        function friendlyTaskDate(value) {
            const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(value || '').trim());
            if (!m) return String(value || '');
            const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
            if (isNaN(d.getTime())) return String(value || '');
            const opts = { weekday: 'short', month: 'short', day: 'numeric' };
            if (d.getFullYear() !== new Date().getFullYear()) opts.year = 'numeric';
            return d.toLocaleDateString(undefined, opts);
        }

        function escapeSuggestionHtml(value) {
            return String(value || '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#39;');
        }

        function hideGraphSearchSuggestions() {
            if (graphSearchSuggestions) {
                graphSearchSuggestions.classList.add('hidden');
                graphSearchSuggestions.innerHTML = '';
            }
            graphSuggestionActiveIndex = -1;
        }

        function setActiveGraphSuggestion(index) {
            const buttons = Array.from(graphSearchSuggestions?.querySelectorAll('.graph-search-suggestion') || []);
            if (!buttons.length) {
                graphSuggestionActiveIndex = -1;
                return;
            }
            if (index < 0) {
                graphSuggestionActiveIndex = buttons.length - 1;
            } else if (index >= buttons.length) {
                graphSuggestionActiveIndex = 0;
            } else {
                graphSuggestionActiveIndex = index;
            }
            buttons.forEach((btn, idx) => {
                btn.dataset.active = idx === graphSuggestionActiveIndex ? 'true' : 'false';
            });
            const activeBtn = buttons[graphSuggestionActiveIndex];
            if (activeBtn) {
                activeBtn.scrollIntoView({ block: 'nearest' });
            }
        }

        function renderGraphSearchSuggestions() {
            if (!graphSearchSuggestions) return;
            const query = String(graphSearchInput?.value || '').trim().toLowerCase();
            const visible = (graphSavedSuggestions || []).filter(item => {
                const label = getSuggestionLabel(item).toLowerCase();
                return !query || label.includes(query);
            }).slice(0, 7);
            if (!visible.length) {
                hideGraphSearchSuggestions();
                return;
            }
            graphSearchSuggestions.innerHTML = visible.map(item => {
                const label = escapeSuggestionHtml(getSuggestionLabel(item));
                const count = Number(item?.count || 0);
                const safeFocus = escapeSuggestionHtml(String(item.focus || ''));
                const safeSearch = escapeSuggestionHtml(String(item.search || ''));
                return `
                    <button type="button" class="graph-search-suggestion" data-focus="${safeFocus}" data-search="${safeSearch}">
                        <div>${label}</div>
                        <div class="meta">Used ${count} time${count === 1 ? '' : 's'}</div>
                    </button>
                `;
            }).join('');
            graphSearchSuggestions.classList.remove('hidden');
            graphSuggestionActiveIndex = -1;
            graphSearchSuggestions.querySelectorAll('.graph-search-suggestion').forEach(btn => {
                btn.addEventListener('click', async () => {
                    const focus = btn.getAttribute('data-focus') || 'total';
                    const search = btn.getAttribute('data-search') || '';
                    graphExcludedIds = new Set();
                    setFocus(focus, { fetch: false });
                    graphSearchInput.value = search;
                    graphSearchQuery = String(search || '').trim();
                    hideGraphSearchSuggestions();
                    await fetchGraphData({ includeTasks: Boolean(graphSearchQuery) });
                    await recordGraphSuggestionUsage();
                });
            });
        }

        async function loadGraphSearchSuggestions() {
            try {
                const response = await fetch('/api/graph-search-suggestions?limit=7', { credentials: 'include' });
                if (!response.ok) return;
                const data = await response.json();
                graphSavedSuggestions = Array.isArray(data?.suggestions) ? data.suggestions : [];
            } catch (e) {
                graphSavedSuggestions = [];
            }
        }

        async function recordGraphSuggestionUsage() {
            if (!graphSearchQuery) return;
            try {
                await fetch('/api/graph-search-suggestions/use', {
                    method: 'POST',
                    credentials: 'include',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ focus: graphFocusValue, search: graphSearchQuery })
                });
                await loadGraphSearchSuggestions();
            } catch (e) {
                // best-effort only
            }
        }

        function updateFocusMenuActive() {
            document.querySelectorAll('.graph-focus-option').forEach(option => {
                const active = (option.dataset.value || '') === graphFocusValue;
                option.dataset.active = active ? 'true' : 'false';
                option.setAttribute('aria-current', active ? 'true' : 'false');
            });
        }

        function setFocus(value, { fetch = true } = {}) {
            graphFocusValue = value;
            currentMetric = value === 'search_only' ? 'total' : value;
            graphFocusLabel.textContent = getFocusLabel(value);
            updateSearchInputState();
            updateFocusMenuActive();
            if (fetch) {
                fetchGraphData({ includeTasks: graphSearchQuery.length > 0 });
            }
        }

        function deriveValuesFromTasks(labels) {
            const totals = {};
            graphTasks.forEach(task => {
                const date = String(task.date || '').trim();
                if (!date) return;
                const minutes = Number(task.duration_minutes || 0);
                totals[date] = (totals[date] || 0) + minutes;
            });
            return labels.map(label => Number(((totals[label] || 0) / 60).toFixed(2)));
        }

        function computeAverageHours(values) {
            const total = values.reduce((sum, v) => sum + (Number(v) || 0), 0);
            const firstIndex = values.findIndex(v => v > 0);
            if (firstIndex < 0) return { total, avg: 0, max: 0 };
            const activeDays = Math.max(1, values.length - firstIndex);
            const avg = total / activeDays;
            const max = Math.max(...values, 0);
            return { total: Number(total.toFixed(2)), avg: Number(avg.toFixed(2)), max: Number(max.toFixed(2)) };
        }

        function getRangeBounds(labels, days) {
            if (!labels || labels.length === 0) {
                return { startIndex: 0, endIndex: 0 };
            }
            const total = labels.length;
            const startIndex = Math.max(0, total - days);
            return { startIndex, endIndex: total - 1 };
        }

        function getLastFinitePoint(values) {
            if (!Array.isArray(values) || !values.length) return { index: null, value: null };
            for (let i = values.length - 1; i >= 0; i--) {
                const num = Number(values[i]);
                if (Number.isFinite(num)) return { index: i, value: num };
            }
            return { index: null, value: null };
        }

        function updateChart({ labels, values, total_hours, avg_hours, max_hours, by_hour }, metricKey, rangeDays = currentDays) {
            closeGraphPointDetail();
            if (graphSearchQuery && graphTasks.length) {
                values = deriveValuesFromTasks(labels);
                const totals = computeAverageHours(values);
                total_hours = totals.total;
                avg_hours = totals.avg;
                max_hours = totals.max;
            }
            const trimmedSeries = trimLeadingInactiveForAllRange(labels, values, currentRange);
            labels = trimmedSeries.labels;
            values = trimmedSeries.values;
            if (shouldAutoMAOnNextRender) {
                const spanDays = getDisplayedSpanDaysForRange(labels, values, currentRange);
                maWindow = pickDefaultMAWindowForDays(spanDays);
                syncMAPills();
                shouldAutoMAOnNextRender = false;
            }
            const ctx = document.getElementById('graphCanvas').getContext('2d');
            const colors = graphColorScheme || { primary: metricColors[metricKey] || '#111827', secondary: null };
            const color = colors.primary;
            const gradient = ctx.createLinearGradient(0, 0, 0, 320);
            gradient.addColorStop(0, hexToRgba(colors.primary, 0.55));
            gradient.addColorStop(1, hexToRgba(colors.secondary || colors.primary, 0.05));
            const avgValues = movingAverage(values, maWindow);
            const valueScale = getValueScale(values, avgValues);
            const avgColor = color.startsWith('#') && color.length === 7 ? `${color}99` : 'rgba(17,24,39,0.55)';
            const isDark = isDarkTheme();
            const projectionPoint = getLastFinitePoint(avgValues);
            const projectionValue = Number.isFinite(Number(projectionPoint.value)) ? Number(projectionPoint.value) : null;
            const projectionLabel = Number.isFinite(projectionValue)
                ? formatGraphValue(projectionValue, valueScale, 1)
                : '';
            const yTickCallback = function(value) {
                const num = Number(value);
                if (Number.isFinite(num) && Number.isFinite(projectionValue)) {
                    const scale = this;
                    const min = Number(scale && scale.min);
                    const max = Number(scale && scale.max);
                    const height = Number(scale && scale.height);
                    if (Number.isFinite(min) && Number.isFinite(max) && Number.isFinite(height) && height > 0) {
                        const unitsPerPixel = Math.abs(max - min) / height;
                        const hideThreshold = Math.max(unitsPerPixel * 14, unitsPerPixel || 0.0001);
                        if (Math.abs(num - projectionValue) <= hideThreshold) {
                            return '';
                        }
                    }
                }
                return formatGraphValue(value, valueScale, 1);
            };
            const projectionConfig = Number.isFinite(projectionValue)
                ? {
                    value: projectionValue,
                    label: projectionLabel,
                    datasetIndex: 0,
                    pointIndex: projectionPoint.index,
                    lineColor: hexToRgba(color, isDark ? 0.58 : 0.44),
                    lineWidth: 1.3,
                    dash: [4, 5],
                    labelColor: isDark ? '#E9D8A6' : '#5A4A2D',
                    labelBackground: isDark ? 'rgba(24, 18, 11, 0.92)' : 'rgba(255, 253, 248, 0.97)',
                    labelBorder: isDark ? 'rgba(184, 168, 120, 0.55)' : 'rgba(148, 126, 86, 0.45)',
                }
                : null;
            graphRawDates = Array.isArray(labels) ? labels.slice() : [];
            graphRawValues = Array.isArray(values) ? values.slice() : [];
            graphMaValues = Array.isArray(avgValues) ? avgValues.slice() : [];

            const shortLabels = labels.map(label => {
                // Local calendar date; new Date('YYYY-MM-DD') would be UTC and show the previous day west of UTC.
                const d = parseIsoDate(label) || new Date(label);
                return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
            });
            const rangeBounds = getRangeBounds(labels, rangeDays);
            const xMinLabel = shortLabels[rangeBounds.startIndex] || shortLabels[0];
            const xMaxLabel = shortLabels[rangeBounds.endIndex] || shortLabels[shortLabels.length - 1];

            const mobile = isGraphMobile();

            const maDataset = {
                __kind: 'ma',
                label: `${metricLabels[metricKey] || 'Time'} (MA ${maWindow}d)`,
                data: avgValues,
                borderColor: color,
                backgroundColor: gradient,
                borderWidth: 3,
                fill: true,
                tension: 0.35,
                pointRadius: 0,
                pointHoverRadius: 0,
                pointHitRadius: 0
            };

            // Long ranges on a narrow chart: dots and dashes every few pixels turn into noise,
            // so draw the daily series as a thin, faint solid line under the average instead.
            const plotWidth = (ctx.canvas.parentElement || ctx.canvas).clientWidth || 600;
            const visiblePoints = Math.max(1, rangeBounds.endIndex - rangeBounds.startIndex + 1);
            const denseRaw = visiblePoints > plotWidth / 6;
            const rawDataset = {
                __kind: 'raw',
                label: `${metricLabels[metricKey] || 'Time'} (daily)`,
                data: values,
                borderColor: denseRaw ? hexToRgba(color, isDark ? 0.45 : 0.4) : avgColor,
                borderWidth: denseRaw ? 1 : 2,
                borderDash: denseRaw ? [] : [6, 6],
                fill: false,
                tension: denseRaw ? 0 : 0.35,
                pointRadius: denseRaw ? 0 : 2,
                pointHoverRadius: 5,
                pointBackgroundColor: '#FFFFFF',
                pointBorderColor: avgColor,
                pointBorderWidth: 2
            };

            const goalLine = goalLineFor(metricKey);
            const goalDataset = goalLine ? {
                __kind: 'goal',
                label: `${goalLine.label} (${formatGraphValue(goalLine.value, valueScale, 1)})`,
                data: labels.map(() => goalLine.value),
                borderColor: goalLine.color,
                borderWidth: 1.5,
                borderDash: [3, 5],
                fill: false,
                tension: 0,
                pointRadius: 0,
                pointHoverRadius: 0,
                pointHitRadius: 0
            } : null;

            if (chartInstance) {
                chartInstance.data.labels = shortLabels;
                const datasets = chartInstance.data.datasets || [];
                if (!datasets[0]) datasets[0] = { __kind: 'ma' };
                if (!datasets[1]) datasets[1] = { __kind: 'raw' };

                Object.assign(datasets[0], maDataset);
                Object.assign(datasets[1], rawDataset);
                datasets.length = 2;
                if (goalDataset) datasets.push(goalDataset);
                chartInstance.options.scales.x.min = xMinLabel;
                chartInstance.options.scales.x.max = xMaxLabel;
                if (chartInstance.options?.scales?.y?.ticks) {
                    chartInstance.options.scales.y.ticks.callback = yTickCallback;
                }
                if (chartInstance.options?.plugins?.tooltip) {
                    chartInstance.options.plugins.tooltip.enabled = !mobile;
                    chartInstance.options.plugins.tooltip.callbacks = {
                        title: function(items) {
                            const idx = items && items.length ? items[0].dataIndex : null;
                            const rawDate = idx != null ? graphRawDates[idx] : '';
                            return rawDate ? formatGraphDetailDate(rawDate) : '';
                        },
                        label: function(context) {
                            const kind = context?.dataset?.__kind;
                            const y = Number(context?.parsed?.y || 0);
                            if (kind === 'raw') return `Day: ${formatGraphValue(y, valueScale, 2)}`;
                            if (kind === 'goal') return context.dataset.label;
                            if (kind === 'prev') return `Previous period: ${formatGraphValue(y, valueScale, 2)}`;
                            return `MA (${maWindow}d): ${formatGraphValue(y, valueScale, 2)}`;
                        }
                    };
                }
                chartInstance.$currentProjection = projectionConfig;
                chartInstance.options.animation = { duration: 650, easing: 'easeOutQuart' };
                chartInstance.options.onHover = (evt) => {
                    if (mobile) return;
                    const points = chartInstance.getElementsAtEventForMode(evt, 'nearest', { intersect: true }, true);
                    const hit = points[0];
                    const dataset = hit ? chartInstance.data.datasets[hit.datasetIndex] : null;
                    if (evt?.native?.target) {
                        evt.native.target.style.cursor = dataset?.__kind === 'raw' ? 'pointer' : 'default';
                    }
                };
                chartInstance.options.onClick = (evt) => {
                    const points = chartInstance.getElementsAtEventForMode(evt, 'nearest', { intersect: true }, true);
                    if (!points.length) {
                        if (mobile) closeGraphPointDetail();
                        return;
                    }
                    const hit = points[0];
                    const dataset = chartInstance.data.datasets[hit.datasetIndex];
                    if (dataset?.__kind !== 'raw') return;
                    const rawDate = graphRawDates[hit.index];
                    if (!rawDate) return;
                    if (mobile) {
                        showGraphPointDetail(chartInstance, hit.index, hit);
                    } else {
                        navigateToGraphDate(rawDate);
                    }
                };
                chartInstance.update();
            } else {
                chartInstance = new Chart(ctx, {
                    plugins: [currentProjectionPlugin],
                    type: 'line',
                    data: {
                        labels: shortLabels,
                        datasets: [
                            maDataset,
                            rawDataset
                        ].concat(goalDataset ? [goalDataset] : [])
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        interaction: { mode: 'nearest', intersect: true },
                        animation: { duration: 650, easing: 'easeOutQuart' },
                        plugins: {
                            legend: { display: false },
                            tooltip: {
                                enabled: !mobile,
                                backgroundColor: isDarkTheme() ? 'rgba(22,19,14,0.98)' : 'rgba(17, 24, 39, 0.96)',
                                padding: 12,
                                titleFont: { family: 'Inter', size: 12, weight: '600' },
                                bodyFont: { family: 'Inter', size: 12, weight: '400' },
                                callbacks: {
                                    title: function(items) {
                                        const idx = items && items.length ? items[0].dataIndex : null;
                                        const rawDate = idx != null ? graphRawDates[idx] : '';
                                        return rawDate ? formatGraphDetailDate(rawDate) : '';
                                    },
                                    label: function(context) {
                                        const kind = context?.dataset?.__kind;
                                        const y = Number(context?.parsed?.y || 0);
                                        if (kind === 'raw') return `Day: ${formatGraphValue(y, valueScale, 2)}`;
                                        if (kind === 'goal') return context.dataset.label;
                            if (kind === 'prev') return `Previous period: ${formatGraphValue(y, valueScale, 2)}`;
                                        return `MA (${maWindow}d): ${formatGraphValue(y, valueScale, 2)}`;
                                    }
                                }
                            }
                        },
                        onHover: (evt) => {
                            if (mobile) return;
                            const points = chartInstance.getElementsAtEventForMode(evt, 'nearest', { intersect: true }, true);
                            const hit = points[0];
                            const dataset = hit ? chartInstance.data.datasets[hit.datasetIndex] : null;
                            if (evt?.native?.target) {
                                evt.native.target.style.cursor = dataset?.__kind === 'raw' ? 'pointer' : 'default';
                            }
                        },
                        onClick: (evt) => {
                            const points = chartInstance.getElementsAtEventForMode(evt, 'nearest', { intersect: true }, true);
                            if (!points.length) {
                                if (mobile) closeGraphPointDetail();
                                return;
                            }
                            const hit = points[0];
                            const dataset = chartInstance.data.datasets[hit.datasetIndex];
                            if (dataset?.__kind !== 'raw') return;
                            const rawDate = graphRawDates[hit.index];
                            if (!rawDate) return;
                            if (mobile) {
                                showGraphPointDetail(chartInstance, hit.index, hit);
                            } else {
                                navigateToGraphDate(rawDate);
                            }
                        },
                        scales: {
                            x: {
                                grid: { display: false },
                                ticks: { color: isDarkTheme() ? '#635848' : '#6B7280', maxTicksLimit: 8 },
                                min: xMinLabel,
                                max: xMaxLabel
                            },
                            y: {
                                beginAtZero: true,
                                grid: { color: isDarkTheme() ? 'rgba(180,148,72,0.07)' : 'rgba(148,163,184,0.25)' },
                                ticks: {
                                    color: isDarkTheme() ? '#635848' : '#6B7280',
                                    callback: yTickCallback
                                }
                            }
                        }
                    }
                });
                chartInstance.$currentProjection = projectionConfig;
                chartInstance.update('none');
            }

            totalHoursEl.textContent = formatGraphValue(total_hours, valueScale, 1);
            avgHoursEl.textContent = formatGraphValue(avg_hours, valueScale, 1);
            maxHoursEl.textContent = formatGraphValue(max_hours, valueScale, 1);
            updateRecentAverage(values, avg_hours, valueScale, labels);
            updateWeekdayPattern(labels, values, valueScale);
            updateHourPattern(by_hour);
            updateCalendarHeatmap(labels, values, valueScale);
            persistGraphState();

            const label = metricLabels[metricKey] || 'Total time';
            if (graphFocusValue === 'search_only' && graphSearchQuery) {
                chartTitle.textContent = `Search: ${graphSearchQuery}`;
            } else if (graphSearchQuery) {
                chartTitle.textContent = `${label} and (${graphSearchQuery})`;
            } else {
                chartTitle.textContent = label;
            }
            const displayedDays = getDisplayedSpanDaysForRange(labels, values, currentRange);
            const subtitleParts = [
                currentRange === 'all' && !firstLogDateStr ? 'No entries yet' : `Last ${displayedDays} days`,
                `${maWindow}-day avg`
            ];
            if (graphSearchQuery || graphExcludedIds.size) {
                subtitleParts.push('Filtered');
            }
            chartSubtitle.textContent = subtitleParts.join(' · ');
            updateGraphEmptyState(values, displayedDays);
            applyCompareOverlay(labels, values, rangeDays, valueScale);
        }

        // A search or exclusion that leaves nothing would otherwise draw a silent flat line.
        function updateGraphEmptyState(values, days) {
            const box = document.getElementById('graphEmpty');
            const text = document.getElementById('graphEmptyText');
            if (!box || !text) return;
            const filtered = Boolean(graphSearchQuery) || graphExcludedIds.size > 0;
            const empty = filtered && !(values || []).some(v => Number(v) > 0);
            box.classList.toggle('hidden', !empty);
            box.classList.toggle('flex', empty);
            if (!empty) return;
            text.textContent = graphSearchQuery
                ? `No entries match “${graphSearchQuery}” in the last ${days} days.`
                : `Nothing left in the last ${days} days after the excluded tasks.`;
            document.getElementById('graphEmptyClear').classList.toggle('hidden', !graphSearchQuery);
        }
        document.getElementById('graphEmptyClear')?.addEventListener('click', () => graphSearchClear.click());

        // ---- Compare with the previous period ---------------------------------
        // Fetches the same number of days just before the visible window (same
        // focus, search and exclusions) and draws them as a faint dashed line,
        // index-aligned to the window, plus a 'previous vs now' daily average.
        const graphCompareToggle = document.getElementById('graphCompareToggle');
        const chartCompareNote = document.getElementById('chartCompareNote');
        let graphCompareEnabled = false;
        try { graphCompareEnabled = localStorage.getItem('ttp-graph-compare') === '1'; } catch (e) {}
        let graphCompareRequest = 0;

        function syncCompareToggle() {
            if (!graphCompareToggle) return;
            const usable = currentRange !== 'all';
            graphCompareToggle.disabled = !usable;
            graphCompareToggle.classList.toggle('active', graphCompareEnabled && usable);
            graphCompareToggle.classList.toggle('opacity-50', !usable);
            graphCompareToggle.setAttribute('aria-pressed', graphCompareEnabled && usable ? 'true' : 'false');
            graphCompareToggle.title = usable
                ? 'Overlay the same number of days just before this range'
                : 'Pick a time range (not All) to compare with the previous period';
        }

        function clearCompareOverlay() {
            if (chartCompareNote) { chartCompareNote.classList.add('hidden'); chartCompareNote.textContent = ''; }
            if (!chartInstance) return;
            const datasets = chartInstance.data.datasets || [];
            const idx = datasets.findIndex(d => d.__kind === 'prev');
            if (idx >= 0) { datasets.splice(idx, 1); chartInstance.update(); }
        }

        function isoMinusDays(iso, days) {
            const d = parseIsoDate(iso);
            if (!d) return '';
            d.setDate(d.getDate() - days);
            return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
        }

        async function applyCompareOverlay(labels, values, rangeDays, valueScale) {
            syncCompareToggle();
            const request = ++graphCompareRequest;
            if (!graphCompareEnabled || currentRange === 'all' || !Array.isArray(labels) || !labels.length) {
                clearCompareOverlay();
                return;
            }
            const { startIndex, endIndex } = getRangeBounds(labels, rangeDays);
            const span = endIndex - startIndex + 1;
            const prevEnd = isoMinusDays(labels[startIndex], 1);
            if (!prevEnd || span <= 0) { clearCompareOverlay(); return; }
            const params = new URLSearchParams();
            params.set('metric', currentMetric);
            params.set('days', String(span));
            params.set('end', prevEnd);
            if (graphSearchQuery) params.set('search', graphSearchQuery);
            if (graphExcludedIds.size) params.set('exclude', Array.from(graphExcludedIds).join(','));
            let prev;
            try {
                const resp = await fetch(`/api/graph-data?${params.toString()}`, { credentials: 'include' });
                if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
                prev = await resp.json();
            } catch (e) {
                console.warn('Could not load the previous period', e);
                return;
            }
            if (request !== graphCompareRequest || !chartInstance) return;  // a newer render won
            const prevValues = Array.isArray(prev.values) ? prev.values.slice(-span) : [];
            const aligned = labels.map((_, i) => (i >= startIndex && i <= endIndex) ? (Number(prevValues[i - startIndex]) || 0) : null);
            const dark = typeof isDarkTheme === 'function' && isDarkTheme();
            const dataset = {
                __kind: 'prev',
                label: 'Previous period',
                data: aligned,
                borderColor: dark ? 'rgba(184, 168, 120, 0.55)' : 'rgba(100, 116, 139, 0.55)',
                borderWidth: 1.5,
                borderDash: [2, 4],
                fill: false,
                tension: 0.35,
                pointRadius: 0,
                pointHoverRadius: 0,
                pointHitRadius: 0,
                spanGaps: false
            };
            const datasets = chartInstance.data.datasets;
            const idx = datasets.findIndex(d => d.__kind === 'prev');
            if (idx >= 0) datasets[idx] = dataset; else datasets.push(dataset);
            // Animated on purpose: after update('none') an entry/update animation that is still
            // running finishes at its old targets (laid out for the old y max), so with the overlay
            // raising the axis every line ended up drawn too high. update() re-targets it.
            chartInstance.update();

            const windowValues = values.slice(startIndex, endIndex + 1).map(v => Number(v) || 0);
            const nowAvg = windowValues.reduce((a, b) => a + b, 0) / Math.max(1, span);
            const prevAvg = prevValues.reduce((a, b) => a + (Number(b) || 0), 0) / Math.max(1, span);
            if (chartCompareNote) {
                const delta = nowAvg - prevAvg;
                const sign = delta > 0.05 ? '▲' : (delta < -0.05 ? '▼' : '=');
                chartCompareNote.textContent = `Previous ${span} days ${formatGraphValue(prevAvg, valueScale, 1)}/day → now ${formatGraphValue(nowAvg, valueScale, 1)}/day ${sign === '=' ? '(same)' : sign + ' ' + formatGraphValue(Math.abs(delta), valueScale, 1)}`;
                chartCompareNote.classList.remove('hidden');
            }
        }

        if (graphCompareToggle) {
            graphCompareToggle.addEventListener('click', () => {
                if (currentRange === 'all') return;
                graphCompareEnabled = !graphCompareEnabled;
                try { localStorage.setItem('ttp-graph-compare', graphCompareEnabled ? '1' : '0'); } catch (e) {}
                if (lastGraphPayload) {
                    updateChart(lastGraphPayload, currentMetric, currentDays);
                } else {
                    syncCompareToggle();
                }
            });
        }

        // The plotted series as CSV: one row per day with the moving average beside it.
        document.getElementById('graphDownloadCsv')?.addEventListener('click', () => {
            if (!graphRawDates.length) return;
            const focus = graphFocusValue === 'search_only' ? 'search' : graphFocusValue;
            const rows = [['date', 'hours', `moving_average_${maWindow}d`]];
            graphRawDates.forEach((day, i) => {
                const ma = Number(graphMaValues[i]);
                rows.push([day, Number(graphRawValues[i] || 0).toFixed(2), Number.isFinite(ma) ? ma.toFixed(2) : '']);
            });
            const csv = rows.map(r => r.join(',')).join('\n') + '\n';
            const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
            const a = document.createElement('a');
            a.href = url;
            a.download = `time-tracker-${focus}-${graphRawDates[0]}-to-${graphRawDates[graphRawDates.length - 1]}.csv`;
            document.body.appendChild(a);
            a.click();
            a.remove();
            setTimeout(() => URL.revokeObjectURL(url), 1000);
        });

        function buildGraphUrl(includeTasks = false) {
            const params = new URLSearchParams();
            params.set('metric', currentMetric);
            params.set('days', String(currentDays));
            params.set('end', getEndDate());
            if (graphSearchQuery) {
                params.set('search', graphSearchQuery);
            }
            if (includeTasks) {
                params.set('include_tasks', 'true');
            }
            if (graphExcludedIds.size) {
                params.set('exclude', Array.from(graphExcludedIds).join(','));
            }
            return `/api/graph-data?${params.toString()}`;
        }

        function openGraphTaskModal() {
            if (!graphTaskModal) return;
            const editPanel = document.getElementById('graphTaskEditPanel');
            const deletePanel = document.getElementById('graphTaskDeleteConfirm');
            if (editPanel) editPanel.classList.add('hidden');
            if (deletePanel) deletePanel.classList.add('hidden');
            graphPendingDeleteTaskId = null;
            const sortLabels = {
                time_desc: 'Time ↓',
                time_asc: 'Time ↑',
                duration_desc: 'Duration ↓',
                duration_asc: 'Duration ↑',
                task_az: 'Task A→Z',
                task_za: 'Task Z→A',
                tag_az: 'Tag A→Z',
                tag_za: 'Tag Z→A',
                imp_desc: 'Important first',
                urg_desc: 'Urgent first'
            };
            const sortToggles = {
                time: ['time_desc', 'time_asc'],
                duration: ['duration_desc', 'duration_asc'],
                task: ['task_az', 'task_za'],
                tag: ['tag_az', 'tag_za']
            };
            const resolveSort = (base) => {
                const options = sortToggles[base];
                if (!options) {
                    const fallback = base === 'imp' ? 'imp_desc' : base === 'urg' ? 'urg_desc' : 'time_desc';
                    return { key: fallback, label: sortLabels[fallback] || 'Time ↓' };
                }
                const current = graphTaskSort;
                const next = options.includes(current)
                    ? (current === options[0] ? options[1] : options[0])
                    : options[0];
                return { key: next, label: sortLabels[next] || 'Time ↓' };
            };
            if (graphTaskTools) {
                graphTaskTools.innerHTML = `
                    <div class="w-full flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                        <div class="w-full sm:flex-1 sm:min-w-0">
                            <input id="graphTaskSearch" aria-label="Search tasks" type="search" placeholder="Search tasks..." class="w-full px-4 py-2 rounded-full bg-white border border-slate-200 text-sm text-gray-700 shadow-sm focus:outline-none focus:ring-2 focus:ring-amber-300" />
                        </div>
                        <div class="w-full sm:w-auto flex items-center gap-2 justify-end sm:justify-start shrink-0">
                            <button id="graphTaskExportBtn" class="px-3 py-2 rounded-full bg-white border border-slate-200 text-xs text-gray-700 shadow-sm active:scale-[0.98] transition">Export</button>
                            <div class="relative">
                                <button id="graphTaskSortBtn" class="px-3 py-2 rounded-full bg-white border border-slate-200 text-xs text-gray-700 shadow-sm active:scale-[0.98] transition">
                                    Sort: <span id="graphTaskSortLabel">${sortLabels[graphTaskSort] || graphTaskSortLabel || 'Time ↓'}</span>
                                </button>
                                <div id="graphTaskSortMenu" class="absolute right-0 mt-2 w-44 bg-white rounded-xl shadow-2xl border border-slate-200 hidden">
                                    <div class="dropdown-item" data-key="time">Time</div>
                                    <div class="dropdown-item" data-key="duration">Duration</div>
                                    <div class="dropdown-item" data-key="task">Task</div>
                                    <div class="dropdown-item" data-key="tag">Tag</div>
                                    <div class="dropdown-item" data-key="imp">Important first</div>
                                    <div class="dropdown-item" data-key="urg">Urgent first</div>
                                </div>
                            </div>
                        </div>
                    </div>
                `;
                const btn = document.getElementById('graphTaskSortBtn');
                const menu = document.getElementById('graphTaskSortMenu');
                const label = document.getElementById('graphTaskSortLabel');
                const search = document.getElementById('graphTaskSearch');
                const exportBtn = document.getElementById('graphTaskExportBtn');
                if (search) {
                    search.value = String(graphTaskQuery || '');
                    search.oninput = () => {
                        graphTaskQuery = search.value;
                        renderGraphTaskStats();
                        renderGraphTaskChart();
                        renderGraphTaskList();
                    };
                }
                if (exportBtn) {
                    exportBtn.onclick = () => exportGraphModalTasks();
                }
                if (btn && menu && label) {
                    btn.onclick = () => menu.classList.toggle('hidden');
                    menu.querySelectorAll('.dropdown-item').forEach(item => {
                        item.onclick = () => {
                            const base = item.getAttribute('data-key');
                            const next = resolveSort(base);
                            graphTaskSort = next.key;
                            graphTaskSortLabel = next.label;
                            label.textContent = next.label;
                            menu.classList.add('hidden');
                            renderGraphTaskList();
                        };
                    });
                    document.addEventListener('click', (e) => {
                        if (!e.target.closest('#graphTaskSortBtn') && !e.target.closest('#graphTaskSortMenu')) {
                            menu.classList.add('hidden');
                        }
                    });
                }
            }
            renderGraphTaskStats();
            renderGraphTaskChart();
            renderGraphTaskList();
            graphTaskModal.classList.add('active');
            focusModal(graphTaskModal);
        }

        function closeGraphTaskModal() {
            if (!graphTaskModal) return;
            graphTaskModal.classList.remove('active');
            if (lastGraphModalFocus && typeof lastGraphModalFocus.focus === 'function') {
                lastGraphModalFocus.focus();
            }
        }

        function updateReviewButton() {
            const showButton = true;
            if (showButton) {
                reviewGraphTasks.classList.remove('hidden');
                const countLabel = graphTasks.length ? ` (${graphTasks.length})` : '';
                reviewGraphTasks.textContent = `Review tasks${countLabel}`;
            } else {
                reviewGraphTasks.classList.add('hidden');
                reviewGraphTasks.textContent = 'Review tasks';
            }
        }


        let graphFetchSeq = 0;
        async function fetchGraphData({ includeTasks = false, openModal = false } = {}) {
            const metricKey = currentMetric;
            currentDays = getRangeDaysFromSelection();
            const shouldIncludeTasks = includeTasks || graphSearchQuery.length > 0 || graphExcludedIds.size > 0;
            const url = buildGraphUrl(shouldIncludeTasks);
            // Fetches overlap (init, pill clicks, focus changes); only the newest may render,
            // otherwise a slow older response repaints the chart with the wrong range/focus.
            const seq = ++graphFetchSeq;
            try {
                const response = await fetch(url, { credentials: 'include' });
                if (seq !== graphFetchSeq) return;
                if (response.status === 401) {
                    const nextUrl = encodeURIComponent(window.location.pathname + window.location.search);
                    window.location.href = `/login?next=${nextUrl}`;
                    return;
                }
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                const data = await response.json();
                if (seq !== graphFetchSeq) return;
                graphNotes = (data && typeof data.notes === 'object' && data.notes) || {};
                if (shouldIncludeTasks) {
                    graphTasks = Array.isArray(data.tasks) ? data.tasks : [];
                    graphColorScheme = graphSearchQuery ? deriveSearchColors(graphTasks) : null;
                    updateReviewButton();
                } else {
                    graphTasks = [];
                    graphColorScheme = null;
                    updateReviewButton();
                }
                updateChart(data, metricKey);
                lastGraphPayload = data;
                lastGraphDays = currentDays;
                if (openModal && shouldIncludeTasks) {
                    openGraphTaskModal();
                }
            } catch (e) {
                if (seq !== graphFetchSeq) return;
                console.error('Failed to load graph data', e);
                const message = getNetworkErrorMessage(e, 'load graph data');
                if (window.showErrorToast) {
                    window.showErrorToast(message);
                } else {
                    alert(message);
                }
            }
        }

        // ---- Saved views -------------------------------------------------
        const graphSaveViewBtn = document.getElementById('graphSaveView');
        const graphSavedViews = document.getElementById('graphSavedViews');
        const graphSavedViewsList = document.getElementById('graphSavedViewsList');
        let graphViews = [];

        function rangeLabelFor(range) {
            return String(range) === 'all' ? 'All' : `${range}d`;
        }

        function renderSavedViews() {
            if (!graphSavedViews || !graphSavedViewsList) return;
            graphSavedViews.classList.toggle('hidden', graphViews.length === 0);
            graphSavedViewsList.innerHTML = graphViews.map(view => {
                const detail = [getFocusLabel(view.focus), view.search ? `“${view.search}”` : '', rangeLabelFor(view.range), `MA ${view.ma}d`]
                    .filter(Boolean).join(' · ');
                return `<span class="saved-view-chip">
                    <button type="button" class="saved-view-apply" data-view-id="${Number(view.id)}" title="${escapeSuggestionHtml(detail)}">${escapeSuggestionHtml(view.name)}</button>
                    <button type="button" class="saved-view-delete" data-delete-view-id="${Number(view.id)}" aria-label="Delete saved view ${escapeSuggestionHtml(view.name)}">×</button>
                </span>`;
            }).join('');
        }

        async function loadSavedViews() {
            try {
                const resp = await fetch('/api/graph-views', { credentials: 'include' });
                if (!resp.ok) return;
                const data = await resp.json();
                graphViews = Array.isArray(data.views) ? data.views : [];
                renderSavedViews();
            } catch (e) {
                console.warn('Could not load saved views', e);
            }
        }

        // Remember focus, range and average window in this browser so the page opens
        // where you left it (the search is not restored: a silent filter would confuse).
        const GRAPH_STATE_KEY = 'ttp-graphs-state';
        function persistGraphState() {
            try {
                localStorage.setItem(GRAPH_STATE_KEY, JSON.stringify({ focus: graphFocusValue, range: currentRange, ma: maWindow }));
            } catch (e) { /* storage unavailable */ }
        }
        function loadGraphState() {
            try {
                const state = JSON.parse(localStorage.getItem(GRAPH_STATE_KEY) || 'null');
                if (!state || typeof state !== 'object') return null;
                const focusOk = Array.from(document.querySelectorAll('.graph-focus-option')).some(o => o.dataset.value === state.focus);
                const maOk = Array.from(document.querySelectorAll('.ma-pill')).some(p => Number(p.dataset.ma) === Number(state.ma));
                if (!focusOk || !maOk) return null;
                return { focus: state.focus, range: state.range, ma: Number(state.ma), search: '' };
            } catch (e) {
                return null;
            }
        }

        // Links into this page (e.g. the dashboard's Sleep insight): /graphs?focus=sleep&range=90&search=gym
        function loadGraphStateFromUrl() {
            try {
                const params = new URLSearchParams(window.location.search);
                const focus = params.get('focus');
                const search = (params.get('search') || '').slice(0, 200);
                if (!focus && !search) return null;
                const focusOk = focus && Array.from(document.querySelectorAll('.graph-focus-option')).some(o => o.dataset.value === focus);
                const stored = loadGraphState();
                const range = normalizeRangeValue(params.get('range') || (stored ? stored.range : '30'));
                return {
                    focus: focusOk ? focus : (search ? 'search_only' : 'work'),
                    range,
                    ma: pickDefaultMAWindowForDays(range === 'all' ? 366 : Number(range)),
                    search,
                };
            } catch (e) {
                return null;
            }
        }

        function applySavedView(view) {
            if (!view) return;
            graphExcludedIds = new Set();
            graphSearchQuery = String(view.search || '');
            if (graphSearchInput) graphSearchInput.value = graphSearchQuery;
            currentRange = normalizeRangeValue(view.range);
            currentDays = currentRange === 'all' ? getAllDaysDefault() : Number(currentRange || 30);
            maWindow = Number(view.ma || 14);
            shouldAutoMAOnNextRender = false;
            syncRangePills();
            syncMAPills();
            setFocus(view.focus || 'work', { fetch: false });
            fetchGraphData({ includeTasks: Boolean(graphSearchQuery) });
        }

        async function saveCurrentView() {
            const search = (graphSearchQuery || '').trim();
            const suggested = [getFocusLabel(graphFocusValue), search, rangeLabelFor(currentRange)].filter(Boolean).join(' · ');
            const name = window.prompt('Name this view', suggested);
            if (name === null) return;
            try {
                const resp = await fetch('/api/graph-views', {
                    method: 'POST',
                    credentials: 'include',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name, focus: graphFocusValue, search, range: currentRange, ma: maWindow })
                });
                const data = await resp.json().catch(() => ({}));
                if (!resp.ok) throw new Error(data.error || `HTTP ${resp.status}`);
                graphViews.push(data.view);
                renderSavedViews();
                if (window.showSuccessToast) window.showSuccessToast('View saved');
            } catch (e) {
                if (window.showErrorToast) window.showErrorToast(e.message || 'Could not save view');
            }
        }

        if (graphSaveViewBtn) graphSaveViewBtn.addEventListener('click', saveCurrentView);
        if (graphSavedViewsList) {
            graphSavedViewsList.addEventListener('click', async (event) => {
                const del = event.target.closest('[data-delete-view-id]');
                if (del) {
                    const id = Number(del.dataset.deleteViewId);
                    try {
                        const resp = await fetch(`/api/graph-views/${id}`, { method: 'DELETE', credentials: 'include' });
                        if (!resp.ok && resp.status !== 404) throw new Error(`HTTP ${resp.status}`);
                        // 404: already gone (e.g. deleted in another tab) - drop it here too.
                        graphViews = graphViews.filter(v => Number(v.id) !== id);
                        renderSavedViews();
                    } catch (e) {
                        if (window.showErrorToast) window.showErrorToast('Could not delete the view. Try again.');
                    }
                    return;
                }
                const apply = event.target.closest('[data-view-id]');
                if (apply) applySavedView(graphViews.find(v => Number(v.id) === Number(apply.dataset.viewId)));
            });
        }
        loadSavedViews();

        const focusOptions = () => Array.from(document.querySelectorAll('.graph-focus-option'));
        function setFocusMenuOpen(open, { focusOption = false } = {}) {
            graphFocusMenu.classList.toggle('hidden', !open);
            graphFocusBtn.setAttribute('aria-expanded', String(open));
            if (open && focusOption) {
                (focusOptions().find(o => o.dataset.active === 'true') || focusOptions()[0])?.focus();
            }
        }

        graphFocusBtn.addEventListener('click', () => {
            setFocusMenuOpen(graphFocusMenu.classList.contains('hidden'));
        });
        // Keyboard: Down/Up open the menu and move between options, Escape closes it.
        graphFocusBtn.addEventListener('keydown', (event) => {
            if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
                event.preventDefault();
                setFocusMenuOpen(true, { focusOption: true });
            }
        });
        graphFocusMenu.addEventListener('keydown', (event) => {
            const options = focusOptions();
            const index = options.indexOf(document.activeElement);
            if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
                event.preventDefault();
                const step = event.key === 'ArrowDown' ? 1 : -1;
                options[(index + step + options.length) % options.length]?.focus();
            } else if (event.key === 'Home' || event.key === 'End') {
                event.preventDefault();
                options[event.key === 'Home' ? 0 : options.length - 1]?.focus();
            } else if (event.key === 'Escape') {
                event.preventDefault();
                event.stopPropagation();
                setFocusMenuOpen(false);
                graphFocusBtn.focus();
            } else if (event.key === 'Tab') {
                setFocusMenuOpen(false);
            }
        });

        document.querySelectorAll('.graph-focus-option').forEach(option => {
            option.addEventListener('click', () => {
                setFocusMenuOpen(false);
                graphFocusBtn.focus();
                graphExcludedIds = new Set();
                setFocus(option.dataset.value || 'work');
            });
        });

        document.addEventListener('click', (event) => {
            if (!event.target.closest('#graphFocusBtn') && !event.target.closest('#graphFocusMenu')) {
                setFocusMenuOpen(false);
            }
            if (!event.target.closest('#graphSearchWrap') && !event.target.closest('#graphSearchSuggestions')) {
                hideGraphSearchSuggestions();
            }
            if (graphHelpWrapper && !event.target.closest('#graphHelpWrapper')) {
                graphHelpTooltip.classList.add('hidden');
            }
            if (graphPointDetail && !graphPointDetail.classList.contains('hidden')) {
                const clickedDetail = Boolean(event.target.closest('#graphPointDetail'));
                const clickedCanvas = Boolean(event.target.closest('#graphCanvas'));
                if (!clickedDetail && !clickedCanvas) {
                    closeGraphPointDetail();
                }
            }
        });

        if (graphPointDetail) {
            graphPointDetail.addEventListener('click', (event) => {
                event.stopPropagation();
                const dateStr = graphPointDetail.dataset.date;
                if (!dateStr) return;
                navigateToGraphDate(dateStr);
            });
        }

        if (graphHelpBtn && graphHelpTooltip) {
            graphHelpBtn.addEventListener('click', (event) => {
                event.stopPropagation();
                graphHelpTooltip.classList.toggle('hidden');
            });
        }

        document.querySelectorAll('.range-pill').forEach(btn => {
            btn.addEventListener('click', () => {
                const nextRange = normalizeRangeValue(btn.dataset.range);
                const nextDays = nextRange === 'all' ? getAllDaysDefault() : Number(nextRange || 30);
                if (nextRange === currentRange && nextDays === currentDays) return;
                currentRange = nextRange;
                currentDays = nextDays;
                shouldAutoMAOnNextRender = true;
                syncRangePills();
                if (lastGraphPayload && lastGraphDays >= currentDays) {
                    if (shouldAutoMAOnNextRender) {
                        maWindow = pickDefaultMAWindowForDays(
                            getDisplayedSpanDaysForRange(lastGraphPayload.labels, lastGraphPayload.values, currentRange)
                        );
                        syncMAPills();
                        shouldAutoMAOnNextRender = false;
                    }
                    updateChart(lastGraphPayload, currentMetric, currentDays);
                    return;
                }
                fetchGraphData();
            });
        });

        document.querySelectorAll('.ma-pill').forEach(btn => {
            btn.addEventListener('click', () => {
                maWindow = Number(btn.dataset.ma || 7);
                syncMAPills();
                fetchGraphData();
            });
        });

        graphSearchApply.addEventListener('click', async () => {
            const originalText = graphSearchApply.textContent;
            graphSearchApply.disabled = true;
            graphSearchApply.textContent = 'Applying...';
            const query = (graphSearchInput.value || '').trim();
            graphExcludedIds = new Set();
            graphSearchQuery = query;
            await fetchGraphData({ includeTasks: Boolean(query) });
            await recordGraphSuggestionUsage();
            graphSearchApply.textContent = originalText || 'Apply';
            graphSearchApply.disabled = false;
        });

        graphSearchInput.addEventListener('focus', async () => {
            await loadGraphSearchSuggestions();
            renderGraphSearchSuggestions();
        });

        graphSearchInput.addEventListener('input', () => {
            renderGraphSearchSuggestions();
        });

        graphSearchInput.addEventListener('blur', () => {
            window.setTimeout(() => {
                const active = document.activeElement;
                const inSuggestions = Boolean(active && graphSearchSuggestions && graphSearchSuggestions.contains(active));
                if (!inSuggestions) {
                    hideGraphSearchSuggestions();
                }
            }, 120);
        });

        if (window.visualViewport) {
            let lastGraphViewportHeight = window.visualViewport.height;
            window.visualViewport.addEventListener('resize', () => {
                const currentHeight = window.visualViewport.height;
                const keyboardLikelyClosed = currentHeight - lastGraphViewportHeight > 120;
                lastGraphViewportHeight = currentHeight;
                if (keyboardLikelyClosed) {
                    hideGraphSearchSuggestions();
                }
            });
        }

        graphSearchInput.addEventListener('keydown', (event) => {
            const hasSuggestions = graphSearchSuggestions && !graphSearchSuggestions.classList.contains('hidden');
            if (event.key === 'ArrowDown' && hasSuggestions) {
                event.preventDefault();
                setActiveGraphSuggestion(graphSuggestionActiveIndex + 1);
                return;
            }
            if (event.key === 'ArrowUp' && hasSuggestions) {
                event.preventDefault();
                setActiveGraphSuggestion(graphSuggestionActiveIndex - 1);
                return;
            }
            if (event.key === 'Enter') {
                if (hasSuggestions && graphSuggestionActiveIndex >= 0) {
                    event.preventDefault();
                    const activeButton = graphSearchSuggestions.querySelectorAll('.graph-search-suggestion')[graphSuggestionActiveIndex];
                    if (activeButton) {
                        activeButton.click();
                        return;
                    }
                }
                event.preventDefault();
                hideGraphSearchSuggestions();
                graphSearchApply.click();
            }
            if (event.key === 'Escape' && hasSuggestions) {
                event.preventDefault();
                hideGraphSearchSuggestions();
            }
        });

        graphSearchClear.addEventListener('click', () => {
            graphExcludedIds = new Set();
            graphSearchQuery = '';
            graphSearchInput.value = '';
            hideGraphSearchSuggestions();
            fetchGraphData();
        });

        reviewGraphTasks.addEventListener('click', () => {
            if (!graphTasks.length) {
                fetchGraphData({ includeTasks: true, openModal: true });
            } else {
                openGraphTaskModal();
            }
        });

        closeGraphTasks.addEventListener('click', closeGraphTaskModal);

        if (graphTasksList) {
            graphTasksList.addEventListener('click', (event) => {
                const editBtn = event.target.closest('[data-action="edit-task"]');
                if (editBtn) {
                    const taskId = parseInt(editBtn.dataset.taskId || '0', 10);
                    if (taskId) openGraphEditPanel(getGraphTaskById(taskId));
                    return;
                }
                const deleteBtn = event.target.closest('[data-action="delete-task"]');
                if (deleteBtn) {
                    const taskId = parseInt(deleteBtn.dataset.taskId || '0', 10);
                    if (taskId) openGraphDeleteConfirm(getGraphTaskById(taskId));
                }
            });
        }

        const closeGraphEdit = document.getElementById('closeGraphEditPanel');
        const cancelGraphEdit = document.getElementById('cancelGraphEditTask');
        if (closeGraphEdit) closeGraphEdit.onclick = closeGraphEditPanel;
        if (cancelGraphEdit) cancelGraphEdit.onclick = closeGraphEditPanel;
        const closeGraphDelete = document.getElementById('closeGraphDeleteConfirm');
        const cancelGraphDelete = document.getElementById('cancelGraphDeleteTask');
        if (closeGraphDelete) closeGraphDelete.onclick = closeGraphDeleteConfirm;
        if (cancelGraphDelete) cancelGraphDelete.onclick = closeGraphDeleteConfirm;

        const graphEditForm = document.getElementById('graphTaskEditForm');
        const graphEditStartMode = document.getElementById('graphEditStartMode');
        const graphEditStartRaw = document.getElementById('graphEditStartRaw');
        const graphEditEndMode = document.getElementById('graphEditEndMode');
        const graphEditEndRaw = document.getElementById('graphEditEndRaw');

        const fillGraphEditStartFromPrev = async () => {
            const task = window.__graphEditingTask;
            if (!task) return;
            const neighbors = getGraphTaskNeighbors(task);
            if (!neighbors.prev) {
                if (window.showWarningToast) window.showWarningToast('No previous task found for this day.');
                if (graphEditStartMode) graphEditStartMode.value = 'manual';
                return;
            }
            if (graphEditStartRaw) {
                graphEditStartRaw.value = formatGraphTaskDateTime(neighbors.prev.date, neighbors.prev.end_time);
            }
        };

        const fillGraphEditEndFromNext = async () => {
            const task = window.__graphEditingTask;
            if (!task) return;
            const neighbors = getGraphTaskNeighbors(task);
            if (!neighbors.next) {
                if (window.showWarningToast) window.showWarningToast('No next task found for this day.');
                if (graphEditEndMode) graphEditEndMode.value = 'manual';
                return;
            }
            if (graphEditEndRaw) {
                graphEditEndRaw.value = formatGraphTaskDateTime(neighbors.next.date, neighbors.next.start_time);
            }
        };

        if (graphEditStartMode && !graphEditStartMode.__bound) {
            graphEditStartMode.addEventListener('change', async () => {
                if (graphEditStartMode.value === 'prev_end') {
                    await fillGraphEditStartFromPrev();
                }
            });
            graphEditStartMode.__bound = true;
        }
        if (graphEditEndMode && !graphEditEndMode.__bound) {
            graphEditEndMode.addEventListener('change', async () => {
                if (graphEditEndMode.value === 'next_start') {
                    await fillGraphEditEndFromNext();
                }
            });
            graphEditEndMode.__bound = true;
        }
        if (graphEditStartRaw && !graphEditStartRaw.__bound) {
            graphEditStartRaw.addEventListener('input', () => {
                if (graphEditStartMode) graphEditStartMode.value = 'manual';
            });
            graphEditStartRaw.__bound = true;
        }
        if (graphEditEndRaw && !graphEditEndRaw.__bound) {
            graphEditEndRaw.addEventListener('input', () => {
                if (graphEditEndMode) graphEditEndMode.value = 'manual';
            });
            graphEditEndRaw.__bound = true;
        }

        if (graphEditForm) {
            graphEditForm.addEventListener('submit', async (event) => {
                event.preventDefault();
                const taskId = parseInt(document.getElementById('graphEditTaskId')?.value || '0', 10);
                if (!taskId) return;
                const name = String(document.getElementById('graphEditTaskName')?.value || '').trim();
                const start = String(document.getElementById('graphEditStartRaw')?.value || '').trim();
                const end = String(document.getElementById('graphEditEndRaw')?.value || '').trim();
                const tags = String(document.getElementById('graphEditTaskTags')?.value || '').trim();
                const important = Boolean(document.getElementById('graphEditTaskImportant')?.checked);
                const urgent = Boolean(document.getElementById('graphEditTaskUrgent')?.checked);
                if (!name) {
                    if (window.showErrorToast) {
                        window.showErrorToast('Task name is required');
                    } else {
                        alert('Task name is required');
                    }
                    return;
                }
                if (!start) {
                    if (window.showErrorToast) {
                        window.showErrorToast('Start time is required');
                    } else {
                        alert('Start time is required');
                    }
                    return;
                }
                if (!end) {
                    if (window.showErrorToast) {
                        window.showErrorToast('End time is required');
                    } else {
                        alert('End time is required');
                    }
                    return;
                }
                const saveBtn = document.getElementById('saveGraphTaskChanges');
                const originalText = saveBtn ? saveBtn.textContent : '';
                if (saveBtn) {
                    saveBtn.textContent = 'Saving...';
                    saveBtn.disabled = true;
                }
                try {
                    const response = await fetch(`/api/tasks/${taskId}?by=sheety`, {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ task: name, start, end, tag: tags, urgent, important })
                    });
                    const contentType = response.headers.get('content-type') || '';
                    const result = contentType.includes('application/json') ? await response.json() : null;
                    if (!response.ok) {
                        throw new Error(result?.error || `HTTP ${response.status}`);
                    }
                    if (result?.failover && window.showApiFailoverNotification) {
                        window.showApiFailoverNotification(result.failover.from, result.failover.to);
                    }
                    if (window.showSuccessToast) {
                        window.showSuccessToast('Task updated');
                    }
                    closeGraphEditPanel();
                    await refreshGraphTaskModal();
                } catch (error) {
                    const message = getNetworkErrorMessage(error, 'update the task');
                    if (window.showErrorToast) {
                        window.showErrorToast(message);
                    } else {
                        alert(message);
                    }
                } finally {
                    if (saveBtn) {
                        saveBtn.textContent = originalText || 'Save changes';
                        saveBtn.disabled = false;
                    }
                }
            });
        }

        const confirmGraphDelete = document.getElementById('confirmGraphDeleteTask');
        if (confirmGraphDelete) {
            confirmGraphDelete.addEventListener('click', async () => {
                const taskId = Number(graphPendingDeleteTaskId || 0);
                if (!taskId) return;
                confirmGraphDelete.disabled = true;
                const originalText = confirmGraphDelete.textContent;
                confirmGraphDelete.textContent = 'Deleting...';
                try {
                    const response = await fetch(`/api/tasks/${taskId}?by=sheety`, { method: 'DELETE' });
                    const contentType = response.headers.get('content-type') || '';
                    const result = contentType.includes('application/json') ? await response.json() : null;
                    if (!response.ok) {
                        throw new Error(result?.error || `HTTP ${response.status}`);
                    }
                    if (result?.failover && window.showApiFailoverNotification) {
                        window.showApiFailoverNotification(result.failover.from, result.failover.to);
                    }
                    if (window.showSuccessToast) {
                        window.showSuccessToast('Task deleted');
                    }
                    closeGraphDeleteConfirm();
                    await refreshGraphTaskModal();
                } catch (error) {
                    const message = getNetworkErrorMessage(error, 'delete the task');
                    if (window.showErrorToast) {
                        window.showErrorToast(message);
                    } else {
                        alert(message);
                    }
                } finally {
                    confirmGraphDelete.textContent = originalText || 'Delete';
                    confirmGraphDelete.disabled = false;
                }
            });
        }

        graphTaskModal.addEventListener('click', (event) => {
            if (event.target === graphTaskModal) {
                closeGraphTaskModal();
            }
        });

        document.addEventListener('keydown', (event) => {
            if (!graphTaskModal || !graphTaskModal.classList.contains('active')) return;
            if (event.key === 'Escape') {
                // Close an open Edit/Delete panel first rather than the whole list.
                const deletePanel = document.getElementById('graphTaskDeleteConfirm');
                const editPanel = document.getElementById('graphTaskEditPanel');
                if (deletePanel && !deletePanel.classList.contains('hidden')) {
                    event.preventDefault();
                    closeGraphDeleteConfirm();
                    graphTaskModal.querySelector('button')?.focus();
                    return;
                }
                if (editPanel && !editPanel.classList.contains('hidden')) {
                    event.preventDefault();
                    closeGraphEditPanel();
                    graphTaskModal.querySelector('button')?.focus();
                    return;
                }
                closeGraphTaskModal();
            }
            if (event.key === 'Tab') {
                trapModalFocus(graphTaskModal, event);
            }
        });

        const dashboardUrl = GRAPHS_CONFIG.dashboardUrl;
        const adminUrl = GRAPHS_CONFIG.adminUrl;
        const navHome = document.getElementById('navHome');
        const navMatrix = document.getElementById('navMatrix');
        const navTags = document.getElementById('navTags');
        const navGraphs = document.getElementById('navGraphs');
        const navInsights = document.getElementById('navInsights');
        
        function setActiveGraphNav(id) {
            [navHome, navMatrix, navTags, navInsights, navGraphs].forEach(btn => {
                if (!btn) return;
                if (btn.id === id) {
                    btn.classList.remove('text-gray-600', 'bg-transparent');
                    btn.classList.add('text-gray-900', 'bg-slate-100');
                } else {
                    btn.classList.remove('text-gray-900', 'bg-slate-100');
                    btn.classList.add('text-gray-600', 'bg-transparent');
                }
            });
        }
        
        setActiveGraphNav('navGraphs');
        
        if (navHome) navHome.onclick = () => { window.location.href = `${dashboardUrl}#top`; };
        if (navMatrix) navMatrix.onclick = () => { window.location.href = `${dashboardUrl}#matrix`; };
        if (navTags) navTags.onclick = () => { window.location.href = `${dashboardUrl}#tags`; };
        if (navInsights) navInsights.onclick = () => { window.location.href = `${dashboardUrl}#insights`; };
        if (navGraphs) navGraphs.onclick = () => { window.location.href = GRAPHS_CONFIG.graphsUrl; };

        let graphShortcutToast = null;
        document.addEventListener('keydown', (event) => {
            const tag = event.target?.tagName;
            if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || event.target?.isContentEditable) return;
            if (event.metaKey || event.ctrlKey || event.altKey) return;
            if (graphTaskModal && graphTaskModal.classList.contains('active')) return;
            const key = event.key.toLowerCase();
            const rangePills = Array.from(document.querySelectorAll('.range-pill'));
            const reviewBtn = document.getElementById('reviewGraphTasks');
            const canReview = reviewBtn && !reviewBtn.classList.contains('hidden') && !reviewBtn.disabled;
            if (key === 'd') {
                window.location.href = dashboardUrl;
            } else if (key === 's') {
                window.location.href = GRAPHS_CONFIG.settingsUrl;
            } else if (key === 'r' && canReview) {
                event.preventDefault();
                reviewBtn.click();
            } else if (key === 'a' && adminUrl) {
                window.location.href = adminUrl;
            } else if (key === '/') {
                event.preventDefault();
                graphSearchInput?.focus();
            } else if (/^[1-9]$/.test(key) && rangePills[Number(key) - 1]) {
                event.preventDefault();
                rangePills[Number(key) - 1].click();
            } else if (key === '?') {
                event.preventDefault();
                if (graphShortcutToast && document.body.contains(graphShortcutToast) && graphShortcutToast.__removeToast) {
                    graphShortcutToast.__removeToast();
                    graphShortcutToast = null;
                    return;
                }
                if (!window.showToast) return;
                const row = (keys, label) => `<div class="flex items-center gap-2">${keys.map(k => `<kbd class="toast-kbd">${k}</kbd>`).join('')}<span class="toast-kbd-label">${label}</span></div>`;
                graphShortcutToast = window.showToast(`
                    <div class="space-y-3">
                        <div class="text-xs uppercase tracking-[0.2em] text-white/80 font-semibold">Keyboard Shortcuts</div>
                        <div class="space-y-2 text-sm">
                            ${row(['/'], 'Search activities')}
                            ${canReview ? row(['R'], 'Review tasks') : ''}
                            ${row([`1–${rangePills.length}`], 'Time range (7 days … All)')}
                            ${row(['D'], 'Dashboard')}
                            ${row(['S'], 'Settings')}
                            ${adminUrl ? row(['A'], 'Admin') : ''}
                        </div>
                    </div>
                `, 'shortcut', 7000);
            }
        });

        syncRangePills();
        syncMAPills();
        const urlGraphState = loadGraphStateFromUrl();
        if (urlGraphState) {
            // Applied once; a reload then reopens wherever the user went from here.
            try { history.replaceState(null, '', window.location.pathname); } catch (e) {}
        }
        const restoredGraphState = urlGraphState || loadGraphState();
        if (restoredGraphState) {
            applySavedView(restoredGraphState);
        } else {
            fetchGraphData();
            setFocus('work', { fetch: false });
        }

        // Re-render chart when theme changes so axis colors update
        new MutationObserver(function(mutations) {
            mutations.forEach(function(m) {
                if (m.attributeName === 'data-theme' && chartInstance && lastGraphPayload) {
                    chartInstance.destroy();
                    chartInstance = null;
                    updateChart(lastGraphPayload, currentMetric, currentDays);
                }
            });
        }).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    