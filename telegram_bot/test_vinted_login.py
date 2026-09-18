#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vinted Login Test - Yeni insansı login metodunu test et
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.config.credentials import VINTED

# StoreTransferHandler'ı import et
from store_transfer_handler import StoreTransferHandler

def test_vinted_login():
    """Vinted login test"""
    print("=" * 60)
    print("VINTED LOGIN TEST")
    print("=" * 60)

    # Handler oluştur
    handler = StoreTransferHandler()

    # Vinted hesabı
    account = VINTED['accounts'][0]
    print(f"\nHesap: {account['email']}")
    print(f"Username: {account.get('username', 'N/A')}")

    # Login dene
    print("\nLogin deneniyor...")
    result = handler.login_to_vinted(account)

    if result:
        print("\n✅ VINTED LOGIN BASARILI!")

        # Screenshot al
        if handler.driver:
            screenshot_path = Path(__file__).parent.parent / "T6_LISTING_ENGINE" / "temp" / "vinted_login_success.png"
            handler.driver.save_screenshot(str(screenshot_path))
            print(f"Screenshot: {screenshot_path}")
    else:
        print("\n❌ VINTED LOGIN BASARISIZ!")
        print("Temp klasöründeki screenshot'ları kontrol edin.")

    # Driver'ı kapat
    if handler.driver:
        try:
            handler.driver.quit()
        except:
            pass

    return result

if __name__ == "__main__":
    success = test_vinted_login()
    sys.exit(0 if success else 1)
