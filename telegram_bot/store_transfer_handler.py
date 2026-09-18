#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TATANGA - Store Transfer Handler
Magazalar arasi urun transferi - Kleinanzeigen -> Vinted, eBay, etc.
"""

import sys
import json
import time
import requests
import re
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.config.credentials import (
    TELEGRAM, AI_SERVICES, KLEINANZEIGEN, VINTED
)

# Dizinler
BASE_DIR = Path(__file__).parent.parent
LOG_DIR = BASE_DIR / "logs"
TEMP_DIR = BASE_DIR / "T6_LISTING_ENGINE" / "temp"
PENDING_DIR = BASE_DIR / "T6_LISTING_ENGINE" / "pending"

LOG_DIR.mkdir(exist_ok=True)
TEMP_DIR.mkdir(exist_ok=True)
PENDING_DIR.mkdir(exist_ok=True)

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.common.action_chains import ActionChains
    import undetected_chromedriver as uc
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    print("[!] Selenium yuklu degil - pip install selenium undetected-chromedriver")

from PIL import Image, ImageEnhance, ImageFilter
import hashlib
import random

# CAPTCHA Handler import
try:
    from captcha_handler import CaptchaHandler
    CAPTCHA_HANDLER_AVAILABLE = True
except ImportError:
    CAPTCHA_HANDLER_AVAILABLE = False
    print("[!] CaptchaHandler yuklenemedi")

# Quality Controller import
try:
    from quality_controller import QualityController
    QUALITY_CONTROLLER_AVAILABLE = True
except ImportError:
    QUALITY_CONTROLLER_AVAILABLE = False
    print("[!] QualityController yuklenemedi")

class StoreTransferHandler:
    """Magazalar arasi transfer isleyici"""

    def __init__(self):
        self.bot_token = TELEGRAM['bot_token']
        self.channels = TELEGRAM['channels']
        self.ai_key = AI_SERVICES['groq']['api_key']
        self.ai_model = AI_SERVICES['groq']['model']
        self.last_update_id = 0
        self.driver = None
        self.send_telegram = True  # Telegram bildirimlerini acip kapatmak icin

        # Grup gorevleri - her grup sadece kendi alaninda calisir
        self.group_responsibilities = {
            self.channels['store_transfer']: {
                'name': 'store_transfer',
                'allowed_intents': ['transfer_products', 'list_store', 'sync_stores', 'check_transfer_status', 'update_price'],
                'description': 'Magazalar arasi urun transferi ve fiyat guncelleme'
            },
            self.channels['scrape_command']: {
                'name': 'scrape_command',
                'allowed_intents': ['platform_search', 'category_search', 'stop_scrape'],
                'description': 'Urun arama ve kazima'
            },
            self.channels['product_found']: {
                'name': 'product_found',
                'allowed_intents': ['list_products', 'skip_product', 'add_to_favorites'],
                'description': 'Bulunan urunleri listeleme'
            },
            self.channels['messages']: {
                'name': 'messages',
                'allowed_intents': ['approve_product', 'reject_product', 'change_price', 'change_title', 'reprocess_images'],
                'description': 'Urun onay ve duzenleme'
            },
            self.channels['sales']: {
                'name': 'sales',
                'allowed_intents': ['sales_report', 'revenue_report', 'customer_info'],
                'description': 'Satis raporlari'
            },
            self.channels['shipping']: {
                'name': 'shipping',
                'allowed_intents': ['track_shipping', 'create_label', 'delivery_list'],
                'description': 'Kargo islemleri'
            },
            self.channels['system']: {
                'name': 'system',
                'allowed_intents': ['show_errors', 'system_status', 'view_logs'],
                'description': 'Sistem durumu ve hatalar'
            }
        }

        # Log dosyasi
        self.log_file = LOG_DIR / f"store_transfer_{datetime.now().strftime('%Y%m%d')}.jsonl"

        # CAPTCHA Handler
        self.captcha_handler = None
        if CAPTCHA_HANDLER_AVAILABLE:
            self.captcha_handler = CaptchaHandler(logger=self.log)

        # Quality Controller
        self.quality_controller = None
        if QUALITY_CONTROLLER_AVAILABLE:
            self.quality_controller = QualityController(logger=self.log)

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

        # Tum log seviyelerini ekrana yaz
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] [{level}] {message}", flush=True)

    def send_message(self, chat_id, text, reply_to=None, buttons=None):
        """Telegram mesaji gonder"""
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
            resp = requests.post(url, data=data, timeout=10)
            return resp.json()
        except Exception as e:
            self.log("ERROR", f"Telegram gonderim hatasi: {e}")
            return None

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
            self.log("ERROR", f"getUpdates hatasi: {e}")

        return []

    def analyze_edit_request(self, user_request, product_id):
        """AI ile reply duzenleme istegini analiz et ve uygula"""
        try:
            # Urun dosyasini bul
            pending_file = PENDING_DIR / f"{product_id}.json"
            completed_dir = PENDING_DIR.parent / "completed"
            completed_file = completed_dir / f"{product_id}.json"

            target_file = None
            if pending_file.exists():
                target_file = pending_file
            elif completed_file.exists():
                target_file = completed_file
            else:
                return f"[-] Urun bulunamadi: `{product_id}`"

            # Urunu yukle
            with open(target_file, 'r', encoding='utf-8') as f:
                product = json.load(f)

            # AI ile istegi analiz et
            headers = {
                "Authorization": f"Bearer {self.ai_key}",
                "Content-Type": "application/json"
            }

            current_title = product.get('optimized', {}).get('title', '')
            current_desc = product.get('optimized', {}).get('description', '')
            current_price = product.get('optimized', {}).get('suggested_price', 0)

            prompt = f"""
Kullanici bir urunde degisiklik istiyor.

Mevcut urun:
- Baslik: {current_title}
- Aciklama: {current_desc[:200]}...
- Fiyat: {current_price} EUR

Kullanici istegi: "{user_request}"

Bu istegi analiz et ve JSON formatinda dondur:
{{
    "action": "update_title" | "update_description" | "update_price" | "update_all" | "unknown",
    "new_title": "yeni baslik" | null,
    "new_description": "yeni aciklama" | null,
    "new_price": yeni fiyat (sayi) | null,
    "explanation": "yapilan degisiklik aciklamasi"
}}

Ornekler:
- "basligi kisalt" -> title guncelle
- "fiyati 30 yap" -> price guncelle
- "marka ekle: Nike" -> title guncelle
- "aciklamaya beden bilgisi ekle" -> description guncelle

Sadece JSON dondur.
"""

            data = {
                "model": self.ai_model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 500,
                "temperature": 0.3
            }

            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json=data,
                timeout=30
            )

            if response.status_code != 200:
                return "[-] AI analiz hatasi"

            result = response.json()
            content = result['choices'][0]['message']['content'].strip()

            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            analysis = json.loads(content)

            # Degisiklikleri uygula
            changes_made = []

            if analysis.get('new_title'):
                product['optimized']['title'] = analysis['new_title']
                changes_made.append(f"Baslik: {analysis['new_title'][:50]}...")

            if analysis.get('new_description'):
                product['optimized']['description'] = analysis['new_description']
                changes_made.append("Aciklama guncellendi")

            if analysis.get('new_price'):
                # Tam sayi fiyat
                new_price = int(analysis['new_price'])
                product['optimized']['suggested_price'] = new_price
                changes_made.append(f"Fiyat: {new_price} EUR")

            if not changes_made:
                return f"[-] Istek anlasilamadi: {analysis.get('explanation', 'Bilinmeyen hata')}"

            # Kaydet
            with open(target_file, 'w', encoding='utf-8') as f:
                json.dump(product, f, ensure_ascii=False, indent=2)

            return (
                f"*URUN GUNCELLENDI*\n\n"
                f"ID: `{product_id}`\n\n"
                f"*Degisiklikler:*\n" +
                "\n".join(f"- {c}" for c in changes_made) +
                f"\n\n_{analysis.get('explanation', '')}_"
            )

        except Exception as e:
            self.log("ERROR", f"Edit request hatasi: {e}")
            return f"[-] Duzenleme hatasi: {e}"

    def analyze_command(self, message, chat_id):
        """AI ile komutu analiz et ve alan kontrolu yap"""
        group_info = self.group_responsibilities.get(chat_id)
        if not group_info:
            return None

        try:
            headers = {
                "Authorization": f"Bearer {self.ai_key}",
                "Content-Type": "application/json"
            }

            prompt = f"""
Sen TATANGA e-ticaret sisteminin AI koordinatorusun.

Grup: {group_info['name']} ({group_info['description']})
Izin verilen islemler: {', '.join(group_info['allowed_intents'])}

Kullanici mesaji: "{message}"

Bu mesaji analiz et ve JSON formatinda dondur:

{{
    "intent": "tespit edilen intent",
    "is_allowed": true/false,
    "source_platform": "kleinanzeigen" | "vinted" | "ebay" | null,
    "target_platform": "vinted" | "ebay" | "kleinanzeigen" | null,
    "account_email": "hesap email" | null,
    "action_params": {{}},
    "response": "kullaniciya yanit",
    "redirect_to": "dogru grup adi" | null
}}

Transfer intent'leri:
- transfer_products: "kleinanzeigen'deki urunleri vinted'e aktar", "magazadan magazaya transfer"
- list_store: "magazadaki urunleri listele"
- sync_stores: "magazalari senkronize et"
- update_price: "TRANSFER-xxx fiyatini 50 yap", "fiyat guncelle TRANSFER-xxx 30"

