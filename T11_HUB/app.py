#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TATANGA T11_HUB - Komuta Merkezi
Lokal Dashboard + Canli Kazima + Pipeline Yonetimi
"""

import asyncio
import json
import os
import re
import sqlite3
import sys
import time
import uuid
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from dotenv import load_dotenv
load_dotenv()

# Telegram bot integration (Unified v2 - multi-channel)
try:
    from telegram_bot import (
        run_bot_polling, notify_scrape_complete, notify_product_added,
        notify_product_published, notify_source_sold, notify_error,
        notify_system_status, notify_captcha_required, notify_sms_required,
        notify_all, send_to_bildirimler, send_to_sistem_hata, send_to_captcha,
        load_config as load_telegram_config,
        save_config as save_telegram_config, get_bot,
        CHANNELS as TELEGRAM_CHANNELS,
    )
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    print("[TELEGRAM] telegram_bot.py bulunamadi, bot devre disi")

# Paths
BASE_DIR = Path(__file__).parent
TATANGA_DIR = BASE_DIR.parent

# Yeni logic modulleri (additive) — cwd farkli olsa da import edilebilsin diye
# BASE_DIR sys.path'e eklenir. Bu moduller app.py'ye dokunmadan test edildi.
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
try:
    from logic.keyword_localizer import localize_keyword as _localize_keyword
    from logic.quality_filter import should_keep as _should_keep
    from logic.facet_driver import drive_to_exhaustion as _drive_facets
    from logic.image_sourcing import source_best_image as _source_best_image
    from logic import condition_intel as _condition_intel
    from logic import outcome_learning as _outcome_learning
    from logic import currency as _currency
    from logic.rate_guard import GUARD as _rate_guard
    from logic.observation_store import ObservationStore as _ObsStore
    from logic.observation_store import observation_from_product as _obs_from_product
    from logic import demand_stats as _demand_stats
except Exception as _logic_imp_err:  # pragma: no cover - import guvencesi
    print(f"[LOGIC] yeni logic modulleri yuklenemedi: {_logic_imp_err}")
    _localize_keyword = None
    _should_keep = None
    _drive_facets = None
    _source_best_image = None
    _condition_intel = None
    _outcome_learning = None
    _currency = None
    _rate_guard = None
    _ObsStore = None
    _obs_from_product = None
    _demand_stats = None
try:
    from media.image_processor import matte_to_studio as _matte_to_studio
except Exception as _media_imp_err:  # pragma: no cover - import guvencesi
    print(f"[MEDIA] image_processor yuklenemedi (eski u2net yoluna dusulecek): {_media_imp_err}")
    _matte_to_studio = None
try:
    from logic import pricing as _pricing
except Exception as _pricing_imp_err:  # pragma: no cover - import guvencesi
    print(f"[PRICING] pricing yuklenemedi: {_pricing_imp_err}")
    _pricing = None
try:
    from logic import demand_tracker as _demand_tracker
except Exception as _dt_imp_err:  # pragma: no cover - import guvencesi
    print(f"[TALEP] demand_tracker yuklenemedi: {_dt_imp_err}")
    _demand_tracker = None
try:
    from core import event_bus as _event_bus
except Exception as _bus_imp_err:  # pragma: no cover - import guvencesi
    print(f"[BUS] event_bus yuklenemedi: {_bus_imp_err}")
    _event_bus = None
DATA_DIR = BASE_DIR / "data"

# ── cssberlin.de kopru ayarlari ───────────────────────────────────────────────
# Adres ve anahtar .env'den okunur, koda gomulmez.
#
# Onceki hali iki yerde `"x-api-key": "tatanga_cssberlin_2026_secret"` yaziyordu.
# Bir sir kaynak kodunda durursa git gecmisine girer ve oradan silinmez; ayrica
# sunucudaki karsiligi degistiginde kod da degismek zorunda kalir. Bu iki cagri
# (fiyat guncelleme ve yayindan kaldirma) simdi diger cagrilarla ayni kaynaktan
# besleniyor.
#
# Anahtar eksikse sessizce "yetkisiz" istek atmak yerine hemen patlariz: 401
# donen bir istegin sebebini aramak, eksik yapilandirmayi bastan gormekten cok
# daha pahali.

def _cssberlin_base() -> str:
    """Yayin hedefinin kok adresi (sondaki / temizlenir)."""
    base = os.getenv("CSSBERLIN_API_URL", "").rstrip("/")
    if not base:
        raise RuntimeError("CSSBERLIN_API_URL .env'de tanimli degil")
    return base


def _cssberlin_key() -> str:
    """cssberlin tarafindaki TATANGA_IMPORT_API_KEY ile birebir ayni olmali."""
    key = os.getenv("CSSBERLIN_API_KEY", "")
    if not key:
        raise RuntimeError("CSSBERLIN_API_KEY .env'de tanimli degil")
    return key


# Cinsiyeti tespit edilemeyen urunler bu kategoriye gider. "damen" YAPMA —
# bilinmeyenleri kadin kataloguna doldurur (bkz. _detect_category).
CATEGORY_FALLBACK = os.getenv("CATEGORY_FALLBACK", "sport")
IMAGES_RAW = DATA_DIR / "images" / "raw"
IMAGES_PROCESSED = DATA_DIR / "images" / "processed"
LOGS_DIR = BASE_DIR / "logs"
DB_PATH = DATA_DIR / "hub.db"

# Ensure directories exist
for d in [DATA_DIR, IMAGES_RAW, IMAGES_PROCESSED, LOGS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ============================================
# DATABASE SETUP (SQLite + aiosqlite)
# ============================================
import aiosqlite

DB_FILE = str(DB_PATH)

async def init_db():
    """Veritabani tablolarini olustur"""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS products (
                id TEXT PRIMARY KEY,
                source_platform TEXT NOT NULL,
                source_url TEXT UNIQUE,
                source_id TEXT,
                title TEXT,
                description TEXT,
                price REAL,
                currency TEXT DEFAULT 'EUR',
                brand TEXT,
                size TEXT,
                color TEXT,
                condition TEXT,
                category TEXT,
                images_json TEXT DEFAULT '[]',

                -- AI optimized fields
                seo_title TEXT,
                seo_description TEXT,
                seo_keywords TEXT DEFAULT '[]',
                seo_tags TEXT DEFAULT '[]',

                -- Arbitrage (Site bazli karsilastirmali)
                estimated_sell_price REAL,
                profit_margin REAL,
                profit_euro REAL,
                total_cost REAL DEFAULT 0,
                recommendation TEXT DEFAULT 'analyze',
                best_sell_platform TEXT,
                shipping_cost REAL DEFAULT 0,
                platform_fee REAL DEFAULT 0,
                arbitrage_json TEXT DEFAULT '[]',

                -- Images
                raw_images_json TEXT DEFAULT '[]',
                processed_images_json TEXT DEFAULT '[]',
                bg_removed INTEGER DEFAULT 0,

                -- Status
                status TEXT DEFAULT 'scraped',
                source_status TEXT DEFAULT 'active',
                last_source_check TEXT,
                published_to TEXT DEFAULT '[]',
                cssberlin_id TEXT,

                -- Meta
                views INTEGER DEFAULT 0,
                favorites INTEGER DEFAULT 0,
                scraped_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS scrape_jobs (
                id TEXT PRIMARY KEY,
                keyword TEXT NOT NULL,
                platforms TEXT DEFAULT '[]',
                status TEXT DEFAULT 'pending',
                total_found INTEGER DEFAULT 0,
                profitable_count INTEGER DEFAULT 0,
                started_at TEXT,
                completed_at TEXT,
                error_log TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS platform_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,
                success_count INTEGER DEFAULT 0,
                fail_count INTEGER DEFAULT 0,
                avg_response_time REAL DEFAULT 0,
                last_scrape TEXT,
                is_blocked INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS source_checks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id TEXT,
                source_url TEXT,
                status TEXT,
                checked_at TEXT DEFAULT CURRENT_TIMESTAMP,
                response_code INTEGER,
                FOREIGN KEY (product_id) REFERENCES products(id)
            );

            CREATE TABLE IF NOT EXISTS activity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                details TEXT,
                level TEXT DEFAULT 'info',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            -- ==========================================
            -- MUHASEBE / ACCOUNTING (Kleinunternehmer)
            -- ==========================================

            -- Tum gelir ve giderler (EUeR - Einnahmen Ueberschuss Rechnung)
            CREATE TABLE IF NOT EXISTS accounting_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_type TEXT NOT NULL CHECK(entry_type IN ('income','expense')),
                category TEXT NOT NULL,
                subcategory TEXT DEFAULT '',
                description TEXT NOT NULL,
                amount REAL NOT NULL,
                currency TEXT DEFAULT 'EUR',
                tax_rate REAL DEFAULT 0,
                tax_amount REAL DEFAULT 0,
                date TEXT NOT NULL,
                invoice_number TEXT,
                counterparty TEXT,
                payment_method TEXT DEFAULT 'bank_transfer',
                receipt_path TEXT,
                product_id TEXT,
                platform TEXT,
                notes TEXT,
                is_recurring INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (product_id) REFERENCES products(id)
            );

            -- Satis kayitlari (Her satilan urun icin)
            CREATE TABLE IF NOT EXISTS sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id TEXT,
                sold_platform TEXT NOT NULL,
                sold_price REAL NOT NULL,
                shipping_income REAL DEFAULT 0,
                platform_fee REAL DEFAULT 0,
                shipping_cost_actual REAL DEFAULT 0,
                packaging_cost REAL DEFAULT 0,
                buy_price REAL DEFAULT 0,
                net_profit REAL DEFAULT 0,
                buyer_username TEXT,
                buyer_country TEXT DEFAULT 'DE',
                sold_date TEXT NOT NULL,
                invoice_number TEXT,
                tracking_number TEXT,
                notes TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (product_id) REFERENCES products(id)
            );

            -- Alis kayitlari (Tedarik)
            CREATE TABLE IF NOT EXISTS purchases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id TEXT,
                source_platform TEXT NOT NULL,
                source_url TEXT,
                buy_price REAL NOT NULL,
                shipping_cost REAL DEFAULT 0,
                total_cost REAL NOT NULL,
                seller_username TEXT,
                seller_country TEXT DEFAULT 'DE',
                purchase_date TEXT NOT NULL,
                receipt_path TEXT,
                notes TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (product_id) REFERENCES products(id)
            );

            -- Isletme giderleri (paketleme malzemesi, yazilim, vb.)
            CREATE TABLE IF NOT EXISTS business_expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                description TEXT NOT NULL,
                amount REAL NOT NULL,
                tax_deductible INTEGER DEFAULT 1,
                date TEXT NOT NULL,
                vendor TEXT,
                receipt_path TEXT,
                notes TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            -- Aylik ozet (ELSTER beyanname destegi)
            CREATE TABLE IF NOT EXISTS monthly_summary (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                year INTEGER NOT NULL,
                month INTEGER NOT NULL,
                total_income REAL DEFAULT 0,
                total_expenses REAL DEFAULT 0,
                total_purchases REAL DEFAULT 0,
                total_shipping REAL DEFAULT 0,
                total_fees REAL DEFAULT 0,
                net_profit REAL DEFAULT 0,
                items_sold INTEGER DEFAULT 0,
                items_purchased INTEGER DEFAULT 0,
                notes TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(year, month)
            );

            -- Arsiv: Trend ve analiz icin
            CREATE TABLE IF NOT EXISTS product_archive (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id TEXT,
                title TEXT,
                brand TEXT,
                category TEXT,
                buy_price REAL,
                sell_price REAL,
                profit REAL,
                source_platform TEXT,
                sold_platform TEXT,
                days_to_sell INTEGER,
                archived_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_products_status ON products(status);
            CREATE INDEX IF NOT EXISTS idx_products_platform ON products(source_platform);
            CREATE INDEX IF NOT EXISTS idx_products_source_url ON products(source_url);
            CREATE INDEX IF NOT EXISTS idx_scrape_jobs_status ON scrape_jobs(status);
            CREATE INDEX IF NOT EXISTS idx_accounting_date ON accounting_entries(date);
            CREATE INDEX IF NOT EXISTS idx_accounting_type ON accounting_entries(entry_type);
            CREATE INDEX IF NOT EXISTS idx_sales_date ON sales(sold_date);
            CREATE INDEX IF NOT EXISTS idx_purchases_date ON purchases(purchase_date);
            CREATE INDEX IF NOT EXISTS idx_archive_brand ON product_archive(brand);
            CREATE INDEX IF NOT EXISTS idx_archive_category ON product_archive(category);
        """)
        await db.commit()
    print("[DB] Veritabani hazir")

# ============================================
# FASTAPI APP
# ============================================
app = FastAPI(title="TATANGA Hub", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
app.mount("/data", StaticFiles(directory=str(DATA_DIR)), name="data")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# Custom Jinja2 filters
def fromjson_filter(value):
    """JSON string to Python object"""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except:
            return []
    return value

templates.env.filters["fromjson"] = fromjson_filter
templates.env.globals["json"] = json

# WebSocket connections
ws_clients: list[WebSocket] = []

@app.on_event("startup")
async def startup():
    await init_db()
    # Onceki calistirmadan (sert kapanma/crash) 'running' halinde kalmis zombi
    # kazima isleri temizlenir - aksi halde "Aktif Is" sayaci hicbir zaman
    # gercek olmayan eski isleri saymaya devam eder.
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM scrape_jobs WHERE status='running'")
        stale_count = (await cursor.fetchone())[0]
        if stale_count:
            await db.execute(
                "UPDATE scrape_jobs SET status='failed', error_log='Uygulama yeniden baslatildiginda yarim kalmisti' WHERE status='running'"
            )
            await db.commit()
            await log_activity("startup_cleanup", f"{stale_count} zombi kazima isi temizlendi", "warning")
    await log_activity("system", "TATANGA Hub baslatildi", "info")

    # Deterministik yonetici dongusu (core/manager): olay otobusunu ve
    # zamanlanmis isleri yonetir, hata esiginde teshis eder. Guard'li -
    # yuklenemezse uygulama normal calismaya devam eder.
    try:
        from core import manager as _manager
        # app.py'ye bagimli handler'lar burada kaydedilir (core/handlers'a tasinamaz).
        _manager.register_handler("source_recheck", _source_recheck_handler)
        if _event_bus is not None:
            await _event_bus.init_bus(db_file=DB_FILE)
            await _event_bus.register_job("source_recheck", kind="source_recheck",
                                          interval_seconds=600, db_file=DB_FILE)  # 10 dk
        asyncio.create_task(_manager.run_loop(interval_seconds=60))
        print("[MANAGER] deterministik yonetici dongusu baslatildi (60s)")
    except Exception as _mgr_err:  # pragma: no cover
        print(f"[MANAGER] dongu baslatilamadi: {_mgr_err}")


@app.on_event("shutdown")
async def shutdown():
    # Kapanista yarim kalan isleri ayirt edilebilir sekilde isaretler - sert
    # 'taskkill /F' hala son care olarak kalabilir ama artik DB'de temiz iz birakir.
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("UPDATE scrape_jobs SET status='interrupted' WHERE status='running'")
        await db.commit()


@app.post("/api/admin/mark-jobs-interrupted")
async def mark_jobs_interrupted():
    """start_hub.bat, sert 'taskkill /F' cagirmadan hemen once bunu cagirir -
    uvicorn'un shutdown event'inin calisma garantisi olmadigi (force-kill sinyal
    yakalamayi atlayabilir) Windows ortaminda, DB temizligini guvenceye alir."""
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute("UPDATE scrape_jobs SET status='interrupted' WHERE status='running'")
        await db.commit()
        return {"marked": cursor.rowcount}

# ============================================
# WEBSOCKET - Canli Bildirimler
# ============================================
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    ws_clients.append(websocket)
    try:
        while True:
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        ws_clients.remove(websocket)

async def broadcast_ws(event: str, data: dict):
    """Tum baglananlara mesaj gonder"""
    message = json.dumps({"event": event, "data": data, "ts": datetime.now().isoformat()})
    for client in ws_clients[:]:
        try:
            await client.send_text(message)
        except:
            ws_clients.remove(client)

# ============================================
# HELPER FUNCTIONS
# ============================================
# Basari kriteri: bir kazima isi, en az bu kadar KARLI (buy/watch) urun uretmeli;
# altindaysa low_yield sinyali (ham sayi degil, kaliteli-buy odakli).
SCRAPE_SUCCESS_MIN_PROFITABLE = 1

# action oneki -> olay otobusu asamasi (stage). Bilinmeyen -> system.
_STAGE_BY_HINT = (
    ("vinted", "scrape"), ("kleinanzeigen", "scrape"), ("scrape", "scrape"),
    ("relevance", "scrape"), ("quality", "scrape"), ("keyword", "scrape"),
    ("bg", "image"), ("image", "image"),
    ("publish", "publish"), ("reprice", "reprice"),
    ("video", "video"), ("ad_", "ad"), ("startup", "system"),
)


def _bridge_stage_status(action: str, level: str) -> tuple[str, str, str | None]:
    """log_activity(action,level) -> (stage, status, error_code) olay otobusu icin."""
    a = (action or "").lower()
    stage = "system"
    for hint, st in _STAGE_BY_HINT:
        if hint in a:
            stage = st
            break
    if "captcha" in a:
        return stage, "blocked", "captcha"
    if "blocked" in a or "403" in a or "401" in a:
        code = ("vinted_blocked" if "vinted" in a
                else "akamai_blocked" if "kleinanzeigen" in a or "akamai" in a
                else "blocked")
        return stage, "blocked", code
    if "429" in a or "rate" in a:
        return stage, "blocked", "rate_limited"
    if "low_yield" in a:
        return "scrape", "failed", "low_yield"
    if a == "bg_qc" or a.endswith("_qc"):
        return stage, "warn", "qc_hole"
    if level == "error" or "error" in a or "fail" in a:
        return stage, "failed", a or "unknown_error"
    return stage, "ok", None


async def log_activity(action: str, details: str, level: str = "info"):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "INSERT INTO activity_log (action, details, level) VALUES (?, ?, ?)",
            (action, details, level)
        )
        await db.commit()
    # Olay otobusune koprule (guard'li, best-effort): mevcut TUM log cagrilari
    # otomatik yapisal olaya donusur; manager/diagnostician bunu okur. Bir kilit/
    # hata olursa sadece o olay dusulur — loglama/kazima asla kirilmaz.
    if _event_bus is not None:
        try:
            _stage, _status, _err = _bridge_stage_status(action, level)
            await _event_bus.emit(_stage, _status, level=level, error_code=_err,
                                  message=(details or "")[:300], db_file=DB_FILE)
        except Exception:
            pass

def gen_id(prefix="PROD"):
    return f"{prefix}-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"

# ============================================
# DASHBOARD PAGES
# ============================================
@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row

        # Stats
        cursor = await db.execute("SELECT COUNT(*) as c FROM products")
        total = (await cursor.fetchone())[0]

        cursor = await db.execute("SELECT COUNT(*) as c FROM products WHERE status='scraped'")
        scraped = (await cursor.fetchone())[0]

        cursor = await db.execute("SELECT COUNT(*) as c FROM products WHERE recommendation='buy'")
        profitable = (await cursor.fetchone())[0]

        cursor = await db.execute("SELECT COUNT(*) as c FROM products WHERE status='published'")
        published = (await cursor.fetchone())[0]

        cursor = await db.execute("SELECT COUNT(*) as c FROM products WHERE source_status='sold'")
        sold = (await cursor.fetchone())[0]

        cursor = await db.execute("SELECT COUNT(*) as c FROM scrape_jobs WHERE status='running'")
        active_jobs = (await cursor.fetchone())[0]

        # Platform breakdown
        cursor = await db.execute(
            """SELECT source_platform as platform, COUNT(*) as count,
               SUM(CASE WHEN recommendation='buy' THEN 1 ELSE 0 END) as profitable
               FROM products GROUP BY source_platform ORDER BY count DESC"""
        )
        cols = [d[0] for d in cursor.description]
        by_platform = [dict(zip(cols, row)) for row in await cursor.fetchall()]

        # Top profitable products
        cursor = await db.execute(
            "SELECT id, title, source_platform, profit_euro, profit_margin FROM products WHERE recommendation='buy' ORDER BY profit_euro DESC LIMIT 8"
        )
        cols = [d[0] for d in cursor.description]
        top_profitable = [dict(zip(cols, row)) for row in await cursor.fetchall()]

        # Recent activity
        cursor = await db.execute(
            "SELECT * FROM activity_log ORDER BY created_at DESC LIMIT 15"
        )
        cols = [d[0] for d in cursor.description]
        activities = [dict(zip(cols, row)) for row in await cursor.fetchall()]

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "stats": {
            "total": total,
            "scraped": scraped,
            "profitable": profitable,
            "published": published,
            "sold": sold,
            "active_jobs": active_jobs,
            "by_platform": by_platform,
            "top_profitable": top_profitable,
        },
        "activities": activities,
    })

@app.get("/scraper", response_class=HTMLResponse)
async def scraper_page(request: Request):
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM scrape_jobs ORDER BY created_at DESC LIMIT 20")
        cols = [d[0] for d in cursor.description]
        jobs = [dict(zip(cols, row)) for row in await cursor.fetchall()]
    return templates.TemplateResponse("scraper.html", {
        "request": request,
        "jobs": jobs,
    })

@app.get("/products", response_class=HTMLResponse)
async def products_page(
    request: Request,
    status: str = "",
    platform: str = "",
    recommendation: str = "",
    category: str = "",
    gender: str = "",
    price_min: str = "",
    price_max: str = "",
    sort: str = "",
    page: int = 1,
    per_page: int = 100,
):
    from urllib.parse import urlencode
    from logic.category_plan import CLOTHING_TREE, GENDERS
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        where = "WHERE 1=1"
        params = []
        if status:
            where += " AND status=?"
            params.append(status)
        if platform:
            where += " AND source_platform=?"
            params.append(platform)
        if recommendation:
            where += " AND recommendation=?"
            params.append(recommendation)
        if category:
            terms = CLOTHING_TREE.get(category, [category])
            placeholders = " OR ".join(["LOWER(title) LIKE ?" for _ in terms])
            where += f" AND ({placeholders})"
            params.extend([f"%{t}%" for t in terms])
        if gender:
            where += " AND LOWER(title) LIKE ?"
            params.append(f"%{gender}%")
        if price_min:
            try:
                where += " AND price >= ?"
                params.append(float(price_min))
            except ValueError:
                pass
        if price_max:
            try:
                where += " AND price <= ?"
                params.append(float(price_max))
            except ValueError:
                pass

        # Toplam kayit sayisi
        count_cur = await db.execute(f"SELECT COUNT(*) FROM products {where}", params)
        total = (await count_cur.fetchone())[0]

        # Sayfalama
        page = max(1, page)
        per_page = max(10, min(per_page, 500))
        offset = (page - 1) * per_page
        total_pages = max(1, (total + per_page - 1) // per_page)

        # Siralama — SADECE beyaz listeden. Kullanici girdisi dogrudan SQL'e
        # konmaz (siralama ifadeleri parametrelenemez, bu yuzden esleme sart).
        # NULLS LAST etkisi icin "x IS NULL" on-anahtari: bos kar/fiyat ustte
        # gorunup listeyi bozmasin.
        SIRALAMA = {
            "": "created_at DESC",
            "yeni": "created_at DESC",
            "eski": "created_at ASC",
            # GERCEK SATIS ZEKASI (ops/hetzner_observer/zeka_urunler.py yazar). Puanlanamayan urun en altta.
            # siralama disi (yem fiyat < 5 EUR, zayif karsilastirma, "once yaz" ilanlari) her zaman en sonda
            "zeka_kar": "COALESCE(zeka_sirala,0)=0, zeka_net_kar IS NULL, zeka_net_kar DESC",
            "zeka_beklenen": "COALESCE(zeka_sirala,0)=0, zeka_beklenen IS NULL, zeka_beklenen DESC",
            "zeka_hiz": "COALESCE(zeka_sirala,0)=0 OR zeka_p30 IS NULL OR zeka_net_kar <= 0, zeka_p30 DESC, zeka_net_kar DESC",
            "kar_yuksek": "profit_euro IS NULL, profit_euro DESC",
            "kar_dusuk": "profit_euro IS NULL, profit_euro ASC",
            "marj_yuksek": "profit_margin IS NULL, profit_margin DESC",
            "fiyat_dusuk": "price IS NULL, price ASC",
            "fiyat_yuksek": "price IS NULL, price DESC",
            "durum_iyi": "condition_score IS NULL, condition_score DESC",
            "iade_riski": "CASE return_risk WHEN 'high' THEN 0 WHEN 'medium' THEN 1 "
                          "WHEN 'low' THEN 2 ELSE 3 END",
            "favori_cok": "favorites IS NULL, favorites DESC",
            "gpsr_eksik": "gpsr_ready ASC, gpsr_required DESC",
            "baslik": "title COLLATE NOCASE ASC",
        }
        order_by = SIRALAMA.get(sort, SIRALAMA[""])
        _have = {r[1] for r in await (await db.execute("PRAGMA table_info(products)")).fetchall()}
        for _c, _d in (("zeka_net_kar", "REAL"), ("zeka_net_medyan", "REAL"), ("zeka_satis_p25", "REAL"),
                       ("zeka_satis_medyan", "REAL"), ("zeka_p30", "REAL"), ("zeka_beklenen", "REAL"),
                       ("zeka_n", "INTEGER"), ("zeka_seviye", "TEXT"), ("zeka_alis_toplam", "REAL"),
                       ("zeka_isaret", "TEXT"), ("zeka_tarih", "TEXT"), ("zeka_sirala", "INTEGER")):
            if _c not in _have:
                await db.execute(f"ALTER TABLE products ADD COLUMN {_c} {_d}")
        await db.commit()

        cursor = await db.execute(
            f"SELECT * FROM products {where} ORDER BY {order_by} LIMIT ? OFFSET ?",
            params + [per_page, offset]
        )
        cols = [d[0] for d in cursor.description]
        products = [dict(zip(cols, row)) for row in await cursor.fetchall()]

    # --- Fiyat gosterimi: EUR karsiligini SUNUCUDA hesapla -----------------
    # Sablon eskiden ham `price` sutununu alip yanina sabit "€" koyuyordu.
    # Ama vinted_uk GBP, vinted_pl PLN kaydediyor: 89,63 GBP "89,63 €" diye
    # gosteriliyordu (gercegi 104,90 EUR). Ekran maliyeti ~16 EUR DUSUK
    # gosteriyordu — dogrudan yanlis alim karari demek.
    # Hangi urunler favoride — kalp butonu dolu/bos dogru cizilsin.
    favoriler: set = set()
    try:
        async with aiosqlite.connect(DB_FILE) as db:
            cur = await db.execute("SELECT product_id FROM watchlist")
            favoriler = {r[0] for r in await cur.fetchall()}
    except Exception:
        favoriler = set()

    r = _rates() if _currency else None
    for p in products:
        p["is_favorite"] = p.get("id") in favoriler
        birim = (p.get("currency") or "EUR").upper()
        p["display_currency"] = birim
        if birim == "EUR" or not r or not _currency:
            p["price_eur"] = p.get("price")
        else:
            p["price_eur"] = _currency.to_eur(p.get("price") or 0, birim, r)

    # --- Ayni ilanin tekrari: GORSEL ICERIGINE gore, PLATFORMDAN BAGIMSIZ ---
    # Olculen gercek (2317 urun): 278 tekrar var ve bunlarin 269'u PLATFORMLAR
    # ARASI. Sebep bizim mimarimiz: vinted.de / .fr / .be / .pl / .co.uk AYNI
    # pazaryerinin farkli alan adlari — ayni ilan ucunde birden gorunuyor.
    # Onlari 5 ayri platform sayinca ayni urunu 3 kez "firsat" olarak sayiyorduk.
    #
    # Gorsel URL'leri farkli olsa da indirilen DOSYA ayni (Vinted her ilan icin
    # ayri CDN yolu veriyor; olculdu: 4 URL, tek md5 f5fef6f00c30, 184686 bayt).
    # Bu yuzden anahtar = gorsel icerik hash'i; platform anahtara GIRMEZ.
    gruplu: list = []
    indeks: dict = {}
    for p in products:
        h = (p.get("image_hash") or "").strip()
        if h:
            anahtar = ("img", h)
        else:
            # Hash yoksa (gorsel indirilememis) baslik+fiyat+platform — zayif
            # ama hicten iyi; hash geldiginde gruplama kendiliginden guclenir.
            anahtar = (
                (p.get("source_platform") or ""),
                (p.get("title") or "").strip().lower(),
                round(float(p.get("price") or 0), 2),
            )
        mevcut = indeks.get(anahtar)
        if mevcut is None:
            p["duplicate_count"] = 1
            p["duplicate_ids"] = [p.get("id")]
            p["duplicate_platforms"] = [p.get("source_platform") or ""]
            indeks[anahtar] = p
            gruplu.append(p)
        else:
            mevcut["duplicate_count"] += 1
            mevcut["duplicate_ids"].append(p.get("id"))
            pl = p.get("source_platform") or ""
            if pl and pl not in mevcut["duplicate_platforms"]:
                mevcut["duplicate_platforms"].append(pl)
    products = gruplu

    current_params = urlencode({k: v for k, v in {
        "status": status, "platform": platform,
        "recommendation": recommendation, "category": category,
        "gender": gender, "price_min": price_min,
        "price_max": price_max, "sort": sort,
    }.items() if v})

    # Siralama menusu: is anlamina gore gruplanmis. Kullanici "hangi urunu
    # once alayim" sorusunu farkli aciardan sorar; menu o sorulari yansitir.
    sort_groups = [
        ("Gercek satis zekasi", [
            ("zeka_kar",      "En karli (gercek satislara gore)", "Tutucu net kar: ayni urun grubunun gercek satislarinin alt ceyregi (P25)"),
            ("zeka_beklenen", "Beklenen 30 gun kar",              "Tutucu net kar x 30 gunde satilma olasiligi"),
            ("zeka_hiz",      "En hizli satilir (karlilar)",      "Karli urunler, 30 gunde satilma olasiligina gore"),
        ]),
        ("Karlilik (eski kaba tahmin)", [
            ("kar_yuksek",  "Kar - eski tahmin",  "Eski hesap: satis = alis x ~1,4 (pahali urunu karli gosterir)"),
            ("marj_yuksek", "Marj - eski tahmin", "Eski hesap"),
            ("kar_dusuk",   "En dusuk kar (eski)", "Eski hesap"),
        ]),
        ("Fiyat", [
            ("fiyat_dusuk",  "Ucuzdan pahaliya",  "Ilan fiyati artan"),
            ("fiyat_yuksek", "Pahalidan ucuza",   "Ilan fiyati azalan"),
        ]),
        ("Kalite ve risk", [
            ("durum_iyi",   "En iyi durum",       "Durum skoru 5'ten 1'e (yeni -> yipranmis)"),
            ("iade_riski",  "Iade riski once",    "Beyan celiskisi olanlar en ustte"),
            ("gpsr_eksik",  "GPSR eksigi once",   "Uretici bilgisi belirlenemeyenler en ustte"),
        ]),
        ("Ilgi ve zaman", [
            ("favori_cok",  "En cok favorilenen", "Kaynak platformdaki favori sayisi"),
            ("yeni",        "En yeni kazinan",    "Son eklenen once"),
            ("eski",        "En eski kazinan",    "Ilk eklenen once"),
            ("baslik",      "Basliga gore (A-Z)", "Alfabetik"),
        ]),
    ]
    sort_labels = {d: e for _, secenekler in sort_groups for d, e, _ in secenekler}
    sort_labels[""] = "Sırala"

    category_labels = {
        "jacken": "Jacken", "mantel": "Mantel & Parka", "fleece": "Fleece",
        "pullover": "Pullover & Hoodie", "hemden": "Hemden & Blusen",
        "tshirts": "T-Shirts & Polos", "hosen": "Hosen & Jeans",
        "kleider": "Kleider & Röcke", "schuhe": "Schuhe",
        "taschen": "Taschen & Rucksäcke", "sport": "Sport", "accessoires": "Accessoires",
    }
    gender_labels = {"herren": "Herren", "damen": "Damen", "kinder": "Kinder"}

    return templates.TemplateResponse("products.html", {
        "request": request,
        "products": products,
        "filters": {
            "status": status,
            "platform": platform,
            "recommendation": recommendation,
            "category": category,
            "gender": gender,
            "price_min": price_min,
            "price_max": price_max,
            "sort": sort,
        },
        "category_list": list(category_labels.items()),
        "gender_list": list(gender_labels.items()),
        "sort_groups": sort_groups,
        "sort_labels": sort_labels,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
        },
        "current_params": current_params,
    })

