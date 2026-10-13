// Dashboard page script (moved out of templates/dashboard.html so browsers cache it).
// Per-request values come from the JSON block #dashboardConfig rendered by the template.
const DASHBOARD_CONFIG = JSON.parse(document.getElementById('dashboardConfig').textContent || '{}');
        function escapeHtml(value) {
            return String(value ?? '').replace(/[&<>"']/g, ch => ({
                '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
            }[ch]));
        }
        window.escapeHtml = escapeHtml;

        // Global variables
        window.currentDate = DASHBOARD_CONFIG.currentDate;
        window.currentPeriod = DASHBOARD_CONFIG.period;
        window.periodStart = DASHBOARD_CONFIG.periodStart;
        window.periodEnd = DASHBOARD_CONFIG.periodEnd;
        window.avgStart = DASHBOARD_CONFIG.avgStart;
        window.avgEnd = DASHBOARD_CONFIG.avgEnd;
        const rawSyncStats = document.body?.dataset?.syncStats || '{}';
        try {
            window.syncStats = JSON.parse(rawSyncStats);
        } catch (e) {
            window.syncStats = {};
        }

        // Define functions globally
        window.changePeriod = function(period) {
            window.currentPeriod = period;
            window.periodEnd = window.computePeriodEnd(window.currentDate, period);
            window.updateTodayButtons();
            window.location.href = `/?date=${window.currentDate}&period=${period}`;
        };

        window.changeDate = function(date) {
            window.currentDate = date;
            window.periodEnd = window.computePeriodEnd(date, window.currentPeriod);
            window.updateTodayButtons();
            window.location.href = `/?date=${date}&period=${window.currentPeriod}`;
        };

        const exportFormatModal = document.getElementById('exportFormatModal');

        window.getLocalIsoDate = function() {
            const now = new Date();
            const y = now.getFullYear();
            const m = String(now.getMonth() + 1).padStart(2, '0');
            const d = String(now.getDate()).padStart(2, '0');
            return `${y}-${m}-${d}`;
        };

        window.normalizeDateString = function(value) {
            const raw = String(value || '').trim();
            if (!raw) return '';
            const match = raw.match(/^(\d{4})-(\d{2})-(\d{2})$/);
            if (match) return match[0];
            const parsed = new Date(raw);
            if (Number.isNaN(parsed.getTime())) return '';
            const y = parsed.getFullYear();
            const m = String(parsed.getMonth() + 1).padStart(2, '0');
            const d = String(parsed.getDate()).padStart(2, '0');
            return `${y}-${m}-${d}`;
        };

        window.toIsoDateString = function(dateObj) {
            if (!(dateObj instanceof Date) || Number.isNaN(dateObj.getTime())) return '';
            const y = dateObj.getFullYear();
            const m = String(dateObj.getMonth() + 1).padStart(2, '0');
            const d = String(dateObj.getDate()).padStart(2, '0');
            return `${y}-${m}-${d}`;
        };

        window.computePeriodEnd = function(dateStr, period) {
            const normalized = window.normalizeDateString(dateStr || window.currentDate || window.getLocalIsoDate());
            if (!normalized) return '';
            const [year, month, day] = normalized.split('-').map(Number);
            const base = new Date(year, month - 1, day);
            if (Number.isNaN(base.getTime())) return '';
            const mode = period || window.currentPeriod || 'day';
            if (mode === 'week') {
                const idx = base.getDay();
                const start = new Date(base);
                start.setDate(base.getDate() - idx);
                const end = new Date(start);
                end.setDate(start.getDate() + 6);
                return window.toIsoDateString(end);
            }
            if (mode === 'month') {
                const end = new Date(year, month, 0);
                return window.toIsoDateString(end);
            }
            return normalized;
        };

        window.updateTodayButtons = function() {
            const today = window.getLocalIsoDate();
            const periodEnd = window.normalizeDateString(window.periodEnd) || window.computePeriodEnd(window.currentDate, window.currentPeriod);
            const shouldShow = Boolean(periodEnd) && periodEnd < today;
            const todayBtn = document.getElementById('todayBtn');
            if (todayBtn) {
                todayBtn.style.display = shouldShow ? 'inline-flex' : 'none';
            }
        };

        window.goToToday = function() {
            const today = window.getLocalIsoDate();
            window.location.href = `/?date=${encodeURIComponent(today)}&period=${encodeURIComponent(window.currentPeriod || 'day')}`;
        };

        window.updateTodayButtons();
        window.addEventListener('load', () => {
            window.updateTodayButtons();
            const scroller = document.getElementById('weekScroller');
            if (!scroller || scroller.scrollWidth <= scroller.clientWidth + 1) return;
            const selected = scroller.querySelector('[data-selected-day="true"]');
            if (!selected) return;
            // offsetLeft is relative to the offsetParent (not the scroller), so measure via rects.
            const offsetInScroller = selected.getBoundingClientRect().left - scroller.getBoundingClientRect().left + scroller.scrollLeft;
            const targetLeft = offsetInScroller - (scroller.clientWidth / 2) + (selected.clientWidth / 2);
            scroller.scrollTo({ left: Math.max(0, targetLeft), behavior: 'smooth' });
        });
        document.addEventListener('DOMContentLoaded', () => {
            window.updateTodayButtons();
        });
        window.addEventListener('resize', () => {
            window.updateTodayButtons();
        });

        window.toggleDatePicker = function() {
            const dropdown = document.getElementById('dateDropdown');
            if (!dropdown) return;
            const open = dropdown.classList.toggle('hidden') === false;
            document.getElementById('datePickerBtn')?.setAttribute('aria-expanded', String(open));
        };

        // Parse 'YYYY-MM-DD' as a *local* calendar date. new Date('YYYY-MM-DD') is UTC
        // midnight, which is the previous day anywhere west of UTC.
        window.parseLocalDate = function(iso) {
            const [y, m, d] = String(iso || '').split('-').map(Number);
            if (!y || !m || !d) return new Date();
            return new Date(y, m - 1, d);
        };

        window.navigateMonth = function(offset) {
            const cursor = window.dateCursor || window.parseLocalDate(window.currentDate);
            // Anchor on the 1st so moving from the 29th-31st never skips a month.
            window.dateCursor = new Date(cursor.getFullYear(), cursor.getMonth() + offset, 1);
            window.renderDateGrid();
        };

        window.renderDateGrid = function() {
            const grid = document.getElementById('dateGrid');
            const label = document.getElementById('dateDropdownLabel');
            if (!grid || !label) return;

            const base = window.dateCursor ? new Date(window.dateCursor) : window.parseLocalDate(window.currentDate);
            const year = base.getFullYear();
            const month = base.getMonth();

            const first = new Date(year, month, 1);
            const startDay = first.getDay();
            const last = new Date(year, month + 1, 0);
            const totalDays = last.getDate();

            label.textContent = base.toLocaleString('default', { month: 'long', year: 'numeric' });

            grid.innerHTML = '';
            for (let i = 0; i < startDay; i++) {
                const empty = document.createElement('div');
                empty.className = 'h-8';
                grid.appendChild(empty);
            }

            const selected = window.parseLocalDate(window.currentDate);
            const todayIso = window.getLocalIsoDate();
            for (let day = 1; day <= totalDays; day++) {
                const d = new Date(year, month, day);
                const btn = document.createElement('button');
                const isSelected = d.toDateString() === selected.toDateString();
                const iso = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
                const isToday = iso === todayIso;
                btn.type = 'button';
                btn.textContent = day;
                btn.setAttribute('aria-label', d.toLocaleDateString('default', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' }) + (isToday ? ' (today)' : ''));
                if (isSelected) btn.setAttribute('aria-current', 'date');
                btn.className = [
                    'h-8 w-8 flex items-center justify-center rounded-full text-xs',
                    isSelected
                        ? 'bg-[#111827] text-[#F8D574] shadow'
                        : 'text-gray-700 hover:bg-[#F5EDE1]',
                    (isToday && !isSelected) ? 'ring-1 ring-amber-400 font-semibold' : ''
                ].join(' ');
                btn.onclick = function() {
                    window.changeDate(iso);
                };
                grid.appendChild(btn);
            }
        };

        function updateCreateTagChipStyles() {
            const tagInput = document.getElementById('createTaskTags');
            const chips = document.querySelectorAll('.create-tag-chip');
            if (!tagInput || !chips.length) return;
            const tags = String(tagInput.value || '')
                .split(',')
                .map(t => t.trim())
                .filter(Boolean);
            chips.forEach(chip => {
                const tag = chip.dataset.createTag || '';
                const active = tags.some(t => t.toLowerCase() === tag.toLowerCase());
                chip.classList.toggle('active', active);
                chip.setAttribute('aria-pressed', active ? 'true' : 'false');
                chip.classList.toggle('bg-emerald-600', active);
                chip.classList.toggle('text-white', active);
                chip.classList.toggle('border-emerald-600', active);
                chip.classList.toggle('bg-white/80', !active);
                chip.classList.toggle('text-gray-600', !active);
                chip.classList.toggle('border-slate-200', !active);
            });
        }

        // Picking a known name from the autocomplete fills in its usual tags and
        // priority, but only while those are still untouched.
        (function bindTaskNameSuggestions() {
            const nameInput = document.getElementById('createTaskName');
            const dataEl = document.getElementById('taskSuggestionData');
            if (!nameInput || !dataEl) return;
            let byName = {};
            try {
                (JSON.parse(dataEl.textContent || '[]') || []).forEach(item => {
                    byName[String(item.name || '').trim().toLowerCase()] = item;
                });
            } catch (e) {
                byName = {};
            }
            const apply = () => {
                const item = byName[String(nameInput.value || '').trim().toLowerCase()];
                if (!item) return;
                const tagInput = document.getElementById('createTaskTags');
                const importantInput = document.getElementById('createTaskImportant');
                const urgentInput = document.getElementById('createTaskUrgent');
                const untouched = tagInput && !tagInput.value.trim()
                    && !(importantInput && importantInput.checked) && !(urgentInput && urgentInput.checked);
                if (!untouched) return;
                tagInput.value = item.tags || '';
                if (importantInput) importantInput.checked = Boolean(item.important);
                if (urgentInput) urgentInput.checked = Boolean(item.urgent);
                updateCreateTagChipStyles();
                updateCreatePriorityChips();
            };
            nameInput.addEventListener('change', apply);
            // Choosing from the list (not typing) fires input without a typing inputType.
            nameInput.addEventListener('input', (event) => {
                if (!event.inputType || event.inputType === 'insertReplacementText') apply();
            });
        })();

        function updateCreatePriorityChips() {
            const importantInput = document.getElementById('createTaskImportant');
            const urgentInput = document.getElementById('createTaskUrgent');
            document.querySelectorAll('.create-priority-chip').forEach(chip => {
                const key = chip.dataset.createPriority || '';
                const active = key === 'important'
                    ? Boolean(importantInput?.checked)
                    : Boolean(urgentInput?.checked);
                const activeClasses = key === 'urgent'
                    ? ['bg-red-500', 'text-white', 'border-red-500']
                    : ['bg-emerald-600', 'text-white', 'border-emerald-600'];
                chip.classList.toggle('active', active);
                chip.setAttribute('aria-pressed', active ? 'true' : 'false');
                chip.classList.toggle(activeClasses[0], active);
                chip.classList.toggle(activeClasses[1], active);
                chip.classList.toggle(activeClasses[2], active);
                chip.classList.toggle('bg-white/80', !active);
                chip.classList.toggle('text-gray-600', !active);
                chip.classList.toggle('border-slate-200', !active);
            });
        }

        function syncCreateDurationFromTimes() {
            const startInput = document.getElementById('createTaskStart');
            const endInput = document.getElementById('createTaskEnd');
            const durationInput = document.getElementById('createTaskDuration');
            if (!startInput || !endInput || !durationInput) return;
            if (syncCreateDurationFromTimes.__locked) return;
            const startMinutes = inputTimeToMinutes(startInput.value);
            const endMinutes = inputTimeToMinutes(endInput.value);
            if (startMinutes == null || endMinutes == null) return;
            const diff = endMinutes - startMinutes;
            if (diff <= 0) return;
            syncCreateDurationFromTimes.__locked = true;
            durationInput.value = Number((diff / 60).toFixed(2));
            syncCreateDurationFromTimes.__locked = false;
        }

        function syncCreateEndFromDuration() {
            const startInput = document.getElementById('createTaskStart');
            const endInput = document.getElementById('createTaskEnd');
            const durationInput = document.getElementById('createTaskDuration');
            if (!startInput || !endInput || !durationInput) return;
            if (syncCreateEndFromDuration.__locked) return;
            const startMinutes = inputTimeToMinutes(startInput.value);
            const durationHours = Number(durationInput.value);
            if (startMinutes == null || !Number.isFinite(durationHours) || durationHours <= 0) return;
            const endMinutes = startMinutes + Math.round(durationHours * 60);
            syncCreateEndFromDuration.__locked = true;
            endInput.value = minutesToInputTime(endMinutes);
            syncCreateEndFromDuration.__locked = false;
        }

        function renderCreateOverlap(overlaps) {
            const container = document.getElementById('createTaskOverlap');
            if (!container) return;
            if (!Array.isArray(overlaps) || !overlaps.length) {
                container.classList.add('hidden');
                container.innerHTML = '';
                return;
            }
            const items = overlaps.map(item => {
                const label = escapeHtml(`${item.task || 'Task'} · ${item.start_time} - ${item.end_time}`);
                return `
                    <div class="flex flex-wrap items-center justify-between gap-2">
                        <div class="text-xs text-amber-900 font-semibold">${label}</div>
                        <button type="button" class="px-2.5 py-1 rounded-full border border-amber-300 text-[11px] font-semibold text-amber-700 hover:bg-white" data-overlap-id="${Number(item.id) || 0}">Edit</button>
                    </div>
                `;
            }).join('');
            container.innerHTML = `
                <div class="text-xs font-semibold text-amber-800 mb-2">Overlaps with existing logs. Edit them to make space:</div>
                <div class="space-y-2">${items}</div>
            `;
            container.classList.remove('hidden');
            if (!container.__bound) {
                container.addEventListener('click', (event) => {
                    const btn = event.target.closest('[data-overlap-id]');
                    if (!btn) return;
                    const taskId = Number(btn.dataset.overlapId || 0);
                    if (!taskId) return;
                    const task = window.getModalTaskById ? window.getModalTaskById(taskId) : null;
                    if (task && window.openEditTaskPanel) {
                        window.openEditTaskPanel(task);
                        return;
                    }
                    if (window.showWarningToast) {
                        window.showWarningToast('Could not find the overlapping task. Refresh and try again.');
                    } else {
                        setGlobalLoading(false, 'Could not find the overlapping task.');
                    }
                });
                container.__bound = true;
            }
        }

        window.viewFullDay = function() {
            const period = window.currentPeriod || 'day';
            const periodMap = { 'day': 'Day', 'week': 'Week', 'month': 'Month' };
            const periodLabel = periodMap[period] || 'Day';
            window.applyFilter('all', 'Full ' + periodLabel + ' Log', '', 'tags');
        };

        window.viewActivity = function(name) {
            const period = window.currentPeriod || 'day';
            const periodMap = { 'day': 'Day', 'week': 'Week', 'month': 'Month' };
            const clean = String(name || '').replace(/["']/g, ' ').replace(/\s+/g, ' ').trim();
            // 'only': exactly the activity the row counted, not every task containing its name.
            window.pendingModalQuery = clean ? `only "${clean}"` : '';
            window.applyFilter('all', `${name} · ${periodMap[period] || 'Day'}`, '', 'tags');
        };

        window.toggleDropdown = function() {};

        window.closeDropdown = function() {};

        window.viewMatrixQuadrant = function(quadrant, name) {
            window.applyFilter(quadrant, name, '', 'tags');
        };

        window.getPeriodDays = function() {
            try {
                const start = new Date(window.periodStart);
                const end = new Date(window.periodEnd);
                const avgStart = window.avgStart ? new Date(window.avgStart) : start;
                const avgEnd = window.avgEnd ? new Date(window.avgEnd) : end;
                if (
                    Number.isNaN(start.valueOf())
                    || Number.isNaN(end.valueOf())
                    || Number.isNaN(avgStart.valueOf())
                    || Number.isNaN(avgEnd.valueOf())
                ) {
                    return 1;
                }
                const effectiveStart = avgStart > start ? avgStart : start;
                const effectiveEnd = avgEnd < end ? avgEnd : end;
                if (effectiveEnd < effectiveStart) {
                    return 1;
                }
                const diff = Math.round((effectiveEnd - effectiveStart) / (1000 * 60 * 60 * 24));
                return Math.max(1, diff + 1);
            } catch (e) {
                return 1;
            }
        };

        window.updateMatrixDisplay = function() {
            const period = window.currentPeriod || 'day';
            const isMultiDay = period === 'week' || period === 'month';
            const mode = isMultiDay ? (window.matrixMode || 'avg') : 'total';
            const days = isMultiDay ? window.getPeriodDays() : 1;
            const useAverage = mode === 'avg' && days > 0;
            const formatHours = (h) => {
                const val = Number(h);
                return Number.isFinite(val) ? val.toFixed(1) : '0.0';
            };

            document.querySelectorAll('.matrix-hours').forEach(el => {
                const total = Number(el.getAttribute('data-total-hours') || 0);
                const display = useAverage ? (total / days) : total;
                el.setAttribute('data-hours', display);
                el.textContent = `${formatHours(display)}h`;
            });

            document.querySelectorAll('[data-summary-hours]').forEach(el => {
                const total = Number(el.getAttribute('data-total-hours') || 0);
                const display = useAverage ? (total / days) : total;
                el.setAttribute('data-hours', display);
                el.textContent = `${formatHours(display)}h`;
            });

            const summaryTitle = document.getElementById('summaryPeriodTitle');
            if (summaryTitle) {
                const totalLabel = summaryTitle.getAttribute('data-total-label') || 'Period total';
                const avgLabel = summaryTitle.getAttribute('data-avg-label') || 'Period avg';
                summaryTitle.textContent = useAverage && isMultiDay ? avgLabel : totalLabel;
            }
            const summaryCaption = document.getElementById('summaryPeriodCaption');
            if (summaryCaption) {
                const totalText = summaryCaption.getAttribute('data-total-text');
                const avgText = summaryCaption.getAttribute('data-avg-text');
                summaryCaption.textContent = useAverage && isMultiDay
                    ? (avgText || summaryCaption.textContent)
                    : (totalText || summaryCaption.textContent);
            }

            const titleEl = document.getElementById('matrixTotalTitle');
            const subtitleEl = document.getElementById('matrixTotalSubtitle');
            if (titleEl && subtitleEl) {
                if (useAverage && isMultiDay) {
                    titleEl.textContent = 'Average';
                    subtitleEl.textContent = 'Per Day';
                } else if (isMultiDay) {
                    titleEl.textContent = 'Total';
                    subtitleEl.textContent = 'Period Total';
                } else {
                    titleEl.textContent = 'Total';
                    subtitleEl.textContent = 'Time Logged';
                }
            }
            if (window.attachHoverSwap) window.attachHoverSwap();
        };

        window.toggleMatrixMode = function() {
            const period = window.currentPeriod || 'day';
            if (period !== 'week' && period !== 'month') return;
            window.matrixMode = window.matrixMode === 'avg' ? 'total' : 'avg';
            window.updateMatrixDisplay();
        };

        // Decimal helpers (global) used by modal and charts
        window.ensureFinite = function(n) {
            const v = Number(n);
            return Number.isFinite(v) ? v : 0;
        };
        window.minutesFromHours = function(h) {
            return Math.round(window.ensureFinite(h) * 60);
        };
        window.formatHours = function(h, decimals = 1) {
            return window.ensureFinite(h).toFixed(decimals);
        };

        window.timeStringToMinutes = function(value) {
            if (!value) return null;
            const parts = String(value).trim().match(/(\d{1,2})(?::(\d{2}))?\s*(AM|PM)?/i);
            if (!parts) return null;
            let hour = Number(parts[1] || 0);
            const minute = Number(parts[2] || 0);
            const meridian = (parts[3] || '').toUpperCase();
            if (meridian === 'PM' && hour < 12) hour += 12;
            if (meridian === 'AM' && hour === 12) hour = 0;
            return (hour * 60) + minute;
        };

        function formatMinutesToTime(minutes) {
            const safe = Math.max(0, Math.min(Math.round(minutes), 24 * 60));
            const normalized = safe === 24 * 60 ? 0 : safe;
            let hour = Math.floor(normalized / 60);
            const minute = normalized % 60;
            const meridian = hour >= 12 ? 'PM' : 'AM';
            hour = hour % 12;
            if (hour === 0) hour = 12;
            return `${hour}:${String(minute).padStart(2, '0')} ${meridian}`;
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
                    : 1;
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
                    const pct = (value / total) * 100;
                    if (pct < minPercent) return;
                    const bg = Array.isArray(dataset.backgroundColor)
                        ? dataset.backgroundColor[idx]
                        : dataset.backgroundColor;
                    const textColor = useAutoColor
                        ? getContrastColor(bg, darkColor, lightColor)
                        : darkColor;
                    ctx.fillStyle = textColor;
                    if (shadowEnabled && textColor === lightColor) {
                        ctx.shadowColor = 'rgba(0, 0, 0, 0.35)';
                        ctx.shadowBlur = 3;
                        ctx.shadowOffsetY = 1;
                    } else {
                        ctx.shadowColor = 'transparent';
                        ctx.shadowBlur = 0;
                        ctx.shadowOffsetY = 0;
                    }
                    const pos = element.tooltipPosition();
                    ctx.fillText(`${pct.toFixed(precision)}%`, pos.x, pos.y);
                });
                ctx.restore();
            }
        };

        const TAG_COLOR_MAP = {
            'Work': '#10B981',
            'Necessity': '#F59E0B',
            'Soul': '#6366F1',
            'Rest': '#C4B5FD',
            'Waste': '#DC2626'
        };

        const SPECIAL_TAGS = Object.keys(TAG_COLOR_MAP);
        // Day notes in this week/month ('YYYY-MM-DD' -> text), shown under full-log day headers.
        const PERIOD_NOTES = DASHBOARD_CONFIG.periodNotes || {};

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

        function hoursToHuman(h) {
            const total = Math.max(0, Math.round(Number(h || 0) * 60));
            const hrs = Math.floor(total / 60);
            const mins = total % 60;
            if (hrs === 0) return `${mins} min`;
            if (mins === 0) return `${hrs} hr`;
            if (mins === 30) return `${hrs}.5 hr`;
            return `${hrs} hr ${mins} min`;
        }
        window.attachHoverSwap = function() {
            document.querySelectorAll('.js-hover-hours').forEach(el => {
                if (el.__hoverBound) return;
                const raw = el.getAttribute('data-hours') || el.textContent;
                const h = Number(raw);
                if (isNaN(h)) return;
                const decimalText = `${window.formatHours(h, 1)}h`;
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
        };

        function setGlobalLoading(isLoading, errorMessage = '') {
            const loadingEl = document.getElementById('globalLoading');
            const errorEl = document.getElementById('globalError');
            const errorText = document.getElementById('globalErrorText');
            if (!loadingEl || !errorEl || !errorText) return;
            if (isLoading) {
                loadingEl.classList.remove('hidden');
                errorEl.classList.add('hidden');
                errorText.textContent = '';
            } else {
                loadingEl.classList.add('hidden');
                if (errorMessage) {
                    errorText.textContent = errorMessage;
                    errorEl.classList.remove('hidden');
                    setTimeout(() => {
                        errorEl.classList.add('hidden');
                    }, 4000);
                }
            }
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

        let lastModalFocus = null;
        function getFocusableElements(container) {
            if (!container) return [];
            return Array.from(
                container.querySelectorAll(
                    'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'
                )
            ).filter(el => el.offsetParent !== null);
        }

        function focusModal(modal) {
            lastModalFocus = document.activeElement;
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

        window.getModalTaskById = function(taskId) {
            if (!window.modalData || !Array.isArray(window.modalData.tasks)) return null;
            return window.modalData.tasks.find(task => {
                const localId = Number(task.id || 0);
                const remoteId = Number(task.sheety_id || 0);
                return localId === Number(taskId) || (remoteId && remoteId === Number(taskId));
            });
        };

        function getLatestTaskEndMinutes(dateValue) {
            if (!window.modalData || !Array.isArray(window.modalData.tasks)) return null;
            const dayTasks = window.modalData.tasks.filter(task => String(task.date || '') === String(dateValue || ''));
            let latest = null;
            dayTasks.forEach(task => {
                const endMinutes = window.timeStringToMinutes(task.end_time);
                if (endMinutes == null) return;
                if (latest == null || endMinutes > latest) {
                    latest = endMinutes;
                }
            });
            return latest;
        }

        function minutesToInputTime(totalMinutes) {
            if (totalMinutes == null || Number.isNaN(totalMinutes)) return '';
            const safe = Math.max(0, Math.min(Math.round(totalMinutes), 24 * 60 - 1));
            const hours = String(Math.floor(safe / 60)).padStart(2, '0');
            const mins = String(safe % 60).padStart(2, '0');
            return `${hours}:${mins}`;
        }

        function inputTimeToMinutes(value) {
            if (!value) return null;
            const parts = String(value).split(':');
            if (parts.length < 2) return null;
            const hours = Number(parts[0]);
            const mins = Number(parts[1]);
            if (!Number.isFinite(hours) || !Number.isFinite(mins)) return null;
            return (hours * 60) + mins;
        }

        window.formatTaskDateTime = function(dateStr, timeStr) {
            const date = String(dateStr || '').trim();
            const minutes = window.timeStringToMinutes(timeStr);
            const hhmm = minutes != null ? minutesToInputTime(minutes) : String(timeStr || '').trim();
            return date && hhmm ? `${date} ${hhmm}` : '';
        };

        window.__dayTasksCache = window.__dayTasksCache || {};
        window.fetchDayTasks = async function(dateValue) {
            const key = String(dateValue || '').trim();
            if (!key) return [];
            if (Array.isArray(window.__dayTasksCache[key])) return window.__dayTasksCache[key];
            const url = `/api/tasks?date=${encodeURIComponent(key)}&period=day&filter=all`;
            // Neighbour lookup is best-effort: on failure return [] without caching it, so a retry can succeed.
            try {
                const response = await fetch(url, { credentials: 'include' });
                if (!response.ok) return [];
                const data = await response.json();
                window.__dayTasksCache[key] = Array.isArray(data?.tasks) ? data.tasks : [];
                return window.__dayTasksCache[key];
            } catch (e) {
                return [];
            }
        };

        window.getTaskNeighborsForEdit = async function(task) {
            if (!task) return { prev: null, next: null };
            const date = String(task.date || '').trim();
            const targetId = Number(task.sheety_id || task.id || 0);
            const tasks = await window.fetchDayTasks(date);
            const sorted = (tasks || []).slice().sort((a, b) => {
                const aStart = window.timeStringToMinutes(a.start_time);
                const bStart = window.timeStringToMinutes(b.start_time);
                if (aStart == null && bStart == null) return 0;
                if (aStart == null) return 1;
                if (bStart == null) return -1;
                if (aStart !== bStart) return aStart - bStart;
                const aId = Number(a.sheety_id || a.id || 0);
                const bId = Number(b.sheety_id || b.id || 0);
                return aId - bId;
            });
            let idx = -1;
            if (targetId) {
                idx = sorted.findIndex(t => Number(t.sheety_id || t.id || 0) === targetId);
            }
            if (idx < 0) {
                const startMin = window.timeStringToMinutes(task.start_time);
                if (startMin != null) {
                    idx = sorted.findIndex(t => window.timeStringToMinutes(t.start_time) === startMin);
                }
            }
            const prev = idx > 0 ? sorted[idx - 1] : null;
            const next = idx >= 0 && idx < sorted.length - 1 ? sorted[idx + 1] : null;
            return { prev, next };
        };

        window.closeCreateTaskPanel = function() {
            const panel = document.getElementById('taskCreatePanel');
            if (panel) panel.classList.add('hidden');
            const overlap = document.getElementById('createTaskOverlap');
            if (overlap) {
                overlap.classList.add('hidden');
                overlap.innerHTML = '';
            }
        };

        // prefill: optional { start, end } in minutes (e.g. from a 'Missing time' gap).
        window.openCreateTaskPanel = function(prefill = null) {
            const panel = document.getElementById('taskCreatePanel');
            if (!panel) return;
            const modal = document.getElementById('taskModal');
            if (modal && !modal.classList.contains('active')) {
                return;
            }
            if (window.closeEditTaskPanel) {
                window.closeEditTaskPanel();
            }
            if (window.closeDeleteTaskConfirm) {
                window.closeDeleteTaskConfirm();
            }
            const nameInput = document.getElementById('createTaskName');
            const dateInput = document.getElementById('createTaskDate');
            const timeInput = document.getElementById('createTaskStart');
            const endInput = document.getElementById('createTaskEnd');
            const durationInput = document.getElementById('createTaskDuration');
            const tagInput = document.getElementById('createTaskTags');
            const importantInput = document.getElementById('createTaskImportant');
            const urgentInput = document.getElementById('createTaskUrgent');
            const overlap = document.getElementById('createTaskOverlap');
            const now = new Date();
            if (nameInput) nameInput.value = '';
            if (durationInput) durationInput.value = '';
            if (tagInput) tagInput.value = '';
            if (importantInput) importantInput.checked = false;
            if (urgentInput) urgentInput.checked = false;
            if (endInput) endInput.value = '';
            if (dateInput) {
                const selected = window.currentDate || window.getLocalIsoDate();
                dateInput.value = selected;
            }
            if (timeInput) {
                const selectedDate = dateInput?.value || window.currentDate;
                const lastEnd = getLatestTaskEndMinutes(selectedDate);
                if (lastEnd != null) {
                    timeInput.value = minutesToInputTime(lastEnd);
                } else {
                    const hours = String(now.getHours()).padStart(2, '0');
                    const minutes = String(now.getMinutes()).padStart(2, '0');
                    timeInput.value = `${hours}:${minutes}`;
                }
            }
            // 'Log again': same name, tags and priority; times stay as computed above.
            if (prefill && prefill.name) {
                if (nameInput) nameInput.value = prefill.name;
                if (tagInput) tagInput.value = prefill.tags || '';
                if (importantInput) importantInput.checked = Boolean(prefill.important);
                if (urgentInput) urgentInput.checked = Boolean(prefill.urgent);
            }
            if (prefill && Number.isFinite(prefill.start)) {
                if (timeInput) timeInput.value = minutesToInputTime(prefill.start);
                // A gap that runs to midnight has no same-day end time; leave End for the user.
                if (endInput && Number.isFinite(prefill.end) && prefill.end < 24 * 60) {
                    endInput.value = minutesToInputTime(prefill.end);
                }
            }
            if (overlap) {
                overlap.classList.add('hidden');
                overlap.innerHTML = '';
            }
            updateCreateTagChipStyles();
            updateCreatePriorityChips();
            panel.classList.remove('hidden');
            try {
                const focusTarget = prefill && prefill.name
                    ? (endInput || durationInput)
                    : document.getElementById('createTaskName');
                if (focusTarget) focusTarget.focus();
            } catch (e) {
                // ignore focus errors
            }
            try {
                panel.scrollIntoView({ behavior: 'smooth', block: 'center' });
            } catch (e) {
                panel.scrollIntoView();
            }
        };

        window.closeEditTaskPanel = function() {
            const panel = document.getElementById('taskEditPanel');
            if (panel) panel.classList.add('hidden');
        };

        window.openEditTaskPanel = function(task) {
            if (!task) return;
            if (task.sheety_id == null) {
                if (window.showWarningToast) {
                    window.showWarningToast('This task is not linked to Sheety yet. Sync with full API access to edit it.');
                } else {
                    setGlobalLoading(false, 'This task is not linked to Sheety yet.');
                }
                return;
            }
            const panel = document.getElementById('taskEditPanel');
            if (!panel) return;
            window.closeDeleteTaskConfirm();
            window.closeCreateTaskPanel();
            const nameInput = document.getElementById('editTaskName');
            const startMode = document.getElementById('editTaskStartMode');
            const startRaw = document.getElementById('editTaskStartRaw');
            const endMode = document.getElementById('editTaskEndMode');
            const endRaw = document.getElementById('editTaskEndRaw');
            const tagInput = document.getElementById('editTaskTags');
            const importantInput = document.getElementById('editTaskImportant');
            const urgentInput = document.getElementById('editTaskUrgent');
            const idInput = document.getElementById('editTaskId');
            const resolvedTaskId = task.sheety_id ?? task.id ?? '';
            if (idInput) idInput.value = resolvedTaskId;
            if (nameInput) nameInput.value = String(task.task || '').trim();
            if (tagInput) {
                const displayTag = formatTagNames(task.tag);
                tagInput.value = displayTag === 'Waste' ? '' : displayTag;
            }
            if (window.updateEditTagChipStyles) window.updateEditTagChipStyles();
            if (importantInput) importantInput.checked = Boolean(task.important);
            if (urgentInput) urgentInput.checked = Boolean(task.urgent);
            window.__editingTask = task;
            if (task?.date) {
                try { window.fetchDayTasks(task.date); } catch (e) { /* ignore */ }
            }
            if (startMode) startMode.value = 'manual';
            if (endMode) endMode.value = 'manual';
            const normalizeTaskDateTime = (dateStr, timeStr) => {
                const date = String(dateStr || '').trim();
                const minutes = window.timeStringToMinutes(timeStr);
                const hhmm = minutes != null ? minutesToInputTime(minutes) : String(timeStr || '').trim();
                return date && hhmm ? `${date} ${hhmm}` : '';
            };
            if (startRaw) {
                startRaw.value = normalizeTaskDateTime(task.date, task.start_time);
            }
            if (endRaw) {
                endRaw.value = normalizeTaskDateTime(task.date, task.end_time);
            }
            panel.classList.remove('hidden');
            try {
                panel.scrollIntoView({ behavior: 'smooth', block: 'center' });
            } catch (e) {
                panel.scrollIntoView();
            }
        };

        window.closeDeleteTaskConfirm = function() {
            const panel = document.getElementById('taskDeleteConfirm');
            if (panel) panel.classList.add('hidden');
            window.pendingDeleteTaskId = null;
        };

        window.openDeleteTaskConfirm = function(task) {
            if (!task) return;
            if (task.sheety_id == null) {
                if (window.showWarningToast) {
                    window.showWarningToast('This task is not linked to Sheety yet. Sync with full API access to delete it.');
                } else {
                    setGlobalLoading(false, 'This task is not linked to Sheety yet.');
                }
                return;
            }
            const panel = document.getElementById('taskDeleteConfirm');
            if (!panel) return;
            window.closeEditTaskPanel();
            window.closeCreateTaskPanel();
            window.pendingDeleteTaskId = task.sheety_id ?? task.id ?? null;
            const label = document.getElementById('deleteTaskLabel');
            if (label) {
                const taskName = String(task.task || '').trim() || 'this task';
                label.textContent = `Delete "${taskName}"? This action cannot be undone.`;
            }
            panel.classList.remove('hidden');
        };

        window.refreshModalData = function() {
            const filterType = window.modalFilterType || 'all';
            const title = window.modalTitle || (document.getElementById('modalTitle')?.textContent || 'Tasks');
            const tagName = window.modalTagName || '';
            const chartMode = window.modalChartMode || 'auto';
            window.applyFilter(filterType, title, tagName, chartMode);
        };

        let applyFilterSeq = 0;
        window.applyFilter = function(filterType, title, tagName = '', chartMode = 'auto') {
            window.closeDropdown();
            window.modalTitle = title;
            window.modalTagName = tagName;
            const url = `/api/tasks?date=${window.currentDate}&period=${window.currentPeriod}&filter=${filterType}${tagName ? '&tag=' + encodeURIComponent(tagName) : ''}`;

            // Two quick card clicks: only the latest request may open the modal.
            const seq = ++applyFilterSeq;
            setGlobalLoading(true);
            fetch(url)
                .then(r => {
                    if (seq !== applyFilterSeq) return null;
                    if (r.status === 401) {
                        const nextUrl = encodeURIComponent(window.location.pathname + window.location.search);
                        window.location.href = `/login?next=${nextUrl}`;
                        throw new Error('Unauthorized');
                    }
                    if (!r.ok) {
                        throw new Error(`HTTP error! status: ${r.status}`);
                    }
                    return r.json();
                })
                .then(data => {
                    if (seq !== applyFilterSeq || data === null) return;
                    setGlobalLoading(false);
                    window.modalSort = 'time_desc';
                    window.modalSortLabel = 'Time ↓';
                    window.showModal(title, data, filterType, chartMode);
                })
                .catch(error => {
                    if (seq !== applyFilterSeq) return;
                    console.error('Error fetching tasks:', error);
                    const message = getNetworkErrorMessage(error, 'load tasks');
                    setGlobalLoading(false, message);
                    try {
                        const fallback = { tasks: [], total_hours: 0, total_minutes: 0, count: 0, load_error: message || 'Could not load tasks.' };
                        window.showModal(title, fallback, filterType, chartMode);
                    } catch (e) {
                        console.error('Failed to open modal fallback', e);
                    }
                });
        };

        const MODAL_QUERY_TOKEN_RE = /"[^"]*"|'[^']*'|\(|\)|,|\+|\-|\*|\bAND\b|\bOR\b|\bNOT\b|[^\s()+*\-,]+/gi;

        function tokenizeModalQuery(raw) {
            const cleaned = String(raw || '').trim();
            if (!cleaned) return [];
            const matches = cleaned.match(MODAL_QUERY_TOKEN_RE) || [];
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

        function parseModalQuery(raw) {
            const tokens = tokenizeModalQuery(raw);
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
                    // 'only sleep': the task is exactly that (not 'Sleep in').
                    consume();
                    const expr = parsePrimary();
                    return expr && expr.type === 'term' ? { type: 'only', value: expr.value } : expr;
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

        function normalizeModalValue(value) {
            return String(value || '').toLowerCase().replace(/\s+/g, ' ').trim();
        }

        function modalTermMatches(task, term) {
            // note:tired matches entries on days whose day note mentions "tired"; note: alone = any note.
            const noteTerm = String(term || '').trim().replace(/^["']|["']$/g, '').match(/^notes?:(.*)$/i);
            if (noteTerm) {
                const note = normalizeModalValue(PERIOD_NOTES[String(task.date || '')] || '');
                const wanted = normalizeModalValue(noteTerm[1]);
                return wanted ? note.includes(wanted) : Boolean(note);
            }
            const clean = normalizeModalValue(term);
            if (!clean) return false;
            if (clean === 'imp' || clean === 'important') {
                return Number(task.important) > 0;
            }
            if (clean === 'urg' || clean === 'urgent') {
                return Number(task.urgent) > 0;
            }
            const taskText = normalizeModalValue(task.task);
            const tagText = normalizeModalValue(formatTagNames(task.tag) || '');
            const rawTag = normalizeModalValue(task.tag);
            return taskText.includes(clean) || tagText.includes(clean) || rawTag.includes(clean);
        }

        // Same name rule as Insights' Top activities: case, spacing and a stray
        // trailing '.'/',' ("Instagram .") don't make a different activity.
        function modalActivityName(value) {
            return normalizeModalValue(String(value || '').replace(/[\s.,;:]+$/, ''));
        }

        function evaluateModalQuery(expr, task) {
            if (!expr) return true;
            if (expr.type === 'term') return modalTermMatches(task, expr.value);
            if (expr.type === 'only') return modalActivityName(task.task) === modalActivityName(expr.value);
            if (expr.type === 'not') return !evaluateModalQuery(expr.expr, task);
            if (expr.type === 'and') return evaluateModalQuery(expr.left, task) && evaluateModalQuery(expr.right, task);
            if (expr.type === 'or') return evaluateModalQuery(expr.left, task) || evaluateModalQuery(expr.right, task);
            return true;
        }

        function modalTaskMatchesQuery(task, expr) {
            if (!expr) return true;
            return evaluateModalQuery(expr, task);
        }

        window.getVisibleModalTasks = function() {
            if (!window.modalData) return [];
            const hidden = window.hiddenTags || {};
            const tasks = window.modalData.tasks || [];
            const filterType = window.modalFilterType || 'all';
            const sortKey = window.modalSort || 'time_desc';
            const query = String(window.modalQuery || '').trim();
            const searchExpr = parseModalQuery(query);
            const getTaskTimestamp = (task) => {
                const date = String(task.date || '').trim();
                if (!date) return 0;
                const timeValue = String(task.start_time || '').trim();
                if (!timeValue) return 0;
                const match = timeValue.match(/(\d{1,2})(?::(\d{2}))?(?::(\d{2}))?\s*(AM|PM)?/i);
                if (!match) return 0;
                let hour = Number(match[1] || 0);
                const minute = Number(match[2] || 0);
                const second = Number(match[3] || 0);
                const meridian = (match[4] || '').toUpperCase();
                if (meridian === 'PM' && hour < 12) hour += 12;
                if (meridian === 'AM' && hour === 12) hour = 0;
                const iso = `${date}T${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}:${String(second).padStart(2, '0')}`;
                return new Date(iso).getTime();
            };
            const getKey = (task) => {
                if (filterType === 'tag') {
                    let key = String(task.task || '').replace(/[\s.,;:]+$/, '').trim();
                    if (!key || /^(undefined|null|none|nan)$/i.test(key)) key = 'Unspecified';
                    return key;
                }
                return normalizeTagName(task.tag);
            };
            const active = Object.keys(hidden).length
                ? tasks.filter(t => !hidden[getKey(t)])
                : tasks.slice();
            const searched = searchExpr
                ? active.filter(t => modalTaskMatchesQuery(t, searchExpr))
                : active;
            // Stats describe exactly what's listed: legend selection and search.
            window.modalActiveTasks = searched;
            const sorters = {
                time_asc: (a, b) => getTaskTimestamp(a) - getTaskTimestamp(b),
                time_desc: (a, b) => getTaskTimestamp(b) - getTaskTimestamp(a),
                duration_desc: (a, b) => (b.duration || 0) - (a.duration || 0),
                duration_asc: (a, b) => (a.duration || 0) - (b.duration || 0),
                task_az: (a, b) => String(a.task || '').localeCompare(String(b.task || '')),
                task_za: (a, b) => String(b.task || '').localeCompare(String(a.task || '')),
                tag_az: (a, b) => normalizeTagName(a.tag).localeCompare(normalizeTagName(b.tag)),
                tag_za: (a, b) => normalizeTagName(b.tag).localeCompare(normalizeTagName(a.tag)),
                imp_desc: (a, b) => Number(b.important) - Number(a.important),
                urg_desc: (a, b) => Number(b.urgent) - Number(a.urgent)
            };
            searched.sort(sorters[sortKey] || sorters.time_desc);
            return searched;
        };

        window.unifiedExportHeaders = ['start date', 'start time', 'end date', 'end time', 'task', 'duration', 'special tags', 'urgent', 'important'];

        window.rowsToExportCsv = function(rows, headers) {
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
        };

        window.showExportFormatPicker = function() {
            return new Promise((resolve) => {
                if (!exportFormatModal) {
                    resolve('csv');
                    return;
                }
                const opener = document.activeElement;
                exportFormatModal.classList.remove('hidden');
                exportFormatModal.querySelector('[data-export-format]')?.focus();
                // Capture phase: Escape must close the picker, not the task modal underneath it.
                const onKey = (event) => {
                    if (event.key === 'Escape') {
                        event.preventDefault();
                        event.stopImmediatePropagation();
                        close();
                        resolve(null);
                    } else if (event.key === 'Tab') {
                        event.stopImmediatePropagation();
                        const items = Array.from(exportFormatModal.querySelectorAll('button'));
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
                    exportFormatModal.classList.add('hidden');
                    if (opener && document.body.contains(opener)) opener.focus();
                    exportFormatModal.querySelectorAll('[data-export-format]').forEach(btn => {
                        btn.onclick = null;
                    });
                    exportFormatModal.querySelectorAll('[data-close-export-format="true"]').forEach(btn => {
                        btn.onclick = null;
                    });
                };
                exportFormatModal.querySelectorAll('[data-export-format]').forEach(btn => {
                    btn.onclick = () => {
                        const format = btn.getAttribute('data-export-format') || 'csv';
                        close();
                        resolve(format);
                    };
                });
                exportFormatModal.querySelectorAll('[data-close-export-format="true"]').forEach(btn => {
                    btn.onclick = () => {
                        close();
                        resolve(null);
                    };
                });
            });
        };

        window.normalizeTaskForUnifiedExport = function(task) {
            return {
                'start date': String(task?.date || ''),
                'start time': String(task?.start_time || ''),
                'end date': String(task?.end_date || task?.date || ''),
                'end time': String(task?.end_time || ''),
                'task': String(task?.task || ''),
                'duration': Number(task?.duration || 0),
                'special tags': String(task?.tag || task?.tags || ''),
                'urgent': task?.urgent ? 'Yes' : 'No',
                'important': task?.important ? 'Yes' : 'No',
            };
        };

        // Resolves false when the format picker is dismissed (nothing downloaded).
        window.downloadUnifiedRows = async function(rows, filePrefix = 'time-tracker-export', fileDate = '') {
            const format = await window.showExportFormatPicker();
            if (!format) return false;
            const headers = window.unifiedExportHeaders || [];
            const payload = format === 'json'
                ? JSON.stringify({ columns: headers, rows }, null, 2)
                : window.rowsToExportCsv(rows, headers);
            const mimeType = format === 'json' ? 'application/json' : 'text/csv';
            const extension = format === 'json' ? 'json' : 'csv';
            const blob = new Blob([payload], { type: mimeType });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `${filePrefix}-${fileDate || window.getLocalIsoDate()}.${extension}`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
            return true;
        };

        window.exportModalTasks = async function() {
            const searched = window.getVisibleModalTasks();
            if (!searched.length) {
                if (window.showWarningToast) window.showWarningToast('No visible tasks to export');
                return;
            }
            const rows = searched.map(task => window.normalizeTaskForUnifiedExport(task));
            const saved = await window.downloadUnifiedRows(rows, 'time-tracker-review');
            if (saved && window.showSuccessToast) window.showSuccessToast('Review exported successfully');
        };

        window.renderModalTasks = function() {
            const container = document.getElementById('modalTasks');
            if (!container || !window.modalData) return;
            const searched = window.getVisibleModalTasks();
            if (searched.length === 0) {
                container.innerHTML = '<div class="text-center py-8 text-gray-400">No tasks found</div>';
                if (window.renderModalStats) window.renderModalStats();
                return;
            }
            let html = '';
            // A one-day list doesn't need the same date repeated on every card.
            const showDate = new Set(searched.map(t => t.date)).size > 1;
            // Multi-day lists in time order get a header per day instead of a date on every card.
            const groupByDay = showDate && String(window.modalSort || 'time_desc').startsWith('time');
            const dayTotals = {};
            if (groupByDay) {
                searched.forEach(t => {
                    const key = String(t.date || '');
                    const entry = dayTotals[key] || (dayTotals[key] = { count: 0, hours: 0 });
                    entry.count += 1;
                    entry.hours += Number(t.duration || 0) || 0;
                });
            }
            let lastDay = null;
            searched.forEach(task => {
                if (groupByDay && String(task.date || '') !== lastDay) {
                    lastDay = String(task.date || '');
                    const totals = dayTotals[lastDay] || { count: 0, hours: 0 };
                    html += `
                        <div class="flex items-baseline justify-between gap-3 px-1 ${html ? 'pt-4' : 'pt-1'} pb-2">
                            <h4 class="text-xs font-semibold uppercase tracking-[0.14em] text-gray-600" title="${escapeHtml(lastDay)}">${escapeHtml(friendlyTaskDate(lastDay))}</h4>
                            <span class="text-xs text-gray-500 tabular-nums">${totals.count} ${totals.count === 1 ? 'task' : 'tasks'} · ${hoursToHuman(totals.hours)}</span>
                        </div>`;
                    const dayNote = PERIOD_NOTES[lastDay];
                    if (dayNote) {
                        html += `<p class="px-1 pb-2 -mt-1 text-xs text-gray-600 italic whitespace-pre-line">“${escapeHtml(dayNote)}”</p>`;
                    }
                }
                const dur = Number(task.duration || 0);
                const durText = hoursToHuman(isNaN(dur) ? 0 : dur);
                const badges = [];
                if (task.important) badges.push('<span class="px-2 py-1 bg-emerald-50 text-emerald-700 text-xs rounded-full">Important</span>');
                if (task.urgent) badges.push('<span class="px-2 py-1 bg-red-50 text-red-700 text-xs rounded-full">Urgent</span>');
                const displayTag = formatTagNames(task.tag);
                const primaryTag = normalizeTagName(task.tag);
                let tagBadge = '';
                if (displayTag) {
                    const tagColor = TAG_COLOR_MAP[primaryTag] || '#6B7280';
                    const tagStyle = `background-color: ${tagColor}15; color: ${tagColor}; border: 1px solid ${tagColor}30;`;
                    tagBadge = `<span class="px-2 py-0.5 rounded-full text-xs font-medium" style="${tagStyle}">${displayTag}</span>`;
                }
                const taskId = Number(task.sheety_id || task.id || 0);
                const localId = Number(task.id || 0);
                const againButton = localId
                    ? `<button class="px-2.5 py-1 rounded-full border border-slate-200 text-[11px] font-semibold text-gray-600 hover:bg-white" data-action="repeat-task" data-local-id="${localId}" aria-label="Log ${escapeHtml(task.task)} again" title="Add a new entry with this name, tags and priority">Again</button>`
                    : '';
                // Phones: actions get their own row under the task so the times don't wrap.
                const actionButtons = (taskId && task.sheety_id != null)
                    ? `<div class="flex items-center gap-2">
                            ${againButton}
                            <button class="px-2.5 py-1 rounded-full border border-slate-200 text-[11px] font-semibold text-gray-600 hover:bg-white" data-action="edit-task" data-task-id="${taskId}">Edit</button>
                            <button class="px-2.5 py-1 rounded-full border border-red-200 text-[11px] font-semibold text-red-600 hover:bg-white" data-action="delete-task" data-task-id="${taskId}">Delete</button>
                        </div>`
                    : (againButton ? `<div class="flex items-center gap-2">${againButton}</div>` : '');
                html += `
                    <div class="luxury-card rounded-2xl p-4 md:p-5 mb-3 shadow-lg">
                        <div class="flex items-center justify-between gap-3">
                            <div class="flex-1 min-w-0">
                                <div class="font-medium text-gray-900 mb-1 line-clamp-2 break-words" title="${escapeHtml(task.task)}">${escapeHtml(task.task)}</div>
                                <div class="flex flex-wrap items-center gap-2 text-[13px] text-gray-600">
                                    ${showDate && !groupByDay ? `<span class="text-gray-500" title="${escapeHtml(task.date)}">${escapeHtml(friendlyTaskDate(task.date))}</span>` : ''}
                                    <span class="text-gray-500">${escapeHtml(task.start_time)} - ${escapeHtml(task.end_time)}</span>
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
            container.innerHTML = html;
            window.attachHoverSwap();
            if (window.renderModalStats) window.renderModalStats();
        };

        window.showModal = function(title, data, filterType, chartMode = 'auto') {
            const modal = document.getElementById('taskModal');
            if (!modal) return;
            modal.style.display = 'flex';
            window.modalData = data;
            window.modalFilterType = filterType;
            window.modalChartMode = chartMode || 'auto';
            // A caller (e.g. an Insights activity) may pre-fill the search box.
            window.modalQuery = window.pendingModalQuery || '';
            window.pendingModalQuery = '';
            window.hiddenTags = window.hiddenTags || {};
            document.getElementById('modalTitle').textContent = title;
            const editPanel = document.getElementById('taskEditPanel');
            if (editPanel) editPanel.classList.add('hidden');
            const deletePanel = document.getElementById('taskDeleteConfirm');
            if (deletePanel) deletePanel.classList.add('hidden');
            window.pendingDeleteTaskId = null;
            const missingContainer = document.getElementById('modalMissingTime');

            const periodMinutes = ensureFinite(data.period_minutes || data.total_minutes || 0);
            const period = window.currentPeriod || 'day';
            const isMultiDay = period === 'week' || period === 'month';
            const dayCount = isMultiDay ? window.getPeriodDays() : 1;
            window.modalStatsMode = isMultiDay ? 'avg' : 'total';

            const periodMatrix = data.period_matrix_minutes || {};
            const pct = (num, den) => (den ? Math.round((num / den) * 100) : 0);
            const parentShareForQuadrant = (qType, viewMinutes) => {
                if (!qType) return { label: '', pct: 0 };
                if (qType === 'q2') {
                    return { label: 'Of Important time', pct: pct(viewMinutes, periodMatrix.important || 0) };
                }
                if (qType === 'q4') {
                    return { label: 'Of Not Urgent time', pct: pct(viewMinutes, periodMatrix.not_urgent || 0) };
                }
                if (qType === 'q1' || qType === 'q3') {
                    return { label: 'Of Urgent time', pct: pct(viewMinutes, periodMatrix.urgent || 0) };
                }
                return { label: '', pct: 0 };
            };

            // hint: optional static explainer, shown from sm up (it wrapped to 5 lines on phones).
            const statItem = (value, label, hint = '') => `
                <div class="rounded-xl border border-slate-100 bg-white/80 px-3 py-3 text-center"${hint ? ` title="${hint}"` : ''}>
                    <div class="text-xl md:text-2xl font-light text-gray-900">${value}</div>
                    <div class="text-[10px] md:text-xs text-gray-500 mt-1 uppercase tracking-wider">${label}</div>
                    ${hint ? `<div class="hidden sm:block text-[10px] md:text-xs text-gray-400 mt-0.5">${hint}</div>` : ''}
                </div>
            `;

            const isQuadrant = ['q1', 'q2', 'q3', 'q4'].includes(filterType);
            const isTag = filterType === 'tag';
            const renderStats = () => {
                const activeTasks = Array.isArray(window.modalActiveTasks) ? window.modalActiveTasks : (data.tasks || []);
                const totalMinutes = activeTasks.reduce((sum, task) => sum + minutesFromHours(task.duration || 0), 0);
                const taskCount = activeTasks.length;
                const sharePct = periodMinutes ? Math.round((totalMinutes / periodMinutes) * 100) : 0;
                let importantMinutes = 0;
                let urgentMinutes = 0;
                const quadrantMinutes = { Critical: 0, Growth: 0, Drudgery: 0, Waste: 0 };

                activeTasks.forEach(task => {
                    const dMin = minutesFromHours(task.duration || 0);
                    if (task.important) importantMinutes += dMin;
                    if (task.urgent) urgentMinutes += dMin;
                    if (task.urgent && task.important) {
                        quadrantMinutes.Critical += dMin;
                    } else if (task.important && !task.urgent) {
                        quadrantMinutes.Growth += dMin;
                    } else if (task.urgent && !task.important) {
                        quadrantMinutes.Drudgery += dMin;
                    } else {
                        quadrantMinutes.Waste += dMin;
                    }
                });

                const topQuadrantEntry = Object.entries(quadrantMinutes).sort((a, b) => b[1] - a[1])[0];
                const topQuadrantName = topQuadrantEntry && topQuadrantEntry[1] ? topQuadrantEntry[0] : '';
                const topQuadrantPct = topQuadrantName ? pct(topQuadrantEntry[1], totalMinutes) : 0;

                const maxSessionMin = activeTasks.reduce((m, t) => {
                    const d = minutesFromHours(t.duration || 0);
                    return d > m ? d : m;
                }, 0);

                const useAverage = isMultiDay && window.modalStatsMode === 'avg';
                const divisor = useAverage ? Math.max(dayCount, 1) : 1;
                const toHours = (minutes) => (ensureFinite(minutes) / 60) / divisor;
                const modeLabel = useAverage ? 'Avg/day' : 'Total';
                const hoursValue = (minutes) => {
                    const hours = toHours(minutes);
                    return `<span class="js-hover-hours hover-swap" data-hours="${hours}">${formatHours(hours, 1)}h</span>`;
                };

                const stats = [];
                const totalValue = hoursValue(totalMinutes);

                if (filterType === 'all') {
                    const base = totalMinutes || 1;
                    const cMin = quadrantMinutes.Critical || 0;
                    const gMin = quadrantMinutes.Growth || 0;
                    const dMin = quadrantMinutes.Drudgery || 0;
                    const wMin = quadrantMinutes.Waste || 0;
                    const gVal = hoursValue(gMin);
                    const dVal = hoursValue(dMin);
                    const wVal = hoursValue(wMin);
                    stats.push(statItem(hoursValue(cMin), `${pct(cMin, base)}% critical`, 'Urgent & important'));
                    stats.push(statItem(gVal, `${pct(gMin, base)}% growth`, 'Important, not urgent'));
                    stats.push(statItem(dVal, `${pct(dMin, base)}% drudgery`, 'Urgent, not important'));
                    stats.push(statItem(wVal, `${pct(wMin, base)}% waste`, 'Neither'));
                } else if (isTag) {
                    stats.push(statItem(totalValue, `${modeLabel} in view · ${sharePct}% of period`));
                    stats.push(statItem(`${pct(importantMinutes, totalMinutes)}%`, 'Important share'));
                    stats.push(statItem(`${pct(urgentMinutes, totalMinutes)}%`, 'Urgent share'));
                } else if (isQuadrant) {
                    stats.push(statItem(totalValue, `${modeLabel} in view · ${sharePct}% of period`));
                    const parent = parentShareForQuadrant(filterType, totalMinutes);
                    stats.push(statItem(`${parent.pct}%`, parent.label || 'Share of parent'));
                    const longestVal = maxSessionMin ? hoursToHuman(maxSessionMin / 60) : '0 min';
                    stats.push(statItem(longestVal, 'Longest session'));
                } else if (filterType === 'important') {
                    stats.push(statItem(totalValue, `Important · ${modeLabel} · ${sharePct}% of period`));
                    stats.push(statItem(`${pct(quadrantMinutes.Growth, totalMinutes)}%`, 'Growth (not urgent)'));
                    stats.push(statItem(`${pct(quadrantMinutes.Critical, totalMinutes)}%`, 'Critical (urgent)'));
                } else if (filterType === 'not_important') {
                    stats.push(statItem(totalValue, `Not Important · ${modeLabel} · ${sharePct}% of period`));
                    stats.push(statItem(`${pct(quadrantMinutes.Drudgery, totalMinutes)}%`, 'Drudgery (urgent)'));
                    stats.push(statItem(`${pct(quadrantMinutes.Waste, totalMinutes)}%`, 'Waste (not urgent)'));
                } else if (filterType === 'urgent') {
                    stats.push(statItem(totalValue, `Urgent · ${modeLabel} · ${sharePct}% of period`));
                    stats.push(statItem(`${pct(quadrantMinutes.Critical, totalMinutes)}%`, 'Critical (important)'));
                    stats.push(statItem(`${pct(quadrantMinutes.Drudgery, totalMinutes)}%`, 'Drudgery (not important)'));
                } else if (filterType === 'not_urgent') {
                    stats.push(statItem(totalValue, `Not Urgent · ${modeLabel} · ${sharePct}% of period`));
                    stats.push(statItem(`${pct(quadrantMinutes.Growth, totalMinutes)}%`, 'Growth (important)'));
                    stats.push(statItem(`${pct(quadrantMinutes.Waste, totalMinutes)}%`, 'Waste (not important)'));
                } else {
                    stats.push(statItem(totalValue, `${modeLabel} in view · ${sharePct}% of period`));
                    const longestVal = maxSessionMin ? hoursToHuman(maxSessionMin / 60) : '0 min';
                    stats.push(statItem(longestVal, 'Longest session'));
                    stats.push(statItem(`${topQuadrantPct}%`, topQuadrantName ? `Dominant · ${topQuadrantName}` : 'Dominant quadrant'));
                }

                const statsHtml = stats.join('');
                const statsEl = document.getElementById('modalStats');
                if (statsEl) {
                    statsEl.innerHTML = statsHtml;
                    // The all-tasks view shows the four quadrants; others show three facts.
                    const four = stats.length === 4;
                    statsEl.classList.toggle('grid-cols-3', !four);
                    statsEl.classList.toggle('grid-cols-2', four);
                    statsEl.classList.toggle('sm:grid-cols-4', four);
                }
                window.attachHoverSwap();
            };
            window.renderModalStats = renderStats;
            renderStats();
            const renderMissingTime = () => {
                if (!missingContainer) return;
                if (data.load_error) {
                    // Don't report the whole day as "missing" when the request itself failed.
                    missingContainer.innerHTML = `
                        <div class="rounded-2xl border border-rose-200 bg-rose-50/80 px-4 py-4 flex flex-wrap items-center justify-between gap-3" role="alert">
                            <div>
                                <p class="text-xs uppercase tracking-[0.22em] text-rose-700 font-semibold">Couldn't load tasks</p>
                                <p class="text-sm text-rose-900">${escapeHtml(String(data.load_error))}</p>
                            </div>
                            <button type="button" class="px-3 py-2 rounded-full bg-white border border-rose-200 text-xs font-semibold text-rose-700 shadow-sm active:scale-[0.98] transition" onclick="window.refreshModalData()">Try again</button>
                        </div>
                    `;
                    missingContainer.classList.remove('hidden');
                    return;
                }
                const period = window.currentPeriod || 'day';
                if (period !== 'day' || filterType !== 'all') {
                    missingContainer.classList.add('hidden');
                    missingContainer.innerHTML = '';
                    return;
                }
                const intervals = [];
                (data.tasks || []).forEach(task => {
                    const start = window.timeStringToMinutes(task.start_time);
                    const end = window.timeStringToMinutes(task.end_time);
                    if (start == null || end == null || start === end) return;
                    const overnight = task.end_date && task.date && String(task.end_date) !== String(task.date);
                    if (end > start && !overnight) {
                        intervals.push({ start, end });
                    } else {
                        // Runs past midnight: it covers the rest of *this* day only. Its
                        // early-morning part belongs to tomorrow, not to this morning.
                        intervals.push({ start, end: 24 * 60 });
                    }
                });
                // Logs that started the evening before and run into this day.
                const carryIn = Number(data.carry_in_minutes) || 0;
                if (carryIn > 0) intervals.push({ start: 0, end: Math.min(carryIn, 24 * 60) });
                intervals.sort((a, b) => a.start - b.start);

                const merged = [];
                intervals.forEach(item => {
                    const last = merged[merged.length - 1];
                    if (!last || item.start > last.end) {
                        merged.push({ start: item.start, end: item.end });
                    } else {
                        last.end = Math.max(last.end, item.end);
                    }
                });

                const gaps = [];
                let cursor = 0;
                merged.forEach(item => {
                    if (item.start > cursor) {
                        gaps.push({ start: cursor, end: item.start });
                    }
                    cursor = Math.max(cursor, item.end);
                });
                if (cursor < 24 * 60) {
                    gaps.push({ start: cursor, end: 24 * 60 });
                }

                const missingMinutes = gaps.reduce((sum, gap) => sum + (gap.end - gap.start), 0);
                const gapHtml = gaps.length
                    ? gaps.map(gap => `
                        <button type="button" class="px-2.5 py-1 rounded-full bg-amber-50 text-amber-800 text-xs font-semibold border border-amber-200 hover:bg-amber-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-400 transition" data-gap-start="${gap.start}" data-gap-end="${gap.end}" title="Log this gap" aria-label="Log ${formatMinutesToTime(gap.start)} to ${formatMinutesToTime(gap.end)}">${formatMinutesToTime(gap.start)} – ${formatMinutesToTime(gap.end)}</button>
                    `).join('')
                    : '<span class="text-xs text-gray-500">No missing gaps found.</span>';

                missingContainer.innerHTML = `
                    <div class="rounded-2xl border border-amber-200 bg-amber-50/70 px-4 py-4">
                        <div class="flex flex-wrap items-center justify-between gap-3">
                            <div>
                                <p class="text-xs uppercase tracking-[0.22em] text-amber-700 font-semibold">Missing time</p>
                                <p class="text-sm text-amber-900 font-semibold">${hoursToHuman(missingMinutes / 60)}</p>
                            </div>
                            <p class="text-[11px] text-amber-700">${gaps.length ? 'Tap a gap to log it' : 'Unlogged gaps this day'}</p>
                        </div>
                        <div class="mt-3 flex flex-wrap gap-2">
                            ${gapHtml}
                        </div>
                    </div>
                `;
                missingContainer.classList.remove('hidden');
            };
            renderMissingTime();
            if (missingContainer) {
                missingContainer.onclick = (event) => {
                    const chip = event.target.closest('[data-gap-start]');
                    if (!chip || !window.openCreateTaskPanel) return;
                    window.openCreateTaskPanel({ start: Number(chip.dataset.gapStart), end: Number(chip.dataset.gapEnd) });
                };
            }
            const statsContainer = document.getElementById('modalStats');
            if (statsContainer && isMultiDay) {
                statsContainer.classList.add('cursor-pointer');
                statsContainer.title = 'Click to toggle avg/total';
                statsContainer.setAttribute('role', 'button');
                statsContainer.setAttribute('tabindex', '0');
                statsContainer.setAttribute('aria-label', 'Toggle between average per day and total');
                statsContainer.onclick = () => {
                    window.modalStatsMode = window.modalStatsMode === 'avg' ? 'total' : 'avg';
                    renderStats();
                };
                statsContainer.onkeydown = (event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault();
                        statsContainer.onclick();
                    }
                };
            } else if (statsContainer) {
                // A single-day modal reuses this element: drop the toggle a week/month modal left behind.
                statsContainer.classList.remove('cursor-pointer');
                statsContainer.removeAttribute('title');
                statsContainer.removeAttribute('role');
                statsContainer.removeAttribute('tabindex');
                statsContainer.removeAttribute('aria-label');
                statsContainer.onclick = null;
                statsContainer.onkeydown = null;
            }
            const chartContainer = document.getElementById('modalChart');
            chartContainer.innerHTML = '<div class="relative w-full" style="height: 280px;"><canvas id="filterChart" class="w-full h-full"></canvas></div><div id="mobileModalLegend" class="mt-4 mb-4 md:hidden flex flex-wrap gap-2 justify-center text-[11px] text-gray-700 px-2"></div><div id="desktopModalLegend" class="mt-4 hidden md:flex flex-wrap gap-3 justify-center text-[11px] text-gray-700 px-4"></div>';
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
                const current = window.modalSort;
                const next = options.includes(current)
                    ? (current === options[0] ? options[1] : options[0])
                    : options[0];
                return { key: next, label: sortLabels[next] || 'Time ↓' };
            };
            const tools = document.getElementById('modalTools');
            if (tools) {
                tools.innerHTML = `
                    <div class="w-full space-y-2.5">
                        <div class="relative">
                            <span class="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-slate-400">
                                <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"></circle><path d="m21 21-4.3-4.3"></path></svg>
                            </span>
                            <input id="modalSearch" aria-label="Search tasks" type="search" placeholder="gym, reading · only lunch · -waste" title="Comma = or, - = not, only = exact name, quotes for phrases, note:word = days whose note mentions it" class="w-full pl-10 pr-4 py-2.5 rounded-full bg-white border border-slate-200 text-sm text-gray-700 shadow-sm focus:outline-none focus:ring-2 focus:ring-amber-300" />
                        </div>
                        <div class="flex flex-nowrap items-center gap-2 w-full overflow-x-auto sm:overflow-visible">
                            <button id="openCreateTask" class="px-3 py-2.5 rounded-full bg-gray-900 text-emerald-200 text-xs font-semibold shadow-sm active:scale-[0.98] transition text-center shrink-0 whitespace-nowrap">Add task</button>
                            <button id="modalExportBtn" class="px-3 py-2.5 rounded-full bg-white border border-slate-200 text-xs text-gray-700 font-medium shadow-sm active:scale-[0.98] transition text-center shrink-0 whitespace-nowrap">Export</button>
                            <div class="relative sm:min-w-[190px] shrink-0">
                                <button id="modalSortBtn" class="w-auto px-3 py-2.5 rounded-full bg-white border border-slate-200 text-xs text-gray-700 shadow-sm active:scale-[0.98] transition inline-flex items-center justify-between gap-2 whitespace-nowrap">
                                    <span>Sort: <span id="modalSortLabel">${sortLabels[window.modalSort] || window.modalSortLabel || 'Time ↓'}</span></span>
                                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"></polyline></svg>
                                </button>
                                <div id="modalSortMenu" class="absolute right-0 mt-2 w-full sm:w-44 bg-white rounded-xl shadow-2xl border border-slate-200 hidden">
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
                const btn = document.getElementById('modalSortBtn');
                const menu = document.getElementById('modalSortMenu');
                const label = document.getElementById('modalSortLabel');
                const search = document.getElementById('modalSearch');
                const exportBtn = document.getElementById('modalExportBtn');
                if (search) {
                    search.value = String(window.modalQuery || '');
                    search.oninput = () => {
                        window.modalQuery = search.value;
                        window.renderModalTasks();
                    };
                }
                const addBtn = document.getElementById('openCreateTask');
                if (addBtn) {
                    addBtn.onclick = () => window.openCreateTaskPanel && window.openCreateTaskPanel();
                }
                if (exportBtn) {
                    exportBtn.onclick = () => window.exportModalTasks && window.exportModalTasks();
                }
                if (btn && menu && label) {
                    btn.onclick = () => menu.classList.toggle('hidden');
                    menu.querySelectorAll('.dropdown-item').forEach(item => {
                        item.onclick = () => {
                            const base = item.getAttribute('data-key');
                            const next = resolveSort(base);
                            window.modalSort = next.key;
                            window.modalSortLabel = next.label;
                            label.textContent = next.label;
                            menu.classList.add('hidden');
                            window.renderModalTasks();
                        };
                    });
                    document.addEventListener('click', (e) => {
                        if (!e.target.closest('#modalSortBtn') && !e.target.closest('#modalSortMenu')) {
                            menu.classList.add('hidden');
                        }
                    });
                }
            }
            if (data.tasks.length > 0) {
                const ctx = document.getElementById('filterChart').getContext('2d');
                let labels = [];
                let values = [];
                let colors = [];
                window.__modalBuildChartView = null;
                let allEntries = [];
                let colorByKey = {};
                let chartKeyMap = {};

                const chartMode = window.modalChartMode || 'auto';
                const showTaskBreakdown = chartMode === 'tasks'
                    || (chartMode === 'auto' && window.modalFilterType === 'tag');

                const modalFallbackLabel = window.modalFilterType === 'tag' ? 'Unspecified' : 'Waste';
                const normalizeModalLabel = (value) => {
                    const s = String(value ?? '').replace(/[\s.,;:]+$/, '').trim();
                    if (!s || /^(undefined|null|none|nan)$/i.test(s)) return modalFallbackLabel;
                    return s;
                };
                const palette = ['#111827', '#16A34A', '#A16207', '#7C3AED', '#0EA5A4', '#9F1239', '#9CA3AF', '#F59E0B'];

                if (showTaskBreakdown) {
                    const taskGroups = {};
                    data.tasks.forEach(task => {
                        const key = normalizeModalLabel(task.task);
                        taskGroups[key] = (taskGroups[key] || 0) + (task.duration || 0);
                    });
                    const entries = Object.entries(taskGroups).sort((a, b) => b[1] - a[1]);
                    allEntries = entries.map(([key, value], idx) => ({
                        key,
                        label: key,
                        value: Number(value || 0),
                        color: palette[idx % palette.length]
                    }));
                } else {
                    const tagGroups = {};
                    data.tasks.forEach(task => {
                        const key = normalizeTagName(task.tag) || modalFallbackLabel;
                        tagGroups[key] = (tagGroups[key] || 0) + (task.duration || 0);
                    });
                    const entries = Object.entries(tagGroups).sort((a, b) => b[1] - a[1]);
                    allEntries = entries.map(([key, value], idx) => ({
                        key,
                        label: key,
                        value: Number(value || 0),
                        color: TAG_COLOR_MAP[key] || palette[idx % palette.length]
                    }));
                }

                colorByKey = {};
                allEntries.forEach(entry => {
                    if (!colorByKey[entry.key]) colorByKey[entry.key] = entry.color;
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
                    const hidden = window.hiddenTags || {};
                    const visible = allEntries.filter(e => !hidden[e.key]);
                    const maxSlots = getExpandedSlots(visible);
                    const top = visible.slice(0, maxSlots);
                    const rest = visible.slice(maxSlots);
                    const nextLabels = top.map(e => e.label);
                    const nextValues = top.map(e => e.value);
                    let otherValue = 0;
                    if (rest.length) {
                        otherValue = rest.reduce((sum, e) => sum + e.value, 0);
                        nextLabels.push('Other');
                        nextValues.push(otherValue);
                    }
                    const nextColors = nextLabels.map(label => {
                        if (label === 'Other') return '#9CA3AF';
                        const key = top.find(e => e.label === label)?.key || label;
                        return colorByKey[key] || '#111827';
                    });
                    const keyMap = {};
                    top.forEach(entry => {
                        keyMap[entry.label] = entry.key;
                    });
                    return { labels: nextLabels, values: nextValues, colors: nextColors, keyMap, otherValue };
                };

                const initialView = buildChartView();
                labels = initialView.labels;
                values = initialView.values;
                colors = initialView.colors;
                chartKeyMap = initialView.keyMap;
                window.__modalBuildChartView = buildChartView;
                const isModalMobile = window.matchMedia('(max-width: 767px)').matches;
                const showPercentInChart = true;
                const showMobileLegend = isModalMobile;

                const buildLegendItems = () => {
                    const hidden = window.hiddenTags || {};
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
                            color: colorByKey[key] || '#111827',
                            hidden: false,
                            disabled: false
                        };
                    }).filter(Boolean);
                    const hiddenItems = allEntries
                        .filter(entry => hidden[entry.key])
                        .map(entry => ({
                            key: entry.key,
                            label: entry.label,
                            color: entry.color,
                            hidden: true,
                            disabled: false
                        }));
                    return visibleItems.concat(hiddenItems);
                };

                // Toggleable legend entries are buttons (keyboard + screen readers); 'Other' stays a span.
                const legendTag = (item) => item.disabled
                    ? 'span'
                    : `button type="button" aria-pressed="${item.hidden ? 'false' : 'true'}" title="${item.hidden ? 'Show' : 'Hide'} ${escapeHtml(item.label)}"`;
                const mobileLegendEl = document.getElementById('mobileModalLegend');
                const updateMobileLegend = (chart) => {
                    if (mobileLegendEl && showMobileLegend) {
                        const legendItems = buildLegendItems();
                        mobileLegendEl.innerHTML = legendItems.map(item => {
                            const color = item.color || '#9CA3AF';
                            const isHidden = item.hidden;
                            const textDecoration = isHidden ? 'line-through' : 'none';
                            const opacity = isHidden ? '0.5' : '1';
                            const cursor = item.disabled ? 'cursor-default' : 'cursor-pointer hover:opacity-70';
                            return `<${legendTag(item)} class="inline-flex items-center gap-1 ${cursor} transition-opacity" data-legend-key="${escapeHtml(item.key)}" style="opacity:${opacity}">
                                <span class="inline-block w-2.5 h-2.5 rounded-full" style="background:${color}"></span>
                                <span style="text-decoration:${textDecoration}">${escapeHtml(item.label)}</span>
                            </${item.disabled ? 'span' : 'button'}>`;
                        }).join('');
                    } else if (mobileLegendEl) {
                        mobileLegendEl.innerHTML = '';
                    }
                };
                updateMobileLegend(null);

                const desktopLegendEl = document.getElementById('desktopModalLegend');
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
                        return `<${legendTag(item)} class="inline-flex items-center gap-1 ${cursor} transition-opacity" data-legend-key="${escapeHtml(item.key)}" style="opacity:${opacity}">
                            <span class="inline-block w-2.5 h-2.5 rounded-full" style="background:${color}"></span>
                            <span style="text-decoration:${textDecoration}" class="max-w-[160px] truncate">${escapeHtml(item.label)}</span>
                        </${item.disabled ? 'span' : 'button'}>`;
                    }).join('');
                };

                const applyChartView = (chart) => {
                    const view = buildChartView();
                    labels = view.labels;
                    values = view.values;
                    colors = view.colors;
                    chartKeyMap = view.keyMap;
                    if (chart) {
                        chart.data.labels = labels;
                        chart.data.datasets[0].data = values;
                        chart.data.datasets[0].backgroundColor = colors;
                        chart.update();
                    }
                    return view;
                };

                const chart = new Chart(ctx, {
                    type: 'pie',
                    data: {
                        labels: labels,
                        datasets: [{
                            data: values,
                            backgroundColor: colors,
                            // A lone slice would show its rim as a seam at 12 o'clock.
                            borderWidth: (c) => (c.chart.data.datasets[0].data.filter(v => Number(v) > 0).length > 1 ? 2 : 0),
                            // Slice gaps take the surface colour (white rims glare in dark mode).
                            borderColor: document.documentElement.getAttribute('data-theme') === 'dark' ? '#0E0C08' : '#FFFFFF',
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
                                display: showPercentInChart,
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
                                backgroundColor: 'rgba(17, 24, 39, 0.96)',
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
                                        const label = String(raw ?? '').trim() || (window.modalFilterType === 'tag' ? 'Unspecified' : 'Waste');
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
                            const label = chart.data.labels[index];
                            const key = chartKeyMap[label];
                            if (!key) return;
                            if (!window.hiddenTags) window.hiddenTags = {};
                            if (window.hiddenTags[key]) delete window.hiddenTags[key];
                            else window.hiddenTags[key] = true;
                            applyChartView(chart);
                            updateMobileLegend(chart);
                            updateDesktopLegend(chart);
                            window.renderModalTasks();
                        }
                    }
                });
                updateMobileLegend(chart);
                updateDesktopLegend(chart);
                const legendClickHandler = (e) => {
                    const legendItem = e.target.closest('[data-legend-key]');
                    if (!legendItem) return;
                    const key = legendItem.dataset.legendKey;
                    if (!key || key === '__other__') return;
                    if (!window.hiddenTags) window.hiddenTags = {};
                    if (window.hiddenTags[key]) delete window.hiddenTags[key];
                    else window.hiddenTags[key] = true;
                    applyChartView(chart);
                    updateMobileLegend(chart);
                    updateDesktopLegend(chart);
                    window.renderModalTasks();
                    // The legend was re-rendered: keep keyboard focus on the entry just toggled.
                    const again = Array.from(e.currentTarget.querySelectorAll('button[data-legend-key]')).find(el => el.dataset.legendKey === key);
                    if (again) again.focus();
                };
                if (mobileLegendEl) {
                    mobileLegendEl.addEventListener('click', legendClickHandler);
                }
                if (desktopLegendEl) {
                    desktopLegendEl.addEventListener('click', legendClickHandler);
                }
            }
            window.renderModalTasks();
            if (window.renderModalStats) window.renderModalStats();
            modal.classList.add('active');
            focusModal(modal);
        };

        window.closeModal = function() {
            const modal = document.getElementById('taskModal');
            if (modal) {
                modal.classList.remove('active');
                modal.style.display = 'none';
            }
            setGlobalLoading(false);
            if (window.closeCreateTaskPanel) window.closeCreateTaskPanel();
            if (window.closeEditTaskPanel) window.closeEditTaskPanel();
            if (window.closeDeleteTaskConfirm) window.closeDeleteTaskConfirm();
            if (lastModalFocus && typeof lastModalFocus.focus === 'function') {
                try {
                    lastModalFocus.focus();
                } catch (e) {
                    // ignore focus errors
                }
            }
            // Totals, matrix, timeline and insights are server-rendered: after an
            // add/edit/delete in the log, reload so they match what was just changed.
            if (window.dashboardStale) {
                window.dashboardStale = false;
                window.location.reload();
            }
        };

        // Initialize on DOM load
        document.addEventListener('DOMContentLoaded', function() {
            document.querySelectorAll('[data-height]').forEach(el => {
                const value = Number(el.dataset.height || 0);
                if (Number.isFinite(value)) {
                    el.style.height = `${value}%`;
                }
            });
            document.querySelectorAll('[data-width]').forEach(el => {
                const value = Number(el.dataset.width || 0);
                if (Number.isFinite(value)) {
                    el.style.width = `${value}%`;
                }
            });
            function setActiveNav(id) {
                ['navHome','navMatrix','navTags','navInsights','navGraphs','navFilter'].forEach(k => {
                    const el = document.getElementById(k);
                    if (!el) return;
                    if (k === id) {
                        el.className = 'flex flex-col items-center gap-1 px-3 py-1 rounded-xl text-gray-900 bg-slate-100';
                        el.setAttribute('aria-current', 'true');
                    } else {
                        el.className = 'flex flex-col items-center gap-1 px-3 py-1 rounded-xl text-gray-600';
                        el.removeAttribute('aria-current');
                    }
                });
            }

            function smoothScrollTo(targetId) {
                const el = document.getElementById(targetId);
                if (!el) return;
                el.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }

            const homeBtn = document.getElementById('navHome');
            const matrixBtn = document.getElementById('navMatrix');
            const tagsBtn = document.getElementById('navTags');
            const graphsBtn = document.getElementById('navGraphs');
            const filterBtn = document.getElementById('navFilter');
            if (homeBtn) homeBtn.onclick = () => { smoothScrollTo('top'); setActiveNav('navHome'); };
            if (matrixBtn) matrixBtn.onclick = () => { smoothScrollTo('matrix'); setActiveNav('navMatrix'); };
            if (tagsBtn) tagsBtn.onclick = () => { smoothScrollTo('tags'); setActiveNav('navTags'); };
            const insightsBtn = document.getElementById('navInsights');
            if (insightsBtn) insightsBtn.onclick = () => { smoothScrollTo('insights'); setActiveNav('navInsights'); };
            if (graphsBtn) graphsBtn.onclick = () => {
                setActiveNav('navGraphs');
                window.location.href = DASHBOARD_CONFIG.graphsUrl;
            };
            if (filterBtn) {
                filterBtn.onclick = () => {
                    openMobileFilter();
                    setActiveNav('navFilter');
                };
                ['touchstart','mousedown'].forEach(evt => {
                    filterBtn.addEventListener(evt, () => filterBtn.classList.add('bg-slate-100'));
                });
                ['touchend','mouseup','mouseleave'].forEach(evt => {
                    filterBtn.addEventListener(evt, () => filterBtn.classList.remove('bg-slate-100'));
                });
            }

            function openMobileFilter() {
                try {
                    const sheet = document.getElementById('mobileFilterSheet');
                    const backdrop = document.getElementById('mobileFilterBackdrop');
                    if (!sheet || !backdrop) return;
                    backdrop.classList.remove('pointer-events-none');
                    backdrop.classList.add('opacity-100');
                    sheet.classList.remove('translate-y-full');
                } catch (e) {
                    setGlobalLoading(false, 'Unable to open filters');
                    console.error(e);
                }
            }
            function closeMobileFilter() {
                try {
                    const sheet = document.getElementById('mobileFilterSheet');
                    const backdrop = document.getElementById('mobileFilterBackdrop');
                    if (!sheet || !backdrop) return;
                    sheet.classList.add('translate-y-full');
                    backdrop.classList.remove('opacity-100');
                    backdrop.classList.add('pointer-events-none');
                } catch (e) {
                    setGlobalLoading(false, 'Unable to close filters');
                    console.error(e);
                }
            }
            const mobileFilterClose = document.getElementById('mobileFilterClose');
            const mobileBackdrop = document.getElementById('mobileFilterBackdrop');
            if (mobileFilterClose) mobileFilterClose.onclick = closeMobileFilter;
            if (mobileBackdrop) mobileBackdrop.onclick = closeMobileFilter;

            const observerTargets = [
                { id: 'top', btn: 'navHome' },
                { id: 'matrix', btn: 'navMatrix' },
                { id: 'tags', btn: 'navTags' },
                { id: 'insights', btn: 'navInsights' }
            ].map(({ id, btn }) => ({ el: document.getElementById(id), btn }));

            // Scroll spy: the active section is the last one whose top has passed
            // 35% of the viewport; at the very bottom, the last section wins (it may
            // never reach that line). A visibility-ratio observer missed sections
            // taller than the screen (Matrix, Insights on phones).
            let navSpyQueued = false;
            function updateNavFromScroll() {
                navSpyQueued = false;
                const present = observerTargets.filter(t => t.el && t.el.offsetParent !== null);
                if (!present.length) return;
                const line = window.innerHeight * 0.35;
                let current = present[0];
                present.forEach(t => {
                    if (t.el.getBoundingClientRect().top <= line) current = t;
                });
                const doc = document.documentElement;
                if (window.innerHeight + window.scrollY >= doc.scrollHeight - 4 && window.scrollY > 0) {
                    current = present[present.length - 1];
                }
                setActiveNav(current.btn);
            }
            window.addEventListener('scroll', () => {
                if (navSpyQueued) return;
                navSpyQueued = true;
                requestAnimationFrame(updateNavFromScroll);
            }, { passive: true });
            window.addEventListener('resize', () => updateNavFromScroll());
            updateNavFromScroll();

            document.addEventListener('click', (e) => {
                if (!e.target.closest('.dropdown')) {
                    window.closeDropdown();
                }
                if (!e.target.closest('#datePicker')) {
                    const dd = document.getElementById('dateDropdown');
                    if (dd) dd.classList.add('hidden');
                    document.getElementById('datePickerBtn')?.setAttribute('aria-expanded', 'false');
                }
            });
            // Escape closes the date picker and returns focus to its button.
            document.addEventListener('keydown', (e) => {
                if (e.key !== 'Escape') return;
                const dd = document.getElementById('dateDropdown');
                if (!dd || dd.classList.contains('hidden')) return;
                dd.classList.add('hidden');
                const btn = document.getElementById('datePickerBtn');
                btn?.setAttribute('aria-expanded', 'false');
                btn?.focus();
            });

            const summaryCards = document.querySelectorAll('[data-filter], [data-action]');
            summaryCards.forEach(card => {
                const triggerCard = () => {
                    const action = card.dataset.action;
                    if (action === 'full-period') {
                        viewFullDay();
                        return;
                    }
                    const filter = card.dataset.filter;
                    const title = card.dataset.title || '';
                    const tag = card.dataset.tag || '';
                    const chart = card.dataset.chart || 'auto';
                    if (filter) {
                        window.applyFilter(filter, title, tag, chart);
                    }
                };
                card.addEventListener('click', triggerCard);
                card.addEventListener('keydown', (event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault();
                        triggerCard();
                    }
                });
            });

            // Matrix cards use inline onclick; make them reachable and operable from the keyboard.
            document.querySelectorAll('.matrix-card[data-quadrant]').forEach(card => {
                if (!card.hasAttribute('tabindex')) card.setAttribute('tabindex', '0');
                card.setAttribute('role', 'button');
                const heading = card.querySelector('h4');
                if (heading && !card.hasAttribute('aria-label')) {
                    const hours = card.querySelector('.matrix-hours');
                    card.setAttribute('aria-label', `${heading.textContent.trim()}${hours ? ', ' + hours.textContent.trim() : ''}`);
                }
                card.addEventListener('keydown', (event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault();
                        card.click();
                    }
                });
            });

            // Close modal on outside click
            document.getElementById('taskModal').addEventListener('click', (e) => {
                if (e.target.id === 'taskModal') {
                    window.closeModal();
                }
            });

            document.addEventListener('keydown', (event) => {
                const modal = document.getElementById('taskModal');
                if (!modal || !modal.classList.contains('active')) return;
                if (event.key === 'Escape') {
                    // Close an open Add/Edit/Delete panel first so a stray Escape
                    // doesn't throw away a half-typed task along with the whole log.
                    const panels = [
                        ['taskDeleteConfirm', window.closeDeleteTaskConfirm],
                        ['taskEditPanel', window.closeEditTaskPanel],
                        ['taskCreatePanel', window.closeCreateTaskPanel],
                    ];
                    for (const [id, closePanel] of panels) {
                        const panel = document.getElementById(id);
                        if (panel && !panel.classList.contains('hidden') && typeof closePanel === 'function') {
                            event.preventDefault();
                            closePanel();
                            // Keep focus inside the dialog (the focused field is now hidden).
                            document.getElementById('openCreateTask')?.focus();
                            return;
                        }
                    }
                    window.closeModal();
                    return;
                }
                if (event.key === 'Tab') {
                    trapModalFocus(modal, event);
                }
            });

            const graphsUrl = DASHBOARD_CONFIG.graphsUrl;
            const settingsUrl = DASHBOARD_CONFIG.settingsUrl;
            const dashboardUrl = DASHBOARD_CONFIG.dashboardUrl;
            const adminUrl = DASHBOARD_CONFIG.adminUrl;
            const getSheetyNotice = (stats) => {
                if (!stats || String(stats.status || '') !== 'failed') return null;
                const reason = String(stats.skipped_reason || '').trim();
                const error = String(stats.sheety_error || '').trim();
                const quota = Boolean(stats.sheety_quota_exhausted);
                if (quota || reason === 'sheety_subscription_required') {
                    return {
                        type: 'warning',
                        message: `Sheety quota reached. Sync is paused — update your API keys in <a href="${settingsUrl}" class="underline">Settings</a> to restore cloud sync.`
                    };
                }
                if (reason || error) {
                    return {
                        type: 'warning',
                        message: `Sheety sync failed. Update your API keys in <a href="${settingsUrl}" class="underline">Settings</a> and try again.`
                    };
                }
                return null;
            };
            const showSheetyNotice = (stats, { force = false } = {}) => {
                if (!force && window.__sheetyNoticeShown) return;
                const notice = getSheetyNotice(stats);
                if (!notice || !window.showWarningToast) return;
                window.__sheetyNoticeShown = true;
                window.showToast(notice.message, 'warning', 9000, { html: true });
            };
            showSheetyNotice(window.syncStats);
            let shortcutToast = null;
            const isDialogOpen = () => {
                if (document.getElementById('taskModal')?.classList.contains('active')) return true;
                const exportModal = document.getElementById('exportFormatModal');
                return Boolean(exportModal && !exportModal.classList.contains('hidden'));
            };
            // Previous/next day, week or month (arrow keys, swipes).
            window.shiftPeriod = (delta, unit) => {
                // Work on local calendar parts: new Date('YYYY-MM-DD') is UTC midnight,
                // and setMonth() on the 29th-31st overflows into the following month.
                const [y, m, d] = String(window.currentDate || window.getLocalIsoDate()).split('-').map(Number);
                const period = unit || window.currentPeriod || 'day';
                let base;
                if (period === 'month') {
                    base = new Date(y, m - 1 + delta, 1);
                } else {
                    base = new Date(y, m - 1, d + (period === 'week' ? 7 * delta : delta));
                }
                const iso = `${base.getFullYear()}-${String(base.getMonth() + 1).padStart(2, '0')}-${String(base.getDate()).padStart(2, '0')}`;
                window.changeDate(iso);
            };
            // Phones have no arrow keys: a horizontal swipe on the week strip or the
            // day-by-day chart moves to the previous/next period (left swipe = next);
            // the day view's week strip moves a whole week, keeping the weekday.
            document.querySelectorAll('[data-swipe-period]').forEach(area => {
                let start = null;
                area.addEventListener('touchstart', (event) => {
                    start = event.touches.length === 1
                        ? { x: event.touches[0].clientX, y: event.touches[0].clientY, t: Date.now() }
                        : null;
                }, { passive: true });
                area.addEventListener('touchend', (event) => {
                    if (!start || !event.changedTouches.length) return;
                    const dx = event.changedTouches[0].clientX - start.x;
                    const dy = event.changedTouches[0].clientY - start.y;
                    const quick = Date.now() - start.t < 700;
                    start = null;
                    // Leave a strip that actually scrolls sideways to its own scrolling.
                    if (area.scrollWidth > area.clientWidth + 1) return;
                    if (quick && Math.abs(dx) >= 60 && Math.abs(dx) > 1.5 * Math.abs(dy)) {
                        window.shiftPeriod(dx < 0 ? 1 : -1, area.dataset.swipePeriod || undefined);
                    }
                }, { passive: true });
                area.addEventListener('touchcancel', () => { start = null; }, { passive: true });
            });
            // New task: open the full log, then its Add-task panel once the modal is up.
            function openAddTaskFromAnywhere() {
                window.viewFullDay();
                let tries = 0;
                const openWhenReady = () => {
                    const modal = document.getElementById('taskModal');
                    if (modal && modal.classList.contains('active') && window.openCreateTaskPanel) {
                        window.openCreateTaskPanel();
                    } else if (++tries < 40) {
                        setTimeout(openWhenReady, 50);
                    }
                };
                openWhenReady();
            }
            // '/#add-task' (the installed app's "Add task" shortcut) opens the form straight away.
            if (window.location.hash === '#add-task') {
                history.replaceState(null, '', window.location.pathname + window.location.search);
                openAddTaskFromAnywhere();
            }
            document.addEventListener('keydown', (event) => {
                const tag = event.target?.tagName;
                if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || event.target?.isContentEditable) return;
                // Page shortcuts would navigate away underneath an open dialog.
                if (isDialogOpen()) return;
                const key = event.key.toLowerCase();
                if (event.altKey && (event.key === 'ArrowRight' || event.key === 'ArrowLeft')) {
                    event.preventDefault();
                    const order = ['day', 'week', 'month'];
                    const idx = order.indexOf(window.currentPeriod || 'day');
                    const direction = event.key === 'ArrowRight' ? 1 : -1;
                    const next = order[(idx + direction + order.length) % order.length];
                    window.changePeriod(next);
                    return;
                }
                if (!event.metaKey && !event.ctrlKey && !event.altKey && (event.key === 'ArrowRight' || event.key === 'ArrowLeft')) {
                    event.preventDefault();
                    window.shiftPeriod(event.key === 'ArrowRight' ? 1 : -1);
                    return;
                }
                if (event.metaKey || event.ctrlKey || event.altKey) return;
                if (key === 't') {
                    const todayBtn = document.getElementById('todayBtn');
                    if (todayBtn && window.getComputedStyle(todayBtn).display !== 'none') {
                        todayBtn.click();
                    }
                } else if (key === 'g') {
                    window.location.href = graphsUrl;
                } else if (key === 's') {
                    window.location.href = settingsUrl;
                } else if (key === 'd') {
                    window.location.href = dashboardUrl;
                } else if (key === 'a' && adminUrl) {
                    window.location.href = adminUrl;
                } else if (key === 'f') {
                    const modal = document.getElementById('taskModal');
                    if (!modal || !modal.classList.contains('active')) {
                        event.preventDefault();
                        window.viewFullDay();
                    }
                } else if (key === 'n') {
                    event.preventDefault();
                    openAddTaskFromAnywhere();
                } else if (key === 'j') {
                    // Jot a note for this day (day view).
                    const note = document.getElementById('dayNoteInput');
                    if (note) {
                        event.preventDefault();
                        note.scrollIntoView({ block: 'center', behavior: 'smooth' });
                        note.focus({ preventScroll: true });
                        note.setSelectionRange(note.value.length, note.value.length);
                    }
                } else if (key === 'c') {
                    const copyBtn = document.getElementById('copySummaryBtn');
                    if (copyBtn) {
                        event.preventDefault();
                        copyBtn.click();
                    }
                } else if (key === '/') {
                    // Search: open the full log and focus its search box.
                    event.preventDefault();
                    window.viewFullDay();
                    let tries = 0;
                    const focusWhenReady = () => {
                        const modal = document.getElementById('taskModal');
                        const search = document.getElementById('modalSearch');
                        if (modal && modal.classList.contains('active') && search) {
                            search.focus();
                        } else if (++tries < 40) {
                            setTimeout(focusWhenReady, 50);
                        }
                    };
                    focusWhenReady();
                } else if (key === '?') {
                    event.preventDefault();
                    if (shortcutToast && !document.body.contains(shortcutToast)) {
                        shortcutToast = null;
                    }
                    if (shortcutToast?.__removeToast) {
                        shortcutToast.__removeToast();
                        shortcutToast = null;
                        return;
                    }
                    if (window.showInfoToast) {
                        shortcutToast = window.showToast(`
                            <div class="space-y-3">
                                <div class="text-xs uppercase tracking-[0.2em] text-white/80 font-semibold">Keyboard Shortcuts</div>
                                <div class="space-y-2 text-sm">
                                    <div class="flex items-center gap-2">
                                        <kbd class="toast-kbd">←</kbd><kbd class="toast-kbd">→</kbd>
                                        <span class="toast-kbd-label">Change date</span>
                                    </div>
                                    <div class="flex items-center gap-2">
                                        <kbd class="toast-kbd">⌥</kbd><kbd class="toast-kbd">←</kbd><kbd class="toast-kbd">→</kbd>
                                        <span class="toast-kbd-label">Change period</span>
                                    </div>
                                    <div class="flex items-center gap-2">
                                        <kbd class="toast-kbd">F</kbd>
                                        <span class="toast-kbd-label">Full log for this period</span>
                                    </div>
                                    <div class="flex items-center gap-2">
                                        <kbd class="toast-kbd">N</kbd>
                                        <span class="toast-kbd-label">Add a task</span>
                                    </div>
                                    <div class="flex items-center gap-2">
                                        <kbd class="toast-kbd">/</kbd>
                                        <span class="toast-kbd-label">Search the log</span>
                                    </div>
                                    <div class="flex items-center gap-2">
                                        <kbd class="toast-kbd">C</kbd>
                                        <span class="toast-kbd-label">Copy summary</span>
                                    </div>
                                    ${document.getElementById('dayNoteInput') ? `<div class="flex items-center gap-2">
                                        <kbd class="toast-kbd">J</kbd>
                                        <span class="toast-kbd-label">Day note</span>
                                    </div>` : ''}
                                    <div class="flex items-center gap-2">
                                        <kbd class="toast-kbd">G</kbd>
                                        <span class="toast-kbd-label">Graphs</span>
                                    </div>
                                    <div class="flex items-center gap-2">
                                        <kbd class="toast-kbd">S</kbd>
                                        <span class="toast-kbd-label">Settings</span>
                                    </div>
                                    <div class="flex items-center gap-2">
                                        <kbd class="toast-kbd">D</kbd>
                                        <span class="toast-kbd-label">Dashboard</span>
                                    </div>
                                    <div class="flex items-center gap-2">
                                        <kbd class="toast-kbd">T</kbd>
                                        <span class="toast-kbd-label">Today</span>
                                    </div>
                                    ${adminUrl ? `
                                    <div class="flex items-center gap-2">
                                        <kbd class="toast-kbd">A</kbd>
                                        <span class="toast-kbd-label">Admin</span>
                                    </div>
                                    ` : ''}
                                </div>
                            </div>
                        `, 'shortcut', 7000);
                    }
                }
            });

            const modalTasks = document.getElementById('modalTasks');
            if (modalTasks && !modalTasks.__taskActionBound) {
                modalTasks.addEventListener('click', (e) => {
                    const repeatBtn = e.target.closest('[data-action="repeat-task"]');
                    if (repeatBtn) {
                        const localId = Number(repeatBtn.dataset.localId || 0);
                        const task = (window.modalData?.tasks || []).find(t => Number(t.id || 0) === localId);
                        if (task && window.openCreateTaskPanel) {
                            window.openCreateTaskPanel({
                                name: String(task.task || '').trim(),
                                tags: formatTagNames(task.tag),
                                important: task.important,
                                urgent: task.urgent,
                            });
                        }
                        return;
                    }
                    const editBtn = e.target.closest('[data-action="edit-task"]');
                    if (editBtn) {
                        const taskId = parseInt(editBtn.dataset.taskId || '0', 10);
                        if (taskId) window.openEditTaskPanel(window.getModalTaskById(taskId));
                        return;
                    }
                    const deleteBtn = e.target.closest('[data-action="delete-task"]');
                    if (deleteBtn) {
                        const taskId = parseInt(deleteBtn.dataset.taskId || '0', 10);
                        if (taskId) window.openDeleteTaskConfirm(window.getModalTaskById(taskId));
                    }
                });
                modalTasks.__taskActionBound = true;
            }
            const closeEdit = document.getElementById('closeEditPanel');
            const cancelEdit = document.getElementById('cancelEditTask');
            if (closeEdit) closeEdit.onclick = window.closeEditTaskPanel;
            if (cancelEdit) cancelEdit.onclick = window.closeEditTaskPanel;
            const closeCreate = document.getElementById('closeCreatePanel');
            const cancelCreate = document.getElementById('cancelCreateTask');
            if (closeCreate) closeCreate.onclick = window.closeCreateTaskPanel;
            if (cancelCreate) cancelCreate.onclick = window.closeCreateTaskPanel;
            const closeDelete = document.getElementById('closeDeleteConfirm');
            const cancelDelete = document.getElementById('cancelDeleteTask');
            if (closeDelete) closeDelete.onclick = window.closeDeleteTaskConfirm;
            if (cancelDelete) cancelDelete.onclick = window.closeDeleteTaskConfirm;
            const createTagInput = document.getElementById('createTaskTags');
            if (createTagInput && !createTagInput.__bound) {
                createTagInput.addEventListener('input', updateCreateTagChipStyles);
                createTagInput.__bound = true;
            }
            // Edit form: same toggle-a-tag chips as the Add form.
            window.updateEditTagChipStyles = function() {
                const tagInput = document.getElementById('editTaskTags');
                if (!tagInput) return;
                const tags = String(tagInput.value || '').split(',').map(t => t.trim().toLowerCase()).filter(Boolean);
                document.querySelectorAll('.edit-tag-chip').forEach(chip => {
                    const active = tags.includes(String(chip.dataset.editTag || '').toLowerCase());
                    chip.classList.toggle('active', active);
                    chip.setAttribute('aria-pressed', active ? 'true' : 'false');
                    chip.classList.toggle('bg-emerald-600', active);
                    chip.classList.toggle('text-white', active);
                    chip.classList.toggle('border-emerald-600', active);
                    chip.classList.toggle('bg-white/80', !active);
                    chip.classList.toggle('text-gray-600', !active);
                    chip.classList.toggle('border-slate-200', !active);
                });
            };
            document.querySelectorAll('.edit-tag-chip').forEach(chip => {
                if (chip.__bound) return;
                chip.addEventListener('click', () => {
                    const tagInput = document.getElementById('editTaskTags');
                    const tag = chip.dataset.editTag || '';
                    if (!tagInput || !tag) return;
                    const tags = String(tagInput.value || '').split(',').map(t => t.trim()).filter(Boolean);
                    const exists = tags.some(t => t.toLowerCase() === tag.toLowerCase());
                    tagInput.value = (exists ? tags.filter(t => t.toLowerCase() !== tag.toLowerCase()) : [...tags, tag]).join(', ');
                    window.updateEditTagChipStyles();
                });
                chip.__bound = true;
            });
            const editTagsInput = document.getElementById('editTaskTags');
            if (editTagsInput && !editTagsInput.__chipsBound) {
                editTagsInput.addEventListener('input', () => window.updateEditTagChipStyles());
                editTagsInput.__chipsBound = true;
            }
            document.querySelectorAll('.create-tag-chip').forEach(chip => {
                if (chip.__bound) return;
                chip.addEventListener('click', () => {
                    const tagInput = document.getElementById('createTaskTags');
                    if (!tagInput) return;
                    const tag = chip.dataset.createTag || '';
                    if (!tag) return;
                    const tags = String(tagInput.value || '')
                        .split(',')
                        .map(t => t.trim())
                        .filter(Boolean);
                    const exists = tags.find(t => t.toLowerCase() === tag.toLowerCase());
                    const nextTags = exists
                        ? tags.filter(t => t.toLowerCase() !== tag.toLowerCase())
                        : [...tags, tag];
                    tagInput.value = nextTags.join(', ');
                    updateCreateTagChipStyles();
                });
                chip.__bound = true;
            });
            document.querySelectorAll('.create-priority-chip').forEach(chip => {
                if (chip.__bound) return;
                chip.addEventListener('click', () => {
                    const key = chip.dataset.createPriority || '';
                    const importantInput = document.getElementById('createTaskImportant');
                    const urgentInput = document.getElementById('createTaskUrgent');
                    if (key === 'important' && importantInput) {
                        importantInput.checked = !importantInput.checked;
                    }
                    if (key === 'urgent' && urgentInput) {
                        urgentInput.checked = !urgentInput.checked;
                    }
                    updateCreatePriorityChips();
                });
                chip.__bound = true;
            });
            const createStart = document.getElementById('createTaskStart');
            const createEnd = document.getElementById('createTaskEnd');
            const createDuration = document.getElementById('createTaskDuration');
            if (createStart && !createStart.__bound) {
                createStart.addEventListener('change', () => {
                    syncCreateDurationFromTimes();
                    syncCreateEndFromDuration();
                });
                createStart.__bound = true;
            }
            if (createEnd && !createEnd.__bound) {
                createEnd.addEventListener('change', syncCreateDurationFromTimes);
                createEnd.__bound = true;
            }
            if (createDuration && !createDuration.__bound) {
                createDuration.addEventListener('input', syncCreateEndFromDuration);
                createDuration.__bound = true;
            }
            const createForm = document.getElementById('taskCreateForm');
            if (createForm && !createForm.__bound) {
                createForm.addEventListener('submit', async (e) => {
                    e.preventDefault();
                    const name = String(document.getElementById('createTaskName')?.value || '').trim();
                    const date = String(document.getElementById('createTaskDate')?.value || '').trim();
                    const startTime = String(document.getElementById('createTaskStart')?.value || '').trim();
                    const endTime = String(document.getElementById('createTaskEnd')?.value || '').trim();
                    let duration = parseFloat(document.getElementById('createTaskDuration')?.value || '0');
                    const tags = String(document.getElementById('createTaskTags')?.value || '').trim();
                    const important = Boolean(document.getElementById('createTaskImportant')?.checked);
                    const urgent = Boolean(document.getElementById('createTaskUrgent')?.checked);
                    const overlap = document.getElementById('createTaskOverlap');
                    if (overlap) {
                        overlap.classList.add('hidden');
                        overlap.innerHTML = '';
                    }
                    if (!name) {
                        setGlobalLoading(false, 'Task name is required');
                        return;
                    }
                    if (!date) {
                        setGlobalLoading(false, 'Date is required');
                        return;
                    }
                    if (!startTime) {
                        setGlobalLoading(false, 'Start time is required');
                        return;
                    }
                    if (endTime) {
                        const startMinutes = inputTimeToMinutes(startTime);
                        const endMinutes = inputTimeToMinutes(endTime);
                        if (startMinutes == null || endMinutes == null || endMinutes <= startMinutes) {
                            setGlobalLoading(false, 'End time must be after start time');
                            return;
                        }
                        duration = Number(((endMinutes - startMinutes) / 60).toFixed(2));
                    }
                    if (!Number.isFinite(duration) || duration <= 0) {
                        setGlobalLoading(false, 'Duration must be greater than 0');
                        return;
                    }
                    const saveBtn = document.getElementById('saveNewTask');
                    const originalText = saveBtn ? saveBtn.textContent : '';
                    if (saveBtn) {
                        saveBtn.textContent = 'Adding...';
                        saveBtn.disabled = true;
                    }
                    setGlobalLoading(true);
                    try {
                        const response = await fetch('/api/tasks', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                task: name,
                                date,
                                start_time: startTime,
                                duration,
                                tag: tags,
                                urgent,
                                important
                            })
                        });
                        const contentType = response.headers.get('content-type') || '';
                        const result = contentType.includes('application/json') ? await response.json() : null;
                        if (!response.ok) {
                            if (response.status === 409 && result?.overlaps) {
                                renderCreateOverlap(result.overlaps);
                                setGlobalLoading(false, 'Overlapping logs detected');
                                return;
                            }
                            throw new Error(result?.error || `HTTP ${response.status}`);
                        }
                        if (result?.failover && window.showApiFailoverNotification) {
                            window.showApiFailoverNotification(result.failover.from, result.failover.to);
                        }
                        if (window.showSuccessToast) {
                            window.showSuccessToast('Task added');
                        }
                        window.closeCreateTaskPanel();
                        window.refreshModalData();
                        window.dashboardStale = true;
                    } catch (error) {
                        const message = getNetworkErrorMessage(error, 'add the task');
                        if (window.showErrorToast) {
                            window.showErrorToast(message);
                        } else {
                            setGlobalLoading(false, message);
                        }
                    } finally {
                        if (saveBtn) {
                            saveBtn.textContent = originalText || 'Add task';
                            saveBtn.disabled = false;
                        }
                        setGlobalLoading(false);
                    }
                });
                createForm.__bound = true;
            }
            const editForm = document.getElementById('taskEditForm');
            const editStartMode = document.getElementById('editTaskStartMode');
            const editStartRaw = document.getElementById('editTaskStartRaw');
            const editEndMode = document.getElementById('editTaskEndMode');
            const editEndRaw = document.getElementById('editTaskEndRaw');

            const fillEditStartFromPrevEnd = async () => {
                const task = window.__editingTask;
                if (!task) return;
                const neighbors = await window.getTaskNeighborsForEdit(task);
                if (!neighbors.prev) {
                    if (window.showWarningToast) window.showWarningToast('No previous task found for this day.');
                    if (editStartMode) editStartMode.value = 'manual';
                    return;
                }
                if (editStartRaw) editStartRaw.value = window.formatTaskDateTime(neighbors.prev.date, neighbors.prev.end_time);
            };

            const fillEditEndFromNextStart = async () => {
                const task = window.__editingTask;
                if (!task) return;
                const neighbors = await window.getTaskNeighborsForEdit(task);
                if (!neighbors.next) {
                    if (window.showWarningToast) window.showWarningToast('No next task found for this day.');
                    if (editEndMode) editEndMode.value = 'manual';
                    return;
                }
                if (editEndRaw) editEndRaw.value = window.formatTaskDateTime(neighbors.next.date, neighbors.next.start_time);
            };

            if (editStartMode && !editStartMode.__bound) {
                editStartMode.addEventListener('change', async () => {
                    if (editStartMode.value === 'prev_end') {
                        await fillEditStartFromPrevEnd();
                    }
                });
                editStartMode.__bound = true;
            }
            if (editEndMode && !editEndMode.__bound) {
                editEndMode.addEventListener('change', async () => {
                    if (editEndMode.value === 'next_start') {
                        await fillEditEndFromNextStart();
                    }
                });
                editEndMode.__bound = true;
            }
            if (editStartRaw && !editStartRaw.__bound) {
                editStartRaw.addEventListener('input', () => {
                    if (editStartMode) editStartMode.value = 'manual';
                });
                editStartRaw.__bound = true;
            }
            if (editEndRaw && !editEndRaw.__bound) {
                editEndRaw.addEventListener('input', () => {
                    if (editEndMode) editEndMode.value = 'manual';
                });
                editEndRaw.__bound = true;
            }

            if (editForm && !editForm.__bound) {
                editForm.addEventListener('submit', async (e) => {
                    e.preventDefault();
                    const taskId = parseInt(document.getElementById('editTaskId')?.value || '0', 10);
                    if (!taskId) return;
                    const name = String(document.getElementById('editTaskName')?.value || '').trim();
                    const start = String(document.getElementById('editTaskStartRaw')?.value || '').trim();
                    const end = String(document.getElementById('editTaskEndRaw')?.value || '').trim();
                    const tags = String(document.getElementById('editTaskTags')?.value || '').trim();
                    const important = Boolean(document.getElementById('editTaskImportant')?.checked);
                    const urgent = Boolean(document.getElementById('editTaskUrgent')?.checked);
                    if (!name) {
                        setGlobalLoading(false, 'Task name is required');
                        return;
                    }
                    if (!start) {
                        setGlobalLoading(false, 'Start time is required');
                        return;
                    }
                    if (!end) {
                        setGlobalLoading(false, 'End time is required');
                        return;
                    }
                    const saveBtn = document.getElementById('saveTaskChanges');
                    const originalText = saveBtn ? saveBtn.textContent : '';
                    if (saveBtn) {
                        saveBtn.textContent = 'Saving...';
                        saveBtn.disabled = true;
                    }
                    setGlobalLoading(true);
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
                        window.closeEditTaskPanel();
                        window.refreshModalData();
                        window.dashboardStale = true;
                    } catch (error) {
                        const message = getNetworkErrorMessage(error, 'update the task');
                        if (window.showErrorToast) {
                            window.showErrorToast(message);
                        } else {
                            setGlobalLoading(false, message);
                        }
                    } finally {
                        if (saveBtn) {
                            saveBtn.textContent = originalText || 'Save changes';
                            saveBtn.disabled = false;
                        }
                        setGlobalLoading(false);
                    }
                });
                editForm.__bound = true;
            }
            const confirmDelete = document.getElementById('confirmDeleteTask');
            if (confirmDelete && !confirmDelete.__bound) {
                confirmDelete.addEventListener('click', async () => {
                    const taskId = Number(window.pendingDeleteTaskId || 0);
                    if (!taskId) return;
                    confirmDelete.disabled = true;
                    const originalText = confirmDelete.textContent;
                    confirmDelete.textContent = 'Deleting...';
                    setGlobalLoading(true);
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
                        window.closeDeleteTaskConfirm();
                        window.refreshModalData();
                        window.dashboardStale = true;
                    } catch (error) {
                        const message = getNetworkErrorMessage(error, 'delete the task');
                        if (window.showErrorToast) {
                            window.showErrorToast(message);
                        } else {
                            setGlobalLoading(false, message);
                        }
                    } finally {
                        confirmDelete.textContent = originalText || 'Delete';
                        confirmDelete.disabled = false;
                        setGlobalLoading(false);
                    }
                });
                confirmDelete.__bound = true;
            }

            // Update button text based on period
            const period = window.currentPeriod || 'day';
            const periodMap = { 'day': 'Day', 'week': 'Week', 'month': 'Month' };
            const periodLabel = periodMap[period] || 'Day';
            const viewFullBtnMobile = document.getElementById('viewFullBtnMobile');
            // Phones: shorter label so long month names ('September 2026') stay on one line.
            if (viewFullBtnMobile) {
                viewFullBtnMobile.textContent = 'Full ' + periodLabel;
                viewFullBtnMobile.setAttribute('aria-label', 'View full ' + period + ' log');
            }

            window.dateCursor = window.parseLocalDate(window.currentDate);
            window.renderDateGrid();

            const isMultiDayPeriod = period === 'week' || period === 'month';
            window.matrixMode = isMultiDayPeriod ? 'avg' : 'total';
            window.updateMatrixDisplay();

            const tagCanvas = document.getElementById('tagChart');
            const tagCtx = tagCanvas ? tagCanvas.getContext('2d') : null;
            const isMobile = window.matchMedia('(max-width: 767px)').matches;
            const tagPalette = ['#111827', '#16A34A', '#F59E0B', '#E11D48', '#64748B', '#0369A1', '#7C3AED', '#F97316'];
            const tagLabels = DASHBOARD_CONFIG.tagLabels || [];
            const tagData = DASHBOARD_CONFIG.tagData || [];
            if (tagCtx && tagLabels.length) {
                const tagColors = tagLabels.map((label, idx) => TAG_COLOR_MAP[label] || tagPalette[idx % tagPalette.length]);
                const tagTotal = tagData.reduce((sum, v) => sum + Number(v || 0), 0);
                const tagChartDark = document.documentElement.getAttribute('data-theme') === 'dark';
                const tagHoursLabel = (idx) => `${Number(tagData[idx] || 0).toFixed(1)}h`;
                try {
                    const tagChart = new Chart(tagCtx, {
                        type: 'doughnut',
                        data: {
                            labels: tagLabels,
                            datasets: [{
                                data: tagData,
                                backgroundColor: tagColors,
                                // A lone slice would show its rim as a seam at 12 o'clock.
                                borderWidth: (c) => (c.chart.data.datasets[0].data.filter(v => Number(v) > 0).length > 1 ? 2 : 0),
                                borderColor: tagChartDark ? '#0E0C08' : '#FFFFFF',
                                hoverOffset: 12,
                                hoverBorderWidth: (c) => (c.chart.data.datasets[0].data.filter(v => Number(v) > 0).length > 1 ? 3 : 0)
                            }]
                        },
                        plugins: [percentLabelPlugin],
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
                            cutout: isMobile ? '58%' : '64%',
                            spacing: 3,
                            plugins: {
                                percentLabelPlugin: {
                                    display: true,
                                    fontSize: isMobile ? 11 : 12,
                                    fontFamily: 'Inter',
                                    fontWeight: '600',
                                    color: '#111827',
                                    lightColor: '#FFFFFF',
                                    autoColor: true,
                                    shadow: true,
                                    minPercent: 5
                                },
                                legend: {
                                    display: !isMobile,
                                    position: 'bottom',
                                    maxWidth: 280,
                                    labels: {
                                        usePointStyle: true,
                                        pointStyle: 'circle',
                                        font: { family: 'Inter', size: 11, weight: '500' },
                                        padding: 14,
                                        color: tagChartDark ? '#B8A878' : '#374151',
                                        boxWidth: 10,
                                        boxHeight: 10,
                                        // "Necessity 11.1h" instead of just the name.
                                        generateLabels: (chart) => Chart.overrides.doughnut.plugins.legend.labels
                                            .generateLabels(chart)
                                            .map(item => ({ ...item, text: `${item.text} ${tagHoursLabel(item.index)}` }))
                                    }
                                },
                                tooltip: {
                                    backgroundColor: 'rgba(17, 24, 39, 0.96)',
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
                                            const label = context.label || '';
                                            const value = context.parsed || 0;
                                            const total = context.dataset.data.reduce((sum, v, idx) => {
                                                const visible = typeof context.chart.getDataVisibility === 'function'
                                                    ? context.chart.getDataVisibility(idx) !== false
                                                    : true;
                                                return visible ? sum + Number(v || 0) : sum;
                                            }, 0);
                                            const percent = total > 0 ? ((value / total) * 100).toFixed(1) : 0;
                                            return label + ': ' + value.toFixed(1) + 'h (' + percent + '%)';
                                        }
                                    }
                                }
                            }
                        }
                    });
                    tagChart.options.onClick = function(evt, elements) {
                        if (!elements || !elements.length) return;
                        const index = elements[0].index;
                        const label = tagChart.data.labels[index];
                        window.applyFilter('tag', label, label);
                    };
                    tagChart.update();
                    const mobileLegend = document.getElementById('mobileTagLegend');
                    if (isMobile && mobileLegend) {
                        tagChart.options.plugins.legend.display = false;
                        tagChart.update();
                        mobileLegend.innerHTML = tagLabels.map((label, idx) => {
                            return `<span class="inline-flex items-center gap-1">
                                <span class="inline-block w-2.5 h-2.5 rounded-full" style="background:${tagColors[idx]}"></span>
                                ${escapeHtml(label)} <span class="text-gray-400">${tagHoursLabel(idx)}</span>
                            </span>`;
                        }).join('');
                    }
                } catch (e) {
                    const wrap = document.getElementById('tags');
                    if (wrap) {
                        const holder = wrap.querySelector('[aria-label="Time spent by tag category"]');
                        if (holder) {
                            holder.innerHTML = '<div class="text-center text-xs text-gray-400">Unable to render chart</div>';
                        }
                    }
                }
            }

            // Decimal handling helpers: sum in minutes to avoid float drift, format using fixed decimals
            function ensureFinite(n) {
                const v = Number(n);
                return Number.isFinite(v) ? v : 0;
            }
            function minutesFromHours(h) {
                return Math.round(ensureFinite(h) * 60);
            }
            function formatHours(h, decimals = 1) {
                return ensureFinite(h).toFixed(decimals);
            }
            function hoursToHM(h) {
                const total = Math.max(0, Math.round(Number(h || 0) * 60));
                const hrs = Math.floor(total / 60);
                const mins = total % 60;
                if (hrs === 0) return `${mins} min`;
                if (mins === 0) return `${hrs} hr`;
                return `${hrs} hr ${mins} min`;
            }
            async function runManualSync({ reload = true, showLoading = true } = {}) {
                try {
                    if (showLoading) {
                        setGlobalLoading(true, '');
                    }
                    const r = await fetch('/sync-now', { method: 'POST', credentials: 'include' });
                    if (r.status === 401) {
                        const nextUrl = encodeURIComponent(window.location.pathname + window.location.search);
                        window.location.href = `/login?next=${nextUrl}`;
                        return;
                    }
                    if (!r.ok) throw new Error(`HTTP ${r.status}`);
                    let result = null;
                    try {
                        result = await r.json();
                    } catch (e) {
                        result = null;
                    }
                    if (result?.failover && window.showApiFailoverNotification) {
                        window.showApiFailoverNotification(result.failover.from, result.failover.to);
                    }
                    const notice = getSheetyNotice(result?.stats || null);
                    if (notice && window.showWarningToast) {
                        window.showToast(notice.message, 'warning', 9000, { html: true });
                    } else if (showLoading && window.showSuccessToast) {
                        window.showSuccessToast('Synced latest data');
                    }
                    if (showLoading) {
                        setGlobalLoading(false, '');
                    }
                    if (reload) {
                        window.location.href = `/?date=${window.currentDate}&period=${window.currentPeriod}`;
                    }
                } catch (e) {
                    console.error('Manual sync failed', e);
                    if (showLoading) {
                        setGlobalLoading(false, 'Failed to sync from cloud');
                    }
                }
            }
            window.runManualSync = runManualSync;
            const titleBtn = document.getElementById('appTitleBtn');
            if (titleBtn) {
                titleBtn.addEventListener('click', () => runManualSync());
            }

            const copySummaryBtn = document.getElementById('copySummaryBtn');
            if (copySummaryBtn) {
                copySummaryBtn.addEventListener('click', async () => {
                    let text = '';
                    try {
                        text = JSON.parse(document.getElementById('periodSummaryText')?.textContent || '""');
                    } catch (_) { /* fall through to the error toast */ }
                    if (!text) {
                        if (window.showWarningToast) window.showWarningToast('No logs to summarise for this period');
                        return;
                    }
                    try {
                        await navigator.clipboard.writeText(text);
                    } catch (_) {
                        // Older browsers / non-secure origins: hidden textarea + execCommand.
                        const area = document.createElement('textarea');
                        area.value = text;
                        area.setAttribute('readonly', '');
                        area.style.position = 'fixed';
                        area.style.opacity = '0';
                        document.body.appendChild(area);
                        area.select();
                        let ok = false;
                        try { ok = document.execCommand('copy'); } catch (__) { ok = false; }
                        area.remove();
                        if (!ok) {
                            if (window.showErrorToast) window.showErrorToast('Could not copy - your browser blocked clipboard access');
                            return;
                        }
                    }
                    if (window.showSuccessToast) window.showSuccessToast('Summary copied');
                });
            }
            const exportSummaryBtn = document.getElementById('exportSummaryBtn');
            if (exportSummaryBtn) {
                exportSummaryBtn.addEventListener('click', async () => {
                    try {
                        const query = new URLSearchParams({
                            date: String(window.currentDate || ''),
                            period: String(window.currentPeriod || 'day'),
                            filter: 'all'
                        });
                        const response = await fetch(`/api/tasks?${query.toString()}`, { credentials: 'include' });
                        if (!response.ok) {
                            throw new Error(`HTTP ${response.status}`);
                        }
                        const data = await response.json();
                        const tasks = Array.isArray(data?.tasks) ? data.tasks : [];
                        if (!tasks.length) {
                            if (window.showWarningToast) window.showWarningToast('No tasks available to export for this period');
                            return;
                        }
                        const rows = tasks.map(task => window.normalizeTaskForUnifiedExport(task));
                        // Name the file after the period being exported, not the day it was downloaded.
                        const saved = await window.downloadUnifiedRows(rows, `time-tracker-${window.currentPeriod || 'period'}`, String(window.currentDate || ''));
                        if (saved && window.showSuccessToast) {
                            window.showSuccessToast('Summary exported successfully');
                        }
                    } catch (error) {
                        if (window.showErrorToast) {
                            window.showErrorToast('Failed to export summary');
                        }
                    }
                });
            }
            setTimeout(() => {
                runManualSync({ reload: false, showLoading: false });
            }, 2000);
            function attachHoverSwap() {
                document.querySelectorAll('.js-hover-hours').forEach(el => {
                    if (el.__hoverBound) return;
                    const raw = el.getAttribute('data-hours') || el.textContent;
                    const h = Number(raw);
                    if (isNaN(h)) return;
                    const decimalText = `${window.formatHours(h, 1)}h`;
                    const humanText = hoursToHM(h);
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
            attachHoverSwap();

            // Tilt-responsive water animation for mobile devices.
            // deviceorientation fires ~60x/s: write styles at most once per frame,
            // to a cached element list, and not at all with reduced motion.
            const waterElements = Array.from(document.querySelectorAll('.water-fill'));
            const reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
            if (window.DeviceOrientationEvent && waterElements.length && !reduceMotion) {
                let pendingGamma = null;
                window.addEventListener('deviceorientation', function(event) {
                    if (event.gamma === null) return; // Left-right tilt (-90 to 90)
                    const first = pendingGamma === null;
                    pendingGamma = event.gamma;
                    if (!first) return;
                    requestAnimationFrame(() => {
                        // Normalize gamma to -1 to 1 range (clamp to -30 to 30 degrees)
                        const tiltFactor = Math.max(-30, Math.min(30, pendingGamma)) / 30;
                        pendingGamma = null;
                        waterElements.forEach(function(water) {
                            water.style.setProperty('--tilt-x', (tiltFactor * 10) + '%');
                            water.style.setProperty('--tilt-rotate', (tiltFactor * 2) + 'deg');
                        });
                    });
                }, { passive: true });
            }

            // Pull down to sync - only in the installed app (browsers have their own
            // pull-to-refresh). Never while a dialog is open, when the touch starts in a
            // scrolled panel, or for sideways swipes (week strip / day-by-day).
            (function initPullToSync() {
                const standalone = window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true;
                if (!standalone || !('ontouchstart' in window)) return;
                const READY_AT = 64;
                const pill = document.createElement('div');
                pill.className = 'pull-sync';
                pill.setAttribute('aria-hidden', 'true');
                document.body.appendChild(pill);
                let startX = 0, startY = 0, pull = 0, tracking = false, decided = false;
                const dialogOpen = () => Boolean(document.querySelector('.modal.active, #exportFormatModal:not(.hidden), [role="dialog"][aria-modal="true"]:not(.hidden):not(.modal)'));
                const inScrolledPanel = (el) => {
                    for (let node = el; node && node !== document.body; node = node.parentElement) {
                        if (node.scrollTop > 0) return true;
                    }
                    return false;
                };
                const show = (distance, text) => {
                    pill.textContent = text;
                    pill.style.transform = `translate(-50%, ${Math.round(distance) - 48}px)`;
                    pill.style.opacity = distance > 8 ? '1' : '0';
                };
                const reset = () => {
                    tracking = false;
                    decided = false;
                    pull = 0;
                    pill.classList.remove('is-dragging');
                    show(0, '');
                };
                document.addEventListener('touchstart', (event) => {
                    if (event.touches.length !== 1 || window.scrollY > 0 || dialogOpen() || inScrolledPanel(event.target)) return;
                    if (event.target.closest && event.target.closest('input, textarea, select, [contenteditable="true"]')) return;
                    startX = event.touches[0].clientX;
                    startY = event.touches[0].clientY;
                    tracking = true;
                    decided = false;
                }, { passive: true });
                document.addEventListener('touchmove', (event) => {
                    if (!tracking) return;
                    const dx = event.touches[0].clientX - startX;
                    const dy = event.touches[0].clientY - startY;
                    if (!decided) {
                        if (Math.abs(dx) < 8 && Math.abs(dy) < 8) return;
                        decided = true;
                        if (dy <= 0 || Math.abs(dx) > Math.abs(dy)) { reset(); return; }
                        pill.classList.add('is-dragging');
                    }
                    pull = Math.max(0, Math.min(dy * 0.5, 96));
                    show(pull, pull >= READY_AT ? 'Release to sync' : 'Pull down to sync');
                }, { passive: true });
                const finish = () => {
                    if (!tracking) return;
                    const ready = pull >= READY_AT;
                    tracking = false;
                    pill.classList.remove('is-dragging');
                    if (ready) {
                        show(READY_AT, 'Syncing…');
                        window.location.reload();  // the dashboard syncs on load
                    } else {
                        reset();
                    }
                };
                document.addEventListener('touchend', finish, { passive: true });
                document.addEventListener('touchcancel', reset, { passive: true });
            })();
        }); // End DOMContentLoaded
    