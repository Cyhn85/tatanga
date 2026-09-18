#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TATANGA - Telegram AI Assistant
Mesajlari okuyan ve komutlari anlayan AI asistan
"""

import os
import sys
import json
import re
import asyncio
from pathlib import Path
from datetime import datetime

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters
)
import requests

from shared.config.credentials import TELEGRAM, AI_SERVICES, KLEINANZEIGEN, VINTED, EBAY, WILLHABEN

# ============================================
# CONFIGURATION
# ============================================
BOT_TOKEN = TELEGRAM["bot_token"]
ADMIN_CHAT_ID = TELEGRAM["admin_chat_id"]

# Magaza takma adlari
STORE_ALIASES = {
    # Kleinanzeigen
    "kleinanzeigen1": {"platform": "kleinanzeigen", "account": "main"},
    "kleinanzeigen2": {"platform": "kleinanzeigen", "account": "secondary"},
    "kleinanzeigen3": {"platform": "kleinanzeigen", "account": "tertiary"},
    "ka1": {"platform": "kleinanzeigen", "account": "main"},
    "ka2": {"platform": "kleinanzeigen", "account": "secondary"},
    "ka3": {"platform": "kleinanzeigen", "account": "tertiary"},

    # Vinted
    "vinted1": {"platform": "vinted", "account": "main"},
    "vinted2": {"platform": "vinted", "account": "secondary"},
    "v1": {"platform": "vinted", "account": "main"},
    "v2": {"platform": "vinted", "account": "secondary"},

    # eBay
    "ebay": {"platform": "ebay", "account": "main"},
    "cssberlin": {"platform": "ebay", "account": "main"},

    # Willhaben
    "willhaben": {"platform": "willhaben", "account": "main"},
    "wh": {"platform": "willhaben", "account": "main"}
}

# ============================================
# AI MESSAGE PARSER
# ============================================
class AIMessageParser:
    """AI ile mesaj ayrıstırıcı"""

    def __init__(self):
        self.groq_api_key = AI_SERVICES['groq']['api_key']
        self.model = AI_SERVICES['groq']['model']

    def parse_command(self, message):
        """
        Dogal dil komutunu parse et

        Args:
            message: Kullanici mesaji

        Returns:
            dict: Komut detaylari
        """
        try:
            headers = {
                "Authorization": f"Bearer {self.groq_api_key}",
                "Content-Type": "application/json"
            }

            prompt = f"""
            Analyze this Turkish message and extract the command/intent.

            Message: "{message}"

            Available store aliases: {list(STORE_ALIASES.keys())}

            Return a JSON object with:
            {{
                "intent": "check_store" | "check_favorites" | "check_messages" | "check_sales" | "list_products" | "get_stats" | "search_product" | "unknown",
                "platform": "kleinanzeigen" | "vinted" | "ebay" | "willhaben" | null,
                "account": "main" | "secondary" | "tertiary" | null,
                "store_alias": "detected alias from message" | null,
                "action": "favorites" | "messages" | "sales" | "products" | "notifications" | null,
                "parameters": {{any additional parameters}},
                "confidence": 0.0 to 1.0
            }}

            Examples:
            - "kleinanzeigen 3'e gir ve favorilere bak" -> {{"intent": "check_favorites", "platform": "kleinanzeigen", "account": "tertiary", "store_alias": "kleinanzeigen3"}}
            - "vinted'de kac favori aldik" -> {{"intent": "check_favorites", "platform": "vinted", "account": "main"}}
            - "ka2'deki mesajlara bak" -> {{"intent": "check_messages", "platform": "kleinanzeigen", "account": "secondary", "store_alias": "ka2"}}
            - "ebay satislarini kontrol et" -> {{"intent": "check_sales", "platform": "ebay"}}

            Return ONLY the JSON, no other text.
            """

            data = {
                "model": self.model,
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 300,
                "temperature": 0.1
            }

            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json=data,
                timeout=30
            )

            if response.status_code == 200:
                result = response.json()
                content = result['choices'][0]['message']['content'].strip()

                # JSON'i parse et
                # Bazen markdown code block icinde geliyor
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0]
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0]

                return json.loads(content)

        except Exception as e:
            print(f"AI parse hatasi: {e}")

        return {"intent": "unknown", "confidence": 0}

    def generate_response(self, query, context=None):
        """
        AI yaniti olustur

        Args:
            query: Soru
            context: Ek bagiam

        Returns:
            str: Yanit
        """
        try:
            headers = {
                "Authorization": f"Bearer {self.groq_api_key}",
                "Content-Type": "application/json"
            }

            system_prompt = """
            Sen TATANGA sisteminin Telegram asistanisin.
            Kullaniciya Turkce olarak kisa ve net yanitlar ver.
            2. el urun satisi, arbitraj ve magaza yonetimi konularinda yardimci ol.
            Teknik detaylari basit sekilde acikla.
            """

            messages = [
                {"role": "system", "content": system_prompt}
            ]

            if context:
                messages.append({"role": "system", "content": f"Bagiam: {context}"})

            messages.append({"role": "user", "content": query})

            data = {
                "model": self.model,
                "messages": messages,
                "max_tokens": 500
            }

            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json=data,
                timeout=30
            )

            if response.status_code == 200:
                result = response.json()
                return result['choices'][0]['message']['content'].strip()

        except Exception as e:
            print(f"AI yanit hatasi: {e}")

        return "Bir hata olustu. Lutfen tekrar deneyin."

# ============================================
# STORE CHECKER
# ============================================
class StoreChecker:
    """Magaza kontrol islemleri"""

    def __init__(self):
        pass

    async def check_favorites(self, platform, account):
        """
        Magaza favorilerini kontrol et

        Args:
            platform: Platform adi
            account: Hesap adi

        Returns:
            dict: Favori bilgileri
        """
        # Bu kisim gercek scraping ile doldurulacak
        # Simdilik placeholder

        if platform == "kleinanzeigen":
            # Kleinanzeigen favori kontrolu
            return {
                "platform": platform,
                "account": account,
                "total_favorites": 0,
                "new_favorites": 0,
                "products_with_favorites": [],
                "status": "Simdilik veri yok - scraper entegrasyonu gerekli"
            }

        elif platform == "vinted":
            # Vinted favori kontrolu
            return {
                "platform": platform,
                "account": account,
                "total_favorites": 0,
                "new_favorites": 0,
                "products_with_favorites": [],
                "status": "Simdilik veri yok - scraper entegrasyonu gerekli"
            }

        elif platform == "ebay":
            # eBay watching kontrolu
            return {
                "platform": platform,
                "account": account,
                "watchers": 0,
                "status": "API entegrasyonu gerekli"
            }

        return {"error": "Bilinmeyen platform"}

    async def check_messages(self, platform, account):
        """
        Magaza mesajlarini kontrol et

        Args:
            platform: Platform adi
            account: Hesap adi

        Returns:
            dict: Mesaj bilgileri
        """
        return {
            "platform": platform,
            "account": account,
            "unread_count": 0,
            "messages": [],
            "status": "Scraper entegrasyonu gerekli"
        }

    async def check_sales(self, platform, account):
        """
        Satis bilgilerini kontrol et

        Args:
            platform: Platform adi
            account: Hesap adi

        Returns:
            dict: Satis bilgileri
        """
        return {
            "platform": platform,
            "account": account,
            "today_sales": 0,
            "pending_shipments": 0,
            "total_revenue": 0,
            "status": "Scraper entegrasyonu gerekli"
        }

    async def get_store_stats(self, platform, account):
        """
        Magaza istatistikleri

        Args:
            platform: Platform adi
            account: Hesap adi

        Returns:
            dict: Istatistikler
        """
        return {
            "platform": platform,
            "account": account,
            "active_listings": 0,
            "total_views": 0,
            "conversion_rate": 0,
            "status": "Scraper entegrasyonu gerekli"
        }

# ============================================
# TELEGRAM BOT HANDLERS
# ============================================
ai_parser = AIMessageParser()
store_checker = StoreChecker()

async def start(update: Update, context):
    """Start komutu"""
    user = update.effective_user
    chat_id = update.effective_chat.id

    welcome = f"""
