#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
eBay Token Manuel Kaydetme
eBay Developer Portal'dan aldığınız token'ı buraya yapıştırın
"""

import json
import time
from pathlib import Path

# Dizinler
BASE_DIR = Path(__file__).parent.parent.parent
TEMP_DIR = BASE_DIR / "T6_LISTING_ENGINE" / "temp"
TOKEN_FILE = TEMP_DIR / "ebay_token.json"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

def save_token():
    print("=" * 60)
    print("EBAY TOKEN KAYDETME")
    print("=" * 60)
    print()
    print("eBay Developer Portal'dan token almak için:")
    print("1. https://developer.ebay.com/my/keys adresine gidin")
    print("2. Production keyset'inizde 'User Tokens' > 'Get a User Token' tıklayın")
    print("3. eBay hesabınıza giriş yapın")
    print("4. Verilen Access Token'ı kopyalayın")
    print()
    print("NOT: Token çok uzun olacak (1000+ karakter)")
    print()

    access_token = input("Access Token: ").strip()

    if not access_token:
        print("Token girilmedi!")
        return False

    # Refresh token opsiyonel
    print()
    print("Refresh Token (opsiyonel, yoksa boş bırakın):")
    refresh_token = input("Refresh Token: ").strip()

    # Token verisi oluştur
    token_data = {
        "access_token": access_token,
        "token_type": "User Access Token",
        "expires_in": 7200,
        "expires_at": time.time() + 7200  # 2 saat
    }

    if refresh_token:
        token_data["refresh_token"] = refresh_token
        token_data["refresh_token_expires_in"] = 47304000  # 18 ay

    # Kaydet
    with open(TOKEN_FILE, 'w') as f:
        json.dump(token_data, f, indent=2)

    print()
    print(f"Token kaydedildi: {TOKEN_FILE}")
    print()
    print("Artık ebay_uploader.py ile ürün yükleyebilirsiniz:")
    print("  python ebay_uploader.py")
    print("  Seçim: 3 (Test Ürün Yükle)")

    return True

if __name__ == "__main__":
    save_token()
