#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TATANGA - Product Transfer v2
SEO-uyumlu benzersiz icerik + Telegram onay + T5 Image Processing
"""

import os
import sys
import json
import time
import re
import requests
import hashlib
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.config.credentials import TELEGRAM, VINTED, KLEINANZEIGEN, EBAY, WILLHABEN, AI_SERVICES

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    import undetected_chromedriver as uc
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

try:
    from PIL import Image, ImageEnhance, ImageFilter
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# ============================================
# CONFIGURATION
# ============================================
OUTPUT_DIR = Path(__file__).parent / "output"
TEMP_DIR = Path(__file__).parent / "temp"
LOGS_DIR = Path(__file__).parent / "logs"
PENDING_DIR = Path(__file__).parent / "pending_approval"

for d in [OUTPUT_DIR, TEMP_DIR, LOGS_DIR, PENDING_DIR]:
    d.mkdir(exist_ok=True)

# ============================================
# TELEGRAM WITH APPROVAL
# ============================================
class TelegramApproval:
    """Telegram onay sistemi"""

    def __init__(self):
        self.bot_token = TELEGRAM['bot_token']
        self.admin_chat = TELEGRAM['admin_chat_id']
        self.pending_products = {}

    def send_photo_with_buttons(self, photo_path, caption, buttons):
        """Fotograf ve butonlarla mesaj gonder"""
        url = f"https://api.telegram.org/bot{self.bot_token}/sendPhoto"

        with open(photo_path, 'rb') as photo:
            files = {'photo': photo}
            data = {
                'chat_id': self.admin_chat,
                'caption': caption,
                'parse_mode': 'Markdown',
                'reply_markup': json.dumps({'inline_keyboard': buttons})
            }

            try:
                resp = requests.post(url, files=files, data=data)
                return resp.json()
            except Exception as e:
                print(f"Telegram foto hatasi: {e}")
                return None

    def send_approval_request(self, product_data):
        """
        Urun onay istegi gonder

        Args:
            product_data: {
                'id': 'PROD-xxx',
                'original': {...},
                'optimized': {...},
                'images': [...],
                'target_platform': 'vinted',
                'target_account': 'main'
            }
        """
        product_id = product_data['id']
        original = product_data['original']
        optimized = product_data['optimized']
        target = product_data['target_platform']

        # Kaydet
        self.pending_products[product_id] = product_data
        pending_file = PENDING_DIR / f"{product_id}.json"
        with open(pending_file, 'w', encoding='utf-8') as f:
            json.dump(product_data, f, ensure_ascii=False, indent=2)

        # Mesaj hazirla
        caption = f"""
*URUN TRANSFER ONAYI*

*ID:* `{product_id}`
*Hedef:* {target.upper()} ({product_data['target_account']})

*ORIJINAL:*
_{original['title'][:60]}..._
Fiyat: {original['price']} EUR

*OPTIMIZE EDILMIS:*
_{optimized['title'][:60]}..._
Fiyat: {optimized['price']} EUR

*Yeni Aciklama:*
```
{optimized['description'][:300]}...
```

