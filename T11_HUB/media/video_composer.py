"""
Kompozisyon-tabanli video modulu (ffmpeg) — KOMPOZISYON, URETKEN DEGIL.

Bilincli mimari karar: "prompt -> video" ureten modeller kullanilmaz (gecmiste
bu yol batti). Burada video, GERCEK urun fotograflarindan + gercek kampanya
metninden + marka renklerinden DETERMINISTIK olarak kurgulanir. Ayni girdi ayni
videoyu verir; icerikte uydurma bir sey olmaz.

ffmpeg: PATH'te aranmaz — `imageio_ffmpeg` paketinin BIRLIKTE GELDIGI binary
kullanilir (zaten kurulu, ek kurulum/indirme yok).

Ses: media/voice.py'den gelirse eklenir; yoksa video SESSIZ uretilir ve
`has_audio=False` doner — "seslendirme var" gibi davranilmaz.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Dikey sosyal medya formati (Reels/Shorts/TikTok)
WIDTH, HEIGHT = 1080, 1920
SECONDS_PER_IMAGE = 3.0
FPS = 30

# Kapanis: reklamin markayla bitmesi sart — izleyici en son logoyu gormeli.
LOGO_PATH = Path(__file__).resolve().parent.parent / "static" / "img" / "css_berlin_logo.png"
LOGO_OUTRO_SECONDS = 2.5
# Konusma bittikten sonra birakilan sessiz pay. Bu olmadan son cumle
# "yutuluyor" gibi duyuluyor (video sesten once bitiyordu).
TAIL_SILENCE_SECONDS = 1.5
OUTRO_COLOR = "0x2D6A4F"   # marka yesili — turuncu/yesil logo bu zeminde okunuyor


@dataclass
class VideoResult:
    path: Path
    duration_s: float
    image_count: int
    has_audio: bool
    voice_matched: bool = True


def ffmpeg_exe() -> Optional[str]:
    """Once imageio_ffmpeg'in bundle ettigi binary, sonra PATH."""
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return shutil.which("ffmpeg")


# Videonun kisa kenari 1080. Bunun yarisindan dar bir gorseli 1080'e cikarmak
# gercek detay eklemez, sadece bulanik/bloklu bir goruntu uretir. Kazima bazi
# urunlerde kucuk-resim (ornegin 140x105) kaydettigi icin bu filtre sart:
# kotu bir video uretmektense o gorseli hic kullanmamak dogru.
MIN_IMAGE_WIDTH = 540


def _media_duration(exe: str, path: Path) -> float:
    """ffmpeg ciktisindan sure okur. Okunamazsa 0.0 (tahmin yurutulmez)."""
    try:
        proc = subprocess.run([exe, "-i", str(path)], capture_output=True,
                              text=True, timeout=60)
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", proc.stderr or "")
        if not m:
            return 0.0
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    except Exception:
        return 0.0


def _wide_enough(path: Path) -> bool:
    try:
        from PIL import Image
        with Image.open(path) as img:
            return min(img.size) >= MIN_IMAGE_WIDTH
    except Exception:
        return False  # okunamayan gorsel videoya girmez


