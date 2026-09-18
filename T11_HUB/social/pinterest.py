"""
Pinterest API v5 — pin olusturma (resmi API, OAuth 2.0).

ERISIM KADEMELERI (Pinterest'in kendi kurali, atlanamaz):
  Trial    -> yalnizca OKUMA kapsamlari. pins:write YOK.
  Standard -> pins:write acilir. Basvuru icin calisan akisin video kaydi istenir.
Yani bu modul yazilmis olsa bile, Standard erisim gelene kadar gercek pin
atamaz. Bunu sessizce denemek yerine status() acikca soyler.

Pinterest dokumantasyonu ayrica sunu yaziyor: kullanici giris bilgisi ya da
oturum cerezi toplayan uygulamalarin yukseltme talebi REDDEDILIR. Bu modul
yalnizca OAuth kullanir; sifre gormez, saklamaz.

Gerekli ortam degiskenleri:
    PINTEREST_APP_ID, PINTEREST_APP_SECRET
"""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlencode

from . import oauth_store

AUTH_ENDPOINT = "https://www.pinterest.com/oauth/"
TOKEN_ENDPOINT = "https://api.pinterest.com/v5/oauth/token"
API_BASE = "https://api.pinterest.com/v5"

SCOPES = "pins:write,boards:read,user_accounts:read"
DEFAULT_REDIRECT = "http://localhost:8501/api/social/pinterest/callback"
PLATFORM = "pinterest"


@dataclass
class PinResult:
    ok: bool
    pin_id: str = ""
    url: str = ""
    error: str = ""


def is_configured() -> bool:
    return bool(os.getenv("PINTEREST_APP_ID") and os.getenv("PINTEREST_APP_SECRET"))


def is_connected() -> bool:
    account = oauth_store.get_account(PLATFORM)
    return bool(account and account.get("refresh_token"))


def status() -> dict:
    if not is_configured():
        reason = "PINTEREST_APP_ID/SECRET tanimli degil (developers.pinterest.com'da uygulama gerekli)"
    elif not is_connected():
        reason = "yapilandirildi ama hesap baglanmamis — /api/social/pinterest/start"
    else:
        reason = "bagli (pin atabilmek icin Pinterest'ten Standard erisim de gerekir)"
    return {"platform": PLATFORM, "configured": is_configured(),
            "connected": is_connected(),
            "quota_left_today": oauth_store.quota_left(PLATFORM), "reason": reason}


def auth_url(redirect_uri: str = DEFAULT_REDIRECT, state: str = "") -> Optional[str]:
    if not is_configured():
        return None
    return AUTH_ENDPOINT + "?" + urlencode({
        "client_id": os.getenv("PINTEREST_APP_ID"),
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": SCOPES,
        **({"state": state} if state else {}),
    })


def _basic_auth_header() -> str:
    raw = f"{os.getenv('PINTEREST_APP_ID')}:{os.getenv('PINTEREST_APP_SECRET')}"
    return "Basic " + base64.b64encode(raw.encode()).decode()


def exchange_code(code: str, redirect_uri: str = DEFAULT_REDIRECT) -> tuple[bool, str]:
    if not is_configured():
        return False, "PINTEREST_APP_ID/SECRET tanimli degil"
    import requests
    try:
        resp = requests.post(
            TOKEN_ENDPOINT,
            headers={"Authorization": _basic_auth_header(),
                     "Content-Type": "application/x-www-form-urlencoded"},
            data={"grant_type": "authorization_code", "code": code,
                  "redirect_uri": redirect_uri},
            timeout=30)
    except Exception as exc:
        return False, f"token istegi basarisiz: {exc}"
    if resp.status_code != 200:
        return False, f"token reddedildi (HTTP {resp.status_code}): {resp.text[:200]}"

    payload = resp.json()
    refresh = payload.get("refresh_token")
    if not refresh:
        return False, "yenileme belirteci donmedi"
    oauth_store.save_account(PLATFORM, refresh_token=refresh, account_label="Pinterest")
    return True, "Pinterest hesabi baglandi"


def _access_token() -> Optional[str]:
    account = oauth_store.get_account(PLATFORM)
    if not account or not is_configured():
        return None
    import requests
    try:
        resp = requests.post(
            TOKEN_ENDPOINT,
            headers={"Authorization": _basic_auth_header(),
                     "Content-Type": "application/x-www-form-urlencoded"},
            data={"grant_type": "refresh_token",
                  "refresh_token": account["refresh_token"]},
            timeout=30)
    except Exception:
        return None
    return resp.json().get("access_token") if resp.status_code == 200 else None


def list_boards() -> list[dict]:
    """Pin atmak icin pano kimligi gerekir; kullanici hangisine atacagini secer."""
    token = _access_token()
    if not token:
        return []
    import requests
    try:
        resp = requests.get(f"{API_BASE}/boards", params={"page_size": 25},
                            headers={"Authorization": f"Bearer {token}"}, timeout=30)
        if resp.status_code != 200:
            return []
        return [{"id": b.get("id"), "name": b.get("name")}
                for b in resp.json().get("items", [])]
    except Exception:
        return []


def create_pin(
    *,
    board_id: str,
    image_url: str,
    title: str,
    description: str = "",
    link: str = "https://cssberlin.de",
) -> PinResult:
    """
    Gorsel pin olusturur. Pinterest ONCE gorseli kendi indirir; bu yuzden
    image_url HERKESE ACIK olmali (yerel dosya yolu ise calismaz).
    """
    if not is_connected():
        return PinResult(False, error="Pinterest hesabi bagli degil")
    if oauth_store.quota_left(PLATFORM) <= 0:
        return PinResult(False, error="gunluk yayin kotasi doldu")
    if not image_url.startswith("http"):
        return PinResult(False, error="gorsel herkese acik bir URL olmali (yerel yol kabul edilmez)")

    token = _access_token()
    if not token:
        return PinResult(False, error="erisim belirteci alinamadi")

    import requests
    try:
        resp = requests.post(
            f"{API_BASE}/pins",
            headers={"Authorization": f"Bearer {token}",
                     "Content-Type": "application/json"},
            json={"board_id": board_id,
                  "title": title[:100],
                  "description": description[:500],
                  "link": link,
                  "media_source": {"source_type": "image_url", "url": image_url}},
            timeout=60)
    except Exception as exc:
        return PinResult(False, error=f"pin olusturulamadi: {str(exc)[:200]}")

    if resp.status_code not in (200, 201):
        # 403 genelde "Standard erisim yok" demektir — gerekce aynen tasinir.
        return PinResult(False, error=f"HTTP {resp.status_code}: {resp.text[:250]}")

    pin_id = resp.json().get("id", "")
    oauth_store.record_publish(PLATFORM)
    return PinResult(True, pin_id=pin_id, url=f"https://www.pinterest.com/pin/{pin_id}/")
