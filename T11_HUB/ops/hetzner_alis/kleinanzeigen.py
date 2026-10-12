#!/usr/bin/env python3
"""
Kleinanzeigen ALIS tarafi toplayicisi. Salt okur: giris yapmaz, mesaj atmaz, cerez onayi vermez,
gorsel indirmez/saklamaz. Gercek tarayici (Chromium) ile insan hiziyla gezer.

    python kleinanzeigen.py              -> surekli calisir (systemd)
    python kleinanzeigen.py --tek-tur N  -> en fazla N sayfa gezip durur (test)

Kurallar (kroki: ops/platform_kroki/kleinanzeigen.md):
  - Arama: marka x kategori x tur, yalnizca ilk 3 kondisyon (Neu mit Etikett / Neu / Sehr Gut), en yeni once.
  - Ilan sayfasi yalnizca basliginda marka gecen ilanlar icin acilir; once takip basladiktan sonra
    yayinlananlar (yeni), sonra mevcut stok (baseline). Aciklamada markayi anan ilan (benzer/wie X) acilmaz.
  - TOP (ucretli one cikarilmis) ilanin listede tarihi yoktur; tarih ilan sayfasindan alinir.
  - Fiyati "VB"/"Zu verschenken"/bos olan ilanin fiyati istatistige girmez (price NULL, price_type yazilir).
  - Kusur kelimeleri ELEMEZ, isaretler (defect_words).
  - Her sayfanin sonucu health tablosuna: (gun, asama, sonuc) -> sayi. Engel -> kademeli bekleme.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import re
import sqlite3
import sys
import unicodedata
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "alis.db")
BRAND_CONFIG = os.environ.get("TATANGA_BRAND_CONFIG", "/opt/tatanga-observer/config.json")
BERLIN = ZoneInfo("Europe/Berlin")
SITE = "https://www.kleinanzeigen.de"

PAGES_PER_DAY = 1500            # liste + ilan sayfasi toplami
ACTIVE_HOURS = (7, 23)          # Berlin saati; gece insan gibi uyur
DELAY = (15, 40)                # sayfalar arasi saniye
BREAK_EVERY = (25, 45)          # bu kadar sayfada bir mola
BREAK_MINUTES = (2, 6)
SESSION_PAGES = (60, 110)       # tarayici baglami bu kadar sayfada bir yenilenir (yeni ziyaretci)
CELL_HOURS = {"core": 24, "watch": 48, "luxury": 48}
DETAILS_PER_CELL = 8            # bir hucre ziyaretinde en fazla bu kadar ilan sayfasi
BLOCK_STEPS = (30, 120, 360)    # ust uste engelde bekleme (dk)

ZUSTAND = "global.zustand:new_with_tag,new,like_new"
# bizim kategori -> [(cinsiyet, kategori yolu, kat no, tur filtresi)]
KA_CATS = {
    "jacken": [("herren", "kleidung-herren/jacken_maentel", 160, "kleidung_herren.art_s:jacken_maentel"),
               ("damen", "kleidung-damen/jacken_maentel", 154, "kleidung_damen.art_s:jacken_maentel")],
    "oberteile": [("herren", "kleidung-herren/pullover", 160, "kleidung_herren.art_s:pullover"),
                  ("damen", "kleidung-damen/pullover", 154, "kleidung_damen.art_s:pullover")],
    "jeans": [("herren", "kleidung-herren/jeans", 160, "kleidung_herren.art_s:jeans"),
              ("damen", "kleidung-damen/jeans", 154, "kleidung_damen.art_s:jeans")],
    "schuhe": [("herren", "schuhe-herren", 158, None), ("damen", "schuhe-damen", 159, None)],
}
DEFECT_RE = re.compile(
    r"\b(fleck\w*|loch|l[oö]cher|riss\w*|defekt\w*|kaputt|verf[aä]rb\w*|abgenutzt|pilling|besch[aä]digt\w*|"
    r"stofffehler|gebrauchsspuren|abgel[oö]st|fehlt|fehlen)\b", re.I)


def log(msg: str) -> None:
    print(f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} {msg}", flush=True)


def norm(text: str) -> str:
    t = unicodedata.normalize("NFD", (text or "").lower())
    return "".join(c for c in t if not unicodedata.combining(c)).replace("’", "'").strip()


def slug(brand: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", norm(brand).replace("'", "")).strip("-")


def build_cells() -> list[dict]:
    cfg = json.load(open(BRAND_CONFIG, encoding="utf-8"))
    allowed_extra = cfg.get("extra_categories", {})
    cells = []
    for tier, brands in cfg["brands"].items():
        for brand in brands:
            aliases = [norm(a) for a in cfg.get("brand_match", {}).get(brand, [brand])]
            only = cfg.get("brand_categories", {}).get(brand)
            for cat in KA_CATS:
                if only and cat not in only:
                    continue
                if cat == "jeans" and brand not in allowed_extra.get("jeans", []):
                    continue
                for gender, path, kat, art in KA_CATS[cat]:
                    filt = "+".join(x for x in (art, ZUSTAND) if x)
                    url = f"{SITE}/s-{path}/{slug(cfg.get('brand_search', {}).get(brand, brand))}/k0c{kat}+{filt}"
                    cells.append({"id": f"{brand}|{cat}|{gender}", "brand": brand, "cat": cat, "gender": gender,
                                  "tier": tier, "url": url, "aliases": aliases})
    return cells


def title_has_brand(title: str, aliases: list[str]) -> bool:
    t = " " + re.sub(r"[^a-z0-9'&]+", " ", norm(title)) + " "
    return any((" " + re.sub(r"[^a-z0-9'&]+", " ", a).strip() + " ") in t for a in aliases)


UNKNOWN_MARKE = {"sonstige", "sonstiges", "andere", "keine", "keine angabe", "unbekannt", "no name", "noname"}


def _tokens(text: str) -> set[str]:
    return set(re.sub(r"[^a-z0-9]+", " ", norm(text).replace("&", " ").replace("'", "")).split())


def marke_matches(marke: str | None, aliases: list[str]) -> bool | None:
    """
    Saticinin sectigi Marke bizim marka mi. None = bilinmiyor ("Sonstige" vb.).
    Kelime duzeyinde: biri digerinin kelimelerini kapsiyorsa ayni marka
    ("Gf Ferre" ~ Ferre, "Paul&Shark"/"Shark" ~ Paul & Shark, "Jack" ~ Jack Wolfskin, "adidas Originals" ~ adidas).
    Kisa takma adlar (On) yalnizca TAM eslesir: "Onitsuka" On sayilmaz.
    """
    if not marke or norm(marke) in UNKNOWN_MARKE:
        return None
    got = _tokens(marke)
    glued = re.sub(r"[^a-z0-9]", "", norm(marke))
    for a in aliases:
        at = _tokens(a)
        if not at:
            continue
        if len(a) <= 3:
            if got == at:
                return True
            continue
        if at <= got or (got and got <= at) or glued == re.sub(r"[^a-z0-9]", "", a):
            return True
    return False


def parse_price(text: str | None) -> tuple[float | None, str]:
    t = (text or "").strip()
    if not t:
        return None, "yok"
    if "verschenken" in t.lower():
        return None, "bedava"
    m = re.search(r"(\d{1,3}(?:\.\d{3})*|\d+)(?:,(\d{1,2}))?\s*€", t)
    if not m:
        return None, "vb" if "VB" in t else "yok"
    val = float(m.group(1).replace(".", "") + ("." + m.group(2) if m.group(2) else ""))
    return val, "vb" if "VB" in t else "sabit"


def parse_card_date(text: str | None, now: datetime) -> str | None:
    t = (text or "").strip()
    if t.startswith("Heute"):
        return now.strftime("%Y-%m-%d")
    if t.startswith("Gestern"):
        return (now - timedelta(days=1)).strftime("%Y-%m-%d")
    m = re.match(r"(\d{2})\.(\d{2})\.(\d{4})", t)
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None


# ---------- veritabani ----------

def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_FILE, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS ka_ads (
        adid TEXT PRIMARY KEY, cell TEXT, brand TEXT, cat TEXT, gender TEXT, url TEXT, title TEXT,
        price REAL, price_type TEXT, size_card TEXT, plz TEXT, place TEXT, card_date TEXT, top INTEGER,
        buy_now INTEGER, shipping TEXT, baseline INTEGER, title_brand INTEGER,
        first_seen TEXT, last_seen TEXT,
        detail_at TEXT, detail_status TEXT, art TEXT, marke TEXT, marke_ok INTEGER, groesse TEXT, farbe TEXT,
        zustand TEXT, posted TEXT, ship_cost REAL, seller_type TEXT, seller_since TEXT, seller_ads INTEGER,
        seller_badges TEXT, descr TEXT, defect_words TEXT, detail_price REAL, views INTEGER, tries INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS ka_cells (cell TEXT PRIMARY KEY, first_visit TEXT, last_visit TEXT,
        last_total INTEGER, visits INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS health (day TEXT, stage TEXT, outcome TEXT, n INTEGER,
        PRIMARY KEY (day, stage, outcome));
    CREATE TABLE IF NOT EXISTS error_log (id INTEGER PRIMARY KEY, ts TEXT, stage TEXT, outcome TEXT,
        detail TEXT, url TEXT);
    CREATE TABLE IF NOT EXISTS pauses (id INTEGER PRIMARY KEY, ts TEXT, minutes INTEGER, reason TEXT);
    CREATE TABLE IF NOT EXISTS budget (day TEXT PRIMARY KEY, pages INTEGER);
    CREATE INDEX IF NOT EXISTS ix_ka_detail ON ka_ads (detail_at, baseline, title_brand);
    """)
    if "views" not in {r[1] for r in conn.execute("PRAGMA table_info(ka_ads)")}:
        conn.execute("ALTER TABLE ka_ads ADD COLUMN views INTEGER")
    if "tries" not in {r[1] for r in conn.execute("PRAGMA table_info(ka_ads)")}:
        conn.execute("ALTER TABLE ka_ads ADD COLUMN tries INTEGER DEFAULT 0")
    return conn