@app.get("/product/{product_id}", response_class=HTMLResponse)
async def product_detail(request: Request, product_id: str):
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM products WHERE id=?", (product_id,))
        row = await cursor.fetchone()
        if not row:
            return HTMLResponse("<h1>Urun bulunamadi</h1>", status_code=404)
        cols = [d[0] for d in cursor.description]
        product = dict(zip(cols, row))

        # Source checks
        cursor = await db.execute(
            "SELECT * FROM source_checks WHERE product_id=? ORDER BY checked_at DESC LIMIT 10",
            (product_id,)
        )
        cols2 = [d[0] for d in cursor.description]
        checks = [dict(zip(cols2, r)) for r in await cursor.fetchall()]

    return templates.TemplateResponse("product_detail.html", {
        "request": request,
        "product": product,
        "source_checks": checks,
    })

@app.get("/monitor", response_class=HTMLResponse)
async def monitor_page(request: Request):
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM products WHERE status IN ('published', 'scraped') ORDER BY last_source_check ASC LIMIT 50"
        )
        cols = [d[0] for d in cursor.description]
        products = [dict(zip(cols, row)) for row in await cursor.fetchall()]

        cursor = await db.execute(
            "SELECT * FROM source_checks ORDER BY checked_at DESC LIMIT 30"
        )
        cols2 = [d[0] for d in cursor.description]
        checks = [dict(zip(cols2, r)) for r in await cursor.fetchall()]

    return templates.TemplateResponse("monitor.html", {
        "request": request,
        "products": products,
        "recent_checks": checks,
    })

@app.get("/published", response_class=HTMLResponse)
async def published_page(request: Request):
    """Yayinlanan urunler + canlilik takip sayfasi"""
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row

        # Yayindaki urunler
        cursor = await db.execute(
            "SELECT * FROM products WHERE status='published' ORDER BY created_at DESC"
        )
        cols = [d[0] for d in cursor.description]
        published_products = [dict(zip(cols, row)) for row in await cursor.fetchall()]

        # Yayinda istatistikler
        cursor2 = await db.execute("SELECT COUNT(*) FROM products WHERE status='published'")
        pub_count = (await cursor2.fetchone())[0]

        cursor3 = await db.execute("SELECT COUNT(*) FROM products WHERE source_status='sold'")
        sold_count = (await cursor3.fetchone())[0]

        # Monitor: Kontrol bekleyen urunler
        cursor4 = await db.execute(
            "SELECT * FROM products WHERE status IN ('published', 'scraped') ORDER BY last_source_check ASC LIMIT 50"
        )
        cols4 = [d[0] for d in cursor4.description]
        monitor_products = [dict(zip(cols4, row)) for row in await cursor4.fetchall()]

        # Son kaynak kontrolleri
        cursor5 = await db.execute(
            "SELECT sc.*, p.title FROM source_checks sc LEFT JOIN products p ON sc.product_id = p.id ORDER BY sc.checked_at DESC LIMIT 30"
        )
        cols5 = [d[0] for d in cursor5.description]
        recent_checks = [dict(zip(cols5, row)) for row in await cursor5.fetchall()]

    return templates.TemplateResponse("published.html", {
        "request": request,
        "published_products": published_products,
        "stats": {
            "published": pub_count,
            "sold": sold_count,
        },
        "monitor_products": monitor_products,
        "recent_checks": recent_checks,
    })


@app.post("/api/product/{product_id}/update-price")
async def update_product_price(product_id: str, request: Request):
    """Yayindaki urunun fiyatini guncelle — hem DB hem cssberlin.de"""
    import requests as req
    body = await request.json()
    new_price = body.get("price")

    if not new_price or float(new_price) <= 0:
        return JSONResponse({"error": "Gecersiz fiyat"}, status_code=400)

    new_price = float(new_price)

    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT cssberlin_id, title FROM products WHERE id=?", (product_id,))
        row = await cursor.fetchone()
        if not row:
            return JSONResponse({"error": "Urun bulunamadi"}, status_code=404)
        cssberlin_id = row["cssberlin_id"]

        # DB guncelle
        await db.execute(
            "UPDATE products SET estimated_sell_price=? WHERE id=?",
            (new_price, product_id)
        )
        await db.commit()

    # cssberlin.de API guncelle
    cssberlin_synced = False
    if cssberlin_id:
        try:
            resp = req.put(
                f"{_cssberlin_base()}/api/products/{cssberlin_id}",
                json={"price": new_price},
                headers={"x-api-key": _cssberlin_key()},
                timeout=10
            )
            cssberlin_synced = resp.status_code == 200
        except Exception:
            pass

    await log_activity("price_update", f"Fiyat guncellendi: {product_id} → {new_price}€")
    return {"status": "updated", "price": new_price, "cssberlin_synced": cssberlin_synced}


@app.post("/api/product/{product_id}/unpublish")
async def unpublish_product(product_id: str):
    """Urunu yayindan kaldir — hem cssberlin.de hem DB"""
    import requests as req

    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT cssberlin_id FROM products WHERE id=?", (product_id,))
        row = await cursor.fetchone()
        if not row:
            return JSONResponse({"error": "Urun bulunamadi"}, status_code=404)
        cssberlin_id = row["cssberlin_id"]

    # cssberlin.de'den sil
    cssberlin_removed = False
    if cssberlin_id:
        try:
            resp = req.delete(
                f"{_cssberlin_base()}/api/products/{cssberlin_id}",
                headers={"x-api-key": _cssberlin_key()},
                timeout=10
            )
            cssberlin_removed = resp.status_code in (200, 204)
        except Exception:
            pass

    # DB guncelle
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "UPDATE products SET status='scraped', cssberlin_id=NULL, published_to='[]' WHERE id=?",
            (product_id,)
        )
        await db.commit()

    await log_activity("unpublish", f"Yayindan kaldirildi: {product_id}")
    return {"status": "unpublished", "cssberlin_removed": cssberlin_removed}


@app.get("/images", response_class=HTMLResponse)
async def images_page(request: Request):
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM products WHERE bg_removed=0 AND images_json != '[]' ORDER BY created_at DESC LIMIT 30"
        )
        cols = [d[0] for d in cursor.description]
        pending = [dict(zip(cols, row)) for row in await cursor.fetchall()]

        cursor = await db.execute(
            "SELECT * FROM products WHERE bg_removed=1 ORDER BY updated_at DESC LIMIT 30"
        )
        processed = [dict(zip(cols, row)) for row in await cursor.fetchall()]

    return templates.TemplateResponse("images.html", {
        "request": request,
        "pending": pending,
        "processed": processed,
    })

# ============================================
# KURASYON — insan onayli yayin akisi
# ============================================
# Otomatik yayin kaliteyi olcemiyor: rembg bazen kapusonun icini deliyor,
# bazen elli fotografta urunu yiyor. Cozum: gorsel ISLENDIKTEN SONRA
# nihai 1200x1200 ciktiyi kullanici gorur, begendigini onaylar, sadece
# onaylananlar cssberlin'e gider.

async def init_curation_column():
    """products.curation_status: NULL=karar yok, 'onay'=aday, 'red'
    products.manual_price: kullanicinin elle girdigi vitrin fiyati."""
    async with aiosqlite.connect(DB_FILE) as db:
        cur = await db.execute("PRAGMA table_info(products)")
        cols = {r[1] for r in await cur.fetchall()}
        for kolon, tip in (("curation_status", "TEXT"), ("curated_at", "TEXT"),
                           ("manual_price", "REAL")):
            if kolon not in cols:
                await db.execute(f"ALTER TABLE products ADD COLUMN {kolon} {tip}")
                print(f"[DB] {kolon} kolonu eklendi")
        await db.commit()


@app.on_event("startup")
async def startup_curation():
    await init_curation_column()


@app.get("/kurasyon", response_class=HTMLResponse)
async def kurasyon_page(request: Request, kategori: str = "", durum: str = "bekleyen"):
    """Islenmis gorselleri gosterip onay/red almak icin izgara."""
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row

        # Kategori listesi (yayinlanmamis, kar getirebilir olanlar)
        cur = await db.execute("""
            SELECT COALESCE(NULLIF(TRIM(category),''),'(kategorisiz)') AS k,
                   COUNT(*) AS n,
                   SUM(CASE WHEN bg_removed=1 THEN 1 ELSE 0 END) AS islenmis
            FROM products
            WHERE (cssberlin_id IS NULL OR cssberlin_id='')
            GROUP BY k HAVING n > 0 ORDER BY islenmis DESC, n DESC LIMIT 40
        """)
        kategoriler = [dict(r) for r in await cur.fetchall()]

        # Izgara: islenmis + karar bekleyen
        kosullar = ["bg_removed=1", "processed_images_json IS NOT NULL",
                    "processed_images_json != '[]'",
                    "(cssberlin_id IS NULL OR cssberlin_id='')"]
        params: list = []
        if durum == "bekleyen":
            kosullar.append("curation_status IS NULL")
        elif durum in ("onay", "red"):
            kosullar.append("curation_status=?")
            params.append(durum)
        if kategori and kategori != "(kategorisiz)":
            kosullar.append("category=?")
            params.append(kategori)
        elif kategori == "(kategorisiz)":
            kosullar.append("(category IS NULL OR TRIM(category)='')")

        cur = await db.execute(
            f"SELECT * FROM products WHERE {' AND '.join(kosullar)} "
            "ORDER BY updated_at DESC LIMIT 60", params)
        cols = [d[0] for d in cur.description]
        urunler = [dict(zip(cols, r)) for r in await cur.fetchall()]

        cur = await db.execute("""
            SELECT
              SUM(CASE WHEN curation_status='onay' THEN 1 ELSE 0 END) onay,
              SUM(CASE WHEN curation_status='red' THEN 1 ELSE 0 END) red,
              SUM(CASE WHEN curation_status IS NULL AND bg_removed=1
                        AND processed_images_json != '[]' THEN 1 ELSE 0 END) bekleyen
            FROM products WHERE (cssberlin_id IS NULL OR cssberlin_id='')
        """)
        sayim = dict(await cur.fetchone())

    return templates.TemplateResponse("kurasyon.html", {
        "request": request, "urunler": urunler, "kategoriler": kategoriler,
        "secili_kategori": kategori, "secili_durum": durum, "sayim": sayim,
    })


@app.post("/api/curation/{product_id}/decide")
async def curation_decide(product_id: str, request: Request):
    """Tek urun icin onay/red kaydet."""
    body = await request.json()
    karar = body.get("decision")
    if karar not in ("onay", "red", None):
        return JSONResponse({"error": "decision 'onay' | 'red' | null olmali"}, status_code=400)
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "UPDATE products SET curation_status=?, curated_at=? WHERE id=?",
            (karar, datetime.now().isoformat(), product_id))
        await db.commit()
    return {"status": "ok", "product_id": product_id, "decision": karar}


@app.post("/api/curation/process-batch")
async def curation_process_batch(request: Request, background_tasks: BackgroundTasks):
    """Secili kategoriden N adet urunun gorselini isle (arka planda).
    Isleme bitince /kurasyon izgarasinda nihai ciktiyla belirirler."""
    body = await request.json()
    kategori = (body.get("category") or "").strip()
    limit = max(1, min(int(body.get("limit", 20)), 100))

    kosullar = ["bg_removed=0", "images_json IS NOT NULL", "images_json != '[]'",
                "(cssberlin_id IS NULL OR cssberlin_id='')"]
    params: list = []
    if kategori and kategori != "(kategorisiz)":
        kosullar.append("category=?"); params.append(kategori)
    elif kategori == "(kategorisiz)":
        kosullar.append("(category IS NULL OR TRIM(category)='')")

    async with aiosqlite.connect(DB_FILE) as db:
        cur = await db.execute(
            f"SELECT id FROM products WHERE {' AND '.join(kosullar)} "
            "ORDER BY created_at DESC LIMIT ?", (*params, limit))
        ids = [r[0] for r in await cur.fetchall()]

    for pid in ids:
        background_tasks.add_task(process_background_removal, pid)

    await log_activity("kurasyon_batch",
                       f"{len(ids)} urun gorsel islemeye alindi (kategori: {kategori or 'hepsi'})")
    return {"status": "queued", "count": len(ids), "category": kategori}


# ============================================
# YAYIN EKRANI — fiyat girip yayina alma
# ============================================
# Kurasyonda "aday" isaretlenen urunler buraya duser. Fav'dan DOGRUDAN
# yayin yok: once maliyet gorulur, fiyat elle girilir, sonra yayinlanir.

def _urun_maliyeti(p: dict) -> dict:
    """Bir urun satiri icin cssberlin maliyet dokumu + onerilen vitrin fiyati."""
    if _pricing is None:
        return {}
    alis = float(p.get("price") or 0)
    gelen = float(p.get("shipping_cost") or 0)
    oneri = _pricing.onerilen_fiyat(alis, gelen)
    secili = float(p.get("manual_price") or 0) or oneri
    m = _pricing.hesapla(alis, gelen, secili)
    d = m.dict()
    d["onerilen"] = oneri
    return d


@app.get("/yayin", response_class=HTMLResponse)
async def yayin_page(request: Request):
    """Aday urunler: maliyet dokumu + fiyat girisi + yayinla."""
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("""
            SELECT * FROM products
            WHERE curation_status='onay' AND (cssberlin_id IS NULL OR cssberlin_id='')
            ORDER BY curated_at ASC LIMIT 80
        """)
        cols = [d[0] for d in cur.description]
        urunler = [dict(zip(cols, r)) for r in await cur.fetchall()]

    for p in urunler:
        p["_maliyet"] = _urun_maliyeti(p)
        p["_seo_tamam"] = bool(p.get("seo_title") and p.get("seo_description"))

    return templates.TemplateResponse("yayin.html", {
        "request": request, "urunler": urunler,
    })


@app.post("/api/yayin/{product_id}/fiyat")
async def yayin_fiyat_kaydet(product_id: str, request: Request):
    """Elle girilen vitrin fiyatini kaydet ve guncel maliyet dokumunu don."""
    body = await request.json()
    try:
        fiyat = float(body.get("price"))
    except (TypeError, ValueError):
        return JSONResponse({"error": "gecerli bir fiyat gonder"}, status_code=400)
    if fiyat <= 0:
        return JSONResponse({"error": "fiyat 0'dan buyuk olmali"}, status_code=400)

    yuvarlanmis = _pricing.yuvarla(fiyat) if _pricing else round(fiyat, 2)

    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("UPDATE products SET manual_price=? WHERE id=?",
                         (yuvarlanmis, product_id))
        await db.commit()
        cur = await db.execute("SELECT * FROM products WHERE id=?", (product_id,))
        row = await cur.fetchone()
        if not row:
            return JSONResponse({"error": "urun bulunamadi"}, status_code=404)
        p = dict(zip([d[0] for d in cur.description], row))

    return {"status": "ok", "price": yuvarlanmis, "maliyet": _urun_maliyeti(p)}


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    return templates.TemplateResponse("settings.html", {"request": request})

# ============================================
# API ENDPOINTS
# ============================================

@app.post("/api/scrape/start")
async def start_scrape(request: Request, background_tasks: BackgroundTasks):
    """Kazima isi baslat.
    scrape_strategy: 'single' (varsayilan, hizli) | 'multi_order' (onerilir, daha fazla urun)
                     | 'faceted' (renk/beden/siralama facet'leriyle tam-sonuca-kadar sur)
    """
    body = await request.json()
    keyword = body.get("keyword", "")
    platforms = body.get("platforms", ["vinted", "kleinanzeigen", "ebay", "sellpy", "willhaben", "tradera", "leboncoin"])
    max_pages = body.get("max_pages", 3)
    strategy = body.get("scrape_strategy", "single")

    if not keyword:
        return JSONResponse({"error": "Anahtar kelime gerekli"}, status_code=400)

    job_id = gen_id("JOB")

    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "INSERT INTO scrape_jobs (id, keyword, platforms, status, started_at) VALUES (?, ?, ?, 'running', ?)",
            (job_id, keyword, json.dumps(platforms), datetime.now().isoformat())
        )
        await db.commit()

    await log_activity("scrape_start", f"Kazima basladi: '{keyword}' [{strategy}] - {', '.join(platforms)}")
    await broadcast_ws("scrape_started", {"job_id": job_id, "keyword": keyword, "platforms": platforms, "strategy": strategy})

    # Background task olarak kazima baslat
    background_tasks.add_task(run_scrape_job, job_id, keyword, platforms, max_pages, strategy)

    return {"job_id": job_id, "status": "started", "keyword": keyword, "platforms": platforms, "strategy": strategy}

# ============================================
# AKILLI KAZIMA — min_favorites filtreli (YENI, mevcut sisteme dokunmaz)
# ============================================
async def run_smart_scrape_job(job_id: str, keyword: str, platforms: list, max_pages: int,
                               min_favorites: int, min_views: int, strategy: str = "single"):
    """
    Akilli kazima: Vinted'de favorite_count >= min_favorites olan urunleri kaydet.
    Diger platformlarda favorites verisi gelmez, o urunler oldugu gibi kaydedilir.
    Mevcut run_scrape_job fonksiyonuna DOKUNMAZ.
    strategy: 'single' veya 'multi_order'
    """
    total_found = 0
    total_skipped = 0
    profitable = 0

    try:
        for platform in platforms:
            try:
                await broadcast_ws("scrape_progress", {
                    "job_id": job_id,
                    "platform": platform,
                    "status": "scraping",
                    "mode": "smart",
                    "strategy": strategy
                })

                products = await collect_products(platform, keyword, max_pages, strategy, job_id)
                await _talep_kaydet(platform, keyword, job_id, products)
                platform_skipped = 0

                for prod in products:
                    # AKILLI FILTRE: Vinted icin favorite_count kontrolu
                    fav_count = prod.get("favorites", 0) or 0
                    view_count = prod.get("views", 0) or 0

                    if platform == "vinted":
                        if fav_count < min_favorites:
                            platform_skipped += 1
                            total_skipped += 1
                            continue  # DB'ye kaydetme, atla
                        if min_views > 0 and view_count < min_views:
                            platform_skipped += 1
                            total_skipped += 1
                            continue

                    prod_id = gen_id("PROD")
                    analysis = analyze_profit(prod, platform)
                    source_url = prod.get("url", "")

                    async with aiosqlite.connect(DB_FILE) as db:
                        try:
                            if source_url:
                                cursor = await db.execute("SELECT id FROM products WHERE source_url=?", (source_url,))
                                existing = await cursor.fetchone()
                                if existing:
                                    await db.execute(
                                        "UPDATE products SET price=?, favorites=?, views=?, updated_at=?, source_status='active' WHERE source_url=?",
                                        (prod.get("price", 0), fav_count, view_count, datetime.now().isoformat(), source_url))
                                    await db.commit()
                                    total_found += 1
                                    continue

                            await db.execute("""
                                INSERT INTO products
                                (id, source_platform, source_url, source_id, title, description,
                                 price, currency, brand, size, color, condition, category,
                                 images_json, estimated_sell_price, profit_margin, profit_euro,
                                 total_cost, recommendation, best_sell_platform, shipping_cost,
                                 platform_fee, arbitrage_json,
                                 views, favorites, scraped_at, status)
                                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                            """, (
                                prod_id, platform, source_url, prod.get("source_id"),
                                prod.get("title"), prod.get("description"),
                                prod.get("price", 0), prod.get("currency", "EUR"),
                                prod.get("brand"), prod.get("size"), prod.get("color"),
                                prod.get("condition"), prod.get("category"),
                                json.dumps(prod.get("images", [])),
                                analysis.get("sell_price", 0), analysis.get("margin", 0),
                                analysis.get("profit", 0), analysis.get("total_cost", 0),
                                analysis.get("recommendation", "skip"),
                                analysis.get("best_platform", ""),
                                analysis.get("shipping", 0), analysis.get("fee", 0),
                                analysis.get("arbitrage_json", "[]"),
                                view_count, fav_count,
                                datetime.now().isoformat(), "scraped"
                            ))
                            await db.commit()
                            await _save_condition_fields(db, prod_id, prod)
                            total_found += 1
                            if analysis.get("recommendation") == "buy":
                                profitable += 1
                        except Exception as e:
                            print(f"[SMART INSERT ERROR] {platform}: {str(e)[:100]}")

                await broadcast_ws("scrape_progress", {
                    "job_id": job_id,
                    "platform": platform,
                    "status": "done",
                    "found": len(products) - platform_skipped,
                    "skipped": platform_skipped,
                    "mode": "smart"
                })
                await log_activity("smart_scrape",
                    f"{platform}: {len(products) - platform_skipped} kayit, {platform_skipped} atildi "
                    f"(min_fav>={min_favorites}) [{keyword}]")

            except Exception as e:
                await log_activity("smart_scrape_error", f"{platform} hatasi: {str(e)}", "error")

        # Job tamamla
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute(
                "UPDATE scrape_jobs SET status='completed', total_found=?, profitable_count=?, completed_at=? WHERE id=?",
                (total_found, profitable, datetime.now().isoformat(), job_id)
            )
            await db.commit()

        await broadcast_ws("scrape_completed", {
            "job_id": job_id,
            "total_found": total_found,
            "total_skipped": total_skipped,
            "profitable": profitable,
            "mode": "smart",
            "filters": {"min_favorites": min_favorites, "min_views": min_views}
        })
        await log_activity("smart_scrape_complete",
            f"Akilli kazima bitti: {total_found} kaydedildi, {total_skipped} atildi "
            f"(min_fav>={min_favorites}, min_views>={min_views})")

        # Basari kriteri (akilli kazima): yeterli karli urun yoksa low_yield sinyali.
        if profitable < SCRAPE_SUCCESS_MIN_PROFITABLE:
            await log_activity(
                "low_yield",
                f"Dusuk verim (akilli): {profitable} karli (<{SCRAPE_SUCCESS_MIN_PROFITABLE}), toplam {total_found}",
                "warning",
            )

    except Exception as e:
        await log_activity("smart_scrape_fatal", f"Fatal hata: {str(e)}", "error")
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute("UPDATE scrape_jobs SET status='error' WHERE id=?", (job_id,))
            await db.commit()

# Platform adi -> modul. Yeni platform eklemek icin tek yer.
_SOCIAL_MODULES = ("youtube", "tiktok", "instagram", "pinterest")


def _social_module(platform: str):
    if platform not in _SOCIAL_MODULES:
        return None
    import importlib
    return importlib.import_module(f"social.{platform}")


@app.get("/api/social/status")
async def social_status():
    """
    Hangi platform bagli, hangisi degil ve NEDEN degil — sessiz basarisizlik olmasin.
    Belirtecler dondurulmez, sadece bagli/degil bilgisi.
    """
    from social import oauth_store
    durumlar = {}
    for ad in _SOCIAL_MODULES:
        modul = _social_module(ad)
        durumlar[ad] = modul.status() if modul else {}
    return {"platforms": oauth_store.connected_platforms(), "detay": durumlar}


@app.get("/api/social/{platform}/start")
async def social_start(platform: str):
    """
    Platformun izin baglantisini uretir. Giris KULLANICININ kendi tarayicisinda
    yapilir; sifre hicbir zaman bu sisteme girilmez/saklanmaz.
    """
    modul = _social_module(platform)
    if modul is None:
        return JSONResponse({"error": f"bilinmeyen platform: {platform}"}, status_code=404)

    redirect_uri = os.getenv(f"{platform.upper()}_REDIRECT_URI", modul.DEFAULT_REDIRECT)
    url = modul.auth_url(redirect_uri)
    if not url:
        return JSONResponse({"error": modul.status()["reason"],
                             "redirect_uri": redirect_uri}, status_code=503)
    return {"auth_url": url, "redirect_uri": redirect_uri,
            "not": "Bu baglantiyi kendi tarayicinizda acin ve izin verin."}


@app.get("/api/social/{platform}/callback")
async def social_callback(platform: str, code: str = "", error: str = ""):
    """Platformun geri dondugu adres. Yetki kodunu belirtece cevirir."""
    modul = _social_module(platform)
    if modul is None:
        return HTMLResponse("<h3>Bilinmeyen platform</h3>", status_code=404)
    if error:
        return HTMLResponse(f"<h3>Baglanti iptal edildi</h3><p>{error}</p>", status_code=400)
    if not code:
        return HTMLResponse("<h3>Yetki kodu gelmedi</h3>", status_code=400)

    redirect_uri = os.getenv(f"{platform.upper()}_REDIRECT_URI", modul.DEFAULT_REDIRECT)
    ok, message = await asyncio.to_thread(modul.exchange_code, code, redirect_uri)
    await log_activity("social_connect", f"{platform}: {message}", "info" if ok else "error")
    return HTMLResponse(
        f"<h3>{platform} {'baglandi' if ok else 'baglanamadi'}</h3><p>{message}</p>"
        "<p>Bu sekmeyi kapatabilirsiniz.</p>", status_code=200 if ok else 400)


def _youtube_redirect_uri() -> str:
    """
    Yonlendirme adresi ISTEKTEN TURETILMEZ. Google, Cloud Console'a kayitli adresle
    birebir karsilastirir: '127.0.0.1' ile 'localhost' ayni sayilmaz ve
    redirect_uri_mismatch hatasi verir. Bu yuzden sabit (env ile degistirilebilir).
    """
    from social.youtube import DEFAULT_REDIRECT
    return os.getenv("YOUTUBE_REDIRECT_URI", DEFAULT_REDIRECT)


@app.get("/api/social/youtube/start")
async def social_youtube_start(request: Request):
    """
    Google izin baglantisini uretir. Giris KULLANICININ kendi tarayicisinda
    yapilir; sifre hicbir zaman bu sisteme girilmez/saklanmaz.
    """
    from social import youtube
    redirect_uri = _youtube_redirect_uri()
    url = youtube.auth_url(redirect_uri)
    if not url:
        return JSONResponse({
            "error": "YOUTUBE_CLIENT_ID/YOUTUBE_CLIENT_SECRET tanimli degil",
            "nasil": ("Google Cloud'da bir proje acip 'YouTube Data API v3'u etkinlestirin, "
                      "OAuth istemcisi (Web application) olusturun ve yetkili yonlendirme "
                      f"adresi olarak {redirect_uri} girin."),
        }, status_code=503)
    return {"auth_url": url, "redirect_uri": redirect_uri,
            "not": "Bu baglantiyi kendi tarayicinizda acin ve izin verin."}


@app.get("/api/social/youtube/callback")
async def social_youtube_callback(request: Request, code: str = "", error: str = ""):
    """Google'in geri dondugu adres. Kodu yenileme belirtecine cevirir."""
    from social import youtube
    if error:
        return HTMLResponse(f"<h3>YouTube baglantisi iptal edildi</h3><p>{error}</p>", status_code=400)
    if not code:
        return HTMLResponse("<h3>Yetki kodu gelmedi</h3>", status_code=400)

    # Kod takasinda da AYNI adres kullanilmali, yoksa Google reddeder.
    redirect_uri = _youtube_redirect_uri()
    ok, message = await asyncio.to_thread(youtube.exchange_code, code, redirect_uri)
    await log_activity("social_connect", f"YouTube: {message}", "info" if ok else "error")
    return HTMLResponse(
        f"<h3>{'YouTube baglandi' if ok else 'Baglanti basarisiz'}</h3><p>{message}</p>"
        "<p>Bu sekmeyi kapatabilirsiniz.</p>", status_code=200 if ok else 400)


@app.post("/api/social/{platform}/disconnect")
async def social_disconnect(platform: str):
    """Saklanan yetkiyi siler (platformdaki hesaba dokunmaz)."""
    from social import oauth_store
    removed = oauth_store.forget_account(platform)
    if removed:
        await log_activity("social_disconnect", f"{platform} yetkisi kaldirildi")
    return {"platform": platform, "removed": removed}


@app.get("/api/campaigns")
async def list_campaigns(status: str = "", lang: str = ""):
    """Kampanya taslaklarini listeler (Hub arayuzunde insan onayi icin)."""
    where, params = [], []
    if status:
        where.append("status=?"); params.append(status)
    if lang:
        where.append("lang=?"); params.append(lang)
    sql = "SELECT * FROM campaign_drafts"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY created_at DESC LIMIT 100"

    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        try:
            cursor = await db.execute(sql, params)
        except Exception:
            return {"campaigns": []}   # tablo henuz olusmamis (ad_generate hic kosmamis)
        return {"campaigns": [dict(r) for r in await cursor.fetchall()]}


@app.post("/api/campaigns/{draft_id}/{decision}")
async def decide_campaign(draft_id: str, decision: str):
    """
    Kampanya taslagini onaylar/reddeder. INSAN KARARI — otomatik onay YOKTUR;
    yalnizca 'approved' olanlar siteye gonderilebilir.
    """
    if decision not in ("approve", "reject"):
        return JSONResponse({"error": "decision 'approve' veya 'reject' olmali"}, status_code=400)
    new_status = "approved" if decision == "approve" else "rejected"

    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute(
            "UPDATE campaign_drafts SET status=? WHERE id=?", (new_status, draft_id))
        await db.commit()
        if cursor.rowcount == 0:
            return JSONResponse({"error": "taslak bulunamadi"}, status_code=404)

    await log_activity("campaign_decision", f"{draft_id} -> {new_status}")
    return {"id": draft_id, "status": new_status}


# Kampanya turu -> sitede GERCEKTEN var olan hedef (olu link uretilmez)
_CAMPAIGN_HREF = {
    "sale": "/catalog",
    "new_arrival": "/catalog",
    "category_spotlight": "/catalog",
    "eco": "/eco-impact",
}


@app.post("/api/campaigns/push")
async def push_campaigns():
    """
    ONAYLANMIS kampanyalari cssberlin'e gonderir. Taslak/reddedilmis olanlar
    ASLA gonderilmez; site tarafi da `evidence` olmayan kaydi kabul etmez.
    """
    import requests as req

    base = os.getenv("CSSBERLIN_API_URL", "")
    api_key = os.getenv("CSSBERLIN_API_KEY")
    if not base or not api_key:
        return JSONResponse(
            {"error": "CSSBERLIN_API_URL/CSSBERLIN_API_KEY yapilandirilmamis (.env)"},
            status_code=503)
    target = base.replace("/api/products/import", "/api/campaigns/import")

    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        try:
            cursor = await db.execute(
                "SELECT * FROM campaign_drafts WHERE status='approved'")
            rows = [dict(r) for r in await cursor.fetchall()]
        except Exception:
            rows = []

    if not rows:
        return {"pushed": 0, "message": "gonderilecek ONAYLI kampanya yok"}

    payload = [{
        "source_id": r["id"], "kind": r["kind"], "lang": r["lang"],
        "headline": r["headline"], "body": r["body"], "cta": r["cta"],
        "href": _CAMPAIGN_HREF.get(r["kind"], "/catalog"),
        "evidence": r["evidence"], "active": True,
    } for r in rows]

    try:
        resp = req.post(target, json={"campaigns": payload},
                        headers={"x-api-key": api_key}, timeout=30)
        data = resp.json() if resp.status_code == 200 else {}
    except Exception as e:
        await log_activity("campaign_push_error", f"cssberlin'e ulasilamadi: {e}", "error")
        return JSONResponse({"error": f"cssberlin'e ulasilamadi: {e}"}, status_code=502)

    accepted = data.get("accepted", 0)
    rejected = data.get("rejected", [])
    await log_activity(
        "campaign_push",
        f"{accepted} kampanya siteye gonderildi"
        + (f", {len(rejected)} reddedildi: {rejected[:2]}" if rejected else ""),
        "warning" if rejected else "info")
    return {"pushed": accepted, "rejected": rejected}


