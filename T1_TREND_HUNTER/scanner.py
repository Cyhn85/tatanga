#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TATANGA - T1 Trend Hunter
Kategori bazli trend urun tarama ve analiz sistemi
"""

import os
import sys
import json
import time
import requests
from pathlib import Path
from datetime import datetime, timedelta
from collections import Counter

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.config.credentials import TELEGRAM, AI_SERVICES
from shared.config.settings import PLATFORMS, SCRAPING

# ============================================
# CONFIGURATION
# ============================================
OUTPUT_DIR = Path(__file__).parent / "output"
LOGS_DIR = Path(__file__).parent / "logs"

OUTPUT_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

# Trend kategorileri (Almanya pazari icin)
TREND_CATEGORIES = {
    "fashion": {
        "keywords": ["Nike", "Adidas", "Puma", "Ralph Lauren", "Tommy Hilfiger", "Hugo Boss", "Lacoste"],
        "types": ["Sneaker", "Jacke", "Hemd", "Hose", "Pullover"],
        "min_margin": 30  # Minimum kar marji %
    },
    "luxury": {
        "keywords": ["Gucci", "Louis Vuitton", "Prada", "Burberry", "Versace", "Balenciaga"],
        "types": ["Tasche", "Schuhe", "Accessoires", "Gurtel"],
        "min_margin": 40
    },
    "vintage": {
        "keywords": ["Vintage", "Retro", "80er", "90er", "Y2K", "Old School"],
        "types": ["Jeans", "Lederjacke", "Sportjacke", "Trainingsanzug"],
        "min_margin": 50
    },
    "streetwear": {
        "keywords": ["Supreme", "Off-White", "Stussy", "Champion", "Carhartt", "Dickies"],
        "types": ["Hoodie", "T-Shirt", "Cargo", "Beanie"],
        "min_margin": 35
    }
}

# Platform URL templates
VINTED_SEARCH_URL = "https://www.vinted.de/catalog?search_text={query}&order=newest_first"
KLEINANZEIGEN_SEARCH_URL = "https://www.kleinanzeigen.de/s-{query}/k0"

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
# GOOGLE TRENDS INTEGRATION
# ============================================
def get_google_trends(keywords, timeframe='now 7-d', geo='DE'):
    """
    Google Trends verisi cek
    pytrends kullanir
    """
    try:
        from pytrends.request import TrendReq

        pytrends = TrendReq(hl='de-DE', tz=60)
        pytrends.build_payload(keywords[:5], cat=0, timeframe=timeframe, geo=geo)

        interest = pytrends.interest_over_time()

        if interest.empty:
            return {}

        # Son 7 gunun ortalamasini al
        trends = {}
        for kw in keywords[:5]:
            if kw in interest.columns:
                trends[kw] = int(interest[kw].mean())

        return trends

    except Exception as e:
        print(f"Google Trends hatasi: {e}")
        return {}

# ============================================
# VINTED SCANNER
# ============================================
class VintedTrendScanner:
    """Vinted trend tarayici"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'de-DE,de;q=0.9'
        })
        self.base_url = "https://www.vinted.de/api/v2"

    def search_items(self, query, page=1, per_page=48):
        """
        Vinted'de urun ara
        """
        url = f"{self.base_url}/catalog/items"
        params = {
            'search_text': query,
            'page': page,
            'per_page': per_page,
            'order': 'newest_first',
            'catalog_ids': '',  # Tum kategoriler
            'time': '3600',  # Son 1 saat
        }

        try:
            resp = self.session.get(url, params=params, timeout=10)
            if resp.status_code == 200:
                return resp.json().get('items', [])
        except Exception as e:
            print(f"Vinted arama hatasi: {e}")

        return []

    def analyze_category(self, category_name, category_config):
        """
        Kategori analizi yap
        """
        results = {
            "category": category_name,
            "timestamp": datetime.now().isoformat(),
            "brands": {},
            "types": {},
            "price_ranges": [],
            "hot_items": []
        }

        # Her marka icin ara
        for brand in category_config.get('keywords', []):
            items = self.search_items(brand, per_page=24)

            if items:
                results["brands"][brand] = {
                    "count": len(items),
                    "avg_price": sum(float(i.get('price', {}).get('amount', 0)) for i in items) / len(items) if items else 0,
                    "newest": items[0] if items else None
                }

            time.sleep(1)  # Rate limiting

        # En populer urunleri bul (favorilere gore)
        all_items = []
        for brand_data in results["brands"].values():
            if brand_data.get("newest"):
                all_items.append(brand_data["newest"])

        # Favori sayisina gore sirala
        all_items.sort(key=lambda x: x.get('favourite_count', 0), reverse=True)
        results["hot_items"] = all_items[:10]

        return results

