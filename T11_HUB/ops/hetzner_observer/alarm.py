#!/usr/bin/env python3
"""
Saglama alarmi: saatte bir calisir (systemd timer). Durdurucu bir test (FAIL) 1 saatten uzun
surerse Telegram'a TEK mesaj atar; duzelince "duzeldi" mesaji atar. Ayni sorun icin tekrar
tekrar mesaj gondermez.

Neden: 2026-10-07'de testler sorunu yakaladi ama kimse gormedi; sistem 36 saat bos calisti.

Telegram anahtarlari tatanga-relay servisinin kendi .env dosyasindan SADECE okunur,
baska yere kopyalanmaz.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE_DIR, "alarm_state.json")
RELAY_ENV = "/opt/tatanga-relay/.env"
GRACE_MINUTES = 60

sys.path.insert(0, BASE_DIR)
from saglama import FAIL, connect, run_checks  # noqa: E402


def telegram_keys() -> tuple[str, str] | None:
    keys = {}
    try:
        for line in open(RELAY_ENV, encoding="utf-8"):
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.strip().split("=", 1)
                keys[k.strip()] = v.strip()
    except OSError:
        return None
    token, chat = keys.get("TELEGRAM_BOT_TOKEN"), keys.get("TELEGRAM_CHAT_ID")
    return (token, chat) if token and chat else None


def send(text: str) -> bool:
    keys = telegram_keys()
    if not keys:
        print("telegram anahtari yok, mesaj gonderilemedi")
        return False
    token, chat = keys
    data = urllib.parse.urlencode({"chat_id": chat, "text": text[:3500]}).encode()
    try:
        urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", data=data, timeout=20)
        return True
    except Exception as exc:
        print(f"telegram hatasi: {type(exc).__name__}")
        return False


def main() -> int:
    now = datetime.now(timezone.utc)
    state = json.load(open(STATE_FILE)) if os.path.exists(STATE_FILE) else {}
    conn = connect()
    fails = [(code, text) for lvl, code, text in run_checks(conn) if lvl == FAIL]

    if not fails:
        if state.get("alerted"):
            send("✅ TATANGA gozlemci DUZELDI. Tum durdurucu testler gecti.")
        json.dump({}, open(STATE_FILE, "w"))
        print("temiz")
        return 0

    since = state.get("since") or now.isoformat()
    minutes = (now - datetime.fromisoformat(since)).total_seconds() / 60
    if minutes >= GRACE_MINUTES and not state.get("alerted"):
        errs = conn.execute(
            "SELECT ts, market, stage, outcome, detail FROM error_log ORDER BY id DESC LIMIT 3").fetchall()
        lines = [f"🚨 TATANGA gozlemci: {len(fails)} durdurucu test {int(minutes)} dakikadir kirmizi"]
        lines += [f"• {code} {text}" for code, text in fails]
        lines += ["Son hatalar:"] + [f"  {e[0][11:16]} {e[1]} {e[2]} {e[3]} {e[4][:50]}" for e in errs]
        lines.append("Kontrol: cd /opt/tatanga-observer && ./venv/bin/python saglama.py")
        state["alerted"] = send("\n".join(lines))
    state["since"] = since
    json.dump(state, open(STATE_FILE, "w"))
    print(f"FAIL {len(fails)} test, {int(minutes)} dk, uyari gonderildi={state.get('alerted', False)}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
