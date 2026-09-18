#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Basarisiz urunleri tekrar eBay'e yukle (Huawei haric)
"""

import sys
import json
import time
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from telegram_bot.uploaders.ebay_uploader import EbayUploader, log

# Dizinler
BASE_DIR = Path(__file__).parent.parent.parent
TEMP_DIR = BASE_DIR / "T6_LISTING_ENGINE" / "temp"

# Basarisiz urunlerin ad_id'leri (sadece Brille kaldi)
FAILED_PRODUCTS = [
    '3243046030',  # Calvin Klein Brillenfassung
]

# Kategori mapping - Daha spesifik alt kategoriler
CATEGORY_MAP = {
    'Jacke': {
        'Herren': '57990',    # Herrenbekleidung > Jacken & Mäntel
        'Damen': '63862',     # Damenbekleidung > Jacken & Mäntel
    },
    'Jeans': {
        'Herren': '11483',    # Herrenbekleidung > Jeans
        'Damen': '11554',     # Damenbekleidung > Jeans
    },
    'Shirt': {
        'Herren': '15687',    # Herrenbekleidung > T-Shirts
        'Damen': '53159',     # Damenbekleidung > Tops
    },
    'Brille': '179247',       # Brillen > Brillenfassungen
}

def upload_failed():
    """Basarisiz urunleri tekrar yukle"""
    print("=" * 60)
    print("BASARISIZ URUNLERI TEKRAR YUKLE")
    print("=" * 60)

    uploader = EbayUploader(sandbox=False)

    if not uploader.user_token:
        print("Token yok! Once authorize edin.")
        return

    # Urunleri yukle
    products_file = TEMP_DIR / "optimized_products.json"
    with open(products_file, 'r', encoding='utf-8') as f:
        all_products = json.load(f)

    # Sadece basarisiz urunleri filtrele
    products = [p for p in all_products if p.get('ad_id') in FAILED_PRODUCTS]

    print(f"\nYuklenecek urun sayisi: {len(products)}")
    print("=" * 60)

    uploaded = []
    failed = []

    for i, product in enumerate(products):
        print(f"\n[{i+1}/{len(products)}] {product.get('title', 'N/A')[:50]}...")

        # eBay icin urun hazirla
        ebay_product = prepare_product(product)

        if not ebay_product:
            print("  -> ATLANDI")
            failed.append({'title': product.get('title'), 'reason': 'Hazirlanamadi'})
            continue

        # Yukle
        try:
            item_id = uploader.upload_product(ebay_product)

            if item_id:
                print(f"  -> BASARILI! ItemID: {item_id}")
                uploaded.append({
                    'title': product.get('title'),
                    'item_id': item_id,
                    'url': f"https://www.ebay.de/itm/{item_id}"
                })
            else:
                print("  -> BASARISIZ!")
                failed.append({'title': product.get('title'), 'reason': 'API hatasi'})
        except Exception as e:
            print(f"  -> HATA: {e}")
            failed.append({'title': product.get('title'), 'reason': str(e)})

        # Rate limit
        if i < len(products) - 1:
            time.sleep(2)

    # Sonuc
    print("\n" + "=" * 60)
    print("YUKLEME TAMAMLANDI")
    print("=" * 60)
    print(f"Basarili: {len(uploaded)}")
    print(f"Basarisiz: {len(failed)}")

    if uploaded:
        print("\nYuklenen urunler:")
        for item in uploaded:
            print(f"  - {item['url']}")

    if failed:
        print("\nBasarisiz:")
        for item in failed:
            print(f"  - {item['title'][:40]}... ({item['reason']})")

def prepare_product(product):
    """Urunu eBay formatina cevir"""
    analysis = product.get('analysis', {})
    seo = product.get('seo', {}).get('ebay', {})
    category = product.get('category', '')
    product_type = analysis.get('product_type', '')
    title = product.get('title', '')

    # Target belirle
    if 'Damen' in category or 'Damen' in title:
        target = 'Damen'
    else:
        target = 'Herren'

    # Kategori belirle
    if product_type == 'Brille':
        ebay_category = '180957'  # Brillen > Brillenfassungen (alt kategori)
    elif product_type in CATEGORY_MAP:
        cats = CATEGORY_MAP[product_type]
        ebay_category = cats.get(target, list(cats.values())[0])
    else:
        # Default kategori
        if target == 'Damen':
            ebay_category = '63862'  # Damenbekleidung > Jacken
        else:
            ebay_category = '57990'  # Herrenbekleidung > Jacken

    # Fiyat
    default_prices = {
        'Jacke': 34.99,
        'Jeans': 29.99,
        'Shirt': 24.99,
        'Brille': 39.99,
    }
    price = default_prices.get(product_type, 29.99)

    # Size
    size_match = re.search(r'Gr\.?\s*(\d+|XS|S|M|L|XL|XXL)', title, re.I)
    size = size_match.group(1).upper() if size_match else 'M'

    # Renk
    colors = ['Schwarz', 'Weiss', 'Blau', 'Rot', 'Gruen', 'Gelb', 'Grau', 'Braun', 'Beige', 'Rosa', 'Lila', 'Orange', 'Creme', 'Marineblau']
    color = 'Mehrfarbig'
    for c in colors:
        if c.lower() in title.lower():
            color = c
            break

    # Resimler
    images = product.get('images', [])
    image_urls = []
    for img_url in images:
        if 'kleinanzeigen.de' in img_url:
            big_url = img_url.replace('$_57.JPG', '$_59.JPG').replace('$_2.JPG', '$_59.JPG')
            image_urls.append(big_url)
        else:
            image_urls.append(img_url)

    return {
        'title': title,
        'seo': {
            'ebay': {
                'title': seo.get('title', title[:80]),
            }
        },
        'platform_prices': {'ebay': price},
        'ebay_category_id': ebay_category,
        'brand': analysis.get('brand', 'Unbranded'),
        'condition': 'Sehr gut',
        'size': size,
        'color': color,
        'department': target,
        'description': seo.get('description', ''),
        'local_images': image_urls
    }

if __name__ == "__main__":
    upload_failed()