@app.post("/api/scrape/smart-start")
async def smart_start_scrape(request: Request, background_tasks: BackgroundTasks):
    """
    Akilli Kazima — min_favorites ve min_views filtreleri ile.
    scrape_strategy: 'single' (hizli) | 'multi_order' (onerilir) | 'faceted' (tam-sonuca-kadar).
    Mevcut /api/scrape/start endpointi degistirilmedi, bu tamamen ayri bir yol.
    """
    body = await request.json()
    keyword = body.get("keyword", "")
    platforms = body.get("platforms", ["vinted"])
    max_pages = body.get("max_pages", 3)
    min_favorites = int(body.get("min_favorites", 5))
    min_views = int(body.get("min_views", 0))
    strategy = body.get("scrape_strategy", "single")

    if not keyword:
        return JSONResponse({"error": "Anahtar kelime gerekli"}, status_code=400)

    job_id = gen_id("SJOB")  # Smart job prefix ile

    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "INSERT INTO scrape_jobs (id, keyword, platforms, status, started_at) VALUES (?, ?, ?, 'running', ?)",
            (job_id, f"[AKILLI] {keyword} (min_fav>={min_favorites})", json.dumps(platforms), datetime.now().isoformat())
        )
        await db.commit()

    await log_activity("smart_scrape_start",
        f"Akilli kazima basladi: '{keyword}' | min_fav>={min_favorites} | min_views>={min_views} | {', '.join(platforms)}")
    await broadcast_ws("scrape_started", {
        "job_id": job_id,
        "keyword": keyword,
        "platforms": platforms,
        "mode": "smart",
        "filters": {"min_favorites": min_favorites, "min_views": min_views}
    })

    background_tasks.add_task(run_smart_scrape_job, job_id, keyword, platforms, max_pages, min_favorites, min_views, strategy)

    return {
        "job_id": job_id,
        "status": "started",
        "mode": "smart",
        "keyword": keyword,
        "platforms": platforms,
        "strategy": strategy,
        "filters": {"min_favorites": min_favorites, "min_views": min_views}
    }

@app.post("/api/scrape/category-round")
async def category_round_scrape(request: Request, background_tasks: BackgroundTasks):
    """Kategori-bazli kazima turu. category_plan.plan_next_round() ile otomatik
    kesif/somuru dengeli bir batch olusturur ve tum calisir platformlarda tarar."""
    from logic.category_plan import plan_next_round, coverage_report, all_tasks, CLOTHING_TREE, GENDERS

    body = await request.json()
    batch_size = int(body.get("batch_size", 12))
    max_pages = int(body.get("max_pages", 2))
    strategy = body.get("scrape_strategy", "multi_order")
    selected_categories = body.get("categories", [])
    selected_genders = body.get("genders", [])
    platforms = body.get("platforms", ["vinted", "kleinanzeigen", "markt", "tradera", "leboncoin"])

    coverage: dict[str, int] = {}
    async with aiosqlite.connect(DB_FILE) as db:
        rows = await db.execute("SELECT category, COUNT(*) FROM products WHERE category IS NOT NULL AND category != '' GROUP BY category")
        for cat, cnt in await rows.fetchall():
            coverage[cat] = cnt

    tasks = plan_next_round(coverage, None, batch_size=batch_size)

    if selected_categories:
        tasks = [t for t in tasks if t.category in selected_categories]
    if selected_genders:
        tasks = [t for t in tasks if t.gender in selected_genders]

    if not tasks:
        return JSONResponse({"error": "Filtrelerle eslesen gorev yok"}, status_code=400)

    job_id = gen_id("CJOB")
    task_queries = [{"query": t.query, "category": t.category, "gender": t.gender,
                     "reason": t.reason, "priority": t.priority} for t in tasks]

    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "INSERT INTO scrape_jobs (id, keyword, platforms, status, started_at) VALUES (?, ?, ?, 'running', ?)",
            (job_id, f"[KATEGORİ] {len(tasks)} gorev", json.dumps(platforms), datetime.now().isoformat()))
        await db.commit()

    await log_activity("category_round_start",
        f"Kategori turu basladi: {len(tasks)} gorev, {len(platforms)} platform, strateji={strategy}")
    await broadcast_ws("scrape_started", {
        "job_id": job_id, "mode": "category_round",
        "tasks": task_queries, "platforms": platforms})

    background_tasks.add_task(_run_category_round, job_id, tasks, platforms, max_pages, strategy)

    report = coverage_report(coverage)
    return {"job_id": job_id, "status": "started", "mode": "category_round",
            "tasks": task_queries, "platforms": platforms, "coverage": report}


async def _run_category_round(job_id: str, tasks, platforms: list,
                              max_pages: int, strategy: str):
    """Arka planda kategori turunun tum gorevlerini sirayla calistirir."""
    from logic.quality_filter import should_keep
    total_found = 0
    total_kept = 0
    profitable = 0

    try:
        for i, task in enumerate(tasks):
            for platform in platforms:
                try:
                    await broadcast_ws("scrape_progress", {
                        "job_id": job_id, "platform": platform,
                        "task_index": i + 1, "task_total": len(tasks),
                        "query": task.query, "category": task.category,
                        "gender": task.gender, "status": "scraping"})

                    products = await collect_products(platform, task.query, max_pages, strategy, job_id)
                    await _talep_kaydet(platform, task.query, job_id, products)

                    for prod in products:
                        total_found += 1
                        if not should_keep(prod.get("title"), prod.get("description"),
                                           prod.get("condition"), prod.get("brand")):
                            continue

                        prod_id = gen_id("PROD")
                        analysis = analyze_profit(prod, platform)
                        source_url = prod.get("url", "")

                        async with aiosqlite.connect(DB_FILE) as db:
                            try:
                                if source_url:
                                    cursor = await db.execute("SELECT id FROM products WHERE source_url=?", (source_url,))
                                    existing = await cursor.fetchone()
                                    if existing:
                                        await db.execute(
                                            "UPDATE products SET price=?, updated_at=?, source_status='active' WHERE source_url=?",
                                            (prod.get("price", 0), datetime.now().isoformat(), source_url))
                                        await db.commit()
                                        total_kept += 1
                                        continue

                                await db.execute("""
                                    INSERT INTO products
                                    (id, source_platform, source_url, source_id, title, description,
                                     price, currency, brand, size, color, condition, category,
                                     images_json, estimated_sell_price, profit_margin, profit_euro,
                                     total_cost, recommendation, best_sell_platform, shipping_cost,
                                     platform_fee, arbitrage_json,
                                     views, favorites, scraped_at, status)
                                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                                """, (
                                    prod_id, platform, source_url, prod.get("source_id"),
                                    prod.get("title"), prod.get("description"),
                                    prod.get("price", 0), prod.get("currency", "EUR"),
                                    prod.get("brand"), prod.get("size"), prod.get("color"),
                                    prod.get("condition"), task.category,
                                    json.dumps(prod.get("images", [])),
                                    analysis.get("estimated_sell_price"),
                                    analysis.get("profit_margin"),
                                    analysis.get("profit_euro"),
                                    analysis.get("total_cost"),
                                    analysis.get("recommendation"),
                                    analysis.get("best_sell_platform"),
                                    analysis.get("shipping_cost", 0),
                                    analysis.get("platform_fee", 0),
                                    json.dumps(analysis.get("arbitrage", [])),
                                    prod.get("views", 0), prod.get("favorites", 0),
                                    datetime.now().isoformat(), "scraped"))
                                await db.commit()
                                total_kept += 1
                                if analysis.get("recommendation") == "buy":
                                    profitable += 1
                            except Exception:
                                pass

                except Exception as e:
                    await log_activity("category_round_error",
                        f"{platform}/{task.query}: {str(e)[:120]}", "error")

        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute(
                "UPDATE scrape_jobs SET status='completed', total_found=?, profitable_count=?, completed_at=? WHERE id=?",
                (total_found, profitable, datetime.now().isoformat(), job_id))
            await db.commit()

        await log_activity("category_round_done",
            f"Kategori turu bitti: {total_found} bulundu, {total_kept} kaydedildi (kalite filtreli), {profitable} karli")
        await broadcast_ws("scrape_completed", {
            "job_id": job_id, "mode": "category_round",
            "total_found": total_found, "kept": total_kept, "profitable": profitable})

    except Exception as e:
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute(
                "UPDATE scrape_jobs SET status='failed', error_log=?, completed_at=? WHERE id=?",
                (str(e)[:500], datetime.now().isoformat(), job_id))
            await db.commit()
        await log_activity("category_round_fail", str(e)[:200], "error")


@app.get("/api/scrape/category-coverage")
async def category_coverage():
    """Kategori kapsama karnesi — UI icin."""
    from logic.category_plan import coverage_report
    coverage: dict[str, int] = {}
    async with aiosqlite.connect(DB_FILE) as db:
        rows = await db.execute("SELECT category, COUNT(*) FROM products WHERE category IS NOT NULL AND category != '' GROUP BY category")
        for cat, cnt in await rows.fetchall():
            coverage[cat] = cnt
    return coverage_report(coverage)


@app.get("/api/scrape/status/{job_id}")
async def scrape_status(job_id: str):
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM scrape_jobs WHERE id=?", (job_id,))
        row = await cursor.fetchone()
        if not row:
            return JSONResponse({"error": "Job bulunamadi"}, status_code=404)
        cols = [d[0] for d in cursor.description]
        return dict(zip(cols, row))

@app.get("/api/products")
async def api_products(status: str = "", platform: str = "", limit: int = 50, offset: int = 0):
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        query = "SELECT * FROM products WHERE 1=1"
        params = []
        if status:
            query += " AND status=?"
            params.append(status)
        if platform:
            query += " AND source_platform=?"
            params.append(platform)
        query += f" ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        cursor = await db.execute(query, params)
        cols = [d[0] for d in cursor.description]
        products = [dict(zip(cols, row)) for row in await cursor.fetchall()]
    return {"products": products, "count": len(products)}

@app.get("/api/product/{product_id}")
async def api_product(product_id: str):
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM products WHERE id=?", (product_id,))
        row = await cursor.fetchone()
        if not row:
            return JSONResponse({"error": "Urun bulunamadi"}, status_code=404)
        cols = [d[0] for d in cursor.description]
        return dict(zip(cols, row))

@app.post("/api/product/add-by-url")
async def add_product_by_url(request: Request):
    """URL ile urun ekle - soerfte balik tutma modu"""
    import requests as req
    from bs4 import BeautifulSoup

    body = await request.json()
    url = body.get("url", "").strip()
    if not url:
        return JSONResponse({"status": "error", "error": "URL gerekli"}, status_code=400)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
        "Accept-Language": "de-DE,de;q=0.9",
    }

    # Platform tespit
    platform = "unknown"
    if "vinted" in url: platform = "vinted"
    elif "ebay" in url: platform = "ebay"
    elif "kleinanzeigen" in url: platform = "kleinanzeigen"
    elif "willhaben" in url: platform = "willhaben"
    elif "sellpy" in url: platform = "sellpy"
    elif "tradera" in url: platform = "tradera"
    elif "leboncoin" in url: platform = "leboncoin"

    title = ""
    price = 0.0
    description = ""
    images = []
    brand = ""

    try:
        # Tum platformlar icin: HTML + JSON-LD + OG tag destegi
        resp = req.get(url, headers=headers, timeout=15, allow_redirects=True)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            color = ""
            category = ""

            # 1) JSON-LD (en guvenilir - Vinted, eBay, Kleinanzeigen destekler)
            ld_script = soup.find("script", type="application/ld+json")
            if ld_script:
                try:
                    ld_data = json.loads(ld_script.text)
                    if isinstance(ld_data, list):
                        ld_data = next((d for d in ld_data if d.get("@type") == "Product"), ld_data[0] if ld_data else {})
                    title = ld_data.get("name", "")
                    description = ld_data.get("description", "")[:500]
                    brand_data = ld_data.get("brand", {})
                    brand = brand_data.get("name", "") if isinstance(brand_data, dict) else str(brand_data)
                    color = ld_data.get("color", "")
                    category = ld_data.get("category", "")
                    img_data = ld_data.get("image", "")
                    if isinstance(img_data, list):
                        images = img_data[:5]
                    elif img_data:
                        images = [img_data]
                    offers = ld_data.get("offers", {})
                    if isinstance(offers, list):
                        offers = offers[0] if offers else {}
                    price = float(offers.get("price", 0))
                except Exception:
                    pass

            # 2) OG tags (fallback)
            if not title:
                og_title = soup.find("meta", property="og:title")
                title = og_title["content"] if og_title else (soup.title.text.strip() if soup.title else "")
            if not description:
                og_desc = soup.find("meta", property="og:description")
                description = og_desc["content"][:500] if og_desc else ""
            if price <= 0:
                og_price = soup.find("meta", property="product:price:amount")
                if og_price:
                    try: price = float(og_price.get("content", "0").replace(",", "."))
                    except: pass
            if not images:
                og_img = soup.find("meta", property="og:image")
                if og_img:
                    images = [og_img["content"]]

        if not title:
            return JSONResponse({"status": "error", "error": "Urun bilgileri cekilemedi"})

        # DB'ye kaydet
        prod_id = gen_id("PROD")
        analysis = analyze_profit({"price": price, "url": url}, platform)

        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute("""
                INSERT INTO products
                (id, source_platform, source_url, title, description, price, currency,
                 brand, images_json, estimated_sell_price, profit_margin, profit_euro,
                 total_cost, recommendation, best_sell_platform, shipping_cost,
                 platform_fee, arbitrage_json, scraped_at, status)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                prod_id, platform, url, title, description, price, "EUR",
                brand, json.dumps(images),
                analysis.get("sell_price", 0), analysis.get("margin", 0),
                analysis.get("profit", 0), analysis.get("total_cost", 0),
                analysis.get("recommendation", "skip"),
                analysis.get("best_platform", ""), analysis.get("shipping", 0),
                analysis.get("fee", 0), analysis.get("arbitrage_json", "[]"),
                datetime.now().isoformat(), "scraped"
            ))
            await db.commit()

        await log_activity("url_add", f"URL ile eklendi: {title[:50]} ({platform})")
        await broadcast_ws("url_product_added", {"product_id": prod_id, "title": title, "platform": platform})

        return {
            "status": "ok", "product_id": prod_id,
            "title": title, "price": price, "platform": platform,
            "image": images[0] if images else ""
        }
    except Exception as e:
        return JSONResponse({"status": "error", "error": str(e)[:200]})

@app.post("/api/product/{product_id}/check-source")
async def check_source(product_id: str, background_tasks: BackgroundTasks):
    """Kaynak urunun canliligini kontrol et"""
    background_tasks.add_task(check_product_source, product_id)
    return {"status": "checking", "product_id": product_id}

@app.post("/api/product/{product_id}/remove-bg")
async def remove_bg_endpoint(product_id: str, background_tasks: BackgroundTasks):
    """Urun gorsellerinin arka planini kaldir"""
    background_tasks.add_task(process_background_removal, product_id)
    return {"status": "processing", "product_id": product_id}

@app.post("/api/product/{product_id}/publish")
async def publish_product(product_id: str, request: Request):
    """Urunu cssberlin.de'ye gercek olarak yayinla"""
    import requests as req

    body = await request.json()
    target = body.get("target", "cssberlin")
    sell_price = body.get("sell_price")
    category_slug = body.get("category_slug")
    condition = body.get("condition", "good")
    image_type = body.get("image_type", "processed")

    # Urun bilgilerini cek
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM products WHERE id=?", (product_id,))
        row = await cursor.fetchone()
        if not row:
            return JSONResponse({"error": "Urun bulunamadi"}, status_code=404)
        cols = [d[0] for d in cursor.description]
        product = dict(zip(cols, row))

    # ZORUNLU KONTROLLER — bypass YOKTUR.
    # Google Lens ham resimleri eslestirir, Ingilizce baslik Almanca siteyi bozar.
    eksikler = []
    if not product.get("seo_title"):
        eksikler.append("SEO basligi yok → once POST /api/product/{id}/generate-seo")
    if not product.get("seo_description"):
        eksikler.append("SEO aciklamasi yok → once POST /api/product/{id}/generate-seo")
    processed = product.get("processed_images_json") or "[]"
    if processed == "[]":
        eksikler.append("Islenmis gorsel yok → once POST /api/product/{id}/remove-bg (BG kaldir + watermark + organik varyasyon)")
    if eksikler:
        return JSONResponse({
            "status": "error",
            "error": "YAYIN ENGELLENDI — zorunlu adimlar tamamlanmamis",
            "missing": eksikler,
        }, status_code=400)

    # Gorselleri gercek byte'lar olarak topla - cssberlin'in backend'i
    # TATANGA'nin localhost'una hicbir zaman erisemez, bu yuzden URL
    # paylasmiyoruz, gercek dosya icerigini multipart ile gonderiyoruz.
    image_uploads = []  # list of (filename, bytes, content_type)

    def _content_type_for(path_str: str) -> str:
        lower = path_str.lower()
        if lower.endswith(".png"):
            return "image/png"
        if lower.endswith(".webp"):
            return "image/webp"
        return "image/jpeg"

    if image_type == "processed" and product.get("processed_images_json") and product["processed_images_json"] != "[]":
        for img in json.loads(product["processed_images_json"]):
            if img.startswith("/data/"):
                local_path = DATA_DIR / img[len("/data/"):]
                if local_path.is_file():
                    image_uploads.append((local_path.name, local_path.read_bytes(), _content_type_for(str(local_path))))
            else:
                # Gecmis platform gorseli (ham kaynak URL'si) - indirip gercek byte'i gonder.
                try:
                    dl = req.get(img, timeout=15)
                    if dl.status_code == 200:
                        image_uploads.append((img.rsplit("/", 1)[-1][:60] or "image.jpg", dl.content, _content_type_for(img)))
                except req.RequestException:
                    pass
    else:
        for img in json.loads(product.get("images_json", "[]")):
            try:
                dl = req.get(img, timeout=15)
                if dl.status_code == 200:
                    image_uploads.append((img.rsplit("/", 1)[-1][:60] or "image.jpg", dl.content, _content_type_for(img)))
            except req.RequestException:
                pass

    image_uploads = image_uploads[:8]

    if not image_uploads:
        return JSONResponse({"status": "error", "error": "Gorsel bulunamadi oder konnte nicht gelesen werden"}, status_code=400)

    # Satis fiyatini belirle.
    # Oncelik: istekte gelen > kullanicinin elle girdigi > otomatik tahmin.
    # Vitrine giden fiyat her zaman yuvarlanir (183.31 degil 184.90).
    if not sell_price:
        sell_price = (product.get("manual_price")
                      or product.get("estimated_sell_price")
                      or (product.get("price", 0) * 1.5))
    if _pricing is not None:
        sell_price = _pricing.yuvarla(float(sell_price))

    CSSBERLIN_API_URL = os.getenv("CSSBERLIN_API_URL")
    CSSBERLIN_API_KEY = os.getenv("CSSBERLIN_API_KEY")

    if not CSSBERLIN_API_URL or not CSSBERLIN_API_KEY:
        return JSONResponse({
            "status": "error",
            "error": "CSSBERLIN_API_URL/CSSBERLIN_API_KEY sind nicht konfiguriert (.env fehlt)."
        }, status_code=500)

    # GPSR (AB Urun Guvenligi Tuzugu, DE'de 19.02.2026'dan beri tam etkili):
    # uretici adi/adresi ve iletisim bilgisi ALIM ONCESI ilanda gorunmeli.
    # Kayitta not yoksa (eski urunler) yayin aninda hesaplanir — hicbir urun
    # bu bilgi olmadan siteye cikmasin.
    aciklama = product.get("seo_description") or product.get("description", "") or ""
    gpsr_note = product.get("gpsr_note") or ""
    if not gpsr_note and _condition_intel:
        try:
            gpsr_note = _condition_intel.analyze(
                title=product.get("title", "") or "",
                description=aciklama,
                raw_condition=product.get("condition", "") or "",
                brand=product.get("brand", "") or "",
                known_brands=await _known_brands(),
            ).gpsr_note
        except Exception:
            gpsr_note = ""
    if gpsr_note and gpsr_note not in aciklama:
        aciklama = f"{aciklama}\n\n{gpsr_note}".strip()

    if not category_slug:
        blob = f"{product.get('title','')} {product.get('seo_title','')} {product.get('category','')}".lower()
        if any(w in blob for w in ("herren", "herr ", "men ", "homme", "uomo", " man ")):
            category_slug = "herren"
        elif any(w in blob for w in ("kinder", "kids", "enfant", "bambino", "barn")):
            category_slug = "kinder"
        else:
            category_slug = "damen"

    form_fields = {
        "title": product.get("seo_title") or product.get("title", "Urun"),
        "description": aciklama,
        "price": str(float(sell_price)),
        "brand": product.get("brand") or "",
        "size": product.get("size") or "",
        "condition": condition,
        "category_slug": category_slug,
        "source_platform": product.get("source_platform") or "",
        "source_url": product.get("source_url") or "",
        "hub_product_id": product_id,
    }
    multipart_files = [
        ("images", (filename, content, content_type))
        for filename, content, content_type in image_uploads
    ]

    try:
        resp = req.post(
            CSSBERLIN_API_URL,
            data=form_fields,
            files=multipart_files,
            headers={"x-api-key": CSSBERLIN_API_KEY},
            timeout=60
        )

        if resp.status_code == 200:
            data = resp.json()
            if data.get("success"):
                cssberlin_id = data.get("productId", "")

                # DB guncelle
                async with aiosqlite.connect(DB_FILE) as db:
                    await db.execute(
                        "UPDATE products SET status='published', cssberlin_id=?, updated_at=? WHERE id=?",
                        (cssberlin_id, datetime.now().isoformat(), product_id)
                    )
                    await db.commit()

                await log_activity("publish", f"CSSberlin'e yayinlandi: {product.get('title', '')[:40]} -> {cssberlin_id}")
                await broadcast_ws("product_published", {
                    "product_id": product_id,
                    "cssberlin_id": cssberlin_id,
                    "target": "cssberlin"
                })

                return {
                    "status": "published",
                    "product_id": product_id,
                    "cssberlin_id": cssberlin_id,
                    "duplicate": data.get("duplicate", False),
                    "target": target
                }
            else:
                return JSONResponse({
                    "status": "error",
                    "error": data.get("error", "CSSberlin API hatasi")
                }, status_code=400)
        else:
            error_msg = f"CSSberlin API HTTP {resp.status_code}"
            try:
                error_msg = resp.json().get("error", error_msg)
            except:
                pass
            return JSONResponse({
                "status": "error",
                "error": error_msg
            }, status_code=resp.status_code)

    except req.ConnectionError:
        # CSSberlin calismiyor - urun GERCEKTE hicbir yere gitmedi. Bunu
        # "published" olarak isaretlemek yaniltici olurdu (kullanici gercekten
        # yayinda saniyordu) - ayirt edilebilir ayri bir durum kullaniyoruz.
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute(
                "UPDATE products SET status='local_only', updated_at=? WHERE id=?",
                (datetime.now().isoformat(), product_id)
            )
            await db.commit()

        await log_activity("publish_local", f"CSSberlin ulasilamadi, GERCEKTE yayinlanmadi: {product_id}", "warning")
        return {
            "status": "published_local_only",
            "product_id": product_id,
            "cssberlin_id": None,
            "cssberlin_reachable": False,
            "error": f"CSSberlin API ({CSSBERLIN_API_URL}) nicht erreichbar. Urun HENUZ siteye gitmedi.",
            "target": target
        }
    except Exception as e:
        await log_activity("publish_error", f"Yayin hatasi: {str(e)}", "error")
        return JSONResponse({
            "status": "error",
            "error": str(e)[:200]
        }, status_code=500)

@app.get("/api/stats")
async def api_stats():
    async with aiosqlite.connect(DB_FILE) as db:
        stats = {}
        for key, q in [
            ("total", "SELECT COUNT(*) FROM products"),
            ("scraped", "SELECT COUNT(*) FROM products WHERE status='scraped'"),
            ("profitable", "SELECT COUNT(*) FROM products WHERE recommendation='buy'"),
            ("published", "SELECT COUNT(*) FROM products WHERE status='published'"),
            ("sold", "SELECT COUNT(*) FROM products WHERE source_status='sold'"),
            ("active_jobs", "SELECT COUNT(*) FROM scrape_jobs WHERE status='running'"),
            ("bg_processed", "SELECT COUNT(*) FROM products WHERE bg_removed=1"),
        ]:
            cursor = await db.execute(q)
            stats[key] = (await cursor.fetchone())[0]

        # Platform breakdown
        cursor = await db.execute(
            "SELECT source_platform, COUNT(*) as c FROM products GROUP BY source_platform"
        )
        stats["platforms"] = {row[0]: row[1] for row in await cursor.fetchall()}

    return stats

@app.get("/api/activity")
async def api_activity(limit: int = 20):
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute(
            "SELECT * FROM activity_log ORDER BY created_at DESC LIMIT ?", (limit,)
        )
        cols = [d[0] for d in cursor.description]
        return [dict(zip(cols, row)) for row in await cursor.fetchall()]

# ============================================
# SCRAPING ENGINE (Background Tasks)
# ============================================
SCRAPE_FACET_TARGET_QUALIFIED = 5  # faceted modda: bu kadar buy/watch bulununca dur

SCRAPE_DOWNLOAD_IMAGES = 6   # kazima aninda indirilecek gorsel tavani (urun basina)


async def download_product_images(product_id: str, image_urls: list, platform: str = "") -> list:
    """
    Gorselleri KAZIMA ANINDA diske indirir ve yerel yollari dondurur.

    NEDEN: Onceden yalnizca gorselin URL'si kaydediliyordu, dosya ancak yayin
    asamasinda indirilmeye calisiliyordu. Ilan bu arada kaldirilirsa platform
    gorseli de siliyor ve urun kalici olarak gorselsiz kaliyor. Gercek olculen
    durum: 2026-02-28'de kazinan urunlerin gorselleri bugun HTTP 404 —
    6 uründen 5'i bu yuzden kullanilamaz halde.

    Ayrica image_sourcing sayesinde kucuk-resim yerine bulunabilen en buyuk
    surum indirilir (video 1080 kisa kenar istiyor).
    """
    if not image_urls:
        return []

    import requests as req
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
        "Referer": "https://www.google.com/",
    }

    def _fetch(url: str):
        try:
            resp = req.get(url, headers=headers, timeout=12)
            if resp.status_code == 200 and len(resp.content) > 1000:
                return resp.content
        except Exception:
            return None
        return None

    def _work() -> list:
        saved, small, ilk_hash = [], 0, ""
        for index, url in enumerate(image_urls[:SCRAPE_DOWNLOAD_IMAGES]):
            if not url or len(url) < 10:
                continue
            data = None
            if _source_best_image is not None:
                found = _source_best_image(url, platform=platform, fetch=_fetch)
                if found:
                    data = found.data
                    small += (not found.meets_minimum)
            else:
                data = _fetch(url)
            if not data:
                continue
            # ILK gorselin icerik hash'i: ayni ilanin farkli source_id ile
            # tekrar tekrar acilmasini yakalar. Vinted ayni dosyayi her ilan
            # icin FARKLI CDN yolunda sunuyor — URL karsilastirmak ise yaramaz,
            # dosya icerigi karsilastirmak yarar (olculdu: 4 ilan, 4 farkli URL,
            # tek md5 f5fef6f00c30e5, 184686 bayt).
            if not ilk_hash:
                ilk_hash = hashlib.md5(data).hexdigest()
            target = IMAGES_RAW / f"{product_id}_{index + 1}.jpg"
            try:
                target.write_bytes(data)
                saved.append(str(target))
            except Exception:
                continue
        return [saved, small, ilk_hash]

    saved, small, ilk_hash = await asyncio.to_thread(_work)
    if ilk_hash:
        try:
            async with aiosqlite.connect(DB_FILE) as db:
                cur = await db.execute("PRAGMA table_info(products)")
                kol = {r[1] for r in await cur.fetchall()}
                if "image_hash" not in kol:
                    await db.execute("ALTER TABLE products ADD COLUMN image_hash TEXT")
                await db.execute("UPDATE products SET image_hash=? WHERE id=?",
                                 (ilk_hash, product_id))
                await db.commit()
        except Exception as e:
            print(f"[IMG HASH] {product_id}: {str(e)[:110]}")
    if saved:
        note = f"{len(saved)}/{len(image_urls[:SCRAPE_DOWNLOAD_IMAGES])} gorsel kazima aninda indirildi"
        if small:
            note += f" ({small} tanesi dusuk cozunurluk)"
        await log_activity("images_downloaded", f"{product_id}: {note}")
    elif image_urls:
        await log_activity("images_missing",
                           f"{product_id}: hicbir gorsel indirilemedi (ilan kaldirilmis olabilir)",
                           "warning")
    return saved


async def _talep_kaydet(platform: str, keyword: str, job_id: str, products: list) -> None:
    """Kazima turunda gorulen ilanlari kaydet, onceki turda olup bu turda
    OLMAYANLARI 'kaybolmus' olarak isaretle.

    NEDEN: Havuzumuz sadece AKTIF ilanlardan olusuyor — yani satilmayanlardan.
    Neyin sattigini bilmiyoruz. Arama sonucu farki bunu doldurur; tekil URL
    yoklamasi yerine (403 aliyoruz) zaten yaptigimiz aramanin ciktisini kullanir.

    Hicbir sekilde kazimayi bloklamaz: hata olursa sessizce gecer."""
    if _demand_tracker is None or not products or not job_id:
        return

    def _is():
        import sqlite3 as _sq
        db = _sq.connect(DB_FILE, timeout=30)
        try:
            db.execute("PRAGMA busy_timeout=30000")
            sidler = [p.get("source_id") for p in products if p.get("source_id")]
            _demand_tracker.tur_kaydet(db, tur_id=job_id, platform=platform,
                                       keyword=keyword, source_idler=sidler)
            return _demand_tracker.dusenleri_isle(db, tur_id=job_id,
                                                  platform=platform, keyword=keyword)
        finally:
            db.close()

    try:
        sonuc = await asyncio.to_thread(_is)
        if sonuc.get("dusenler"):
            await log_activity(
                "talep_gozlem",
                f"{platform}/{keyword}: {sonuc['dusenler']} ilan aramadan dustu "
                f"(satildi veya kaldirildi) — talep verisine islendi")
    except Exception as e:
        print(f"[TALEP] kayit atlandi ({platform}/{keyword}): {type(e).__name__}: {e}")


