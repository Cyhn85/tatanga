#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram SMS Handler
SMS kodu istemek ve almak icin Telegram entegrasyonu
"""

import asyncio
import time
import requests
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.config.credentials import TELEGRAM

class TelegramSMSHandler:
    """Telegram uzerinden SMS kodu isteme ve alma"""

    def __init__(self):
        self.bot_token = TELEGRAM['bot_token']
        self.captcha_chat_id = TELEGRAM['channels']['captcha_approval']
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
        self.last_update_id = 0

    def send_message(self, text, chat_id=None):
        """Telegram'a mesaj gonder"""
        if chat_id is None:
            chat_id = self.captcha_chat_id

        url = f"{self.base_url}/sendMessage"
        data = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }

        try:
            response = requests.post(url, data=data, timeout=30)
            return response.status_code == 200
        except Exception as e:
            print(f"Telegram mesaj hatasi: {e}")
            return False

    def get_updates(self, timeout=30):
        """Yeni mesajlari al"""
        url = f"{self.base_url}/getUpdates"
        params = {
            "offset": self.last_update_id + 1,
            "timeout": timeout
        }

        try:
            response = requests.get(url, params=params, timeout=timeout + 10)
            if response.status_code == 200:
                return response.json().get('result', [])
        except Exception as e:
            print(f"Telegram update hatasi: {e}")

        return []

    def request_sms_code(self, platform, phone_hint="", reference="", timeout_seconds=120):
        """
        SMS kodu iste ve bekle

        Args:
            platform: Platform adi (Willhaben, Vinted, etc.)
            phone_hint: Telefon numarasi ipucu (***2485 gibi)
            reference: Referans kodu (varsa)
            timeout_seconds: Maksimum bekleme suresi

        Returns:
            str: SMS kodu veya None
        """
        # Mesaj olustur
        message = f"*{platform} SMS DOGRULAMA*\n\n"
        message += f"SMS kodu bekleniyor!\n\n"

        if phone_hint:
            message += f"Telefon: `{phone_hint}`\n"
        if reference:
            message += f"Referans: `{reference}`\n"

        message += f"\nLutfen 4 haneli kodu yazip gonderin.\n"
        message += f"_(Ornek: 1234)_\n\n"
        message += f"Bekleme suresi: {timeout_seconds} saniye"

        # Mesaji gonder
        if not self.send_message(message):
            print("SMS istegi gonderilemedi!")
            return None

        print(f"SMS kodu istendi - {platform}")
        print(f"Bekleniyor... (max {timeout_seconds}s)")

        # Mevcut update ID'yi kaydet
        updates = self.get_updates(timeout=1)
        if updates:
            self.last_update_id = updates[-1]['update_id']

        # Kodu bekle
        start_time = time.time()

        while time.time() - start_time < timeout_seconds:
            updates = self.get_updates(timeout=5)

            for update in updates:
                self.last_update_id = update['update_id']

                # Mesaj kontrolu
                message_obj = update.get('message', {})
                text = message_obj.get('text', '').strip()
                chat_id = message_obj.get('chat', {}).get('id')

                # Dogru kanaldan mi geldi?
                if chat_id == self.captcha_chat_id:
                    # 4 haneli sayi mi?
                    if text.isdigit() and len(text) == 4:
                        # Onay mesaji gonder
                        self.send_message(f"Kod alindi: `{text}`\nIslem devam ediyor...")
                        print(f"SMS kodu alindi: {text}")
                        return text

            # Kalan sureyi goster
            elapsed = int(time.time() - start_time)
            remaining = timeout_seconds - elapsed
            if elapsed % 15 == 0 and remaining > 0:
                print(f"Bekleniyor... {remaining}s kaldi")

        # Timeout
        self.send_message("Zaman asimi! SMS kodu alinamadi.")
        print("SMS kodu timeout!")
        return None

    def notify(self, message, chat_id=None):
        """Bildirim gonder"""
        return self.send_message(message, chat_id)

    def notify_success(self, platform, action):
        """Basari bildirimi"""
        text = f"*{platform}*\n{action} BASARILI!"
        return self.send_message(text)

    def notify_error(self, platform, error):
        """Hata bildirimi"""
        text = f"*{platform}*\nHATA: {error}"
        return self.send_message(text)


# Test
if __name__ == "__main__":
    handler = TelegramSMSHandler()

    print("=" * 60)
    print("TELEGRAM SMS HANDLER TEST")
    print("=" * 60)

    # Test mesaji gonder
    print("\n1. Test mesaji gonderiliyor...")
    handler.send_message("*Test Mesaji*\nTelegram SMS Handler calisiyor!")

    # SMS kodu iste
    print("\n2. SMS kodu isteniyor...")
    code = handler.request_sms_code(
        platform="WILLHABEN",
        phone_hint="***2485",
        reference="test123",
        timeout_seconds=60
    )

    if code:
        print(f"\nSMS Kodu: {code}")
    else:
        print("\nSMS kodu alinamadi!")
