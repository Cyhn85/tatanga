#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TATANGA - Kleinanzeigen Scraper
Selenium ile Kleinanzeigen tarama
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

from shared.config.credentials import TELEGRAM, KLEINANZEIGEN
from shared.utils.proxy_manager import SafeRequester, ProxyManager

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException, NoSuchElementException
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

KLEINANZEIGEN_BASE = "https://www.kleinanzeigen.de"

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
# KLEINANZEIGEN SCRAPER
# ============================================
class KleinanzeigenScraper:
    """Kleinanzeigen Selenium tarayici"""

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
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_argument('--window-size=1920,1080')
            options.add_argument('--lang=de-DE')

            # User agent
            ua = self.proxy_manager.get_random_user_agent()
            options.add_argument(f'--user-agent={ua}')

            # Proxy
            proxy = self.proxy_manager.get_proxy_for_platform('kleinanzeigen')
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
            # GDPR consent
            consent_btn = WebDriverWait(self.driver, 5).until(
                EC.element_to_be_clickable((By.ID, "gdpr-banner-accept"))
            )
            consent_btn.click()
            time.sleep(1)
        except:
            pass

    def search(self, query, category=None, location=None, max_pages=5):
        """
        Kleinanzeigen'de ara

        Args:
            query: Arama sorgusu
            category: Kategori
            location: Konum
            max_pages: Maksimum sayfa

        Returns:
            list: Urunler
        """
        if not self.init_driver():
            return []

        all_items = []

        try:
            # Arama URL'i olustur
            search_url = f"{KLEINANZEIGEN_BASE}/s-{query.replace(' ', '-')}/k0"
            if location:
                search_url = f"{KLEINANZEIGEN_BASE}/s-{location}/{query.replace(' ', '-')}/k0"

            print(f"\n[*] Arama: {search_url}")
            self.driver.get(search_url)
            time.sleep(3)

            self.close_popups()

            for page in range(1, max_pages + 1):
                print(f"    Sayfa {page} taraniyor...")

                # Urunleri cek
                items = self.parse_listings()
                all_items.extend(items)

                # Sonraki sayfa
                try:
                    next_btn = self.driver.find_element(By.CSS_SELECTOR, "[data-testid='pagination-forward']")
                    if 'disabled' in next_btn.get_attribute('class'):
                        break

                    next_btn.click()
                    time.sleep(self.proxy_manager.get_delay('kleinanzeigen'))

                except NoSuchElementException:
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
        """
        Sayfa urunlerini parse et

        Returns:
            list: Urun listesi
        """
        items = []

        try:
            listings = self.driver.find_elements(By.CSS_SELECTOR, "article.aditem")

            for listing in listings:
                try:
                    item = self.parse_item(listing)
                    if item:
                        items.append(item)
                except Exception as e:
                    continue

        except Exception as e:
            print(f"    [-] Parse hatasi: {e}")

        return items

    def parse_item(self, element):
        """
        Tek item parse et

        Args:
            element: Selenium element

        Returns:
            dict: Urun bilgileri
        """
        try:
            # ID
            item_id = element.get_attribute('data-adid')

            # Link ve baslik
            title_el = element.find_element(By.CSS_SELECTOR, "a.ellipsis")
            title = title_el.text.strip()
            url = title_el.get_attribute('href')

            # Fiyat
            try:
                price_el = element.find_element(By.CSS_SELECTOR, "p.aditem-main--middle--price-shipping--price")
                price_text = price_el.text.strip()
                # "25 EUR VB" -> 25
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
                location_el = element.find_element(By.CSS_SELECTOR, "div.aditem-main--top--left")
                location = location_el.text.strip()
            except:
                location = ""

            # Tarih
            try:
                date_el = element.find_element(By.CSS_SELECTOR, "div.aditem-main--top--right")
                date_text = date_el.text.strip()
            except:
                date_text = ""

            return {
                "id": item_id,
                "title": title,
                "price": price,
                "currency": "EUR",
                "url": url,
                "image": image,
                "location": location,
                "date": date_text,
                "source": "kleinanzeigen",
                "scraped_at": datetime.now().isoformat()
            }

        except Exception as e:
            return None

    def get_user_listings(self, user_id):
        """
        Kullanici ilanlarini al

        Args:
            user_id: Kullanici ID

        Returns:
            list: Ilanlar
        """
        if not self.init_driver():
            return []

        try:
            url = f"{KLEINANZEIGEN_BASE}/s-bestandsliste.html?userId={user_id}"
            print(f"\n[*] Kullanici ilanlari: {url}")

            self.driver.get(url)
            time.sleep(3)
            self.close_popups()

            items = self.parse_listings()
            return items

        except Exception as e:
            print(f"[-] Kullanici ilanlari hatasi: {e}")
            return []

        finally:
            if self.driver:
                self.driver.quit()

    def save_results(self, items, filename=None):
        """Sonuclari kaydet"""
        if not filename:
            filename = f"kleinanzeigen_search_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

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

    parser = argparse.ArgumentParser(description='TATANGA - Kleinanzeigen Scraper')
    parser.add_argument('query', nargs='?', help='Arama sorgusu')
    parser.add_argument('--pages', type=int, default=3, help='Maksimum sayfa')
    parser.add_argument('--location', type=str, help='Konum')
    parser.add_argument('--user', type=str, help='Kullanici ID')
    parser.add_argument('--visible', action='store_true', help='Browser gorunsun')

    args = parser.parse_args()

    print("=" * 50)
    print("TATANGA - Kleinanzeigen Scraper")
    print("=" * 50)

    if not SELENIUM_AVAILABLE:
        print("\n[-] Selenium yuklu degil!")
        return

    scraper = KleinanzeigenScraper(headless=not args.visible)

    if args.user:
        items = scraper.get_user_listings(args.user)

    elif args.query:
        items = scraper.search(args.query, location=args.location, max_pages=args.pages)

    else:
        # Demo
        print("\nDemo: Nike arama")
        items = scraper.search("Nike", max_pages=2)

    if items:
        # Sonuclari goster
        print("\nBulunan Urunler:")
        for item in items[:10]:
            print(f"  - {item['title'][:40]}... | {item['price']} EUR | {item['location']}")

        # Kaydet
        scraper.save_results(items)

        # Telegram
        msg = f"""
Kleinanzeigen Tarama Tamamlandi!

Sorgu: {args.query or 'Demo'}
Bulunan: {len(items)} urun

En Ucuz 3:
"""
        for item in sorted(items, key=lambda x: x['price'] if x['price'] > 0 else 9999)[:3]:
            msg += f"- {item['title'][:25]}... | {item['price']} EUR\n"

        send_telegram(msg)

    else:
        print("\nKullanim:")
        print("  python kleinanzeigen_scraper.py 'Nike Air Max' --pages 5")
        print("  python kleinanzeigen_scraper.py --user 123456")

if __name__ == "__main__":
    main()
