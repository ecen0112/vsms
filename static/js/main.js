// VSMS Main JavaScript

// ===== Sidebar Toggle =====
document.getElementById('sidebarToggle')?.addEventListener('click', () => {
    document.getElementById('sidebar').classList.toggle('open');
});

// ===== Current Date in Topbar =====
const dateEl = document.getElementById('currentDate');
if (dateEl) {
    const now = new Date();
    dateEl.textContent = now.toLocaleDateString('en-PH', {
        weekday: 'short', year: 'numeric', month: 'short', day: 'numeric'
    });
}

// ===== Alert Badge Updater =====
async function updateAlertBadge() {
    try {
        const res = await fetch('/api/alerts/count');
        const data = await res.json();
        const badge = document.getElementById('topbar-badge');
        const navBadge = document.getElementById('alert-badge');
        if (badge) {
            if (data.total > 0) {
                badge.textContent = data.total > 99 ? '99+' : data.total;
                badge.style.display = 'flex';
            } else {
                badge.style.display = 'none';
            }
        }
        if (navBadge) {
            if (data.total > 0) {
                navBadge.textContent = data.total > 99 ? '99+' : data.total;
                navBadge.style.display = 'inline-flex';
            } else {
                navBadge.style.display = 'none';
            }
        }
    } catch(e) {}
}

updateAlertBadge();
setInterval(updateAlertBadge, 60000); // Refresh every minute

// ===== Auto-dismiss flash alerts =====
setTimeout(() => {
    document.querySelectorAll('.vsms-alert').forEach(el => {
        const bsAlert = bootstrap.Alert.getOrCreateInstance(el);
        bsAlert?.close();
    });
}, 5000);
