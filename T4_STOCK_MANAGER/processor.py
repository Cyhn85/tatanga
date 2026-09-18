#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TATANGA - T4 Stock Manager
Stoklu urun giris sistemi
"""

import os
import sys
import json
import time
import base64
import requests
from pathlib import Path
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.config.credentials import TELEGRAM, AI_SERVICES

# ============================================
# CONFIGURATION
# ============================================
INBOX_DIR = Path(__file__).parent / "inbox"
OUTPUT_DIR = Path(__file__).parent / "output"
LOGS_DIR = Path(__file__).parent / "logs"

# Ensure directories exist
INBOX_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

# ============================================
# TELEGRAM NOTIFICATION
# ============================================
def send_telegram(message):
    """Telegram'a mesaj gonder"""
    url = f"https://api.telegram.org/bot{TELEGRAM['bot_token']}/sendMessage"
    data = {
        "chat_id": TELEGRAM["admin_chat_id"],
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, data=data)
    except Exception as e:
        print(f"Telegram hatasi: {e}")

# ============================================
# AI EXTRACTION
# ============================================
def extract_from_screenshot(image_path):
    """
    Groq ile screenshot'tan urun bilgisi cikar
    """
    try:
        # Read image as base64
        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode()

        # Groq API call
        headers = {
            "Authorization": f"Bearer {AI_SERVICES['groq']['api_key']}",
            "Content-Type": "application/json"
        }

        prompt = """
        Bu Almanca urun aciklamasi screenshot'indan bilgileri JSON formatinda cikar:

        {
            "brand": "marka adi",
            "type": "urun turu (Hemd, Hose, Jacke, Schuhe, vb.)",
            "size": "beden (S, M, L, XL, 38, 42, vb.)",
            "condition": "durum (Neu, Sehr gut, Gut, Akzeptabel)",
            "color": "renk",
            "material": "kumas (varsa)",
            "gender": "Herren/Damen/Kinder",
            "description_de": "Almanca aciklama metni (2-3 cumle)",
            "suggested_price": "onerilen fiyat EUR (sayi olarak)"
        }

        Sadece JSON dondur, baska birsey yazma.
        Eger bilgi bulamazsan o alani bos birak.
        """

        # Note: Groq doesn't support vision yet, using text extraction
        # For now, return placeholder - will be enhanced

        return {
            "brand": "",
            "type": "",
            "size": "",
            "condition": "Gut",
            "color": "",
            "material": "",
            "gender": "Herren",
            "description_de": "",
            "suggested_price": 0
        }

    except Exception as e:
        print(f"AI extraction hatasi: {e}")
        return None

def generate_description(product_info):
    """
    Groq ile Almanca aciklama olustur
    """
    try:
        headers = {
            "Authorization": f"Bearer {AI_SERVICES['groq']['api_key']}",
            "Content-Type": "application/json"
        }

        prompt = f"""
        Su urun icin Almanca satis aciklamasi yaz (2-3 cumle):

        Marka: {product_info.get('brand', 'Unbekannt')}
        Tur: {product_info.get('type', 'Kleidung')}
        Beden: {product_info.get('size', '')}
        Durum: {product_info.get('condition', 'Gut')}
        Renk: {product_info.get('color', '')}

        Profesyonel ve kisa tut. Sadece aciklamayi yaz.
        """

        data = {
            "model": AI_SERVICES['groq']['model'],
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 200
        }

        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers,
            json=data
        )

        if response.status_code == 200:
            result = response.json()
            return result['choices'][0]['message']['content'].strip()
        else:
            return f"Original {product_info.get('brand', '')} {product_info.get('type', 'Artikel')} in gutem Zustand."

    except Exception as e:
        print(f"Description generation hatasi: {e}")
        return ""

