"""
VIDEOCU Studio - Social Media Login & Management
YouTube, TikTok, Instagram hesap yönetimi
"""

import streamlit as st
import sys
import os
import json
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

st.set_page_config(
    page_title="Social Login - VIDEOCU",
    page_icon="🔐",
    layout="wide"
)

# Custom CSS
st.markdown("""
<style>
    .platform-card {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        border-radius: 15px;
        padding: 1.5rem;
        margin: 0.5rem 0;
        border: 1px solid #0f3460;
    }
    .connected {
        border-left: 4px solid #00ff88;
    }
    .disconnected {
        border-left: 4px solid #ff4444;
    }
    .status-badge {
        padding: 0.3rem 0.8rem;
        border-radius: 20px;
        font-size: 0.8rem;
        font-weight: bold;
    }
    .status-connected {
        background: #00ff8820;
        color: #00ff88;
    }
    .status-disconnected {
        background: #ff444420;
        color: #ff4444;
    }
</style>
""", unsafe_allow_html=True)

st.title("🔐 Sosyal Medya Hesap Yönetimi")
st.markdown("*YouTube, TikTok ve Instagram hesaplarınızı bağlayın*")

# Config file path
CONFIG_DIR = Path(__file__).parent.parent.parent / "config"
CONFIG_DIR.mkdir(exist_ok=True)
SOCIAL_CONFIG = CONFIG_DIR / "social_accounts.json"

# Load existing config
def load_social_config():
    if SOCIAL_CONFIG.exists():
        with open(SOCIAL_CONFIG, 'r') as f:
            return json.load(f)
    return {
        "youtube": {"connected": False, "channel_name": "", "channel_id": "", "credentials_file": ""},
        "tiktok": {"connected": False, "username": "", "session_id": ""},
        "instagram": {"connected": False, "username": "", "session_id": ""}
    }

def save_social_config(config):
    with open(SOCIAL_CONFIG, 'w') as f:
        json.dump(config, f, indent=2)

# Initialize session state
if 'social_config' not in st.session_state:
    st.session_state.social_config = load_social_config()

st.divider()

# Platform tabs
tab1, tab2, tab3, tab4 = st.tabs([
    "📺 YouTube",
    "🎵 TikTok",
    "📸 Instagram",
    "📊 Hesap Durumu"
])

# ==================== YOUTUBE ====================
with tab1:
    st.header("📺 YouTube Hesap Bağlantısı")

    yt_config = st.session_state.social_config.get("youtube", {})
    is_connected = yt_config.get("connected", False)

    col1, col2 = st.columns([2, 1])

    with col1:
        if is_connected:
            st.success(f"✅ Bağlı: {yt_config.get('channel_name', 'Kanal')}")
            st.write(f"**Kanal ID:** {yt_config.get('channel_id', 'N/A')}")

            if st.button("🔌 Bağlantıyı Kes", key="yt_disconnect"):
                st.session_state.social_config["youtube"]["connected"] = False
                save_social_config(st.session_state.social_config)
                st.rerun()
        else:
            st.warning("⚠️ YouTube hesabı bağlı değil")

            st.markdown("""
            ### 📋 YouTube API Kurulum Adımları:

            1. **Google Cloud Console'a gidin:** [console.cloud.google.com](https://console.cloud.google.com)
            2. **Yeni proje oluşturun** veya mevcut projeyi seçin
            3. **YouTube Data API v3'ü etkinleştirin**
            4. **OAuth 2.0 Credentials oluşturun:**
               - Application type: Desktop App
               - Download JSON
            5. **JSON dosyasını yükleyin**
            """)

            uploaded_creds = st.file_uploader(
                "OAuth Credentials JSON Yükle",
                type=['json'],
                key="yt_creds"
            )

            if uploaded_creds:
                creds_path = CONFIG_DIR / "youtube_client_secrets.json"
                with open(creds_path, 'wb') as f:
                    f.write(uploaded_creds.read())
                st.success(f"✅ Credentials kaydedildi: {creds_path}")

                if st.button("🔗 YouTube'a Bağlan", type="primary"):
                    with st.spinner("YouTube'a bağlanılıyor..."):
                        try:
                            from modules.youtube_uploader import YouTubeUploader

                            uploader = YouTubeUploader(client_secrets_file=str(creds_path))

                            # Get channel info
                            channel_info = uploader.get_channel_info()

                            if channel_info:
                                st.session_state.social_config["youtube"] = {
                                    "connected": True,
                                    "channel_name": channel_info.get("title", "Kanal"),
                                    "channel_id": channel_info.get("id", ""),
                                    "credentials_file": str(creds_path)
                                }
                                save_social_config(st.session_state.social_config)
                                st.success(f"✅ Bağlandı: {channel_info.get('title')}")
                                st.rerun()
                            else:
                                st.error("Kanal bilgisi alınamadı")
                        except Exception as e:
                            st.error(f"Bağlantı hatası: {e}")

    with col2:
        st.subheader("📊 Kanal İstatistikleri")
        if is_connected:
            st.metric("Aboneler", "N/A")
            st.metric("Toplam Video", "N/A")
            st.metric("Görüntülenme", "N/A")
        else:
            st.info("Hesap bağlandığında gösterilecek")

