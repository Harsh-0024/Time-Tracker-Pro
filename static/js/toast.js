(function() {
    'use strict';

    // Messages are plain text (server errors can echo user data); only the static 'shortcut'
    // cheat-sheets or callers passing {html: true} with already-escaped markup render HTML.
    window.showToast = function(message, type = 'info', duration = 5000, options = {}) {
        const container = document.getElementById('toastContainer');
        if (!container) return null;

        const toast = document.createElement('div');
        toast.className = 'toast-item pointer-events-auto transform transition-all duration-300 ease-out';
        // Errors interrupt; everything else is announced politely by the container.
        if (type === 'error') toast.setAttribute('role', 'alert');

        // Determine colors based on type
        let bgColor, borderColor, iconPath, iconColor;
        switch(type) {
            // Shades chosen so white text clears 4.5:1 (the lighter ones were ~2-3:1).
            case 'success':
                bgColor = '#047857';
                borderColor = '#065F46';
                iconColor = '#FFFFFF';
                iconPath = 'M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z';
                break;
            case 'error':
                bgColor = '#DC2626';
                borderColor = '#B91C1C';
                iconColor = '#FFFFFF';
                iconPath = 'M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z';
                break;
            case 'warning':
                bgColor = '#B45309';
                borderColor = '#92400E';
                iconColor = '#FFFFFF';
                iconPath = 'M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z';
                break;
            case 'failover':
                bgColor = '#7C3AED';
                borderColor = '#6D28D9';
                iconColor = '#FFFFFF';
                iconPath = 'M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4';
                break;
            case 'shortcut':
                bgColor = '#0F172A';
                borderColor = '#334155';
                iconColor = '#F8D574';
                iconPath = 'M12 3v18m9-9H3';
                break;
            default: // info
                bgColor = '#2563EB';
                borderColor = '#1D4ED8';
                iconColor = '#FFFFFF';
                iconPath = 'M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z';
        }

        toast.innerHTML = `
            <div class="flex items-start gap-3 px-4 py-3 rounded-xl shadow-2xl border-2 toast-surface" 
                 style="background: ${bgColor}; border-color: ${borderColor}; min-width: 280px; max-width: 420px;">
                <svg class="w-5 h-5 flex-shrink-0 mt-0.5" style="color: ${iconColor}" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="${iconPath}"></path>
                </svg>
                <div class="toast-message flex-1 text-sm font-medium" style="color: #FFFFFF; word-break: break-word;"></div>
                <button class="toast-close flex-shrink-0 ml-2 hover:opacity-70 transition-opacity" aria-label="Close">
                    <svg class="w-4 h-4" style="color: ${iconColor}" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                    </svg>
                </button>
            </div>
        `;
        const messageEl = toast.querySelector('.toast-message');
        if (options.html === true || type === 'shortcut') {
            messageEl.innerHTML = message;
        } else {
            messageEl.textContent = String(message ?? '');
        }

        // Add to container
        container.appendChild(toast);

        // Animate in
        requestAnimationFrame(() => {
            toast.style.opacity = '0';
            toast.style.transform = 'translateX(100px)';
            requestAnimationFrame(() => {
                toast.style.opacity = '1';
                toast.style.transform = 'translateX(0)';
            });
        });

        // Close handler
        const closeBtn = toast.querySelector('.toast-close');
        const removeToast = () => {
            toast.style.opacity = '0';
            toast.style.transform = 'translateX(100px)';
            setTimeout(() => {
                if (toast.parentNode) {
                    toast.parentNode.removeChild(toast);
                }
            }, 300);
        };

        if (closeBtn) {
            closeBtn.addEventListener('click', removeToast);
        }
        toast.__removeToast = removeToast;

        // Auto remove after duration
        if (duration > 0) {
            setTimeout(removeToast, duration);
        }
        return toast;
    };

    // API Failover notification helper
    window.showApiFailoverNotification = function(fromAccount, toAccount) {
        const esc = (value) => String(value ?? '').replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
        const message = `API switched from <strong>${esc(fromAccount)}</strong> to <strong>${esc(toAccount)}</strong> due to connection failure.`;
        window.showToast(message, 'failover', 8000, { html: true });
    };

    // Success helper
    window.showSuccessToast = function(message, duration) {
        window.showToast(message, 'success', duration);
    };

    // Error helper
    window.showErrorToast = function(message, duration) {
        window.showToast(message, 'error', duration);
    };

    // Warning helper
    window.showWarningToast = function(message, duration) {
        window.showToast(message, 'warning', duration);
    };

    // Info helper
    window.showInfoToast = function(message, duration) {
        window.showToast(message, 'info', duration);
    };

})();
