#!/usr/bin/env python3
"""
TATANGA pazar gozlemcisi — TATANGA'dan BAGIMSIZ calisir, hicbir seye karar vermez.

NE YAPAR: Marka/kategori/ulke hucrelerinde yeni ilanlari tespit eder, sonra her ilanin
satilip satilmadigini belirli araliklarla kontrol eder. Boylece "ne kadar sure sonra,
hangi fiyattan satildi" verisi birikir. Sirkulasyon ve fiyat baremleri bundan cikar.

NE YAPMAZ: Fiyat onermez, urun almaz, yayin yapmaz, gorsel indirmez/saklamaz.
hub.db'ye ve senkron veritabanina erismez. Kendi klasorundeki observe.db disina yazmaz.

VERI: Yalnizca en ust 3 kondisyon (Neu mit Preisschild / Neu ohne Preisschild / Sehr gut).
Kusurlu urunler istatistige girmez. Saticinin kullanici adi saklanmaz; sadece geri
cevrilemez bir ozet (ayni saticinin ilanlarini tek emsal saymak icin) ve ulkesi tutulur.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import sqlite3
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from curl_cffi import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "observe.db")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")

# JSON-LD blogunun yeri sabit degil: bazen ~120 KB'de, bazen sayfanin sonunda.
# Bulununca indirme kesilir; bulunamazsa sayfa sonuna kadar okunur.
ITEM_PAGE_SCAN_LIMIT = 2_400_000
# Durum blogu bu kadar kez ust uste okunamazsa ilan 'bilinmiyor' olur (tahmin yurutulmez)
UNRESOLVED_LIMIT = 6
# Engel (dogrulama) sayfasi: normal sayfalar bundan cok buyuktur
CHALLENGE_MAX_BYTES = 60_000
CHALLENGE_PAUSE_AFTER = 3        # yeni oturuma ragmen ust uste bu kadar engel -> 2 saat dur
SESSION_ROTATE_EVERY = 150       # tek oturum bu kadar istekten sonra yenilenir (403'ler ~2 saatte bir geliyordu)
BLOCK_MID_COUNT = 3              # 30 dk icinde bu kadar 403/429 -> 2 saat dur
BLOCK_LONG_COUNT = 6             # 3 saat icinde bu kadar 403/429 -> 6 saat dur (gercek engel)
CATALOG_MAX_BYTES = 12_000_000
SELLER_SALT = "tatanga-observer-v1"

# Katalog sayfasi 7 MB. Tek buyuk desenle taramak islemciyi saatlerce mesgul ediyordu;
# bunun yerine sayfa ilan bloklarina bolunup her blogun basi kisa desenlerle okunur.
_ITEM_SPLIT = '\\"productItem\\":'
# Bazi ilan bloklari (uzun baslik, coklu gorsel adresi) 4000 karakteri asiyor; o zaman marka/beden/
# kondisyon satiri pencere disinda kaliyor ve ilan sessizce kayboluyordu (2026-10-05: Paul & Shark 96/96).
_ITEM_WINDOW = 20000
_F_ID = re.compile(r'\\"id\\":(\d+)')
_F_URL = re.compile(r'\\"url\\":\\"(/items/[^\\]*)')
# Sayfadaki JSON metninde "&" gibi karakterler \\u0026 kacis dizisiyle yazilir. Eskiden kalip ters
# egik cizgide duruyordu: adinda "&" olan markalarin (Paul & Shark, Dolce & Gabbana) TUM ilanlari
# sessizce kayboluyordu. Kacis dizileri artik metnin parcasi sayilir ve sonra cozulur.
_ESC_STR = r'((?:[^\\]|\\{1,2}u[0-9a-fA-F]{4}){0,200})'
_UNESC_RE = re.compile(r'\\{1,2}u([0-9a-fA-F]{4})')


def _unesc(text: str) -> str:
    return _UNESC_RE.sub(lambda m: chr(int(m.group(1), 16)), text)


_F_TITLE = re.compile(r'\\"title\\":\\"' + _ESC_STR)
_F_FAV = re.compile(r'\\"favouriteCount\\":(\d+)')
_F_PRICE = re.compile(r'\\"price\\":\{\\"amount\\":\\"([\d.]+)')
# Isvec SEK ile fiyatlar: para birimi her ilanla birlikte saklanir, EUR'ya cevrim analizde yapilir
_F_CUR = re.compile(r'\\"price\\":\{\\"amount\\":\\"[\d.]+\\",\\"currencyCode\\":\\"([A-Z]{3})')
_F_TOTAL = re.compile(r'\\"totalItemPrice\\":\{\\"amount\\":\\"([\d.]+)')
_F_THUMB = re.compile(r'\\"thumbnailUrl\\":\\"(https://[^\\]*)')
_F_LINES = re.compile(r'\\"firstLine\\":\\"' + _ESC_STR + r'\\",\\"secondLine\\":\\"' + _ESC_STR)
_OWNER_RE = re.compile(r'\\"ownerId\\":(\d+)')
_TOTAL_RE = re.compile(r'\\"total_entries\\":(\d+)')
_PAGES_RE = re.compile(r'\\"total_pages\\":(\d+)')
# Arayuzdeki sonuc sayisi: "342 Ergebnisse" gercek, "500+ Ergebnisse" ust sinira takilmis
_RESULTS_RE = re.compile(r">(\d+)(\+?)\s*(?:Ergebnis|résultat|result)", re.IGNORECASE)
_AVAIL_RE = re.compile(r'"availability":"([^"]+)"')
# Satilmis ilanin KESIN isareti (2026-10-05, gercek satilmis ilanla dogrulandi):
# sayfa 200 doner, stok blogu YOKTUR, sonda buyer_item_status eklentisi theme=SUCCESS tasir.
# Baslik dile gore degisir (Verkauft/Vendu/Venduto/Verkocht); karar dilden bagimsiz 'theme' ile.
_STATUS_RE = re.compile(
    r'\\"theme\\":\\"(\w+)\\",\\"title\\":\\"([^\\]{0,40})\\"\},\\"exposures\\":\[\],'
    r'\\"name\\":\\"buyer_item_status\\"')
_OFFER_PRICE_RE = re.compile(r'"price":([\d.]+),"availability"')
_LD_NAME_RE = re.compile(r'"@type":"Product","name":"([^"]{0,150})"')
# Aciklama: stil kodu, olcu, kusur bilgisi burada yazilir. Sayfa zaten indirildigi icin bedava.
_LD_DESC_RE = re.compile(r'"@type":"Product","name":"(?:[^"\\]|\\.)*","description":"((?:[^"\\]|\\.){0,1200})')
# Cocuk bedenleri: emsal ve istatistik disinda (farkli pazar, dusuk fiyat)
_CHILD_SIZE_RE = re.compile(r"\b(monate|jahre|mois|ans|kinder)\b|^\d{2,3}\s*(cm)?$", re.IGNORECASE)


def now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def log(msg: str) -> None:
    print(f"{iso(now())} {msg}", flush=True)


def load_config() -> dict:
    with open(CONFIG_FILE, encoding="utf-8") as fh:
        return json.load(fh)


def build_cells(cfg: dict) -> list[dict]:
    """
    Marka x kategori x pazar hucreleri. Markalar config'te kilitli; tier sadece hiz/kotayi belirler.
    brand_categories bir markayi anlamli kategorilerine sinirlar (Birkenstock'ta 'mont' aranmaz).
    """
    cells = []
    all_cats = list(cfg["categories"])
    for tier in cfg["enabled_tiers"]:
        for brand in cfg["brands"][tier]:
            search = cfg.get("brand_search", {}).get(brand, brand)
            for category in cfg.get("brand_categories", {}).get(brand, all_cats):
                keywords = cfg["categories"][category]
                for country in cfg["enabled_markets"]:
                    if country not in keywords:
                        continue
                    cells.append({
                        "id": f"{brand}|{category}|{country}",
                        "brand": brand,
                        "match": [_norm_brand(a) for a in cfg.get("brand_match", {}).get(brand, [brand])],
                        "tier": tier,
                        "category": category,
                        "country": country,
                        "market": cfg["markets"][country],
                        "query": f"{search} {keywords[country]}",
                        "daily_new": cfg["daily_new"][tier],
                        "discovery_hours": cfg["discovery_hours"][tier],
                    })
    # B3: analizin yazdigi dar arama plani (model_cells.json). Analiz -> kazima geri beslemesi.
    plan_path = os.path.join(BASE_DIR, "model_cells.json")
    if os.path.exists(plan_path):
        try:
            plan = json.load(open(plan_path, encoding="utf-8")).get("hucreler", [])
        except (ValueError, OSError):
            plan = []
        for p in plan:
            for country in cfg["enabled_markets"]:
                cells.append({
                    "id": f"{p['brand']}|model:{p['model']}|{country}",
                    "brand": p["brand"],
                    "match": [_norm_brand(a) for a in cfg.get("brand_match", {}).get(p["brand"], [p["brand"]])],
                    "tier": "model",
                    "category": f"model:{p['model']}",
                    "country": country,
                    "market": cfg["markets"][country],
                    "query": p["query"],
                    "daily_new": cfg["daily_new"].get("model", 1),
                    "discovery_hours": cfg["discovery_hours"].get("model", 72),
                })
    # Ayni pazarin hucreleri pes pese: her pazar degisiminde bir oturum istegi gerekiyor
    cells.sort(key=lambda c: (c["market"], c["brand"], c["category"]))
    return cells


def brand_matches(cell: dict, item_brand: str) -> bool:
    """
    Ilanin marka alani bizim markamiz mi? 'adidas Originals' -> adidas (on ek eslesmesi).
    Kisa takma adlar (On) TAM eslesmeli: yoksa 'Onitsuka' da On sayilirdi.
    """
    got = _norm_brand(item_brand or "")
    for alias in cell["match"]:
        if (len(alias) <= 3 and got == alias) or (len(alias) > 3 and got.startswith(alias)):
            return True
    return False


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_FILE, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS listings (
            item_id     INTEGER PRIMARY KEY,
            market      TEXT NOT NULL,      -- vinted.de
            country     TEXT NOT NULL,      -- DE / FR
            cell        TEXT NOT NULL,      -- marka|kategori|ulke
            brand       TEXT,
            title       TEXT,
            size        TEXT,
            condition   TEXT,
            url         TEXT NOT NULL,
            price       REAL,               -- ilan fiyati
            total_price REAL,               -- alicinin odedigi toplam (koruma ucreti dahil)
            currency    TEXT DEFAULT 'EUR',
            favourites  INTEGER DEFAULT 0,
            seller_hash TEXT,
            first_seen  TEXT NOT NULL,
            last_check  TEXT,
            checks      INTEGER DEFAULT 0,
            cohort      TEXT NOT NULL DEFAULT 'fresh',   -- baseline: biz baslamadan once vardi
            photo_sig   TEXT,                            -- gorselin parmak izi (gorsel saklanmaz)
            relist_of   INTEGER,                         -- ayni fotograf: onceki ilanin kimligi
            avail_raw   TEXT,                            -- platformun son bildirdigi ham durum
            state       TEXT NOT NULL DEFAULT 'active',  -- active/sold/gone/relisted/unknown/expired
            final_price REAL,
            closed_at   TEXT,
            days_to_close REAL
        );
        CREATE INDEX IF NOT EXISTS idx_listings_state ON listings(state, last_check);
        CREATE INDEX IF NOT EXISTS idx_listings_cell ON listings(cell, first_seen);

        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL,
            ts TEXT NOT NULL,
            type TEXT NOT NULL,             -- discovered/sold/gone/price_changed/reserved
            price REAL,
            favourites INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_events_item ON events(item_id, ts);

        -- Hucrenin o andaki toplam arzi: ayni filtrede kac ilan var. Sayidaki dusus
        -- talep/sirkulasyon sinyali; tek tek ilan takibinden bagimsiz, bedava gelir.
        CREATE TABLE IF NOT EXISTS cell_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cell TEXT NOT NULL,
            ts TEXT NOT NULL,
            total_entries INTEGER,
            capped INTEGER DEFAULT 0,   -- 1: gercek arz daha buyuk, sayfalama sinirina takildi
            page_items INTEGER,
            median_price REAL
        );
        CREATE INDEX IF NOT EXISTS idx_snap_cell ON cell_snapshots(cell, ts);

        -- Katalog sayfasindan gecen HER ilan (takibe alinmasa bile). Ek istek maliyeti yok:
        -- sayfa zaten indirildi. Model sozlugu ve kondisyon/pazar/beden carpanlari bundan cikar.
        CREATE TABLE IF NOT EXISTS catalog_samples (
            item_id     INTEGER PRIMARY KEY,
            ts          TEXT NOT NULL,
            cell        TEXT NOT NULL,
            country     TEXT NOT NULL,
            brand       TEXT,
            title       TEXT,
            size        TEXT,
            condition   TEXT,
            price       REAL,
            total_price REAL,
            favourites  INTEGER,
            is_child    INTEGER DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_samples_brand ON catalog_samples(brand, condition);

        CREATE TABLE IF NOT EXISTS budget (
            day TEXT PRIMARY KEY,
            requests INTEGER DEFAULT 0,
            errors INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);

        -- Saglik matrisi: gun x pazar x asama x sonuc. HTTP basarisi ile OKUMA basarisi
        -- ayri asamalardir: 10 gunluk sessiz hata, HTTP 'ok' iken okumanin bos donmesiydi.
        CREATE TABLE IF NOT EXISTS health (
            day TEXT NOT NULL, market TEXT NOT NULL, stage TEXT NOT NULL, outcome TEXT NOT NULL,
            n INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (day, market, stage, outcome)
        );
        -- Her duraklama sebebi ve suresiyle: "gunun ne kadari bosta gecti" olculebilsin diye
        CREATE TABLE IF NOT EXISTS pauses (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, minutes INTEGER NOT NULL, reason TEXT
        );
        CREATE TABLE IF NOT EXISTS error_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL, market TEXT, stage TEXT, outcome TEXT, detail TEXT, url TEXT
        );
        """
    )
    have = {r[1] for r in conn.execute("PRAGMA table_info(listings)")}
    for col, decl in (("photo_sig", "TEXT"), ("relist_of", "INTEGER"), ("avail_raw", "TEXT"),
                      ("unresolved", "INTEGER DEFAULT 0"),
                      # Satis ani iki kontrol arasinda bir yerdedir: [son aktif gorulme, satildi gorulme]
                      ("last_active_at", "TEXT"), ("close_window", "REAL"),
                      # 1: kapanis zamani bilinmiyor -> fiyat verisinde kullanilir, HIZ hesabina girmez
                      ("close_uncertain", "INTEGER DEFAULT 0"),
                      # Ilan aciklamasi: stil kodu / olcu / kusur ifadeleri icin (ilk aktif okumada bir kez)
                      ("description", "TEXT")):
        if col not in have:
            conn.execute(f"ALTER TABLE listings ADD COLUMN {col} {decl}")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_listings_sig ON listings(photo_sig)")
    have_s = {r[1] for r in conn.execute("PRAGMA table_info(catalog_samples)")}
    if "currency" not in have_s:
        conn.execute("ALTER TABLE catalog_samples ADD COLUMN currency TEXT DEFAULT 'EUR'")
    conn.commit()