# ============================================
# KLEINANZEIGEN SCANNER
# ============================================
class KleinanzeigenTrendScanner:
    """Kleinanzeigen trend tarayici"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })

    def search_items(self, query):
        """
        Kleinanzeigen'de urun ara (HTML scraping)
        """
        # Bu kisim Selenium gerektirir
        # Simdilik placeholder
        return []

# ============================================
# TREND ANALYZER
# ============================================
class TrendAnalyzer:
    """Trend analiz motoru"""

    def __init__(self):
        self.vinted = VintedTrendScanner()

    def scan_all_categories(self):
        """
        Tum kategorileri tara
        """
        print("\n" + "=" * 50)
        print("TATANGA - T1 Trend Hunter")
        print("=" * 50)
        print(f"\nTarama basliyor... {datetime.now().strftime('%Y-%m-%d %H:%M')}")

        all_results = {
            "scan_time": datetime.now().isoformat(),
            "categories": {}
        }

        for cat_name, cat_config in TREND_CATEGORIES.items():
            print(f"\n[*] Kategori: {cat_name}")

            results = self.vinted.analyze_category(cat_name, cat_config)
            all_results["categories"][cat_name] = results

            # Ozet goster
            total_items = sum(b.get('count', 0) for b in results['brands'].values())
            print(f"    Bulunan urun: {total_items}")

            time.sleep(2)  # Kategoriler arasi bekleme

        return all_results

    def find_arbitrage_opportunities(self, results):
        """
        Arbitraj firsatlarini bul
        """
        opportunities = []

        for cat_name, cat_data in results.get("categories", {}).items():
            min_margin = TREND_CATEGORIES.get(cat_name, {}).get('min_margin', 30)

            for item in cat_data.get("hot_items", []):
                price = float(item.get('price', {}).get('amount', 0))

                # Basit arbitraj kontrolu
                # Gercek sistemde platformlar arasi fiyat karsilastirmasi yapilacak
                if price > 10 and price < 100:
                    potential_profit = price * (min_margin / 100)

                    if potential_profit > 5:  # Minimum 5 EUR kar
                        opportunities.append({
                            "item_id": item.get('id'),
                            "title": item.get('title'),
                            "brand": item.get('brand_title'),
                            "price": price,
                            "potential_profit": round(potential_profit, 2),
                            "category": cat_name,
                            "url": f"https://www.vinted.de/items/{item.get('id')}"
                        })

        return opportunities

    def generate_report(self, results):
        """
        Rapor olustur
        """
        report = []
        report.append("TATANGA Trend Raporu")
        report.append(f"Tarih: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
        report.append("=" * 40)

        for cat_name, cat_data in results.get("categories", {}).items():
            report.append(f"\n{cat_name.upper()}")
            report.append("-" * 20)

            for brand, brand_data in cat_data.get("brands", {}).items():
                if brand_data.get('count', 0) > 0:
                    report.append(f"  {brand}: {brand_data['count']} urun, avg {brand_data['avg_price']:.2f} EUR")

            # Hot items
            if cat_data.get("hot_items"):
                report.append("\n  En Populer:")
                for item in cat_data["hot_items"][:3]:
                    title = item.get('title', '')[:30]
                    price = item.get('price', {}).get('amount', 0)
                    favs = item.get('favourite_count', 0)
                    report.append(f"    - {title}... | {price} EUR | {favs} fav")

        return "\n".join(report)

# ============================================
# AI TREND PREDICTION
# ============================================
def get_ai_trend_prediction(category_data):
    """
    Groq ile trend tahmini yap
    """
    try:
        headers = {
            "Authorization": f"Bearer {AI_SERVICES['groq']['api_key']}",
            "Content-Type": "application/json"
        }

        prompt = f"""
        Analyze this second-hand fashion market data and predict trends:

        {json.dumps(category_data, indent=2)}

        Provide:
        1. Top 3 trending brands
        2. Price trend (up/down/stable)
        3. Best items to buy for resale
        4. Recommended selling price range

        Keep response under 200 words. Use German for product names.
        """

        data = {
            "model": AI_SERVICES['groq']['model'],
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 300
        }

        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers,
            json=data,
            timeout=30
        )

        if response.status_code == 200:
            result = response.json()
            return result['choices'][0]['message']['content'].strip()

    except Exception as e:
        print(f"AI prediction hatasi: {e}")

    return ""

# ============================================
# MAIN
# ============================================
def main():
    import argparse

    parser = argparse.ArgumentParser(description='TATANGA - T1 Trend Hunter')
    parser.add_argument('--category', type=str, help='Tek kategori tara')
    parser.add_argument('--notify', action='store_true', help='Telegram bildirim gonder')
    parser.add_argument('--ai', action='store_true', help='AI tahmin ekle')

    args = parser.parse_args()

    analyzer = TrendAnalyzer()

    # Tarama yap
    results = analyzer.scan_all_categories()

    # Arbitraj firsatlarini bul
    opportunities = analyzer.find_arbitrage_opportunities(results)

    # Rapor olustur
    report = analyzer.generate_report(results)
    print("\n" + report)

    # Arbitraj firsatlari
    if opportunities:
        print("\n" + "=" * 40)
        print("ARBITRAJ FIRSATLARI")
        print("=" * 40)
        for opp in opportunities[:10]:
            print(f"- {opp['brand']} {opp['title'][:25]}...")
            print(f"  Fiyat: {opp['price']} EUR | Potansiyel Kar: +{opp['potential_profit']} EUR")
            print(f"  {opp['url']}")
            print()

    # Kaydet
    output_file = OUTPUT_DIR / f"trend_scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            "results": results,
            "opportunities": opportunities
        }, f, ensure_ascii=False, indent=2)

    print(f"\n[+] Kaydedildi: {output_file}")

    # Telegram bildirim
    if args.notify or True:  # Varsayilan olarak gonder
        msg = f"""
Trend Taramasi Tamamlandi!

Tarih: {datetime.now().strftime('%d.%m.%Y %H:%M')}

Kategoriler: {len(results.get('categories', {}))}
Arbitraj Firsati: {len(opportunities)}

En Iyi Firsatlar:
"""
        for opp in opportunities[:3]:
            msg += f"- {opp['brand']} | {opp['price']}EUR -> +{opp['potential_profit']}EUR\n"

        send_telegram(msg)

    # AI tahmin
    if args.ai:
        print("\n[*] AI trend tahmini aliniyor...")
        prediction = get_ai_trend_prediction(results)
        if prediction:
            print("\nAI Tahmini:")
            print(prediction)

if __name__ == "__main__":
    main()
