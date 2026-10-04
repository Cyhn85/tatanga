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
CATALOG_MAX_BYTES = 12_000_000
SELLER_SALT = "tatanga-observer-v1"

# Katalog sayfasi 7 MB. Tek buyuk desenle taramak islemciyi saatlerce mesgul ediyordu;
# bunun yerine sayfa ilan bloklarina bolunup her blogun basi kisa desenlerle okunur.
_ITEM_SPLIT = '\\"productItem\\":'
_ITEM_WINDOW = 4000
_F_ID = re.compile(r'\\"id\\":(\d+)')
_F_URL = re.compile(r'\\"url\\":\\"(/items/[^\\]*)')
_F_TITLE = re.compile(r'\\"title\\":\\"([^\\]{0,160})')
_F_FAV = re.compile(r'\\"favouriteCount\\":(\d+)')
_F_PRICE = re.compile(r'\\"price\\":\{\\"amount\\":\\"([\d.]+)')
_F_TOTAL = re.compile(r'\\"totalItemPrice\\":\{\\"amount\\":\\"([\d.]+)')
_F_THUMB = re.compile(r'\\"thumbnailUrl\\":\\"(https://[^\\]*)')
_F_LINES = re.compile(r'\\"firstLine\\":\\"([^\\]*)\\",\\"secondLine\\":\\"([^\\]*)')
_OWNER_RE = re.compile(r'\\"ownerId\\":(\d+)')
_TOTAL_RE = re.compile(r'\\"total_entries\\":(\d+)')
_PAGES_RE = re.compile(r'\\"total_pages\\":(\d+)')
# Arayuzdeki sonuc sayisi: "342 Ergebnisse" gercek, "500+ Ergebnisse" ust sinira takilmis
_RESULTS_RE = re.compile(r">(\d+)(\+?)\s*(?:Ergebnis|résultat|result)", re.IGNORECASE)
_AVAIL_RE = re.compile(r'"availability":"([^"]+)"')
_OFFER_PRICE_RE = re.compile(r'"price":([\d.]+),"availability"')
_LD_NAME_RE = re.compile(r'"@type":"Product","name":"([^"]{0,150})"')
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
    """Marka x pazar hucreleri. Markalar config'te kilitli; tier sadece hiz/kotayi belirler."""
    cells = []
    for tier in cfg["enabled_tiers"]:
        for brand in cfg["brands"][tier]:
            for country in cfg["enabled_markets"]:
                market = cfg["markets"][country]
                cells.append({
                    "id": f"{brand}|{cfg['category']}|{country}",
                    "brand": brand,
                    "tier": tier,
                    "country": country,
                    "market": market["domain"],
                    "query": f"{brand} {market['keyword']}",
                    "daily_new": cfg["daily_new"][tier],
                    "discovery_hours": cfg["discovery_hours"][tier],
                })
    # Ayni pazarin hucreleri pes pese: her pazar degisiminde bir oturum istegi gerekiyor
    cells.sort(key=lambda c: (c["market"], c["brand"]))
    return cells


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
        """
    )
    have = {r[1] for r in conn.execute("PRAGMA table_info(listings)")}
    for col, decl in (("photo_sig", "TEXT"), ("relist_of", "INTEGER"), ("avail_raw", "TEXT"),
                      ("unresolved", "INTEGER DEFAULT 0")):
        if col not in have:
            conn.execute(f"ALTER TABLE listings ADD COLUMN {col} {decl}")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_listings_sig ON listings(photo_sig)")
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

    def _pause(self, hours: int) -> None:
        until = now() + timedelta(hours=hours)
        meta_set(self.conn, "paused_until", iso(until))
        log(f"ENGEL KORUMASI: {hours} saat duraklatildi ({iso(until)})")

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
        if self.warm_market == market:
            return
        self._throttle()
        self.session.get(f"https://www.{market}/", timeout=40)
        self._count()
        self.warm_market = market

    def get(self, url: str, params: dict | None = None, scan_limit: int | None = None) -> str | None:
        """Sayfayi getirir. scan_limit verilirse JSON-LD bulununca indirme kesilir."""
        if self.budget_left() <= 0:
            raise BudgetExhausted()
        if self.paused_until():
            raise Paused()
        self._throttle()
        self.last_status = None
        try:
            if scan_limit:
                # Sayfa 2 MB; aradigimiz schema.org blogu ~110 KB'de. Bulunca indirmeyi keseriz.
                buf = bytearray()
                resp = self.session.get(url, params=params, timeout=60, stream=True)
                found_at = None
                try:
                    if resp.status_code != 200:
                        return self._handle_bad(resp.status_code)
                    for chunk in resp.iter_content():
                        buf.extend(chunk)
                        if found_at is None and b'"availability"' in buf[-len(chunk) - 40:]:
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
                    return self._handle_bad(resp.status_code)
                text = resp.text[:CATALOG_MAX_BYTES]
        except (BudgetExhausted, Paused):
            raise
        except Exception as exc:  # aglayla ilgili hata
            self._count(error=True)
            self.consecutive_errors += 1
            log(f"istek hatasi: {type(exc).__name__}: {str(exc)[:120]}")
            if self.consecutive_errors >= 5:
                self._pause(6)
            return None
        self._count()
        self.consecutive_errors = 0
        self.last_status = 200
        return text

    def get_bytes(self, url: str, max_bytes: int = 120_000) -> bytes | None:
        """Kucuk onizleme gorseli: parmak izi icin indirilir, diske yazilmaz."""
        if self.budget_left() <= 0 or self.paused_until():
            return None
        self._throttle()
        try:
            resp = self.session.get(url, timeout=30)
            self._count()
            return resp.content[:max_bytes] if resp.status_code == 200 else None
        except Exception:
            self._count(error=True)
            return None

    def _handle_bad(self, status: int) -> None:
        self.last_status = status
        if status in (404, 410):
            # Silinmis ilan: normal bir sonuc, hata degil. Engel korumasini tetiklemez.
            self._count()
            self.consecutive_errors = 0
            return None
        self._count(error=True)
        self.consecutive_errors += 1
        log(f"HTTP {status} (ust uste {self.consecutive_errors})")
        if status in (403, 429) or self.consecutive_errors >= 5:
            self._pause(6 if status in (403, 429) else 3)
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
        second = lines.group(2)
        size, _, condition = second.partition(" · ")
        out.append({
            "item_id": int(ident.group(1)),
            "url": url.group(1),
            "favourites": int(fav.group(1)),
            "price": float(price.group(1)),
            "total_price": float(total.group(1)),
            "brand": lines.group(1),
            "size": size.strip(),
            "condition": condition.strip() or second.strip(),
            "seller_hash": seller_hash(owner.group(1)) if owner else None,
            "thumb": thumb.group(1) if thumb else None,
            "title": title.group(1) if title else None,   # model cikarimi bunun uzerinden yapilacak
        })
    return out


def parse_item_state(html: str) -> dict | None:
    """Ilan sayfasindaki schema.org blogundan durum ve fiyat."""
    avail = _AVAIL_RE.search(html)
    if not avail:
        return None
    price = _OFFER_PRICE_RE.search(html)
    name = _LD_NAME_RE.search(html)
    value = avail.group(1).rsplit("/", 1)[-1]
    state = {"InStock": "active"}.get(value, "sold" if "Sold" in value or "OutOfStock" in value else "unknown")
    return {
        "state": state,
        "availability": value,
        "price": float(price.group(1)) if price else None,
        "title": name.group(1) if name else None,
    }


def add_event(conn, item_id: int, etype: str, price=None, favourites=None) -> None:
    conn.execute(
        "INSERT INTO events (item_id, ts, type, price, favourites) VALUES (?,?,?,?,?)",
        (item_id, iso(now()), etype, price, favourites),
    )


def discover(conn: sqlite3.Connection, fetcher: Fetcher, cfg: dict, cell: dict) -> dict:
    market = cell["market"]
    fetcher.warm(market)
    params = {
        "search_text": cell["query"],
        "order": "newest_first",
        "status_ids[]": cfg["conditions"],
    }
    html = fetcher.get(f"https://www.{market}/catalog", params=params)
    if not html:
        return {"found": 0, "new": 0}
    items = parse_catalog(html)
    total, pages = _TOTAL_RE.search(html), _PAGES_RE.search(html)
    results = _RESULTS_RE.search(html)
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
    brand_key = _norm_brand(cell["brand"])

    # Sayfadaki butun ilanlar ornek havuzuna girer (takip kotasindan bagimsiz, bedava veri)
    conn.executemany(
        "INSERT OR IGNORE INTO catalog_samples (item_id, ts, cell, country, brand, title, size, "
        "condition, price, total_price, favourites, is_child) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        [(i["item_id"], iso(now()), cell["id"], cell["country"], i["brand"], i.get("title"),
          i["size"], i["condition"], i["price"], i["total_price"], i["favourites"],
          1 if _CHILD_SIZE_RE.search(i["size"] or "") else 0)
         for i in items if brand_key in _norm_brand(i["brand"] or "")],
    )
    conn.commit()
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
        if brand_key not in _norm_brand(item["brand"] or ""):
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
                   photo_sig, relist_of, state)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'active')""",
            (item["item_id"], market, cell["country"], cell["id"], item["brand"], item.get("title"),
             item["size"], item["condition"], f"https://www.{market}{item['url']}",
             item["price"], item["total_price"], item["favourites"], item["seller_hash"],
             iso(now()), cohort, sig, relist_of),
        )
        add_event(conn, item["item_id"], "discovered", item["price"], item["favourites"])
        new += 1
        room -= 1
    conn.commit()
    return {"found": len(items), "new": new}


