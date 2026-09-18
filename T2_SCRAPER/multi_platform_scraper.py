#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TATANGA - Multi-Platform Scraper Engine V2
Tum platformlarda cok dilli arama, self-learning AI, SEO optimizasyonu
"""

import sys
import json
import time
import random
import requests
import re
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.config.credentials import (
    TELEGRAM, AI_SERVICES, PROXY,
    KLEINANZEIGEN, VINTED, EBAY, WILLHABEN, HETZNER
)

# Dizinler
BASE_DIR = Path(__file__).parent.parent
LOG_DIR = BASE_DIR / "logs"
OUTPUT_DIR = BASE_DIR / "T2_SCRAPER" / "output"
CACHE_DIR = BASE_DIR / "T2_SCRAPER" / "cache"
LEARNING_DIR = BASE_DIR / "T2_SCRAPER" / "learning"

LOG_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)
CACHE_DIR.mkdir(exist_ok=True)
LEARNING_DIR.mkdir(exist_ok=True)

class MultiPlatformScraper:
    """Coklu platform kazima motoru - V2"""

    def __init__(self):
        self.bot_token = TELEGRAM['bot_token']
        self.channels = TELEGRAM['channels']
        self.ai_key = AI_SERVICES['groq']['api_key']
        self.ai_model = AI_SERVICES['groq']['model']
        self.hetzner = HETZNER

        # Ulke ve dil eslestirme
        self.country_languages = {
            'de': {'name': 'Almanya', 'lang': 'de', 'currency': 'EUR'},
            'at': {'name': 'Avusturya', 'lang': 'de', 'currency': 'EUR'},
            'ch': {'name': 'Isvicre', 'lang': 'de', 'currency': 'CHF'},
            'nl': {'name': 'Hollanda', 'lang': 'nl', 'currency': 'EUR'},
            'be': {'name': 'Belcika', 'lang': 'nl', 'currency': 'EUR'},
            'fr': {'name': 'Fransa', 'lang': 'fr', 'currency': 'EUR'},
            'it': {'name': 'Italya', 'lang': 'it', 'currency': 'EUR'},
            'es': {'name': 'Ispanya', 'lang': 'es', 'currency': 'EUR'},
            'se': {'name': 'Isvec', 'lang': 'sv', 'currency': 'SEK'},
            'pl': {'name': 'Polonya', 'lang': 'pl', 'currency': 'PLN'},
        }

        # Platform konfigurasyonlari - GENISLETILMIS
        self.platforms = {
            # ALMANYA
            'vinted_de': {
                'name': 'Vinted DE',
                'country': 'de',
                'base_url': 'https://www.vinted.de',
                'search_url': 'https://www.vinted.de/catalog?search_text={query}',
                'enabled': True,
                'rate_limit': 2,
                'max_pages': 5,
                'ban_risk': 'medium',
                'requires_selenium': True
            },
            'kleinanzeigen': {
                'name': 'Kleinanzeigen',
                'country': 'de',
                'base_url': 'https://www.kleinanzeigen.de',
                'search_url': 'https://www.kleinanzeigen.de/s-{query}/k0',
                'enabled': True,
                'rate_limit': 3,
                'max_pages': 10,
                'ban_risk': 'low',
                'requires_selenium': False
            },
            'ebay_de': {
                'name': 'eBay DE',
                'country': 'de',
                'base_url': 'https://www.ebay.de',
                'search_url': 'https://www.ebay.de/sch/i.html?_nkw={query}',
                'enabled': True,
                'rate_limit': 1,
                'max_pages': 5,
                'ban_risk': 'low',
                'requires_selenium': False
            },
            'shpock_de': {
                'name': 'Shpock DE',
                'country': 'de',
                'base_url': 'https://www.shpock.com/de-de',
                'search_url': 'https://www.shpock.com/de-de/q/{query}',
                'enabled': True,
                'rate_limit': 2,
                'max_pages': 5,
                'ban_risk': 'medium',
                'requires_selenium': True
            },
            'selpy': {
                'name': 'Selpy',
                'country': 'de',
                'base_url': 'https://www.selpy.de',
                'search_url': 'https://www.selpy.de/search?q={query}',
                'enabled': True,
                'rate_limit': 2,
                'max_pages': 3,
                'ban_risk': 'low',
                'requires_selenium': False
            },
            'percentil': {
                'name': 'Percentil',
                'country': 'de',
                'base_url': 'https://www.percentil.de',
                'search_url': 'https://www.percentil.de/search?q={query}',
                'enabled': True,
                'rate_limit': 2,
                'max_pages': 3,
                'ban_risk': 'low',
                'requires_selenium': False
            },
            # AVUSTURYA
            'willhaben': {
                'name': 'Willhaben',
                'country': 'at',
                'base_url': 'https://www.willhaben.at',
                'search_url': 'https://www.willhaben.at/iad/kaufen-und-verkaufen/marktplatz?keyword={query}',
                'enabled': True,
                'rate_limit': 2,
                'max_pages': 5,
                'ban_risk': 'medium',
                'requires_selenium': True
            },
            'shpock_at': {
                'name': 'Shpock AT',
                'country': 'at',
                'base_url': 'https://www.shpock.com/de-at',
                'search_url': 'https://www.shpock.com/de-at/q/{query}',
                'enabled': True,
                'rate_limit': 2,
                'max_pages': 5,
                'ban_risk': 'medium',
                'requires_selenium': True
            },
            # ISVICRE
            'ricardo': {
                'name': 'Ricardo',
                'country': 'ch',
                'base_url': 'https://www.ricardo.ch',
                'search_url': 'https://www.ricardo.ch/de/s/{query}',
                'enabled': True,
                'rate_limit': 2,
                'max_pages': 3,
                'ban_risk': 'medium',
                'requires_selenium': True
            },
            'tutti': {
                'name': 'Tutti',
                'country': 'ch',
                'base_url': 'https://www.tutti.ch',
                'search_url': 'https://www.tutti.ch/de/li?q={query}',
                'enabled': True,
                'rate_limit': 2,
                'max_pages': 3,
                'ban_risk': 'low',
                'requires_selenium': False
            },
            'anibis': {
                'name': 'Anibis',
                'country': 'ch',
                'base_url': 'https://www.anibis.ch',
                'search_url': 'https://www.anibis.ch/de/c/alle-kategorien?fts={query}',
                'enabled': True,
                'rate_limit': 2,
                'max_pages': 3,
                'ban_risk': 'low',
                'requires_selenium': False
            },
            # FRANSA
            'vinted_fr': {
                'name': 'Vinted FR',
                'country': 'fr',
                'base_url': 'https://www.vinted.fr',
                'search_url': 'https://www.vinted.fr/catalog?search_text={query}',
                'enabled': True,
                'rate_limit': 2,
                'max_pages': 5,
                'ban_risk': 'medium',
                'requires_selenium': True
            },
            'leboncoin': {
                'name': 'Leboncoin',
                'country': 'fr',
                'base_url': 'https://www.leboncoin.fr',
                'search_url': 'https://www.leboncoin.fr/recherche?text={query}',
                'enabled': True,
                'rate_limit': 3,
                'max_pages': 5,
                'ban_risk': 'high',
                'requires_selenium': True
            },
            # HOLLANDA/BELCIKA
            'marktplaats': {
                'name': 'Marktplaats',
                'country': 'nl',
                'base_url': 'https://www.marktplaats.nl',
                'search_url': 'https://www.marktplaats.nl/q/{query}/',
                'enabled': True,
                'rate_limit': 2,
                'max_pages': 5,
                'ban_risk': 'medium',
                'requires_selenium': True
            },
            '2dehands': {
                'name': '2dehands',
                'country': 'be',
                'base_url': 'https://www.2dehands.be',
                'search_url': 'https://www.2dehands.be/q/{query}/',
                'enabled': True,
                'rate_limit': 2,
                'max_pages': 5,
                'ban_risk': 'medium',
                'requires_selenium': True
            },
            # ITALYA
            'subito': {
                'name': 'Subito',
                'country': 'it',
                'base_url': 'https://www.subito.it',
                'search_url': 'https://www.subito.it/annunci-italia/vendita/usato/?q={query}',
                'enabled': True,
                'rate_limit': 2,
                'max_pages': 5,
                'ban_risk': 'medium',
                'requires_selenium': True
            },
            # ISVEC
            'tradera': {
                'name': 'Tradera',
                'country': 'se',
                'base_url': 'https://www.tradera.com',
                'search_url': 'https://www.tradera.com/search?q={query}',
                'enabled': True,
                'rate_limit': 2,
                'max_pages': 3,
                'ban_risk': 'low',
                'requires_selenium': False
            },
            'blocket': {
                'name': 'Blocket',
                'country': 'se',
                'base_url': 'https://www.blocket.se',
                'search_url': 'https://www.blocket.se/annonser?q={query}',
                'enabled': True,
                'rate_limit': 2,
                'max_pages': 3,
                'ban_risk': 'medium',
                'requires_selenium': True
            },
        }

        # Kategori cevirileri
        self.category_translations = {
            'mont': {
                'de': 'jacke winterjacke mantel',
                'fr': 'veste manteau',
                'nl': 'jas winterjas',
                'it': 'giacca cappotto',
                'es': 'chaqueta abrigo',
                'sv': 'jacka kappa',
                'pl': 'kurtka plaszcz'
            },
            'ayakkabi': {
                'de': 'schuhe sneaker',
                'fr': 'chaussures baskets',
                'nl': 'schoenen sneakers',
                'it': 'scarpe sneakers',
                'es': 'zapatos zapatillas',
                'sv': 'skor sneakers',
                'pl': 'buty'
            },
            'canta': {
                'de': 'tasche handtasche',
                'fr': 'sac sacoche',
                'nl': 'tas handtas',
                'it': 'borsa',
                'es': 'bolso',
                'sv': 'vaska',
                'pl': 'torba'
            },
            'elbise': {
                'de': 'kleid',
                'fr': 'robe',
                'nl': 'jurk',
                'it': 'vestito abito',
                'es': 'vestido',
                'sv': 'klanninng',
                'pl': 'sukienka'
            },
            'pantolon': {
                'de': 'hose jeans',
                'fr': 'pantalon jean',
                'nl': 'broek jeans',
                'it': 'pantaloni jeans',
                'es': 'pantalon vaqueros',
                'sv': 'byxor jeans',
                'pl': 'spodnie'
            }
        }

        # Log dosyasi
        self.log_file = LOG_DIR / f"scraper_{datetime.now().strftime('%Y%m%d')}.jsonl"

        # Learning dosyasi
        self.learning_file = LEARNING_DIR / "scraper_learning.json"
        self.load_learning_data()

    def load_learning_data(self):
        """Ogrenme verilerini yukle"""
        if self.learning_file.exists():
            with open(self.learning_file, 'r', encoding='utf-8') as f:
                self.learning_data = json.load(f)
        else:
            self.learning_data = {
                "platform_success_rates": {},
                "query_patterns": {},
                "error_patterns": {},
                "selector_updates": {}
            }

    def save_learning_data(self):
        """Ogrenme verilerini kaydet"""
        with open(self.learning_file, 'w', encoding='utf-8') as f:
            json.dump(self.learning_data, f, ensure_ascii=False, indent=2)

    def log(self, level, message, data=None):
        """Detayli log"""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "level": level,
            "message": message,
            "data": data or {}
        }
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

        if level in ['ERROR', 'WARNING']:
            print(f"[{level}] {message}")

    def send_telegram(self, chat_id, text, buttons=None):
        """Telegram mesaji gonder"""
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        data = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }
        if buttons:
            data["reply_markup"] = json.dumps({"inline_keyboard": buttons})

        try:
            requests.post(url, data=data, timeout=10)
        except Exception as e:
            self.log("ERROR", f"Telegram gonderim hatasi: {e}")

    def translate_query(self, query, target_lang):
        """Arama terimini hedef dile cevir"""
        # Kategori cevirisi kontrol
        query_lower = query.lower()
        for tr_key, translations in self.category_translations.items():
            if tr_key in query_lower:
                if target_lang in translations:
                    return translations[target_lang]

        # AI ile ceviri
        if target_lang != 'de':  # Turkce'den ceviriyoruz
            try:
                headers = {
                    "Authorization": f"Bearer {self.ai_key}",
                    "Content-Type": "application/json"
                }

                lang_names = {
                    'de': 'Almanca', 'fr': 'Fransizca', 'nl': 'Felemenkce',
                    'it': 'Italyanca', 'es': 'Ispanyolca', 'sv': 'Isveççe', 'pl': 'Lehce'
                }

                prompt = f"""
