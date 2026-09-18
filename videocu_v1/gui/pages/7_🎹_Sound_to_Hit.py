"""
VIDEOCU Studio - Sound to Hit
Ham sesleri profesyonel muzige donustur

Features:
1. Ham ses yukleme (MP3, WAV, OGG)
2. Nota/ritim tespiti (Basic Pitch + Librosa)
3. Piano Roll gorsellestirme
4. Enstruman donusumu (808, 909, Acoustic, Electronic)
5. Elektronik efektler (Distortion, Filter, Reverb, Delay)
6. DJ kontrolleri (hiz, EQ, presetler)
7. Export (MP3/WAV)
"""

import streamlit as st
import sys
import os
import tempfile
import json
from pathlib import Path
import numpy as np

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

st.set_page_config(
    page_title="Sound to Hit - VIDEOCU",
    page_icon="🎹",
    layout="wide"
)

# Custom CSS
st.markdown("""
<style>
    .hit-header {
        background: linear-gradient(135deg, #667eea 0%, #f093fb 50%, #f5576c 100%);
        padding: 1.5rem;
        border-radius: 15px;
        margin-bottom: 1.5rem;
        text-align: center;
    }
    .hit-header h1 {
        color: white;
        margin: 0;
        text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
    }
    .hit-header p {
        color: rgba(255,255,255,0.9);
        margin: 0.5rem 0 0 0;
    }
    .effect-card {
        background: linear-gradient(145deg, #1a1a2e, #16213e);
        border: 1px solid #333;
        border-radius: 10px;
        padding: 1rem;
        margin-bottom: 1rem;
    }
    .preset-button {
        background: linear-gradient(135deg, #667eea, #764ba2);
        border: none;
        border-radius: 8px;
        padding: 0.5rem 1rem;
        color: white;
        cursor: pointer;
    }
    .timeline-container {
        background: #0a0a15;
        border: 1px solid #333;
        border-radius: 10px;
        padding: 1rem;
        min-height: 200px;
    }
    .note-detected {
        background: #10b981;
        color: white;
        padding: 0.2rem 0.5rem;
        border-radius: 4px;
        font-size: 0.8rem;
        margin-right: 0.3rem;
    }
</style>
""", unsafe_allow_html=True)

# Header
st.markdown("""
<div class="hit-header">
    <h1>🎹 Sound to Hit</h1>
    <p>Ham sesten HIT bir sarkiya - Transform your raw sounds into professional music</p>
</div>
""", unsafe_allow_html=True)

# Initialize session state
if 'raw_audio_path' not in st.session_state:
    st.session_state.raw_audio_path = None
if 'detected_notes' not in st.session_state:
    st.session_state.detected_notes = None
if 'detected_rhythm' not in st.session_state:
    st.session_state.detected_rhythm = None
if 'processed_audio' not in st.session_state:
    st.session_state.processed_audio = None
if 'effect_chain' not in st.session_state:
    st.session_state.effect_chain = []

# Check GPU availability
try:
    from modules.colab.colab_bridge import ColabBridge
    bridge = ColabBridge()
    gpu_available = bridge.is_available()
except:
    gpu_available = False
    bridge = None

# Status bar
col1, col2, col3 = st.columns([1, 1, 2])
with col1:
    if gpu_available:
        st.success("🟢 GPU Ready (Modal)")
    else:
        st.warning("🟡 CPU Mode")
with col2:
    if st.button("🔄 Refresh"):
        st.rerun()

st.divider()

# Main tabs
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📁 1. Ses Yukle",
    "🎼 2. Analiz",
    "🎸 3. Enstruman",
    "🎛️ 4. Efektler",
    "💾 5. Export"
])

