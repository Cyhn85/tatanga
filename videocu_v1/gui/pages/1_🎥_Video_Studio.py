"""
VIDEOCU Studio - Video Production Page
"""

import streamlit as st
import sys
import os
import tempfile
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

st.set_page_config(
    page_title="Video Studio - VIDEOCU",
    page_icon="🎥",
    layout="wide"
)

# Custom CSS
st.markdown("""
<style>
    .section-header {
        background: linear-gradient(90deg, #FF6B6B, #FF8E53);
        padding: 1rem;
        border-radius: 10px;
        margin-bottom: 1rem;
    }
    .info-box {
        background: #1a1a2e;
        padding: 1rem;
        border-radius: 10px;
        border-left: 4px solid #4ECDC4;
    }
</style>
""", unsafe_allow_html=True)

st.title("🎥 Video Studio")
st.markdown("*AI destekli otomatik video üretim sistemi*")

# Initialize session state
if 'video_script' not in st.session_state:
    st.session_state.video_script = None
if 'video_images' not in st.session_state:
    st.session_state.video_images = []
if 'video_audio' not in st.session_state:
    st.session_state.video_audio = None

st.divider()

# Tabs for different features
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📊 Trend Analizi",
    "📝 Senaryo Yazımı",
    "🖼️ Görsel Üretimi",
    "🎤 Seslendirme",
    "🎬 Video Montaj",
    "📱 Yayınlama"
])

