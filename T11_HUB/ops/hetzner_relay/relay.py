#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TATANGA posta rolesi — Hetzner'de 7/24 calisan KUCUK servis.

NEDEN AYRI BIR SERVIS: Asil Hub kullanicinin bilgisayarinda calisiyor ve makine
kapaliyken hicbir sey duyulmuyor. Musteri mesaji, satis bildirimi, odeme haberi
saatlerce beklerse "interaktif sistem" olmaz. Bu servis sunucuda durur, posta
kutusunu dinler ve olan biteni Telegram'a duser.

NEDEN TUM HUB TASINMADI: Kazima Chrome/Selenium istiyor (~1 GB RAM), gorsel ve
ses modelleri yuzlerce MB. Sunucuda 3.8 GB RAM ve 5.6 GB bos disk var; agir
isler orada calismaz. Bu servis ise SIFIR bagimlilik kullanir (yalnizca Python
standart kutuphanesi) ve ~50 MB bellek harcar.

SINIR — asil Hub'daki ile ayni: OKUR, siniflandirir, Telegram'a bildirir.
E-posta GONDERMEZ, hicbir islem tetiklemez. Gelen postanin icerigi komut
olarak yorumlanmaz (bkz. logic/mail_triage.py).
"""

from __future__ import annotations

import email
import html
import imaplib
import json
import os
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
from email.header import decode_header, make_header
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from logic.mail_triage import classify_mail  # noqa: E402

DB_PATH = BASE / "relay.db"
POLL_SECONDS = int(os.getenv("RELAY_POLL_SECONDS", "300"))   # 5 dk
BATCH = 15
MAX_BODY = 4000


# ----------------------------------------------------------------- yapilandirma
def load_env() -> None:
    """Yanindaki .env dosyasini okur (sir degerler yalnizca sunucuda durur)."""
    env_file = BASE / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def configured() -> bool:
    return all(os.getenv(k) for k in
               ("MAIL_IMAP_HOST", "MAIL_IMAP_USER", "MAIL_IMAP_PASSWORD",
                "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"))


def missing_keys() -> list[str]:
    return [k for k in ("MAIL_IMAP_HOST", "MAIL_IMAP_USER", "MAIL_IMAP_PASSWORD",
                        "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")
            if not os.getenv(k)]


# ------------------------------------------------------------------------- db
def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS seen (
        uid TEXT PRIMARY KEY, category TEXT, subject TEXT, created_at TEXT)""")
    conn.commit()
    return conn


# -------------------------------------------------------------------- telegram
def notify(text: str) -> bool:
    """Telegram'a bildirim. Basarisizlik sessizce yutulmaz, log'a yazilir."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    payload = urllib.parse.urlencode({
        "chat_id": chat_id, "text": text[:4000],
        "parse_mode": "HTML", "disable_web_page_preview": "true",
    }).encode()
    try:
        request = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage", data=payload)
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status == 200
    except Exception as exc:
        print(f"[relay] telegram hatasi: {exc}", flush=True)
        return False


# ------------------------------------------------------------------------ imap
def _decode(value):
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return str(value)


def _body(message) -> str:
    if not message.is_multipart():
        try:
            return message.get_payload(decode=True).decode(errors="replace")[:MAX_BODY]
        except Exception:
            return ""
    for part in message.walk():
        if part.get_content_type() == "text/plain" and \
           not part.get("Content-Disposition", "").startswith("attachment"):
            try:
                return part.get_payload(decode=True).decode(errors="replace")[:MAX_BODY]
            except Exception:
                continue
    return ""


def fetch_unseen():
    out = []
    try:
        conn = imaplib.IMAP4_SSL(os.getenv("MAIL_IMAP_HOST"),
                                 int(os.getenv("MAIL_IMAP_PORT", "993")))
        conn.login(os.getenv("MAIL_IMAP_USER"), os.getenv("MAIL_IMAP_PASSWORD"))
        conn.select(os.getenv("MAIL_IMAP_FOLDER", "INBOX"))
        typ, data = conn.search(None, "UNSEEN")
        if typ == "OK":
            for uid in data[0].split()[-BATCH:]:
                typ, raw = conn.fetch(uid, "(RFC822)")
                if typ != "OK" or not raw or not raw[0]:
                    continue
                msg = email.message_from_bytes(raw[0][1])
                out.append((uid.decode(), _decode(msg.get("From")),
                            _decode(msg.get("Subject")), _body(msg),
                            {k: v for k, v in msg.items()}))
        conn.close()
        conn.logout()
    except Exception as exc:
        print(f"[relay] imap hatasi: {exc}", flush=True)
    return out


# ------------------------------------------------------------------------ tur
ICON = {"customer_message": "👤", "finance": "💶", "platform_notification": "🔔",
        "marketing": "📣", "other": "✉️"}


def run_once() -> int:
    conn = db()
    işlenen = 0
    for uid, sender, subject, body, headers in fetch_unseen():
        if conn.execute("SELECT 1 FROM seen WHERE uid=?", (uid,)).fetchone():
            continue
        verdict = classify_mail(sender=sender, subject=subject,
                                body=body, headers=headers)

        # E-posta alanlari HTML kacisindan GECMELI: gonderen adresi
        # 'Vinted <noreply@vinted.de>' seklinde gelir ve icindeki < > karakterleri
        # Telegram'in HTML ayrisricisini bozar (HTTP 400 Bad Request).
        esc = html.escape
        parcalar = [f"{ICON.get(verdict.category, '✉️')} <b>{esc(verdict.label)}</b>",
                    f"<i>{esc(sender[:80])}</i>", esc(verdict.summary)]
        if verdict.draft_reply:
            parcalar += ["", f"<b>Taslak yanit ({esc(verdict.draft_lang)}):</b>",
                         f"<code>{esc(verdict.draft_reply[:900])}</code>",
                         "", "⚠️ Gonderilmedi — onay sizde."]
        if verdict.warnings:
            parcalar.append(f"⚑ {esc(', '.join(verdict.warnings)[:200])}")
        # SIRA ONEMLI: once bildir, ANCAK basarili olursa "gorulmus" isaretle.
        # Tersi yapilirsa Telegram bir hata verdiginde posta sessizce yutulur ve
        # bir daha hic bildirilmez — gercekten yasandi, 15 bildirim boyle kayboldu.
        if not notify("\n".join(parcalar)):
            print(f"[relay] bildirilemedi, tekrar denenecek: {subject[:60]}", flush=True)
            continue

        conn.execute("INSERT OR IGNORE INTO seen VALUES (?,?,?,datetime('now'))",
                     (uid, verdict.category, subject[:200]))
        conn.commit()
        işlenen += 1
    conn.close()
    return işlenen


def main() -> None:
    load_env()
    if not configured():
        print(f"[relay] yapilandirilmamis, eksik: {', '.join(missing_keys())}", flush=True)
        print("[relay] .env doldurulunca servis kendiliginden calismaya baslar", flush=True)
    print(f"[relay] basladi — her {POLL_SECONDS} sn kontrol", flush=True)
    while True:
        if configured():
            try:
                count = run_once()
                if count:
                    print(f"[relay] {count} yeni posta islendi", flush=True)
            except Exception as exc:
                print(f"[relay] beklenmeyen hata: {exc}", flush=True)
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
