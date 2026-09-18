#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HTML'den urun verilerini cek - BeautifulSoup ile
Selenium'a ihtiyac yok
"""

import sys
import json
import re
import requests
import hashlib
from pathlib import Path
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent.parent))

# Dizinler
BASE_DIR = Path(__file__).parent.parent
TEMP_DIR = BASE_DIR / "T6_LISTING_ENGINE" / "temp"
DOWNLOADS_DIR = TEMP_DIR / "downloads"
DOWNLOADS_DIR.mkdir(exist_ok=True)

def parse_kleinanzeigen_html(html_path):
    """HTML dosyasindan urun verilerini cek"""
    print("=" * 60)
    print("KLEINANZEIGEN HTML PARSER")
    print("=" * 60)

    # HTML oku
    with open(html_path, 'r', encoding='utf-8') as f:
        html = f.read()

    soup = BeautifulSoup(html, 'html.parser')

    # Urun kartlarini bul
    products = []

    # data-adid olan tum li elementlerini bul
    items = soup.find_all('li', attrs={'data-adid': True})
    print(f"\n{len(items)} urun karti bulundu\n")

    for item in items:
        try:
            ad_id = item.get('data-adid', '')

            # Baslik - h3 icindeki a
            title = ""
            title_el = item.find('h3')
            if title_el:
                link = title_el.find('a')
                if link:
                    title = link.get_text(strip=True)

            # URL
            url = ""
            link_el = item.find('a', href=lambda x: x and '/s-anzeige/' in x)
            if link_el:
                url = link_el.get('href', '')
                if not url.startswith('http'):
                    url = 'https://www.kleinanzeigen.de' + url

            # Kategori
            category = ""
            cat_el = item.find('div', class_=lambda x: x and 'text-bodySmall' in x)
            if cat_el:
                category = cat_el.get_text(strip=True)

            # Resim
            images = []
            img_el = item.find('img', attrs={'data-testid': 'ad-image'})
            if img_el:
                img_src = img_el.get('src', '')
                if img_src:
                    # Yuksek cozunurluk
                    img_src = re.sub(r'\?rule=\$_\d+', '?rule=$_57', img_src)
                    images.append(img_src)

            # Resim sayisi
            img_count = 0
            count_el = item.find('div', class_=lambda x: x and 'absolute' in str(x) and 'right-xsmall' in str(x))
            if count_el:
                try:
                    img_count = int(count_el.get_text(strip=True))
                except:
                    img_count = len(images)

            if title:
                product = {
                    'ad_id': ad_id,
                    'title': title,
                    'url': url,
                    'category': category,
                    'images': images,
                    'image_count': img_count if img_count else len(images),
                    'price': 0,  # Liste sayfasinda fiyat yok, detay sayfasindan alinmali
                    'description': ''  # Detay sayfasindan alinmali
                }
                products.append(product)

                print(f"{len(products)}. {title[:50]}")
                print(f"   ID: {ad_id}")
                print(f"   Kategori: {category}")
                print(f"   Resim: {img_count or len(images)} adet")
                print()

        except Exception as e:
            print(f"Hata: {e}")
            continue

    return products

def download_product_images(products):
    """Urun resimlerini indir"""
    print("\n" + "=" * 60)
    print("RESIMLER INDIRILIYOR")
    print("=" * 60)

    for product in products:
        ad_id = product.get('ad_id', 'unknown')
        downloaded = []

        for i, url in enumerate(product.get('images', [])[:10]):
            try:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
                response = requests.get(url, headers=headers, timeout=30)

                if response.status_code == 200:
                    filename = f"PROD-{ad_id}_img_{i+1}.jpg"
                    filepath = DOWNLOADS_DIR / filename

                    with open(filepath, 'wb') as f:
                        f.write(response.content)

                    downloaded.append(str(filepath))
                    print(f"  {filename} indirildi")
            except Exception as e:
                print(f"  Hata: {e}")
                continue

        product['local_images'] = downloaded

    return products

def main():
    # HTML dosyasini bul
    html_files = [
        TEMP_DIR / "kleinanzeigen_products.html",
        TEMP_DIR / "kleinanzeigen_page.html"
    ]

    html_path = None
    for f in html_files:
        if f.exists():
            html_path = f
            break

    if not html_path:
        print("HTML dosyasi bulunamadi!")
        return

    print(f"HTML: {html_path}")

    # Parse et
    products = parse_kleinanzeigen_html(html_path)

    if not products:
        print("\nUrun bulunamadi!")
        return

    # Resimleri indir
    products = download_product_images(products)

    # Sonuclari kaydet
    output_path = TEMP_DIR / "parsed_products.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(products, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 60)
    print(f"TOPLAM {len(products)} URUN CEKILDI")
    print(f"Sonuclar: {output_path}")
    print("=" * 60)

    return products

if __name__ == "__main__":
    main()
