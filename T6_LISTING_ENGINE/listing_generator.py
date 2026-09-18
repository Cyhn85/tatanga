#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TATANGA - T6 Listing Engine
Yari-otomatik ilan olusturma ve Telegram entegrasyonu
"""

import os
import sys
import json
import time
import requests
from pathlib import Path
from datetime import datetime

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.config.credentials import TELEGRAM, AI_SERVICES, KLEINANZEIGEN, EBAY, WILLHABEN, VINTED

# ============================================
# CONFIGURATION
# ============================================
OUTPUT_DIR = Path(__file__).parent / "output"
TEMPLATES_DIR = Path(__file__).parent / "templates"
LOGS_DIR = Path(__file__).parent / "logs"

OUTPUT_DIR.mkdir(exist_ok=True)
TEMPLATES_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

# Platform ozellikleri
PLATFORM_SPECS = {
    "vinted": {
        "title_max": 80,
        "description_max": 2000,
        "image_max": 20,
        "has_shipping": True,
        "categories_required": True
    },
    "kleinanzeigen": {
        "title_max": 65,
        "description_max": 4000,
        "image_max": 20,
        "has_shipping": True,
        "categories_required": True
    },
    "ebay": {
        "title_max": 80,
        "description_max": 4000,
        "image_max": 12,
        "has_shipping": True,
        "categories_required": True
    },
    "willhaben": {
        "title_max": 100,
        "description_max": 4000,
        "image_max": 20,
        "has_shipping": True,
        "categories_required": True
    }
}

# ============================================
# TELEGRAM NOTIFICATION
# ============================================
def send_telegram(message, chat_id=None, buttons=None):
    """Telegram'a mesaj gonder"""
    if not chat_id:
        chat_id = TELEGRAM["admin_chat_id"]

    url = f"https://api.telegram.org/bot{TELEGRAM['bot_token']}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"
    }

    if buttons:
        # Inline keyboard
        keyboard = {
            "inline_keyboard": buttons
        }
        data["reply_markup"] = json.dumps(keyboard)

    try:
        resp = requests.post(url, data=data)
        return resp.json()
    except Exception as e:
        print(f"Telegram hatasi: {e}")
        return None

def send_telegram_photo(photo_path, caption="", chat_id=None):
    """Telegram'a foto gonder"""
    if not chat_id:
        chat_id = TELEGRAM["admin_chat_id"]

    url = f"https://api.telegram.org/bot{TELEGRAM['bot_token']}/sendPhoto"

    with open(photo_path, 'rb') as photo:
        files = {'photo': photo}
        data = {
            'chat_id': chat_id,
            'caption': caption,
            'parse_mode': 'Markdown'
        }
        try:
            resp = requests.post(url, files=files, data=data)
            return resp.json()
        except Exception as e:
            print(f"Telegram foto hatasi: {e}")
            return None

