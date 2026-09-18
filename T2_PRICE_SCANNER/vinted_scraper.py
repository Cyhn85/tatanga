#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TATANGA - Vinted Profile Scraper
Vinted magazasindan mevcut ilanlari ceker
"""

import os
import sys
import json
import time
import re
import requests
from pathlib import Path
from datetime import datetime
from bs4 import BeautifulSoup

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.config.credentials import TELEGRAM, VINTED, PROXY

# ============================================
# CONFIGURATION
# ============================================
OUTPUT_DIR = Path(__file__).parent / "output"
LOGS_DIR = Path(__file__).parent / "logs"

OUTPUT_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

# Vinted API endpoints
VINTED_API_BASE = "https://www.vinted.de/api/v2"
VINTED_WEB_BASE = "https://www.vinted.de"

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
# VINTED SESSION MANAGER
# ============================================
class VintedSession:
    """Vinted oturumu yonetici"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7',
            'Referer': 'https://www.vinted.de/',
            'Origin': 'https://www.vinted.de'
        })

        # Proxy kullan (opsiyonel)
        if PROXY.get('tailscale', {}).get('http'):
            self.session.proxies = {
                'http': PROXY['tailscale']['http'],
                'https': PROXY['tailscale']['http']
            }

    def get_csrf_token(self):
        """CSRF token al"""
        try:
            resp = self.session.get(VINTED_WEB_BASE)
            # Token genellikle cookie'de veya HTML'de
            cookies = self.session.cookies.get_dict()
            return cookies.get('_csrf_token', '')
        except:
            return ''

    def init_session(self):
        """Oturumu baslatarak gerekli cookie'leri al"""
        try:
            # Ana sayfayi ziyaret et
            self.session.get(VINTED_WEB_BASE)
            time.sleep(1)

            # OAuth kontrolu
            self.session.get(f"{VINTED_WEB_BASE}/auth/token_refresh")

            return True
        except Exception as e:
            print(f"Session init hatasi: {e}")
            return False

# ============================================
# PROFILE SCRAPER
# ============================================
class VintedProfileScraper:
    """Vinted profil ve ilan cekici"""

    def __init__(self):
        self.vinted = VintedSession()

    def get_member_id_from_url(self, profile_url):
        """
        Profil URL'inden member ID cikart
        https://www.vinted.de/member/293217988 -> 293217988
        """
        match = re.search(r'/member/(\d+)', profile_url)
        if match:
            return match.group(1)
        return None

    def fetch_member_items(self, member_id, page=1, per_page=96):
        """
        Uye ilanlarini API ile cek
        """
        url = f"{VINTED_API_BASE}/users/{member_id}/items"
        params = {
            'page': page,
            'per_page': per_page,
            'order': 'relevance'
        }

        try:
            resp = self.vinted.session.get(url, params=params)

            if resp.status_code == 200:
                return resp.json()
            else:
                print(f"API hatasi: {resp.status_code}")
                return None

        except Exception as e:
            print(f"Fetch hatasi: {e}")
            return None

    def parse_item(self, item):
        """
        Tek ilani parse et
        """
        return {
            "id": item.get('id'),
            "title": item.get('title', ''),
            "description": item.get('description', ''),
            "price": float(item.get('price', {}).get('amount', 0)),
            "currency": item.get('price', {}).get('currency_code', 'EUR'),
            "brand": item.get('brand_title', ''),
            "size": item.get('size_title', ''),
            "condition": item.get('status', ''),
            "color": item.get('color1', ''),
            "photos": [p.get('full_size_url') or p.get('url') for p in item.get('photos', [])],
            "url": f"{VINTED_WEB_BASE}/items/{item.get('id')}",
            "created_at": item.get('created_at_ts'),
            "views": item.get('view_count', 0),
            "favourites": item.get('favourite_count', 0),
            "category": item.get('catalog_title', ''),
            "is_visible": item.get('is_visible', True),
            "is_reserved": item.get('is_reserved', False),
            "is_sold": False  # API'de direkt yok, status'a bakmak lazim
        }

    def scrape_profile(self, profile_url_or_id):
        """
        Profildeki tum ilanlari cek
        """
        # ID'yi belirle
        if str(profile_url_or_id).isdigit():
            member_id = profile_url_or_id
        else:
            member_id = self.get_member_id_from_url(profile_url_or_id)

        if not member_id:
            print("[-] Gecersiz profil URL veya ID")
            return None

        print(f"\n[*] Vinted profili taraniyor: {member_id}")

        # Oturumu baslat
        self.vinted.init_session()
        time.sleep(2)

        all_items = []
        page = 1

        while True:
            print(f"    Sayfa {page} yukleniyor...")

            data = self.fetch_member_items(member_id, page=page)

            if not data or 'items' not in data:
                break

            items = data.get('items', [])
            if not items:
                break

            for item in items:
                parsed = self.parse_item(item)
                all_items.append(parsed)

            # Pagination kontrolu
            pagination = data.get('pagination', {})
            total_pages = pagination.get('total_pages', 1)

            if page >= total_pages:
                break

            page += 1
            time.sleep(2)  # Rate limiting

        print(f"\n[+] Toplam {len(all_items)} ilan bulundu")

        return {
            "member_id": member_id,
            "scraped_at": datetime.now().isoformat(),
            "total_items": len(all_items),
            "items": all_items
        }

    def save_results(self, data, filename=None):
        """
        Sonuclari JSON olarak kaydet
        """
        if not filename:
            filename = f"vinted_profile_{data['member_id']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        output_path = OUTPUT_DIR / filename

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"[+] Kaydedildi: {output_path}")
        return output_path