def _font_path() -> Optional[str]:
    """drawtext icin gercekten var olan bir font. Yoksa yazi katmani atlanir."""
    for candidate in (r"C:\Windows\Fonts\arialbd.ttf", r"C:\Windows\Fonts\arial.ttf",
                      "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        if Path(candidate).exists():
            return candidate
    return None


def _esc_font(path: str) -> str:
    """ffmpeg filtre dizgesinde Windows yolu: ters bolu ve iki nokta kacisi."""
    return path.replace("\\", "/").replace(":", r"\:")


def _esc_text(text: str) -> str:
    """drawtext metin kacisi (tek tirnak, iki nokta, yuzde, ters bolu)."""
    return (text.replace("\\", r"\\").replace(":", r"\:")
                .replace("'", r"\'").replace("%", r"\%"))


def compose_product_video(
    image_paths: list[Path | str],
    out_path: Path | str,
    *,
    headline: str = "",
    cta: str = "",
    brand_color: str = "0xE8651A",     # marka turuncusu (brand_identity.palette)
    audio_path: Optional[Path | str] = None,
    voice_matched: bool = True,
    seconds_per_image: float = SECONDS_PER_IMAGE,
    timeout: int = 300,
) -> Optional[VideoResult]:
    """
    Gercek urun gorsellerinden dikey bir tanitim videosu kurgular.

    image_paths: GERCEK, var olan dosyalar (islenmis stüdyo gorselleri).
    headline/cta: kampanya motorundan gelen, iddia bekcisinden GECMIS metin.
    audio_path: voice.synthesize() ciktisi; None ise video sessiz uretilir.

    Basarisizlikta None doner (bozuk/yarim dosya birakmaz).
    """
    exe = ffmpeg_exe()
    if not exe:
        return None

    images = [Path(p) for p in image_paths]
    images = [p for p in images if p.exists() and p.stat().st_size > 0]
    images = [p for p in images if _wide_enough(p)]
    if not images:
        return None  # kullanilabilir cozunurlukte gorsel yok -> video URETILMEZ

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Gecici ad GERCEK uzantiyi korumali (".part.mp4"), cunku ffmpeg cikti
    # muxer'ini uzantidan secer; ".mp4.part" ile "Invalid argument" verir.
    tmp_path = out_path.with_name(f"{out_path.stem}.part{out_path.suffix}")

    # Kapanis suresi: logo en az LOGO_OUTRO_SECONDS gorunur; ses gorsellerden
    # uzunsa logo, konusma bitene + TAIL_SILENCE kadar daha ekranda kalir.
    # Boylece son cumle asla kesilmez ve reklam markayla biter.
    has_audio = bool(audio_path and Path(audio_path).exists())
    outro_seconds = LOGO_OUTRO_SECONDS
    if has_audio:
        speech = _media_duration(exe, Path(audio_path))
        if speech > 0:
            needed = speech + TAIL_SILENCE_SECONDS - len(images) * seconds_per_image
            outro_seconds = max(LOGO_OUTRO_SECONDS, round(needed, 2))

    use_logo = LOGO_PATH.exists()
    frames = max(1, int(seconds_per_image * FPS))
    outro_frames = max(1, int(outro_seconds * FPS))

    cmd: list[str] = [exe, "-y"]
    # Her gorsel TEK KARE olarak beslenir (-framerate 1 -t 1). Suresi asagida
    # zoompan'in d= degeriyle verilir. Aksi halde zoompan her GIRIS karesi icin
    # d kare uretir (3s x 25fps x 90 = 6750 kare/gorsel) ve render dakikalarca surer.
    for img in images:
        cmd += ["-loop", "1", "-framerate", "1", "-t", "1", "-i", str(img)]
    if use_logo:
        cmd += ["-loop", "1", "-framerate", "1", "-t", "1", "-i", str(LOGO_PATH)]
    if has_audio:
        cmd += ["-i", str(audio_path)]

    # Her gorsel: orana sadik olcekle -> marka renkli dikey tuvale ortala ->
    # hafif Ken Burns yakinlasmasi (statik slayt gosterisi gibi durmasin).
    filters = []
    for i in range(len(images)):
        filters.append(
            f"[{i}:v]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,"
            f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2:color={brand_color},"
            f"zoompan=z='min(zoom+0.0009,1.12)':d={frames}:"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={WIDTH}x{HEIGHT}:fps={FPS},"
            f"setsar=1[v{i}]"
        )
    concat_inputs = "".join(f"[v{i}]" for i in range(len(images)))
    filters.append(f"{concat_inputs}concat=n={len(images)}:v=1:a=0[vcat]")

    # Yazilar SADECE urun bolumune bindirilir; kapanis karesinde logonun
    # uzerine metin gelmez.
    last = "vcat"
    font = _font_path()
    if font and (headline or cta):
        font_arg = f"fontfile='{_esc_font(font)}'"
        if headline:
            filters.append(
                f"[{last}]drawtext={font_arg}:text='{_esc_text(headline)}':"
                f"fontcolor=white:fontsize=72:box=1:boxcolor=black@0.45:boxborderw=24:"
                f"x=(w-text_w)/2:y=140[vh]"
            )
            last = "vh"
        if cta:
            filters.append(
                f"[{last}]drawtext={font_arg}:text='{_esc_text(cta)}':"
                f"fontcolor=white:fontsize=54:box=1:boxcolor={brand_color}@0.85:boxborderw=22:"
                f"x=(w-text_w)/2:y=h-260[vc]"
            )
            last = "vc"

    # Kapanis: marka zemini uzerinde logo, hafifce buyuyerek yerlesir ve
    # ekranda kalir — reklamin son karesi DAIMA marka.
    if use_logo:
        logo_index = len(images)
        filters.append(
            f"[{logo_index}:v]scale=640:640:force_original_aspect_ratio=decrease,"
            f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2:color={OUTRO_COLOR},"
            f"zoompan=z='min(zoom+0.0015,1.08)':d={outro_frames}:"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={WIDTH}x{HEIGHT}:fps={FPS},"
            f"setsar=1[vlogo]"
        )
        filters.append(f"[{last}][vlogo]concat=n=2:v=1:a=0[vout]")
        last = "vout"

    cmd += ["-filter_complex", ";".join(filters), "-map", f"[{last}]"]
    if has_audio:
        audio_index = len(images) + (1 if use_logo else 0)
        # -shortest YOK: video sesten uzun, ses bitince logo sessizce kalir.
        # (-shortest ile video gorsellerde bitiyor ve son cumle kesiliyordu.)
        cmd += ["-map", f"{audio_index}:a", "-c:a", "aac", "-b:a", "128k"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS),
            "-movflags", "+faststart", str(tmp_path)]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        return None

    if proc.returncode != 0 or not tmp_path.exists() or tmp_path.stat().st_size == 0:
        tmp_path.unlink(missing_ok=True)
        return None

    tmp_path.replace(out_path)  # yarim dosya asla nihai ada tasinmaz
    return VideoResult(
        path=out_path,
        duration_s=round(len(images) * seconds_per_image
                         + (outro_seconds if use_logo else 0), 2),
        image_count=len(images),
        has_audio=has_audio,
        voice_matched=voice_matched if has_audio else True,
    )