Asagidaki Turkce arama terimini {lang_names.get(target_lang, target_lang)} diline cevir.
Sadece cevirilmis kelimeyi/kelimeleri yaz, baska bir sey yazma.

Turkce: {query}
{lang_names.get(target_lang, target_lang)}:"""

                data = {
                    "model": self.ai_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 50,
                    "temperature": 0.1
                }

                response = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers=headers,
                    json=data,
                    timeout=10
                )

                if response.status_code == 200:
                    result = response.json()
                    translated = result['choices'][0]['message']['content'].strip()
                    self.log("INFO", f"Ceviri: {query} -> {translated} ({target_lang})")
                    return translated

            except Exception as e:
                self.log("WARNING", f"Ceviri hatasi: {e}")

        return query  # Ceviri basarisiz, orjinali kullan

    def analyze_profit(self, product, source_platform):
        """AI ile kar analizi yap"""
        try:
            headers = {
                "Authorization": f"Bearer {self.ai_key}",
                "Content-Type": "application/json"
            }

            platform_info = self.platforms.get(source_platform, {})
            country = platform_info.get('country', 'de')

            prompt = f"""
Urun kar analizi yap:

Baslik: {product.get('title', '')}
Fiyat: {product.get('price', 0)} {self.country_languages.get(country, {}).get('currency', 'EUR')}
Platform: {platform_info.get('name', source_platform)}
Ulke: {self.country_languages.get(country, {}).get('name', country)}