def check_interval_days(age_days: float, tr: dict) -> float:
    if age_days <= 7:
        return float(tr["day1_7"])
    if age_days <= 30:
        return float(tr["day8_30"])
    return float(tr["day31_90"])


def due_listings(conn: sqlite3.Connection, cfg: dict, limit: int) -> list[sqlite3.Row]:
    tr = cfg["tracking"]
    rows = conn.execute(
        "SELECT * FROM listings WHERE state='active' ORDER BY COALESCE(last_check, first_seen) LIMIT ?",
        (limit * 4,),
    ).fetchall()
    due = []
    for row in rows:
        first = datetime.strptime(row["first_seen"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        age = (now() - first).total_seconds() / 86400
        if age > float(tr["max_days"]):
            conn.execute("UPDATE listings SET state='expired' WHERE item_id=?", (row["item_id"],))
            continue
        last = row["last_check"] or row["first_seen"]
        last_dt = datetime.strptime(last, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        if (now() - last_dt).total_seconds() / 86400 >= check_interval_days(age, tr):
            due.append(row)
        if len(due) >= limit:
            break
    conn.commit()
    return due


def check_listing(conn: sqlite3.Connection, fetcher: Fetcher, row: sqlite3.Row) -> str:
    fetcher.warm(row["market"])
    html = fetcher.get(row["url"], scan_limit=ITEM_PAGE_SCAN_LIMIT)
    ts = iso(now())

    # SADECE 404/410 "kalkti" demektir. Sayfanin yuklenmemesi ya da durum blogunun
    # o gelisde bulunmamasi ilanin kalktigini GOSTERMEZ (bu varsayim 1397 yanlis kayda
    # yol acmisti). Cozulemeyen kontrol durumu degistirmez, sadece yeniden denenir.
    if html is None:
        if fetcher.last_status in (404, 410):
            first = datetime.strptime(row["first_seen"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            days = round((now() - first).total_seconds() / 86400, 2)
            conn.execute(
                "UPDATE listings SET state='gone', closed_at=?, days_to_close=?, last_check=?, "
                "checks=checks+1 WHERE item_id=?", (ts, days, ts, row["item_id"]),
            )
            add_event(conn, row["item_id"], "gone")
            conn.commit()
            return "gone"
        conn.execute("UPDATE listings SET last_check=?, checks=checks+1 WHERE item_id=?", (ts, row["item_id"]))
        conn.commit()
        return "error"

    info = parse_item_state(html)
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
        first = datetime.strptime(row["first_seen"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        days = round((now() - first).total_seconds() / 86400, 2)
        conn.execute(
            "UPDATE listings SET state='sold', final_price=?, closed_at=?, days_to_close=?, "
            "last_check=?, checks=checks+1, avail_raw=? WHERE item_id=?",
            (price if price is not None else row["price"], ts, days, ts,
             info["availability"], row["item_id"]),
        )
        add_event(conn, row["item_id"], "sold", price)
    else:
        if new_state == "unknown":
            # Tanimadigimiz durum degeri: tahmin yurutmuyoruz, ham degeri kaydedip isaretliyoruz
            add_event(conn, row["item_id"], f"unknown:{info['availability'][:40]}")
        conn.execute(
            "UPDATE listings SET last_check=?, checks=checks+1, state=?, avail_raw=?, unresolved=0 "
            "WHERE item_id=?",
            (ts, "active" if new_state == "active" else row["state"], info["availability"], row["item_id"]),
        )
    conn.commit()
    return new_state


def run_cycle(conn: sqlite3.Connection, cfg: dict, fetcher: Fetcher) -> dict:
    stats = {"discovered": 0, "found": 0, "checked": 0, "sold": 0, "gone": 0, "cells": 0, "takipte": 0}
    reserve = int(cfg["budget"].get("reserve_for_checks", 0.7) * cfg["budget"]["max_requests_per_day"])
    # Takip yuku kapasiteyi asarsa yeni ilan almayi kendiliginden durdurur:
    # yarim takip edilen cok ilan yerine, tam takip edilen daha az ilan.
    tracked = conn.execute("SELECT COUNT(*) c FROM listings WHERE state='active'").fetchone()["c"]
    discovery_open = tracked < int(cfg["budget"].get("max_tracked", 2500))
    stats["takipte"] = tracked
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

        # Sonra kesif, yalnizca kontrol payi korunuyorsa
        for cell in (build_cells(cfg) if discovery_open else []):
            if fetcher.budget_left() <= reserve:
                break
            last = meta_get(conn, f"disc:{cell['id']}")
            if last:
                last_dt = datetime.strptime(last, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                if (now() - last_dt).total_seconds() < cell["discovery_hours"] * 3600:
                    continue
            res = discover(conn, fetcher, cfg, cell)
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
                  ROUND(AVG(CASE WHEN state='sold' THEN days_to_close END), 1) ort_gun,
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
        time.sleep(interval)


if __name__ == "__main__":
    sys.exit(main())