# ============================================
# ALTERNATIVE: WEB SCRAPING
# ============================================
def scrape_profile_html(profile_url):
    """
    API calismazsa HTML scraping ile dene
    """
    print(f"\n[*] HTML scraping deneniyor: {profile_url}")

    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    })

    try:
        resp = session.get(profile_url)
        soup = BeautifulSoup(resp.text, 'lxml')

        # JSON-LD veya script tag'lerinden veri cekmeye calis
        scripts = soup.find_all('script', type='application/json')

        for script in scripts:
            try:
                data = json.loads(script.string)
                # Vinted data yapısını ara
                if 'items' in str(data):
                    print("[+] JSON data bulundu")
                    return data
            except:
                continue

        # Alternatif: item kartlarini scrape et
        items = []
        item_cards = soup.select('.feed-grid__item')

        for card in item_cards:
            try:
                item = {
                    "title": card.select_one('.web_ui__Text__title')['text'] if card.select_one('.web_ui__Text__title') else '',
                    "price": card.select_one('.web_ui__Text__subtitle').text if card.select_one('.web_ui__Text__subtitle') else '',
                    "url": VINTED_WEB_BASE + card.find('a')['href'] if card.find('a') else ''
                }
                items.append(item)
            except:
                continue

        return {"items": items} if items else None

    except Exception as e:
        print(f"[-] HTML scraping hatasi: {e}")
        return None

# ============================================
# MAIN
# ============================================
def main():
    import argparse

    parser = argparse.ArgumentParser(description='TATANGA - Vinted Profile Scraper')
    parser.add_argument('profile', nargs='?', help='Profil URL veya member ID')
    parser.add_argument('--all-accounts', action='store_true', help='Tum hesaplari tara')

    args = parser.parse_args()

    print("=" * 50)
    print("TATANGA - Vinted Profile Scraper")
    print("=" * 50)

    scraper = VintedProfileScraper()

    if args.all_accounts:
        # Tum Vinted hesaplarini tara
        for account_name, account_data in VINTED.items():
            profile_url = account_data.get('profile_url', '')
            if profile_url:
                print(f"\n{'='*40}")
                print(f"Hesap: {account_name}")
                print(f"{'='*40}")

                data = scraper.scrape_profile(profile_url)
                if data:
                    scraper.save_results(data)

                    # Telegram bildirim
                    msg = f"""
Vinted Profil Tarandi!

Hesap: {account_name}
Ilan Sayisi: {data['total_items']}

Detaylar output klasorunde.
                    """
                    send_telegram(msg)

                time.sleep(5)  # Hesaplar arasi bekleme

    elif args.profile:
        # Tek profil tara
        data = scraper.scrape_profile(args.profile)
        if data:
            output_path = scraper.save_results(data)

            # Telegram bildirim
            msg = f"""
Vinted Profil Tarandi!

Member ID: {data['member_id']}
Ilan Sayisi: {data['total_items']}

Dosya: {output_path.name}
            """
            send_telegram(msg)

    else:
        # Default: Ana hesabi tara
        main_profile = VINTED.get('main', {}).get('profile_url', '')

        if main_profile:
            print(f"\nAna hesap taranıyor: {main_profile}")
            data = scraper.scrape_profile(main_profile)

            if data:
                scraper.save_results(data)
        else:
            print("\nKullanim:")
            print("  python vinted_scraper.py https://www.vinted.de/member/293217988")
            print("  python vinted_scraper.py 293217988")
            print("  python vinted_scraper.py --all-accounts")

if __name__ == "__main__":
    main()
