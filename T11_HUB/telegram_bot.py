#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TATANGA Telegram Bot - Unified v2
=================================
Eski legacy bot (telegram_bot/ klasoru) + T11_HUB bot birlestirildi.
Tek bot, coklu kanal, T11_HUB API uzerinden calisir.

Kanal Yapisi (minimize edildi):
  - BILDIRIMLER : Urun eklendi, kazima, yayinlandi, satildi, karli urunler
  - SISTEM HATA : Hatalar, loglar, sistem durumu, uyarilar
  - CAPTCHA      : Manuel islem gereken durumlar (SMS, cookie onayi)
  - ADMIN (DM)   : Komutlar, URL ekleme, sorgular

Cakisma Yonetimi (PC/Mobil):
  - Telegram Bot API sadece 1 polling/webhook destekler.
  - Bu bot POLLING kullanir ve tek bir process'te calisir.
  - PC ve mobilden AYNI ANDA mesaj gonderilebilir - sorun yok.
"""

import asyncio
import json
import os
import sys
import time
import logging
from pathlib import Path
from datetime import datetime

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [TELEGRAM] %(message)s')
logger = logging.getLogger("telegram_bot")

# ============================================
# CONFIGURATION
# ============================================
BOT_TOKEN = ""
HUB_API_URL = "http://localhost:8501"

# Kanal / Grup Chat ID'leri
CHANNELS = {
    "admin": 5149567290,            # Ana DM - komutlar (css kullanici)
    "bildirimler": -5067377770,     # TATANGA - Bildirimler
    "sistem_hata": -5056933851,     # TATANGA - Sistem hata
    "captcha": -5090446180,         # TATANGA - CAPTCHA / CEREZ ONAYI
    # Kampanya odasi: uretilen reklam metinleri ONAY icin buraya duser.
    # Ayri bir grup acilana kadar admin DM'ine gider (yanlis odaya dusmesin).
    "kampanya": 5149567290,
}

# Eski gruplar (kullanilmiyor ama referans icin)
LEGACY_CHANNELS = {
    "messages": -5052367604,        # TATANGA - Mesajlar
    "sales": -5094670256,           # TATANGA - Satislar
    "shipping": -5093349867,        # TATANGA - Kargo
    "scrape_command": -5038357725,  # TATANGA - URUN KAZIMA BASLAT
    "product_found": -5038660282,   # TATANGA - URUN BULDUM
    "store_transfer": -5079922151,  # TATANGA - Magazalar arasi transfer
}

# Izin verilen chat ID'leri (admin + aktif kanallar)
ALLOWED_CHAT_IDS = [
    CHANNELS["admin"],
    CHANNELS["bildirimler"],
    CHANNELS["sistem_hata"],
    CHANNELS["captcha"],
]

# Config dosyasindan oku
CONFIG_PATH = Path(__file__).parent / "data" / "telegram_config.json"


def load_config():
    """Config dosyasini oku ve globalleri guncelle"""
    global BOT_TOKEN, CHANNELS, ALLOWED_CHAT_IDS

    # Oncelikle credentials.py'den oku
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from shared.config.credentials import TELEGRAM
        BOT_TOKEN = TELEGRAM.get("bot_token", "")

        # Channel bilgilerini credentials'dan al
        ch = TELEGRAM.get("channels", {})
        if ch.get("notifications"):
            CHANNELS["bildirimler"] = ch["notifications"]
        if ch.get("system"):
            CHANNELS["sistem_hata"] = ch["system"]
        if ch.get("captcha_approval"):
            CHANNELS["captcha"] = ch["captcha_approval"]
        if ch.get("general"):
            CHANNELS["admin"] = ch["general"]

        ALLOWED_CHAT_IDS = list(set([
            CHANNELS["admin"],
            CHANNELS["bildirimler"],
            CHANNELS["sistem_hata"],
            CHANNELS["captcha"],
        ]))

        logger.info(f"Credentials yuklendi: bot={TELEGRAM.get('bot_username', '?')}")
    except ImportError:
        logger.warning("credentials.py bulunamadi, config dosyasindan yuklenecek")

    # Config dosyasi override
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                if cfg.get("bot_token"):
                    BOT_TOKEN = cfg["bot_token"]
                if cfg.get("channels"):
                    CHANNELS.update(cfg["channels"])
                if cfg.get("allowed_chat_ids"):
                    ALLOWED_CHAT_IDS = list(set(ALLOWED_CHAT_IDS + cfg["allowed_chat_ids"]))
        except Exception as e:
            logger.error(f"Config okuma hatasi: {e}")

    return {
        "bot_token": BOT_TOKEN,
        "channels": CHANNELS,
        "allowed_chat_ids": ALLOWED_CHAT_IDS,
    }


def save_config(token=None, chat_ids=None, channels=None):
    """Config dosyasina kaydet"""
    global BOT_TOKEN, ALLOWED_CHAT_IDS, CHANNELS
    if token:
        BOT_TOKEN = token
    if chat_ids is not None:
        ALLOWED_CHAT_IDS = chat_ids
    if channels:
        CHANNELS.update(channels)

    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump({
            "bot_token": BOT_TOKEN,
            "channels": CHANNELS,
            "allowed_chat_ids": ALLOWED_CHAT_IDS,
        }, f, indent=2, ensure_ascii=False)


# ============================================
# TELEGRAM API WRAPPER
# ============================================
import requests as req_lib


class TelegramBot:
    def __init__(self, token: str):
        self.token = token
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.offset = 0
        self.running = False

    def api(self, method: str, data: dict = None, files: dict = None) -> dict:
        """Telegram API cagirisi"""
        try:
            url = f"{self.base_url}/{method}"
            if files:
                resp = req_lib.post(url, data=data, files=files, timeout=30)
            elif data:
                resp = req_lib.post(url, json=data, timeout=30)
            else:
                resp = req_lib.get(url, timeout=30)
            return resp.json()
        except Exception as e:
            logger.error(f"API error ({method}): {e}")
            return {"ok": False, "error": str(e)}

    def send_message(self, chat_id, text: str, parse_mode: str = "HTML",
                     reply_markup: dict = None, disable_preview: bool = True) -> dict:
        data = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": disable_preview,
        }
        if reply_markup:
            data["reply_markup"] = reply_markup
        return self.api("sendMessage", data)

    def send_photo(self, chat_id, photo_url: str, caption: str = "") -> dict:
        return self.api("sendPhoto", {
            "chat_id": chat_id,
            "photo": photo_url,
            "caption": caption[:1024],
            "parse_mode": "HTML",
        })

    def get_updates(self, timeout: int = 30) -> list:
        result = self.api("getUpdates", {
            "offset": self.offset,
            "timeout": timeout,
            "allowed_updates": ["message", "callback_query"],
        })
        if result.get("ok"):
            updates = result.get("result", [])
            if updates:
                self.offset = updates[-1]["update_id"] + 1
            return updates
        return []

    def get_me(self) -> dict:
        return self.api("getMe")

    def answer_callback(self, callback_query_id: str, text: str = "") -> dict:
        return self.api("answerCallbackQuery", {
            "callback_query_id": callback_query_id,
            "text": text,
        })

    def edit_message(self, chat_id, message_id: int, text: str,
                     parse_mode: str = "HTML", reply_markup: dict = None) -> dict:
        data = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": parse_mode,
        }
        if reply_markup:
            data["reply_markup"] = reply_markup
        return self.api("editMessageText", data)


# ============================================
# AUTHORIZATION
# ============================================
def is_allowed(chat_id) -> bool:
    """Chat ID izin kontrolu"""
    if not ALLOWED_CHAT_IDS:
        return True
    return chat_id in ALLOWED_CHAT_IDS


def is_url(text: str) -> bool:
    return text.startswith("http://") or text.startswith("https://")


def is_supported_url(url: str) -> bool:
    platforms = ["vinted", "ebay", "kleinanzeigen", "willhaben", "sellpy", "tradera", "leboncoin"]
    return any(p in url.lower() for p in platforms)


# ============================================
# CHANNEL-SPECIFIC SEND FUNCTIONS
# ============================================
def send_to_channel(channel_key: str, text: str, parse_mode: str = "HTML"):
    """Belirli bir kanala mesaj gonder"""
    bot = get_bot()
    if not bot:
        return
    chat_id = CHANNELS.get(channel_key)
    if not chat_id:
        logger.warning(f"Kanal bulunamadi: {channel_key}")
        return
    try:
        return bot.send_message(chat_id, text, parse_mode)
    except Exception as e:
        logger.error(f"Kanal mesaj hatasi ({channel_key}): {e}")


def send_to_bildirimler(text: str):
    """Bildirim kanalina gonder"""
    return send_to_channel("bildirimler", text)


def send_to_sistem_hata(text: str):
    """Sistem hata kanalina gonder"""
    return send_to_channel("sistem_hata", text)


def send_to_captcha(text: str, reply_markup: dict = None):
    """CAPTCHA kanalina gonder"""
    bot = get_bot()
    if not bot:
        return
    chat_id = CHANNELS.get("captcha")
    if chat_id:
        return bot.send_message(chat_id, text, reply_markup=reply_markup)


def send_to_admin(text: str):
    """Admin DM'e gonder"""
    return send_to_channel("admin", text)