*Resim:* {len(product_data['images'])} adet (islenmis)
"""

        # Butonlar
        buttons = [
            [
                {"text": "ONAYLA", "callback_data": f"approve:{product_id}"},
                {"text": "REDDET", "callback_data": f"reject:{product_id}"}
            ],
            [
                {"text": "Fiyat Degistir", "callback_data": f"price:{product_id}"},
                {"text": "Baslik Degistir", "callback_data": f"title:{product_id}"}
            ]
        ]

        # Ilk resmi gonder
        if product_data['images']:
            result = self.send_photo_with_buttons(
                product_data['images'][0],
                caption,
                buttons
            )
        else:
            # Resim yoksa metin gonder
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            data = {
                'chat_id': self.admin_chat,
                'text': caption,
                'parse_mode': 'Markdown',
                'reply_markup': json.dumps({'inline_keyboard': buttons})
            }
            result = requests.post(url, data=data).json()

        print(f"[+] Onay istegi gonderildi: {product_id}")
        return result

# ============================================
# AI CONTENT OPTIMIZER
# ============================================
class ContentOptimizer:
    """AI ile SEO-uyumlu benzersiz icerik olusturucu"""

    def __init__(self):
        self.api_key = AI_SERVICES['groq']['api_key']
        self.model = AI_SERVICES['groq']['model']

    def optimize_for_platform(self, product, target_platform):
        """
        Platform icin optimize edilmis icerik olustur

        Args:
            product: Orijinal urun bilgileri
            target_platform: Hedef platform

        Returns:
            dict: Optimize edilmis baslik, aciklama, etiketler
        """
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            platform_hints = {
                "vinted": "Vinted kullanicilari genellikle genc, moda odakli. Kisa, catchy basliklar ve hashtagler onemli.",
                "kleinanzeigen": "Kleinanzeigen kullanicilari detayli bilgi ister. Durum, olculer, marka bilgisi onemli.",
                "ebay": "eBay icin profesyonel, detayli baslik ve aciklama. Anahtar kelimeler onemli.",
                "willhaben": "Willhaben Avusturya pazari. Almanca, resmi dil. Detayli bilgi."
            }

            prompt = f"""
Asagidaki urunu {target_platform.upper()} icin optimize et.
{platform_hints.get(target_platform, '')}

ORIJINAL:
Baslik: {product.get('title', '')}
Aciklama: {product.get('description', '')[:500]}
Fiyat: {product.get('price', 0)} EUR
Kategori: {product.get('category', '')}

KURALLAR:
1. Baslik tamamen yeni olmali (duplicate tespit edilmemeli)
2. SEO icin anahtar kelimeler icermeli
3. Platform diline uygun olmali (Almanca)
4. Aciklama bilgilendirici ama benzersiz olmali
5. Fiyat %5-10 yukarida olabilir (pazarlik payi)

JSON formatinda dondur:
{{
    "title": "yeni benzersiz baslik (max 80 karakter)",
    "description": "yeni benzersiz aciklama (max 1000 karakter)",
    "price": fiyat (sayi),
    "tags": ["tag1", "tag2", "tag3"],
    "seo_keywords": ["keyword1", "keyword2"]
}}

