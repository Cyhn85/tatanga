#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI Destekli CAPTCHA Handler
Screenshot alip AI ile analiz eder
Manuel mudahale gerekirse Telegram'a gonderir
"""

import base64
import json
import time
import requests
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.config.credentials import TELEGRAM, AI_SERVICES

class AICaptchaHandler:
    """AI destekli CAPTCHA yonetimi"""

    def __init__(self, driver):
        self.driver = driver
        self.bot_token = TELEGRAM['bot_token']
        self.chat_id = TELEGRAM['channels']['captcha_approval']
        self.groq_api_key = AI_SERVICES['groq']['api_key']
        self.base_dir = Path(__file__).parent.parent
        self.temp_dir = self.base_dir / "T6_LISTING_ENGINE" / "temp"
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.last_update_id = 0

    def take_screenshot(self, name="screen"):
        """Screenshot al ve kaydet"""
        path = self.temp_dir / f"{name}_{int(time.time())}.png"
        self.driver.save_screenshot(str(path))
        return path

    def analyze_with_ai(self, screenshot_path, question=None):
        """
        Screenshot'i AI ile analiz et
        Groq vision destegi yok, sadece metin analizi yapabiliriz
        Alternatif: Sayfa HTML'ini analiz et
        """
        if not question:
            question = "Bu sayfada CAPTCHA var mi? Login basarili mi?"

        # Sayfa kaynak kodu ve URL'den analiz
        page_source = self.driver.page_source.lower()
        current_url = self.driver.current_url

        # Basit analiz
        result = {
            "has_captcha": False,
            "captcha_type": None,
            "needs_manual": False,
            "is_logged_in": False,
            "is_sms_page": False,
            "description": ""
        }

        # reCAPTCHA kontrolu
        if 'recaptcha' in page_source:
            result["has_captcha"] = True

            # Challenge iframe var mi?
            if 'recaptcha-aufgabe' in page_source or 'recaptcha challenge' in page_source:
                result["captcha_type"] = "image_selection"
                result["needs_manual"] = True
                result["description"] = "reCAPTCHA gorsel secim challenge acik"
            else:
                result["captcha_type"] = "checkbox"
                result["description"] = "reCAPTCHA checkbox mevcut"

        # SMS dogrulama
        if 'sso.willhaben.at' in current_url or 'verifizierung' in page_source:
            result["is_sms_page"] = True
            result["needs_manual"] = True
            result["description"] = "SMS dogrulama sayfasi"

        # Login kontrolu
        if '/iad' in current_url and 'login' not in current_url:
            if 'mein willhaben' in page_source or 'profil' in page_source:
                result["is_logged_in"] = True
                result["description"] = "Login basarili"

        return result

    def send_screenshot_to_telegram(self, screenshot_path, message):
        """Screenshot'i Telegram'a gonder"""
        url = f"https://api.telegram.org/bot{self.bot_token}/sendPhoto"

        with open(screenshot_path, 'rb') as photo:
            data = {
                "chat_id": self.chat_id,
                "caption": message,
                "parse_mode": "Markdown"
            }
            files = {
                "photo": photo
            }

            try:
                response = requests.post(url, data=data, files=files, timeout=30)
                return response.status_code == 200
            except Exception as e:
                print(f"Telegram foto gonderme hatasi: {e}")
                return False

    def send_message(self, text):
        """Telegram'a mesaj gonder"""
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        data = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }

        try:
            response = requests.post(url, data=data, timeout=30)
            return response.status_code == 200
        except Exception as e:
            print(f"Telegram mesaj hatasi: {e}")
            return False

    def wait_for_confirmation(self, keywords=None, timeout_seconds=120):
        """
        Telegram'dan onay bekle
        keywords: Kabul edilecek kelimeler ["tamam", "ok", "done", "1234"]
        """
        if keywords is None:
            keywords = ["tamam", "ok", "done", "devam", "bitti", "yes", "evet"]

        # Mevcut update ID'yi al
        url = f"https://api.telegram.org/bot{self.bot_token}/getUpdates"
        try:
            response = requests.get(url, params={"offset": -1, "limit": 1}, timeout=10)
            if response.status_code == 200:
                updates = response.json().get('result', [])
                if updates:
                    self.last_update_id = updates[-1]['update_id']
        except:
            pass

        start_time = time.time()

        while time.time() - start_time < timeout_seconds:
            try:
                response = requests.get(url, params={
                    "offset": self.last_update_id + 1,
                    "timeout": 5
                }, timeout=15)

                if response.status_code == 200:
                    updates = response.json().get('result', [])

                    for update in updates:
                        self.last_update_id = update['update_id']

                        message = update.get('message', {})
                        text = message.get('text', '').strip().lower()
                        chat_id = message.get('chat', {}).get('id')

                        if chat_id == self.chat_id:
                            # 4 haneli kod mu?
                            if text.isdigit() and len(text) == 4:
                                self.send_message(f"Kod alindi: `{text}`")
                                return {"type": "sms_code", "value": text}

                            # Onay kelimesi mi?
                            for keyword in keywords:
                                if keyword.lower() in text:
                                    self.send_message("Onay alindi, devam ediliyor...")
                                    return {"type": "confirmation", "value": text}

            except Exception as e:
                print(f"Telegram update hatasi: {e}")

            # Kalan sure
            elapsed = int(time.time() - start_time)
            remaining = timeout_seconds - elapsed
            if elapsed % 15 == 0 and remaining > 0:
                print(f"Bekleniyor... {remaining}s")

        return None

    def handle_captcha_challenge(self):
        """
        CAPTCHA challenge'i yonet
        1. Screenshot al
        2. Analiz et
        3. Gerekirse Telegram'a gonder
        4. Onay bekle
        """
        print("CAPTCHA durumu kontrol ediliyor...")

        # Screenshot al
        ss_path = self.take_screenshot("captcha_check")

        # Analiz et
        analysis = self.analyze_with_ai(ss_path)

        if analysis["needs_manual"]:
            print(f"Manuel mudahale gerekli: {analysis['description']}")

            # Telegram'a gonder
            message = f"*MANUEL ISLEM GEREKLI*\n\n"
            message += f"{analysis['description']}\n\n"

            if analysis["is_sms_page"]:
                message += "Lutfen SMS kodunu (4 hane) yazip gonderin.\n"
            elif analysis["captcha_type"] == "image_selection":
                message += "Lutfen ekrandaki CAPTCHA'yi cozun.\n"
                message += "Cozunce 'tamam' yazin.\n"

            message += f"\n_Bekleme: 120 saniye_"

            self.send_screenshot_to_telegram(ss_path, message)

            # Onay bekle
            result = self.wait_for_confirmation(timeout_seconds=120)

            if result:
                if result["type"] == "sms_code":
                    return {"action": "enter_sms", "code": result["value"]}
                else:
                    return {"action": "continue"}
            else:
                return {"action": "timeout"}

        elif analysis["is_logged_in"]:
            print("Login basarili!")
            return {"action": "success"}

        else:
            print("Normal durum, devam ediliyor...")
            return {"action": "continue"}

    def interactive_login_flow(self, email, password):
        """
        Interaktif login akisi
        Her adimda durumu kontrol et ve gerekirse Telegram'a sor
        """
        self.send_message("*LOGIN ISLEMI BASLIYOR*\nDurum bildirilecek...")

        steps = [
            ("navigate", "Login sayfasina gidiliyor..."),
            ("fill_form", "Form dolduruluyor..."),
            ("click_recaptcha", "reCAPTCHA tiklaniyor..."),
            ("submit", "Form gonderiliyor..."),
            ("check_result", "Sonuc kontrol ediliyor...")
        ]

        for step_name, step_desc in steps:
            print(f"\n[ADIM] {step_desc}")

            # Adimi calistir
            if step_name == "navigate":
                self.driver.get("https://www.willhaben.at/iad/myprofile/login")
                time.sleep(3)

            elif step_name == "fill_form":
                # Cookie popup kapat
                self.driver.execute_script("""
                    var btns = document.querySelectorAll('button');
                    for (var b of btns) {
                        var txt = b.textContent.toLowerCase();
                        if (txt.includes('akzeptieren') || txt.includes('zustimmen')) {
                            b.click();
                            break;
                        }
                    }
                """)
                time.sleep(2)

                # Email ve sifre - import gerekli
                from selenium.webdriver.common.by import By
                from selenium.webdriver.support.ui import WebDriverWait
                from selenium.webdriver.support import expected_conditions as EC

                email_input = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.ID, "email"))
                )
                email_input.send_keys(email)

                pwd_input = self.driver.find_element(By.ID, "password")
                pwd_input.send_keys(password)
                time.sleep(1)

            elif step_name == "click_recaptcha":
                from selenium.webdriver.common.by import By
                from selenium.webdriver.support.ui import WebDriverWait
                from selenium.webdriver.support import expected_conditions as EC

                frames = self.driver.find_elements(By.TAG_NAME, "iframe")
                for frame in frames:
                    src = frame.get_attribute('src') or ''
                    if 'recaptcha' in src.lower():
                        self.driver.switch_to.frame(frame)
                        try:
                            checkbox = WebDriverWait(self.driver, 5).until(
                                EC.element_to_be_clickable((By.CSS_SELECTOR, ".recaptcha-checkbox-border"))
                            )
                            self.driver.execute_script("arguments[0].click();", checkbox)
                        except:
                            pass
                        self.driver.switch_to.default_content()
                        break
                time.sleep(3)

            elif step_name == "submit":
                from selenium.webdriver.common.by import By

                # Challenge kontrolu
                result = self.handle_captcha_challenge()
                if result["action"] == "timeout":
                    self.send_message("CAPTCHA timeout!")
                    return False

                # Submit
                btn = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
                self.driver.execute_script("arguments[0].click();", btn)
                time.sleep(5)

            elif step_name == "check_result":
                # SMS veya basari kontrolu
                result = self.handle_captcha_challenge()

                if result["action"] == "enter_sms":
                    # SMS kodunu gir
                    from selenium.webdriver.common.by import By
                    from selenium.webdriver.common.keys import Keys

                    code = result["code"]
                    inputs = self.driver.find_elements(By.CSS_SELECTOR, "input[maxlength='1']")

                    if len(inputs) >= 4:
                        for i, digit in enumerate(code[:4]):
                            inputs[i].clear()
                            inputs[i].send_keys(digit)
                            time.sleep(0.2)

                        time.sleep(1)
                        inputs[3].send_keys(Keys.ENTER)
                        time.sleep(5)

                        # Son kontrol
                        final = self.handle_captcha_challenge()
                        if final["action"] == "success":
                            self.send_message("LOGIN BASARILI!")
                            return True

                elif result["action"] == "success":
                    self.send_message("LOGIN BASARILI!")
                    return True

        self.send_message("Login tamamlanamadi.")
        return False


# Test
if __name__ == "__main__":
    print("=" * 60)
    print("AI CAPTCHA HANDLER TEST")
    print("=" * 60)

    try:
        import undetected_chromedriver as uc
        from shared.config.credentials import WILLHABEN

        options = uc.ChromeOptions()
        options.add_argument('--start-maximized')
        options.add_argument('--lang=de')
        driver = uc.Chrome(options=options)

        handler = AICaptchaHandler(driver)

        account = WILLHABEN['accounts'][0]
        success = handler.interactive_login_flow(
            account['email'],
            account['password']
        )

        if success:
            print("\nLogin BASARILI!")
        else:
            print("\nLogin BASARISIZ!")

        time.sleep(10)
        driver.quit()

    except Exception as e:
        print(f"Hata: {e}")
        import traceback
        traceback.print_exc()