Bu urun Almanya'daki platformlarda (Vinted, eBay, Kleinanzeigen) ne kadara satabilirim?
Kar marji en az %20 olmali.

JSON formatinda dondur:
{{
    "estimated_sell_price": 0,
    "estimated_profit": 0,
    "profit_margin_percent": 0,
    "recommendation": "buy" | "skip" | "watch",
    "reason": "kisa aciklama",
    "best_platform_to_sell": "platform adi",
    "seo_title_de": "Almanca SEO baslik",
    "seo_description_de": "Almanca SEO aciklama (max 200 karakter)"
}}

Sadece JSON dondur.
"""

            data = {
                "model": self.ai_model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 400,
                "temperature": 0.3
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

                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0]
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0]

                return json.loads(content)

        except Exception as e:
            self.log("ERROR", f"Kar analizi hatasi: {e}")

        return {
            "estimated_sell_price": product.get('price', 0) * 1.3,
            "estimated_profit": product.get('price', 0) * 0.3,
            "profit_margin_percent": 30,
            "recommendation": "watch",
            "reason": "Analiz yapilamadi",
            "best_platform_to_sell": "vinted",
            "seo_title_de": product.get('title', ''),
            "seo_description_de": ""
        }

    def learn_from_error(self, platform_key, error_msg):
        """Hatadan ogren ve sistemi guncelle"""
        self.log("INFO", f"Hatadan ogreniliyor: {platform_key}")

        # Hata pattern'ini kaydet
        if platform_key not in self.learning_data["error_patterns"]:
            self.learning_data["error_patterns"][platform_key] = []

        self.learning_data["error_patterns"][platform_key].append({
            "timestamp": datetime.now().isoformat(),
            "error": error_msg[:200]
        })

        # AI ile cozum onerisi al
        try:
            headers = {
                "Authorization": f"Bearer {self.ai_key}",
                "Content-Type": "application/json"
            }

            prompt = f"""