Sadece JSON dondur.
"""

            data = {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 800,
                "temperature": 0.7
            }

            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json=data,
                timeout=30
            )

            if response.status_code == 200:
                result = response.json()
                content = result['choices'][0]['message']['content'].strip()

                # JSON parse
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0]
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0]

                optimized = json.loads(content)
                print(f"[+] Icerik optimize edildi: {target_platform}")
                return optimized

        except Exception as e:
            print(f"[-] Optimizasyon hatasi: {e}")

        # Fallback - temel degisiklikler
        return {
            "title": self._make_unique_title(product.get('title', '')),
            "description": product.get('description', ''),
            "price": int(product.get('price', 0) * 1.05),
            "tags": [],
            "seo_keywords": []
        }

    def _make_unique_title(self, title):
        """Basit benzersiz baslik olustur"""
        # Kelimeleri karistir, ek ekle
        words = title.split()
        if len(words) > 3:
            words = [words[-1]] + words[:-1]
        return " ".join(words)

# ============================================
# IMAGE PROCESSOR (T5 Entegrasyonu)
# ============================================
class ImageProcessor:
    """Resim isleme - benzersiz resimler olustur"""

    def __init__(self):
        self.processed_dir = TEMP_DIR / "processed"
        self.processed_dir.mkdir(exist_ok=True)

    def make_unique(self, image_paths, product_id):
        """
        Resimleri benzersiz yap

        Args:
            image_paths: Orijinal resim dosyalari
            product_id: Urun ID

        Returns:
            list: Islenmis resim dosyalari
        """
        if not PIL_AVAILABLE:
            print("[-] PIL yuklu degil, resimler islenmedi")
            return image_paths

        processed_paths = []

        for i, img_path in enumerate(image_paths):
            try:
                img = Image.open(img_path)

                # 1. Boyut degisikligi (hafif)
                width, height = img.size
                new_width = int(width * 0.98)
                new_height = int(height * 0.98)
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

                # 2. Hafif parlaklik ayari
                enhancer = ImageEnhance.Brightness(img)
                img = enhancer.enhance(1.02)  # %2 parlaklik

                # 3. Hafif kontrast
                enhancer = ImageEnhance.Contrast(img)
                img = enhancer.enhance(1.01)  # %1 kontrast

                # 4. Metadata temizle (yeni kayit ile otomatik)

                # 5. Benzersiz isim
                hash_suffix = hashlib.md5(f"{product_id}{i}{time.time()}".encode()).hexdigest()[:8]
                new_filename = f"{product_id}_{i+1}_{hash_suffix}.jpg"
                new_path = self.processed_dir / new_filename

                # RGB'ye cevir (RGBA ise)
                if img.mode == 'RGBA':
                    img = img.convert('RGB')

                # Kaydet
                img.save(new_path, 'JPEG', quality=92)
                processed_paths.append(str(new_path))

                print(f"    Resim {i+1} islendi: {new_filename}")

            except Exception as e:
                print(f"    [-] Resim {i+1} islenemedi: {e}")
                processed_paths.append(img_path)  # Orijinali kullan

        return processed_paths

# ============================================
# PRODUCT SCRAPER
# ============================================
class ProductScraper:
    """Platform'dan urun bilgisi cek"""

    def __init__(self):
        self.driver = None

    def init_driver(self, headless=True):
        """Driver baslat"""
        if not SELENIUM_AVAILABLE:
            return False

        try:
            options = uc.ChromeOptions()
            if headless:
                options.add_argument('--headless=new')

            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--window-size=1920,1080')
            options.add_argument('--lang=de-DE')

            self.driver = uc.Chrome(options=options)
            self.driver.implicitly_wait(10)
            return True

        except Exception as e:
            print(f"[-] Driver hatasi: {e}")
            return False

    def scrape_kleinanzeigen(self, url):
        """Kleinanzeigen urun cek"""
        if not self.init_driver():
            return None

        try:
            print(f"[*] Kleinanzeigen cekiliyor: {url}")
            self.driver.get(url)
            time.sleep(5)  # Daha uzun bekle

            # Cookie popup'i kapat
            try:
                self.driver.execute_script("""
                    var buttons = document.querySelectorAll('button');
                    for (var btn of buttons) {
                        if (btn.textContent.includes('Alle akzeptieren') ||
                            btn.textContent.includes('Accept all')) {
                            btn.click();
                            break;
                        }
                    }
                """)
                time.sleep(2)
            except:
                pass

            # Debug: Sayfayi kaydet
            debug_file = TEMP_DIR / "kleinanzeigen_debug.html"
            with open(debug_file, 'w', encoding='utf-8') as f:
                f.write(self.driver.page_source)
            print(f"    [DEBUG] Sayfa kaydedildi: {debug_file}")

            # Screenshot al
            screenshot_file = TEMP_DIR / "kleinanzeigen_debug.png"
            self.driver.save_screenshot(str(screenshot_file))
            print(f"    [DEBUG] Screenshot: {screenshot_file}")

            product = {
                "source": "kleinanzeigen",
                "source_url": url,
                "scraped_at": datetime.now().isoformat()
            }

            # Baslik - farkli selectorlar dene
            title_selectors = [
                "#viewad-title",
                "h1[itemprop='name']",
                "[data-testid='ad-detail-title']",
                "h1"
            ]
            for sel in title_selectors:
                try:
                    title_el = self.driver.find_element(By.CSS_SELECTOR, sel)
                    title = title_el.text.strip()
                    if title:
                        product["title"] = title
                        break
                except:
                    continue
            if "title" not in product:
                product["title"] = ""

            # Fiyat
            price_selectors = [
                "#viewad-price",
                "[itemprop='price']",
                "[data-testid='ad-detail-price']",
                ".boxedarticle--price"
            ]
            for sel in price_selectors:
                try:
                    price_el = self.driver.find_element(By.CSS_SELECTOR, sel)
                    price_text = price_el.text.strip()
                    price_match = re.search(r'(\d+)', price_text.replace('.', ''))
                    if price_match:
                        product["price"] = int(price_match.group(1))
                        break
                except:
                    continue
            if "price" not in product:
                product["price"] = 0

            # Aciklama
            desc_selectors = [
                "#viewad-description-text",
                "[itemprop='description']",
                "[data-testid='ad-detail-description']"
            ]
            for sel in desc_selectors:
                try:
                    desc_el = self.driver.find_element(By.CSS_SELECTOR, sel)
                    desc = desc_el.text.strip()
                    if desc:
                        product["description"] = desc
                        break
                except:
                    continue
            if "description" not in product:
                product["description"] = ""

            # Resimler - farkli selectorlar
            images = []
            img_selectors = [
                "#viewad-thumbnail-list img",
                "[data-testid='ad-detail-image'] img",
                ".galleryimage-element img",
                "img[src*='img.kleinanzeigen']"
            ]
            for sel in img_selectors:
                try:
                    img_elements = self.driver.find_elements(By.CSS_SELECTOR, sel)
                    for img in img_elements:
                        src = img.get_attribute("src") or img.get_attribute("data-src")
                        if src and "kleinanzeigen" in src:
                            # Buyuk resim URL'i
                            big_src = src.replace("_57.", "_2048.").replace("_72.", "_2048.").replace("_9.", "_2048.")
                            if big_src not in images:
                                images.append(big_src)
                    if images:
                        break
                except:
                    continue

            product["images"] = images

            # Kategori
            try:
                cat_el = self.driver.find_element(By.CSS_SELECTOR, "#vap-brdcrmb a:last-child")
                product["category"] = cat_el.text.strip()
            except:
                product["category"] = ""

            print(f"[+] Cekildi: {product['title'][:40] if product['title'] else 'Baslik yok'}...")
            print(f"    Fiyat: {product['price']} EUR")
            print(f"    Resim: {len(product['images'])} adet")
            print(f"    Aciklama: {len(product.get('description', ''))} karakter")

            return product

        except Exception as e:
            print(f"[-] Scrape hatasi: {e}")
            import traceback
            traceback.print_exc()
            return None

        finally:
            if self.driver:
                try:
                    self.driver.quit()
                except:
                    pass

    def download_images(self, image_urls, product_id):
        """Resimleri indir"""
        local_paths = []

        for i, url in enumerate(image_urls):
            try:
                response = requests.get(url, timeout=30)
                if response.status_code == 200:
                    filename = f"{product_id}_orig_{i+1}.jpg"
                    filepath = TEMP_DIR / filename

                    with open(filepath, 'wb') as f:
                        f.write(response.content)

                    local_paths.append(str(filepath))
                    print(f"    Resim {i+1} indirildi")

            except Exception as e:
                print(f"    [-] Resim {i+1} indirilemedi: {e}")

        return local_paths

