#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TATANGA - Proxy ve IP Guvenlik Yonetimi
Ban riskini minimize etmek icin proxy rotasyonu ve guvenlik
"""

import os
import sys
import json
import time
import random
import requests
from pathlib import Path
from datetime import datetime, timedelta

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.config.credentials import PROXY, HETZNER

# ============================================
# CONFIGURATION
# ============================================
LOGS_DIR = Path(__file__).parent.parent.parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)

# IP turleri ve risk seviyeleri
IP_TYPES = {
    "home": {
        "risk_level": "HIGH",
        "use_for": [],  # Hicbir sey icin kullanma
        "description": "Ev IP - ASLA kullanilmamali"
    },
    "hetzner": {
        "risk_level": "LOW",
        "use_for": ["scraping", "api_calls", "bulk_operations"],
        "description": "Hetzner VPS - Tum riskli islemler icin"
    },
    "tailscale": {
        "risk_level": "MEDIUM",
        "use_for": ["light_scraping", "api_calls"],
        "description": "Tailscale VPN - Orta riskli islemler"
    },
    "rotating_proxy": {
        "risk_level": "LOW",
        "use_for": ["scraping", "account_actions"],
        "description": "Rotating proxy - Yogun tarama icin"
    }
}

# Platform-spesifik guvenlik ayarlari
PLATFORM_SECURITY = {
    "vinted": {
        "min_delay": 3,
        "max_delay": 8,
        "requests_per_minute": 10,
        "use_proxy": True,
        "rotate_user_agent": True,
        "clear_cookies_after": 50,
        "ban_indicators": ["403", "429", "captcha", "blocked"]
    },
    "kleinanzeigen": {
        "min_delay": 5,
        "max_delay": 15,
        "requests_per_minute": 6,
        "use_proxy": True,
        "rotate_user_agent": True,
        "clear_cookies_after": 30,
        "ban_indicators": ["403", "captcha", "robot"]
    },
    "ebay": {
        "min_delay": 1,
        "max_delay": 3,
        "requests_per_minute": 20,
        "use_proxy": False,  # API kullan
        "rotate_user_agent": False,
        "ban_indicators": ["rate limit", "unauthorized"]
    },
    "willhaben": {
        "min_delay": 4,
        "max_delay": 10,
        "requests_per_minute": 8,
        "use_proxy": True,
        "rotate_user_agent": True,
        "ban_indicators": ["403", "captcha"]
    },
    "shpock": {
        "min_delay": 3,
        "max_delay": 8,
        "requests_per_minute": 10,
        "use_proxy": True,
        "rotate_user_agent": True,
        "ban_indicators": ["403", "blocked"]
    }
}

# User agent listesi
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
]

# ============================================
# PROXY MANAGER
# ============================================
class ProxyManager:
    """Proxy ve IP guvenlik yoneticisi"""

    def __init__(self):
        self.current_proxy = None
        self.request_counts = {}
        self.last_request_time = {}
        self.banned_ips = set()
        self.load_state()

    def load_state(self):
        """Onceki durumu yukle"""
        state_file = LOGS_DIR / "proxy_state.json"
        if state_file.exists():
            try:
                with open(state_file, 'r') as f:
                    state = json.load(f)
                    self.banned_ips = set(state.get('banned_ips', []))
                    self.request_counts = state.get('request_counts', {})
            except:
                pass

    def save_state(self):
        """Durumu kaydet"""
        state_file = LOGS_DIR / "proxy_state.json"
        state = {
            "banned_ips": list(self.banned_ips),
            "request_counts": self.request_counts,
            "last_updated": datetime.now().isoformat()
        }
        with open(state_file, 'w') as f:
            json.dump(state, f, indent=2)

    def get_proxy_for_platform(self, platform):
        """
        Platform icin uygun proxy sec

        Args:
            platform: Platform adi (vinted, kleinanzeigen, etc.)

        Returns:
            dict: Proxy ayarlari
        """
        security = PLATFORM_SECURITY.get(platform, {})

        if not security.get('use_proxy', True):
            return None

        # Hetzner sunucusu varsa onu kullan
        if HETZNER.get('ip'):
            return {
                "type": "hetzner",
                "http": f"http://{HETZNER['ip']}:8080",
                "https": f"http://{HETZNER['ip']}:8080"
            }

        # Tailscale VPN
        if PROXY.get('tailscale', {}).get('http'):
            return {
                "type": "tailscale",
                "http": PROXY['tailscale']['http'],
                "https": PROXY['tailscale']['http']
            }

        # Ucretsiz rotating proxy servisleri
        free_proxies = self.get_free_rotating_proxies()
        if free_proxies:
            proxy = random.choice(free_proxies)
            return {
                "type": "rotating_free",
                "http": proxy,
                "https": proxy
            }

        return None

    def get_free_rotating_proxies(self):
        """
        Ucretsiz proxy listesi al
        Birden fazla kaynaktan ceker
        """
        proxies = []

        # Proxy kaynaklari
        sources = [
            "https://api.proxyscrape.com/v2/?request=getproxies&protocol=http&timeout=10000&country=DE&ssl=all&anonymity=all",
            "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
            "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt"
        ]

        for source in sources:
            try:
                resp = requests.get(source, timeout=5)
                if resp.status_code == 200:
                    for line in resp.text.strip().split('\n'):
                        if ':' in line:
                            proxies.append(f"http://{line.strip()}")
            except:
                continue

        # Benzersiz ve calisan proxyleri filtrele
        return list(set(proxies))[:50]

    def get_random_user_agent(self):
        """Rastgele user agent sec"""
        return random.choice(USER_AGENTS)

    def get_delay(self, platform):
        """
        Platform icin bekleme suresi

        Args:
            platform: Platform adi

        Returns:
            float: Bekleme suresi (saniye)
        """
        security = PLATFORM_SECURITY.get(platform, {})
        min_delay = security.get('min_delay', 3)
        max_delay = security.get('max_delay', 8)

        # Rastgele gecikme + jitter
        delay = random.uniform(min_delay, max_delay)
        jitter = random.uniform(0, 1)

        return delay + jitter

    def check_rate_limit(self, platform):
        """
        Rate limit kontrolu

        Args:
            platform: Platform adi

        Returns:
            bool: Istek yapilabilir mi
        """
        security = PLATFORM_SECURITY.get(platform, {})
        max_rpm = security.get('requests_per_minute', 10)

        now = datetime.now()
        key = f"{platform}_{now.strftime('%Y%m%d%H%M')}"

        count = self.request_counts.get(key, 0)

        if count >= max_rpm:
            return False

        self.request_counts[key] = count + 1
        return True

    def wait_for_rate_limit(self, platform):
        """
        Rate limit icin bekle

        Args:
            platform: Platform adi
        """
        while not self.check_rate_limit(platform):
            print(f"    [!] Rate limit, bekleniyor...")
            time.sleep(10)

    def check_ban_indicators(self, platform, response_text):
        """
        Ban gostergelerini kontrol et

        Args:
            platform: Platform adi
            response_text: Yanit metni

        Returns:
            bool: Ban tespit edildi mi
        """
        security = PLATFORM_SECURITY.get(platform, {})
        indicators = security.get('ban_indicators', [])

        response_lower = response_text.lower()

        for indicator in indicators:
            if indicator.lower() in response_lower:
                return True

        return False

    def report_ban(self, platform, proxy_info):
        """
        Ban raporla ve proxy'yi kara listeye al

        Args:
            platform: Platform adi
            proxy_info: Kullanilan proxy bilgisi
        """
        if proxy_info:
            self.banned_ips.add(proxy_info.get('http', ''))

        # Log
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "platform": platform,
            "proxy": proxy_info,
            "action": "banned"
        }

        log_file = LOGS_DIR / "ban_log.jsonl"
        with open(log_file, 'a') as f:
            f.write(json.dumps(log_entry) + "\n")

        self.save_state()

        print(f"[!] BAN tespit edildi: {platform}")

# ============================================
# SAFE REQUEST WRAPPER
# ============================================
class SafeRequester:
    """Guvenli istek yapici"""

    def __init__(self, platform):
        self.platform = platform
        self.proxy_manager = ProxyManager()
        self.session = requests.Session()
        self.request_count = 0

    def setup_session(self):
        """Session'i hazirla"""
        # User agent
        self.session.headers['User-Agent'] = self.proxy_manager.get_random_user_agent()

        # Proxy
        proxy = self.proxy_manager.get_proxy_for_platform(self.platform)
        if proxy:
            self.session.proxies = {
                'http': proxy['http'],
                'https': proxy.get('https', proxy['http'])
            }
            print(f"    [*] Proxy: {proxy['type']}")

        # Diger headerlar
        self.session.headers.update({
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })

    def get(self, url, **kwargs):
        """
        Guvenli GET istegi

        Args:
            url: Istek URL'i
            **kwargs: Ek parametreler

        Returns:
            Response veya None
        """
        # Rate limit kontrolu
        self.proxy_manager.wait_for_rate_limit(self.platform)

        # Gecikme
        delay = self.proxy_manager.get_delay(self.platform)
        time.sleep(delay)

        try:
            response = self.session.get(url, timeout=30, **kwargs)

            # Ban kontrolu
            if self.proxy_manager.check_ban_indicators(self.platform, response.text):
                proxy = self.proxy_manager.get_proxy_for_platform(self.platform)
                self.proxy_manager.report_ban(self.platform, proxy)

                # Proxy degistir ve tekrar dene
                self.setup_session()
                time.sleep(30)  # Uzun bekleme
                return self.get(url, **kwargs)

            self.request_count += 1

            # Periyodik cookie temizleme
            security = PLATFORM_SECURITY.get(self.platform, {})
            if self.request_count >= security.get('clear_cookies_after', 50):
                self.session.cookies.clear()
                self.request_count = 0

            return response

        except Exception as e:
            print(f"    [-] Istek hatasi: {e}")
            return None

    def close(self):
        """Session'i kapat"""
        self.session.close()