Web scraping hatasi analizi:

Platform: {platform_key}
Hata: {error_msg}

Bu hatayi cozmek icin ne yapilmali?
JSON formatinda dondur:
{{
    "solution_type": "rate_limit" | "proxy" | "selector_update" | "captcha" | "retry" | "skip",
    "action": "yapilacak islem",
    "new_rate_limit": 0,
    "should_disable": false
}}

Sadece JSON dondur.
"""

            data = {
                "model": self.ai_model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 200,
                "temperature": 0.2
            }

            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json=data,
                timeout=15
            )

            if response.status_code == 200:
                result = response.json()
                content = result['choices'][0]['message']['content'].strip()

                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0]
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0]

                solution = json.loads(content)

                # Cozumu uygula
                if solution.get('solution_type') == 'rate_limit':
                    new_limit = solution.get('new_rate_limit', 5)
                    if new_limit > 0:
                        self.platforms[platform_key]['rate_limit'] = new_limit
                        self.log("INFO", f"Rate limit guncellendi: {new_limit}s")

                elif solution.get('should_disable'):
                    self.platforms[platform_key]['enabled'] = False
                    self.log("WARNING", f"Platform devre disi birakildi: {platform_key}")

                # Ogrenilenteri kaydet
                self.save_learning_data()

                return solution

        except Exception as e:
            self.log("ERROR", f"Ogrenme hatasi: {e}")

        return None

    def scrape_platform(self, platform_key, query, max_results=50):
        """Tek bir platformu tara"""
        platform = self.platforms.get(platform_key)
        if not platform or not platform['enabled']:
            return []

        # Platform diline cevir
        country = platform.get('country', 'de')
        lang = self.country_languages.get(country, {}).get('lang', 'de')
        translated_query = self.translate_query(query, lang)

        self.log("INFO", f"{platform['name']} taraniyor: {translated_query} ({lang})")

        products = []

        try:
            # Basit HTTP tarama
            products = self.scrape_http(platform_key, translated_query, max_results)

            # Basari oranini guncelle
            if platform_key not in self.learning_data["platform_success_rates"]:
                self.learning_data["platform_success_rates"][platform_key] = {"success": 0, "fail": 0}

            if products:
                self.learning_data["platform_success_rates"][platform_key]["success"] += 1
            else:
                self.learning_data["platform_success_rates"][platform_key]["fail"] += 1

            self.save_learning_data()

            self.log("INFO", f"{platform['name']}: {len(products)} urun bulundu")

        except Exception as e:
            error_msg = str(e)
            self.log("ERROR", f"{platform['name']} hatasi: {error_msg}")

            # Hatadan ogren
            solution = self.learn_from_error(platform_key, error_msg)

            # Hata grubuna bildir
            self.send_telegram(
                self.channels['system'],
                f"*SCRAPER HATASI*\n\n"
                f"Platform: {platform['name']}\n"
                f"Hata: {error_msg[:150]}\n\n"
                f"_Cozum: {solution.get('action', 'Tekrar denenecek') if solution else 'Analiz edilecek'}_"
            )

        return products

    def scrape_http(self, platform_key, query, max_results):
        """HTTP ile tara"""
        platform = self.platforms.get(platform_key)
        products = []

        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept-Language': 'de-DE,de;q=0.9,en;q=0.8'
            }

            search_url = platform['search_url'].format(query=query.replace(' ', '+'))

            response = requests.get(search_url, headers=headers, timeout=30)

            if response.status_code == 200:
                # Platform-specific parsing
                if 'ebay' in platform_key:
                    products = self.parse_ebay(response.text, max_results, platform_key)
                elif 'kleinanzeigen' in platform_key:
                    products = self.parse_kleinanzeigen(response.text, max_results)
                elif 'tutti' in platform_key:
                    products = self.parse_tutti(response.text, max_results)
                elif 'anibis' in platform_key:
                    products = self.parse_anibis(response.text, max_results)
                else:
                    # Generic parsing
                    products = self.parse_generic(response.text, max_results, platform_key)

            # Rate limiting
            time.sleep(platform['rate_limit'])

        except Exception as e:
            raise e

        return products

    def parse_ebay(self, html, max_results, platform_key):
        """eBay sonuclarini parse et"""
        products = []
        pattern = r'<div class="s-item__wrapper.*?<a.*?href="([^"]+)".*?<span[^>]*>([^<]+)</span>.*?<span class="s-item__price">([^<]+)</span>'

        matches = re.findall(pattern, html, re.DOTALL)[:max_results]

        for url, title, price in matches:
            price_clean = re.sub(r'[^\d,.]', '', price).replace(',', '.')
            try:
                price_value = float(price_clean.split()[0]) if price_clean else 0
            except:
                price_value = 0

            products.append({
                'title': title.strip()[:100],
                'price': price_value,
                'url': url,
                'source': platform_key
            })

        return products

    def parse_kleinanzeigen(self, html, max_results):
        """Kleinanzeigen sonuclarini parse et"""
        products = []
        pattern = r'<article.*?data-adid="(\d+)".*?<a.*?href="(/s-anzeige/[^"]+)"[^>]*>([^<]+)</a>.*?<p[^>]*class="[^"]*price[^"]*"[^>]*>([^<]+)</p>'

        matches = re.findall(pattern, html, re.DOTALL)[:max_results]

        for ad_id, url, title, price in matches:
            price_clean = re.sub(r'[^\d]', '', price)
            try:
                price_value = int(price_clean) if price_clean else 0
            except:
                price_value = 0

            products.append({
                'title': title.strip()[:100],
                'price': price_value,
                'url': f"https://www.kleinanzeigen.de{url}",
                'source': 'kleinanzeigen'
            })

        return products

    def parse_tutti(self, html, max_results):
        """Tutti sonuclarini parse et"""
        products = []
        # Tutti JSON data iceriyor genelde
        try:
            json_match = re.search(r'<script[^>]*>window\.__INITIAL_STATE__\s*=\s*({.*?})</script>', html, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(1))
                # Parse Tutti data structure
        except:
            pass
        return products

    def parse_anibis(self, html, max_results):
        """Anibis sonuclarini parse et"""
        products = []
        return products

    def parse_generic(self, html, max_results, platform_key):
        """Generic parsing"""
        products = []
        # Basit URL ve baslik yakalama
        pattern = r'<a[^>]*href="([^"]*)"[^>]*>([^<]{10,100})</a>.*?(\d+[.,]?\d*)\s*(?:EUR|CHF|€)'

        matches = re.findall(pattern, html, re.DOTALL)[:max_results]

        for url, title, price in matches:
            try:
                price_value = float(price.replace(',', '.'))
            except:
                price_value = 0

            if not url.startswith('http'):
                base = self.platforms[platform_key]['base_url']
                url = f"{base}{url}"

            products.append({
                'title': title.strip()[:100],
                'price': price_value,
                'url': url,
                'source': platform_key
            })

        return products

    def search_all_platforms(self, query, platforms=None, min_profit=5):
        """Tum platformlarda ara"""
        if platforms is None:
            # Varsayilan: tum aktif platformlar
            platforms = [k for k, v in self.platforms.items() if v['enabled']]

        search_id = f"SEARCH-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        self.log("INFO", f"Arama baslatildi: {search_id}", {
            "query": query,
            "platforms": platforms
        })

        # Kazima grubuna bilgi ver
        self.send_telegram(
            self.channels['scrape_command'],
            f"*ARAMA BASLATILDI*\n\n"
            f"ID: `{search_id}`\n"
            f"Arama: {query}\n"
            f"Platformlar: {len(platforms)} site\n\n"
            f"_Her platform kendi dilinde aranacak..._"
        )

        all_products = []
        platform_results = {}

        # Paralel tarama
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {
                executor.submit(self.scrape_platform, p, query): p
                for p in platforms
            }

            for future in as_completed(futures):
                platform = futures[future]
                try:
                    products = future.result()
                    platform_results[platform] = len(products)
                    all_products.extend(products)
                except Exception as e:
                    self.log("ERROR", f"{platform} future hatasi: {e}")
                    platform_results[platform] = 0

        # Kar analizi ve filtreleme
        profitable_products = []

        for product in all_products:
            analysis = self.analyze_profit(product, product.get('source', ''))
            product['profit_analysis'] = analysis

            if analysis.get('estimated_profit', 0) >= min_profit:
                if analysis.get('recommendation') in ['buy', 'watch']:
                    profitable_products.append(product)

        # Sonuclari kaydet
        output_file = OUTPUT_DIR / f"{search_id}.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump({
                "search_id": search_id,
                "query": query,
                "timestamp": datetime.now().isoformat(),
                "platform_results": platform_results,
                "total_products": len(all_products),
                "profitable_products": len(profitable_products),
                "products": profitable_products
            }, f, ensure_ascii=False, indent=2)

        # Karli urunleri URUN BULDUM grubuna gonder
        for product in profitable_products[:10]:
            self.send_product_found(product)

        # Ozet raporu gonder
        successful = [p for p, c in platform_results.items() if c > 0]
        failed = [p for p, c in platform_results.items() if c == 0]

        self.send_telegram(
            self.channels['scrape_command'],
            f"*ARAMA TAMAMLANDI*\n\n"
            f"ID: `{search_id}`\n"
            f"Toplam: {len(all_products)} urun\n"
            f"Karli: {len(profitable_products)} urun\n\n"
            f"*Basarili:* {len(successful)} platform\n"
            f"*Basarisiz:* {len(failed)} platform\n\n"
            f"_Karli urunler URUN BULDUM grubuna gonderildi._"
        )

        return profitable_products

    def send_product_found(self, product):
        """URUN BULDUM grubuna karli urun gonder"""
        analysis = product.get('profit_analysis', {})
        platform_info = self.platforms.get(product.get('source', ''), {})

        msg = f"""*KARLI URUN BULUNDU*

