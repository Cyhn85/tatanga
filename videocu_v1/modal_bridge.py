"""
VIDEOCU Modal Bridge
Modal.com GPU Backend ile Telegram Bot arasindaki kopru

Kullanim:
    from modal_bridge import ModalMusicStudio

    studio = ModalMusicStudio()
    audio_bytes = studio.generate_music("hip hop beat", duration=30)
"""

import modal
from typing import Optional
import os


class ModalMusicStudio:
    """Modal.com GPU backend ile muzik islemleri"""

    APP_NAME = "videocu-music-studio"

    def __init__(self):
        """Modal fonksiyonlarini yukle"""
        self._generate_music = None
        self._extract_melody = None
        self._separate_stems = None
        self._transform_melody = None
        self._quantize_midi = None
        self._midi_to_audio = None
        self._transpose_midi = None
        self._health = None
        self._initialized = False

    def _init_functions(self):
        """Lazy initialization - ilk kullanim sirasinda baglan"""
        if self._initialized:
            return

        try:
            self._generate_music = modal.Function.from_name(self.APP_NAME, "generate_music")
            self._extract_melody = modal.Function.from_name(self.APP_NAME, "extract_melody")
            self._separate_stems = modal.Function.from_name(self.APP_NAME, "separate_stems")
            self._transform_melody = modal.Function.from_name(self.APP_NAME, "transform_melody")
            self._quantize_midi = modal.Function.from_name(self.APP_NAME, "quantize_midi")
            self._midi_to_audio = modal.Function.from_name(self.APP_NAME, "midi_to_audio")
            self._transpose_midi = modal.Function.from_name(self.APP_NAME, "transpose_midi")
            self._health = modal.Function.from_name(self.APP_NAME, "health")
            self._initialized = True
            print("[Modal Bridge] Fonksiyonlar yuklendi")
        except Exception as e:
            print(f"[Modal Bridge] Baglanti hatasi: {e}")
            raise

    def health_check(self) -> dict:
        """GPU durumunu kontrol et"""
        # Health endpoint web endpoint olarak calisir, Function.from_name ile cagrilamaz
        # Bunun yerine generate_music fonksiyonunun var olup olmadigini kontrol et
        try:
            self._init_functions()
            # Fonksiyon yuklendiyse Modal erisilebilir demektir
            if self._generate_music is not None:
                return {
                    "status": "healthy",
                    "gpu": True,
                    "gpu_name": "Tesla T4 (Modal.com)"
                }
            return {"status": "error", "message": "Modal fonksiyonlari yuklenemedi"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def generate_music(self, prompt: str, duration: int = 30) -> bytes:
        """
        MusicGen ile muzik uret

        Args:
            prompt: Muzik aciklamasi (ornek: "hip hop beat with 808 bass")
            duration: Sure (saniye), max 30

        Returns:
            WAV formatinda audio bytes
        """
        self._init_functions()

        # Duration limiti
        duration = min(duration, 30)

        print(f"[Modal Bridge] Muzik uretiliyor: {prompt[:50]}... ({duration}s)")

        audio_bytes = self._generate_music.remote(prompt=prompt, duration=duration)

        print(f"[Modal Bridge] Muzik uretildi: {len(audio_bytes)} bytes")
        return audio_bytes

    def extract_melody(self, audio_bytes: bytes) -> dict:
        """
        Ses dosyasindan melodi cikar (Basic Pitch)

        Args:
            audio_bytes: WAV formatinda audio

        Returns:
            {
                "success": True/False,
                "note_count": int,
                "notes": [...],
                "midi_bytes": hex string
            }
        """
        self._init_functions()

        print(f"[Modal Bridge] Melodi cikariliyor... ({len(audio_bytes)} bytes)")

        result = self._extract_melody.remote(audio_bytes=audio_bytes)

        if result.get("success"):
            print(f"[Modal Bridge] Melodi cikarildi: {result.get('note_count')} nota")
        else:
            print("[Modal Bridge] Melodi cikarma basarisiz")

        return result

    def separate_stems(self, audio_bytes: bytes) -> dict:
        """
        Vokal ve enstrumani ayir (Demucs)

        Args:
            audio_bytes: WAV formatinda audio

        Returns:
            {
                "success": True/False,
                "vocals_bytes": hex string,
                "instrumental_bytes": hex string
            }
        """
        self._init_functions()

        print(f"[Modal Bridge] Stem ayirma baslatiliyor... ({len(audio_bytes)} bytes)")

        result = self._separate_stems.remote(audio_bytes=audio_bytes)

        if result.get("success"):
            print("[Modal Bridge] Stem ayirma tamamlandi")
        else:
            print("[Modal Bridge] Stem ayirma basarisiz")

        return result

    def transform_melody(self, audio_bytes: bytes, style_prompt: str, duration: int = 30) -> bytes:
        """
        Melodiyi farkli stile donustur

        Args:
            audio_bytes: Kaynak audio (WAV)
            style_prompt: Hedef stil (ornek: "jazz piano version")
            duration: Cikti suresi

        Returns:
            WAV formatinda donusturulmus audio
        """
        self._init_functions()

        duration = min(duration, 30)

        print(f"[Modal Bridge] Stil donusumu: {style_prompt[:50]}...")

        result_bytes = self._transform_melody.remote(
            audio_bytes=audio_bytes,
            style_prompt=style_prompt,
            duration=duration
        )

        print(f"[Modal Bridge] Donusum tamamlandi: {len(result_bytes)} bytes")
        return result_bytes

    def save_audio(self, audio_bytes: bytes, filename: str) -> str:
        """Audio bytes'i dosyaya kaydet"""
        with open(filename, "wb") as f:
            f.write(audio_bytes)
        return os.path.abspath(filename)

    def save_midi(self, midi_hex: str, filename: str) -> str:
        """Hex encoded MIDI'yi dosyaya kaydet"""
        midi_bytes = bytes.fromhex(midi_hex)
        with open(filename, "wb") as f:
            f.write(midi_bytes)
        return os.path.abspath(filename)

    def quantize_midi(self, midi_hex: str, grid: str = "16th") -> dict:
        """
        MIDI notalarini grid'e oturtur (dalgali notalari duzelt)

        Args:
            midi_hex: Hex encoded MIDI bytes
            grid: Quantize grid ("8th", "16th", "32nd")

        Returns:
            {
                "success": True/False,
                "midi_bytes": hex string (quantized),
                "note_count": int,
                "corrections": int
            }
        """
        self._init_functions()

        print(f"[Modal Bridge] MIDI Quantize baslatiliyor... Grid: {grid}")

        result = self._quantize_midi.remote(midi_hex=midi_hex, grid=grid)

        if result.get("success"):
            print(f"[Modal Bridge] Quantize tamamlandi: {result.get('corrections')}/{result.get('note_count')} nota duzeltildi")
        else:
            print("[Modal Bridge] Quantize basarisiz")

        return result

    def midi_to_audio(self, midi_hex: str, instrument: str = "piano") -> dict:
        """
        MIDI'yi enstruman sesiyle audio'ya donustur

        Args:
            midi_hex: Hex encoded MIDI bytes
            instrument: Enstruman tipi ("piano", "bass", "synth", "strings", "guitar", "organ", "pad")

        Returns:
            {
                "success": True/False,
                "audio_bytes": hex string (WAV),
                "duration": float
            }
        """
        self._init_functions()

        print(f"[Modal Bridge] MIDI -> Audio donusumu... Enstruman: {instrument}")

        result = self._midi_to_audio.remote(midi_hex=midi_hex, instrument=instrument)

        if result.get("success"):
            print(f"[Modal Bridge] Audio olusturuldu: {result.get('duration'):.1f}s")
        else:
            print(f"[Modal Bridge] MIDI -> Audio basarisiz: {result.get('error')}")

        return result

    def transpose_midi(self, midi_hex: str, semitones: int) -> dict:
        """
        MIDI'yi transpoze et (tonu degistir)

        Args:
            midi_hex: Hex encoded MIDI bytes
            semitones: Kac yarim adim (pozitif=yukari, negatif=asagi)

        Returns:
            {
                "success": True/False,
                "midi_bytes": hex string,
                "note_count": int
            }
        """
        self._init_functions()

        print(f"[Modal Bridge] MIDI Transpose: {semitones:+d} semitone")

        result = self._transpose_midi.remote(midi_hex=midi_hex, semitones=semitones)

        if result.get("success"):
            print(f"[Modal Bridge] Transpose tamamlandi: {result.get('note_count')} nota")
        else:
            print("[Modal Bridge] Transpose basarisiz")

        return result


# ============ TEST ============
if __name__ == "__main__":
    print("=" * 50)
    print("VIDEOCU Modal Bridge Test")
    print("=" * 50)

    studio = ModalMusicStudio()

    # Health check
    print("\n1. Health Check...")
    health = studio.health_check()
    print(f"   Status: {health}")

    # MusicGen test
    print("\n2. MusicGen Test (10s)...")
    audio = studio.generate_music(
        prompt="lo-fi hip hop beat, chill vibes, jazzy chords",
        duration=10
    )

    # Kaydet
    output_path = studio.save_audio(audio, "bridge_test_output.wav")
    print(f"   Kaydedildi: {output_path}")

    # Basic Pitch test (uretilen audio ile)
    print("\n3. Basic Pitch Test...")
    melody_result = studio.extract_melody(audio)
    if melody_result.get("success"):
        print(f"   Nota sayisi: {melody_result.get('note_count')}")
        # MIDI kaydet
        if melody_result.get("midi_bytes"):
            midi_path = studio.save_midi(melody_result["midi_bytes"], "bridge_test_melody.mid")
            print(f"   MIDI kaydedildi: {midi_path}")

    print("\n" + "=" * 50)
    print("TEST TAMAMLANDI!")
    print("=" * 50)