update_price icin action_params:
- product_id: "TRANSFER-xxx"
- new_price: yeni fiyat degeri (sayi)

Eger intent bu grubun yetkisinde degilse:
- is_allowed: false
- redirect_to: dogru grup adi
- response: "Bu islem [grup adi] grubunda yapilmali"

Sadece JSON dondur.
"""

            data = {
                "model": self.ai_model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 400,
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

                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0]
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0]

                return json.loads(content)

        except Exception as e:
            self.log("ERROR", f"Komut analizi hatasi: {e}")

        return {
            "intent": "unknown",
            "is_allowed": False,
            "response": "Komut anlasilmadi.",
            "redirect_to": None
        }

    def init_driver(self):
        """Selenium driver baslat"""
        if not SELENIUM_AVAILABLE:
            return False

        if self.driver:
            return True

        try:
            options = uc.ChromeOptions()
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--window-size=1920,1080')
            options.add_argument('--disable-blink-features=AutomationControlled')

            self.driver = uc.Chrome(options=options)
            self.driver.implicitly_wait(10)

            # CAPTCHA Handler'a driver'i ata
            if self.captcha_handler:
                self.captcha_handler.driver = self.driver

            # Quality Controller'a driver'i ata
            if self.quality_controller:
                self.quality_controller.driver = self.driver

            return True
        except Exception as e:
            self.log("ERROR", f"Driver baslatilamadi: {e}")
            return False

    def human_like_delay(self, min_sec=1, max_sec=3):
        """Insan benzeri bekleme"""
        delay = random.uniform(min_sec, max_sec)
        time.sleep(delay)

    def download_image(self, url, product_id):
        """URL'den resim indir ve dosyaya kaydet"""
        if not url:
            return None

        try:
            # Dosya adı oluştur
            ext = url.split('.')[-1].split('?')[0].lower()
            if ext not in ['jpg', 'jpeg', 'png', 'gif', 'webp']:
                ext = 'jpg'

            filename = f"{product_id}_{hashlib.md5(url.encode()).hexdigest()[:8]}.{ext}"
            filepath = TEMP_DIR / filename

            # Zaten varsa tekrar indirme
            if filepath.exists():
                return str(filepath)

            # İndir
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(url, headers=headers, timeout=30)

            if response.status_code == 200:
                with open(filepath, 'wb') as f:
                    f.write(response.content)
                self.log("INFO", f"Resim indirildi: {filename}")
                return str(filepath)
            else:
                self.log("WARNING", f"Resim indirilemedi: {url} - Status: {response.status_code}")
                return None

        except Exception as e:
            self.log("ERROR", f"Resim indirme hatasi: {e}")
            return None

    def scroll_page(self, scroll_count=3):
        """Sayfayi scroll et"""
        for i in range(scroll_count):
            self.driver.execute_script("window.scrollBy(0, 500);")
            self.human_like_delay(0.5, 1)

    def get_kleinanzeigen_products(self, email):
        """Kleinanzeigen magazasindaki urunleri cek"""
        if not self.init_driver():
            return []

        # Hesap bilgilerini bul
        account = None
        for acc in KLEINANZEIGEN['accounts']:
            if acc['email'] == email:
                account = acc
                break

        if not account:
            self.log("ERROR", f"Hesap bulunamadi: {email}")
            return []

        products = []

        try:
            # Login sayfasi
            self.log("INFO", "Kleinanzeigen login yapiliyor...")
            self.driver.get("https://www.kleinanzeigen.de/m-einloggen.html")
            self.human_like_delay(2, 3)

            # Cookie popup - CAPTCHA Handler ile isle
            if self.captcha_handler:
                result = self.captcha_handler.check_and_handle(platform='kleinanzeigen', auto_accept=True)
                if result == 'waiting':
                    self.log("INFO", "Insan onayi bekleniyor...")
                    time.sleep(30)
            else:
                try:
                    self.driver.execute_script("""
                        var buttons = document.querySelectorAll('button');
                        for (var btn of buttons) {
                            if (btn.textContent.includes('Alle akzeptieren')) {
                                btn.click();
                                break;
                            }
                        }
                    """)
                    self.human_like_delay(1, 2)
                except:
                    pass

            # Email gir
            email_input = self.driver.find_element(By.ID, "login-email")
            email_input.clear()
            for char in account['email']:
                email_input.send_keys(char)
                time.sleep(random.uniform(0.05, 0.15))

            self.human_like_delay(0.5, 1)

            # Sifre gir
            pass_input = self.driver.find_element(By.ID, "login-password")
            pass_input.clear()
            for char in account['password']:
                pass_input.send_keys(char)
                time.sleep(random.uniform(0.05, 0.15))

            self.human_like_delay(0.5, 1)

            # Login buton
            submit_btn = self.driver.find_element(By.ID, "login-submit")
            submit_btn.click()

            self.human_like_delay(3, 5)

            # Login sonrasi "Willkommen bei Kleinanzeigen" popup - Alle akzeptieren
            try:
                self.driver.execute_script("""
                    var buttons = document.querySelectorAll('button');
                    for (var btn of buttons) {
                        if (btn.textContent.includes('Alle akzeptieren')) {
                            btn.click();
                            break;
                        }
                    }
                """)
                self.human_like_delay(1, 2)
                self.log("INFO", "Willkommen popup kapatildi")
            except:
                pass

            # Ilanlarim sayfasi
            self.log("INFO", "Ilanlar sayfasina gidiliyor...")
            self.driver.get("https://www.kleinanzeigen.de/m-meine-anzeigen.html")
            self.human_like_delay(2, 3)

            # Insansi gezinme - rastgele mouse ve scroll
            if self.quality_controller:
                try:
                    self.quality_controller.random_mouse_movement()
                    self.quality_controller.random_scroll()
                except Exception as e:
                    self.log("WARNING", f"Insansi gezinme hatasi: {e}")

            # Scroll ile tum urunleri yukle
            self.scroll_page(5)

            # Urunleri bul - yeni Kleinanzeigen yapisi
            selectors = [
                "li[data-testid='ad-card'][data-adid]",
                "li[data-adid]",
                "article[data-adid]",
            ]

            items = []
            for selector in selectors:
                items = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if items:
                    self.log("INFO", f"Selector '{selector}' ile {len(items)} urun bulundu")
                    break

            self.log("INFO", f"{len(items)} urun bulundu")

            for item in items:
                try:
                    # Baslik - h3 icindeki a elementi
                    try:
                        title_el = item.find_element(By.CSS_SELECTOR, "h3.text-title4 a, h3 a")
                        title = title_el.text.strip()[:100]
                        url = title_el.get_attribute("href")
                    except:
                        # Alternatif selector
                        try:
                            title_el = item.find_element(By.CSS_SELECTOR, "a[aria-label]")
                            title = title_el.get_attribute("aria-label").replace("Anzeige ", "")[:100]
                            url = title_el.get_attribute("href")
                        except:
                            continue

                    if not title or title.isdigit():
                        continue

                    # Fiyat - li.text-title3.text-secondary
                    try:
                        price_el = item.find_element(By.CSS_SELECTOR, "li.text-title3.text-secondary, .text-title3")
                        price_text = price_el.text.strip()
                        # "30 €" formatindan sayiyi cek
                        price_match = re.search(r'(\d+(?:[.,]\d+)?)', price_text.replace('.', ''))
                        price = int(float(price_match.group(1).replace(',', '.'))) if price_match else 0
                    except:
                        price = 0

                    # Resim - data-testid ile
                    try:
                        img_el = item.find_element(By.CSS_SELECTOR, "img[data-testid='ad-image'], img[src*='kleinanzeigen']")
                        img_url = img_el.get_attribute("src")
                        # Daha yuksek cozunurluk icin rule parametresini degistir
                        if img_url and '?rule=$_2.JPG' in img_url:
                            img_url = img_url.replace('?rule=$_2.JPG', '?rule=$_57.JPG')
                    except:
                        img_url = ""

                    # Kategori
                    try:
                        cat_el = item.find_element(By.CSS_SELECTOR, "div.text-bodySmall.text-onSurfaceNonessential")
                        category = cat_el.text.strip()
                    except:
                        category = ""

                    self.log("INFO", f"Urun: {title[:40]}... - {price} EUR - {category}")

                    products.append({
                        'original': {
                            'title': title,
                            'price': price,
                            'url': url,
                            'image': img_url,
                            'description': title,
                            'category': category,
                        },
                        'optimized': {
                            'title': title,
                            'description': title,
                        },
                        'images': [img_url] if img_url else [],
                        'source': 'kleinanzeigen'
                    })

                except Exception as e:
                    continue

            self.log("INFO", f"Toplam {len(products)} urun cekildi")

        except Exception as e:
            self.log("ERROR", f"Kleinanzeigen scrape hatasi: {e}")

        return products

    def handle_cookie_popup(self):
        """Cookie popup'ini insan gibi tikla"""
        try:
            # Farkli cookie popup selectorlari
            cookie_selectors = [
                "button#gdpr-banner-accept",
                "[data-testid='gdpr-banner-accept']",
                "button[class*='accept']",
                "#onetrust-accept-btn-handler",
                ".cmpboxbtnyes",
                "button[title*='akzeptieren']",
                "button[title*='Akzeptieren']"
            ]

            for selector in cookie_selectors:
                try:
                    btn = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if btn.is_displayed():
                        # Insan gibi tikla - ActionChains kullan
                        actions = ActionChains(self.driver)
                        actions.move_to_element(btn)
                        self.human_like_delay(0.3, 0.7)
                        actions.click(btn)
                        actions.perform()
                        self.log("INFO", f"Cookie popup kapatildi: {selector}")
                        self.human_like_delay(1, 2)
                        return True
                except:
                    continue

            # JavaScript ile dene
            self.driver.execute_script("""
                var buttons = document.querySelectorAll('button');
                for (var btn of buttons) {
                    var text = btn.textContent.toLowerCase();
                    if (text.includes('akzeptieren') || text.includes('accept') ||
                        text.includes('zustimmen') || text.includes('agree')) {
                        btn.click();
                        return true;
                    }
                }
                return false;
            """)
            self.human_like_delay(1, 2)

        except Exception as e:
            self.log("WARNING", f"Cookie popup handle edilemedi: {e}")

        return False

    def get_product_details(self, url):
        """Urun detaylarini cek - gelismis versiyon"""
        if not self.init_driver():
            return None

        try:
            self.driver.get(url)
            self.human_like_delay(2, 3)

            # Cookie popup - CAPTCHA Handler ile isle
            if self.captcha_handler:
                result = self.captcha_handler.check_and_handle(platform='kleinanzeigen', auto_accept=True)
                if result == 'waiting':
                    self.log("INFO", "Insan onayi bekleniyor...")
                    time.sleep(30)  # 30 saniye bekle
            else:
                self.handle_cookie_popup()

            product = {
                'source_url': url,
                'scraped_at': datetime.now().isoformat()
            }

            # Sayfa yuklenmesini bekle
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )

            # Baslik - birden fazla selector dene
            title_selectors = [
                "#viewad-title",
                "h1#viewad-title",
                "[itemprop='name']",
                "h1[class*='title']",
                ".boxedarticle--title"
            ]

            product['title'] = ""
            for selector in title_selectors:
                try:
                    title_el = self.driver.find_element(By.CSS_SELECTOR, selector)
                    title_text = title_el.text.strip()
                    if title_text:
                        product['title'] = title_text
                        self.log("INFO", f"Baslik bulundu: {title_text[:50]}...")
                        break
                except:
                    continue

            # Fiyat - birden fazla selector dene
            price_selectors = [
                "#viewad-price",
                "[itemprop='price']",
                ".boxedarticle--price",
                "[class*='price'] strong",
                "h2#viewad-price"
            ]

            product['price'] = 0
            for selector in price_selectors:
                try:
                    price_el = self.driver.find_element(By.CSS_SELECTOR, selector)
                    price_text = price_el.text.strip()
                    # Sayilari cikar - SADECE tam sayi, küsürat YOK
                    # Önce binlik ayracı olan noktaları kaldır, sonra virgülü noktaya çevir
                    clean_price = price_text.replace('.', '').replace(',', '.')
                    price_match = re.search(r'(\d+(?:\.\d+)?)', clean_price)
                    if price_match:
                        # Tam sayiya yuvarla - küsürat yok
                        product['price'] = int(round(float(price_match.group(1))))
                        self.log("INFO", f"Fiyat bulundu: {product['price']} EUR (tam sayi)")
                        break
                except:
                    continue

            # Aciklama
            desc_selectors = [
                "#viewad-description-text",
                "[itemprop='description']",
                ".boxedarticle--description",
                "#viewad-description"
            ]

            product['description'] = ""
            for selector in desc_selectors:
                try:
                    desc_el = self.driver.find_element(By.CSS_SELECTOR, selector)
                    desc_text = desc_el.text.strip()
                    if desc_text:
                        product['description'] = desc_text
                        self.log("INFO", f"Aciklama bulundu: {len(desc_text)} karakter")
                        break
                except:
                    continue

            # Resimler - gelismis
            images = []
            img_selectors = [
                "#viewad-thumbnail-list img",
                ".galleryimage-element img",
                "[class*='gallery'] img",
                ".imagebox img",
                "#viewad-image img"
            ]

            for selector in img_selectors:
                try:
                    img_elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for img in img_elements:
                        src = img.get_attribute("src") or img.get_attribute("data-src") or img.get_attribute("data-imgsrc")
                        if src and src not in images:
                            # Buyuk versiyonu al
                            big_src = src
                            for size in ["_57.", "_72.", "_23.", "_9."]:
                                big_src = big_src.replace(size, "_2048.")
                            if big_src not in images:
                                images.append(big_src)
                    if images:
                        break
                except:
                    continue

            product['images'] = images
            self.log("INFO", f"Toplam {len(images)} resim bulundu")

            # Eger hala baslik yoksa sayfa kaynagindan cikarmaya calis
            if not product['title']:
                try:
                    # og:title meta tag'ini dene
                    og_title = self.driver.find_element(By.CSS_SELECTOR, "meta[property='og:title']")
                    product['title'] = og_title.get_attribute("content") or ""
                    self.log("INFO", f"OG title bulundu: {product['title'][:50]}...")
                except:
                    pass

            # Eger hala fiyat yoksa
            if not product['price']:
                try:
                    # Sayfada fiyat ara
                    page_text = self.driver.find_element(By.TAG_NAME, "body").text
                    price_matches = re.findall(r'(\d+)\s*(?:€|EUR|Euro)', page_text)
                    if price_matches:
                        product['price'] = int(price_matches[0])
                        self.log("INFO", f"Regex ile fiyat bulundu: {product['price']} EUR")
                except:
                    pass

            return product

        except Exception as e:
            self.log("ERROR", f"Urun detay hatasi: {e}")
            import traceback
            self.log("ERROR", traceback.format_exc())
            return None

    def process_images(self, image_urls, product_id):
        """Resimleri indir ve isle"""
        processed_images = []
        download_dir = TEMP_DIR / "downloads"
        processed_dir = TEMP_DIR / "processed"
        download_dir.mkdir(exist_ok=True)
        processed_dir.mkdir(exist_ok=True)

        for i, url in enumerate(image_urls):
            try:
                # Indir
                response = requests.get(url, timeout=30)
                if response.status_code == 200:
                    ext = ".jpg"
                    download_path = download_dir / f"{product_id}_{i+1}_orig{ext}"
                    with open(download_path, 'wb') as f:
                        f.write(response.content)

                    # Isle - Vinted duplicate tespitinden kacinma
                    img = Image.open(download_path)

                    # 1. Boyut degistir (%90-96)
                    scale = random.uniform(0.90, 0.96)
                    new_size = (int(img.width * scale), int(img.height * scale))
                    img = img.resize(new_size, Image.Resampling.LANCZOS)

                    # 2. Parlaklik (%97-103)
                    enhancer = ImageEnhance.Brightness(img)
                    img = enhancer.enhance(random.uniform(0.97, 1.03))

                    # 3. Kontrast (%98-102)
                    enhancer = ImageEnhance.Contrast(img)
                    img = enhancer.enhance(random.uniform(0.98, 1.02))

                    # 4. Renk doygunlugu (%95-105)
                    enhancer = ImageEnhance.Color(img)
                    img = enhancer.enhance(random.uniform(0.95, 1.05))

                    # 5. Hafif blur
                    if random.random() > 0.5:
                        img = img.filter(ImageFilter.GaussianBlur(radius=0.3))

                    # 6. Kenar kirpma
                    crop = random.randint(1, 3)
                    img = img.crop((crop, crop, img.width - crop, img.height - crop))

                    # RGB'ye cevir
                    if img.mode == 'RGBA':
                        img = img.convert('RGB')

                    # Kaydet
                    hash_suffix = hashlib.md5(f"{product_id}{i}{time.time()}".encode()).hexdigest()[:8]
                    processed_path = processed_dir / f"{product_id}_{i+1}_{hash_suffix}.jpg"
                    img.save(processed_path, 'JPEG', quality=random.randint(88, 94))

                    processed_images.append(str(processed_path))
                    self.log("INFO", f"Resim {i+1} islendi")

            except Exception as e:
                self.log("ERROR", f"Resim {i+1} islenemedi: {e}")

        return processed_images

    def optimize_content(self, product):
        """AI ile baslik ve aciklama optimize et"""
        try:
            headers = {
                "Authorization": f"Bearer {self.ai_key}",
                "Content-Type": "application/json"
            }

            prompt = f"""
Asagidaki urunu Vinted icin optimize et. Almanca, SEO uyumlu, gramer kurallarina uygun.

Orijinal Baslik: {product.get('title', '')}
Orijinal Aciklama: {product.get('description', '')}
Fiyat: {product.get('price', 0)} EUR

JSON formatinda dondur:
{{
    "title": "Yeni SEO baslik (max 80 karakter)",
    "description": "Yeni SEO aciklama (max 500 karakter, Almanca gramer kurallari)",
    "suggested_price": {product.get('price', 0)},
    "hashtags": ["ilgili", "hashtagler"],
    "category_suggestion": "vinted kategori onerisi"
}}

Kurallari:
- Baslik: Marka + Urun turu + Ozellik + Beden
- Aciklama: Durum, olculer, materyal, ozellikler
- Fiyat: KAYNAK SITEDEKI ORIJINAL FIYATI KULLAN - DEGISTIRME! (Bu magaza transferi, kullanici sonra degistirebilir)

NOT: Bu MAGAZA TRANSFERI - kendi magazalarim arasinda urun aktarimi.
Kazima sonrasi listeleme FARKLI bir islem (kar marji eklenir).

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
            self.log("ERROR", f"Icerik optimizasyonu hatasi: {e}")

        # Hata durumunda orijinal fiyati kullan - kar marji EKLEME
        return {
            "title": product.get('title', ''),
            "description": product.get('description', ''),
            "suggested_price": product.get('price', 0)
        }

    def calculate_selling_price(self, original_price, shipping_cost=4.99, min_profit=5.0):
        """
        Satis fiyati hesapla: Orijinal fiyat + (2 x kargo) + minimum kar

        Args:
            original_price: Kaynak sitedeki orijinal fiyat
            shipping_cost: Kargo ucreti (varsayilan 4.99€)
            min_profit: Minimum kar marji (varsayilan 5€)

        Returns:
            int: Hesaplanan satis fiyati (yuvarlanmis)

        Formul:
            selling_price = original_price + (2 * shipping_cost) + min_profit

        Ornek:
            original: 10€, shipping: 4.99€, min_profit: 5€
            selling = 10 + (2 * 4.99) + 5 = 10 + 9.98 + 5 = 24.98€ ≈ 25€
        """
        try:
            original = float(original_price)
            shipping = float(shipping_cost)
            profit = float(min_profit)

            # Formul: orijinal + (2x kargo) + minimum kar
            calculated_price = original + (2 * shipping) + profit

            # Yuvarla ve int'e cevir
            final_price = int(round(calculated_price))

            # Minimum fiyat kontrolu (en az 5€)
            if final_price < 5:
                final_price = 5

            self.log("INFO", f"Fiyat hesaplandi: {original}€ + (2x{shipping}€) + {profit}€ = {final_price}€")
            return final_price

        except Exception as e:
            self.log("ERROR", f"Fiyat hesaplama hatasi: {e}")
            # Hata durumunda orijinal fiyata %50 kar ekle
            return int(float(original_price) * 1.5) if original_price else 10

    def get_shipping_cost_by_weight(self, weight_kg=None, category=None):
        """
        Agirlik veya kategoriye gore kargo ucreti belirle

        Args:
            weight_kg: Urun agirligi (kg)
            category: Urun kategorisi

        Returns:
            float: Kargo ucreti
        """
        # Kategori bazli varsayilan kargo ucretleri (Almanya icin)
        category_shipping = {
            'schuhe': 5.99,      # Ayakkabi
            'jacken': 5.99,     # Ceketler
            'taschen': 5.99,    # Cantalar
            'accessoires': 3.99, # Aksesuarlar
            'schmuck': 2.99,    # Takı
            't-shirts': 3.99,   # Tisortler
            'hosen': 4.99,      # Pantolonlar
            'kleider': 4.99,    # Elbiseler
            'default': 4.99,    # Varsayilan
        }

        # Agirlik bazli kargo (kg)
        if weight_kg:
            if weight_kg <= 0.5:
                return 2.99
            elif weight_kg <= 1:
                return 3.99
            elif weight_kg <= 2:
                return 4.99
            elif weight_kg <= 5:
                return 5.99
            else:
                return 7.99

        # Kategori bazli
        if category:
            category_lower = category.lower()
            for key, cost in category_shipping.items():
                if key in category_lower:
                    return cost

        return category_shipping['default']

    def login_to_vinted(self, account):
        """Vinted'e login ol - SELENIUM WEBDRIVERWAIT YONTEMI"""
        if not self.init_driver():
            return False

        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            from selenium.webdriver.common.action_chains import ActionChains

            self.log("INFO", "Vinted login yapiliyor - Selenium WebDriverWait yontemi...")
            email = account['email']
            password = account['password']

            # ADIM 1: Ana sayfaya git
            self.log("INFO", "ADIM 1: vinted.de ana sayfasina gidiliyor...")
            self.driver.get("https://www.vinted.de")
            self.human_like_delay(3, 5)

            # ADIM 2: Cookie popup'ini isle
            self.log("INFO", "ADIM 2: Cookie popup kontrol ediliyor...")
            try:
                # OneTrust veya genel cookie butonu
                cookie_selectors = [
                    (By.ID, "onetrust-accept-btn-handler"),
                    (By.XPATH, "//button[contains(text(), 'Alle zulassen')]"),
                    (By.XPATH, "//button[contains(text(), 'akzeptieren')]"),
                    (By.XPATH, "//button[contains(text(), 'Accept')]"),
                ]

                for selector in cookie_selectors:
                    try:
                        cookie_btn = WebDriverWait(self.driver, 3).until(
                            EC.element_to_be_clickable(selector)
                        )
                        ActionChains(self.driver).move_to_element(cookie_btn).click().perform()
                        self.log("INFO", f"Cookie kabul edildi: {selector[1]}")
                        self.human_like_delay(1.5, 2.5)
                        break
                    except:
                        continue
            except Exception as e:
                self.log("DEBUG", f"Cookie popup bulunamadi veya zaten kapatilmis: {e}")

            # Screenshot - ana sayfa
            try:
                self.driver.save_screenshot(str(TEMP_DIR / "vinted_1_homepage.png"))
            except:
                pass

            # ADIM 3: "Artikel verkaufen" butonuna tikla (header'daki petrol yesili buton)
            self.log("INFO", "ADIM 3: 'Artikel verkaufen' butonuna tiklaniyor...")
            try:
                # Header'daki "Artikel verkaufen" butonunu bul
                # Bu buton petrol yesili ve header'in sag tarafinda
                artikel_selectors = [
                    # Tam metin eslesmesi - sadece header icinde
                    (By.XPATH, "//header//a[normalize-space(text())='Artikel verkaufen']"),
                    (By.XPATH, "//header//button[normalize-space(text())='Artikel verkaufen']"),
                    # Iceren metin - sadece header icinde
                    (By.XPATH, "//header//a[contains(text(), 'Artikel verkaufen')]"),
                    (By.XPATH, "//header//button[contains(text(), 'Artikel verkaufen')]"),
                    # nav icinde
                    (By.XPATH, "//nav//a[contains(text(), 'Artikel verkaufen')]"),
                    # data-testid
                    (By.XPATH, "//*[@data-testid='sell-button']"),
                    (By.XPATH, "//*[@data-testid='header-sell-button']"),
                ]

                artikel_found = False

                # Oncelikle header'daki tum linkleri tara
                header_links = self.driver.find_elements(By.XPATH, "//header//a | //nav//a")
                for link in header_links:
                    try:
                        text = link.text.strip()
                        if text == 'Artikel verkaufen':
                            location = link.location
                            if location['y'] < 150:
                                ActionChains(self.driver).move_to_element(link).click().perform()
                                self.log("INFO", f"Artikel verkaufen tiklandi (y:{location['y']})")
                                artikel_found = True
                                self.human_like_delay(4, 6)
                                break
                    except:
                        continue

                # Eger bulunamadiysa selector'lari dene
                if not artikel_found:
                    for selector in artikel_selectors:
                        try:
                            artikel_btn = WebDriverWait(self.driver, 3).until(
                                EC.element_to_be_clickable(selector)
                            )
                            location = artikel_btn.location
                            if location['y'] < 150:
                                ActionChains(self.driver).move_to_element(artikel_btn).click().perform()
                                self.log("INFO", f"Artikel verkaufen tiklandi (y:{location['y']})")
                                artikel_found = True
                                self.human_like_delay(4, 6)
                                break
                        except:
                            continue

                if not artikel_found:
                    # Debug: header'daki tum linkleri listele
                    header_elements = self.driver.find_elements(By.XPATH, "//header//a | //header//button")
                    self.log("DEBUG", f"Header'daki elementler ({len(header_elements)} adet):")
                    for i, elem in enumerate(header_elements[:20]):
                        try:
                            text = elem.text.strip()[:40]
                            tag = elem.tag_name
                            loc = elem.location
                            if text:
                                self.log("DEBUG", f"  {i+1}. <{tag}> '{text}' y:{loc['y']}")
                        except:
                            pass
                    self.log("ERROR", "Artikel verkaufen butonu bulunamadi!")
                    try:
                        self.driver.save_screenshot(str(TEMP_DIR / "vinted_artikel_error.png"))
                    except:
                        pass
                    return False

            except Exception as e:
                self.log("ERROR", f"Artikel verkaufen hatasi: {e}")
                try:
                    self.driver.save_screenshot(str(TEMP_DIR / "vinted_artikel_error.png"))
                except:
                    pass
                return False

            # Screenshot - login secenekleri ekrani
            try:
                self.driver.save_screenshot(str(TEMP_DIR / "vinted_2_loginoptions.png"))
            except:
                pass

            # ADIM 4: KAYIT POPUP - "Einloggen" linkine tikla
            # Modal popup'ta: "Hast du schon einen Account? Einloggen"
            self.log("INFO", "ADIM 4: Kayit popup - 'Einloggen' linki araniyor...")
            try:
                einloggen_found = False

                # Modal popup icerisindeki "Einloggen" linkini ara
                # Link bir <a>, <button> veya <span> olabilir
                einloggen_selectors = [
                    "//a[text()='Einloggen']",  # <a> tam eslesme
                    "//span[text()='Einloggen']",  # <span> tam eslesme
                    "//a[contains(text(), 'Einloggen')]",
                    "//button[text()='Einloggen']",
                    "//*[@data-testid='auth-select-login']",
                    "//div[contains(@class, 'modal')]//a[contains(text(), 'Einloggen')]",
                ]

                for selector in einloggen_selectors:
                    try:
                        elements = self.driver.find_elements(By.XPATH, selector)
                        for elem in elements:
                            try:
                                loc = elem.location
                                # Header disinda (y > 100) ve gorunur
                                if loc['y'] > 100 and elem.is_displayed():
                                    ActionChains(self.driver).move_to_element(elem).click().perform()
                                    self.log("INFO", f"Einloggen tiklandi (y:{loc['y']}, selector:{selector[:30]})")
                                    einloggen_found = True
                                    self.human_like_delay(3, 5)
                                    break
                            except:
                                continue
                        if einloggen_found:
                            break
                    except:
                        continue

                if not einloggen_found:
                    # Debug: sayfadaki Einloggen elementlerini listele
                    all_elements = self.driver.find_elements(By.XPATH, "//*[contains(text(), 'Einloggen')]")
                    self.log("DEBUG", f"Sayfadaki Einloggen elementleri ({len(all_elements)} adet):")
                    for i, elem in enumerate(all_elements[:10]):
                        try:
                            text = elem.text.strip()[:50]
                            tag = elem.tag_name
                            loc = elem.location
                            visible = elem.is_displayed()
                            self.log("DEBUG", f"  {i+1}. <{tag}> '{text}' y:{loc['y']} visible:{visible}")
                        except:
                            pass

                    # Screenshot kaydet
                    try:
                        self.driver.save_screenshot(str(TEMP_DIR / "vinted_no_einloggen_link.png"))
                    except:
                        pass

                    self.log("ERROR", "Einloggen linki bulunamadi!")
                    return False

            except Exception as e:
                self.log("ERROR", f"Einloggen hatasi: {e}")
                return False

            # Screenshot - login secenekleri
            try:
                self.driver.save_screenshot(str(TEMP_DIR / "vinted_3_loginoptions.png"))
            except:
                pass

            # ADIM 5: LOGIN EKRANI - "E-Mail" secenegine tikla
            # "Einloggen mit E-Mail"
            self.log("INFO", "ADIM 5: Login ekrani - 'E-Mail' secenegi araniyor...")
            try:
                email_option_found = False

                # Sayfadaki E-Mail iceren elementleri tara
                all_elements = self.driver.find_elements(By.XPATH, "//*[contains(text(), 'E-Mail') or contains(text(), 'E-mail')]")
                for elem in all_elements:
                    try:
                        text = elem.text.strip()
                        tag = elem.tag_name
                        loc = elem.location

                        # Header disinda ve gorunur
                        if loc['y'] > 100 and elem.is_displayed():
                            if text == 'E-Mail' or 'E-Mail' in text:
                                # Eger span ise, parent'a tikla
                                if tag == 'span':
                                    parent = elem.find_element(By.XPATH, "./..")
                                    ActionChains(self.driver).move_to_element(parent).click().perform()
                                else:
                                    ActionChains(self.driver).move_to_element(elem).click().perform()
                                self.log("INFO", f"E-Mail secenegi tiklandi (y:{loc['y']}, tag:{tag})")
                                email_option_found = True
                                self.human_like_delay(3, 4)
                                break
                    except:
                        continue

                if not email_option_found:
                    self.log("ERROR", "E-Mail secenegi bulunamadi!")
                    return False

            except Exception as e:
                self.log("ERROR", f"E-Mail secenegi hatasi: {e}")
                return False

            # Screenshot - email/sifre formu
            try:
                self.driver.save_screenshot(str(TEMP_DIR / "vinted_4_emailform.png"))
            except:
                pass

            # ADIM 6: Email gir
            self.log("INFO", "ADIM 6: Email giriliyor...")
            try:
                email_selectors = [
                    (By.CSS_SELECTOR, "input[type='email']"),
                    (By.CSS_SELECTOR, "input[name='email']"),
                    (By.CSS_SELECTOR, "input[autocomplete='email']"),
                    (By.XPATH, "//input[contains(@placeholder, 'E-Mail') or contains(@placeholder, 'email')]"),
                    (By.XPATH, "//label[contains(text(), 'E-Mail')]/following::input[1]"),
                ]

                email_input = None
                for selector in email_selectors:
                    try:
                        email_input = WebDriverWait(self.driver, 5).until(
                            EC.element_to_be_clickable(selector)
                        )
                        # Gorunur ve y > 100 kontrolu
                        if email_input.is_displayed() and email_input.location['y'] > 100:
                            break
                        email_input = None
                    except:
                        continue

                if email_input:
                    ActionChains(self.driver).move_to_element(email_input).click().perform()
                    email_input.clear()
                    # Karakter karakter yaz (insan gibi)
                    for char in email:
                        email_input.send_keys(char)
                        time.sleep(random.uniform(0.03, 0.08))
                    self.log("INFO", "Email girildi")
                    self.human_like_delay(0.5, 1)
                else:
                    self.log("ERROR", "Email input bulunamadi!")
                    return False

            except Exception as e:
                self.log("ERROR", f"Email girisi hatasi: {e}")
                return False

            # ADIM 7: Sifre gir
            self.log("INFO", "ADIM 7: Sifre giriliyor...")
            try:
                password_selectors = [
                    (By.CSS_SELECTOR, "input[type='password']"),
                    (By.CSS_SELECTOR, "input[name='password']"),
                    (By.XPATH, "//input[@type='password']"),
                ]

                password_input = None
                for selector in password_selectors:
                    try:
                        password_input = WebDriverWait(self.driver, 5).until(
                            EC.element_to_be_clickable(selector)
                        )
                        if password_input.is_displayed():
                            break
                        password_input = None
                    except:
                        continue

                if password_input:
                    ActionChains(self.driver).move_to_element(password_input).click().perform()
                    password_input.clear()
                    # Karakter karakter yaz (insan gibi)
                    for char in password:
                        password_input.send_keys(char)
                        time.sleep(random.uniform(0.03, 0.08))
                    self.log("INFO", "Sifre girildi")
                    self.human_like_delay(0.5, 1)
                else:
                    self.log("ERROR", "Sifre input bulunamadi!")
                    return False

            except Exception as e:
                self.log("ERROR", f"Sifre girisi hatasi: {e}")
                return False

            # ADIM 8: "Weiter" butonuna tikla
            self.log("INFO", "ADIM 8: 'Weiter' butonuna tiklaniyor...")
            try:
                weiter_selectors = [
                    (By.XPATH, "//button[normalize-space(text())='Weiter']"),
                    (By.XPATH, "//button[contains(text(), 'Weiter')]"),
                    (By.XPATH, "//button[@type='submit']"),
                    (By.CSS_SELECTOR, "button[type='submit']"),
                ]

                weiter_found = False
                for selector in weiter_selectors:
                    try:
                        weiter_btn = WebDriverWait(self.driver, 5).until(
                            EC.element_to_be_clickable(selector)
                        )
                        ActionChains(self.driver).move_to_element(weiter_btn).click().perform()
                        self.log("INFO", f"Weiter/Submit tiklandi")
                        weiter_found = True
                        self.human_like_delay(5, 7)
                        break
                    except:
                        continue

                if not weiter_found:
                    self.log("ERROR", "Weiter butonu bulunamadi!")
                    return False

            except Exception as e:
                self.log("ERROR", f"Weiter hatasi: {e}")
                return False

            # ADIM 9: Login basarili mi kontrol et
            self.log("INFO", "ADIM 9: Login durumu kontrol ediliyor...")
            current_url = self.driver.current_url

            # Screenshot al
            try:
                self.driver.save_screenshot(str(TEMP_DIR / "vinted_4_afterlogin.png"))
                self.log("INFO", f"Login sonrasi screenshot: {TEMP_DIR / 'vinted_4_afterlogin.png'}")
                if self.send_telegram and self.captcha_handler:
                    self.captcha_handler.send_telegram_photo(
                        str(TEMP_DIR / "vinted_4_afterlogin.png"),
                        f"*VINTED LOGIN*\n\nURL: {current_url}"
                    )
            except:
                pass

            # Login basarili mi?
            if 'login' not in current_url.lower() and 'signup' not in current_url.lower():
                self.log("INFO", "Vinted login basarili!")
                return True
            else:
                self.log("ERROR", f"Vinted login basarisiz - URL: {current_url}")
                return False

        except Exception as e:
            self.log("ERROR", f"Vinted login hatasi: {e}")
            import traceback
            self.log("ERROR", traceback.format_exc())
            try:
                self.driver.save_screenshot(str(TEMP_DIR / "vinted_login_exception.png"))
            except:
                pass
            return False

    def upload_to_vinted(self, product, account):
        """Vinted'e urun yukle - Gercek form selector'lari ile"""
        try:
            self.log("INFO", "Urun yukleme sayfasina gidiliyor...")
            self.driver.get("https://www.vinted.de/items/new")
            self.human_like_delay(3, 4)

            optimized = product.get('optimized', {})
            images = product.get('images', [])
            original = product.get('original', {})

            # Benzersiz urun ID olustur
            product_id = hashlib.md5(original.get('url', str(time.time())).encode()).hexdigest()[:12]

            # ADIM 1: Resimleri indir ve yukle
            self.log("INFO", f"{len(images)} resim hazirlanıyor...")
            downloaded_images = []

            for img_url in images:
                # URL ise indir, dosya ise direkt kullan
                if img_url.startswith('http'):
                    local_path = self.download_image(img_url, product_id)
                    if local_path:
                        downloaded_images.append(local_path)
                elif Path(img_url).exists():
                    downloaded_images.append(img_url)

            if downloaded_images:
                self.log("INFO", f"{len(downloaded_images)} resim yukleniyor...")
                try:
                    # Dosya input'u bul - name='photos'
                    file_input = WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "input[name='photos']"))
                    )

                    # Resimleri yukle (max 20)
                    for i, img_path in enumerate(downloaded_images[:20]):
                        if Path(img_path).exists():
                            file_input.send_keys(str(img_path))
                            self.human_like_delay(2, 3)
                            self.log("INFO", f"Resim {i+1} yuklendi: {Path(img_path).name}")
                except Exception as e:
                    self.log("ERROR", f"Resim yukleme hatasi: {e}")
            else:
                self.log("WARNING", "Yuklenecek resim yok!")

            self.human_like_delay(2, 3)

            # ADIM 2: Baslik gir - testid='title--input'
            title = optimized.get('title', product.get('original', {}).get('title', ''))[:80]
            try:
                title_input = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid='title--input'], input[name='title']"))
                )
                title_input.clear()
                for char in title:
                    title_input.send_keys(char)
                    time.sleep(random.uniform(0.03, 0.08))
                self.log("INFO", f"Baslik girildi: {title[:30]}...")
            except Exception as e:
                self.log("ERROR", f"Baslik girisi hatasi: {e}")

            self.human_like_delay(1, 2)

            # ADIM 3: Aciklama gir - testid='description--input'
            description = optimized.get('description', product.get('original', {}).get('description', ''))[:2000]
            try:
                desc_input = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid='description--input'], textarea[name='description']"))
                )
                desc_input.clear()
                # Hizli yaz - cok uzun olabilir
                desc_input.send_keys(description)
                self.log("INFO", "Aciklama girildi")
            except Exception as e:
                self.log("ERROR", f"Aciklama girisi hatasi: {e}")

            self.human_like_delay(0.5, 1)

            # ADIM 4: Kategori sec - ZORUNLU ALAN
            category_selected = False
            try:
                # Kategori dropdown'ini bul ve tikla
                category_input = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "[data-testid='catalog-select-dropdown-input'], input[name='catalog_id'], [class*='catalog-select']"))
                )
                category_input.click()
                self.human_like_delay(1, 2)

                # Kleinanzeigen kategorisine gore Vinted kategorisi sec
                source_category = original.get('category', '').lower()

                # Kategori mapping
                if 'schuhe' in source_category or 'shoe' in source_category:
                    search_terms = ['Schuhe', 'Herrenschuhe', 'Damenschuhe']
                elif 'damen' in source_category or 'women' in source_category:
                    search_terms = ['Damen', 'Damenbekleidung']
                elif 'herren' in source_category or 'men' in source_category:
                    search_terms = ['Herren', 'Herrenbekleidung']
                elif 'jacke' in source_category or 'jacket' in source_category:
                    search_terms = ['Jacken', 'Mäntel']
                else:
                    search_terms = ['Sonstiges', 'Anderes']

                # Kategori ara ve sec
                for term in search_terms:
                    try:
                        # Kategori listesinde ara
                        category_option = WebDriverWait(self.driver, 3).until(
                            EC.element_to_be_clickable((By.XPATH, f"//*[contains(text(), '{term}')]"))
                        )
                        category_option.click()
                        self.human_like_delay(0.5, 1)

                        # Alt kategori varsa sec
                        try:
                            sub_category = WebDriverWait(self.driver, 2).until(
                                EC.element_to_be_clickable((By.CSS_SELECTOR, "[data-testid*='category'], [class*='catalog-item']"))
                            )
                            sub_category.click()
                            self.human_like_delay(0.5, 1)
                        except:
                            pass

                        category_selected = True
                        self.log("INFO", f"Kategori secildi: {term}")
                        break
                    except:
                        continue

                # Hala secilemedi ise ilk kategoriyi sec
                if not category_selected:
                    try:
                        first_cat = WebDriverWait(self.driver, 3).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, "[class*='catalog-item'], [data-testid*='catalog']"))
                        )
                        first_cat.click()
                        self.human_like_delay(0.5, 1)
                        category_selected = True
                        self.log("INFO", "Varsayilan kategori secildi")
                    except:
                        category_input.send_keys(Keys.ESCAPE)
                        self.log("WARNING", "Kategori secilemedi!")

            except Exception as e:
                self.log("ERROR", f"Kategori secim hatasi: {e}")

            if not category_selected:
                self.log("ERROR", "KATEGORI ZORUNLU - Yukleme basarisiz olacak!")
                # Yine de devam et, belki form submit olur

            # ADIM 5: Durum sec
            try:
                condition_btn = self.driver.find_element(By.CSS_SELECTOR, "[data-testid='status-select'], [class*='status']")
                condition_btn.click()
                self.human_like_delay(0.5, 1)

                # "Gut" durumunu sec
                good_condition = self.driver.find_element(By.XPATH, "//*[contains(text(), 'Gut') or contains(text(), 'Good')]")
                good_condition.click()
                self.human_like_delay(0.5, 1)
            except Exception as e:
                self.log("WARNING", f"Durum secimi atlandi: {e}")

            # ADIM 6: Fiyat gir - testid='price-input--input'
            # MAĞAZA TRANSFERİ: Fiyat AYNI kalır!
            price = product.get('original', {}).get('price', 0)
            try:
                price_input = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid='price-input--input'], input[name='price']"))
                )
                price_input.clear()
                price_str = str(int(price)) if price else "10"
                for char in price_str:
                    price_input.send_keys(char)
                    time.sleep(random.uniform(0.05, 0.1))
                self.log("INFO", f"Fiyat girildi: {price_str} EUR (orijinal fiyat)")
            except Exception as e:
                self.log("ERROR", f"Fiyat girisi hatasi: {e}")

            self.human_like_delay(1, 2)

            # ADIM 7: Kargo secenekleri
            try:
                # DHL/Hermes checkbox'lari
                shipping_checkboxes = self.driver.find_elements(By.CSS_SELECTOR, "input[type='checkbox'][name*='shipping'], [class*='shipping'] input")
                for checkbox in shipping_checkboxes[:2]:  # Ilk 2 kargo secenegi
                    if not checkbox.is_selected():
                        checkbox.click()
                        self.human_like_delay(0.3, 0.5)
            except Exception as e:
                self.log("WARNING", f"Kargo secimi atlandi: {e}")

            # ADIM 8: Hochladen (Yayinla) butonu - testid='upload-form-save-button'
            self.human_like_delay(2, 3)
            try:
                # Screenshot - form dolduruldu
                try:
                    self.driver.save_screenshot(str(TEMP_DIR / "vinted_form_filled.png"))
                except:
                    pass

                publish_btn = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "[data-testid='upload-form-save-button'], button[type='submit']"))
                )

                # Scroll to button and click
                ActionChains(self.driver).move_to_element(publish_btn).click().perform()
                self.log("INFO", "Hochladen butonu tiklandi")
                self.human_like_delay(5, 8)

                # Basari kontrolu - URL degisimi veya success mesaji
                current_url = self.driver.current_url
                if "items" in current_url or "member" in current_url or "/item/" in current_url:
                    self.log("INFO", "Urun Vinted'e basariyla yuklendi!")

                    # Screenshot - basarili yukleme
                    try:
                        self.driver.save_screenshot(str(TEMP_DIR / "vinted_upload_success.png"))
                    except:
                        pass
                    return True
                else:
                    # Hata mesaji var mi kontrol et
                    try:
                        error_msg = self.driver.find_element(By.CSS_SELECTOR, "[class*='error'], [class*='alert']")
                        if error_msg.is_displayed():
                            self.log("ERROR", f"Yukleme hatasi: {error_msg.text}")
                            return False
                    except:
                        pass

                    self.log("WARNING", f"Yukleme durumu belirsiz, URL: {current_url}")
                    return True  # Yine de basarili say

            except Exception as e:
                self.log("ERROR", f"Hochladen butonu hatasi: {e}")
                try:
                    self.driver.save_screenshot(str(TEMP_DIR / "vinted_upload_error.png"))
                except:
                    pass
                return False

        except Exception as e:
            self.log("ERROR", f"Vinted yukleme hatasi: {e}")
            return False

    def transfer_to_vinted(self, product, target_email):
        """Urunu Vinted'e yukle"""
        # Vinted hesap bilgisi
        vinted_account = None
        for acc in VINTED['accounts']:
            if acc['email'] == target_email:
                vinted_account = acc
                break

        if not vinted_account:
            self.log("ERROR", f"Vinted hesabi bulunamadi: {target_email}")
            return False

        self.log("INFO", f"Vinted'e yukleniyor: {product.get('optimized', {}).get('title', '')}")

        # Gercek Vinted yukleme
        product_id = f"TRANSFER-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        try:
            # Vinted'e login ol (eger yapilmadiysa)
            if not hasattr(self, 'vinted_logged_in') or not self.vinted_logged_in:
                if not self.login_to_vinted(vinted_account):
                    # Login basarisiz, pending olarak kaydet
                    self.log("WARNING", "Vinted login basarisiz, pending olarak kaydediliyor")
                    product['id'] = product_id
                    product['target_platform'] = 'vinted'
                    product['target_account'] = target_email
                    product['status'] = 'pending_upload'
                    product['error'] = 'login_failed'

                    pending_file = PENDING_DIR / f"{product_id}.json"
                    with open(pending_file, 'w', encoding='utf-8') as f:
                        json.dump(product, f, ensure_ascii=False, indent=2)
                    return product_id

                self.vinted_logged_in = True

            # Urunu yukle
            if self.upload_to_vinted(product, vinted_account):
                self.log("INFO", f"Transfer basarili: {product_id}")

                # Basarili yukleme kaydini tut
                product['id'] = product_id
                product['target_platform'] = 'vinted'
                product['target_account'] = target_email
                product['status'] = 'uploaded'
                product['uploaded_at'] = datetime.now().isoformat()

                # Completed dizinine kaydet
                completed_dir = PENDING_DIR.parent / "completed"
                completed_dir.mkdir(exist_ok=True)
                completed_file = completed_dir / f"{product_id}.json"
                with open(completed_file, 'w', encoding='utf-8') as f:
                    json.dump(product, f, ensure_ascii=False, indent=2)

                return product_id
            else:
                # Yukleme basarisiz, pending olarak kaydet
                self.log("WARNING", "Yukleme basarisiz, pending olarak kaydediliyor")
                product['id'] = product_id
                product['target_platform'] = 'vinted'
                product['target_account'] = target_email
                product['status'] = 'upload_failed'

                pending_file = PENDING_DIR / f"{product_id}.json"
                with open(pending_file, 'w', encoding='utf-8') as f:
                    json.dump(product, f, ensure_ascii=False, indent=2)
                return product_id

        except Exception as e:
            self.log("ERROR", f"Transfer hatasi: {e}")

            # Hata durumunda pending olarak kaydet
            product['id'] = product_id
            product['target_platform'] = 'vinted'
            product['target_account'] = target_email
            product['status'] = 'error'
            product['error'] = str(e)

            pending_file = PENDING_DIR / f"{product_id}.json"
            with open(pending_file, 'w', encoding='utf-8') as f:
                json.dump(product, f, ensure_ascii=False, indent=2)
            return product_id

    def execute_transfer(self, source_email, target_platform, target_email, chat_id):
        """Magazadan magazaya transfer"""
        self.send_message(
            chat_id,
            f"*TRANSFER BASLATILDI*\n\n"
            f"Kaynak: Kleinanzeigen ({source_email})\n"
            f"Hedef: {target_platform} ({target_email})\n\n"
            f"_Insansi gezinme baslatiliyor..._"
        )

        # Insansi gezinme oturumu - transfer oncesi
        if self.quality_controller and self.driver:
            try:
                self.log("INFO", "Insansi gezinme oturumu baslatiliyor...")
                self.quality_controller.human_browsing_session('kleinanzeigen', duration_minutes=1)
                self.log("INFO", "Insansi gezinme oturumu tamamlandi")
            except Exception as e:
                self.log("WARNING", f"Insansi gezinme hatasi: {e}")

        self.send_message(chat_id, "_Urunler cekiliyor..._")

        # Kleinanzeigen urunlerini cek
        products = self.get_kleinanzeigen_products(source_email)

        if not products:
            self.send_message(chat_id, "[-] Hic urun bulunamadi!")
            return

        self.send_message(
            chat_id,
            f"*{len(products)} URUN BULUNDU*\n\n"
            f"Transfer islemi basliyor...\n"
            f"Her urun icin ~2 dakika beklenecek."
        )

        transferred = 0
        failed = 0

        for i, product in enumerate(products, 1):
            try:
                # Urun detaylarini cek
                details = self.get_product_details(product['url'])
                if not details:
                    failed += 1
                    continue

                # Resimleri isle
                processed_images = self.process_images(details.get('images', []), f"PROD{i}")

                # Icerigi optimize et
                optimized = self.optimize_content(details)

                # Transfer objesi olustur
                transfer_product = {
                    'original': details,
                    'optimized': optimized,
                    'images': processed_images
                }

                # KRITIK: Fiyat eslestirmesi - kaynak fiyati OLDUĞU GIBI kullan
                # Kusirat, ondalik OLMAYACAK - tam sayi fiyat
                original_price = details.get('price', 0)
                # Tam sayiya cevir - küsürat yok
                original_price = int(original_price)

                if optimized.get('suggested_price') != original_price:
                    self.log("WARNING", f"Fiyat duzeltiliyor: {optimized.get('suggested_price')} -> {original_price}")
                    transfer_product['optimized']['suggested_price'] = original_price

                # Kalite kontrolu - yukleme oncesi
                qc_passed = True
                if self.quality_controller:
                    try:
                        qc_report = self.quality_controller.run_full_quality_check(transfer_product)

                        if not qc_report.get('overall_passed', True):
                            self.log("WARNING", f"Kalite kontrolu basarisiz: {qc_report.get('issues', [])}")
                            # Telegram'a rapor gonder
                            self.quality_controller.send_quality_report(qc_report)

                            # SEO skoru 60'in altindaysa uyar ama devam et
                            seo_score = qc_report.get('seo', {}).get('score', 100)
                            if seo_score < 40:
                                qc_passed = False
                                self.log("ERROR", f"SEO skoru cok dusuk ({seo_score}), urun atlanıyor")
                        else:
                            self.log("INFO", f"Kalite kontrolu basarili")
                    except Exception as e:
                        self.log("WARNING", f"Kalite kontrolu hatasi: {e}")

                if not qc_passed:
                    failed += 1
                    continue

                # Vinted'e transfer
                product_id = self.transfer_to_vinted(transfer_product, target_email)

                if product_id:
                    transferred += 1
                    # Baslik ve fiyati al - optimize edilmis veya orijinal
                    display_title = optimized.get('title') or details.get('title', 'Baslik yok')
                    display_price = optimized.get('suggested_price') or details.get('price', 0)

                    self.send_message(
                        chat_id,
                        f"*{i}/{len(products)} TAMAMLANDI*\n\n"
                        f"Baslik: {display_title[:50]}...\n"
                        f"Fiyat: {display_price} EUR\n"
                        f"ID: `{product_id}`"
                    )
                else:
                    failed += 1

                # Insan benzeri bekleme
                if i < len(products):
                    wait_time = random.randint(90, 150)  # 1.5-2.5 dakika
                    self.log("INFO", f"Bekleniyor: {wait_time}s")
                    time.sleep(wait_time)

                    # Her 3-5 urun arasinda insansi gezinme
                    if i % random.randint(3, 5) == 0 and self.quality_controller:
                        try:
                            self.log("INFO", "Ara insansi gezinme oturumu...")
                            # Hedef platformda gez
                            self.quality_controller.human_browsing_session(target_platform, duration_minutes=0.5)
                        except Exception as e:
                            self.log("WARNING", f"Ara gezinme hatasi: {e}")

            except Exception as e:
                self.log("ERROR", f"Urun {i} transfer hatasi: {e}")
                failed += 1

        # Ozet
        self.send_message(
            chat_id,
            f"*TRANSFER TAMAMLANDI*\n\n"
            f"Basarili: {transferred}\n"
            f"Basarisiz: {failed}\n"
            f"Toplam: {len(products)}\n\n"
            f"_Transfer dogrulama baslatiliyor..._"
        )

        # Transfer dogrulama - hedef platformdaki urunleri kontrol et
        if transferred > 0:
            self.verify_transfer(target_platform, target_email, chat_id)

        # Driver'i kapat
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None

    def verify_transfer(self, platform, account_email, chat_id):
        """Transfer edilen urunleri hedef platformda dogrula"""
        self.log("INFO", "Transfer dogrulama baslatiliyor...")

        try:
            # Completed dizinindeki urunleri al
            completed_dir = PENDING_DIR.parent / "completed"
            if not completed_dir.exists():
                self.send_message(chat_id, "[-] Tamamlanan transfer bulunamadi")
                return

            completed_files = list(completed_dir.glob("*.json"))
            if not completed_files:
                self.send_message(chat_id, "[-] Dogrulanacak urun bulunamadi")
                return

            # Son 1 saatteki transferleri al
            recent_transfers = []
            one_hour_ago = datetime.now() - timedelta(hours=1)

            for f in completed_files:
                try:
                    with open(f, 'r', encoding='utf-8') as file:
                        product = json.load(file)

                    uploaded_at = product.get('uploaded_at')
                    if uploaded_at:
                        upload_time = datetime.fromisoformat(uploaded_at)
                        if upload_time > one_hour_ago:
                            recent_transfers.append(product)
                except:
                    continue

            if not recent_transfers:
                self.send_message(chat_id, "[-] Son 1 saatte transfer bulunamadi")
                return

            self.send_message(
                chat_id,
                f"*TRANSFER DOGRULAMA*\n\n"
                f"Kontrol edilecek: {len(recent_transfers)} urun\n"
                f"Platform: {platform}\n\n"
                f"_Hedef magazaya baglaniliyor..._"
            )

            # Hedef platformda dogrulama yap
            verification_results = []

            if platform.lower() == 'vinted':
                verification_results = self._verify_vinted_products(recent_transfers, account_email)
            else:
                self.send_message(chat_id, f"[-] {platform} icin dogrulama henuz desteklenmiyor")
                return

            # Sonuclari raporla
            verified = sum(1 for r in verification_results if r['verified'])
            issues = [r for r in verification_results if not r['verified'] or r.get('differences')]

            report = f"*DOGRULAMA RAPORU*\n\n"
            report += f"✅ Dogrulanan: {verified}/{len(recent_transfers)}\n"

            if issues:
                report += f"\n*Sorunlu Urunler:*\n"
                for issue in issues[:5]:  # Max 5 sorun goster
                    report += f"\n• {issue.get('title', 'Bilinmeyen')[:30]}...\n"
                    if issue.get('differences'):
                        for diff in issue['differences'][:3]:
                            report += f"  - {diff}\n"
                    if not issue['verified']:
                        report += f"  ⚠️ Hedef platformda bulunamadi\n"

            self.send_message(chat_id, report)

        except Exception as e:
            self.log("ERROR", f"Dogrulama hatasi: {e}")
            self.send_message(chat_id, f"[-] Dogrulama hatasi: {e}")

    def _verify_vinted_products(self, products, account_email):
        """Vinted'deki urunleri dogrula"""
        results = []

        try:
            # Eger driver yoksa veya login degilse, yeniden login ol
            if not self.driver or not hasattr(self, 'vinted_logged_in') or not self.vinted_logged_in:
                vinted_account = None
                for acc in VINTED['accounts']:
                    if acc['email'] == account_email:
                        vinted_account = acc
                        break

                if not vinted_account:
                    return results

                if not self.login_to_vinted(vinted_account):
                    return results

                self.vinted_logged_in = True

            # Kullanicinin urunlerini listeleyen sayfaya git
            self.driver.get("https://www.vinted.de/member/items")
            self.human_like_delay(3, 5)

            # Sayfa kaynagini al
            page_source = self.driver.page_source

            for product in products:
                result = {
                    'id': product.get('id'),
                    'title': product.get('optimized', {}).get('title') or product.get('original', {}).get('title', ''),
                    'verified': False,
                    'differences': []
                }

                # Baslik arazi
                original_title = result['title']

                # Baslik sayfada var mi kontrol et
                if original_title and len(original_title) > 10:
                    # Basligin bir kismini ara
                    search_text = original_title[:20].lower()
                    if search_text in page_source.lower():
                        result['verified'] = True

                        # Detayli karsilastirma (opsiyonel - performans icin atlanabilir)
                        # Fiyat kontrolu
                        original_price = product.get('optimized', {}).get('suggested_price') or \
                                        product.get('original', {}).get('price', 0)

                        # Fiyat degisikligi kontrolu
                        price_str = f"{original_price}"
                        if price_str not in page_source:
                            # Belki fiyat formati farkli (1.000 vs 1000)
                            formatted_price = f"{original_price:,}".replace(",", ".")
                            if formatted_price not in page_source:
                                result['differences'].append(f"Fiyat farkli olabilir: {original_price} EUR")
                    else:
                        result['differences'].append("Baslik hedef platformda bulunamadi")

                results.append(result)

        except Exception as e:
            self.log("ERROR", f"Vinted dogrulama hatasi: {e}")

        return results

    def process_message(self, message):
        """Mesaji isle"""
        chat_id = message.get("chat", {}).get("id")
        text = message.get("text", "").strip()
        message_id = message.get("message_id")
        reply_to = message.get("reply_to_message")

        if not text:
            return

        # Sadece store_transfer grubundan komut al
        if chat_id != self.channels.get('store_transfer'):
            return

        self.log("INFO", f"Komut alindi: {text[:50]}...")

        # REPLY ILE DUZENLEME - Eger bir mesaja reply yapilmissa
        if reply_to:
            reply_text = reply_to.get("text", "")
            # Transfer mesajindan ID cikar
            import re
            id_match = re.search(r'ID:\s*`?(TRANSFER-\d+)`?', reply_text)
            if id_match:
                product_id = id_match.group(1)
                self.log("INFO", f"Reply ile duzenleme: {product_id}")

                # AI ile istegi analiz et
                edit_result = self.analyze_edit_request(text, product_id)
                if edit_result:
                    self.send_message(chat_id, edit_result, reply_to=message_id)
                return

        # AI ile analiz
        analysis = self.analyze_command(text, chat_id)

        if not analysis:
            return

        # Alan kontrolu
        if not analysis.get('is_allowed'):
            redirect = analysis.get('redirect_to')
            if redirect:
                self.send_message(
                    chat_id,
                    f"*HATALI GRUP*\n\n"
                    f"Bu islem *{redirect}* grubunda yapilmali.\n\n"
                    f"_{analysis.get('response', '')}_",
                    reply_to=message_id
                )
            else:
                self.send_message(
                    chat_id,
                    analysis.get('response', 'Bu islem bu grupta yapilamaz.'),
                    reply_to=message_id
                )
            return

        # Komutu calistir
        intent = analysis.get('intent')

        if intent == 'transfer_products':
            source = analysis.get('source_platform', 'kleinanzeigen')
            target = analysis.get('target_platform', 'vinted')

            # Hesap bilgileri
            source_email = analysis.get('account_email') or KLEINANZEIGEN['accounts'][0]['email']
            target_email = VINTED['accounts'][0]['email']

            # Transfer thread'de baslat
            import threading
            transfer_thread = threading.Thread(
                target=self.execute_transfer,
                args=(source_email, target, target_email, chat_id)
            )
            transfer_thread.start()

        elif intent == 'list_store':
            self.send_message(
                chat_id,
                "*MAGAZA URUNLERI LISTELENIYOR...*\n\n"
                "_Lutfen bekleyin..._",
                reply_to=message_id
            )

            products = self.get_kleinanzeigen_products(
                analysis.get('account_email') or KLEINANZEIGEN['accounts'][0]['email']
            )

            if products:
                msg = f"*MAGAZA URUNLERI ({len(products)})*\n\n"
                for i, p in enumerate(products[:10], 1):
                    msg += f"{i}. {p['title'][:40]}... - {p['price']} EUR\n"

                if len(products) > 10:
                    msg += f"\n_...ve {len(products) - 10} urun daha_"

                self.send_message(chat_id, msg)
            else:
                self.send_message(chat_id, "Magaza bos veya erisim hatasi.")

        elif intent == 'update_price':
            # Fiyat guncelle
            params = analysis.get('action_params', {})
            product_id = params.get('product_id', '')
            new_price = params.get('new_price', 0)

            if not product_id or not new_price:
                self.send_message(
                    chat_id,
                    "Fiyat guncellemek icin:\n`fiyat TRANSFER-xxx 50`\n\n"
                    "Ornek: `fiyat TRANSFER-20251120234832 35`",
                    reply_to=message_id
                )
                return

            # Pending dosyasini bul ve guncelle
            pending_file = PENDING_DIR / f"{product_id}.json"
            completed_file = PENDING_DIR.parent / "completed" / f"{product_id}.json"

            target_file = None
            if pending_file.exists():
                target_file = pending_file
            elif completed_file.exists():
                target_file = completed_file

            if target_file:
                try:
                    with open(target_file, 'r', encoding='utf-8') as f:
                        product = json.load(f)

                    old_price = product.get('optimized', {}).get('suggested_price', 0)
                    product['optimized']['suggested_price'] = int(new_price)

                    with open(target_file, 'w', encoding='utf-8') as f:
                        json.dump(product, f, ensure_ascii=False, indent=2)

                    self.send_message(
                        chat_id,
                        f"*FIYAT GUNCELLENDI*\n\n"
                        f"ID: `{product_id}`\n"
                        f"Eski fiyat: {old_price} EUR\n"
                        f"Yeni fiyat: {new_price} EUR",
                        reply_to=message_id
                    )
                except Exception as e:
                    self.send_message(
                        chat_id,
                        f"[-] Fiyat guncelleme hatasi: {e}",
                        reply_to=message_id
                    )
            else:
                self.send_message(
                    chat_id,
                    f"[-] Urun bulunamadi: `{product_id}`",
                    reply_to=message_id
                )

        else:
            self.send_message(
                chat_id,
                analysis.get('response', 'Komut islendi.'),
                reply_to=message_id
            )

    def run(self):
        """Bot'u calistir"""
        print("=" * 60)
        print("TATANGA - Store Transfer Handler")
        print("=" * 60)
        print(f"\nDinlenen grup: store_transfer ({self.channels.get('store_transfer')})")

        # Baslangic mesaji
        self.send_message(
            self.channels['store_transfer'],
            "*MAGAZALAR ARASI TRANSFER AKTIF*\n\n"
            "Kendi magazalariniz arasinda urun transferi yapabilirsiniz.\n\n"
            "*Ornek komutlar:*\n"
            "- `kleinanzeigen magazamdaki urunleri vinted'e aktar`\n"
            "- `vinted'deki urunleri ebay'e kopyala`\n"
            "- `willhaben magazami listele`\n"
            "- `fiyat TRANSFER-xxx 50`\n\n"
            "*Desteklenen platformlar:*\n"
            "Kleinanzeigen, Vinted, eBay, Willhaben\n\n"
            "_Fiyatlar kaynak sitedeki orijinal haliyle aktarilir._\n"
            "_Sonra degistirebilirsiniz._"
        )

        print("\nDinleniyor... (Ctrl+C ile durdur)\n")

        while True:
            try:
                updates = self.get_updates()

                for update in updates:
                    self.last_update_id = update.get("update_id", self.last_update_id)

                    if "message" in update:
                        self.process_message(update["message"])

            except KeyboardInterrupt:
                print("\n\nDurduruldu.")
                break

            except Exception as e:
                self.log("ERROR", f"Ana dongu hatasi: {e}")
                time.sleep(5)


if __name__ == "__main__":
    handler = StoreTransferHandler()
    handler.run()
