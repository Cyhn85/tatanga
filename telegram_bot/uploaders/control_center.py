#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TATANGA Kontrol Merkezi
Tum platformlar icin tek tarayici - Manuel login, otomatik islem
"""

import sys
import time
import json
import threading
import requests
import re
from pathlib import Path
from datetime import datetime

# Selenium
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException, NoSuchElementException

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.config.credentials import VINTED

# Dizinler
BASE_DIR = Path(__file__).parent.parent.parent
TEMP_DIR = BASE_DIR / "T6_LISTING_ENGINE" / "temp"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

# Telegram bildirim ayarlari
TELEGRAM_BOT_TOKEN = "8222444116:AAG5D2xc7-7EOGYIX1s0Tx0jM2m5nOWG1dw"
TELEGRAM_CHAT_ID = "5149567290"

class ControlCenter:
    """Tum platformlari yoneten merkezi tarayici - Coklu hesap destekli"""

    def __init__(self):
        self.driver = None
        # Coklu hesap destegi - her platform icin birden fazla hesap
        self.accounts = {
            'vinted_1': {
                'platform': 'vinted',
                'name': 'Vinted Ana',
                'url': 'https://www.vinted.de',
                'email': 'cssberlin@hotmail.de',
                'logged_in': False,
                'tab_index': None
            },
            'vinted_2': {
                'platform': 'vinted',
                'name': 'Vinted 2',
                'url': 'https://www.vinted.de',
                'email': '',  # Ikinci hesap email
                'logged_in': False,
                'tab_index': None
            },
            'ebay_1': {
                'platform': 'ebay',
                'name': 'eBay Ana (css_berlin)',
                'url': 'https://www.ebay.de',
                'email': 'cssberlin@hotmail.de',
                'logged_in': False,
                'tab_index': None
            },
            'ebay_2': {
                'platform': 'ebay',
                'name': 'eBay 2',
                'url': 'https://www.ebay.de',
                'email': '',  # Ikinci hesap email
                'logged_in': False,
                'tab_index': None
            },
            'kleinanzeigen': {
                'platform': 'kleinanzeigen',
                'name': 'Kleinanzeigen',
                'url': 'https://www.kleinanzeigen.de',
                'email': '',
                'logged_in': False,
                'tab_index': None
            },
            'willhaben': {
                'platform': 'willhaben',
                'name': 'Willhaben',
                'url': 'https://www.willhaben.at',
                'email': '',
                'logged_in': False,
                'tab_index': None
            }
        }
        self.running = True
        self.task_queue = []
        self.current_task = None
        self.upload_results = {'success': [], 'failed': []}
        self.active_account = None  # Aktif hesap

    def send_telegram(self, message):
        """Telegram'a bildirim gonder"""
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            data = {
                'chat_id': TELEGRAM_CHAT_ID,
                'text': f"TATANGA\n\n{message}",
                'parse_mode': 'HTML'
            }
            requests.post(url, data=data, timeout=10)
        except Exception as e:
            self.log(f"Telegram hatasi: {e}")

    def log(self, message, notify=False):
        """Log ve istege bagli Telegram bildirimi"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        try:
            print(f"[{timestamp}] {message}")
        except UnicodeEncodeError:
            safe_msg = message.encode('ascii', 'replace').decode('ascii')
            print(f"[{timestamp}] {safe_msg}")

        if notify:
            self.send_telegram(message)

    def start_browser(self):
        """Tarayiciyi baslat"""
        self.log("Tarayici baslatiliyor...")

        options = Options()
        options.add_argument("--start-maximized")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)

        # Profil dizini - session'lari sakla
        profile_dir = TEMP_DIR / "chrome_profile"
        profile_dir.mkdir(exist_ok=True)
        options.add_argument(f"--user-data-dir={profile_dir}")

        self.driver = webdriver.Chrome(options=options)
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        self.log("Tarayici hazir!")

    def open_all_accounts(self):
        """Tum hesaplari farkli tablarda ac"""
        self.log("Hesaplar aciliyor...")

        # Ilk hesap
        first_account = list(self.accounts.keys())[0]
        self.driver.get(self.accounts[first_account]['url'])
        self.accounts[first_account]['tab_index'] = 0

        # Diger hesaplari yeni tablarda ac
        for i, (account_id, config) in enumerate(list(self.accounts.items())[1:], 1):
            self.driver.execute_script(f"window.open('{config['url']}', '_blank');")
            time.sleep(1)
            config['tab_index'] = i

        # Tablari listele
        self.log(f"{len(self.accounts)} hesap acildi:")
        for account_id, config in self.accounts.items():
            self.log(f"  Tab {config['tab_index']}: {config['name']}")

    def switch_to_account(self, account_id):
        """Belirli bir hesaba gec"""
        if account_id not in self.accounts:
            return False

        tab_index = self.accounts[account_id]['tab_index']
        if tab_index is not None and tab_index < len(self.driver.window_handles):
            self.driver.switch_to.window(self.driver.window_handles[tab_index])
            self.active_account = account_id
            return True
        return False

    def get_vinted_accounts(self):
        """Vinted hesaplarini getir"""
        return {k: v for k, v in self.accounts.items() if v['platform'] == 'vinted'}

    def get_ebay_accounts(self):
        """eBay hesaplarini getir"""
        return {k: v for k, v in self.accounts.items() if v['platform'] == 'ebay'}

    def check_account_login(self, account_id):
        """Hesap login kontrolu"""
        self.switch_to_account(account_id)
        time.sleep(1)

        account = self.accounts[account_id]
        platform = account['platform']

        try:
            if platform == 'vinted':
                user_elements = self.driver.find_elements(By.CSS_SELECTOR,
                    "[data-testid='header--user-menu'], .c-avatar, [href*='/member/']")
                return len(user_elements) > 0
            elif platform == 'ebay':
                return 'signin' not in self.driver.current_url.lower()
            elif platform == 'kleinanzeigen':
                user_elements = self.driver.find_elements(By.CSS_SELECTOR,
                    ".user-profile-link, [class*='user-menu']")
                return len(user_elements) > 0
            elif platform == 'willhaben':
                user_elements = self.driver.find_elements(By.CSS_SELECTOR,
                    "[data-testid='user-menu'], [class*='user']")
                return len(user_elements) > 0
        except:
            pass
        return False

    def wait_for_manual_login(self):
        """Kullanicinin manuel giris yapmasini bekle"""
        print("\n" + "=" * 60)
        print("MANUEL GIRIS GEREKLI - COKLU HESAP")
        print("=" * 60)
        print("\nHesaplar:")
        for account_id, config in self.accounts.items():
            email_info = f" ({config['email']})" if config['email'] else ""
            print(f"  Tab {config['tab_index']}: {config['name']}{email_info}")
        print("\n1. Her taba sirayla gidin")
        print("2. Cookie popup'larini kabul edin")
        print("3. Ilgili hesapla giris yapin")
        print("\nGiris yaptiktan sonra Enter'a basin...")
        print("=" * 60)

        input("\n>>> Tum girisler tamamlandi mi? [Enter] ")

        # Tum hesaplarin login durumunu kontrol et
        status_lines = []
        for account_id, config in self.accounts.items():
            logged_in = self.check_account_login(account_id)
            config['logged_in'] = logged_in
            status = "OK" if logged_in else "GIRIS GEREKLI"
            status_lines.append(f"{config['name']}: {status}")

        self.log("Login durumlari:")
        for line in status_lines:
            self.log(f"  {line}")

        self.send_telegram("Login durumu:\n" + "\n".join(status_lines))
        return True

    def upload_to_vinted(self, product, account_id='vinted_1'):
        """Vinted'e urun yukle - belirli hesaba"""
        self.switch_to_account(account_id)
        time.sleep(1)

        if not self.accounts[account_id]['logged_in']:
            self.log(f"{self.accounts[account_id]['name']}'e giris yapilmamis!", notify=True)
            return False

        title = product.get('title', '')[:50]
        seo = product.get('seo', {}).get('vinted', {})
        vinted_title = seo.get('title', title)
        vinted_desc = seo.get('description', '')
        price = product.get('platform_prices', {}).get('vinted',
                product.get('price', 19.99))
        brand = product.get('analysis', {}).get('brand', 'Sonstiges')

        # Beden cikar
        size_match = re.search(r'Gr\.?\s*(\d+|XS|S|M|L|XL|XXL)', title, re.I)
        size = size_match.group(1) if size_match else 'M'

        try:
            self.log(f"Vinted yukleme: {vinted_title}")

            # Urun sat sayfasina git
            self.driver.get("https://www.vinted.de/items/new")
            time.sleep(3)

            # Resim yukleme alani
            images = product.get('images', [])
            if images:
                # Resim URL'lerini indir ve yukle (ileride eklenecek)
                pass

            # Baslik gir
            try:
                title_input = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR,
                        "input[data-testid='title-input'], input[name='title'], #title"))
                )
                title_input.clear()
                title_input.send_keys(vinted_title)
                self.log(f"  Baslik: {vinted_title}")
                time.sleep(0.5)
            except Exception as e:
                self.log(f"  Baslik hatasi: {e}")

            # Aciklama gir
            try:
                desc_input = self.driver.find_element(By.CSS_SELECTOR,
                    "textarea[data-testid='description-input'], textarea[name='description'], #description")
                desc_input.clear()
                desc_input.send_keys(vinted_desc)
                self.log(f"  Aciklama girildi")
                time.sleep(0.5)
            except Exception as e:
                self.log(f"  Aciklama hatasi: {e}")

            # Kategori sec (butona tikla)
            try:
                cat_btn = self.driver.find_element(By.CSS_SELECTOR,
                    "[data-testid='category-select'], button[class*='category']")
                cat_btn.click()
                time.sleep(1)
                # Kategori secimi... (dinamik)
            except:
                pass

            # Marka gir
            try:
                brand_input = self.driver.find_element(By.CSS_SELECTOR,
                    "input[data-testid='brand-input'], input[name='brand']")
                brand_input.clear()
                brand_input.send_keys(brand)
                time.sleep(1)
                # Otomatik tamamlama sec
                try:
                    suggestion = WebDriverWait(self.driver, 3).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, "[data-testid='brand-suggestion']"))
                    )
                    suggestion.click()
                except:
                    brand_input.send_keys(Keys.ENTER)
                self.log(f"  Marka: {brand}")
            except Exception as e:
                self.log(f"  Marka hatasi: {e}")

            # Beden sec
            try:
                size_btn = self.driver.find_element(By.CSS_SELECTOR,
                    "[data-testid='size-select'], button[class*='size']")
                size_btn.click()
                time.sleep(1)
                # Beden listesinden sec
                size_option = self.driver.find_element(By.XPATH,
                    f"//button[contains(text(), '{size}')] | //span[contains(text(), '{size}')]")
                size_option.click()
                self.log(f"  Beden: {size}")
                time.sleep(0.5)
            except Exception as e:
                self.log(f"  Beden hatasi: {e}")

            # Durum sec (Sehr gut)
            try:
                condition_btn = self.driver.find_element(By.CSS_SELECTOR,
                    "[data-testid='status-select']")
                condition_btn.click()
                time.sleep(1)
                # Sehr gut sec
                sehr_gut = self.driver.find_element(By.XPATH,
                    "//button[contains(text(), 'Sehr gut')] | //span[contains(text(), 'Sehr gut')]")
                sehr_gut.click()
                self.log("  Durum: Sehr gut")
                time.sleep(0.5)
            except Exception as e:
                self.log(f"  Durum hatasi: {e}")

            # Fiyat gir
            try:
                price_input = self.driver.find_element(By.CSS_SELECTOR,
                    "input[data-testid='price-input'], input[name='price']")
                price_input.clear()
                price_input.send_keys(str(price))
                self.log(f"  Fiyat: {price} EUR")
                time.sleep(0.5)
            except Exception as e:
                self.log(f"  Fiyat hatasi: {e}")

            # Yukleme butonu (TIKLANMAYACAK - kullanici onaylar)
            self.log("  Form dolduruldu - KULLANICI ONAY BEKLIYOR")
            self.send_telegram(f"Vinted formu hazir:\n{vinted_title}\n{price} EUR\n\nOnaylamak icin 'Hochladen' tiklayin!")

            return True

        except Exception as e:
            self.log(f"Vinted yukleme hatasi: {e}", notify=True)
            return False

    def process_task(self, task):
        """Bir gorevi isle"""
        task_type = task.get('type')
        platform = task.get('platform')
        account_id = task.get('account', 'vinted_1')
        data = task.get('data')

        self.current_task = task
        account_name = self.accounts.get(account_id, {}).get('name', account_id)
        self.log(f"Gorev isleniyor: {task_type} - {account_name}")

        try:
            if task_type == 'upload':
                if platform == 'vinted':
                    result = self.upload_to_vinted(data, account_id)
                    if result:
                        self.upload_results['success'].append(f"[{account_name}] {data.get('title', 'N/A')}")
                    else:
                        self.upload_results['failed'].append(f"[{account_name}] {data.get('title', 'N/A')}")
                else:
                    result = False
            else:
                result = False

            if result:
                self.log(f"Gorev tamamlandi: {account_name}")
            else:
                self.log(f"Gorev basarisiz: {account_name}", notify=True)

        except Exception as e:
            self.log(f"Gorev hatasi: {e}", notify=True)
            self.upload_results['failed'].append(f"[{account_name}] {data.get('title', 'N/A') if data else 'Unknown'}")

        self.current_task = None

    def add_task(self, task):
        """Gorev kuyruguna ekle"""
        self.task_queue.append(task)
        self.log(f"Gorev eklendi - Kuyrukta: {len(self.task_queue)}")

    def run_task_loop(self):
        """Gorev dongusu - arka planda calisir"""
        while self.running:
            if self.task_queue:
                task = self.task_queue.pop(0)
                self.process_task(task)
                time.sleep(3)  # Her gorev arasinda bekle
            time.sleep(1)

    def load_products(self):
        """Urunleri yukle"""
        products_file = TEMP_DIR / "optimized_products.json"
        if products_file.exists():
            with open(products_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return []

    def show_menu(self):
        """Ana menu - coklu hesap destekli"""
        while self.running:
            print("\n" + "=" * 60)
            print("TATANGA KONTROL MERKEZI - COKLU HESAP")
            print("=" * 60)
            print(f"\nKuyrukta: {len(self.task_queue)} gorev")
            print(f"Basarili: {len(self.upload_results['success'])}")
            print(f"Basarisiz: {len(self.upload_results['failed'])}")
            print("\n--- VINTED ---")
            print("1. Vinted Ana'ya tum urunleri yukle")
            print("2. Vinted 2'ye tum urunleri yukle")
            print("3. Her iki Vinted'e dagit (cift/tek)")
            print("\n--- GENEL ---")
            print("4. Hesap durumlarini kontrol et")
            print("5. Gorev kuyrugunu goster")
            print("6. Telegram test")
            print("7. Belirli hesaba gec (tab)")
            print("0. Cikis")
            print("\n" + "=" * 60)

            choice = input("\nSeciminiz: ").strip()

            if choice == '1':
                products = self.load_products()
                products = [p for p in products if p.get('category') != 'Handy & Telefon']
                for product in products:
                    self.add_task({
                        'type': 'upload',
                        'platform': 'vinted',
                        'account': 'vinted_1',
                        'data': product
                    })
                self.log(f"{len(products)} urun Vinted Ana'ya kuyruga eklendi", notify=True)

            elif choice == '2':
                products = self.load_products()
                products = [p for p in products if p.get('category') != 'Handy & Telefon']
                for product in products:
                    self.add_task({
                        'type': 'upload',
                        'platform': 'vinted',
                        'account': 'vinted_2',
                        'data': product
                    })
                self.log(f"{len(products)} urun Vinted 2'ye kuyruga eklendi", notify=True)

            elif choice == '3':
                products = self.load_products()
                products = [p for p in products if p.get('category') != 'Handy & Telefon']
                for i, product in enumerate(products):
                    account = 'vinted_1' if i % 2 == 0 else 'vinted_2'
                    self.add_task({
                        'type': 'upload',
                        'platform': 'vinted',
                        'account': account,
                        'data': product
                    })
                v1_count = len([p for i, p in enumerate(products) if i % 2 == 0])
                v2_count = len(products) - v1_count
                self.log(f"Urunler dagitildi: Vinted Ana={v1_count}, Vinted 2={v2_count}", notify=True)

            elif choice == '4':
                print("\nHesap Durumlari:")
                for account_id, config in self.accounts.items():
                    logged_in = self.check_account_login(account_id)
                    config['logged_in'] = logged_in
                    status = "OK" if logged_in else "GIRIS GEREKLI"
                    print(f"  {config['name']}: {status}")

            elif choice == '5':
                print(f"\nKuyrukta {len(self.task_queue)} gorev:")
                for i, task in enumerate(self.task_queue[:10]):
                    title = task.get('data', {}).get('title', 'N/A')[:25]
                    account = task.get('account', 'N/A')
                    print(f"  {i+1}. [{account}] {title}...")

            elif choice == '6':
                self.send_telegram("Test mesaji - Kontrol Merkezi calisiyor!")
                print("Telegram mesaji gonderildi")

            elif choice == '7':
                print("\nHesaplar:")
                for i, (account_id, config) in enumerate(self.accounts.items()):
                    print(f"  {i}. {config['name']} (Tab {config['tab_index']})")
                tab_choice = input("Tab numarasi: ").strip()
                try:
                    tab_num = int(tab_choice)
                    account_id = list(self.accounts.keys())[tab_num]
                    self.switch_to_account(account_id)
                    print(f"{self.accounts[account_id]['name']} tabina gecildi")
                except:
                    print("Gecersiz secim")

            elif choice == '0':
                self.running = False
                results_file = TEMP_DIR / "vinted_upload_results.json"
                with open(results_file, 'w', encoding='utf-8') as f:
                    json.dump(self.upload_results, f, indent=2, ensure_ascii=False)
                self.log(f"Sonuclar kaydedildi: {results_file}")
                print("Cikis yapiliyor...")

    def run(self):
        """Ana calistirma"""
        try:
            # Tarayiciyi baslat
            self.start_browser()

            # Tum hesaplari ac
            self.open_all_accounts()

            # Manuel login bekle
            self.wait_for_manual_login()

            # Gorev dongusunu arka planda baslat
            task_thread = threading.Thread(target=self.run_task_loop, daemon=True)
            task_thread.start()

            # Telegram bildir
            self.send_telegram("Kontrol Merkezi baslatildi!\n6 hesap acik:\n- 2x Vinted\n- 2x eBay\n- Kleinanzeigen\n- Willhaben")

            # Menuyu goster
            self.show_menu()

        except KeyboardInterrupt:
            print("\nKapatiliyor...")
        finally:
            if self.driver:
                self.driver.quit()

def main():
    """Ana fonksiyon"""
    center = ControlCenter()
    center.run()

if __name__ == "__main__":
    main()
