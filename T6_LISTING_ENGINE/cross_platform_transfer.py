#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TATANGA - Cross-Platform Product Transfer
Platformlar arasi urun aktarma
Kleinanzeigen -> Vinted, eBay -> Willhaben, etc.
"""

import os
import sys
import json
import time
import re
import requests
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.config.credentials import TELEGRAM, VINTED, KLEINANZEIGEN, EBAY, WILLHABEN, AI_SERVICES
from shared.utils.proxy_manager import ProxyManager

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.common.keys import Keys
    import undetected_chromedriver as uc
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

from PIL import Image
import io

# ============================================
# CONFIGURATION
# ============================================
OUTPUT_DIR = Path(__file__).parent / "output"
TEMP_DIR = Path(__file__).parent / "temp"
LOGS_DIR = Path(__file__).parent / "logs"

for d in [OUTPUT_DIR, TEMP_DIR, LOGS_DIR]:
    d.mkdir(exist_ok=True)

# ============================================
# TELEGRAM NOTIFICATION
# ============================================
def send_telegram(message, channel="general"):
    """Telegram'a mesaj gonder"""
    channels = TELEGRAM.get("channels", {})
    chat_id = channels.get(channel, TELEGRAM["admin_chat_id"])

    url = f"https://api.telegram.org/bot{TELEGRAM['bot_token']}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, data=data)
    except Exception as e:
        print(f"Telegram hatasi: {e}")

# ============================================
# PRODUCT SCRAPER
# ============================================
class ProductScraper:
    """Platform'dan urun bilgisi cekici"""

    def __init__(self):
        self.driver = None
        self.proxy_manager = ProxyManager()

    def init_driver(self, headless=True):
        """Driver baslat"""
        if not SELENIUM_AVAILABLE:
            return False

        try:
            options = uc.ChromeOptions()
            if headless:
                options.add_argument('--headless=new')

            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--window-size=1920,1080')

            ua = self.proxy_manager.get_random_user_agent()
            options.add_argument(f'--user-agent={ua}')

            self.driver = uc.Chrome(options=options)
            self.driver.implicitly_wait(10)
            return True

        except Exception as e:
            print(f"[-] Driver hatasi: {e}")
            return False

    def scrape_kleinanzeigen_product(self, url):
        """
        Kleinanzeigen urun bilgisi cek

        Args:
            url: Urun URL'i

        Returns:
            dict: Urun bilgileri
        """
        if not self.init_driver():
            return None

        try:
            print(f"[*] Kleinanzeigen urun cekiliyor: {url}")
            self.driver.get(url)
            time.sleep(3)

            product = {
                "source": "kleinanzeigen",
                "source_url": url,
                "scraped_at": datetime.now().isoformat()
            }

            # Baslik
            try:
                title_el = self.driver.find_element(By.ID, "viewad-title")
                product["title"] = title_el.text.strip()
            except:
                product["title"] = ""

            # Fiyat
            try:
                price_el = self.driver.find_element(By.ID, "viewad-price")
                price_text = price_el.text.strip()
                price_match = re.search(r'(\d+)', price_text.replace('.', ''))
                product["price"] = int(price_match.group(1)) if price_match else 0
            except:
                product["price"] = 0

            # Aciklama
            try:
                desc_el = self.driver.find_element(By.ID, "viewad-description-text")
                product["description"] = desc_el.text.strip()
            except:
                product["description"] = ""

            # Resimler
            images = []
            try:
                img_elements = self.driver.find_elements(By.CSS_SELECTOR, "#viewad-thumbnail-list img")
                for img in img_elements:
                    src = img.get_attribute("src")
                    if src:
                        # Buyuk resim URL'i
                        big_src = src.replace("_57.", "_2048.").replace("_72.", "_2048.")
                        images.append(big_src)
            except:
                pass

            product["images"] = images

            # Konum
            try:
                loc_el = self.driver.find_element(By.ID, "viewad-locality")
                product["location"] = loc_el.text.strip()
            except:
                product["location"] = ""

            # Kategori
            try:
                cat_el = self.driver.find_element(By.CSS_SELECTOR, "#vap-brdcrmb a:last-child")
                product["category"] = cat_el.text.strip()
            except:
                product["category"] = ""

            print(f"[+] Urun cekildi: {product['title'][:40]}...")
            return product

        except Exception as e:
            print(f"[-] Scrape hatasi: {e}")
            return None

        finally:
            if self.driver:
                self.driver.quit()

    def scrape_vinted_product(self, url):
        """Vinted urun bilgisi cek"""
        # Benzer yapi
        pass

    def scrape_ebay_product(self, url):
        """eBay urun bilgisi cek"""
        # API kullan
        pass

    def download_images(self, image_urls, product_id):
        """
        Resimleri indir

        Args:
            image_urls: Resim URL listesi
            product_id: Urun ID

        Returns:
            list: Lokal dosya yollari
        """
        local_paths = []

        for i, url in enumerate(image_urls):
            try:
                response = requests.get(url, timeout=30)
                if response.status_code == 200:
                    filename = f"{product_id}_{i+1}.jpg"
                    filepath = TEMP_DIR / filename

                    with open(filepath, 'wb') as f:
                        f.write(response.content)

                    local_paths.append(str(filepath))
                    print(f"    Resim {i+1} indirildi")

            except Exception as e:
                print(f"    [-] Resim {i+1} indirilemedi: {e}")

        return local_paths

