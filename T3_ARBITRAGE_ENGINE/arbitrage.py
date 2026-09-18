#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TATANGA - T3 Arbitrage Engine
Platformlar arasi fiyat farki ve arbitraj firsati bulma
"""

import os
import sys
import json
import time
import requests
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.config.credentials import TELEGRAM
from shared.config.settings import ARBITRAGE

# ============================================
# CONFIGURATION
# ============================================
OUTPUT_DIR = Path(__file__).parent / "output"
LOGS_DIR = Path(__file__).parent / "logs"

OUTPUT_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

# Minimum kar oranları
MIN_PROFIT_PERCENT = ARBITRAGE.get('min_profit_percent', 20)
MIN_PROFIT_AMOUNT = ARBITRAGE.get('min_profit_amount', 5)

# Platform komisyonları
PLATFORM_FEES = {
    "vinted": 0.05,      # %5
    "kleinanzeigen": 0,  # Komisyon yok
    "ebay": 0.12,        # %12
    "willhaben": 0.05    # %5
}

# Kargo maliyetleri (ortalama)
SHIPPING_COSTS = {
    "vinted": 4.50,
    "kleinanzeigen": 5.99,
    "ebay": 5.99,
    "willhaben": 6.50
}

# ============================================
# TELEGRAM NOTIFICATION
# ============================================
def send_telegram(message, buttons=None):
    """Telegram'a mesaj gonder"""
    url = f"https://api.telegram.org/bot{TELEGRAM['bot_token']}/sendMessage"
    data = {
        "chat_id": TELEGRAM["admin_chat_id"],
        "text": message,
        "parse_mode": "Markdown"
    }

    if buttons:
        keyboard = {"inline_keyboard": buttons}
        data["reply_markup"] = json.dumps(keyboard)

    try:
        requests.post(url, data=data)
    except Exception as e:
        print(f"Telegram hatasi: {e}")

# ============================================
# ARBITRAGE CALCULATOR
# ============================================
class ArbitrageCalculator:
    """Arbitraj hesaplayici"""

    def __init__(self):
        self.platform_fees = PLATFORM_FEES
        self.shipping_costs = SHIPPING_COSTS

    def calculate_profit(self, buy_price, sell_price, buy_platform, sell_platform, include_shipping=True):
        """
        Net kar hesapla

        Args:
            buy_price: Alis fiyati
            sell_price: Satis fiyati
            buy_platform: Alinan platform
            sell_platform: Satilan platform
            include_shipping: Kargo dahil mi

        Returns:
            dict: Kar detaylari
        """
        # Platform komisyonu (satis platformundan)
        commission = sell_price * self.platform_fees.get(sell_platform, 0)

        # Kargo maliyeti
        shipping = 0
        if include_shipping:
            shipping = self.shipping_costs.get(sell_platform, 5)

        # Net kar
        net_profit = sell_price - buy_price - commission - shipping

        # Kar yuzdesi
        profit_percent = (net_profit / buy_price * 100) if buy_price > 0 else 0

        return {
            "buy_price": buy_price,
            "sell_price": sell_price,
            "commission": round(commission, 2),
            "shipping": shipping,
            "net_profit": round(net_profit, 2),
            "profit_percent": round(profit_percent, 1),
            "buy_platform": buy_platform,
            "sell_platform": sell_platform,
            "is_profitable": net_profit >= MIN_PROFIT_AMOUNT and profit_percent >= MIN_PROFIT_PERCENT
        }

    def find_best_sell_platform(self, buy_price, buy_platform, target_prices):
        """
        En karli satis platformunu bul

        Args:
            buy_price: Alis fiyati
            buy_platform: Alinan platform
            target_prices: {platform: fiyat} dict

        Returns:
            dict: En iyi secenek
        """
        best_option = None
        best_profit = 0

        for platform, price in target_prices.items():
            if platform == buy_platform:
                continue

            result = self.calculate_profit(buy_price, price, buy_platform, platform)

            if result['net_profit'] > best_profit:
                best_profit = result['net_profit']
                best_option = result

        return best_option

    def suggest_sell_price(self, buy_price, platform, min_profit_percent=None):
        """
        Onerilen satis fiyatini hesapla

        Args:
            buy_price: Alis fiyati
            platform: Satis platformu
            min_profit_percent: Minimum kar yuzdesi

        Returns:
            float: Onerilen fiyat
        """
        if min_profit_percent is None:
            min_profit_percent = MIN_PROFIT_PERCENT

        fee_rate = self.platform_fees.get(platform, 0)
        shipping = self.shipping_costs.get(platform, 5)

        # Hedef kar
        target_profit = buy_price * (min_profit_percent / 100)

        # Gerekli satis fiyati
        # sell_price = buy_price + profit + commission + shipping
        # sell_price = buy_price + profit + (sell_price * fee_rate) + shipping
        # sell_price - (sell_price * fee_rate) = buy_price + profit + shipping
        # sell_price * (1 - fee_rate) = buy_price + profit + shipping
        # sell_price = (buy_price + profit + shipping) / (1 - fee_rate)

        sell_price = (buy_price + target_profit + shipping) / (1 - fee_rate)

        return round(sell_price, 2)

