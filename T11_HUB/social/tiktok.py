"""
TikTok Content Posting API — video yayinlama (resmi API, OAuth 2.0).

DENETIM (audit) KURALI — atlanamaz, sessizce denenmemeli:
Uygulama TikTok denetiminden gecmeden once yuklenen her video yalnizca
SELF_ONLY (sadece hesap sahibi gorur) olarak yayinlanabilir ve 24 saatte en
fazla 5 kullanici gonderim yapabilir. Herkese acik paylasim icin uygulamanin
denetime girmesi gerekir. Bu yuzden `privacy` varsayilani SELF_ONLY: denetim
oncesi "herkese acik" istemek zaten API tarafindan reddedilir.

AKIS (iki asamali, dogrudan dosya POST'u YOK):
  1. /post/publish/video/init/  -> yukleme adresi (upload_url) doner
  2. o adrese PUT ile video baytlari gonderilir
  3. TikTok isler; durum /post/publish/status/fetch/ ile sorulur

Gerekli ortam degiskenleri:
    TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

from . import oauth_store

AUTH_ENDPOINT = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_ENDPOINT = "https://open.tiktokapis.com/v2/oauth/token/"
INIT_ENDPOINT = "https://open.tiktokapis.com/v2/post/publish/video/init/"
STATUS_ENDPOINT = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"

SCOPES = "video.publish"
DEFAULT_REDIRECT = "http://localhost:8501/api/social/tiktok/callback"
PLATFORM = "tiktok"

# Denetimden once TEK gecerli deger. Denetim gecince "PUBLIC_TO_EVERYONE" olur.
DEFAULT_PRIVACY = "SELF_ONLY"


@dataclass
class TikTokResult:
    ok: bool
    publish_id: str = ""
    privacy: str = ""
    error: str = ""
    note: str = ""


def is_configured() -> bool:
    return bool(os.getenv("TIKTOK_CLIENT_KEY") and os.getenv("TIKTOK_CLIENT_SECRET"))


def is_connected() -> bool:
    account = oauth_store.get_account(PLATFORM)
    return bool(account and account.get("refresh_token"))


def status() -> dict:
    # Denetim kisiti HER durumda soylenir: kullanici kurulumun sonunda degil,
    # BASINDA "herkese acik paylasim icin ayrica denetim gerekiyor" bilgisini
    # gormeli. Yoksa kurulumu bitirip beklentisi karsilanmamis olur.
    denetim = ("Not: TikTok denetimi gecilene kadar gonderiler SELF_ONLY "
               "(yalnizca hesap sahibi gorur), 24 saatte 5 gonderim siniri.")
    if not is_configured():
        reason = ("TIKTOK_CLIENT_KEY/SECRET tanimli degil "
                  f"(developers.tiktok.com'da uygulama gerekli). {denetim}")
    elif not is_connected():
        reason = f"yapilandirildi ama hesap baglanmamis — /api/social/tiktok/start. {denetim}"
    else:
        reason = f"bagli. {denetim}"
    return {"platform": PLATFORM, "configured": is_configured(),
            "connected": is_connected(),
            "quota_left_today": oauth_store.quota_left(PLATFORM), "reason": reason}


def auth_url(redirect_uri: str = DEFAULT_REDIRECT, state: str = "") -> Optional[str]:
    if not is_configured():
        return None
    return AUTH_ENDPOINT + "?" + urlencode({
        "client_key": os.getenv("TIKTOK_CLIENT_KEY"),
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": SCOPES,
        **({"state": state} if state else {}),
    })


def exchange_code(code: str, redirect_uri: str = DEFAULT_REDIRECT) -> tuple[bool, str]:
    if not is_configured():
        return False, "TIKTOK_CLIENT_KEY/SECRET tanimli degil"
    import requests
    try:
        resp = requests.post(
            TOKEN_ENDPOINT,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={"client_key": os.getenv("TIKTOK_CLIENT_KEY"),
                  "client_secret": os.getenv("TIKTOK_CLIENT_SECRET"),
                  "code": code, "grant_type": "authorization_code",
                  "redirect_uri": redirect_uri},
            timeout=30)
    except Exception as exc:
        return False, f"token istegi basarisiz: {exc}"
    if resp.status_code != 200:
        return False, f"token reddedildi (HTTP {resp.status_code}): {resp.text[:200]}"

    payload = resp.json()
    refresh = payload.get("refresh_token")
    if not refresh:
        return False, f"yenileme belirteci donmedi: {str(payload)[:200]}"
    oauth_store.save_account(PLATFORM, refresh_token=refresh, account_label="TikTok")
    return True, "TikTok hesabi baglandi"


def _access_token() -> Optional[str]:
    account = oauth_store.get_account(PLATFORM)
    if not account or not is_configured():
        return None
    import requests
    try:
        resp = requests.post(
            TOKEN_ENDPOINT,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={"client_key": os.getenv("TIKTOK_CLIENT_KEY"),
                  "client_secret": os.getenv("TIKTOK_CLIENT_SECRET"),
                  "grant_type": "refresh_token",
                  "refresh_token": account["refresh_token"]},
            timeout=30)
    except Exception:
        return None
    return resp.json().get("access_token") if resp.status_code == 200 else None


def upload_video(
    video_path: Path | str,
    *,
    title: str,
    privacy: str = DEFAULT_PRIVACY,
) -> TikTokResult:
    """
    Videoyu iki asamali akisla yukler. Denetim oncesi privacy SELF_ONLY olmali;
    aksi halde TikTok istegi reddeder.
    """
    video_path = Path(video_path)
    if not video_path.exists() or video_path.stat().st_size == 0:
        return TikTokResult(False, error="video dosyasi yok veya bos")
    if not is_connected():
        return TikTokResult(False, error="TikTok hesabi bagli degil")
    if oauth_store.quota_left(PLATFORM) <= 0:
        return TikTokResult(False, error="gunluk yayin kotasi doldu")

    token = _access_token()
    if not token:
        return TikTokResult(False, error="erisim belirteci alinamadi")

    import requests
    size = video_path.stat().st_size
    try:
        init = requests.post(
            INIT_ENDPOINT,
            headers={"Authorization": f"Bearer {token}",
                     "Content-Type": "application/json; charset=UTF-8"},
            json={
                "post_info": {
                    "title": title[:2000],
                    "privacy_level": privacy,
                    "disable_comment": False,
                },
                "source_info": {
                    "source": "FILE_UPLOAD",
                    "video_size": size,
                    "chunk_size": size,      # tek parca
                    "total_chunk_count": 1,
                },
            }, timeout=60)
    except Exception as exc:
        return TikTokResult(False, error=f"oturum acilamadi: {str(exc)[:200]}")

    if init.status_code != 200:
        return TikTokResult(False, error=f"init HTTP {init.status_code}: {init.text[:250]}")

    data = (init.json() or {}).get("data", {})
    upload_url = data.get("upload_url")
    publish_id = data.get("publish_id", "")
    if not upload_url:
        return TikTokResult(False, error=f"yukleme adresi donmedi: {init.text[:200]}")

    try:
        with open(video_path, "rb") as fh:
            put = requests.put(
                upload_url,
                headers={"Content-Type": "video/mp4",
                         "Content-Range": f"bytes 0-{size - 1}/{size}"},
                data=fh, timeout=600)
    except Exception as exc:
        return TikTokResult(False, error=f"yukleme hatasi: {str(exc)[:200]}")

    if put.status_code not in (200, 201, 204):
        return TikTokResult(False, error=f"yukleme HTTP {put.status_code}: {put.text[:200]}")

    oauth_store.record_publish(PLATFORM)
    note = ("Denetim oncesi gonderiler yalnizca size gorunur (SELF_ONLY)."
            if privacy == "SELF_ONLY" else "")
    return TikTokResult(True, publish_id=publish_id, privacy=privacy, note=note)


def publish_status(publish_id: str) -> dict:
    """Yuklemenin islenme durumunu sorar (TikTok isleme suresi degisir)."""
    token = _access_token()
    if not token or not publish_id:
        return {}
    import requests
    try:
        resp = requests.post(
            STATUS_ENDPOINT,
            headers={"Authorization": f"Bearer {token}",
                     "Content-Type": "application/json; charset=UTF-8"},
            json={"publish_id": publish_id}, timeout=30)
        return resp.json().get("data", {}) if resp.status_code == 200 else {}
    except Exception:
        return {}
