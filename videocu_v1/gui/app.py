"""
VIDEOCU Studio - Ana Sayfa
Streamlit Multi-Page Application
"""

import streamlit as st
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

st.set_page_config(
    page_title="VIDEOCU Studio",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 3rem;
        font-weight: bold;
        background: linear-gradient(90deg, #FF6B6B, #4ECDC4, #45B7D1);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        padding: 1rem;
    }
    .feature-card {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        border-radius: 15px;
        padding: 2rem;
        margin: 1rem 0;
        border: 1px solid #0f3460;
    }
    .stat-box {
        background: #0f3460;
        border-radius: 10px;
        padding: 1rem;
        text-align: center;
    }
    .stButton>button {
        width: 100%;
        border-radius: 10px;
        height: 3rem;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# Header
st.markdown('<h1 class="main-header">🎬 VIDEOCU Studio</h1>', unsafe_allow_html=True)
st.markdown('<p style="text-align: center; color: #888; font-size: 1.2rem;">AI-Powered Video & Music Production Platform</p>', unsafe_allow_html=True)

st.divider()

# Main content
col1, col2 = st.columns(2)

with col1:
    st.markdown("### 🎥 Video Prodüksiyon")
    st.markdown("""
    **Özellikler:**
    - 📊 Trend Analizi (Google Trends)
    - 📝 AI Senaryo Yazımı (Gemini)
    - 🖼️ Görsel Bulma/Üretme (Pexels + AI)
    - 🎤 TTS Seslendirme (Edge TTS)
    - 🎬 Otomatik Video Montaj
    - 📱 YouTube Yükleme
    """)
    if st.button("🎥 Video Studio'ya Git", type="primary", use_container_width=True):
        st.switch_page("pages/1_🎥_Video_Studio.py")

with col2:
    st.markdown("### 🎵 Ses Prodüksiyon")
    st.markdown("""
    **Özellikler:**
    - 🎼 Melodi Çıkarma (Basic Pitch)
    - 🎹 MIDI → Audio Dönüşüm
    - 🔀 Stem Ayırma (Vokal/Enstrüman)
    - 🎨 AI Müzik Üretimi (MusicGen)
    - ⚡ MIDI Quantize & Transpose
    - 🎸 Çoklu Enstrüman Desteği
    """)
    if st.button("🎵 Music Studio'ya Git", type="primary", use_container_width=True):
        st.switch_page("pages/2_🎵_Music_Studio.py")

st.divider()

# System Status
st.markdown("### 📊 Sistem Durumu")

col1, col2, col3, col4 = st.columns(4)

# Check GPU status
try:
    from modules.colab.colab_bridge import ColabBridge
    bridge = ColabBridge()
    gpu_status = "✅ Bağlı" if bridge.is_available() else "❌ Bağlı Değil"
    gpu_name = "Tesla T4 (Modal)" if bridge._modal_available else "N/A"
except:
    gpu_status = "❌ Yüklenemedi"
    gpu_name = "N/A"

with col1:
    st.metric("🖥️ GPU Durumu", gpu_status)

with col2:
    st.metric("🎮 GPU Model", gpu_name)

with col3:
    st.metric("🎤 TTS", "Edge TTS")

with col4:
    st.metric("🤖 AI Model", "Gemini 2.5")

# Footer
st.divider()
st.markdown("""
<p style="text-align: center; color: #666; font-size: 0.9rem;">
    VIDEOCU Studio v1.0 | Modal.com GPU Backend | Made with ❤️
</p>
""", unsafe_allow_html=True)