async def collect_products(platform: str, keyword: str, max_pages: int,
                           strategy: str, job_id: str = "") -> list:
    """
    Kazima turlerinin TEK giris noktasi.

    strategy='faceted' -> facet driver'i surer: sorgu uzayini renk/beden/siralama
    eksenlerine bolup, hedef sayida nitelikli (buy/watch) urun bulunana YA DA
    facet'ler tukenene/doygunluga ulasilana kadar tekrarlar. Platform hata
    verirse geri cekilir (agresif yeniden deneme YOK).

    Diger stratejilerde bugunku tek-turlu davranis AYNEN korunur (regresyon yok).
    Hem normal hem akilli kazima bunu cagirir -> iki mod da tutarli davranir.
    """
    if strategy != "faceted" or _drive_facets is None:
        return await scrape_platform(platform, keyword, max_pages, strategy=strategy)

    def _qualifies(product: dict) -> bool:
        return analyze_profit(product, platform).get("recommendation") in ("buy", "watch")

    drive = await _drive_facets(
        platform, keyword,
        scrape_fn=scrape_platform,
        qualifies_fn=_qualifies,
        max_pages=max_pages,
        target_qualified=SCRAPE_FACET_TARGET_QUALIFIED,
    )

    await log_activity(
        "facet_drive",
        f"{platform}: {len(drive.facets_run)} facet turu ({', '.join(drive.facets_run) or '-'}) -> "
        f"{len(drive.products)} tekil urun, {drive.qualified} nitelikli (buy/watch), "
        f"durus: {drive.stop_reason}" + (f" | hata: {drive.error}" if drive.error else ""),
        "warning" if drive.blocked else "info",
    )
    await broadcast_ws("facet_progress", {
        "job_id": job_id,
        "platform": platform,
        "facets_run": drive.facets_run,
        "found": len(drive.products),
        "qualified": drive.qualified,
        "stop_reason": drive.stop_reason,
    })
    return drive.products


async def run_scrape_job(job_id: str, keyword: str, platforms: list, max_pages: int, strategy: str = "single"):
    """Ana kazima gorevi - tum platformlari tarar.
    strategy: 'single' = standart, 'multi_order' = tum siralamalari dolas (daha fazla urun),
              'faceted' = facet driver ile tam-sonuca-kadar sur
    """
    total_found = 0
    profitable = 0

    try:
        for platform in platforms:
            try:
                await broadcast_ws("scrape_progress", {
                    "job_id": job_id,
                    "platform": platform,
                    "status": "scraping",
                    "strategy": strategy
                })

                products = await collect_products(platform, keyword, max_pages, strategy, job_id)
                await _talep_kaydet(platform, keyword, job_id, products)

                for prod in products:
                    prod_id = gen_id("PROD")
                    # Arbitrage analysis
                    analysis = analyze_profit(prod, platform)
                    source_url = prod.get("url", "")

                    async with aiosqlite.connect(DB_FILE) as db:
                        try:
                            # Check if URL already exists
                            if source_url:
                                cursor = await db.execute("SELECT id FROM products WHERE source_url=?", (source_url,))
                                existing = await cursor.fetchone()
                                if existing:
                                    # Update price/status for existing
                                    await db.execute(
                                        "UPDATE products SET price=?, updated_at=?, source_status='active' WHERE source_url=?",
                                        (prod.get("price", 0), datetime.now().isoformat(), source_url))
                                    await db.commit()
                                    total_found += 1
                                    continue

                            await db.execute("""
                                INSERT INTO products
                                (id, source_platform, source_url, source_id, title, description,
                                 price, currency, brand, size, color, condition, category,
                                 images_json, estimated_sell_price, profit_margin, profit_euro,
                                 total_cost, recommendation, best_sell_platform, shipping_cost,
                                 platform_fee, arbitrage_json,
                                 views, favorites, scraped_at, status)
                                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                            """, (
                                prod_id, platform, source_url, prod.get("source_id"),
                                prod.get("title"), prod.get("description"),
                                prod.get("price", 0), prod.get("currency", "EUR"),
                                prod.get("brand"), prod.get("size"), prod.get("color"),
                                prod.get("condition"), prod.get("category"),
                                json.dumps(prod.get("images", [])),
                                analysis.get("sell_price", 0), analysis.get("margin", 0),
                                analysis.get("profit", 0), analysis.get("total_cost", 0),
                                analysis.get("recommendation", "skip"),
                                analysis.get("best_platform", ""),
                                analysis.get("shipping", 0), analysis.get("fee", 0),
                                analysis.get("arbitrage_json", "[]"),
                                prod.get("views", 0), prod.get("favorites", 0),
                                datetime.now().isoformat(), "scraped"
                            ))
                            await db.commit()
                            await _save_condition_fields(db, prod_id, prod)
                            total_found += 1
                            if analysis.get("recommendation") == "buy":
                                profitable += 1
                        except Exception as e:
                            print(f"[DB INSERT ERROR] {platform}: {str(e)[:100]}")
                            continue

                    # Gorselleri HEMEN indir: ilan yarin kaldirilirsa gec kalinmis olur.
                    raw_paths = await download_product_images(
                        prod_id, prod.get("images", []), platform)
                    if raw_paths:
                        async with aiosqlite.connect(DB_FILE) as db:
                            await db.execute(
                                "UPDATE products SET raw_images_json=? WHERE id=?",
                                (json.dumps(raw_paths), prod_id))
                            await db.commit()

                await broadcast_ws("scrape_progress", {
                    "job_id": job_id,
                    "platform": platform,
                    "status": "done",
                    "found": len(products)
                })
                await log_activity("scrape", f"{platform}: {len(products)} urun bulundu ({keyword})")

            except Exception as e:
                await log_activity("scrape_error", f"{platform} hatasi: {str(e)}", "error")
                await broadcast_ws("scrape_error", {
                    "job_id": job_id,
                    "platform": platform,
                    "error": str(e)
                })

        # Job tamamlandi
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute(
                "UPDATE scrape_jobs SET status='completed', total_found=?, profitable_count=?, completed_at=? WHERE id=?",
                (total_found, profitable, datetime.now().isoformat(), job_id)
            )
            await db.commit()

        await broadcast_ws("scrape_completed", {
            "job_id": job_id,
            "total_found": total_found,
            "profitable": profitable
        })
        await log_activity("scrape_complete", f"Kazima tamamlandi: {total_found} urun, {profitable} karli")

        # Basari kriteri: ham sayi degil, kaliteli-buy odakli. Yeterli karli urun
        # yoksa low_yield -> diagnostician widen_search onerir (facet/dil/filtre).
        if profitable < SCRAPE_SUCCESS_MIN_PROFITABLE:
            await log_activity(
                "low_yield",
                f"Dusuk verim: {profitable} karli (<{SCRAPE_SUCCESS_MIN_PROFITABLE}), toplam {total_found} ('{keyword}')",
                "warning",
            )

        # Telegram bildirim - DEVRE DISI
        # Kazima sonuclari Telegram'a gonderilmez (kullanici tercihi)
        # Sadece /scrape komutu ile admin DM'de yanit verilir

    except Exception as e:
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute(
                "UPDATE scrape_jobs SET status='failed', error_log=? WHERE id=?",
                (str(e), job_id)
            )
            await db.commit()
        await log_activity("scrape_fail", f"Kazima basarisiz: {str(e)}", "error")

        # Kazima hatalari Telegram'a gonderilmez (kullanici tercihi)

_SLUG_TRANSLIT = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss", "Ä": "ae", "Ö": "oe", "Ü": "ue"})


def _slugify(keyword: str) -> str:
    """Anahtar kelimeyi URL path segmenti icin guvenli hale getirir (Kleinanzeigen vb.
    'bosluklu-degil-tireli' bekleyen platformlar icin). Alman ozel karakterleri translitere eder."""
    text = (keyword or "").strip().lower().translate(_SLUG_TRANSLIT)
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or "urun"


def _is_relevant(title: str, keyword: str, threshold: float = 0.7) -> bool:
    """Baslikta arama kelimesinin token'larinin yeterince gectigini dogrular.
    Bu, bir platform URL/parametre hatasi yuzunden alakasiz/varsayilan bir liste
    sayfasi donse bile o urunlerin DB'ye sessizce girmesini engelleyen savunma katmanidir.

    COK DILLI ESLEME: Vinted cok-uluslu bir pazar — Fransiz satici 'veste homme',
    Polonyali 'kurtka meska' yazar. keyword_localizer'daki TYPE_WORDS sozlugu
    kullanilarak her token'in tum dillerdeki karsiliklari kabul edilir.
    Boylece 'jacke herren' aramasinda 'Puffer Jacket Men's XL' de gecerli olur.
    """
    title_lower = (title or "").lower()
    tokens = [t for t in re.findall(r"[a-z0-9]+", (keyword or "").lower()) if len(t) > 1]
    if not tokens:
        return True

    # Her token icin esanlamli kume olustur (tum dillerdeki karsiliklar).
    # keyword_localizer._WORD_TO_CANON ve TYPE_WORDS zaten yuklenmis durumda.
    try:
        from logic.keyword_localizer import _WORD_TO_CANON, TYPE_WORDS
    except ImportError:
        _WORD_TO_CANON, TYPE_WORDS = {}, {}

    def _synonyms(tok: str) -> set[str]:
        """Bir token'in tum dillerdeki karsiliklar kumesini dondurur.
        'men' -> 'mens' -> canon 'mens' -> tum karsiliklar dahil.
        Possessive/plural: men's tokenize edilince 'men' kalir, ama
        _WORD_TO_CANON'da 'mens' var — bu yuzden tok+'s' de denenir.
        Ayrica her esanlamlinin s-li/s-siz varyanti da eklenir."""
        synonyms = {tok}
        # Ayni token'in olasi varyantlarini dene: tok, tok+'s', tok[:-1]
        candidates = [tok]
        if not tok.endswith("s"):
            candidates.append(tok + "s")     # men -> mens
        if tok.endswith("s") and len(tok) > 2:
            candidates.append(tok[:-1])       # mens -> men (baslikta "men" de gecer)
        for cand in candidates:
            canon = _WORD_TO_CANON.get(cand)
            if canon and canon in TYPE_WORDS:
                for v in TYPE_WORDS[canon].values():
                    # Cok kelimeli ifadeleri ("sac a dos") de tek kelimeye parcala
                    for part in v.lower().split():
                        if len(part) > 1:
                            synonyms.add(part)
                            # men/mens, jacket/jackets gibi varyantlari da ekle
                            if part.endswith("s") and len(part) > 2:
                                synonyms.add(part[:-1])
                            else:
                                synonyms.add(part + "s")
                synonyms.add(canon)
                synonyms.update(candidates)
                break
        return synonyms

    matched = 0
    for tok in tokens:
        syns = _synonyms(tok)
        if any(s in title_lower for s in syns):
            matched += 1

    required = len(tokens) if len(tokens) <= 2 else max(1, round(len(tokens) * threshold))
    return matched >= required


async def scrape_platform(platform: str, keyword: str, max_pages: int, strategy: str = "single") -> list:
    """Platform bazli kazima - requests + BeautifulSoup
    strategy: "single" = standart siralama, "multi_order" = tum siralamalari dolas (daha fazla urun)
    """
    import requests
    from bs4 import BeautifulSoup

    products = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    # Vinted multi-country domain haritasi
    vinted_domains = {
        "vinted":    "www.vinted.de",
        "vinted_fr": "www.vinted.fr",
        "vinted_pl": "www.vinted.pl",
        "vinted_be": "www.vinted.be",
        "vinted_uk": "www.vinted.co.uk",
        # 2026-10-16: istatistik gozlemcisinin pazarlariyla ayni ulkeler
        "vinted_it": "www.vinted.it",
        "vinted_nl": "www.vinted.nl",
        "vinted_at": "www.vinted.at",
        "vinted_es": "www.vinted.es",
        "vinted_se": "www.vinted.se",
    }

    # Yerel-dil arama: hedef site diline gore tip kelimelerini cevir (marka korunur).
    # keyword yeniden atanir -> hem dispatch hem alaka filtresi lokalize kelimeyi kullanir.
    original_keyword = keyword
    if _localize_keyword:
        localized = _localize_keyword(keyword, platform)
        if localized != keyword:
            keyword = localized
            await log_activity("keyword_localized",
                               f"{platform}: '{original_keyword}' -> '{keyword}'", "info")

    # Hiz koruyucusu: platform sogumadaysa HIC istek atma. Engelli kapiyi
    # tekrar calmak engeli uzatir — bugun eBay ve Leboncoin tam olarak boyle
    # kaybedildi (555 ardisik istek -> "Error Page", sonra saatlerce kapali).
    if _rate_guard:
        izin, sebep = await asyncio.to_thread(_rate_guard.acquire, platform)
        if not izin:
            await log_activity("rate_cooldown", f"{platform}: {sebep} — atlandi", "warning")
            await _record_platform_stat(platform, ok=False, sure=0.0, ham=0, kalan=0,
                                        engellendi=True, sebep=f"soguma: {sebep}")
            return []

    _basladi = time.time()
    _hata_sebep = ""
    try:
        if platform in vinted_domains:
            domain = vinted_domains[platform]
            products = await scrape_vinted(keyword, max_pages, headers, strategy=strategy, domain=domain)
        elif platform == "kleinanzeigen":
            products = await scrape_kleinanzeigen(keyword, max_pages, headers, strategy=strategy)
        elif platform == "ebay":
            products = await scrape_ebay(keyword, max_pages, headers, strategy=strategy)
        elif platform == "sellpy":
            products = await scrape_sellpy(keyword, max_pages, headers, strategy=strategy)
        elif platform == "willhaben":
            products = await scrape_willhaben(keyword, max_pages, headers, strategy=strategy)
        elif platform == "tradera":
            products = await scrape_tradera(keyword, max_pages, headers, strategy=strategy)
        elif platform == "leboncoin":
            products = await scrape_leboncoin(keyword, max_pages, headers, strategy=strategy)
        elif platform == "markt":
            products = await scrape_markt(keyword, max_pages, headers, strategy=strategy)
        elif platform == "depop":
            products = await scrape_depop(keyword, max_pages, headers, strategy=strategy)
        elif platform == "percentil":
            products = await scrape_percentil(keyword, max_pages, headers)
    except Exception as e:
        _hata_sebep = str(e)[:200]
        await log_activity("scrape_error", f"{platform} kazima hatasi: {str(e)}", "error")

    _ham_sayi = len(products)

    # Sonucu koruyucuya bildir: hic urun gelmediyse bu bir engel sinyalidir,
    # platform sogumaya alinir ve bir sonraki turda bosuna denenmez.
    if _rate_guard:
        engellendi_mi = _rate_guard.report(
            platform, status=200,
            body=("engel" if (_ham_sayi == 0 and not _hata_sebep) else ""),
            got_results=(_ham_sayi > 0))
        if engellendi_mi:
            await log_activity(
                "rate_block",
                f"{platform}: sonuc yok — sogumaya alindi "
                f"({int(_rate_guard.cooling(platform) // 60)} dk)", "warning")

    # Alaka filtresi: platform yanlis/varsayilan bir sayfa dondurse bile
    # (ornegin bir URL/slug hatasi yuzunden) alakasiz urunlerin DB'ye gitmesini
    # engelleyen tek noktali savunma katmani (hem run_scrape_job hem
    # run_smart_scrape_job bu fonksiyonu cagirir, ikisine de otomatik yansir).
    before_count = len(products)
    products = [p for p in products if _is_relevant(p.get("title", ""), keyword)]
    filtered_count = before_count - len(products)
    if filtered_count > 0:
        await log_activity(
            "relevance_filter",
            f"{platform}: {filtered_count} alakasiz urun elendi ('{keyword}' ile eslesmedi)",
            "warning",
        )

    # Kalite/defekt filtresi: iade riski tasiyan (defekt/kaputt/riss...) urunler
    # bize dusmesin. condition alani bos geldigi icin baslik+aciklama metninden
    # karar verilir. Tek noktali -> tum platformlar + her iki kazima modu kapsanir.
    if _should_keep:
        pre_q = len(products)
        products = [
            p for p in products
            if _should_keep(p.get("title", ""), p.get("description", ""),
                            p.get("condition"), p.get("brand"))
        ]
        q_dropped = pre_q - len(products)
        if q_dropped > 0:
            await log_activity(
                "quality_filter",
                f"{platform}: {q_dropped} defektli/dusuk kalite urun elendi (iade riski)",
                "warning",
            )

    # Durum zekasi + GPSR: quality_filter'in GORMEDIGI iki seyi olcer —
    #   (1) etiket "sehr gut" derken aciklamanin kusur saymasi (yanlis beyan),
    #   (2) AB Urun Guvenligi Tuzugu'nun (19.02.2026'dan beri DE'de tam etkili)
    #       ilanda uretici bilgisi zorunlulugu.
    # Elemeyi degil ISARETLEMEYI yapar: gpsr_note yayin sirasinda ilana eklenir.
    if _condition_intel:
        pre_c = len(products)
        kalan = []
        bilinen_markalar = await _known_brands()
        for p in products:
            v = _condition_intel.analyze(
                title=p.get("title", "") or "",
                description=p.get("description", "") or "",
                raw_condition=p.get("condition", "") or "",
                brand=p.get("brand", "") or "",
                category=p.get("category", "") or "",
                known_brands=bilinen_markalar,
            )
            kacin, _sebep = _condition_intel.should_avoid(v)
            if kacin:
                continue
            p["condition_score"] = v.score
            p["return_risk"] = v.return_risk
            # Marka alani bos gelip basliktan cozulduyse urune geri yaz:
            # yayin payload'i ve kampanya motoru da bu markadan faydalansin.
            if v.brand_source == "baslik" and not (p.get("brand") or "").strip():
                p["brand"] = v.brand_resolved
            p["gpsr_required"] = 1 if v.gpsr_required else 0
            p["gpsr_ready"] = 1 if v.gpsr_ready else 0
            p["gpsr_note"] = v.gpsr_note
            kalan.append(p)
        c_dropped = pre_c - len(kalan)
        products = kalan
        if c_dropped > 0:
            await log_activity(
                "condition_intel",
                f"{platform}: {c_dropped} urun beyan celiskisi/defekt nedeniyle elendi",
                "warning",
            )
        eksik_gpsr = sum(1 for p in products if p.get("gpsr_required") and not p.get("gpsr_ready"))
        if eksik_gpsr:
            await log_activity(
                "gpsr_gap",
                f"{platform}: {eksik_gpsr} urunde uretici belirlenemedi — ilana "
                "'Hersteller nicht ermittelbar' notu dusulecek (GPSR Art. 19)",
                "warning",
            )

    # Platform-basina kayit: hangi site ne dondurdu, ne kadar surdu, engelli mi.
    # "0 urun" ile "hic denenmedi" ve "engellendi" burada birbirinden ayrilir.
    _sebep = _hata_sebep
    if not _sebep:
        if _ham_sayi == 0:
            _sebep = "site hic sonuc dondurmedi (engel veya bos arama)"
        elif len(products) == 0:
            _sebep = f"{_ham_sayi} ham sonuc geldi ama tamami filtrelendi (alaka/kalite/durum)"
        else:
            _sebep = "ok"
    await _record_platform_stat(
        platform,
        ok=(len(products) > 0),
        sure=round(time.time() - _basladi, 2),
        ham=_ham_sayi,
        kalan=len(products),
        engellendi=(_ham_sayi == 0 and not _hata_sebep),
        sebep=_sebep,
    )

    # Talep gecmisi: filtrelerden GECEN urunler gozlem deposuna yazilir.
    # Elenen urunler yazilmaz — onlar zaten alinmayacak, istatistigi kirletir.
    if products:
        yazilan = await _write_observations(products, platform)
        if yazilan:
            await log_activity("observations",
                               f"{platform}: {yazilan} gozlem talep gecmisine yazildi", "info")

    return products

_OBS_STORE = None


def _obs_store():
    """Gozlem deposu (kategori bazli TSV + DBeaver icin SQLite indeks)."""
    global _OBS_STORE
    if _OBS_STORE is None and _ObsStore:
        _OBS_STORE = _ObsStore(DATA_DIR / "talep")
    return _OBS_STORE


# Baslikan kategori/cinsiyet cikarimi. cssberlin kategori agaciyla hizalanmis
# sade bir esleme; amac tam siniflandirma degil, ISTATISTIK icin yeterli
# kirilim uretmek. Yanlis siniflandirma "sonstige"ye duser, veri kaybolmaz.
_KAT_ISARET = {
    "jacken":  ("jacke", "jacket", "veste", "kurtka", "jas", "chaqueta", "blouson", "anorak", "parka"),
    "fleece":  ("fleece", "polaire", "polar", "sherpa"),
    "hosen":   ("hose", "pant", "trouser", "spodnie", "broek", "pantalon", "jeans"),
    "pullover": ("pullover", "sweat", "hoodie", "sweter", "trui", "sudadera"),
    "hemden":  ("hemd", "shirt", "chemise", "koszula", "camisa"),
    "schuhe":  ("schuh", "shoe", "boot", "sneaker", "chaussure", "buty"),
}
_CINS_ISARET = {
    "herren": ("herren", "homme", "men's", "mens", " men ", "heren", "herr", "meska", "hombre", "erkek"),
    "damen":  ("damen", "femme", "women", "dames", " dam ", "damska", "mujer", "kadin"),
    "kinder": ("kinder", "enfant", "kids", "barn", "dziecie", "nino", "cocuk"),
}


def _kategori_cikar(title: str) -> tuple[str, str]:
    """(kategori, cinsiyet) — basliktan, cok dilli isaretlerle."""
    t = f" {(title or '').lower()} "
    kat = "sonstige"
    for ad, isaretler in _KAT_ISARET.items():
        if any(i in t for i in isaretler):
            kat = ad
            break
    cins = "unisex"
    for ad, isaretler in _CINS_ISARET.items():
        if any(i in t for i in isaretler):
            cins = ad
            break
    return kat, cins


async def _write_observations(products: list, platform: str) -> int:
    """
    Kazinan urunleri gozlem deposuna yazar (satir ~93 bayt).

    NEDEN AYRI DEPO: products tablosu gorsel/aciklama/JSON tasiyor ve urun
    yayindan kalkinca temizleniyor. Talep istatistigi ise GECMIS gerektirir —
    silinen urunun satip satmadigi bilgisi en degerli veridir. Gozlem deposu
    ekleme-only oldugu icin bu gecmis hic kaybolmaz.
    """
    depo = _obs_store()
    if not depo or not _obs_from_product or not products:
        return 0
    try:
        gozlemler = []
        for p in products:
            kat, cins = _kategori_cikar(p.get("title", ""))
            eur = p.get("price")
            if _currency and (p.get("currency") or "EUR").upper() != "EUR":
                r = _rates()
                eur = _currency.to_eur(p.get("price") or 0,
                                       (p.get("currency") or "EUR").upper(), r) if r else None
            if eur is None:
                continue     # kuru bilinmeyen urun istatistigi bozar
            gozlemler.append(_obs_from_product(
                {**p, "source_platform": platform,
                 "source_id": p.get("source_id"),
                 "scraped_at": datetime.now().isoformat()},
                category=kat, gender=cins, price_eur=float(eur)))
        if gozlemler:
            await asyncio.to_thread(depo.append_many, gozlemler)
        return len(gozlemler)
    except Exception as e:
        print(f"[OBS] {platform}: {str(e)[:130]}")
        return 0


async def _record_platform_stat(platform: str, *, ok: bool, sure: float,
                                ham: int, kalan: int, engellendi: bool = False,
                                sebep: str = "") -> None:
    """
    Platform-basina kazima sonucunu kaydeder. `platform_stats` tablosu sistemde
    ZATEN tanimliydi ama hicbir yerde YAZILMIYORDU — yani "hangi site calisiyor,
    hangisi engelli, hangisi bos donuyor" sorusunun cevabi hic tutulmuyordu.
    Her platform ayri satirda birikir; boylece bir site sessizce olduginde
    (Vinted'in bugun oldugu gibi) bu rakamlardan gorulur.
    """
    try:
        async with aiosqlite.connect(DB_FILE) as db:
            cur = await db.execute("PRAGMA table_info(platform_stats)")
            kol = {r[1] for r in await cur.fetchall()}
            for ad, tip in (("raw_count", "INTEGER"), ("kept_count", "INTEGER"),
                            ("last_reason", "TEXT")):
                if ad not in kol:
                    await db.execute(f"ALTER TABLE platform_stats ADD COLUMN {ad} {tip}")

            cur = await db.execute("SELECT id FROM platform_stats WHERE platform=?", (platform,))
            row = await cur.fetchone()
            simdi = datetime.now().isoformat()
            if row:
                await db.execute(
                    "UPDATE platform_stats SET success_count=success_count+?, "
                    "fail_count=fail_count+?, avg_response_time=(avg_response_time+?)/2, "
                    "last_scrape=?, is_blocked=?, raw_count=?, kept_count=?, last_reason=? "
                    "WHERE id=?",
                    (1 if ok else 0, 0 if ok else 1, sure, simdi,
                     1 if engellendi else 0, ham, kalan, sebep[:200], row[0]))
            else:
                await db.execute(
                    "INSERT INTO platform_stats (platform, success_count, fail_count, "
                    "avg_response_time, last_scrape, is_blocked, raw_count, kept_count, last_reason) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    (platform, 1 if ok else 0, 0 if ok else 1, sure, simdi,
                     1 if engellendi else 0, ham, kalan, sebep[:200]))
            await db.commit()
    except Exception as e:
        print(f"[PLATFORM STAT] {platform}: {str(e)[:120]}")


_RATES_CACHE = None


def _rates():
    """Gunluk ECB kuru — surec omru boyunca bir kez cekilir, diske onbelleklenir.
    Kur kaynagi (ecb/cache/static) her zaman rapor edilebilir durumda tutulur;
    statik tahmine dusuldugunde kar hesabinin sapabilecegi acikca bilinir."""
    global _RATES_CACHE
    if _RATES_CACHE is None and _currency:
        def _getir(u: str) -> str:
            import requests as _rq
            return _rq.get(u, timeout=20).text
        _RATES_CACHE = _currency.load_rates(DATA_DIR / "ecb_kur.json", fetcher=_getir)
        print(f"[KUR] {_currency.describe(_RATES_CACHE)}")
    return _RATES_CACHE


_KNOWN_BRANDS_CACHE: list[str] | None = None


async def _known_brands() -> list[str]:
    """
    GPSR uretici cozumu icin marka sozlugu — UYDURULMAZ, DB'deki GERCEK
    markalardan turetilir. Bazi platformlar (eBay) brand alanini bos birakiyor
    ama uretici basliktan okunabiliyor; bu liste o eslemeyi mumkun kilar.
    Surec omru boyunca bir kez okunur.
    """
    global _KNOWN_BRANDS_CACHE
    if _KNOWN_BRANDS_CACHE is not None:
        return _KNOWN_BRANDS_CACHE
    markalar: list[str] = []
    try:
        async with aiosqlite.connect(DB_FILE) as db:
            cur = await db.execute(
                "SELECT brand, COUNT(*) n FROM products "
                "WHERE brand IS NOT NULL AND TRIM(brand) <> '' "
                "GROUP BY LOWER(brand) HAVING n >= 2 ORDER BY n DESC LIMIT 800")
            markalar = [r[0].strip() for r in await cur.fetchall() if r[0] and len(r[0].strip()) >= 3]
    except Exception as e:
        print(f"[BRANDS] marka sozlugu okunamadi: {str(e)[:120]}")
    _KNOWN_BRANDS_CACHE = markalar
    print(f"[BRANDS] {len(markalar)} gercek marka yuklendi (GPSR uretici cozumu icin)")
    return markalar


_CONDITION_COLUMNS_READY = False


async def _ensure_condition_columns(db) -> None:
    """products'a additive durum/GPSR kolonlari ekler (yoksa). Veri kaybi yok.
    Surec omru boyunca bir kez calisir — her INSERT'te PRAGMA maliyeti olmasin."""
    global _CONDITION_COLUMNS_READY
    if _CONDITION_COLUMNS_READY:
        return
    cur = await db.execute("PRAGMA table_info(products)")
    cols = {r[1] for r in await cur.fetchall()}
    for ad, tip in (("condition_score", "INTEGER"), ("return_risk", "TEXT"),
                    ("gpsr_required", "INTEGER"), ("gpsr_ready", "INTEGER"),
                    ("gpsr_note", "TEXT")):
        if ad not in cols:
            await db.execute(f"ALTER TABLE products ADD COLUMN {ad} {tip}")
    await db.commit()
    _CONDITION_COLUMNS_READY = True


async def _save_condition_fields(db, prod_id: str, prod: dict) -> None:
    """scrape_platform'un isaretledigi durum/GPSR alanlarini kaydeder.
    INSERT kolon listelerini genisletmek yerine ayri UPDATE: iki ayri kazima
    yolunun (keyword/smart) INSERT'lerini degistirme riski alinmaz."""
    if "gpsr_note" not in prod:
        return
    try:
        await _ensure_condition_columns(db)
        await db.execute(
            "UPDATE products SET condition_score=?, return_risk=?, "
            "gpsr_required=?, gpsr_ready=?, gpsr_note=? WHERE id=?",
            (prod.get("condition_score"), prod.get("return_risk"),
             prod.get("gpsr_required"), prod.get("gpsr_ready"),
             prod.get("gpsr_note"), prod_id))
        await db.commit()
    except Exception as e:
        print(f"[CONDITION SAVE] {prod_id}: {str(e)[:120]}")


# ---- PLATFORM SCRAPERS ----

_CHROME_MAJOR_VERSION_CACHE: int | None = None


def _installed_chrome_major_version() -> int | None:
    """Windows'ta kurulu Chrome.exe'nin dosya surumunden major numarayi okur
    (ornegin '150.0.7871.182' -> 150). undetected_chromedriver'in kendi
    otomatik tespiti bazen bir surum geride/ileride bir driver indirip
    'session not created: version mismatch' hatasina yol aciyor - bunu
    kurulu tarayiciya sabitleyerek onluyoruz. Bulunamazsa None doner (uc
    kendi varsayilan tespitine geri duser)."""
    global _CHROME_MAJOR_VERSION_CACHE
    if _CHROME_MAJOR_VERSION_CACHE is not None:
        return _CHROME_MAJOR_VERSION_CACHE
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for path in candidates:
        try:
            if os.path.exists(path):
                import subprocess
                result = subprocess.run(
                    ["powershell", "-NoProfile", "-Command",
                     f"(Get-Item '{path}').VersionInfo.FileVersion"],
                    capture_output=True, text=True, timeout=10,
                )
                version = result.stdout.strip()
                if version:
                    major = int(version.split(".")[0])
                    _CHROME_MAJOR_VERSION_CACHE = major
                    return major
        except Exception:
            continue
    return None


def _open_vinted_browser(domain: str):
    """Vinted icin gercek bir Chrome oturumu acar ve bot-korumasi sayfasinin
    dogal olarak cozulmesini bekler. NOT headless: headless=new modu Vinted'in
    Datadome korumasi tarafindan tutarli sekilde tespit edilip sonsuza kadar
    'Bir dakika lutfen...' sayfasinda tutuluyor (dogrulanmis) - gorunur pencere
    ile normal bir kullanicinin tarayicisi gibi davraniyor. Bu, kazima
    calisirken kisa sureli goze gorunur bir Chrome penceresi acilmasi demek."""
    import undetected_chromedriver as uc
    options = uc.ChromeOptions()
    options.add_argument("--window-size=1280,800")
    options.add_argument("--disable-notifications")
    chrome_major_version = _installed_chrome_major_version()
    driver = uc.Chrome(options=options, version_main=chrome_major_version)
    driver.set_page_load_timeout(25)
    driver.get(f"https://{domain}")
    # Bot-korumasi sayfasinin gecmesini cerez sayisina bakarak bekle (sabit
    # bekleme yerine) - dogrulanan surelerde 2-14 saniye arasi degisiyordu.
    for _ in range(10):
        time.sleep(1.5)
        if len(driver.get_cookies()) >= 8:
            break
    return driver


