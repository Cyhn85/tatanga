#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TATANGA - System Settings
Genel sistem ayarlari
"""

import os
from pathlib import Path

# ============================================
# PATHS
# ============================================
BASE_DIR = Path(__file__).resolve().parents[2]  # tatanga/ project root, wherever it is installed
DATABASE_DIR = BASE_DIR / "shared" / "database"
LOGS_DIR = BASE_DIR / "logs"

# ============================================
# SCRAPING SETTINGS
# ============================================
SCRAPING = {
    "vinted": {
        "base_url": "https://www.vinted.de",
        "pagination": {
            "per_page": 96,
            "max_pages": 10,
        },
        "rate_limit": {
            "min_delay": 60,
            "max_delay": 120,
            "requests_per_session": 10,
        },
        "proxy_required": True,
        "risk_level": "high",
    },
    "kleinanzeigen": {
        "base_url": "https://www.kleinanzeigen.de",
        "pagination": {
            "per_page": 25,
            "max_pages": 50,
        },
        "rate_limit": {
            "min_delay": 30,
            "max_delay": 60,
            "requests_per_session": 30,
        },
        "proxy_required": False,
        "risk_level": "medium",
    },
    "ebay": {
        "base_url": "https://www.ebay.de",
        "api_method": "Browse API",
        "rate_limit": {
            "calls_per_day": 5000,
            "delay": 1,
        },
        "proxy_required": False,
        "risk_level": "low",
    },
    "willhaben": {
        "base_url": "https://www.willhaben.at",
        "pagination": {
            "per_page": 25,
            "max_pages": 40,
        },
        "rate_limit": {
            "min_delay": 30,
            "max_delay": 60,
            "requests_per_session": 30,
        },
        "proxy_required": False,
        "risk_level": "medium",
    },
}

# ============================================
# FILTERING / ARBITRAGE SETTINGS
# ============================================
ARBITRAGE = {
    "min_profit_margin": 0.25,  # %25 minimum kar marji
    "min_profit_euro": 5,       # Minimum 5 EUR kar
    "max_buy_price": 100,       # Maximum 100 EUR alis fiyati
    "min_favorites": 5,         # Minimum 5 favori
    "exclude_brands": [
        "Shein", "Primark", "KiK", "Takko",
    ],
    "preferred_brands": [
        "Tommy Hilfiger", "Nike", "Adidas", "Zara", "H&M",
        "Levis", "Calvin Klein", "Hugo Boss", "Ralph Lauren",
        "North Face", "Patagonia", "Carhartt",
    ],
    "conditions": ["Neu", "Sehr gut", "Gut"],
}

# ============================================
# IMAGE PROCESSING SETTINGS
# ============================================
IMAGE_PROCESSING = {
    "platforms": {
        "cssberlin": {
            "rotation": 0,
            "crop_percent": 1,
            "zoom_out_percent": 5,
        },
        "ebay": {
            "rotation": 1.5,
            "perspective": 2,
            "zoom_out_percent": 3,
        },
        "vinted": {
            "rotation": -1,
            "crop_percent": 2,
            "zoom_out_percent": 4,
        },
        "kleinanzeigen": {
            "rotation": -2,
            "crop_percent": 1,
            "zoom_out_percent": 5,
        },
        "willhaben": {
            "rotation": 1,
            "crop_percent": 3,
            "zoom_out_percent": 4,
        },
    },
    "clean_metadata": True,
    "max_size_mb": 5,
    "output_format": "JPEG",
    "quality": 90,
}

# ============================================
# TELEGRAM CHANNELS
# ============================================
TELEGRAM_CHANNELS = {
    "trendler": "Trend urun bildirimleri",
    "arbitraj": "Arbitraj firsatlari",
    "listeleme": "Yeni ilan bildirimleri",
    "satislar": "Satis bildirimleri",
    "mesajlar": "Magaza mesajlari",
    "pazarlik": "Pazarlik bildirimleri",
    "kargo": "Kargo takip",
    "sistem": "Hata/uyari",
    "raporlar": "Gunluk/haftalik raporlar",
}

# ============================================
# MONITORING SETTINGS
# ============================================
MONITORING = {
    "check_interval_minutes": 15,
    "link_check_enabled": True,
    "message_check_enabled": True,
    "sale_check_enabled": True,
}

# ============================================
# NEGOTIATION SETTINGS
# ============================================
NEGOTIATION = {
    "auto_accept_threshold": 1.0,    # Tam fiyat veya ustu
    "auto_counter_threshold": 0.85,  # %85 ve ustu
    "min_acceptable": 0.75,          # %75 alti reddet
    "default_counter_discount": 0.05, # %5 indirim teklif et
}

# ============================================
# SHIPPING COSTS (GERMANY INTERNAL)
# ============================================
SHIPPING_COSTS = {
    "dhl": {
        "paket_s": 4.99,
        "paket_m": 5.99,
        "paket_l": 7.99,
    },
    "hermes": {
        "s": 4.50,
        "m": 5.50,
        "l": 6.95,
    },
    "dpd": {
        "classic": 6.99,
        "express": 12.99,
    },
    "gls": {
        "standard": 5.99,
        "express": 9.99,
    },
}

# ============================================
# CATEGORIES
# ============================================
CATEGORIES = {
    "clothing": {
        "de": "Kleidung",
        "subcategories": [
            "Hemden", "Hosen", "Jacken", "Pullover",
            "T-Shirts", "Kleider", "Rocke", "Blusen",
        ],
    },
    "shoes": {
        "de": "Schuhe",
        "subcategories": [
            "Sneaker", "Stiefel", "Sandalen", "Pumps",
        ],
    },
    "accessories": {
        "de": "Accessoires",
        "subcategories": [
            "Uhren", "Taschen", "Gurtel", "Sonnenbrillen",
        ],
    },
    "electronics": {
        "de": "Elektronik",
        "subcategories": [
            "Smartphones", "Tablets", "Kopfhorer", "Kameras",
        ],
    },
}

# ============================================
# LISTING TEMPLATES
# ============================================
LISTING_DEFAULTS = {
    "condition_map": {
        "Neu": "NEW",
        "Sehr gut": "LIKE_NEW",
        "Gut": "GOOD",
        "Akzeptabel": "ACCEPTABLE",
    },
    "default_shipping": "DHL",
    "return_policy": "14 Tage Ruckgaberecht",
}
