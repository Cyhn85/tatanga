#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Kleinanzeigen urunlerini eBay'e yukle
"""

import sys
import json
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from telegram_bot.uploaders.ebay_uploader import EbayUploader, log

# Dizinler
BASE_DIR = Path(__file__).parent.parent.parent
TEMP_DIR = BASE_DIR / "T6_LISTING_ENGINE" / "temp"

# Kategori mapping - Kleinanzeigen -> eBay (ALT kategoriler!)
CATEGORY_MAP = {
    'Herrenschuhe': '93427',       # Herrenschuhe > Turnschuhe & Sneaker
    'Herrenbekleidung': '57990',   # Herrenbekleidung > Jacken & Mäntel
    'Damenbekleidung': '63862',    # Damenbekleidung > Jacken & Mäntel
    'Taschen & Accessoires': '179247',  # Brillen > Brillenfassungen
    'Handy & Telefon': '9355',     # Handys & Smartphones (skip)
}

# Urun tipine gore kategori (daha spesifik)
PRODUCT_TYPE_CATEGORY = {
    'Schuhe': {
        'Herren': '93427',    # Herrenschuhe > Turnschuhe & Sneaker
        'Damen': '95672',     # Damenschuhe > Turnschuhe & Sneaker
    },
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
    'Brille': {
        'unisex': '179247',   # Brillen > Brillenfassungen
    },
}

# Condition mapping
CONDITION_MAP = {
    'Neu': 'Neu',
    'iyi': 'Sehr gut',
    'Sehr gut': 'Sehr gut',
    'Gut': 'Gut',
}

def upload_all_products():
    """Tum urunleri eBay'e yukle"""
    print("=" * 60)
    print("KLEINANZEIGEN -> EBAY TOPLU YUKLEME")
    print("=" * 60)

    # Uploader baslat
    uploader = EbayUploader(sandbox=False)

    if not uploader.user_token:
        print("Token yok! Once authorize edin.")
        return

    # Urunleri yukle
    products_file = TEMP_DIR / "optimized_products.json"
    if not products_file.exists():
        print(f"Urun dosyasi bulunamadi: {products_file}")
        return

    with open(products_file, 'r', encoding='utf-8') as f:
        products = json.load(f)

    print(f"\nToplam {len(products)} urun bulundu")
    print("=" * 60)

    uploaded = []
    failed = []

    for i, product in enumerate(products):
        print(f"\n[{i+1}/{len(products)}] {product.get('title', 'N/A')[:50]}...")

        # eBay icin urun hazirla
        ebay_product = prepare_ebay_product(product)

        if not ebay_product:
            print("  -> ATLANDI (kategori desteklenmiyor)")
            failed.append({'title': product.get('title'), 'reason': 'Kategori desteklenmiyor'})
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

        # Rate limit - her urun arasinda bekle
        if i < len(products) - 1:
            time.sleep(2)

    # Sonuc ozeti
    print("\n" + "=" * 60)
    print("YUKLEME TAMAMLANDI")
    print("=" * 60)
    print(f"Basarili: {len(uploaded)}")
    print(f"Basarisiz: {len(failed)}")
    print("=" * 60)

    if uploaded:
        print("\nYuklenen urunler:")
        for item in uploaded:
            print(f"  - {item['title'][:40]}...")
            print(f"    {item['url']}")

    if failed:
        print("\nBasarisiz urunler:")
        for item in failed:
            print(f"  - {item['title'][:40]}... ({item['reason']})")

    # Sonuclari kaydet
    results = {
        'uploaded': uploaded,
        'failed': failed,
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
    }

    results_file = TEMP_DIR / "ebay_upload_results.json"
    with open(results_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\nSonuclar kaydedildi: {results_file}")

def prepare_ebay_product(product):
    """Kleinanzeigen urununu eBay formatina cevir"""
    import re

    category = product.get('category', '')
    analysis = product.get('analysis', {})
    seo = product.get('seo', {}).get('ebay', {})

    # Huawei/Telefon urunlerini atla
    if category == 'Handy & Telefon':
        return None

    # Product type'a gore kategori sec
    product_type = analysis.get('product_type', '')
    target = analysis.get('target_audience', 'Herren')

    # Target'i normalize et
    if target in ['unisex', 'Unisex']:
        target = 'Herren'
    elif 'Damen' in category:
        target = 'Damen'

    # Kategori belirle
    ebay_category = None
    if product_type in PRODUCT_TYPE_CATEGORY:
        type_cats = PRODUCT_TYPE_CATEGORY[product_type]
        if target in type_cats:
            ebay_category = type_cats[target]
        elif 'unisex' in type_cats:
            ebay_category = type_cats['unisex']
        else:
            ebay_category = list(type_cats.values())[0]
    else:
        ebay_category = CATEGORY_MAP.get(category)

    if not ebay_category:
        return None

    # Fiyat belirle (min 5 EUR)
    price = product.get('price', 0)
    if price == 0:
        # Kategoriye gore varsayilan fiyat
        default_prices = {
            'Herrenschuhe': 29.99,
            'Herrenbekleidung': 24.99,
            'Damenbekleidung': 24.99,
            'Taschen & Accessoires': 19.99,
            'Handy & Telefon': 49.99,
        }
        price = default_prices.get(category, 19.99)

    # Condition
    raw_condition = analysis.get('condition', 'Gebraucht')
    condition = CONDITION_MAP.get(raw_condition, 'Sehr gut')

    # Beden/Size - urun tipine gore
    size = ''
    title = product.get('title', '')

    # Title'dan beden cikar
    import re
    size_match = re.search(r'Gr\.?\s*(\d+|XS|S|M|L|XL|XXL)', title, re.I)
    if size_match:
        size = size_match.group(1).upper()
    else:
        size = 'L'  # Varsayilan

    # Renk
    color = analysis.get('color', '')
    if not color:
        # Title'dan renk cikar
        colors = ['Schwarz', 'Weiss', 'Blau', 'Rot', 'Gruen', 'Gelb', 'Grau', 'Braun', 'Beige', 'Rosa', 'Lila', 'Orange']
        for c in colors:
            if c.lower() in title.lower():
                color = c
                break
        if not color:
            color = 'Mehrfarbig'

    # Department
    if 'Damen' in category or 'Damen' in title:
        department = 'Damen'
    else:
        department = 'Herren'

    # Resim URL'leri - Kleinanzeigen'den buyuk resim al
    images = product.get('images', [])
    image_urls = []
    for img_url in images:
        # Buyuk resim icin rule degistir
        if 'kleinanzeigen.de' in img_url:
            big_url = img_url.replace('$_57.JPG', '$_59.JPG').replace('$_2.JPG', '$_59.JPG')
            image_urls.append(big_url)
        else:
            image_urls.append(img_url)

    # eBay product objesi
    ebay_product = {
        'title': product.get('title', ''),
        'seo': {
            'ebay': {
                'title': seo.get('title', product.get('title', '')[:80]),
                # Description create_seo_description ile olusturulacak
            }
        },
        'platform_prices': {
            'ebay': price
        },
        'ebay_category_id': ebay_category,
        'brand': analysis.get('brand', 'Unbranded'),
        'condition': condition,
        'size': size,
        'color': color,
        'department': department,
        'description': seo.get('description', product.get('description', '')),
        'local_images': image_urls
    }

    return ebay_product

if __name__ == "__main__":
    upload_all_products()