# ==================== TAB 1: TREND ANALİZİ ====================
with tab1:
    st.header("📊 Trend Analizi")

    # Platform seçimi
    platform = st.radio(
        "Platform Seçin",
        ["google", "youtube", "tiktok", "instagram", "all"],
        format_func=lambda x: {
            "google": "🔍 Google Trends",
            "youtube": "📺 YouTube",
            "tiktok": "🎵 TikTok Trending",
            "instagram": "📸 Instagram Reels",
            "all": "🌐 Tüm Platformlar"
        }.get(x, x),
        horizontal=True
    )

    col1, col2, col3 = st.columns([2, 1, 1])

    with col1:
        if platform in ["google", "youtube", "all"]:
            country = st.selectbox(
                "Ülke Seçin",
                ["germany", "turkey", "united_states", "united_kingdom", "france"],
                format_func=lambda x: {
                    "germany": "🇩🇪 Almanya",
                    "turkey": "🇹🇷 Türkiye",
                    "united_states": "🇺🇸 ABD",
                    "united_kingdom": "🇬🇧 İngiltere",
                    "france": "🇫🇷 Fransa"
                }.get(x, x)
            )
        else:
            country = "germany"

        if platform == "instagram":
            ig_hashtags = st.text_input(
                "Instagram Hashtag'leri (virgülle ayır)",
                value="reelsdeutschland, deutschland, viral, trending",
                help="Aranacak hashtag'leri girin"
            )

    with col2:
        trend_count = st.slider("Trend Sayısı", 5, 30, 10)

    with col3:
        # Tarih aralığı seçici
        time_range = st.selectbox(
            "📅 Tarih Aralığı",
            ["now", "24h", "7d", "30d", "90d"],
            index=2,  # Default: 7 gün
            format_func=lambda x: {
                "now": "⚡ Anlık",
                "24h": "📅 Son 24 Saat",
                "7d": "📅 Son 7 Gün",
                "30d": "📅 Son 1 Ay",
                "90d": "📅 Son 3 Ay"
            }.get(x, x),
            help="Google ve YouTube için 3 aya kadar, TikTok/Instagram sadece anlık"
        )

        # Platform bazlı uyarı
        if time_range in ["30d", "90d"] and platform in ["tiktok", "instagram"]:
            st.warning("⚠️ TikTok/Instagram sadece anlık trending destekler")

    if st.button("🔍 Trendleri Getir", type="primary", use_container_width=True):
        with st.spinner("Trendler analiz ediliyor..."):
            trends = []

            # Ülke kodu mapping
            country_codes = {
                "germany": "DE",
                "turkey": "TR",
                "united_states": "US",
                "united_kingdom": "GB",
                "france": "FR"
            }
            region_code = country_codes.get(country, "DE")

            try:
                # Google Trends
                if platform in ["google", "all"]:
                    from modules.trend_analyzer import TrendAnalyzer
                    import os
                    from dotenv import load_dotenv
                    load_dotenv()

                    youtube_api_key = os.getenv("YOUTUBE_API_KEY")
                    analyzer = TrendAnalyzer(youtube_api_key=youtube_api_key)

                    # Tarih filtreli trend analizi
                    if time_range in ["30d", "90d"]:
                        # Uzun dönem için pytrends kullan
                        google_trends = analyzer.get_trends_by_timerange(
                            keywords=[],  # Boş = trending topics al
                            time_range=time_range,
                            region=region_code
                        )
                    else:
                        # Kısa dönem için RSS
                        if country == "germany":
                            google_trends = analyzer.get_trending_searches_germany(limit=trend_count)
                        else:
                            google_trends = analyzer._get_trends_via_rss(limit=trend_count)

                    for t in google_trends:
                        t['platform'] = 'google'
                        t['platform_icon'] = '🔍'
                        t['title'] = t.get('keyword', t.get('title', 'N/A'))
                    trends.extend(google_trends[:trend_count])

                # YouTube Trends (YENİ - tarih filtreli)
                if platform in ["youtube", "all"]:
                    try:
                        from modules.trend_analyzer import TrendAnalyzer
                        import os
                        from dotenv import load_dotenv
                        load_dotenv()

                        youtube_api_key = os.getenv("YOUTUBE_API_KEY")
                        if youtube_api_key:
                            analyzer = TrendAnalyzer(youtube_api_key=youtube_api_key)

                            # Tarih filtreli YouTube arama
                            yt_trends = analyzer.search_youtube_by_timerange(
                                query=None,  # Genel trending
                                time_range=time_range,
                                region_code=region_code,
                                max_results=trend_count
                            )

                            for t in yt_trends:
                                t['platform'] = 'youtube'
                                t['platform_icon'] = '📺'
                            trends.extend(yt_trends)
                        else:
                            st.warning("⚠️ YOUTUBE_API_KEY tanımlı değil")
                    except Exception as e:
                        st.warning(f"YouTube trend hatası: {e}")

                # TikTok Trends
                if platform in ["tiktok", "all"]:
                    try:
                        from modules.social_trend_analyzer import SocialTrendAnalyzer
                        import asyncio

                        social_analyzer = SocialTrendAnalyzer()
                        tiktok_trends = asyncio.run(social_analyzer.get_tiktok_trending(count=trend_count))

                        for t in tiktok_trends:
                            t['platform'] = 'tiktok'
                            t['platform_icon'] = '🎵'
                            t['title'] = t.get('desc', t.get('title', 'N/A'))[:100]
                        trends.extend(tiktok_trends)
                    except Exception as e:
                        st.warning(f"TikTok trend hatası: {e}")

                # Instagram Trends
                if platform in ["instagram", "all"]:
                    try:
                        from modules.social_trend_analyzer import SocialTrendAnalyzer

                        social_analyzer = SocialTrendAnalyzer()
                        hashtags = [h.strip() for h in ig_hashtags.split(",")] if platform == "instagram" else ["reelsdeutschland", "viral"]
                        ig_trends = social_analyzer.get_instagram_trending_by_hashtags(hashtags=hashtags, amount_per_tag=5)

                        for t in ig_trends:
                            t['platform'] = 'instagram'
                            t['platform_icon'] = '📸'
                            t['title'] = t.get('caption_text', t.get('title', 'N/A'))[:100]
                        trends.extend(ig_trends)
                    except Exception as e:
                        st.warning(f"Instagram trend hatası: {e}")

                if trends:
                    st.success(f"✅ {len(trends)} trend bulundu!")

                    # Platform bazlı gruplama
                    for i, trend in enumerate(trends, 1):
                        title = trend.get('title', trend.get('keyword', trend.get('desc', 'N/A')))
                        platform_icon = trend.get('platform_icon', '📊')
                        platform_name = trend.get('platform', 'unknown').upper()

                        with st.expander(f"{platform_icon} {i}. {title[:80]}..."):
                            col_a, col_b = st.columns(2)

                            with col_a:
                                st.write(f"**Platform:** {platform_name}")
                                if trend.get('traffic') or trend.get('approximate_traffic'):
                                    st.write(f"**Arama Hacmi:** {trend.get('traffic', trend.get('approximate_traffic', 'N/A'))}")
                                if trend.get('views') or trend.get('view_count'):
                                    st.write(f"**Görüntülenme:** {trend.get('views', trend.get('view_count', 'N/A')):,}")
                                if trend.get('likes') or trend.get('like_count'):
                                    st.write(f"**Beğeni:** {trend.get('likes', trend.get('like_count', 'N/A')):,}")

                            with col_b:
                                if trend.get('engagement_score'):
                                    st.metric("Engagement Score", f"{trend.get('engagement_score', 0):,.0f}")
                                if trend.get('author'):
                                    st.write(f"**Yazar:** @{trend.get('author')}")
                                if trend.get('url'):
                                    st.write(f"[🔗 Linke Git]({trend.get('url')})")

                            if trend.get('summary'):
                                st.write(f"**Özet:** {trend.get('summary')}")

                            if trend.get('news_items'):
                                st.write("**İlgili Haberler:**")
                                for news in trend.get('news_items', [])[:3]:
                                    st.write(f"- {news.get('title', '')}")

                            if st.button(f"Bu konuda video yap", key=f"trend_{i}"):
                                st.session_state.selected_topic = title
                                st.success(f"✅ Seçilen konu: {title}")
                                st.info("👉 Senaryo Yazımı sekmesine gidin")
                else:
                    st.warning("Trend bulunamadı")

            except Exception as e:
                st.error(f"Hata: {e}")
                import traceback
                st.code(traceback.format_exc())