*Baslik:* {product.get('title', '')[:50]}...
*Fiyat:* {product.get('price', 0)} EUR
*Kaynak:* {platform_info.get('name', product.get('source', ''))}
*Ulke:* {self.country_languages.get(platform_info.get('country', 'de'), {}).get('name', '')}

*Tahmini Satis:* {analysis.get('estimated_sell_price', 0):.0f} EUR
*Tahmini Kar:* +{analysis.get('estimated_profit', 0):.0f} EUR ({analysis.get('profit_margin_percent', 0):.0f}%)
*Oneri:* {analysis.get('recommendation', '')}

*SEO Baslik:* {analysis.get('seo_title_de', '')[:50]}...

_{analysis.get('reason', '')}_
"""

        buttons = [
            [
                {"text": "TRANSFER ET", "callback_data": f"transfer:{product.get('url', '')[:60]}"},
                {"text": "ATLA", "callback_data": "skip"}
            ]
        ]

        self.send_telegram(self.channels['product_found'], msg, buttons)


def main():
    """Test"""
    scraper = MultiPlatformScraper()

    # Test arama
    results = scraper.search_all_platforms(
        "nike air max",
        platforms=['ebay_de', 'kleinanzeigen'],
        min_profit=5
    )

    print(f"\nToplam {len(results)} karli urun bulundu")

if __name__ == "__main__":
    main()
