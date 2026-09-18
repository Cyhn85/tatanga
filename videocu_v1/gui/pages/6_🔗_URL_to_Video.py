"""
VIDEOCU v1 - URL to Video
Herhangi bir URL'den video üret
"""

import streamlit as st
import sys
import os
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

st.set_page_config(
    page_title="URL to Video - VIDEOCU",
    page_icon="🔗",
    layout="wide"
)

# Custom CSS
st.markdown("""
<style>
    .url-input-box {
        background: linear-gradient(135deg, #1e1e2e 0%, #2d2d44 100%);
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 20px;
    }
    .section-header {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        padding: 1rem 1.5rem;
        border-radius: 10px;
        margin-bottom: 1.5rem;
    }
    .article-preview {
        background: #1e1e2e;
        border-radius: 10px;
        padding: 15px;
        border: 1px solid #3d3d5c;
    }
    .video-script-box {
        background: linear-gradient(135deg, #2d2d44 0%, #1e1e2e 100%);
        border-radius: 10px;
        padding: 15px;
        margin: 10px 0;
        border-left: 4px solid #667eea;
    }
</style>
""", unsafe_allow_html=True)

# Header
st.markdown('<div class="section-header"><h1 style="margin:0;color:white;">🔗 URL / Metin to Video</h1><p style="margin:0;color:rgba(255,255,255,0.8);">URL veya manuel metin girisiyle otomatik video uret</p></div>', unsafe_allow_html=True)

# ============================================================
# ADIM 1: ICERIK GIRISI (TAB YAPISI)
# ============================================================
st.subheader("1️⃣ Icerik Girisi")

tab_url, tab_manual = st.tabs(["🔗 URL'den Cikar", "📝 Manuel Metin Gir"])

# URL degiskeni - her iki tab icin de tanimla
url = ""

with tab_url:
    url = st.text_input(
        "Web Sayfasi URL'si",
        placeholder="https://example.com/article/...",
        help="Haber, blog veya herhangi bir makale URL'si",
        key="url_input"
    )

    if st.button("📥 Makaleyi Cikar", type="primary", use_container_width=True, key="extract_url_btn"):
        if not url:
            st.warning("Lutfen bir URL girin")
        else:
            with st.spinner("Makale cikariliyor..."):
                try:
                    from modules.article_extractor import ArticleExtractor

                    extractor = ArticleExtractor()
                    result = extractor.extract_for_video(url)

                    if result['success']:
                        st.session_state['extracted_article'] = result
                        st.session_state['script_saved'] = False  # Yeni icerik, senaryo kaydedilmedi
                        # Yeni makale cikarildiginda ceviriyi sifirla
                        if 'translated_article' in st.session_state:
                            del st.session_state['translated_article']
                        st.success(f"✅ Makale cikarildi: {result['word_count']} kelime")
                        st.rerun()
                    else:
                        st.error(f"❌ Hata: {result['error']}")

                except Exception as e:
                    st.error(f"Hata: {e}")
                    import traceback
                    st.code(traceback.format_exc())

with tab_manual:
    st.info("💡 Dogrudan metin girerek video olusturabilirsiniz. Gemini otomatik senaryo uretecek.")

    manual_title = st.text_input(
        "Baslik",
        placeholder="Video basligi...",
        help="Video ve senaryo icin baslik",
        key="manual_title"
    )

    manual_text = st.text_area(
        "Metin",
        placeholder="Video icerigi icin metin girin...\n\nBu metin Gemini tarafindan analiz edilecek ve otomatik senaryo olusturulacak.",
        height=200,
        help="En az 50 karakter girin",
        key="manual_text"
    )

    if st.button("📝 Metin Yukle ve Senaryo Olustur", type="primary", use_container_width=True, key="load_manual_btn"):
        if not manual_title or not manual_text:
            st.warning("Lutfen baslik ve metin girin")
        elif len(manual_text) < 50:
            st.warning("Metin en az 50 karakter olmali")
        else:
            with st.spinner("Senaryo olusturuluyor..."):
                try:
                    import google.generativeai as genai
                    from dotenv import load_dotenv
                    load_dotenv()

                    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
                    model = genai.GenerativeModel('gemini-2.0-flash')

                    # Gemini ile senaryo olustur
                    prompt = f"""Asagidaki metin icin video senaryosu olustur.

BASLIK: {manual_title}

METIN:
{manual_text}

JSON formatinda cevap ver:
{{
    "intro": "Giris cumlesi (1-2 cumle, ilgi cekici)",
    "main_points": ["Ana nokta 1", "Ana nokta 2", "Ana nokta 3"],
    "conclusion": "Kapanıs cumlesi"
}}

KURALLAR:
- Her ana nokta 1-2 cumle olsun
- Toplam 3-5 ana nokta olustur
- Dil: Metinle ayni dilde yaz
- Profesyonel haber sunucusu gibi yaz
"""
                    response = model.generate_content(prompt)
                    response_text = response.text

                    # JSON parse
                    import json
                    import re
                    json_match = re.search(r'\{[\s\S]*\}', response_text)
                    if json_match:
                        script_data = json.loads(json_match.group())

                        # Session state'e kaydet
                        st.session_state['extracted_article'] = {
                            'success': True,
                            'title': manual_title,
                            'text': manual_text,
                            'word_count': len(manual_text.split()),
                            'source': 'manuel',
                            'video_script': script_data,
                            'top_image': None,
                            'images': [],
                            'suggested_visuals': manual_title.split()[:5]
                        }
                        st.session_state['script_saved'] = False
                        if 'translated_article' in st.session_state:
                            del st.session_state['translated_article']

                        st.success("✅ Metin yuklendi ve senaryo olusturuldu!")
                        st.rerun()
                    else:
                        st.error("Senaryo olusturulamadi - JSON parse hatasi")

                except Exception as e:
                    st.error(f"Hata: {e}")
                    import traceback
                    st.code(traceback.format_exc())

