#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Kleinanzeigen Scrape Test - Urun selector'larini analiz et
"""

import sys
import time
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.config.credentials import KLEINANZEIGEN
from store_transfer_handler import StoreTransferHandler

def test_kleinanzeigen_scrape():
    """Kleinanzeigen urun scrape test"""
    print("=" * 60, flush=True)
    print("KLEINANZEIGEN SCRAPE TEST", flush=True)
    print("=" * 60, flush=True)

    handler = StoreTransferHandler()
    handler.send_telegram = False

    account = KLEINANZEIGEN['accounts'][0]
    print(f"\nHesap: {account['email']}", flush=True)

    if not handler.init_driver():
        print("Driver baslatilamadi!", flush=True)
        return

    try:
        # Login sayfasi
        print("\nLogin sayfasina gidiliyor...", flush=True)
        handler.driver.get("https://www.kleinanzeigen.de/m-einloggen.html")
        time.sleep(3)

        # Cookie popup
        try:
            handler.driver.execute_script("""
                var buttons = document.querySelectorAll('button');
                for (var btn of buttons) {
                    if (btn.textContent.includes('Alle akzeptieren') || btn.textContent.includes('Akzeptieren')) {
                        btn.click();
                        break;
                    }
                }
            """)
            time.sleep(1)
        except:
            pass

        # Screenshot
        handler.driver.save_screenshot(str(Path(__file__).parent.parent / "T6_LISTING_ENGINE" / "temp" / "kleinanzeigen_login.png"))

        # Email gir
        from selenium.webdriver.common.by import By
        email_input = handler.driver.find_element(By.ID, "login-email")
        email_input.clear()
        email_input.send_keys(account['email'])
        time.sleep(0.5)

        # Sifre gir
        pass_input = handler.driver.find_element(By.ID, "login-password")
        pass_input.clear()
        pass_input.send_keys(account['password'])
        time.sleep(0.5)

        # Login buton
        submit_btn = handler.driver.find_element(By.ID, "login-submit")
        submit_btn.click()
        print("Login butonu tiklandi", flush=True)
        time.sleep(5)

        # Ilanlarim sayfasi
        print("Ilanlar sayfasina gidiliyor...", flush=True)
        handler.driver.get("https://www.kleinanzeigen.de/m-meine-anzeigen.html")
        time.sleep(5)

        # Screenshot
        handler.driver.save_screenshot(str(Path(__file__).parent.parent / "T6_LISTING_ENGINE" / "temp" / "kleinanzeigen_anzeigen.png"))
        print(f"Screenshot: kleinanzeigen_anzeigen.png", flush=True)

        # Scroll
        for i in range(3):
            handler.driver.execute_script("window.scrollBy(0, 500)")
            time.sleep(0.5)

        # Analiz - farkli selector'lari dene
        print("\n" + "=" * 60, flush=True)
        print("SELECTOR ANALIZI", flush=True)
        print("=" * 60, flush=True)

        test_selectors = [
            "li[data-adid]",
            "article[data-adid]",
            "[class*='aditem']",
            ".ad-listitem",
            "[class*='AdItem']",
            "[data-testid*='ad']",
            "li.ad-listitem",
            "article.aditem",
            "[class*='userads-listitem']",
            ".userads-listitem",
        ]

        for selector in test_selectors:
            try:
                items = handler.driver.find_elements(By.CSS_SELECTOR, selector)
                if items:
                    print(f"  '{selector}' -> {len(items)} sonuc", flush=True)
            except:
                pass

        # Sayfadaki tum li elementleri
        print("\n--- Tum LI elementleri ---", flush=True)
        lis = handler.driver.find_elements(By.TAG_NAME, "li")
        print(f"Toplam {len(lis)} li elementi", flush=True)

        # data-* attribute'lu li elementler
        print("\n--- data-* attribute'lu elementler ---", flush=True)
        data_elements = handler.driver.find_elements(By.XPATH, "//*[@*[starts-with(name(), 'data-')]]")
        unique_attrs = set()
        for elem in data_elements[:50]:
            try:
                attrs = handler.driver.execute_script(
                    "var attrs = arguments[0].attributes; var result = []; for (var i = 0; i < attrs.length; i++) { if (attrs[i].name.startsWith('data-')) result.push(attrs[i].name); } return result;",
                    elem
                )
                for attr in attrs:
                    unique_attrs.add(attr)
            except:
                pass

        for attr in sorted(unique_attrs):
            print(f"  {attr}", flush=True)

        # HTML kaydet
        html_path = Path(__file__).parent.parent / "T6_LISTING_ENGINE" / "temp" / "kleinanzeigen_page.html"
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(handler.driver.page_source)
        print(f"\nHTML kaydedildi: {html_path}", flush=True)

    except Exception as e:
        print(f"Hata: {e}", flush=True)
        import traceback
        traceback.print_exc()

    finally:
        try:
            handler.driver.quit()
        except:
            pass

if __name__ == "__main__":
    test_kleinanzeigen_scrape()
