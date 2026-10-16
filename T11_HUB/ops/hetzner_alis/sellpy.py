#!/usr/bin/env python3
"""
Sellpy ALIS tarafi toplayicisi. Gercek tarayici ile insan hizinda gezer; sayfanin KENDI arama servisinden
(Algolia) aldigi yapilandirilmis yaniti dinler. Arayuzu atlamaz, servise kendisi istek atmaz.
Giris yapmaz, cerez onayi vermez (pencereye dokunmaz: zorunlu olmayan cerez kurulmaz), gorsel indirmez.

    python sellpy.py              -> surekli calisir (systemd)
    python sellpy.py --tek-tur N  -> en fazla N sayfa gezip durur (test)

Adres parametreleri (2026-10-12 olcumle dogrulandi, kroki: ops/platform_kroki/sellpy.md):
  /search/<Herren|Damen>/<kategori yolu>?query=<marka>&condition=Neuwertig&condition=Sehr gut
  &sortBy=saleStartedAt_desc (en yeni once)&page=N (1'den baslar). Sayfa basina 60 ilan.
Fiyat kurus cinsinden gelir (price_DE.amount 650 = 6,50 EUR).
Kusurlar Sellpy'de yapilandirilmis yazilir (metadata.defects); ELENMEZ, kayda gecer.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
import kleinanzeigen as K  # noqa: E402  (ortak: tarayici, marka listesi, veritabani, health)

SITE = "https://www.sellpy.de"
PAGES_PER_DAY = 1500
CONDITIONS = ("Neuwertig", "Sehr gut")
SP_CATS = {
    "jacken": "Kleidung/Jacken & Outdoor",
    "oberteile": "Kleidung/Pullover & Strickjacken",
    "jeans": "Kleidung/Hosen & Jeans/Jeans",
    "schuhe": "Schuhe",
}
CELL_HOURS = {"core": 12, "watch": 24, "luxury": 24}
FIRST_VISIT_PAGES = 8      # ilk ziyaret: mevcut stoktan en fazla 8 x 60 ilan
LATER_PAGES = 4            # sonraki ziyaretler: tamami bilinen sayfaya gelince durur
WAIT_RESULT = 40           # arama yaniti icin en fazla (olculdu: CPU sinirinda 17-20 sn surebiliyor)


def log(msg: str) -> None:
    K.log("[sellpy] " + msg)


def connect():
    conn = K.connect()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS sp_items (
        object_id TEXT PRIMARY KEY, cell TEXT, brand_q TEXT, brand TEXT, brand_ok INTEGER, gender TEXT, cat TEXT,
        cat_path TEXT, type TEXT, condition TEXT, defects TEXT, defect_n INTEGER, size TEXT, color TEXT,
        material TEXT, season TEXT, price REAL, old_price REAL, fav INTEGER, first_offered TEXT, sale_started TEXT,
        created TEXT, reserved INTEGER, for_sale INTEGER, sale_type TEXT, p2p INTEGER, price_point INTEGER,
        url TEXT, baseline INTEGER, first_seen TEXT, last_seen TEXT);
    CREATE TABLE IF NOT EXISTS sp_cells (cell TEXT PRIMARY KEY, first_visit TEXT, last_visit TEXT,
        last_total INTEGER, visits INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS sp_budget (day TEXT PRIMARY KEY, pages INTEGER);
    """)
    if "image_url" not in {r[1] for r in conn.execute("PRAGMA table_info(sp_items)")}:
        conn.execute("ALTER TABLE sp_items ADD COLUMN image_url TEXT")   # yalniz adres; gorsel saklanmaz
    return conn


def count_page(conn) -> None:
    conn.execute("INSERT INTO sp_budget VALUES (date('now'),1) ON CONFLICT(day) DO UPDATE SET pages=pages+1")
    conn.commit()


def pages_today(conn) -> int:
    r = conn.execute("SELECT pages FROM sp_budget WHERE day=date('now')").fetchone()
    return r[0] if r else 0


def build_cells() -> list[dict]:
    out = []
    for c in K.build_cells():
        if c["cat"] not in SP_CATS:
            continue
        g = "Herren" if c["gender"] == "herren" else "Damen"
        path = urllib.parse.quote(f"/search/{g}/{SP_CATS[c['cat']]}")
        qs = urllib.parse.urlencode([("query", c["brand"])] + [("condition", x) for x in CONDITIONS]
                                    + [("sortBy", "saleStartedAt_desc")])
        out.append({**c, "url": f"{SITE}{path}?{qs}"})
    return out


