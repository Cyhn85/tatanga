"""
VIDEOCU Studio - Music Production Page
Modal GPU Backend ile Ses Prodüksiyon
"""

import streamlit as st
import sys
import os
import tempfile
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

st.set_page_config(
    page_title="Music Studio - VIDEOCU",
    page_icon="🎵",
    layout="wide"
)

# Custom CSS
st.markdown("""
<style>
    .music-header {
        background: linear-gradient(90deg, #667eea, #764ba2);
        padding: 1rem;
        border-radius: 10px;
        margin-bottom: 1rem;
    }
    .gpu-status {
        background: #1a1a2e;
        padding: 0.5rem 1rem;
        border-radius: 5px;
        display: inline-block;
    }
    .waveform-box {
        background: #0f0f1a;
        border: 1px solid #333;
        border-radius: 10px;
        padding: 1rem;
        min-height: 100px;
    }
</style>
""", unsafe_allow_html=True)

st.title("🎵 Music Studio")
st.markdown("*Modal GPU ile profesyonel ses prodüksiyon*")

# Initialize session state
if 'audio_file' not in st.session_state:
    st.session_state.audio_file = None
if 'midi_file' not in st.session_state:
    st.session_state.midi_file = None
if 'processed_audio' not in st.session_state:
    st.session_state.processed_audio = None

# GPU Status Check
try:
    from modules.colab.colab_bridge import ColabBridge
    bridge = ColabBridge()
    gpu_available = bridge.is_available()
    gpu_name = "Tesla T4 (Modal.com)" if bridge._modal_available else "N/A"
except Exception as e:
    gpu_available = False
    gpu_name = f"Error: {e}"
    bridge = None

col1, col2, col3 = st.columns([1, 1, 2])
with col1:
    if gpu_available:
        st.success(f"🟢 GPU: {gpu_name}")
    else:
        st.error("🔴 GPU Bağlı Değil")
with col2:
    if st.button("🔄 Yenile"):
        st.rerun()

st.divider()

# Main Tabs
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📁 Dosya Yükle",
    "🎼 Melodi Çıkar",
    "🎹 MIDI İşlemleri",
    "🔀 Stem Ayır",
    "🎨 AI Müzik Üret",
    "🎸 Stil Dönüştür"
])

# ==================== TAB 1: DOSYA YÜKLE ====================
with tab1:
    st.header("📁 Ses Dosyası Yükle")

    col1, col2 = st.columns(2)

    with col1:
        uploaded_audio = st.file_uploader(
            "Ses Dosyası Seçin",
            type=['mp3', 'wav', 'ogg', 'm4a', 'flac'],
            help="Desteklenen formatlar: MP3, WAV, OGG, M4A, FLAC"
        )

        if uploaded_audio:
            # Save to temp file
            temp_dir = tempfile.mkdtemp()
            temp_path = os.path.join(temp_dir, uploaded_audio.name)
            with open(temp_path, 'wb') as f:
                f.write(uploaded_audio.read())

            st.session_state.audio_file = temp_path
            st.success(f"✅ Dosya yüklendi: {uploaded_audio.name}")
            st.audio(temp_path)

            # File info
            file_size = os.path.getsize(temp_path) / (1024 * 1024)
            st.info(f"📊 Boyut: {file_size:.2f} MB")

    with col2:
        st.subheader("🎤 Ses Kaydet")
        st.info("Mikrofon kaydı yakında eklenecek...")

        st.subheader("📋 Mevcut Dosya")
        if st.session_state.audio_file:
            st.write(f"**Dosya:** {os.path.basename(st.session_state.audio_file)}")
            if st.button("❌ Dosyayı Kaldır"):
                st.session_state.audio_file = None
                st.rerun()
        else:
            st.write("Henüz dosya yüklenmedi")

