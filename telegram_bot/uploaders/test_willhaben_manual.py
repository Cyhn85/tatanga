#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Willhaben Manuel Test - Komut satirindan SMS kodu ile
Kullanim: python test_willhaben_manual.py [sms_code]
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.config.credentials import WILLHABEN

# Dizinler
BASE_DIR = Path(__file__).parent.parent.parent
TEMP_DIR = BASE_DIR / "T6_LISTING_ENGINE" / "temp"
LOG_DIR = BASE_DIR / "logs"

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.common.keys import Keys
    import undetected_chromedriver as uc
except ImportError:
    print("Selenium yuklu degil!")
    sys.exit(1)

def log(message):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}", flush=True)

def main():
    # Komut satiri argumani varsa SMS kodu olarak kullan
    sms_code = None
    if len(sys.argv) > 1:
        sms_code = sys.argv[1]
        log(f"SMS kodu argumandan alindi: {sms_code}")

    # Chrome baslat
    options = uc.ChromeOptions()
    options.add_argument('--start-maximized')
    options.add_argument('--lang=de')
    driver = uc.Chrome(options=options)

    log("Chrome baslatildi")

    try:
        account = WILLHABEN['accounts'][0]

        # Ana sayfaya git
        driver.get("https://www.willhaben.at/iad")
        time.sleep(3)

        # Popup kapat
        driver.execute_script("""
            var btns = document.querySelectorAll('button');
            for (var b of btns) {
                var txt = b.textContent.toLowerCase();
                if (txt.includes('akzeptieren') || txt.includes('zustimmen')) {
                    b.click();
                    return;
                }
            }
        """)
        time.sleep(1)

        # Einloggen
        try:
            einloggen = driver.find_element(By.XPATH,
                "//a[contains(@href, 'login')] | //span[contains(text(), 'Einloggen')]"
            )
            einloggen.click()
            log("Einloggen tiklandi")
            time.sleep(3)
        except:
            driver.get("https://www.willhaben.at/iad/myprofile/login")
            time.sleep(3)

        # Email ve sifre
        email_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "email"))
        )
        email_input.send_keys(account['email'])
        log(f"Email: {account['email']}")

        pwd_input = driver.find_element(By.ID, "password")
        pwd_input.send_keys(account['password'])
        log("Sifre girildi")

        # reCAPTCHA checkbox'i tikla - "Ich bin kein Roboter"
        log("reCAPTCHA araniyor...")
        time.sleep(2)

        recaptcha_clicked = False
        try:
            # iframe icindeki recaptcha
            frames = driver.find_elements(By.TAG_NAME, "iframe")
            log(f"Toplam {len(frames)} iframe bulundu")

            for i, frame in enumerate(frames):
                try:
                    src = frame.get_attribute('src') or ''
                    title = frame.get_attribute('title') or ''

                    if 'recaptcha' in src.lower() or 'recaptcha' in title.lower():
                        log(f"reCAPTCHA iframe bulundu (index {i})")

                        # iframe'e geç
                        driver.switch_to.frame(frame)
                        time.sleep(1)

                        # Checkbox'i bul ve tikla
                        try:
                            checkbox = WebDriverWait(driver, 10).until(
                                EC.element_to_be_clickable((By.CSS_SELECTOR, ".recaptcha-checkbox-border, .recaptcha-checkbox, #recaptcha-anchor, span[role='checkbox']"))
                            )

                            # JavaScript ile tikla (daha guvenilir)
                            driver.execute_script("arguments[0].click();", checkbox)
                            log("reCAPTCHA checkbox tiklandi!")
                            recaptcha_clicked = True

                        except Exception as e:
                            log(f"Checkbox tiklama hatasi: {e}")

                        driver.switch_to.default_content()
                        time.sleep(3)
                        break

                except Exception as e:
                    continue

            if not recaptcha_clicked:
                # Alternatif: direkt JavaScript ile bul
                log("Alternatif yontem deneniyor...")
                result = driver.execute_script("""
                    var frames = document.querySelectorAll('iframe');
                    for (var f of frames) {
                        if (f.src && f.src.includes('recaptcha')) {
                            return f.src;
                        }
                    }
                    return null;
                """)
                if result:
                    log(f"reCAPTCHA iframe src: {result[:50]}...")
                else:
                    log("reCAPTCHA iframe bulunamadi")

        except Exception as e:
            log(f"reCAPTCHA hatasi: {e}")
            driver.switch_to.default_content()

        # reCAPTCHA tiklandiktan sonra bekle
        if recaptcha_clicked:
            log("reCAPTCHA dogrulamasi bekleniyor...")
            # Challenge varsa cozulmesini bekle (max 60 saniye)
            for i in range(60):
                time.sleep(1)
                try:
                    challenge_frames = driver.find_elements(By.CSS_SELECTOR, "iframe[title*='reCAPTCHA-Aufgabe'], iframe[title*='recaptcha challenge']")
                    visible_challenges = [f for f in challenge_frames if f.is_displayed()]
                    if not visible_challenges:
                        log("reCAPTCHA challenge tamamlandi")
                        break
                    if i % 10 == 0:
                        log(f"Challenge bekleniyor... {60-i}s - LUTFEN COZUN!")
                except:
                    break
            time.sleep(2)

        # Login butonu - JavaScript ile tikla
        login_btn = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
        driver.execute_script("arguments[0].click();", login_btn)
        log("Login butonu tiklandi")
        time.sleep(5)

        # SMS dogrulama kontrolu
        current_url = driver.current_url
        if 'sso.willhaben.at' in current_url:
            log("SMS dogrulama sayfasinda!")

            # Kod yoksa ekran acik kalsin
            if not sms_code:
                log("SMS kodu bekleniyor...")
                log("Telegram'dan kodu alip scripti yeniden calistirin:")
                log(f"  python test_willhaben_manual.py XXXX")

                # 60 saniye bekle
                for i in range(60):
                    time.sleep(1)
                    if i % 10 == 0:
                        log(f"Bekleniyor... {60-i} saniye")
                return

            # Sayfa yuklenmesini bekle
            time.sleep(3)

            # HTML kaydet (debug icin)
            html_path = TEMP_DIR / "willhaben_sms_page.html"
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(driver.page_source)
            log(f"SMS sayfasi HTML: {html_path}")

            # Screenshot al
            driver.save_screenshot(str(TEMP_DIR / "willhaben_sms_page.png"))

            # SMS kodunu gir
            log(f"SMS kodu giriliyor: {sms_code}")

            # Farkli selector'lari dene
            selectors = [
                "input[maxlength='1']",
                "input[type='tel']",
                "input[type='number']",
                "input[class*='code']",
                "input[class*='otp']",
                "input[autocomplete='one-time-code']"
            ]

            inputs = []
            for sel in selectors:
                inputs = driver.find_elements(By.CSS_SELECTOR, sel)
                if len(inputs) >= 4:
                    log(f"Selector '{sel}' ile {len(inputs)} input bulundu")
                    break

            if len(inputs) >= 4:
                for i, digit in enumerate(sms_code[:4]):
                    inputs[i].clear()
                    inputs[i].send_keys(digit)
                    time.sleep(0.3)

                log("Kod girildi")
                time.sleep(2)

                # Weiter butonu
                try:
                    btn = driver.find_element(By.XPATH, "//button[contains(text(), 'Weiter')]")
                    btn.click()
                    log("Weiter tiklandi")
                except:
                    inputs[3].send_keys(Keys.ENTER)
                    log("ENTER ile gonderildi")

                time.sleep(5)
            else:
                log(f"Input bulunamadi! Toplam {len(inputs)} tane var")
                log("HTML dosyasini kontrol edin")

        # Login kontrolu
        time.sleep(3)
        current_url = driver.current_url
        if '/iad' in current_url and 'login' not in current_url:
            log("LOGIN BASARILI!")

            # Ana sayfaya git ve screenshot al
            driver.get("https://www.willhaben.at/iad")
            time.sleep(3)
            screenshot_path = TEMP_DIR / "willhaben_logged_in.png"
            driver.save_screenshot(str(screenshot_path))
            log(f"Screenshot: {screenshot_path}")

            # Neue Anzeige aufgeben butonu
            try:
                neue_btn = driver.find_element(By.XPATH,
                    "//a[contains(text(), 'Neue Anzeige')] | //button[contains(text(), 'Neue Anzeige')]"
                )
                log(f"'Neue Anzeige aufgeben' butonu bulundu!")
            except:
                log("'Neue Anzeige' butonu bulunamadi")

        else:
            log("LOGIN BASARISIZ!")
            driver.save_screenshot(str(TEMP_DIR / "willhaben_login_failed.png"))

        # 30 saniye bekle
        log("30 saniye bekleniyor...")
        time.sleep(30)

    except Exception as e:
        log(f"HATA: {e}")
        import traceback
        traceback.print_exc()

    finally:
        driver.quit()
        log("Chrome kapatildi")

if __name__ == "__main__":
    main()
