"""
YouTube Data API v3 — video yukleme (resmi API, OAuth 2.0).

AKIS (sifre bizde DURMAZ):
  1. `auth_url()` bir Google giris baglantisi uretir.
  2. Kullanici KENDI tarayicisinda giris yapar ve izin verir.
  3. Google, /api/social/youtube/callback adresine bir kod dondurur.
  4. `exchange_code()` bu kodu yenileme belirtecine cevirir ve saklar.
Bundan sonra yukleme, her seferinde tazelenen kisa omurlu bir erisim
belirteciyle yapilir. Google sifresi hicbir asamada bize ulasmaz.

KOTA: videos.insert = 1600 birim, varsayilan gunluk kota 10.000 -> ~6 video/gun.
oauth_store gunluk 4 ile daha muhafazakar bir tavan uygular; kota duvarina
toslamak, o gunku tum yuklemeleri kaybetmek demektir.

GEREKENLER (kullanici tarafinda, tek seferlik):
  - Google Cloud projesi + "YouTube Data API v3" etkin
  - OAuth istemcisi (Web application), yetkili yonlendirme adresi:
        http://localhost:8501/api/social/youtube/callback
  - Ortam degiskenleri: YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

from . import oauth_store

AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
UPLOAD_ENDPOINT = "https://www.googleapis.com/upload/youtube/v3/videos"

# Yalnizca yukleme izni istiyoruz — kanali okuma/silme yetkisi ISTENMEZ.
SCOPE = "https://www.googleapis.com/auth/youtube.upload"
DEFAULT_REDIRECT = "http://localhost:8501/api/social/youtube/callback"

PLATFORM = "youtube"


@dataclass
class UploadResult:
    ok: bool
    video_id: str = ""
    url: str = ""
    error: str = ""


def is_configured() -> bool:
    return bool(os.getenv("YOUTUBE_CLIENT_ID") and os.getenv("YOUTUBE_CLIENT_SECRET"))


def is_connected() -> bool:
    account = oauth_store.get_account(PLATFORM)
    return bool(account and account.get("refresh_token"))


def status() -> dict:
    """Neden calismadigi ACIKCA gorunsun — sessiz basarisizlik olmasin."""
    if not is_configured():
        reason = "YOUTUBE_CLIENT_ID/SECRET tanimli degil (Google Cloud projesi acilmali)"
    elif not is_connected():
        reason = "yapilandirildi ama hesap baglanmamis — /api/social/youtube/start ile baglayin"
    else:
        reason = "hazir"
    return {
        "platform": PLATFORM,
        "configured": is_configured(),
        "connected": is_connected(),
        "quota_left_today": oauth_store.quota_left(PLATFORM),
        "reason": reason,
    }


def auth_url(redirect_uri: str = DEFAULT_REDIRECT, state: str = "") -> Optional[str]:
    """Kullanicinin KENDI tarayicisinda acacagi Google izin baglantisi."""
    if not is_configured():
        return None
    return AUTH_ENDPOINT + "?" + urlencode({
        "client_id": os.getenv("YOUTUBE_CLIENT_ID"),
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": SCOPE,
        # offline + consent: yenileme belirteci ancak boyle doner
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        **({"state": state} if state else {}),
    })


def exchange_code(code: str, redirect_uri: str = DEFAULT_REDIRECT) -> tuple[bool, str]:
    """Yetki kodunu yenileme belirtecine cevirir ve saklar. (basari, mesaj)"""
    if not is_configured():
        return False, "YOUTUBE_CLIENT_ID/SECRET tanimli degil"

    import requests
    try:
        resp = requests.post(TOKEN_ENDPOINT, data={
            "code": code,
            "client_id": os.getenv("YOUTUBE_CLIENT_ID"),
            "client_secret": os.getenv("YOUTUBE_CLIENT_SECRET"),
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }, timeout=30)
    except Exception as exc:
        return False, f"token istegi basarisiz: {exc}"

    if resp.status_code != 200:
        # Google'in hata gerekcesi tasinir ama belirtec ASLA loglanmaz
        return False, f"token reddedildi (HTTP {resp.status_code}): {resp.text[:200]}"

    payload = resp.json()
    refresh_token = payload.get("refresh_token")
    if not refresh_token:
        return False, ("yenileme belirteci donmedi — izni kaldirip tekrar deneyin "
                       "(access_type=offline & prompt=consent gerekli)")

    oauth_store.save_account(PLATFORM, refresh_token=refresh_token,
                             account_label="YouTube")
    return True, "YouTube hesabi baglandi"


def _access_token() -> Optional[str]:
    """Kisa omurlu erisim belirteci — saklanmaz, her cagrida tazelenir."""
    account = oauth_store.get_account(PLATFORM)
    if not account or not is_configured():
        return None

    import requests
    try:
        resp = requests.post(TOKEN_ENDPOINT, data={
            "refresh_token": account["refresh_token"],
            "client_id": os.getenv("YOUTUBE_CLIENT_ID"),
            "client_secret": os.getenv("YOUTUBE_CLIENT_SECRET"),
            "grant_type": "refresh_token",
        }, timeout=30)
    except Exception:
        return None
    if resp.status_code != 200:
        return None
    return resp.json().get("access_token")


def upload_video(
    video_path: Path | str,
    *,
    title: str,
    description: str = "",
    tags: Optional[list[str]] = None,
    privacy: str = "private",
    category_id: str = "22",       # 22 = People & Blogs
) -> UploadResult:
    """
    Videoyu resumable yukleme ile gonderir.

    privacy VARSAYILAN OLARAK 'private': otomatik bir hattin ilk denemesinde
    videoyu dogrudan herkese acmak yanlis olur. Kullanici sonucu gorup kendi
    kararyla 'public' yapar (ya da cagiran taraf bilincle public gecer).
    """
    video_path = Path(video_path)
    if not video_path.exists() or video_path.stat().st_size == 0:
        return UploadResult(False, error="video dosyasi yok veya bos")
    if not is_connected():
        return UploadResult(False, error="YouTube hesabi bagli degil")
    if oauth_store.quota_left(PLATFORM) <= 0:
        return UploadResult(False, error="gunluk yayin kotasi doldu")

    token = _access_token()
    if not token:
        return UploadResult(False, error="erisim belirteci alinamadi (yetki dusmus olabilir)")

    import requests

    metadata = {
        "snippet": {
            "title": title[:100],                 # YouTube siniri
            "description": description[:5000],
            "tags": (tags or [])[:20],
            "categoryId": category_id,
        },
        "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False},
    }

    size = video_path.stat().st_size
    try:
        # 1) Oturum baslat — Location basligi yukleme adresini verir
        init = requests.post(
            UPLOAD_ENDPOINT,
            params={"uploadType": "resumable", "part": "snippet,status"},
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=UTF-8",
                "X-Upload-Content-Length": str(size),
                "X-Upload-Content-Type": "video/mp4",
            },
            json=metadata, timeout=60,
        )
        if init.status_code not in (200, 201):
            return UploadResult(False, error=f"oturum acilamadi (HTTP {init.status_code}): {init.text[:200]}")

        session_url = init.headers.get("Location")
        if not session_url:
            return UploadResult(False, error="yukleme adresi (Location) donmedi")

        # 2) Baytlari gonder
        with open(video_path, "rb") as fh:
            put = requests.put(
                session_url,
                headers={"Content-Type": "video/mp4", "Content-Length": str(size)},
                data=fh, timeout=600,
            )
        if put.status_code not in (200, 201):
            return UploadResult(False, error=f"yukleme basarisiz (HTTP {put.status_code}): {put.text[:200]}")

        video_id = put.json().get("id", "")
    except Exception as exc:
        return UploadResult(False, error=f"yukleme hatasi: {str(exc)[:200]}")

    oauth_store.record_publish(PLATFORM)   # yalnizca GERCEKTEN olan sayilir
    return UploadResult(True, video_id=video_id,
                        url=f"https://www.youtube.com/watch?v={video_id}")