# ==================== TAB 2: SENARYO YAZIMI ====================
with tab2:
    st.header("📝 AI Senaryo Yazımı")

    col1, col2 = st.columns([2, 1])

    with col1:
        topic = st.text_input(
            "Video Konusu",
            value=st.session_state.get('selected_topic', ''),
            placeholder="Örn: Yapay Zeka ile Geleceğin Teknolojileri"
        )

        script_style = st.selectbox(
            "Senaryo Stili",
            ["informativ", "unterhaltsam", "emotional", "educational", "news"],
            format_func=lambda x: {
                "informativ": "📚 Bilgilendirici",
                "unterhaltsam": "🎉 Eğlenceli",
                "emotional": "❤️ Duygusal",
                "educational": "🎓 Eğitici",
                "news": "📰 Haber"
            }.get(x, x)
        )

    with col2:
        duration = st.slider("Video Süresi (saniye)", 30, 300, 60)
        language = st.selectbox("Dil", ["de", "tr", "en"], format_func=lambda x: {
            "de": "🇩🇪 Almanca",
            "tr": "🇹🇷 Türkçe",
            "en": "🇬🇧 İngilizce"
        }.get(x, x))

    if st.button("✍️ Senaryo Oluştur", type="primary", use_container_width=True):
        if not topic:
            st.warning("Lütfen bir konu girin")
        else:
            with st.spinner("AI senaryo yazıyor..."):
                try:
                    from dotenv import load_dotenv
                    load_dotenv()
                    from modules.content_generator import ContentGenerator

                    api_key = os.getenv("GEMINI_API_KEY")
                    if not api_key:
                        st.error("GEMINI_API_KEY bulunamadı!")
                    else:
                        generator = ContentGenerator(api_key=api_key)
                        script = generator.generate_script(
                            topic=topic,
                            duration=duration,
                            style=script_style,
                            language=language
                        )

                        if script:
                            st.session_state.video_script = script
                            st.success("✅ Senaryo oluşturuldu!")
                        else:
                            st.error("Senaryo oluşturulamadı")
                except Exception as e:
                    st.error(f"Hata: {e}")

    # Display script
    if st.session_state.video_script:
        st.subheader("📄 Oluşturulan Senaryo")
        script = st.session_state.video_script

        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"**Başlık:** {script.get('title', 'N/A')}")
            st.markdown(f"**Açıklama:** {script.get('description', 'N/A')}")
        with col2:
            st.markdown(f"**Etiketler:** {', '.join(script.get('tags', []))}")

        st.markdown("**Sahneler:**")
        for i, scene in enumerate(script.get('scenes', []), 1):
            with st.expander(f"Sahne {i}"):
                st.write(f"**Metin:** {scene.get('text', 'N/A')}")
                st.write(f"**Görsel:** {scene.get('image_prompt', 'N/A')}")

