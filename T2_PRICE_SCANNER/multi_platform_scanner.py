#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TATANGA - Multi-Platform Scanner
Tum platformlari ayni anda tara ve karsilastir
"""

import os
import sys
import json
import time
import asyncio
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.config.credentials import TELEGRAM
import requests

# Import scrapers
from ebay_api_scanner import EbayScanner
from kleinanzeigen_scraper import KleinanzeigenScraper
from willhaben_scraper import WillhabenScraper
from shpock_scraper import ShpockScraper
from vinted_scraper import VintedProfileScraper

# ============================================
# CONFIGURATION
# ============================================
OUTPUT_DIR = Path(__file__).parent / "output"
LOGS_DIR = Path(__file__).parent / "logs"

OUTPUT_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

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
# MULTI-PLATFORM SCANNER
# ============================================
class MultiPlatformScanner:
    """Tum platformlari tara"""

    def __init__(self):
        self.results = {}
        self.errors = {}

    def search_ebay(self, query, max_results=100):
        """eBay'de ara"""
        try:
            scanner = EbayScanner()
            items = scanner.search_with_pagination(query, max_results=max_results)
            return [scanner.parse_item(item) for item in items]
        except Exception as e:
            self.errors['ebay'] = str(e)
            return []

    def search_kleinanzeigen(self, query, max_pages=3):
        """Kleinanzeigen'de ara"""
        try:
            scanner = KleinanzeigenScraper(headless=True)
            return scanner.search(query, max_pages=max_pages)
        except Exception as e:
            self.errors['kleinanzeigen'] = str(e)
            return []

    def search_willhaben(self, query, max_pages=3):
        """Willhaben'de ara"""
        try:
            scanner = WillhabenScraper(headless=True)
            return scanner.search(query, max_pages=max_pages)
        except Exception as e:
            self.errors['willhaben'] = str(e)
            return []

    def search_shpock(self, query, max_scrolls=5):
        """Shpock'ta ara"""
        try:
            scanner = ShpockScraper(headless=True)
            return scanner.search(query, max_scrolls=max_scrolls)
        except Exception as e:
            self.errors['shpock'] = str(e)
            return []

    def search_all_platforms(self, query, platforms=None):
        """
        Tum platformlarda paralel ara

        Args:
            query: Arama sorgusu
            platforms: Platform listesi (None = hepsi)

        Returns:
            dict: Platform bazli sonuclar
        """
        if platforms is None:
            platforms = ['ebay', 'kleinanzeigen', 'willhaben', 'shpock']

        print(f"\n[*] Multi-platform arama: {query}")
        print(f"    Platformlar: {', '.join(platforms)}")

        results = {}

        # Paralel arama
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {}

            if 'ebay' in platforms:
                futures[executor.submit(self.search_ebay, query)] = 'ebay'
            if 'kleinanzeigen' in platforms:
                futures[executor.submit(self.search_kleinanzeigen, query)] = 'kleinanzeigen'
            if 'willhaben' in platforms:
                futures[executor.submit(self.search_willhaben, query)] = 'willhaben'
            if 'shpock' in platforms:
                futures[executor.submit(self.search_shpock, query)] = 'shpock'

            for future in as_completed(futures):
                platform = futures[future]
                try:
                    items = future.result()
                    results[platform] = items
                    print(f"    [+] {platform}: {len(items)} urun")
                except Exception as e:
                    results[platform] = []
                    self.errors[platform] = str(e)
                    print(f"    [-] {platform}: Hata - {e}")

        self.results = results
        return results

    def find_price_differences(self):
        """
        Ayni urunlerin farkli platformlardaki fiyatlarini karsilastir

        Returns:
            list: Fiyat farki olan urunler
        """
        differences = []

        # Tum urunleri birlestir ve basliga gore grupla
        all_items = []
        for platform, items in self.results.items():
            for item in items:
                item['platform'] = platform
                all_items.append(item)

        # Basitlerilmis benzerlik kontrolu (marka + anahtar kelimeler)
        # Gercek sistemde daha gelismis matching gerekli

        # Fiyata gore sirala
        all_items.sort(key=lambda x: x.get('price', 0))

        return all_items

    def generate_report(self):
        """Rapor olustur"""
        report = []
        report.append("=" * 50)
        report.append("MULTI-PLATFORM TARAMA RAPORU")
        report.append(f"Tarih: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
        report.append("=" * 50)

        total_items = 0

        for platform, items in self.results.items():
            count = len(items)
            total_items += count

            report.append(f"\n{platform.upper()}: {count} urun")

            if items:
                # En ucuz 3
                sorted_items = sorted(items, key=lambda x: x.get('price', 9999) if x.get('price', 0) > 0 else 9999)
                report.append("  En Ucuz:")
                for item in sorted_items[:3]:
                    title = item.get('title', '')[:30]
                    price = item.get('price', 0)
                    report.append(f"    - {title}... | {price} EUR")

        report.append(f"\nToplam: {total_items} urun")

        if self.errors:
            report.append("\nHatalar:")
            for platform, error in self.errors.items():
                report.append(f"  - {platform}: {error}")

        return "\n".join(report)

    def save_results(self, filename=None):
        """Sonuclari kaydet"""
        if not filename:
            filename = f"multi_platform_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        output_path = OUTPUT_DIR / filename

        data = {
            "query": "",
            "timestamp": datetime.now().isoformat(),
            "platforms": self.results,
            "errors": self.errors,
            "totals": {p: len(items) for p, items in self.results.items()}
        }

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"\n[+] Kaydedildi: {output_path}")
        return output_path

# ============================================
# MAIN
# ============================================
def main():
    import argparse

    parser = argparse.ArgumentParser(description='TATANGA - Multi-Platform Scanner')
    parser.add_argument('query', nargs='?', help='Arama sorgusu')
    parser.add_argument('--platforms', nargs='+', default=['ebay', 'kleinanzeigen'],
                       help='Platformlar (ebay, kleinanzeigen, willhaben, shpock)')
    parser.add_argument('--notify', action='store_true', help='Telegram bildirim')

    args = parser.parse_args()

    print("=" * 50)
    print("TATANGA - Multi-Platform Scanner")
    print("=" * 50)

    scanner = MultiPlatformScanner()

    if args.query:
        results = scanner.search_all_platforms(args.query, args.platforms)
    else:
        print("\nDemo: Nike Air Max arama")
        results = scanner.search_all_platforms("Nike Air Max", ['ebay'])

    # Rapor
    report = scanner.generate_report()
    print(report)

    # Kaydet
    scanner.save_results()

    # Telegram
    if args.notify:
        total = sum(len(items) for items in results.values())
        msg = f"""
Multi-Platform Tarama Tamamlandi!

Sorgu: {args.query or 'Demo'}
Toplam: {total} urun

Platformlar:
"""
        for platform, items in results.items():
            msg += f"- {platform}: {len(items)}\n"

        send_telegram(msg)

    print("\nKullanim:")
    print("  python multi_platform_scanner.py 'Nike Air Max' --platforms ebay kleinanzeigen willhaben")

if __name__ == "__main__":
    main()