st.divider()

# Video ayarlari - her iki tab icin de gecerli
col1, col2, col3 = st.columns([2, 1, 1])

with col1:
    output_language = st.selectbox(
        "Video Cikti Dili",
        ["de", "en", "tr"],
        format_func=lambda x: {"de": "🇩🇪 Almanca", "en": "🇬🇧 Ingilizce", "tr": "🇹🇷 Turkce"}.get(x, x),
        help="Senaryo bu dile cevrilecek ve sesli anlatim bu dilde olacak"
    )

with col2:
    video_duration = st.selectbox(
        "Video Suresi",
        ["30s", "60s", "90s"],
        index=1,
        format_func=lambda x: {"30s": "30 saniye", "60s": "1 dakika", "90s": "1.5 dakika"}.get(x, x)
    )

with col3:
    voice_style = st.selectbox(
        "Ses Stili",
        ["professional", "casual", "news"],
        format_func=lambda x: {"professional": "Profesyonel", "casual": "Sohbet", "news": "Haber"}.get(x, x)
    )

# Session state'e dil kaydet
if 'selected_language' not in st.session_state:
    st.session_state['selected_language'] = output_language

# Dil degistiginde ceviriyi sifirla
if st.session_state['selected_language'] != output_language:
    st.session_state['selected_language'] = output_language
    if 'translated_article' in st.session_state:
        del st.session_state['translated_article']

st.divider()

