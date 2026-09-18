#!/usr/bin/env python3
"""TATANGA System Test"""
import requests
import json

base = 'http://localhost:8501'
tests = {
    'Dashboard': '/',
    'Scraper': '/scraper',
    'Products': '/products',
    'Watchlist': '/watchlist',
    'Settings': '/settings',
    'Accounting': '/accounting',
    'Images': '/images',
    'Monitor': '/monitor',
    'API Stats': '/api/stats',
    'API Telegram': '/api/telegram/status',
    'API Scheduler': '/api/scheduler',
    'API Watchlist': '/api/watchlist',
    'API Activity': '/api/activity',
}

print('=' * 50)
print('TATANGA T11_HUB - Sistem Testi')
print('=' * 50)
all_ok = True
for name, path in tests.items():
    try:
        r = requests.get(base + path, timeout=5)
        status = 'OK' if r.status_code == 200 else f'FAIL ({r.status_code})'
        if r.status_code != 200:
            all_ok = False
        print(f'  {status:6s} | {name:20s} | {path}')
    except Exception as e:
        all_ok = False
        print(f'  ERROR  | {name:20s} | {str(e)[:40]}')

print('=' * 50)
stats = requests.get(base + '/api/stats', timeout=5).json()
print(f'Toplam Urun: {stats["total"]}')
print(f'Karli: {stats["profitable"]}')
print(f'Yayinda: {stats["published"]}')
print(f'Satilan: {stats["sold"]}')
print(f'Platformlar: {json.dumps(stats["platforms"])}')
print('=' * 50)
print('Sonuc: ' + ('TUM TESTLER BASARILI!' if all_ok else 'BAZI TESTLER BASARISIZ'))
