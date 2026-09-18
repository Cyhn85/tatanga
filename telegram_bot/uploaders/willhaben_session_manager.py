#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Willhaben Session Manager
Manuel login sonrasi session kaydet, sonra bot ile kullan
"""

import sys
import time
import json
import pickle
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.config.credentials import WILLHABEN

# Dizinler
BASE_DIR = Path(__file__).parent.parent.parent
TEMP_DIR = BASE_DIR / "T6_LISTING_ENGINE" / "temp"
SESSION_DIR = TEMP_DIR / "sessions"
SESSION_DIR.mkdir(parents=True, exist_ok=True)

COOKIES_FILE = SESSION_DIR / "willhaben_cookies.pkl"

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

def save_cookies(driver, filepath=COOKIES_FILE):
    """Cookies'i dosyaya kaydet"""
    cookies = driver.get_cookies()
    with open(filepath, 'wb') as f:
        pickle.dump(cookies, f)
    log(f"Cookies kaydedildi: {filepath}")
    log(f"Toplam {len(cookies)} cookie")

def load_cookies(driver, filepath=COOKIES_FILE):
    """Cookies'i dosyadan yukle"""
    if not filepath.exists():
        log("Cookie dosyasi bulunamadi!")
        return False

    # Once siteye git (domain icin gerekli)
    driver.get("https://www.willhaben.at")
    time.sleep(2)

    with open(filepath, 'rb') as f:
        cookies = pickle.load(f)

    for cookie in cookies:
        try:
            # SameSite problemini coz
            if 'sameSite' in cookie:
                if cookie['sameSite'] == 'None':
                    cookie['sameSite'] = 'Strict'
            driver.add_cookie(cookie)
        except Exception as e:
            pass  # Bazi cookieler eklenemeyebilir

    log(f"Cookies yuklendi: {len(cookies)} adet")
    return True

def check_logged_in(driver):
    """Login durumunu kontrol et"""
    driver.get("https://www.willhaben.at/iad/myprofile")
    time.sleep(3)

    current_url = driver.current_url

    # Login sayfasina yonlendirildiyse login degil
    if 'login' in current_url:
        return False

    # Profil sayfasindaysa login
    if '/myprofile' in current_url or '/iad' in current_url:
        # Kullanici adi var mi kontrol et
        try:
            page_source = driver.page_source
            if 'Ceyhun' in page_source or 'Sorguc' in page_source or 'Mein willhaben' in page_source:
                return True
        except:
            pass

    return False

