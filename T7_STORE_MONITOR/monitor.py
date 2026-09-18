#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TATANGA - T7 Store Monitor
Magaza izleme: Favoriler, Mesajlar, Satislar, Bildirimler
15 dakikada bir otomatik kontrol
"""

import os
import sys
import json
import time
import asyncio
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.config.credentials import TELEGRAM, VINTED, KLEINANZEIGEN, EBAY, WILLHABEN
from shared.utils.proxy_manager import SafeRequester, ProxyManager

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

OUTPUT_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)

# Izleme araligi (dakika)
CHECK_INTERVAL = 15

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
# VINTED MONITOR
# ============================================
class VintedMonitor:
    """Vinted magaza izleyici"""

    def __init__(self):
        self.driver = None
        self.proxy_manager = ProxyManager()
        self.previous_data = self.load_previous_data("vinted")

    def load_previous_data(self, platform):
        """Onceki verileri yukle"""
        data_file = DATA_DIR / f"{platform}_state.json"
        if data_file.exists():
            with open(data_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def save_data(self, platform, data):
        """Verileri kaydet"""
        data_file = DATA_DIR / f"{platform}_state.json"
        with open(data_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

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
            options.add_argument('--lang=de-DE')

            ua = self.proxy_manager.get_random_user_agent()
            options.add_argument(f'--user-agent={ua}')

            self.driver = uc.Chrome(options=options)
            self.driver.implicitly_wait(10)
            return True

        except Exception as e:
            print(f"[-] Driver hatasi: {e}")
            return False

    def login(self, account):
        """Vinted'e giris yap"""
        try:
            self.driver.get("https://www.vinted.de/member/general/login")
            time.sleep(3)

            # Cookie popup
            try:
                accept_btn = WebDriverWait(self.driver, 5).until(
                    EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler"))
                )
                accept_btn.click()
                time.sleep(1)
            except:
                pass

            # Email
            email_input = self.driver.find_element(By.NAME, "email")
            email_input.send_keys(account['email'])

            # Password
            password_input = self.driver.find_element(By.NAME, "password")
            password_input.send_keys(account['password'])

            # Submit
            submit_btn = self.driver.find_element(By.CSS_SELECTOR, "[type='submit']")
            submit_btn.click()

            time.sleep(5)
            return True

        except Exception as e:
            print(f"[-] Login hatasi: {e}")
            return False

    def check_notifications(self):
        """
        Bildirimleri kontrol et
        Screenshot'taki gibi: will250, katrin06.03, etc. favoriler
        """
        try:
            self.driver.get("https://www.vinted.de/inbox")
            time.sleep(3)

            notifications = []

            # Bildirim butonu
            try:
                notif_btn = self.driver.find_element(By.CSS_SELECTOR, "[data-testid='notification-button']")
                notif_btn.click()
                time.sleep(2)

                # Bildirim listesi
                notif_items = self.driver.find_elements(By.CSS_SELECTOR, "[data-testid='notification-item']")

                for item in notif_items[:10]:  # Son 10 bildirim
                    try:
                        text = item.text
                        notifications.append({
                            "text": text,
                            "timestamp": datetime.now().isoformat()
                        })
                    except:
                        continue

            except:
                pass

            return notifications

        except Exception as e:
            print(f"[-] Bildirim kontrolu hatasi: {e}")
            return []

    def check_messages(self):
        """
        Mesajlari kontrol et
        Screenshot'taki gibi: garnachuk "Hello, would you accept 15 euro?"
        """
        try:
            self.driver.get("https://www.vinted.de/inbox")
            time.sleep(3)

            messages = []

            # Mesaj listesi
            msg_items = self.driver.find_elements(By.CSS_SELECTOR, "[data-testid='conversation-item']")

            for item in msg_items[:10]:
                try:
                    # Kullanici adi
                    username = item.find_element(By.CSS_SELECTOR, "[data-testid='conversation-username']").text

                    # Son mesaj
                    last_msg = item.find_element(By.CSS_SELECTOR, "[data-testid='conversation-last-message']").text

                    # Zaman
                    time_el = item.find_element(By.CSS_SELECTOR, "[data-testid='conversation-time']")
                    time_text = time_el.text

                    # Okunmamis mi
                    unread = "unread" in item.get_attribute("class").lower()

                    messages.append({
                        "username": username,
                        "last_message": last_msg,
                        "time": time_text,
                        "unread": unread
                    })

                except:
                    continue

            return messages

        except Exception as e:
            print(f"[-] Mesaj kontrolu hatasi: {e}")
            return []

    def check_favorites(self):
        """
        Urun favorilerini kontrol et
        Hangi urunler kac favori almis
        """
        try:
            self.driver.get("https://www.vinted.de/member/items")
            time.sleep(3)

            favorites = []

            # Urun kartlari
            items = self.driver.find_elements(By.CSS_SELECTOR, "[data-testid='grid-item']")

            for item in items:
                try:
                    # Baslik
                    title = item.find_element(By.CSS_SELECTOR, "img").get_attribute("alt")

                    # Fiyat
                    price_el = item.find_element(By.CSS_SELECTOR, "[data-testid='item-price']")
                    price = price_el.text

                    # Favori sayisi (varsa)
                    try:
                        fav_el = item.find_element(By.CSS_SELECTOR, "[data-testid='favourite-count']")
                        fav_count = int(fav_el.text)
                    except:
                        fav_count = 0

                    favorites.append({
                        "title": title,
                        "price": price,
                        "favorites": fav_count
                    })

                except:
                    continue

            return favorites

        except Exception as e:
            print(f"[-] Favori kontrolu hatasi: {e}")
            return []

    def monitor_account(self, account):
        """Tek hesabi izle"""
        if not self.init_driver():
            return None

        try:
            print(f"\n[*] Vinted izleniyor: {account['username']}")

            # Login
            if not self.login(account):
                return None

            # Kontroller
            notifications = self.check_notifications()
            messages = self.check_messages()
            favorites = self.check_favorites()

            result = {
                "account": account['name'],
                "username": account.get('username', ''),
                "checked_at": datetime.now().isoformat(),
                "notifications": notifications,
                "messages": messages,
                "favorites": favorites,
                "unread_messages": len([m for m in messages if m.get('unread')])
            }

            return result

        except Exception as e:
            print(f"[-] Monitor hatasi: {e}")
            return None

        finally:
            if self.driver:
                self.driver.quit()

    def compare_and_alert(self, current_data):
        """
        Onceki veri ile karsilastir ve degisiklikleri bildir
        """
        alerts = []
        account_name = current_data.get('account', 'unknown')

        previous = self.previous_data.get(account_name, {})

        # Yeni mesaj kontrolu
        unread_now = current_data.get('unread_messages', 0)
        unread_before = previous.get('unread_messages', 0)

        if unread_now > unread_before:
            new_count = unread_now - unread_before
            alerts.append(f"Yeni mesaj: {new_count} adet")

            # Mesaj detaylari
            for msg in current_data.get('messages', [])[:new_count]:
                if msg.get('unread'):
                    alerts.append(f"  - {msg['username']}: {msg['last_message'][:50]}...")

        # Favori degisiklikleri
        current_favs = {f['title']: f['favorites'] for f in current_data.get('favorites', [])}
        previous_favs = {f['title']: f['favorites'] for f in previous.get('favorites', [])}

        for title, count in current_favs.items():
            old_count = previous_favs.get(title, 0)
            if count > old_count:
                alerts.append(f"Yeni favori: {title[:30]}... (+{count - old_count})")

        # Kaydet
        self.previous_data[account_name] = current_data
        self.save_data("vinted", self.previous_data)

        return alerts

