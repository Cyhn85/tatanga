#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TATANGA - CAPTCHA & Cookie Consent Handler
Akilli tespit ve insan onay sistemi
"""

import os
import sys
import json
import time
import random
import asyncio
import tempfile
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

import requests
from shared.config.credentials import TELEGRAM

class CaptchaHandler:
    """CAPTCHA ve Cookie Consent tespit ve onay sistemi"""

    def __init__(self, driver=None, logger=None):
        self.driver = driver
        self.logger = logger
        self.bot_token = TELEGRAM['bot_token']
        self.chat_id = TELEGRAM['channels']['captcha_approval']
        self.learning_file = Path(__file__).parent / "captcha_learning.json"
        self.load_learning_data()

        # Platform-spesifik selectorler
        self.platform_selectors = {
            'kleinanzeigen': {
                'cookie_accept': [
                    "button#gdpr-banner-accept",
                    "[data-testid='gdpr-banner-accept']",
                    "#gdpr-banner-accept",
                    "button[class*='gdpr'][class*='accept']",
                    ".sc-1out364-0.cxizOH",  # Kleinanzeigen specific
                ],
                'cookie_decline': [
                    "button#gdpr-banner-decline",
                    "[data-testid='gdpr-banner-decline']",
                ],
                'cookie_settings': [
                    "button#gdpr-banner-settings",
                    "[data-testid='gdpr-banner-settings']",
                ],
                'cookie_modal': [
                    "#gdpr-banner",
                    "[data-testid='gdpr-banner']",
                    ".ReactModal__Content",
                ],
                'captcha': [
                    ".g-recaptcha",
                    "#recaptcha",
                    "iframe[src*='recaptcha']",
                    ".h-captcha",
                    "iframe[src*='hcaptcha']",
                ],
            },
            'vinted': {
                'cookie_accept': [
                    "#onetrust-accept-btn-handler",
                    "button[id*='accept']",
                    ".c-button--primary[data-testid*='cookie']",
                ],
                'cookie_decline': [
                    "#onetrust-reject-all-handler",
                ],
                'cookie_settings': [
                    "#onetrust-pc-btn-handler",
                ],
                'cookie_modal': [
                    "#onetrust-banner-sdk",
                    ".onetrust-pc-dark-filter",
                ],
                'captcha': [
                    ".g-recaptcha",
                    "iframe[src*='recaptcha']",
                ],
            },
            'ebay': {
                'cookie_accept': [
                    "#gdpr-banner-accept",
                    "button#scroll-to-top-btn",
                    "#gdpr-banner .gdpr-button--primary",
                ],
                'cookie_decline': [
                    "#gdpr-banner-decline",
                ],
                'cookie_settings': [
                    "#gdpr-banner-settings",
                ],
                'cookie_modal': [
                    "#gdpr-banner",
                    ".gdpr-banner__content",
                ],
                'captcha': [
                    ".g-recaptcha",
                    "#captcha-box",
                    "iframe[src*='recaptcha']",
                ],
            },
            'willhaben': {
                'cookie_accept': [
                    "#didomi-notice-agree-button",
                    "button[class*='agree']",
                    ".didomi-continue-without-agreeing",
                ],
                'cookie_decline': [
                    "#didomi-notice-disagree-button",
                ],
                'cookie_settings': [
                    "#didomi-notice-learn-more-button",
                ],
                'cookie_modal': [
                    "#didomi-host",
                    ".didomi-popup-container",
                ],
                'captcha': [
                    ".g-recaptcha",
                    "iframe[src*='recaptcha']",
                ],
            },
            'generic': {
                'cookie_accept': [
                    "button[class*='accept']",
                    "button[class*='agree']",
                    "button[id*='accept']",
                    "button[title*='akzeptieren']",
                    "button[title*='Akzeptieren']",
                    ".cmpboxbtnyes",
                    "a[class*='accept']",
                ],
                'cookie_decline': [
                    "button[class*='decline']",
                    "button[class*='reject']",
                    "button[id*='decline']",
                ],
                'cookie_settings': [
                    "button[class*='settings']",
                    "button[class*='preferences']",
                    "a[class*='settings']",
                ],
                'cookie_modal': [
                    "[class*='cookie']",
                    "[class*='consent']",
                    "[class*='gdpr']",
                    "[id*='cookie']",
                    "[id*='consent']",
                ],
                'captcha': [
                    ".g-recaptcha",
                    ".h-captcha",
                    "iframe[src*='recaptcha']",
                    "iframe[src*='hcaptcha']",
                    "#captcha",
                ],
            },
        }

    def log(self, level, message):
        """Log mesaji"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_message = f"[{timestamp}] [{level}] {message}"
        print(log_message)
        if self.logger:
            self.logger(level, message)

    def load_learning_data(self):
        """Ogrenme verisini yukle"""
        try:
            if self.learning_file.exists():
                with open(self.learning_file, 'r', encoding='utf-8') as f:
                    self.learning_data = json.load(f)
            else:
                self.learning_data = {
                    'successful_selectors': {},
                    'failed_selectors': {},
                    'user_actions': [],
                }
        except Exception as e:
            self.log("WARNING", f"Ogrenme verisi yuklenemedi: {e}")
            self.learning_data = {
                'successful_selectors': {},
                'failed_selectors': {},
                'user_actions': [],
            }

    def save_learning_data(self):
        """Ogrenme verisini kaydet"""
        try:
            with open(self.learning_file, 'w', encoding='utf-8') as f:
                json.dump(self.learning_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.log("ERROR", f"Ogrenme verisi kaydedilemedi: {e}")

    def human_like_delay(self, min_sec=0.5, max_sec=1.5):
        """Insan gibi bekleme"""
        time.sleep(random.uniform(min_sec, max_sec))

    def detect_platform(self, url):
        """URL'den platform tespit et"""
        url_lower = url.lower()
        if 'kleinanzeigen' in url_lower:
            return 'kleinanzeigen'
        elif 'vinted' in url_lower:
            return 'vinted'
        elif 'ebay' in url_lower:
            return 'ebay'
        elif 'willhaben' in url_lower:
            return 'willhaben'
        return 'generic'

    def detect_cookie_popup(self, platform=None):
        """Cookie popup tespit et"""
        if not self.driver:
            return None

        if not platform:
            platform = self.detect_platform(self.driver.current_url)

        selectors = self.platform_selectors.get(platform, self.platform_selectors['generic'])

        # Modal/banner kontrolu
        for selector in selectors.get('cookie_modal', []):
            try:
                element = self.driver.find_element(By.CSS_SELECTOR, selector)
                if element.is_displayed():
                    self.log("INFO", f"Cookie popup tespit edildi: {selector}")
                    return {
                        'type': 'cookie',
                        'platform': platform,
                        'modal_selector': selector,
                    }
            except:
                continue

        # Generic modal kontrolu
        for selector in self.platform_selectors['generic'].get('cookie_modal', []):
            try:
                element = self.driver.find_element(By.CSS_SELECTOR, selector)
                if element.is_displayed():
                    self.log("INFO", f"Generic cookie popup tespit edildi: {selector}")
                    return {
                        'type': 'cookie',
                        'platform': 'generic',
                        'modal_selector': selector,
                    }
            except:
                continue

        return None

    def detect_captcha(self, platform=None):
        """CAPTCHA tespit et"""
        if not self.driver:
            return None

        if not platform:
            platform = self.detect_platform(self.driver.current_url)

        selectors = self.platform_selectors.get(platform, self.platform_selectors['generic'])

        # CAPTCHA kontrolu
        for selector in selectors.get('captcha', []):
            try:
                element = self.driver.find_element(By.CSS_SELECTOR, selector)
                if element.is_displayed():
                    self.log("WARNING", f"CAPTCHA tespit edildi: {selector}")
                    return {
                        'type': 'captcha',
                        'platform': platform,
                        'captcha_selector': selector,
                    }
            except:
                continue

        # Generic captcha kontrolu
        for selector in self.platform_selectors['generic'].get('captcha', []):
            try:
                element = self.driver.find_element(By.CSS_SELECTOR, selector)
                if element.is_displayed():
                    self.log("WARNING", f"Generic CAPTCHA tespit edildi: {selector}")
                    return {
                        'type': 'captcha',
                        'platform': 'generic',
                        'captcha_selector': selector,
                    }
            except:
                continue

        return None

    def take_screenshot(self):
        """Ekran goruntusu al"""
        if not self.driver:
            return None

        try:
            # Gecici dosya olustur
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
                screenshot_path = f.name

            self.driver.save_screenshot(screenshot_path)
            self.log("INFO", f"Screenshot alindi: {screenshot_path}")
            return screenshot_path

        except Exception as e:
            self.log("ERROR", f"Screenshot alinamadi: {e}")
            return None

    def send_telegram_photo(self, photo_path, caption, reply_markup=None):
        """Telegram'a foto gonder"""
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendPhoto"

            with open(photo_path, 'rb') as photo:
                data = {
                    'chat_id': self.chat_id,
                    'caption': caption,
                    'parse_mode': 'Markdown',
                }

                if reply_markup:
                    data['reply_markup'] = json.dumps(reply_markup)

                files = {'photo': photo}
                response = requests.post(url, data=data, files=files)

                if response.status_code == 200:
                    result = response.json()
                    self.log("INFO", "Telegram'a foto gonderildi")
                    return result.get('result', {}).get('message_id')
                else:
                    self.log("ERROR", f"Telegram foto gonderilemedi: {response.text}")
                    return None

        except Exception as e:
            self.log("ERROR", f"Telegram foto hatasi: {e}")
            return None

    def send_telegram_message(self, message, reply_markup=None):
        """Telegram'a mesaj gonder"""
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"

            data = {
                'chat_id': self.chat_id,
                'text': message,
                'parse_mode': 'Markdown',
            }

            if reply_markup:
                data['reply_markup'] = json.dumps(reply_markup)

            response = requests.post(url, json=data)

            if response.status_code == 200:
                return response.json().get('result', {}).get('message_id')
            else:
                self.log("ERROR", f"Telegram mesaj gonderilemedi: {response.text}")
                return None

        except Exception as e:
            self.log("ERROR", f"Telegram mesaj hatasi: {e}")
            return None

    def request_human_approval(self, detection_result, auto_timeout=60):
        """Insan onayi iste"""
        if not detection_result:
            return None

        popup_type = detection_result.get('type', 'unknown')
        platform = detection_result.get('platform', 'generic')

        # Screenshot al
        screenshot_path = self.take_screenshot()

        # Mesaj olustur
        if popup_type == 'cookie':
            caption = (
                f"*CEREZ ONAYI GEREKLI*\n\n"
                f"Platform: {platform.upper()}\n"
                f"URL: {self.driver.current_url[:50]}...\n\n"
                f"Ne yapmami istersiniz?\n\n"
                f"_Otomatik kabul {auto_timeout} saniye sonra_"
            )

            # Inline keyboard
            reply_markup = {
                'inline_keyboard': [
                    [
                        {'text': 'Kabul Et', 'callback_data': f'cookie_accept_{platform}'},
                        {'text': 'Reddet', 'callback_data': f'cookie_decline_{platform}'},
                    ],
                    [
                        {'text': 'Ayarlar', 'callback_data': f'cookie_settings_{platform}'},
                        {'text': 'Atla', 'callback_data': 'cookie_skip'},
                    ],
                ]
            }

        elif popup_type == 'captcha':
            caption = (
                f"*CAPTCHA TESPIT EDILDI*\n\n"
                f"Platform: {platform.upper()}\n"
                f"URL: {self.driver.current_url[:50]}...\n\n"
                f"Lutfen manuel olarak cozerek 'Tamamlandi' butonuna basin.\n\n"
                f"_Bekleme suresi: {auto_timeout} saniye_"
            )

            reply_markup = {
                'inline_keyboard': [
                    [
                        {'text': 'Tamamlandi', 'callback_data': 'captcha_done'},
                        {'text': 'Atlat', 'callback_data': 'captcha_skip'},
                    ],
                    [
                        {'text': 'Yeniden Dene', 'callback_data': 'captcha_retry'},
                    ],
                ]
            }

        else:
            caption = (
                f"*BILINMEYEN POPUP*\n\n"
                f"Platform: {platform}\n"
                f"URL: {self.driver.current_url[:50]}...\n\n"
                f"Ne yapilmali?"
            )

            reply_markup = {
                'inline_keyboard': [
                    [
                        {'text': 'Devam Et', 'callback_data': 'unknown_continue'},
                        {'text': 'Durdur', 'callback_data': 'unknown_stop'},
                    ],
                ]
            }

        # Foto gonder
        if screenshot_path:
            message_id = self.send_telegram_photo(screenshot_path, caption, reply_markup)
            # Gecici dosyayi sil
            try:
                os.unlink(screenshot_path)
            except:
                pass
        else:
            message_id = self.send_telegram_message(caption, reply_markup)

        return message_id

    def auto_handle_cookie(self, platform=None, action='accept'):
        """Cookie popup'i otomatik isle"""
        if not self.driver:
            return False

        if not platform:
            platform = self.detect_platform(self.driver.current_url)

        selectors = self.platform_selectors.get(platform, self.platform_selectors['generic'])

        # Hangi action?
        if action == 'accept':
            selector_key = 'cookie_accept'
        elif action == 'decline':
            selector_key = 'cookie_decline'
        elif action == 'settings':
            selector_key = 'cookie_settings'
        else:
            return False

        # Ogrenilmis basarili selector'u once dene
        learned_key = f"{platform}_{selector_key}"
        if learned_key in self.learning_data.get('successful_selectors', {}):
            learned_selector = self.learning_data['successful_selectors'][learned_key]
            try:
                btn = self.driver.find_element(By.CSS_SELECTOR, learned_selector)
                if btn.is_displayed():
                    self.human_like_click(btn)
                    self.log("INFO", f"Ogrenilmis selector ile {action}: {learned_selector}")
                    return True
            except:
                pass

        # Platform-spesifik selectorleri dene
        for selector in selectors.get(selector_key, []):
            try:
                btn = self.driver.find_element(By.CSS_SELECTOR, selector)
                if btn.is_displayed():
                    self.human_like_click(btn)
                    self.log("INFO", f"Cookie {action} tiklandi: {selector}")

                    # Ogren
                    self.learning_data['successful_selectors'][learned_key] = selector
                    self.save_learning_data()

                    return True
            except:
                continue

        # Generic selectorleri dene
        for selector in self.platform_selectors['generic'].get(selector_key, []):
            try:
                btn = self.driver.find_element(By.CSS_SELECTOR, selector)
                if btn.is_displayed():
                    self.human_like_click(btn)
                    self.log("INFO", f"Generic cookie {action}: {selector}")
                    return True
            except:
                continue

        # JavaScript fallback
        try:
            if action == 'accept':
                result = self.driver.execute_script("""
                    var buttons = document.querySelectorAll('button, a');
                    for (var btn of buttons) {
                        var text = btn.textContent.toLowerCase();
                        if (text.includes('akzeptieren') || text.includes('accept') ||
                            text.includes('zustimmen') || text.includes('agree') ||
                            text.includes('alle akzeptieren') || text.includes('accept all')) {
                            btn.click();
                            return true;
                        }
                    }
                    return false;
                """)
                if result:
                    self.log("INFO", "JavaScript ile cookie kabul edildi")
                    return True
        except:
            pass

        self.log("WARNING", f"Cookie {action} bulunamadi")
        return False

    def human_like_click(self, element):
        """Insan gibi tikla"""
        try:
            actions = ActionChains(self.driver)

            # Elemana git
            actions.move_to_element(element)
            self.human_like_delay(0.2, 0.5)

            # Tikla
            actions.click(element)
            actions.perform()

            self.human_like_delay(0.5, 1.0)
            return True

        except Exception as e:
            self.log("ERROR", f"Human-like click hatasi: {e}")
            # Direkt tikla
            try:
                element.click()
                return True
            except:
                return False

    def human_like_scroll(self, pixels=300, direction='down'):
        """Insan gibi scroll"""
        if not self.driver:
            return

        try:
            if direction == 'down':
                self.driver.execute_script(f"window.scrollBy(0, {pixels});")
            elif direction == 'up':
                self.driver.execute_script(f"window.scrollBy(0, -{pixels});")

            self.human_like_delay(0.3, 0.7)

        except Exception as e:
            self.log("ERROR", f"Scroll hatasi: {e}")

    def human_like_type(self, element, text):
        """Insan gibi yaz"""
        try:
            element.clear()
            self.human_like_delay(0.2, 0.4)

            for char in text:
                element.send_keys(char)
                time.sleep(random.uniform(0.05, 0.15))

            return True

        except Exception as e:
            self.log("ERROR", f"Type hatasi: {e}")
            return False

    def detect_captcha_type(self):
        """
        CAPTCHA turunu tespit et

        Returns:
            dict: CAPTCHA bilgileri (type, provider, selector, iframe_src)
        """
        if not self.driver:
            return None

        captcha_types = {
            'recaptcha_v2': {
                'selectors': [
                    'iframe[src*="recaptcha"]',
                    '.g-recaptcha',
                    '#g-recaptcha',
                    'div[data-sitekey]',
                ],
                'identifier': 'recaptcha'
            },
            'recaptcha_v3': {
                'selectors': [
                    '.grecaptcha-badge',
                    'script[src*="recaptcha/api.js?render"]',
                ],
                'identifier': 'recaptcha-v3'
            },
            'hcaptcha': {
                'selectors': [
                    'iframe[src*="hcaptcha"]',
                    '.h-captcha',
                    '#h-captcha',
                    'div[data-hcaptcha-widget-id]',
                ],
                'identifier': 'hcaptcha'
            },
            'funcaptcha': {
                'selectors': [
                    'iframe[src*="funcaptcha"]',
                    '#arkose-iframe',
                    '.funcaptcha',
                ],
                'identifier': 'funcaptcha'
            },
            'cloudflare_turnstile': {
                'selectors': [
                    'iframe[src*="challenges.cloudflare"]',
                    '.cf-turnstile',
                    'div[data-sitekey][data-callback]',
                ],
                'identifier': 'turnstile'
            },
            'image_captcha': {
                'selectors': [
                    'img[src*="captcha"]',
                    '#captcha-image',
                    '.captcha-img',
                    'input[name="captcha"]',
                ],
                'identifier': 'image'
            },
            'text_captcha': {
                'selectors': [
                    '.text-captcha',
                    '#text-captcha',
                    'input[placeholder*="captcha" i]',
                ],
                'identifier': 'text'
            },
        }

        for captcha_name, captcha_info in captcha_types.items():
            for selector in captcha_info['selectors']:
                try:
                    element = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if element.is_displayed() or 'iframe' in selector:
                        # iframe src al
                        iframe_src = None
                        if element.tag_name == 'iframe':
                            iframe_src = element.get_attribute('src')

                        self.log("WARNING", f"CAPTCHA tespit edildi: {captcha_name}")
                        return {
                            'type': captcha_name,
                            'provider': captcha_info['identifier'],
                            'selector': selector,
                            'iframe_src': iframe_src,
                            'element': element,
                        }
                except:
                    continue

        return None

    def send_captcha_notification(self, captcha_info, screenshot_path=None):
        """
        CAPTCHA icin detayli Telegram bildirimi gonder

        Args:
            captcha_info: detect_captcha_type() sonucu
            screenshot_path: Ekran goruntusu yolu

        Returns:
            int: Message ID
        """
        if not captcha_info:
            return None

        captcha_type = captcha_info.get('type', 'unknown')
        provider = captcha_info.get('provider', 'unknown')

        # CAPTCHA turune gore ozel mesaj
        type_messages = {
            'recaptcha_v2': "reCAPTCHA v2 - Resim secimi gerekiyor",
            'recaptcha_v3': "reCAPTCHA v3 - Arka planda calisir, genellikle otomatik",
            'hcaptcha': "hCaptcha - Resim secimi gerekiyor",
            'funcaptcha': "FunCaptcha - Oyun bazli zorluk",
            'cloudflare_turnstile': "Cloudflare Turnstile - Genellikle otomatik",
            'image_captcha': "Resim CAPTCHA - Gosterilen metni girin",
            'text_captcha': "Metin CAPTCHA - Basit metin girisi",
        }

        type_desc = type_messages.get(captcha_type, "Bilinmeyen CAPTCHA turu")

        # Detayli caption
        caption = (
            f"*🔒 CAPTCHA TESPIT EDILDI*\n\n"
            f"*Tur:* {captcha_type}\n"
            f"*Saglayici:* {provider}\n"
            f"*Aciklama:* {type_desc}\n\n"
            f"*Platform:* {self.detect_platform(self.driver.current_url).upper()}\n"
            f"*URL:* {self.driver.current_url[:60]}...\n\n"
            f"_Lutfen manuel olarak cozun ve 'Tamamlandi' butonuna basin_"
        )

        # Inline keyboard - CAPTCHA turune gore
        if captcha_type in ['recaptcha_v3', 'cloudflare_turnstile']:
            # Otomatik cozulebilir
            reply_markup = {
                'inline_keyboard': [
                    [
                        {'text': '✅ Tamamlandi', 'callback_data': 'captcha_done'},
                        {'text': '🔄 Yenile', 'callback_data': 'captcha_refresh'},
                    ],
                    [
                        {'text': '⏳ Bekle (30sn)', 'callback_data': 'captcha_wait_30'},
                        {'text': '⏭️ Atla', 'callback_data': 'captcha_skip'},
                    ],
                ]
            }
        else:
            # Manuel cozum gerekli
            reply_markup = {
                'inline_keyboard': [
                    [
                        {'text': '✅ Cozdum', 'callback_data': 'captcha_done'},
                        {'text': '🔄 Yeni CAPTCHA', 'callback_data': 'captcha_new'},
                    ],
                    [
                        {'text': '❌ Cozemedim', 'callback_data': 'captcha_failed'},
                        {'text': '⏭️ Atla', 'callback_data': 'captcha_skip'},
                    ],
                    [
                        {'text': '📞 2Captcha ile Coz', 'callback_data': 'captcha_2captcha'},
                    ],
                ]
            }

        # Screenshot al veya kullan
        if not screenshot_path:
            screenshot_path = self.take_screenshot()

        if screenshot_path:
            message_id = self.send_telegram_photo(screenshot_path, caption, reply_markup)
            # Gecici dosyayi sil
            try:
                if 'temp' in screenshot_path.lower():
                    os.unlink(screenshot_path)
            except:
                pass
        else:
            message_id = self.send_telegram_message(caption, reply_markup)

        return message_id

    def send_error_notification(self, error_type, error_message, screenshot_path=None):
        """
        Hata bildirimi gonder

        Args:
            error_type: Hata turu (login_failed, timeout, element_not_found, etc.)
            error_message: Hata mesaji
            screenshot_path: Ekran goruntusu yolu
        """
        error_icons = {
            'login_failed': '🔐',
            'timeout': '⏱️',
            'element_not_found': '🔍',
            'network_error': '🌐',
            'blocked': '🚫',
            'rate_limit': '⚡',
            'unknown': '❓',
        }

        icon = error_icons.get(error_type, '⚠️')

        caption = (
            f"*{icon} HATA BILDIRIMI*\n\n"
            f"*Tur:* {error_type}\n"
            f"*Mesaj:* {error_message[:200]}\n\n"
            f"*Platform:* {self.detect_platform(self.driver.current_url).upper() if self.driver else 'N/A'}\n"
            f"*Zaman:* {datetime.now().strftime('%H:%M:%S')}\n\n"
            f"_Ne yapilmali?_"
        )

        reply_markup = {
            'inline_keyboard': [
                [
                    {'text': '🔄 Yeniden Dene', 'callback_data': f'error_retry_{error_type}'},
                    {'text': '⏭️ Atla', 'callback_data': f'error_skip_{error_type}'},
                ],
                [
                    {'text': '🛑 Durdur', 'callback_data': 'error_stop'},
                ],
            ]
        }

        if not screenshot_path and self.driver:
            screenshot_path = self.take_screenshot()

        if screenshot_path:
            return self.send_telegram_photo(screenshot_path, caption, reply_markup)
        else:
            return self.send_telegram_message(caption, reply_markup)

    def check_and_handle(self, platform=None, auto_accept=True, request_approval=True):
        """
        Popup kontrolu ve islem

        Args:
            platform: Platform adi (otomatik tespit edilir)
            auto_accept: True ise otomatik kabul et
            request_approval: True ise Telegram'dan onay iste

        Returns:
            'handled': Popup islendi
            'skipped': Popup atlandi
            'waiting': Kullanici onayi bekleniyor
            'none': Popup yok
        """
        if not self.driver:
            return 'none'

        if not platform:
            platform = self.detect_platform(self.driver.current_url)

        # Cookie popup kontrolu
        cookie_popup = self.detect_cookie_popup(platform)
        if cookie_popup:
            if auto_accept:
                success = self.auto_handle_cookie(platform, 'accept')
                if success:
                    self.human_like_delay(1, 2)
                    return 'handled'

            if request_approval:
                self.request_human_approval(cookie_popup)
                return 'waiting'

            return 'skipped'

        # CAPTCHA kontrolu
        captcha = self.detect_captcha(platform)
        if captcha:
            if request_approval:
                self.request_human_approval(captcha)
                return 'waiting'
            return 'skipped'

        return 'none'

    def wait_for_page_load(self, timeout=10):
        """Sayfa yuklenene kadar bekle"""
        if not self.driver:
            return

        try:
            WebDriverWait(self.driver, timeout).until(
                lambda d: d.execute_script('return document.readyState') == 'complete'
            )
        except:
            pass


# Test
if __name__ == "__main__":
    handler = CaptchaHandler()
    print("CAPTCHA Handler baslatildi")
    print(f"Telegram grubu: {handler.chat_id}")
    print(f"Platform sayisi: {len(handler.platform_selectors)}")

    # Test mesaji gonder
    handler.send_telegram_message(
        "*CAPTCHA Handler Test*\n\n"
        "Sistem basariyla baslatildi.\n"
        "Cookie ve CAPTCHA tespiti aktif."
    )
