#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Kleinanzeigen magazasindan urun listesi cek
"""

import sys
import time
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.config.credentials import KLEINANZEIGEN

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    import undetected_chromedriver as uc
except ImportError:
    print("Selenium yuklu degil!")
    exit(1)

def get_products():
    """Kleinanzeigen magazasindaki urunleri listele"""

    account = KLEINANZEIGEN['accounts'][0]  # main hesap
    print(f"Hesap: {account['email']}")

    # Driver
    options = uc.ChromeOptions()
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')

    driver = uc.Chrome(options=options)
    driver.implicitly_wait(10)

    try:
        # Login sayfasi
        print("[*] Login sayfasina gidiliyor...")
        driver.get("https://www.kleinanzeigen.de/m-einloggen.html")
        time.sleep(3)

        # Cookie popup
        try:
            driver.execute_script("""
                var buttons = document.querySelectorAll('button');
                for (var btn of buttons) {
                    if (btn.textContent.includes('Alle akzeptieren')) {
                        btn.click();
                        break;
                    }
                }
            """)
            time.sleep(1)
        except:
            pass

        # Email
        print("[*] Email giriliyor...")
        email_input = driver.find_element(By.ID, "login-email")
        email_input.clear()
        email_input.send_keys(account['email'])

        # Password
        print("[*] Sifre giriliyor...")
        pass_input = driver.find_element(By.ID, "login-password")
        pass_input.clear()
        pass_input.send_keys(account['password'])

        # Submit
        print("[*] Giris yapiliyor...")
        submit_btn = driver.find_element(By.ID, "login-submit")
        submit_btn.click()

        time.sleep(5)

        # Basarili mi?
        if "einloggen" in driver.current_url.lower():
            print("[-] Giris basarisiz!")
            input("Manuel giris yapin ve Enter'a basin...")

        # Ilanlarim sayfasi
        print("[*] Ilanlarim sayfasina gidiliyor...")
        driver.get("https://www.kleinanzeigen.de/m-meine-anzeigen.html")
        time.sleep(3)

        # Urunleri listele
        products = []

        # Sayfayi kaydet debug icin
        page_source = driver.page_source
        debug_file = Path(__file__).parent / "debug_page.html"
        with open(debug_file, 'w', encoding='utf-8') as f:
            f.write(page_source)
        print(f"[DEBUG] Sayfa kaydedildi: {debug_file}")

        # Farkli selectorlar dene
        selectors = [
            "article[data-adid]",
            "[class*='aditem']",
            ".managead-list-item",
            "[class*='myads-ad']",
            "li[data-adid]"
        ]

        items = []
        for selector in selectors:
            items = driver.find_elements(By.CSS_SELECTOR, selector)
            if items:
                print(f"[+] Selector '{selector}' ile {len(items)} ilan bulundu\n")
                break

        if not items:
            print("[-] Hic ilan bulunamadi. Debug dosyasini kontrol edin.")
            print("    Sayfa screenshot aliniyor...")
            driver.save_screenshot(str(Path(__file__).parent / "debug_screenshot.png"))

        for i, item in enumerate(items[:10], 1):
            try:
                # URL - farkli yollar dene
                url = None
                for link_sel in ["a[href*='/s-anzeige/']", "a[href*='/anzeige/']", "a"]:
                    try:
                        link = item.find_element(By.CSS_SELECTOR, link_sel)
                        href = link.get_attribute("href")
                        if href and "anzeige" in href:
                            url = href
                            break
                    except:
                        continue

                if not url:
                    continue

                # Baslik
                title = "Baslik alinamadi"
                for title_sel in ["[class*='text-module']", "h2", "[class*='title']", "a"]:
                    try:
                        title_el = item.find_element(By.CSS_SELECTOR, title_sel)
                        title = title_el.text.strip()
                        if title:
                            break
                    except:
                        continue

                # Fiyat
                price = "?"
                for price_sel in ["[class*='price']", "[class*='aditem-main--middle--price']"]:
                    try:
                        price_el = item.find_element(By.CSS_SELECTOR, price_sel)
                        price = price_el.text.strip()
                        if price:
                            break
                    except:
                        continue

                products.append({
                    "title": title,
                    "price": price,
                    "url": url
                })

                print(f"{i}. {title[:50]}...")
                print(f"   Fiyat: {price}")
                print(f"   URL: {url}")
                print()

            except Exception as e:
                print(f"   [-] Urun {i} alinamadi: {e}")
                continue

        if products:
            # JSON kaydet
            output_file = Path(__file__).parent / "kleinanzeigen_products.json"
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(products, f, ensure_ascii=False, indent=2)
            print(f"\n[+] Kaydedildi: {output_file}")

            # Test icin ilk urunu sec
            print("\n" + "=" * 60)
            print("TEST ICIN ILANI SEC:")
            print("=" * 60)
            for i, p in enumerate(products, 1):
                print(f"{i}. {p['title'][:40]}... - {p['price']}")

            # Ilk urunu otomatik sec
            if products:
                selected = products[0]
                print(f"\n[+] Otomatik secilen: {selected['title']}")
                print(f"    URL: {selected['url']}")

                # Transfer test
                print("\n[*] Transfer testi baslatiliyor...")
                from product_transfer_v2 import ProductTransferV2
                transfer = ProductTransferV2()
                transfer.transfer_with_approval(selected['url'], 'vinted', 'main')

        return products

    except Exception as e:
        print(f"[-] Hata: {e}")
        import traceback
        traceback.print_exc()
        return []

    finally:
        try:
            driver.quit()
        except:
            pass

if __name__ == "__main__":
    products = get_products()