# ============================================
# OPPORTUNITY FINDER
# ============================================
class OpportunityFinder:
    """Arbitraj firsati bulucu"""

    def __init__(self):
        self.calculator = ArbitrageCalculator()
        self.opportunities = []

    def compare_prices(self, product_data):
        """
        Ayni urunun farkli platformlardaki fiyatlarini karsilastir

        Args:
            product_data: {
                "name": "...",
                "brand": "...",
                "prices": {
                    "vinted": 25.00,
                    "kleinanzeigen": 35.00,
                    "ebay": 40.00
                }
            }

        Returns:
            list: Arbitraj firsatlari
        """
        opportunities = []
        prices = product_data.get('prices', {})

        # Her platform ciftini kontrol et
        platforms = list(prices.keys())

        for buy_platform in platforms:
            buy_price = prices[buy_platform]

            for sell_platform in platforms:
                if buy_platform == sell_platform:
                    continue

                sell_price = prices[sell_platform]

                # Kar hesapla
                result = self.calculator.calculate_profit(
                    buy_price, sell_price, buy_platform, sell_platform
                )

                if result['is_profitable']:
                    opportunity = {
                        **result,
                        "product_name": product_data.get('name', ''),
                        "brand": product_data.get('brand', ''),
                        "product_id": product_data.get('id', ''),
                        "source_url": product_data.get('urls', {}).get(buy_platform, ''),
                        "found_at": datetime.now().isoformat()
                    }
                    opportunities.append(opportunity)

        return opportunities

    def analyze_market(self, products_list):
        """
        Urun listesini analiz et ve firsatlari bul

        Args:
            products_list: Urun listesi

        Returns:
            list: Tum firsatlar
        """
        all_opportunities = []

        for product in products_list:
            opps = self.compare_prices(product)
            all_opportunities.extend(opps)

        # Kar'a gore sirala
        all_opportunities.sort(key=lambda x: x['net_profit'], reverse=True)

        return all_opportunities

    def save_opportunities(self, opportunities, filename=None):
        """Firsatlari kaydet"""
        if not filename:
            filename = f"opportunities_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        output_path = OUTPUT_DIR / filename

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(opportunities, f, ensure_ascii=False, indent=2)

        print(f"[+] Kaydedildi: {output_path}")
        return output_path

    def send_alerts(self, opportunities, top_n=5):
        """
        En iyi firsatlari Telegram'a gonder
        """
        if not opportunities:
            return

        msg = f"""
ARBITRAJ FIRSATLARI

{datetime.now().strftime('%d.%m.%Y %H:%M')}
Bulunan firsat: {len(opportunities)}

EN IYI {min(top_n, len(opportunities))} FIRSAT:
"""

        for i, opp in enumerate(opportunities[:top_n], 1):
            msg += f"""
{i}. {opp['brand']} {opp['product_name'][:20]}...
   {opp['buy_platform']} -> {opp['sell_platform']}
   Al: {opp['buy_price']} EUR | Sat: {opp['sell_price']} EUR
   Net Kar: +{opp['net_profit']} EUR ({opp['profit_percent']}%)
"""

        # Butonlar
        buttons = [
            [
                {"text": "Detaylari Gor", "callback_data": "arb:details"},
                {"text": "Al!", "callback_data": f"arb:buy:{opportunities[0]['product_id']}" if opportunities else "arb:none"}
            ]
        ]

        send_telegram(msg, buttons=buttons)

