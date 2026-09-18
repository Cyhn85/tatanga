#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI SEO Optimizer
Her platform icin optimize edilmis baslik ve aciklama uretir
"""

import sys
import json
import base64
import requests
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.config.credentials import AI_SERVICES

# Dizinler
BASE_DIR = Path(__file__).parent.parent
TEMP_DIR = BASE_DIR / "T6_LISTING_ENGINE" / "temp"

def analyze_product_image(image_path):
    """Urun resmini AI ile analiz et - Simdilik basit analiz"""
    # Groq gorsel desteklemiyor, basit kategori tahmini yap
    return None

def analyze_from_title(title, category):
    """Basliktan urun ozellikleri cikar"""
    analysis = {
        "product_type": "",
        "brand": "",
        "color": "",
        "condition": "iyi",
        "style": "",
        "target_audience": "unisex"
    }

    title_lower = title.lower()

    # Marka tespiti
    brands = ['zara', 'nike', 'calvin klein', 'paciotti', 'paul & shark', 'g-star', 'huawei']
    for brand in brands:
        if brand in title_lower:
            analysis['brand'] = brand.title()
            break

    # Urun tipi
    if 'schuhe' in title_lower:
        analysis['product_type'] = 'Schuhe'
        analysis['style'] = 'Casual'
    elif 'jeans' in title_lower:
        analysis['product_type'] = 'Jeans'
        analysis['style'] = 'Casual'
    elif 'jacke' in title_lower or 'weste' in title_lower:
        analysis['product_type'] = 'Jacke'
        analysis['style'] = 'Casual'
    elif 'shirt' in title_lower or 'polo' in title_lower:
        analysis['product_type'] = 'Shirt'
        analysis['style'] = 'Classic'
    elif 'brille' in title_lower:
        analysis['product_type'] = 'Brille'
        analysis['style'] = 'Modern'
    elif 'handy' in title_lower or 'huawei' in title_lower:
        analysis['product_type'] = 'Smartphone'
        analysis['style'] = 'Tech'

    # Hedef kitle
    if 'herren' in title_lower or 'man' in title_lower:
        analysis['target_audience'] = 'Herren'
    elif 'damen' in title_lower:
        analysis['target_audience'] = 'Damen'

    # Durum
    if 'neu' in title_lower:
        analysis['condition'] = 'Neu'
    elif 'top' in title_lower:
        analysis['condition'] = 'Sehr gut'

    return analysis

def generate_seo_content(product, analysis):
    """Platform bazli SEO icerigi uret - Groq API"""
    groq_config = AI_SERVICES.get('groq', {})
    api_key = groq_config.get('api_key', '')
    model = groq_config.get('model', 'llama-3.3-70b-versatile')

    if not api_key:
        print("Groq API key bulunamadi!")
        return None

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    original_title = product.get('title', '')
    category = product.get('category', '')

    prompt = f"""Urun bilgileri:
- Orijinal baslik: {original_title}
- Kategori: {category}
- Analiz: {json.dumps(analysis, ensure_ascii=False) if analysis else 'Yok'}

Bu urun icin 3 farkli platform icin SEO-optimize edilmis baslik ve aciklama uret:

1. **Vinted** (max 80 karakter baslik, 500 karakter aciklama)
   - Casual, kisa
   - Hashtag kullanma

2. **eBay** (max 80 karakter baslik, 1000 karakter aciklama)
   - Profesyonel, detayli
   - Anahtar kelimeler onemli

3. **Willhaben** (max 50 karakter baslik, 800 karakter aciklama)
   - Almanca, resmi ton
   - Acik ve net

JSON formatinda ver:
{{
  "vinted": {{
    "title": "...",
    "description": "..."
  }},
  "ebay": {{
    "title": "...",
    "description": "..."
  }},
  "willhaben": {{
    "title": "...",
    "description": "..."
  }}
}}

Sadece JSON ver, baska aciklama ekleme."""

    data = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.7,
        "max_tokens": 2048
    }

    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers,
            json=data,
            timeout=60
        )

        if response.status_code == 200:
            result = response.json()
            content = result['choices'][0]['message']['content']

            start = content.find('{')
            end = content.rfind('}') + 1
            if start != -1 and end > start:
                return json.loads(content[start:end])
        else:
            print(f"Groq API hatasi: {response.status_code}")
            print(response.text)

    except Exception as e:
        print(f"SEO uretim hatasi: {e}")

    return None

def process_products(products_path):
    """Tum urunleri isle"""
    print("=" * 60)
    print("AI SEO OPTIMIZER")
    print("=" * 60)

    # Urunleri yukle
    with open(products_path, 'r', encoding='utf-8') as f:
        products = json.load(f)

    print(f"\n{len(products)} urun islenecek\n")

    optimized_products = []

    for i, product in enumerate(products):
        print(f"\n[{i+1}/{len(products)}] {product['title'][:40]}...")

        # Basliktan analiz et
        title = product.get('title', '')
        category = product.get('category', '')

        print("  Basliktan analiz ediliyor...")
        analysis = analyze_from_title(title, category)

        if analysis:
            print(f"  Marka: {analysis.get('brand', '-')}")
            print(f"  Tip: {analysis.get('product_type', '-')}")
            print(f"  Durum: {analysis.get('condition', '-')}")

        # SEO icerigi uret
        print("  SEO icerigi uretiliyor...")
        seo_content = generate_seo_content(product, analysis)

        if seo_content:
            product['analysis'] = analysis
            product['seo'] = seo_content
            print("  Vinted: OK")
            print("  eBay: OK")
            print("  Willhaben: OK")
        else:
            print("  SEO uretimi basarisiz!")

        optimized_products.append(product)

    # Sonuclari kaydet
    output_path = TEMP_DIR / "optimized_products.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(optimized_products, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 60)
    print(f"TOPLAM {len(optimized_products)} URUN OPTIMIZE EDILDI")
    print(f"Sonuclar: {output_path}")
    print("=" * 60)

    return optimized_products

def main():
    products_path = TEMP_DIR / "parsed_products.json"

    if not products_path.exists():
        print("parsed_products.json bulunamadi!")
        print("Once parse_html_products.py calistirin.")
        return

    products = process_products(products_path)

    # Ornek cikti
    if products and products[0].get('seo'):
        print("\n\nORNEK SEO CIKTISI:")
        print("-" * 40)
        seo = products[0]['seo']

        print("\nVINTED:")
        print(f"  Baslik: {seo.get('vinted', {}).get('title', '-')}")
        print(f"  Aciklama: {seo.get('vinted', {}).get('description', '-')[:100]}...")

        print("\nEBAY:")
        print(f"  Baslik: {seo.get('ebay', {}).get('title', '-')}")

        print("\nWILLHABEN:")
        print(f"  Baslik: {seo.get('willhaben', {}).get('title', '-')}")

if __name__ == "__main__":
    main()