# ============================================
# MESSAGE HANDLERS
# ============================================
async def handle_message(bot: TelegramBot, message: dict):
    """Ana mesaj isleyici"""
    chat_id = message["chat"]["id"]
    text = message.get("text", "").strip()
    user = message.get("from", {})
    username = user.get("username", user.get("first_name", "Bilinmiyor"))

    if not text:
        return

    if not is_allowed(chat_id):
        bot.send_message(chat_id, "Bu bot ozel kullanim icindir. Erisim izniniz yok.")
        return

    logger.info(f"[{chat_id}] {username}: {text[:60]}")

    # KOMUTLAR
    if text.startswith("/"):
        await handle_command(bot, chat_id, text, username)
        return

    # URL GONDERILDI - Urun yakala
    if is_url(text):
        await handle_url(bot, chat_id, text, username)
        return

    # Normal metin
    bot.send_message(chat_id,
        f"Merhaba {username}!\n\n"
        "Bana su seyleri gonderebilirsin:\n"
        "- <b>URL</b>: Platform linki gonder, urunu otomatik eklerim\n"
        "- <code>/scrape nike air max</code> - Kazima baslat\n"
        "- <code>/stats</code> - Sistem durumu\n"
        "- <code>/karli</code> - Karli urunler\n"
        "- <code>/help</code> - Tum komutlar\n"
    )