# ============================================
# PRODUCT UPLOADER
# ============================================
class ProductUploader:
    """Platform'a urun yukleyici"""

    def __init__(self):
        self.driver = None
        self.proxy_manager = ProxyManager()

    def init_driver(self, headless=False):
        """Driver baslat (upload icin gorunur olabilir)"""
        if not SELENIUM_AVAILABLE:
            return False

        try:
            options = uc.ChromeOptions()
            if headless:
                options.add_argument('--headless=new')

            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--window-size=1920,1080')

            ua = self.proxy_manager.get_random_user_agent()
            options.add_argument(f'--user-agent={ua}')

            self.driver = uc.Chrome(options=options)
            self.driver.implicitly_wait(10)
            return True

        except Exception as e:
            print(f"[-] Driver hatasi: {e}")
            return False

    def login_vinted(self, account):
        """Vinted'e giris yap"""
        try:
            self.driver.get("https://www.vinted.de/member/general/login")
            time.sleep(3)

            # Cookie popup
            try:
                accept = self.driver.find_element(By.ID, "onetrust-accept-btn-handler")
                accept.click()
                time.sleep(1)
            except:
                pass

            # Email
            email_input = self.driver.find_element(By.NAME, "email")
            email_input.send_keys(account['email'])

            # Password
            pass_input = self.driver.find_element(By.NAME, "password")
            pass_input.send_keys(account['password'])

            # Submit
            submit = self.driver.find_element(By.CSS_SELECTOR, "[type='submit']")
            submit.click()

            time.sleep(5)

            # Basarili mi?
            if "login" not in self.driver.current_url:
                print("[+] Vinted giris basarili")
                return True

            print("[-] Vinted giris basarisiz")
            return False

        except Exception as e:
            print(f"[-] Login hatasi: {e}")
            return False

    def upload_to_vinted(self, product, account, images):
        """
        Vinted'e urun yukle

        Args:
            product: Urun bilgileri
            account: Vinted hesap bilgisi
            images: Lokal resim dosyalari

        Returns:
            str: Olusturulan ilan URL'i
        """
        if not self.init_driver(headless=False):
            return None

        try:
            # Login
            if not self.login_vinted(account):
                return None

            # Urun ekleme sayfasi
            self.driver.get("https://www.vinted.de/items/new")
            time.sleep(3)

            # Resim yukle
            print("[*] Resimler yukleniyor...")
            file_input = self.driver.find_element(By.CSS_SELECTOR, "input[type='file']")

            for img_path in images[:20]:  # Max 20 resim
                file_input.send_keys(img_path)
                time.sleep(2)

            # Baslik
            title_input = self.driver.find_element(By.NAME, "title")
            title_input.clear()
            title_input.send_keys(product['title'][:80])

            # Aciklama
            desc_input = self.driver.find_element(By.NAME, "description")
            desc_input.clear()
            desc_input.send_keys(product.get('description', '')[:2000])

            # Kategori secimi
            # ... (kategori dropdown)

            # Fiyat
            price_input = self.driver.find_element(By.NAME, "price")
            price_input.clear()
            price_input.send_keys(str(product['price']))

            # Beden, marka vs.
            # ...

            print("[*] Form dolduruldu, onay bekleniyor...")

            # OTOMATIK GONDERME - Dikkatli ol!
            # submit_btn = self.driver.find_element(By.CSS_SELECTOR, "[type='submit']")
            # submit_btn.click()

            # Simdilik sadece form doldur, manuel onay icin bekle
            input("Enter'a bas submit icin (veya Ctrl+C iptal)...")

            return "https://www.vinted.de/items/NEW_ID"

        except Exception as e:
            print(f"[-] Upload hatasi: {e}")
            return None

        finally:
            if self.driver:
                self.driver.quit()

    def login_kleinanzeigen(self, account):
        """Kleinanzeigen'e giris yap"""
        # Benzer yapi
        pass

    def upload_to_kleinanzeigen(self, product, account, images):
        """Kleinanzeigen'e urun yukle"""
        # Benzer yapi
        pass