# ============================================
# MAIN
# ============================================
def main():
    import argparse

    parser = argparse.ArgumentParser(description='TATANGA - T3 Arbitrage Engine')
    parser.add_argument('--analyze', type=str, help='JSON dosyasini analiz et')
    parser.add_argument('--calculate', nargs=3, metavar=('BUY', 'SELL', 'PLATFORM'),
                       help='Tek kar hesapla')
    parser.add_argument('--suggest', nargs=2, metavar=('PRICE', 'PLATFORM'),
                       help='Satis fiyati oner')

    args = parser.parse_args()

    print("=" * 50)
    print("TATANGA - T3 Arbitrage Engine")
    print("=" * 50)

    calculator = ArbitrageCalculator()
    finder = OpportunityFinder()

    if args.calculate:
        buy_price = float(args.calculate[0])
        sell_price = float(args.calculate[1])
        platform = args.calculate[2]

        result = calculator.calculate_profit(buy_price, sell_price, "vinted", platform)

        print(f"\nKar Hesaplama:")
        print(f"  Alis: {result['buy_price']} EUR")
        print(f"  Satis: {result['sell_price']} EUR")
        print(f"  Komisyon: -{result['commission']} EUR")
        print(f"  Kargo: -{result['shipping']} EUR")
        print(f"  ---")
        print(f"  Net Kar: {result['net_profit']} EUR ({result['profit_percent']}%)")
        print(f"  Karli mi: {'Evet' if result['is_profitable'] else 'Hayir'}")

    elif args.suggest:
        buy_price = float(args.suggest[0])
        platform = args.suggest[1]

        suggested = calculator.suggest_sell_price(buy_price, platform)

        print(f"\nOnerilen Satis Fiyati ({platform}):")
        print(f"  Alis fiyati: {buy_price} EUR")
        print(f"  Onerilen satis: {suggested} EUR")
        print(f"  Hedef kar: %{MIN_PROFIT_PERCENT}")

    elif args.analyze:
        # JSON dosyasini analiz et
        with open(args.analyze, 'r', encoding='utf-8') as f:
            products = json.load(f)

        opportunities = finder.analyze_market(products)

        print(f"\n{len(opportunities)} arbitraj firsati bulundu:")
        for opp in opportunities[:10]:
            print(f"  - {opp['brand']}: {opp['buy_platform']} -> {opp['sell_platform']}")
            print(f"    {opp['buy_price']} -> {opp['sell_price']} EUR = +{opp['net_profit']} EUR")

        finder.save_opportunities(opportunities)
        finder.send_alerts(opportunities)

    else:
        # Demo mod
        print("\nDemo: Ornek hesaplama")

        # Ornek urun
        demo_product = {
            "id": "DEMO-001",
            "name": "Nike Air Max 90",
            "brand": "Nike",
            "prices": {
                "vinted": 45.00,
                "kleinanzeigen": 65.00,
                "ebay": 75.00,
                "willhaben": 60.00
            }
        }

        opportunities = finder.compare_prices(demo_product)

        print(f"\n{demo_product['name']} icin firsatlar:")
        for opp in opportunities:
            status = "KARLI" if opp['is_profitable'] else "Dusuk"
            print(f"  {opp['buy_platform']} ({opp['buy_price']} EUR) -> {opp['sell_platform']} ({opp['sell_price']} EUR)")
            print(f"    Net kar: {opp['net_profit']} EUR ({opp['profit_percent']}%) [{status}]")

        print("\nKullanim:")
        print("  Hesapla:  python arbitrage.py --calculate 45 75 ebay")
        print("  Oner:     python arbitrage.py --suggest 50 vinted")
        print("  Analiz:   python arbitrage.py --analyze products.json")

if __name__ == "__main__":
    main()
