"""
Colab Bridge - CPU Server ↔ GPU İletişimi

Bu modül, yerel sunucu ile GPU backend arasındaki iletişimi yönetir.
Üç bağlantı modu desteklenir (öncelik sırasıyla):
1. Modal.com: Serverless GPU (tercih edilir - stabil URL)
2. Gradio API: COLAB_GRADIO_URL
3. Flask API (ngrok): COLAB_API_URL
"""

import os
import base64
import requests
import json
from typing import Optional, Dict, Any
import logging
import tempfile

logger = logging.getLogger(__name__)

# Gradio client lazy import (sunucuda kurulu olmayabilir)
_gradio_client = None

# Modal lazy import
_modal_bridge = None


def get_gradio_client_class():
    """Gradio Client sınıfını lazy import et"""
    global _gradio_client
    if _gradio_client is None:
        try:
            from gradio_client import Client
            _gradio_client = Client
        except ImportError:
            logger.warning("gradio_client kurulu değil: pip install gradio_client")
            _gradio_client = False
    return _gradio_client if _gradio_client else None


def get_modal_bridge():
    """Modal Bridge'i lazy import et"""
    global _modal_bridge
    if _modal_bridge is None:
        try:
            from modal_bridge import ModalMusicStudio
            _modal_bridge = ModalMusicStudio()
            logger.info("Modal Bridge yüklendi")
        except ImportError:
            logger.warning("modal_bridge modülü bulunamadı")
            _modal_bridge = False
        except Exception as e:
            logger.warning(f"Modal Bridge yüklenemedi: {e}")
            _modal_bridge = False
    return _modal_bridge if _modal_bridge else None