def manual_login_and_save():
    """
    Manuel login icin browser ac, kullanici login olsun, sonra kaydet
    """
    if not SELENIUM_AVAILABLE:
        return False

    log("=" * 60)
    log("WILLHABEN MANUEL LOGIN")
    log("=" * 60)
    log("")
    log("Browser acilacak. Lutfen:")
    log("1. Willhaben'e manuel olarak login olun")
    log("2. reCAPTCHA'yi cozun")
    log("3. SMS kodunu girin")
    log("4. Login tamamlaninca bu pencereye donun")
    log("")

    options = uc.ChromeOptions()
    options.add_argument('--start-maximized')
    options.add_argument('--lang=de')

    driver = uc.Chrome(options=options)

    try:
        # Login sayfasina git
        driver.get("https://www.willhaben.at/iad/myprofile/login")
        time.sleep(2)

        # Cookie popup kapat
        driver.execute_script("""
            var btns = document.querySelectorAll('button');
            for (var b of btns) {
                var txt = b.textContent.toLowerCase();
                if (txt.includes('akzeptieren') || txt.includes('zustimmen')) {
                    b.click();
                    break;
                }
            }
        """)

        # Email ve sifre otomatik doldur
        account = WILLHABEN['accounts'][0]
        try:
            email_input = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "email"))
            )
            email_input.send_keys(account['email'])

            pwd_input = driver.find_element(By.ID, "password")
            pwd_input.send_keys(account['password'])

            log("Email ve sifre otomatik dolduruldu")
            log("Simdi reCAPTCHA'yi cozun ve login butonuna basin!")
        except:
            log("Form bulunamadi, manuel doldurun")

        # Kullanicinin login olmasini bekle (max 5 dakika)
        log("")
        log("Login bekleniyor... (max 300 saniye)")
        log("reCAPTCHA'yi cozun, SMS kodunu girin!")

        sms_page_detected = False

        for i in range(300):
            time.sleep(1)
            try:
                current_url = driver.current_url

                # SMS dogrulama sayfasinda mi?
                if 'sso.willhaben.at' in current_url:
                    if not sms_page_detected:
                        log("SMS dogrulama sayfasi algilandi!")
                        log("Telefonunuza gelen 4 haneli kodu girin...")
                        sms_page_detected = True
                    continue

                # Login olduysa (profil sayfasina yonlendirildiyse)
                if '/iad' in current_url and 'login' not in current_url:
                    log("Login algilandi!")
                    break

                # Her 30 saniyede bilgi ver
                if i % 30 == 0 and i > 0:
                    log(f"Bekleniyor... {300-i}s kaldi")
            except:
                pass

        time.sleep(3)

        # Login kontrolu
        if check_logged_in(driver):
            log("LOGIN BASARILI!")

            # Cookies kaydet
            save_cookies(driver)

            # Screenshot al
            screenshot_path = TEMP_DIR / "willhaben_logged_in.png"
            driver.save_screenshot(str(screenshot_path))
            log(f"Screenshot: {screenshot_path}")

            return True
        else:
            log("LOGIN BASARISIZ! Tekrar deneyin.")
            return False

    except Exception as e:
        log(f"Hata: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        log("Browser kapatiliyor...")
        driver.quit()

def test_saved_session():
    """Kaydedilmis session'i test et"""
    if not SELENIUM_AVAILABLE:
        return False

    if not COOKIES_FILE.exists():
        log("Kaydedilmis session yok! Once manual_login_and_save() calistirin.")
        return False

    log("=" * 60)
    log("SESSION TEST")
    log("=" * 60)

    options = uc.ChromeOptions()
    options.add_argument('--start-maximized')
    options.add_argument('--lang=de')

    driver = uc.Chrome(options=options)

    try:
        # Cookies yukle
        load_cookies(driver)

        # Sayfayi yenile
        driver.refresh()
        time.sleep(3)

        # Login kontrolu
        if check_logged_in(driver):
            log("SESSION GECERLI - Login aktif!")

            # Profil sayfasina git
            driver.get("https://www.willhaben.at/iad/myprofile/myads")
            time.sleep(3)

            # Screenshot al
            screenshot_path = TEMP_DIR / "willhaben_session_test.png"
            driver.save_screenshot(str(screenshot_path))
            log(f"Screenshot: {screenshot_path}")

            return True
        else:
            log("SESSION GECERSIZ - Yeniden login gerekli!")
            return False

    except Exception as e:
        log(f"Hata: {e}")
        return False

    finally:
        driver.quit()

class WillhabenSessionUploader:
    """Session kullanarak urun yukleme"""

    def __init__(self):
        self.driver = None
        self.logged_in = False

    def init_with_session(self):
        """Session ile baslat"""
        if not SELENIUM_AVAILABLE:
            return False

        if not COOKIES_FILE.exists():
            log("Session dosyasi yok! Once manuel login yapin.")
            return False

        options = uc.ChromeOptions()
        options.add_argument('--start-maximized')
        options.add_argument('--lang=de')

        self.driver = uc.Chrome(options=options)

        # Cookies yukle
        load_cookies(self.driver)
        self.driver.refresh()
        time.sleep(3)

        # Login kontrolu
        if check_logged_in(self.driver):
            log("Session ile login basarili!")
            self.logged_in = True
            return True
        else:
            log("Session gecersiz!")
            return False

    def upload_product(self, product):
        """Urun yukle"""
        if not self.logged_in:
            log("Login yapilmamis!")
            return False

        title = product.get('seo', {}).get('willhaben', {}).get('title', product.get('title', ''))[:50]
        description = product.get('seo', {}).get('willhaben', {}).get('description', product.get('description', ''))
        price = product.get('platform_prices', {}).get('willhaben', product.get('price', 0))
        images = product.get('local_images', [])
        category = product.get('category', '')

        log(f"Urun yukleniyor: {title}")

        try:
            # Yeni ilan sayfasina git
            self.driver.get("https://www.willhaben.at/iad/object/insert")
            time.sleep(3)

            # Kostenlose Anzeige sec
            try:
                free_btn = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH,
                        "//button[contains(text(), 'Kostenlos')] | //a[contains(text(), 'Kostenlos')]"
                    ))
                )
                free_btn.click()
                log("Kostenlose Anzeige secildi")
                time.sleep(2)
            except:
                log("Kostenlos butonu bulunamadi, devam ediliyor...")

            # Kategori secimi
            # Willhaben kategorileri: Marktplatz > Mode & Accessoires
            try:
                # Marktplatz
                marktplatz = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH,
                        "//span[contains(text(), 'Marktplatz')] | //button[contains(text(), 'Marktplatz')]"
                    ))
                )
                marktplatz.click()
                time.sleep(1)

                # Mode & Accessoires
                if 'mode' in category.lower() or 'herren' in category.lower() or 'damen' in category.lower():
                    mode = self.driver.find_element(By.XPATH,
                        "//span[contains(text(), 'Mode')] | //button[contains(text(), 'Mode')]"
                    )
                    mode.click()
                    time.sleep(1)

                    # Alt kategori (Herrenbekleidung, Damenbekleidung, etc.)
                    if 'herren' in category.lower():
                        subcat = self.driver.find_element(By.XPATH, "//span[contains(text(), 'Herren')]")
                        subcat.click()
                    elif 'damen' in category.lower():
                        subcat = self.driver.find_element(By.XPATH, "//span[contains(text(), 'Damen')]")
                        subcat.click()
                    time.sleep(1)

                log("Kategori secildi")
            except Exception as e:
                log(f"Kategori secimi hatasi: {e}")

            # Baslik
            try:
                title_input = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR,
                        "input[name='title'], input[id*='title'], input[data-testid='title']"
                    ))
                )
                title_input.clear()
                title_input.send_keys(title)
                log(f"Baslik: {title}")
            except Exception as e:
                log(f"Baslik hatasi: {e}")

            # Aciklama
            try:
                desc_input = self.driver.find_element(By.CSS_SELECTOR,
                    "textarea[name='description'], textarea[id*='description'], textarea[data-testid='description']"
                )
                desc_input.clear()
                desc_input.send_keys(description[:800])  # Max 800 karakter
                log("Aciklama girildi")
            except Exception as e:
                log(f"Aciklama hatasi: {e}")

            # Fiyat
            try:
                price_input = self.driver.find_element(By.CSS_SELECTOR,
                    "input[name='price'], input[id*='price'], input[data-testid='price']"
                )
                price_input.clear()
                price_input.send_keys(str(int(price)))
                log(f"Fiyat: {price} EUR")
            except Exception as e:
                log(f"Fiyat hatasi: {e}")

            # Resimler
            if images:
                try:
                    file_inputs = self.driver.find_elements(By.CSS_SELECTOR, "input[type='file']")
                    if file_inputs:
                        # Tum resimleri yukle
                        for i, img_path in enumerate(images[:10]):  # Max 10 resim
                            if Path(img_path).exists():
                                file_inputs[0].send_keys(str(img_path))
                                log(f"Resim {i+1} yuklendi: {Path(img_path).name}")
                                time.sleep(2)
                except Exception as e:
                    log(f"Resim yukleme hatasi: {e}")

            # Konum (Berlin -> Avusturya icin Wien varsayilan)
            try:
                location_input = self.driver.find_element(By.CSS_SELECTOR,
                    "input[name='location'], input[id*='location'], input[placeholder*='PLZ']"
                )
                location_input.clear()
                location_input.send_keys("1010")  # Wien merkez
                time.sleep(1)
                # Dropdown'dan sec
                location_input.send_keys(Keys.ARROW_DOWN)
                location_input.send_keys(Keys.ENTER)
                log("Konum: 1010 Wien")
            except Exception as e:
                log(f"Konum hatasi: {e}")

            # Screenshot al
            screenshot_path = TEMP_DIR / f"willhaben_upload_{int(time.time())}.png"
            self.driver.save_screenshot(str(screenshot_path))
            log(f"Form screenshot: {screenshot_path}")

            # Form gonder (simdilik manuel onay icin bekle)
            log("")
            log("Form dolduruldu. Kontrol edip 'Anzeige aufgeben' butonuna basin.")
            log("Devam etmek icin ENTER'a basin...")

            return True

        except Exception as e:
            log(f"Upload hatasi: {e}")
            import traceback
            traceback.print_exc()
            return False

    def close(self):
        if self.driver:
            self.driver.quit()

def main():
    """Ana menu"""
    print("=" * 60)
    print("WILLHABEN SESSION MANAGER")
    print("=" * 60)
    print("")
    print("1. Manuel login ve session kaydet")
    print("2. Kaydedilmis session'i test et")
    print("3. Test urun yukle")
    print("0. Cikis")
    print("")

    choice = input("Seciminiz: ").strip()

    if choice == "1":
        manual_login_and_save()

    elif choice == "2":
        test_saved_session()

    elif choice == "3":
        uploader = WillhabenSessionUploader()
        if uploader.init_with_session():
            # Test urun
            test_product = {
                'title': 'Test Urun - Herren Shirt',
                'description': 'Bu bir test urunudur. Cok iyi durumda.',
                'category': 'Herrenmode',
                'seo': {
                    'willhaben': {
                        'title': 'Herren Shirt Gr. L',
                        'description': 'Herren T-Shirt in sehr gutem Zustand. Groesse L, Farbe Blau. Versand moeglich.'
                    }
                },
                'platform_prices': {
                    'willhaben': 25
                },
                'local_images': []
            }

            uploader.upload_product(test_product)
            input("\nDevam etmek icin ENTER...")

        uploader.close()

    else:
        print("Cikis...")

if __name__ == "__main__":
    main()