def note(conn, stage: str, outcome: str, detail: str = "", url: str = "") -> None:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    conn.execute("INSERT INTO health VALUES (?,?,?,1) ON CONFLICT(day,stage,outcome) DO UPDATE SET n=n+1",
                 (day, stage, outcome))
    if outcome != "ok":
        conn.execute("INSERT INTO error_log (ts, stage, outcome, detail, url) VALUES (datetime('now'),?,?,?,?)",
                     (stage, outcome, detail[:300], url[:300]))
        conn.execute("DELETE FROM error_log WHERE id NOT IN (SELECT id FROM error_log ORDER BY id DESC LIMIT 300)")
    conn.commit()


def pages_today(conn) -> int:
    r = conn.execute("SELECT pages FROM budget WHERE day=date('now')").fetchone()
    return r[0] if r else 0


def count_page(conn) -> None:
    conn.execute("INSERT INTO budget VALUES (date('now'),1) ON CONFLICT(day) DO UPDATE SET pages=pages+1")
    conn.commit()


# ---------- sayfadan okuma (tarayici icinde) ----------

CARDS_JS = r"""
() => [...document.querySelectorAll('article[data-adid]')].map(a => {
  const li = a.closest('li');
  const spans = [...a.querySelectorAll('span')].map(s => s.textContent.trim());
  const badges = [...a.querySelectorAll('[data-dhl-promotion]')].map(s => s.textContent.trim());
  const priceEl = [...a.querySelectorAll('p')].find(p => /€|VB|verschenken/.test(p.textContent));
  return {
    adid: a.dataset.adid, href: a.dataset.href,
    top: !!(li && li.querySelector('svg path[fill="#5A33AE"]')),
    title: (a.querySelector('h3')?.textContent || '').trim(),
    price: priceEl ? priceEl.textContent.trim() : null,
    place: spans.find(s => /^\d{5}\b/.test(s)) || null,
    date: spans.find(s => /^(Heute|Gestern|\d{2}\.\d{2}\.\d{4})/.test(s)) || null,
    badges,
  };
})
"""

