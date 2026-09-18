#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TATANGA - Willhaben.at Scraper
Avusturya pazari icin Willhaben tarama
"""

import os
import sys
import json
import time
import re
from pathlib import Path
from datetime import datetime

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.config.credentials import TELEGRAM, WILLHABEN
from shared.utils.proxy_manager import SafeRequester, ProxyManager

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    import undetected_chromedriver as uc
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

import requests

# ============================================
# CONFIGURATION
# ============================================
OUTPUT_DIR = Path(__file__).parent / "output"
LOGS_DIR = Path(__file__).parent / "logs"

OUTPUT_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

WILLHABEN_BASE = "https://www.willhaben.at"

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
# WILLHABEN SCRAPER
# ============================================
class WillhabenScraper:
    """Willhaben Selenium tarayici"""

    def __init__(self, headless=True):
        self.driver = None
        self.headless = headless
        self.proxy_manager = ProxyManager()

    def init_driver(self):
        """Chrome driver baslat"""
        if not SELENIUM_AVAILABLE:
            print("[-] Selenium yuklu degil!")
            return False

        try:
            options = uc.ChromeOptions()

            if self.headless:
                options.add_argument('--headless=new')

            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--window-size=1920,1080')
            options.add_argument('--lang=de-AT')

            ua = self.proxy_manager.get_random_user_agent()
            options.add_argument(f'--user-agent={ua}')

            proxy = self.proxy_manager.get_proxy_for_platform('willhaben')
            if proxy:
                options.add_argument(f'--proxy-server={proxy["http"]}')

            self.driver = uc.Chrome(options=options)
            self.driver.implicitly_wait(10)

            print("[+] Chrome driver baslatildi")
            return True

        except Exception as e:
            print(f"[-] Driver hatasi: {e}")
            return False

    def close_popups(self):
        """Popup'lari kapat"""
        try:
            # Cookie consent
            consent_btn = WebDriverWait(self.driver, 5).until(
                EC.element_to_be_clickable((By.ID, "didomi-notice-agree-button"))
            )
            consent_btn.click()
            time.sleep(1)
        except:
            pass

    def search(self, query, category="marktplatz", max_pages=5):
        """
        Willhaben'de ara

        Args:
            query: Arama sorgusu
            category: Kategori (marktplatz, mode-accessoires, etc.)
            max_pages: Maksimum sayfa

        Returns:
            list: Urunler
        """
        if not self.init_driver():
            return []

        all_items = []

        try:
            # Arama URL'i
            search_url = f"{WILLHABEN_BASE}/iad/{category}?keyword={query.replace(' ', '+')}&rows=30&sort=1"
            print(f"\n[*] Arama: {search_url}")

            self.driver.get(search_url)
            time.sleep(3)
            self.close_popups()

            for page in range(1, max_pages + 1):
                print(f"    Sayfa {page} taraniyor...")

                items = self.parse_listings()
                all_items.extend(items)

                # Scroll ve yeni icerik yukle
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)

                # Sonraki sayfa
                try:
                    next_btn = self.driver.find_element(By.CSS_SELECTOR, "[data-testid='pagination-top-next-button']")
                    if next_btn.get_attribute('disabled'):
                        break
                    next_btn.click()
                    time.sleep(self.proxy_manager.get_delay('willhaben'))
                except:
                    break

            print(f"\n[+] Toplam {len(all_items)} urun bulundu")
            return all_items

        except Exception as e:
            print(f"[-] Arama hatasi: {e}")
            return all_items

        finally:
            if self.driver:
                self.driver.quit()

    def parse_listings(self):
        """Sayfa urunlerini parse et"""
        items = []

        try:
            listings = self.driver.find_elements(By.CSS_SELECTOR, "[data-testid='search-result-entry']")

            for listing in listings:
                try:
                    item = self.parse_item(listing)
                    if item:
                        items.append(item)
                except:
                    continue

        except Exception as e:
            print(f"    [-] Parse hatasi: {e}")

        return items

    def parse_item(self, element):
        """Tek item parse et"""
        try:
            # Link
            link_el = element.find_element(By.CSS_SELECTOR, "a")
            url = link_el.get_attribute('href')
            item_id = url.split('/')[-1] if url else ""

            # Baslik
            try:
                title_el = element.find_element(By.CSS_SELECTOR, "[data-testid='ad-title']")
                title = title_el.text.strip()
            except:
                title = ""

            # Fiyat
            try:
                price_el = element.find_element(By.CSS_SELECTOR, "[data-testid='ad-price']")
                price_text = price_el.text.strip()
                price_match = re.search(r'(\d+(?:[.,]\d+)?)', price_text.replace('.', '').replace(',', '.'))
                price = float(price_match.group(1)) if price_match else 0
            except:
                price = 0

            # Resim
            try:
                img_el = element.find_element(By.CSS_SELECTOR, "img")
                image = img_el.get_attribute('src')
            except:
                image = ""

            # Konum
            try:
                location_el = element.find_element(By.CSS_SELECTOR, "[data-testid='ad-location']")
                location = location_el.text.strip()
            except:
                location = ""

            return {
                "id": item_id,
                "title": title,
                "price": price,
                "currency": "EUR",
                "url": url,
                "image": image,
                "location": location,
                "source": "willhaben",
                "scraped_at": datetime.now().isoformat()
            }

        except:
            return None

    def save_results(self, items, filename=None):
        """Sonuclari kaydet"""
        if not filename:
            filename = f"willhaben_search_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        output_path = OUTPUT_DIR / filename

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(items, f, ensure_ascii=False, indent=2)

        print(f"[+] Kaydedildi: {output_path}")
        return output_path

# ============================================
# MAIN
# ============================================
def main():
    import argparse

    parser = argparse.ArgumentParser(description='TATANGA - Willhaben Scraper')
    parser.add_argument('query', nargs='?', help='Arama sorgusu')
    parser.add_argument('--pages', type=int, default=3, help='Maksimum sayfa')
    parser.add_argument('--category', type=str, default='marktplatz', help='Kategori')
    parser.add_argument('--visible', action='store_true', help='Browser gorunsun')

    args = parser.parse_args()

    print("=" * 50)
    print("TATANGA - Willhaben.at Scraper")
    print("=" * 50)

    if not SELENIUM_AVAILABLE:
        print("\n[-] Selenium yuklu degil!")
        return

    scraper = WillhabenScraper(headless=not args.visible)

    if args.query:
        items = scraper.search(args.query, category=args.category, max_pages=args.pages)
    else:
        print("\nDemo: Nike arama")
        items = scraper.search("Nike", max_pages=2)

    if items:
        print("\nBulunan Urunler:")
        for item in items[:10]:
            print(f"  - {item['title'][:40]}... | {item['price']} EUR")

        scraper.save_results(items)

        msg = f"Willhaben Tarama: {len(items)} urun bulundu"
        send_telegram(msg)

    else:
        print("\nKullanim: python willhaben_scraper.py 'Nike Air Max'")

if __name__ == "__main__":
    main()