Merhaba {user.first_name}!

TATANGA AI Asistanina hosgeldiniz.

**Dogal Dil Komutlari:**
- "kleinanzeigen 3'e gir ve favorilere bak"
- "vinted'de kac favori aldik"
- "ebay satislarini kontrol et"
- "ka2'deki mesajlara bak"

**Standart Komutlar:**
/status - Sistem durumu
/stores - Tum magazalar
/favorites <magaza> - Favoriler
/messages <magaza> - Mesajlar
/sales <magaza> - Satislar

**Magaza Kisayollari:**
ka1, ka2, ka3 = Kleinanzeigen 1/2/3
v1, v2 = Vinted 1/2
ebay, wh = eBay, Willhaben

Chat ID: `{chat_id}`
    """

    await update.message.reply_text(welcome, parse_mode="Markdown")

async def status(update: Update, context):
    """Sistem durumu"""
    status_text = f"""
**TATANGA Sistem Durumu**
{datetime.now().strftime('%d.%m.%Y %H:%M')}

**Magazalar:**
- Kleinanzeigen: 3 hesap
- Vinted: 2 hesap
- eBay: css_berlin
- Willhaben: 1 hesap

**Servisler:**
- Telegram Bot: Aktif
- AI Asistan: Aktif
- Scraper: Beklemede