ERROR_LOG_KEEP = 300
_MARKET_RE = re.compile(r"www\.(vinted\.[a-z]+)")


def market_of(url: str) -> str:
    m = _MARKET_RE.search(url or "")
    return m.group(1) if m else "gorsel-cdn"


def note(conn: sqlite3.Connection, market: str, stage: str, outcome: str,
         detail: str = "", url: str = "") -> None:
    """
    Her istegin ve her okumanin sonucunu saglik matrisine yazar.
    Asamalar: oturum, katalog, katalog_okuma, ilan, ilan_okuma, gorsel, gorsel_okuma
    Sonuclar: ok, yok (404), http, ag, bos, okunamadi
    """
    conn.execute(
        "INSERT INTO health (day, market, stage, outcome, n) VALUES (?,?,?,?,1) "
        "ON CONFLICT(day, market, stage, outcome) DO UPDATE SET n=n+1",
        (now().strftime("%Y-%m-%d"), market, stage, outcome),
    )
    if outcome not in ("ok", "yok"):
        conn.execute(
            "INSERT INTO error_log (ts, market, stage, outcome, detail, url) VALUES (?,?,?,?,?,?)",
            (iso(now()), market, stage, outcome, detail[:200], url[:200]),
        )
        conn.execute(
            "DELETE FROM error_log WHERE id <= (SELECT MAX(id) FROM error_log) - ?", (ERROR_LOG_KEEP,)
        )
    conn.commit()