STATE_JS = r"""
() => ({
  hasList: !!document.querySelector('#srchrslt-adtable'),
  h1: (document.querySelector('h1')?.innerText || '').replace(/\s+/g, ' '),
  empty: /keine Ergebnisse|leider nichts gefunden/i.test(document.body.innerText.slice(0, 20000)),
  title: document.title,
  ldCount: document.querySelectorAll('#srchrslt-adtable script[type="application/ld+json"]').length,
})
"""

DETAIL_JS = r"""
() => {
  const q = s => document.querySelector(s);
  const details = {};
  // Iki tasarim var (site oturum icinde A/B deneyi uyguluyor):
  //   A: <li>Art<span>Jacken</span></li>      B: <li><span>Art</span><span>Jacken</span></li>
  document.querySelectorAll('#viewad-details li').forEach(li => {
    const spans = [...li.querySelectorAll('span')];
    if (!spans.length) return;
    let label, value;
    if (spans.length >= 2) { label = spans[0].textContent.trim(); value = spans[spans.length - 1].textContent.trim(); }
    else { value = spans[0].textContent.trim(); label = li.textContent.replace(spans[0].textContent, '').trim(); }
    if (label && value && label !== value) details[label] = value;
  });
  const leafDates = [...document.querySelectorAll('#viewad-extra-info span, main span, article span')]
    .filter(x => x.children.length === 0).map(x => x.textContent.trim()).filter(t => /^\d{2}\.\d{2}\.\d{4}$/.test(t));
  const contact = (q('#viewad-contact')?.innerText || q('#viewad-profile-box')?.innerText || '');
  const priceBox = q('#viewad-price')?.parentElement?.innerText || '';
  return {
    title: (q('#viewad-title')?.innerText || '').trim(),
    price: (q('#viewad-price')?.innerText || '').trim(),
    ship: (priceBox.match(/Versand[^\n]*/) || [null])[0],
    locality: (q('#viewad-locality')?.innerText || '').trim(),
    posted: leafDates[0] || null,
    views: (q('#viewad-cntr-num')?.textContent || '').trim(),
    detailsHtml: (q('#viewad-details')?.outerHTML || '').replace(/\s+/g, ' ').slice(0, 280),
    details,
    descr: (q('#viewad-description-text')?.innerText || '').trim().slice(0, 2000),
    sellerType: (contact.match(/(Privater|Gewerblicher) Nutzer/) || [null])[0],
    sellerSince: (contact.match(/Aktiv seit (\d{2}\.\d{2}\.\d{4})/) || [null, null])[1],
    sellerAds: (document.body.innerText.match(/(\d+) Anzeigen online/) || [null, null])[1],
    badges: ['TOP Zufriedenheit', 'Sehr freundlich', 'Besonders zuverlässig', 'Freundlich', 'Zuverlässig']
            .filter(b => contact.includes(b)),
    gone: /nicht mehr verfügbar|wurde gelöscht|existiert nicht/i.test(document.body.innerText.slice(0, 5000)),
  };
}
"""