# ==================== TAB 3: GÖRSEL ÜRETİMİ ====================
with tab3:
    st.header("🖼️ Görsel Bulma & Üretme")

    # 4-Layer Fallback Sistemi göster
    st.info("🔄 **4 Katmanlı Fallback:** Pexels → Unsplash → Pollinations.ai → Placeholder")

    source = st.radio(
        "Görsel Kaynağı",
        ["pexels", "unsplash", "ai_generate", "auto_fallback", "upload"],
        format_func=lambda x: {
            "pexels": "📷 Pexels (HD Stok)",
            "unsplash": "🖼️ Unsplash (Ücretsiz)",
            "ai_generate": "🎨 AI Üretimi (Pollinations)",
            "auto_fallback": "🔄 Otomatik (Fallback Chain)",
            "upload": "📁 Dosya Yükle"
        }.get(x, x),
        horizontal=True
    )

    if source in ["pexels", "unsplash", "auto_fallback"]:
        search_query = st.text_input("Arama Terimi", placeholder="Örn: technology, nature, city")
        col1, col2, col3 = st.columns(3)
        with col1:
            image_count = st.slider("Görsel Sayısı", 1, 10, 5)
        with col2:
            orientation = st.selectbox("Yön", ["landscape", "portrait", "square"])
        with col3:
            resolution = st.selectbox("Çözünürlük", ["1920x1080", "1280x720", "1080x1920"])

        if st.button("🔍 Görselleri Getir", type="primary", key="fetch_images"):
            with st.spinner("Görseller aranıyor..."):
                images = []
                used_provider = None

                try:
                    # Pexels
                    if source in ["pexels", "auto_fallback"]:
                        try:
                            from modules.pexels_provider import PexelsProvider
                            provider = PexelsProvider()
                            pexels_images = provider.search_photos(search_query, per_page=image_count, orientation=orientation)
                            if pexels_images:
                                images = pexels_images
                                used_provider = "Pexels"
                        except Exception as e:
                            if source == "pexels":
                                st.error(f"Pexels hatası: {e}")

                    # Unsplash (fallback veya direkt)
                    if (source == "unsplash" or (source == "auto_fallback" and not images)):
                        try:
                            from modules.unsplash_provider import UnsplashProvider
                            provider = UnsplashProvider()
                            unsplash_images = provider.search_photos(search_query, per_page=image_count, orientation=orientation)
                            if unsplash_images:
                                images = unsplash_images
                                used_provider = "Unsplash"
                        except Exception as e:
                            if source == "unsplash":
                                st.error(f"Unsplash hatası: {e}")

                    # AI Generation (son fallback)
                    if source == "auto_fallback" and not images:
                        try:
                            from modules.image_generator import ImageGenerator
                            generator = ImageGenerator()
                            st.info("📷 Stok görseller bulunamadı, AI üretiyor...")

                            ai_images = []
                            w, h = map(int, resolution.split('x'))
                            for i in range(min(image_count, 3)):  # AI için max 3
                                img_path = generator._generate_with_pollinations(
                                    f"{search_query}, professional photo, high quality",
                                    os.path.join(tempfile.gettempdir(), f"ai_img_{i}.png"),
                                    width=w, height=h
                                )
                                if img_path:
                                    ai_images.append({"url": img_path, "source": "AI"})
                            if ai_images:
                                images = ai_images
                                used_provider = "Pollinations.ai"
                        except Exception as e:
                            st.warning(f"AI üretimi başarısız: {e}")

                    if images:
                        st.success(f"✅ {len(images)} görsel bulundu! (Kaynak: {used_provider})")

                        # Görselleri kaydet
                        st.session_state.video_images = images

                        cols = st.columns(3)
                        for i, img in enumerate(images):
                            with cols[i % 3]:
                                img_url = img.get('url') or img.get('src', {}).get('large') or img.get('urls', {}).get('regular', '')
                                if img_url:
                                    st.image(img_url, caption=f"{i+1}. {img.get('photographer', img.get('user', {}).get('name', 'Unknown'))}")

                                    # İndirme butonu
                                    if st.button(f"💾 Kaydet", key=f"save_img_{i}"):
                                        st.session_state.setdefault('saved_images', []).append(img_url)
                                        st.success("Kaydedildi!")
                    else:
                        st.warning("Görsel bulunamadı. Farklı arama terimi deneyin.")

                except Exception as e:
                    st.error(f"Hata: {e}")
                    import traceback
                    st.code(traceback.format_exc())

    elif source == "ai_generate":
        prompt = st.text_area("Görsel Açıklaması",
                             placeholder="Örn: A futuristic city with flying cars, cyberpunk style, 8k, detailed")

        col1, col2, col3 = st.columns(3)
        with col1:
            ai_model = st.selectbox("AI Model", ["flux", "turbo", "flux-realism"],
                                   format_func=lambda x: {"flux": "🎨 Flux (Yüksek Kalite)", "turbo": "⚡ Turbo (Hızlı)", "flux-realism": "📸 Flux Realism"}.get(x, x))
        with col2:
            ai_width = st.number_input("Genişlik", 512, 2048, 1920, step=64)
        with col3:
            ai_height = st.number_input("Yükseklik", 512, 2048, 1080, step=64)

        enhance_prompt = st.checkbox("Prompt'u geliştir (AI optimize)", value=True)

        if st.button("🎨 AI ile Üret", type="primary"):
            if not prompt:
                st.warning("Lütfen açıklama girin")
            else:
                with st.spinner(f"AI görsel üretiyor ({ai_model})..."):
                    try:
                        from modules.image_generator import ImageGenerator
                        generator = ImageGenerator()

                        output_path = os.path.join(tempfile.gettempdir(), f"ai_generated_{hash(prompt) % 10000}.png")
                        image_path = generator._generate_with_pollinations(
                            prompt,
                            output_path,
                            width=ai_width,
                            height=ai_height,
                            model=ai_model,
                            enhance=enhance_prompt
                        )

                        if image_path and os.path.exists(image_path):
                            st.success("✅ Görsel üretildi!")
                            st.image(image_path)

                            # İndirme butonu
                            with open(image_path, 'rb') as f:
                                st.download_button("⬇️ İndir", f.read(), f"ai_image.png", "image/png")

                            st.session_state.setdefault('saved_images', []).append(image_path)
                        else:
                            st.error("Görsel üretilemedi")
                    except Exception as e:
                        st.error(f"Hata: {e}")

    else:  # upload
        uploaded_files = st.file_uploader(
            "Görselleri Yükle",
            type=['png', 'jpg', 'jpeg', 'webp'],
            accept_multiple_files=True
        )

        if uploaded_files:
            cols = st.columns(3)
            for i, file in enumerate(uploaded_files):
                with cols[i % 3]:
                    st.image(file, caption=file.name)