def meta_get(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def meta_set(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, str(value)),
    )
    conn.commit()


class Fetcher:
    """Hiz siniri, gunluk butce ve engel korumasi olan istemci."""

    def __init__(self, conn: sqlite3.Connection, cfg: dict):
        self.conn = conn
        self.cfg = cfg["budget"]
        self.session = requests.Session(impersonate="chrome")
        self.last_request = 0.0
        self.consecutive_errors = 0
        self.warm_market: str | None = None
        self.last_status: int | None = None
        self.consecutive_challenges = 0
        self.session_requests = 0
        self.recent_blocks: list[float] = []

    def new_session(self, reason: str) -> None:
        """
        Yeni oturum. 2026-10-07'de tek oturum gunlerce acik kaldi, bot korumasi onu isaretledi ve
        36 saat boyunca her istege ~20 KB dogrulama sayfasi dondu (IP engelli degildi: yeni oturum
        normal sayfa aliyordu). Artik engel gorulunce ve belirli araliklarla oturum yenilenir.
        """
        self.session = requests.Session(impersonate="chrome")
        self.warm_market = None
        self.session_requests = 0
        log(f"yeni oturum: {reason}")

    def _today(self) -> str:
        return now().strftime("%Y-%m-%d")

    def used_today(self) -> int:
        row = self.conn.execute("SELECT requests FROM budget WHERE day=?", (self._today(),)).fetchone()
        return row["requests"] if row else 0

    def budget_left(self) -> int:
        return max(0, int(self.cfg["max_requests_per_day"]) - self.used_today())

    def _count(self, error: bool = False) -> None:
        self.conn.execute(
            "INSERT INTO budget (day, requests, errors) VALUES (?, 1, ?) "
            "ON CONFLICT(day) DO UPDATE SET requests=requests+1, errors=errors+?",
            (self._today(), 1 if error else 0, 1 if error else 0),
        )
        self.conn.commit()

    def paused_until(self) -> datetime | None:
        raw = meta_get(self.conn, "paused_until")
        if not raw:
            return None
        until = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        return until if until > now() else None

    def _pause(self, minutes: int, reason: str) -> None:
        until = now() + timedelta(minutes=minutes)
        meta_set(self.conn, "paused_until", iso(until))
        self.conn.execute("INSERT INTO pauses (ts, minutes, reason) VALUES (?,?,?)", (iso(now()), minutes, reason))
        self.conn.commit()
        log(f"DURAKLAMA: {minutes} dk ({reason}) -> {iso(until)}")

    def _on_block(self, status: int) -> None:
        """
        Kademeli 403/429 politikasi. Eskiden TEK bir 403 sistemi 6 saat uyutuyordu: gunun ~%75'i
        bosta geciyordu (2026-10-09/10 olcumu). 403 cogunlukla oturumun isaretlenmesidir, IP engeli
        degildir: yeni oturum + kisa bekleme yeter; ancak tekrar ederse uzun durulur.
        """
        cutoff = time.time() - 3 * 3600
        self.recent_blocks = [t for t in self.recent_blocks if t > cutoff] + [time.time()]
        last_30m = sum(1 for t in self.recent_blocks if t > time.time() - 1800)
        self.new_session(f"HTTP {status}")
        if len(self.recent_blocks) >= BLOCK_LONG_COUNT:
            self._pause(360, f"3 saatte {len(self.recent_blocks)} kez HTTP {status}")
            self.recent_blocks = []
        elif last_30m >= BLOCK_MID_COUNT:
            self._pause(120, f"30 dk icinde {last_30m} kez HTTP {status}")
        else:
            self._pause(15, f"tek HTTP {status}, yeni oturum")

    def error_rate(self) -> float:
        row = self.conn.execute("SELECT requests, errors FROM budget WHERE day=?", (self._today(),)).fetchone()
        if not row or row["requests"] < 20:
            return 0.0
        return row["errors"] / row["requests"]

    def _throttle(self) -> None:
        # Kendi kendini ayarlar: hata orani yukseldikce yavaslar (insan mudahalesi gerekmez)
        rate = self.error_rate()
        factor = 4.0 if rate > 0.2 else 2.0 if rate > 0.05 else 1.0
        wait = factor * float(self.cfg["min_interval_seconds"]) + random.uniform(0, float(self.cfg.get("jitter", 3)))
        elapsed = time.time() - self.last_request
        if elapsed < wait:
            time.sleep(wait - elapsed)
        self.last_request = time.time()

    def warm(self, market: str) -> None:
        """Pazar degistiginde bir kez ana sayfa: oturum cerezleri icin."""
        if self.session_requests >= SESSION_ROTATE_EVERY:
            self.new_session(f"{SESSION_ROTATE_EVERY} istek doldu")
        if self.warm_market == market:
            return
        self._throttle()
        try:
            resp = self.session.get(f"https://www.{market}/", timeout=40)
            self._count(error=resp.status_code != 200)
            note(self.conn, market, "oturum", "ok" if resp.status_code == 200 else "http",
                 f"HTTP {resp.status_code}")
        except Exception as exc:
            # Onceden yakalanmiyordu: tek bir ag hatasi butun turu dusurebiliyordu
            self._count(error=True)
            note(self.conn, market, "oturum", "ag", f"{type(exc).__name__}: {str(exc)[:120]}")
            return
        self.warm_market = market

    def get(self, url: str, params: dict | None = None, scan_limit: int | None = None,
            stage: str = "katalog") -> str | None:
        """Sayfayi getirir. scan_limit verilirse JSON-LD bulununca indirme kesilir."""
        if self.budget_left() <= 0:
            raise BudgetExhausted()
        if self.paused_until():
            raise Paused()
        self._throttle()
        self.last_status = None
        market = market_of(url)
        try:
            if scan_limit:
                # Sayfa 2 MB; aradigimiz schema.org blogu ~110 KB'de. Bulunca indirmeyi keseriz.
                buf = bytearray()
                resp = self.session.get(url, params=params, timeout=60, stream=True)
                found_at = None
                try:
                    if resp.status_code != 200:
                        return self._handle_bad(resp.status_code, market, stage, url)
                    for chunk in resp.iter_content():
                        buf.extend(chunk)
                        tail = buf[-len(chunk) - 60:]
                        if found_at is None and (b'"availability"' in tail or b'buyer_item_status' in tail):
                            found_at = len(buf)
                        # isareti gordukten sonra blogun kalanini da al, sonra kes
                        if len(buf) > scan_limit or (found_at and len(buf) - found_at > 4096):
                            break
                finally:
                    resp.close()
                text = buf.decode("utf-8", errors="replace")
            else:
                resp = self.session.get(url, params=params, timeout=90)
                if resp.status_code != 200:
                    return self._handle_bad(resp.status_code, market, stage, url)
                text = resp.text[:CATALOG_MAX_BYTES]
        except (BudgetExhausted, Paused):
            raise
        except Exception as exc:  # aglayla ilgili hata
            self._count(error=True)
            self.consecutive_errors += 1
            detail = f"{type(exc).__name__}: {str(exc)[:120]}"
            log(f"istek hatasi [{market}/{stage}]: {detail}")
            note(self.conn, market, stage, "ag", detail, url)
            if self.consecutive_errors >= 5:
                self.consecutive_errors = 0
                self._pause(30, "ust uste 5 ag hatasi")
            return None
        self.session_requests += 1
        if self._is_challenge(text, stage):
            # HTTP 200 ama icerik dogrulama sayfasi: veri yok, oturum yenilenir, ust uste olursa durulur
            self._count(error=True)
            self.consecutive_challenges += 1
            note(self.conn, market, stage, "engel", f"{len(text)} bayt dogrulama sayfasi", url)
            self.new_session("engel sayfasi")
            if self.consecutive_challenges >= CHALLENGE_PAUSE_AFTER:
                self.consecutive_challenges = 0
                self._pause(120, f"ust uste {CHALLENGE_PAUSE_AFTER} engel sayfasi")
            return None
        self._count()
        self.consecutive_errors = 0
        self.consecutive_challenges = 0
        self.last_status = 200
        note(self.conn, market, stage, "ok")
        return text

    @staticmethod
    def _is_challenge(text: str, stage: str) -> bool:
        """Normal katalog ~2-4 MB, ilan sayfasi >=100 KB. Kucuk VE beklenen blogu olmayan sayfa = engel."""
        if len(text) >= CHALLENGE_MAX_BYTES:
            return False
        if stage == "katalog":
            return _ITEM_SPLIT not in text
        if stage == "ilan":
            return '"availability"' not in text and "buyer_item_status" not in text
        return False

    def get_bytes(self, url: str, max_bytes: int = 120_000) -> bytes | None:
        """Kucuk onizleme gorseli: parmak izi icin indirilir, diske yazilmaz."""
        if self.budget_left() <= 0 or self.paused_until():
            return None
        self._throttle()
        try:
            resp = self.session.get(url, timeout=30)
            self._count(error=resp.status_code != 200)
            note(self.conn, "gorsel-cdn", "gorsel", "ok" if resp.status_code == 200 else "http",
                 f"HTTP {resp.status_code}", url)
            return resp.content[:max_bytes] if resp.status_code == 200 else None
        except Exception as exc:
            self._count(error=True)
            note(self.conn, "gorsel-cdn", "gorsel", "ag", f"{type(exc).__name__}", url)
            return None

    def _handle_bad(self, status: int, market: str = "?", stage: str = "?", url: str = "") -> None:
        self.last_status = status
        if status in (404, 410):
            # Silinmis ilan: normal bir sonuc, hata degil. Engel korumasini tetiklemez.
            self._count()
            self.consecutive_errors = 0
            note(self.conn, market, stage, "yok")
            return None
        self._count(error=True)
        self.consecutive_errors += 1
        note(self.conn, market, stage, "http", f"HTTP {status}", url)
        log(f"HTTP {status} [{market}/{stage}] (ust uste {self.consecutive_errors})")
        if status in (403, 429):
            self._on_block(status)
        elif self.consecutive_errors >= 5:
            self.consecutive_errors = 0
            self._pause(30, f"ust uste 5 HTTP hatasi (son {status})")
        return None


