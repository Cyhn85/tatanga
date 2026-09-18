#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Direkt Transfer - Kleinanzeigen -> Vinted
Telegram bildirimleri KAPALI
"""

import sys
import time
import json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.config.credentials import KLEINANZEIGEN, VINTED
from store_transfer_handler import StoreTransferHandler

def direct_transfer():
    """Kleinanzeigen'den Vinted'e direkt transfer"""
    print("=" * 60, flush=True)
    print("DIREKT TRANSFER: Kleinanzeigen -> Vinted", flush=True)
    print("Telegram bildirimleri KAPALI", flush=True)
    print("=" * 60, flush=True)

    # Handler olustur
    handler = StoreTransferHandler()

    # Telegram bildirimlerini devre disi birak
    handler.send_telegram = False

    # Kaynak ve hedef hesaplar
    source_email = KLEINANZEIGEN['accounts'][0]['email']
    target_email = VINTED['accounts'][0]['email']

    print(f"\nKaynak: Kleinanzeigen ({source_email})")
    print(f"Hedef: Vinted ({target_email})")

    # ADIM 1: Kleinanzeigen'den urunleri cek
    print("\n" + "=" * 60)
    print("ADIM 1: Kleinanzeigen'den urunler cekiliyor...")
    print("=" * 60)

    products = handler.get_kleinanzeigen_products(source_email)

    if not products:
        print("Hic urun bulunamadi!")
        return False

    print(f"\n{len(products)} urun bulundu:", flush=True)
    for i, p in enumerate(products[:10]):
        orig = p.get('original', {})
        title = orig.get('title', 'Baslik yok')[:40]
        price = orig.get('price', 0)
        category = orig.get('category', 'N/A')
        images = p.get('images', [])
        print(f"  {i+1}. {title}...", flush=True)
        print(f"      Fiyat: {price} EUR | Kategori: {category} | Resim: {len(images)}", flush=True)

    if len(products) > 10:
        print(f"  ... ve {len(products) - 10} urun daha")

    # ADIM 2: Vinted'e login
    print("\n" + "=" * 60)
    print("ADIM 2: Vinted'e login yapiliyor...")
    print("=" * 60)

    vinted_account = VINTED['accounts'][0]
    if not handler.login_to_vinted(vinted_account):
        print("Vinted login basarisiz!")
        return False

    print("Vinted login basarili!")
    handler.vinted_logged_in = True

    # ADIM 3: Urunleri Vinted'e yukle
    print("\n" + "=" * 60)
    print("ADIM 3: Urunler Vinted'e yukleniyor...")
    print("=" * 60)

    success_count = 0
    fail_count = 0

    for i, product in enumerate(products):
        title = product.get('original', {}).get('title', 'Baslik yok')[:30]
        price = product.get('original', {}).get('price', 0)

        print(f"\n[{i+1}/{len(products)}] {title}... ({price} EUR)")

        try:
            if handler.upload_to_vinted(product, vinted_account):
                success_count += 1
                print(f"  BASARILI")
            else:
                fail_count += 1
                print(f"  BASARISIZ")
        except Exception as e:
            fail_count += 1
            print(f"  HATA: {e}")

        # Urunler arasi bekleme
        if i < len(products) - 1:
            time.sleep(3)

    # Sonuc ozeti
    print("\n" + "=" * 60)
    print("TRANSFER TAMAMLANDI")
    print("=" * 60)
    print(f"Toplam: {len(products)}")
    print(f"Basarili: {success_count}")
    print(f"Basarisiz: {fail_count}")

    # Driver kapat
    if handler.driver:
        try:
            handler.driver.quit()
        except:
            pass

    return success_count > 0

if __name__ == "__main__":
    success = direct_transfer()
    sys.exit(0 if success else 1)
