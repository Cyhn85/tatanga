"""
Instagram Graph API — Reels yayinlama (resmi API, Meta OAuth).

DIGERLERINDEN ONEMLI BIR FARK: Instagram video DOSYASI KABUL ETMEZ.
Videoyu kendisi indirir, bu yuzden video HERKESE ACIK bir URL'de durmali.
Bizim durumumuzda cozum hazir: cssberlin sunucusunda nginx zaten
https://cssberlin.de/uploads/... altini servis ediyor; video oraya konup
adresi verilir. Yerel dosya yolu ile bu API calismaz.

AKIS (iki asamali):
  1. POST /{ig_user_id}/media          -> "container" olusturulur (video indirilir)
  2. POST /{ig_user_id}/media_publish  -> container yayinlanir
Arada video islenir; hazir olmadan yayinlamak hata verir, bu yuzden durum
beklenir.

SARTLAR (Meta'nin kurali, kod ile asilamaz):
  - Instagram hesabi BUSINESS olmali (Creator hesaplarda yayinlama CALISMAZ)
  - Bir Facebook Sayfasina bagli olmali
  - instagram_business_content_publish izni App Review'dan gecmis olmali
  - Reels sekmesinde gorunmek icin 9:16 ve 5-90 saniye
  - 24 saatte en fazla 25 gonderi

Gerekli ortam degiskenleri:
    INSTAGRAM_APP_ID, INSTAGRAM_APP_SECRET, INSTAGRAM_USER_ID
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlencode

from . import oauth_store

GRAPH_VERSION = "v21.0"
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_VERSION}"
AUTH_ENDPOINT = "https://www.facebook.com/{v}/dialog/oauth".format(v=GRAPH_VERSION)
TOKEN_ENDPOINT = f"{GRAPH_BASE}/oauth/access_token"

SCOPES = "instagram_business_basic,instagram_business_content_publish"
DEFAULT_REDIRECT = "http://localhost:8501/api/social/instagram/callback"
PLATFORM = "instagram"

CONTAINER_POLL_SECONDS = 5
CONTAINER_MAX_WAIT = 300


@dataclass
class ReelResult:
    ok: bool
    media_id: str = ""
    error: str = ""


def is_configured() -> bool:
    return bool(os.getenv("INSTAGRAM_APP_ID") and os.getenv("INSTAGRAM_APP_SECRET")
                and os.getenv("INSTAGRAM_USER_ID"))


def is_connected() -> bool:
    account = oauth_store.get_account(PLATFORM)
    return bool(account and account.get("refresh_token"))


def status() -> dict:
    if not is_configured():
        eksik = [k for k in ("INSTAGRAM_APP_ID", "INSTAGRAM_APP_SECRET", "INSTAGRAM_USER_ID")
                 if not os.getenv(k)]
        reason = f"eksik: {', '.join(eksik)} (developers.facebook.com'da Business app gerekli)"
    elif not is_connected():
        reason = "yapilandirildi ama hesap baglanmamis — /api/social/instagram/start"
    else:
        reason = "bagli (yayin icin App Review onayi da gerekir)"
    return {"platform": PLATFORM, "configured": is_configured(),
            "connected": is_connected(),
            "quota_left_today": oauth_store.quota_left(PLATFORM), "reason": reason}


def auth_url(redirect_uri: str = DEFAULT_REDIRECT, state: str = "") -> Optional[str]:
    if not is_configured():
        return None
    return AUTH_ENDPOINT + "?" + urlencode({
        "client_id": os.getenv("INSTAGRAM_APP_ID"),
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": SCOPES,
        **({"state": state} if state else {}),
    })


def exchange_code(code: str, redirect_uri: str = DEFAULT_REDIRECT) -> tuple[bool, str]:
    """
    Kisa omurlu belirteci alip UZUN OMURLU olanla degistirir (Meta'da yenileme
    belirteci yok; 60 gunluk uzun omurlu belirtec kullanilir ve tazelenir).
    """
    if not is_configured():
        return False, "INSTAGRAM_APP_ID/SECRET/USER_ID tanimli degil"
    import requests
    try:
        short = requests.get(TOKEN_ENDPOINT, params={
            "client_id": os.getenv("INSTAGRAM_APP_ID"),
            "client_secret": os.getenv("INSTAGRAM_APP_SECRET"),
            "redirect_uri": redirect_uri, "code": code}, timeout=30)
        if short.status_code != 200:
            return False, f"token reddedildi (HTTP {short.status_code}): {short.text[:200]}"

        long_lived = requests.get(TOKEN_ENDPOINT, params={
            "grant_type": "fb_exchange_token",
            "client_id": os.getenv("INSTAGRAM_APP_ID"),
            "client_secret": os.getenv("INSTAGRAM_APP_SECRET"),
            "fb_exchange_token": short.json().get("access_token", "")}, timeout=30)
    except Exception as exc:
        return False, f"token istegi basarisiz: {exc}"

    if long_lived.status_code != 200:
        return False, f"uzun omurlu belirtec alinamadi: {long_lived.text[:200]}"
    token = long_lived.json().get("access_token")
    if not token:
        return False, "belirtec donmedi"

    # Meta'da refresh_token yok; uzun omurlu belirteci ayni alanda saklariz.
    oauth_store.save_account(PLATFORM, refresh_token=token, account_label="Instagram",
                             extra={"token_type": "long_lived"})
    return True, "Instagram hesabi baglandi (belirtec 60 gun gecerli)"


def _access_token() -> Optional[str]:
    account = oauth_store.get_account(PLATFORM)
    return account.get("refresh_token") if account else None


def publish_reel(
    *,
    video_url: str,
    caption: str,
    share_to_feed: bool = True,
) -> ReelResult:
    """
    Reels yayinlar. video_url HERKESE ACIK olmali — Instagram videoyu kendisi
    indirir, dosya yuklemesi kabul etmez.
    """
    if not video_url.startswith("http"):
        return ReelResult(False, error="video herkese acik bir URL olmali (yerel yol calismaz)")
    if not is_connected():
        return ReelResult(False, error="Instagram hesabi bagli degil")
    if oauth_store.quota_left(PLATFORM) <= 0:
        return ReelResult(False, error="gunluk yayin kotasi doldu")

    token = _access_token()
    user_id = os.getenv("INSTAGRAM_USER_ID")
    if not token or not user_id:
        return ReelResult(False, error="erisim belirteci veya kullanici kimligi yok")

    import requests
    try:
        container = requests.post(f"{GRAPH_BASE}/{user_id}/media", data={
            "media_type": "REELS", "video_url": video_url,
            "caption": caption[:2200],
            "share_to_feed": "true" if share_to_feed else "false",
            "access_token": token}, timeout=60)
    except Exception as exc:
        return ReelResult(False, error=f"container olusturulamadi: {str(exc)[:200]}")
    if container.status_code != 200:
        return ReelResult(False, error=f"container HTTP {container.status_code}: {container.text[:250]}")

    creation_id = container.json().get("id")
    if not creation_id:
        return ReelResult(False, error="container kimligi donmedi")

    # Instagram videoyu indirip isler; hazir olmadan yayinlanamaz.
    beklendi = 0
    while beklendi < CONTAINER_MAX_WAIT:
        try:
            durum = requests.get(f"{GRAPH_BASE}/{creation_id}",
                                 params={"fields": "status_code", "access_token": token},
                                 timeout=30)
            kod = durum.json().get("status_code") if durum.status_code == 200 else None
        except Exception:
            kod = None
        if kod == "FINISHED":
            break
        if kod == "ERROR":
            return ReelResult(False, error="Instagram videoyu isleyemedi (format/sure uygun mu?)")
        time.sleep(CONTAINER_POLL_SECONDS)
        beklendi += CONTAINER_POLL_SECONDS
    else:
        return ReelResult(False, error=f"video {CONTAINER_MAX_WAIT} sn icinde islenmedi")

    try:
        published = requests.post(f"{GRAPH_BASE}/{user_id}/media_publish",
                                  data={"creation_id": creation_id, "access_token": token},
                                  timeout=60)
    except Exception as exc:
        return ReelResult(False, error=f"yayinlanamadi: {str(exc)[:200]}")
    if published.status_code != 200:
        return ReelResult(False, error=f"publish HTTP {published.status_code}: {published.text[:250]}")

    oauth_store.record_publish(PLATFORM)
    return ReelResult(True, media_id=published.json().get("id", ""))
