#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TATANGA - T5 Image Processor
Resim isleme, aci degistirme, platform varyantlari
"""

import os
import sys
import json
import random
import hashlib
from pathlib import Path
from datetime import datetime
from PIL import Image, ImageEnhance, ImageFilter, ExifTags
import requests

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.config.credentials import TELEGRAM

# ============================================
# CONFIGURATION
# ============================================
INPUT_DIR = Path(__file__).parent / "input"
OUTPUT_DIR = Path(__file__).parent / "output"
LOGS_DIR = Path(__file__).parent / "logs"

# Platform configurations
PLATFORM_CONFIGS = {
    "vinted": {
        "max_images": 20,
        "max_size": (1920, 1920),
        "format": "JPEG",
        "quality": 85
    },
    "kleinanzeigen": {
        "max_images": 20,
        "max_size": (1600, 1200),
        "format": "JPEG",
        "quality": 80
    },
    "ebay": {
        "max_images": 12,
        "max_size": (1600, 1600),
        "format": "JPEG",
        "quality": 90
    },
    "willhaben": {
        "max_images": 20,
        "max_size": (1200, 1200),
        "format": "JPEG",
        "quality": 85
    }
}

# Ensure directories exist
INPUT_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

# ============================================
# TELEGRAM NOTIFICATION
# ============================================
def send_telegram(message):
    """Telegram'a mesaj gonder"""
    url = f"https://api.telegram.org/bot{TELEGRAM['bot_token']}/sendMessage"
    data = {
        "chat_id": TELEGRAM["admin_chat_id"],
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, data=data)
    except Exception as e:
        print(f"Telegram hatasi: {e}")

# ============================================
# IMAGE PROCESSING FUNCTIONS
# ============================================

def remove_metadata(image):
    """
    Resimden EXIF ve diger metadata'yi temizle
    """
    # Copy image data without metadata
    data = list(image.getdata())
    clean_image = Image.new(image.mode, image.size)
    clean_image.putdata(data)
    return clean_image

def rotate_image(image, angle):
    """
    Resmi belirli bir aciyla dondur
    """
    return image.rotate(angle, expand=True, fillcolor='white')

def apply_slight_rotation(image, max_angle=3):
    """
    Hafif rastgele rotasyon uygula (duplikat tespitinden kacmak icin)
    """
    angle = random.uniform(-max_angle, max_angle)
    return image.rotate(angle, expand=True, fillcolor='white')

def apply_zoom_out(image, factor=0.95):
    """
    Resmi hafifce zoom out yap (kenarlara beyaz padding ekle)
    """
    new_size = (int(image.width * factor), int(image.height * factor))
    resized = image.resize(new_size, Image.Resampling.LANCZOS)

    # Create new image with white background
    new_image = Image.new('RGB', image.size, 'white')

    # Paste resized image in center
    x = (image.width - new_size[0]) // 2
    y = (image.height - new_size[1]) // 2
    new_image.paste(resized, (x, y))

    return new_image

def apply_subtle_filter(image):
    """
    Hafif filtre uygula (brightness/contrast degisikligi)
    """
    # Random subtle adjustments
    brightness = random.uniform(0.97, 1.03)
    contrast = random.uniform(0.98, 1.02)

    enhancer = ImageEnhance.Brightness(image)
    image = enhancer.enhance(brightness)

    enhancer = ImageEnhance.Contrast(image)
    image = enhancer.enhance(contrast)

    return image

def resize_for_platform(image, platform):
    """
    Platform icin uygun boyuta getir
    """
    config = PLATFORM_CONFIGS.get(platform, PLATFORM_CONFIGS["vinted"])
    max_size = config["max_size"]

    # Calculate new size maintaining aspect ratio
    ratio = min(max_size[0] / image.width, max_size[1] / image.height)
    if ratio < 1:
        new_size = (int(image.width * ratio), int(image.height * ratio))
        image = image.resize(new_size, Image.Resampling.LANCZOS)

    return image

def create_platform_variant(image, platform, variant_index=0):
    """
    Platform icin ozel varyant olustur
    Her platform farkli hash uretecek sekilde
    """
    # Convert to RGB if necessary
    if image.mode != 'RGB':
        image = image.convert('RGB')

    # Remove metadata
    image = remove_metadata(image)

    # Apply platform-specific variations
    if platform == "vinted":
        # Slight rotation for Vinted
        image = apply_slight_rotation(image, max_angle=2)
        image = apply_subtle_filter(image)

    elif platform == "kleinanzeigen":
        # Zoom out slightly for Kleinanzeigen
        image = apply_zoom_out(image, factor=0.96)
        image = apply_subtle_filter(image)

    elif platform == "ebay":
        # Different rotation for eBay
        image = apply_slight_rotation(image, max_angle=1.5)
        # Slight sharpening
        image = image.filter(ImageFilter.UnsharpMask(radius=1, percent=50))

    elif platform == "willhaben":
        # Combination for Willhaben
        image = apply_zoom_out(image, factor=0.97)
        image = apply_slight_rotation(image, max_angle=1)

    # Resize for platform
    image = resize_for_platform(image, platform)

    return image

