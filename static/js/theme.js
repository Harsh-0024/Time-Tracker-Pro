/**
 * Theme manager: light / dark / system
 * Persists preference in localStorage under key 'ttp-theme'.
 * Applies data-theme="light"|"dark" on <html>.
 */
(function () {
    const STORAGE_KEY = 'ttp-theme';
    const VALID = ['light', 'dark', 'system'];
    let memoryPref = 'system';

    function safeGetStored() {
        try {
            return localStorage.getItem(STORAGE_KEY);
        } catch (err) {
            return memoryPref;
        }
    }

    function safeSetStored(value) {
        try {
            localStorage.setItem(STORAGE_KEY, value);
        } catch (err) {
            memoryPref = value;
        }
    }

    function getPreference() {
        const stored = safeGetStored();
        return VALID.includes(stored) ? stored : 'system';
    }

    function resolveTheme(pref) {
        if (pref === 'system') {
            return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
        }
        return pref;
    }

    function applyTheme(pref) {
        const resolved = resolveTheme(pref);
        document.documentElement.setAttribute('data-theme', resolved);
        // Update meta theme-color
        const meta = document.querySelector('meta[name="theme-color"]');
        if (meta) {
            meta.content = resolved === 'dark' ? '#050403' : '#F7F1E6';
        }
    }

    function syncAppearanceButtons(pref) {
        const map = { dark: 'appearanceDark', light: 'appearanceLight', system: 'appearanceSystem' };
        Object.entries(map).forEach(function(entry) {
            var btn = document.getElementById(entry[1]);
            if (!btn) return;
            btn.classList.toggle('appearance-theme-btn-active', entry[0] === pref);
        });
    }

    function setTheme(pref) {
        if (!VALID.includes(pref)) pref = 'system';
        safeSetStored(pref);
        applyTheme(pref);
        // Sync all toggle buttons on the page
        document.querySelectorAll('[data-theme-btn]').forEach(btn => {
            const active = btn.dataset.themeBtn === pref;
            btn.setAttribute('aria-pressed', String(active));
            btn.classList.toggle('theme-btn-active', active);
        });
        syncAppearanceButtons(pref);
    }

    // Apply immediately (before paint) to avoid flash
    applyTheme(getPreference());

    // Listen for system preference changes when set to 'system'
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    const onSystemChange = () => {
        if (getPreference() === 'system') applyTheme('system');
    };
    if (mediaQuery.addEventListener) {
        mediaQuery.addEventListener('change', onSystemChange);
    } else if (mediaQuery.addListener) {
        mediaQuery.addListener(onSystemChange);
    }

    // Expose globally
    window.TTPTheme = {
        get: getPreference,
        set: setTheme,
        apply: function () { applyTheme(getPreference()); },
    };
    window.setTheme = setTheme;
    window.getTheme = getPreference;

    // Wire up buttons after DOM ready
    document.addEventListener('DOMContentLoaded', function () {
        const pref = getPreference();
        document.querySelectorAll('[data-theme-btn]').forEach(btn => {
            const active = btn.dataset.themeBtn === pref;
            btn.setAttribute('aria-pressed', String(active));
            btn.classList.toggle('theme-btn-active', active);
            btn.addEventListener('click', function () {
                window.TTPTheme.set(btn.dataset.themeBtn);
            });
        });
        syncAppearanceButtons(pref);
    });
})();
