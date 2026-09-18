"""
Modal MusicGen Simple Test
Windows encoding sorunu olmadan test
"""
import modal

# Modal app'e baglan
app = modal.App.lookup("videocu-music-studio")

# generate_music fonksiyonunu al
generate_music = modal.Function.from_name("videocu-music-studio", "generate_music")

print("MusicGen testi basliyor...")
print("Prompt: modern hip hop beat with heavy 808 bass")
print("Sure: 10 saniye")
print("Lutfen bekleyin...")

# Muzik uret
audio_bytes = generate_music.remote(
    prompt="modern hip hop beat with heavy 808 bass, trap hi-hats",
    duration=10
)

print(f"Uretilen audio: {len(audio_bytes)} bytes")

# Kaydet
with open("modal_test_output.wav", "wb") as f:
    f.write(audio_bytes)

print("Kaydedildi: modal_test_output.wav")
print("TEST BASARILI!")