Bir magaza kontrol etmek icin mesaj yazin.
Ornek: "vinted favorilere bak"
    """

    await update.message.reply_text(status_text, parse_mode="Markdown")

async def stores(update: Update, context):
    """Tum magazalari listele"""
    stores_text = """
**Tum Magazalar**

**Kleinanzeigen:**
- ka1 / kleinanzeigen1: Ana hesap
- ka2 / kleinanzeigen2: Ikinci hesap
- ka3 / kleinanzeigen3: Ucuncu hesap

**Vinted:**
- v1 / vinted1: Ana hesap (Cyhn85)
- v2 / vinted2: Ikinci hesap

**eBay:**
- ebay / cssberlin: css_berlin (50★)

**Willhaben:**
- wh / willhaben: Gewerblich hesap

Kullanim: "ka3 favorilere bak" veya /favorites ka3
    """

    await update.message.reply_text(stores_text, parse_mode="Markdown")

async def favorites_command(update: Update, context):
    """Favori komutu"""
    if not context.args:
        await update.message.reply_text("Kullanim: /favorites <magaza>\nOrnek: /favorites ka2")
        return

    alias = context.args[0].lower()
    store_info = STORE_ALIASES.get(alias)

    if not store_info:
        await update.message.reply_text(f"Bilinmeyen magaza: {alias}\n/stores ile tum magazalari gorun.")
        return

    await update.message.reply_text(f"{alias} favorileri kontrol ediliyor...")

    result = await store_checker.check_favorites(store_info['platform'], store_info['account'])

    response = f"""
**{store_info['platform'].title()} - {store_info['account']}**

Toplam Favori: {result.get('total_favorites', 0)}
Yeni Favori: {result.get('new_favorites', 0)}

Durum: {result.get('status', 'Bilinmiyor')}
    """

    await update.message.reply_text(response, parse_mode="Markdown")

async def messages_command(update: Update, context):
    """Mesaj komutu"""
    if not context.args:
        await update.message.reply_text("Kullanim: /messages <magaza>\nOrnek: /messages v1")
        return

    alias = context.args[0].lower()
    store_info = STORE_ALIASES.get(alias)

    if not store_info:
        await update.message.reply_text(f"Bilinmeyen magaza: {alias}")
        return

    await update.message.reply_text(f"{alias} mesajlari kontrol ediliyor...")

    result = await store_checker.check_messages(store_info['platform'], store_info['account'])

    response = f"""
**{store_info['platform'].title()} Mesajlari**

Okunmamis: {result.get('unread_count', 0)}

Durum: {result.get('status', 'Bilinmiyor')}
    """

    await update.message.reply_text(response, parse_mode="Markdown")

async def sales_command(update: Update, context):
    """Satis komutu"""
    if not context.args:
        await update.message.reply_text("Kullanim: /sales <magaza>\nOrnek: /sales ebay")
        return

    alias = context.args[0].lower()
    store_info = STORE_ALIASES.get(alias)

    if not store_info:
        await update.message.reply_text(f"Bilinmeyen magaza: {alias}")
        return

    await update.message.reply_text(f"{alias} satislari kontrol ediliyor...")

    result = await store_checker.check_sales(store_info['platform'], store_info['account'])

    response = f"""
**{store_info['platform'].title()} Satislari**

Bugun: {result.get('today_sales', 0)} satis
Bekleyen Kargo: {result.get('pending_shipments', 0)}
Toplam Gelir: {result.get('total_revenue', 0)} EUR