# ============================================
# MAIN TRANSFER CLASS
# ============================================
class ProductTransferV2:
    """Gelismis urun transfer sistemi"""

    def __init__(self):
        self.scraper = ProductScraper()
        self.optimizer = ContentOptimizer()
        self.image_processor = ImageProcessor()
        self.telegram = TelegramApproval()

    def transfer_with_approval(self, source_url, target_platform, target_account):
        """
        Onay sistemli urun transferi

        1. Urunu cek
        2. AI ile optimize et
        3. Resimleri isle
        4. Telegram'a onaya gonder
        5. Onay gelince yukle
        """
        print("\n" + "=" * 60)
        print("TATANGA - URUN TRANSFER V2")
        print("=" * 60)

        # 1. Urunu cek
        print("\n[ADIM 1] Urun bilgisi cekiliyor...")

        if "kleinanzeigen.de" in source_url:
            product = self.scraper.scrape_kleinanzeigen(source_url)
        else:
            print(f"[-] Desteklenmeyen kaynak: {source_url}")
            return None

        if not product:
            print("[-] Urun alinamadi")
            return None

        print(f"    Baslik: {product['title']}")
        print(f"    Fiyat: {product['price']} EUR")
        print(f"    Resim: {len(product.get('images', []))} adet")

        # 2. Resimleri indir
        print("\n[ADIM 2] Resimler indiriliyor...")
        product_id = f"PROD-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        original_images = self.scraper.download_images(product.get('images', []), product_id)

        if not original_images:
            print("[-] Resim indirilemedi")
            return None

        # 3. AI ile optimize et
        print("\n[ADIM 3] Icerik optimize ediliyor...")
        optimized = self.optimizer.optimize_for_platform(product, target_platform)

        print(f"    Yeni baslik: {optimized['title'][:50]}...")
        print(f"    Yeni fiyat: {optimized['price']} EUR")

        # 4. Resimleri isle
        print("\n[ADIM 4] Resimler isleniyor...")
        processed_images = self.image_processor.make_unique(original_images, product_id)

        # 5. Telegram'a onaya gonder
        print("\n[ADIM 5] Telegram'a onay istegi gonderiliyor...")

        product_data = {
            'id': product_id,
            'original': product,
            'optimized': optimized,
            'images': processed_images,
            'target_platform': target_platform,
            'target_account': target_account
        }

        self.telegram.send_approval_request(product_data)

        print("\n" + "=" * 60)
        print("ONAY BEKLENIYOR")
        print("=" * 60)
        print(f"\nUrun ID: {product_id}")
        print(f"Telegram'dan ONAYLA veya REDDET butonuna basin.")
        print(f"\nOnaylanan urunler otomatik olarak {target_platform}'e yuklenecek.")

        return product_id

