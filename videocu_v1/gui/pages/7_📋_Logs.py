"""
VIDEOCU v1 - Logs Dashboard
Sistem loglarını görüntüleme
"""

import streamlit as st
import sys
import os
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

st.set_page_config(
    page_title="Logs - VIDEOCU",
    page_icon="📋",
    layout="wide"
)

# Custom CSS
st.markdown("""
<style>
    .log-entry {
        background: #1e1e2e;
        padding: 8px 12px;
        border-radius: 6px;
        margin: 4px 0;
        font-family: monospace;
        font-size: 0.85rem;
    }
    .log-info { border-left: 3px solid #3498db; }
    .log-success { border-left: 3px solid #2ecc71; }
    .log-warning { border-left: 3px solid #f39c12; }
    .log-error { border-left: 3px solid #e74c3c; }
    .section-header {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        padding: 1rem 1.5rem;
        border-radius: 10px;
        margin-bottom: 1.5rem;
    }
</style>
""", unsafe_allow_html=True)

# Header
st.markdown('<div class="section-header"><h1 style="margin:0;color:white;">📋 Sistem Logları</h1><p style="margin:0;color:rgba(255,255,255,0.8);">Tüm sistem aktivitelerini takip edin</p></div>', unsafe_allow_html=True)

# Log directory
LOG_DIR = Path(__file__).parent.parent.parent / "output" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Tabs
tab1, tab2, tab3 = st.tabs(["📊 Aktiviteler", "⚠️ Hatalar", "📁 Log Dosyaları"])

with tab1:
    st.subheader("Son Aktiviteler")

    try:
        from modules.logger import get_recent_activities, log_activity

        activities = get_recent_activities(50)

        if activities:
            for act in activities:
                status = act.get('status', 'info')
                css_class = f"log-{status}"

                timestamp = act.get('timestamp', '')[:19]
                action = act.get('action', 'Unknown')
                details = act.get('details', {})

                details_str = ""
                if details:
                    details_str = " | " + " | ".join([f"{k}: {v}" for k, v in list(details.items())[:3]])

                st.markdown(f'<div class="log-entry {css_class}">[{timestamp}] <strong>{action}</strong>{details_str}</div>', unsafe_allow_html=True)
        else:
            st.info("Henüz aktivite kaydı yok")

    except Exception as e:
        st.warning(f"Aktivite logları yüklenemedi: {e}")

    # Refresh button
    if st.button("🔄 Yenile", key="refresh_activities"):
        st.rerun()

with tab2:
    st.subheader("Son Hatalar")

    try:
        from modules.logger import get_recent_errors

        errors = get_recent_errors(20)

        if errors:
            for err in errors:
                st.markdown(f'<div class="log-entry log-error"><pre>{err}</pre></div>', unsafe_allow_html=True)
        else:
            st.success("✅ Henüz hata kaydı yok!")

    except Exception as e:
        # Fallback: Error log dosyasını doğrudan oku
        error_log = LOG_DIR / "errors.log"
        if error_log.exists():
            with open(error_log, 'r', encoding='utf-8') as f:
                content = f.read()[-10000:]  # Son 10KB
                if content.strip():
                    st.code(content, language="log")
                else:
                    st.success("✅ Henüz hata kaydı yok!")
        else:
            st.info("Hata log dosyası henüz oluşturulmadı")

with tab3:
    st.subheader("Log Dosyaları")

    # Log files list
    log_files = list(LOG_DIR.glob("*.log*"))

    if log_files:
        for log_file in sorted(log_files, key=lambda x: x.stat().st_mtime, reverse=True):
            col1, col2, col3, col4 = st.columns([3, 1, 1, 1])

            with col1:
                st.write(f"📄 **{log_file.name}**")

            with col2:
                size_kb = log_file.stat().st_size / 1024
                st.write(f"{size_kb:.1f} KB")

            with col3:
                mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
                st.write(mtime.strftime("%Y-%m-%d %H:%M"))

            with col4:
                if st.button("👁️", key=f"view_{log_file.name}", help="Görüntüle"):
                    st.session_state['selected_log'] = log_file

        # Selected log viewer
        if 'selected_log' in st.session_state:
            st.divider()
            st.subheader(f"📄 {st.session_state['selected_log'].name}")

            try:
                with open(st.session_state['selected_log'], 'r', encoding='utf-8') as f:
                    # Son 100 satır
                    lines = f.readlines()[-100:]
                    content = ''.join(lines)

                st.code(content, language="log")

                # Download button
                st.download_button(
                    label="⬇️ İndir",
                    data=content,
                    file_name=st.session_state['selected_log'].name,
                    mime="text/plain"
                )

            except Exception as e:
                st.error(f"Dosya okunamadı: {e}")
    else:
        st.info("Henüz log dosyası oluşturulmadı")

# Sidebar stats
st.sidebar.subheader("📊 Log İstatistikleri")

try:
    from modules.logger import get_recent_activities

    activities = get_recent_activities(100)

    total = len(activities)
    success = sum(1 for a in activities if a.get('status') == 'success')
    warnings = sum(1 for a in activities if a.get('status') == 'warning')
    errors = sum(1 for a in activities if a.get('status') == 'error')

    st.sidebar.metric("Toplam Aktivite", total)

    col_s1, col_s2 = st.sidebar.columns(2)
    with col_s1:
        st.metric("Başarılı", success, delta=None)
    with col_s2:
        st.metric("Uyarı", warnings, delta=None)

    st.sidebar.metric("Hata", errors, delta=None if errors == 0 else f"+{errors}")

except Exception:
    st.sidebar.info("İstatistikler yüklenemedi")

# Clear logs
st.sidebar.divider()
if st.sidebar.button("🗑️ Eski Logları Temizle", type="secondary"):
    try:
        from modules.logger import clear_old_logs
        clear_old_logs(30)
        st.sidebar.success("30 günden eski loglar temizlendi")
    except Exception as e:
        st.sidebar.error(f"Temizleme hatası: {e}")

# Footer
st.markdown("---")
st.caption("VIDEOCU v1 - Logs Dashboard | Powered by Claude Code")
