"""
Test: ColabBridge Modal Integration
Modal.com entegrasyonunun duzgun calistigini test eder
"""

import sys
import os

# videocu_v1 dizinini path'e ekle
sys.path.insert(0, r"c:\Users\cyhnsrgc\Desktop\CSS BOT\videocu_v1")

print("=" * 60)
print("COLAB BRIDGE - MODAL ENTEGRASYONU TEST")
print("=" * 60)

from modules.colab.colab_bridge import ColabBridge

print("\n1. ColabBridge Olusturuluyor...")
bridge = ColabBridge()

print("\n2. GPU Erisilebilirlik Testi...")
available = bridge.is_available()
print(f"   Sonuc: {available}")

if available:
    print("\n3. MusicGen Testi (10 saniye)...")
    print("   Prompt: trap beat with heavy 808 bass")
    print("   Lutfen bekleyin...")

    result = bridge.generate_music(
        prompt="trap beat with heavy 808 bass and dark synths",
        duration=10
    )

    if result.get("success"):
        audio_path = result.get("audio_path")
        print(f"   BASARILI!")
        print(f"   Dosya: {audio_path}")
        if audio_path and os.path.exists(audio_path):
            size = os.path.getsize(audio_path)
            print(f"   Boyut: {size:,} bytes")
    else:
        print(f"   HATA: {result.get('error')}")
else:
    print("   GPU erisimi yok, test atlanıyor")

print("\n" + "=" * 60)
print("TEST TAMAMLANDI")
print("=" * 60)