def dmy(s: str | None) -> str | None:
    m = re.match(r"(\d{2})\.(\d{2})\.(\d{4})", s or "")
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None


# ---------- tarayici ----------

class Browser:
    def __init__(self, pw, conn):
        self.pw, self.conn = pw, conn
        self.browser = self.ctx = self.page = None
        self.pages = 0
        self.limit = random.randint(*SESSION_PAGES)
        self.until_break = random.randint(*BREAK_EVERY)
        self.strikes = 0

    async def start(self, reason: str) -> None:
        await self.close()
        self.browser = await self.pw.chromium.launch(headless=True,
                                                     args=["--disable-blink-features=AutomationControlled"])
        w, h = random.choice([(1366, 768), (1440, 900), (1536, 864), (1920, 1080)])
        self.ctx = await self.browser.new_context(locale="de-DE", timezone_id="Europe/Berlin",
                                                  viewport={"width": w, "height": h})
        self.page = await self.ctx.new_page()
        # gorsel/yazi tipi/video indirilmez: hem veri saklamama kurali hem trafik
        await self.page.route(re.compile(r"\.(png|jpe?g|webp|gif|avif|svg|mp4|woff2?)(\?|$)|img\.kleinanzeigen"),
                              lambda r: r.abort())
        self.pages, self.limit = 0, random.randint(*SESSION_PAGES)
        log(f"yeni tarayici oturumu ({reason}) {w}x{h}")
        await self.visit(SITE + "/", "oturum")

    async def close(self) -> None:
        if self.browser:
            try:
                await self.browser.close()
            except Exception:
                pass
        self.browser = self.ctx = self.page = None

    async def human(self) -> None:
        for _ in range(random.randint(1, 3)):
            await self.page.mouse.wheel(0, random.randint(300, 900))
            await self.page.wait_for_timeout(random.randint(600, 1800))

    async def visit(self, url: str, stage: str, referer_wait: bool = True) -> int | None:
        """Sayfaya gider; HTTP durumunu dondurur (None = ag hatasi). Butce ve molalar burada."""
        if self.page is None:
            await self.start("ilk")
        if self.pages >= self.limit:
            await self.start("oturum yenileme")
        if referer_wait:
            await asyncio.sleep(random.uniform(*DELAY))
        self.until_break -= 1
        if self.until_break <= 0:
            mins = random.uniform(*BREAK_MINUTES)
            log(f"mola {mins:.1f} dk")
            await asyncio.sleep(mins * 60)
            self.until_break = random.randint(*BREAK_EVERY)
        try:
            resp = await self.page.goto(url, wait_until="domcontentloaded", timeout=45000)
            await self.page.wait_for_timeout(random.randint(1500, 3500))
            status = resp.status if resp else None
        except Exception as exc:
            note(self.conn, stage, "ag", f"{type(exc).__name__}: {exc}"[:200], url)
            return None
        self.pages += 1
        count_page(self.conn)
        if status in (403, 429) or re.search(r"Access Denied|Zugriff verweigert|captcha",
                                             (await self.page.title()) or "", re.I):
            note(self.conn, stage, "engel", f"HTTP {status} {await self.page.title()}", url)
            await self.on_block(status)
            return 403
        if status == 200:
            self.strikes = 0
            note(self.conn, stage, "ok")
        elif status in (404, 410):
            self.strikes = 0
        else:
            note(self.conn, stage, "http", f"HTTP {status}", url)
        return status

    async def on_block(self, status) -> None:
        self.strikes += 1
        mins = BLOCK_STEPS[min(self.strikes, len(BLOCK_STEPS)) - 1]
        self.conn.execute("INSERT INTO pauses (ts, minutes, reason) VALUES (datetime('now'),?,?)",
                          (mins, f"engel HTTP {status} ({self.strikes}. ust uste)"))
        self.conn.commit()
        log(f"ENGEL: {mins} dk bekleme ({self.strikes}. ust uste)")
        await self.close()
        await asyncio.sleep(mins * 60)