async def handle_command(bot: TelegramBot, chat_id, text: str, username: str):
    """Komut isleyicisi"""
    parts = text.split(maxsplit=1)
    cmd = parts[0].lower().split("@")[0]  # /cmd@botname -> /cmd
    args = parts[1] if len(parts) > 1 else ""

    if cmd == "/start":
        bot.send_message(chat_id,
            "<b>TATANGA Kumanda Merkezi</b>\n\n"
            "Hosgeldin! Su islemleri yapabilirim:\n\n"
            "<b>URL Gonder</b> -> Urun otomatik eklenir\n\n"
            "<b>Komutlar:</b>\n"
            "<code>/stats</code> - Sistem durumu\n"
            "<code>/son</code> - Son eklenen urunler\n"
            "<code>/karli</code> - Karli urunler\n"
            "<code>/scrape keyword</code> - Kazima baslat\n"
            "<code>/publish ID</code> - cssberlin.de'ye yayinla\n"
            "<code>/watchlist</code> - Takip listesi\n"
            "<code>/check ID</code> - Kaynak kontrol\n"
            "<code>/seo ID</code> - SEO olustur\n"
            "<code>/kanallar</code> - Kanal durumu\n"
            "<code>/help</code> - Yardim\n\n"
            f"Chat ID: <code>{chat_id}</code>",
            reply_markup={
                "keyboard": [
                    [{"text": "/stats"}, {"text": "/karli"}],
                    [{"text": "/son"}, {"text": "/watchlist"}],
                    [{"text": "/kanallar"}, {"text": "/help"}],
                ],
                "resize_keyboard": True,
            }
        )
        # Chat ID'yi otomatik kaydet
        if chat_id not in ALLOWED_CHAT_IDS:
            ALLOWED_CHAT_IDS.append(chat_id)
            save_config()
            logger.info(f"Chat ID eklendi: {chat_id} ({username})")

    elif cmd == "/help":
        bot.send_message(chat_id,
            "<b>TATANGA Bot Komutlari</b>\n\n"
            "<b>Bilgi:</b>\n"
            "/stats - Sistem istatistikleri\n"
            "/son [N] - Son N urun (varsayilan 5)\n"
            "/karli [N] - Karli urunler\n"
            "/watchlist - Takip listesi\n"
            "/kanallar - Telegram kanal durumu\n\n"
            "<b>Islem:</b>\n"
            "/scrape keyword - Kazima baslat\n"
            "/publish ID - cssberlin.de'ye yayinla\n"
            "/check ID - Kaynak durumu kontrol\n"
            "/seo ID - SEO icerik olustur\n"
            "/bgremove ID - Arkaplan kaldir\n\n"
            "<b>URL ile Urun Ekleme:</b>\n"
            "Herhangi bir Vinted, eBay, Kleinanzeigen, Willhaben, "
            "Sellpy, Tradera, Leboncoin linki gonder -> otomatik eklenir!"
        )

    elif cmd == "/stats":
        await cmd_stats(bot, chat_id)

    elif cmd in ("/son", "/recent"):
        limit = int(args) if args.isdigit() else 5
        await cmd_recent(bot, chat_id, limit)

    elif cmd in ("/karli", "/profitable"):
        limit = int(args) if args.isdigit() else 10
        await cmd_profitable(bot, chat_id, limit)

    elif cmd == "/scrape":
        if not args:
            bot.send_message(chat_id,
                "Kullanim: <code>/scrape anahtar kelime</code>\n"
                "Ornek: <code>/scrape nike air max</code>\n"
                "Ornek: <code>/scrape adidas spor ayakkabi</code>")
            return
        await cmd_scrape(bot, chat_id, args, username)

    elif cmd == "/publish":
        if not args:
            bot.send_message(chat_id, "Kullanim: <code>/publish PROD-xxx</code>")
            return
        await cmd_publish(bot, chat_id, args.strip())

    elif cmd == "/watchlist":
        await cmd_watchlist(bot, chat_id)

    elif cmd == "/check":
        if not args:
            bot.send_message(chat_id, "Kullanim: <code>/check PROD-xxx</code>")
            return
        await cmd_check(bot, chat_id, args.strip())

    elif cmd == "/seo":
        if not args:
            bot.send_message(chat_id, "Kullanim: <code>/seo PROD-xxx</code>")
            return
        await cmd_seo(bot, chat_id, args.strip())

    elif cmd == "/bgremove":
        if not args:
            bot.send_message(chat_id, "Kullanim: <code>/bgremove PROD-xxx</code>")
            return
        await cmd_bgremove(bot, chat_id, args.strip())

    elif cmd == "/kanallar":
        await cmd_channels(bot, chat_id)

    else:
        bot.send_message(chat_id, f"Bilinmeyen komut: {cmd}\n/help yazarak tum komutlari gorebilirsin.")


