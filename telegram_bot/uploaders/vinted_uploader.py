#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vinted.de Uploader
Selenium ile urun yukleme
"""

import sys
import time
import pickle
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.config.credentials import VINTED

# Dizinler
BASE_DIR = Path(__file__).parent.parent.parent
TEMP_DIR = BASE_DIR / "T6_LISTING_ENGINE" / "temp"
SESSION_DIR = TEMP_DIR / "sessions"
SESSION_DIR.mkdir(parents=True, exist_ok=True)

COOKIES_FILE = SESSION_DIR / "vinted_cookies.pkl"

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
    print("Selenium yuklu degil!")

def log(message):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}", flush=True)

class VintedUploader:
    """Vinted.de urun yukleme"""

    def __init__(self):
        self.driver = None
        self.logged_in = False

    def init_driver(self):
        """Driver baslat"""
        if not SELENIUM_AVAILABLE:
            return False

        options = uc.ChromeOptions()
        options.add_argument('--start-maximized')
        options.add_argument('--lang=de')

        self.driver = uc.Chrome(options=options)
        return True

    def save_cookies(self):
        """Cookies kaydet"""
        if not self.driver:
            return
        cookies = self.driver.get_cookies()
        with open(COOKIES_FILE, 'wb') as f:
            pickle.dump(cookies, f)
        log(f"Cookies kaydedildi: {COOKIES_FILE}")

    def load_cookies(self):
        """Cookies yukle"""
        if not COOKIES_FILE.exists():
            log("Cookie dosyasi bulunamadi!")
            return False

        # Once siteye git
        self.driver.get("https://www.vinted.de")
        time.sleep(2)

        with open(COOKIES_FILE, 'rb') as f:
            cookies = pickle.load(f)

        for cookie in cookies:
            try:
                if 'sameSite' in cookie:
                    if cookie['sameSite'] == 'None':
                        cookie['sameSite'] = 'Strict'
                self.driver.add_cookie(cookie)
            except:
                pass

        log(f"Cookies yuklendi: {len(cookies)} adet")
        return True

    def login(self, account):
        """Manuel login - kullanici Artikel verkaufen tiklayana kadar bekle"""
        log("Vinted login basliyor...")
        log("")
        log("=" * 50)
        log("MANUEL LOGIN MODU")
        log("=" * 50)
        log("")
        log("1. Vinted.de acilacak")
        log("2. Cookie popup'i KABUL ET")
        log("3. 'Artikel verkaufen' butonuna TIKLA")
        log("4. Login popup acilinca sistem devralacak")
        log("")
        log("Bekleniyor...")

        # Ana sayfaya git
        self.driver.get("https://www.vinted.de")
        time.sleep(3)

        # Login popup'inin acilmasini bekle (max 120 saniye)
        # Kullanici Artikel verkaufen'e tikladiginda popup acilir
        popup_found = False
        for i in range(120):
            time.sleep(1)
            try:
                # E-Mail butonu veya email input gorunuyor mu?
                elements = self.driver.find_elements(By.XPATH,
                    "//*[contains(text(), 'E-Mail')] | //input[@type='email'] | //input[@name='email']"
                )
                for elem in elements:
                    if elem.is_displayed():
                        popup_found = True
                        log("Login popup algilandi!")
                        break
                if popup_found:
                    break

                if i % 15 == 0 and i > 0:
                    log(f"Popup bekleniyor... {120-i}s kaldi")
            except:
                pass

        if not popup_found:
            log("Login popup bulunamadi!")
            return False

        time.sleep(2)

        # Weiter mit E-Mail tikla
        try:
            email_login = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH,
                    "//button[contains(text(), 'E-Mail')] | //span[contains(text(), 'E-Mail')] | //*[contains(text(), 'Weiter mit E-Mail')] | //button[@data-testid='auth--form--email-toggle']"
                ))
            )
            email_login.click()
            log("E-Mail ile devam secildi")
            time.sleep(2)
        except:
            log("E-Mail butonu bulunamadi, direkt form araniyor...")

        # Email gir
        try:
            email_input = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR,
                    "input[data-testid='auth-email-input'], input[type='email'], input[name='email']"
                ))
            )
            email_input.clear()
            email_input.send_keys(account['email'])
            log(f"Email: {account['email']}")
            time.sleep(1)
        except Exception as e:
            log(f"Email input hatasi: {e}")
            return False

        # Sifre gir
        try:
            pwd_input = self.driver.find_element(By.CSS_SELECTOR,
                "input[data-testid='auth-password-input'], input[type='password'], input[name='password']"
            )
            pwd_input.clear()
            pwd_input.send_keys(account['password'])
            log("Sifre girildi")
            time.sleep(1)
        except Exception as e:
            log(f"Sifre input hatasi: {e}")
            return False

        # Login butonu
        try:
            submit_btn = self.driver.find_element(By.CSS_SELECTOR,
                "button[type='submit'], button[data-testid='auth-submit-button']"
            )
            submit_btn.click()
            log("Login butonu tiklandi")
            time.sleep(5)
        except Exception as e:
            log(f"Submit butonu hatasi: {e}")
            return False

        # Login kontrolu
        if self.check_logged_in():
            self.logged_in = True
            self.save_cookies()
            log("LOGIN BASARILI!")
            return True
        else:
            log("LOGIN BASARISIZ!")
            return False

    def check_logged_in(self):
        """Login durumu kontrol"""
        try:
            # Profil ikonu veya kullanici adi var mi
            self.driver.find_element(By.CSS_SELECTOR,
                "[data-testid='header-user-menu'], .c-avatar, .user-menu"
            )
            return True
        except:
            return False

    def login_with_session(self):
        """Kaydedilmis session ile login"""
        if not COOKIES_FILE.exists():
            log("Session yok!")
            return False

        if not self.init_driver():
            return False

        self.load_cookies()
        self.driver.refresh()
        time.sleep(3)

        if self.check_logged_in():
            self.logged_in = True
            log("Session ile login basarili!")
            return True
        else:
            log("Session gecersiz!")
            return False

    def upload_product(self, product):
        """Urun yukle"""
        if not self.logged_in:
            log("Login yapilmamis!")
            return False

        title = product.get('seo', {}).get('vinted', {}).get('title', product.get('title', ''))[:40]
        description = product.get('seo', {}).get('vinted', {}).get('description', product.get('description', ''))
        price = product.get('platform_prices', {}).get('vinted', product.get('price', 0))
        images = product.get('local_images', [])
        brand = product.get('brand', '')
        size = product.get('size', 'L')
        condition = product.get('condition', 'Sehr gut')

        log(f"Urun yukleniyor: {title}")

        try:
            # Yeni ilan sayfasina git
            self.driver.get("https://www.vinted.de/items/new")
            time.sleep(5)

            # Resim yukle
            if images:
                file_inputs = self.driver.find_elements(By.CSS_SELECTOR, "input[type='file']")
                if file_inputs:
                    for i, img_path in enumerate(images[:20]):
                        if Path(img_path).exists():
                            file_inputs[0].send_keys(str(img_path))
                            log(f"Resim {i+1} yuklendi")
                            time.sleep(2)

            # Baslik
            try:
                title_input = self.driver.find_element(By.CSS_SELECTOR,
                    "input[data-testid='item-form-title-input'], input[name='title']"
                )
                title_input.clear()
                title_input.send_keys(title)
                log(f"Baslik: {title}")
            except:
                pass

            # Aciklama
            try:
                desc_input = self.driver.find_element(By.CSS_SELECTOR,
                    "textarea[data-testid='item-form-description-input'], textarea[name='description']"
                )
                desc_input.clear()
                desc_input.send_keys(description[:2000])
                log("Aciklama girildi")
            except:
                pass

            # Kategori secimi - Click ile
            try:
                category_btn = self.driver.find_element(By.CSS_SELECTOR,
                    "[data-testid='item-form-category-button'], button[contains(text(), 'Kategorie')]"
                )
                category_btn.click()
                time.sleep(1)
                # Herren > Kleidung > ...
                # Bu kisim manuel yapilmali veya daha detayli selector gerekli
            except:
                pass

            # Marka
            try:
                brand_input = self.driver.find_element(By.CSS_SELECTOR,
                    "[data-testid='item-form-brand-input'], input[name='brand']"
                )
                brand_input.clear()
                brand_input.send_keys(brand)
                time.sleep(1)
                brand_input.send_keys(Keys.ARROW_DOWN)
                brand_input.send_keys(Keys.ENTER)
                log(f"Marka: {brand}")
            except:
                pass

            # Beden
            try:
                size_btn = self.driver.find_element(By.CSS_SELECTOR,
                    "[data-testid='item-form-size-button'], button[contains(text(), 'Groesse')]"
                )
                size_btn.click()
                time.sleep(1)
            except:
                pass

            # Fiyat
            try:
                price_input = self.driver.find_element(By.CSS_SELECTOR,
                    "input[data-testid='item-form-price-input'], input[name='price']"
                )
                price_input.clear()
                price_input.send_keys(str(int(price)))
                log(f"Fiyat: {price} EUR")
            except:
                pass

            # Screenshot al
            screenshot_path = TEMP_DIR / f"vinted_upload_{int(time.time())}.png"
            self.driver.save_screenshot(str(screenshot_path))
            log(f"Form screenshot: {screenshot_path}")

            # Simdilik submit yapma, manuel kontrol icin bekle
            log("Form dolduruldu. 'Artikel hochladen' butonuna tiklayin.")

            return True

        except Exception as e:
            log(f"Upload hatasi: {e}")
            import traceback
            traceback.print_exc()
            return False

    def close(self):
        if self.driver:
            self.driver.quit()

def manual_login():
    """Manuel login ve session kaydet"""
    uploader = VintedUploader()
    if not uploader.init_driver():
        return False

    account = VINTED['accounts'][0]
    success = uploader.login(account)

    if success:
        log("Session kaydedildi!")

    time.sleep(5)
    uploader.close()
    return success

def test_session():
    """Kaydedilmis session test"""
    uploader = VintedUploader()
    success = uploader.login_with_session()

    if success:
        # Profil sayfasina git
        uploader.driver.get("https://www.vinted.de/member/self/items")
        time.sleep(3)
        screenshot_path = TEMP_DIR / "vinted_session_test.png"
        uploader.driver.save_screenshot(str(screenshot_path))
        log(f"Screenshot: {screenshot_path}")

    time.sleep(5)
    uploader.close()
    return success

def test_upload():
    """Test urun yukle"""
    uploader = VintedUploader()
    if not uploader.login_with_session():
        log("Session gecersiz, manuel login yapiliyor...")
        if not uploader.init_driver():
            return
        account = VINTED['accounts'][0]
        if not uploader.login(account):
            uploader.close()
            return

    # Test urun
    test_product = {
        'title': 'Test Herren T-Shirt L',
        'description': 'Herren T-Shirt in sehr gutem Zustand. Groesse L, Farbe Blau.',
        'seo': {
            'vinted': {
                'title': 'Tommy Hilfiger T-Shirt L',
                'description': 'Biete hier ein sehr gut erhaltenes Tommy Hilfiger T-Shirt an. Groesse L, Farbe Blau. Tierfreier Nichtraucherhaushalt.'
            }
        },
        'platform_prices': {
            'vinted': 25
        },
        'brand': 'Tommy Hilfiger',
        'size': 'L',
        'condition': 'Sehr gut',
        'local_images': []
    }

    uploader.upload_product(test_product)
    input("\nDevam etmek icin ENTER...")
    uploader.close()

def main():
    """Ana menu"""
    print("=" * 60)
    print("VINTED.DE UPLOADER")
    print("=" * 60)
    print()
    print("1. Login ve session kaydet")
    print("2. Session test")
    print("3. Test urun yukle")
    print("0. Cikis")
    print()

    choice = input("Seciminiz: ").strip()

    if choice == "1":
        manual_login()
    elif choice == "2":
        test_session()
    elif choice == "3":
        test_upload()
    else:
        print("Cikis...")

if __name__ == "__main__":
    main()
