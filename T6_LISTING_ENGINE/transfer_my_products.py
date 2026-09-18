#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TATANGA - Kendi Kleinanzeigen Magazasindan Vinted'e Transfer
Login yapip kendi urunlerini cek ve transfer et
"""

import sys
import time
import json
import re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.config.credentials import KLEINANZEIGEN
from product_transfer_v2 import ProductTransferV2

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    import undetected_chromedriver as uc
except ImportError:
    print("Selenium yuklu degil!")
    exit(1)

OUTPUT_DIR = Path(__file__).parent / "output"
TEMP_DIR = Path(__file__).parent / "temp"
OUTPUT_DIR.mkdir(exist_ok=True)
TEMP_DIR.mkdir(exist_ok=True)

def get_my_products():
    """Kleinanzeigen magazasindan kendi urunlerimi listele"""

    account = KLEINANZEIGEN['accounts'][0]  # main hesap
    print(f"\n[*] Hesap: {account['email']}")
    print(f"    Profil: {account.get('profile_name', 'N/A')}")

    # Driver - gorunur modda
    options = uc.ChromeOptions()
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--lang=de-DE')

    print("\n[*] Chrome baslatiliyor...")
    driver = uc.Chrome(options=options)
    driver.implicitly_wait(10)

    products = []

    try:
        # Login sayfasi
        print("[*] Login sayfasina gidiliyor...")
        driver.get("https://www.kleinanzeigen.de/m-einloggen.html")
        time.sleep(4)

        # Cookie popup
        print("[*] Cookie popup kontrol ediliyor...")
        try:
            driver.execute_script("""
                var buttons = document.querySelectorAll('button, a');
                for (var btn of buttons) {
                    var text = btn.textContent || btn.innerText;
                    if (text.includes('Alle akzeptieren') ||
                        text.includes('Accept all') ||
                        text.includes('Einverstanden')) {
                        btn.click();
                        console.log('Cookie accepted');
                        break;
                    }
                }
            """)
            time.sleep(2)
        except Exception as e:
            print(f"    Cookie popup: {e}")

        # Screenshot al
        driver.save_screenshot(str(TEMP_DIR / "01_login_page.png"))

        # Email gir
        print("[*] Email giriliyor...")
        try:
            email_input = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "login-email"))
            )
            email_input.clear()
            email_input.send_keys(account['email'])
            time.sleep(1)
        except Exception as e:
            print(f"    [-] Email input bulunamadi: {e}")
            # Alternatif selector
            try:
                email_input = driver.find_element(By.NAME, "email")
                email_input.clear()
                email_input.send_keys(account['email'])
            except:
                pass

        # Sifre gir
        print("[*] Sifre giriliyor...")
        try:
            pass_input = driver.find_element(By.ID, "login-password")
            pass_input.clear()
            pass_input.send_keys(account['password'])
            time.sleep(1)
        except Exception as e:
            print(f"    [-] Password input bulunamadi: {e}")
            try:
                pass_input = driver.find_element(By.NAME, "password")
                pass_input.clear()
                pass_input.send_keys(account['password'])
            except:
                pass

        # Screenshot al
        driver.save_screenshot(str(TEMP_DIR / "02_login_filled.png"))

        # Submit
        print("[*] Giris yapiliyor...")
        try:
            submit_btn = driver.find_element(By.ID, "login-submit")
            submit_btn.click()
        except:
            try:
                submit_btn = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
                submit_btn.click()
            except:
                pass

        time.sleep(5)

        # Screenshot al
        driver.save_screenshot(str(TEMP_DIR / "03_after_login.png"))

        # Basarili mi?
        current_url = driver.current_url.lower()
        if "einloggen" in current_url or "login" in current_url:
            print("[-] Giris basarisiz olabilir!")
            print(f"    URL: {driver.current_url}")
            # Devam et, belki captcha var
        else:
            print("[+] Giris basarili!")

        # Ilanlarim sayfasi
        print("\n[*] Ilanlarim sayfasina gidiliyor...")
        driver.get("https://www.kleinanzeigen.de/m-meine-anzeigen.html")
        time.sleep(4)

        # Screenshot al
        driver.save_screenshot(str(TEMP_DIR / "04_my_ads.png"))

        # Sayfayi kaydet
        with open(TEMP_DIR / "my_ads_page.html", 'w', encoding='utf-8') as f:
            f.write(driver.page_source)
        print(f"    [DEBUG] Sayfa kaydedildi: {TEMP_DIR / 'my_ads_page.html'}")

        # Urunleri bul - farkli selectorlar
        print("\n[*] Urunler araniyor...")

        selectors_to_try = [
            # Yeni Kleinanzeigen tasarimi
            "[data-testid='ad-list-item']",
            "article[data-adid]",
            "[class*='aditem']",
            ".managead-list-item",
            "li[data-adid]",
            # Eski tasarim
            ".ad-listitem",
            "[class*='myads-ad']",
            # Genel
            "article",
            ".cardbox"
        ]

        items = []
        used_selector = None

        for selector in selectors_to_try:
            try:
                found = driver.find_elements(By.CSS_SELECTOR, selector)
                if found:
                    items = found
                    used_selector = selector
                    print(f"[+] '{selector}' ile {len(items)} ilan bulundu")
                    break
            except:
                continue

        if not items:
            print("[-] Hic ilan bulunamadi!")
            print("    Sayfa icerigi kontrol ediliyor...")

            # Sayfada ne var?
            page_text = driver.find_element(By.TAG_NAME, "body").text
            if "Keine Anzeigen" in page_text or "keine" in page_text.lower():
                print("    [!] Magazada ilan yok gibi gorunuyor")

            # Tum linkleri kontrol et
            all_links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/s-anzeige/']")
            if all_links:
                print(f"    [+] {len(all_links)} ilan linki bulundu")
                items = all_links

        # Urunleri isle
        print(f"\n{'='*60}")
        print(f"BULUNAN ILANLAR: {len(items)}")
        print(f"{'='*60}\n")

        for i, item in enumerate(items[:10], 1):
            try:
                product = {"index": i}

                # URL bul
                url = None

                # Eger item kendisi link ise
                if item.tag_name == "a":
                    url = item.get_attribute("href")
                else:
                    # Icindeki linki bul
                    for link_sel in ["a[href*='/s-anzeige/']", "a[href*='anzeige']", "a"]:
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

                product["url"] = url

                # Baslik bul
                title = "Baslik alinamadi"
                for title_sel in ["h2", "h3", "[class*='title']", "[class*='text-module']", "a"]:
                    try:
                        title_el = item.find_element(By.CSS_SELECTOR, title_sel)
                        t = title_el.text.strip()
                        if t and len(t) > 3:
                            title = t
                            break
                    except:
                        continue

                product["title"] = title

                # Fiyat bul
                price = "?"
                for price_sel in ["[class*='price']", "[class*='aditem-main--middle--price']", "span"]:
                    try:
                        price_el = item.find_element(By.CSS_SELECTOR, price_sel)
                        p = price_el.text.strip()
                        if p and ("EUR" in p or "€" in p or p.replace('.','').replace(',','').isdigit()):
                            price = p
                            break
                    except:
                        continue

                product["price"] = price

                products.append(product)

                print(f"{i}. {title[:50]}...")
                print(f"   Fiyat: {price}")
                print(f"   URL: {url}")
                print()

            except Exception as e:
                print(f"   [-] Urun {i} islenemedi: {e}")
                continue

        # Sonuclari kaydet
        if products:
            output_file = OUTPUT_DIR / "my_kleinanzeigen_products.json"
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(products, f, ensure_ascii=False, indent=2)
            print(f"\n[+] {len(products)} urun kaydedildi: {output_file}")

            # Transfer et
            print("\n" + "="*60)
            print("TRANSFER BASLATILIYOR")
            print("="*60)

            if products:
                # Ilk urunu transfer et
                selected = products[0]
                print(f"\n[*] Secilen urun: {selected['title']}")
                print(f"    URL: {selected['url']}")

                # Driver'i kapat ve transfer baslat
                driver.quit()
                driver = None

                print("\n[*] Transfer islemi baslatiliyor...")
                transfer = ProductTransferV2()
                product_id = transfer.transfer_with_approval(selected['url'], 'vinted', 'main')

                if product_id:
                    print(f"\n[+] Transfer baslatildi: {product_id}")
                    print("    Telegram'dan onay bekleniyor...")
                else:
                    print("\n[-] Transfer basarisiz!")

        return products

    except Exception as e:
        print(f"\n[-] HATA: {e}")
        import traceback
        traceback.print_exc()
        return []

    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass

if __name__ == "__main__":
    print("="*60)
    print("TATANGA - Kendi Magazamdan Vinted'e Transfer")
    print("="*60)

    products = get_my_products()

    if products:
        print(f"\n[+] Toplam {len(products)} urun bulundu")
    else:
        print("\n[-] Urun bulunamadi")
