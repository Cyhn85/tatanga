#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TATANGA - Vinted Selenium Scraper
Selenium ile Vinted magazasindan mevcut ilanlari ceker
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

from shared.config.credentials import TELEGRAM, VINTED

import requests

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
    print("Selenium yuklu degil. pip install selenium undetected-chromedriver")

# ============================================
# CONFIGURATION
# ============================================
OUTPUT_DIR = Path(__file__).parent / "output"
LOGS_DIR = Path(__file__).parent / "logs"

OUTPUT_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

VINTED_WEB_BASE = "https://www.vinted.de"

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
# SELENIUM SCRAPER
# ============================================
class VintedSeleniumScraper:
    """Selenium ile Vinted profil cekici"""

    def __init__(self, headless=True):
        self.driver = None
        self.headless = headless

    def init_driver(self):
        """Chrome driver baslat"""
        if not SELENIUM_AVAILABLE:
            print("[-] Selenium yuklu degil!")
            return False

        try:
            # Undetected Chrome kullan
            options = uc.ChromeOptions()

            if self.headless:
                options.add_argument('--headless=new')

            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_argument('--window-size=1920,1080')
            options.add_argument('--lang=de-DE')

            self.driver = uc.Chrome(options=options)
            self.driver.implicitly_wait(10)

            print("[+] Chrome driver baslatildi")
            return True

        except Exception as e:
            print(f"[-] Driver hatasi: {e}")
            return False

    def close_cookie_popup(self):
        """Cookie popup'ini kapat"""
        try:
            # Cookie kabul butonu
            accept_btn = WebDriverWait(self.driver, 5).until(
                EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler"))
            )
            accept_btn.click()
            time.sleep(1)
            print("[+] Cookie popup kapatildi")
        except:
            pass

    def scrape_profile(self, member_id):
        """
        Profildeki tum ilanlari cek
        """
        if not self.init_driver():
            return None

        profile_url = f"{VINTED_WEB_BASE}/member/{member_id}"
        print(f"\n[*] Profil aciliyor: {profile_url}")

        try:
            self.driver.get(profile_url)
            time.sleep(3)

            # Cookie popup
            self.close_cookie_popup()

            # Sayfa yuklenene kadar bekle
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid='grid-item']"))
            )

            all_items = []
            scroll_count = 0
            max_scrolls = 20

            # Scroll ile tum urunleri yukle
            last_height = self.driver.execute_script("return document.body.scrollHeight")

            while scroll_count < max_scrolls:
                # Sayfanin altina scroll
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)

                # Yeni icerik yuklendi mi kontrol et
                new_height = self.driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    break
                last_height = new_height
                scroll_count += 1
                print(f"    Scroll {scroll_count}...")

            # Urunleri cek
            items = self.driver.find_elements(By.CSS_SELECTOR, "[data-testid='grid-item']")
            print(f"\n[*] {len(items)} urun bulundu, parse ediliyor...")

            for i, item in enumerate(items):
                try:
                    product = self.parse_item(item)
                    if product:
                        all_items.append(product)
                except Exception as e:
                    print(f"    [-] Item {i+1} hatasi: {e}")

            print(f"\n[+] Toplam {len(all_items)} ilan parse edildi")

            return {
                "member_id": member_id,
                "scraped_at": datetime.now().isoformat(),
                "total_items": len(all_items),
                "items": all_items
            }

        except TimeoutException:
            print("[-] Sayfa yuklenemedi (timeout)")
            return None

        except Exception as e:
            print(f"[-] Scraping hatasi: {e}")
            return None

        finally:
            if self.driver:
                self.driver.quit()

    def parse_item(self, item_element):
        """
        Tek item element'ini parse et
        """
        try:
            # Link
            link = item_element.find_element(By.CSS_SELECTOR, "a").get_attribute("href")
            item_id = re.search(r'/items/(\d+)', link)
            item_id = item_id.group(1) if item_id else ""

            # Resim
            img = item_element.find_element(By.CSS_SELECTOR, "img")
            image_url = img.get_attribute("src")
            title = img.get_attribute("alt") or ""

            # Fiyat
            try:
                price_el = item_element.find_element(By.CSS_SELECTOR, "[data-testid='item-price']")
                price_text = price_el.text.replace("EUR", "").replace(",", ".").strip()
                price = float(re.sub(r'[^\d.]', '', price_text))
            except:
                price = 0

            # Beden
            try:
                size_el = item_element.find_element(By.CSS_SELECTOR, "[data-testid='item-size']")
                size = size_el.text.strip()
            except:
                size = ""

            # Marka
            try:
                brand_el = item_element.find_element(By.CSS_SELECTOR, "[data-testid='item-brand']")
                brand = brand_el.text.strip()
            except:
                brand = ""

            return {
                "id": item_id,
                "title": title,
                "price": price,
                "currency": "EUR",
                "brand": brand,
                "size": size,
                "url": link,
                "image": image_url,
                "scraped_at": datetime.now().isoformat()
            }

        except Exception as e:
            return None

    def save_results(self, data, filename=None):
        """
        Sonuclari JSON olarak kaydet
        """
        if not filename:
            filename = f"vinted_profile_{data['member_id']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        output_path = OUTPUT_DIR / filename

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"[+] Kaydedildi: {output_path}")
        return output_path

# ============================================
# MAIN
# ============================================
def main():
    import argparse

    parser = argparse.ArgumentParser(description='TATANGA - Vinted Selenium Scraper')
    parser.add_argument('member_id', nargs='?', default='293217988', help='Member ID')
    parser.add_argument('--visible', action='store_true', help='Browser gorunur olsun')

    args = parser.parse_args()

    print("=" * 50)
    print("TATANGA - Vinted Selenium Scraper")
    print("=" * 50)

    if not SELENIUM_AVAILABLE:
        print("\n[-] Selenium yuklu degil!")
        print("Yuklemek icin: pip install selenium undetected-chromedriver")
        return

    scraper = VintedSeleniumScraper(headless=not args.visible)
    data = scraper.scrape_profile(args.member_id)

    if data:
        output_path = scraper.save_results(data)

        # Telegram bildirim
        msg = f"""
Vinted Profil Tarandi (Selenium)

Member ID: {data['member_id']}
Ilan Sayisi: {data['total_items']}

Dosya: {output_path.name}
        """
        send_telegram(msg)

        # Ozet goster
        print("\n" + "=" * 40)
        print("OZET:")
        print("=" * 40)
        for item in data['items'][:5]:
            print(f"- {item['title'][:40]}... | {item['price']} EUR | {item['size']}")
        if len(data['items']) > 5:
            print(f"... ve {len(data['items']) - 5} urun daha")

if __name__ == "__main__":
    main()