def _fetch_json_via_browser(driver, url: str, timeout_seconds: int = 20) -> dict | None:
    """API cagrisini tarayicinin kendi fetch() context'inden yapar - dogrulandi
    ki disaridan (requests kutuphanesiyle) aynen ayni cerezlerle yapilan
    cagri bile 403 aliyor (TLS/HTTP parmak izi farki), ama tarayicinin
    kendi JS ortamindan yapilan fetch() 200 donuyor. CAPTCHA otomatik asma
    degil - normal bir kullanicinin tarayicisinda calisan sayfanin zaten
    yapacagi bir istek, sadece Python'dan tetikleniyor."""
    script = """
        var callback = arguments[arguments.length - 1];
        var targetUrl = arguments[0];
        fetch(targetUrl, {credentials: "include"})
          .then(function(r) {
            var status = r.status;
            return r.text().then(function(body) { callback(status + "|" + body); });
          })
          .catch(function(e) { callback("ERROR|" + e); });
    """
    driver.set_script_timeout(timeout_seconds)
    raw = driver.execute_async_script(script, url)
    if not raw or raw.startswith("ERROR|"):
        return None
    status_str, _, body = raw.partition("|")
    try:
        status = int(status_str)
    except ValueError:
        return None
    if status != 200:
        return None
    try:
        return json.loads(body)
    except (ValueError, TypeError):
        return None


def _fetch_html_via_browser(url: str, wait_seconds: float = 4.0) -> str | None:
    """Paylasilan yardimci: bot-korumali bir sayfayi gercek (headless olmayan)
    Chrome ile acar, HTML'i dondurur, tarayiciyi kapatir. eBay/Leboncoin gibi
    duz-requests ile 403 alan ama gercek tarayicida acilan platformlar icin."""
    import undetected_chromedriver as uc
    options = uc.ChromeOptions()
    options.add_argument("--window-size=1280,800")
    options.add_argument("--disable-notifications")
    driver = uc.Chrome(options=options, version_main=_installed_chrome_major_version())
    try:
        driver.set_page_load_timeout(25)
        driver.get(url)
        time.sleep(wait_seconds)
        return driver.page_source
    except Exception:
        return None
    finally:
        driver.quit()


_VINTED_PARSER = None


def _vinted_parser():
    """Istatistik gozlemcisinin dogrulanmis katalog ayristiricisi (ops/hetzner_observer/observer.py:parse_catalog)."""
    global _VINTED_PARSER
    if _VINTED_PARSER is None:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "tatanga_observer_parser", str(BASE_DIR / "ops" / "hetzner_observer" / "observer.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _VINTED_PARSER = mod.parse_catalog
    return _VINTED_PARSER


def _vinted_fetch(domain: str, keyword: str, order: str, page: int,
                  session=None) -> tuple[dict | None, int, object]:
    """
    Vinted katalog SAYFASI (curl_cffi, Chrome TLS taklidi) -> sayfanin icindeki RSC ilan bloklari.

    2026-10-16: eski /api/v2/catalog/items ucu KALKTI (tum alan adlarinda HTTP 404, HTML hata sayfasi; ayni
    oturumla /catalog sayfasi 200 ve 96 ilan veriyordu). TATANGA'nin Vinted kazimasi bu yuzden her ulkede 0
    donuyordu. Artik istatistik gozlemcisinin kanitlanmis ayristiricisi kullanilir; donus bicimi eski API ile
    ayni ({"items": [...]}) tutuldu, scrape_vinted'in geri kalani degismedi.
    Dogrulama/engel sayfasi (kucuk yanit, ilan blogu yok) None doner -> "vinted_blocked" olarak kaydedilir.
    """
    from curl_cffi import requests as cr
    from urllib.parse import quote
    if session is None:
        session = cr.Session(impersonate="chrome")
        session.get(f"https://{domain}/", timeout=30)   # oturum cerezi
    url = f"https://{domain}/catalog?search_text={quote(keyword)}&page={page}&order={order}"
    r = session.get(url, timeout=40, headers={"Referer": f"https://{domain}/"})
    if r.status_code != 200:
        return None, r.status_code, session
    html = r.text
    blocks = html.count('\\"productItem\\":')
    if blocks == 0 and len(html) < 60_000:
        return None, 200, session          # dogrulama / engel sayfasi
    items = []
    for it in _vinted_parser()(html):
        items.append({
            "id": it["item_id"],
            "url": f"https://{domain}{it['url']}",
            "title": it.get("title") or "",
            "price": {"amount": it["price"], "currency_code": it.get("currency") or "EUR"},
            "photos": [{"url": it["thumb"]}] if it.get("thumb") else [],
            "brand_title": it.get("brand") or "",
            "size_title": it.get("size") or "",
            "status": it.get("condition") or "",
            "favourite_count": it.get("favourites", 0),
        })
    return {"items": items, "blocks": blocks}, 200, session


async def scrape_vinted(keyword: str, max_pages: int, headers: dict,
                        strategy: str = "single", domain: str = "www.vinted.de") -> list:
    """Vinted kazima — curl_cffi ile TLS parmak izi taklidi (tarayici gerekmez).
    strategy: "single" = sadece relevance, "multi_order" = tum siralamalari dolas
    domain: www.vinted.de | .fr | .pl | .be | .co.uk
    """
    del headers  # curl_cffi kendi tarayici-esdeger baslıklarini kullanir

    # Yerel para birimi: Vinted PL zloti, UK sterlin yayinliyor. Sabit kur
    # KULLANILMAZ — urun yerel birimiyle kaydedilir, EUR'ya cevrimi
    # analyze_profit gercek ECB kuruyla yapar (tek kaynak, tek dogruluk).
    yerel_birim = {"www.vinted.pl": "PLN", "www.vinted.co.uk": "GBP"}.get(domain, "EUR")

    orders = SCRAPE_ORDERS.get("vinted", ["relevance"])
    if strategy != "multi_order":
        orders = [orders[0]]

    seen_ids: set = set()
    products: list = []
    session = None

    for order in orders:
        for page in range(1, max_pages + 1):
            try:
                data, kod, session = await asyncio.to_thread(
                    _vinted_fetch, domain, keyword, order, page, session)
            except Exception as e:
                await log_activity("vinted_error",
                                   f"Vinted {domain} {order} s.{page}: {str(e)[:150]}", "warning")
                break

            if data is None:
                await log_activity(
                    "vinted_blocked",
                    f"Vinted {domain}: API HTTP {kod} — TLS taklidi yetmedi "
                    f"(Datadome JS-challenge devrede olabilir), {order} s.{page}",
                    "warning",
                )
                break

            items = data.get("items", [])
            for item in items:
                item_id = str(item.get("id", ""))
                if not item_id or item_id in seen_ids:
                    continue
                seen_ids.add(item_id)

                raw_price = item.get("price", {})
                if isinstance(raw_price, dict):
                    price_local = float(raw_price.get("amount") or 0)
                    birim = (raw_price.get("currency_code") or yerel_birim).upper()
                else:
                    price_local = float(raw_price or 0)
                    birim = yerel_birim

                photos = item.get("photos", [])
                if isinstance(photos, list) and photos:
                    imgs = [p.get("full_size_url") or p.get("url", "") for p in photos[:5]]
                elif item.get("photo"):
                    imgs = [item["photo"].get("full_size_url", "")]
                else:
                    imgs = []

                products.append({
                    "source_id": item_id,
                    "url": item.get("url") or f"https://{domain}/items/{item_id}",
                    "title": item.get("title", ""),
                    "description": item.get("description", ""),
                    "price": price_local,
                    "currency": birim,
                    "brand": item.get("brand_title", ""),
                    "size": item.get("size_title", ""),
                    # `status` GERCEK durum etiketi: "Sehr gut", "Neu, mit Etikett".
                    # Eskiden bos ("") yaziliyordu — durum zekasi bu yuzden hic
                    # calisamiyordu. Vinted bunu liste ucunda zaten veriyormus.
                    "condition": item.get("status", "") or "",
                    "category": str(item.get("catalog_id", "")),
                    "images": [i for i in imgs if i],
                    "views": item.get("view_count", 0),
                    "favorites": item.get("favourite_count", 0),
                })

            if not items:
                break  # bu siralama icin sayfa bitti

            await asyncio.sleep(1.5)  # nazik hiz siniri

    return products

async def scrape_kleinanzeigen(keyword: str, max_pages: int, headers: dict, strategy: str = "single") -> list:
    """Kleinanzeigen kazima. strategy=multi_order ile fiyat sirali sayfalar da taranir."""
    import requests
    from bs4 import BeautifulSoup

    orders = SCRAPE_ORDERS.get("kleinanzeigen", ["default"])
    if strategy != "multi_order":
        orders = [orders[0]]

    # Kleinanzeigen siralama suffix haritasi
    order_suffix = {
        "default": "",
        "price_asc": "/preis:aufsteigend",
        "price_desc": "/preis:absteigend",
    }

    seen_ids: set = set()
    products: list = []
    keyword_slug = _slugify(keyword)

    # curl_cffi: Kleinanzeigen duz `requests`'i bazen yonlendirme/engelle karsiliyor;
    # Chrome TLS parmak izi taklidiyle sayfa dogrudan aciliyor (canli olculdu).
    try:
        from curl_cffi import requests as _cr
        ka_session = _cr.Session(impersonate="chrome")
    except Exception:
        ka_session = None

    for order in orders:
        suffix = order_suffix.get(order, "")
        for page in range(1, max_pages + 1):
            try:
                # SAYFALAMA FORMATI KRITIK: "/seite:N" anahtar kelime ile "/k0"
                # ARASINA konursa Kleinanzeigen arama terimini "seite" saniyor ve
                # Seitenmarkise/Seitenblinker gibi tamamen alakasiz ilanlar
                # donuyor (canli dogrulandi). Dogru bicim: sayfa 1 -> s-{slug}/k0,
                # sayfa N -> s-seite:N/{slug}/k0.
                if page == 1:
                    url = f"https://www.kleinanzeigen.de/s-{keyword_slug}/k0{suffix}"
                else:
                    url = f"https://www.kleinanzeigen.de/s-seite:{page}/{keyword_slug}/k0{suffix}"
                if ka_session is not None:
                    resp = ka_session.get(url, timeout=25, allow_redirects=True)
                else:
                    resp = requests.get(url, headers=headers, timeout=15, allow_redirects=True)

                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "lxml")
                    listings = soup.select("article.aditem")

                    new_this_page = 0
                    for item in listings:
                        try:
                            title_el = item.select_one("a.ellipsis")
                            price_el = item.select_one("p.aditem-main--middle--price-shipping--price")
                            img_el = item.select_one("img")
                            link_el = item.select_one("a[href*='/s-anzeige/']")

                            title = title_el.text.strip() if title_el else ""
                            price_text = price_el.text.strip() if price_el else "0"
                            price = float(price_text.replace("€", "").replace(".", "").replace(",", ".").strip()) if price_text and "VB" not in price_text else 0
                            img_url = img_el.get("src", "") if img_el else ""
                            link = "https://www.kleinanzeigen.de" + link_el["href"] if link_el else ""
                            item_id = link.split("/")[-1] if link else ""

                            if title and price > 0 and item_id and item_id not in seen_ids:
                                seen_ids.add(item_id)
                                new_this_page += 1
                                products.append({
                                    "source_id": item_id,
                                    "url": link,
                                    "title": title,
                                    "description": "",
                                    "price": price,
                                    "currency": "EUR",
                                    "brand": "",
                                    "size": "",
                                    "condition": "",
                                    "category": "",
                                    "images": [img_url] if img_url else [],
                                    "views": 0,
                                    "favorites": 0,
                                })
                        except:
                            continue

                    if not listings or new_this_page == 0:
                        break
                else:
                    break

                await asyncio.sleep(3)
            except Exception as e:
                await log_activity("kleinanzeigen_error", f"Kleinanzeigen {order} s.{page}: {str(e)}", "warning")
                break

    return products

async def scrape_ebay(keyword: str, max_pages: int, headers: dict, strategy: str = "single") -> list:
    """eBay DE kazima - 2026 guncel selectors. strategy=multi_order ile birden fazla siralama."""
    import requests
    from bs4 import BeautifulSoup

    orders = SCRAPE_ORDERS.get("ebay", ["BestMatch"])
    if strategy != "multi_order":
        orders = [orders[0]]

    # eBay siralama parametresi haritasi
    order_param = {
        "BestMatch":               "12",
        "EndTimeSoonest":          "1",
        "PricePlusShippingLowest": "15",
        "NewlyListed":             "10",
    }

    seen_ids: set = set()
    products: list = []

    for order in orders:
        sort_val = order_param.get(order, "12")
        for page in range(1, max_pages + 1):
            try:
                url = f"https://www.ebay.de/sch/i.html?_nkw={keyword}&_ipg=50&_pgn={page}&_sop={sort_val}"
                # eBay duz 'requests' ile 403 (bot-korumasi) veriyor - dogrulandi,
                # gercek tarayici navigasyonu ile ayni sayfa sorunsuz aciliyor.
                html = await asyncio.to_thread(_fetch_html_via_browser, url)

                if html:
                    soup = BeautifulSoup(html, "lxml")
                    items = soup.select(".srp-results li")

                    new_this_page = 0
                    for item in items:
                        try:
                            text = item.get_text(strip=True)
                            if len(text) < 10:
                                continue

                            title_el = item.select_one("[role=heading], h3, .s-item__title")
                            price_el = item.select_one(".s-item__price, [class*=price]")
                            link_el = item.select_one('a[href*="itm"], a[href*="/p/"]')
                            img_el = item.select_one('img[src*="ebay"], img')

                            if not title_el:
                                continue

                            title = title_el.text.strip()
                            for suffix in ["Wird in neuem", "Opens in a new"]:
                                if suffix in title:
                                    title = title[:title.index(suffix)].strip()

                            price_text = price_el.text.strip() if price_el else "0"
                            price = 0

                            if "EUR" in price_text or "€" in price_text:
                                clean = price_text.replace("EUR", "").replace("€", "").replace(".", "").replace(",", ".").strip()
                                if "bis" in clean or " to " in clean:
                                    clean = clean.split("bis")[0].split(" to ")[0].strip()
                                try:
                                    price = float(clean.split()[0])
                                except:
                                    price = 0

                            elif "GBP" in price_text or "£" in price_text:
                                clean = price_text.replace("GBP", "").replace("£", "").replace(",", ".").strip()
                                if " to " in clean:
                                    clean = clean.split(" to ")[0].strip()
                                try:
                                    price = round(float(clean.split()[0]) * 1.17, 2)  # GBP -> EUR
                                except:
                                    price = 0

                            elif "CHF" in price_text:
                                clean = price_text.replace("CHF", "").replace(",", ".").strip()
                                try:
                                    price = round(float(clean.split()[0]) * 1.04, 2)  # CHF -> EUR
                                except:
                                    price = 0

                            img_url = ""
                            if img_el:
                                img_url = img_el.get("src", img_el.get("data-src", ""))

                            link_url = link_el["href"].split("?")[0] if link_el else ""
                            item_id = link_url.split("/")[-1] if link_url else ""

                            # DURUM: eBay ilan kartinda "Brandneu"/"Gebraucht" gibi
                            # bir alt-basli k zaten var; kod bunu hic okumuyordu ve
                            # condition bos kaliyordu (545 uruncte %0). Durum zekasi
                            # ve GPSR muafiyeti bu alandan beslenir.
                            cond_el = item.select_one(
                                ".s-item__subtitle .SECONDARY_INFO, .SECONDARY_INFO, "
                                ".s-item__subtitle, [class*=condition]")
                            condition = cond_el.get_text(strip=True) if cond_el else ""
                            if condition and len(condition) > 40:
                                condition = ""      # alt-baslik durum degil, baska metin

                            if title and price > 0 and "shop on ebay" not in title.lower() and item_id and item_id not in seen_ids:
                                seen_ids.add(item_id)
                                new_this_page += 1
                                products.append({
                                    "source_id": item_id,
                                    "url": link_url,
                                    "title": title,
                                    "description": "",
                                    "price": price,
                                    "currency": "EUR",
                                    # Marka BASLIKTAN cozulur: eBay arama sonucunda
                                    # ayri bir marka alani vermiyor, ama condition_intel
                                    # gercek marka sozlugunu kullanarak baslikta ariyor
                                    # (scrape_platform'da, urun dict'ine geri yazilir).
                                    "brand": "",
                                    "size": "",
                                    "condition": condition,
                                    "category": "",
                                    "images": [img_url] if img_url else [],
                                    "views": 0,
                                    "favorites": 0,
                                })
                        except:
                            continue

                    if not items or new_this_page == 0:
                        break
                else:
                    await log_activity("ebay_blocked", "eBay: sayfa alinamadi (bot-korumasi olabilir), 0 urun", "warning")
                    break

                await asyncio.sleep(2)
            except Exception as e:
                await log_activity("ebay_error", f"eBay {order} s.{page}: {str(e)}", "warning")
                break

    return products

async def scrape_sellpy(keyword: str, max_pages: int, headers: dict, strategy: str = "single") -> list:
    """
    Sellpy: site tamamen JavaScript; duz istekle ilan verisi GELMEZ (5 KB iskelet; TATANGA'da hic Sellpy urunu
    olmamasinin sebebi buydu, 2026-10-16). Bu yuzden sunucudaki gercek tarayicili Sellpy toplayicisinin verisinden
    (istatistik/alis_arsiv.db, sp_items) aranir: yalniz HALA SATISTA (for_sale, rezerve degil, son 3 gunde goruldu).
    Anahtar kelimenin her kelimesi marka / tur / kategori yolunda gecmeli.
    """
    import sqlite3 as _sq
    db_path = BASE_DIR.parent / "istatistik" / "alis_arsiv.db"
    if not db_path.exists():
        await log_activity("sellpy_error", "Sellpy: alis arsivi yok (istatistik/alis_arsiv.db)", "warning")
        return []
    words = [w.lower() for w in (keyword or "").replace(",", " ").split() if len(w) > 1]
    con = _sq.connect(f"file:{db_path}?mode=ro", uri=True)
    con.row_factory = _sq.Row
    cols = {r[1] for r in con.execute("PRAGMA table_info(sp_items)")}
    img_col = "image_url" if "image_url" in cols else "NULL AS image_url"
    rows = con.execute(
        f"SELECT object_id, url, brand, brand_q, type, cat_path, condition, size, price, fav, defects, {img_col} "
        "FROM sp_items WHERE for_sale=1 AND reserved=0 AND last_seen >= datetime('now','-3 day') "
        "ORDER BY sale_started DESC").fetchall()
    con.close()
    products = []
    limit = max(1, max_pages) * 60
    for r in rows:
        hay = " ".join(str(x or "") for x in (r["brand"], r["brand_q"], r["type"], r["cat_path"], r["condition"])).lower()
        if words and not all(w in hay for w in words):
            continue
        size = (r["size"] or "").split("-")[-1]
        products.append({
            "source_id": r["object_id"], "url": r["url"],
            "title": f"{r['brand'] or r['brand_q']}, {r['type'] or ''}" + (f", Größe: {size}" if size else ""),
            "description": ("Mängel: " + r["defects"]) if r["defects"] else "",
            "price": float(r["price"] or 0), "currency": "EUR",
            "brand": r["brand"] or r["brand_q"] or "", "size": size, "condition": r["condition"] or "",
            "category": r["cat_path"] or "", "images": [r["image_url"]] if r["image_url"] else [],
            "views": 0, "favorites": r["fav"] or 0,
        })
        if len(products) >= limit:
            break
    await log_activity("sellpy_arsiv", f"Sellpy (toplayici verisi): '{keyword}' -> {len(products)} aktif ilan")
    return products

async def scrape_willhaben(keyword: str, max_pages: int, headers: dict, strategy: str = "single") -> list:
    """Willhaben.at kazima. strategy=multi_order ile fiyat/tarih siralamalari da taranir."""
    import requests
    from bs4 import BeautifulSoup

    orders = SCRAPE_ORDERS.get("willhaben", ["relevance"])
    if strategy != "multi_order":
        orders = [orders[0]]

    order_param = {
        "relevance":  "relevance",
        "price_asc":  "price_ascending",
        "price_desc": "price_descending",
        "date_desc":  "date_descending",
    }

    seen_ids: set = set()
    products: list = []

    for order in orders:
        sort_val = order_param.get(order, "relevance")
        # Willhaben artik "sort=relevance" degerini gecersiz sayip 404 donduruyor
        # (site guncellendi, relevance zaten varsayilan siralama) - sadece
        # relevance disi bir siralama istendiginde parametreyi ekliyoruz.
        sort_qs = f"&sort={sort_val}" if sort_val != "relevance" else ""
        for page in range(1, max_pages + 1):
            try:
                url = f"https://www.willhaben.at/iad/kaufen-und-verkaufen/marktplatz?keyword={keyword}&page={page}{sort_qs}"
                resp = requests.get(url, headers=headers, timeout=15)

                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "lxml")
                    new_this_page = 0

                    # JSON-LD
                    scripts = soup.select("script[type='application/ld+json']")
                    for script in scripts:
                        try:
                            data = json.loads(script.string)
                            if isinstance(data, dict) and "itemListElement" in data:
                                for el in data["itemListElement"]:
                                    item = el.get("item", el)
                                    item_id = item.get("sku", "") or item.get("url", "")
                                    if not item_id or item_id in seen_ids:
                                        continue
                                    seen_ids.add(item_id)
                                    new_this_page += 1
                                    products.append({
                                        "source_id": item.get("sku", ""),
                                        "url": item.get("url", ""),
                                        "title": item.get("name", ""),
                                        "description": item.get("description", ""),
                                        "price": float(item.get("offers", {}).get("price", 0)) if item.get("offers") else 0,
                                        "currency": "EUR",
                                        "brand": "",
                                        "size": "",
                                        "condition": "",
                                        "category": "",
                                        "images": [item.get("image", "")] if item.get("image") else [],
                                        "views": 0,
                                        "favorites": 0,
                                    })
                        except:
                            continue

                    # HTML fallback
                    if new_this_page == 0:
                        items = soup.select("[data-testid='ad-list-item'], .search-result-entry")
                        for item in items:
                            try:
                                title_el = item.select_one("h3, [data-testid='ad-title']")
                                price_el = item.select_one("[data-testid='ad-price'], .info-1--price")
                                link_el = item.select_one("a[href]")
                                img_el = item.select_one("img")

                                title = title_el.text.strip() if title_el else ""
                                price_text = price_el.text.strip() if price_el else "0"
                                price = float(price_text.replace("€", "").replace(".", "").replace(",", ".").strip()) if price_text else 0
                                link_href = link_el["href"] if link_el else ""
                                item_id = link_href.split("/")[-1] if link_href else ""

                                if title and price > 0 and item_id and item_id not in seen_ids:
                                    seen_ids.add(item_id)
                                    new_this_page += 1
                                    products.append({
                                        "source_id": item_id,
                                        "url": ("https://www.willhaben.at" + link_href) if link_href and not link_href.startswith("http") else link_href,
                                        "title": title,
                                        "description": "",
                                        "price": price,
                                        "currency": "EUR",
                                        "brand": "",
                                        "size": "",
                                        "condition": "",
                                        "category": "",
                                        "images": [img_el.get("src", "")] if img_el else [],
                                        "views": 0,
                                        "favorites": 0,
                                    })
                            except:
                                continue

                    if new_this_page == 0:
                        break
                else:
                    await log_activity("willhaben_error", f"Willhaben: HTTP {resp.status_code}", "warning")
                    break

                await asyncio.sleep(3)
            except Exception as e:
                await log_activity("willhaben_error", f"Willhaben {order} s.{page}: {str(e)}", "warning")
                break

    return products

async def scrape_tradera(keyword: str, max_pages: int, headers: dict, strategy: str = "single") -> list:
    """Tradera (Isvec) kazima. strategy=multi_order destekler."""
    import requests
    from bs4 import BeautifulSoup

    orders = SCRAPE_ORDERS.get("tradera", ["relevance"])
    if strategy != "multi_order":
        orders = [orders[0]]

    order_param = {
        "relevance":  "",
        "date_desc":  "&sortField=EndDate&sortOrder=Descending",
        "price_asc":  "&sortField=Price&sortOrder=Ascending",
    }

    seen_ids: set = set()
    products: list = []

    for order in orders:
        sort_suffix = order_param.get(order, "")
        for page in range(1, max_pages + 1):
            try:
                url = f"https://www.tradera.com/search?q={keyword}&paging.pageNumber={page}{sort_suffix}"
                resp = requests.get(url, headers={**headers, "Accept-Language": "sv-SE,sv;q=0.9,en;q=0.8"}, timeout=15)

                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "lxml")
                    # Tradera CSS-modules class isimleri hash'li ("item-card-module-scss-module__ihfzoa__itemCard")
                    # ve her deploy'da hash degisebilir - bu yuzden sabit hash yerine
                    # anlamli soneki (__itemCard) iceren class'lari eslestiriyoruz.
                    items = soup.select('div[class*="__itemCard"]')

                    new_this_page = 0
                    for item in items:
                        try:
                            link_el = item.select_one('a[data-testid="item-card-image"]')
                            price_el = item.select_one('[data-testid="price"]')
                            img_el = item.select_one("img")

                            title = (link_el.get("title") or "").strip() if link_el else ""
                            price_text = price_el.text.strip() if price_el else "0"
                            price_sek = float(re.sub(r"[^\d,\.]", "", price_text.split(",")[0]).replace(",", ".") or 0)
                            price_eur = round(price_sek * 0.087, 2)
                            link_href = link_el.get("href", "") if link_el else ""
                            item_id = (item.get("id") or "").removeprefix("item-card-") or link_href.split("/")[-1]

                            if title and price_sek > 0 and item_id and item_id not in seen_ids:
                                seen_ids.add(item_id)
                                new_this_page += 1
                                products.append({
                                    "source_id": item_id,
                                    "url": ("https://www.tradera.com" + link_href) if link_href and not link_href.startswith("http") else link_href,
                                    "title": title,
                                    "description": "",
                                    "price": price_eur,
                                    "currency": "EUR",
                                    "brand": "",
                                    "size": "",
                                    "condition": "",
                                    "category": "",
                                    "images": [img_el.get("src", "")] if img_el else [],
                                    "views": 0,
                                    "favorites": 0,
                                })
                        except:
                            continue

                    if not items or new_this_page == 0:
                        break
                else:
                    await log_activity("tradera_error", f"Tradera: HTTP {resp.status_code}", "warning")
                    break

                await asyncio.sleep(3)
            except Exception as e:
                await log_activity("tradera_error", f"Tradera {order} s.{page}: {str(e)}", "warning")
                break

    return products

def _lbc_ads_from_html(html: str) -> list:
    """
    Leboncoin arama sayfasindaki __NEXT_DATA__ icinden ilanlari cikarir.

    NEDEN BOYLE: Eski kod api.leboncoin.fr/finder/search'e sabit bir api_key ile
    POST atiyordu; Datadome bunu 403'le kesiyor (canli dogrulandi) ve HTML
    fallback'i de duz requests kullandigi icin ayni engele takiliyordu — sonuc
    her zaman 0 idi. Gercek tarayici sayfayi acabiliyor ve Next.js sayfanin
    icine TUM ilan verisini gomuyor: baslik, ACIKLAMA (body), fiyat, marka,
    gorseller. Yani ekstra istek atmadan tam veri elde ediliyor.
    """
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "lxml")
    el = soup.find("script", id="__NEXT_DATA__")
    if not el or not el.string:
        return []
    try:
        data = json.loads(el.string)
    except Exception:
        return []
    try:
        return data["props"]["pageProps"]["searchData"]["ads"] or []
    except Exception:
        pass
    # Sayfa yapisi degisirse: 'ads' anahtarini derinlemesine ara.
    bulunan: list = []

    def gez(o, derin=0):
        nonlocal bulunan
        if bulunan or derin > 8:
            return
        if isinstance(o, dict):
            for k, v in o.items():
                if k == "ads" and isinstance(v, list) and v and isinstance(v[0], dict):
                    bulunan = v
                    return
                gez(v, derin + 1)
        elif isinstance(o, list):
            for x in o[:20]:
                gez(x, derin + 1)

    gez(data)
    return bulunan


async def scrape_leboncoin(keyword: str, max_pages: int, headers: dict, strategy: str = "single") -> list:
    """Leboncoin (Fransa) kazima — gercek tarayici + gomulu Next.js verisi."""
    del headers
    from urllib.parse import quote

    orders = SCRAPE_ORDERS.get("leboncoin", ["relevance"])
    if strategy != "multi_order":
        orders = [orders[0]]
    order_map = {"relevance": "", "time_desc": "&sort=time&order=desc",
                 "price_asc": "&sort=price&order=asc"}

    seen_ids: set = set()
    products: list = []

    for order in orders:
        ek = order_map.get(order, "")
        for page in range(1, max_pages + 1):
            url = (f"https://www.leboncoin.fr/recherche?text={quote(keyword)}"
                   f"&page={page}{ek}")
            try:
                html = await asyncio.to_thread(_fetch_html_via_browser, url, 7.0)
            except Exception as e:
                await log_activity("leboncoin_error",
                                   f"Leboncoin {order} s.{page}: {str(e)[:130]}", "warning")
                break

            if not html:
                await log_activity("leboncoin_blocked",
                                   f"Leboncoin: sayfa alinamadi ({order} s.{page})", "warning")
                break

            ilanlar = _lbc_ads_from_html(html)
            if not ilanlar:
                await log_activity("leboncoin_blocked",
                                   f"Leboncoin: sayfada ilan verisi yok ({order} s.{page}) — "
                                   "Datadome duvari veya sayfa yapisi degismis", "warning")
                break

            yeni = 0
            for item in ilanlar:
                iid = str(item.get("list_id") or "")
                if not iid or iid in seen_ids:
                    continue
                seen_ids.add(iid)

                p = item.get("price")
                fiyat = 0.0
                try:
                    fiyat = float(p[0] if isinstance(p, list) and p else (p or 0))
                except Exception:
                    fiyat = 0.0
                if fiyat <= 0:
                    continue

                gorseller = (item.get("images") or {}).get("urls_large") \
                    or (item.get("images") or {}).get("urls") or []

                # Durum/beden Leboncoin'de 'attributes' listesinde gelir.
                durum, beden = "", ""
                for a in item.get("attributes") or []:
                    k = (a.get("key") or "").lower()
                    v = a.get("value_label") or a.get("value") or ""
                    if k in ("item_condition", "condition", "etat"):
                        durum = str(v)
                    elif k in ("clothing_size", "size", "taille"):
                        beden = str(v)

                yeni += 1
                products.append({
                    "source_id": iid,
                    "url": item.get("url") or f"https://www.leboncoin.fr/ad/{iid}",
                    "title": item.get("subject") or "",
                    "description": item.get("body") or "",
                    "price": fiyat,
                    "currency": "EUR",
                    "brand": str(item.get("brand") or ""),
                    "size": beden,
                    "condition": durum,
                    "category": item.get("category_name") or "",
                    "images": list(gorseller)[:5],
                    "views": 0,
                    "favorites": 0,
                })

            if yeni == 0:
                break
            await asyncio.sleep(3)

    return products

def _markt_fetch(keyword: str, offset: int, limit: int, sort: str, session=None):
    """
    Marktplaats.nl'in KENDI arama ucu (lrp/api/search) — sayfa HTML'i kazimak
    yerine sitenin kendi verisini okur.

    NEDEN BU: Eski kod markt.de'ye (Almanya) gidiyordu ama yerellestirici bu
    platforma HOLLANDACA kelime yolluyordu — iki taraf birbiriyle tutarsizdi
    ve sonuc her zaman 0'di. Marktplaats.nl Hollanda'nin en buyuk ilan sitesi,
    Almanya'ya kargo yapan saticilari var ve API'si ELEN ZENGIN veriyi veriyor:
    tam aciklama, durum (attributes.condition), marka (extendedAttributes) —
    hicbir platformda bir arada bulamadigimiz uclu.
    """
    from curl_cffi import requests as cr
    from urllib.parse import quote
    if session is None:
        session = cr.Session(impersonate="chrome")
    url = (f"https://www.marktplaats.nl/lrp/api/search?query={quote(keyword)}"
           f"&limit={limit}&offset={offset}&sortBy={sort}")
    r = session.get(url, timeout=30, headers={"Accept": "application/json"})
    if r.status_code != 200:
        return None, r.status_code, session
    try:
        return r.json(), 200, session
    except Exception:
        return None, r.status_code, session


