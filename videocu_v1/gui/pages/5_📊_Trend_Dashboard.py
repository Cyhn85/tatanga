"""
VIDEOCU v1 - Trend Dashboard
Trendyol tarzı trend kartları ile çoklu platform görünümü
"""

import streamlit as st
import sys
import os
import sqlite3
import json
from datetime import datetime
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

st.set_page_config(
    page_title="Trend Dashboard - VIDEOCU",
    page_icon="📊",
    layout="wide"
)

# Database setup
DB_PATH = Path(__file__).parent.parent.parent / "database" / "favorites.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

def init_db():
    """Initialize SQLite database"""
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS favorites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trend_id TEXT UNIQUE,
            platform TEXT,
            country TEXT,
            title TEXT,
            url TEXT,
            thumbnail TEXT,
            views INTEGER,
            likes INTEGER,
            score INTEGER,
            channel TEXT,
            transcript TEXT,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'pending'
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS productions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            favorite_id INTEGER,
            video_path TEXT,
            youtube_url TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (favorite_id) REFERENCES favorites(id)
        )
    ''')
    conn.commit()
    conn.close()

def add_to_favorites(trend: dict) -> bool:
    """Add trend to favorites"""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        c = conn.cursor()
        c.execute('''
            INSERT OR REPLACE INTO favorites
            (trend_id, platform, country, title, url, thumbnail, views, likes, score, channel)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            trend.get('video_id', trend.get('keyword', '')),
            trend.get('platform', 'unknown'),
            trend.get('country', 'DE'),
            trend.get('title', trend.get('keyword', '')),
            trend.get('url', ''),
            trend.get('thumbnail', ''),
            trend.get('views', 0),
            trend.get('likes', 0),
            trend.get('score', 0),
            trend.get('channel', '')
        ))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"Favorite error: {e}")
        return False

def get_favorites() -> list:
    """Get all favorites"""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        c = conn.cursor()
        c.execute('SELECT * FROM favorites ORDER BY added_at DESC')
        rows = c.fetchall()
        conn.close()

        favorites = []
        for row in rows:
            favorites.append({
                'id': row[0],
                'trend_id': row[1],
                'platform': row[2],
                'country': row[3],
                'title': row[4],
                'url': row[5],
                'thumbnail': row[6],
                'views': row[7],
                'likes': row[8],
                'score': row[9],
                'channel': row[10],
                'transcript': row[11],
                'added_at': row[12],
                'status': row[13]
            })
        return favorites
    except:
        return []

def remove_favorite(trend_id: str):
    """Remove from favorites"""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        c = conn.cursor()
        c.execute('DELETE FROM favorites WHERE trend_id = ?', (trend_id,))
        conn.commit()
        conn.close()
    except:
        pass

def is_favorite(trend_id: str) -> bool:
    """Check if trend is in favorites"""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        c = conn.cursor()
        c.execute('SELECT 1 FROM favorites WHERE trend_id = ?', (trend_id,))
        result = c.fetchone()
        conn.close()
        return result is not None
    except:
        return False

# Initialize database
init_db()

# Custom CSS for Trendyol-style cards
st.markdown("""
<style>
    .trend-card {
        background: linear-gradient(135deg, #1e1e2e 0%, #2d2d44 100%);
        border-radius: 12px;
        padding: 12px;
        margin: 8px 0;
        border: 1px solid #3d3d5c;
        transition: all 0.3s ease;
    }
    .trend-card:hover {
        border-color: #667eea;
        transform: translateY(-2px);
        box-shadow: 0 8px 25px rgba(102,126,234,0.3);
    }
    .platform-badge {
        display: inline-block;
        padding: 4px 10px;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: bold;
        margin-right: 8px;
    }
    .badge-youtube { background: #ff0000; color: white; }
    .badge-google { background: #4285f4; color: white; }
    .badge-tiktok { background: #00f2ea; color: black; }
    .badge-instagram { background: linear-gradient(45deg, #f09433, #e6683c, #dc2743, #cc2366, #bc1888); color: white; }
    .metric-box {
        background: rgba(255,255,255,0.05);
        padding: 8px 12px;
        border-radius: 8px;
        text-align: center;
    }
    .country-flag {
        font-size: 1.2rem;
        margin-right: 4px;
    }
    .favorite-btn {
        cursor: pointer;
        font-size: 1.5rem;
    }
    .section-header {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        padding: 1rem 1.5rem;
        border-radius: 10px;
        margin-bottom: 1.5rem;
    }
</style>
""", unsafe_allow_html=True)