async def handle_url(bot: TelegramBot, chat_id, url: str, username: str):
    """URL ile urun ekleme"""
    if not is_supported_url(url):
        bot.send_message(chat_id,
            "Bu URL desteklenen platformlardan degil.\n"
            "Desteklenen: Vinted, eBay, Kleinanzeigen, Willhaben, Sellpy, Tradera, Leboncoin"
        )
        return

    # Platform belirle
    platform = "?"
    for p in ["vinted", "ebay", "kleinanzeigen", "willhaben", "sellpy", "tradera", "leboncoin"]:
        if p in url.lower():
            platform = p.capitalize()
            break

    bot.send_message(chat_id, f"<b>{platform}</b> urunu cekiliyor...")

    try:
        resp = req_lib.post(f"{HUB_API_URL}/api/product/add-by-url",
                            json={"url": url}, timeout=30)

        if resp.status_code == 200:
            data = resp.json()
            if data.get("status") == "ok":
                profit = data.get("profit_euro", 0) or 0
                rec = data.get("recommendation", "analyze")
                rec_emoji = {"buy": "AL", "watch": "IZLE", "skip": "ATLA"}.get(rec, "?")

                msg = (
                    f"<b>Urun Yakalandi!</b>\n\n"
                    f"<b>{data.get('title', 'Urun')[:80]}</b>\n"
                    f"Platform: {data.get('platform', platform)}\n"
                    f"Fiyat: {data.get('price', 0):.2f} EUR\n"
                    f"Kar: {profit:.2f} EUR | [{rec_emoji}]\n"
                    f"ID: <code>{data.get('product_id', '')}</code>\n\n"
                    f"<a href='{HUB_API_URL}/product/{data.get('product_id', '')}'>Hub'da Gor</a>"
                )

                # Gorsel varsa gonder
                if data.get("image"):
                    bot.send_photo(chat_id, data["image"], msg)
                else:
                    bot.send_message(chat_id, msg)

                # Bildirimler kanalina da gonder
                if chat_id != CHANNELS.get("bildirimler"):
                    send_to_bildirimler(
                        f"<b>Yeni Urun (URL)</b>\n"
                        f"{data.get('title', '')[:50]}\n"
                        f"{platform} | {data.get('price', 0):.2f} EUR | "
                        f"Kar: {profit:.2f} EUR [{rec_emoji}]\n"
                        f"Ekleyen: {username}"
                    )

                logger.info(f"URL eklendi ({username}): {data.get('title', '')[:40]}")
            else:
                bot.send_message(chat_id, f"Hata: {data.get('error', 'Bilinmeyen hata')}")
        else:
            bot.send_message(chat_id, f"Hub API hatasi (HTTP {resp.status_code})")

    except req_lib.ConnectionError:
        bot.send_message(chat_id, "T11_HUB sunucusu kapali!\nLutfen Hub'i baslatin: http://localhost:8501")
    except Exception as e:
        bot.send_message(chat_id, f"Hata: {str(e)[:200]}")
        send_to_sistem_hata(f"<b>URL Ekleme Hatasi</b>\n{url[:80]}\n{str(e)[:200]}")


# ============================================
# CALLBACK HANDLER (inline butonlar)
# ============================================
async def handle_campaign_decision(bot: TelegramBot, chat_id, message_id,
                                   decision: str, draft_id: str):
    """
    Kampanya metni icin INSAN karari. Onaylanmadikca hicbir metin siteye gitmez;
    'push' adimi yalnizca status='approved' kayitlari gonderir.

    duzelt: metin burada YENIDEN YAZILMAZ — Hub arayuzune yonlendirilir. Sohbet
    uzerinden serbest metin duzenlemek, onaylanan metnin iddia bekcisinden
    gecmemis olmasi riskini dogurur.
    """
    if decision == "duzelt":
        bot.edit_message(
            chat_id, message_id,
            f"<b>Duzeltme icin Hub'a gecin</b>\n<code>{draft_id}</code>\n\n"
            f"{HUB_API_URL}/scraper\n\n"
            "Metni orada duzeltip yeniden onaylayin — boylece degisiklik de "
            "iddia denetiminden gecer.")
        return

    if decision not in ("onayla", "iptal"):
        bot.edit_message(chat_id, message_id, "Bilinmeyen islem.")
        return

    action = "approve" if decision == "onayla" else "reject"
    try:
        resp = await asyncio.to_thread(
            lambda: req_lib.post(
                f"{HUB_API_URL}/api/campaigns/{draft_id}/{action}", timeout=15))
        ok = resp.status_code == 200
    except Exception as e:
        bot.edit_message(chat_id, message_id, f"Hub'a ulasilamadi: {e}")
        return

    if not ok:
        bot.edit_message(chat_id, message_id,
                         f"Islem basarisiz (HTTP {resp.status_code}) — <code>{draft_id}</code>")
        return

    if action == "approve":
        bot.edit_message(
            chat_id, message_id,
            f"<b>ONAYLANDI</b> — <code>{draft_id}</code>\n"
            "Siteye gonderilmek uzere sirada. (Gonderim ayri adim: /kampanya_gonder)")
    else:
        bot.edit_message(chat_id, message_id,
                         f"<b>IPTAL EDILDI</b> — <code>{draft_id}</code>\nBu metin yayinlanmayacak.")


async def notify_campaign_drafts(bot: TelegramBot, limit: int = 5) -> int:
    """
    Onay bekleyen kampanya taslaklarini kampanya odasina duser (onay butonlariyla).
    Metinlerin yaninda KANIT da gosterilir: onaylayan kisi iddianin neye
    dayandigini gormeden karar vermesin.
    """
    try:
        resp = await asyncio.to_thread(
            lambda: req_lib.get(f"{HUB_API_URL}/api/campaigns?status=draft", timeout=15))
        drafts = resp.json().get("campaigns", []) if resp.status_code == 200 else []
    except Exception:
        return 0

    sent = 0
    for draft in drafts[:limit]:
        warn = draft.get("warnings") or ""
        text = (
            f"<b>Kampanya onayi</b> [{draft.get('kind')}/{draft.get('lang')}]\n\n"
            f"<b>{draft.get('headline','')}</b>\n{draft.get('body','')}\n"
            f"<i>{draft.get('cta','')}</i>\n\n"
            f"Kanit: {draft.get('evidence','-')}\n"
            + (f"Uyari: {warn}\n" if warn else "")
            + f"<code>{draft.get('id')}</code>"
        )
        buttons = {"inline_keyboard": [[
            {"text": "Onayla", "callback_data": f"cmp:onayla:{draft.get('id')}"},
            {"text": "Duzelt", "callback_data": f"cmp:duzelt:{draft.get('id')}"},
            {"text": "Iptal", "callback_data": f"cmp:iptal:{draft.get('id')}"},
        ]]}
        bot.send_message(CHANNELS["kampanya"], text, reply_markup=buttons)
        sent += 1
    return sent


