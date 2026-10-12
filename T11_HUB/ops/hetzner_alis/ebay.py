#!/usr/bin/env python3
"""
eBay ALIS tarafi toplayicisi: resmi Browse API (EBAY_DE). Sayfa kazimaz; yalnizca aktif ilanlari okur.

    python ebay.py              -> surekli calisir (systemd)
    python ebay.py --tek-tur N  -> en fazla N hucre arar ve durur (test)

Anahtarlar: ebay.env (EBAY_CLIENT_ID / EBAY_CLIENT_SECRET, chmod 600). Uygulama token'i 2 saatte bir
kendiliginden yenilenir. Veri yalnizca ic kullanim icindir (eBay API kosulu: baskasina yayinlanmaz).

Kondisyon Satici konumu: yalnizca AB ici (gumruksuz; AT/FR/BE/NL/IT/PL dahil). AB disi (GB, KR, CA, JP, US) gumruk/ithalat
KDV'si ve replika riski nedeniyle alinmaz; ulke ayri kaydedilir.
Kondisyon (eBay'in kendi listesinden dogrulandi, 2026-10-12): 1000 Neu mit Etikett/Karton,
1500 Neu ohne Etikett/Karton, 2990 Gebraucht - Hervorragend. 1750 (Neu mit Mängeln), 3000, 3010 alinmaz.
Acik artirmanin fiyati guncel teklif oldugundan fiyat istatistigine ayri tur olarak girer (buying).
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
import kleinanzeigen as K  # noqa: E402  (ortak: marka listesi, normallestirme, veritabani, health)

API = "https://api.ebay.com"
CONDITIONS = "1000|1500|2990"
EB_CATS = {
    "jacken": [("herren", 57988), ("damen", 63862)],
    "oberteile": [("herren", 11484), ("damen", 63866)],
    "jeans": [("herren", 11483), ("damen", 11554)],
    "schuhe": [("herren", 93427), ("damen", 3034)],
}
CELL_HOURS = {"core": 12, "watch": 24, "luxury": 24}
PAGE_LIMIT = 200
CALLS_PER_DAY = 3000          # eBay varsayilan Browse kotasi 5000/gun; pay birakilir
CALL_GAP = (2, 5)


def log(msg: str) -> None:
    K.log("[ebay] " + msg)


class Api:
    def __init__(self, conn):
        env = dict(l.strip().split("=", 1) for l in open(os.path.join(BASE_DIR, "ebay.env"), encoding="utf-8")
                   if "=" in l)
        self.cid, self.secret = env["EBAY_CLIENT_ID"], env["EBAY_CLIENT_SECRET"]
        self.conn = conn
        self.token, self.exp = None, 0.0

    def _token(self) -> str:
        if self.token and time.time() < self.exp - 300:
            return self.token
        auth = base64.b64encode(f"{self.cid}:{self.secret}".encode()).decode()
        req = urllib.request.Request(
            API + "/identity/v1/oauth2/token",
            data=urllib.parse.urlencode({"grant_type": "client_credentials",
                                         "scope": "https://api.ebay.com/oauth/api_scope"}).encode(),
            headers={"Authorization": "Basic " + auth, "Content-Type": "application/x-www-form-urlencoded"})
        tok = json.load(urllib.request.urlopen(req, timeout=20))
        self.token, self.exp = tok["access_token"], time.time() + tok["expires_in"]
        K.note(self.conn, "eb_token", "ok")
        return self.token

    def get(self, path: str, params: dict) -> dict | None:
        url = API + path + "?" + urllib.parse.urlencode(params, safe="{}|:,")
        try:
            req = urllib.request.Request(url, headers={
                "Authorization": "Bearer " + self._token(), "X-EBAY-C-MARKETPLACE-ID": "EBAY_DE",
                "Accept-Language": "de-DE"})
            data = json.load(urllib.request.urlopen(req, timeout=30))
            K.count_page(self.conn)
            K.note(self.conn, "eb_arama", "ok")
            return data
        except urllib.error.HTTPError as exc:
            body = exc.read()[:300].decode("utf-8", "replace")
            K.note(self.conn, "eb_arama", "engel" if exc.code in (401, 403, 429) else "http",
                   f"HTTP {exc.code} {body}", url)
            if exc.code == 401:
                self.token = None
            if exc.code == 429:
                log("kota/hiz siniri: 30 dk bekleme")
                self.conn.execute("INSERT INTO pauses (ts, minutes, reason) VALUES (datetime('now'),30,'ebay 429')")
                self.conn.commit()
                time.sleep(1800)
        except Exception as exc:
            K.note(self.conn, "eb_arama", "ag", f"{type(exc).__name__}: {exc}"[:200], url)
        return None


def connect():
    conn = K.connect()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS eb_items (
        item_id TEXT PRIMARY KEY, cell TEXT, brand TEXT, cat TEXT, gender TEXT, url TEXT, title TEXT,
        price REAL, currency TEXT, buying TEXT, condition_id TEXT, condition TEXT, ship_cost REAL, ship_type TEXT,
        country TEXT, postal TEXT, seller TEXT, seller_score INTEGER, seller_pct REAL, created TEXT,
        end_date TEXT, category_id TEXT, title_brand INTEGER, baseline INTEGER, first_seen TEXT, last_seen TEXT);
    CREATE TABLE IF NOT EXISTS eb_cells (cell TEXT PRIMARY KEY, first_visit TEXT, last_visit TEXT,
        last_total INTEGER, visits INTEGER DEFAULT 0);
    """)
    return conn


