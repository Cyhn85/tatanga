"""
VIDEOCU v1 - Web Scraper Module
Instagram ve Google Trends için Selenium tabanlı scraper
Undetected ChromeDriver kullanarak bot detection'ı bypass eder
"""

import os
import time
import json
import logging
import re
from datetime import datetime
from typing import List, Dict, Optional
from fake_useragent import UserAgent

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

logger = logging.getLogger(__name__)


class WebScraper:
    """Selenium tabanlı web scraper"""

    def __init__(self, headless: bool = True):
        self.headless = headless
        self.driver = None
        self.ua = UserAgent()

    def _get_driver(self):
        """Undetected ChromeDriver instance al"""
        if self.driver is None:
            options = uc.ChromeOptions()

            if self.headless:
                options.add_argument('--headless=new')

            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-gpu')
            options.add_argument('--window-size=1920,1080')
            options.add_argument(f'--user-agent={self.ua.random}')
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_argument('--lang=de-DE')

            # Performance optimizations
            options.add_argument('--disable-extensions')
            options.add_argument('--disable-infobars')

            self.driver = uc.Chrome(options=options, version_main=131)

        return self.driver

    def close(self):
        """Driver'ı kapat"""
        if self.driver:
            self.driver.quit()
            self.driver = None

    def scrape_google_trends_germany(self, limit: int = 20) -> List[Dict]:
        """
        Google Trends Germany Daily Trends sayfasını scrape et

        Args:
            limit: Maksimum trend sayısı

        Returns:
            Trend listesi
        """
        try:
            logger.info("Scraping Google Trends Germany...")
            driver = self._get_driver()

            # Google Trends Daily Trends sayfası
            url = "https://trends.google.de/trending?geo=DE&hours=24"
            driver.get(url)

            # Sayfanın yüklenmesini bekle
            time.sleep(3)

            # Cookie consent varsa kabul et
            try:
                consent_button = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Alle akzeptieren') or contains(text(), 'Accept all')]"))
                )
                consent_button.click()
                time.sleep(1)
            except TimeoutException:
                pass

            # Trending topics'i al
            trends = []

            # Trend kartlarını bul
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "[class*='trending']"))
                )

                # Farklı selector'ları dene
                selectors = [
                    "div[class*='feed-item']",
                    "div[class*='trending-item']",
                    "md-list-item",
                    ".feed-item",
                    "[data-testid='trend-card']"
                ]

                trend_elements = []
                for selector in selectors:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        trend_elements = elements[:limit]
                        break

                if not trend_elements:
                    # Alternatif: Tüm metin içeriklerini al
                    page_source = driver.page_source
                    # Basit regex ile trend'leri çıkar
                    # Bu kısım Google Trends'in HTML yapısına göre ayarlanmalı

            except TimeoutException:
                logger.warning("Could not find trend elements, trying alternative method")

            # Alternatif: RSS feed veya API endpoint
            if not trends:
                trends = self._scrape_trends_via_rss()

            logger.info(f"Found {len(trends)} trends from Google Trends")
            return trends

        except Exception as e:
            logger.error(f"Google Trends scraping error: {e}")
            return []

    def _scrape_trends_via_rss(self) -> List[Dict]:
        """Google Trends RSS feed üzerinden scrape et"""
        import requests

        try:
            # Google Trends RSS feed
            rss_url = "https://trends.google.de/trending/rss?geo=DE"

            response = requests.get(rss_url, headers={
                'User-Agent': self.ua.random,
                'Accept-Language': 'de-DE,de;q=0.9'
            }, timeout=10)

            if response.status_code == 200:
                # RSS XML'i parse et
                from xml.etree import ElementTree as ET
                root = ET.fromstring(response.content)

                trends = []
                for i, item in enumerate(root.findall('.//item')):
                    title = item.find('title')
                    traffic = item.find('{https://trends.google.de/trends/trendingsearches/daily}approx_traffic')

                    if title is not None:
                        trend = {
                            'keyword': title.text,
                            'rank': i + 1,
                            'region': 'DE',
                            'score': self._parse_traffic(traffic.text if traffic is not None else ''),
                            'source': 'google_trends_rss',
                            'discovered_at': datetime.now().isoformat()
                        }
                        trends.append(trend)

                return trends

        except Exception as e:
            logger.error(f"RSS scraping error: {e}")

        return []

    def _parse_traffic(self, traffic_str: str) -> int:
        """Traffic string'ini sayıya çevir (örn: '100K+' -> 100000)"""
        if not traffic_str:
            return 0

        traffic_str = traffic_str.replace('+', '').replace(',', '').strip()

        multipliers = {
            'K': 1000,
            'M': 1000000,
            'B': 1000000000
        }

        for suffix, multiplier in multipliers.items():
            if suffix in traffic_str.upper():
                try:
                    num = float(traffic_str.upper().replace(suffix, ''))
                    return int(num * multiplier)
                except ValueError:
                    pass

        try:
            return int(traffic_str)
        except ValueError:
            return 0

    def scrape_instagram_explore(self, hashtags: List[str] = None, limit: int = 20) -> List[Dict]:
        """
        Instagram Explore/Reels sayfasını scrape et

        Args:
            hashtags: Aranacak hashtag'ler (opsiyonel)
            limit: Maksimum reel sayısı

        Returns:
            Reel listesi
        """
        if hashtags is None:
            hashtags = ['trending', 'viral', 'deutschland', 'fyp']

        try:
            logger.info(f"Scraping Instagram for hashtags: {hashtags}")
            driver = self._get_driver()

            all_reels = []

            for hashtag in hashtags:
                try:
                    # Instagram hashtag sayfası (login gerekmez)
                    url = f"https://www.instagram.com/explore/tags/{hashtag}/"
                    driver.get(url)
                    time.sleep(3)

                    # Cookie consent
                    try:
                        consent_button = driver.find_element(By.XPATH, "//button[contains(text(), 'Allow')]")
                        consent_button.click()
                        time.sleep(1)
                    except NoSuchElementException:
                        pass

                    # Login popup'ı kapat
                    try:
                        close_button = driver.find_element(By.XPATH, "//button[contains(@class, 'close') or @aria-label='Close']")
                        close_button.click()
                        time.sleep(1)
                    except NoSuchElementException:
                        pass

                    # Scroll yaparak daha fazla içerik yükle
                    for _ in range(3):
                        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                        time.sleep(2)

                    # Post linklerini al
                    post_links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/reel/'], a[href*='/p/']")

                    for link in post_links[:limit // len(hashtags)]:
                        try:
                            href = link.get_attribute('href')
                            if href and '/reel/' in href or '/p/' in href:
                                # Post ID'yi çıkar
                                post_id = href.split('/')[-2]

                                # Thumbnail al
                                img = link.find_element(By.TAG_NAME, 'img')
                                thumbnail = img.get_attribute('src') if img else ''

                                reel = {
                                    'platform': 'instagram',
                                    'media_id': post_id,
                                    'url': href,
                                    'thumbnail': thumbnail,
                                    'hashtag': hashtag,
                                    'region': 'DE',
                                    'source': 'instagram_scraper',
                                    'discovered_at': datetime.now().isoformat(),
                                    'score': 0  # Score'u ayrı hesapla
                                }
                                all_reels.append(reel)

                        except Exception as e:
                            logger.warning(f"Error processing post: {e}")
                            continue

                    time.sleep(2)  # Rate limiting

                except Exception as e:
                    logger.warning(f"Error scraping hashtag #{hashtag}: {e}")
                    continue

            # Duplikatları kaldır
            unique_reels = {reel['media_id']: reel for reel in all_reels}.values()

            logger.info(f"Found {len(list(unique_reels))} unique Instagram reels")
            return list(unique_reels)

        except Exception as e:
            logger.error(f"Instagram scraping error: {e}")
            return []

    def scrape_instagram_with_login(self, username: str, password: str,
                                    hashtags: List[str] = None, limit: int = 20) -> List[Dict]:
        """
        Instagram'a login olup scrape et (daha fazla veri)

        Args:
            username: Instagram kullanıcı adı/email
            password: Instagram şifresi
            hashtags: Aranacak hashtag'ler
            limit: Maksimum reel sayısı

        Returns:
            Reel listesi
        """
        if hashtags is None:
            hashtags = ['trending', 'viral', 'deutschland']

        try:
            logger.info("Logging into Instagram...")
            driver = self._get_driver()

            # Login sayfasına git
            driver.get("https://www.instagram.com/accounts/login/")
            time.sleep(3)

            # Cookie consent
            try:
                consent_button = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Allow') or contains(text(), 'Alle')]"))
                )
                consent_button.click()
                time.sleep(1)
            except TimeoutException:
                pass

            # Login formu doldur
            try:
                username_input = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.NAME, "username"))
                )
                password_input = driver.find_element(By.NAME, "password")

                username_input.clear()
                username_input.send_keys(username)
                time.sleep(0.5)

                password_input.clear()
                password_input.send_keys(password)
                time.sleep(0.5)

                # Login butonuna tıkla
                login_button = driver.find_element(By.XPATH, "//button[@type='submit']")
                login_button.click()

                time.sleep(5)

                # Login başarılı mı kontrol et
                if "challenge" in driver.current_url or "two_factor" in driver.current_url:
                    logger.warning("Instagram 2FA or challenge required")
                    return self.scrape_instagram_explore(hashtags, limit)

                logger.info("Instagram login successful")

            except Exception as e:
                logger.error(f"Login failed: {e}")
                return self.scrape_instagram_explore(hashtags, limit)

            # Artık hashtag'leri scrape et
            return self.scrape_instagram_explore(hashtags, limit)

        except Exception as e:
            logger.error(f"Instagram login scraping error: {e}")
            return []