# ==================== TAB 1: SES YUKLE ====================
with tab1:
    st.header("📁 Ham Ses Yukle")
    st.markdown("*Beatbox, mirilti, ritim - ne olursa olsun yukleyin!*")

    col1, col2 = st.columns(2)

    with col1:
        uploaded_file = st.file_uploader(
            "Ses Dosyasi Secin",
            type=['mp3', 'wav', 'ogg', 'm4a', 'flac'],
            help="Desteklenen: MP3, WAV, OGG, M4A, FLAC"
        )

        if uploaded_file:
            # Save to temp
            temp_dir = tempfile.mkdtemp()
            temp_path = os.path.join(temp_dir, uploaded_file.name)
            with open(temp_path, 'wb') as f:
                f.write(uploaded_file.read())

            st.session_state.raw_audio_path = temp_path
            st.success(f"✅ Yuklendi: {uploaded_file.name}")
            st.audio(temp_path)

            # File info
            file_size = os.path.getsize(temp_path) / (1024 * 1024)
            st.info(f"📊 Boyut: {file_size:.2f} MB")

    with col2:
        st.subheader("🎤 Ornek Sesler")
        st.markdown("""
        **Desteklenen girdi turleri:**
        - 🥁 Beatbox (agiz davulu)
        - 🎵 Mirilti (humming)
        - 🥄 Ritim (kasik, bardak vb.)
        - 🎸 Ham enstruman kaydi
        - 🎤 Vokal
        """)

        st.subheader("📋 Mevcut Dosya")
        if st.session_state.raw_audio_path:
            st.write(f"**Dosya:** {os.path.basename(st.session_state.raw_audio_path)}")
            if st.button("❌ Dosyayi Kaldir"):
                st.session_state.raw_audio_path = None
                st.session_state.detected_notes = None
                st.session_state.detected_rhythm = None
                st.rerun()
        else:
            st.write("Henuz dosya yuklenmedi")