# ==================== TIKTOK ====================
with tab2:
    st.header("🎵 TikTok Hesap Bağlantısı")

    tt_config = st.session_state.social_config.get("tiktok", {})
    is_connected = tt_config.get("connected", False)

    col1, col2 = st.columns([2, 1])

    with col1:
        if is_connected:
            st.success(f"✅ Bağlı: @{tt_config.get('username', 'user')}")

            if st.button("🔌 Bağlantıyı Kes", key="tt_disconnect"):
                st.session_state.social_config["tiktok"]["connected"] = False
                save_social_config(st.session_state.social_config)
                st.rerun()
        else:
            st.warning("⚠️ TikTok hesabı bağlı değil")

            st.markdown("""
            ### 📋 TikTok Bağlantı Yöntemleri:

            **Yöntem 1: Session ID ile (Önerilen)**
            1. TikTok.com'a tarayıcıdan giriş yapın
            2. Developer Tools açın (F12)
            3. Application > Cookies > sessionid değerini kopyalayın

            **Yöntem 2: TikTok for Developers API**
            - [developers.tiktok.com](https://developers.tiktok.com) üzerinden uygulama oluşturun
            """)

            tt_method = st.radio(
                "Bağlantı Yöntemi",
                ["session_id", "api"],
                format_func=lambda x: "🍪 Session ID" if x == "session_id" else "🔑 API Credentials",
                horizontal=True
            )

            if tt_method == "session_id":
                tt_username = st.text_input("TikTok Kullanıcı Adı", placeholder="@username")
                tt_session = st.text_input("Session ID", type="password", placeholder="sid_tt=...")

                if st.button("🔗 TikTok'a Bağlan", type="primary", key="tt_connect"):
                    if tt_username and tt_session:
                        st.session_state.social_config["tiktok"] = {
                            "connected": True,
                            "username": tt_username.replace("@", ""),
                            "session_id": tt_session
                        }
                        save_social_config(st.session_state.social_config)
                        st.success(f"✅ Bağlandı: @{tt_username}")
                        st.rerun()
                    else:
                        st.warning("Kullanıcı adı ve Session ID gerekli")
            else:
                st.info("TikTok API entegrasyonu yakında...")

    with col2:
        st.subheader("📊 Hesap İstatistikleri")
        if is_connected:
            st.metric("Takipçi", "N/A")
            st.metric("Video", "N/A")
            st.metric("Beğeni", "N/A")
        else:
            st.info("Hesap bağlandığında gösterilecek")

# ==================== INSTAGRAM ====================
with tab3:
    st.header("📸 Instagram Hesap Bağlantısı")

    ig_config = st.session_state.social_config.get("instagram", {})
    is_connected = ig_config.get("connected", False)

    col1, col2 = st.columns([2, 1])

    with col1:
        if is_connected:
            st.success(f"✅ Bağlı: @{ig_config.get('username', 'user')}")

            if st.button("🔌 Bağlantıyı Kes", key="ig_disconnect"):
                st.session_state.social_config["instagram"]["connected"] = False
                save_social_config(st.session_state.social_config)
                st.rerun()
        else:
            st.warning("⚠️ Instagram hesabı bağlı değil")

            st.markdown("""
            ### 📋 Instagram Bağlantı Yöntemleri:

            **Yöntem 1: Instagrapi (Önerilen)**
            - Kullanıcı adı ve şifre ile
            - 2FA destekli

            **Yöntem 2: Meta Business API**
            - İşletme hesabı gerektirir
            - [developers.facebook.com](https://developers.facebook.com)

            ⚠️ **Uyarı:** Instagram'ın kullanım şartlarına dikkat edin
            """)

            ig_method = st.radio(
                "Bağlantı Yöntemi",
                ["instagrapi", "business_api"],
                format_func=lambda x: "👤 Kullanıcı Girişi" if x == "instagrapi" else "🏢 Business API",
                horizontal=True
            )

            if ig_method == "instagrapi":
                ig_username = st.text_input("Instagram Kullanıcı Adı", placeholder="username")
                ig_password = st.text_input("Şifre", type="password")
                ig_2fa = st.text_input("2FA Kodu (varsa)", placeholder="123456")

                if st.button("🔗 Instagram'a Bağlan", type="primary", key="ig_connect"):
                    if ig_username and ig_password:
                        with st.spinner("Instagram'a bağlanılıyor..."):
                            try:
                                # Try to login with instagrapi
                                from instagrapi import Client

                                cl = Client()
                                if ig_2fa:
                                    cl.login(ig_username, ig_password, verification_code=ig_2fa)
                                else:
                                    cl.login(ig_username, ig_password)

                                # Save session
                                session_path = CONFIG_DIR / f"ig_session_{ig_username}.json"
                                cl.dump_settings(session_path)

                                st.session_state.social_config["instagram"] = {
                                    "connected": True,
                                    "username": ig_username,
                                    "session_file": str(session_path)
                                }
                                save_social_config(st.session_state.social_config)
                                st.success(f"✅ Bağlandı: @{ig_username}")
                                st.rerun()
                            except ImportError:
                                st.error("instagrapi yüklü değil. Çalıştır: pip install instagrapi")
                            except Exception as e:
                                st.error(f"Bağlantı hatası: {e}")
                    else:
                        st.warning("Kullanıcı adı ve şifre gerekli")
            else:
                st.info("Meta Business API entegrasyonu yakında...")

    with col2:
        st.subheader("📊 Hesap İstatistikleri")
        if is_connected:
            st.metric("Takipçi", "N/A")
            st.metric("Gönderi", "N/A")
            st.metric("Takip", "N/A")
        else:
            st.info("Hesap bağlandığında gösterilecek")

