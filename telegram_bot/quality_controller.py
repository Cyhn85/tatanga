#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TATANGA - Quality Controller & Human-like Browser
Kalite kontrol, SEO analiz, ban tespiti ve insansi gezinme
"""

import os
import sys
import json
import time
import random
import hashlib
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

import requests
from PIL import Image
from shared.config.credentials import TELEGRAM

# Log dizini
LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

class QualityController:
    """Kalite kontrol ve insansi gezinme sistemi"""

    def __init__(self, driver=None, logger=None):
        self.driver = driver
        self.logger = logger
        self.bot_token = TELEGRAM['bot_token']
        self.system_chat = TELEGRAM['channels']['system']

        # Log dosyasi
        self.qc_log_file = LOG_DIR / f"quality_control_{datetime.now().strftime('%Y%m%d')}.jsonl"

        # Platform URL'leri
        self.platform_urls = {
            'kleinanzeigen': 'https://www.kleinanzeigen.de',
            'vinted': 'https://www.vinted.de',
            'ebay': 'https://www.ebay.de',
            'willhaben': 'https://www.willhaben.at',
        }

    def log(self, level, message, data=None):
        """Log kaydet"""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "level": level,
            "message": message,
            "data": data or {}
        }

        with open(self.qc_log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

        if self.logger:
            self.logger(level, message, data)
        else:
            print(f"[{level}] {message}")

    def human_like_delay(self, min_sec=0.5, max_sec=2.0):
        """Insan gibi bekleme"""
        time.sleep(random.uniform(min_sec, max_sec))

    # ========================================
    # INSANSI GEZINME DAVRANISLARI
    # ========================================

    def random_mouse_movement(self):
        """Rastgele mouse hareketi"""
        if not self.driver:
            return

        try:
            actions = ActionChains(self.driver)

            # Rastgele koordinatlar
            x_offset = random.randint(-100, 100)
            y_offset = random.randint(-100, 100)

            actions.move_by_offset(x_offset, y_offset)
            actions.perform()

            self.human_like_delay(0.1, 0.3)

            # Geri don
            actions.move_by_offset(-x_offset, -y_offset)
            actions.perform()

        except:
            pass

    def random_scroll(self):
        """Rastgele scroll"""
        if not self.driver:
            return

        try:
            # Rastgele scroll miktari
            scroll_amount = random.randint(200, 600)
            direction = random.choice(['down', 'up'])

            if direction == 'down':
                self.driver.execute_script(f"window.scrollBy(0, {scroll_amount});")
            else:
                self.driver.execute_script(f"window.scrollBy(0, -{scroll_amount});")

            self.human_like_delay(0.5, 1.5)

        except:
            pass

    def click_random_product(self, platform):
        """Ana sayfadan rastgele bir urune tikla"""
        if not self.driver:
            return False

        try:
            # Platform-spesifik urun selectorleri
            product_selectors = {
                'kleinanzeigen': [
                    "article.aditem a",
                    "[data-testid='aditem'] a",
                    ".ad-listitem a",
                ],
                'vinted': [
                    "[data-testid='grid-item'] a",
                    ".feed-grid__item a",
                    ".ItemBox_container a",
                ],
                'ebay': [
                    ".s-item__link",
                    ".srp-results .s-item a",
                ],
                'willhaben': [
                    "[data-testid='ad-list-item'] a",
                    ".search-result-entry a",
                ],
            }

            selectors = product_selectors.get(platform, product_selectors['kleinanzeigen'])

            for selector in selectors:
                try:
                    products = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if products:
                        # Rastgele bir urun sec
                        product = random.choice(products[:10])  # Ilk 10'dan

                        # Scroll into view
                        self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", product)
                        self.human_like_delay(0.5, 1)

                        # Tikla
                        actions = ActionChains(self.driver)
                        actions.move_to_element(product)
                        self.human_like_delay(0.3, 0.7)
                        actions.click()
                        actions.perform()

                        self.log("INFO", f"Rastgele urune tiklandi: {platform}")
                        self.human_like_delay(2, 4)

                        return True
                except:
                    continue

            return False

        except Exception as e:
            self.log("WARNING", f"Rastgele urun tiklama hatasi: {e}")
            return False

    def visit_seller_profile(self, platform):
        """Satici profiline git"""
        if not self.driver:
            return False

        try:
            # Platform-spesifik satici profil selectorleri
            seller_selectors = {
                'kleinanzeigen': [
                    "[data-testid='seller-info'] a",
                    ".userprofile-vip a",
                    "a[href*='/s-bestandsliste']",
                ],
                'vinted': [
                    "[data-testid='item-details-user'] a",
                    ".ItemPage_user a",
                    "a[href*='/member/']",
                ],
                'ebay': [
                    ".x-sellercard-atf__info a",
                    "a[href*='/usr/']",
                ],
                'willhaben': [
                    "[data-testid='seller-info'] a",
                    ".seller-info a",
                ],
            }

            selectors = seller_selectors.get(platform, seller_selectors['kleinanzeigen'])

            for selector in selectors:
                try:
                    seller_link = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if seller_link.is_displayed():
                        # Scroll into view
                        self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", seller_link)
                        self.human_like_delay(0.5, 1)

                        # Tikla
                        actions = ActionChains(self.driver)
                        actions.move_to_element(seller_link)
                        self.human_like_delay(0.3, 0.7)
                        actions.click()
                        actions.perform()

                        self.log("INFO", f"Satici profiline gidildi: {platform}")
                        self.human_like_delay(3, 5)

                        return True
                except:
                    continue

            return False

        except Exception as e:
            self.log("WARNING", f"Satici profil ziyareti hatasi: {e}")
            return False

    def go_back(self):
        """Geri git"""
        if not self.driver:
            return

        try:
            self.driver.back()
            self.human_like_delay(1, 2)
        except:
            pass

    def human_browsing_session(self, platform, duration_minutes=2):
        """Insansi gezinme oturumu"""
        if not self.driver:
            return

        self.log("INFO", f"Insansi gezinme baslatildi: {platform} ({duration_minutes} dk)")

        start_time = time.time()
        end_time = start_time + (duration_minutes * 60)

        # Ana sayfaya git
        base_url = self.platform_urls.get(platform)
        if not base_url:
            return

        try:
            self.driver.get(base_url)
            self.human_like_delay(2, 3)

            actions_performed = 0

            while time.time() < end_time:
                # Rastgele aksiyon sec
                action = random.choice([
                    'scroll', 'scroll', 'scroll',  # Daha fazla scroll
                    'click_product',
                    'visit_seller',
                    'mouse_move',
                    'go_back',
                ])

                if action == 'scroll':
                    self.random_scroll()

                elif action == 'click_product':
                    if self.click_random_product(platform):
                        actions_performed += 1

                elif action == 'visit_seller':
                    if self.visit_seller_profile(platform):
                        actions_performed += 1
                        self.human_like_delay(2, 4)
                        self.go_back()

                elif action == 'mouse_move':
                    self.random_mouse_movement()

                elif action == 'go_back':
                    self.go_back()

                self.human_like_delay(1, 3)

            self.log("INFO", f"Insansi gezinme tamamlandi: {actions_performed} aksiyon")

        except Exception as e:
            self.log("ERROR", f"Insansi gezinme hatasi: {e}")

    # ========================================
    # KALITE KONTROL
    # ========================================

    def check_image_quality(self, image_path):
        """Resim kalitesini kontrol et"""
        result = {
            'passed': True,
            'issues': [],
            'details': {}
        }

        try:
            img = Image.open(image_path)

            # Boyut kontrolu
            width, height = img.size
            result['details']['size'] = f"{width}x{height}"

            if width < 400 or height < 400:
                result['issues'].append(f"Resim cok kucuk: {width}x{height} (min 400x400)")
                result['passed'] = False

            if width > 4000 or height > 4000:
                result['issues'].append(f"Resim cok buyuk: {width}x{height} (max 4000x4000)")

            # Format kontrolu
            format_name = img.format or 'Unknown'
            result['details']['format'] = format_name

            if format_name not in ['JPEG', 'PNG', 'WEBP']:
                result['issues'].append(f"Desteklenmeyen format: {format_name}")

            # Dosya boyutu
            file_size = os.path.getsize(image_path)
            result['details']['file_size_kb'] = round(file_size / 1024, 2)

            if file_size > 10 * 1024 * 1024:  # 10MB
                result['issues'].append(f"Dosya cok buyuk: {file_size / 1024 / 1024:.1f}MB")

            # Hash hesapla (duplicate tespiti icin)
            with open(image_path, 'rb') as f:
                result['details']['hash'] = hashlib.md5(f.read()).hexdigest()

        except Exception as e:
            result['passed'] = False
            result['issues'].append(f"Resim acilamadi: {e}")

        return result

    def check_seo_quality(self, title, description):
        """SEO kalitesini kontrol et"""
        result = {
            'passed': True,
            'score': 100,
            'issues': [],
            'suggestions': []
        }

        # Baslik kontrolleri
        if not title:
            result['issues'].append("Baslik bos")
            result['score'] -= 30
            result['passed'] = False
        else:
            title_len = len(title)
            result['details'] = {'title_length': title_len}

            if title_len < 20:
                result['issues'].append(f"Baslik cok kisa: {title_len} karakter (min 20)")
                result['score'] -= 15
            elif title_len > 80:
                result['issues'].append(f"Baslik cok uzun: {title_len} karakter (max 80)")
                result['score'] -= 10

            # Marka kontrolu
            brands = ['Nike', 'Adidas', 'Puma', 'Zara', 'H&M', 'Tommy', 'Gucci', 'Louis', 'Chanel']
            has_brand = any(brand.lower() in title.lower() for brand in brands)
            if not has_brand:
                result['suggestions'].append("Marka adi eklemeyi deneyin")

            # Beden kontrolu
            sizes = ['XS', 'S', 'M', 'L', 'XL', 'XXL', '36', '38', '40', '42', '44']
            has_size = any(size in title.upper() for size in sizes)
            if not has_size:
                result['suggestions'].append("Beden bilgisi eklemeyi deneyin")

        # Aciklama kontrolleri
        if not description:
            result['issues'].append("Aciklama bos")
            result['score'] -= 20
        else:
            desc_len = len(description)

            if desc_len < 50:
                result['issues'].append(f"Aciklama cok kisa: {desc_len} karakter (min 50)")
                result['score'] -= 15
            elif desc_len > 2000:
                result['issues'].append(f"Aciklama cok uzun: {desc_len} karakter (max 2000)")
                result['score'] -= 5

        result['passed'] = result['score'] >= 60

        return result

    def check_price_validity(self, original_price, suggested_price, source_platform):
        """Fiyat gecerliligi kontrol et"""
        result = {
            'passed': True,
            'issues': [],
            'details': {
                'original': original_price,
                'suggested': suggested_price,
                'source': source_platform
            }
        }

        if not suggested_price or suggested_price <= 0:
            result['issues'].append("Gecersiz fiyat: 0 veya negatif")
            result['passed'] = False
            return result

        # Fiyat farki kontrolu (magaza transferinde ayni olmali)
        if original_price and original_price > 0:
            diff_percent = abs(suggested_price - original_price) / original_price * 100
            result['details']['diff_percent'] = round(diff_percent, 2)

            if diff_percent > 50:
                result['issues'].append(f"Fiyat farki cok yuksek: %{diff_percent:.0f}")
                result['passed'] = False
            elif diff_percent > 20:
                result['issues'].append(f"Fiyat farki dikkat: %{diff_percent:.0f}")

        # Mantikli fiyat araligi
        if suggested_price < 1:
            result['issues'].append("Fiyat cok dusuk: < 1 EUR")
            result['passed'] = False
        elif suggested_price > 10000:
            result['issues'].append("Fiyat cok yuksek: > 10000 EUR")

        return result

    def check_ban_indicators(self, platform):
        """Ban/engel gostergelerini kontrol et"""
        if not self.driver:
            return {'passed': True, 'issues': []}

        result = {
            'passed': True,
            'issues': [],
            'indicators': []
        }

        try:
            page_text = self.driver.find_element(By.TAG_NAME, "body").text.lower()
            current_url = self.driver.current_url.lower()

            # Ban gostergeleri
            ban_keywords = [
                'gesperrt', 'blocked', 'suspended', 'banned',
                'konto deaktiviert', 'account disabled',
                'zugriff verweigert', 'access denied',
                'captcha', 'robot', 'bot detection',
                'unusual activity', 'ungewohnliche aktivitat'
            ]

            for keyword in ban_keywords:
                if keyword in page_text:
                    result['indicators'].append(keyword)
                    result['issues'].append(f"Ban gostergesi tespit edildi: {keyword}")
                    result['passed'] = False

            # URL kontrolu
            if 'captcha' in current_url or 'blocked' in current_url:
                result['issues'].append(f"Engel URL'si tespit edildi: {current_url}")
                result['passed'] = False

            # Login sayfasina yonlendirme
            if 'login' in current_url and 'login' not in self.driver.title.lower():
                result['issues'].append("Beklenmedik login yonlendirmesi")

        except Exception as e:
            result['issues'].append(f"Ban kontrolu hatasi: {e}")

        return result

    def run_full_quality_check(self, product):
        """Tam kalite kontrolu calistir"""
        report = {
            'product_id': product.get('id', 'unknown'),
            'timestamp': datetime.now().isoformat(),
            'checks': {},
            'overall_passed': True,
            'total_issues': 0
        }

        # 1. Resim kalite kontrolu
        images = product.get('images', [])
        image_results = []
        for i, img_path in enumerate(images):
            if os.path.exists(img_path):
                img_result = self.check_image_quality(img_path)
                img_result['index'] = i + 1
                image_results.append(img_result)
                if not img_result['passed']:
                    report['overall_passed'] = False
                    report['total_issues'] += len(img_result['issues'])

        report['checks']['images'] = image_results

        # 2. SEO kalite kontrolu
        optimized = product.get('optimized', {})
        original = product.get('original', {})

        title = optimized.get('title') or original.get('title', '')
        description = optimized.get('description') or original.get('description', '')

        seo_result = self.check_seo_quality(title, description)
        report['checks']['seo'] = seo_result
        report['seo'] = seo_result  # Kisa erisim icin

        if not seo_result['passed']:
            report['overall_passed'] = False
            report['total_issues'] += len(seo_result['issues'])

        # 3. Fiyat kontrolu
        original_price = original.get('price', 0)
        suggested_price = optimized.get('suggested_price', 0)
        source_platform = original.get('source', 'unknown')

        price_result = self.check_price_validity(original_price, suggested_price, source_platform)
        report['checks']['price'] = price_result

        if not price_result['passed']:
            report['overall_passed'] = False
            report['total_issues'] += len(price_result['issues'])

        # Log kaydet
        self.log("INFO", f"Kalite kontrolu tamamlandi: {report['product_id']}", {
            'passed': report['overall_passed'],
            'issues': report['total_issues']
        })

        return report

    def send_quality_report(self, report):
        """Kalite raporunu Telegram'a gonder"""
        product_id = report.get('product_id', 'unknown')
        passed = report.get('overall_passed', False)
        issues = report.get('total_issues', 0)

        status = "GECTI" if passed else "BASARISIZ"
        emoji = "✅" if passed else "⚠️"

        message = (
            f"*KALITE KONTROL RAPORU*\n\n"
            f"ID: `{product_id}`\n"
            f"Durum: {emoji} {status}\n"
            f"Sorun sayisi: {issues}\n\n"
        )

        # Detaylar
        if not passed:
            message += "*Sorunlar:*\n"

            for check_name, check_result in report.get('checks', {}).items():
                if isinstance(check_result, list):
                    for item in check_result:
                        if not item.get('passed', True):
                            for issue in item.get('issues', []):
                                message += f"- {issue}\n"
                elif isinstance(check_result, dict):
                    if not check_result.get('passed', True):
                        for issue in check_result.get('issues', []):
                            message += f"- {issue}\n"

        # Telegram'a gonder
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            data = {
                'chat_id': self.system_chat,
                'text': message,
                'parse_mode': 'Markdown'
            }
            requests.post(url, json=data, timeout=10)
        except Exception as e:
            self.log("ERROR", f"Telegram rapor gonderim hatasi: {e}")


# Test
if __name__ == "__main__":
    qc = QualityController()
    print("Quality Controller baslatildi")

    # Test raporu
    test_product = {
        'id': 'TEST-001',
        'original': {
            'title': 'Nike Ayakkabi',
            'description': 'Guzel ayakkabi',
            'price': 50,
            'source': 'kleinanzeigen'
        },
        'optimized': {
            'title': 'Nike Air Max Sneaker Gr. 42 Herren Sportschuhe',
            'description': 'Hochwertige Nike Air Max Sneaker in Größe 42. Sehr guter Zustand, kaum getragen. Originale Verpackung vorhanden.',
            'suggested_price': 50
        },
        'images': []
    }

    report = qc.run_full_quality_check(test_product)
    print(f"\nRapor: {json.dumps(report, indent=2)}")
