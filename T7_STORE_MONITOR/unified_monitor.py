#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TATANGA - Unified Store Monitor
TUM PLATFORMLAR: Vinted, Kleinanzeigen, eBay, Willhaben
Farkli Telegram kanallarina bildirim
"""

import os
import sys
import json
import time
import asyncio
from pathlib import Path
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.config.credentials import TELEGRAM, VINTED, KLEINANZEIGEN, EBAY, WILLHABEN
from shared.utils.proxy_manager import ProxyManager

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    import undetected_chromedriver as uc
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

import requests

# ============================================
# CONFIGURATION
# ============================================
OUTPUT_DIR = Path(__file__).parent / "output"
LOGS_DIR = Path(__file__).parent / "logs"
DATA_DIR = Path(__file__).parent / "data"

for d in [OUTPUT_DIR, LOGS_DIR, DATA_DIR]:
    d.mkdir(exist_ok=True)

# Kontrol araligi (dakika)
CHECK_INTERVAL = 15

# ============================================
# TELEGRAM MULTI-CHANNEL
# ============================================
class TelegramNotifier:
    """Coklu kanal bildirici"""

    def __init__(self):
        self.bot_token = TELEGRAM["bot_token"]
        self.channels = TELEGRAM.get("channels", {})
        self.admin_chat = TELEGRAM["admin_chat_id"]

    def send(self, channel, message, buttons=None):
        """
        Belirli kanala mesaj gonder

        Args:
            channel: "general", "messages", "sales", "shipping", "notifications", "system"
            message: Mesaj metni
            buttons: Inline butonlar
        """
        chat_id = self.channels.get(channel, 0)

        # Kanal ayarlanmamissa admin'e gonder
        if not chat_id:
            chat_id = self.admin_chat

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        data = {
            "chat_id": chat_id,
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

    def send_message_alert(self, platform, account, sender, message, product):
        """Mesaj bildirimi - messages kanalina"""
        msg = f"""
YENI MESAJ - {platform.upper()}

*Hesap:* {account}
*Gonderen:* {sender}
*Urun:* {product.get('title', '')[:40]}...
*Fiyat:* {product.get('price', 0)} EUR

*Mesaj:*
_{message}_
        """

        buttons = [
            [
                {"text": "Yanit Ver", "callback_data": f"reply:{platform}:{sender}"},
                {"text": "Gormezden Gel", "callback_data": f"ignore:{platform}:{sender}"}
            ]
        ]

        self.send("messages", msg, buttons)

    def send_sale_alert(self, platform, account, product, buyer, price):
        """Satis bildirimi - sales kanalina"""
        msg = f"""
SATIS - {platform.upper()}

*Hesap:* {account}
*Alici:* {buyer}
*Urun:* {product.get('title', '')}
*Fiyat:* {price} EUR

Kargo hazirlanmali!
        """

        buttons = [
            [
                {"text": "Kargo Olustur", "callback_data": f"ship:{platform}:{product.get('id')}"},
                {"text": "Detay", "url": product.get('url', '')}
            ]
        ]

        self.send("sales", msg, buttons)

    def send_shipping_alert(self, platform, tracking_number, carrier, status):
        """Kargo bildirimi - shipping kanalina"""
        msg = f"""
KARGO GUNCELLEME

*Platform:* {platform}
*Tasiyici:* {carrier}
*Takip No:* `{tracking_number}`
*Durum:* {status}
        """

        self.send("shipping", msg)

    def send_notification_alert(self, platform, account, notification_type, items):
        """Favori/goruntulenme bildirimi - notifications kanalina"""
        msg = f"""
{notification_type.upper()} - {platform.upper()}

*Hesap:* {account}
*Yeni:* {len(items)} adet

"""
        for item in items[:5]:
            msg += f"- {item.get('title', '')[:30]}... (+{item.get('count', 1)})\n"

        if len(items) > 5:
            msg += f"... ve {len(items) - 5} daha"

        self.send("notifications", msg)

    def send_system_alert(self, message, level="info"):
        """Sistem bildirimi - system kanalina"""
        emoji = {"info": "i", "warning": "!", "error": "X", "success": "+"}

        msg = f"""
[{emoji.get(level, 'i')}] SISTEM