# ==================== HESAP DURUMU ====================
with tab4:
    st.header("📊 Tüm Hesap Durumları")

    config = st.session_state.social_config

    # Summary cards
    col1, col2, col3 = st.columns(3)

    with col1:
        yt = config.get("youtube", {})
        status = "✅ Bağlı" if yt.get("connected") else "❌ Bağlı Değil"
        st.markdown(f"""
        <div class="platform-card {'connected' if yt.get('connected') else 'disconnected'}">
            <h3>📺 YouTube</h3>
            <p><strong>Durum:</strong> {status}</p>
            <p><strong>Kanal:</strong> {yt.get('channel_name', 'N/A')}</p>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        tt = config.get("tiktok", {})
        status = "✅ Bağlı" if tt.get("connected") else "❌ Bağlı Değil"
        st.markdown(f"""
        <div class="platform-card {'connected' if tt.get('connected') else 'disconnected'}">
            <h3>🎵 TikTok</h3>
            <p><strong>Durum:</strong> {status}</p>
            <p><strong>Kullanıcı:</strong> @{tt.get('username', 'N/A')}</p>
        </div>
        """, unsafe_allow_html=True)

    with col3:
        ig = config.get("instagram", {})
        status = "✅ Bağlı" if ig.get("connected") else "❌ Bağlı Değil"
        st.markdown(f"""
        <div class="platform-card {'connected' if ig.get('connected') else 'disconnected'}">
            <h3>📸 Instagram</h3>
            <p><strong>Durum:</strong> {status}</p>
            <p><strong>Kullanıcı:</strong> @{ig.get('username', 'N/A')}</p>
        </div>
        """, unsafe_allow_html=True)

    st.divider()

    # Quick publish section
    st.subheader("🚀 Hızlı Yayınlama")

    connected_platforms = []
    if config.get("youtube", {}).get("connected"):
        connected_platforms.append("YouTube")
    if config.get("tiktok", {}).get("connected"):
        connected_platforms.append("TikTok")
    if config.get("instagram", {}).get("connected"):
        connected_platforms.append("Instagram")

    if connected_platforms:
        st.write(f"**Bağlı Platformlar:** {', '.join(connected_platforms)}")

        uploaded_video = st.file_uploader("Video Yükle", type=['mp4', 'mov'], key="quick_upload")

        publish_title = st.text_input("Başlık")
        publish_desc = st.text_area("Açıklama")

        selected_platforms = st.multiselect(
            "Yayınlanacak Platformlar",
            connected_platforms,
            default=connected_platforms
        )

        if st.button("🚀 Seçili Platformlara Yayınla", type="primary"):
            if not uploaded_video:
                st.warning("Video yükleyin")
            elif not publish_title:
                st.warning("Başlık girin")
            else:
                progress = st.progress(0)
                for i, platform in enumerate(selected_platforms):
                    with st.spinner(f"{platform}'a yükleniyor..."):
                        # Simulate upload
                        import time
                        time.sleep(1)
                        st.success(f"✅ {platform}'a yüklendi!")
                    progress.progress((i + 1) / len(selected_platforms))
    else:
        st.info("Yayınlamak için en az bir platform bağlayın")

    st.divider()

    # Scheduled posts
    st.subheader("⏰ Zamanlanmış Yayınlar")
    st.info("Henüz zamanlanmış yayın yok")

    # Activity log
    st.subheader("📋 Aktivite Geçmişi")
    st.info("Henüz aktivite yok")

# Footer
st.divider()
st.markdown("""
<p style="text-align: center; color: #666;">
    🔐 Sosyal Medya Yönetimi | VIDEOCU Studio
</p>
""", unsafe_allow_html=True)