# ==================== TAB 2: MELODİ ÇIKAR ====================
with tab2:
    st.header("🎼 Melodi Çıkarma (Basic Pitch)")
    st.markdown("*Ses dosyasından MIDI melodi çıkar*")

    col1, col2 = st.columns([2, 1])

    with col1:
        if st.session_state.audio_file:
            st.audio(st.session_state.audio_file)
            st.write(f"**Kaynak:** {os.path.basename(st.session_state.audio_file)}")
        else:
            st.warning("⚠️ Önce bir ses dosyası yükleyin")

    with col2:
        st.subheader("⚙️ Ayarlar")
        min_note_length = st.slider("Min. Nota Uzunluğu (ms)", 50, 500, 100)
        onset_threshold = st.slider("Onset Hassasiyeti", 0.1, 1.0, 0.5)

    if st.button("🎼 Melodiyi Çıkar", type="primary", use_container_width=True, disabled=not gpu_available):
        if not st.session_state.audio_file:
            st.error("Önce ses dosyası yükleyin!")
        elif not bridge:
            st.error("GPU bağlantısı yok!")
        else:
            with st.spinner("🎼 Modal GPU'da melodi çıkarılıyor..."):
                try:
                    result = bridge.extract_melody(st.session_state.audio_file)

                    if result.get('success'):
                        st.success("✅ Melodi başarıyla çıkarıldı!")

                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("🎵 Nota Sayısı", result.get('note_count', 'N/A'))
                        with col2:
                            st.metric("🎼 Anahtar", result.get('key', 'N/A'))
                        with col3:
                            st.metric("⏱️ Tempo", f"{result.get('tempo', 'N/A')} BPM")

                        # Save MIDI path
                        midi_path = result.get('midi_path')
                        if midi_path and os.path.exists(midi_path):
                            st.session_state.midi_file = midi_path
                            st.info(f"📁 MIDI kaydedildi: {midi_path}")

                            with open(midi_path, 'rb') as f:
                                st.download_button(
                                    "⬇️ MIDI İndir",
                                    f.read(),
                                    file_name="melody.mid",
                                    mime="audio/midi"
                                )
                    else:
                        st.error(f"❌ Hata: {result.get('error', 'Bilinmeyen hata')}")
                except Exception as e:
                    st.error(f"❌ Hata: {e}")

# ==================== TAB 3: MIDI İŞLEMLERİ ====================
with tab3:
    st.header("🎹 MIDI İşlemleri")

    # MIDI upload or use existing
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("📁 MIDI Dosyası")
        uploaded_midi = st.file_uploader("MIDI Yükle", type=['mid', 'midi'])

        if uploaded_midi:
            temp_dir = tempfile.mkdtemp()
            midi_temp = os.path.join(temp_dir, uploaded_midi.name)
            with open(midi_temp, 'wb') as f:
                f.write(uploaded_midi.read())
            st.session_state.midi_file = midi_temp
            st.success(f"✅ MIDI yüklendi: {uploaded_midi.name}")

        if st.session_state.midi_file:
            st.info(f"📁 Aktif MIDI: {os.path.basename(st.session_state.midi_file)}")

    with col2:
        st.subheader("🛠️ İşlem Seç")

    st.divider()

    # MIDI Operations
    midi_col1, midi_col2, midi_col3 = st.columns(3)

    with midi_col1:
        st.markdown("### ⚡ Quantize")
        st.markdown("*Notaları grid'e hizala*")

        grid_size = st.selectbox(
            "Grid Boyutu",
            ["8th", "16th", "32nd"],
            format_func=lambda x: {
                "8th": "1/8 Nota",
                "16th": "1/16 Nota",
                "32nd": "1/32 Nota"
            }.get(x, x)
        )

        if st.button("⚡ Quantize Yap", type="primary", disabled=not gpu_available):
            if not st.session_state.midi_file:
                st.error("Önce MIDI dosyası yükleyin!")
            else:
                with st.spinner("Quantize ediliyor..."):
                    try:
                        result = bridge.quantize_midi(st.session_state.midi_file, grid=grid_size)
                        if result.get('success'):
                            st.success(f"✅ {result.get('corrections', 0)} nota düzeltildi!")
                            st.session_state.midi_file = result.get('midi_path')

                            with open(result['midi_path'], 'rb') as f:
                                st.download_button("⬇️ İndir", f.read(), "quantized.mid")
                        else:
                            st.error(f"❌ {result.get('error')}")
                    except Exception as e:
                        st.error(f"❌ Hata: {e}")

    with midi_col2:
        st.markdown("### 🎵 Transpose")
        st.markdown("*Tonu değiştir*")

        semitones = st.slider("Yarım Adım", -12, 12, 0)

        transpose_label = ""
        if semitones > 0:
            transpose_label = f"+{semitones} (Yukarı)"
        elif semitones < 0:
            transpose_label = f"{semitones} (Aşağı)"
        else:
            transpose_label = "0 (Değişiklik yok)"
        st.write(f"**Değişim:** {transpose_label}")

        if st.button("🎵 Transpose Yap", type="primary", disabled=not gpu_available):
            if not st.session_state.midi_file:
                st.error("Önce MIDI dosyası yükleyin!")
            elif semitones == 0:
                st.warning("Lütfen bir değer seçin")
            else:
                with st.spinner("Transpose ediliyor..."):
                    try:
                        result = bridge.transpose_midi(st.session_state.midi_file, semitones=semitones)
                        if result.get('success'):
                            st.success(f"✅ {result.get('note_count', 0)} nota transpose edildi!")
                            st.session_state.midi_file = result.get('midi_path')

                            with open(result['midi_path'], 'rb') as f:
                                st.download_button("⬇️ İndir", f.read(), "transposed.mid")
                        else:
                            st.error(f"❌ {result.get('error')}")
                    except Exception as e:
                        st.error(f"❌ Hata: {e}")

    with midi_col3:
        st.markdown("### 🎸 MIDI → Audio")
        st.markdown("*Enstrüman ile çal*")

        instrument = st.selectbox(
            "Enstrüman",
            ["piano", "bass", "synth", "strings", "guitar", "organ"],
            format_func=lambda x: {
                "piano": "🎹 Piyano",
                "bass": "🎸 Bas",
                "synth": "🎛️ Synthesizer",
                "strings": "🎻 Yaylılar",
                "guitar": "🎸 Gitar",
                "organ": "🎹 Org"
            }.get(x, x)
        )

        if st.button("🎸 Audio Oluştur", type="primary", disabled=not gpu_available):
            if not st.session_state.midi_file:
                st.error("Önce MIDI dosyası yükleyin!")
            else:
                with st.spinner(f"MIDI → {instrument} audio dönüştürülüyor..."):
                    try:
                        result = bridge.midi_to_audio(st.session_state.midi_file, instrument=instrument)
                        if result.get('success'):
                            st.success(f"✅ Audio oluşturuldu! ({result.get('duration', 0):.1f}s)")
                            audio_path = result.get('audio_path')
                            if audio_path and os.path.exists(audio_path):
                                st.audio(audio_path)
                                with open(audio_path, 'rb') as f:
                                    st.download_button("⬇️ WAV İndir", f.read(), f"{instrument}_output.wav")
                        else:
                            st.error(f"❌ {result.get('error')}")
                    except Exception as e:
                        st.error(f"❌ Hata: {e}")