def ms_to_ts(v) -> str | None:
    try:
        return datetime.fromtimestamp(float(v) / (1000 if float(v) > 1e11 else 1), timezone.utc) \
            .strftime("%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return None


class Listener:
    """Sayfanin arama servisinden aldigi yanitlari toplar (yalnizca ilan indeksi, liste boyutunda)."""

    def __init__(self):
        self.results: list[dict] = []

    def attach(self, page) -> None:
        page.on("response", self._on_response)

    async def _on_response(self, resp) -> None:
        if "algolia.net" not in resp.url or resp.request.method != "POST":
            return
        try:
            body = json.loads(resp.request.post_data or "{}")
            data = await resp.json()
        except Exception:
            return
        for q, res in zip(body.get("requests", []), data.get("results", [])):
            if "marketItem" in q.get("indexName", "") and q.get("hitsPerPage", 0) >= 20:
                self.results.append({"query": q, "res": res})


def save_hits(conn, cell: dict, hits: list[dict], baseline: bool) -> tuple[int, int, int]:
    """(kaydedilen, yeni, ilk 3 disi kondisyon) dondurur."""
    ids = [h["objectID"] for h in hits]
    seen = {r[0] for r in conn.execute(
        f"SELECT object_id FROM sp_items WHERE object_id IN ({','.join('?' * len(ids))})", ids)} if ids else set()
    off = 0
    for h in hits:
        m = h.get("metadata") or {}
        if m.get("condition") not in CONDITIONS:
            off += 1
            continue
        defects = m.get("defects") or []
        price = (h.get("price_DE") or {}).get("amount")
        old = ((h.get("priceDrop_DE") or {}).get("oldPrice") or {}).get("amount")
        lvl = (h.get("categories") or {})
        path = (lvl.get("lvl3") or lvl.get("lvl2") or lvl.get("lvl1") or [None])[0]
        conn.execute(
            "INSERT INTO sp_items (object_id, cell, brand_q, brand, brand_ok, gender, cat, cat_path, type, "
            "condition, defects, defect_n, size, color, material, season, price, old_price, fav, first_offered, "
            "sale_started, created, reserved, for_sale, sale_type, p2p, price_point, url, baseline, first_seen, "
            "last_seen) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,"
            "datetime('now'),datetime('now')) ON CONFLICT(object_id) DO UPDATE SET last_seen=datetime('now'), "
            "price=excluded.price, old_price=excluded.old_price, fav=excluded.fav, reserved=excluded.reserved, "
            "for_sale=excluded.for_sale",
            (h["objectID"], cell["id"], cell["brand"], m.get("brand"), K.marke_matches(m.get("brand"), cell["aliases"]),
             cell["gender"], cell["cat"], path, m.get("type"), m.get("condition"),
             "; ".join(f"{d.get('type')}@{d.get('location') or '-'}" for d in defects) or None, len(defects),
             m.get("size"), ",".join(m.get("color") or []) or None, ",".join(m.get("material") or []) or None,
             ",".join(m.get("season") or []) or None,
             price / 100 if price else None, old / 100 if old else None, h.get("favouriteCount"),
             ms_to_ts(h.get("firstOfferedAt_DE")), ms_to_ts(h.get("saleStartedAt")), ms_to_ts(h.get("createdAt")),
             int(bool(h.get("isReserved"))), int(bool(h.get("isForSale"))), h.get("saleType"),
             int(bool(h.get("p2p"))), (h.get("brandClassification") or {}).get("pricePoint"),
             f"{SITE}/item/{h['objectID']}", 1 if baseline else 0))
        if h.get("images"):
            conn.execute("UPDATE sp_items SET image_url=? WHERE object_id=?", (h["images"][0], h["objectID"]))
    conn.commit()
    return len(hits) - off, len(set(ids) - seen), off


async def read_page(br: K.Browser, lst: Listener, conn, cell: dict, page_no: int) -> dict | None:
    url = cell["url"] + (f"&page={page_no}" if page_no > 1 else "")
    hit = None
    for attempt in (1, 2):
        lst.results.clear()
        if attempt == 1:
            status = await br.visit(url, "sp_liste")
            if status != 200:
                return None
        else:
            # bir insanin "yenile"ye basmasi gibi tek seferlik yeniden yukleme
            try:
                await br.page.reload(wait_until="domcontentloaded", timeout=45000)
            except Exception as exc:
                K.note(conn, "sp_okuma", "ag", f"yenileme: {type(exc).__name__}", url)
                return None
        for _ in range(WAIT_RESULT * 2):
            hit = next((r for r in lst.results if (r["query"].get("page") or 0) == page_no - 1), None)
            if hit:
                break
            await asyncio.sleep(0.5)
        if hit:
            if attempt == 2:
                K.note(conn, "sp_yenileme", "ok")
            break
        # teshis: o ana kadar gelen yanitlar ve sayfa basligi (bir sonraki hatada sebep kesin gorunsun)
        got = [(r["query"].get("page"), r["query"].get("indexName", "")[-12:], r["query"].get("hitsPerPage"))
               for r in lst.results]
        try:
            title = (await br.page.title())[:60]
        except Exception:
            title = "?"
        K.note(conn, "sp_yenileme" if attempt == 1 else "sp_okuma", "okunamadi",
               f"arama yaniti gelmedi (deneme {attempt}) | gelen {got[:6]} | baslik {title} | url {br.page.url[-50:]}",
               url)
    if not hit:
        return None
    # yanitin gercekten istedigimiz filtreyle geldigini dogrula (adres parametresi bozulursa sessizce kaymasin)
    ff = json.dumps(hit["query"].get("facetFilters") or [], ensure_ascii=False)
    if not all(f"metadata.condition:{c}" in ff for c in CONDITIONS) or "saleStartedAt_desc" not in \
            hit["query"].get("indexName", ""):
        K.note(conn, "sp_okuma", "eksik", f"filtre/siralama tutmadi: {hit['query'].get('indexName')} {ff[:150]}", url)
        return None
    await br.human()
    return hit["res"]


async def visit_cell(br: K.Browser, lst: Listener, conn, cell: dict, budget_left) -> dict:
    first = conn.execute("SELECT 1 FROM sp_cells WHERE cell=?", (cell["id"],)).fetchone() is None
    out = {"sayfa": 0, "kayit": 0, "yeni": 0, "okundu": False}
    max_pages = FIRST_VISIT_PAGES if first else LATER_PAGES
    total = None
    for page_no in range(1, max_pages + 1):
        if budget_left() <= 0:
            break
        res = await read_page(br, lst, conn, cell, page_no)
        if res is None:
            break
        out["okundu"] = True
        out["sayfa"] += 1
        total = res.get("nbHits")
        hits = res.get("hits") or []
        if not hits:
            K.note(conn, "sp_okuma", "ok" if page_no > 1 or total == 0 else "bos")
            break
        saved, new, off = save_hits(conn, cell, hits, first)
        out["kayit"] += saved
        out["yeni"] += 0 if first else new
        K.note(conn, "sp_okuma", "eksik" if off else "ok", f"ilk 3 disi kondisyon {off}" if off else "")
        # en yeni once siralama: sayfanin tamami zaten biliniyorsa geri kalani da bilinir
        if (not first and new == 0) or page_no >= (res.get("nbPages") or 1):
            break
    if out["okundu"]:
        conn.execute("INSERT INTO sp_cells VALUES (?, datetime('now'), datetime('now'), ?, 1) ON CONFLICT(cell) "
                     "DO UPDATE SET last_visit=datetime('now'), last_total=excluded.last_total, visits=visits+1",
                     (cell["id"], total))
        conn.commit()
    return out


def due(conn, cells):
    last = {r[0]: r[1] for r in conn.execute("SELECT cell, last_visit FROM sp_cells")}
    now = datetime.now(timezone.utc)
    out = []
    for c in cells:
        lv = last.get(c["id"])
        if lv is None:
            out.append((0, random.random(), c))
        elif now - datetime.strptime(lv, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc) \
                >= timedelta(hours=CELL_HOURS.get(c["tier"], 24)):
            out.append((1, random.random(), c))
    return [c for _, _, c in sorted(out, key=lambda x: (x[0], x[1]))]


async def run(max_pages: int | None) -> None:
    from playwright.async_api import async_playwright
    conn = connect()
    cells = build_cells()
    lst = Listener()
    log(f"basladi: {len(cells)} hucre, gunluk sayfa {PAGES_PER_DAY}")
    start = pages_today(conn)

    def budget_left() -> int:
        if max_pages is not None:
            return max_pages - (pages_today(conn) - start)
        return PAGES_PER_DAY - pages_today(conn)

    async with async_playwright() as pw:
        br = K.Browser(pw, conn, home=SITE + "/", count=count_page, on_page=lst.attach)
        while True:
            if budget_left() <= 0:
                if max_pages is not None:
                    break
                await br.close()
                await asyncio.sleep(900)
                continue
            if max_pages is None and not K.active_now():
                await br.close()
                await asyncio.sleep(600)
                continue
            todo = due(conn, cells)
            if not todo:
                if max_pages is not None:
                    break
                await br.close()
                await asyncio.sleep(900)
                continue
            cell = todo[0]
            res = await br.guarded(visit_cell(br, lst, conn, cell, budget_left), f"sellpy {cell['id']}") \
                or {"sayfa": 0, "kayit": 0, "yeni": 0, "okundu": False}
            log(f"{cell['id']}: {res}")
        await br.close()
    log("bitti")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tek-tur", type=int, metavar="N")
    args = ap.parse_args()
    asyncio.run(run(args.tek_tur))
