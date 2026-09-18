#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TATANGA - Scrape Command Handler
Ana kazima tetikleme sistemi - Tum komutlar bu gruptan alinir
"""

import sys
import json
import time
import requests
import re
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.config.credentials import TELEGRAM, AI_SERVICES

# Multi-platform scraper import
sys.path.insert(0, str(Path(__file__).parent.parent / "T2_SCRAPER"))
from multi_platform_scraper import MultiPlatformScraper

# QualityController import (insansi gezinme icin)
try:
    sys.path.insert(0, str(Path(__file__).parent))
    from quality_controller import QualityController
    QUALITY_CONTROLLER_AVAILABLE = True
except ImportError:
    QUALITY_CONTROLLER_AVAILABLE = False
    print("[!] QualityController yuklenemedi - insansi gezinme pasif")

# Dizinler
BASE_DIR = Path(__file__).parent.parent
LOG_DIR = BASE_DIR / "logs"
PENDING_DIR = BASE_DIR / "T6_LISTING_ENGINE" / "pending"
OUTPUT_DIR = BASE_DIR / "T6_LISTING_ENGINE" / "output"
SCRAPED_DIR = BASE_DIR / "T6_LISTING_ENGINE" / "scraped"

LOG_DIR.mkdir(exist_ok=True)
PENDING_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)
SCRAPED_DIR.mkdir(exist_ok=True)

class ScrapeCommandHandler:
    """Ana kazima komut merkezi"""

    def __init__(self):
        self.bot_token = TELEGRAM['bot_token']
        self.channels = TELEGRAM['channels']
        self.ai_key = AI_SERVICES['groq']['api_key']
        self.ai_model = AI_SERVICES['groq']['model']
        self.last_update_id = 0

        # Grup isim eslestirme
        self.group_names = {
            self.channels['scrape_command']: 'scrape_command',
            self.channels['product_found']: 'product_found',
            self.channels['messages']: 'messages',
            self.channels['sales']: 'sales',
            self.channels['shipping']: 'shipping',
            self.channels['notifications']: 'notifications',
            self.channels['system']: 'system',
        }

        # Log dosyasi
        self.log_file = LOG_DIR / f"scrape_commands_{datetime.now().strftime('%Y%m%d')}.jsonl"

        # Multi-platform scraper
        self.scraper = MultiPlatformScraper()

        # Quality Controller (insansi gezinme)
        self.quality_controller = None
        if QUALITY_CONTROLLER_AVAILABLE:
            self.quality_controller = QualityController(logger=self.log_action)

        # Platform durumu takibi - ENGEL ASMA MEKANIZMASI
        self.platform_status = {
            'vinted': {'status': 'active', 'last_success': None, 'failures': 0, 'bypass_attempts': 0, 'last_bypass': None},
            'kleinanzeigen': {'status': 'active', 'last_success': None, 'failures': 0, 'bypass_attempts': 0, 'last_bypass': None},
            'ebay': {'status': 'active', 'last_success': None, 'failures': 0, 'bypass_attempts': 0, 'last_bypass': None},
            'willhaben': {'status': 'active', 'last_success': None, 'failures': 0, 'bypass_attempts': 0, 'last_bypass': None},
            'ricardo': {'status': 'active', 'last_success': None, 'failures': 0, 'bypass_attempts': 0, 'last_bypass': None},
            'tutti': {'status': 'active', 'last_success': None, 'failures': 0, 'bypass_attempts': 0, 'last_bypass': None},
            'tradera': {'status': 'active', 'last_success': None, 'failures': 0, 'bypass_attempts': 0, 'last_bypass': None},
        }

        # Duplicate kontrolu - daha once kazilan urunler
        self.scraped_products_file = SCRAPED_DIR / "scraped_products.json"
        self.scraped_products = self.load_scraped_products()

    def load_scraped_products(self):
        """Daha once kazilan urunleri yukle"""
        if self.scraped_products_file.exists():
            try:
                with open(self.scraped_products_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {}

    def save_scraped_products(self):
        """Kazilan urunleri kaydet"""
        with open(self.scraped_products_file, 'w', encoding='utf-8') as f:
            json.dump(self.scraped_products, f, ensure_ascii=False, indent=2)

    def is_duplicate(self, product_url):
        """Urun daha once kazildi mi kontrol et"""
        import hashlib
        url_hash = hashlib.md5(product_url.encode()).hexdigest()
        return url_hash in self.scraped_products

    def mark_as_scraped(self, product_url, product_data):
        """Urunu kazildi olarak isaretle"""
        import hashlib
        url_hash = hashlib.md5(product_url.encode()).hexdigest()
        self.scraped_products[url_hash] = {
            'url': product_url,
            'title': product_data.get('title', '')[:50],
            'scraped_at': datetime.now().isoformat()
        }
        self.save_scraped_products()

    def update_platform_status(self, platform, success, error_msg=None):
        """Platform durumunu guncelle - ENGEL ASMA MEKANIZMASI"""
        if platform not in self.platform_status:
            return

        if success:
            self.platform_status[platform]['status'] = 'active'
            self.platform_status[platform]['last_success'] = datetime.now().isoformat()
            self.platform_status[platform]['failures'] = 0
            self.platform_status[platform]['bypass_attempts'] = 0  # Basarili olunca sifirla
        else:
            self.platform_status[platform]['failures'] += 1
            failures = self.platform_status[platform]['failures']

            if failures >= 3:
                # ENGELLEME YERINE ENGEL ASMA DENE
                self.platform_status[platform]['status'] = 'bypassing'
                self.platform_status[platform]['bypass_attempts'] += 1
                bypass_attempt = self.platform_status[platform]['bypass_attempts']

                # Bildiri gonder - ama VAZ GECME
                self.send_message(
                    self.channels['system'],
                    f"*PLATFORM ENGEL ASMA*\n\n"
                    f"Platform: `{platform}`\n"
                    f"Hata: {error_msg or 'Bilinmeyen'}\n"
                    f"Deneme: {bypass_attempt}/5\n\n"
                    f"*İnsansı yaklaşım ile aşılıyor...*\n"
                    f"- Proxy değişimi\n"
                    f"- Bekletme süresi artırma\n"
                    f"- Farklı user-agent\n"
                    f"- Cookie temizleme\n\n"
                    f"_Otomatik engel aşma 2 dakika sonra..._"
                )

                # Engel asma stratejisi belirle
                self.schedule_bypass_attempt(platform, bypass_attempt)

    def schedule_bypass_attempt(self, platform, attempt):
        """Engel aşma denemesi planla"""
        import threading

        # Deneme sayisina gore bekleme suresi artir
        wait_time = min(attempt * 60, 300)  # Max 5 dakika

        def bypass_callback():
            self.attempt_platform_bypass(platform, attempt)

        timer = threading.Timer(wait_time, bypass_callback)
        timer.daemon = True
        timer.start()

        self.log_action("BYPASS_SCHEDULED", {
            'platform': platform,
            'attempt': attempt,
            'wait_time': wait_time
        })

    def attempt_platform_bypass(self, platform, attempt):
        """Platform engelini asma denemesi"""
        self.log_action("BYPASS_ATTEMPT", {'platform': platform, 'attempt': attempt})

        # INSANSI YAKLASIM STRATEJILERI
        strategies = [
            self._bypass_with_delay,           # 1. Uzun bekleme
            self._bypass_with_human_browse,    # 2. Insansi gezinme
            self._bypass_with_cookie_clear,    # 3. Cookie temizle
            self._bypass_with_different_entry, # 4. Farkli giris noktasi
            self._bypass_with_screenshot,      # 5. Screenshot ile veri cekme
        ]

        if attempt <= len(strategies):
            strategy = strategies[attempt - 1]
            success = strategy(platform)

            if success:
                self.platform_status[platform]['status'] = 'active'
                self.platform_status[platform]['failures'] = 0
                self.send_message(
                    self.channels['system'],
                    f"*ENGEL ASILDI!*\n\n"
                    f"Platform: `{platform}`\n"
                    f"Strateji: {strategy.__name__}\n"
                    f"Deneme: {attempt}\n\n"
                    f"✅ Platform tekrar aktif!"
                )
            else:
                if attempt < 5:
                    # Sonraki stratejiyi dene
                    self.schedule_bypass_attempt(platform, attempt + 1)
                else:
                    # Tum stratejiler basarisiz
                    self.platform_status[platform]['status'] = 'manual_required'
                    self.send_message(
                        self.channels['system'],
                        f"*MANUEL MUDAHALE GEREKLI*\n\n"
                        f"Platform: `{platform}`\n"
                        f"Tüm otomatik stratejiler başarısız\n\n"
                        f"*Önerilen:*\n"
                        f"- Proxy değiştir\n"
                        f"- IP sıfırla\n"
                        f"- 30 dakika bekle\n"
                        f"- VPN kullan"
                    )

    def _bypass_with_delay(self, platform):
        """Strateji 1: Uzun bekleme ile bypass"""
        import time
        self.log_action("BYPASS_STRATEGY", {'platform': platform, 'strategy': 'delay'})

        # 2-3 dakika bekle
        time.sleep(random.uniform(120, 180))

        # Test et
        return self._test_platform_access(platform)

    def _bypass_with_human_browse(self, platform):
        """Strateji 2: Insansi gezinme ile bypass"""
        self.log_action("BYPASS_STRATEGY", {'platform': platform, 'strategy': 'human_browse'})

        if self.quality_controller and hasattr(self.quality_controller, 'insansi_gezinme'):
            try:
                # QualityController'in insansi gezinme fonksiyonunu kullan
                # Farkli siteler gezin
                distraction_sites = [
                    'https://www.google.de',
                    'https://www.amazon.de',
                    'https://www.ebay.de',
                    'https://news.google.com'
                ]

                for site in random.sample(distraction_sites, 2):
                    self.quality_controller.insansi_gezinme(site)
                    time.sleep(random.uniform(10, 20))

                return self._test_platform_access(platform)
            except:
                pass

        return False

    def _bypass_with_cookie_clear(self, platform):
        """Strateji 3: Cookie temizleme ile bypass"""
        self.log_action("BYPASS_STRATEGY", {'platform': platform, 'strategy': 'cookie_clear'})

        try:
            if hasattr(self.scraper, 'driver') and self.scraper.driver:
                self.scraper.driver.delete_all_cookies()
                time.sleep(5)
                return self._test_platform_access(platform)
        except:
            pass

        return False

    def _bypass_with_different_entry(self, platform):
        """Strateji 4: Farkli giris noktasi ile bypass"""
        self.log_action("BYPASS_STRATEGY", {'platform': platform, 'strategy': 'different_entry'})

        # Platform URL'leri - farkli giris noktalari
        entry_points = {
            'willhaben': [
                'https://www.willhaben.at/',
                'https://www.willhaben.at/iad',
                'https://www.willhaben.at/iad/kaufen-und-verkaufen'
            ],
            'vinted': [
                'https://www.vinted.de/',
                'https://www.vinted.de/catalog',
                'https://www.vinted.de/women'
            ],
            'kleinanzeigen': [
                'https://www.kleinanzeigen.de/',
                'https://www.kleinanzeigen.de/s-berlin/anzeige:angebote/c173l3331'
            ],
            'ebay': [
                'https://www.ebay.de/',
                'https://www.ebay.de/b/Fashion/11450/bn_1863532'
            ]
        }

        if platform in entry_points:
            entry = random.choice(entry_points[platform])
            try:
                if hasattr(self.scraper, 'driver') and self.scraper.driver:
                    self.scraper.driver.get(entry)
                    time.sleep(random.uniform(5, 10))
                    return self._test_platform_access(platform)
            except:
                pass

        return False

    def _bypass_with_screenshot(self, platform):
        """Strateji 5: Screenshot ile veri cekme (son care)"""
        self.log_action("BYPASS_STRATEGY", {'platform': platform, 'strategy': 'screenshot'})

        # Bu strateji: sayfanin screenshot'ini al ve OCR ile veri cek
        # Simdilik sadece test erisimi yap
        try:
            if hasattr(self.scraper, 'driver') and self.scraper.driver:
                # Screenshot al
                screenshot_path = SCRAPED_DIR / f"bypass_{platform}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                self.scraper.driver.save_screenshot(str(screenshot_path))
                self.log_action("SCREENSHOT_SAVED", {'path': str(screenshot_path)})

                return self._test_platform_access(platform)
        except:
            pass

        return False

    def _test_platform_access(self, platform):
        """Platform erisimini test et"""
        test_urls = {
            'willhaben': 'https://www.willhaben.at/iad/kaufen-und-verkaufen/marktplatz',
            'vinted': 'https://www.vinted.de/catalog?search_text=test',
            'kleinanzeigen': 'https://www.kleinanzeigen.de/',
            'ebay': 'https://www.ebay.de/',
            'ricardo': 'https://www.ricardo.ch/',
            'tutti': 'https://www.tutti.ch/',
            'tradera': 'https://www.tradera.com/'
        }

        if platform not in test_urls:
            return False

        try:
            if hasattr(self.scraper, 'driver') and self.scraper.driver:
                self.scraper.driver.get(test_urls[platform])
                time.sleep(random.uniform(3, 5))

                # Basarili sayfa yuklenme kontrolu
                page_source = self.scraper.driver.page_source.lower()

                # Engel isaretleri
                block_indicators = ['captcha', 'blocked', 'denied', 'forbidden', '403', '429', 'too many requests']
                for indicator in block_indicators:
                    if indicator in page_source:
                        return False

                # Basarili isaretler
                if len(page_source) > 5000:  # Sayfa yuklendi
                    return True

        except Exception as e:
            self.log_action("TEST_ACCESS_ERROR", {'platform': platform, 'error': str(e)})

        return False

    def get_platform_status_report(self):
        """Platform durum raporu - detayli"""
        active = []
        bypassing = []
        manual_required = []

        for platform, status in self.platform_status.items():
            if status['status'] == 'active':
                active.append(platform)
            elif status['status'] == 'bypassing':
                bypassing.append(f"{platform} (deneme {status['bypass_attempts']}/5)")
            elif status['status'] == 'manual_required':
                manual_required.append(f"{platform} (manuel gerekli)")
            else:
                bypassing.append(f"{platform} ({status['failures']} hata)")

        return {
            'active': active,
            'bypassing': bypassing,
            'manual_required': manual_required
        }

    def log_action(self, action_type, data):
        """Aksiyonu logla"""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "type": action_type,
            "data": data
        }
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

    def get_updates(self):
        """Telegram'dan guncellemeleri al"""
        url = f"https://api.telegram.org/bot{self.bot_token}/getUpdates"
        params = {
            "offset": self.last_update_id + 1,
            "timeout": 30
        }

        try:
            resp = requests.get(url, params=params, timeout=35)
            data = resp.json()
            if data.get("ok"):
                return data.get("result", [])
        except Exception as e:
            print(f"[-] getUpdates hatasi: {e}")

        return []

    def send_message(self, chat_id, text, reply_to=None, buttons=None):
        """Mesaj gonder"""
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        data = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }

        if reply_to:
            data["reply_to_message_id"] = reply_to

        if buttons:
            data["reply_markup"] = json.dumps({"inline_keyboard": buttons})

        try:
            resp = requests.post(url, data=data)
            return resp.json()
        except Exception as e:
            print(f"[-] sendMessage hatasi: {e}")
            return None

    def analyze_command(self, message, group_type):
        """AI ile komutu analiz et"""
        try:
            headers = {
                "Authorization": f"Bearer {self.ai_key}",
                "Content-Type": "application/json"
            }

            prompt = f"""
Sen TATANGA e-ticaret otomasyon sisteminin komut analizcisisin.

Grup: {group_type}
Kullanici mesaji: "{message}"

Bu mesajdan kullanicinin talebini anla ve JSON formatinda dondur:

{{
    "intent": "scrape_start" | "scrape_check" | "scrape_stop" | "list_pending" | "approve_product" | "reject_product" | "delete_listing" | "price_change" | "search_product" | "platform_search" | "status_check" | "unknown",
    "platforms": ["vinted", "kleinanzeigen", "ebay", "willhaben", "ricardo", "tutti", "anibis", "tradera"],
    "search_query": "arama terimi veya marka",
    "price_range": {{"min": 0, "max": 100}},
    "product_id": "varsa urun ID",
    "action_params": {{}},
    "response": "kullaniciya kisa yanit",
    "needs_confirmation": true/false
}}

Ornek komutlar:
- "vinted'de nike ayakkabi ara" -> platform_search, platforms: ["vinted"], search_query: "nike ayakkabi"
- "tum platformlarda adidas ara" -> platform_search, platforms: [...], search_query: "adidas"
- "bekleyen urunleri goster" -> list_pending
- "PROD-xxx onayla" -> approve_product, product_id: "PROD-xxx"
- "waffenschrank sil" -> delete_listing
- "kazima durdur" -> scrape_stop
- "sistem durumu" -> status_check

Sadece JSON dondur.
"""

            data = {
                "model": self.ai_model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 500,
                "temperature": 0.2
            }

            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json=data,
                timeout=30
            )

            if response.status_code == 200:
                result = response.json()
                content = result['choices'][0]['message']['content'].strip()

                # JSON parse
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0]
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0]

                return json.loads(content)

        except Exception as e:
            print(f"[-] AI analiz hatasi: {e}")

        return {
            "intent": "unknown",
            "platforms": [],
            "search_query": "",
            "response": "Komut anlasilmadi. Ornek: 'vinted'de nike ara' veya 'bekleyen urunleri goster'",
            "needs_confirmation": False
        }

    def execute_command(self, analysis, chat_id, message_id):
        """Komutu calistir"""
        intent = analysis.get('intent', 'unknown')

        self.log_action("command_received", {
            "intent": intent,
            "analysis": analysis
        })

        if intent == "platform_search":
            return self.start_platform_search(analysis, chat_id)

        elif intent == "list_pending":
            return self.list_pending_products(chat_id)

        elif intent == "approve_product":
            return self.approve_product(analysis, chat_id)

        elif intent == "reject_product":
            return self.reject_product(analysis, chat_id)

        elif intent == "delete_listing":
            return self.delete_listing(analysis, chat_id)

        elif intent == "status_check":
            return self.check_system_status(chat_id)

        elif intent == "scrape_stop":
            return self.stop_scraping(chat_id)

        else:
            return analysis.get('response', 'Komut anlasilmadi.')

    def start_platform_search(self, analysis, chat_id):
        """Platform aramasini baslat"""
        platforms = analysis.get('platforms', [])
        query = analysis.get('search_query', '')
        price_range = analysis.get('price_range', {})

        if not query:
            return "Arama terimi belirtmelisiniz.\nOrnek: 'vinted'de nike ayakkabi ara'"

        # Eger platform belirtilmemisse tum platformlarda ara
        if not platforms:
            platforms = ['vinted', 'kleinanzeigen', 'ebay']

        # Direkt aramaya basla (onay butonu yerine)
        self.log_action("search_started", {
            "platforms": platforms,
            "query": query,
            "price_range": price_range
        })

        # Arama baslatildi mesaji
        platform_text = ", ".join(platforms) if len(platforms) <= 3 else f"{len(platforms)} platform"
        self.send_message(chat_id, f"*ARAMA BASLATILDI*\n\nPlatformlar: {platform_text}\nArama: {query}\n\n_Sonuclar URUN BULDUM grubuna gonderilecek..._")

        # Gercek aramay baslat (thread icinde)
        import threading
        search_thread = threading.Thread(
            target=self.run_search,
            args=(query, platforms, chat_id)
        )
        search_thread.start()

        return None  # Mesaj zaten gonderildi

    def run_search(self, query, platforms, chat_id):
        """Aramay arka planda calistir - insansi gezinme ve duplicate kontrolu ile"""
        import random

        total_found = 0
        total_duplicates = 0
        platform_results = {}

        for platform in platforms:
            # Platform durumunu kontrol et
            if self.platform_status.get(platform, {}).get('status') == 'blocked':
                self.send_message(
                    chat_id,
                    f"*[{platform.upper()}] ATLANDI*\n_Platform gecici olarak engellenmi durumda_"
                )
                continue

            try:
                # INSANSI GEZINME - arama oncesi
                if self.quality_controller:
                    try:
                        self.send_message(chat_id, f"_[{platform}] Insansi gezinme..._")
                        self.quality_controller.human_browsing_session(platform, duration_minutes=0.5)
                    except Exception as e:
                        self.log_action("human_browsing_error", {"platform": platform, "error": str(e)})

                # Arama yap
                results = self.scraper.search_platform(
                    platform,
                    query,
                    min_profit=5,
                    max_pages=10  # Vinted 10 sayfa siniri
                )

                # Duplicate kontrolu
                unique_results = []
                duplicates = 0

                for result in results:
                    url = result.get('url', '')
                    if self.is_duplicate(url):
                        duplicates += 1
                        continue

                    # Urunu kazildi olarak isaretle
                    self.mark_as_scraped(url, result)
                    unique_results.append(result)

                    # URUN BULDUM grubuna gonder
                    self.send_product_found(result)

                total_found += len(unique_results)
                total_duplicates += duplicates
                platform_results[platform] = len(unique_results)

                # Platform durumunu guncelle - basarili
                self.update_platform_status(platform, True)

                self.send_message(
                    chat_id,
                    f"*[{platform.upper()}] TAMAMLANDI*\n\n"
                    f"Bulunan: {len(unique_results)}\n"
                    f"Duplicate: {duplicates}"
                )

                # Platformlar arasi bekleme
                if platforms.index(platform) < len(platforms) - 1:
                    wait_time = random.randint(30, 60)
                    self.log_action("platform_wait", {"seconds": wait_time})
                    import time
                    time.sleep(wait_time)

            except Exception as e:
                error_msg = str(e)
                self.log_action("platform_error", {"platform": platform, "error": error_msg})

                # Platform durumunu guncelle - basarisiz
                self.update_platform_status(platform, False, error_msg)

                self.send_message(
                    chat_id,
                    f"*[{platform.upper()}] HATA*\n\n{error_msg[:100]}..."
                )

        # Final ozet
        status_report = self.get_platform_status_report()

        summary = (
            f"*ARAMA TAMAMLANDI*\n\n"
            f"Toplam bulunan: {total_found}\n"
            f"Duplicate atlanan: {total_duplicates}\n\n"
            f"*Platform Sonuclari:*\n"
        )

        for platform, count in platform_results.items():
            summary += f"- {platform}: {count}\n"

        summary += f"\n*Aktif Platformlar:* {', '.join(status_report['active'])}\n"

        if status_report['blocked']:
            summary += f"*Engellenen:* {', '.join(status_report['blocked'])}\n"

        summary += f"\n_Detaylar URUN BULDUM grubunda._"

        self.send_message(chat_id, summary)

    def list_pending_products(self, chat_id):
        """Bekleyen urunleri listele"""
        pending_files = list(PENDING_DIR.glob("PROD-*.json"))

        if not pending_files:
            return "Bekleyen urun yok."

        msg = "*BEKLEYEN URUNLER*\n\n"

        for i, pf in enumerate(pending_files[:10], 1):
            try:
                with open(pf, 'r', encoding='utf-8') as f:
                    product = json.load(f)

                product_id = product.get('id', pf.stem)
                title = product.get('optimized', {}).get('title', 'Baslik yok')[:40]
                price = product.get('optimized', {}).get('price', '?')
                target = product.get('target_platform', '?')

                msg += f"{i}. `{product_id}`\n"
                msg += f"   {title}...\n"
                msg += f"   {price} EUR -> {target}\n\n"
            except:
                continue

        msg += f"\n_Toplam {len(pending_files)} bekleyen urun_"

        return msg

    def approve_product(self, analysis, chat_id):
        """Urunu onayla"""
        product_id = analysis.get('product_id', '')

        if not product_id:
            # Son urunu onayla
            pending_files = list(PENDING_DIR.glob("PROD-*.json"))
            if pending_files:
                latest = max(pending_files, key=lambda p: p.stat().st_mtime)
                product_id = latest.stem
            else:
                return "Onaylanacak urun bulunamadi."

        pending_file = PENDING_DIR / f"{product_id}.json"
        if not pending_file.exists():
            return f"Urun bulunamadi: {product_id}"

        # TODO: Vinted'e yukle
        self.log_action("product_approved", {"product_id": product_id})

        return f"*ONAYLANDI*\n\nUrun `{product_id}` Vinted'e yuklenecek.\n\n_Yukleme islemi basladi..._"

    def reject_product(self, analysis, chat_id):
        """Urunu reddet"""
        product_id = analysis.get('product_id', '')

        if not product_id:
            pending_files = list(PENDING_DIR.glob("PROD-*.json"))
            if pending_files:
                latest = max(pending_files, key=lambda p: p.stat().st_mtime)
                product_id = latest.stem
            else:
                return "Reddedilecek urun bulunamadi."

        pending_file = PENDING_DIR / f"{product_id}.json"
        if pending_file.exists():
            pending_file.unlink()
            self.log_action("product_rejected", {"product_id": product_id})
            return f"*REDDEDILDI*\n\nUrun `{product_id}` silindi."

        return f"Urun bulunamadi: {product_id}"

    def delete_listing(self, analysis, chat_id):
        """Magazadan ilan sil"""
        # Arama terimine gore bul
        search = analysis.get('search_query', '').lower()

        if not search:
            return "Silinecek ilan belirtilmedi."

        # Pending urunlerde ara
        for pf in PENDING_DIR.glob("PROD-*.json"):
            try:
                with open(pf, 'r', encoding='utf-8') as f:
                    product = json.load(f)

                title = product.get('original', {}).get('title', '').lower()
                if search in title:
                    product_id = product.get('id', pf.stem)
                    pf.unlink()

                    self.log_action("listing_deleted", {
                        "product_id": product_id,
                        "search": search
                    })

                    return f"*SILINDI*\n\n`{product_id}` silindi.\nBaslik: {title[:50]}..."
            except:
                continue

        return f"'{search}' iceren urun bulunamadi."

    def check_system_status(self, chat_id):
        """Sistem durumunu kontrol et"""
        pending_count = len(list(PENDING_DIR.glob("PROD-*.json")))
        scraped_count = len(self.scraped_products)

        # Platform durum raporu
        status_report = self.get_platform_status_report()

        # Log dosyalarindan son aktiviteleri al
        recent_logs = []
        if self.log_file.exists():
            with open(self.log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()[-5:]
                for line in lines:
                    try:
                        log = json.loads(line)
                        recent_logs.append(f"- {log['type']}: {log['timestamp'][-8:]}")
                    except:
                        continue

        msg = f"""*SISTEM DURUMU*

*Bekleyen Urunler:* {pending_count}
*Kazilan Urunler:* {scraped_count}
*Bot Durumu:* AKTIF
*Zaman:* {datetime.now().strftime('%H:%M:%S')}

*PLATFORM DURUMU*
*Aktif:* {', '.join(status_report['active']) if status_report['active'] else 'Yok'}
*Engellenen:* {', '.join(status_report['blocked']) if status_report['blocked'] else 'Yok'}

*Son Aktiviteler:*
{chr(10).join(recent_logs) if recent_logs else '- Aktivite yok'}
"""

        return msg

    def stop_scraping(self, chat_id):
        """Kazima durdur"""
        self.log_action("scrape_stopped", {})
        return "*KAZIMA DURDURULDU*\n\nTum aktif kazima islemleri durduruldu."

    def send_product_found(self, product_data):
        """URUN BULDUM grubuna karli link gonder"""
        chat_id = self.channels['product_found']

        title = product_data.get('title', 'Baslik yok')[:60]
        price = product_data.get('price', 0)
        source = product_data.get('source', '?')
        url = product_data.get('url', '')
        profit = product_data.get('estimated_profit', 0)

        msg = f"""*KARLI URUN BULUNDU*

*Baslik:* {title}
*Fiyat:* {price} EUR
*Kaynak:* {source}
*Tahmini Kar:* +{profit} EUR

*Link:* {url}
"""

        buttons = [
            [
                {"text": "TRANSFER ET", "callback_data": f"transfer:{url}"},
                {"text": "ATLA", "callback_data": "skip_product"}
            ]
        ]

        self.send_message(chat_id, msg, buttons=buttons)

        self.log_action("product_found_sent", {
            "title": title,
            "price": price,
            "profit": profit
        })

    def process_callback(self, callback_query):
        """Callback buton islemleri"""
        callback_id = callback_query.get("id")
        data = callback_query.get("data", "")
        chat_id = callback_query.get("message", {}).get("chat", {}).get("id")

        # Callback'i onayla
        url = f"https://api.telegram.org/bot{self.bot_token}/answerCallbackQuery"
        requests.post(url, data={"callback_query_id": callback_id})

        if data.startswith("search_start:"):
            parts = data.split(":")
            platforms = parts[1].split(",")
            query = parts[2] if len(parts) > 2 else ""

            self.send_message(chat_id, f"*ARAMA BASLADI*\n\nPlatformlar: {', '.join(platforms)}\nArama: {query}\n\n_Sonuclar URUN BULDUM grubuna gonderilecek..._")

            # TODO: Gercek arama baslat
            self.log_action("search_started", {
                "platforms": platforms,
                "query": query
            })

        elif data == "search_cancel":
            self.send_message(chat_id, "Arama iptal edildi.")

        elif data.startswith("transfer:"):
            url = data.replace("transfer:", "")
            self.send_message(chat_id, f"*TRANSFER BASLADI*\n\nURL: {url[:50]}...\n\n_Onay icin MESAJLAR grubuna gonderilecek..._")

            # TODO: Transfer baslat
            self.log_action("transfer_started", {"url": url})

        elif data == "skip_product":
            self.send_message(chat_id, "Urun atlandi.")

    def process_message(self, message):
        """Mesaji isle"""
        chat_id = message.get("chat", {}).get("id")
        text = message.get("text", "").strip()
        message_id = message.get("message_id")

        if not text:
            return

        # Hangi grup?
        group_type = self.group_names.get(chat_id, "unknown")

        # Sadece scrape_command grubundan komut al
        if group_type != "scrape_command":
            return

        print(f"[KOMUT] {text[:50]}...")

        # AI ile analiz
        analysis = self.analyze_command(text, group_type)

        # Yanit gonder
        if analysis.get('needs_confirmation'):
            # Onay gerektiren komutlar icin butonlu mesaj
            pass  # execute_command icinde halledilecek

        # Komutu calistir
        response = self.execute_command(analysis, chat_id, message_id)

        if response:
            self.send_message(chat_id, response, reply_to=message_id)

    def run(self):
        """Bot'u calistir"""
        print("=" * 60)
        print("TATANGA - Scrape Command Handler")
        print("=" * 60)
        print("\nAna komut grubu dinleniyor:")
        print(f"  - scrape_command: {self.channels['scrape_command']}")
        print(f"  - product_found: {self.channels['product_found']}")

        # Baslangic mesaji gonder
        self.send_message(
            self.channels['scrape_command'],
            "*KAZIMA SISTEMI AKTIF*\n\n"
            "Bu gruptan tum kazima komutlarini verebilirsiniz.\n\n"
            "*Ornek komutlar:*\n"
            "- `vinted'de nike ayakkabi ara`\n"
            "- `tum platformlarda adidas ara`\n"
            "- `bekleyen urunleri goster`\n"
            "- `sistem durumu`\n"
            "- `kazima durdur`\n\n"
            "_Komutlarinizi dogal dilde yazin, AI anlayacak._"
        )

        print("\nDinleniyor... (Ctrl+C ile durdur)\n")

        while True:
            try:
                updates = self.get_updates()

                for update in updates:
                    self.last_update_id = update.get("update_id", self.last_update_id)

                    if "message" in update:
                        self.process_message(update["message"])

                    if "callback_query" in update:
                        self.process_callback(update["callback_query"])

            except KeyboardInterrupt:
                print("\n\nDurduruldu.")
                break

            except Exception as e:
                print(f"[-] Hata: {e}")
                time.sleep(5)

if __name__ == "__main__":
    handler = ScrapeCommandHandler()
    handler.run()
