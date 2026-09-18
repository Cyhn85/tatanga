"""
Sesten metne (STT) — yerel, ucretsiz, hesap/API yok.

faster-whisper kullanir: tamamen bu makinede calisir, ses kaydi hicbir dis
servise GONDERILMEZ. Musteri sesi hassas veridir; yerel calismak bunu
bulut saglayicisina tasimamak demektir.

Dil: otomatik algilar ya da zorlanir (de/en/tr/uk). Boylece gelen sesli mesaj
hangi dildeyse, yaniti da o dilde seslendirebiliriz (media/voice.py Piper).

Model ILK CAGRIDA indirilir (~150 MB, 'base'). Indirilemezse None doner —
uydurma metin URETILMEZ.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

DEFAULT_MODEL = "base"          # small/medium daha iyi ama belirgin yavas
SUPPORTED_LANGS = ("de", "en", "tr", "uk")
_MODEL_CACHE: dict = {}


@dataclass
class Transcript:
    text: str
    language: str
    duration_s: float
    confidence: float           # 0-1, dil algilama guveni


def is_available() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except Exception:
        return False


def status() -> dict:
    if not is_available():
        return {"available": False,
                "reason": "faster-whisper kurulu degil (pip install faster-whisper)"}
    return {"available": True, "model": DEFAULT_MODEL,
            "reason": "hazir (model ilk kullanimda indirilir)"}


def _load(model_size: str):
    if model_size not in _MODEL_CACHE:
        from faster_whisper import WhisperModel
        # int8 + CPU: bu makinede GPU varsaymiyoruz, bellek dostu.
        _MODEL_CACHE[model_size] = WhisperModel(model_size, device="cpu",
                                                compute_type="int8")
    return _MODEL_CACHE[model_size]


def transcribe(
    audio_path: Path | str,
    *,
    language: Optional[str] = None,
    model_size: str = DEFAULT_MODEL,
) -> Optional[Transcript]:
    """
    Ses dosyasini metne cevirir. Kurulu degilse / dosya yoksa / hata olursa
    None doner — bos ya da uydurma metin uretilmez.

    language=None -> otomatik algila. Bilinen bir dil verilirse zorlanir
    (kisa kayitlarda otomatik algilama yaniliyor).
    """
    audio_path = Path(audio_path)
    if not is_available() or not audio_path.exists() or audio_path.stat().st_size == 0:
        return None
    try:
        model = _load(model_size)
        segments, info = model.transcribe(
            str(audio_path),
            language=language if language in SUPPORTED_LANGS else None,
            vad_filter=True,        # sessizlikleri atla, halusinasyonu azaltir
        )
        text = " ".join(segment.text.strip() for segment in segments).strip()
    except Exception:
        return None
    if not text:
        return None
    return Transcript(
        text=text,
        language=getattr(info, "language", language or "") or "",
        duration_s=round(getattr(info, "duration", 0.0), 2),
        confidence=round(getattr(info, "language_probability", 0.0), 3),
    )