async def handle_callback(bot: TelegramBot, callback_query: dict):
    """Inline buton tiklama isleyici"""
    data = callback_query.get("data", "")
    chat_id = callback_query["message"]["chat"]["id"]
    message_id = callback_query["message"]["message_id"]
    cb_id = callback_query["id"]

    if not is_allowed(chat_id):
        bot.answer_callback(cb_id, "Yetkiniz yok!")
        return

    bot.answer_callback(cb_id)

    if data.startswith("cmp:"):
        # cmp:<karar>:<taslak_id> — kampanya metni onayi (ONAY/DUZELT/IPTAL)
        _, decision, draft_id = (data.split(":", 2) + ["", ""])[:3]
        await handle_campaign_decision(bot, chat_id, message_id, decision, draft_id)

    elif data.startswith("captcha_done"):
        bot.edit_message(chat_id, message_id,
            "CAPTCHA / Cookie islendi. Devam ediliyor...")

    elif data.startswith("captcha_skip"):
        bot.edit_message(chat_id, message_id,
            "CAPTCHA / Cookie atlandi.")

    elif data.startswith("publish_"):
        product_id = data.replace("publish_", "")
        bot.edit_message(chat_id, message_id,
            f"Urun yayinlaniyor: <code>{product_id}</code>...")
        await cmd_publish(bot, chat_id, product_id)

    elif data.startswith("bgremove_"):
        product_id = data.replace("bgremove_", "")
        bot.edit_message(chat_id, message_id,
            f"Arkaplan kaldiriliyor: <code>{product_id}</code>...")
        await cmd_bgremove(bot, chat_id, product_id)

    elif data.startswith("seo_"):
        product_id = data.replace("seo_", "")
        bot.edit_message(chat_id, message_id,
            f"SEO olusturuluyor: <code>{product_id}</code>...")
        await cmd_seo(bot, chat_id, product_id)

    else:
        bot.edit_message(chat_id, message_id, f"Islem yapildi: {data}")


# ============================================
# COMMAND IMPLEMENTATIONS
# ============================================

async def cmd_stats(bot: TelegramBot, chat_id):
    try:
        resp = req_lib.get(f"{HUB_API_URL}/api/stats", timeout=10)
        data = resp.json()

        msg = (
            "<b>TATANGA Sistem Durumu</b>\n"
            f"{datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
            f"Toplam Urun: <b>{data.get('total', 0)}</b>\n"
            f"Karli: <b>{data.get('profitable', 0)}</b>\n"
            f"Yayinda: {data.get('published', 0)}\n"
            f"Satilan: {data.get('sold', 0)}\n"
            f"BG Islenen: {data.get('bg_processed', 0)}\n"
            f"Aktif Is: {data.get('active_jobs', 0)}\n\n"
            f"<b>Platformlar:</b>\n"
        )
        for platform, count in data.get("platforms", {}).items():
            msg += f"  {platform}: {count}\n"

        bot.send_message(chat_id, msg)
    except req_lib.ConnectionError:
        bot.send_message(chat_id, "Hub sunucusu kapali!")
    except Exception as e:
        bot.send_message(chat_id, f"Hata: {e}")


async def cmd_recent(bot: TelegramBot, chat_id, limit: int = 5):
    try:
        resp = req_lib.get(f"{HUB_API_URL}/api/products?limit={limit}", timeout=10)
        data = resp.json()
        products = data.get("products", [])

        if not products:
            bot.send_message(chat_id, "Henuz urun yok.")
            return

        msg = f"<b>Son {len(products)} Urun</b>\n\n"
        for p in products:
            rec = ""
            if p.get("recommendation") == "buy": rec = " [AL]"
            elif p.get("recommendation") == "watch": rec = " [IZLE]"

            msg += (
                f"<b>{(p.get('title') or 'Isimsiz')[:45]}</b>{rec}\n"
                f"  {p.get('source_platform', '?')} | {p.get('price', 0):.2f} EUR | "
                f"Kar: {p.get('profit_euro', 0):.2f} EUR\n"
                f"  <code>{p.get('id', '')}</code>\n\n"
            )

        bot.send_message(chat_id, msg)
    except req_lib.ConnectionError:
        bot.send_message(chat_id, "Hub sunucusu kapali!")
    except Exception as e:
        bot.send_message(chat_id, f"Hata: {e}")


async def cmd_profitable(bot: TelegramBot, chat_id, limit: int = 10):
    try:
        resp = req_lib.get(f"{HUB_API_URL}/api/products?limit=100", timeout=10)
        data = resp.json()
        products = [p for p in data.get("products", []) if p.get("recommendation") == "buy"]

        if not products:
            bot.send_message(chat_id, "Henuz karli urun bulunamadi.")
            return

        # Kar'a gore sirala
        products.sort(key=lambda x: x.get("profit_euro", 0) or 0, reverse=True)

        msg = f"<b>En Karli {min(limit, len(products))} Urun</b>\n\n"
        for p in products[:limit]:
            msg += (
                f"<b>{(p.get('title') or 'Isimsiz')[:40]}</b>\n"
                f"  {p.get('source_platform', '?')} | Alis: {p.get('price', 0):.2f} EUR\n"
                f"  Kar: <b>{p.get('profit_euro', 0):.2f} EUR</b> "
                f"({p.get('profit_margin', 0):.0f}%)\n"
                f"  En iyi: {p.get('best_sell_platform', 'cssberlin')}\n"
                f"  <code>{p.get('id', '')}</code>\n\n"
            )

        bot.send_message(chat_id, msg)
    except Exception as e:
        bot.send_message(chat_id, f"Hata: {e}")


