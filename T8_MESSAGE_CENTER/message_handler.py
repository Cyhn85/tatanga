#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TATANGA - T8 Message Center
AI destekli mesaj analizi ve otomatik yanit onerisi
"""

import os
import sys
import json
import time
import re
from pathlib import Path
from datetime import datetime

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.config.credentials import TELEGRAM, AI_SERVICES
import requests

# ============================================
# CONFIGURATION
# ============================================
OUTPUT_DIR = Path(__file__).parent / "output"
LOGS_DIR = Path(__file__).parent / "logs"
TEMPLATES_DIR = Path(__file__).parent / "templates"

OUTPUT_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)
TEMPLATES_DIR.mkdir(exist_ok=True)

# Yanit sablonlari
RESPONSE_TEMPLATES = {
    "accept_offer": {
        "de": "Vielen Dank! Ich akzeptiere Ihr Angebot von {price} EUR. Bitte kaufen Sie den Artikel.",
        "en": "Thank you! I accept your offer of {price} EUR. Please proceed to buy."
    },
    "counter_offer": {
        "de": "Danke fur Ihr Interesse! Der niedrigste Preis, den ich akzeptieren kann, ist {price} EUR.",
        "en": "Thanks for your interest! The lowest price I can accept is {price} EUR."
    },
    "reject_offer": {
        "de": "Danke fur Ihr Interesse, aber der Preis ist leider zu niedrig. Mein Mindestpreis ist {min_price} EUR.",
        "en": "Thanks for your interest, but the price is too low. My minimum is {min_price} EUR."
    },
    "question_size": {
        "de": "Die Grosse ist {size}. Bei Fragen melden Sie sich gerne!",
        "en": "The size is {size}. Feel free to ask if you have questions!"
    },
    "question_condition": {
        "de": "Der Artikel ist in {condition} Zustand. Weitere Details finden Sie in der Beschreibung.",
        "en": "The item is in {condition} condition. More details in the description."
    },
    "shipping_info": {
        "de": "Versand ist moglich mit {carrier}. Lieferzeit ca. {days} Werktage.",
        "en": "Shipping available via {carrier}. Delivery in approximately {days} business days."
    },
    "bundle_discount": {
        "de": "Bei Kauf mehrerer Artikel biete ich gerne einen Rabatt an!",
        "en": "I offer discounts for multiple items!"
    }
}

# ============================================
# TELEGRAM NOTIFICATION
# ============================================
def send_telegram(message, buttons=None):
    """Telegram'a mesaj gonder"""
    url = f"https://api.telegram.org/bot{TELEGRAM['bot_token']}/sendMessage"
    data = {
        "chat_id": TELEGRAM["admin_chat_id"],
        "text": message,
        "parse_mode": "Markdown"
    }

    if buttons:
        keyboard = {"inline_keyboard": buttons}
        data["reply_markup"] = json.dumps(keyboard)

    try:
        resp = requests.post(url, data=data)
        return resp.json()
    except Exception as e:
        print(f"Telegram hatasi: {e}")
        return None