def _markt_attr(item: dict, alan: str, uzun: bool = False) -> str:
    """attributes / extendedAttributes listesinden bir anahtarin degerini alir."""
    for kutu in ("attributes", "extendedAttributes"):
        for a in item.get(kutu) or []:
            k = (a.get("key") or "").lower()
            if k == alan or (uzun and alan in k):
                return str(a.get("value") or "")
    return ""


async def scrape_markt(keyword: str, max_pages: int, headers: dict, strategy: str = "single") -> list:
    """Marktplaats.nl (NL) kazima — sitenin kendi arama API'si uzerinden."""
    del headers
    siralamalar = ["OPTIMIZED", "SORT_INDEX"] if strategy == "multi_order" else ["OPTIMIZED"]
    LIMIT = 30

    seen_ids: set = set()
    products: list = []
    session = None

    for sort in siralamalar:
        for page in range(max_pages):
            try:
                data, kod, session = await asyncio.to_thread(
                    _markt_fetch, keyword, page * LIMIT, LIMIT, sort, session)
            except Exception as e:
                await log_activity("markt_error", f"Marktplaats {sort} s.{page+1}: {str(e)[:130]}", "warning")
                break

            if data is None:
                await log_activity("markt_blocked",
                                   f"Marktplaats: API HTTP {kod} ({sort} s.{page+1})", "warning")
                break

            ilanlar = data.get("listings") or []
            for it in ilanlar:
                iid = str(it.get("itemId") or "")
                if not iid or iid in seen_ids:
                    continue
                seen_ids.add(iid)

                # Fiyat cent cinsinden. priceType 'FAST_BID'/'SEE_DESCRIPTION' gibi
                # degerlerde priceCents 0 gelir — bu "bedava" degil "fiyat yok"
                # demektir; 0 fiyatli urun karliligi bozar, atlanir.
                pi = it.get("priceInfo") or {}
                cents = pi.get("priceCents") or 0
                if not cents or (pi.get("priceType") or "") not in ("FIXED", "MIN_BID", "NOTK", ""):
                    if not cents:
                        continue
                fiyat = round(cents / 100.0, 2)
                if fiyat <= 0:
                    continue

                gorseller = []
                for p in (it.get("pictures") or []):
                    u = p.get("extraExtraLargeUrl") or p.get("largeUrl") or p.get("url") or ""
                    if u:
                        gorseller.append(u if u.startswith("http") else "https:" + u)
                if not gorseller:
                    for u in (it.get("imageUrls") or []):
                        gorseller.append(u if u.startswith("http") else "https:" + u)

                vip = it.get("vipUrl") or ""
                products.append({
                    "source_id": iid,
                    "url": vip if vip.startswith("http") else f"https://www.marktplaats.nl{vip}",
                    "title": it.get("title") or "",
                    # Marktplaats liste ucunda TAM ACIKLAMA veriyor — beyan
                    # celiskisi tespiti bu platformda gercekten calisabilir.
                    "description": it.get("description") or "",
                    "price": fiyat,
                    "currency": "EUR",
                    "brand": _markt_attr(it, "brand", uzun=True),
                    "size": _markt_attr(it, "size", uzun=True),
                    "condition": _markt_attr(it, "condition"),
                    "category": str(it.get("categoryId") or ""),
                    "images": gorseller[:5],
                    "views": 0,
                    "favorites": 0,
                })

            if len(ilanlar) < LIMIT:
                break   # son sayfa
            await asyncio.sleep(1.5)

    return products


async def scrape_depop(keyword: str, max_pages: int, headers: dict, strategy: str = "single") -> list:
    """Depop kazima - JSON API response kullanir."""
    import requests

    orders = ["relevance", "priceAscending"] if strategy == "multi_order" else ["relevance"]

    seen_ids: set = set()
    products: list = []

    session = requests.Session()
    session.headers.update({
        **headers,
        "Accept": "application/json",
        "Depop-Client-Type": "Web",
    })

    for order in orders:
        for page in range(1, max_pages + 1):
            try:
                offset = (page - 1) * 24
                url = f"https://api.depop.com/api/v2/search/products/?q={keyword}&sort={order}&offset={offset}&limit=24&country=de&currency=EUR"
                resp = session.get(url, timeout=15)

                if resp.status_code == 200:
                    data = resp.json()
                    items = data.get("objects", data.get("products", []))

                    new_this_page = 0
                    for item in items:
                        item_id = str(item.get("id", "") or item.get("slug", ""))
                        if not item_id or item_id in seen_ids:
                            continue
                        seen_ids.add(item_id)

                        # Fiyat (GBP -> EUR ~1.17)
                        price_data = item.get("price", {})
                        if isinstance(price_data, dict):
                            price_val = float(price_data.get("amountInCents", 0)) / 100
                            currency = price_data.get("currencyName", "GBP")
                        else:
                            price_val = float(price_data or 0)
                            currency = "GBP"

                        # GBP -> EUR donusumu
                        price_eur = round(price_val * 1.17, 2) if currency == "GBP" else price_val

                        # Resimler
                        previews = item.get("previews", [])
                        images = [p.get("url", "") for p in previews[:5]] if previews else []

                        slug = item.get("slug", item_id)
                        seller = item.get("sellerUsername", "")

                        new_this_page += 1
                        products.append({
                            "source_id": item_id,
                            "url": f"https://www.depop.com/products/{slug}/",
                            "title": item.get("description", item.get("title", ""))[:100],
                            "description": item.get("description", ""),
                            "price": price_eur,
                            "currency": "EUR",
                            "brand": item.get("brand", {}).get("name", "") if isinstance(item.get("brand"), dict) else "",
                            "size": item.get("size", {}).get("display", "") if isinstance(item.get("size"), dict) else str(item.get("size", "")),
                            "condition": "",
                            "category": str(item.get("categoryId", "")),
                            "images": images,
                            "views": item.get("likesCount", 0),
                            "favorites": item.get("likesCount", 0),
                        })

                    if not items or new_this_page == 0:
                        break
                else:
                    break

                await asyncio.sleep(2)
            except Exception as e:
                await log_activity("depop_error", f"Depop {order} s.{page}: {str(e)}", "warning")
                break

    return products


async def scrape_percentil(keyword: str, max_pages: int, headers: dict) -> list:
    """Percentil kazima - konsinyasyon platformu (Almanya)."""
    import requests
    from bs4 import BeautifulSoup

    seen_ids: set = set()
    products: list = []

    for page in range(1, max_pages + 1):
        try:
            url = f"https://www.percentil.com/de/search/?q={keyword}&p={page}"
            resp = requests.get(url, headers=headers, timeout=15)

            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "lxml")
                listings = soup.select(".product-item, .item-product, article[class*=product], [class*=product-card]")

                new_this_page = 0
                for item in listings:
                    try:
                        title_el = item.select_one("h2, h3, .product-name, [class*=title]")
                        price_el = item.select_one(".price, [class*=price], [itemprop=price]")
                        link_el = item.select_one("a[href]")
                        img_el = item.select_one("img")

                        title = title_el.get_text(strip=True) if title_el else ""
                        price_text = price_el.get("content", price_el.get_text(strip=True)) if price_el else ""
                        price = 0
                        if price_text:
                            clean = str(price_text).replace("€", "").replace(",", ".").strip()
                            try:
                                price = float(clean.split()[0])
                            except:
                                price = 0

                        link_href = link_el["href"] if link_el else ""
                        if link_href and not link_href.startswith("http"):
                            link_href = "https://www.percentil.com" + link_href
                        item_id = link_href.split("/")[-1] if link_href else ""

                        if title and price > 0 and item_id and item_id not in seen_ids:
                            seen_ids.add(item_id)
                            new_this_page += 1
                            products.append({
                                "source_id": item_id,
                                "url": link_href,
                                "title": title,
                                "description": "",
                                "price": price,
                                "currency": "EUR",
                                "brand": "",
                                "size": "",
                                "condition": "",
                                "category": "",
                                "images": [img_el.get("src", img_el.get("data-src", ""))] if img_el else [],
                                "views": 0,
                                "favorites": 0,
                            })
                    except:
                        continue

                if not listings or new_this_page == 0:
                    break
            else:
                break

            await asyncio.sleep(3)
        except Exception as e:
            await log_activity("percentil_error", f"Percentil s.{page}: {str(e)}", "warning")
            break

    return products


# ============================================
# PROFIT ANALYSIS - SITE BAZLI KARSILASTIRMALI ARBITRAJ
# ============================================

# Platform komisyonlari (satis yaptigimizda - SADECE harici satis platformlari)
# cssberlin bizim kendi sitemiz, kazima/satis algoritmasi disinda tutulur
SELL_FEES = {
    "vinted": 0.05,          # %5 satis komisyonu
    "kleinanzeigen": 0.0,    # Komisyon yok (Direkt satis)
    "ebay": 0.12,            # %12 (eBay DE)
    "willhaben": 0.05,       # %5
    "tradera": 0.08,         # %8
    "leboncoin": 0.04,       # %4
    "markt": 0.0,            # Komisyon yok
    "depop": 0.10,           # %10
    "percentil": 0.20,       # %20 (konsinyasyon modeli)
}

# Drop-shipping gercekci maliyet sabitleri
PACKAGING_COST = 1.50    # Kutu, bant, kagit sabit paketleme maliyeti (EUR)
BROCHURE_COST  = 0.20    # CSS Berlin reklam brosuru (EUR)

# Bu alis fiyatinin ustunde sistem tek basina "buy" demez, "watch"e ceker.
# Sebep: kar modeli sabit bir markup carpanina dayaniyor; ucuz urunlerde
# gercekci, pahali urunlerde tamamen yaniltici. 150 EUR, ikinci el giyimde
# "sokak fiyati" ile "koleksiyon/hatali fiyat" arasindaki pratik sinir.
HIGH_PRICE_REVIEW_EUR = 150.0

# Kargo maliyetleri (kaynak_ulke -> hedef_ulke)
SHIPPING_COSTS = {
    # Almanya ic
    "DE_DE": {"letter": 2.75, "small": 4.99, "medium": 5.99, "large": 10.99},
    # Avusturya
    "AT_DE": {"small": 6.99, "medium": 8.99, "large": 14.99},
    "DE_AT": {"small": 6.99, "medium": 8.99, "large": 14.99},
    # Isvec
    "SE_DE": {"small": 9.99, "medium": 14.99, "large": 19.99},
    "DE_SE": {"small": 9.99, "medium": 14.99, "large": 19.99},
    # Fransa
    "FR_DE": {"small": 7.99, "medium": 12.99, "large": 17.99},
    "DE_FR": {"small": 7.99, "medium": 12.99, "large": 17.99},
    # Polonya (Vinted.pl)
    "PL_DE": {"small": 8.99, "medium": 12.99, "large": 18.99},
    "DE_PL": {"small": 8.99, "medium": 12.99, "large": 18.99},
    # Belcika (Vinted.be)
    "BE_DE": {"small": 6.99, "medium": 9.99, "large": 14.99},
    "DE_BE": {"small": 6.99, "medium": 9.99, "large": 14.99},
    # Ingiltere (Vinted.co.uk, Depop)
    "UK_DE": {"small": 9.99, "medium": 15.99, "large": 22.99},
    "DE_UK": {"small": 9.99, "medium": 15.99, "large": 22.99},
    # Italya
    "IT_DE": {"small": 8.99, "medium": 13.99, "large": 19.99},
    "DE_IT": {"small": 8.99, "medium": 13.99, "large": 19.99},
    # 2026-10-16 eklendi (varsayim: komsu AB ulkesi tarifeleri; gercek Vinted kargo fiyatiyla guncellenmeli)
    "NL_DE": {"small": 6.99, "medium": 9.99, "large": 14.99},
    "DE_NL": {"small": 6.99, "medium": 9.99, "large": 14.99},
    "ES_DE": {"small": 9.99, "medium": 14.99, "large": 19.99},
    "DE_ES": {"small": 9.99, "medium": 14.99, "large": 19.99},
}

# Platform ulkeleri (kaynak kazima platformlari + satis platformlari)
PLATFORM_COUNTRY = {
    # Mevcut kazima/satis platformlari
    "vinted": "DE", "kleinanzeigen": "DE", "ebay": "DE",
    "sellpy": "DE", "willhaben": "AT", "tradera": "SE", "leboncoin": "FR",
    # Vinted multi-country
    "vinted_fr": "FR", "vinted_pl": "PL", "vinted_be": "BE", "vinted_uk": "UK",
    "vinted_it": "IT", "vinted_nl": "NL", "vinted_at": "AT", "vinted_es": "ES", "vinted_se": "SE",
    # Yeni platformlar
    # markt = Marktplaats.nl (Hollanda). Eskiden yanlislikla markt.de (DE)
    # olarak isaretliydi ama yerellestirici bu platforma Hollandaca kelime
    # yolluyordu — iki taraf tutarsizdi ve sonuc hep 0 idi.
    "markt": "NL", "depop": "UK", "percentil": "ES",
}

# Kazima stratejisi — her platform icin siralamalar
SCRAPE_ORDERS = {
    "vinted":        ["relevance", "newest_first", "price_low_to_high", "price_high_to_low"],
    "ebay":          ["BestMatch", "EndTimeSoonest", "PricePlusShippingLowest", "NewlyListed"],
    "kleinanzeigen": ["default", "price_asc", "price_desc"],
    "willhaben":     ["relevance", "price_asc", "price_desc", "date_desc"],
    "tradera":       ["relevance", "date_desc", "price_asc"],
    "leboncoin":     ["relevance", "time_desc", "price_asc"],
    "sellpy":        ["default", "price_asc"],
    "markt":         ["default", "price_asc"],
    "depop":         ["relevance", "priceAscending"],
    "percentil":     ["default"],
    # Vinted multi-country ayni stratejileri kullanir
    "vinted_fr":     ["relevance", "newest_first", "price_low_to_high", "price_high_to_low"],
    "vinted_pl":     ["relevance", "newest_first", "price_low_to_high", "price_high_to_low"],
    "vinted_be":     ["relevance", "newest_first", "price_low_to_high", "price_high_to_low"],
    "vinted_uk":     ["relevance", "newest_first", "price_low_to_high", "price_high_to_low"],
    "vinted_it":     ["relevance", "newest_first", "price_low_to_high", "price_high_to_low"],
    "vinted_nl":     ["relevance", "newest_first", "price_low_to_high", "price_high_to_low"],
    "vinted_at":     ["relevance", "newest_first", "price_low_to_high", "price_high_to_low"],
    "vinted_es":     ["relevance", "newest_first", "price_low_to_high", "price_high_to_low"],
    "vinted_se":     ["relevance", "newest_first", "price_low_to_high", "price_high_to_low"],
}

def get_shipping_cost(from_country: str, to_country: str, size: str = "medium") -> float:
    """Kargo maliyetini hesapla"""
    key = f"{from_country}_{to_country}"
    costs = SHIPPING_COSTS.get(key, SHIPPING_COSTS.get("DE_DE"))
    return costs.get(size, costs.get("medium", 5.99))

def analyze_profit(product: dict, source_platform: str) -> dict:
    """Drop-shipping gercekci arbitraj analizi.
    Model: alis + gelen_kargo + giden_kargo + paketleme + brosur + platform_komisyonu
    Tavsiye esikleri: buy >= 8EUR & 30%, watch >= 4EUR & 20%, skip = alti
    cssberlin bizim kendi sitemiz — satis platformu listesinde YOK.
    """
    buy_price = product.get("price", 0)
    if buy_price <= 0:
        return {"recommendation": "skip", "profit": 0, "margin": 0,
                "arbitrage_json": "[]", "shipping": 0, "fee": 0,
                "sell_price": 0, "best_platform": ""}

    # Yerel para birimi -> EUR. Kaziyicilar cogunlukla EUR'a cevirip yaziyor;
    # ama urun hala yerel birimde geldiyse (currency alani EUR degilse) burada
    # GERCEK ECB kuruyla cevrilir. Kur bilinmiyorsa 1:1 VARSAYILMAZ — urun
    # atlanir, cunku SEK'i EUR sanmak 11 kat sisirilmis kar demektir.
    kur_notu = ""
    urun_birimi = (product.get("currency") or "EUR").upper()
    if _currency and urun_birimi != "EUR":
        r = _rates()
        cevrilen = _currency.to_eur(buy_price, urun_birimi, r) if r else None
        if cevrilen is None:
            return {"recommendation": "skip", "profit": 0, "margin": 0,
                    "arbitrage_json": "[]", "shipping": 0, "fee": 0,
                    "sell_price": 0, "best_platform": "",
                    "learning_note": f"kur bilinmiyor ({urun_birimi}) — atlandi"}
        kur_notu = f"{buy_price} {urun_birimi} -> {cevrilen} EUR ({r.source})"
        buy_price = cevrilen

    source_country = PLATFORM_COUNTRY.get(source_platform, "DE")

    # Gelen kargo: kaynak -> bize (DE)
    inbound_shipping = get_shipping_cost(source_country, "DE", "medium")

    # Sabit dropshipping maliyetleri
    fixed_costs = PACKAGING_COST + BROCHURE_COST   # 1.50 + 0.20 = 1.70 EUR

    # Temel maliyet bazis (alis + gelen kargo)
    base_cost = buy_price + inbound_shipping

    # Her harici platformda satis analizi
    platform_analysis = []
    for sell_platform, sell_fee_rate in SELL_FEES.items():
        sell_country = PLATFORM_COUNTRY.get(sell_platform, "DE")
        outbound_shipping = get_shipping_cost("DE", sell_country, "medium")

        # Tahmini satis fiyati: toplam maliyet * markup
        # Komisyon yuksek platformlarda (ebay %12) daha agresif markup
        if sell_platform == "ebay":
            markup = 1.45   # %45 markup (yuksek komisyon absorbe edilsin)
        elif sell_platform in ("percentil",):
            markup = 1.60   # %60 (konsinyasyon - %20 komisyon + uzun sure)
        elif sell_platform in ("kleinanzeigen", "markt"):
            markup = 1.42   # %42 (komisyon yok, pazarlik toleransi)
        else:
            markup = 1.40   # %40 standart (vinted, willhaben, tradera, leboncoin, depop)

        est_sell_price = round(base_cost * markup, 2)
        sell_fee = round(est_sell_price * sell_fee_rate, 2)

        # GERCEKCI net kar:
        # satis_fiyati - alis - gelen_kargo - giden_kargo - paketleme - brosur - komisyon
        net_profit = round(
            est_sell_price
            - buy_price
            - inbound_shipping
            - outbound_shipping
            - fixed_costs
            - sell_fee,
            2
        )
        total_cost_full = buy_price + inbound_shipping + outbound_shipping + fixed_costs + sell_fee
        margin = round((net_profit / total_cost_full * 100), 1) if total_cost_full > 0 else 0

        platform_analysis.append({
            "platform": sell_platform,
            "est_sell_price": est_sell_price,
            "sell_fee": sell_fee,
            "sell_fee_rate": sell_fee_rate,
            "outbound_shipping": outbound_shipping,
            "net_profit": net_profit,
            "margin": margin,
        })

    # En karli harici platformu bul
    platform_analysis.sort(key=lambda x: x["net_profit"], reverse=True)
    best = platform_analysis[0] if platform_analysis else {}

    # Tavsiye — gercekci esikler
    best_profit = best.get("net_profit", 0)
    best_margin = best.get("margin", 0)
    if best_profit >= 8 and best_margin >= 30:
        recommendation = "buy"
    elif best_profit >= 4 and best_margin >= 20:
        recommendation = "watch"
    else:
        recommendation = "skip"

    # --- YUKSEK FIYAT TAVANI --------------------------------------------
    # Model "satis = alis x markup" varsayar. Bu ucuz urunlerde makul, ama
    # PAHALI urunlerde tehlikeli sekilde yanlistir: 2650 EUR'luk bir montu
    # "3781 EUR'ya satarim, 1110 EUR kar" diye isaretledi (canli gorulду).
    # Ikinci el pazarinda o fiyata alici yok; o ilan ya koleksiyon parcasi ya
    # yanlis fiyatlanmis. Model, "ne kadar pahaliysa o kadar karli" diyerek
    # gercegin TERSINI soyluyor.
    #
    # Bu yuzden: belirli bir alis fiyatinin ustunde otomatik "buy" VERILMEZ.
    # Urun elenmez — insan incelemesine birakilir ("watch"), cunku gercek bir
    # firsat da olabilir; ama sistem tek basina karar vermez.
    if buy_price > HIGH_PRICE_REVIEW_EUR and recommendation == "buy":
        recommendation = "watch"
        best_margin_note = (f"alis {buy_price:.0f} EUR > {HIGH_PRICE_REVIEW_EUR} EUR esigi: "
                            "markup modeli bu bantta guvenilir degil, insan incelemesi gerekir")
    else:
        best_margin_note = ""

    # Gecmis sonuclar: bu (platform, marka, fiyat bandi) baglami gercekten
    # satiyor mu? Hesap ne kadar karli gorunurse gorunsun, o baglamda yeterli
    # gozlem varken satis orani cok dusukse "buy" -> "watch"e cekilir.
    # Yeterli gozlem YOKSA hicbir sey degismez — az veriyle karar verilmez.
    learning_note = ""
    if _outcome_learning:
        try:
            ogr_conn = sqlite3.connect(DB_FILE)
            try:
                oneri = _outcome_learning.recommend(
                    ogr_conn, platform=source_platform,
                    brand=product.get("brand", "") or "",
                    price=buy_price)
            finally:
                ogr_conn.close()
            learning_note = f"{oneri.verdict}: {oneri.reason}"
            if oneri.verdict == "avoid" and recommendation == "buy":
                recommendation = "watch"
            elif oneri.verdict == "avoid" and recommendation == "watch":
                recommendation = "skip"
        except Exception as e:
            print(f"[OUTCOME RECOMMEND] {str(e)[:120]}")

    return {
        "learning_note": " | ".join(x for x in (kur_notu, best_margin_note, learning_note) if x),
        "sell_price": best.get("est_sell_price", 0),
        "profit": best_profit,
        "margin": best_margin,
        "shipping": inbound_shipping,
        "outbound_shipping": best.get("outbound_shipping", 0),
        "packaging": fixed_costs,
        "fee": best.get("sell_fee", 0),
        "recommendation": recommendation,
        "best_platform": best.get("platform", ""),
        "total_cost": base_cost,
        "arbitrage_json": json.dumps(platform_analysis),
    }

# ============================================
# SOURCE PRODUCT LIVENESS CHECK
# ============================================
async def check_product_source(product_id: str):
    """Kaynak urunun hala aktif olup olmadigini kontrol et"""
    import requests

    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute(
            "SELECT source_url, source_platform, source_status, brand, price "
            "FROM products WHERE id=?", (product_id,))
        row = await cursor.fetchone()
        if not row:
            return

        source_url, platform, onceki_durum, marka, alis_fiyat = row
        if not source_url:
            return

        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            resp = requests.get(source_url, headers=headers, timeout=10, allow_redirects=True)

            status = "active"
            if resp.status_code == 404:
                status = "removed"
            elif resp.status_code == 410:
                status = "sold"
            elif resp.status_code == 200:
                text = resp.text.lower()
                if any(kw in text for kw in ["sold", "verkauft", "vendu", "saldu", "nicht mehr verfugbar", "sasld"]):
                    status = "sold"
                elif any(kw in text for kw in ["reserved", "reserviert"]):
                    status = "reserved"
                elif any(kw in text for kw in ["deactivated", "deaktiviert", "entfernt", "geloscht"]):
                    status = "removed"
                else:
                    status = "active"
            else:
                status = "unknown"

            # Update DB
            await db.execute(
                "UPDATE products SET source_status=?, last_source_check=?, updated_at=? WHERE id=?",
                (status, datetime.now().isoformat(), datetime.now().isoformat(), product_id)
            )
            await db.execute(
                "INSERT INTO source_checks (product_id, source_url, status, response_code) VALUES (?,?,?,?)",
                (product_id, source_url, status, resp.status_code)
            )
            await db.commit()

            # Sonuc ogrenme: kaynak ilan "aktif"ten "satildi/kaldirildi"ya GECTIGI
            # anda gercek bir sonuc olusur. Sadece GECISTE kaydedilir — her
            # kontrolde tekrar sayilirsa istatistik sisirilir ve yanlis ogrenilir.
            terminal = {"sold", "removed"}
            if (_outcome_learning and status in terminal
                    and (onceki_durum or "active") not in terminal):
                try:
                    ogrenme_conn = sqlite3.connect(DB_FILE)
                    try:
                        _outcome_learning.record_outcome(
                            ogrenme_conn,
                            platform=platform or "",
                            brand=marka or "",
                            price=float(alis_fiyat or 0),
                            sold=(status == "sold"),
                        )
                    finally:
                        ogrenme_conn.close()
                except Exception as e:
                    print(f"[OUTCOME] {product_id}: {str(e)[:120]}")

            await log_activity("source_check", f"{product_id}: {status} ({resp.status_code})")
            await broadcast_ws("source_checked", {
                "product_id": product_id,
                "status": status,
                "code": resp.status_code
            })

        except Exception as e:
            await db.execute(
                "INSERT INTO source_checks (product_id, source_url, status, response_code) VALUES (?,?,?,?)",
                (product_id, source_url, "error", 0)
            )
            await db.commit()
            await log_activity("source_check_error", f"{product_id}: {str(e)}", "error")


async def _source_recheck_handler(job=None):
    """
    Manager handler'i (source_recheck): en eski kontrol edilmis YAYINLI urunlerden
    kucuk bir parti (8) alir, mevcut check_product_source ile kaynagini tazeler.
    Kaynakta satilmis/kaldirilmis olanlari isaretler (guven zedelenmesin). Kucuk
    parti + 10dk arayla -> platformlari yormaz. Otomatik yayindan-kaldirma YOK
    (bu bir insan/sonraki-adim karari) - sadece isaretler + olay yazar.
    """
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT id, source_status FROM products WHERE status='published' AND source_url IS NOT NULL "
            "ORDER BY (last_source_check IS NULL) DESC, last_source_check ASC LIMIT 8"
        )
        rows = await cur.fetchall()
    before = {r["id"]: r["source_status"] for r in rows}
    for pid in before:
        try:
            await check_product_source(pid)
        except Exception:
            pass
    gone_ids: list[str] = []
    if before:
        async with aiosqlite.connect(DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            qs = ",".join("?" * len(before))
            cur = await db.execute(
                f"SELECT id, source_status FROM products WHERE id IN ({qs})", tuple(before)
            )
            for r in await cur.fetchall():
                # Sadece KESIN olu (sold/removed) -> kaldir. reserved/unknown belirsiz,
                # dokunma (ileride insan onayi / ekran-goruntusu kademesi).
                if (r["source_status"] in ("sold", "removed")
                        and before.get(r["id"]) not in ("sold", "removed")):
                    gone_ids.append(r["id"])
    gone = len(gone_ids)

    # AUTO-UNPUBLISH: kaynagi olen urunu kendi sitemizden (cssberlin) de kaldir.
    # "Hedefte yoksa bizde de olmasin" — guven. Mevcut unpublish_product yeniden
    # kullanilir (cssberlin DELETE + status='scraped'). 7/24 manager dongusuyle.
    unpublished = 0
    for pid in gone_ids:
        try:
            await unpublish_product(pid)
            unpublished += 1
        except Exception:
            pass
    if gone:
        await log_activity(
            "source_recheck",
            f"{gone} yayinli urunun kaynagi oldu -> {unpublished} tanesi sitemizden otomatik kaldirildi (guven)",
            "warning",
        )
    return {"checked": len(before), "gone": gone, "unpublished": unpublished}

# ============================================
# BACKGROUND REMOVAL + WATERMARK
# ============================================
LOGO_PATH = BASE_DIR / "static" / "img" / "css_berlin_logo.png"
DESKTOP_OUTPUT = Path(os.path.expanduser("~")) / "Desktop" / "CSS_Berlin_Output"
DESKTOP_OUTPUT.mkdir(parents=True, exist_ok=True)

def apply_watermark(image, logo_path=None, opacity=0.15):
    """CSS Berlin logosunu gorsel uzerine saydam watermark olarak ekle"""
    from PIL import Image, ImageEnhance

    if logo_path is None:
        logo_path = str(LOGO_PATH)

    if not os.path.exists(logo_path):
        return image

    try:
        logo = Image.open(logo_path).convert("RGBA")

        # Logo boyutunu gorselin %25'i kadar ayarla
        img_w, img_h = image.size
        logo_target_w = int(img_w * 0.25)
        logo_ratio = logo.width / logo.height
        logo_target_h = int(logo_target_w / logo_ratio)
        logo = logo.resize((logo_target_w, logo_target_h), Image.LANCZOS)

        # Saydam yap
        alpha = logo.split()[3]
        alpha = ImageEnhance.Brightness(alpha).enhance(opacity)
        logo.putalpha(alpha)

        # Sag alt koseye simetrik yerlestir (padding %3)
        pad_x = int(img_w * 0.03)
        pad_y = int(img_h * 0.03)
        pos_x = img_w - logo_target_w - pad_x
        pos_y = img_h - logo_target_h - pad_y

        # Gorsele yapistir
        if image.mode != "RGBA":
            image = image.convert("RGBA")
        image.paste(logo, (pos_x, pos_y), logo)

        return image.convert("RGB")
    except Exception as e:
        print(f"[WATERMARK] Hata: {e}")
        return image

def _apply_organic_variation(image):
    """Hafif rastgele dondurme + zoom/kirpma uygular. Ayni kaynak gorselin
    birden fazla platformda/urunde piksel-birebir 'duplicate content' olarak
    isaretlenme riskini azaltir - anlam bozulmadan (agac govdesi degil, urunun
    kendisi net kalir), sadece kompozisyonda kucuk bir varyasyon yaratir."""
    import random
    from PIL import Image
    angle = random.uniform(-2.0, 2.0)
    rotated = image.rotate(angle, resample=Image.BICUBIC, expand=False, fillcolor=(255, 255, 255))
    width, height = rotated.size
    zoom = random.uniform(0.02, 0.04)
    dx, dy = int(width * zoom), int(height * zoom)
    cropped = rotated.crop((dx, dy, width - dx, height - dy))
    return cropped.resize((width, height), Image.LANCZOS)


async def process_background_removal(product_id: str):
    """Urun gorsellerinin arka planini kaldir + watermark ekle + masaustune kaydet.
    Max 6 gorsel islenir, her gorsel icin 30sn timeout uygulanir."""
    try:
        from rembg import remove
        from PIL import Image
        import io
        import requests as req

        MAX_IMAGES = 6

        async with aiosqlite.connect(DB_FILE) as db:
            cursor = await db.execute("SELECT images_json, title, source_platform, raw_images_json FROM products WHERE id=?", (product_id,))
            row = await cursor.fetchone()
            if not row:
                return
        # DB connection released here

        images = json.loads(row[0] or "[]")[:MAX_IMAGES]
        title = row[1] or "product"
        platform = row[2] or "unknown"
        processed_paths = []

        local_raw = [p for p in json.loads(row[3] or "[]") if Path(p).exists()]
        if local_raw:
            images = local_raw[:MAX_IMAGES]

        if not images:
            await log_activity("bg_skip", f"{product_id}: Gorsel yok", "warning")
            return

        safe_title = "".join(c for c in title[:40] if c.isalnum() or c in " _-").strip()
        product_output_dir = DESKTOP_OUTPUT / f"{platform}_{safe_title}_{product_id[-6:]}"
        product_output_dir.mkdir(parents=True, exist_ok=True)

        await log_activity("bg_start", f"{product_id}: {len(images)} gorsel isleniyor...")

        for i, img_url in enumerate(images):
            try:
                if not img_url or len(img_url) < 10:
                    continue

                dl_headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
                    "Referer": "https://www.google.com/",
                }

                def _fetch(u: str, _h=dl_headers):
                    try:
                        r = req.get(u, headers=_h, timeout=10)
                        return r.content if r.status_code == 200 and len(r.content) > 1000 else None
                    except Exception:
                        return None

                img_data = None
                if not img_url.lower().startswith("http") and Path(img_url).exists():
                    img_data = Path(img_url).read_bytes()
                else:
                    sourced = None
                    if _source_best_image is not None:
                        sourced = _source_best_image(img_url, platform=platform, fetch=_fetch)

                    if sourced is not None:
                        img_data = sourced.data
                        if sourced.upgraded:
                            await log_activity(
                                "image_upgraded",
                                f"{product_id} gorsel {i+1}: kucuk-resim yerine "
                                f"{sourced.width}x{sourced.height} indirildi")
                        if not sourced.meets_minimum:
                            await log_activity(
                                "image_too_small",
                                f"{product_id} gorsel {i+1}: sadece "
                                f"{sourced.width}x{sourced.height} bulunabildi "
                                f"(video icin yetersiz, urun kartinda kullanilir)", "warning")
                    elif img_url.lower().startswith("http"):
                        resp = req.get(img_url, headers=dl_headers, timeout=10, stream=False)
                        if resp.status_code != 200 or len(resp.content) < 1000:
                            continue
                        img_data = resp.content

                if not img_data:
                    continue

                if len(img_data) > 5_000_000:
                    tmp_img = Image.open(io.BytesIO(img_data))
                    tmp_img.thumbnail((1200, 1200), Image.LANCZOS)
                    buf = io.BytesIO()
                    tmp_img.save(buf, format="PNG")
                    img_data = buf.getvalue()

                if _matte_to_studio is None:
                    await log_activity("bg_skip", f"{product_id}: image_processor yuklenemedi", "error")
                    return

                final, _cut_q, _model_used = _matte_to_studio(img_data)
                if not _cut_q.likely_ok:
                    await log_activity(
                        "bg_qc_skip",
                        f"{product_id} gorsel {i+1}: supheli kesim ({_cut_q.reason}) "
                        f"[kaplama={_cut_q.coverage_pct}%] - YAYINLANMIYOR",
                        "warning",
                    )
                    continue

                filename = f"{product_id}_{i+1}.jpg"
                save_path = IMAGES_PROCESSED / filename
                final.save(str(save_path), "JPEG", quality=92)
                processed_paths.append(f"/data/images/processed/{filename}")

                final.save(str(product_output_dir / f"{i+1}.jpg"), "JPEG", quality=92)

            except Exception as e:
                await log_activity("bg_img_error", f"Gorsel {i+1}: {str(e)[:80]}", "warning")
                continue

        async with aiosqlite.connect(DB_FILE) as db:
            if processed_paths:
                await db.execute(
                    "UPDATE products SET processed_images_json=?, bg_removed=1, updated_at=? WHERE id=?",
                    (json.dumps(processed_paths), datetime.now().isoformat(), product_id)
                )
            else:
                await db.execute(
                    "UPDATE products SET bg_removed=-1, updated_at=? WHERE id=?",
                    (datetime.now().isoformat(), product_id)
                )
            await db.commit()

        count = len(processed_paths)
        await log_activity("bg_done", f"{product_id}: {count}/{len(images)} gorsel islendi")
        await broadcast_ws("bg_removed", {
            "product_id": product_id,
            "count": count,
            "paths": processed_paths,
            "desktop_path": str(product_output_dir),
        })

        if count > 0:
            await _try_auto_publish(product_id)

    except ImportError:
        await log_activity("bg_error", "rembg kurulu degil! pip install rembg[cpu]", "error")
    except Exception as e:
        await log_activity("bg_remove_error", f"Arka plan kaldirma hatasi: {str(e)}", "error")