# ---------- is akisi ----------

async def visit_cell(br: Browser, conn, cell: dict) -> dict:
    now_b = datetime.now(BERLIN)
    status = await br.visit(cell["url"], "liste")
    out = {"kart": 0, "yeni": 0, "okundu": False}
    if status != 200:
        return out
    st = await br.page.evaluate(STATE_JS)
    if not st["hasList"]:
        note(conn, "liste_okuma", "bos" if st["empty"] else "okunamadi", st["title"][:120], cell["url"])
        if st["empty"]:
            out["okundu"] = True
        return out
    await br.human()
    cards = await br.page.evaluate(CARDS_JS)
    if not cards:
        note(conn, "liste_okuma", "bos" if st["empty"] else "okunamadi", st["h1"][:120], cell["url"])
        out["okundu"] = st["empty"]
        return out
    # kart sayisi ile sayfadaki ld+json sayisi tutmali; tutmazsa yapi degismis olabilir
    if st["ldCount"] and len(cards) < 0.9 * st["ldCount"]:
        note(conn, "liste_okuma", "eksik", f"kart {len(cards)} / ld {st['ldCount']}", cell["url"])
    else:
        note(conn, "liste_okuma", "ok")
    m = re.search(r"von ([\d.]+)", st["h1"])
    total = int(m.group(1).replace(".", "")) if m else None
    first = conn.execute("SELECT first_visit FROM ka_cells WHERE cell=?", (cell["id"],)).fetchone()
    is_first = first is None
    conn.execute("INSERT INTO ka_cells (cell, first_visit, last_visit, last_total, visits) "
                 "VALUES (?, datetime('now'), datetime('now'), ?, 1) ON CONFLICT(cell) DO UPDATE SET "
                 "last_visit=datetime('now'), last_total=excluded.last_total, visits=visits+1", (cell["id"], total))
    ids = [c["adid"] for c in cards]
    seen = {r[0] for r in conn.execute(
        f"SELECT adid FROM ka_ads WHERE adid IN ({','.join('?' * len(ids))})", ids)}
    for c in cards:
        price, ptype = parse_price(c["price"])
        badges = c["badges"] or []
        known = {"Direkt kaufen", "Versand möglich", "Nur Abholung"}
        size = next((b for b in badges if b not in known), None)
        shipping = "versand" if "Versand möglich" in badges else "abholung" if "Nur Abholung" in badges else None
        plz, place = (c["place"].split(" ", 1) + [None])[:2] if c["place"] else (None, None)
        has_brand = 1 if title_has_brand(c["title"], cell["aliases"]) else 0
        conn.execute(
            "INSERT INTO ka_ads (adid, cell, brand, cat, gender, url, title, price, price_type, size_card, plz, "
            "place, card_date, top, buy_now, shipping, baseline, title_brand, first_seen, last_seen) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'),datetime('now')) "
            "ON CONFLICT(adid) DO UPDATE SET last_seen=datetime('now'), price=excluded.price, "
            "price_type=excluded.price_type",
            (c["adid"], cell["id"], cell["brand"], cell["cat"], cell["gender"], SITE + c["href"], c["title"],
             price, ptype, size, plz, place, parse_card_date(c["date"], now_b), int(c["top"]),
             int("Direkt kaufen" in badges), shipping, 1 if is_first else 0, has_brand))
        out["kart"] += 1
        out["yeni"] += 1 if c["adid"] not in seen and not is_first else 0
    conn.commit()
    out["okundu"] = True
    return out