# ============================================
# AI MESSAGE ANALYZER
# ============================================
class MessageAnalyzer:
    """AI ile mesaj analizi"""

    def __init__(self):
        self.api_key = AI_SERVICES['groq']['api_key']
        self.model = AI_SERVICES['groq']['model']

    def analyze_message(self, message, product_info=None):
        """
        Mesaji analiz et ve kategorilendir

        Args:
            message: Alici mesaji
            product_info: Urun bilgileri (fiyat, durum, etc.)

        Returns:
            dict: Analiz sonucu
        """
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            context = ""
            if product_info:
                context = f"""
Product Info:
- Title: {product_info.get('title', '')}
- Price: {product_info.get('price', 0)} EUR
- Condition: {product_info.get('condition', '')}
- Size: {product_info.get('size', '')}
"""

            prompt = f"""
Analyze this buyer message and determine intent:

Message: "{message}"
{context}

Return JSON:
{{
    "intent": "offer" | "question" | "complaint" | "shipping" | "general",
    "sub_intent": "price_offer" | "counter_offer" | "size_question" | "condition_question" | "availability" | "other",
    "offered_price": number or null (if price offer detected),
    "sentiment": "positive" | "neutral" | "negative",
    "urgency": "high" | "medium" | "low",
    "language": "de" | "en" | "other",
    "key_points": ["list of important points"],
    "suggested_action": "accept" | "counter" | "reject" | "answer" | "clarify"
}}

Only return valid JSON.
"""

            data = {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
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

                # JSON parse
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0]
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0]

                return json.loads(content)

        except Exception as e:
            print(f"AI analiz hatasi: {e}")

        return {"intent": "unknown", "suggested_action": "clarify"}

    def generate_response(self, analysis, product_info):
        """
        Analiz sonucuna gore yanit olustur

        Args:
            analysis: AI analiz sonucu
            product_info: Urun bilgileri

        Returns:
            str: Onerilen yanit
        """
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            lang = analysis.get('language', 'de')
            intent = analysis.get('intent', 'general')
            sub_intent = analysis.get('sub_intent', '')
            action = analysis.get('suggested_action', 'answer')
            offered_price = analysis.get('offered_price')

            product_price = product_info.get('price', 0)
            min_price = product_price * 0.85  # %15 indirim limiti

            # Template secimi
            if intent == 'offer' and offered_price:
                if offered_price >= product_price:
                    template_key = "accept_offer"
                elif offered_price >= min_price:
                    template_key = "counter_offer"
                else:
                    template_key = "reject_offer"
            elif sub_intent == 'size_question':
                template_key = "question_size"
            elif sub_intent == 'condition_question':
                template_key = "question_condition"
            elif intent == 'shipping':
                template_key = "shipping_info"
            else:
                # AI ile ozel yanit olustur
                return self._generate_custom_response(analysis, product_info, lang)

            # Template'i doldur
            template = RESPONSE_TEMPLATES.get(template_key, {}).get(lang, "")

            response = template.format(
                price=offered_price or product_price,
                min_price=int(min_price),
                size=product_info.get('size', 'S'),
                condition=product_info.get('condition', 'gut'),
                carrier="DHL",
                days="2-3"
            )

            return response

        except Exception as e:
            print(f"Yanit olusturma hatasi: {e}")
            return ""

    def _generate_custom_response(self, analysis, product_info, lang):
        """AI ile ozel yanit olustur"""
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            prompt = f"""
Generate a polite, professional response in {"German" if lang == "de" else "English"}.

Context:
- Message intent: {analysis.get('intent')}
- Product: {product_info.get('title', '')}
- Price: {product_info.get('price', 0)} EUR
- Key points: {analysis.get('key_points', [])}

Requirements:
- Keep it short (1-2 sentences)
- Be friendly but professional
- Address the buyer's concern directly

Output only the response text, nothing else.
"""

            data = {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 150
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

        except:
            pass

        return ""

# ============================================
# MESSAGE HANDLER
# ============================================
class MessageHandler:
    """Mesaj isleyici"""

    def __init__(self):
        self.analyzer = MessageAnalyzer()
        self.pending_messages = []

    def process_message(self, message_data):
        """
        Gelen mesaji isle

        Args:
            message_data: {
                "platform": "vinted",
                "sender": "garnachuk",
                "message": "Hello, would you accept 15 euro?",
                "product": {...},
                "timestamp": "..."
            }

        Returns:
            dict: Islem sonucu
        """
        message = message_data.get('message', '')
        product = message_data.get('product', {})
        sender = message_data.get('sender', '')
        platform = message_data.get('platform', '')

        print(f"\n[*] Mesaj isleniyor: {sender}")
        print(f"    Mesaj: {message[:50]}...")

        # AI analiz
        analysis = self.analyzer.analyze_message(message, product)
        print(f"    Intent: {analysis.get('intent')}")
        print(f"    Aksiyon: {analysis.get('suggested_action')}")

        # Yanit olustur
        suggested_response = self.analyzer.generate_response(analysis, product)

        result = {
            "message_id": message_data.get('id', ''),
            "platform": platform,
            "sender": sender,
            "original_message": message,
            "analysis": analysis,
            "suggested_response": suggested_response,
            "product": product,
            "processed_at": datetime.now().isoformat(),
            "status": "pending_approval"
        }

        # Telegram'a gonder
        self.send_to_telegram(result)

        return result

    def send_to_telegram(self, result):
        """Telegram'a onay icin gonder"""
        analysis = result['analysis']
        product = result['product']

        # Emoji'ler
        intent_emoji = {
            "offer": "Teklif",
            "question": "Soru",
            "shipping": "Kargo",
            "complaint": "Sikayet",
            "general": "Genel"
        }

        msg = f"""
YENI MESAJ - {result['platform'].upper()}

*Gonderen:* {result['sender']}
*Urun:* {product.get('title', '')[:30]}...
*Fiyat:* {product.get('price', 0)} EUR

*Mesaj:*
_{result['original_message']}_

*AI Analiz:*
- Tur: {intent_emoji.get(analysis.get('intent'), 'Diger')}
- Teklif: {analysis.get('offered_price', '-')} EUR
- Oneri: {analysis.get('suggested_action', '-')}

*Onerilen Yanit:*
```
{result['suggested_response']}
```
"""

        # Butonlar
        buttons = [
            [
                {"text": "Gonder", "callback_data": f"msg:send:{result['message_id']}"},
                {"text": "Duzenle", "callback_data": f"msg:edit:{result['message_id']}"}
            ],
            [
                {"text": "Reddet", "callback_data": f"msg:reject:{result['message_id']}"},
                {"text": "Manuel", "callback_data": f"msg:manual:{result['message_id']}"}
            ]
        ]

        send_telegram(msg, buttons=buttons)

    def handle_telegram_callback(self, callback_data, user_input=None):
        """
        Telegram buton callback'i isle

        Args:
            callback_data: "msg:action:message_id"
            user_input: Kullanici duzenleme (opsiyonel)

        Returns:
            dict: Islem sonucu
        """
        parts = callback_data.split(":")
        if len(parts) < 3:
            return {"error": "Gecersiz callback"}

        action = parts[1]
        message_id = parts[2]

        if action == "send":
            # Mesaji gonder
            return {"status": "sent", "message_id": message_id}

        elif action == "edit":
            # Duzenleme bekle
            return {"status": "awaiting_edit", "message_id": message_id}

        elif action == "reject":
            # Reddet
            return {"status": "rejected", "message_id": message_id}

        elif action == "manual":
            # Manuel isle
            return {"status": "manual", "message_id": message_id}

        return {"error": "Bilinmeyen aksiyon"}

# ============================================
# MAIN
# ============================================
def main():
    import argparse

    parser = argparse.ArgumentParser(description='TATANGA - T8 Message Center')
    parser.add_argument('--demo', action='store_true', help='Demo mod')

    args = parser.parse_args()

    print("=" * 50)
    print("TATANGA - T8 Message Center")
    print("=" * 50)

    handler = MessageHandler()

    if args.demo:
        # Demo: Screenshot'taki mesaji isle
        demo_message = {
            "id": "MSG-001",
            "platform": "vinted",
            "sender": "garnachuk",
            "message": "Hello, would you accept 15 euro?",
            "product": {
                "id": "12345",
                "title": "Paul & Shark Yachting Sweatjacke | Zip-Jacke | Gr. XXL | Schwarz | KPW Patches",
                "price": 25.00,
                "condition": "Gut",
                "size": "XXL"
            },
            "timestamp": datetime.now().isoformat()
        }

        result = handler.process_message(demo_message)

        print("\n" + "=" * 40)
        print("DEMO SONUC:")
        print("=" * 40)
        print(f"Intent: {result['analysis'].get('intent')}")
        print(f"Teklif: {result['analysis'].get('offered_price')} EUR")
        print(f"Oneri: {result['analysis'].get('suggested_action')}")
        print(f"\nOnerilen yanit:\n{result['suggested_response']}")

    else:
        print("\nKullanim:")
        print("  Demo:    python message_handler.py --demo")
        print("\nBu modul T7 Store Monitor ile entegre calisir.")
        print("Yeni mesaj geldiginde otomatik islenir.")

if __name__ == "__main__":
    main()
