#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TATANGA - eBay API Scanner
eBay Browse API ile urun tarama ve pagination
"""

import os
import sys
import json
import time
import base64
import requests
from pathlib import Path
from datetime import datetime, timedelta

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.config.credentials import TELEGRAM, EBAY

# ============================================
# CONFIGURATION
# ============================================
OUTPUT_DIR = Path(__file__).parent / "output"
LOGS_DIR = Path(__file__).parent / "logs"

OUTPUT_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

# eBay API endpoints
EBAY_AUTH_URL = "https://api.ebay.com/identity/v1/oauth2/token"
EBAY_BROWSE_API = "https://api.ebay.com/buy/browse/v1"

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
# EBAY API CLIENT
# ============================================
class EbayApiClient:
    """eBay API istemcisi"""

    def __init__(self):
        self.app_id = EBAY.get('app_id', '')
        self.cert_id = EBAY.get('cert_id', '')
        self.dev_id = EBAY.get('dev_id', '')
        self.access_token = None
        self.token_expiry = None

    def get_access_token(self):
        """
        OAuth access token al
        """
        if self.access_token and self.token_expiry and datetime.now() < self.token_expiry:
            return self.access_token

        # Basic auth header
        credentials = f"{self.app_id}:{self.cert_id}"
        encoded = base64.b64encode(credentials.encode()).decode()

        headers = {
            "Authorization": f"Basic {encoded}",
            "Content-Type": "application/x-www-form-urlencoded"
        }

        data = {
            "grant_type": "client_credentials",
            "scope": "https://api.ebay.com/oauth/api_scope"
        }

        try:
            response = requests.post(EBAY_AUTH_URL, headers=headers, data=data)

            if response.status_code == 200:
                result = response.json()
                self.access_token = result['access_token']
                expires_in = result.get('expires_in', 7200)
                self.token_expiry = datetime.now() + timedelta(seconds=expires_in - 60)

                print("[+] eBay access token alindi")
                return self.access_token
            else:
                print(f"[-] Token hatasi: {response.status_code}")
                print(response.text)
                return None

        except Exception as e:
            print(f"[-] Token alma hatasi: {e}")
            return None

    def search_items(self, query, category_id=None, limit=50, offset=0, sort="newlyListed", filters=None):
        """
        Browse API ile urun ara

        Args:
            query: Arama sorgusu
            category_id: Kategori ID (opsiyonel)
            limit: Sayfa basina urun (max 200)
            offset: Sayfa offset
            sort: Siralama (newlyListed, price, -price)
            filters: Ek filtreler

        Returns:
            dict: API yaniti
        """
        token = self.get_access_token()
        if not token:
            return None

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-EBAY-C-MARKETPLACE-ID": "EBAY_DE"  # Almanya
        }

        # Filter string olustur
        filter_parts = []

        if filters:
            if filters.get('min_price'):
                filter_parts.append(f"price:[{filters['min_price']}..{filters.get('max_price', '*')}]")
            if filters.get('condition'):
                filter_parts.append(f"conditions:{{{filters['condition']}}}")
            if filters.get('buying_options'):
                filter_parts.append(f"buyingOptions:{{{filters['buying_options']}}}")

        params = {
            "q": query,
            "limit": min(limit, 200),
            "offset": offset,
            "sort": sort
        }

        if category_id:
            params["category_ids"] = category_id

        if filter_parts:
            params["filter"] = ",".join(filter_parts)

        try:
            response = requests.get(
                f"{EBAY_BROWSE_API}/item_summary/search",
                headers=headers,
                params=params
            )

            if response.status_code == 200:
                return response.json()
            else:
                print(f"[-] API hatasi: {response.status_code}")
                print(response.text)
                return None

        except Exception as e:
            print(f"[-] Search hatasi: {e}")
            return None

    def get_item_details(self, item_id):
        """
        Urun detaylari al

        Args:
            item_id: eBay item ID

        Returns:
            dict: Urun detaylari
        """
        token = self.get_access_token()
        if not token:
            return None

        headers = {
            "Authorization": f"Bearer {token}",
            "X-EBAY-C-MARKETPLACE-ID": "EBAY_DE"
        }

        try:
            response = requests.get(
                f"{EBAY_BROWSE_API}/item/{item_id}",
                headers=headers
            )

            if response.status_code == 200:
                return response.json()
            else:
                print(f"[-] Item hatasi: {response.status_code}")
                return None

        except Exception as e:
            print(f"[-] Item detay hatasi: {e}")
            return None

# ============================================
# EBAY SCANNER
# ============================================
class EbayScanner:
    """eBay tarayici"""

    def __init__(self):
        self.client = EbayApiClient()
        self.all_items = []

    def search_with_pagination(self, query, max_results=500, **kwargs):
        """
        Pagination ile toplu arama

        Args:
            query: Arama sorgusu
            max_results: Maksimum sonuc sayisi
            **kwargs: Ek filtreler

        Returns:
            list: Tum urunler
        """
        print(f"\n[*] eBay arama: {query}")

        all_items = []
        offset = 0
        limit = 200  # Sayfa basina maksimum

        while offset < max_results:
            print(f"    Sayfa {offset // limit + 1} yukleniyor...")

            result = self.client.search_items(
                query,
                limit=min(limit, max_results - offset),
                offset=offset,
                **kwargs
            )

            if not result:
                break

            items = result.get('itemSummaries', [])
            if not items:
                break

            all_items.extend(items)

            # Toplam sonuc kontrolu
            total = result.get('total', 0)
            if offset + limit >= total:
                break

            offset += limit
            time.sleep(0.5)  # Rate limiting

        print(f"\n[+] Toplam {len(all_items)} urun bulundu")
        self.all_items = all_items
        return all_items

    def parse_item(self, item):
        """
        Item'i standart formata cevir

        Args:
            item: eBay item summary

        Returns:
            dict: Standart format
        """
        price_info = item.get('price', {})

        return {
            "id": item.get('itemId', ''),
            "title": item.get('title', ''),
            "price": float(price_info.get('value', 0)),
            "currency": price_info.get('currency', 'EUR'),
            "condition": item.get('condition', ''),
            "url": item.get('itemWebUrl', ''),
            "image": item.get('thumbnailImages', [{}])[0].get('imageUrl', '') if item.get('thumbnailImages') else item.get('image', {}).get('imageUrl', ''),
            "seller": item.get('seller', {}).get('username', ''),
            "location": item.get('itemLocation', {}).get('city', ''),
            "shipping": item.get('shippingOptions', [{}])[0].get('shippingCost', {}).get('value', '0') if item.get('shippingOptions') else '0',
            "source": "ebay",
            "scraped_at": datetime.now().isoformat()
        }

    def find_deals(self, query, max_price=None, condition="USED"):
        """
        Uygun fiyatli urunleri bul

        Args:
            query: Arama sorgusu
            max_price: Maksimum fiyat
            condition: Durum (USED, NEW, etc.)

        Returns:
            list: Firsatlar
        """
        filters = {"condition": condition}
        if max_price:
            filters["max_price"] = max_price

        items = self.search_with_pagination(query, filters=filters)

        # Fiyata gore sirala
        parsed = [self.parse_item(item) for item in items]
        parsed.sort(key=lambda x: x['price'])

        return parsed

    def save_results(self, items, filename=None):
        """
        Sonuclari kaydet

        Args:
            items: Urun listesi
            filename: Dosya adi

        Returns:
            Path: Dosya yolu
        """
        if not filename:
            filename = f"ebay_search_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        output_path = OUTPUT_DIR / filename

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(items, f, ensure_ascii=False, indent=2)

        print(f"[+] Kaydedildi: {output_path}")
        return output_path

    def get_seller_items(self, seller_name, max_results=200):
        """
        Belirli saticinan urunlerini al

        Args:
            seller_name: Satici adi
            max_results: Maksimum sonuc

        Returns:
            list: Satici urunleri
        """
        return self.search_with_pagination(
            f"",  # Bos query
            max_results=max_results,
            filters={"sellers": seller_name}
        )

# ============================================
# CATEGORY SCANNER
# ============================================
class EbayCategoryScanner:
    """Kategori bazli tarayici"""

    # Populer kategoriler (DE)
    CATEGORIES = {
        "kleidung_herren": "260010",
        "kleidung_damen": "260012",
        "schuhe_herren": "93427",
        "schuhe_damen": "3034",
        "uhren": "31387",
        "taschen": "169291",
        "accessoires": "4250"
    }

    def __init__(self):
        self.scanner = EbayScanner()

    def scan_category(self, category_name, brands=None, max_results=200):
        """
        Kategori tara

        Args:
            category_name: Kategori adi
            brands: Marka listesi
            max_results: Maksimum sonuc

        Returns:
            dict: Kategori sonuclari
        """
        category_id = self.CATEGORIES.get(category_name)
        if not category_id:
            print(f"[-] Bilinmeyen kategori: {category_name}")
            return None

        results = {
            "category": category_name,
            "brands": {},
            "all_items": []
        }

        if brands:
            for brand in brands:
                print(f"\n[*] {category_name} - {brand}")
                items = self.scanner.search_with_pagination(
                    brand,
                    category_id=category_id,
                    max_results=max_results // len(brands)
                )
                parsed = [self.scanner.parse_item(item) for item in items]
                results["brands"][brand] = parsed
                results["all_items"].extend(parsed)
        else:
            items = self.scanner.search_with_pagination(
                "",
                category_id=category_id,
                max_results=max_results
            )
            results["all_items"] = [self.scanner.parse_item(item) for item in items]

        return results

# ============================================
# MAIN
# ============================================
def main():
    import argparse

    parser = argparse.ArgumentParser(description='TATANGA - eBay API Scanner')
    parser.add_argument('query', nargs='?', help='Arama sorgusu')
    parser.add_argument('--max', type=int, default=100, help='Maksimum sonuc')
    parser.add_argument('--category', type=str, help='Kategori')
    parser.add_argument('--seller', type=str, help='Satici adi')
    parser.add_argument('--deals', action='store_true', help='Firsat modu')

    args = parser.parse_args()

    print("=" * 50)
    print("TATANGA - eBay API Scanner")
    print("=" * 50)

    scanner = EbayScanner()

    if args.seller:
        # Satici urunleri
        items = scanner.get_seller_items(args.seller, args.max)
        parsed = [scanner.parse_item(item) for item in items]

    elif args.deals and args.query:
        # Firsat modu
        parsed = scanner.find_deals(args.query, condition="USED")

    elif args.query:
        # Normal arama
        items = scanner.search_with_pagination(args.query, max_results=args.max)
        parsed = [scanner.parse_item(item) for item in items]

    else:
        # Demo
        print("\nDemo: Nike Sneaker arama")
        items = scanner.search_with_pagination("Nike Air Max", max_results=20)
        parsed = [scanner.parse_item(item) for item in items]

    # Sonuclari goster
    if parsed:
        print("\nBulunan Urunler:")
        for item in parsed[:10]:
            print(f"  - {item['title'][:40]}... | {item['price']} {item['currency']}")

        # Kaydet
        scanner.save_results(parsed)

        # Telegram
        msg = f"""
eBay Tarama Tamamlandi!

Sorgu: {args.query or 'Demo'}
Bulunan: {len(parsed)} urun

En Ucuz 3:
"""
        for item in sorted(parsed, key=lambda x: x['price'])[:3]:
            msg += f"- {item['title'][:30]}... | {item['price']} EUR\n"

        send_telegram(msg)

    else:
        print("\nKullanim:")
        print("  python ebay_api_scanner.py 'Nike Air Max' --max 200")
        print("  python ebay_api_scanner.py --seller css_berlin")
        print("  python ebay_api_scanner.py 'Adidas' --deals")

if __name__ == "__main__":
    main()
