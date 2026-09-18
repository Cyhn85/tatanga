#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TATANGA - Telegram Approval Bot
Onay butonlari ve metin mesajlarini isle
"""

import sys
import json
import time
import requests
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.config.credentials import TELEGRAM, VINTED

PENDING_DIR = Path(__file__).parent / "pending_approval"
PENDING_DIR.mkdir(exist_ok=True)

class TelegramApprovalBot:
    """Telegram onay bot'u - polling ile"""

    def __init__(self):
        self.bot_token = TELEGRAM['bot_token']
        self.admin_chat = TELEGRAM['admin_chat_id']
        self.last_update_id = 0
        self.waiting_for_input = {}  # {chat_id: {"type": "price", "product_id": "xxx"}}

    def get_updates(self):
        """Yeni mesajlari al"""
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

    def send_message(self, text, reply_markup=None):
        """Mesaj gonder"""
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        data = {
            "chat_id": self.admin_chat,
            "text": text,
            "parse_mode": "Markdown"
        }

        if reply_markup:
            data["reply_markup"] = json.dumps(reply_markup)

        try:
            requests.post(url, data=data)
        except Exception as e:
            print(f"[-] sendMessage hatasi: {e}")

    def answer_callback(self, callback_id, text=""):
        """Callback'e cevap ver"""
        url = f"https://api.telegram.org/bot{self.bot_token}/answerCallbackQuery"
        data = {
            "callback_query_id": callback_id,
            "text": text
        }
        try:
            requests.post(url, data=data)
        except:
            pass

    def load_pending_product(self, product_id):
        """Bekleyen urunu yukle"""
        pending_file = PENDING_DIR / f"{product_id}.json"
        if pending_file.exists():
            with open(pending_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return None

    def save_pending_product(self, product_id, data):
        """Bekleyen urunu kaydet"""
        pending_file = PENDING_DIR / f"{product_id}.json"
        with open(pending_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def process_callback(self, callback):
        """Buton callback'ini isle"""
        callback_id = callback.get("id")
        data = callback.get("data", "")
        chat_id = callback.get("from", {}).get("id")

        parts = data.split(":")
        if len(parts) < 2:
            return

        action = parts[0]
        product_id = parts[1] if len(parts) > 1 else ""

        print(f"[*] Callback: {action} - {product_id}")

        if action == "approve":
            # ONAYLA
            self.answer_callback(callback_id, "Urun onaylandi!")
            product = self.load_pending_product(product_id)
            if product:
                self.send_message(f"*ONAYLANDI!* Urun Vinted'e yukleniyor...\n\nID: `{product_id}`")
                # Burada upload fonksiyonunu cagir
                self.upload_to_vinted(product)
            else:
                self.send_message(f"[-] Urun bulunamadi: {product_id}")

        elif action == "reject":
            # REDDET
            self.answer_callback(callback_id, "Urun reddedildi")
            self.send_message(f"*REDDEDILDI*\n\nID: `{product_id}`")
            # Dosyayi sil
            pending_file = PENDING_DIR / f"{product_id}.json"
            if pending_file.exists():
                pending_file.unlink()

        elif action == "price":
            # Fiyat degistir
            self.answer_callback(callback_id, "Yeni fiyati yazin")
            self.waiting_for_input[chat_id] = {
                "type": "price",
                "product_id": product_id
            }
            self.send_message(f"Yeni fiyati yazin (sadece sayi):\n\nOrnek: `35`")

        elif action == "title":
            # Baslik degistir
            self.answer_callback(callback_id, "Yeni basligi yazin")
            self.waiting_for_input[chat_id] = {
                "type": "title",
                "product_id": product_id
            }
            self.send_message(f"Yeni basligi yazin:")

        elif action == "reprocess":
            # Resimleri tekrar isle
            self.answer_callback(callback_id, "Resimler isleniyor...")
            product = self.load_pending_product(product_id)
            if product:
                new_images = self.reprocess_images_aggressive(product)
                if new_images:
                    product['images'] = new_images
                    self.save_pending_product(product_id, product)
                    self.resend_approval(product)
                else:
                    self.send_message("[-] Resim isleme basarisiz!")
            else:
                self.send_message(f"[-] Urun bulunamadi: {product_id}")

    def process_message(self, message):
        """Metin mesajini isle"""
        chat_id = message.get("chat", {}).get("id")
        text = message.get("text", "").strip()

        if not text:
            return

        print(f"[*] Mesaj: {text[:50]}...")

        # Bekleyen input var mi?
        if chat_id in self.waiting_for_input:
            waiting = self.waiting_for_input[chat_id]
            product_id = waiting["product_id"]
            input_type = waiting["type"]

            product = self.load_pending_product(product_id)
            if not product:
                self.send_message(f"[-] Urun bulunamadi: {product_id}")
                del self.waiting_for_input[chat_id]
                return

            if input_type == "price":
                # Fiyat guncelle
                try:
                    new_price = int(text.replace("EUR", "").replace("€", "").strip())
                    product["optimized"]["price"] = new_price
                    self.save_pending_product(product_id, product)
                    self.send_message(f"Fiyat guncellendi: *{new_price} EUR*\n\nOnaylamak icin ONAYLA butonuna basin.")
                except:
                    self.send_message("Gecersiz fiyat! Sadece sayi girin.\nOrnek: `35`")
                    return

            elif input_type == "title":
                # Baslik guncelle
                product["optimized"]["title"] = text
                self.save_pending_product(product_id, product)
                self.send_message(f"Baslik guncellendi:\n*{text}*\n\nOnaylamak icin ONAYLA butonuna basin.")

            elif input_type == "description":
                # Aciklama guncelle
                product["optimized"]["description"] = text
                self.save_pending_product(product_id, product)
                self.send_message(f"Aciklama guncellendi.\n\nOnaylamak icin ONAYLA butonuna basin.")

            del self.waiting_for_input[chat_id]

        else:
            # Genel mesaj - komut veya degisiklik istegi olabilir
            text_lower = text.lower()

            # Fiyat degisikligi istegi
            if any(word in text_lower for word in ["fiyat", "price", "euro", "eur"]):
                # Son bekleyen urunu bul
                pending_files = list(PENDING_DIR.glob("PROD-*.json"))
                if pending_files:
                    latest = max(pending_files, key=lambda p: p.stat().st_mtime)
                    product_id = latest.stem
                    self.waiting_for_input[chat_id] = {
                        "type": "price",
                        "product_id": product_id
                    }
                    self.send_message(f"Urun: `{product_id}`\n\nYeni fiyati yazin (sadece sayi):")
                else:
                    self.send_message("Bekleyen urun yok.")

            # Baslik degisikligi
            elif any(word in text_lower for word in ["baslik", "title", "isim", "ad"]):
                pending_files = list(PENDING_DIR.glob("PROD-*.json"))
                if pending_files:
                    latest = max(pending_files, key=lambda p: p.stat().st_mtime)
                    product_id = latest.stem
                    self.waiting_for_input[chat_id] = {
                        "type": "title",
                        "product_id": product_id
                    }
                    self.send_message(f"Urun: `{product_id}`\n\nYeni basligi yazin:")
                else:
                    self.send_message("Bekleyen urun yok.")

            # Aciklama degisikligi
            elif any(word in text_lower for word in ["aciklama", "description", "tanim"]):
                pending_files = list(PENDING_DIR.glob("PROD-*.json"))
                if pending_files:
                    latest = max(pending_files, key=lambda p: p.stat().st_mtime)
                    product_id = latest.stem
                    self.waiting_for_input[chat_id] = {
                        "type": "description",
                        "product_id": product_id
                    }
                    self.send_message(f"Urun: `{product_id}`\n\nYeni aciklamayi yazin:")
                else:
                    self.send_message("Bekleyen urun yok.")

            # Resim degisikligi istegi
            elif any(word in text_lower for word in ["resim", "foto", "image", "kopya", "uzaklastir", "hassas"]):
                # AI ile mesaji analiz et ve resimleri guncelle
                pending_files = list(PENDING_DIR.glob("PROD-*.json"))
                if pending_files:
                    latest = max(pending_files, key=lambda p: p.stat().st_mtime)
                    product_id = latest.stem
                    product = self.load_pending_product(product_id)

                    if product:
                        self.send_message(f"*RESIMLER GUNCELLENIYOR...*\n\nUrun: `{product_id}`\n\nDaha agresif isleme uygulaniyor...")

                        # Resimleri daha agresif isle
                        new_images = self.reprocess_images_aggressive(product)

                        if new_images:
                            product['images'] = new_images
                            self.save_pending_product(product_id, product)

                            # Tekrar onaya sun
                            self.resend_approval(product)
                        else:
                            self.send_message("[-] Resim isleme basarisiz!")
                else:
                    self.send_message("Bekleyen urun yok.")

            # Yardim
            elif any(word in text_lower for word in ["yardim", "help", "komut"]):
                self.send_message("*TATANGA Transfer Bot*\n\n"
                                  "*Butonlar:*\n"
                                  "- ONAYLA: Urunu Vinted'e yukle\n"
                                  "- REDDET: Transferi iptal et\n"
                                  "- Fiyat Degistir: Yeni fiyat gir\n"
                                  "- Baslik Degistir: Yeni baslik gir\n\n"
                                  "*Mesaj ile:*\n"
                                  "- 'fiyat 35' - Fiyati 35 EUR yap\n"
                                  "- 'baslik ...' - Basligi degistir\n"
                                  "- 'aciklama ...' - Aciklamayi degistir")

            else:
                # Bilinmeyen mesaj
                self.send_message("Anlasilmadi. Butonlari kullanin veya:\n"
                                  "- 'fiyat' yazin fiyat degistirmek icin\n"
                                  "- 'baslik' yazin baslik degistirmek icin\n"
                                  "- 'yardim' yazin komutlari gormek icin")

    def reprocess_images_aggressive(self, product):
        """Resimleri daha agresif isle - Vinted duplicate tespitinden kacinmak icin"""
        try:
            from PIL import Image, ImageEnhance, ImageFilter
            import hashlib
            import random

            TEMP_DIR = Path(__file__).parent / "temp"
            processed_dir = TEMP_DIR / "processed_v2"
            processed_dir.mkdir(exist_ok=True)

            product_id = product['id']
            original_images = product.get('images', [])
            new_images = []

            for i, img_path in enumerate(original_images):
                try:
                    img = Image.open(img_path)

                    # 1. Rastgele boyut degisikligi (%90-96)
                    scale = random.uniform(0.90, 0.96)
                    new_width = int(img.width * scale)
                    new_height = int(img.height * scale)
                    img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

                    # 2. Rastgele parlaklik (%97-103)
                    brightness = random.uniform(0.97, 1.03)
                    enhancer = ImageEnhance.Brightness(img)
                    img = enhancer.enhance(brightness)

                    # 3. Rastgele kontrast (%98-102)
                    contrast = random.uniform(0.98, 1.02)
                    enhancer = ImageEnhance.Contrast(img)
                    img = enhancer.enhance(contrast)

                    # 4. Hafif renk doygunlugu (%95-105)
                    saturation = random.uniform(0.95, 1.05)
                    enhancer = ImageEnhance.Color(img)
                    img = enhancer.enhance(saturation)

                    # 5. Cok hafif blur (Vinted hash'i kirma)
                    if random.random() > 0.5:
                        img = img.filter(ImageFilter.GaussianBlur(radius=0.3))

                    # 6. Kenar kirpma (1-3 piksel)
                    crop_pixels = random.randint(1, 3)
                    img = img.crop((crop_pixels, crop_pixels,
                                    img.width - crop_pixels, img.height - crop_pixels))

                    # RGB'ye cevir
                    if img.mode == 'RGBA':
                        img = img.convert('RGB')

                    # Benzersiz isim
                    hash_suffix = hashlib.md5(f"{product_id}{i}{time.time()}{random.random()}".encode()).hexdigest()[:8]
                    new_filename = f"{product_id}_v2_{i+1}_{hash_suffix}.jpg"
                    new_path = processed_dir / new_filename

                    # Rastgele kalite (%88-94)
                    quality = random.randint(88, 94)
                    img.save(new_path, 'JPEG', quality=quality)
                    new_images.append(str(new_path))

                except Exception as e:
                    print(f"[-] Resim {i+1} islenemedi: {e}")
                    new_images.append(img_path)

            return new_images

        except ImportError:
            self.send_message("[-] PIL yuklu degil!")
            return None
        except Exception as e:
            print(f"[-] Agresif isleme hatasi: {e}")
            return None

    def resend_approval(self, product):
        """Guncellenmis urunu tekrar onaya sun"""
        product_id = product['id']
        original = product['original']
        optimized = product['optimized']

        caption = f"""
*GUNCELLENMIS URUN - TEKRAR ONAY*

*ID:* `{product_id}`

*Baslik:* {optimized['title'][:60]}...
*Fiyat:* {optimized['price']} EUR

*Resimler:* Daha agresif islendi
- Boyut: %90-96 rastgele
- Parlaklik/Kontrast: Rastgele
- Kenar kirpma: 1-3px
- Kalite: %88-94 rastgele

Simdi Vinted duplicate tespitinden kacinacak!
"""

        buttons = [
            [
                {"text": "ONAYLA", "callback_data": f"approve:{product_id}"},
                {"text": "REDDET", "callback_data": f"reject:{product_id}"}
            ],
            [
                {"text": "Tekrar Isle", "callback_data": f"reprocess:{product_id}"},
                {"text": "Fiyat Degistir", "callback_data": f"price:{product_id}"}
            ]
        ]

        # Ilk resmi gonder
        if product.get('images'):
            url = f"https://api.telegram.org/bot{self.bot_token}/sendPhoto"
            with open(product['images'][0], 'rb') as photo:
                files = {'photo': photo}
                data = {
                    'chat_id': self.admin_chat,
                    'caption': caption,
                    'parse_mode': 'Markdown',
                    'reply_markup': json.dumps({'inline_keyboard': buttons})
                }
                requests.post(url, files=files, data=data)
        else:
            self.send_message(caption)

    def upload_to_vinted(self, product):
        """Urunu Vinted'e yukle"""
        product_id = product['id']
        optimized = product['optimized']

        self.send_message(f"*YUKLEME BASLATILDI*\n\n"
                          f"Baslik: {optimized['title']}\n"
                          f"Fiyat: {optimized['price']} EUR\n\n"
                          f"Lutfen bekleyin...")

        # TODO: Burada gercek upload yapilacak
        # from product_transfer_v2 import ProductUploader
        # uploader = ProductUploader()
        # result = uploader.upload_to_vinted(...)

        # Simdilik sadece mesaj
        self.send_message(f"[TEST] Urun Vinted'e yuklenecek:\n\n"
                          f"ID: `{product_id}`\n"
                          f"Baslik: {optimized['title']}\n"
                          f"Fiyat: {optimized['price']} EUR\n\n"
                          f"Gercek upload icin 'upload_to_vinted' fonksiyonunu tamamlayin.")

    def run(self):
        """Bot'u calistir (polling)"""
        print("=" * 60)
        print("TATANGA - Telegram Approval Bot")
        print("=" * 60)
        print(f"\nBot: @{TELEGRAM.get('bot_username', 'cssberlin_notify_bot')}")
        print(f"Admin: {self.admin_chat}")
        print("\nDinleniyor... (Ctrl+C ile durdur)\n")

        while True:
            try:
                updates = self.get_updates()

                for update in updates:
                    self.last_update_id = update.get("update_id", self.last_update_id)

                    # Callback (buton)
                    if "callback_query" in update:
                        self.process_callback(update["callback_query"])

                    # Mesaj
                    elif "message" in update:
                        self.process_message(update["message"])

            except KeyboardInterrupt:
                print("\n\nDurduruldu.")
                break

            except Exception as e:
                print(f"[-] Hata: {e}")
                time.sleep(5)

if __name__ == "__main__":
    bot = TelegramApprovalBot()
    bot.run()