class InstagramScraper(WebScraper):
    """Instagram için özelleştirilmiş scraper"""

    def get_trending_reels(self, limit: int = 30) -> List[Dict]:
        """Instagram Reels trending içerikleri al"""
        hashtags = [
            'reelsdeutschland',
            'deutschland',
            'viral',
            'trending',
            'fyp',
            'foryou'
        ]
        return self.scrape_instagram_explore(hashtags, limit)


class GoogleTrendsScraper(WebScraper):
    """Google Trends için özelleştirilmiş scraper"""

    def get_daily_trends(self, limit: int = 20) -> List[Dict]:
        """Günlük trending aramalar"""
        # Önce RSS'i dene (daha hızlı)
        trends = self._scrape_trends_via_rss()

        if not trends:
            # RSS başarısız olursa browser scraping
            trends = self.scrape_google_trends_germany(limit)

        return trends[:limit]


# Test
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Google Trends test
    print("\n" + "="*60)
    print("GOOGLE TRENDS SCRAPER TEST")
    print("="*60)

    gt_scraper = GoogleTrendsScraper(headless=True)
    trends = gt_scraper.get_daily_trends(limit=10)

    for trend in trends:
        print(f"{trend['rank']}. {trend['keyword']} (Score: {trend['score']:,})")

    gt_scraper.close()

    # Instagram test
    print("\n" + "="*60)
    print("INSTAGRAM SCRAPER TEST")
    print("="*60)

    ig_scraper = InstagramScraper(headless=True)
    reels = ig_scraper.get_trending_reels(limit=10)

    for reel in reels:
        print(f"- {reel['url']} (#{reel.get('hashtag', 'N/A')})")

    ig_scraper.close()
