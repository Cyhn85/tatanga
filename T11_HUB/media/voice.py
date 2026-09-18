"""
Yerel seslendirme (TTS) adaptoru — EN/DE/TR, ucretsiz, API/kayit YOK.

Backend sirasi (ilk calisan kullanilir):
  1. piper        — en iyi kalite, kuruluysa (PATH'te 'piper')
  2. pyttsx3      — Python paketi, kuruluysa
  3. Windows SAPI — Windows 11'de YERLESIK, ek kurulum gerektirmez (bugunku yol)

ONEMLI: Hicbir backend yoksa None doner — SAHTE/BOS ses dosyasi URETILMEZ.
Video modulu sesi olmayan videoyu sessiz uretir, "seslendirme var" gibi davranmaz.

Dil eslesmesi de durustce raporlanir: istenen dilde yuklu ses yoksa
`voice_matched=False` doner (ornegin Turkce ses paketi kurulu degilse), boylece
cagiran taraf yanlis aksanli bir seslendirmeyi bilmeden yayinlamaz.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Dil -> Windows SAPI kultur onekleri
_SAPI_CULTURE = {"de": "de", "en": "en", "tr": "tr", "uk": "uk"}

# --- Piper (birincil): yerel, ucretsiz, hesap/API yok, dogru dilde gercek ses ---
VOICES_DIR = Path(__file__).resolve().parent.parent / "data" / "voices"

# Dil -> indirilmis Piper modeli. Berlin'in gercek musteri profiline gore secildi
# (Almanca ana dil, Ingilizce genel, Turkce ve Ukraynaca buyuk topluluklar).
PIPER_VOICES = {
    "de": "de_DE-thorsten-medium",
    "en": "en_US-lessac-medium",
    "tr": "tr_TR-dfki-medium",
    "uk": "uk_UA-tetiana-high",
}


@dataclass
class SpeechResult:
    path: Path
    backend: str
    voice_matched: bool      # istenen dilde gercek bir ses bulundu mu
    voice_name: str = ""


def piper_model(lang: str) -> Optional[Path]:
    """O dil icin indirilmis model dosyasi (yoksa None — uydurma ses uretilmez)."""
    name = PIPER_VOICES.get(lang)
    if not name:
        return None
    model = VOICES_DIR / f"{name}.onnx"
    return model if model.exists() else None


def available_backends() -> list[str]:
    found = []
    try:
        import piper  # noqa: F401
        found.append("piper")
    except Exception:
        pass
    if shutil.which("piper"):
        found.append("piper_cli")
    try:
        import pyttsx3  # noqa: F401
        found.append("pyttsx3")
    except Exception:
        pass
    if sys.platform == "win32":
        found.append("sapi")
    return found


def _speak_sapi(text: str, out_path: Path, lang: str) -> Optional[SpeechResult]:
    """Windows'ta yerlesik System.Speech ile WAV uretir (ek kurulum yok)."""
    culture = _SAPI_CULTURE.get(lang, "en")
    # PowerShell tarafinda: istenen kulture uyan ilk sesi sec; yoksa varsayilanla
    # devam et ama eslesmedigini bildir (sessizce yanlis aksanla konusmasin).
    script = f"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$match = $synth.GetInstalledVoices() | Where-Object {{
    $_.Enabled -and $_.VoiceInfo.Culture.Name -like '{culture}*'
}} | Select-Object -First 1
if ($match) {{ $synth.SelectVoice($match.VoiceInfo.Name); $matched = 'yes' }} else {{ $matched = 'no' }}
$synth.SetOutputToWaveFile('{out_path.as_posix()}')
$synth.Speak(@'
{text}
'@)
$synth.Dispose()
Write-Output ("MATCHED=" + $matched)
Write-Output ("VOICE=" + $synth.Voice.Name)
"""
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, timeout=120,
        )
    except Exception:
        return None
    if proc.returncode != 0 or not out_path.exists() or out_path.stat().st_size == 0:
        return None

    out = proc.stdout or ""
    matched = "MATCHED=yes" in out
    voice_name = ""
    for line in out.splitlines():
        if line.startswith("VOICE="):
            voice_name = line.split("=", 1)[1].strip()
    return SpeechResult(path=out_path, backend="sapi",
                        voice_matched=matched, voice_name=voice_name)


def _speak_piper(text: str, out_path: Path, lang: str) -> Optional[SpeechResult]:
    """
    Piper ile yerel sentez. Istenen dilin modeli indirilmemisse None doner —
    baska bir dilin sesiyle konusmak, yanlis aksanli bir reklam uretmek olurdu.
    """
    model = piper_model(lang)
    if model is None:
        return None
    try:
        import wave
        from piper import PiperVoice

        voice = PiperVoice.load(str(model))
        with wave.open(str(out_path), "wb") as wav:
            voice.synthesize_wav(text, wav)
    except Exception:
        return None
    if not out_path.exists() or out_path.stat().st_size == 0:
        return None
    return SpeechResult(path=out_path, backend="piper", voice_matched=True,
                        voice_name=PIPER_VOICES[lang])


def _speak_pyttsx3(text: str, out_path: Path, lang: str) -> Optional[SpeechResult]:
    try:
        import pyttsx3
        engine = pyttsx3.init()
        matched = False
        for v in engine.getProperty("voices"):
            if lang in (getattr(v, "id", "") or "").lower() or \
               lang in (getattr(v, "name", "") or "").lower():
                engine.setProperty("voice", v.id)
                matched = True
                break
        engine.save_to_file(text, str(out_path))
        engine.runAndWait()
    except Exception:
        return None
    if not out_path.exists() or out_path.stat().st_size == 0:
        return None
    return SpeechResult(path=out_path, backend="pyttsx3", voice_matched=matched)


def synthesize(text: str, out_path: Path, *, lang: str = "de") -> Optional[SpeechResult]:
    """
    Metni WAV'a seslendirir. Hicbir backend yoksa None (sahte ses URETILMEZ).
    """
    if not text or not text.strip():
        return None
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    for backend in available_backends():
        result = None
        if backend == "piper":
            result = _speak_piper(text, out_path, lang)
        elif backend == "pyttsx3":
            result = _speak_pyttsx3(text, out_path, lang)
        elif backend == "sapi":
            result = _speak_sapi(text, out_path, lang)
        if result is not None:
            return result
    return None