# ==================== TAB 2: ANALİZ ====================
with tab2:
    st.header("🎼 Ses Analizi")

    if not st.session_state.raw_audio_path:
        st.warning("⚠️ Once bir ses dosyasi yukleyin")
    else:
        st.audio(st.session_state.raw_audio_path)

        col1, col2 = st.columns(2)

        with col1:
            st.subheader("⚙️ Analiz Ayarlari")
            analysis_type = st.selectbox(
                "Analiz Turu",
                ["Melodi + Ritim", "Sadece Melodi", "Sadece Ritim"]
            )
            onset_threshold = st.slider("Onset Hassasiyeti", 0.1, 1.0, 0.5)

        with col2:
            st.subheader("🎯 Beklenen Icerik")
            content_type = st.selectbox(
                "Ses Turu",
                ["Otomatik", "Beatbox", "Mirilti/Vokal", "Ritim Sesi", "Enstruman"]
            )

        if st.button("🔍 Analiz Et", type="primary", use_container_width=True):
            with st.spinner("Ses analiz ediliyor..."):
                try:
                    # Use scipy-based analysis to avoid numba DLL issues on Windows
                    from scipy.io import wavfile
                    from scipy import signal
                    import soundfile as sf
                    from pydub import AudioSegment

                    audio_path = st.session_state.raw_audio_path
                    file_ext = os.path.splitext(audio_path)[1].lower()

                    # Convert non-WAV formats to WAV first (soundfile doesn't support M4A/MP3 well)
                    if file_ext in ['.m4a', '.mp3', '.ogg', '.flac', '.aac']:
                        try:
                            # Use pydub to convert to WAV
                            audio_segment = AudioSegment.from_file(audio_path)
                            temp_wav = os.path.join(tempfile.mkdtemp(), "temp_audio.wav")
                            audio_segment.export(temp_wav, format="wav")
                            audio_path = temp_wav
                        except Exception as conv_err:
                            st.error(f"Format donusturme hatasi: {conv_err}")
                            st.info("Lutfen WAV formatinda dosya yukleyin veya ffmpeg'in yuklu oldugundan emin olun.")
                            raise

                    # Load audio with soundfile (no numba dependency)
                    y, sr = sf.read(audio_path)

                    # Convert to mono if stereo
                    if len(y.shape) > 1:
                        y = np.mean(y, axis=1)

                    # Resample to 22050 if needed
                    if sr != 22050:
                        num_samples = int(len(y) * 22050 / sr)
                        y = signal.resample(y, num_samples)
                        sr = 22050

                    # Ensure float32
                    y = y.astype(np.float32)

                    # === TEMPO DETECTION (Autocorrelation method) ===
                    # Calculate envelope
                    envelope = np.abs(y)
                    # Smooth envelope
                    window_size = int(sr * 0.01)  # 10ms window
                    envelope = np.convolve(envelope, np.ones(window_size)/window_size, mode='same')

                    # Autocorrelation for tempo
                    min_bpm, max_bpm = 60, 200
                    min_lag = int(60 * sr / max_bpm)
                    max_lag = int(60 * sr / min_bpm)

                    # Use only first 10 seconds for tempo detection
                    segment = envelope[:min(len(envelope), sr * 10)]
                    correlation = np.correlate(segment, segment, mode='full')
                    correlation = correlation[len(correlation)//2:]

                    # Find peak in valid range
                    valid_corr = correlation[min_lag:max_lag]
                    if len(valid_corr) > 0:
                        peak_lag = np.argmax(valid_corr) + min_lag
                        tempo_value = 60 * sr / peak_lag
                        tempo_value = max(60, min(200, tempo_value))  # Clamp to valid range
                    else:
                        tempo_value = 120.0  # Default

                    # === ONSET DETECTION (Energy-based) ===
                    # Calculate spectral flux
                    hop_length = 512
                    n_fft = 2048

                    # Simple STFT
                    num_frames = (len(y) - n_fft) // hop_length + 1
                    onset_env = np.zeros(num_frames)

                    for i in range(num_frames):
                        start = i * hop_length
                        frame = y[start:start + n_fft]
                        if len(frame) < n_fft:
                            frame = np.pad(frame, (0, n_fft - len(frame)))
                        spectrum = np.abs(np.fft.rfft(frame * np.hanning(n_fft)))
                        onset_env[i] = np.sum(spectrum)

                    # Normalize
                    onset_env = (onset_env - np.min(onset_env)) / (np.max(onset_env) - np.min(onset_env) + 1e-6)

                    # Find peaks
                    threshold = onset_threshold * np.mean(onset_env)
                    peaks, _ = signal.find_peaks(onset_env, height=threshold, distance=5)
                    onset_times = (peaks * hop_length / sr).tolist()

                    # === PITCH DETECTION (FFT peak method) ===
                    pitches = []
                    freqs = np.fft.rfftfreq(n_fft, 1/sr)

                    # MIDI note names
                    note_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

                    def midi_to_note(midi):
                        octave = (midi // 12) - 1
                        note = note_names[midi % 12]
                        return f"{note}{octave}"

                    for i in range(0, num_frames, 10):  # Sample every 10 frames
                        start = i * hop_length
                        frame = y[start:start + n_fft]
                        if len(frame) < n_fft:
                            continue
                        spectrum = np.abs(np.fft.rfft(frame * np.hanning(n_fft)))
                        peak_idx = np.argmax(spectrum)
                        if spectrum[peak_idx] > 0.01:
                            freq = freqs[peak_idx]
                            if 80 < freq < 2000:  # Valid pitch range
                                # Convert to MIDI note
                                midi_note = int(12 * np.log2(freq / 440) + 69)
                                time = i * hop_length / sr
                                pitches.append({
                                    'time': float(time),
                                    'freq': float(freq),
                                    'midi': midi_note,
                                    'note': midi_to_note(midi_note)
                                })

                    # Store results
                    st.session_state.detected_rhythm = {
                        'tempo': float(tempo_value),
                        'beats': [],
                        'onsets': onset_times[:200],  # Limit onsets
                        'duration': float(len(y) / sr)
                    }
                    st.session_state.detected_notes = pitches[:100]  # Limit to 100 notes

                    st.success(f"Analiz tamamlandi! Tempo: {tempo_value:.0f} BPM")

                except Exception as e:
                    st.error(f"Analiz hatasi: {e}")

        # Show results
        if st.session_state.detected_rhythm:
            st.divider()
            st.subheader("📊 Analiz Sonuclari")

            rhythm = st.session_state.detected_rhythm
            notes = st.session_state.detected_notes or []

            # Metrics
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("⏱️ Tempo", f"{rhythm['tempo']:.0f} BPM")
            with col2:
                st.metric("🎵 Notalar", len(notes))
            with col3:
                st.metric("🥁 Vuruslar", len(rhythm['onsets']))
            with col4:
                st.metric("⏰ Sure", f"{rhythm['duration']:.1f}s")

            # Piano Roll visualization
            st.subheader("🎹 Piano Roll")

            if notes:
                import plotly.graph_objects as go

                # Create piano roll
                fig = go.Figure()

                # Add notes as rectangles
                for note in notes:
                    midi = note['midi']
                    time = note['time']
                    fig.add_trace(go.Scatter(
                        x=[time, time + 0.1, time + 0.1, time, time],
                        y=[midi, midi, midi + 0.8, midi + 0.8, midi],
                        fill='toself',
                        fillcolor='rgba(102, 126, 234, 0.7)',
                        line=dict(color='rgba(102, 126, 234, 1)', width=1),
                        name=note['note'],
                        hovertemplate=f"Nota: {note['note']}<br>Zaman: {time:.2f}s<br>MIDI: {midi}"
                    ))

                # Add onset markers
                for onset in rhythm['onsets'][:50]:  # Limit markers
                    fig.add_vline(x=onset, line_width=1, line_dash="dash", line_color="red", opacity=0.3)

                fig.update_layout(
                    title="Tespit Edilen Notalar ve Ritim",
                    xaxis_title="Zaman (saniye)",
                    yaxis_title="MIDI Nota",
                    showlegend=False,
                    height=400,
                    template="plotly_dark"
                )

                st.plotly_chart(fig, use_container_width=True)

                # Note list
                with st.expander("📋 Tespit Edilen Notalar"):
                    note_names = [n['note'] for n in notes[:20]]
                    st.write(" ".join([f"`{n}`" for n in note_names]))
            else:
                st.info("Belirgin nota tespit edilemedi. Ritim bazli analiz yapildi.")

# ==================== TAB 3: ENSTRUMAN ====================
with tab3:
    st.header("🎸 Enstruman Donusumu")

    if not st.session_state.detected_rhythm:
        st.warning("⚠️ Once ses analizini yapin")
    else:
        col1, col2 = st.columns([1, 1])

        with col1:
            st.subheader("🥁 Drum Kit Secimi")
            drum_kit = st.selectbox(
                "Kit",
                ["808 (Hip-Hop/Trap)", "909 (House/Techno)", "Acoustic (Pop/Rock)", "Electronic (EDM)"],
                help="Beatbox sesleriniz bu kit ile degistirilecek"
            )

            st.markdown("""
            **Kit Ozellikleri:**
            - **808:** Deep bass, punchy kick - Trap/Hip-Hop
            - **909:** Punchy kick, snappy snare - House/Techno
            - **Acoustic:** Natural drum sounds - Pop/Rock
            - **Electronic:** Modern EDM sounds - Club/Dance
            """)

        with col2:
            st.subheader("🎹 Melodic Enstruman")
            melodic_instrument = st.selectbox(
                "Enstruman",
                ["Piano", "Synth Lead", "Bass (Synth)", "Strings", "Guitar (Electric)", "Pad"]
            )

            st.markdown("""
            **Enstruman Ozellikleri:**
            - **Piano:** Akustik piyano tonu
            - **Synth Lead:** Elektronik lead synth
            - **Bass:** Sub bass / synth bass
            - **Strings:** Orchestral strings
            - **Guitar:** Electric guitar tone
            - **Pad:** Atmospheric synth pad
            """)

        st.divider()

        if st.button("🎸 Donustur", type="primary", use_container_width=True):
            with st.spinner("Enstruman donusumu yapiliyor - beat'ler tespit ediliyor ve drum sentezleniyor..."):
                try:
                    # Use drum synthesis with onset detection
                    from modules.audio_effects import AudioEffectsProcessor

                    processor = AudioEffectsProcessor()
                    audio, sr = processor.load_audio(st.session_state.raw_audio_path)

                    # Get kit name
                    kit_name = drum_kit.split(" ")[0].lower()

                    # REAL drum transformation: detect beats and replace with synth drums
                    st.info(f"🔍 Beat'ler tespit ediliyor...")
                    audio = processor.transform_to_drumkit(audio, sr, kit=kit_name)

                    # Apply additional processing based on kit for final polish
                    if kit_name == "808":
                        audio = processor.apply_bass_boost(audio, sr, gain=4)
                    elif kit_name == "909":
                        audio = processor.apply_compressor(audio, sr, threshold=-15, ratio=4)
                    elif kit_name == "acoustic":
                        audio = processor.apply_reverb(audio, sr, room_size=0.3)
                    else:  # electronic
                        audio = processor.apply_compressor(audio, sr, threshold=-12, ratio=3)

                    # Save processed
                    output_path = os.path.join(tempfile.mkdtemp(), "transformed.wav")
                    processor.save_audio(audio, sr, output_path)
                    st.session_state.processed_audio = output_path

                    st.success("✅ Donusum tamamlandi! Sesdeki beat'ler gercek drum sesleriyle degistirildi.")
                    st.audio(output_path)

                except Exception as e:
                    st.error(f"Donusum hatasi: {e}")
                    import traceback
                    st.code(traceback.format_exc())

# ==================== TAB 4: EFEKTLER ====================
with tab4:
    st.header("🎛️ Elektronik Efektler")

    # Get audio source
    audio_source = st.session_state.processed_audio or st.session_state.raw_audio_path

    if not audio_source:
        st.warning("⚠️ Once bir ses yukleyin")
    else:
        st.audio(audio_source)

        # Effect presets
        st.subheader("🎨 Efekt Presetleri")
        preset_cols = st.columns(7)

        presets = ['club', 'lofi', '8bit', 'ambient', 'trap', 'rock', 'dreamy']
        preset_labels = ['🎉 Club', '📻 Lo-Fi', '🎮 8-Bit', '🌙 Ambient', '🔥 Trap', '🎸 Rock', '✨ Dreamy']

        selected_preset = None
        for i, (preset, label) in enumerate(zip(presets, preset_labels)):
            with preset_cols[i]:
                if st.button(label, use_container_width=True, key=f"preset_{preset}"):
                    selected_preset = preset

        if selected_preset:
            with st.spinner(f"{selected_preset.upper()} preset uygulanıyor..."):
                try:
                    from modules.audio_effects import AudioEffectsProcessor

                    processor = AudioEffectsProcessor()
                    audio, sr = processor.load_audio(audio_source)
                    audio = processor.apply_preset(audio, sr, selected_preset)

                    output_path = os.path.join(tempfile.mkdtemp(), f"preset_{selected_preset}.wav")
                    processor.save_audio(audio, sr, output_path)
                    st.session_state.processed_audio = output_path

                    st.success(f"✅ {selected_preset.upper()} preset uygulandi!")
                    st.audio(output_path)
                except Exception as e:
                    st.error(f"Preset hatasi: {e}")

        st.divider()

        # Manual effects
        st.subheader("🔧 Manuel Efekt Kontrolu")

        col1, col2, col3 = st.columns(3)

        with col1:
            st.markdown("**🔊 Distortion**")
            distortion_drive = st.slider("Drive", 0.0, 1.0, 0.0, key="dist_drive")
            bitcrush_bits = st.slider("Bitcrusher", 4, 16, 16, key="bit_bits")

        with col2:
            st.markdown("**🎚️ Filter**")
            lowpass_cutoff = st.slider("Low-pass (Hz)", 500, 20000, 20000, key="lp_cutoff")
            highpass_cutoff = st.slider("High-pass (Hz)", 20, 2000, 20, key="hp_cutoff")
            bass_boost = st.slider("Bass Boost (dB)", 0, 12, 0, key="bass_db")

        with col3:
            st.markdown("**🌊 Spatial**")
            reverb_size = st.slider("Reverb", 0.0, 1.0, 0.0, key="rev_size")
            delay_ms = st.slider("Delay (ms)", 0, 500, 0, key="delay_ms")

        # Speed/Pitch
        st.subheader("⏩ Hiz & Pitch")
        col1, col2 = st.columns(2)
        with col1:
            speed = st.slider("Hiz", 0.5, 2.0, 1.0, 0.1, key="speed")
        with col2:
            pitch_shift = st.slider("Pitch (yari ton)", -12, 12, 0, key="pitch")

        if st.button("🎛️ Efektleri Uygula", type="primary", use_container_width=True):
            with st.spinner("Efektler uygulanıyor..."):
                try:
                    from modules.audio_effects import AudioEffectsProcessor

                    processor = AudioEffectsProcessor()
                    audio, sr = processor.load_audio(audio_source)

                    # Apply effects based on sliders
                    if distortion_drive > 0:
                        audio = processor.apply_distortion(audio, sr, drive=distortion_drive)

                    if bitcrush_bits < 16:
                        audio = processor.apply_bitcrusher(audio, sr, bits=bitcrush_bits)

                    if lowpass_cutoff < 20000:
                        audio = processor.apply_lowpass(audio, sr, cutoff=lowpass_cutoff)

                    if highpass_cutoff > 20:
                        audio = processor.apply_highpass(audio, sr, cutoff=highpass_cutoff)

                    if bass_boost > 0:
                        audio = processor.apply_bass_boost(audio, sr, gain=bass_boost)

                    if reverb_size > 0:
                        audio = processor.apply_reverb(audio, sr, room_size=reverb_size)

                    if delay_ms > 0:
                        audio = processor.apply_delay(audio, sr, delay_ms=delay_ms)

                    if speed != 1.0:
                        audio, sr = processor.apply_speed_change(audio, sr, speed=speed)

                    if pitch_shift != 0:
                        audio = processor.apply_pitch_shift(audio, sr, semitones=pitch_shift)

                    output_path = os.path.join(tempfile.mkdtemp(), "effects_applied.wav")
                    processor.save_audio(audio, sr, output_path)
                    st.session_state.processed_audio = output_path

                    st.success("✅ Efektler uygulandi!")
                    st.audio(output_path)

                except Exception as e:
                    st.error(f"Efekt hatasi: {e}")

# ==================== TAB 5: EXPORT ====================
with tab5:
    st.header("💾 Export")

    final_audio = st.session_state.processed_audio or st.session_state.raw_audio_path

    if not final_audio:
        st.warning("⚠️ Export icin ses dosyasi yok")
    else:
        st.subheader("🎵 Son Hali")
        st.audio(final_audio)

        col1, col2 = st.columns(2)

        with col1:
            st.subheader("📥 Indir")
            export_format = st.selectbox("Format", ["WAV", "MP3"])

            if st.button("💾 Dosyayi Indir", type="primary"):
                with open(final_audio, 'rb') as f:
                    audio_bytes = f.read()

                file_ext = export_format.lower()
                st.download_button(
                    label=f"📥 {export_format} Indir",
                    data=audio_bytes,
                    file_name=f"sound_to_hit_output.{file_ext}",
                    mime=f"audio/{file_ext}"
                )

        with col2:
            st.subheader("📊 Dosya Bilgisi")
            if os.path.exists(final_audio):
                file_size = os.path.getsize(final_audio) / (1024 * 1024)
                st.write(f"**Boyut:** {file_size:.2f} MB")
                st.write(f"**Konum:** {final_audio}")

        st.divider()

        st.subheader("🔄 Yeni Basla")
        if st.button("🗑️ Tum Verileri Temizle"):
            st.session_state.raw_audio_path = None
            st.session_state.detected_notes = None
            st.session_state.detected_rhythm = None
            st.session_state.processed_audio = None
            st.session_state.effect_chain = []
            st.success("Temizlendi! Yeni bir sesle baslayabilirsiniz.")
            st.rerun()

# Footer
st.divider()
st.markdown("""
<div style="text-align: center; color: #888; font-size: 0.9rem;">
    <p>🎹 Sound to Hit - VIDEOCU Studio</p>
    <p>Ham sesten HIT bir sarkiya | Transform raw sounds into professional music</p>
</div>
""", unsafe_allow_html=True)
