#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TATANGA - Telegram Bot
Ana Telegram bot modulu
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path

# Add parent directory to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters
)

from shared.config.credentials import TELEGRAM, AI_SERVICES, KLEINANZEIGEN, VINTED

# Transfer handler import
import threading
from store_transfer_handler import StoreTransferHandler

# ============================================
# CONFIGURATION
# ============================================
BOT_TOKEN = TELEGRAM["bot_token"]
ADMIN_CHAT_IDS = []  # Buraya chat ID eklenecek

# ============================================
# COMMAND HANDLERS
# ============================================

async def start(update: Update, context):
    """Start komutu"""
    user = update.effective_user
    chat_id = update.effective_chat.id

    # Chat ID'yi kaydet
    print(f"Yeni kullanici: {user.first_name} ({user.id})")
    print(f"Chat ID: {chat_id}")

    welcome_text = f"""
Merhaba {user.first_name}!

TATANGA Sistemine hosgeldiniz.

**Komutlar:**
/status - Sistem durumu
/trends - Guncel trendler
/sales - Satis ozeti
/help - Yardim

**Chat ID:** `{chat_id}`
(Bu ID'yi config dosyasina ekleyin)
"""

    await update.message.reply_text(
        welcome_text,
        parse_mode="Markdown"
    )

async def status(update: Update, context):
    """Sistem durumu"""
    status_text = f"""
**TATANGA Sistem Durumu**

Tarih: {datetime.now().strftime("%d.%m.%Y %H:%M")}

**Platformlar:**
- Vinted: Aktif
- Kleinanzeigen: Aktif
- eBay: Aktif
- Willhaben: Aktif

**Servisler:**
- Telegram Bot: Calisiyorum
- Hetzner Server: Online
- AI (Groq): Hazir

**Istatistikler:**
- Aktif Ilanlar: -
- Bugunun Satislari: -
- Bekleyen Mesajlar: -
"""

    await update.message.reply_text(
        status_text,
        parse_mode="Markdown"
    )

async def help_command(update: Update, context):
    """Yardim komutu"""
    help_text = """
**TATANGA Komutlari**

/start - Botu baslat
/status - Sistem durumu
/transfer - Kleinanzeigen → Vinted transfer
/ebay - Kleinanzeigen → eBay transfer
/trends - Guncel trend urunler
/sales - Satis ozeti
/help - Bu mesaj

**Transfer Komutlari:**
- /transfer - Vinted'e urun aktar
- /ebay - eBay'e urun aktar (API)

**Telegram Kanallari:**
- #store_transfer - Transfer bildirimleri
- #captcha_approval - CAPTCHA onayi
- #trendler - Trend urun bildirimleri
- #satislar - Satis bildirimleri

**Kullanim:**
Mesaj geldinde interaktif butonlar ile islem yapabilirsiniz.
"""

    await update.message.reply_text(
        help_text,
        parse_mode="Markdown"
    )

async def trends(update: Update, context):
    """Trend urunler"""
    # Placeholder - T1_TREND_HUNTER ile entegre edilecek
    await update.message.reply_text(
        "Trend urunler yukleniyor...\n(Bu ozellik yakinda aktif olacak)",
        parse_mode="Markdown"
    )

async def sales(update: Update, context):
    """Satis ozeti"""
    # Placeholder - T10_ANALYTICS ile entegre edilecek
    await update.message.reply_text(
        "Satis ozeti yukleniyor...\n(Bu ozellik yakinda aktif olacak)",
        parse_mode="Markdown"
    )