class ColabBridge:
    """GPU sunucusuyla iletişim (Modal + Gradio + Flask desteği)"""

    def __init__(self, colab_url: Optional[str] = None, gradio_url: Optional[str] = None):
        """
        Args:
            colab_url: Colab Flask/ngrok URL'i (örn: https://xxx.ngrok.io)
            gradio_url: Colab Gradio URL'i (örn: https://xxx.gradio.live)
        """
        self.colab_url = colab_url or os.getenv("COLAB_API_URL", "")
        self.gradio_url = gradio_url or os.getenv("COLAB_GRADIO_URL", "")
        self.timeout = 300  # 5 dakika (GPU işlemleri uzun sürebilir)
        self._gradio_client_instance = None
        self._modal_checked = False
        self._modal_available = False

    @property
    def modal_bridge(self):
        """Lazy-load Modal bridge"""
        return get_modal_bridge()

    @property
    def gradio_client(self):
        """Lazy-load Gradio client"""
        if self._gradio_client_instance is None and self.gradio_url:
            Client = get_gradio_client_class()
            if Client:
                try:
                    self._gradio_client_instance = Client(self.gradio_url)
                    logger.info(f"Gradio client bağlandı: {self.gradio_url}")
                except Exception as e:
                    logger.error(f"Gradio client hatası: {e}")
        return self._gradio_client_instance

    def _check_modal(self) -> bool:
        """Modal.com erişilebilir mi kontrol et"""
        # Her çağrıda tekrar dene (bağlantı düzelebilir)
        if self.modal_bridge:
            try:
                health = self.modal_bridge.health_check()
                if health.get("status") == "healthy" and health.get("gpu"):
                    if not self._modal_available:
                        logger.info(f"Modal GPU erişilebilir: {health.get('gpu_name', 'Unknown')}")
                    self._modal_available = True
                    self._modal_checked = True
                    return True
            except Exception as e:
                logger.warning(f"Modal health check hatası: {e}")
                self._modal_available = False
        return self._modal_available

    def is_available(self) -> bool:
        """GPU sunucusu erişilebilir mi? (Modal > Gradio > Flask)"""
        # 1. Modal.com (tercih edilir - stabil URL)
        if self._check_modal():
            logger.info("Modal.com GPU erişilebilir")
            return True

        # 2. Gradio dene
        if self.gradio_url:
            try:
                if self.gradio_client:
                    logger.info("Colab Gradio API erişilebilir")
                    return True
            except Exception as e:
                logger.warning(f"Gradio bağlantı hatası: {e}")

        # 3. Flask/ngrok API fallback
        if self.colab_url:
            try:
                response = requests.get(
                    f"{self.colab_url}/health",
                    timeout=10
                )
                data = response.json()
                if data.get("status") == "healthy" and data.get("gpu", False):
                    logger.info("Colab Flask API erişilebilir")
                    return True
            except Exception as e:
                logger.warning(f"Flask API bağlantı hatası: {e}")

        logger.warning("GPU sunucusu erişilemez (Modal bağlantısını kontrol edin)")
        return False

    def _use_modal(self) -> bool:
        """Modal kullanılabilir mi?"""
        return self._check_modal()

    def _use_gradio(self) -> bool:
        """Gradio kullanılabilir mi?"""
        return self.gradio_client is not None

    def extract_melody(self, audio_path: str) -> Dict[str, Any]:
        """
        Ses dosyasından melodi çıkar (Basic Pitch)

        Args:
            audio_path: Ses dosyası yolu

        Returns:
            dict: {
                "success": bool,
                "note_count": int,
                "notes": [...],
                "key": str,
                "tempo": int,
                "midi_base64": str
            }
        """
        # 1. Modal.com kullan (tercih edilir)
        if self._use_modal():
            try:
                logger.info(f"Modal ile melodi çıkarılıyor: {audio_path}")
                with open(audio_path, 'rb') as f:
                    audio_bytes = f.read()
                result = self.modal_bridge.extract_melody(audio_bytes)
                if result.get("success"):
                    # MIDI dosyasını kaydet
                    if result.get("midi_bytes"):
                        midi_dir = os.path.join(tempfile.gettempdir(), "videocu_midi")
                        os.makedirs(midi_dir, exist_ok=True)
                        midi_path = os.path.join(midi_dir, f"melody_{os.path.basename(audio_path)}.mid")
                        self.modal_bridge.save_midi(result["midi_bytes"], midi_path)
                        result["midi_path"] = midi_path
                    return result
                # Modal başarısız olursa devam et
            except Exception as e:
                logger.warning(f"Modal melodi çıkarma hatası: {e}")

        # 2. Gradio API kullan
        if self._use_gradio():
            try:
                logger.info(f"Gradio ile melodi çıkarılıyor: {audio_path}")
                # Gradio predict çağrısı
                result = self.gradio_client.predict(
                    audio_path,
                    api_name="/extract_melody"
                )
                # Gradio tuple döndürür: (plot, json_data)
                if isinstance(result, tuple) and len(result) >= 2:
                    json_data = result[1]
                    return {
                        "success": True,
                        "note_count": json_data.get("nota_sayisi", 0),
                        "key": json_data.get("anahtar", "Unknown"),
                        "tempo": json_data.get("tempo", 120),
                        "duration": json_data.get("sure", "0s"),
                        "midi_path": json_data.get("midi_dosyasi", "")
                    }
                return {"success": True, "result": result}
            except Exception as e:
                logger.error(f"Gradio melodi çıkarma hatası: {e}")
                # Fallback to Flask API
                if not self.colab_url:
                    return {"success": False, "error": str(e)}

        # Flask/ngrok API fallback
        if not self.colab_url:
            return {"success": False, "error": "GPU sunucusu erişilemez (Modal bağlantısını kontrol edin)"}

        try:
            # Ses dosyasını base64'e çevir
            with open(audio_path, 'rb') as f:
                audio_b64 = base64.b64encode(f.read()).decode()

            # API çağrısı
            response = requests.post(
                f"{self.colab_url}/extract-melody",
                json={
                    "audio": audio_b64,
                    "filename": os.path.basename(audio_path)
                },
                timeout=self.timeout
            )

            data = response.json()

            if data.get("success"):
                return {
                    "success": True,
                    **data["result"]
                }
            else:
                return {"success": False, "error": data.get("error", "Bilinmeyen hata")}

        except requests.Timeout:
            return {"success": False, "error": "İşlem zaman aşımına uğradı"}
        except Exception as e:
            logger.error(f"Melodi çıkarma hatası: {e}")
            return {"success": False, "error": str(e)}

    def generate_music(self, prompt: str, duration: int = 30) -> Dict[str, Any]:
        """
        Prompt'tan müzik üret (MusicGen)

        Args:
            prompt: Stil açıklaması
            duration: Süre (saniye)

        Returns:
            dict: {
                "success": bool,
                "audio_path": str veya "audio_base64": str,
                "duration": int
            }
        """
        # 1. Modal.com kullan (tercih edilir)
        if self._use_modal():
            try:
                logger.info(f"Modal ile müzik üretiliyor: {prompt[:50]}...")
                audio_bytes = self.modal_bridge.generate_music(prompt=prompt, duration=duration)
                # Dosyaya kaydet
                output_dir = os.path.join(tempfile.gettempdir(), "videocu_audio")
                os.makedirs(output_dir, exist_ok=True)
                audio_path = os.path.join(output_dir, f"generated_{hash(prompt) % 10000}.wav")
                self.modal_bridge.save_audio(audio_bytes, audio_path)
                return {
                    "success": True,
                    "audio_path": audio_path,
                    "duration": duration
                }
            except Exception as e:
                logger.warning(f"Modal müzik üretme hatası: {e}")

        # 2. Gradio API kullan
        if self._use_gradio():
            try:
                logger.info(f"Gradio ile müzik üretiliyor: {prompt[:50]}...")
                # Gradio predict çağrısı - style, custom_prompt, duration
                result = self.gradio_client.predict(
                    prompt,  # style dropdown value
                    "",      # custom_prompt (boş = style kullan)
                    duration,
                    api_name="/generate_music"
                )
                # Sonuç audio dosya yolu
                if result:
                    return {
                        "success": True,
                        "audio_path": result,
                        "duration": duration
                    }
                return {"success": False, "error": "Müzik üretilemedi"}
            except Exception as e:
                logger.error(f"Gradio müzik üretme hatası: {e}")
                if not self.colab_url:
                    return {"success": False, "error": str(e)}

        # Flask/ngrok API fallback
        if not self.colab_url:
            return {"success": False, "error": "GPU sunucusu erişilemez (Modal bağlantısını kontrol edin)"}

        try:
            response = requests.post(
                f"{self.colab_url}/generate-music",
                json={
                    "prompt": prompt,
                    "duration": duration
                },
                timeout=self.timeout
            )

            return response.json()

        except requests.Timeout:
            return {"success": False, "error": "İşlem zaman aşımına uğradı"}
        except Exception as e:
            logger.error(f"Müzik üretme hatası: {e}")
            return {"success": False, "error": str(e)}

    def transform_melody(self, audio_path: str, style_prompt: str, duration: int = 30) -> Dict[str, Any]:
        """
        Melodiyi profesyonel sese dönüştür (MusicGen melody-conditioned)

        Args:
            audio_path: Melodi ses dosyası
            style_prompt: Hedef stil açıklaması
            duration: Çıktı süresi

        Returns:
            dict: {
                "success": bool,
                "audio_path": str veya "audio_base64": str
            }
        """
        # 1. Modal.com kullan (tercih edilir)
        if self._use_modal():
            try:
                logger.info(f"Modal ile melodi dönüştürülüyor: {style_prompt[:50]}...")
                with open(audio_path, 'rb') as f:
                    audio_bytes = f.read()
                result_bytes = self.modal_bridge.transform_melody(
                    audio_bytes=audio_bytes,
                    style_prompt=style_prompt,
                    duration=duration
                )
                # Dosyaya kaydet
                output_dir = os.path.join(tempfile.gettempdir(), "videocu_audio")
                os.makedirs(output_dir, exist_ok=True)
                output_path = os.path.join(output_dir, f"transformed_{hash(style_prompt) % 10000}.wav")
                self.modal_bridge.save_audio(result_bytes, output_path)
                return {
                    "success": True,
                    "audio_path": output_path
                }
            except Exception as e:
                logger.warning(f"Modal melodi dönüştürme hatası: {e}")

        # 2. Gradio API kullan
        if self._use_gradio():
            try:
                logger.info(f"Gradio ile melodi dönüştürülüyor: {style_prompt[:50]}...")
                # Gradio predict çağrısı - audio, style, duration
                result = self.gradio_client.predict(
                    audio_path,
                    style_prompt,
                    duration,
                    api_name="/transform_melody"
                )
                if result:
                    return {
                        "success": True,
                        "audio_path": result
                    }
                return {"success": False, "error": "Melodi dönüştürülemedi"}
            except Exception as e:
                logger.error(f"Gradio melodi dönüştürme hatası: {e}")
                if not self.colab_url:
                    return {"success": False, "error": str(e)}

        # Flask/ngrok API fallback
        if not self.colab_url:
            return {"success": False, "error": "GPU sunucusu erişilemez (Modal bağlantısını kontrol edin)"}

        try:
            # Ses dosyasını base64'e çevir
            with open(audio_path, 'rb') as f:
                audio_b64 = base64.b64encode(f.read()).decode()

            response = requests.post(
                f"{self.colab_url}/transform-melody",
                json={
                    "audio": audio_b64,
                    "prompt": style_prompt,
                    "duration": duration
                },
                timeout=self.timeout
            )

            return response.json()

        except requests.Timeout:
            return {"success": False, "error": "İşlem zaman aşımına uğradı"}
        except Exception as e:
            logger.error(f"Melodi dönüştürme hatası: {e}")
            return {"success": False, "error": str(e)}

    def separate_stems(self, audio_path: str) -> Dict[str, Any]:
        """
        Sesi stem'lerine ayır (Demucs)

        Args:
            audio_path: Ses dosyası

        Returns:
            dict: {
                "success": bool,
                "stems": {
                    "vocals": path veya base64,
                    "no_vocals": path veya base64
                }
            }
        """
        # 1. Modal.com kullan (tercih edilir)
        if self._use_modal():
            try:
                logger.info(f"Modal ile stem'ler ayrılıyor: {audio_path}")
                with open(audio_path, 'rb') as f:
                    audio_bytes = f.read()
                result = self.modal_bridge.separate_stems(audio_bytes)
                if result.get("success"):
                    # Dosyalara kaydet
                    output_dir = os.path.join(tempfile.gettempdir(), "videocu_stems")
                    os.makedirs(output_dir, exist_ok=True)

                    vocals_path = None
                    instrumental_path = None

                    if result.get("vocals_bytes"):
                        vocals_path = os.path.join(output_dir, f"vocals_{os.path.basename(audio_path)}")
                        with open(vocals_path, 'wb') as f:
                            f.write(bytes.fromhex(result["vocals_bytes"]))

                    if result.get("instrumental_bytes"):
                        instrumental_path = os.path.join(output_dir, f"instrumental_{os.path.basename(audio_path)}")
                        with open(instrumental_path, 'wb') as f:
                            f.write(bytes.fromhex(result["instrumental_bytes"]))

                    return {
                        "success": True,
                        "stems": {
                            "vocals": vocals_path,
                            "no_vocals": instrumental_path
                        }
                    }
            except Exception as e:
                logger.warning(f"Modal stem ayırma hatası: {e}")

        # 2. Gradio API kullan
        if self._use_gradio():
            try:
                logger.info(f"Gradio ile stem'ler ayrılıyor: {audio_path}")
                # Gradio predict çağrısı - audio
                result = self.gradio_client.predict(
                    audio_path,
                    api_name="/separate_stems"
                )
                # Sonuç tuple: (vocals_path, instrumental_path)
                if isinstance(result, tuple) and len(result) >= 2:
                    return {
                        "success": True,
                        "stems": {
                            "vocals": result[0],
                            "no_vocals": result[1]
                        }
                    }
                return {"success": False, "error": "Stem'ler ayrılamadı"}
            except Exception as e:
                logger.error(f"Gradio stem ayırma hatası: {e}")
                if not self.colab_url:
                    return {"success": False, "error": str(e)}

        # Flask/ngrok API fallback
        if not self.colab_url:
            return {"success": False, "error": "GPU sunucusu erişilemez (Modal bağlantısını kontrol edin)"}

        try:
            with open(audio_path, 'rb') as f:
                audio_b64 = base64.b64encode(f.read()).decode()

            response = requests.post(
                f"{self.colab_url}/separate-stems",
                json={"audio": audio_b64},
                timeout=self.timeout
            )

            return response.json()

        except requests.Timeout:
            return {"success": False, "error": "İşlem zaman aşımına uğradı"}
        except Exception as e:
            logger.error(f"Stem ayırma hatası: {e}")
            return {"success": False, "error": str(e)}

    def save_audio_from_base64(self, audio_b64: str, output_path: str) -> str:
        """Base64 ses verisini dosyaya kaydet"""
        audio_bytes = base64.b64decode(audio_b64)
        with open(output_path, 'wb') as f:
            f.write(audio_bytes)
        return output_path

    def quantize_midi(self, midi_path: str, grid: str = "16th") -> Dict[str, Any]:
        """
        MIDI notalarini grid'e oturtur (dalgali notalari duzelt)

        Args:
            midi_path: MIDI dosyasi yolu
            grid: Quantize grid ("8th", "16th", "32nd")

        Returns:
            dict: {
                "success": bool,
                "midi_path": str,
                "note_count": int,
                "corrections": int
            }
        """
        if self._use_modal():
            try:
                logger.info(f"Modal ile MIDI quantize: {midi_path}")
                with open(midi_path, 'rb') as f:
                    midi_hex = f.read().hex()
                result = self.modal_bridge.quantize_midi(midi_hex=midi_hex, grid=grid)
                if result.get("success"):
                    # Duzeltilmis MIDI'yi kaydet
                    output_dir = os.path.join(tempfile.gettempdir(), "videocu_midi")
                    os.makedirs(output_dir, exist_ok=True)
                    output_path = os.path.join(output_dir, f"quantized_{os.path.basename(midi_path)}")
                    self.modal_bridge.save_midi(result["midi_bytes"], output_path)
                    return {
                        "success": True,
                        "midi_path": output_path,
                        "note_count": result.get("note_count", 0),
                        "corrections": result.get("corrections", 0)
                    }
            except Exception as e:
                logger.warning(f"Modal quantize hatasi: {e}")
        return {"success": False, "error": "GPU erisimi yok"}

    def midi_to_audio(self, midi_path: str, instrument: str = "piano") -> Dict[str, Any]:
        """
        MIDI'yi enstruman sesiyle audio'ya donustur

        Args:
            midi_path: MIDI dosyasi yolu
            instrument: Enstruman tipi ("piano", "bass", "synth", "strings", "guitar")

        Returns:
            dict: {
                "success": bool,
                "audio_path": str,
                "duration": float
            }
        """
        if self._use_modal():
            try:
                logger.info(f"Modal ile MIDI -> Audio: {midi_path}, enstruman: {instrument}")
                with open(midi_path, 'rb') as f:
                    midi_hex = f.read().hex()
                result = self.modal_bridge.midi_to_audio(midi_hex=midi_hex, instrument=instrument)
                if result.get("success"):
                    # Audio'yu kaydet
                    output_dir = os.path.join(tempfile.gettempdir(), "videocu_audio")
                    os.makedirs(output_dir, exist_ok=True)
                    output_path = os.path.join(output_dir, f"{instrument}_{os.path.basename(midi_path)}.wav")
                    with open(output_path, 'wb') as f:
                        f.write(bytes.fromhex(result["audio_bytes"]))
                    return {
                        "success": True,
                        "audio_path": output_path,
                        "duration": result.get("duration", 0)
                    }
            except Exception as e:
                logger.warning(f"Modal MIDI->Audio hatasi: {e}")
        return {"success": False, "error": "GPU erisimi yok"}

    def transpose_midi(self, midi_path: str, semitones: int) -> Dict[str, Any]:
        """
        MIDI'yi transpoze et (tonu degistir)

        Args:
            midi_path: MIDI dosyasi yolu
            semitones: Kac yarim adim (pozitif=yukari, negatif=asagi)

        Returns:
            dict: {
                "success": bool,
                "midi_path": str,
                "note_count": int
            }
        """
        if self._use_modal():
            try:
                logger.info(f"Modal ile MIDI transpose: {semitones:+d}")
                with open(midi_path, 'rb') as f:
                    midi_hex = f.read().hex()
                result = self.modal_bridge.transpose_midi(midi_hex=midi_hex, semitones=semitones)
                if result.get("success"):
                    # Transpoze edilmis MIDI'yi kaydet
                    output_dir = os.path.join(tempfile.gettempdir(), "videocu_midi")
                    os.makedirs(output_dir, exist_ok=True)
                    sign = "up" if semitones > 0 else "down"
                    output_path = os.path.join(output_dir, f"transposed_{sign}{abs(semitones)}_{os.path.basename(midi_path)}")
                    self.modal_bridge.save_midi(result["midi_bytes"], output_path)
                    return {
                        "success": True,
                        "midi_path": output_path,
                        "note_count": result.get("note_count", 0)
                    }
            except Exception as e:
                logger.warning(f"Modal transpose hatasi: {e}")
        return {"success": False, "error": "GPU erisimi yok"}


# Stil şablonları
STYLE_PROMPTS = {
    "hip-hop": "modern hip hop beat with heavy 808 bass, trap hi-hats, and punchy snares",
    "pop": "catchy pop melody with bright synths, upbeat drums, and energetic rhythm",
    "electronic": "electronic dance music with pulsing synths, four-on-the-floor beat, and big drops",
    "rock": "rock song with electric guitars, driving drums, and powerful bass",
    "lofi": "chill lofi hip hop with jazzy piano, vinyl crackle, and relaxed drums",
    "rnb": "smooth r&b with soulful chords, soft drums, and warm bass",
    "trap": "dark trap beat with heavy 808s, fast hi-hats, and aggressive energy",
    "acoustic": "acoustic ballad with gentle guitar, soft percussion, and intimate feel",
    "orchestral": "epic orchestral piece with strings, brass, and dramatic percussion",
    "jazz": "jazz composition with piano, upright bass, and swing drums"
}


def get_style_prompt(style: str) -> str:
    """Stil adından prompt al"""
    return STYLE_PROMPTS.get(style.lower(), STYLE_PROMPTS["pop"])
