#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Screenshot + AI Vision Test
Kleinanzeigen'den screenshot al, AI ile analiz et
"""

import sys
import time
import json
import base64
import requests
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.config.credentials import KLEINANZEIGEN, AI_SERVICES

# Dizinler
BASE_DIR = Path(__file__).parent.parent
TEMP_DIR = BASE_DIR / "T6_LISTING_ENGINE" / "temp"

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    import undetected_chromedriver as uc
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

def take_kleinanzeigen_screenshot():
    """Kleinanzeigen ürün listesi screenshot'ı al"""
    print("=" * 60)
    print("SCREENSHOT + AI VISION TEST")
    print("=" * 60)

    if not SELENIUM_AVAILABLE:
        print("Selenium yuklu degil!")
        return None

    # Chrome baslat
    print("\nChrome baslatiliyor...")
    options = uc.ChromeOptions()
    options.add_argument('--start-maximized')
    driver = uc.Chrome(options=options)

    try:
        # Login sayfasi
        print("Kleinanzeigen login yapiliyor...")
        driver.get("https://www.kleinanzeigen.de/m-einloggen.html")
        time.sleep(3)

        # Cookie popup
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

        # Login
        account = KLEINANZEIGEN['accounts'][0]
        email_input = driver.find_element(By.ID, "login-email")
        email_input.send_keys(account['email'])
        time.sleep(0.5)

        pass_input = driver.find_element(By.ID, "login-password")
        pass_input.send_keys(account['password'])
        time.sleep(0.5)

        submit_btn = driver.find_element(By.ID, "login-submit")
        submit_btn.click()
        time.sleep(5)

        # Willkommen popup kapat
        driver.execute_script("""
            var buttons = document.querySelectorAll('button');
            for (var btn of buttons) {
                if (btn.textContent.includes('Alle akzeptieren')) {
                    btn.click();
                    break;
                }
            }
        """)
        time.sleep(2)

        # Ilanlar sayfasi
        print("Ilanlar sayfasina gidiliyor...")
        driver.get("https://www.kleinanzeigen.de/m-meine-anzeigen.html")
        time.sleep(5)

        # Popup varsa kapat
        driver.execute_script("""
            var buttons = document.querySelectorAll('button');
            for (var btn of buttons) {
                if (btn.textContent.includes('Alle akzeptieren') || btn.textContent.includes('Schließen')) {
                    btn.click();
                    break;
                }
            }
        """)
        time.sleep(2)

        # Scroll down to load products
        for i in range(3):
            driver.execute_script("window.scrollBy(0, 500)")
            time.sleep(0.5)

        # Scroll back to top
        driver.execute_script("window.scrollTo(0, 0)")
        time.sleep(1)

        # Screenshot al
        screenshot_path = TEMP_DIR / "kleinanzeigen_products.png"
        driver.save_screenshot(str(screenshot_path))
        print(f"\nScreenshot kaydedildi: {screenshot_path}")

        return str(screenshot_path)

    except Exception as e:
        print(f"Hata: {e}")
        return None

    finally:
        try:
            driver.quit()
        except:
            pass

def analyze_with_ai(image_path):
    """Screenshot'ı AI ile analiz et"""
    print("\n" + "=" * 60)
    print("AI ANALİZ")
    print("=" * 60)

    # Resmi base64'e çevir
    with open(image_path, 'rb') as f:
        image_data = base64.b64encode(f.read()).decode('utf-8')

    # Claude API ile analiz
    api_key = AI_SERVICES.get('anthropic_api_key', '')
    if not api_key:
        print("Anthropic API key bulunamadı!")
        return None

    print("Claude API ile analiz ediliyor...")

    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }

    prompt = """Bu Kleinanzeigen ürün listesi screenshot'ını analiz et.

Her ürün için şu bilgileri JSON formatında çıkar:
- title: Ürün başlığı
- price: Fiyat (sadece sayı, EUR olmadan)
- category: Kategori
- image_count: Resim sayısı (varsa)

Yanıtı sadece JSON array olarak ver, başka açıklama ekleme.
Örnek format:
[
  {"title": "Zara Herren Schuhe", "price": 30, "category": "Herrenschuhe", "image_count": 3},
  ...
]"""

    data = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 4096,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": image_data
                        }
                    },
                    {
                        "type": "text",
                        "text": prompt
                    }
                ]
            }
        ]
    }

    try:
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json=data,
            timeout=60
        )

        if response.status_code == 200:
            result = response.json()
            content = result['content'][0]['text']

            # JSON parse
            try:
                # JSON array'i bul
                start = content.find('[')
                end = content.rfind(']') + 1
                if start != -1 and end > start:
                    json_str = content[start:end]
                    products = json.loads(json_str)

                    print(f"\n{len(products)} ürün bulundu:\n")
                    for i, p in enumerate(products):
                        print(f"{i+1}. {p.get('title', 'N/A')}")
                        print(f"   Fiyat: {p.get('price', 0)} EUR")
                        print(f"   Kategori: {p.get('category', 'N/A')}")
                        print(f"   Resim: {p.get('image_count', 0)}")
                        print()

                    return products
                else:
                    print(f"JSON bulunamadı: {content}")
                    return None

            except json.JSONDecodeError as e:
                print(f"JSON parse hatası: {e}")
                print(f"İçerik: {content}")
                return None
        else:
            print(f"API hatası: {response.status_code}")
            print(response.text)
            return None

    except Exception as e:
        print(f"API çağrı hatası: {e}")
        return None

def main():
    # Screenshot al
    screenshot_path = take_kleinanzeigen_screenshot()

    if screenshot_path:
        # AI ile analiz et
        products = analyze_with_ai(screenshot_path)

        if products:
            # Sonuçları kaydet
            output_path = TEMP_DIR / "ai_extracted_products.json"
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(products, f, ensure_ascii=False, indent=2)
            print(f"\nSonuçlar kaydedildi: {output_path}")

            print("\n" + "=" * 60)
            print("TEST BAŞARILI!")
            print("=" * 60)
            return True

    print("\n" + "=" * 60)
    print("TEST BAŞARISIZ!")
    print("=" * 60)
    return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