# ============================================
# CROSS-PLATFORM TRANSFER
# ============================================
class CrossPlatformTransfer:
    """Platformlar arasi aktarma yoneticisi"""

    def __init__(self):
        self.scraper = ProductScraper()
        self.uploader = ProductUploader()

    def transfer(self, source_url, target_platform, target_account_name):
        """
        Urunu bir platformdan digerine aktar

        Args:
            source_url: Kaynak urun URL'i
            target_platform: Hedef platform (vinted, kleinanzeigen, ebay, willhaben)
            target_account_name: Hedef hesap adi (main, secondary, etc.)

        Returns:
            str: Olusturulan ilan URL'i
        """
        print("\n" + "=" * 50)
        print("URUN AKTARMA")
        print("=" * 50)

        # Kaynak platformu belirle
        if "kleinanzeigen.de" in source_url:
            source_platform = "kleinanzeigen"
            product = self.scraper.scrape_kleinanzeigen_product(source_url)
        elif "vinted.de" in source_url:
            source_platform = "vinted"
            product = self.scraper.scrape_vinted_product(source_url)
        elif "ebay" in source_url:
            source_platform = "ebay"
            product = self.scraper.scrape_ebay_product(source_url)
        else:
            print(f"[-] Bilinmeyen kaynak platform: {source_url}")
            return None

        if not product:
            print("[-] Urun bilgisi alinamadi")
            return None

        print(f"\n[+] Kaynak: {source_platform}")
        print(f"    Baslik: {product['title']}")
        print(f"    Fiyat: {product['price']} EUR")
        print(f"    Resim: {len(product.get('images', []))} adet")

        # Resimleri indir
        product_id = f"TRANSFER-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        local_images = self.scraper.download_images(product.get('images', []), product_id)

        if not local_images:
            print("[-] Resim indirilemedi")
            return None

        # Hedef hesabi bul
        if target_platform == "vinted":
            accounts = VINTED.get('accounts', [])
        elif target_platform == "kleinanzeigen":
            accounts = KLEINANZEIGEN.get('accounts', [])
        elif target_platform == "ebay":
            accounts = EBAY.get('accounts', [])
        elif target_platform == "willhaben":
            accounts = WILLHABEN.get('accounts', [])
        else:
            print(f"[-] Bilinmeyen hedef platform: {target_platform}")
            return None

        target_account = next((a for a in accounts if a['name'] == target_account_name), None)
        if not target_account:
            print(f"[-] Hesap bulunamadi: {target_account_name}")
            return None

        print(f"\n[*] Hedef: {target_platform} ({target_account_name})")

        # Yukle
        if target_platform == "vinted":
            result_url = self.uploader.upload_to_vinted(product, target_account, local_images)
        elif target_platform == "kleinanzeigen":
            result_url = self.uploader.upload_to_kleinanzeigen(product, target_account, local_images)
        else:
            print(f"[-] {target_platform} yukleme henuz desteklenmiyor")
            result_url = None

        # Telegram bildirim
        if result_url:
            msg = f"""
URUN AKTARILDI!

Kaynak: {source_platform}
Hedef: {target_platform} ({target_account_name})

{product['title'][:40]}...
Fiyat: {product['price']} EUR

Yeni URL: {result_url}
            """
            send_telegram(msg, "notifications")

        # Temizlik
        for img_path in local_images:
            try:
                Path(img_path).unlink()
            except:
                pass

        return result_url

    def bulk_transfer(self, source_urls, target_platform, target_account):
        """Toplu aktarma"""
        results = []

        for url in source_urls:
            result = self.transfer(url, target_platform, target_account)
            results.append({
                "source": url,
                "result": result,
                "success": result is not None
            })
            time.sleep(30)  # Rate limiting

        return results

# ============================================
# MAIN
# ============================================
def main():
    import argparse

    parser = argparse.ArgumentParser(description='TATANGA - Cross-Platform Transfer')
    parser.add_argument('--source', type=str, help='Kaynak urun URL')
    parser.add_argument('--target', type=str, default='vinted', help='Hedef platform')
    parser.add_argument('--account', type=str, default='main', help='Hedef hesap')
    parser.add_argument('--demo', action='store_true', help='Demo mod')

    args = parser.parse_args()

    print("=" * 50)
    print("TATANGA - Cross-Platform Transfer")
    print("=" * 50)

    if not SELENIUM_AVAILABLE:
        print("\n[-] Selenium yuklu degil!")
        return

    transfer = CrossPlatformTransfer()

    if args.demo:
        print("\nDemo: Kleinanzeigen -> Vinted aktarma")
        print("Bu islem icin gercek bir Kleinanzeigen URL'i gerekli.")
        print("\nKullanim:")
        print("  python cross_platform_transfer.py --source 'https://www.kleinanzeigen.de/s-anzeige/...' --target vinted --account main")

    elif args.source:
        result = transfer.transfer(args.source, args.target, args.account)
        if result:
            print(f"\n[+] Basarili! Yeni URL: {result}")
        else:
            print("\n[-] Aktarma basarisiz")

    else:
        print("\nKullanim:")
        print("  python cross_platform_transfer.py --source URL --target PLATFORM --account ACCOUNT")
        print("\nOrnekler:")
        print("  Kleinanzeigen -> Vinted:")
        print("    --source 'https://www.kleinanzeigen.de/...' --target vinted --account main")
        print("\n  eBay -> Willhaben:")
        print("    --source 'https://www.ebay.de/...' --target willhaben --account main")

if __name__ == "__main__":
    main()