{message}
        """

        self.send("system", msg)

# ============================================
# PLATFORM MONITORS
# ============================================

class BaseMonitor:
    """Temel monitor sinifi"""

    def __init__(self, platform_name):
        self.platform = platform_name
        self.driver = None
        self.proxy_manager = ProxyManager()
        self.notifier = TelegramNotifier()
        self.previous_data = self.load_data()

    def load_data(self):
        """Onceki verileri yukle"""
        data_file = DATA_DIR / f"{self.platform}_state.json"
        if data_file.exists():
            with open(data_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def save_data(self, data):
        """Verileri kaydet"""
        data_file = DATA_DIR / f"{self.platform}_state.json"
        with open(data_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        self.previous_data = data

    def init_driver(self, headless=True):
        """Chrome driver baslat"""
        if not SELENIUM_AVAILABLE:
            return False

        try:
            options = uc.ChromeOptions()
            if headless:
                options.add_argument('--headless=new')

            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--window-size=1920,1080')

            ua = self.proxy_manager.get_random_user_agent()
            options.add_argument(f'--user-agent={ua}')

            proxy = self.proxy_manager.get_proxy_for_platform(self.platform)
            if proxy:
                options.add_argument(f'--proxy-server={proxy["http"]}')

            self.driver = uc.Chrome(options=options)
            self.driver.implicitly_wait(10)
            return True

        except Exception as e:
            self.notifier.send_system_alert(f"{self.platform} driver hatasi: {e}", "error")
            return False

    def close_driver(self):
        """Driver kapat"""
        if self.driver:
            self.driver.quit()
            self.driver = None


class VintedMonitor(BaseMonitor):
    """Vinted monitor"""

    def __init__(self):
        super().__init__("vinted")

    def check_account(self, account):
        """Hesabi kontrol et"""
        if not self.init_driver():
            return None

        try:
            result = {
                "account": account['name'],
                "username": account.get('username', ''),
                "messages": [],
                "notifications": [],
                "favorites": [],
                "sales": []
            }

            # Login ve kontrol
            # ... (login kodu)

            return result

        finally:
            self.close_driver()


class KleinanzeigenMonitor(BaseMonitor):
    """Kleinanzeigen monitor"""

    def __init__(self):
        super().__init__("kleinanzeigen")

    def check_account(self, account):
        """Hesabi kontrol et"""
        if not self.init_driver():
            return None

        try:
            result = {
                "account": account['name'],
                "email": account.get('email', ''),
                "messages": [],
                "notifications": [],
                "favorites": [],
                "active_listings": []
            }

            # Login
            self.driver.get("https://www.kleinanzeigen.de/m-einloggen.html")
            time.sleep(3)

            # ... (login ve kontrol kodu)

            return result

        finally:
            self.close_driver()


class EbayMonitor(BaseMonitor):
    """eBay monitor"""

    def __init__(self):
        super().__init__("ebay")

    def check_account(self, account):
        """Hesabi kontrol et"""
        # eBay API kullan
        result = {
            "account": account['name'],
            "username": account.get('username', ''),
            "messages": [],
            "sales": [],
            "watchers": []
        }

        # API ile veri cek
        # ...

        return result


class WillhabenMonitor(BaseMonitor):
    """Willhaben monitor"""

    def __init__(self):
        super().__init__("willhaben")

    def check_account(self, account):
        """Hesabi kontrol et"""
        if not self.init_driver():
            return None

        try:
            result = {
                "account": account['name'],
                "email": account.get('email', ''),
                "messages": [],
                "notifications": [],
                "active_listings": []
            }

            # Login ve kontrol
            # ...

            return result

        finally:
            self.close_driver()


# ============================================
# UNIFIED MONITOR
# ============================================
class UnifiedStoreMonitor:
    """Tum platformlari yoneten birlesik monitor"""

    def __init__(self):
        self.notifier = TelegramNotifier()
        self.monitors = {
            "vinted": VintedMonitor(),
            "kleinanzeigen": KleinanzeigenMonitor(),
            "ebay": EbayMonitor(),
            "willhaben": WillhabenMonitor()
        }

        # Platform hesaplari
        self.accounts = {
            "vinted": VINTED.get('accounts', []),
            "kleinanzeigen": KLEINANZEIGEN.get('accounts', []),
            "ebay": EBAY.get('accounts', []),
            "willhaben": WILLHABEN.get('accounts', [])
        }

    def run_check(self, platforms=None):
        """
        Tum platformlari kontrol et

        Args:
            platforms: Kontrol edilecek platformlar (None = hepsi)
        """
        if platforms is None:
            platforms = list(self.monitors.keys())

        print("\n" + "=" * 50)
        print(f"BIRLESIK MAGAZA KONTROLU - {datetime.now().strftime('%H:%M')}")
        print("=" * 50)

        all_results = {}

        # Paralel kontrol
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {}

            for platform in platforms:
                if platform not in self.monitors:
                    continue

                monitor = self.monitors[platform]
                accounts = self.accounts.get(platform, [])

                for account in accounts:
                    if account.get('status') != 'active':
                        continue

                    future = executor.submit(monitor.check_account, account)
                    futures[future] = (platform, account['name'])

            for future in futures:
                platform, account_name = futures[future]
                try:
                    result = future.result()
                    if result:
                        key = f"{platform}_{account_name}"
                        all_results[key] = result
                        print(f"[+] {platform} ({account_name}): OK")
                except Exception as e:
                    print(f"[-] {platform} ({account_name}): {e}")

        # Degisiklikleri tespit et ve bildir
        self.process_changes(all_results)

        return all_results

    def process_changes(self, results):
        """Degisiklikleri isle ve bildir"""
        for key, data in results.items():
            platform = key.split('_')[0]
            account = data.get('account', '')

            # Yeni mesajlar
            messages = data.get('messages', [])
            for msg in messages:
                if msg.get('unread'):
                    self.notifier.send_message_alert(
                        platform,
                        account,
                        msg.get('sender', ''),
                        msg.get('text', ''),
                        msg.get('product', {})
                    )

            # Yeni favoriler
            favorites = data.get('favorites', [])
            new_favs = [f for f in favorites if f.get('is_new')]
            if new_favs:
                self.notifier.send_notification_alert(
                    platform,
                    account,
                    "Yeni Favoriler",
                    new_favs
                )

            # Satislar
            sales = data.get('sales', [])
            for sale in sales:
                if sale.get('is_new'):
                    self.notifier.send_sale_alert(
                        platform,
                        account,
                        sale.get('product', {}),
                        sale.get('buyer', ''),
                        sale.get('price', 0)
                    )

    def run_continuous(self, interval=15):
        """Surekli izleme"""
        print(f"\n[*] Birlesik izleme baslatildi ({interval} dk aralik)")
        print(f"    Platformlar: {', '.join(self.monitors.keys())}")
        print("    Durdurmak icin Ctrl+C\n")

        self.notifier.send_system_alert(
            f"Birlesik monitor baslatildi. {len(self.monitors)} platform izleniyor.",
            "success"
        )

        while True:
            try:
                self.run_check()

                next_check = datetime.now() + timedelta(minutes=interval)
                print(f"\n[*] Sonraki kontrol: {next_check.strftime('%H:%M')}")

                time.sleep(interval * 60)

            except KeyboardInterrupt:
                self.notifier.send_system_alert("Monitor durduruldu.", "info")
                print("\n\nDurduruldu.")
                break

            except Exception as e:
                self.notifier.send_system_alert(f"Monitor hatasi: {e}", "error")
                time.sleep(60)

    def get_all_products(self, platform=None):
        """
        Tum platformlardaki urunleri getir

        Args:
            platform: Belirli platform (None = hepsi)

        Returns:
            dict: Platform bazli urun listesi
        """
        products = {}

        platforms = [platform] if platform else list(self.monitors.keys())

        for p in platforms:
            monitor = self.monitors.get(p)
            if not monitor:
                continue

            accounts = self.accounts.get(p, [])
            p_products = []

            for account in accounts:
                if account.get('status') != 'active':
                    continue

                # Hesaptaki urunleri cek
                # ...

            products[p] = p_products

        return products

# ============================================
# MAIN
# ============================================
def main():
    import argparse

    parser = argparse.ArgumentParser(description='TATANGA - Unified Store Monitor')
    parser.add_argument('--once', action='store_true', help='Tek sefer kontrol')
    parser.add_argument('--interval', type=int, default=15, help='Kontrol araligi (dk)')
    parser.add_argument('--platforms', nargs='+', help='Platformlar')

    args = parser.parse_args()

    print("=" * 50)
    print("TATANGA - Unified Store Monitor")
    print("=" * 50)
    print("\nPlatformlar: Vinted, Kleinanzeigen, eBay, Willhaben")

    if not SELENIUM_AVAILABLE:
        print("\n[-] Selenium yuklu degil!")
        return

    monitor = UnifiedStoreMonitor()

    if args.once:
        monitor.run_check(args.platforms)
    else:
        monitor.run_continuous(args.interval)

if __name__ == "__main__":
    main()
