"""
Sosyal medya OAuth belirtec deposu + gunluk kota sayaci.

Belirtecler `data/social_tokens.json` icinde tutulur. Bu dosya SIR icerir:
- .gitignore'a eklenir,
- POSIX'te 0600 izniyle yazilir,
- hicbir log/olay mesajina belirtec YAZILMAZ (sadece "bagli/degil" bilgisi).

Kota: her platformun gunluk yayin butcesi burada sayilir. YouTube'un kendi
kota hesabi da var (videos.insert = 1600 birim, gunluk 10.000 -> ~6 video),
ama biz kendi sayacimizi tutariz ki kota dolmadan once duralim.
"""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from typing import Optional

STORE_PATH = Path(__file__).resolve().parent.parent / "data" / "social_tokens.json"

# Platform basina gunluk yayin tavani (muhafazakar; kota duvarina toslamamak icin)
DAILY_LIMITS = {
    "youtube": 4,     # API tavani ~6; 4 ile guvenli marj birakiyoruz
    "instagram": 8,
    "tiktok": 4,
    "pinterest": 10,
}


def _read() -> dict:
    if not STORE_PATH.exists():
        return {"accounts": {}, "usage": {}}
    try:
        with open(STORE_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {"accounts": {}, "usage": {}}


def _write(data: dict) -> None:
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STORE_PATH.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    tmp.replace(STORE_PATH)
    try:
        os.chmod(STORE_PATH, 0o600)   # Windows'ta etkisiz, POSIX'te gerekli
    except Exception:
        pass


def save_account(platform: str, *, refresh_token: str, account_label: str = "",
                 extra: Optional[dict] = None) -> None:
    """Yenileme belirtecini saklar. Erisim belirteci saklanmaz — her seferinde tazelenir."""
    data = _read()
    data["accounts"][platform] = {
        "refresh_token": refresh_token,
        "account_label": account_label,
        **(extra or {}),
    }
    _write(data)


def get_account(platform: str) -> Optional[dict]:
    return _read()["accounts"].get(platform)


def forget_account(platform: str) -> bool:
    data = _read()
    if platform in data["accounts"]:
        del data["accounts"][platform]
        _write(data)
        return True
    return False


def connected_platforms() -> dict:
    """
    Arayuz/teshis icin GUVENLI ozet: belirtecin kendisi ASLA dondurulmez,
    yalnizca bagli olup olmadigi ve bugun kac yayin yapildigi.
    """
    data = _read()
    today = date.today().isoformat()
    out = {}
    for platform, limit in DAILY_LIMITS.items():
        account = data["accounts"].get(platform)
        out[platform] = {
            "connected": bool(account and account.get("refresh_token")),
            "account_label": (account or {}).get("account_label", ""),
            "used_today": data["usage"].get(today, {}).get(platform, 0),
            "daily_limit": limit,
        }
    return out


def quota_left(platform: str) -> int:
    data = _read()
    today = date.today().isoformat()
    used = data["usage"].get(today, {}).get(platform, 0)
    return max(0, DAILY_LIMITS.get(platform, 0) - used)


def record_publish(platform: str) -> None:
    """Basarili bir yayindan SONRA cagrilir (denenen degil, olan sayilir)."""
    data = _read()
    today = date.today().isoformat()
    day = data["usage"].setdefault(today, {})
    day[platform] = day.get(platform, 0) + 1
    # Eski gunleri biriktirme
    for old in [k for k in data["usage"] if k < today]:
        del data["usage"][old]
    _write(data)
