/* ============================================
   TATANGA HUB - JavaScript Core
   WebSocket + UI Updates
   ============================================ */

let ws = null;
let wsReconnectTimer = null;
let notifCount = 0;

// ============================================
// WEBSOCKET CONNECTION
// ============================================
function connectWS() {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(`${proto}//${location.host}/ws`);

    ws.onopen = () => {
        console.log('[WS] Baglandi');
        updateWSStatus(true);
        if (wsReconnectTimer) {
            clearTimeout(wsReconnectTimer);
            wsReconnectTimer = null;
        }
    };

    ws.onmessage = (event) => {
        try {
            const msg = JSON.parse(event.data);
            handleWSMessage(msg);
        } catch (e) {
            console.error('[WS] Parse hatasi:', e);
        }
    };

    ws.onclose = () => {
        console.log('[WS] Baglanti kesildi');
        updateWSStatus(false);
        wsReconnectTimer = setTimeout(connectWS, 3000);
    };

    ws.onerror = (err) => {
        console.error('[WS] Hata:', err);
    };
}

function updateWSStatus(online) {
    const el = document.getElementById('ws-status');
    if (el) {
        const dot = el.querySelector('.dot');
        const text = el.querySelector('small');
        if (online) {
            dot.className = 'dot online';
            text.textContent = 'Canli baglanti aktif';
        } else {
            dot.className = 'dot offline';
            text.textContent = 'Baglanti bekleniyor...';
        }
    }
}

// ============================================
// WS MESSAGE HANDLER
// ============================================
function handleWSMessage(msg) {
    const { event, data, ts } = msg;

    switch (event) {
        case 'scrape_started':
            showToast(`Kazima basladi: ${data.keyword}`, 'info');
            updateJobBadge(1);
            break;

        case 'scrape_progress':
            if (data.status === 'scraping') {
                addScrapeLog(`<i class="fas fa-spinner fa-spin" style="color:#ffa500;"></i> ${data.platform} taraniyor...`);
                updatePlatformBadge(data.platform, 'Taraniyor', '#ffa500');
            } else if (data.status === 'done') {
                addScrapeLog(`<i class="fas fa-check-circle" style="color:#28a745;"></i> ${data.platform}: <strong>${data.found}</strong> urun bulundu`);
                updatePlatformBadge(data.platform, data.found + ' urun', '#28a745');
                updateProgressBar(data.platform);
            }
            break;

        case 'scrape_completed':
            showToast(`Kazima tamamlandi! ${data.total_found} urun, ${data.profitable} karli`, 'success');
            updateJobBadge(-1);
            markScrapeComplete();
            refreshStats();
            break;

        case 'scrape_error':
            showToast(`${data.platform} hatasi: ${data.error}`, 'danger');
            addScrapeLog(`<i class="fas fa-exclamation-triangle" style="color:#dc3545;"></i> ${data.platform}: ${data.error}`);
            updatePlatformBadge(data.platform, 'Hata', '#dc3545');
            break;

        case 'source_checked':
            showToast(`Kaynak kontrol: ${data.product_id} - ${data.status}`,
                data.status === 'active' ? 'success' : 'warning');
            break;

        case 'bg_removed':
            showToast(`Arka plan kaldirildi: ${data.count} gorsel`, 'success');
            break;

        case 'url_product_added':
            showToast(`Urun yakalandi: ${data.title}`, 'success');
            break;

        default:
            console.log('[WS] Bilinmeyen event:', event, data);
    }
}

// ============================================
// UI HELPERS
// ============================================
function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const icons = {
        success: 'fa-check-circle',
        danger: 'fa-exclamation-circle',
        warning: 'fa-exclamation-triangle',
        info: 'fa-info-circle'
    };

    const toast = document.createElement('div');
    toast.className = `toast show border-${type}`;
    toast.setAttribute('role', 'alert');
    toast.innerHTML = `
        <div class="toast-body d-flex align-items-center gap-2">
            <i class="fas ${icons[type] || icons.info} text-${type}"></i>
            <span>${message}</span>
            <button class="btn-close btn-close-white ms-auto" onclick="this.closest('.toast').remove()"></button>
        </div>
    `;
    container.appendChild(toast);

    // Auto remove after 5 sec
    setTimeout(() => {
        if (toast.parentNode) toast.remove();
    }, 5000);

    // Increment notification count
    notifCount++;
    updateNotifBadge();
}

function updateNotifBadge() {
    const el = document.getElementById('notif-count');
    if (el) {
        if (notifCount > 0) {
            el.textContent = notifCount > 99 ? '99+' : notifCount;
            el.style.display = 'flex';
        } else {
            el.style.display = 'none';
        }
    }
}

function updateJobBadge(delta) {
    const el = document.getElementById('stat-active-jobs');
    if (el) {
        let current = parseInt(el.textContent) || 0;
        current = Math.max(0, current + delta);
        el.textContent = `${current} Aktif Is`;
    }
}

function addScrapeLog(msg) {
    const log = document.getElementById('scrape-log');
    if (log) {
        const div = document.createElement('div');
        div.className = 'mb-1';
        div.style.borderBottom = '1px solid rgba(255,255,255,0.05)';
        div.style.paddingBottom = '2px';
        div.style.fontSize = '0.7rem';
        div.innerHTML = `<span style="color:#666;">${new Date().toLocaleTimeString('de-DE')}</span> ${msg}`;
        log.prepend(div);
    }
}

function updatePlatformBadge(platform, text, color) {
    const badge = document.getElementById('ps-badge-' + platform);
    if (badge) {
        badge.textContent = text;
        badge.style.background = color;
        badge.style.color = '#fff';
    }
}

let progressPlatforms = [];
function updateProgressBar(platform) {
    const bar = document.getElementById('scrape-bar');
    if (!bar) return;

    if (!progressPlatforms.includes(platform)) {
        progressPlatforms.push(platform);
    }

    const total = document.querySelectorAll('.chip.active').length || 7;
    const pct = Math.round((progressPlatforms.length / total) * 100);
    bar.style.width = pct + '%';
}

function markScrapeComplete() {
    const bar = document.getElementById('scrape-bar');
    if (bar) {
        bar.style.width = '100%';
        bar.classList.remove('progress-bar-animated');
        bar.classList.add('bg-success');
    }
    const status = document.getElementById('quick-status');
    if (status) {
        status.textContent = 'Tamamlandi';
        status.className = 'badge bg-success';
    }
    progressPlatforms = [];
}

async function refreshStats() {
    try {
        const resp = await fetch('/api/stats');
        const data = await resp.json();

        const map = {
            's-total': data.total,
            's-scraped': data.scraped,
            's-profitable': data.profitable,
            's-published': data.published,
            's-sold': data.sold,
            's-jobs': data.active_jobs,
            'stat-total': `${data.total} Urun`,
            'stat-active-jobs': `${data.active_jobs} Aktif Is`,
        };

        for (const [id, val] of Object.entries(map)) {
            const el = document.getElementById(id);
            if (el) el.textContent = val;
        }
    } catch (e) {
        console.error('Stats refresh hatasi:', e);
    }
}

function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    const backdrop = document.getElementById('sidebar-backdrop');
    sidebar.classList.toggle('open');
    if (backdrop) {
        backdrop.classList.toggle('show');
    }
}

// ============================================
// INIT
// ============================================
document.addEventListener('DOMContentLoaded', () => {
    connectWS();
    // Refresh stats every 30 sec
    setInterval(refreshStats, 30000);
});
