#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TATANGA - Direct Transfer Test
Dogrudan bir Kleinanzeigen URL'si ile test
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from product_transfer_v2 import ProductTransferV2

# Kleinanzeigen'dan ornek bir urun URL'si
# Bu URL'yi kendi magazanizdaki bir urunle degistirebilirsiniz
TEST_URL = "https://www.kleinanzeigen.de/s-anzeige/northface-jacke-gr-l-herren/2993412341-87-3331"

def main():
    print("=" * 60)
    print("TATANGA - DIRECT TRANSFER TEST")
    print("=" * 60)

    if "placeholder" in TEST_URL:
        print("\n[!] UYARI: Test URL'sini degistirmediniz!")
        print("\ndirect_transfer_test.py dosyasini acin ve TEST_URL'yi degistirin.")
        print("\nOrnek URL:")
        print("https://www.kleinanzeigen.de/s-anzeige/nike-air-max-90/12345678-22-1234")
        return

    print(f"\nKaynak URL: {TEST_URL}")
    print(f"Hedef: Vinted (main hesap)")

    transfer = ProductTransferV2()
    product_id = transfer.transfer_with_approval(TEST_URL, 'vinted', 'main')

    if product_id:
        print("\n" + "=" * 60)
        print("[+] BASARILI!")
        print("=" * 60)
        print(f"\nUrun ID: {product_id}")
        print("\nTelegram'da onay istegi gonderildi.")
        print("Bot'tan gelen mesaji kontrol edin.")
    else:
        print("\n[-] Transfer basarisiz!")

if __name__ == "__main__":
    main()
