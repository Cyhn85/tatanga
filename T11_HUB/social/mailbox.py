"""
IMAP posta kutusu okuyucu — SALT OKUNUR.

Bu modul e-posta GONDEREMEZ. Yalnizca okur ve okundu isaretler. Gonderme
yetkisi bilincli olarak yok: gelen posta guvenilmez girdidir ve bu hattin
ucundaki her cikti insan onayindan gecmeli (bkz. logic/mail_triage).

Yapilandirma (.env — degerleri KULLANICI kendi girer, sohbete yazilmaz):
    MAIL_IMAP_HOST=imap.gmail.com
    MAIL_IMAP_PORT=993
    MAIL_IMAP_USER=...
    MAIL_IMAP_PASSWORD=...        # Gmail'de "uygulama sifresi"
    MAIL_IMAP_FOLDER=INBOX        # istege bagli

Gmail icin normal hesap sifresi CALISMAZ; iki adimli dogrulama acikken
uretilen bir "uygulama sifresi" gerekir. Bu, sifreyi paylasmadan sinirli
erisim vermenin dogru yolu ve istendigi an tek tikla iptal edilebilir.
"""

from __future__ import annotations

import email
import imaplib
import os
from dataclasses import dataclass, field
from email.header import decode_header, make_header
from typing import Optional

MAX_BODY_CHARS = 4000


@dataclass
class MailMessage:
    uid: str
    sender: str
    subject: str
    body: str
    headers: dict = field(default_factory=dict)


def is_configured() -> bool:
    return all(os.getenv(k) for k in
               ("MAIL_IMAP_HOST", "MAIL_IMAP_USER", "MAIL_IMAP_PASSWORD"))


def status() -> dict:
    """Neden calismadigi acikca gorunsun — sessiz basarisizlik olmasin."""
    if not is_configured():
        eksik = [k for k in ("MAIL_IMAP_HOST", "MAIL_IMAP_USER", "MAIL_IMAP_PASSWORD")
                 if not os.getenv(k)]
        return {"configured": False, "reason": f".env'de eksik: {', '.join(eksik)}"}
    return {"configured": True, "user": os.getenv("MAIL_IMAP_USER"),
            "folder": os.getenv("MAIL_IMAP_FOLDER", "INBOX"), "reason": "hazir"}


def _decode(value: Optional[str]) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def _extract_body(message) -> str:
    """Duz metin govdeyi cikarir; yoksa HTML'i kaba sekilde metne indirger."""
    if not message.is_multipart():
        try:
            return message.get_payload(decode=True).decode(errors="replace")[:MAX_BODY_CHARS]
        except Exception:
            return ""
    text, html = "", ""
    for part in message.walk():
        ctype = part.get_content_type()
        if part.get("Content-Disposition", "").startswith("attachment"):
            continue
        try:
            payload = part.get_payload(decode=True).decode(errors="replace")
        except Exception:
            continue
        if ctype == "text/plain" and not text:
            text = payload
        elif ctype == "text/html" and not html:
            html = payload
    if text:
        return text[:MAX_BODY_CHARS]
    import re
    return re.sub(r"<[^>]+>", " ", html)[:MAX_BODY_CHARS]


def fetch_unseen(limit: int = 20, mark_seen: bool = True) -> list[MailMessage]:
    """
    Okunmamis mesajlari getirir. Yapilandirma yoksa BOS liste doner (patlamaz).
    mark_seen=False ile salt-okunur deneme yapilabilir.
    """
    if not is_configured():
        return []

    host = os.getenv("MAIL_IMAP_HOST")
    port = int(os.getenv("MAIL_IMAP_PORT", "993"))
    folder = os.getenv("MAIL_IMAP_FOLDER", "INBOX")

    out: list[MailMessage] = []
    try:
        conn = imaplib.IMAP4_SSL(host, port)
        conn.login(os.getenv("MAIL_IMAP_USER"), os.getenv("MAIL_IMAP_PASSWORD"))
        conn.select(folder, readonly=not mark_seen)
        typ, data = conn.search(None, "UNSEEN")
        if typ != "OK":
            conn.logout()
            return []

        uids = data[0].split()[-limit:]
        for uid in uids:
            typ, raw = conn.fetch(uid, "(RFC822)")
            if typ != "OK" or not raw or not raw[0]:
                continue
            message = email.message_from_bytes(raw[0][1])
            out.append(MailMessage(
                uid=uid.decode(),
                sender=_decode(message.get("From")),
                subject=_decode(message.get("Subject")),
                body=_extract_body(message),
                headers={k: v for k, v in message.items()},
            ))
        try:
            conn.close()
        except Exception:
            pass
        conn.logout()
    except Exception:
        return out  # kismi sonuc dondur, cokme yok
    return out