# ==================== TAB 4: SESLENDİRME ====================
with tab4:
    st.header("🎤 TTS Seslendirme")

    col1, col2 = st.columns([2, 1])

    with col1:
        tts_text = st.text_area(
            "Seslendirilecek Metin",
            height=200,
            placeholder="Seslendirilecek metni buraya yazın veya senaryodan alın..."
        )

        if st.session_state.video_script and st.button("📋 Senaryodan Al"):
            full_text = " ".join([
                scene.get('text', '')
                for scene in st.session_state.video_script.get('scenes', [])
            ])
            st.session_state.tts_text = full_text
            st.rerun()

    with col2:
        voice_provider = st.selectbox(
            "Ses Sağlayıcı",
            ["edge-tts", "google-cloud", "elevenlabs"],
            format_func=lambda x: {
                "edge-tts": "🎙️ Edge TTS (Ücretsiz)",
                "google-cloud": "☁️ Google Cloud TTS",
                "elevenlabs": "🎭 ElevenLabs"
            }.get(x, x)
        )

        voice_name = st.selectbox(
            "Ses",
            ["de-DE-KatjaNeural", "de-DE-ConradNeural", "tr-TR-EmelNeural", "en-US-JennyNeural"],
            format_func=lambda x: {
                "de-DE-KatjaNeural": "🇩🇪 Katja (Kadın)",
                "de-DE-ConradNeural": "🇩🇪 Conrad (Erkek)",
                "tr-TR-EmelNeural": "🇹🇷 Emel (Kadın)",
                "en-US-JennyNeural": "🇺🇸 Jenny (Kadın)"
            }.get(x, x)
        )

        speed = st.slider("Hız", 0.5, 2.0, 1.0, 0.1)

    if st.button("🎤 Seslendir", type="primary", use_container_width=True):
        if not tts_text:
            st.warning("Lütfen metin girin")
        else:
            with st.spinner("Seslendiriliyor..."):
                try:
                    from modules.edge_tts_generator import EdgeTTSGenerator

                    tts = EdgeTTSGenerator(voice=voice_name)
                    output_path = os.path.join(tempfile.gettempdir(), "tts_output.mp3")

                    import asyncio
                    result = asyncio.run(tts.generate(tts_text, output_path))

                    if result and os.path.exists(output_path):
                        st.success("✅ Seslendirme tamamlandı!")
                        st.audio(output_path)
                        st.session_state.video_audio = output_path
                    else:
                        st.error("Seslendirme başarısız")
                except Exception as e:
                    st.error(f"Hata: {e}")