async def transfer(update: Update, context):
    """Magaza transferi baslat"""
    chat_id = update.effective_chat.id
    store_transfer_chat = TELEGRAM['channels']['store_transfer']

    # Sadece store_transfer odasindan calissin
    if chat_id != store_transfer_chat:
        await update.message.reply_text(
            f"⚠️ Bu komut sadece *TATANGA - Magazalar arasi transfer* odasindan calisir.\n\n"
            f"Dogru oda Chat ID: `{store_transfer_chat}`\n"
            f"Su anki Chat ID: `{chat_id}`",
            parse_mode="Markdown"
        )
        return

    # Kaynak ve hedef bilgileri
    source_email = KLEINANZEIGEN['accounts'][0]['email']  # ceyhunsabahattinsorguc@gmail.com
    target_email = VINTED['accounts'][0]['email']  # cssberlin@hotmail.com

    # Onay mesaji
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Vinted'e Aktar", callback_data="transfer_start_vinted"),
            InlineKeyboardButton("❌ Iptal", callback_data="transfer_cancel"),
        ],
        [
            InlineKeyboardButton("📋 eBay'e Aktar", callback_data="transfer_start_ebay"),
        ],
    ])

    await update.message.reply_text(
        f"*🔄 MAGAZA TRANSFERI*\n\n"
        f"*Kaynak Platform:* Kleinanzeigen\n"
        f"*Kaynak Hesap:* `{source_email}`\n\n"
        f"*Hedef Platform:* Vinted\n"
        f"*Hedef Magaza:* `{target_email}`\n\n"
        f"*Islem Adimlari:*\n"
        f"1. Kleinanzeigen'e login\n"
        f"2. Mevcut urunleri cek\n"
        f"3. Resimleri indir ve isle\n"
        f"4. AI ile baslik/aciklama optimize et\n"
        f"5. Vinted'e login ve yukle\n\n"
        f"⚠️ *Fiyat AYNI kalir* - Kar marji YOK\n"
        f"_(Kar marji sadece urun kazimada)_\n\n"
        f"_Transfer baslatilsin mi?_",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

async def transfer_to_ebay(update: Update, context):
    """eBay'e transfer baslat"""
    chat_id = update.effective_chat.id

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Baslat", callback_data="transfer_start_ebay"),
            InlineKeyboardButton("❌ Iptal", callback_data="transfer_cancel"),
        ],
    ])

    await update.message.reply_text(
        f"*🔄 EBAY TRANSFERI*\n\n"
        f"*Kaynak:* Kleinanzeigen\n"
        f"*Hedef:* eBay (Css_Berlin)\n\n"
        f"*API Kullanimi:*\n"
        f"- Inventory API\n"
        f"- Media API\n"
        f"- Trading API\n\n"
        f"_Transfer baslatilsin mi?_",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

def run_transfer_in_background(chat_id, target_platform):
    """Transfer'i arka planda calistir"""
    try:
        handler = StoreTransferHandler()
        source_email = KLEINANZEIGEN['accounts'][0]['email']
        target_email = VINTED['accounts'][0]['email']

        if target_platform == 'vinted':
            handler.execute_transfer(source_email, 'vinted', target_email, chat_id)
        elif target_platform == 'ebay':
            # eBay transfer - API kullanacak
            handler.execute_ebay_transfer(source_email, chat_id)

    except Exception as e:
        print(f"Transfer hatasi: {e}")
        import traceback
        traceback.print_exc()

# ============================================
# CALLBACK HANDLERS
# ============================================

async def button_callback(update: Update, context):
    """Buton tiklama isleyici"""
    query = update.callback_query
    await query.answer()

    data = query.data

    if data.startswith("accept:"):
        # Teklifi kabul et
        offer_id = data.split(":")[1]
        await query.edit_message_text(
            f"Teklif kabul edildi: {offer_id}"
        )

    elif data.startswith("reject:"):
        # Teklifi reddet
        offer_id = data.split(":")[1]
        await query.edit_message_text(
            f"Teklif reddedildi: {offer_id}"
        )

    elif data.startswith("counter:"):
        # Karsi teklif
        offer_id = data.split(":")[1]
        await query.edit_message_text(
            f"Karsi teklif gonderildi: {offer_id}"
        )

    elif data.startswith("send:"):
        # Mesaj gonder
        msg_id = data.split(":")[1]
        await query.edit_message_text(
            f"Mesaj gonderildi: {msg_id}"
        )

    elif data == "transfer_start_vinted":
        # Vinted transferi baslat
        chat_id = query.message.chat_id
        await query.edit_message_text(
            "*🚀 TRANSFER BASLATILDI*\n\n"
            "Kleinanzeigen → Vinted\n\n"
            "_Urunler cekilip isleniyor..._\n"
            "_Bu islem birkaç dakika surebilir._",
            parse_mode="Markdown"
        )

        # Arka planda transfer baslat
        transfer_thread = threading.Thread(
            target=run_transfer_in_background,
            args=(chat_id, 'vinted')
        )
        transfer_thread.start()

    elif data == "transfer_start_ebay":
        # eBay transferi baslat
        chat_id = query.message.chat_id
        await query.edit_message_text(
            "*🚀 EBAY TRANSFERI BASLATILDI*\n\n"
            "Kleinanzeigen → eBay (API)\n\n"
            "_Urunler cekilip API ile yukleniyor..._",
            parse_mode="Markdown"
        )

        # Arka planda transfer baslat
        transfer_thread = threading.Thread(
            target=run_transfer_in_background,
            args=(chat_id, 'ebay')
        )
        transfer_thread.start()

    elif data == "transfer_cancel":
        # Transfer iptal
        await query.edit_message_text(
            "❌ Transfer iptal edildi.",
            parse_mode="Markdown"
        )

    elif data.startswith("captcha_"):
        # CAPTCHA callback'leri
        action = data.replace("captcha_", "")
        if action == "done":
            await query.edit_message_text(
                "✅ CAPTCHA cozuldu, islem devam ediyor...",
                parse_mode="Markdown"
            )
        elif action == "skip":
            await query.edit_message_text(
                "⏭️ CAPTCHA atlandi.",
                parse_mode="Markdown"
            )
        elif action == "failed":
            await query.edit_message_text(
                "❌ CAPTCHA cozulemedi, yeniden deneniyor...",
                parse_mode="Markdown"
            )

    elif data.startswith("error_"):
        # Hata callback'leri
        action = data.replace("error_", "")
        if action.startswith("retry"):
            await query.edit_message_text(
                "🔄 Yeniden deneniyor...",
                parse_mode="Markdown"
            )
        elif action.startswith("skip"):
            await query.edit_message_text(
                "⏭️ Hata atlandi, devam ediliyor...",
                parse_mode="Markdown"
            )
        elif action == "stop":
            await query.edit_message_text(
                "🛑 Islem durduruldu.",
                parse_mode="Markdown"
            )

    else:
        await query.edit_message_text(
            f"Islem yapildi: {data}"
        )

# ============================================
# MESSAGE HANDLERS
# ============================================

async def handle_message(update: Update, context):
    """Genel mesaj isleyici"""
    text = update.message.text
    chat_id = update.effective_chat.id

    # Kargo bilgisi guncelleme
    # Format: CSS-001 DHL 123456789
    if text and len(text.split()) == 3:
        parts = text.split()
        if parts[1].upper() in ["DHL", "HERMES", "DPD", "GLS"]:
            product_id = parts[0]
            carrier = parts[1].upper()
            tracking = parts[2]

            await update.message.reply_text(
                f"Kargo bilgisi guncellendi!\n\n"
                f"Urun: {product_id}\n"
                f"Kargo: {carrier}\n"
                f"Takip No: {tracking}",
                parse_mode="Markdown"
            )
            return

    # Bilinmeyen mesaj
    await update.message.reply_text(
        "Anlamadim. /help yazarak komutlari gorebilirsiniz."
    )

# ============================================
# NOTIFICATION FUNCTIONS
# ============================================

async def send_notification(bot, chat_id, text, buttons=None, parse_mode="Markdown"):
    """Bildirim gonder"""
    keyboard = None
    if buttons:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(btn[0], callback_data=btn[1]) for btn in row]
            for row in buttons
        ])

    await bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=keyboard,
        parse_mode=parse_mode
    )

# ============================================
# MAIN
# ============================================

def main():
    """Ana fonksiyon"""
    print("TATANGA Telegram Bot baslatiliyor...")

    # Application olustur
    application = Application.builder().token(BOT_TOKEN).build()

    # Command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("trends", trends))
    application.add_handler(CommandHandler("sales", sales))
    application.add_handler(CommandHandler("transfer", transfer))
    application.add_handler(CommandHandler("ebay", transfer_to_ebay))

    # Callback handler
    application.add_handler(CallbackQueryHandler(button_callback))

    # Message handler
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_message
    ))

    print("Bot hazir! Polling baslatiliyor...")

    # Bot'u calistir
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