# Header
st.markdown('<div class="section-header"><h1 style="margin:0;color:white;">📊 Trend Dashboard</h1><p style="margin:0;color:rgba(255,255,255,0.8);">Tüm platformlardan gerçek zamanlı trendler</p></div>', unsafe_allow_html=True)

# Filters
col1, col2, col3, col4 = st.columns([2, 2, 2, 1])

with col1:
    selected_platforms = st.multiselect(
        "Platform",
        ["youtube", "google", "tiktok", "instagram"],
        default=["youtube", "google"],
        format_func=lambda x: {"youtube": "📺 YouTube", "google": "🔍 Google", "tiktok": "🎵 TikTok", "instagram": "📸 Instagram"}.get(x, x)
    )

with col2:
    selected_countries = st.multiselect(
        "Ülke",
        ["DE", "GB", "US", "TR", "FR"],
        default=["DE", "GB", "US"],
        format_func=lambda x: {"DE": "🇩🇪 Almanya", "GB": "🇬🇧 İngiltere", "US": "🇺🇸 ABD", "TR": "🇹🇷 Türkiye", "FR": "🇫🇷 Fransa"}.get(x, x)
    )

with col3:
    time_range = st.selectbox(
        "Tarih Aralığı",
        ["now", "24h", "7d", "30d"],
        index=2,
        format_func=lambda x: {"now": "⚡ Anlık", "24h": "📅 Son 24 Saat", "7d": "📅 Son 7 Gün", "30d": "📅 Son 1 Ay"}.get(x, x)
    )

with col4:
    trend_limit = st.number_input("Limit", 5, 50, 10)

# Fetch trends button
if st.button("🔄 Trendleri Getir", type="primary", use_container_width=True):
    with st.spinner("Trendler yükleniyor..."):
        all_trends = []

        try:
            from dotenv import load_dotenv
            load_dotenv()

            # YouTube & Google Trends
            if "youtube" in selected_platforms or "google" in selected_platforms:
                from modules.trend_analyzer import TrendAnalyzer

                yt_key = os.getenv("YOUTUBE_API_KEY")
                analyzer = TrendAnalyzer(youtube_api_key=yt_key)

                for country in selected_countries:
                    # YouTube
                    if "youtube" in selected_platforms and yt_key:
                        try:
                            yt_trends = analyzer.get_youtube_trending_videos(
                                region_code=country,
                                max_results=trend_limit // len(selected_countries)
                            )
                            for t in yt_trends:
                                t['platform'] = 'youtube'
                                t['country'] = country
                            all_trends.extend(yt_trends)
                        except Exception as e:
                            st.warning(f"YouTube {country}: {e}")

                    # Google Trends
                    if "google" in selected_platforms:
                        try:
                            if country == "DE":
                                g_trends = analyzer.get_trending_searches_germany(limit=5)
                            else:
                                g_trends = []

                            for t in g_trends:
                                t['platform'] = 'google'
                                t['country'] = country
                                t['title'] = t.get('keyword', '')
                            all_trends.extend(g_trends)
                        except Exception as e:
                            st.warning(f"Google {country}: {e}")

            # TikTok Trends
            if "tiktok" in selected_platforms:
                try:
                    from modules.social_trend_analyzer import SocialTrendAnalyzer
                    import asyncio

                    social = SocialTrendAnalyzer()
                    tt_trends = asyncio.run(social.get_tiktok_trending(count=5))

                    for t in tt_trends:
                        t['platform'] = 'tiktok'
                        t['country'] = 'GLOBAL'
                        t['title'] = t.get('desc', t.get('title', ''))[:60]
                    all_trends.extend(tt_trends)
                except Exception as e:
                    st.warning(f"TikTok: {e}")

            # Store in session
            st.session_state['dashboard_trends'] = all_trends
            st.success(f"✅ {len(all_trends)} trend bulundu!")

        except Exception as e:
            st.error(f"Hata: {e}")
            import traceback
            st.code(traceback.format_exc())

st.divider()

