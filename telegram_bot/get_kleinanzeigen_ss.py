#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Kleinanzeigen Screenshot Al - Dashboard Anzeigen sekmesi
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.config.credentials import KLEINANZEIGEN

TEMP_DIR = Path(__file__).parent.parent / "T6_LISTING_ENGINE" / "temp"

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    import undetected_chromedriver as uc
except ImportError:
    print("Selenium yuklu degil!")
    sys.exit(1)

def main():
    print("=" * 60)
    print("KLEINANZEIGEN SCREENSHOT")
    print("=" * 60)

    options = uc.ChromeOptions()
    options.add_argument('--start-maximized')
    driver = uc.Chrome(options=options)

    try:
        # Login
        print("\n1. Login sayfasi...")
        driver.get("https://www.kleinanzeigen.de/m-einloggen.html")
        time.sleep(3)

        # Cookie popup - tum butonlari dene
        print("2. Cookie popup kapatiliyor...")
        for _ in range(3):
            try:
                driver.execute_script("""
                    var btns = document.querySelectorAll('button, a');
                    for (var b of btns) {
                        var txt = b.textContent.toLowerCase();
                        if (txt.includes('akzeptieren') || txt.includes('accept')) {
                            b.click();
                            return true;
                        }
                    }
                    return false;
                """)
                time.sleep(1)
            except:
                pass

        # Email ve sifre
        print("3. Login bilgileri giriliyor...")
        account = KLEINANZEIGEN['accounts'][0]

        try:
            email = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "login-email"))
            )
            email.clear()
            email.send_keys(account['email'])
            time.sleep(0.5)

            pwd = driver.find_element(By.ID, "login-password")
            pwd.clear()
            pwd.send_keys(account['password'])
            time.sleep(0.5)

            btn = driver.find_element(By.ID, "login-submit")
            btn.click()
            print("4. Login butonu tiklandi, bekleniyor...")
            time.sleep(8)
        except Exception as e:
            print(f"Login hatasi: {e}")
            driver.save_screenshot(str(TEMP_DIR / "login_error.png"))
            return

        # Popup varsa kapat
        print("5. Popup kontrolu...")
        for _ in range(3):
            try:
                driver.execute_script("""
                    var btns = document.querySelectorAll('button, a');
                    for (var b of btns) {
                        var txt = b.textContent.toLowerCase();
                        if (txt.includes('akzeptieren') || txt.includes('schliessen') || txt.includes('close')) {
                            b.click();
                            return true;
                        }
                    }
                    return false;
                """)
                time.sleep(1)
            except:
                pass

        # Anzeigen sayfasi
        print("6. Meine Anzeigen sayfasina gidiliyor...")
        driver.get("https://www.kleinanzeigen.de/m-meine-anzeigen.html")
        time.sleep(5)

        # Popup tekrar kontrol
        for _ in range(3):
            try:
                driver.execute_script("""
                    var btns = document.querySelectorAll('button');
                    for (var b of btns) {
                        var txt = b.textContent.toLowerCase();
                        if (txt.includes('akzeptieren') || txt.includes('schliessen')) {
                            b.click();
                            return true;
                        }
                    }
                    return false;
                """)
                time.sleep(1)
            except:
                pass

        # Sayfayi scroll et
        print("7. Sayfa scroll ediliyor...")
        for i in range(5):
            driver.execute_script(f"window.scrollTo(0, {i * 500})")
            time.sleep(0.5)

        # Yukari don
        driver.execute_script("window.scrollTo(0, 0)")
        time.sleep(2)

        # Screenshot al
        ss_path = TEMP_DIR / "kleinanzeigen_full_products.png"
        driver.save_screenshot(str(ss_path))
        print(f"\n8. Screenshot kaydedildi: {ss_path}")

        # Sayfa HTML kaydet (debug icin)
        html_path = TEMP_DIR / "kleinanzeigen_products.html"
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(driver.page_source)
        print(f"9. HTML kaydedildi: {html_path}")

        print("\n" + "=" * 60)
        print("TAMAMLANDI - Screenshot'i kontrol edin")
        print("=" * 60)

    except Exception as e:
        print(f"Hata: {e}")
        import traceback
        traceback.print_exc()

    finally:
        input("\nDevam etmek icin ENTER'a basin...")
        driver.quit()

if __name__ == "__main__":
    main()