# Cinsiyet kaliplari — kelime siniri ile, kivrik kesme isareti (') dahil.
# Almanca birlesik yazar (Herrenjacke, Damenmantel), o yuzden Almanca koklerde
# sondaki \b YOK — onek eslesmesi. Diger dillerde \b var, yoksa "men" kelimesi
# alakasiz sozcuklerin icinde eslesir.
_RE_KINDER = re.compile(
    r"\b(kinder|kids?\b|child(ren)?\b|enfant|bambino|barn\b|jungen|m(ae|ä)dchen|dziec)", re.I)
_RE_HERREN = re.compile(
    r"\b(herren|herrn|m(ae|ä)nner|men\b|mens\b|men[''’]s|homme|uomo|hombre|heren\b|m(e|ę)ski)", re.I)
_RE_DAMEN = re.compile(
    r"\b(damen|frauen|dame\b|women\b|women[''’]s|womens\b|ladies\b|femme|donna|mujer|damski)", re.I)


def _detect_category(title: str, seo_title: str = "", category: str = "") -> str:
    """cssberlin kategori slug'i tespit et.

    Cinsiyet belirsizse 'damen'e DUSMEZ — CATEGORY_FALLBACK doner. Aksi halde
    cinsiyeti bilinmeyen urunler kadin katalogunu kirletiyor (bkz. 66/117 vaka).
    """
    blob = f"{title or ''} {seo_title or ''} {category or ''}"
    if _RE_KINDER.search(blob):
        return "kinder"
    herren = bool(_RE_HERREN.search(blob))
    damen = bool(_RE_DAMEN.search(blob))
    if herren and not damen:
        return "herren"
    if damen and not herren:
        return "damen"
    return CATEGORY_FALLBACK


async def _try_auto_publish(product_id: str):
    """SEO + BG tamam ve henuz yayinlanmamissa otomatik yayinla."""
    import requests as req
    try:
        async with aiosqlite.connect(DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM products WHERE id=?", (product_id,))
            row = await cursor.fetchone()
            if not row:
                return
            cols = [d[0] for d in cursor.description]
            product = dict(zip(cols, row))

        if product.get("sync_origin"):
            return  # baska Hub'dan senkronla gelen urun: yayini sahibi yonetir
        if product.get("recommendation") != "buy":
            return
        seo_title = product.get("seo_title") or ""
        seo_desc = product.get("seo_description") or ""
        if not seo_title or seo_title.strip() in ("...", "None") or len(seo_title.strip()) < 10:
            return
        if not seo_desc or seo_desc.strip() in ("...", "None") or len(seo_desc.strip()) < 20:
            return
        is_update = bool(product.get("cssberlin_id"))
        proc_imgs = product.get("processed_images_json") or "[]"
        if proc_imgs == "[]":
            return

        CSSBERLIN_API_URL = os.getenv("CSSBERLIN_API_URL")
        CSSBERLIN_API_KEY = os.getenv("CSSBERLIN_API_KEY")
        if not CSSBERLIN_API_URL or not CSSBERLIN_API_KEY:
            return

        image_uploads = []
        for img in json.loads(proc_imgs):
            if img.startswith("/data/"):
                local_path = DATA_DIR / img[len("/data/"):]
                if local_path.is_file():
                    ct = "image/png" if str(local_path).endswith(".png") else "image/jpeg"
                    image_uploads.append((local_path.name, local_path.read_bytes(), ct))
        image_uploads = image_uploads[:8]
        if not image_uploads:
            return

        sell_price = product.get("estimated_sell_price") or (product.get("price", 0) * 1.5)
        aciklama = product.get("seo_description") or product.get("description", "") or ""

        cat_slug = _detect_category(product.get("title"), product.get("seo_title"),
                                   product.get("category"))

        form_fields = {
            "title": product.get("seo_title") or product.get("title", "Urun"),
            "description": aciklama,
            "price": str(float(sell_price)),
            "brand": product.get("brand") or "",
            "size": product.get("size") or "",
            "condition": "good",
            "category_slug": cat_slug,
            "source_platform": product.get("source_platform") or "",
            "source_url": product.get("source_url") or "",
            "hub_product_id": product_id,
        }
        multipart_files = [("images", (fn, data, ct)) for fn, data, ct in image_uploads]

        resp = await asyncio.to_thread(
            req.post, CSSBERLIN_API_URL, data=form_fields, files=multipart_files,
            headers={"x-api-key": CSSBERLIN_API_KEY}, timeout=60)

        if resp.status_code == 200 and resp.json().get("success"):
            cssberlin_id = resp.json().get("productId", "")
            if not is_update:
                for _retry in range(3):
                    try:
                        async with aiosqlite.connect(DB_FILE) as db:
                            await db.execute(
                                "UPDATE products SET status='published', cssberlin_id=?, updated_at=? WHERE id=?",
                                (cssberlin_id, datetime.now().isoformat(), product_id))
                            await db.commit()
                        break
                    except Exception:
                        await asyncio.sleep(2)
            action_label = "auto_update" if is_update else "auto_publish"
            await log_activity(action_label,
                f"{product_id}: {'guncellendi' if is_update else 'otomatik yayinlandi'} -> {cssberlin_id}")
        else:
            await log_activity("auto_publish_fail",
                f"{product_id}: {resp.status_code} {resp.text[:100]}", "warning")
    except Exception as e:
        await log_activity("auto_publish_error", f"{product_id}: {str(e)[:120]}", "warning")


# ============================================
# WATCHLIST / TAKIP LISTESI (10dk kontrol)
# ============================================
async def init_watchlist_table():
    """Takip listesi tablosunu olustur"""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS watchlist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id TEXT NOT NULL,
                source_url TEXT NOT NULL,
                last_status TEXT DEFAULT 'active',
                check_interval INTEGER DEFAULT 600,
                last_checked TEXT,
                notify_on_sold INTEGER DEFAULT 1,
                notify_on_price_drop INTEGER DEFAULT 1,
                original_price REAL DEFAULT 0,
                current_price REAL DEFAULT 0,
                added_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (product_id) REFERENCES products(id)
            );
            CREATE INDEX IF NOT EXISTS idx_watchlist_product ON watchlist(product_id);
        """)
        await db.commit()

@app.on_event("startup")
async def startup_watchlist():
    await init_watchlist_table()

@app.post("/api/watchlist/add")
async def add_to_watchlist(request: Request):
    """Urunu takip listesine ekle"""
    body = await request.json()
    product_id = body.get("product_id")

    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute("SELECT source_url, price FROM products WHERE id=?", (product_id,))
        row = await cursor.fetchone()
        if not row:
            return JSONResponse({"error": "Urun bulunamadi"}, status_code=404)

        # Zaten takipte mi?
        cursor2 = await db.execute("SELECT id FROM watchlist WHERE product_id=?", (product_id,))
        if await cursor2.fetchone():
            return {"status": "already_watching", "product_id": product_id}

        await db.execute(
            "INSERT INTO watchlist (product_id, source_url, original_price, current_price) VALUES (?,?,?,?)",
            (product_id, row[0], row[1], row[1])
        )
        await db.commit()

    await log_activity("watchlist_add", f"Takip listesine eklendi: {product_id}")
    return {"status": "added", "product_id": product_id}

@app.get("/api/demand/cross")
async def demand_cross(dimensions: str = "category,gender", min_trials: int = 10,
                       limit: int = 40):
    """
    Capraz talep sorgusu: istenen kirilimlarda satis orani + Wilson araligi.

    dimensions ornekleri:
      category,gender        -> kategori x cinsiyet
      category,size          -> kategori x beden
      brand,price_band       -> marka x fiyat bandi
      platform,category      -> hangi platform hangi kategoride satiyor

    HAM ORAN DEGIL Wilson alt siniri raporlanir: 2/3 (%67) ile 200/300 (%67)
    ayni degildir; alt sinir bu farki gorunur kilar ve kucuk orneklem
    yanilgisini onler.
    """
    depo = _obs_store()
    if not depo or not _demand_stats:
        return JSONResponse({"error": "gozlem deposu yuklenemedi"}, status_code=503)

    boyutlar = [d.strip() for d in dimensions.split(",") if d.strip()]
    try:
        satirlar = await asyncio.to_thread(
            depo.cross_query, boyutlar, min_trials=max(1, min_trials))
    except Exception as e:
        return JSONResponse(
            {"error": f"sorgu basarisiz (indeks kurulmamis olabilir): {str(e)[:160]}"},
            status_code=500)

    cikti = []
    for r in satirlar[:limit]:
        n = int(r.get("trials") or 0)
        s = int(r.get("successes") or 0)
        alt, ust = _demand_stats.wilson_interval(s, n)
        cikti.append({
            **{d: r.get(d) for d in boyutlar},
            "gozlem": n, "satis": s,
            "ham_oran": round(s / n, 4) if n else 0.0,
            "wilson_alt": alt, "wilson_ust": ust,
            "guven": "yuksek" if n >= 50 else ("orta" if n >= 15 else "dusuk"),
            "ort_fiyat_eur": r.get("avg_price"),
            "ort_satis_gunu": r.get("avg_days"),
            "gereken_ek_gozlem": max(
                0, _demand_stats.required_sample_size(s / n if n else 0.3) - n),
        })
    return {"dimensions": boyutlar, "rows": cikti,
            "not": "wilson_alt = kotumser ama durust tahmin; siralama icin bunu kullan"}


@app.post("/api/demand/reindex")
async def demand_reindex():
    """TSV loglarindan SQLite indeksini yeniden kurar (DBeaver bunu okur)."""
    depo = _obs_store()
    if not depo:
        return JSONResponse({"error": "gozlem deposu yok"}, status_code=503)
    n = await asyncio.to_thread(depo.rebuild_index)
    boyut = depo.size_on_disk()
    await log_activity("demand_reindex", f"{n} gozlem indekslendi")
    return {"indexed": n, "size": boyut,
            "db_path": str(depo.db_path),
            "categories": depo.categories()}


@app.post("/api/watchlist/remove")
async def remove_from_watchlist_post(request: Request):
    """
    Favoriden cikar (POST). Urun listesindeki kalp butonu ac/kapa calisabilsin
    diye eklendi: onceden yalnizca DELETE /api/watchlist/{id} vardi, arayuz
    onu hic cagirmiyordu — bu yuzden favori "geri alinamiyor", buton da hicbir
    zaman dolu/bos durum degistirmiyordu.
    """
    body = await request.json()
    product_id = body.get("product_id")
    async with aiosqlite.connect(DB_FILE) as db:
        cur = await db.execute("SELECT id FROM watchlist WHERE product_id=?", (product_id,))
        if not await cur.fetchone():
            return {"status": "not_found", "product_id": product_id}
        await db.execute("DELETE FROM watchlist WHERE product_id=?", (product_id,))
        await db.commit()
    await log_activity("watchlist_remove", f"Favorilerden cikarildi: {product_id}")
    return {"status": "removed", "product_id": product_id}


@app.delete("/api/watchlist/{product_id}")
async def remove_from_watchlist(product_id: str):
    """Urunu takip listesinden cikar"""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("DELETE FROM watchlist WHERE product_id=?", (product_id,))
        await db.commit()
    await log_activity("watchlist_remove", f"Takip listesinden cikarildi: {product_id}")
    return {"status": "removed", "product_id": product_id}

@app.get("/api/watchlist")
async def get_watchlist():
    """Takip listesindeki tum urunleri getir"""
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute("""
            SELECT w.*, p.title, p.source_platform, p.images_json, p.price, p.source_status
            FROM watchlist w
            LEFT JOIN products p ON w.product_id = p.id
            ORDER BY w.added_at DESC
        """)
        cols = [d[0] for d in cursor.description]
        items = [dict(zip(cols, row)) for row in await cursor.fetchall()]
    return {"watchlist": items, "count": len(items)}

# ============================================
# GORSEL ARAMA: urunun / yuklenen fotografin HALA YAYINDA olan benzerleri (istatistik/gorsel.db)
# Goz kontrolu icindir: "eslesme yok" denen urunleri ve hoslanilan urunun aynilarini bulmak.
# Model (CLIP) ilk aramada ~30 sn'de yuklenir; is parcaciginda calisir, hub'i dondurmaz.
# ============================================
@app.get("/api/gorsel/durum")
async def gorsel_durum():
    from logic import gorsel_arama as GA
    return await asyncio.to_thread(GA.status)


@app.get("/api/gorsel/benzer/{product_id}")
async def gorsel_benzer(product_id: str, k: int = 24):
    from logic import gorsel_arama as GA
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT id, title, source_url, images_json, raw_images_json, processed_images_json "
                               "FROM products WHERE id=?", (product_id,))
        row = await cur.fetchone()
    if not row:
        return JSONResponse({"status": "error", "error": "Urun yok"}, 404)
    try:
        return await asyncio.to_thread(GA.similar_to_product, dict(row), max(1, min(k, 60)))
    except Exception as e:
        return JSONResponse({"status": "error", "error": f"{type(e).__name__}: {str(e)[:150]}"}, 500)


@app.post("/api/gorsel/ara")
async def gorsel_ara(request: Request):
    from logic import gorsel_arama as GA
    body = await request.json()
    if not body.get("image"):
        return JSONResponse({"status": "error", "error": "Gorsel yok"}, 400)
    try:
        return await asyncio.to_thread(GA.similar_to_upload, body["image"], max(1, min(int(body.get("k", 24)), 60)))
    except Exception as e:
        return JSONResponse({"status": "error", "error": f"{type(e).__name__}: {str(e)[:150]}"}, 500)


# ============================================
# NOKTA ATIS: capraz platform degerlemeleri (istatistik/capraz.db, salt okunur)
# Favori / yayin sureclerinin DISINDA. Karar vermez; kullanici "TATANGA'ya Al" derse urun olusur.
# ============================================
@app.get("/nokta-atis", response_class=HTMLResponse)
async def nokta_atis_page(request: Request, sekme: str = "cok_karli", run: str = "", platform: str = "",
                          kategori: str = "", marka: str = "", min_net: str = "", sira: str = "beklenen"):
    from logic import nokta_atis as NA
    taramalar = NA.runs()
    run_id = run or (taramalar[0]["run_id"] if taramalar else "")
    secili = next((t for t in taramalar if t["run_id"] == run_id), None)
    try:
        mn = float(min_net) if min_net else None
    except ValueError:
        mn = None
    items = NA.firsatlar(run_id, sekme == "cok_karli", platform, kategori, marka, mn, sira) if run_id else []
    alinan = {}
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS nokta_atis_alinan (firsat_id TEXT PRIMARY KEY, "
                         "product_id TEXT, run_id TEXT, alindi TEXT)")
        await db.commit()
        cur = await db.execute("SELECT a.firsat_id, a.product_id, p.status FROM nokta_atis_alinan a "
                               "LEFT JOIN products p ON p.id = a.product_id")
        alinan = {r[0]: {"product_id": r[1], "status": r[2]} for r in await cur.fetchall()}
    for it in items:
        it["tatanga"] = alinan.get(it["firsat_id"])
    return templates.TemplateResponse("nokta_atis.html", {
        "request": request, "sekme": sekme, "taramalar": taramalar, "secili": secili, "run_id": run_id,
        "items": items, "facets": NA.facets(run_id) if run_id else {},
        "f": {"platform": platform, "kategori": kategori, "marka": marka, "min_net": min_net, "sira": sira},
    })


@app.post("/api/nokta-atis/al")
async def nokta_atis_al(request: Request):
    """Secilen firsati TATANGA urunu yapar (kaniti arbitrage_json'da). Ayni kaynak varsa yeniden olusturmaz."""
    from logic import nokta_atis as NA
    body = await request.json()
    f = NA.firsat(body.get("run_id", ""), body.get("firsat_id", ""))
    if not f:
        return JSONResponse({"status": "error", "error": "Firsat bulunamadi (tarama yenilenmis olabilir)"}, 404)
    row = NA.product_row(f, gen_id)
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS nokta_atis_alinan (firsat_id TEXT PRIMARY KEY, "
                         "product_id TEXT, run_id TEXT, alindi TEXT, kanit_json TEXT)")
        cur = await db.execute("SELECT id FROM products WHERE source_url=?", (row["source_url"],))
        hit = await cur.fetchone()
        if hit:
            pid, created = hit[0], False
        else:
            pid, created = row["id"], True
            await db.execute("""
                INSERT INTO products (id, source_platform, source_url, source_id, title, price, currency, brand,
                    size, condition, category, images_json, estimated_sell_price, profit_margin, profit_euro,
                    total_cost, recommendation, best_sell_platform, arbitrage_json, scraped_at, status)
                VALUES (?,?,?,?,?,?,'EUR',?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                row["id"], row["source_platform"], row["source_url"], row["source_id"], row["title"], row["price"],
                row["brand"], row["size"], row["condition"], row["category"], row["images_json"],
                row["estimated_sell_price"], row["profit_margin"], row["profit_euro"], row["total_cost"],
                row["recommendation"], row["best_sell_platform"], row["arbitrage_json"], row["scraped_at"],
                row["status"]))
        cols = {r[1] for r in await (await db.execute("PRAGMA table_info(nokta_atis_alinan)")).fetchall()}
        if "kanit_json" not in cols:
            await db.execute("ALTER TABLE nokta_atis_alinan ADD COLUMN kanit_json TEXT")
        await db.execute("INSERT OR REPLACE INTO nokta_atis_alinan (firsat_id, product_id, run_id, alindi, kanit_json) "
                         "VALUES (?,?,?,?,?)", (f["firsat_id"], pid, f["run_id"], datetime.now().isoformat(),
                                                row["kanit_json"]))
        await db.commit()
    if created:
        await log_activity("nokta_atis", f"Nokta atis -> urun: {row['title'][:50]} ({f['platform']}, "
                                         f"tutucu net {row['profit_euro']} EUR)")
    return {"status": "ok", "product_id": pid, "created": created,
            "sell_price": row["estimated_sell_price"], "publish_condition": row["publish_condition"]}


@app.get("/watchlist", response_class=HTMLResponse)
async def watchlist_page(request: Request):
    """Takip listesi sayfasi"""
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute("""
            SELECT w.*, p.title, p.source_platform, p.images_json, p.price as current_product_price,
                   p.source_status, p.source_url as product_source_url, p.profit_euro,
                   p.profit_margin, p.recommendation, p.brand, p.size, p.condition,
                   p.estimated_sell_price, p.shipping_cost, p.status as product_status
            FROM watchlist w
            LEFT JOIN products p ON w.product_id = p.id
            ORDER BY w.added_at DESC
        """)
        cols = [d[0] for d in cursor.description]
        items = [dict(zip(cols, row)) for row in await cursor.fetchall()]

    return templates.TemplateResponse("watchlist.html", {
        "request": request,
        "watchlist": items,
    })

async def run_watchlist_checker():
    """5 dakikada bir takip listesindeki urunleri kontrol et"""
    while True:
        try:
            async with aiosqlite.connect(DB_FILE) as db:
                cursor = await db.execute("SELECT product_id FROM watchlist")
                items = await cursor.fetchall()

            if items:
                await log_activity("watchlist_check", f"{len(items)} urun kontrol ediliyor...")
                for (product_id,) in items:
                    try:
                        await check_product_source(product_id)
                        await asyncio.sleep(3)  # Rate limit
                    except Exception as e:
                        await log_activity("watchlist_error", f"{product_id}: {str(e)}", "warning")

                await log_activity("watchlist_check", f"{len(items)} urun kontrol edildi")
        except Exception as e:
            print(f"[WATCHLIST] Checker hatasi: {e}")

        await asyncio.sleep(300)  # 5 dakika bekle

@app.on_event("startup")
async def start_watchlist_checker():
    asyncio.create_task(run_watchlist_checker())

# ============================================
# SCHEDULED SCRAPER (Otonom calisma)
# ============================================
async def run_scheduled_scraper():
    """Zamanlanmis kazima - settings'den okunan anahtar kelimelerle"""
    while True:
        try:
            # Settings'den zamanlanmis kazimalari oku
            settings_file = DATA_DIR / "scheduler_settings.json"
            if settings_file.exists():
                with open(settings_file, "r", encoding="utf-8") as f:
                    settings = json.load(f)

                if settings.get("enabled", False):
                    keywords = settings.get("keywords", [])
                    platforms = settings.get("platforms", ["vinted", "ebay"])
                    interval = settings.get("interval_minutes", 60)

                    for kw in keywords:
                        job_id = gen_id("SCHED")
                        async with aiosqlite.connect(DB_FILE) as db:
                            await db.execute(
                                "INSERT INTO scrape_jobs (id, keyword, platforms, status, started_at) VALUES (?, ?, ?, 'running', ?)",
                                (job_id, kw, json.dumps(platforms), datetime.now().isoformat())
                            )
                            await db.commit()
                        await run_scrape_job(job_id, kw, platforms, 2)
                        await asyncio.sleep(10)

                    await asyncio.sleep(interval * 60)
                else:
                    await asyncio.sleep(300)  # 5dk sonra tekrar kontrol
            else:
                await asyncio.sleep(300)
        except Exception as e:
            print(f"[SCHEDULER] Hata: {e}")
            await asyncio.sleep(300)

@app.on_event("startup")
async def start_scheduler():
    asyncio.create_task(run_scheduled_scraper())

@app.get("/api/scheduler")
async def get_scheduler_settings():
    """Zamanlanmis kazima ayarlarini getir"""
    settings_file = DATA_DIR / "scheduler_settings.json"
    if settings_file.exists():
        with open(settings_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"enabled": False, "keywords": [], "platforms": ["vinted", "ebay"], "interval_minutes": 60}

@app.post("/api/scheduler")
async def save_scheduler_settings(request: Request):
    """Zamanlanmis kazima ayarlarini kaydet"""
    body = await request.json()
    settings_file = DATA_DIR / "scheduler_settings.json"
    with open(settings_file, "w", encoding="utf-8") as f:
        json.dump(body, f, indent=2, ensure_ascii=False)
    await log_activity("scheduler", f"Zamanlayici guncellendi: {'Aktif' if body.get('enabled') else 'Pasif'}")
    return {"status": "saved"}

# ============================================
# TELEGRAM BOT INTEGRATION (Unified v2)
# ============================================
@app.on_event("startup")
async def start_telegram_bot():
    """Telegram bot'u baslat"""
    if TELEGRAM_AVAILABLE:
        asyncio.create_task(run_bot_polling())
        await log_activity("telegram", "Telegram bot baslatildi (Unified v2)")

@app.get("/api/telegram/status")
async def telegram_status():
    """Telegram bot durumu + kanal bilgileri"""
    if not TELEGRAM_AVAILABLE:
        return {"status": "unavailable", "error": "telegram_bot.py bulunamadi"}
    cfg = load_telegram_config()
    bot = get_bot()
    bot_info = None
    if bot:
        try:
            me = bot.get_me()
            if me.get("ok"):
                bot_info = me["result"]
        except:
            pass
    return {
        "status": "active" if bot_info else "inactive",
        "bot_token_set": bool(cfg.get("bot_token")),
        "channels": cfg.get("channels", {}),
        "allowed_chats": cfg.get("allowed_chat_ids", []),
        "bot_info": bot_info,
    }

@app.post("/api/telegram/config")
async def set_telegram_config(request: Request):
    """Telegram bot yapilandirmasi"""
    body = await request.json()
    token = body.get("bot_token")
    chat_ids = body.get("allowed_chat_ids")
    channels = body.get("channels")
    if TELEGRAM_AVAILABLE:
        save_telegram_config(token=token, chat_ids=chat_ids, channels=channels)
        await log_activity("telegram", "Telegram yapilandirmasi guncellendi")
        return {"status": "saved"}
    return {"status": "error", "error": "Telegram modulu mevcut degil"}

@app.post("/api/telegram/test")
async def test_telegram(request: Request):
    """Telegram bot test mesaji gonder - kanal secimi destekler"""
    body = await request.json()
    message = body.get("message", "TATANGA Hub test mesaji!")
    channel = body.get("channel", "all")  # all, bildirimler, sistem_hata, captcha, admin
    if not TELEGRAM_AVAILABLE:
        return {"status": "error", "error": "Telegram modulu mevcut degil"}
    bot = get_bot()
    if not bot:
        return {"status": "error", "error": "Bot token ayarlanmamis"}

    results = []

    if channel == "all":
        # Tum kanallara gonder
        cfg = load_telegram_config()
        for name, cid in cfg.get("channels", {}).items():
            try:
                resp = bot.send_message(cid, f"[{name.upper()}] {message}")
                results.append({"channel": name, "chat_id": cid, "ok": resp.get("ok", False)})
            except Exception as e:
                results.append({"channel": name, "chat_id": cid, "ok": False, "error": str(e)})
    else:
        # Belirli kanala gonder
        cfg = load_telegram_config()
        cid = cfg.get("channels", {}).get(channel)
        if cid:
            try:
                resp = bot.send_message(cid, message)
                results.append({"channel": channel, "chat_id": cid, "ok": resp.get("ok", False)})
            except Exception as e:
                results.append({"channel": channel, "chat_id": cid, "ok": False, "error": str(e)})
        else:
            return {"status": "error", "error": f"Kanal bulunamadi: {channel}"}

    return {"status": "sent", "results": results}

# ============================================
# SEO CONTENT GENERATION (Groq AI)
# ============================================
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

async def generate_seo_content(product_id: str, target_platform: str = "cssberlin"):
    """AI ile platform bazli SEO baslik + aciklama + etiketler uret"""
    import requests as req

    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute(
            "SELECT title, description, brand, size, color, condition, category, price, source_platform FROM products WHERE id=?",
            (product_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return

        title, desc, brand, size, color, condition, category, price, source = row

        platform_guidelines = {
            "cssberlin": "CSS Berlin (2.el online mağaza, Almanca, profesyonel ton, sürdürülebilir moda vurgusu)",
            "vinted": "Vinted (samimi, genç ton, hashtag kullan, max 150 karakter başlık)",
            "ebay": "eBay (profesyonel, detaylı, marka-model-beden-renk bilgisi başlıkta)",
            "kleinanzeigen": "Kleinanzeigen (kısa, öz, fiyat bilgisi vurgulu, VB yazılabilir)",
            "willhaben": "Willhaben (Avusturya pazarı, Almanca, resmi ton)",
            "tradera": "Tradera (İsveç pazarı, İsveççe/İngilizce, açık artırma formatı)",
            "leboncoin": "Leboncoin (Fransa pazarı, Fransızca, samimi ton)",
        }

        guideline = platform_guidelines.get(target_platform, platform_guidelines["cssberlin"])

        prompt = f"""Du bist ein SEO-Experte für Second-Hand-Mode. Erstelle für folgendes Produkt optimierte Inhalte auf DEUTSCH.
WICHTIG: Falls der Produkttitel in einer anderen Sprache ist (Französisch, Polnisch, Englisch etc.), übersetze und adaptiere ihn ins Deutsche.

Produkt: {title}
Beschreibung: {desc or 'Keine'}
Marke: {brand or 'Unbekannt'}
Größe: {size or 'Nicht angegeben'}
Farbe: {color or 'Nicht angegeben'}
Zustand: {condition or 'Gebraucht'}
Kategorie: {category or 'Mode'}
Preis: {price} EUR
Plattform: {guideline}

Erstelle als JSON (alle Werte auf Deutsch, KEINE Platzhalter wie "..." verwenden):
{{
  "seo_title": "SEO-optimierter Titel auf Deutsch (max 80 Zeichen, Marke + Typ + Größe)",
  "seo_description": "Deutsche Verkaufsbeschreibung (150-300 Zeichen, Vorteile hervorheben)",
  "seo_keywords": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5"],
  "seo_tags": ["#tag1", "#tag2", "#tag3", "#tag4", "#tag5"]
}}

NUR JSON ausgeben, nichts anderes. Keine Platzhalter, keine "...", keine leeren Werte."""

        try:
            resp = req.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "qwen/qwen3.6-27b",
                    "messages": [
                        {"role": "system", "content": "/no_think"},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 2048,
                },
                timeout=60,
            )

            if resp.status_code == 429:
                retry_after = int(resp.headers.get("retry-after", "30"))
                await log_activity("seo_rate_limit", f"{product_id}: TPM limiti — {retry_after}s bekleniyor")
                await asyncio.sleep(retry_after + 2)
                resp = req.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
                    json={"model": "qwen/qwen3.6-27b", "messages": [{"role": "system", "content": "/no_think"}, {"role": "user", "content": prompt}], "temperature": 0.3, "max_tokens": 2048},
                    timeout=60,
                )
            if resp.status_code != 200:
                await log_activity("seo_error", f"Groq API hatasi: {resp.status_code} — {resp.text[:200]}", "error")
                return None

            resp_json = resp.json()
            content = resp_json["choices"][0]["message"].get("content") or ""
            content = content.strip()
            if "</think>" in content:
                content = content.split("</think>", 1)[1].strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1].rsplit("```", 1)[0]
            content = content.strip()

            def _extract_json(text):
                start = text.find("{")
                if start == -1:
                    return text
                depth, end = 0, start
                in_str = False
                escape = False
                for i in range(start, len(text)):
                    c = text[i]
                    if escape:
                        escape = False
                        continue
                    if c == "\\":
                        escape = True
                        continue
                    if c == '"' and not escape:
                        in_str = not in_str
                        continue
                    if in_str:
                        continue
                    if c == "{":
                        depth += 1
                    elif c == "}":
                        depth -= 1
                        if depth == 0:
                            end = i
                            break
                return text[start:end + 1]

            content = _extract_json(content)

            if not content or content == "{" or len(content) < 10:
                await log_activity("seo_error", f"{product_id}: bos icerik (model cikti vermedi)", "warning")
                return None

            try:
                seo_data = json.loads(content)
            except json.JSONDecodeError:
                import re
                content = re.sub(r",\s*}", "}", content)
                content = re.sub(r",\s*]", "]", content)
                content = content.replace("'", '"')
                content = re.sub(r'(?<=[\{,])\s*([a-zA-Z_]\w*)\s*:', r' "\1":', content)
                try:
                    seo_data = json.loads(content)
                except json.JSONDecodeError:
                    await log_activity("seo_error", f"{product_id}: JSON ayrilamadi: {content[:100]}", "warning")
                    return None

            seo_title = seo_data.get("seo_title", "")
            seo_desc = seo_data.get("seo_description", "")
            if not seo_title or seo_title.strip() in ("...", "None", "") or len(seo_title.strip()) < 10:
                await log_activity("seo_error", f"{product_id}: gecersiz baslik: '{seo_title}'", "warning")
                return None
            if not seo_desc or seo_desc.strip() in ("...", "None", "") or len(seo_desc.strip()) < 20:
                await log_activity("seo_error", f"{product_id}: gecersiz aciklama: '{seo_desc[:50]}'", "warning")
                return None

            await db.execute("""
                UPDATE products SET
                    seo_title=?, seo_description=?, seo_keywords=?, seo_tags=?, updated_at=?
                WHERE id=?
            """, (
                seo_title.strip(),
                seo_desc.strip(),
                json.dumps(seo_data.get("seo_keywords", [])),
                json.dumps(seo_data.get("seo_tags", [])),
                datetime.now().isoformat(),
                product_id,
            ))
            await db.commit()

            await log_activity("seo_generated", f"{product_id}: SEO icerigi olusturuldu ({target_platform})")
            await broadcast_ws("seo_generated", {
                "product_id": product_id,
                "platform": target_platform,
                "seo": seo_data,
            })

            await _try_auto_publish(product_id)
            return seo_data

        except Exception as e:
            await log_activity("seo_error", f"SEO uretim hatasi: {type(e).__name__}: {str(e)[:200]}", "error")
            return None

def _template_seo(title: str, brand: str, size: str, condition: str, color: str, category: str, price: float) -> dict:
    """Groq olmadan sablonla Almanca SEO uret."""
    import re as _re

    garment_map = [
        ("steppjacke", "Steppjacke"), ("pufferjacke", "Pufferjacke"), ("puffer", "Pufferjacke"),
        ("daunenjacke", "Daunenjacke"), ("down jacket", "Daunenjacke"), ("dunjacka", "Daunenjacke"),
        ("softshell", "Softshelljacke"), ("fleece", "Fleecejacke"), ("windbreaker", "Windjacke"),
        ("winterjacke", "Winterjacke"), ("regenjacke", "Regenjacke"), ("snowboard", "Snowboardjacke"),
        ("ski ", "Skijacke"), ("bombers", "Bomberjacke"), ("bomber", "Bomberjacke"),
        ("parka", "Parka"), ("anorak", "Anorak"), ("mantel", "Mantel"), ("coat", "Mantel"),
        ("hoodie", "Hoodie"), ("kapuzenjacke", "Kapuzenjacke"), ("hooded", "Kapuzenjacke"),
        ("blazer", "Blazer"), ("cardigan", "Strickjacke"), ("vest", "Weste"), ("gilet", "Weste"),
        ("pullover", "Pullover"), ("sweater", "Pullover"), ("sweatshirt", "Sweatshirt"),
        ("shirt", "Hemd"), ("t-shirt", "T-Shirt"), ("bluse", "Bluse"),
        ("hose", "Hose"), ("pants", "Hose"), ("jeans", "Jeans"), ("shorts", "Shorts"),
        ("rock", "Rock"), ("skirt", "Rock"), ("kleid", "Kleid"), ("dress", "Kleid"),
        ("jacke", "Jacke"), ("jacket", "Jacke"), ("veste", "Jacke"), ("kurtka", "Jacke"),
        ("jacka", "Jacke"),
    ]
    title_lower = title.lower()
    garment_de = "Jacke"
    for pattern, de in garment_map:
        if pattern in title_lower:
            garment_de = de
            break

    model_keywords = []
    for kw in ["Omni-Heat", "Omni-Shield", "Turbodown", "Bugaboo", "Powder Lite",
               "Cascade Ridge", "Horizon Explorer", "Huntsville Peak", "Slick Creek",
               "Barlow Pass", "Convert", "Gore-Tex", "Waterproof", "Thermoball"]:
        if kw.lower() in title_lower:
            model_keywords.append(kw)

    cond_map = {"new_with_tags": "Neu mit Etikett", "new_without_tags": "Neu ohne Etikett",
                "very_good": "Sehr gut", "good": "Gut", "acceptable": "Akzeptabel",
                "new": "Neu", "neuf": "Neu", "nowa": "Neu", "nowy": "Neu"}
    cond_de = cond_map.get((condition or "").lower().replace(" ", "_"), "Second-Hand")
    if any(w in title_lower for w in ("neuve", "neuf", "nowa", "neu ", "new ")):
        cond_de = "Neu"
    if "etikett" in title_lower or "étiquette" in title_lower or "tags" in title_lower:
        cond_de = "Neu mit Etikett"

    gender = {"herren": "Herren", "damen": "Damen", "kinder": "Kinder"}.get(
        _detect_category(title), "")

    brand_clean = brand or ""
    if not brand_clean:
        for known in ["Columbia", "Nike", "Adidas", "Patagonia", "The North Face", "Zara", "H&M",
                       "Mango", "Puma", "Reebok", "Levi's", "Tommy Hilfiger", "Ralph Lauren",
                       "Jack Wolfskin", "Mammut", "Arc'teryx", "Salomon", "Berghaus"]:
            if known.lower() in title_lower:
                brand_clean = known
                break

    size_clean = size or ""
    if not size_clean:
        m = _re.search(r'\b(XXS|XS|S|M|L|XL|XXL|XXXL)\b', title, _re.IGNORECASE)
        if m:
            size_clean = m.group(1).upper()

    color_clean = color or ""
    if not color_clean:
        for c_name in ["Schwarz", "Weiß", "Grau", "Blau", "Rot", "Grün", "Gelb", "Orange",
                        "Braun", "Rosa", "Lila", "Türkis", "Navy", "Beige", "Dunkelblau"]:
            if c_name.lower() in title_lower:
                color_clean = c_name
                break
        if not color_clean:
            color_map = {"black": "Schwarz", "white": "Weiß", "grey": "Grau", "gray": "Grau",
                         "blue": "Blau", "red": "Rot", "green": "Grün", "noir": "Schwarz",
                         "gris": "Grau", "bleu": "Blau", "rouge": "Rot", "saumon": "Lachs"}
            for eng, de in color_map.items():
                if eng in title_lower:
                    color_clean = de
                    break

    parts = [brand_clean]
    if model_keywords:
        parts.append(model_keywords[0])
    if gender:
        parts.append(f"{gender}{garment_de}" if garment_de != "Jacke" else f"{gender}jacke")
    else:
        parts.append(garment_de)
    if color_clean:
        parts.append(color_clean)
    if size_clean:
        parts.append(size_clean)
    if cond_de in ("Neu", "Neu mit Etikett"):
        parts.append(f"| {cond_de}")
    parts.append("| CSS Berlin")
    seo_title = " ".join(p for p in parts if p)[:80]

    desc_parts = []
    full_name = f"{brand_clean} {garment_de}" if brand_clean else garment_de
    if model_keywords:
        full_name += f" {model_keywords[0]}"
    if gender:
        desc_parts.append(f"Hochwertige {full_name} für {gender}")
    else:
        desc_parts.append(f"Hochwertige {full_name}")
    if size_clean:
        desc_parts.append(f"in Größe {size_clean}")
    if color_clean:
        desc_parts.append(f"in {color_clean}")
    desc_parts.append(f"– Zustand: {cond_de}.")
    desc_parts.append("Nachhaltig einkaufen bei CSS Berlin.")
    desc_parts.append("Schneller Versand, Käuferschutz inklusive.")
    seo_desc = " ".join(desc_parts)

    kw = [brand_clean.lower(), garment_de.lower(), "second hand", "nachhaltig", "gebraucht"]
    if gender:
        kw.insert(1, gender.lower())
    kw = [k for k in kw if k][:5]
    tags = [f"#{k.replace(' ', '')}" for k in kw]

    return {"seo_title": seo_title, "seo_description": seo_desc, "seo_keywords": kw, "seo_tags": tags}

async def generate_seo_template(product_id: str):
    """Sablonla SEO uret — Groq API kullanmaz, aninda calisir."""
    for _attempt in range(5):
        try:
            async with aiosqlite.connect(DB_FILE, timeout=30) as db:
                cursor = await db.execute(
                    "SELECT title, description, brand, size, color, condition, category, price FROM products WHERE id=?",
                    (product_id,)
                )
                row = await cursor.fetchone()
                if not row:
                    return None
                title, desc, brand, size, color, condition, category, price = row
            break
        except Exception:
            await asyncio.sleep(3)
    else:
        return None

    seo_data = _template_seo(title, brand or "", size or "", condition or "", color or "", category or "", price or 0)

    for _attempt in range(5):
        try:
            async with aiosqlite.connect(DB_FILE, timeout=30) as db:
                await db.execute("""
                    UPDATE products SET seo_title=?, seo_description=?, seo_keywords=?, seo_tags=?, updated_at=?
                    WHERE id=?
                """, (
                    seo_data["seo_title"], seo_data["seo_description"],
                    json.dumps(seo_data["seo_keywords"]), json.dumps(seo_data["seo_tags"]),
                    datetime.now().isoformat(), product_id,
                ))
                await db.commit()
            break
        except Exception:
            await asyncio.sleep(3)

    await log_activity("seo_template", f"{product_id}: sablon SEO olusturuldu")
    asyncio.ensure_future(_try_auto_publish(product_id))
    return seo_data

@app.post("/api/product/{product_id}/generate-seo")
async def api_generate_seo(product_id: str, request: Request, background_tasks: BackgroundTasks):
    """Urun icin SEO icerik uret"""
    body = await request.json() if request.headers.get("content-type") == "application/json" else {}
    platform = body.get("platform", "cssberlin")
    use_template = body.get("template", False)
    if use_template:
        background_tasks.add_task(generate_seo_template, product_id)
    else:
        background_tasks.add_task(generate_seo_content, product_id, platform)
    return {"status": "generating", "product_id": product_id, "platform": platform, "template": use_template}

async def _bulk_seo_worker(product_ids: list, platform: str, use_template: bool = False):
    ok, fail = 0, 0
    for pid in product_ids:
        try:
            if use_template:
                result = await generate_seo_template(pid)
            else:
                result = await generate_seo_content(pid, platform)
            if result:
                ok += 1
            else:
                fail += 1
        except Exception:
            fail += 1
        if use_template:
            await asyncio.sleep(3)
        else:
            await asyncio.sleep(25)
    await log_activity("bulk_seo_done", f"{ok} basarili, {fail} basarisiz ({len(product_ids)} toplam, template={use_template})")

@app.post("/api/products/bulk-seo")
async def bulk_generate_seo(request: Request, background_tasks: BackgroundTasks):
    """Tum SEO icerik olmayan urunler icin SEO uret — template=true ile sablonla aninda"""
    body = await request.json() if request.headers.get("content-type") == "application/json" else {}
    platform = body.get("platform", "cssberlin")
    limit = int(body.get("limit", 20))
    use_template = body.get("template", False)

    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute(
            "SELECT id FROM products WHERE (seo_title IS NULL OR seo_title = '' OR seo_title = '...' OR seo_title = 'None' OR LENGTH(seo_title) < 10) AND recommendation='buy' LIMIT ?",
            (limit,)
        )
        products = await cursor.fetchall()

    pids = [pid for (pid,) in products]
    background_tasks.add_task(_bulk_seo_worker, pids, platform, use_template)

    return {"status": "generating", "count": len(pids), "platform": platform, "template": use_template}

# ============================================
# BULK OPERATIONS
# ============================================
@app.post("/api/products/bulk-bg-remove")
async def bulk_bg_remove(background_tasks: BackgroundTasks):
    """Tum BG kaldirilmamis urunleri isle"""
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute(
            """SELECT id FROM products WHERE bg_removed=0 AND images_json != '[]'
               AND recommendation='buy'
               ORDER BY CASE WHEN seo_title IS NOT NULL AND seo_title != '' THEN 0 ELSE 1 END,
                        rowid
               LIMIT 30"""
        )
        products = await cursor.fetchall()

    for (pid,) in products:
        background_tasks.add_task(process_background_removal, pid)

    return {"status": "processing", "count": len(products)}

@app.post("/api/products/bulk-check-source")
async def bulk_check_source(background_tasks: BackgroundTasks):
    """Tum urunlerin kaynak canliligini kontrol et"""
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute(
            "SELECT id FROM products WHERE source_url IS NOT NULL LIMIT 50"
        )
        products = await cursor.fetchall()

    for (pid,) in products:
        background_tasks.add_task(check_product_source, pid)

    return {"status": "checking", "count": len(products)}

@app.get("/api/products/delete-non-favorites/preview")
async def preview_delete_non_favorites():
    """
    Silme oncesi on izleme:
    Watchlist'te olan urunler KORUNACAK,
    diger urunler silinecek.
    Hicbir veri degistirmez.
    """
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        # Watchlist'teki product_id'leri al
        cursor = await db.execute("SELECT product_id FROM watchlist")
        watchlist_ids = set(row[0] for row in await cursor.fetchall())

        # Toplam urun sayisi
        cursor = await db.execute("SELECT COUNT(*) FROM products")
        total = (await cursor.fetchone())[0]

        # Korunacak sayisi
        keep_count = len(watchlist_ids)
        # Silinecek sayisi
        delete_count = total - keep_count

    return {
        "total_products": total,
        "will_keep": keep_count,
        "will_delete": delete_count,
        "message": f"{keep_count} urun korunacak (watchlist'te), {delete_count} urun silinecek."
    }

@app.post("/api/products/delete-non-favorites")
async def delete_non_favorites():
    """
    Watchlist tablosunda OLMAYAN tum urunleri sil.
    Korunan = watchlist'e eklenenmis (kalp butonu ile favori yapilan) urunler.
    status='published' veya status='sold' olanlar da daima korunur.
    """
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row

        # Watchlist'teki product_id'leri al
        cursor = await db.execute("SELECT product_id FROM watchlist")
        watchlist_rows = await cursor.fetchall()
        watchlist_ids = [row[0] for row in watchlist_rows]

        # status='published' veya status='sold' olanlari da koru
        cursor = await db.execute(
            "SELECT id FROM products WHERE status IN ('published', 'sold', 'favorite')"
        )
        protected_rows = await cursor.fetchall()
        protected_ids = [row[0] for row in protected_rows]

        # Korunacak tum id'ler (watchlist + published + sold + favorite)
        all_keep_ids = list(set(watchlist_ids + protected_ids))

        # Toplam ve silinecek sayisi
        cursor = await db.execute("SELECT COUNT(*) FROM products")
        total = (await cursor.fetchone())[0]

        if not all_keep_ids:
            # Hicbir favori/watchlist yok - hepsini sil
            cursor = await db.execute("SELECT COUNT(*) FROM products")
            delete_count = (await cursor.fetchone())[0]
        else:
            placeholders = ",".join("?" * len(all_keep_ids))
            cursor = await db.execute(
                f"SELECT COUNT(*) FROM products WHERE id NOT IN ({placeholders})",
                all_keep_ids
            )
            delete_count = (await cursor.fetchone())[0]

        if delete_count == 0:
            return {"status": "ok", "deleted": 0,
                    "message": "Silinecek urun yok. Tum urunler watchlist/favori/yayinda."}

        # Source checks temizle
        try:
            if all_keep_ids:
                placeholders = ",".join("?" * len(all_keep_ids))
                await db.execute(
                    f"DELETE FROM source_checks WHERE product_id NOT IN ({placeholders})",
                    all_keep_ids
                )
            else:
                await db.execute("DELETE FROM source_checks")
        except Exception:
            pass

        # Ana silme: watchlist + published + sold + favorite DISINDAKILER
        db.row_factory = None
        if all_keep_ids:
            placeholders = ",".join("?" * len(all_keep_ids))
            await db.execute(
                f"DELETE FROM products WHERE id NOT IN ({placeholders})",
                all_keep_ids
            )
        else:
            await db.execute("DELETE FROM products")

        await db.commit()

    await log_activity("bulk_delete",
        f"Watchlist/favori disindaki {delete_count} urun silindi. "
        f"{len(all_keep_ids)} urun korundu.")
    return {
        "status": "ok",
        "deleted": delete_count,
        "kept": len(all_keep_ids),
        "message": f"{delete_count} urun silindi. {len(all_keep_ids)} urun korundu (watchlist + favori + yayinda)."
    }

# ============================================
# BULK REANALYZE + CLEAN EMPTY PRODUCTS
# ============================================

@app.post("/api/products/reanalyze-profit")
async def reanalyze_profit_bulk(background_tasks: BackgroundTasks):
    """Tum urunlerin kar/marj hesabini yeni gercekci formul ile yeniden hesapla.
    Eski 'cssberlin' best_sell_platform degerleri de duzeltilir."""

    async def _do_reanalyze():
        async with aiosqlite.connect(DB_FILE) as db:
            cursor = await db.execute(
                "SELECT id, price, source_platform FROM products WHERE price > 0"
            )
            rows = await cursor.fetchall()
            updated = 0
            for (prod_id, price, platform) in rows:
                try:
                    analysis = analyze_profit({"price": price}, platform or "vinted")
                    await db.execute("""
                        UPDATE products SET
                            estimated_sell_price=?, profit_margin=?, profit_euro=?,
                            total_cost=?, recommendation=?, best_sell_platform=?,
                            shipping_cost=?, platform_fee=?, arbitrage_json=?,
                            updated_at=?
                        WHERE id=?
                    """, (
                        analysis.get("sell_price", 0),
                        analysis.get("margin", 0),
                        analysis.get("profit", 0),
                        analysis.get("total_cost", 0),
                        analysis.get("recommendation", "skip"),
                        analysis.get("best_platform", ""),
                        analysis.get("shipping", 0),
                        analysis.get("fee", 0),
                        analysis.get("arbitrage_json", "[]"),
                        datetime.now().isoformat(),
                        prod_id,
                    ))
                    updated += 1
                except Exception as e:
                    print(f"[REANALYZE] {prod_id}: {e}")
            await db.commit()
            await log_activity("reanalyze", f"Yeniden analiz tamamlandi: {updated} urun guncellendi")
            await broadcast_ws("reanalyze_done", {"updated": updated})

    background_tasks.add_task(_do_reanalyze)

    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM products WHERE price > 0")
        total = (await cursor.fetchone())[0]

    return {"status": "started", "total": total, "message": f"{total} urun yeniden hesaplanacak (arka planda)"}


@app.post("/api/products/clean-empty")
async def clean_empty_products():
    """Bos baslik veya fiyat=0 olan islevsiz urunleri sil.
    Bunlar genellikle Willhaben/scraper hatalarindan kaynaklanir."""
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM products WHERE (title IS NULL OR title = '') OR price = 0 OR price IS NULL"
        )
        count = (await cursor.fetchone())[0]

        if count == 0:
            return {"status": "ok", "deleted": 0, "message": "Silinecek bos urun yok"}

        # Watchlist'tekileri koru
        cursor = await db.execute("SELECT product_id FROM watchlist")
        wl_ids = [r[0] for r in await cursor.fetchall()]

        if wl_ids:
            placeholders = ",".join("?" * len(wl_ids))
            await db.execute(
                f"DELETE FROM products WHERE ((title IS NULL OR title = '') OR price = 0 OR price IS NULL) AND id NOT IN ({placeholders})",
                wl_ids
            )
        else:
            await db.execute(
                "DELETE FROM products WHERE (title IS NULL OR title = '') OR price = 0 OR price IS NULL"
            )

        await db.commit()

    await log_activity("clean_empty", f"{count} bos/fiyatsiz urun silindi")
    return {"status": "ok", "deleted": count, "message": f"{count} bos urun temizlendi"}