class BudgetExhausted(Exception):
    pass


class Paused(Exception):
    pass


def photo_signature(image_bytes: bytes) -> str | None:
    """
    Gorselin 64 bitlik parmak izi (fark karsilastirmasi). Gorsel SAKLANMAZ, sadece bu iz.
    Ayni fotograf yeni bir ilanda cikarsa, o ilan 'tekrar yayin'dir ve yeni satis sayilmaz.
    """
    try:
        from io import BytesIO

        from PIL import Image

        img = Image.open(BytesIO(image_bytes)).convert("L").resize((9, 8), Image.LANCZOS)
        px = img.tobytes()
        bits = 0
        for row in range(8):
            for col in range(8):
                left, right = px[row * 9 + col], px[row * 9 + col + 1]
                bits = (bits << 1) | (1 if left > right else 0)
        return f"{bits:016x}"
    except Exception:
        return None


def _norm_brand(name: str) -> str:
    """Levi's / Levis / LEVI`S ayni markadir: karsilastirma icin sadelestirir."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def seller_hash(owner_id: str) -> str:
    return hashlib.sha256((SELLER_SALT + str(owner_id)).encode()).hexdigest()[:16]


def parse_catalog(html: str) -> list[dict]:
    """Katalog sayfasindaki RSC blogundan ilanlari cikarir."""
    out: list[dict] = []
    for block in html.split(_ITEM_SPLIT)[1:]:
        seg = block[:_ITEM_WINDOW]
        fields = [r.search(seg) for r in (_F_ID, _F_URL, _F_FAV, _F_PRICE, _F_TOTAL, _F_LINES)]
        if not all(fields):
            continue
        ident, url, fav, price, total, lines = fields
        thumb = _F_THUMB.search(seg)
        owner = _OWNER_RE.search(seg)
        title = _F_TITLE.search(seg)
        cur = _F_CUR.search(seg)
        second = _unesc(lines.group(2))
        size, _, condition = second.partition(" · ")
        out.append({
            "item_id": int(ident.group(1)),
            "url": url.group(1),
            "favourites": int(fav.group(1)),
            "price": float(price.group(1)),
            "total_price": float(total.group(1)),
            "brand": _unesc(lines.group(1)),
            "size": size.strip(),
            "condition": condition.strip() or second.strip(),
            "seller_hash": seller_hash(owner.group(1)) if owner else None,
            "thumb": thumb.group(1) if thumb else None,
            "title": _unesc(title.group(1)) if title else None,   # model cikarimi bunun uzerinden yapilacak
            "currency": cur.group(1) if cur else "EUR",
        })
    return out


def parse_item_state(html: str) -> dict | None:
    """
    Durum once buyer_item_status eklentisinden (satildi/rezerve), yoksa stok blogundan okunur.
    Ikisi de yoksa None: tahmin yurutulmez, kontrol tekrarlanir.
    """
    status = _STATUS_RE.search(html)
    if status:
        theme, title = status.group(1), status.group(2)
        return {
            "state": "sold" if theme == "SUCCESS" else "unknown",
            "availability": f"{theme}:{title}",
            "price": None,      # satilmis sayfada teklif blogu yok: son bilinen ilan fiyati kullanilir
            "title": None,
        }
    avail = _AVAIL_RE.search(html)
    if not avail:
        return None
    price = _OFFER_PRICE_RE.search(html)
    name = _LD_NAME_RE.search(html)
    desc = _LD_DESC_RE.search(html)
    description = None
    if desc:
        try:
            description = json.loads(f'"{desc.group(1)}"')
        except ValueError:
            description = desc.group(1)
    value = avail.group(1).rsplit("/", 1)[-1]
    state = {"InStock": "active"}.get(value, "sold" if "Sold" in value or "OutOfStock" in value else "unknown")
    return {
        "state": state,
        "availability": value,
        "price": float(price.group(1)) if price else None,
        "title": name.group(1) if name else None,
        "description": description,
    }


def add_event(conn, item_id: int, etype: str, price=None, favourites=None) -> None:
    conn.execute(
        "INSERT INTO events (item_id, ts, type, price, favourites) VALUES (?,?,?,?,?)",
        (item_id, iso(now()), etype, price, favourites),
    )


def discover(conn: sqlite3.Connection, fetcher: Fetcher, cfg: dict, cell: dict,
             enroll: bool = True) -> dict:
    """
    Katalog sayfasini okur. Sayfadaki her ilan ornek havuzuna girer (fiyat iskeleti icin);
    enroll=True ise kota kadari ayrica satis takibine alinir. Takip kapasitesi doluyken
    enroll=False: ornek toplama DURMAZ, sadece yeni takip baslamaz.
    """
    market = cell["market"]
    fetcher.warm(market)
    params = {
        "search_text": cell["query"],
        "order": "newest_first",
        "status_ids[]": cfg["conditions"],
    }
    html = fetcher.get(f"https://www.{market}/catalog", params=params, stage="katalog")
    if not html:
        return {"found": 0, "new": 0, "read": False}
    items = parse_catalog(html)
    total, pages = _TOTAL_RE.search(html), _PAGES_RE.search(html)
    results = _RESULTS_RE.search(html)
    # HTTP basarili ama sayfadan ilan cikmiyorsa: site yapisi degismis olabilir.
    # Platformun kendisi "0 sonuc" diyorsa bu hata degil, gercek bos aramadir.
    genuinely_empty = bool((results and results.group(1) == "0") or (total and total.group(1) == "0"))
    blocks = html.count(_ITEM_SPLIT)
    if not items and not genuinely_empty:
        note(conn, market, "katalog_okuma", "bos", f"{len(html)} bayt, {blocks} blok, 0 okundu",
             f"{market}:{cell['query']}")
        return {"found": 0, "new": 0, "read": False}   # bos sayfa: anlik goruntu ve tarama zamani yazilmaz
    elif blocks and len(items) < 0.9 * blocks:
        # Kismi kayip: sayfada blok var ama bir kismi okunamadi. Eskiden hicbir test bunu gormuyordu.
        note(conn, market, "katalog_okuma", "eksik", f"{len(items)}/{blocks} blok okundu",
             f"{market}:{cell['query']}")
    else:
        note(conn, market, "katalog_okuma", "ok")
    count = int(results.group(1)) if results else (int(total.group(1)) if total else None)
    # Vinted genis aramalarda gercek sayiyi vermiyor: 96 x 10 sayfa = 960, arayuzde "500+"
    capped = bool((results and results.group(2) == "+")
                  or (total and pages and int(total.group(1)) == 96 * int(pages.group(1))))
    prices = sorted(i["price"] for i in items)
    conn.execute(
        "INSERT INTO cell_snapshots (cell, ts, total_entries, capped, page_items, median_price) "
        "VALUES (?,?,?,?,?,?)",
        (cell["id"], iso(now()), count, int(capped), len(items),
         prices[len(prices) // 2] if prices else None),
    )
    # Ilk turda bulunanlarin yasi bilinmiyor (bizden once yayindaydilar) -> 'baseline'.
    # Satis hizi istatistikleri yalnizca 'fresh' kohorttan hesaplanir.
    cohort = "baseline" if not meta_get(conn, f"disc:{cell['id']}") else "fresh"

    # Sayfadaki butun ilanlar ornek havuzuna girer (takip kotasindan bagimsiz, bedava veri)
    conn.executemany(
        "INSERT OR IGNORE INTO catalog_samples (item_id, ts, cell, country, brand, title, size, "
        "condition, price, total_price, favourites, is_child, currency) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [(i["item_id"], iso(now()), cell["id"], cell["country"], i["brand"], i.get("title"),
          i["size"], i["condition"], i["price"], i["total_price"], i["favourites"],
          1 if _CHILD_SIZE_RE.search(i["size"] or "") else 0, i.get("currency", "EUR"))
         for i in items if brand_matches(cell, i["brand"])],
    )
    conn.commit()
    if not enroll:
        return {"found": len(items), "new": 0, "read": True}
    quota = int(cell.get("daily_new", 40))
    today = now().strftime("%Y-%m-%d")
    added_today = conn.execute(
        "SELECT COUNT(*) c FROM listings WHERE cell=? AND substr(first_seen,1,10)=?",
        (cell["id"], today),
    ).fetchone()["c"]
    room = max(0, quota - added_today)
    new = 0
    for item in items:
        if room <= 0:
            break
        if not brand_matches(cell, item["brand"]):
            continue  # arama gurultusu: baska markanin ilani
        if _CHILD_SIZE_RE.search(item["size"] or ""):
            continue  # cocuk bedeni: ayri pazar, fiyat bandi bizim disimizda
        exists = conn.execute("SELECT 1 FROM listings WHERE item_id=?", (item["item_id"],)).fetchone()
        if exists:
            continue
        sig = relist_of = None
        if item.get("thumb"):
            blob = fetcher.get_bytes(item["thumb"])
            sig = photo_signature(blob) if blob else None
            if blob and not sig:
                note(conn, "gorsel-cdn", "gorsel_okuma", "okunamadi", f"{len(blob)} bayt", item["thumb"])
            elif sig:
                note(conn, "gorsel-cdn", "gorsel_okuma", "ok")
        if sig:
            prev = conn.execute(
                "SELECT item_id, state FROM listings WHERE photo_sig=? AND seller_hash IS ? "
                "ORDER BY first_seen DESC LIMIT 1",
                (sig, item["seller_hash"]),
            ).fetchone()
            if prev:
                # Ayni satici, ayni fotograf: onceki ilan satilmadi, yeniden yayinlandi
                relist_of = prev["item_id"]
                conn.execute(
                    "UPDATE listings SET state='relisted' WHERE item_id=? AND state IN ('gone','sold','active')",
                    (prev["item_id"],),
                )
                add_event(conn, prev["item_id"], "relisted")
        conn.execute(
            """INSERT INTO listings (item_id, market, country, cell, brand, title, size, condition,
                   url, price, total_price, favourites, seller_hash, first_seen, cohort,
                   photo_sig, relist_of, currency, state)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'active')""",
            (item["item_id"], market, cell["country"], cell["id"], item["brand"], item.get("title"),
             item["size"], item["condition"], f"https://www.{market}{item['url']}",
             item["price"], item["total_price"], item["favourites"], item["seller_hash"],
             iso(now()), cohort, sig, relist_of, item.get("currency", "EUR")),
        )
        add_event(conn, item["item_id"], "discovered", item["price"], item["favourites"])
        new += 1
        room -= 1
    conn.commit()
    return {"found": len(items), "new": new, "read": True}


def check_interval_days(age_days: float, tr: dict) -> float:
    if age_days <= 7:
        return float(tr["day1_7"])
    if age_days <= 30:
        return float(tr["day8_30"])
    return float(tr["day31_90"])


def _category_of(cell: str) -> str:
    part = (cell.split("|") + ["", ""])[1]
    return "model" if part.startswith("model:") else part


def due_queue(conn: sqlite3.Connection, cfg: dict) -> list[tuple[int, str, int]]:
    """
    Vadesi gelmis tum aktif ilanlar: (oncelik, kategori, item_id).
    Oncelik 0 = hic kontrol edilmemis, 1 = ilk haftadaki genc ilan, 2 = digerleri.
    """
    tr = cfg["tracking"]
    out, expired = [], []
    for item_id, cell, first_seen, last_check in conn.execute(
            "SELECT item_id, cell, first_seen, last_check FROM listings WHERE state='active'"):
        first = datetime.strptime(first_seen, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        age = (now() - first).total_seconds() / 86400
        if age > float(tr["max_days"]):
            expired.append(item_id)
            continue
        last = datetime.strptime(last_check or first_seen, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        waited = (now() - last).total_seconds() / 86400
        if waited >= check_interval_days(age, tr):
            prio = 0 if last_check is None else 1 if age <= 7 else 2
            out.append((prio, _category_of(cell), item_id, waited))
    if expired:
        conn.executemany("UPDATE listings SET state='expired' WHERE item_id=?", [(i,) for i in expired])
        conn.commit()
    return out


def due_listings(conn: sqlite3.Connection, cfg: dict, limit: int) -> list[sqlite3.Row]:
    """
    Adil kontrol kuyrugu. Eskiden 'en eski kontrol once' calisiyordu: gecikmis eski mont ilanlari
    kuyrugu tikiyor, yeni ayakkabi/giyim ilanlari hic sira bulamiyordu (2026-10-10: IT/NL/SE
    ayakkabilarinin %100'u hic kontrol edilmemisti). Simdi: oncelik sirasina gore, her oncelik
    icinde kategoriler donusumlu; ayni kategoride en uzun bekleyen once.
    """
    queue = due_queue(conn, cfg)
    chosen: list[int] = []
    for prio in (0, 1, 2):
        buckets: dict[str, list[tuple]] = defaultdict(list)
        for p, cat, item_id, waited in queue:
            if p == prio:
                buckets[cat].append((waited, item_id))
        for cat in buckets:
            buckets[cat].sort(reverse=True)
        while buckets and len(chosen) < limit:
            for cat in list(buckets):
                if not buckets[cat]:
                    del buckets[cat]
                    continue
                chosen.append(buckets[cat].pop(0)[1])
                if len(chosen) >= limit:
                    break
        if len(chosen) >= limit:
            break
    if not chosen:
        return []
    marks = ",".join("?" * len(chosen))
    rows = {r["item_id"]: r for r in conn.execute(f"SELECT * FROM listings WHERE item_id IN ({marks})", chosen)}
    return [rows[i] for i in chosen if i in rows]


def check_listing(conn: sqlite3.Connection, fetcher: Fetcher, row: sqlite3.Row) -> str:
    fetcher.warm(row["market"])
    html = fetcher.get(row["url"], scan_limit=ITEM_PAGE_SCAN_LIMIT, stage="ilan")
    ts = iso(now())

    # SADECE 404/410 "kalkti" demektir. Sayfanin yuklenmemesi ya da durum blogunun
    # o gelisde bulunmamasi ilanin kalktigini GOSTERMEZ (bu varsayim 1397 yanlis kayda
    # yol acmisti). Cozulemeyen kontrol durumu degistirmez, sadece yeniden denenir.
    if html is None:
        if fetcher.last_status in (404, 410):
            first = datetime.strptime(row["first_seen"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            lower = datetime.strptime(row["last_active_at"] or row["first_seen"],
                                      "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            days = round(((lower + (now() - lower) / 2) - first).total_seconds() / 86400, 2)
            window = round((now() - lower).total_seconds() / 86400, 2)
            conn.execute(
                "UPDATE listings SET state='gone', closed_at=?, days_to_close=?, close_window=?, "
                "last_check=?, checks=checks+1 WHERE item_id=?", (ts, days, window, ts, row["item_id"]),
            )
            add_event(conn, row["item_id"], "gone")
            conn.commit()
            return "gone"
        conn.execute("UPDATE listings SET last_check=?, checks=checks+1 WHERE item_id=?", (ts, row["item_id"]))
        conn.commit()
        return "error"

    info = parse_item_state(html)
    note(conn, row["market"], "ilan_okuma", "ok" if info else "okunamadi",
         "" if info else f"{len(html)} bayt, durum blogu yok", row["url"])
    if info is None:
        unresolved = (row["unresolved"] or 0) + 1
        state = "unknown" if unresolved >= UNRESOLVED_LIMIT else row["state"]
        conn.execute(
            "UPDATE listings SET unresolved=?, state=?, last_check=?, checks=checks+1 WHERE item_id=?",
            (unresolved, state, ts, row["item_id"]),
        )
        if state == "unknown":
            add_event(conn, row["item_id"], "unresolved")
        conn.commit()
        return "unresolved"

    new_state = info["state"]
    price = info["price"]
    if price is not None and row["price"] is not None and abs(price - row["price"]) >= 0.01:
        add_event(conn, row["item_id"], "price_changed", price)
        conn.execute("UPDATE listings SET price=? WHERE item_id=?", (price, row["item_id"]))

    if new_state == "sold":
        # Satis ani [son aktif gorulme, simdi] araligindadir; gun = aralik ortasi, genislik ayrica saklanir
        first = datetime.strptime(row["first_seen"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        lower_raw = row["last_active_at"] or row["first_seen"]
        lower = datetime.strptime(lower_raw, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        mid = lower + (now() - lower) / 2
        days = round((mid - first).total_seconds() / 86400, 2)
        window = round((now() - lower).total_seconds() / 86400, 2)
        conn.execute(
            "UPDATE listings SET state='sold', final_price=?, closed_at=?, days_to_close=?, "
            "close_window=?, last_check=?, checks=checks+1, avail_raw=?, unresolved=0 WHERE item_id=?",
            (price if price is not None else row["price"], ts, days, window, ts,
             info["availability"], row["item_id"]),
        )
        add_event(conn, row["item_id"], "sold", price)
    else:
        if new_state == "unknown":
            # Tanimadigimiz durum degeri: tahmin yurutmuyoruz, ham degeri kaydedip isaretliyoruz
            add_event(conn, row["item_id"], f"unknown:{info['availability'][:40]}")
        conn.execute(
            "UPDATE listings SET last_check=?, checks=checks+1, state=?, avail_raw=?, unresolved=0, "
            "last_active_at=CASE WHEN ?='active' THEN ? ELSE last_active_at END, "
            "description=COALESCE(description, ?), title=COALESCE(title, ?) WHERE item_id=?",
            (ts, "active" if new_state == "active" else row["state"], info["availability"],
             new_state, ts, (info.get("description") or "")[:1200] or None, info.get("title"), row["item_id"]),
        )
    conn.commit()
    return new_state


def run_cycle(conn: sqlite3.Connection, cfg: dict, fetcher: Fetcher) -> dict:
    stats = {"discovered": 0, "found": 0, "checked": 0, "sold": 0, "gone": 0, "cells": 0, "takipte": 0}
    reserve = int(cfg["budget"].get("reserve_for_checks", 0.7) * cfg["budget"]["max_requests_per_day"])
    # Takip yuku kapasiteyi asarsa yeni ilan almayi kendiliginden durdurur:
    # yarim takip edilen cok ilan yerine, tam takip edilen daha az ilan.
    tracked = conn.execute("SELECT COUNT(*) c FROM listings WHERE state='active'").fetchone()["c"]
    # Yeni ilan takibe ancak kontrol kuyrugu yetisebiliyorsa alinir: birikmis is buyukse once onu erit.
    backlog = len(due_queue(conn, cfg))
    backlog_limit = max(200, int(0.1 * tracked))
    discovery_open = tracked < int(cfg["budget"].get("max_tracked", 2500)) and backlog < backlog_limit
    stats["takipte"] = tracked
    stats["birikmis"] = backlog
    try:
        # Once takip (kural 29): vadesi gelen kontroller ertelenirse satis anini kaciririz.
        limit = min(fetcher.budget_left(), int(cfg["budget"].get("checks_per_cycle", 200)))
        for row in due_listings(conn, cfg, limit):
            state = check_listing(conn, fetcher, row)
            stats["checked"] += 1
            if state == "sold":
                stats["sold"] += 1
            elif state == "gone":
                stats["gone"] += 1

        # Sonra kesif, yalnizca kontrol payi korunuyorsa. Takip kapasitesi doluysa da kesif
        # SURER: ornek havuzu (fiyat iskeleti) beslenir, sadece yeni ilan takibe alinmaz.
        for cell in build_cells(cfg):
            if fetcher.budget_left() <= reserve:
                break
            last = meta_get(conn, f"disc:{cell['id']}")
            if last:
                last_dt = datetime.strptime(last, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                if (now() - last_dt).total_seconds() < cell["discovery_hours"] * 3600:
                    continue
            res = discover(conn, fetcher, cfg, cell, enroll=discovery_open)
            # Tarama zamani YALNIZCA sayfa okunduysa yazilir: engel/hata gunlerinde yazilirsa
            # hucre "tarandi" sanilip 24-72 saat atlaniyordu (2026-10-07 boslugu).
            if res.get("read"):
                meta_set(conn, f"disc:{cell['id']}", iso(now()))
            stats["found"] += res["found"]
            stats["discovered"] += res["new"]
            stats["cells"] += 1
    except BudgetExhausted:
        log("gunluk istek butcesi doldu")
    except Paused:
        log("engel korumasi aktif, bu tur atlandi")
    return stats


SOLD_VERIFY_THRESHOLD = 20


def print_stats(conn: sqlite3.Connection) -> None:
    avail = conn.execute(
        "SELECT avail_raw, COUNT(*) c FROM listings WHERE avail_raw IS NOT NULL GROUP BY 1 ORDER BY c DESC"
    ).fetchall()
    sold = conn.execute("SELECT COUNT(*) c FROM listings WHERE state='sold'").fetchone()["c"]
    relisted = conn.execute("SELECT COUNT(*) c FROM listings WHERE state='relisted'").fetchone()["c"]
    print("platformun bildirdigi durumlar:", ", ".join(f"{r['avail_raw']}={r['c']}" for r in avail) or "-")
    print(f"dogrulanmis satis: {sold} | tekrar yayin (satis sayilmadi): {relisted}")
    if sold < SOLD_VERIFY_THRESHOLD:
        print(f"UYARI: satis hizi rakamlari {SOLD_VERIFY_THRESHOLD} dogrulanmis satistan once "
              f"kullanilmaz (kural 33).")
    print()
    rows = conn.execute(
        """SELECT cell,
                  COUNT(*) total,
                  SUM(state='active') aktif,
                  SUM(state='sold') satildi,
                  SUM(state='gone') kalkti,
                  SUM(state='relisted') tekrar,
                  -- hiz yalnizca kapanis ani bilinen ve araligi 7 gunden dar satislardan
                  ROUND(AVG(CASE WHEN state='sold' AND COALESCE(close_uncertain,0)=0
                                  AND COALESCE(close_window,99) <= 7 THEN days_to_close END), 1) ort_gun,
                  ROUND(AVG(CASE WHEN state='sold' THEN final_price END), 2) ort_fiyat
             FROM listings WHERE cohort='fresh' GROUP BY cell ORDER BY total DESC"""
    ).fetchall()
    print(f"{'hucre':34} {'toplam':>7} {'aktif':>6} {'satildi':>8} {'kalkti':>7} {'tekrar':>7} "
          f"{'ort.gun':>8} {'ort.fiyat':>10}")
    for r in rows:
        print(f"{r['cell']:34} {r['total']:7} {r['aktif']:6} {r['satildi']:8} {r['kalkti']:7} {r['tekrar']:7} "
              f"{r['ort_gun'] if r['ort_gun'] is not None else '-':>8} "
              f"{r['ort_fiyat'] if r['ort_fiyat'] is not None else '-':>10}")
    b = conn.execute("SELECT * FROM budget ORDER BY day DESC LIMIT 3").fetchall()
    print("\nistek:", ", ".join(f"{r['day']}: {r['requests']} ({r['errors']} hata)" for r in b))


def main() -> None:
    ap = argparse.ArgumentParser(description="TATANGA pazar gozlemcisi")
    ap.add_argument("--once", action="store_true", help="tek tur calis ve cik")
    ap.add_argument("--stats", action="store_true", help="istatistikleri yazdir ve cik")
    ap.add_argument("--probe", action="store_true", help="tek hucrede kazima testi, veri yazmaz")
    ap.add_argument("--harvest", action="store_true",
                    help="tum hucreleri bir kez gez: ornek havuzunu doldurur (carpan olcumu icin)")
    args = ap.parse_args()

    cfg = load_config()
    conn = connect()
    init_db(conn)

    if args.stats:
        print_stats(conn)
        return

    fetcher = Fetcher(conn, cfg)

    if args.probe:
        cell = build_cells(cfg)[0]
        fetcher.warm(cell["market"])
        html = fetcher.get(f"https://www.{cell['market']}/catalog", params={
            "search_text": cell["query"], "order": "newest_first", "status_ids[]": cfg["conditions"]})
        items = parse_catalog(html or "")
        print(f"hucre {cell['id']}: {len(items)} ilan")
        from collections import Counter
        print("kondisyonlar:", Counter(i["condition"] for i in items).most_common())
        print("markalar:", Counter(i["brand"] for i in items).most_common(5))
        for i in items[:3]:
            print("  ", i["item_id"], i["price"], i["total_price"], i["size"], "|", i["condition"], "|", i["brand"])
        if items:
            fetcher.warm(cell["market"])
            page = fetcher.get(f"https://www.{cell['market']}{items[0]['url']}", scan_limit=ITEM_PAGE_SCAN_LIMIT)
            print("ilan sayfasi:", round(len(page or "") / 1024), "KB ->", parse_item_state(page or ""))
        return

    if args.harvest:
        # Her hucre bir kez taranir; sayfadaki 95 ilanin hepsi ornek havuzuna girer.
        # Servis durdurulmus olmali, yoksa iki surec ayni anda istek atar.
        cells = build_cells(cfg)
        log(f"ornek toplama: {len(cells)} hucre")
        for i, cell in enumerate(cells, 1):
            try:
                res = discover(conn, fetcher, cfg, cell)
                if res.get("read"):
                    meta_set(conn, f"disc:{cell['id']}", iso(now()))
            except (BudgetExhausted, Paused) as exc:
                log(f"durdu: {type(exc).__name__}")
                break
            if i % 20 == 0:
                total = conn.execute("SELECT COUNT(*) c FROM catalog_samples").fetchone()["c"]
                log(f"  {i}/{len(cells)} hucre | havuz: {total} ornek")
        total = conn.execute("SELECT COUNT(*) c FROM catalog_samples").fetchone()["c"]
        log(f"bitti: {total} ornek")
        return

    if args.once:
        log(f"tur basliyor (butce kalan: {fetcher.budget_left()})")
        log(f"tur bitti: {run_cycle(conn, cfg, fetcher)}")
        return

    interval = int(cfg["budget"].get("cycle_minutes", 30)) * 60
    log(f"gozlemci basladi: {len(build_cells(cfg))} hucre, gunluk butce {cfg['budget']['max_requests_per_day']}")
    while True:
        stats = run_cycle(conn, cfg, fetcher)
        log(f"tur: {stats} | butce kalan: {fetcher.budget_left()}")
        # Is varsa (kontrol kotasi doldu ya da kesif yapildi) hemen devam; yoksa uzun bekle.
        # Eskiden her turdan sonra 30 dk bekleniyordu: kuyruk doluyken bile gunun yarisi bosta gecti.
        busy = stats["checked"] >= int(cfg["budget"].get("checks_per_cycle", 150)) or stats["cells"] > 0
        if fetcher.paused_until():
            wait = max(60, (fetcher.paused_until() - now()).total_seconds())
        elif busy and fetcher.budget_left() > 0:
            wait = 60
        else:
            wait = interval
        time.sleep(wait)


if __name__ == "__main__":
    sys.exit(main())