# ==================== TAB 5: VIDEO MONTAJ ====================
with tab5:
    st.header("🎬 Video Montaj")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("📁 Girdiler")

        # Images
        uploaded_images = st.file_uploader(
            "Görseller",
            type=['png', 'jpg', 'jpeg'],
            accept_multiple_files=True,
            key="montage_images"
        )

        # Audio
        uploaded_audio = st.file_uploader(
            "Ses Dosyası",
            type=['mp3', 'wav', 'ogg'],
            key="montage_audio"
        )

        # Background music
        uploaded_music = st.file_uploader(
            "Arka Plan Müziği (Opsiyonel)",
            type=['mp3', 'wav'],
            key="montage_music"
        )

    with col2:
        st.subheader("⚙️ Ayarlar")

        resolution = st.selectbox(
            "Çözünürlük",
            ["1920x1080", "1280x720", "1080x1920", "720x1280"],
            format_func=lambda x: {
                "1920x1080": "📺 1080p (Yatay)",
                "1280x720": "📺 720p (Yatay)",
                "1080x1920": "📱 1080p (Dikey/Reels)",
                "720x1280": "📱 720p (Dikey)"
            }.get(x, x)
        )

        transition = st.selectbox(
            "Geçiş Efekti",
            ["crossfade", "fade", "slide", "none"],
            format_func=lambda x: {
                "crossfade": "🔄 Crossfade",
                "fade": "⬛ Fade",
                "slide": "➡️ Slide",
                "none": "❌ Yok"
            }.get(x, x)
        )

        ken_burns = st.checkbox("Ken Burns Efekti", value=True)
        add_subtitles = st.checkbox("Altyazı Ekle", value=False)

    if st.button("🎬 Video Oluştur", type="primary", use_container_width=True):
        if not uploaded_images:
            st.warning("En az bir görsel yükleyin")
        else:
            with st.spinner("Video oluşturuluyor..."):
                st.info("Video montaj işlemi başlatıldı... (Bu özellik tam implementasyon gerektirir)")
                # TODO: Full video montage implementation
                st.success("✅ Video oluşturuldu! (Demo)")

# ==================== TAB 6: YAYINLAMA ====================
with tab6:
    st.header("📱 Video Yayınlama")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("📤 YouTube Yükleme")

        yt_title = st.text_input("Video Başlığı")
        yt_description = st.text_area("Açıklama")
        yt_tags = st.text_input("Etiketler (virgülle ayırın)")
        yt_privacy = st.selectbox("Gizlilik", ["public", "unlisted", "private"])

        video_file = st.file_uploader("Video Dosyası", type=['mp4', 'mov', 'avi'])

        if st.button("📤 YouTube'a Yükle", type="primary"):
            st.info("YouTube API entegrasyonu gerekli")

    with col2:
        st.subheader("📊 Yayın Geçmişi")
        st.info("Henüz yayın yok")

        st.subheader("⏰ Zamanlama")
        schedule_date = st.date_input("Yayın Tarihi")
        schedule_time = st.time_input("Yayın Saati")

        if st.button("⏰ Zamanla"):
            st.success(f"Video {schedule_date} {schedule_time} için zamanlandı")
