// Settings page script (moved out of templates/settings.html so browsers cache it).
// Per-request values come from the JSON block #settingsConfig rendered by the template.
const SETTINGS_CONFIG = JSON.parse(document.getElementById('settingsConfig').textContent || '{}');
        document.addEventListener('DOMContentLoaded', () => {
            if (document.activeElement && document.activeElement.tagName === 'INPUT') {
                document.activeElement.blur();
            }
        });

        const settingsEmail = document.getElementById('settingsEmail');
        if (settingsEmail) {
            const applyDomain = (domain) => {
                const value = (settingsEmail.value || '').trim();
                if (!value) return;
                if (value.includes('@')) {
                    const local = value.split('@')[0];
                    settingsEmail.value = `${local}@${domain}`;
                    return;
                }
                settingsEmail.value = `${value}@${domain}`;
            };
            settingsEmail.addEventListener('blur', () => {
                const value = (settingsEmail.value || '').trim();
                if (!value) return;
                if (!value.includes('@')) {
                    settingsEmail.value = `${value}@gmail.com`;
                } else if (value.endsWith('@')) {
                    settingsEmail.value = `${value}gmail.com`;
                }
            });
            document.querySelectorAll('.email-domain-chip').forEach(chip => {
                chip.addEventListener('click', () => applyDomain(chip.dataset.domain || 'gmail.com'));
            });
        }

        try {
            // Older versions kept typed values (incl. new passwords) in sessionStorage.
            ['settings.new_name', 'settings.new_user_id', 'settings.new_password',
             'settings.confirm_password', 'settings.username_otp', 'settings.password_otp']
                .forEach(key => sessionStorage.removeItem(key));
        } catch (err) { /* storage blocked */ }

        // 'Send code' for the User ID / Password forms posts in the background, so
        // what's typed (incl. the new password) stays put without being stashed in
        // storage. Falls back to a normal submit if the request can't be made.
        ['usernameOtpForm', 'passwordOtpForm'].forEach(formId => {
            const form = document.getElementById(formId);
            if (!form) return;
            form.addEventListener('submit', async (e) => {
                if (form.dataset.fallback === '1') return;
                e.preventDefault();
                const btn = e.submitter || document.querySelector(`button[form="${formId}"]`);
                if (!btn || btn.disabled) return;
                const idle = btn.textContent;
                btn.disabled = true;
                btn.textContent = 'Sending...';
                let data = null;
                try {
                    const resp = await fetch(form.action, {
                        method: 'POST',
                        body: new FormData(form),
                        headers: { 'Accept': 'application/json' },
                        credentials: 'same-origin'
                    });
                    if ((resp.headers.get('Content-Type') || '').includes('application/json')) {
                        data = await resp.json();
                    }
                } catch (err) {
                    data = null;
                }
                btn.disabled = false;
                btn.textContent = idle;
                if (!data) {
                    // Session expired or offline: let the browser handle it normally.
                    form.dataset.fallback = '1';
                    form.requestSubmit ? form.requestSubmit(btn) : form.submit();
                    return;
                }
                if (window.showToast) {
                    window.showToast(data.message || (data.ok ? 'Verification code sent.' : 'Could not send the code.'), data.ok ? 'success' : 'error');
                }
                if (data.ok) {
                    const codeInput = btn.parentElement && btn.parentElement.querySelector('input[name="otp_code"]');
                    if (codeInput) codeInput.focus();
                }
            });
        });


        const updateForms = ['updateUsernameForm', 'updatePasswordForm'];
        updateForms.forEach(formId => {
            const form = document.getElementById(formId);
            if (!form) return;
            form.addEventListener('submit', (e) => {
                const btn = e.submitter || form.querySelector('button[type="submit"]');
                if (btn && !btn.disabled) {
                    markFormBusy(btn, 'Updating...');
                }
            });
        });

        const emailForms = document.querySelectorAll('form[action="' + SETTINGS_CONFIG.profileRequestOtpUrl + '"]:not(#usernameOtpForm):not(#passwordOtpForm), form[action="' + SETTINGS_CONFIG.updateProfileUrl + '"]');
        emailForms.forEach(form => {
            form.addEventListener('submit', (e) => {
                const btn = e.submitter || form.querySelector('button[type="submit"]');
                if (btn && !btn.disabled) {
                    markFormBusy(btn, btn.textContent.includes('Send') ? 'Sending...' : 'Updating...');
                }
            });
        });

        const iconForm = document.querySelector('form[action="' + SETTINGS_CONFIG.updateAppIconUrl + '"]');
        if (iconForm) {
            iconForm.addEventListener('submit', () => {
                const btn = iconForm.querySelector('button[type="submit"]');
                if (btn) {
                    markFormBusy(btn, 'Uploading...');
                }
            });
        }

        const profileTabs = document.querySelectorAll('.profile-tab');
        const profileTabContents = document.querySelectorAll('.profile-tab-content');
        const switchTab = (tabName) => {
            profileTabs.forEach(tab => {
                const isActive = tab.dataset.tab === tabName;
                tab.classList.toggle('border-gray-900', isActive);
                tab.classList.toggle('text-gray-900', isActive);
                tab.classList.toggle('border-transparent', !isActive);
                tab.classList.toggle('text-gray-500', !isActive);
                tab.setAttribute('aria-selected', isActive ? 'true' : 'false');
            });
            profileTabContents.forEach(content => {
                content.classList.toggle('hidden', content.dataset.tabContent !== tabName);
            });
        };
        profileTabs.forEach(tab => {
            tab.addEventListener('click', () => {
                switchTab(tab.dataset.tab || 'username');
            });
        });

        const authToggles = document.querySelectorAll('.profile-auth-toggle');
        const authFields = document.querySelectorAll('.profile-auth-field');
        const setAuthMode = (target, mode) => {
            // Only touch this form's fields/toggles (the User ID and Password forms
            // each have their own password/OTP switch).
            authFields.forEach(field => {
                if (field.dataset.target !== target) return;
                field.classList.toggle('hidden', field.dataset.mode !== mode);
            });
            authToggles.forEach(btn => {
                if (btn.dataset.target !== target) return;
                const isActive = btn.dataset.mode === mode;
                btn.setAttribute('aria-pressed', isActive ? 'true' : 'false');
                btn.classList.toggle('bg-gray-900', isActive);
                btn.classList.toggle('text-amber-300', isActive);
                btn.classList.toggle('border-gray-900', isActive);
                btn.classList.toggle('bg-white/80', !isActive);
                btn.classList.toggle('text-gray-700', !isActive);
            });
        };
        setAuthMode('username', 'password');
        setAuthMode('password', 'password');
        authToggles.forEach(btn => {
            btn.addEventListener('click', () => {
                setAuthMode(btn.dataset.target || '', btn.dataset.mode || 'password');
            });
        });

        const passwordInput = document.getElementById('settingsNewPassword');
        const strengthBar = document.getElementById('passwordStrengthBar');
        const strengthText = document.getElementById('passwordStrengthText');
        const strengthContainer = document.getElementById('passwordStrength');
        if (passwordInput && strengthBar && strengthText && strengthContainer) {
            passwordInput.addEventListener('input', () => {
                const pwd = passwordInput.value;
                if (!pwd) {
                    strengthContainer.classList.add('hidden');
                    return;
                }
                strengthContainer.classList.remove('hidden');
                let strength = 0;
                if (pwd.length >= 8) strength += 25;
                if (pwd.length >= 12) strength += 15;
                if (/[a-z]/.test(pwd) && /[A-Z]/.test(pwd)) strength += 20;
                if (/\d/.test(pwd)) strength += 20;
                if (/[^a-zA-Z0-9]/.test(pwd)) strength += 20;
                // Label colours meet WCAG AA (4.5:1) for this small text in each theme.
                const darkTheme = document.documentElement.getAttribute('data-theme') === 'dark';
                const colors = {
                    0: { bg: '#EF4444', text: 'Weak', color: darkTheme ? '#F87171' : '#B91C1C' },
                    40: { bg: '#F59E0B', text: 'Fair', color: darkTheme ? '#FBBF24' : '#B45309' },
                    60: { bg: '#10B981', text: 'Good', color: darkTheme ? '#34D399' : '#047857' },
                    80: { bg: '#059669', text: 'Strong', color: darkTheme ? '#6EE7B7' : '#065F46' }
                };
                let level = colors[0];
                if (strength >= 80) level = colors[80];
                else if (strength >= 60) level = colors[60];
                else if (strength >= 40) level = colors[40];
                strengthBar.style.width = `${strength}%`;
                strengthBar.style.backgroundColor = level.bg;
                strengthText.textContent = level.text;
                strengthText.style.color = level.color;
            });
        }

        const sheetyInfoToggle = document.getElementById('sheetyInfoToggle');
        const sheetyInfoPanel = document.getElementById('sheetyInfoPanel');
        if (sheetyInfoToggle && sheetyInfoPanel) {
            const closeSheetyInfo = () => {
                sheetyInfoPanel.classList.add('hidden');
                sheetyInfoToggle.setAttribute('aria-expanded', 'false');
            };
            sheetyInfoToggle.addEventListener('click', (event) => {
                event.stopPropagation();
                const isOpen = !sheetyInfoPanel.classList.contains('hidden');
                if (isOpen) {
                    closeSheetyInfo();
                } else {
                    sheetyInfoPanel.classList.remove('hidden');
                    sheetyInfoToggle.setAttribute('aria-expanded', 'true');
                }
            });
            document.addEventListener('click', (event) => {
                if (!sheetyInfoPanel.contains(event.target) && event.target !== sheetyInfoToggle) {
                    closeSheetyInfo();
                }
            });
        }

        const exportCsvModal = document.getElementById('exportCsvModal');
        const openExportCsvModal = document.getElementById('openExportCsvModal');
        const exportCsvForm = document.getElementById('exportCsvForm');
        const exportRangeFields = document.getElementById('exportRangeFields');
        const exportStartDate = document.getElementById('exportStartDate');
        const exportEndDate = document.getElementById('exportEndDate');
        const exportModeInputs = document.querySelectorAll('input[name="exportMode"]');
        const exportFormatInputs = document.querySelectorAll('input[name="exportFormat"]');
        const exportOptionCards = document.querySelectorAll('[data-export-option]');
        const exportFormatCards = document.querySelectorAll('[data-export-format-option]');

        const notifyExportError = (message) => {
            if (window.showErrorToast) {
                window.showErrorToast(message);
                return;
            }
            alert(message);
        };

        const updateExportModeUI = () => {
            const mode = document.querySelector('input[name="exportMode"]:checked')?.value || 'all';
            const isRange = mode === 'range';
            exportOptionCards.forEach((card) => {
                card.dataset.selected = card.dataset.exportOption === mode ? 'true' : 'false';
            });
            if (exportRangeFields) {
                exportRangeFields.classList.toggle('hidden', !isRange);
            }
            if (exportStartDate) exportStartDate.required = isRange;
            if (exportEndDate) exportEndDate.required = isRange;
        };

        const updateExportFormatUI = () => {
            const format = document.querySelector('input[name="exportFormat"]:checked')?.value || 'csv';
            exportFormatCards.forEach((card) => {
                card.dataset.selected = card.dataset.exportFormatOption === format ? 'true' : 'false';
            });
        };

        let exportModalOpener = null;
        const closeExportModal = () => {
            if (!exportCsvModal) return;
            exportCsvModal.classList.add('hidden');
            document.body.classList.remove('overflow-hidden');
            if (exportModalOpener && document.body.contains(exportModalOpener)) exportModalOpener.focus();
            exportModalOpener = null;
        };

        const openExportModal = () => {
            if (!exportCsvModal) return;
            exportModalOpener = document.activeElement;
            exportCsvModal.classList.remove('hidden');
            document.body.classList.add('overflow-hidden');
            updateExportModeUI();
            updateExportFormatUI();
            // Move focus into the dialog so keyboard/screen-reader users land on its first choice.
            exportCsvModal.querySelector('input[name="exportMode"]:checked, input[name="exportMode"]')?.focus();
        };

        if (openExportCsvModal) {
            openExportCsvModal.addEventListener('click', openExportModal);
        }

        document.querySelectorAll('[data-close-export-modal="true"]').forEach((el) => {
            el.addEventListener('click', closeExportModal);
        });

        if (exportModeInputs.length) {
            exportModeInputs.forEach((input) => {
                input.addEventListener('change', updateExportModeUI);
            });
        }

        if (exportFormatInputs.length) {
            exportFormatInputs.forEach((input) => {
                input.addEventListener('change', updateExportFormatUI);
            });
        }

        if (exportCsvModal) {
            exportCsvModal.addEventListener('click', (event) => {
                if (event.target === exportCsvModal) {
                    closeExportModal();
                }
            });
        }

        document.addEventListener('keydown', (event) => {
            if (!exportCsvModal || exportCsvModal.classList.contains('hidden')) return;
            if (event.key === 'Escape') {
                closeExportModal();
                return;
            }
            if (event.key === 'Tab') {
                // Keep Tab inside the dialog.
                const focusable = Array.from(exportCsvModal.querySelectorAll('button, input, select, a[href], [tabindex]:not([tabindex="-1"])'))
                    .filter((el) => !el.disabled && el.offsetParent !== null);
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
        });

        if (exportCsvForm) {
            exportCsvForm.addEventListener('submit', (event) => {
                event.preventDefault();
                const mode = document.querySelector('input[name="exportMode"]:checked')?.value || 'all';
                const format = document.querySelector('input[name="exportFormat"]:checked')?.value || 'csv';
                let url = `/api/export-csv?mode=all&format=${encodeURIComponent(format)}`;

                if (mode === 'range') {
                    const start = String(exportStartDate?.value || '').trim();
                    const end = String(exportEndDate?.value || '').trim();
                    if (!start || !end) {
                        notifyExportError('Please select both start and end dates.');
                        return;
                    }
                    if (start > end) {
                        notifyExportError('End date must be on or after start date.');
                        return;
                    }
                    url = `/api/export-csv?mode=range&format=${encodeURIComponent(format)}&start_date=${encodeURIComponent(start)}&end_date=${encodeURIComponent(end)}`;
                }

                closeExportModal();
                downloadExport(url);
            });
        }

        // Fetch first so errors and empty ranges become a toast instead of a raw
        // JSON error page or an empty file.
        async function downloadExport(url) {
            try {
                const response = await fetch(url, { credentials: 'include' });
                if (response.status === 401) {
                    window.location.href = '/login?next=' + encodeURIComponent('/settings');
                    return;
                }
                if (!response.ok) {
                    let message = '';
                    try { message = (await response.json()).error || ''; } catch (e) { /* not JSON */ }
                    notifyExportError(message || `Export failed (HTTP ${response.status}).`);
                    return;
                }
                const rows = Number(response.headers.get('X-Export-Rows'));
                if (rows === 0) {
                    if (window.showWarningToast) window.showWarningToast('No logs in that range, so there is nothing to export.');
                    return;
                }
                const blob = await response.blob();
                const disposition = response.headers.get('Content-Disposition') || '';
                const match = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(disposition);
                const link = document.createElement('a');
                link.href = URL.createObjectURL(blob);
                link.download = match ? decodeURIComponent(match[1]) : 'time-tracker-export';
                document.body.appendChild(link);
                link.click();
                link.remove();
                setTimeout(() => URL.revokeObjectURL(link.href), 10000);
                if (window.showSuccessToast && Number.isFinite(rows)) {
                    window.showSuccessToast(`Exported ${rows} ${rows === 1 ? 'entry' : 'entries'}.`);
                }
            } catch (error) {
                notifyExportError('Export failed: check your connection and try again.');
            }
        }

        // API Account Management
        const toggleApiToken = document.getElementById('toggleApiToken');
        if (toggleApiToken) {
            toggleApiToken.addEventListener('click', () => {
                const input = document.getElementById('newApiToken');
                const show = input.type === 'password';
                input.type = show ? 'text' : 'password';
                toggleApiToken.textContent = show ? 'Hide' : 'Show';
                toggleApiToken.setAttribute('aria-pressed', show ? 'true' : 'false');
            });
        }

        const addApiAccountBtn = document.getElementById('addApiAccount');
        const addApiForm = document.getElementById('addApiForm');
        const cancelAddApiBtn = document.getElementById('cancelAddApi');
        const newApiAccountForm = document.getElementById('newApiAccountForm');
        const sheetyAccountsToggle = document.getElementById('sheetyAccountsToggle');
        const sheetyAccountsPanel = document.getElementById('sheetyAccountsPanel');
        const sheetyAccountsChevron = document.getElementById('sheetyAccountsChevron');

        const setSheetyAccountsExpanded = window.setSheetyAccountsExpanded = (expanded) => {
            if (!sheetyAccountsToggle || !sheetyAccountsPanel) return;
            sheetyAccountsToggle.setAttribute('aria-expanded', expanded ? 'true' : 'false');
            sheetyAccountsPanel.classList.toggle('hidden', !expanded);
            if (sheetyAccountsChevron) {
                sheetyAccountsChevron.textContent = expanded ? '▴' : '▾';
            }
        };

        if (sheetyAccountsToggle) {
            sheetyAccountsToggle.addEventListener('click', () => {
                const isExpanded = sheetyAccountsToggle.getAttribute('aria-expanded') === 'true';
                setSheetyAccountsExpanded(!isExpanded);
            });
        }

        // Arriving from "Connect sheet" (#ai-keys) or the API Keys tab: open the accounts panel.
        const expandAccountsForHash = () => {
            if (window.location.hash === '#ai-keys') setSheetyAccountsExpanded(true);
        };
        expandAccountsForHash();
        window.addEventListener('hashchange', expandAccountsForHash);

        if (addApiAccountBtn && addApiForm) {
            addApiAccountBtn.addEventListener('click', () => {
                setSheetyAccountsExpanded(true);
                addApiForm.classList.remove('hidden');
                addApiAccountBtn.style.display = 'none';
            });
        }

        if (cancelAddApiBtn && addApiForm) {
            cancelAddApiBtn.addEventListener('click', () => {
                addApiForm.classList.add('hidden');
                addApiAccountBtn.style.display = 'block';
                newApiAccountForm.reset();
            });
        }

        // In-page toasts instead of blocking alert() boxes (alert as a fallback).
        const notifyError = (message) => (window.showErrorToast ? window.showErrorToast(message) : alert(message));
        const notifySuccess = (message) => (window.showSuccessToast ? window.showSuccessToast(message) : alert(message));

        if (newApiAccountForm) {
            newApiAccountForm.addEventListener('submit', async (e) => {
                e.preventDefault();
                const saveBtn = document.getElementById('saveApiAccountBtn');
                // A double click used to save the same account twice.
                if (saveBtn?.disabled) return;
                const saveLabel = saveBtn ? saveBtn.textContent : '';
                if (saveBtn) {
                    saveBtn.disabled = true;
                    saveBtn.textContent = 'Saving...';
                }
                const formData = {
                    account_email: document.getElementById('newAccountEmail').value.trim(),
                    api_base_url: document.getElementById('newApiBaseUrl').value.trim(),
                    api_token: document.getElementById('newApiToken').value.trim()
                };

                try {
                    const response = await fetch('/api/sheety-accounts', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(formData)
                    });

                    if (response.ok) {
                        window.location.reload();
                        return;
                    }

                    const contentType = response.headers.get('content-type') || '';
                    let message = 'Failed to add API account';
                    if (contentType.includes('application/json')) {
                        const error = await response.json();
                        message = error.error || message;
                    } else {
                        message = `Failed to add API account (HTTP ${response.status})`;
                    }
                    notifyError(message);
                } catch (error) {
                    notifyError('Could not reach the server. Check your connection and try again.');
                } finally {
                    if (saveBtn) {
                        saveBtn.disabled = false;
                        saveBtn.textContent = saveLabel;
                    }
                }
            });
        }

        // Delete API account
        document.addEventListener('click', async (e) => {
            if (e.target.classList.contains('delete-api-btn')) {
                const accountId = e.target.dataset.accountId;
                if (!confirm('Are you sure you want to delete this API account?')) return;

                try {
                    const response = await fetch(`/api/sheety-accounts/${accountId}`, {
                        method: 'DELETE'
                    });

                    if (response.ok) {
                        window.location.reload();
                        return;
                    }

                    const contentType = response.headers.get('content-type') || '';
                    let message = 'Failed to delete API account';
                    if (contentType.includes('application/json')) {
                        const error = await response.json();
                        message = error.error || message;
                    } else {
                        message = `Failed to delete API account (HTTP ${response.status})`;
                    }
                    notifyError(message);
                } catch (error) {
                    notifyError('Could not reach the server. Check your connection and try again.');
                }
            }

            // Test API account
            if (e.target.classList.contains('test-api-btn')) {
                const accountId = e.target.dataset.accountId;
                const btn = e.target;
                btn.textContent = 'Testing...';
                btn.disabled = true;

                try {
                    const response = await fetch(`/api/sheety-accounts/${accountId}/test`);
                    const contentType = response.headers.get('content-type') || '';
                    let result = null;

                    if (contentType.includes('application/json')) {
                        result = await response.json();
                    }

                    if (response.ok && result?.success) {
                        const rows = Number(result.row_count || 0);
                        notifySuccess(`Connection works: ${rows} row${rows === 1 ? '' : 's'} found.`);
                        // Reload to show the updated status, after the toast has been seen.
                        setTimeout(() => window.location.reload(), 1500);
                        return;
                    }

                    const errorMessage = result?.error || `Test failed (HTTP ${response.status})`;
                    notifyError(`Connection test failed: ${errorMessage}`);
                } catch (error) {
                    notifyError('Could not reach the server. Check your connection and try again.');
                } finally {
                    btn.textContent = 'Test';
                    btn.disabled = false;
                }
            }
        });

        const dashboardUrl = SETTINGS_CONFIG.dashboardUrl;
        const adminUrl = SETTINGS_CONFIG.adminUrl;
        const sectionShortcuts = {
            '1': 'account-settings',
            '2': 'ai-keys',
            '3': 'goals-settings',
            '4': 'appearance-settings',
        };
        let shortcutToast = null;

        document.addEventListener('keydown', (event) => {
            const tag = event.target?.tagName;
            if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || event.target?.isContentEditable) return;
            if (exportCsvModal && !exportCsvModal.classList.contains('hidden')) return;

            if ((event.metaKey || event.ctrlKey) && (event.key === '/' || event.key === '?')) {
                event.preventDefault();
                if (shortcutToast && !document.body.contains(shortcutToast)) {
                    shortcutToast = null;
                }
                if (shortcutToast?.__removeToast) {
                    shortcutToast.__removeToast();
                    shortcutToast = null;
                    return;
                }
                if (window.showToast) {
                    shortcutToast = window.showToast(`
                        <div class="space-y-3">
                            <div class="text-xs uppercase tracking-[0.2em] text-white/80 font-semibold">Keyboard Shortcuts</div>
                            <div class="space-y-2 text-sm">
                                <div class="flex items-center gap-2">
                                    <kbd class="toast-kbd">1</kbd>
                                    <span class="toast-kbd-label">Account &amp; Security</span>
                                </div>
                                <div class="flex items-center gap-2">
                                    <kbd class="toast-kbd">2</kbd>
                                    <span class="toast-kbd-label">API Keys</span>
                                </div>
                                <div class="flex items-center gap-2">
                                    <kbd class="toast-kbd">3</kbd>
                                    <span class="toast-kbd-label">Daily Goals</span>
                                </div>
                                <div class="flex items-center gap-2">
                                    <kbd class="toast-kbd">4</kbd>
                                    <span class="toast-kbd-label">Appearance</span>
                                </div>
                                <div class="flex items-center gap-2">
                                    <kbd class="toast-kbd">D</kbd>
                                    <span class="toast-kbd-label">Dashboard</span>
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
                return;
            }

            if (event.metaKey || event.ctrlKey || event.altKey) return;
            const key = event.key.toLowerCase();
            if (key === 'd') {
                window.location.href = dashboardUrl;
            } else if (key === 'a' && adminUrl) {
                window.location.href = adminUrl;
            } else if (sectionShortcuts[key]) {
                scrollToSection(sectionShortcuts[key]);
            }
        });

        function scrollToSection(sectionId) {
            if (!sectionId) return;
            const target = document.getElementById(sectionId);
            if (!target) return;
            target.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }

    