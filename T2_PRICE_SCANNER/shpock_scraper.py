#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TATANGA - Shpock Scraper
Shpock mobil pazaryeri tarama
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

from shared.config.credentials import TELEGRAM
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

SHPOCK_BASE = "https://www.shpock.com"

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
# SHPOCK SCRAPER
# ============================================
class ShpockScraper:
    """Shpock Selenium tarayici"""

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
            options.add_argument('--lang=de-DE')

            ua = self.proxy_manager.get_random_user_agent()
            options.add_argument(f'--user-agent={ua}')

            proxy = self.proxy_manager.get_proxy_for_platform('shpock')
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
                EC.element_to_be_clickable((By.CSS_SELECTOR, "[data-testid='cookie-accept-all']"))
            )
            consent_btn.click()
            time.sleep(1)
        except:
            pass

    def search(self, query, location="Berlin", max_scrolls=10):
        """
        Shpock'ta ara

        Args:
            query: Arama sorgusu
            location: Konum
            max_scrolls: Maksimum scroll sayisi

        Returns:
            list: Urunler
        """
        if not self.init_driver():
            return []

        all_items = []

        try:
            # Arama URL'i - Shpock GraphQL kullaniyor
            search_url = f"{SHPOCK_BASE}/results?q={query.replace(' ', '%20')}"
            print(f"\n[*] Arama: {search_url}")

            self.driver.get(search_url)
            time.sleep(3)
            self.close_popups()

            # Infinite scroll ile urunleri yukle
            last_height = self.driver.execute_script("return document.body.scrollHeight")

            for scroll in range(max_scrolls):
                print(f"    Scroll {scroll + 1}...")

                # Mevcut urunleri cek
                items = self.parse_listings()

                # Yeni urunleri ekle
                for item in items:
                    if not any(i['id'] == item['id'] for i in all_items):
                        all_items.append(item)

                # Scroll
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(self.proxy_manager.get_delay('shpock'))

                # Yeni icerik yuklendi mi
                new_height = self.driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    break
                last_height = new_height

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
            # Shpock item kartlari
            listings = self.driver.find_elements(By.CSS_SELECTOR, "[data-testid='item-card']")

            if not listings:
                # Alternatif selector
                listings = self.driver.find_elements(By.CSS_SELECTOR, "a[href*='/item/']")

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
            # URL ve ID
            try:
                if element.tag_name == 'a':
                    url = element.get_attribute('href')
                else:
                    link = element.find_element(By.CSS_SELECTOR, "a")
                    url = link.get_attribute('href')

                item_id = url.split('/item/')[-1].split('/')[0] if '/item/' in url else ""
            except:
                return None

            # Baslik
            try:
                title_el = element.find_element(By.CSS_SELECTOR, "[data-testid='item-title']")
                title = title_el.text.strip()
            except:
                try:
                    title_el = element.find_element(By.CSS_SELECTOR, "h3, h4")
                    title = title_el.text.strip()
                except:
                    title = ""

            # Fiyat
            try:
                price_el = element.find_element(By.CSS_SELECTOR, "[data-testid='item-price']")
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

            return {
                "id": item_id,
                "title": title,
                "price": price,
                "currency": "EUR",
                "url": url,
                "image": image,
                "source": "shpock",
                "scraped_at": datetime.now().isoformat()
            }

        except:
            return None

    def save_results(self, items, filename=None):
        """Sonuclari kaydet"""
        if not filename:
            filename = f"shpock_search_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

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

    parser = argparse.ArgumentParser(description='TATANGA - Shpock Scraper')
    parser.add_argument('query', nargs='?', help='Arama sorgusu')
    parser.add_argument('--scrolls', type=int, default=5, help='Maksimum scroll')
    parser.add_argument('--visible', action='store_true', help='Browser gorunsun')

    args = parser.parse_args()

    print("=" * 50)
    print("TATANGA - Shpock Scraper")
    print("=" * 50)

    if not SELENIUM_AVAILABLE:
        print("\n[-] Selenium yuklu degil!")
        return

    scraper = ShpockScraper(headless=not args.visible)

    if args.query:
        items = scraper.search(args.query, max_scrolls=args.scrolls)
    else:
        print("\nDemo: Nike arama")
        items = scraper.search("Nike", max_scrolls=3)

    if items:
        print("\nBulunan Urunler:")
        for item in items[:10]:
            print(f"  - {item['title'][:40]}... | {item['price']} EUR")

        scraper.save_results(items)

        msg = f"Shpock Tarama: {len(items)} urun bulundu"
        send_telegram(msg)

    else:
        print("\nKullanim: python shpock_scraper.py 'Nike Air Max'")

if __name__ == "__main__":
    main()
