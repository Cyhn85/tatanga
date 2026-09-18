#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
eBay Real Upload Test - Gercek resimlerle upload test
"""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from telegram_bot.uploaders.ebay_uploader import EbayUploader, log

# Dizinler
BASE_DIR = Path(__file__).parent.parent.parent
TEMP_DIR = BASE_DIR / "T6_LISTING_ENGINE" / "temp"

def test_real_upload():
    """Gercek urun ve resimlerle upload test"""
    print("=" * 60)
    print("EBAY GERCEK RESIM UPLOAD TEST")
    print("=" * 60)

    uploader = EbayUploader(sandbox=False)

    if not uploader.user_token:
        print("Token yok! Once authorize edin.")
        return

    # Nike Tennisschuhe - & karakteri olmayan test urunu
    test_product = {
        'title': 'Nike Court Advantage Tennisschuhe Gr. 46',
        'seo': {
            'ebay': {
                'title': 'Nike Court Advantage Tennisschuhe Weiss Gr. 46',
                # SEO description kullanilacak (create_seo_description)
            }
        },
        'platform_prices': {
            'ebay': 39.99
        },
        'ebay_category_id': '15709',  # Herrenschuhe
        'brand': 'Nike',
        'condition': 'Sehr gut',
        'size': '46',
        'color': 'Weiss',
        'department': 'Herren',
        'description': 'Nike Court Advantage Tennisschuhe in sehr gutem Zustand. Ideal fuer Tennis und andere Sportarten. Aus tierfreiem Nichtraucherhaushalt.',
        'local_images': [
            # Kleinanzeigen'den gercek buyuk resim URL'si
            'https://img.kleinanzeigen.de/api/v1/prod-ads/images/79/7958e6ed-d63b-4635-b46e-04615abce141?rule=$_59.JPG'
        ]
    }

    # Harici URL kullaniyoruz
    print(f"\nResim URL: {test_product['local_images'][0]}")

    print("\n" + "=" * 60)
    print("URUN BILGILERI")
    print("=" * 60)
    print(f"Baslik: {test_product['seo']['ebay']['title']}")
    print(f"Marka: {test_product['brand']}")
    print(f"Fiyat: {test_product['platform_prices']['ebay']} EUR")
    print(f"Beden: {test_product['size']}")
    print(f"Renk: {test_product['color']}")
    print(f"Resim sayisi: {len(test_product['local_images'])}")
    print("=" * 60)

    # Upload
    print("\nYukleme basliyor...")
    item_id = uploader.upload_product(test_product)

    if item_id:
        print("\n" + "=" * 60)
        print("BASARILI!")
        print("=" * 60)
        print(f"ItemID: {item_id}")
        print(f"URL: https://www.ebay.de/itm/{item_id}")
        print("=" * 60)
    else:
        print("\n" + "=" * 60)
        print("YUKLEME BASARISIZ!")
        print("=" * 60)

if __name__ == "__main__":
    test_real_upload()