# ==================== TAB 4: STEM AYIR ====================
with tab4:
    st.header("🔀 Stem Ayırma (Demucs)")
    st.markdown("*Vokal ve enstrümanları ayır*")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("📁 Kaynak Ses")
        if st.session_state.audio_file:
            st.audio(st.session_state.audio_file)
            st.write(f"**Dosya:** {os.path.basename(st.session_state.audio_file)}")
        else:
            st.warning("⚠️ Önce bir ses dosyası yükleyin")

    with col2:
        st.subheader("🎯 Çıktılar")
        st.markdown("""
        - 🎤 **Vocals** - Sadece vokal
        - 🎸 **Instrumental** - Vokal hariç tüm enstrümanlar
        """)

    if st.button("🔀 Stem'leri Ayır", type="primary", use_container_width=True, disabled=not gpu_available):
        if not st.session_state.audio_file:
            st.error("Önce ses dosyası yükleyin!")
        else:
            with st.spinner("🔀 Demucs ile stem'ler ayrılıyor... (Bu işlem 1-2 dk sürebilir)"):
                try:
                    result = bridge.separate_stems(st.session_state.audio_file)

                    if result.get('success'):
                        st.success("✅ Stem'ler başarıyla ayrıldı!")

                        stems = result.get('stems', {})

                        col1, col2 = st.columns(2)

                        with col1:
                            st.markdown("### 🎤 Vocals")
                            vocals_path = stems.get('vocals')
                            if vocals_path and os.path.exists(vocals_path):
                                st.audio(vocals_path)
                                with open(vocals_path, 'rb') as f:
                                    st.download_button("⬇️ Vocals İndir", f.read(), "vocals.wav")
                            else:
                                st.warning("Vokal bulunamadı")

                        with col2:
                            st.markdown("### 🎸 Instrumental")
                            inst_path = stems.get('no_vocals')
                            if inst_path and os.path.exists(inst_path):
                                st.audio(inst_path)
                                with open(inst_path, 'rb') as f:
                                    st.download_button("⬇️ Instrumental İndir", f.read(), "instrumental.wav")
                            else:
                                st.warning("Enstrümantal bulunamadı")
                    else:
                        st.error(f"❌ Hata: {result.get('error')}")
                except Exception as e:
                    st.error(f"❌ Hata: {e}")