async def visit_detail(br: Browser, conn, row: sqlite3.Row, aliases: list[str]) -> None:
    status = await br.visit(row["url"], "ilan")
    if status in (404, 410):
        conn.execute("UPDATE ka_ads SET detail_at=datetime('now'), detail_status='yok' WHERE adid=?", (row["adid"],))
        conn.commit()
        note(conn, "ilan", "yok")
        return
    if status != 200:
        return
    d = await br.page.evaluate(DETAIL_JS)
    if d["gone"] or not d["title"]:
        conn.execute("UPDATE ka_ads SET detail_at=datetime('now'), detail_status=? WHERE adid=?",
                     ("yok" if d["gone"] else "okunamadi", row["adid"]))
        conn.commit()
        note(conn, "ilan_okuma", "yok" if d["gone"] else "okunamadi", "", row["url"])
        return
    await br.human()
    det = d["details"]
    # zorunlu alan yoksa (tasarim yine degismis) kayit "okundu" sayilmaz: ham yapi gunluge, sonra tekrar denenir
    if not det.get("Zustand"):
        conn.execute("UPDATE ka_ads SET tries=COALESCE(tries,0)+1, detail_status='eksik' WHERE adid=?", (row["adid"],))
        conn.commit()
        note(conn, "ilan_okuma", "eksik", f"alanlar {list(det)} | {d['detailsHtml']}", row["url"])
        return
    price, ptype = parse_price(d["price"])
    ship = None
    if d["ship"]:
        m = re.search(r"(\d+),(\d{2})", d["ship"])
        ship = float(f"{m.group(1)}.{m.group(2)}") if m else None
    text = f"{d['title']} {d['descr']}"
    # "keine/ohne Gebrauchsspuren" kusur degildir: kelimeden onceki 12 karakterde olumsuzlama varsa sayilmaz
    defects = sorted({m.group(0).lower() for m in DEFECT_RE.finditer(text)
                      if not re.search(r"\b(keine?n?|ohne)\s+$", text[max(0, m.start() - 12):m.start()], re.I)})
    conn.execute(
        "UPDATE ka_ads SET detail_at=datetime('now'), detail_status='ok', art=?, marke=?, marke_ok=?, groesse=?, "
        "farbe=?, zustand=?, posted=?, ship_cost=?, seller_type=?, seller_since=?, seller_ads=?, seller_badges=?, "
        "descr=?, defect_words=?, detail_price=?, price_type=?, views=? WHERE adid=?",
        (det.get("Art"), det.get("Marke"), marke_matches(det.get("Marke"), aliases), det.get("Größe"),
         det.get("Farbe"), det.get("Zustand"), dmy(d["posted"]), ship, d["sellerType"], dmy(d["sellerSince"]),
         int(d["sellerAds"]) if d["sellerAds"] else None, ",".join(d["badges"]) or None, d["descr"],
         ",".join(defects) or None, price, ptype, int(d["views"]) if d["views"].isdigit() else None, row["adid"]))
    conn.commit()
    note(conn, "ilan_okuma", "ok")


