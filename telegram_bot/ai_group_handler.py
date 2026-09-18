#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TATANGA - AI Group Handler
Tum gruplardan gelen mesajlari AI ile analiz et ve tetikle
"""

import sys
import json
import time
import requests
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.config.credentials import TELEGRAM, AI_SERVICES

class AIGroupHandler:
    """AI destekli grup mesaj isleyici"""

    def __init__(self):
        self.bot_token = TELEGRAM['bot_token']
        self.channels = TELEGRAM['channels']
        self.ai_key = AI_SERVICES['groq']['api_key']
        self.ai_model = AI_SERVICES['groq']['model']
        self.last_update_id = 0

        # Grup ID -> isim eslestirme
        self.group_names = {
            self.channels['messages']: 'messages',
            self.channels['sales']: 'sales',
            self.channels['shipping']: 'shipping',
            self.channels['notifications']: 'notifications',
            self.channels['system']: 'system',
            self.channels['general']: 'general'
        }

    def get_updates(self):
        """Telegram'dan guncellemeleri al"""
        url = f"https://api.telegram.org/bot{self.bot_token}/getUpdates"
        params = {
            "offset": self.last_update_id + 1,
            "timeout": 30
        }

        try:
            resp = requests.get(url, params=params, timeout=35)
            data = resp.json()
            if data.get("ok"):
                return data.get("result", [])
        except Exception as e:
            print(f"[-] getUpdates hatasi: {e}")

        return []

    def send_message(self, chat_id, text, reply_to=None):
        """Mesaj gonder"""
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        data = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }

        if reply_to:
            data["reply_to_message_id"] = reply_to

        try:
            resp = requests.post(url, data=data)
            return resp.json()
        except Exception as e:
            print(f"[-] sendMessage hatasi: {e}")
            return None

    def analyze_with_ai(self, message, group_type, reply_context=None):
        """AI ile mesaji analiz et"""
        try:
            headers = {
                "Authorization": f"Bearer {self.ai_key}",
                "Content-Type": "application/json"
            }

            context = ""
            if reply_context:
                context = f"\nYanitlanan mesaj: {reply_context}"

            prompt = f"""
Sen TATANGA e-ticaret otomasyon sisteminin AI asistanisin.

Grup: {group_type}
Kullanici mesaji: "{message}"
{context}

Bu mesajdan:
1. Kullanicinin ne istedigini anla
2. Hangi sistem fonksiyonunun tetiklenmesi gerektigini belirle
3. Gerekli parametreleri cikar

JSON formatinda dondur:
{{
    "intent": "mesaj_analizi" | "yanit_olustur" | "satis_raporu" | "kargo_takip" | "favori_listele" | "hata_goster" | "bilgi_ver" | "bilinmeyen",
    "action": "tetiklenecek_fonksiyon",
    "parameters": {{}},
    "response": "kullaniciya verilecek kisa yanit",
    "needs_execution": true/false
}}

Grup tipleri ve fonksiyonlari:
- messages: mesaj_analizi, yanit_olustur, teklif_degerlendir
- sales: satis_listele, gelir_raporu, musteri_bilgi
- shipping: kargo_takip, etiket_olustur, teslim_listele
- notifications: favori_listele, goruntulenme_raporu, trend_analizi
- system: hata_goster, sistem_durumu, log_incele

Sadece JSON dondur.
"""

            data = {
                "model": self.ai_model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 500,
                "temperature": 0.3
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
            print(f"[-] AI analiz hatasi: {e}")

        return {
            "intent": "bilinmeyen",
            "action": "none",
            "parameters": {},
            "response": "Anlasilmadi, lutfen daha acik yazin.",
            "needs_execution": False
        }

    def execute_action(self, analysis, chat_id, group_type):
        """Analiz sonucuna gore aksiyonu calistir"""
        action = analysis.get('action', 'none')
        params = analysis.get('parameters', {})

        result = None

        # MESAJLAR grubu
        if group_type == 'messages':
            if action == 'mesaj_listele':
                result = self.list_messages()
            elif action == 'yanit_olustur':
                result = self.create_reply(params)
            elif action == 'teklif_degerlendir':
                result = self.evaluate_offer(params)

        # SATISLAR grubu
        elif group_type == 'sales':
            if action == 'satis_listele':
                result = self.list_sales(params)
            elif action == 'gelir_raporu':
                result = self.revenue_report(params)

        # KARGO grubu
        elif group_type == 'shipping':
            if action == 'kargo_takip':
                result = self.track_shipping(params)
            elif action == 'etiket_olustur':
                result = self.create_label(params)

        # BILDIRIMLER grubu
        elif group_type == 'notifications':
            if action == 'favori_listele':
                result = self.list_favorites()
            elif action == 'goruntulenme_raporu':
                result = self.view_report()

        # SISTEM grubu
        elif group_type == 'system':
            if action == 'hata_goster':
                result = self.show_errors()
            elif action == 'sistem_durumu':
                result = self.system_status()

        return result

    # ============================================
    # AKSIYON FONKSIYONLARI
    # ============================================

    def list_messages(self):
        """Son mesajlari listele"""
        # TODO: Gercek veri cek
        return "Son 5 mesaj:\n1. garnachuk: 15 EUR teklif\n2. maria92: Beden sorusu\n3. ..."

    def create_reply(self, params):
        """Yanit olustur"""
        return f"Yanit olusturuldu: {params}"

    def evaluate_offer(self, params):
        """Teklifi degerlendir"""
        return f"Teklif degerlendirme: {params}"

    def list_sales(self, params):
        """Satislari listele"""
        period = params.get('period', 'today')
        return f"Satis raporu ({period}): 3 satis, toplam 85 EUR"

    def revenue_report(self, params):
        """Gelir raporu"""
        return "Bu hafta: 245 EUR gelir, 12 satis"

    def track_shipping(self, params):
        """Kargo takip"""
        tracking = params.get('tracking_number', '')
        return f"Kargo {tracking}: Dagitimda"

    def create_label(self, params):
        """Kargo etiketi olustur"""
        return "Etiket olusturuldu"

    def list_favorites(self):
        """Favorileri listele"""
        return "Yeni favoriler:\n- Zara ayakkabi: +3\n- Nike spor: +2"

    def view_report(self):
        """Goruntulenme raporu"""
        return "Son 24 saat: 156 goruntulenme, 12 favori"

    def show_errors(self):
        """Hatalari goster"""
        return "Son hatalar:\n- 12:30 Vinted login timeout\n- 14:15 Kleinanzeigen captcha"

    def system_status(self):
        """Sistem durumu"""
        return "Sistem durumu:\n- Scraper: AKTIF\n- Monitor: AKTIF\n- Bot: AKTIF"

    def process_message(self, message):
        """Mesaji isle"""
        chat_id = message.get("chat", {}).get("id")
        text = message.get("text", "").strip()
        message_id = message.get("message_id")

        if not text:
            return

        # Hangi grup?
        group_type = self.group_names.get(chat_id, "unknown")
        if group_type == "unknown":
            return

        # Reply context
        reply_context = None
        if "reply_to_message" in message:
            reply_context = message["reply_to_message"].get("text", "")

        print(f"[{group_type}] {text[:50]}...")

        # AI ile analiz
        analysis = self.analyze_with_ai(text, group_type, reply_context)

        # Yanit gonder
        response_text = analysis.get('response', 'Isleniyor...')

        # Aksiyon calistir
        if analysis.get('needs_execution'):
            action_result = self.execute_action(analysis, chat_id, group_type)
            if action_result:
                response_text += f"\n\n{action_result}"

        self.send_message(chat_id, response_text, reply_to=message_id)

    def run(self):
        """Bot'u calistir"""
        print("=" * 60)
        print("TATANGA - AI Group Handler")
        print("=" * 60)
        print("\nDinlenen gruplar:")
        for name, chat_id in self.channels.items():
            if chat_id:
                print(f"  - {name}: {chat_id}")

        print("\nDinleniyor... (Ctrl+C ile durdur)\n")

        while True:
            try:
                updates = self.get_updates()

                for update in updates:
                    self.last_update_id = update.get("update_id", self.last_update_id)

                    if "message" in update:
                        self.process_message(update["message"])

            except KeyboardInterrupt:
                print("\n\nDurduruldu.")
                break

            except Exception as e:
                print(f"[-] Hata: {e}")
                time.sleep(5)

if __name__ == "__main__":
    handler = AIGroupHandler()
    handler.run()