# ============================================
# HETZNER SSH EXECUTOR
# ============================================
class HetznerExecutor:
    """Hetzner sunucusunda komut calistir"""

    def __init__(self):
        self.host = HETZNER.get('ip', '195.201.146.224')
        self.user = HETZNER.get('user', 'root')
        self.password = HETZNER.get('password', '')

    def run_scraper_on_server(self, scraper_script, args=[]):
        """
        Scraper'i Hetzner sunucusunda calistir

        Bu, tum ban riskini sunucuya tasir ve ev IP'nizi korur.

        Args:
            scraper_script: Calistirilacak script
            args: Script argumanlari

        Returns:
            str: Cikti
        """
        try:
            import paramiko

            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(self.host, username=self.user, password=self.password)

            # Script'i sunucuya kopyala ve calistir
            cmd = f"python3 {scraper_script} {' '.join(args)}"
            stdin, stdout, stderr = ssh.exec_command(cmd)

            output = stdout.read().decode()
            error = stderr.read().decode()

            ssh.close()

            if error:
                print(f"[!] Hetzner hata: {error}")

            return output

        except ImportError:
            print("[-] paramiko yuklu degil: pip install paramiko")
            return None
        except Exception as e:
            print(f"[-] Hetzner baglanti hatasi: {e}")
            return None

    def is_available(self):
        """Sunucu erisimi kontrol et"""
        try:
            resp = requests.get(f"http://{self.host}:8000/", timeout=5)
            return resp.status_code == 200
        except:
            return False

# ============================================
# MAIN
# ============================================
def main():
    print("=" * 50)
    print("TATANGA - Proxy ve Guvenlik Yonetimi")
    print("=" * 50)

    manager = ProxyManager()

    # Proxy test
    print("\nProxy Durumu:")
    for platform in PLATFORM_SECURITY.keys():
        proxy = manager.get_proxy_for_platform(platform)
        if proxy:
            print(f"  {platform}: {proxy['type']}")
        else:
            print(f"  {platform}: Proxy yok (API kullan)")

    # Hetzner test
    print("\nHetzner Sunucu:")
    hetzner = HetznerExecutor()
    if hetzner.is_available():
        print(f"  IP: {hetzner.host} - ONLINE")
    else:
        print(f"  IP: {hetzner.host} - OFFLINE")

    # Oneriler
    print("\nGuvenlik Onerileri:")
    print("  1. Tum scraping islemlerini Hetzner'de calistirin")
    print("  2. Ev IP'nizden ASLA direkt scraping yapmayin")
    print("  3. Rate limitlere uyun")
    print("  4. User agent'lari rotate edin")
    print("  5. Cookie'leri periyodik temizleyin")

if __name__ == "__main__":
    main()