Durum: {result.get('status', 'Bilinmiyor')}
    """

    await update.message.reply_text(response, parse_mode="Markdown")

async def handle_message(update: Update, context):
    """
    Genel mesaj isleyici - AI ile dogal dil komutlari
    """
    text = update.message.text
    chat_id = update.effective_chat.id

    # Admin kontrolu
    if chat_id != ADMIN_CHAT_ID:
        await update.message.reply_text("Bu bot sadece admin tarafindan kullanilabilir.")
        return

    print(f"[*] Mesaj alindi: {text}")

    # AI ile komutu parse et
    parsed = ai_parser.parse_command(text)
    print(f"    Parsed: {parsed}")

    intent = parsed.get('intent', 'unknown')
    platform = parsed.get('platform')
    account = parsed.get('account', 'main')
    confidence = parsed.get('confidence', 0)

    if confidence < 0.5 or intent == 'unknown':
        # AI yaniti olustur
        response = ai_parser.generate_response(text)
        await update.message.reply_text(response)
        return

    # Komutu isle
    if intent == 'check_favorites':
        await update.message.reply_text(f"{platform} ({account}) favorileri kontrol ediliyor...")
        result = await store_checker.check_favorites(platform, account)

        response = f"""
**{platform.title()} Favorileri**

Toplam: {result.get('total_favorites', 0)}
Yeni: {result.get('new_favorites', 0)}

{result.get('status', '')}
        """
        await update.message.reply_text(response, parse_mode="Markdown")

    elif intent == 'check_messages':
        await update.message.reply_text(f"{platform} ({account}) mesajlari kontrol ediliyor...")
        result = await store_checker.check_messages(platform, account)

        response = f"""
**{platform.title()} Mesajlari**

Okunmamis: {result.get('unread_count', 0)}

{result.get('status', '')}
        """
        await update.message.reply_text(response, parse_mode="Markdown")

    elif intent == 'check_sales':
        await update.message.reply_text(f"{platform} ({account}) satislari kontrol ediliyor...")
        result = await store_checker.check_sales(platform, account)

        response = f"""
**{platform.title()} Satislari**

Bugun: {result.get('today_sales', 0)}
Bekleyen: {result.get('pending_shipments', 0)}

{result.get('status', '')}
        """
        await update.message.reply_text(response, parse_mode="Markdown")

    elif intent == 'get_stats':
        await update.message.reply_text(f"{platform} ({account}) istatistikleri aliniyor...")
        result = await store_checker.get_store_stats(platform, account)

        response = f"""
**{platform.title()} Istatistikleri**

Aktif Ilan: {result.get('active_listings', 0)}
Goruntulenme: {result.get('total_views', 0)}

{result.get('status', '')}
        """
        await update.message.reply_text(response, parse_mode="Markdown")

    else:
        # Bilinmeyen intent
        response = ai_parser.generate_response(text)
        await update.message.reply_text(response)

async def button_callback(update: Update, context):
    """Buton callback handler"""
    query = update.callback_query
    await query.answer()

    data = query.data

    if data.startswith("store:"):
        parts = data.split(":")
        action = parts[1]
        store = parts[2] if len(parts) > 2 else None

        if action == "favorites" and store:
            store_info = STORE_ALIASES.get(store)
            if store_info:
                result = await store_checker.check_favorites(store_info['platform'], store_info['account'])
                await query.edit_message_text(f"Favoriler: {result}")

# ============================================
# MAIN
# ============================================
def main():
    """Ana fonksiyon"""
    print("=" * 50)
    print("TATANGA - Telegram AI Assistant")
    print("=" * 50)
    print("\nBot baslatiliyor...")

    # Application olustur
    application = Application.builder().token(BOT_TOKEN).build()

    # Command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("stores", stores))
    application.add_handler(CommandHandler("favorites", favorites_command))
    application.add_handler(CommandHandler("messages", messages_command))
    application.add_handler(CommandHandler("sales", sales_command))

    # Callback handler
    application.add_handler(CallbackQueryHandler(button_callback))

    # Message handler - AI isle
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_message
    ))

    print("Bot hazir! Polling baslatiliyor...")
    print(f"Admin Chat ID: {ADMIN_CHAT_ID}")

    # Bot'u calistir
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
