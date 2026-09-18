#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Willhaben Login Test - Telegram SMS Entegrasyonu
SMS kodu Telegram uzerinden alinir
"""

import sys
import time
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.config.credentials import WILLHABEN
from telegram_sms_handler import TelegramSMSHandler

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
    # Telegram handler
    telegram = TelegramSMSHandler()

    # Baslangic bildirimi
    telegram.notify("*WILLHABEN LOGIN*\nIslem baslatiliyor...")

    # Chrome baslat
    options = uc.ChromeOptions()
    options.add_argument('--start-maximized')
    options.add_argument('--lang=de')
    driver = uc.Chrome(options=options)

    log("Chrome baslatildi")

    try:
        account = WILLHABEN['accounts'][0]

        # Direkt login sayfasina git
        log("Login sayfasina gidiliyor...")
        driver.get("https://www.willhaben.at/iad/myprofile/login")
        time.sleep(4)

        # Cookie popup kapat
        driver.execute_script("""
            var btns = document.querySelectorAll('button');
            for (var b of btns) {
                var txt = b.textContent.toLowerCase();
                if (txt.includes('akzeptieren') || txt.includes('zustimmen') || txt.includes('accept')) {
                    b.click();
                    return;
                }
            }
        """)
        time.sleep(2)

        # Email ve sifre
        email_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "email"))
        )
        email_input.send_keys(account['email'])
        log(f"Email: {account['email']}")

        pwd_input = driver.find_element(By.ID, "password")
        pwd_input.send_keys(account['password'])
        log("Sifre girildi")

        # reCAPTCHA checkbox'i tikla
        log("reCAPTCHA araniyor...")
        time.sleep(2)

        recaptcha_clicked = False
        try:
            frames = driver.find_elements(By.TAG_NAME, "iframe")
            log(f"Toplam {len(frames)} iframe bulundu")

            for i, frame in enumerate(frames):
                try:
                    src = frame.get_attribute('src') or ''
                    title = frame.get_attribute('title') or ''

                    if 'recaptcha' in src.lower() or 'recaptcha' in title.lower():
                        log(f"reCAPTCHA iframe bulundu (index {i})")

                        driver.switch_to.frame(frame)
                        time.sleep(1)

                        try:
                            checkbox = WebDriverWait(driver, 10).until(
                                EC.element_to_be_clickable((By.CSS_SELECTOR, ".recaptcha-checkbox-border, .recaptcha-checkbox, #recaptcha-anchor, span[role='checkbox']"))
                            )

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

        except Exception as e:
            log(f"reCAPTCHA hatasi: {e}")
            driver.switch_to.default_content()

        if recaptcha_clicked:
            log("reCAPTCHA dogrulamasi bekleniyor...")
            # Challenge varsa cozulmesini bekle (max 30 saniye)
            for i in range(30):
                time.sleep(1)
                # Challenge iframe kapandi mi kontrol et
                try:
                    challenge_frames = driver.find_elements(By.CSS_SELECTOR, "iframe[title*='reCAPTCHA-Aufgabe'], iframe[title*='recaptcha challenge']")
                    visible_challenges = [f for f in challenge_frames if f.is_displayed()]
                    if not visible_challenges:
                        log("reCAPTCHA challenge tamamlandi")
                        break
                    if i % 5 == 0:
                        log(f"Challenge cozuluyor... {30-i}s")
                except:
                    break
            time.sleep(2)

        # Login butonu - JavaScript ile tikla (popup engelini asma)
        login_btn = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
        driver.execute_script("arguments[0].click();", login_btn)
        log("Login butonu tiklandi")
        time.sleep(5)

        # SMS dogrulama kontrolu
        current_url = driver.current_url
        if 'sso.willhaben.at' in current_url:
            log("SMS dogrulama sayfasinda!")

            # Telefon numarasi ve referans kodunu al
            page_source = driver.page_source
            phone_match = re.search(r'\*+\d{4}', page_source)
            phone_hint = phone_match.group(0) if phone_match else ""

            ref_match = re.search(r'Referenzwert:\s*([a-zA-Z0-9]+)', page_source)
            reference = ref_match.group(1) if ref_match else ""

            log(f"Telefon: {phone_hint}, Referans: {reference}")

            # Telegram'dan SMS kodu iste
            sms_code = telegram.request_sms_code(
                platform="WILLHABEN",
                phone_hint=phone_hint,
                reference=reference,
                timeout_seconds=120
            )

            if not sms_code:
                log("SMS kodu alinamadi!")
                telegram.notify_error("WILLHABEN", "SMS kodu alinamadi - timeout")
                return

            # Sayfa yuklenmesini bekle
            time.sleep(2)

            # SMS kodunu gir
            log(f"SMS kodu giriliyor: {sms_code}")

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
                telegram.notify_error("WILLHABEN", "SMS input alanlari bulunamadi")

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

            # Basari bildirimi
            telegram.notify_success("WILLHABEN", "Login basarili! Ana sayfa acildi.")

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
            telegram.notify_error("WILLHABEN", "Login basarisiz!")

        # 10 saniye bekle
        log("10 saniye bekleniyor...")
        time.sleep(10)

    except Exception as e:
        log(f"HATA: {e}")
        import traceback
        traceback.print_exc()
        telegram.notify_error("WILLHABEN", str(e))

    finally:
        driver.quit()
        log("Chrome kapatildi")

if __name__ == "__main__":
    main()