async def cmd_scrape(bot: TelegramBot, chat_id, keyword: str, username: str):
    try:
        bot.send_message(chat_id,
            f"Kazima baslatiliyor: <b>{keyword}</b>\n"
            "Platformlar: Vinted, eBay, Kleinanzeigen")

        resp = req_lib.post(f"{HUB_API_URL}/api/scrape/start",
                            json={
                                "keyword": keyword,
                                "platforms": ["vinted", "ebay", "kleinanzeigen"],
                                "max_pages": 3
                            }, timeout=15)
        data = resp.json()

        if data.get("job_id"):
            bot.send_message(chat_id,
                f"Kazima baslatildi!\n"
                f"Job: <code>{data['job_id']}</code>\n"
                f"Keyword: {keyword}\n\n"
                "Tamamlaninca bildirim alacaksin."
            )
            logger.info(f"Scrape started by {username}: {keyword}")

            # NOT: Kazima sonuclari kanallara gonderilmez (kullanici tercihi)
            # Sadece komutu gonderen kisiye DM'de bildirilir

            # Arka planda tamamlanmayi bekle
            asyncio.create_task(wait_scrape_and_notify(bot, chat_id, data["job_id"], keyword, username))
        else:
            bot.send_message(chat_id, "Kazima baslatma hatasi!")

    except req_lib.ConnectionError:
        bot.send_message(chat_id, "Hub sunucusu kapali!")
    except Exception as e:
        bot.send_message(chat_id, f"Hata: {e}")


async def wait_scrape_and_notify(bot: TelegramBot, chat_id, job_id: str,
                                  keyword: str, username: str = ""):
    """Kazima tamamlaninca bildirim gonder"""
    for _ in range(60):  # Max 10dk bekle
        await asyncio.sleep(10)
        try:
            resp = req_lib.get(f"{HUB_API_URL}/api/scrape/status/{job_id}", timeout=10)
            data = resp.json()
            if data.get("status") in ("completed", "failed"):
                if data["status"] == "completed":
                    total = data.get('total_found', 0)
                    profitable = data.get('profitable_count', 0)

                    # Admin'e bildir
                    bot.send_message(chat_id,
                        f"<b>Kazima Tamamlandi!</b>\n\n"
                        f"Keyword: {keyword}\n"
                        f"Bulunan: <b>{total}</b> urun\n"
                        f"Karli: <b>{profitable}</b> urun\n\n"
                        f"/karli yazarak karli urunleri gorebilirsin."
                    )

                    # Kazima sonuclari kanallara gonderilmez
                else:
                    error_msg = data.get('error_log', 'bilinmiyor')[:200]
                    bot.send_message(chat_id,
                        f"Kazima basarisiz: {keyword}\nHata: {error_msg}")
                    # Hata bildirimini de sadece komutu gonderen kisiye gonder
                return
        except:
            continue


async def cmd_publish(bot: TelegramBot, chat_id, product_id: str):
    try:
        bot.send_message(chat_id, f"Urun yayinlaniyor: <code>{product_id}</code>...")

        resp = req_lib.post(f"{HUB_API_URL}/api/product/{product_id}/publish",
                            json={"target": "cssberlin"}, timeout=30)
        data = resp.json()

        if data.get("status") == "published":
            cssid = data.get("cssberlin_id", "")
            url = f"https://cssberlin.de/items/{cssid}" if cssid else ""

            bot.send_message(chat_id,
                f"<b>Urun Yayinlandi!</b>\n"
                f"CSSberlin ID: <code>{cssid}</code>\n"
                f"{url}"
            )

            # Bildirimler kanalina
            send_to_bildirimler(
                f"<b>Urun Yayinlandi</b>\n"
                f"ID: {product_id}\n"
                f"{url}"
            )
        else:
            bot.send_message(chat_id, f"Yayin hatasi: {data.get('error', 'Bilinmiyor')}")

    except req_lib.ConnectionError:
        bot.send_message(chat_id, "Hub sunucusu kapali!")
    except Exception as e:
        bot.send_message(chat_id, f"Hata: {e}")


async def cmd_watchlist(bot: TelegramBot, chat_id):
    try:
        resp = req_lib.get(f"{HUB_API_URL}/api/watchlist", timeout=10)
        data = resp.json()
        items = data.get("watchlist", [])

        if not items:
            bot.send_message(chat_id, "Takip listeniz bos.")
            return

        msg = f"<b>Takip Listesi ({len(items)} urun)</b>\n\n"
        for item in items[:10]:
            st = item.get("source_status") or item.get("last_status", "")
            emoji = {"active": "🟢", "sold": "🔴", "reserved": "🟡"}.get(st, "⚪")

            msg += (
                f"{emoji} <b>{(item.get('title') or 'Isimsiz')[:35]}</b>\n"
                f"  {item.get('source_platform', '?')} | {(item.get('price') or 0):.2f} EUR\n\n"
            )

        bot.send_message(chat_id, msg)
    except Exception as e:
        bot.send_message(chat_id, f"Hata: {e}")


