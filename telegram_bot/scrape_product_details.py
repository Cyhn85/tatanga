#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Kleinanzeigen Urun Detay Scraper
Her urunun detay sayfasindan tam bilgi ceker
"""

import sys
import time
import json
import re
import requests
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.config.credentials import KLEINANZEIGEN, AI_SERVICES

TEMP_DIR = Path(__file__).parent.parent / "T6_LISTING_ENGINE" / "temp"
DOWNLOADS_DIR = TEMP_DIR / "downloads"
DOWNLOADS_DIR.mkdir(exist_ok=True)

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    import undetected_chromedriver as uc
except ImportError:
    print("Selenium yuklu degil!")
    sys.exit(1)

class KleinanzeigenScraper:
    def __init__(self):
        self.driver = None
        self.products = []

    def init_driver(self):
        options = uc.ChromeOptions()
        options.add_argument('--start-maximized')
        self.driver = uc.Chrome(options=options)
        return True

    def login(self):
        """Kleinanzeigen'e login ol"""
        print("Login yapiliyor...")
        self.driver.get("https://www.kleinanzeigen.de/m-einloggen.html")
        time.sleep(3)

        # Cookie popup
        self._close_popups()

        # Login
        account = KLEINANZEIGEN['accounts'][0]
        try:
            email = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "login-email"))
            )
            email.send_keys(account['email'])

            pwd = self.driver.find_element(By.ID, "login-password")
            pwd.send_keys(account['password'])

            btn = self.driver.find_element(By.ID, "login-submit")
            btn.click()
            time.sleep(5)

            self._close_popups()
            print("Login basarili!")
            return True
        except Exception as e:
            print(f"Login hatasi: {e}")
            return False

    def _close_popups(self):
        """Popup'lari kapat"""
        for _ in range(3):
            try:
                self.driver.execute_script("""
                    var btns = document.querySelectorAll('button');
                    for (var b of btns) {
                        var txt = b.textContent.toLowerCase();
                        if (txt.includes('akzeptieren') || txt.includes('schliessen')) {
                            b.click();
                            return;
                        }
                    }
                """)
                time.sleep(0.5)
            except:
                pass

    def get_product_urls(self):
        """Tum urun URL'lerini al"""
        print("\nUrun listesi aliniyor...")
        self.driver.get("https://www.kleinanzeigen.de/m-meine-anzeigen.html")
        time.sleep(3)
        self._close_popups()

        # Scroll to load all
        for i in range(5):
            self.driver.execute_script(f"window.scrollTo(0, {i * 1000})")
            time.sleep(0.5)

        # URL'leri cek
        urls = []
        try:
            # Farkli selectorlari dene
            selectors = [
                "li[data-testid='ad-card'][data-adid]",
                "li[data-adid]",
                "[data-testid='ad-card']",
                "ul#my-manageitems-adlist li"
            ]

            items = []
            for sel in selectors:
                items = self.driver.find_elements(By.CSS_SELECTOR, sel)
                if items:
                    print(f"Selector '{sel}' ile {len(items)} urun karti bulundu")
                    break

            if not items:
                # JavaScript ile dene
                items = self.driver.execute_script("""
                    return Array.from(document.querySelectorAll('li[data-adid]'));
                """)
                print(f"JS ile {len(items)} urun bulundu")

            for item in items:
                try:
                    # h3 icindeki a elementi
                    link = item.find_element(By.CSS_SELECTOR, "h3 a")
                    url = link.get_attribute("href")
                    if url and '/s-anzeige/' in url:
                        urls.append(url)
                        print(f"  URL: {url[:60]}...")
                except Exception as e:
                    # Alternatif: herhangi bir anzeige linki
                    try:
                        link = item.find_element(By.CSS_SELECTOR, "a[href*='/s-anzeige/']")
                        url = link.get_attribute("href")
                        if url and url not in urls:
                            urls.append(url)
                            print(f"  URL (alt): {url[:60]}...")
                    except:
                        continue

        except Exception as e:
            print(f"URL alma hatasi: {e}")
            import traceback
            traceback.print_exc()

        print(f"{len(urls)} urun URL'si alindi")
        return urls

    def scrape_product_detail(self, url):
        """Tek urunun detaylarini cek"""
        print(f"\nDetay aliniyor: {url[:60]}...")
        self.driver.get(url)
        time.sleep(3)
        self._close_popups()

        product = {
            'url': url,
            'title': '',
            'price': 0,
            'description': '',
            'condition': '',
            'category': '',
            'location': '',
            'images': [],
            'seller': '',
            'ad_id': ''
        }

        try:
            # Baslik
            try:
                title_el = self.driver.find_element(By.CSS_SELECTOR, "h1, [data-testid='ad-title']")
                product['title'] = title_el.text.strip()
            except:
                pass

            # Fiyat
            try:
                price_el = self.driver.find_element(By.CSS_SELECTOR, "[class*='price'], h2[class*='price']")
                price_text = price_el.text.strip()
                match = re.search(r'(\d+(?:[.,]\d+)?)', price_text.replace('.', ''))
                if match:
                    product['price'] = float(match.group(1).replace(',', '.'))
            except:
                pass

            # Aciklama
            try:
                desc_el = self.driver.find_element(By.CSS_SELECTOR, "[data-testid='ad-description'], [id='viewad-description']")
                product['description'] = desc_el.text.strip()
            except:
                pass

            # Kategori
            try:
                cat_el = self.driver.find_element(By.CSS_SELECTOR, "[data-testid='ad-category'], [class*='breadcrumb']")
                product['category'] = cat_el.text.strip()
            except:
                pass

            # Konum
            try:
                loc_el = self.driver.find_element(By.CSS_SELECTOR, "[data-testid='ad-location'], [id='viewad-locality']")
                product['location'] = loc_el.text.strip()
            except:
                pass

            # Resimler - tum buyuk resimleri al
            try:
                img_elements = self.driver.find_elements(By.CSS_SELECTOR, "img[src*='kleinanzeigen.de/api'], [data-testid='gallery-image'] img")
                for img in img_elements:
                    src = img.get_attribute("src")
                    if src and 'kleinanzeigen.de' in src:
                        # Yuksek cozunurluk
                        src = re.sub(r'\?rule=\$_\d+', '?rule=$_57', src)
                        if src not in product['images']:
                            product['images'].append(src)
            except:
                pass

            # Ad ID
            match = re.search(r'/(\d+)-', url)
            if match:
                product['ad_id'] = match.group(1)

            print(f"  Baslik: {product['title'][:50]}...")
            print(f"  Fiyat: {product['price']} EUR")
            print(f"  Resim: {len(product['images'])} adet")

        except Exception as e:
            print(f"  Detay hatasi: {e}")

        return product

    def download_images(self, product):
        """Urun resimlerini indir"""
        downloaded = []
        ad_id = product.get('ad_id', 'unknown')

        for i, url in enumerate(product['images'][:10]):  # Max 10 resim
            try:
                response = requests.get(url, timeout=30)
                if response.status_code == 200:
                    filename = f"PROD-{ad_id}_img_{i+1}.jpg"
                    filepath = DOWNLOADS_DIR / filename
                    with open(filepath, 'wb') as f:
                        f.write(response.content)
                    downloaded.append(str(filepath))
            except:
                continue

        product['local_images'] = downloaded
        print(f"  {len(downloaded)} resim indirildi")
        return downloaded

    def run(self):
        """Ana scrape islemi"""
        print("=" * 60)
        print("KLEINANZEIGEN DETAY SCRAPER")
        print("=" * 60)

        if not self.init_driver():
            return []

        try:
            if not self.login():
                return []

            urls = self.get_product_urls()
            if not urls:
                print("Urun bulunamadi!")
                return []

            # Her urunun detayini al
            for i, url in enumerate(urls):
                print(f"\n[{i+1}/{len(urls)}]")
                product = self.scrape_product_detail(url)

                if product['title']:
                    # Resimleri indir
                    self.download_images(product)
                    self.products.append(product)

                time.sleep(2)  # Rate limiting

            # JSON kaydet
            output_path = TEMP_DIR / "scraped_products.json"
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(self.products, f, ensure_ascii=False, indent=2)
            print(f"\n\nSonuclar kaydedildi: {output_path}")

            print("\n" + "=" * 60)
            print(f"TOPLAM {len(self.products)} URUN CEKILDI")
            print("=" * 60)

            return self.products

        finally:
            if self.driver:
                self.driver.quit()

def main():
    scraper = KleinanzeigenScraper()
    products = scraper.run()

    if products:
        print("\n\nCekilen Urunler:")
        for i, p in enumerate(products):
            print(f"\n{i+1}. {p['title']}")
            print(f"   Fiyat: {p['price']} EUR")
            print(f"   Kategori: {p['category']}")
            print(f"   Aciklama: {p['description'][:100]}..." if p['description'] else "   Aciklama: -")
            print(f"   Resim: {len(p.get('local_images', []))} adet")

if __name__ == "__main__":
    main()