# ============================================
# STORE MONITOR MANAGER
# ============================================
class StoreMonitor:
    """Tum magazalari yoneten ana sinif"""

    def __init__(self):
        self.vinted = VintedMonitor()

    def run_check(self):
        """Tum magazalari kontrol et"""
        print("\n" + "=" * 50)
        print(f"MAGAZA KONTROLU - {datetime.now().strftime('%H:%M')}")
        print("=" * 50)

        all_alerts = []

        # Vinted
        for account in VINTED.get('accounts', []):
            if account.get('status') == 'active':
                result = self.vinted.monitor_account(account)
                if result:
                    alerts = self.vinted.compare_and_alert(result)
                    if alerts:
                        all_alerts.append({
                            "platform": "vinted",
                            "account": account['name'],
                            "alerts": alerts
                        })

        # Bildirimleri gonder
        if all_alerts:
            self.send_alerts(all_alerts)
        else:
            print("\n[*] Yeni bildirim yok")

        return all_alerts

    def send_alerts(self, all_alerts):
        """Telegram'a bildirimleri gonder"""
        msg = f"""
MAGAZA BILDIRIMLERI

{datetime.now().strftime('%d.%m.%Y %H:%M')}
"""

        for alert_group in all_alerts:
            platform = alert_group['platform'].upper()
            account = alert_group['account']
            alerts = alert_group['alerts']

            msg += f"\n*{platform} ({account}):*\n"
            for alert in alerts:
                msg += f"{alert}\n"

        # Butonlar
        buttons = [
            [
                {"text": "Vinted Ac", "url": "https://www.vinted.de/inbox"},
                {"text": "Detaylar", "callback_data": "monitor:details"}
            ]
        ]

        send_telegram(msg, buttons=buttons)
        print(f"\n[+] {len(all_alerts)} bildirim gonderildi")

    def run_continuous(self, interval_minutes=15):
        """Surekli izleme modu"""
        print(f"\n[*] Surekli izleme baslatildi ({interval_minutes} dakika aralik)")
        print("    Durdurmak icin Ctrl+C")

        while True:
            try:
                self.run_check()

                # Sonraki kontrol
                next_check = datetime.now() + timedelta(minutes=interval_minutes)
                print(f"\n[*] Sonraki kontrol: {next_check.strftime('%H:%M')}")

                time.sleep(interval_minutes * 60)

            except KeyboardInterrupt:
                print("\n\nDurduruldu.")
                break
            except Exception as e:
                print(f"\n[-] Hata: {e}")
                time.sleep(60)  # Hata durumunda 1 dk bekle

# ============================================
# MAIN
# ============================================
def main():
    import argparse

    parser = argparse.ArgumentParser(description='TATANGA - T7 Store Monitor')
    parser.add_argument('--once', action='store_true', help='Tek sefer kontrol')
    parser.add_argument('--interval', type=int, default=15, help='Kontrol araligi (dakika)')
    parser.add_argument('--platform', type=str, help='Tek platform (vinted, kleinanzeigen)')

    args = parser.parse_args()

    print("=" * 50)
    print("TATANGA - T7 Store Monitor")
    print("=" * 50)

    if not SELENIUM_AVAILABLE:
        print("\n[-] Selenium yuklu degil!")
        print("    pip install selenium undetected-chromedriver")
        return

    monitor = StoreMonitor()

    if args.once:
        monitor.run_check()
    else:
        monitor.run_continuous(args.interval)

if __name__ == "__main__":
    main()
