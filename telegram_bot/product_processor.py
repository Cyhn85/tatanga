#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Product Processor - Tam Pipeline
1. Urunleri parse et
2. Resimleri isle (3 varyasyon)
3. AI ile SEO icerigi uret
4. Kargo ucreti ekle
5. 3 platforma yukle
6. Temizlik yap
"""

import sys
import os
import json
import shutil
from pathlib import Path
from PIL import Image, ImageEnhance, ImageFilter

sys.path.insert(0, str(Path(__file__).parent.parent))

# Dizinler
BASE_DIR = Path(__file__).parent.parent
TEMP_DIR = BASE_DIR / "T6_LISTING_ENGINE" / "temp"
DOWNLOADS_DIR = TEMP_DIR / "downloads"
VARIANTS_DIR = TEMP_DIR / "variants"
VARIANTS_DIR.mkdir(exist_ok=True)

# Almanya -> Avusturya GLS Kargo Ucretleri (Online Franking)
# GLS DHL'den daha uygun: https://www.gls-pakete.de
SHIPPING_COSTS = {
    'small': 11.80,   # 31.5kg'a kadar, en kisa+uzun kenar max 65cm
    'medium': 13.50,  # 31.5kg'a kadar, en kisa+uzun kenar max 90cm
    'large': 16.50,   # 31.5kg'a kadar, en kisa+uzun kenar max 120cm
}
# Not: DHL alternatif - 2kg: 14.49€, 5kg: 17.49€, 10kg: 22.49€

def estimate_shipping(category, product_type=None):
    """Urun kategorisine gore kargo ucreti tahmin et"""
    category_lower = (category or '').lower()

    # Kucuk urunler
    if any(x in category_lower for x in ['accessoires', 'brille', 'schmuck', 'uhr']):
        return SHIPPING_COSTS['small']

    # Orta boyut urunler
    if any(x in category_lower for x in ['schuhe', 'handy', 'telefon', 'tasche']):
        return SHIPPING_COSTS['medium']

    # Buyuk urunler
    if any(x in category_lower for x in ['jacke', 'mantel', 'koffer']):
        return SHIPPING_COSTS['large']

    # Kiyafetler icin varsayilan
    return SHIPPING_COSTS['small']

def create_image_variants(image_path, ad_id):
    """Bir resimden 3 farkli varyasyon olustur"""
    variants = []

    try:
        img = Image.open(image_path)

        # Varyant 1: Orijinal (hafif parlaklik)
        v1 = img.copy()
        enhancer = ImageEnhance.Brightness(v1)
        v1 = enhancer.enhance(1.05)
        v1_path = VARIANTS_DIR / f"{ad_id}_var1_bright.jpg"
        v1.save(v1_path, "JPEG", quality=95)
        variants.append(str(v1_path))

        # Varyant 2: Kontrast arttirilmis
        v2 = img.copy()
        enhancer = ImageEnhance.Contrast(v2)
        v2 = enhancer.enhance(1.1)
        enhancer = ImageEnhance.Sharpness(v2)
        v2 = enhancer.enhance(1.2)
        v2_path = VARIANTS_DIR / f"{ad_id}_var2_sharp.jpg"
        v2.save(v2_path, "JPEG", quality=95)
        variants.append(str(v2_path))

        # Varyant 3: Sicak tonlar
        v3 = img.copy()
        enhancer = ImageEnhance.Color(v3)
        v3 = enhancer.enhance(1.15)
        v3_path = VARIANTS_DIR / f"{ad_id}_var3_warm.jpg"
        v3.save(v3_path, "JPEG", quality=95)
        variants.append(str(v3_path))

        print(f"  3 varyant olusturuldu: {ad_id}")

    except Exception as e:
        print(f"  Varyant olusturma hatasi: {e}")
        # Hata durumunda orijinali kullan
        variants = [image_path] * 3

    return variants

def process_all_products():
    """Tum urunleri isle"""
    print("=" * 60)
    print("PRODUCT PROCESSOR")
    print("=" * 60)

    # Parsed urunleri yukle
    parsed_path = TEMP_DIR / "parsed_products.json"
    if not parsed_path.exists():
        print("parsed_products.json bulunamadi!")
        print("Once parse_html_products.py calistirin.")
        return None

    with open(parsed_path, 'r', encoding='utf-8') as f:
        products = json.load(f)

    print(f"\n{len(products)} urun islenecek\n")

    processed = []

    for i, product in enumerate(products):
        ad_id = product.get('ad_id', f'unknown_{i}')
        title = product.get('title', '')[:40]
        category = product.get('category', '')

        print(f"\n[{i+1}/{len(products)}] {title}...")

        # 1. Resim varyantlari olustur
        local_images = product.get('local_images', [])
        if local_images:
            variants = create_image_variants(local_images[0], ad_id)
            product['image_variants'] = variants
        else:
            product['image_variants'] = []

        # 2. Kargo ucreti hesapla
        shipping = estimate_shipping(category)
        product['shipping_de_at'] = shipping
        print(f"  Kargo (DE->AT): {shipping} EUR")

        # 3. Platform bazli fiyatlar
        base_price = product.get('price', 0)
        if base_price == 0:
            # Fiyat yoksa kategoriye gore tahmin
            if 'schuhe' in category.lower():
                base_price = 30
            elif 'jacke' in category.lower() or 'jeans' in category.lower():
                base_price = 25
            else:
                base_price = 20

        product['platform_prices'] = {
            'vinted': base_price,  # Alici kargo oder
            'ebay': base_price + 5,  # eBay komisyonu icin
            'willhaben': base_price + shipping  # Kargo dahil
        }

        print(f"  Fiyatlar: Vinted={base_price}, eBay={base_price+5}, Willhaben={base_price+shipping}")

        processed.append(product)

    # Sonuclari kaydet
    output_path = TEMP_DIR / "processed_products.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(processed, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 60)
    print(f"TOPLAM {len(processed)} URUN ISLENDI")
    print(f"Sonuclar: {output_path}")
    print("=" * 60)

    return processed

def cleanup_temp_files(keep_json=True):
    """Gecici dosyalari temizle"""
    print("\n" + "=" * 60)
    print("DOSYA TEMIZLIGI")
    print("=" * 60)

    deleted = 0

    # Screenshot'lari sil
    for ext in ['*.png', '*.html']:
        for f in TEMP_DIR.glob(ext):
            try:
                f.unlink()
                deleted += 1
                print(f"  Silindi: {f.name}")
            except:
                pass

    # Downloads klasorunu temizle
    if DOWNLOADS_DIR.exists():
        for f in DOWNLOADS_DIR.glob('*'):
            try:
                f.unlink()
                deleted += 1
            except:
                pass
        print(f"  Downloads klasoru temizlendi")

    # Variants klasorunu temizle
    if VARIANTS_DIR.exists():
        for f in VARIANTS_DIR.glob('*'):
            try:
                f.unlink()
                deleted += 1
            except:
                pass
        print(f"  Variants klasoru temizlendi")

    if not keep_json:
        for f in TEMP_DIR.glob('*.json'):
            try:
                f.unlink()
                deleted += 1
                print(f"  Silindi: {f.name}")
            except:
                pass

    print(f"\nToplam {deleted} dosya silindi")

def main():
    # 1. Urunleri isle
    products = process_all_products()

    if not products:
        return

    # 2. AI SEO optimizer'i calistir (ayri script)
    print("\n\nSimdi ai_seo_optimizer.py calistirilabilir.")
    print("python ai_seo_optimizer.py")

    # Ozet
    print("\n" + "=" * 60)
    print("OZET")
    print("=" * 60)

    print(f"\nToplam: {len(products)} urun")
    print(f"Varyant: {len(products) * 3} resim")

    total_willhaben = sum(p['platform_prices']['willhaben'] for p in products)
    print(f"\nWillhaben toplam deger: {total_willhaben:.2f} EUR")
    print(f"Kargo maliyeti dahil!")

    print("\nSonraki adimlar:")
    print("1. python ai_seo_optimizer.py  # SEO icerigi uret")
    print("2. Platform yukleme scripti")
    print("3. cleanup_temp_files()  # Basariliysa temizlik")

if __name__ == "__main__":
    main()