async def cmd_check(bot: TelegramBot, chat_id, product_id: str):
    try:
        resp = req_lib.post(f"{HUB_API_URL}/api/product/{product_id}/check-source",
                            timeout=15)
        data = resp.json()
        status = data.get("source_status", "?")
        emoji = {"active": "🟢", "sold": "🔴", "reserved": "🟡", "unavailable": "⚫"}.get(status, "⚪")

        bot.send_message(chat_id,
            f"<b>Kaynak Kontrol</b>\n"
            f"ID: <code>{product_id}</code>\n"
            f"Durum: {emoji} {status}")
    except Exception as e:
        bot.send_message(chat_id, f"Hata: {e}")


async def cmd_seo(bot: TelegramBot, chat_id, product_id: str):
    try:
        resp = req_lib.post(f"{HUB_API_URL}/api/product/{product_id}/generate-seo",
                            json={"platform": "cssberlin"}, timeout=30)
        data = resp.json()

        if data.get("seo_title"):
            bot.send_message(chat_id,
                f"<b>SEO Olusturuldu!</b>\n\n"
                f"<b>Baslik:</b> {data.get('seo_title', '')[:80]}\n"
                f"<b>Aciklama:</b> {data.get('seo_description', '')[:200]}\n"
                f"<b>Etiketler:</b> {', '.join(data.get('seo_tags', [])[:5])}"
            )
        else:
            bot.send_message(chat_id,
                f"SEO icerigi olusturuluyor: <code>{product_id}</code>\n"
                "Birkac saniye icerisinde hazir olacak.")
    except Exception as e:
        bot.send_message(chat_id, f"Hata: {e}")


async def cmd_bgremove(bot: TelegramBot, chat_id, product_id: str):
    try:
        resp = req_lib.post(f"{HUB_API_URL}/api/product/{product_id}/remove-bg",
                            timeout=60)
        data = resp.json()

        if data.get("status") == "processing":
            bot.send_message(chat_id,
                f"Arkaplan kaldirma baslatildi: <code>{product_id}</code>\n"
                "Tamamlaninca bildirilecek.")
        elif data.get("processed_images"):
            count = len(data.get("processed_images", []))
            bot.send_message(chat_id,
                f"<b>Arkaplan Kaldirildi!</b>\n"
                f"ID: <code>{product_id}</code>\n"
                f"Islenen gorsel: {count}")
        else:
            bot.send_message(chat_id, f"Hata: {data.get('error', 'Bilinmiyor')}")
    except Exception as e:
        bot.send_message(chat_id, f"Hata: {e}")


async def cmd_channels(bot: TelegramBot, chat_id):
    """Telegram kanal durumu"""
    msg = "<b>Telegram Kanallari</b>\n\n"
    msg += "<b>Aktif Kanallar:</b>\n"

    for name, cid in CHANNELS.items():
        emoji = "🟢"
        label = {
            "admin": "Admin (DM)",
            "bildirimler": "Bildirimler",
            "sistem_hata": "Sistem Hata",
            "captcha": "CAPTCHA / Cerez",
        }.get(name, name)
        msg += f"  {emoji} {label}: <code>{cid}</code>\n"

    msg += f"\n<b>Devre Disi ({len(LEGACY_CHANNELS)} eski grup):</b>\n"
    for name, cid in LEGACY_CHANNELS.items():
        label = {
            "messages": "Mesajlar",
            "sales": "Satislar",
            "shipping": "Kargo",
            "scrape_command": "Urun Kazima",
            "product_found": "Urun Buldum",
            "store_transfer": "Magazalar Arasi",
        }.get(name, name)
        msg += f"  ⚪ {label}\n"

    msg += f"\nToplam izinli chat: {len(ALLOWED_CHAT_IDS)}"
    bot.send_message(chat_id, msg)


# ============================================
# NOTIFICATION FUNCTIONS (T11_HUB'dan cagirilir)
# ============================================
_bot_instance: TelegramBot = None


def get_bot() -> TelegramBot:
    global _bot_instance
    if _bot_instance is None and BOT_TOKEN:
        _bot_instance = TelegramBot(BOT_TOKEN)
    return _bot_instance


# --- Bildirimler Kanalina ---

def notify_scrape_complete(keyword: str, total: int, profitable: int):
    """Kazima bildirimi - DEVRE DISI (kullanici tercihi)"""
    # Kazima sonuclari Telegram'a gonderilmez
    pass


def notify_product_added(title: str, platform: str, price: float, product_id: str):
    """Yeni urun eklenince bildirimler kanalina gonder"""
    send_to_bildirimler(
        f"<b>Yeni Urun Eklendi</b>\n"
        f"{title[:50]}\n"
        f"Platform: {platform} | {price:.2f} EUR\n"
        f"ID: <code>{product_id}</code>"
    )


def notify_product_published(title: str, cssberlin_id: str):
    """Urun yayinlaninca bildirimler kanalina gonder"""
    send_to_bildirimler(
        f"<b>Urun Yayinlandi!</b>\n"
        f"{title[:50]}\n"
        f"https://cssberlin.de/items/{cssberlin_id}"
    )


def notify_source_sold(title: str, platform: str, product_id: str):
    """Kaynakta satilinca bildirimler kanalina gonder"""
    send_to_bildirimler(
        f"<b>Kaynak Urun Satildi!</b>\n"
        f"{title[:50]}\n"
        f"Platform: {platform}\n"
        f"<code>{product_id}</code>"
    )


# --- Sistem Hata Kanalina ---

def notify_error(module: str, error: str, details: str = ""):
    """Hata bildirimini sistem hata kanalina gonder"""
    msg = (
        f"<b>HATA - {module}</b>\n"
        f"{error[:200]}"
    )
    if details:
        msg += f"\n\n{details[:300]}"
    send_to_sistem_hata(msg)


