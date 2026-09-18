#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TATANGA - Transfer Test Runner
Kleinanzeigen'dan Vinted'e gercek urun transferi

KULLANIM:
1. Bu dosyayi calistir
2. Kleinanzeigen magazanizdan bir urun URL'si gir
3. Telegram'dan onayla
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from product_transfer_v2 import ProductTransferV2

def main():
    print("=" * 60)
    print("TATANGA - GERCEK TRANSFER TESTI")
    print("=" * 60)

    # Ornek URL'ler - Kleinanzeigen'dan
    print("\nKleinanzeigen magazanizdan bir urun URL'si girin.")
    print("Ornek: https://www.kleinanzeigen.de/s-anzeige/...")
    print("\nNOT: Kendi magazanizin URL'sini kullanin!")

    source_url = input("\nURL: ").strip()

    if not source_url:
        print("\n[-] URL girmediniz!")
        return

    if "kleinanzeigen.de" not in source_url:
        print("\n[-] Gecersiz URL! Kleinanzeigen URL'si olmali.")
        return

    # Hedef platform
    print("\nHedef platformlar:")
    print("  1. vinted")
    print("  2. ebay")
    print("  3. willhaben")

    target = input("\nHedef platform (varsayilan: vinted): ").strip() or "vinted"

    # Hedef hesap
    print("\nMevcut hesaplar:")
    print("  - main")
    print("  - secondary")

    account = input("\nHesap (varsayilan: main): ").strip() or "main"

    # Transfer baslat
    print("\n" + "=" * 60)

    transfer = ProductTransferV2()
    product_id = transfer.transfer_with_approval(source_url, target, account)

    if product_id:
        print("\n" + "=" * 60)
        print("ISLEM TAMAMLANDI")
        print("=" * 60)
        print(f"\nUrun ID: {product_id}")
        print("\nSimdi Telegram'a gidin ve onayla/reddet butonuna basin.")
        print("\nOnayladiginizda urun otomatik olarak yuklenir.")
    else:
        print("\n[-] Transfer basarisiz oldu!")

if __name__ == "__main__":
    main()
