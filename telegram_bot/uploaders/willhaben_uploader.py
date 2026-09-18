#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Willhaben.at Uploader
SMS dogrulama destegi ile
"""

import sys
import time
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.config.credentials import WILLHABEN

# Dizinler
BASE_DIR = Path(__file__).parent.parent.parent
TEMP_DIR = BASE_DIR / "T6_LISTING_ENGINE" / "temp"
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

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

class WillhabenUploader:
    def __init__(self):
        self.driver = None
        self.logged_in = False
        self.log_file = LOG_DIR / "willhaben_upload.log"

    def log(self, message, level="INFO"):
        """Log mesaji yaz"""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"[{timestamp}] [{level}] {message}"
        print(log_msg, flush=True)

        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(log_msg + "\n")

    def init_driver(self):
        """Chrome driver baslat"""
        if not SELENIUM_AVAILABLE:
            return False

        options = uc.ChromeOptions()
        options.add_argument('--start-maximized')
        options.add_argument('--lang=de')

        self.driver = uc.Chrome(options=options)
        self.log("Chrome baslatildi")
        return True

    def login(self, sms_code_callback=None):
        """
        Willhaben'e login ol
        sms_code_callback: SMS kodu almak icin fonksiyon (None ise input() kullanir)
        """
        self.log("Willhaben login basliyor...")

        account = WILLHABEN['accounts'][0]
        email = account['email']
        password = account['password']

        # Ana sayfaya git
        self.driver.get("https://www.willhaben.at/iad")
        time.sleep(3)

        # Cookie popup kapat
        self._close_popups()

        # Einloggen linkine tikla (sag ust)
        try:
            # Ceyhun Sorguc profil linki veya Einloggen linki
            einloggen = self.driver.find_element(By.XPATH,
                "//a[contains(@href, 'login')] | //span[contains(text(), 'Einloggen')] | //button[contains(text(), 'Einloggen')]"
            )
            einloggen.click()
            self.log("Einloggen tiklandi")
            time.sleep(3)
        except:
            self.log("Einloggen bulunamadi, direkt login URL'sine gidiliyor")
            self.driver.get("https://www.willhaben.at/iad/myprofile/login")
            time.sleep(3)

        try:
            # Email gir
            email_input = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "email"))
            )
            email_input.clear()
            email_input.send_keys(email)
            self.log(f"Email girildi: {email}")

            # Password gir
            pwd_input = self.driver.find_element(By.ID, "password")
            pwd_input.clear()
            pwd_input.send_keys(password)
            self.log("Sifre girildi")

            # Login butonu
            login_btn = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
            login_btn.click()
            self.log("Login butonu tiklandi")
            time.sleep(5)

            # SMS dogrulama kontrolu
            if self._check_sms_verification():
                self.log("SMS dogrulama gerekli!")

                # Kod al
                if sms_code_callback:
                    code = sms_code_callback()
                else:
                    code = input("SMS kodunu girin (4 haneli): ").strip()

                if code and len(code) == 4:
                    self._enter_sms_code(code)
                else:
                    self.log("Gecersiz kod!", "ERROR")
                    return False

            # Login basarili mi kontrol et
            time.sleep(3)
            if self._check_logged_in():
                self.logged_in = True
                self.log("Login BASARILI!")
                return True
            else:
                self.log("Login BASARISIZ!", "ERROR")
                return False

        except Exception as e:
            self.log(f"Login hatasi: {e}", "ERROR")
            self._save_screenshot("login_error")
            return False

    def _check_sms_verification(self):
        """SMS dogrulama sayfasi mi kontrol et"""
        try:
            # URL kontrolu - sso.willhaben.at
            current_url = self.driver.current_url
            if 'sso.willhaben.at' in current_url:
                self.log("SSO sayfasinda - SMS dogrulama gerekli")
                return True

            # Sayfa icerigi kontrolu
            page_source = self.driver.page_source.lower()
            if 'verifizierung' in page_source or 'sms' in page_source or '4-stelligen code' in page_source:
                return True

            # Input kutulari var mi (4 adet tek haneli)
            inputs = self.driver.find_elements(By.CSS_SELECTOR, "input[maxlength='1'], input[type='tel']")
            if len(inputs) >= 4:
                return True

            return False
        except Exception as e:
            self.log(f"SMS kontrol hatasi: {e}", "WARNING")
            return False

    def _enter_sms_code(self, code):
        """SMS kodunu gir"""
        self.log(f"SMS kodu giriliyor: {code}")

        try:
            # 4 ayri input kutusu
            inputs = self.driver.find_elements(By.CSS_SELECTOR, "input[maxlength='1']")

            if len(inputs) >= 4:
                for i, digit in enumerate(code[:4]):
                    inputs[i].clear()
                    inputs[i].send_keys(digit)
                    time.sleep(0.2)

                self.log("SMS kodu girildi")

                # Weiter butonu
                time.sleep(1)
                try:
                    btn = self.driver.find_element(By.XPATH, "//button[contains(text(), 'Weiter')]")
                    btn.click()
                    self.log("Weiter butonu tiklandi")
                except:
                    # Enter tusu ile devam
                    inputs[3].send_keys(Keys.ENTER)

                time.sleep(5)
                return True
            else:
                self.log("SMS input kutulari bulunamadi", "ERROR")
                return False

        except Exception as e:
            self.log(f"SMS kod girisi hatasi: {e}", "ERROR")
            return False

    def _check_logged_in(self):
        """Login basarili mi kontrol et"""
        try:
            # Profil elementi var mi
            self.driver.find_element(By.CSS_SELECTOR, "[data-testid='user-menu'], .user-menu, [class*='profile']")
            return True
        except:
            pass

        # URL kontrolu
        current_url = self.driver.current_url
        if '/iad' in current_url and 'login' not in current_url:
            return True

        return False

    def _close_popups(self):
        """Popup'lari kapat"""
        for _ in range(3):
            try:
                self.driver.execute_script("""
                    var btns = document.querySelectorAll('button');
                    for (var b of btns) {
                        var txt = b.textContent.toLowerCase();
                        if (txt.includes('akzeptieren') || txt.includes('zustimmen')) {
                            b.click();
                            return true;
                        }
                    }
                    return false;
                """)
                time.sleep(0.5)
            except:
                pass

    def _save_screenshot(self, name):
        """Screenshot kaydet"""
        try:
            path = TEMP_DIR / f"willhaben_{name}.png"
            self.driver.save_screenshot(str(path))
            self.log(f"Screenshot: {path}")
        except:
            pass

    def upload_product(self, product):
        """Tek urun yukle"""
        if not self.logged_in:
            self.log("Login yapilmamis!", "ERROR")
            return False

        title = product.get('seo', {}).get('willhaben', {}).get('title', product.get('title', ''))[:50]
        description = product.get('seo', {}).get('willhaben', {}).get('description', '')
        price = product.get('platform_prices', {}).get('willhaben', 0)
        images = product.get('image_variants', product.get('local_images', []))

        self.log(f"Urun yukleniyor: {title}")

        try:
            # Yeni ilan sayfasina git
            self.driver.get("https://www.willhaben.at/iad/object/insert")
            time.sleep(3)

            # Kostenlose Anzeige aufgeben butonu
            try:
                free_btn = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Kostenlose Anzeige')]"))
                )
                free_btn.click()
                self.log("Kostenlose Anzeige secildi")
                time.sleep(2)
            except:
                self.log("Kostenlose Anzeige butonu bulunamadi", "WARNING")

            # Kategori secimi
            # TODO: Kategori mapping eklenecek

            # Baslik
            try:
                title_input = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "input[name='title'], input[id*='title']"))
                )
                title_input.clear()
                title_input.send_keys(title)
                self.log(f"Baslik girildi: {title}")
            except Exception as e:
                self.log(f"Baslik girisi hatasi: {e}", "ERROR")

            # Aciklama
            try:
                desc_input = self.driver.find_element(By.CSS_SELECTOR, "textarea[name='description'], textarea[id*='description']")
                desc_input.clear()
                desc_input.send_keys(description)
                self.log("Aciklama girildi")
            except Exception as e:
                self.log(f"Aciklama girisi hatasi: {e}", "ERROR")

            # Fiyat
            try:
                price_input = self.driver.find_element(By.CSS_SELECTOR, "input[name='price'], input[id*='price']")
                price_input.clear()
                price_input.send_keys(str(int(price)))
                self.log(f"Fiyat girildi: {price} EUR")
            except Exception as e:
                self.log(f"Fiyat girisi hatasi: {e}", "ERROR")

            # Resim yukleme
            if images:
                try:
                    file_input = self.driver.find_element(By.CSS_SELECTOR, "input[type='file']")
                    # Ilk resmi yukle
                    file_input.send_keys(images[0])
                    self.log(f"Resim yuklendi: {images[0]}")
                    time.sleep(3)
                except Exception as e:
                    self.log(f"Resim yukleme hatasi: {e}", "ERROR")

            self._save_screenshot("upload_form")
            self.log("Form dolduruldu - Manuel kontrol gerekiyor")

            # NOT: Form submit otomatik yapilmiyor, manuel kontrol icin
            return True

        except Exception as e:
            self.log(f"Upload hatasi: {e}", "ERROR")
            self._save_screenshot("upload_error")
            return False

    def close(self):
        """Driver'i kapat"""
        if self.driver:
            try:
                self.driver.quit()
                self.log("Chrome kapatildi")
            except:
                pass

def main():
    """Test fonksiyonu"""
    print("=" * 60)
    print("WILLHABEN UPLOADER TEST")
    print("=" * 60)

    uploader = WillhabenUploader()

    if not uploader.init_driver():
        return

    try:
        # Login
        if uploader.login():
            # Test urun
            test_product = {
                'title': 'Test Urun',
                'seo': {
                    'willhaben': {
                        'title': 'Test Urun',
                        'description': 'Bu bir test urunudur.'
                    }
                },
                'platform_prices': {
                    'willhaben': 25
                },
                'image_variants': []
            }

            uploader.upload_product(test_product)

            input("\nDevam etmek icin ENTER'a basin...")

    finally:
        uploader.close()

if __name__ == "__main__":
    main()
