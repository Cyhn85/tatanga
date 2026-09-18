"""
Colab GPU Backend Test Script
Dogrudan konsoldan ColabBridge fonksiyonlarini test eder
"""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load environment
from dotenv import load_dotenv
load_dotenv()

from modules.colab.colab_bridge import ColabBridge, STYLE_PROMPTS

def test_connection():
    """Test Gradio connection"""
    print("\n" + "="*50)
    print("1. COLAB BAGLANTI TESTI")
    print("="*50)

    bridge = ColabBridge()
    print(f"Gradio URL: {bridge.gradio_url}")

    if bridge.is_available():
        print("Colab baglanitisi BASARILI!")
        return True
    else:
        print("HATA: Colab sunucusu erisilemez!")
        return False

def test_generate_music():
    """Test MusicGen - prompt'tan muzik uret"""
    print("\n" + "="*50)
    print("2. MUZIK URETME TESTI (MusicGen)")
    print("="*50)

    bridge = ColabBridge()

    # Hip-hop beat uret
    prompt = "modern hip hop beat with heavy 808 bass, trap hi-hats"
    duration = 10  # 10 saniye

    print(f"Prompt: {prompt}")
    print(f"Sure: {duration} saniye")
    print("Uretiliyor...")

    result = bridge.generate_music(prompt, duration)

    if result.get("success"):
        audio_path = result.get("audio_path")
        print(f"BASARILI! Cikti: {audio_path}")
        return audio_path
    else:
        print(f"HATA: {result.get('error')}")
        return None

def test_extract_melody(audio_path):
    """Test Basic Pitch - melodi cikar"""
    print("\n" + "="*50)
    print("3. MELODI CIKARMA TESTI (Basic Pitch)")
    print("="*50)

    if not audio_path:
        print("Test edilecek ses dosyasi yok!")
        return None

    bridge = ColabBridge()
    print(f"Girdi: {audio_path}")
    print("Melodi cikariliyor...")

    result = bridge.extract_melody(audio_path)

    if result.get("success"):
        print(f"BASARILI!")
        print(f"  Nota sayisi: {result.get('note_count')}")
        print(f"  Anahtar: {result.get('key')}")
        print(f"  Tempo: {result.get('tempo')} BPM")
        print(f"  Sure: {result.get('duration')}")
        return result
    else:
        print(f"HATA: {result.get('error')}")
        return None

def test_transform_melody(audio_path):
    """Test MusicGen melody-conditioned - stil donustur"""
    print("\n" + "="*50)
    print("4. STIL DONUSTURME TESTI (Transform)")
    print("="*50)

    if not audio_path:
        print("Test edilecek ses dosyasi yok!")
        return None

    bridge = ColabBridge()

    style = "catchy pop melody with bright synths, upbeat drums"
    duration = 15

    print(f"Girdi: {audio_path}")
    print(f"Hedef stil: {style}")
    print(f"Sure: {duration} saniye")
    print("Donusturuluyor...")

    result = bridge.transform_melody(audio_path, style, duration)

    if result.get("success"):
        print(f"BASARILI! Cikti: {result.get('audio_path')}")
        return result.get("audio_path")
    else:
        print(f"HATA: {result.get('error')}")
        return None

def test_separate_stems(audio_path):
    """Test Demucs - vokal/enstruman ayir"""
    print("\n" + "="*50)
    print("5. STEM AYIRMA TESTI (Demucs)")
    print("="*50)

    if not audio_path:
        print("Test edilecek ses dosyasi yok!")
        return None

    bridge = ColabBridge()
    print(f"Girdi: {audio_path}")
    print("Stem'ler ayriliyor...")

    result = bridge.separate_stems(audio_path)

    if result.get("success"):
        stems = result.get("stems", {})
        print(f"BASARILI!")
        print(f"  Vokal: {stems.get('vocals')}")
        print(f"  Enstrumental: {stems.get('no_vocals')}")
        return stems
    else:
        print(f"HATA: {result.get('error')}")
        return None

def run_all_tests(input_audio=None):
    """Tum testleri calistir"""
    print("\n" + "="*60)
    print(" VIDEOCU COLAB GPU TEST SUITE")
    print("="*60)

    # 1. Baglanti testi
    if not test_connection():
        print("\n[X] Baglanti basarisiz, testler iptal edildi!")
        return

    # 2. Muzik uretme testi
    generated = test_generate_music()

    # 3. Melodi cikarma testi
    test_audio = input_audio or generated
    if test_audio:
        melody_result = test_extract_melody(test_audio)

    # 4. Stil donusturme testi
    if test_audio:
        transformed = test_transform_melody(test_audio)

    # 5. Stem ayirma testi
    if test_audio:
        stems = test_separate_stems(test_audio)

    print("\n" + "="*60)
    print(" TESTLER TAMAMLANDI")
    print("="*60)

if __name__ == "__main__":
    # Eger arguman verilmisse, o dosyayi kullan
    if len(sys.argv) > 1:
        audio_file = sys.argv[1]
        if os.path.exists(audio_file):
            print(f"Kullanici ses dosyasi: {audio_file}")
            run_all_tests(audio_file)
        else:
            print(f"Dosya bulunamadi: {audio_file}")
    else:
        # Sadece baglanti ve muzik uretme testi
        run_all_tests()