# ==================== TAB 5: AI MÜZİK ÜRET ====================
with tab5:
    st.header("🎨 AI Müzik Üretimi (MusicGen)")
    st.markdown("*Metin açıklamasından müzik üret*")

    col1, col2 = st.columns([2, 1])

    with col1:
        # Style presets
        style_preset = st.selectbox(
            "Stil Şablonu",
            ["custom", "hip-hop", "pop", "electronic", "rock", "lofi", "rnb", "trap", "acoustic", "orchestral", "jazz"],
            format_func=lambda x: {
                "custom": "✏️ Özel Prompt",
                "hip-hop": "🎤 Hip-Hop",
                "pop": "🎵 Pop",
                "electronic": "🎛️ Electronic",
                "rock": "🎸 Rock",
                "lofi": "☕ Lo-Fi",
                "rnb": "💜 R&B",
                "trap": "🔥 Trap",
                "acoustic": "🎸 Acoustic",
                "orchestral": "🎻 Orchestral",
                "jazz": "🎷 Jazz"
            }.get(x, x)
        )

        if style_preset == "custom":
            prompt = st.text_area(
                "Müzik Açıklaması",
                placeholder="Örn: upbeat electronic dance music with pulsing synths and energetic drums",
                height=100
            )
        else:
            # Get preset prompt
            from modules.colab.colab_bridge import STYLE_PROMPTS
            prompt = STYLE_PROMPTS.get(style_preset, "")
            st.info(f"**Prompt:** {prompt}")

    with col2:
        st.subheader("⚙️ Ayarlar")
        duration = st.slider("Süre (saniye)", 5, 30, 15)
        st.caption("⚠️ Uzun süreler daha fazla GPU zamanı gerektirir")

    if st.button("🎨 Müzik Üret", type="primary", use_container_width=True, disabled=not gpu_available):
        if not prompt:
            st.error("Lütfen bir açıklama girin!")
        else:
            with st.spinner(f"🎨 MusicGen ile {duration}s müzik üretiliyor..."):
                try:
                    result = bridge.generate_music(prompt=prompt, duration=duration)

                    if result.get('success'):
                        st.success("✅ Müzik üretildi!")
                        audio_path = result.get('audio_path')

                        if audio_path and os.path.exists(audio_path):
                            st.audio(audio_path)
                            st.session_state.processed_audio = audio_path

                            with open(audio_path, 'rb') as f:
                                st.download_button(
                                    "⬇️ WAV İndir",
                                    f.read(),
                                    f"generated_{style_preset}.wav",
                                    mime="audio/wav"
                                )
                    else:
                        st.error(f"❌ Hata: {result.get('error')}")
                except Exception as e:
                    st.error(f"❌ Hata: {e}")

# ==================== TAB 6: STİL DÖNÜŞTÜR ====================
with tab6:
    st.header("🎸 Melodi Stil Dönüşümü")
    st.markdown("*Melodinizi profesyonel bir stile dönüştürün*")

    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader("📁 Kaynak Melodi")
        if st.session_state.audio_file:
            st.audio(st.session_state.audio_file)
            st.write(f"**Dosya:** {os.path.basename(st.session_state.audio_file)}")
        else:
            st.warning("⚠️ Önce bir ses dosyası yükleyin (Dosya Yükle sekmesinden)")

        style_transform = st.selectbox(
            "Hedef Stil",
            ["hip-hop", "pop", "electronic", "rock", "lofi", "orchestral", "jazz"],
            format_func=lambda x: {
                "hip-hop": "🎤 Hip-Hop Beat",
                "pop": "🎵 Pop Song",
                "electronic": "🎛️ EDM",
                "rock": "🎸 Rock",
                "lofi": "☕ Lo-Fi Chill",
                "orchestral": "🎻 Orchestral",
                "jazz": "🎷 Jazz"
            }.get(x, x)
        )

    with col2:
        st.subheader("⚙️ Ayarlar")
        transform_duration = st.slider("Çıktı Süresi (saniye)", 10, 30, 15, key="transform_dur")

    if st.button("🎸 Stili Dönüştür", type="primary", use_container_width=True, disabled=not gpu_available):
        if not st.session_state.audio_file:
            st.error("Önce ses dosyası yükleyin!")
        else:
            from modules.colab.colab_bridge import get_style_prompt
            style_prompt = get_style_prompt(style_transform)

            with st.spinner(f"🎸 Melodi {style_transform} stiline dönüştürülüyor..."):
                try:
                    result = bridge.transform_melody(
                        audio_path=st.session_state.audio_file,
                        style_prompt=style_prompt,
                        duration=transform_duration
                    )

                    if result.get('success'):
                        st.success("✅ Dönüşüm tamamlandı!")
                        audio_path = result.get('audio_path')

                        if audio_path and os.path.exists(audio_path):
                            st.audio(audio_path)
                            st.session_state.processed_audio = audio_path

                            with open(audio_path, 'rb') as f:
                                st.download_button(
                                    "⬇️ WAV İndir",
                                    f.read(),
                                    f"transformed_{style_transform}.wav",
                                    mime="audio/wav"
                                )
                    else:
                        st.error(f"❌ Hata: {result.get('error')}")
                except Exception as e:
                    st.error(f"❌ Hata: {e}")

# Footer
st.divider()
st.markdown("""
<p style="text-align: center; color: #666;">
    🎵 Music Studio | Modal.com GPU Backend | Tesla T4
</p>
""", unsafe_allow_html=True)