def build_cells() -> list[dict]:
    out = []
    for c in K.build_cells():
        if c["cat"] not in EB_CATS:
            continue
        cat_id = dict(EB_CATS[c["cat"]])[c["gender"]]
        out.append({**c, "cat_id": cat_id, "id": f"{c['brand']}|{c['cat']}|{c['gender']}"})
    return out


def visit_cell(api: Api, conn, cell: dict) -> dict:
    data = api.get("/buy/browse/v1/item_summary/search", {
        "q": cell["brand"], "category_ids": cell["cat_id"], "limit": PAGE_LIMIT, "sort": "newlyListed",
        "filter": f"conditionIds:{{{CONDITIONS}}},deliveryCountry:DE,itemLocationRegion:EUROPEAN_UNION"})
    if data is None:
        return {"okundu": False, "n": 0, "yeni": 0}
    items = data.get("itemSummaries", []) or []
    first = conn.execute("SELECT 1 FROM eb_cells WHERE cell=?", (cell["id"],)).fetchone() is None
    conn.execute("INSERT INTO eb_cells VALUES (?, datetime('now'), datetime('now'), ?, 1) ON CONFLICT(cell) DO "
                 "UPDATE SET last_visit=datetime('now'), last_total=excluded.last_total, visits=visits+1",
                 (cell["id"], data.get("total")))
    ids = [i["itemId"] for i in items]
    seen = {r[0] for r in conn.execute(f"SELECT item_id FROM eb_items WHERE item_id IN ({','.join('?'*len(ids))})",
                                       ids)} if ids else set()
    bad_cond = 0
    for it in items:
        if it.get("conditionId") not in CONDITIONS.split("|"):
            bad_cond += 1
            continue
        ship = (it.get("shippingOptions") or [{}])[0]
        cost = ship.get("shippingCost", {}).get("value")
        seller = it.get("seller", {})
        loc = it.get("itemLocation", {})
        price = it.get("currentBidPrice") if "AUCTION" in it.get("buyingOptions", []) and it.get("currentBidPrice") \
            else it.get("price", {})
        conn.execute(
            "INSERT INTO eb_items VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'),"
            "datetime('now')) ON CONFLICT(item_id) DO UPDATE SET last_seen=datetime('now'), price=excluded.price, "
            "buying=excluded.buying",
            (it["itemId"], cell["id"], cell["brand"], cell["cat"], cell["gender"], it.get("itemWebUrl"),
             it.get("title"), float(price["value"]) if price.get("value") else None, price.get("currency"),
             ",".join(it.get("buyingOptions", [])), it.get("conditionId"), it.get("condition"),
             float(cost) if cost is not None else None, ship.get("shippingCostType"), loc.get("country"),
             loc.get("postalCode"), seller.get("username"), seller.get("feedbackScore"),
             float(seller["feedbackPercentage"]) if seller.get("feedbackPercentage") else None,
             (it.get("itemCreationDate") or "")[:19].replace("T", " ") or None,
             (it.get("itemEndDate") or "")[:19].replace("T", " ") or None,
             (it.get("categories") or [{}])[0].get("categoryId"),
             1 if K.title_has_brand(it.get("title", ""), cell["aliases"]) else 0, 1 if first else 0))
    conn.commit()
    # filtre bozulursa (eBay ilk 3 disi kondisyon dondururse) saglamada gorunsun
    K.note(conn, "eb_okuma", "eksik" if bad_cond else "ok", f"ilk 3 disi kondisyon {bad_cond}" if bad_cond else "")
    return {"okundu": True, "n": len(items), "yeni": 0 if first else len(set(ids) - seen), "toplam": data.get("total")}


def due(conn, cells):
    last = {r[0]: r[1] for r in conn.execute("SELECT cell, last_visit FROM eb_cells")}
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


def calls_today(conn) -> int:
    return conn.execute("SELECT COALESCE(SUM(n),0) FROM health WHERE day=date('now') AND stage='eb_arama'").fetchone()[0]


def run(limit: int | None) -> None:
    conn = connect()
    api = Api(conn)
    cells = build_cells()
    log(f"basladi: {len(cells)} hucre")
    done = 0
    while True:
        if limit is not None and done >= limit:
            break
        if calls_today(conn) >= CALLS_PER_DAY:
            time.sleep(900)
            continue
        todo = due(conn, cells)
        if not todo:
            if limit is not None:
                break
            time.sleep(600)
            continue
        cell = todo[0]
        res = visit_cell(api, conn, cell)
        done += 1
        log(f"{cell['id']}: {res}")
        time.sleep(random.uniform(*CALL_GAP))
    log("bitti")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tek-tur", type=int, metavar="N")
    args = ap.parse_args()
    run(args.tek_tur)