def due_cells(conn, cells: list[dict]) -> list[dict]:
    last = {r["cell"]: r["last_visit"] for r in conn.execute("SELECT cell, last_visit FROM ka_cells")}
    now = datetime.now(timezone.utc)
    due = []
    for c in cells:
        lv = last.get(c["id"])
        if lv is None:
            due.append((0, random.random(), c))
        elif now - datetime.strptime(lv, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc) \
                >= timedelta(hours=CELL_HOURS.get(c["tier"], 48)):
            due.append((1, random.random(), c))
    return [c for _, _, c in sorted(due, key=lambda x: (x[0], x[1]))]


def pending_details(conn, cell_id: str, limit: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT adid, url FROM ka_ads WHERE cell=? AND detail_at IS NULL AND title_brand=1 AND COALESCE(tries,0) < 3 "
        "ORDER BY baseline, first_seen DESC LIMIT ?", (cell_id, limit)).fetchall()


def active_now() -> bool:
    h = datetime.now(BERLIN).hour
    return ACTIVE_HOURS[0] <= h < ACTIVE_HOURS[1]


async def run(max_pages: int | None) -> None:
    from playwright.async_api import async_playwright
    conn = connect()
    cells = build_cells()
    by_id = {c["id"]: c for c in cells}
    log(f"kleinanzeigen toplayici basladi: {len(cells)} hucre, gunluk sayfa {PAGES_PER_DAY}")
    start_pages = pages_today(conn)
    async with async_playwright() as pw:
        br = Browser(pw, conn)
        while True:
            if max_pages is not None and pages_today(conn) - start_pages >= max_pages:
                break
            if max_pages is None and (not active_now() or pages_today(conn) >= PAGES_PER_DAY):
                await br.close()
                await asyncio.sleep(600)
                continue
            due = due_cells(conn, cells)
            if not due:
                await br.close()
                await asyncio.sleep(900 if max_pages is None else 0)
                if max_pages is not None:
                    break
                continue
            cell = due[0]
            res = await visit_cell(br, conn, cell)
            log(f"{cell['id']}: kart {res['kart']}, yeni {res['yeni']}, okundu {res['okundu']}")
            if not res["okundu"]:
                continue
            for row in pending_details(conn, cell["id"], DETAILS_PER_CELL):
                if max_pages is not None and pages_today(conn) - start_pages >= max_pages:
                    break
                await visit_detail(br, conn, row, by_id[cell["id"]]["aliases"])
        await br.close()
    log("bitti")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tek-tur", type=int, metavar="N", help="en fazla N sayfa gez ve dur (test)")
    args = ap.parse_args()
    asyncio.run(run(args.tek_tur))