# ============================================
# MAIN
# ============================================
def main():
    import argparse

    parser = argparse.ArgumentParser(description='TATANGA - Product Transfer v2')
    parser.add_argument('--source', type=str, help='Kaynak urun URL')
    parser.add_argument('--target', type=str, default='vinted', help='Hedef platform')
    parser.add_argument('--account', type=str, default='main', help='Hedef hesap')
    parser.add_argument('--test', action='store_true', help='Test modu')

    args = parser.parse_args()

    print("=" * 60)
    print("TATANGA - Product Transfer v2")
    print("SEO-uyumlu + Benzersiz Resim + Telegram Onay")
    print("=" * 60)

    if not SELENIUM_AVAILABLE:
        print("\n[-] Selenium yuklu degil!")
        print("    pip install selenium undetected-chromedriver")
        return

    transfer = ProductTransferV2()

    if args.source:
        product_id = transfer.transfer_with_approval(
            args.source,
            args.target,
            args.account
        )

        if product_id:
            print(f"\n[+] Transfer islemi baslatildi: {product_id}")
        else:
            print("\n[-] Transfer basarisiz")

    elif args.test:
        # Test icin ornek
        print("\nTest modu - ornek Kleinanzeigen URL gerekli")
        print("\nKullanim:")
        print("  python product_transfer_v2.py --source 'URL' --target vinted --account main")

    else:
        print("\nKullanim:")
        print("  python product_transfer_v2.py --source URL --target PLATFORM --account ACCOUNT")
        print("\nOrnek:")
        print("  python product_transfer_v2.py \\")
        print("    --source 'https://www.kleinanzeigen.de/s-anzeige/...' \\")
        print("    --target vinted \\")
        print("    --account main")

if __name__ == "__main__":
    main()