def calculate_image_hash(image_path):
    """
    Resim icin hash hesapla (duplikat kontrolu icin)
    """
    with open(image_path, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()

def process_product_images(product_id, image_paths, platforms=None):
    """
    Urun resimlerini tum platformlar icin isle

    Args:
        product_id: Urun ID
        image_paths: Kaynak resim dosyalarinin listesi
        platforms: Hedef platformlar (None = hepsi)

    Returns:
        dict: Her platform icin islenmis resim yollari
    """
    if platforms is None:
        platforms = list(PLATFORM_CONFIGS.keys())

    results = {}
    processed_count = 0

    # Create output folder for this product
    product_output_dir = OUTPUT_DIR / product_id
    product_output_dir.mkdir(exist_ok=True)

    print(f"\n[*] Urun resimleri isleniyor: {product_id}")
    print(f"    Kaynak resim sayisi: {len(image_paths)}")
    print(f"    Hedef platformlar: {', '.join(platforms)}")

    for platform in platforms:
        platform_dir = product_output_dir / platform
        platform_dir.mkdir(exist_ok=True)

        config = PLATFORM_CONFIGS[platform]
        max_images = config["max_images"]
        quality = config["quality"]

        platform_images = []

        for i, img_path in enumerate(image_paths[:max_images]):
            try:
                # Load image
                image = Image.open(img_path)

                # Create platform variant
                processed = create_platform_variant(image, platform, i)

                # Save
                output_filename = f"{product_id}_{platform}_{i+1:02d}.jpg"
                output_path = platform_dir / output_filename

                processed.save(
                    output_path,
                    format=config["format"],
                    quality=quality,
                    optimize=True
                )

                platform_images.append(str(output_path))
                processed_count += 1

            except Exception as e:
                print(f"    [-] Hata ({platform}, resim {i+1}): {e}")

        results[platform] = platform_images
        print(f"    [+] {platform}: {len(platform_images)} resim islendi")

    # Log
    log_entry = {
        "product_id": product_id,
        "timestamp": datetime.now().isoformat(),
        "source_count": len(image_paths),
        "platforms": platforms,
        "results": {p: len(imgs) for p, imgs in results.items()},
        "total_processed": processed_count
    }

    log_file = LOGS_DIR / f"{datetime.now().strftime('%Y%m%d')}_processing.log"
    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

    # Telegram notification
    msg = f"""
Resim Isleme Tamamlandi!

Urun: {product_id}
Kaynak: {len(image_paths)} resim
Islenen: {processed_count} dosya

Platformlar:
{chr(10).join([f"- {p}: {len(imgs)}" for p, imgs in results.items()])}

Cikti: {product_output_dir}
    """
    send_telegram(msg)

    return results

def batch_process_from_stock():
    """
    Stock manager'dan gelen urunleri toplu isle
    """
    stock_file = Path(__file__).parent.parent / "T4_STOCK_MANAGER" / "output" / "stock_products.json"

    if not stock_file.exists():
        print("[-] Stock dosyasi bulunamadi")
        return

    with open(stock_file, 'r', encoding='utf-8') as f:
        products = json.load(f)

    # Sadece pending durumundakileri isle
    pending = [p for p in products if p.get('status') == 'pending']

    if not pending:
        print("[*] Islenecek urun yok")
        return

    print(f"\n[*] {len(pending)} urun islenecek")

    for product in pending:
        product_id = product['id']
        images = product.get('images', [])

        if not images:
            continue

        # Resimleri isle
        results = process_product_images(product_id, images)

        # Durumu guncelle
        product['status'] = 'processed'
        product['processed_images'] = results
        product['processed_at'] = datetime.now().isoformat()

    # Kaydet
    with open(stock_file, 'w', encoding='utf-8') as f:
        json.dump(products, f, ensure_ascii=False, indent=2)

    print(f"\n[+] Toplu isleme tamamlandi")

# ============================================
# CLI INTERFACE
# ============================================

def main():
    import argparse

    parser = argparse.ArgumentParser(description='TATANGA - T5 Image Processor')
    parser.add_argument('--batch', action='store_true', help='Stock urunlerini toplu isle')
    parser.add_argument('--product', type=str, help='Tek urun ID')
    parser.add_argument('--images', nargs='+', help='Resim dosyalari')
    parser.add_argument('--platforms', nargs='+', choices=list(PLATFORM_CONFIGS.keys()),
                       help='Hedef platformlar')

    args = parser.parse_args()

    print("=" * 50)
    print("TATANGA - T5 Image Processor")
    print("=" * 50)

    if args.batch:
        batch_process_from_stock()

    elif args.product and args.images:
        process_product_images(args.product, args.images, args.platforms)

    else:
        print("\nKullanim:")
        print("  Toplu isleme: python processor.py --batch")
        print("  Tek urun:     python processor.py --product STOCK-001 --images img1.jpg img2.jpg")
        print("  Platform:     python processor.py --product STOCK-001 --images img1.jpg --platforms vinted ebay")
        print("\nPlatformlar:", list(PLATFORM_CONFIGS.keys()))

if __name__ == "__main__":
    main()