# ============================================
# MUHASEBE / ACCOUNTING (Kleinunternehmer)
# ============================================
MONTH_NAMES_DE = {
    '01': 'Januar', '02': 'Februar', '03': 'Maerz', '04': 'April',
    '05': 'Mai', '06': 'Juni', '07': 'Juli', '08': 'August',
    '09': 'September', '10': 'Oktober', '11': 'November', '12': 'Dezember'
}

CATEGORY_LABELS = {
    'online_sale': 'Online Satis', 'offline_sale': 'Yuz Yuze Satis',
    'shipping_income': 'Kargo Geliri', 'other_income': 'Diger Gelir',
    'purchase': 'Urun Alimi', 'shipping_expense': 'Kargo Gideri',
    'packaging': 'Paketleme', 'platform_fee': 'Platform Komisyonu',
    'software': 'Yazilim', 'office': 'Buro Malzemesi',
    'communication': 'Iletisim', 'advertising': 'Reklam',
    'bank_fee': 'Banka Masrafi', 'other_expense': 'Diger Gider'
}

@app.get("/accounting", response_class=HTMLResponse)
async def accounting_page(request: Request, type: str = "", month: str = ""):
    current_year = datetime.now().strftime("%Y")
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        # Entries with filters
        query = "SELECT * FROM accounting_entries WHERE strftime('%Y', date) = ?"
        params = [current_year]
        if type:
            query += " AND entry_type = ?"
            params.append(type)
        if month:
            query += " AND strftime('%m', date) = ?"
            params.append(month)
        query += " ORDER BY date DESC"
        cursor = await db.execute(query, params)
        entries = [dict(row) for row in await cursor.fetchall()]

        # Summary
        cursor = await db.execute(
            "SELECT COALESCE(SUM(CASE WHEN entry_type='income' THEN amount ELSE 0 END),0) as total_income, "
            "COALESCE(SUM(CASE WHEN entry_type='expense' THEN amount ELSE 0 END),0) as total_expense "
            "FROM accounting_entries WHERE strftime('%Y', date) = ?", [current_year])
        row = await cursor.fetchone()
        total_income = row[0]
        total_expense = row[1]

        # Sales count
        cursor = await db.execute("SELECT COUNT(*) FROM sales WHERE strftime('%Y', sold_date) = ?", [current_year])
        total_sales = (await cursor.fetchone())[0]
        cursor = await db.execute("SELECT COUNT(*) FROM sales WHERE strftime('%Y-%m', sold_date) = ?",
                                  [datetime.now().strftime("%Y-%m")])
        monthly_sales = (await cursor.fetchone())[0]

        # Sales list
        cursor = await db.execute(
            "SELECT s.*, p.title as product_title FROM sales s LEFT JOIN products p ON s.product_id = p.id "
            "WHERE strftime('%Y', s.sold_date) = ? ORDER BY s.sold_date DESC", [current_year])
        sales = [dict(row) for row in await cursor.fetchall()]

        # EUeR data
        cursor = await db.execute(
            "SELECT category, entry_type, SUM(amount) as total FROM accounting_entries "
            "WHERE strftime('%Y', date) = ? GROUP BY category, entry_type", [current_year])
        cat_rows = await cursor.fetchall()
        income_by_cat = {}
        expense_by_cat = {}
        for r in cat_rows:
            label = CATEGORY_LABELS.get(r[0], r[0])
            if r[1] == 'income':
                income_by_cat[label] = r[2]
            else:
                expense_by_cat[label] = r[2]

        # Monthly breakdown
        monthly_data = []
        cumulative = 0
        for m_num in range(1, 13):
            m_str = f"{m_num:02d}"
            cursor = await db.execute(
                "SELECT COALESCE(SUM(CASE WHEN entry_type='income' THEN amount ELSE 0 END),0), "
                "COALESCE(SUM(CASE WHEN entry_type='expense' THEN amount ELSE 0 END),0) "
                "FROM accounting_entries WHERE strftime('%Y', date) = ? AND strftime('%m', date) = ?",
                [current_year, m_str])
            mr = await cursor.fetchone()
            inc, exp = mr[0], mr[1]
            net = inc - exp
            cumulative += net
            monthly_data.append({
                'month_name': MONTH_NAMES_DE.get(m_str, m_str),
                'income': inc, 'expense': exp, 'net': net, 'cumulative': cumulative
            })

    summary = {
        'total_income': total_income, 'total_expense': total_expense,
        'total_sales': total_sales, 'monthly_sales': monthly_sales
    }
    euer = {
        'total_income': total_income, 'total_expense': total_expense,
        'net_profit': total_income - total_expense,
        'income_by_category': income_by_cat, 'expense_by_category': expense_by_cat,
        'monthly': monthly_data
    }
    return templates.TemplateResponse("accounting.html", {
        "request": request, "entries": entries, "sales": sales,
        "summary": summary, "euer": euer, "current_year": current_year
    })

@app.post("/api/accounting/entry")
async def add_accounting_entry(request: Request):
    data = await request.json()
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "INSERT INTO accounting_entries (entry_type, category, description, amount, date, "
            "invoice_number, counterparty, payment_method, platform, notes) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            [data['entry_type'], data['category'], data['description'],
             float(data['amount']), data['date'],
             data.get('invoice_number', ''), data.get('counterparty', ''),
             data.get('payment_method', 'bank_transfer'), data.get('platform', ''),
             data.get('notes', '')])
        await db.commit()
    await log_activity("accounting", f"Yeni {data['entry_type']}: {data['description']} - {data['amount']} EUR")
    return {"status": "ok"}

@app.delete("/api/accounting/entry/{entry_id}")
async def delete_accounting_entry(entry_id: int):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("DELETE FROM accounting_entries WHERE id = ?", [entry_id])
        await db.commit()
    return {"status": "deleted"}

@app.post("/api/accounting/sale")
async def add_sale(request: Request):
    data = await request.json()
    buy_price = float(data.get('buy_price', 0))
    sold_price = float(data['sold_price'])
    platform_fee = float(data.get('platform_fee', 0))
    shipping_cost = float(data.get('shipping_cost_actual', 0))
    packaging = float(data.get('packaging_cost', 0))
    net_profit = sold_price - buy_price - platform_fee - shipping_cost - packaging

    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "INSERT INTO sales (product_id, sold_platform, sold_price, shipping_income, "
            "platform_fee, shipping_cost_actual, packaging_cost, buy_price, net_profit, "
            "buyer_username, buyer_country, sold_date, tracking_number, notes) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [data.get('product_id'), data['sold_platform'], sold_price,
             float(data.get('shipping_income', 0)), platform_fee, shipping_cost,
             packaging, buy_price, net_profit,
             data.get('buyer_username', ''), data.get('buyer_country', 'DE'),
             data['sold_date'], data.get('tracking_number', ''), data.get('notes', '')])
        # Auto-create income entry
        await db.execute(
            "INSERT INTO accounting_entries (entry_type, category, description, amount, date, platform) "
            "VALUES ('income', 'online_sale', ?, ?, ?, ?)",
            [f"Satis: {data.get('product_id', 'urun')}", sold_price, data['sold_date'], data['sold_platform']])
        await db.commit()
    await log_activity("sale", f"Satis: {sold_price} EUR ({data['sold_platform']})")
    return {"status": "ok", "net_profit": net_profit}

@app.get("/api/accounting/euer-export")
async def euer_export():
    """EUeR CSV export"""
    import csv
    import io
    current_year = datetime.now().strftime("%Y")
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM accounting_entries WHERE strftime('%Y', date) = ? ORDER BY date",
            [current_year])
        rows = [dict(r) for r in await cursor.fetchall()]

    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    writer.writerow(['Datum', 'Typ', 'Kategorie', 'Beschreibung', 'Betrag', 'Plattform', 'Rechnungsnr', 'Zahlungsart'])
    for r in rows:
        writer.writerow([r['date'], 'Einnahme' if r['entry_type'] == 'income' else 'Ausgabe',
                         CATEGORY_LABELS.get(r['category'], r['category']),
                         r['description'], f"{r['amount']:.2f}".replace('.', ','),
                         r.get('platform', ''), r.get('invoice_number', ''),
                         r.get('payment_method', '')])

    from fastapi.responses import StreamingResponse
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=EUeR_{current_year}.csv"})

@app.get("/api/accounting/elster-data")
async def elster_data():
    """ELSTER icin veri hazirlama - Anlage EUeR"""
    current_year = datetime.now().strftime("%Y")
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute(
            "SELECT entry_type, category, SUM(amount) as total FROM accounting_entries "
            "WHERE strftime('%Y', date) = ? GROUP BY entry_type, category", [current_year])
        rows = await cursor.fetchall()

    income_total = sum(r[2] for r in rows if r[0] == 'income')
    expense_total = sum(r[2] for r in rows if r[0] == 'expense')

    return {
        "year": current_year,
        "kleinunternehmer": True,
        "umsatzsteuer_befreit": True,
        "paragraph": "19 UStG",
        "betriebseinnahmen": round(income_total, 2),
        "betriebsausgaben": round(expense_total, 2),
        "gewinn": round(income_total - expense_total, 2),
        "umsatzsteuer": 0,
        "vorsteuer": 0,
        "hinweis": "Kleinunternehmer - keine USt-Pflicht solange Umsatz unter 25.000 EUR/Jahr",
        "details": {cat: round(amt, 2) for _, cat, amt in rows},
        "elster_fields": {
            "Zeile_11": round(income_total, 2),
            "Zeile_22": round(expense_total, 2),
            "Zeile_23": round(income_total - expense_total, 2)
        }
    }

# ============================================
# MAIN
# ============================================
if __name__ == "__main__":
    print("\n  TATANGA T11_HUB - Komuta Merkezi")
    print("  http://localhost:8501")
    print("  Takip Listesi: 10dk otomatik kontrol")
    print("  Cikti: ~/Desktop/CSS_Berlin_Output/\n")
    uvicorn.run(app, host="0.0.0.0", port=8501)