# ============================================
# AI DESCRIPTION GENERATOR
# ============================================
def generate_description(product_info, platform="vinted", language="de"):
    """
    Groq ile platform-spesifik aciklama olustur
    """
    try:
        headers = {
            "Authorization": f"Bearer {AI_SERVICES['groq']['api_key']}",
            "Content-Type": "application/json"
        }

        platform_spec = PLATFORM_SPECS.get(platform, {})
        max_length = platform_spec.get('description_max', 2000)

        prompt = f"""
        Write a German product description for {platform} marketplace.

        Product Info:
        - Brand: {product_info.get('brand', 'Unknown')}
        - Type: {product_info.get('type', 'Artikel')}
        - Size: {product_info.get('size', '')}
        - Condition: {product_info.get('condition', 'Gut')}
        - Color: {product_info.get('color', '')}
        - Material: {product_info.get('material', '')}

        Requirements:
        - Max {max_length} characters
        - Professional but friendly tone
        - Include shipping info: "Versand moglich"
        - Mention condition honestly
        - Add hashtags at end for Vinted

        Output in German only.
        """

        data = {
            "model": AI_SERVICES['groq']['model'],
            "messages": [
                {"role": "user", "content": prompt}
            ],
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
        print(f"AI description hatasi: {e}")

    # Fallback basit aciklama
    return f"""Original {product_info.get('brand', '')} {product_info.get('type', 'Artikel')} in {product_info.get('condition', 'gutem')} Zustand.

Grosse: {product_info.get('size', 'Siehe Fotos')}
Farbe: {product_info.get('color', 'Siehe Fotos')}

Versand moglich.
Bei Fragen gerne melden!"""

def generate_title(product_info, platform="vinted"):
    """
    Baslik olustur
    """
    brand = product_info.get('brand', '')
    ptype = product_info.get('type', 'Artikel')
    size = product_info.get('size', '')
    condition = product_info.get('condition', '')

    # Baslik olustur
    parts = []
    if brand:
        parts.append(brand)
    if ptype:
        parts.append(ptype)
    if size:
        parts.append(f"Gr. {size}")
    if condition and condition != "Gut":
        parts.append(condition)

    title = " ".join(parts)

    # Platform limitine gore kes
    max_len = PLATFORM_SPECS.get(platform, {}).get('title_max', 80)
    if len(title) > max_len:
        title = title[:max_len-3] + "..."

    return title

# ============================================
# LISTING GENERATOR
# ============================================
class ListingGenerator:
    """Ilan olusturucu"""

    def __init__(self):
        self.output_dir = OUTPUT_DIR

    def create_listing(self, product_info, platforms=None):
        """
        Urun icin tum platformlara ilan olustur
        """
        if platforms is None:
            platforms = ["vinted", "kleinanzeigen", "ebay", "willhaben"]

        listings = {}
        product_id = product_info.get('id', f"PROD-{datetime.now().strftime('%Y%m%d%H%M%S')}")

        print(f"\n[*] Ilan olusturuluyor: {product_id}")

        for platform in platforms:
            print(f"    [{platform}] isleniyor...")

            listing = {
                "platform": platform,
                "product_id": product_id,
                "title": generate_title(product_info, platform),
                "description": generate_description(product_info, platform),
                "price": product_info.get('price', 0),
                "images": product_info.get('processed_images', {}).get(platform, product_info.get('images', [])),
                "size": product_info.get('size', ''),
                "brand": product_info.get('brand', ''),
                "condition": product_info.get('condition', 'Gut'),
                "created_at": datetime.now().isoformat(),
                "status": "draft"
            }

            listings[platform] = listing

            # Platforma ozel ayarlar
            if platform == "vinted":
                listing["shipping_options"] = ["Vinted Versand", "Abholung"]
            elif platform == "kleinanzeigen":
                listing["shipping_options"] = ["Versand", "Abholung"]
            elif platform == "ebay":
                listing["shipping_options"] = ["DHL Paket"]
            elif platform == "willhaben":
                listing["shipping_options"] = ["Versand", "Selbstabholung"]

        # Kaydet
        output_file = self.output_dir / f"listing_{product_id}.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(listings, f, ensure_ascii=False, indent=2)

        print(f"\n[+] Ilanlar kaydedildi: {output_file}")

        return listings

    def send_to_telegram(self, listings, product_info):
        """
        Ilanlari Telegram'a gonder (kopyala-yapistir icin)
        """
        product_id = product_info.get('id', 'Unknown')

        # Ana resmi gonder
        images = product_info.get('images', [])
        if images and Path(images[0]).exists():
            send_telegram_photo(images[0], f"Urun: {product_id}")

        # Her platform icin ayri mesaj
        for platform, listing in listings.items():
            msg = f"""
*{platform.upper()} ILAN*

*Baslik:*
`{listing['title']}`

*Fiyat:* {listing['price']} EUR

*Aciklama:*
```
{listing['description']}
```

*Resimler:* {len(listing['images'])} adet

---
Kopyala ve {platform}'e yapistir!
"""

            # Butonlar
            buttons = [
                [
                    {"text": "Kopyalandi", "callback_data": f"copied:{product_id}:{platform}"},
                    {"text": "Yayinlandi", "callback_data": f"published:{product_id}:{platform}"}
                ]
            ]

            send_telegram(msg, buttons=buttons)
            time.sleep(1)  # Rate limiting

        # Son mesaj
        send_telegram(f"Tum {len(listings)} platform icin ilan hazir!")

# ============================================
# BATCH PROCESSOR
# ============================================
def process_pending_products():
    """
    Stock Manager'dan bekleyen urunleri isle
    """
    stock_file = Path(__file__).parent.parent / "T4_STOCK_MANAGER" / "output" / "stock_products.json"

    if not stock_file.exists():
        print("[-] Stock dosyasi bulunamadi")
        return

    with open(stock_file, 'r', encoding='utf-8') as f:
        products = json.load(f)

    # Processed durumundakileri isle
    pending = [p for p in products if p.get('status') == 'processed']

    if not pending:
        print("[*] Islenecek urun yok")
        return

    print(f"\n[*] {len(pending)} urun icin ilan olusturulacak")

    generator = ListingGenerator()

    for product in pending:
        listings = generator.create_listing(product)
        generator.send_to_telegram(listings, product)

        # Durumu guncelle
        product['status'] = 'listed'
        product['listings'] = {p: l.get('status') for p, l in listings.items()}

    # Kaydet
    with open(stock_file, 'w', encoding='utf-8') as f:
        json.dump(products, f, ensure_ascii=False, indent=2)

    print(f"\n[+] Tum ilanlar olusturuldu")

# ============================================
# MAIN
# ============================================
def main():
    import argparse

    parser = argparse.ArgumentParser(description='TATANGA - T6 Listing Engine')
    parser.add_argument('--batch', action='store_true', help='Bekleyen urunleri toplu isle')
    parser.add_argument('--product', type=str, help='Tek urun ID')
    parser.add_argument('--platforms', nargs='+', default=['vinted', 'kleinanzeigen'],
                       help='Hedef platformlar')
    parser.add_argument('--telegram', action='store_true', help='Telegram\'a gonder')

    args = parser.parse_args()

    print("=" * 50)
    print("TATANGA - T6 Listing Engine")
    print("=" * 50)

    if args.batch:
        process_pending_products()

    elif args.product:
        # Tek urun isle
        stock_file = Path(__file__).parent.parent / "T4_STOCK_MANAGER" / "output" / "stock_products.json"

        if stock_file.exists():
            with open(stock_file, 'r', encoding='utf-8') as f:
                products = json.load(f)

            product = next((p for p in products if p.get('id') == args.product), None)

            if product:
                generator = ListingGenerator()
                listings = generator.create_listing(product, args.platforms)

                if args.telegram:
                    generator.send_to_telegram(listings, product)
            else:
                print(f"[-] Urun bulunamadi: {args.product}")

    else:
        print("\nKullanim:")
        print("  Toplu isle:   python listing_generator.py --batch")
        print("  Tek urun:     python listing_generator.py --product STOCK-001 --telegram")
        print("  Platformlar:  python listing_generator.py --product STOCK-001 --platforms vinted ebay")

if __name__ == "__main__":
    main()