# Display trends in grid
if 'dashboard_trends' in st.session_state and st.session_state['dashboard_trends']:
    trends = st.session_state['dashboard_trends']

    # Country flags
    flags = {"DE": "🇩🇪", "GB": "🇬🇧", "US": "🇺🇸", "TR": "🇹🇷", "FR": "🇫🇷", "GLOBAL": "🌍"}
    platform_colors = {"youtube": "#ff0000", "google": "#4285f4", "tiktok": "#00f2ea", "instagram": "#e1306c"}
    platform_icons = {"youtube": "📺", "google": "🔍", "tiktok": "🎵", "instagram": "📸"}

    # Grid layout - 4 columns
    cols = st.columns(4)

    for i, trend in enumerate(trends):
        with cols[i % 4]:
            trend_id = trend.get('video_id', trend.get('keyword', f'trend_{i}'))
            platform = trend.get('platform', 'unknown')
            country = trend.get('country', 'DE')
            title = trend.get('title', trend.get('keyword', 'N/A'))[:50]
            views = trend.get('views', trend.get('score', 0))
            thumbnail = trend.get('thumbnail', '')
            url = trend.get('url', '')
            channel = trend.get('channel', '')

            # Format views
            if views >= 1000000:
                views_str = f"{views/1000000:.1f}M"
            elif views >= 1000:
                views_str = f"{views/1000:.0f}K"
            else:
                views_str = str(views)

            # Card container
            with st.container():
                # Thumbnail
                if thumbnail:
                    st.image(thumbnail, use_container_width=True)

                # Platform & Country badges
                flag = flags.get(country, "🌍")
                icon = platform_icons.get(platform, "📊")
                st.markdown(f"**{icon} {platform.upper()}** {flag}")

                # Title
                st.markdown(f"**{title}**")

                # Metrics
                col_m1, col_m2 = st.columns(2)
                with col_m1:
                    st.metric("👁️ Views", views_str)
                with col_m2:
                    if trend.get('likes'):
                        likes = trend.get('likes', 0)
                        likes_str = f"{likes/1000:.0f}K" if likes >= 1000 else str(likes)
                        st.metric("❤️ Likes", likes_str)

                # Channel
                if channel:
                    st.caption(f"📺 {channel[:25]}")

                # Action buttons
                col_a1, col_a2, col_a3 = st.columns(3)

                with col_a1:
                    is_fav = is_favorite(trend_id)
                    if st.button("⭐" if is_fav else "☆", key=f"fav_{i}", help="Favorilere ekle/çıkar"):
                        if is_fav:
                            remove_favorite(trend_id)
                            st.toast("Favorilerden çıkarıldı")
                        else:
                            add_to_favorites(trend)
                            st.toast("Favorilere eklendi!")
                        st.rerun()

                with col_a2:
                    if url:
                        st.link_button("🔗", url, help="Videoya git")

                with col_a3:
                    if st.button("▶️", key=f"prod_{i}", help="Video üret"):
                        st.session_state['selected_trend'] = trend
                        st.success(f"'{title[:30]}' seçildi! Video Studio'ya gidin.")

                st.divider()

else:
    st.info("👆 'Trendleri Getir' butonuna tıklayarak başlayın")

# Favorites Section
st.markdown("---")
st.subheader("⭐ Favorilerim")

favorites = get_favorites()

if favorites:
    fav_cols = st.columns(4)

    for i, fav in enumerate(favorites):
        with fav_cols[i % 4]:
            st.markdown(f"**{fav['title'][:40]}**")
            st.caption(f"{fav['platform'].upper()} | {fav['country']} | {fav['status']}")

            col1, col2, col3 = st.columns(3)
            with col1:
                if st.button("🗑️", key=f"del_fav_{fav['id']}", help="Sil"):
                    remove_favorite(fav['trend_id'])
                    st.rerun()
            with col2:
                if st.button("📋", key=f"trans_fav_{fav['id']}", help="Transkript al"):
                    try:
                        from modules.transcript_extractor import TranscriptExtractor
                        extractor = TranscriptExtractor()
                        result = extractor.get_transcript(fav['trend_id'])
                        if result['success']:
                            st.success(f"Transkript alındı: {result['word_count']} kelime")
                            st.text_area("Transkript", result['transcript_text'][:500], height=150)
                        else:
                            st.warning(f"Transkript yok: {result['error']}")
                    except Exception as e:
                        st.error(f"Hata: {e}")
            with col3:
                if st.button("🎬", key=f"make_fav_{fav['id']}", help="Video üret"):
                    st.session_state['selected_trend'] = fav
                    st.success("Video Studio'ya gidin!")
else:
    st.info("Henüz favori eklenmedi. Yukarıdan trend seçip ⭐ butonuna tıklayın.")

# Footer
st.markdown("---")
st.caption("VIDEOCU v1 - Trend Dashboard | Powered by Claude Code")