def notify_system_status(status_text: str):
    """Sistem durumu bildirimini sistem hata kanalina gonder"""
    send_to_sistem_hata(
        f"<b>Sistem Durumu</b>\n"
        f"{datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
        f"{status_text}"
    )


# --- CAPTCHA Kanalina ---

def notify_captcha_required(platform: str, url: str = "", screenshot_url: str = ""):
    """CAPTCHA/Cookie onayi gerektiginde captcha kanalina gonder"""
    msg = (
        f"<b>MANUEL ISLEM GEREKLI</b>\n\n"
        f"Platform: {platform}\n"
    )
    if url:
        msg += f"URL: {url[:100]}\n"
    msg += "\nLutfen platformda CAPTCHA/Cookie onayini yapin."

    send_to_captcha(msg, reply_markup={
        "inline_keyboard": [
            [
                {"text": "Tamamlandi", "callback_data": f"captcha_done_{platform}"},
                {"text": "Atla", "callback_data": f"captcha_skip_{platform}"},
            ]
        ]
    })


def notify_sms_required(platform: str, timeout: int = 120):
    """SMS dogrulama kodu gerektiginde captcha kanalina gonder"""
    send_to_captcha(
        f"<b>{platform.upper()} SMS DOGRULAMA</b>\n\n"
        f"SMS kodu bekleniyor!\n"
        f"Lutfen 4 haneli kodu yazin.\n"
        f"<i>(Ornek: 1234)</i>\n\n"
        f"Bekleme suresi: {timeout} saniye"
    )


# --- Toplu Bildirim ---

def notify_all(text: str, parse_mode: str = "HTML"):
    """Admin + bildirimler kanalina gonder"""
    bot = get_bot()
    if not bot:
        return

    # Admin DM
    try:
        bot.send_message(CHANNELS.get("admin"), text, parse_mode)
    except Exception as e:
        logger.error(f"Admin notify error: {e}")

    # Bildirimler kanali
    bildirimler_id = CHANNELS.get("bildirimler")
    if bildirimler_id and bildirimler_id != CHANNELS.get("admin"):
        try:
            bot.send_message(bildirimler_id, text, parse_mode)
        except Exception as e:
            logger.error(f"Bildirimler notify error: {e}")


# ============================================
# POLLING LOOP
# ============================================
async def run_bot_polling():
    """Telegram bot polling dongusu"""
    load_config()

    if not BOT_TOKEN:
        logger.warning("Bot token ayarlanmadi! credentials.py veya /settings'den ayarlayin.")
        while True:
            await asyncio.sleep(30)
            load_config()
            if BOT_TOKEN:
                logger.info("Bot token bulundu, polling basliyor...")
                break

    bot = TelegramBot(BOT_TOKEN)
    global _bot_instance
    _bot_instance = bot

    # Bot bilgilerini al (senkron HTTP - thread'e al)
    me = await asyncio.to_thread(bot.get_me)
    if me.get("ok"):
        bot_name = me['result'].get('username', 'unknown')
        logger.info(f"Bot aktif: @{bot_name}")

        # Sistem hata kanalina baslangic bildirimi
        await asyncio.to_thread(send_to_sistem_hata,
            f"<b>Bot Baslatildi</b>\n"
            f"@{bot_name}\n"
            f"{datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
            f"Aktif kanallar: {len(CHANNELS)}\n"
            f"Izinli chatler: {len(ALLOWED_CHAT_IDS)}"
        )
    else:
        logger.error(f"Bot baglanti hatasi: {me}")
        await asyncio.to_thread(send_to_sistem_hata,
            f"<b>Bot Baglanti Hatasi</b>\n"
            f"{me.get('error', 'Bilinmiyor')}"
        )
        await asyncio.sleep(60)
        return

    logger.info("Polling basliyor...")

    error_count = 0
    max_backoff = 300  # Max 5 dakika bekle

    while True:
        try:
            # ONEMLI: get_updates senkron HTTP - asyncio.to_thread ile wrap et
            # yoksa 30sn timeout event loop'u bloklar
            updates = await asyncio.to_thread(bot.get_updates, 30)

            # Basarili - hata sayacini sifirla
            error_count = 0

            for update in updates:
                # Message handler
                msg = update.get("message")
                if msg:
                    try:
                        await handle_message(bot, msg)
                    except Exception as e:
                        logger.error(f"Message handler error: {e}")

                # Callback query handler
                callback = update.get("callback_query")
                if callback:
                    try:
                        await handle_callback(bot, callback)
                    except Exception as e:
                        logger.error(f"Callback handler error: {e}")

        except Exception as e:
            error_count += 1
            # Exponential backoff: 5, 10, 20, 40, 80, 160, 300 (max)
            backoff = min(5 * (2 ** (error_count - 1)), max_backoff)
            if error_count <= 3 or error_count % 10 == 0:
                logger.error(f"Polling error #{error_count}: {str(e)[:100]} (bekle {backoff}s)")
            await asyncio.sleep(backoff)


# ============================================
# STANDALONE MODE
# ============================================
if __name__ == "__main__":
    print("\n  TATANGA Telegram Bot v2 (Unified)")
    print("  T11_HUB API'sine baglanir\n")

    load_config()

    if not BOT_TOKEN:
        token = input("Telegram Bot Token girin: ").strip()
        if token:
            save_config(token=token)
        else:
            print("Token gerekli! @BotFather'dan alin.")
            sys.exit(1)

    asyncio.run(run_bot_polling())