# ============================================
# FILE HANDLER
# ============================================
class StockProductHandler(FileSystemEventHandler):
    """Yeni urun klasoru algilayici"""

    def on_created(self, event):
        if event.is_directory:
            # Yeni urun klasoru eklendi
            folder_path = Path(event.src_path)
            print(f"\n[+] Yeni urun klasoru: {folder_path.name}")

            # Biraz bekle (dosyalar yukleniyor olabilir)
            time.sleep(3)

            # Urunu isle
            self.process_product_folder(folder_path)

    def process_product_folder(self, folder_path):
        """Urun klasorunu isle"""

        product_id = f"STOCK-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        # Dosyalari bul
        images = []
        screenshot = None

        for file in folder_path.iterdir():
            if file.suffix.lower() in ['.jpg', '.jpeg', '.png', '.webp']:
                if 'aciklama' in file.name.lower() or 'desc' in file.name.lower():
                    screenshot = file
                else:
                    images.append(str(file))

        if not images:
            print(f"[-] Resim bulunamadi: {folder_path.name}")
            return

        print(f"[*] {len(images)} resim bulundu")

        # Screenshot'tan bilgi cikar
        product_info = {}
        if screenshot:
            print(f"[*] Screenshot analiz ediliyor: {screenshot.name}")
            product_info = extract_from_screenshot(screenshot) or {}

        # Eksik bilgileri doldur
        if not product_info.get('description_de'):
            product_info['description_de'] = generate_description(product_info)

        # Urun objesi olustur
        product = {
            "id": product_id,
            "source": "stock",
            "folder": str(folder_path),
            "images": images,
            "screenshot": str(screenshot) if screenshot else None,
            "brand": product_info.get('brand', ''),
            "type": product_info.get('type', ''),
            "size": product_info.get('size', ''),
            "condition": product_info.get('condition', 'Gut'),
            "color": product_info.get('color', ''),
            "gender": product_info.get('gender', 'Herren'),
            "description_de": product_info.get('description_de', ''),
            "price": product_info.get('suggested_price', 0),
            "created_at": datetime.now().isoformat(),
            "status": "pending",
            "listings": {}
        }

        # Kaydet
        output_file = OUTPUT_DIR / "stock_products.json"

        # Mevcut urunleri oku
        products = []
        if output_file.exists():
            with open(output_file, 'r', encoding='utf-8') as f:
                products = json.load(f)

        # Yeni urunu ekle
        products.append(product)

        # Kaydet
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(products, f, ensure_ascii=False, indent=2)

        print(f"[+] Urun kaydedildi: {product_id}")

        # Telegram bildirim
        msg = f"""
Yeni Stoklu Urun Eklendi!

ID: {product_id}
Marka: {product.get('brand') or 'Belirsiz'}
Tur: {product.get('type') or 'Belirsiz'}
Beden: {product.get('size') or 'Belirsiz'}
Resim: {len(images)} adet

Sonraki adim: Resim isleme (T5)
        """
        send_telegram(msg)

        # Log
        log_file = LOGS_DIR / f"{datetime.now().strftime('%Y%m%d')}.log"
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f"{datetime.now().isoformat()} - Yeni urun: {product_id}\n")

# ============================================
# MAIN
# ============================================
def main():
    print("=" * 50)
    print("TATANGA - T4 Stock Manager")
    print("=" * 50)
    print(f"\nInbox klasoru: {INBOX_DIR}")
    print("Yeni urun eklemek icin inbox klasorune bir klasor atin.")
    print("Klasor icinde: resimler + aciklama.png (opsiyonel)")
    print("\nDinleniyor... (Ctrl+C ile durdur)\n")

    # Telegram bildirim
    send_telegram("T4 Stock Manager baslatildi. Inbox klasoru dinleniyor.")

    # Observer baslat
    event_handler = StockProductHandler()
    observer = Observer()
    observer.schedule(event_handler, str(INBOX_DIR), recursive=False)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        print("\nDurduruldu.")

    observer.join()

if __name__ == "__main__":
    main()