# Article Preview
if 'extracted_article' in st.session_state:
    article = st.session_state['extracted_article']

    # Dil isimleri
    lang_names = {"de": "Almanca", "en": "İngilizce", "tr": "Türkçe"}
    lang_flags = {"de": "🇩🇪", "en": "🇬🇧", "tr": "🇹🇷"}
    target_lang_name = lang_names.get(output_language, "Almanca")
    target_lang_flag = lang_flags.get(output_language, "🇩🇪")

    st.subheader("2️⃣ Makale Önizleme")

    # Çeviri butonu - Makale önizlemesinin hemen üstünde
    col_translate, col_status = st.columns([1, 2])

    with col_translate:
        if st.button(f"🌐 {target_lang_flag} {target_lang_name}'ya Çevir", type="primary", use_container_width=True):
            with st.spinner(f"Makale {target_lang_name}'ya çevriliyor..."):
                try:
                    import google.generativeai as genai
                    from dotenv import load_dotenv
                    load_dotenv()

                    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
                    model = genai.GenerativeModel('gemini-2.0-flash')

                    # Başlığı çevir
                    title_prompt = f"""Aşağıdaki başlığı {target_lang_name}'ya çevir.
Doğal ve akıcı bir dil kullan, gramer kurallarına uy.
Sadece çeviriyi döndür, açıklama ekleme.

Başlık: {article.get('title', '')}"""

                    title_response = model.generate_content(title_prompt)
                    translated_title = title_response.text.strip() if title_response.text else article.get('title', '')

                    # Tam metni çevir
                    text_prompt = f"""Aşağıdaki makale metnini {target_lang_name}'ya çevir.
Doğal, akıcı ve gramer kurallarına uygun bir dil kullan.
Profesyonel bir haber/makale tonu koru.
Sadece çeviriyi döndür, açıklama ekleme.

Metin:
{article.get('text', '')[:10000]}"""

                    text_response = model.generate_content(text_prompt)
                    translated_text = text_response.text.strip() if text_response.text else article.get('text', '')

                    # Video script'i çevir
                    script = article.get('video_script', {})
                    translated_script = {}

                    if script.get('intro'):
                        intro_prompt = f"""Aşağıdaki video giriş metnini {target_lang_name}'ya çevir.
Kısa video için uygun, akıcı ve doğal bir dil kullan.
Gramer kurallarına uy.
Sadece çeviriyi döndür.

Metin: {script['intro']}"""
                        intro_response = model.generate_content(intro_prompt)
                        translated_script['intro'] = intro_response.text.strip() if intro_response.text else script['intro']

                    if script.get('main_points'):
                        translated_points = []
                        for point in script['main_points']:
                            point_prompt = f"""Aşağıdaki video sahne metnini {target_lang_name}'ya çevir.
Kısa ve öz, video için uygun bir dil kullan.
Gramer kurallarına uy.
Sadece çeviriyi döndür.

Metin: {point}"""
                            point_response = model.generate_content(point_prompt)
                            translated_points.append(point_response.text.strip() if point_response.text else point)
                        translated_script['main_points'] = translated_points

                    if script.get('conclusion'):
                        conclusion_prompt = f"""Aşağıdaki video sonuç metnini {target_lang_name}'ya çevir.
Etkileyici bir kapanış için uygun, akıcı bir dil kullan.
Gramer kurallarına uy.
Sadece çeviriyi döndür.

Metin: {script['conclusion']}"""
                        conclusion_response = model.generate_content(conclusion_prompt)
                        translated_script['conclusion'] = conclusion_response.text.strip() if conclusion_response.text else script['conclusion']

                    translated_script['total_segments'] = script.get('total_segments', 0)

                    # Çevrilmiş makaleyi session'a kaydet
                    st.session_state['translated_article'] = {
                        'title': translated_title,
                        'text': translated_text,
                        'video_script': translated_script,
                        'language': output_language,
                        'word_count': len(translated_text.split())
                    }

                    st.success(f"✅ Makale {target_lang_name}'ya çevrildi!")
                    st.rerun()

                except Exception as e:
                    st.error(f"Çeviri hatası: {e}")
                    import traceback
                    st.code(traceback.format_exc())

    with col_status:
        if 'translated_article' in st.session_state and st.session_state['translated_article'].get('language') == output_language:
            st.success(f"✅ {target_lang_flag} {target_lang_name} çevirisi hazır")
        else:
            st.info(f"💡 Orijinal dilde gösteriliyor. {target_lang_name} için çevir butonuna tıklayın.")

    # Çevrilmiş veya orijinal içeriği göster
    if 'translated_article' in st.session_state and st.session_state['translated_article'].get('language') == output_language:
        display_article = st.session_state['translated_article']
        display_script = display_article.get('video_script', {})
        is_translated = True
    else:
        display_article = article
        display_script = article.get('video_script', {})
        is_translated = False

    col_a, col_b = st.columns([2, 1])

    with col_a:
        title_prefix = f"{target_lang_flag} " if is_translated else "📰 "
        st.markdown(f"### {title_prefix}{display_article.get('title', 'Başlık Yok')}")
        st.caption(f"📰 {article.get('source', 'Bilinmeyen Kaynak')} | 👤 {article.get('author', 'Bilinmeyen Yazar')} | 📅 {article.get('publish_date', 'Tarih Yok')}")

        with st.expander(f"📄 Tam Metin {'(' + target_lang_name + ')' if is_translated else '(Orijinal)'}", expanded=False):
            st.write(display_article.get('text', ''))

    with col_b:
        st.metric("Kelime Sayısı", display_article.get('word_count', article.get('word_count', 0)))

        if article.get('top_image'):
            st.image(article['top_image'], caption="Ana Görsel", use_container_width=True)

        if article.get('suggested_visuals'):
            st.write("**🎨 Önerilen Görseller:**")
            for kw in article.get('suggested_visuals', [])[:5]:
                st.markdown(f"• {kw}")

    st.divider()

    # ============================================================
    # SENARYO DUZENLEYICI
    # ============================================================
    script_lang_label = f"({target_lang_name})" if is_translated else "(Orijinal)"
    st.subheader(f"3️⃣ Senaryo Duzenleyici {script_lang_label}")

    # Session state'de duzenlenmis senaryo yoksa, mevcut senaryoyu yukle
    if 'edited_script' not in st.session_state:
        st.session_state['edited_script'] = {
            'intro': display_script.get('intro', '') if display_script else '',
            'main_points': display_script.get('main_points', []) if display_script else [],
            'conclusion': display_script.get('conclusion', '') if display_script else ''
        }

    # Yeni icerik yuklendiginde edited_script'i guncelle
    if 'script_saved' in st.session_state and not st.session_state.get('script_saved', True):
        if display_script:
            st.session_state['edited_script'] = {
                'intro': display_script.get('intro', ''),
                'main_points': display_script.get('main_points', []),
                'conclusion': display_script.get('conclusion', '')
            }

    if display_script:
        st.info("💡 Asagidaki senaryoyu duzenleyebilirsiniz. Degisiklikler video uretiminde kullanilacak.")

        # GIRIS - Duzenlenebilir
        st.markdown("**🎬 Giris:**")
        edited_intro = st.text_area(
            "Giris metni",
            value=st.session_state['edited_script'].get('intro', ''),
            height=80,
            key="edit_intro",
            label_visibility="collapsed"
        )

        # ANA NOKTALAR - Duzenlenebilir
        st.markdown("**📍 Ana Noktalar:**")

        current_points = st.session_state['edited_script'].get('main_points', [])
        if not current_points:
            current_points = ['']

        edited_points = []
        for i, point in enumerate(current_points):
            col_point, col_del = st.columns([10, 1])
            with col_point:
                edited_point = st.text_area(
                    f"Sahne {i+1}",
                    value=point,
                    height=60,
                    key=f"edit_point_{i}",
                    label_visibility="collapsed",
                    placeholder=f"Sahne {i+1} icerigi..."
                )
                edited_points.append(edited_point)
            with col_del:
                if len(current_points) > 1:
                    if st.button("🗑️", key=f"del_point_{i}", help="Bu noktayi sil"):
                        st.session_state['edited_script']['main_points'].pop(i)
                        st.rerun()

        # Yeni nokta ekleme butonu
        if st.button("➕ Yeni Nokta Ekle", key="add_point_btn"):
            st.session_state['edited_script']['main_points'].append('')
            st.rerun()

        # SONUC - Duzenlenebilir
        st.markdown("**🏁 Sonuc:**")
        edited_conclusion = st.text_area(
            "Sonuc metni",
            value=st.session_state['edited_script'].get('conclusion', ''),
            height=80,
            key="edit_conclusion",
            label_visibility="collapsed"
        )

        # Toplam segment sayisi
        total_segments = 1 + len([p for p in edited_points if p.strip()]) + (1 if edited_conclusion.strip() else 0)
        st.info(f"📊 Toplam {total_segments} segment")

        st.divider()

        # ============================================================
        # KAYDET VE VIDEO OLUSTUR BUTONLARI
        # ============================================================
        col_save, col_create = st.columns(2)

        with col_save:
            if st.button("💾 Senaryoyu Kaydet", type="secondary", use_container_width=True, key="save_script_btn"):
                # Session state'e kaydet
                st.session_state['edited_script'] = {
                    'intro': edited_intro,
                    'main_points': [p for p in edited_points if p.strip()],
                    'conclusion': edited_conclusion
                }
                st.session_state['script_saved'] = True
                st.success("✅ Senaryo kaydedildi! Simdi video olusturabilirsiniz.")
                st.rerun()

        with col_create:
            script_saved = st.session_state.get('script_saved', False)
            if not script_saved:
                st.button("🎬 Video Olustur", type="primary", use_container_width=True, disabled=True, key="create_video_disabled", help="Once senaryoyu kaydedin")
                st.warning("⚠️ Video olusturmak icin once senaryoyu kaydedin")
    else:
        st.warning("⚠️ Henuz icerik yuklenmedi. URL'den cikartin veya manuel metin girin.")

    st.divider()

    # Generate Video Button (only if script is saved)
    st.subheader("4️⃣ Video Uret")

    col_v1, col_v2 = st.columns(2)

    with col_v1:
        auto_images = st.checkbox("🖼️ Otomatik görsel oluştur", value=True)
        auto_voice = st.checkbox("🔊 Sesli anlatım ekle", value=True)

    with col_v2:
        add_music = st.checkbox("🎵 Arka plan müziği", value=False)
        add_subtitles = st.checkbox("📝 Altyazı ekle", value=True)

    # Kategori ve Ses Ayarları
    col_cat, col_voice = st.columns(2)

    with col_cat:
        content_category = st.selectbox(
            "📁 Kategori",
            ["auto", "news", "technology", "science", "sports", "finance", "entertainment", "health", "education"],
            format_func=lambda x: {
                "auto": "🔄 Otomatik",
                "news": "📰 Haber",
                "technology": "💻 Teknoloji",
                "science": "🔬 Bilim",
                "sports": "⚽ Spor",
                "finance": "💰 Finans",
                "entertainment": "🎬 Eğlence",
                "health": "🏥 Sağlık",
                "education": "📚 Eğitim"
            }.get(x, x),
            help="İçerik kategorisi video arama sonuçlarını iyileştirir"
        )

    with col_voice:
        voice_provider = st.selectbox(
            "🎤 Ses Sağlayıcı",
            ["edge-tts", "openai", "elevenlabs"],
            format_func=lambda x: {
                "edge-tts": "🆓 Edge TTS (Ücretsiz)",
                "openai": "💎 OpenAI TTS (Doğal)",
                "elevenlabs": "⭐ ElevenLabs (Premium)"
            }.get(x, x),
            help="OpenAI ve ElevenLabs daha doğal ses üretir"
        )

    # PRO Pipeline vs Classic seçimi
    pipeline_mode = st.radio(
        "Video Üretim Modu",
        ["pro", "classic"],
        format_func=lambda x: {"pro": "🚀 PRO Pipeline (Stock Video + Ken Burns + AI Analiz)", "classic": "📹 Classic (Sadece Stok Fotoğraf)"}.get(x, x),
        horizontal=True
    )

    # Video uret butonu - sadece senaryo kaydedildiyse aktif
    script_is_saved = st.session_state.get('script_saved', False)

    if not script_is_saved:
        st.warning("⚠️ Video olusturmak icin once yukaridaki senaryoyu kaydedin.")
        st.button("🎬 Video Uret", type="primary", use_container_width=True, disabled=True, key="video_btn_disabled")
    elif st.button("🎬 Video Uret", type="primary", use_container_width=True, key="video_btn_active"):
        with st.spinner("Video uretiliyor..."):
            try:
                from dotenv import load_dotenv
                load_dotenv()

                # Video production pipeline
                progress = st.progress(0, text="Baslatiliyor...")

                # DUZENLENMIS SENARYOYU KULLAN
                edited_script = st.session_state.get('edited_script', {})
                use_script = {
                    'intro': edited_script.get('intro', ''),
                    'main_points': edited_script.get('main_points', []),
                    'conclusion': edited_script.get('conclusion', '')
                }

                # Article bilgilerini al
                use_article = st.session_state.get('translated_article', article)
                st.success("✅ Duzenlenmis senaryo kullaniliyor")

                # Çevrilmiş başlık varsa onu kullan
                video_title = use_article.get('title', article.get('title', 'URL Video'))

                duration_seconds = int(video_duration.replace('s', ''))
                source_name = article.get('source', 'unknown').replace('.', '_').replace(' ', '_')[:20]
                timestamp = int(datetime.now().timestamp())

                # ============================================================
                # PRO PIPELINE MODE
                # ============================================================
                if pipeline_mode == "pro":
                    progress.progress(5, text="🚀 PRO Pipeline başlatılıyor...")

                    from modules.pro_video_pipeline import ProVideoPipeline

                    # Initialize PRO pipeline
                    pipeline = ProVideoPipeline(
                        gemini_api_key=os.getenv("GEMINI_API_KEY"),
                        pixabay_api_key=os.getenv("PIXABAY_API_KEY"),
                        pexels_api_key=os.getenv("PEXELS_API_KEY"),
                        output_resolution=(1920, 1080),
                        fps=30
                    )

                    # Pipeline durumunu göster
                    status = pipeline.get_status()
                    status_text = []
                    if status.get('analyzer'):
                        status_text.append("✅ AI Analiz")
                    if status.get('video_provider'):
                        status_text.append("✅ Stock Video")
                    if status.get('ken_burns'):
                        status_text.append("✅ Ken Burns")
                    if status.get('tts'):
                        status_text.append("✅ TTS")

                    st.info(f"🔧 Aktif Modüller: {' | '.join(status_text)}")

                    progress.progress(10, text="📊 İçerik analiz ediliyor...")

                    # Article data hazırla
                    article_data = {
                        'title': video_title,
                        'text': use_article.get('text', ''),
                        'images': [article.get('top_image')] if article.get('top_image') else [],
                        'video_script': {
                            'intro': use_script.get('intro', ''),
                            'main_points': use_script.get('main_points', []),
                            'outro': use_script.get('conclusion', '')
                        }
                    }

                    # Output directory
                    output_dir = Path(__file__).parent.parent.parent / "output" / "pro_videos" / f"{source_name}_{timestamp}"
                    output_dir.mkdir(parents=True, exist_ok=True)

                    # Progress callbacks for UI
                    progress.progress(20, text="🎨 Görsel kaynaklar toplanıyor...")

                    # Produce video
                    result = pipeline.produce_video_from_article(
                        article_data=article_data,
                        output_dir=str(output_dir),
                        language=output_language,
                        duration=duration_seconds,
                        use_article_images=auto_images,
                        use_stock_videos=True,
                        voice_style=voice_style,
                        add_subtitles=add_subtitles,
                        voice_provider=voice_provider,
                        category=content_category
                    )

                    progress.progress(90, text="🎬 Video finalize ediliyor...")

                    if result.get('success'):
                        progress.progress(100, text="✅ Tamamlandı!")

                        video_path = result.get('files', {}).get('video')
                        if video_path and os.path.exists(video_path):
                            st.session_state['produced_video'] = video_path
                            st.session_state['video_ready_to_publish'] = True

                            st.success(f"✅ PRO Video oluşturuldu!")

                            # Detayları göster
                            col_result1, col_result2 = st.columns(2)
                            with col_result1:
                                st.metric("Üretim Süresi", f"{result.get('production_time_seconds', 0):.1f}s")
                            with col_result2:
                                visuals = result.get('phases', {}).get('visuals', {})
                                types = visuals.get('types', {})
                                st.metric("Kaynaklar", f"🎥{types.get('video', 0)} 🖼️{types.get('image', 0)}")

                            st.video(video_path)
                        else:
                            st.error("Video dosyası oluşturulamadı")
                            if result.get('error'):
                                st.code(result.get('error'))
                    else:
                        st.error(f"PRO Pipeline hatası: {result.get('error', 'Bilinmeyen hata')}")
                        # Phase detayları
                        for phase, details in result.get('phases', {}).items():
                            if details.get('status') == 'failed':
                                st.warning(f"❌ {phase}: {details.get('error', 'Hata')}")

                # ============================================================
                # CLASSIC MODE (Eski sistem - fallback)
                # ============================================================
                else:
                    from modules.image_generator import ImageGenerator
                    from modules.video_editor import VideoEditor

                    progress.progress(10, text="Senaryo hazırlanıyor...")

                    # Script'i birleştir
                    script_text = use_script.get('intro', '')
                    for point in use_script.get('main_points', []):
                        script_text += f"\n\n{point}"
                    if use_script.get('conclusion'):
                        script_text += f"\n\n{use_script['conclusion']}"

                    # 2. Görseller
                    if auto_images:
                        progress.progress(30, text="Görseller oluşturuluyor...")

                        img_gen = ImageGenerator(
                            pexels_api_key=os.getenv("PEXELS_API_KEY")
                        )

                        # Output klasörü oluştur
                        images_dir = Path(__file__).parent.parent.parent / "output" / "images"
                        images_dir.mkdir(parents=True, exist_ok=True)

                        keywords = article.get('suggested_visuals', ['technology', 'news'])
                        images = []
                        for i, kw in enumerate(keywords[:4]):
                            img_output_path = str(images_dir / f"url_img_{i}_{timestamp}.jpg")
                            img_success = img_gen.generate_image(kw, output_path=img_output_path)
                            if img_success and os.path.exists(img_output_path):
                                images.append(img_output_path)

                        st.session_state['video_images'] = images
                        st.success(f"✅ {len(images)} görsel oluşturuldu")

                    # 3. Ses
                    if auto_voice:
                        progress.progress(50, text="Sesli anlatım oluşturuluyor...")

                        try:
                            from modules.edge_tts_generator import EdgeTTSGenerator

                            voice_output_path = str(Path(__file__).parent.parent.parent / "output" / "temp_voice.mp3")
                            voice_gen = EdgeTTSGenerator(language=output_language)
                            voice_success = voice_gen.generate_speech(
                                text=script_text[:2000],
                                output_path=voice_output_path
                            )

                            if voice_success:
                                st.session_state['video_voice'] = voice_output_path
                                st.success("✅ Sesli anlatım oluşturuldu")
                            else:
                                st.warning("Ses oluşturulamadı, sessiz video üretilecek")
                        except Exception as voice_error:
                            st.warning(f"Ses hatası: {voice_error}")

                    # 4. Video birleştir
                    progress.progress(70, text="Video birleştiriliyor...")

                    if 'video_images' in st.session_state and st.session_state['video_images']:
                        editor = VideoEditor()

                        output_path = str(Path(__file__).parent.parent.parent / "output" / "videos" / f"url_video_{source_name}_{timestamp}.mp4")

                        num_images = len(st.session_state['video_images'])
                        scene_duration = duration_seconds / num_images

                        script_data = {
                            'title': video_title,
                            'metadata': {'duration': duration_seconds},
                            'scenes': []
                        }

                        current_time = 0
                        main_points = use_script.get('main_points', [])
                        for i in range(num_images):
                            text = main_points[i] if i < len(main_points) else f"Sahne {i+1}"
                            script_data['scenes'].append({
                                'time': f"{int(current_time)}-{int(current_time + scene_duration)}s",
                                'text': text[:100]
                            })
                            current_time += scene_duration

                        video_success = editor.create_video_from_script(
                            script_data=script_data,
                            image_files=st.session_state.get('video_images', []),
                            voiceover_path=st.session_state.get('video_voice'),
                            output_path=output_path
                        )

                        if video_success:
                            progress.progress(100, text="Tamamlandı!")
                            st.success(f"✅ Video oluşturuldu!")
                            st.session_state['produced_video'] = output_path
                            st.session_state['video_ready_to_publish'] = True

                            if os.path.exists(output_path):
                                st.video(output_path)
                        else:
                            st.error("Video oluşturulamadı")
                    else:
                        st.warning("Görsel bulunamadı, video oluşturulamadı")

            except Exception as e:
                st.error(f"Video üretim hatası: {e}")
                import traceback
                st.code(traceback.format_exc())

    # 5. Sosyal Medya Yayınlama Bölümü
    if st.session_state.get('video_ready_to_publish') and st.session_state.get('produced_video'):
        st.divider()
        st.subheader("5️⃣ Sosyal Medyada Yayınla")

        video_path = st.session_state['produced_video']

        # Bağlı hesapları kontrol et
        creds_dir = Path(__file__).parent.parent.parent / "credentials"

        # Platform hesaplarını topla
        youtube_channels = []
        instagram_accounts = []
        tiktok_accounts = []

        if creds_dir.exists():
            for cred_file in creds_dir.glob("youtube_token_*.json"):
                channel_name = cred_file.stem.replace("youtube_token_", "")
                youtube_channels.append(channel_name)

            for cred_file in creds_dir.glob("instagram_*.json"):
                account_name = cred_file.stem.replace("instagram_", "")
                instagram_accounts.append(account_name)

            for cred_file in creds_dir.glob("tiktok_*.json"):
                account_name = cred_file.stem.replace("tiktok_", "")
                tiktok_accounts.append(account_name)

        # Platform seçimi
        tab_yt, tab_ig, tab_tt = st.tabs(["📺 YouTube", "📸 Instagram", "🎵 TikTok"])

        # Video bilgileri (tüm platformlar için ortak)
        video_title_input = st.session_state.get('translated_article', {}).get('title', article.get('title', 'URL Video'))[:100]
        video_tags = ", ".join(article.get('suggested_visuals', [])[:5])
        video_description = f"Bu video {article.get('source', 'web')} kaynağından oluşturulmuştur.\n\n#shorts #news #trending"

        # YouTube Tab
        with tab_yt:
            if youtube_channels:
                st.success(f"✅ {len(youtube_channels)} YouTube hesabı bağlı")

                selected_yt_channel = st.selectbox(
                    "YouTube Kanalı",
                    youtube_channels,
                    format_func=lambda x: f"📺 {x}",
                    key="yt_channel"
                )

                col_yt1, col_yt2 = st.columns(2)
                with col_yt1:
                    yt_title = st.text_input("Başlık", value=video_title_input, key="yt_title")
                    yt_tags = st.text_input("Etiketler", value=video_tags, key="yt_tags")
                with col_yt2:
                    yt_desc = st.text_area("Açıklama", value=video_description, height=80, key="yt_desc")
                    yt_privacy = st.selectbox(
                        "Gizlilik",
                        ["public", "unlisted", "private"],
                        format_func=lambda x: {"public": "🌍 Herkese Açık", "unlisted": "🔗 Bağlantıyla", "private": "🔒 Gizli"}.get(x, x),
                        key="yt_privacy"
                    )

                if st.button("🚀 YouTube'a Yükle", type="primary", use_container_width=True, key="upload_yt"):
                    with st.spinner("YouTube'a yükleniyor..."):
                        try:
                            from modules.youtube_uploader import YouTubeUploader
                            uploader = YouTubeUploader(channel_name=selected_yt_channel)
                            result = uploader.upload_video(
                                video_path=video_path,
                                title=yt_title,
                                description=yt_desc,
                                tags=yt_tags.split(","),
                                privacy_status=yt_privacy
                            )
                            if result.get('success'):
                                video_url = f"https://youtube.com/watch?v={result.get('video_id')}"
                                st.success(f"✅ YouTube'a yüklendi!")
                                st.markdown(f"🔗 [Video'yu İzle]({video_url})")
                                st.balloons()
                            else:
                                st.error(f"Yükleme hatası: {result.get('error')}")
                        except Exception as e:
                            st.error(f"YouTube hatası: {e}")
            else:
                st.warning("⚠️ Bağlı YouTube hesabı yok")
                if st.button("📺 YouTube Hesabı Bağla", key="connect_yt"):
                    st.switch_page("pages/Social_Login.py")

        # Instagram Tab
        with tab_ig:
            if instagram_accounts:
                st.success(f"✅ {len(instagram_accounts)} Instagram hesabı bağlı")

                selected_ig_account = st.selectbox(
                    "Instagram Hesabı",
                    instagram_accounts,
                    format_func=lambda x: f"📸 @{x}",
                    key="ig_account"
                )

                col_ig1, col_ig2 = st.columns(2)
                with col_ig1:
                    ig_caption = st.text_area(
                        "Caption",
                        value=f"{video_title_input}\n\n{video_description}\n\n#reels #viral #trending",
                        height=120,
                        key="ig_caption"
                    )
                with col_ig2:
                    ig_type = st.selectbox(
                        "Paylaşım Türü",
                        ["reels", "story", "post"],
                        format_func=lambda x: {"reels": "🎬 Reels", "story": "📖 Story", "post": "📷 Post"}.get(x, x),
                        key="ig_type"
                    )
                    ig_location = st.text_input("Konum (opsiyonel)", key="ig_location")

                if st.button("🚀 Instagram'a Yükle", type="primary", use_container_width=True, key="upload_ig"):
                    with st.spinner("Instagram'a yükleniyor..."):
                        try:
                            from modules.instagram_uploader import InstagramUploader
                            uploader = InstagramUploader(account_name=selected_ig_account)
                            result = uploader.upload_video(
                                video_path=video_path,
                                caption=ig_caption,
                                upload_type=ig_type,
                                location=ig_location if ig_location else None
                            )
                            if result.get('success'):
                                st.success(f"✅ Instagram'a yüklendi!")
                                if result.get('url'):
                                    st.markdown(f"🔗 [Gönderiyi Gör]({result.get('url')})")
                                st.balloons()
                            else:
                                st.error(f"Yükleme hatası: {result.get('error')}")
                        except ImportError:
                            st.error("Instagram uploader modülü bulunamadı. Modül oluşturulmalı.")
                        except Exception as e:
                            st.error(f"Instagram hatası: {e}")
            else:
                st.warning("⚠️ Bağlı Instagram hesabı yok")
                if st.button("📸 Instagram Hesabı Bağla", key="connect_ig"):
                    st.switch_page("pages/Social_Login.py")

        # TikTok Tab
        with tab_tt:
            if tiktok_accounts:
                st.success(f"✅ {len(tiktok_accounts)} TikTok hesabı bağlı")

                selected_tt_account = st.selectbox(
                    "TikTok Hesabı",
                    tiktok_accounts,
                    format_func=lambda x: f"🎵 @{x}",
                    key="tt_account"
                )

                col_tt1, col_tt2 = st.columns(2)
                with col_tt1:
                    tt_caption = st.text_area(
                        "Caption",
                        value=f"{video_title_input} #fyp #viral #trending #news",
                        height=100,
                        key="tt_caption"
                    )
                with col_tt2:
                    tt_privacy = st.selectbox(
                        "Gizlilik",
                        ["public", "friends", "private"],
                        format_func=lambda x: {"public": "🌍 Herkese Açık", "friends": "👥 Arkadaşlar", "private": "🔒 Gizli"}.get(x, x),
                        key="tt_privacy"
                    )
                    tt_duet = st.checkbox("Düet'e izin ver", value=True, key="tt_duet")
                    tt_stitch = st.checkbox("Stitch'e izin ver", value=True, key="tt_stitch")

                if st.button("🚀 TikTok'a Yükle", type="primary", use_container_width=True, key="upload_tt"):
                    with st.spinner("TikTok'a yükleniyor..."):
                        try:
                            from modules.tiktok_uploader import TikTokUploader
                            uploader = TikTokUploader(account_name=selected_tt_account)
                            result = uploader.upload_video(
                                video_path=video_path,
                                caption=tt_caption,
                                privacy=tt_privacy,
                                allow_duet=tt_duet,
                                allow_stitch=tt_stitch
                            )
                            if result.get('success'):
                                st.success(f"✅ TikTok'a yüklendi!")
                                if result.get('url'):
                                    st.markdown(f"🔗 [Videoyu Gör]({result.get('url')})")
                                st.balloons()
                            else:
                                st.error(f"Yükleme hatası: {result.get('error')}")
                        except ImportError:
                            st.error("TikTok uploader modülü bulunamadı. Modül oluşturulmalı.")
                        except Exception as e:
                            st.error(f"TikTok hatası: {e}")
            else:
                st.warning("⚠️ Bağlı TikTok hesabı yok")
                if st.button("🎵 TikTok Hesabı Bağla", key="connect_tt"):
                    st.switch_page("pages/Social_Login.py")

        # Tüm platformlara yükle butonu
        st.divider()
        all_platforms = []
        if youtube_channels:
            all_platforms.append("YouTube")
        if instagram_accounts:
            all_platforms.append("Instagram")
        if tiktok_accounts:
            all_platforms.append("TikTok")

        if len(all_platforms) > 1:
            if st.button(f"🚀 Tümüne Yükle ({', '.join(all_platforms)})", type="secondary", use_container_width=True):
                st.info("Bu özellik yakında eklenecek - şimdilik tek tek yükleyin.")

else:
    st.info("👆 Yukarıdan bir URL girin ve 'Makaleyi Çıkar' butonuna tıklayın")

# Footer
st.markdown("---")
st.caption("VIDEOCU v1 - URL to Video | Powered by Claude Code")
