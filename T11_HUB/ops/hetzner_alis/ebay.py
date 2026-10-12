#!/usr/bin/env python3
"""
eBay toplayicisi: resmi Browse API, 7 AB ulkesi. Hem ALIS hem SATIS tarafi: her ulkenin kendi piyasasi.
Sayfa kazimaz; yalnizca ilanlari okur ve takipteki ilanlarin durumunu sorar.

    python ebay.py              -> surekli calisir (systemd)
    python ebay.py --tek-tur N  -> en fazla N arama + N takip sorgusu yapip durur (test)

Anahtarlar: ebay.env (EBAY_CLIENT_ID / EBAY_CLIENT_SECRET, chmod 600). Uygulama token'i 2 saatte bir
kendiliginden yenilenir. Veri yalnizca ic kullanim icindir (eBay API kosulu: baskasina yayinlanmaz).

ULKE: her pazar yerinde yalnizca O ULKEDEKI saticilar (itemLocationCountry) -> ulkenin kendi piyasasi.
  Kategori kodlari 7 sitede de gecerli (2026-10-12 olculdu). Hepsi AB ici: gumruksuz.
KARGO: alici konumu Berlin-Spandau verilir -> ship_cost = kullaniciya gonderim ucreti (yoksa DE'ye gondermiyor).
KONDISYON (eBay'in kendi listesinden dogrulandi): 1000 Neu mit Etikett/Karton, 1500 Neu ohne Etikett/Karton,
  2990 Gebraucht - Hervorragend. 1750 (Neu mit Mängeln), 3000, 3010 alinmaz.
SATIS TAKIBI: takip baslangicindan sonra gorulen ilanlarin bir kismi takibe alinir; getItem ile
  estimatedSoldQuantity / estimatedAvailabilityStatus / teklif sayisi / bitis zamani izlenir.
  Ham durum (HTTP kodu, hata kimligi, durum degeri) HER kontrolde kaydedilir: "satildi" ile "kaldirildi"
  ayrimi tahminle degil, gozlenen veriden kurulur. Kurallar:
    - estimatedSoldQuantity > 0                         -> satildi (kesin)
    - acik artirma bitti ve teklif > 0                   -> satildi (son teklif = satis fiyati)
    - bitis zamanindan ONCE kayboldu, satis adedi yok    -> kalkti (satildi VEYA kaldirildi; ayrilamaz)
    - bitis zamani geldi, teklif/satis yok               -> bitti (satilmadi)
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
MARKETS = {"DE": "EBAY_DE", "AT": "EBAY_AT", "FR": "EBAY_FR", "IT": "EBAY_IT", "NL": "EBAY_NL",
           "BE": "EBAY_BE", "ES": "EBAY_ES"}
EB_CATS = {
    "jacken": [("herren", 57988), ("damen", 63862)],
    "oberteile": [("herren", 11484), ("damen", 63866)],
    "jeans": [("herren", 11483), ("damen", 11554)],
    "schuhe": [("herren", 93427), ("damen", 3034)],
}
BUYER_CTX = "contextualLocation=country%3DDE%2Czip%3D13581"   # Berlin-Spandau
CELL_HOURS_DE = {"core": 12, "watch": 24, "luxury": 24}
CELL_HOURS_OTHER = 48
PAGE_LIMIT = 200
CALLS_PER_DAY = 4500          # eBay varsayilan Browse kotasi 5000/gun; pay birakilir
TRACK_SHARE = 0.4             # gunluk cagrilarin en fazla bu kadari takip kontrolune
ENROLL_PER_VISIT = 6          # bir hucre ziyaretinde takibe alinan en fazla yeni ilan
MAX_TRACKED = 6000
TRACK_DAYS = 30
CALL_GAP = (1.5, 4)
END_GRACE = timedelta(hours=1)   # eBay bitiste durumu hemen guncellemiyor (olculdu: bitisten 40 dk sonra hala IN_STOCK)


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

    def call(self, path: str, params: dict, market: str, stage: str) -> tuple[int | None, dict | None]:
        """(HTTP kodu, govde). Ag hatasinda (None, None). 404 gibi kodlar takip icin anlamlidir: govdesi doner."""
        url = API + path + ("?" + urllib.parse.urlencode(params, safe="{}|:,") if params else "")
        try:
            req = urllib.request.Request(url, headers={
                "Authorization": "Bearer " + self._token(), "X-EBAY-C-MARKETPLACE-ID": MARKETS[market],
                "X-EBAY-C-ENDUSERCTX": BUYER_CTX})
            data = json.load(urllib.request.urlopen(req, timeout=30))
            K.count_page(self.conn)
            K.note(self.conn, stage, "ok")
            return 200, data
        except urllib.error.HTTPError as exc:
            K.count_page(self.conn)
            raw = exc.read()[:600].decode("utf-8", "replace")
            try:
                body = json.loads(raw)
            except ValueError:
                body = {"raw": raw}
            if exc.code == 404 and stage == "eb_takip":
                K.note(self.conn, stage, "yok")
                return 404, body
            K.note(self.conn, stage, "engel" if exc.code in (401, 403, 429) else "http",
                   f"HTTP {exc.code} {raw[:250]}", url)
            if exc.code == 401:
                self.token = None
            if exc.code == 429:
                log("kota/hiz siniri: 30 dk bekleme")
                self.conn.execute("INSERT INTO pauses (ts, minutes, reason) VALUES (datetime('now'),30,'ebay 429')")
                self.conn.commit()
                time.sleep(1800)
            return exc.code, body
        except Exception as exc:
            K.note(self.conn, stage, "ag", f"{type(exc).__name__}: {exc}"[:200], url)
            return None, None


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
    CREATE TABLE IF NOT EXISTS eb_track (
        item_id TEXT PRIMARY KEY, market TEXT, enrolled TEXT, last_check TEXT, checks INTEGER DEFAULT 0,
        state TEXT DEFAULT 'active', closed_at TEXT, close_reason TEXT, sold_qty INTEGER, bid_count INTEGER,
        last_price REAL, avail_raw TEXT, last_http INTEGER, err_raw TEXT, days_to_close REAL);
    CREATE TABLE IF NOT EXISTS eb_track_raw (status TEXT PRIMARY KEY, n INTEGER, example TEXT);
    """)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(eb_items)")}
    for name, decl in (("market", "TEXT"), ("bid_count", "INTEGER")):
        if name not in cols:
            conn.execute(f"ALTER TABLE eb_items ADD COLUMN {name} {decl}")
    # ulke bazina gecmeden onceki kayitlar yalnizca EBAY_DE'den gelmisti
    conn.execute("UPDATE eb_items SET market='DE' WHERE market IS NULL")
    conn.execute("UPDATE eb_cells SET cell=cell||'|DE' WHERE cell NOT LIKE '%|__'")
    conn.commit()
    return conn


def build_cells() -> list[dict]:
    out = []
    for c in K.build_cells():
        if c["cat"] not in EB_CATS:
            continue
        cat_id = dict(EB_CATS[c["cat"]])[c["gender"]]
        for cc in MARKETS:
            hours = CELL_HOURS_DE.get(c["tier"], 24) if cc == "DE" else CELL_HOURS_OTHER
            out.append({**c, "cat_id": cat_id, "market": cc, "hours": hours,
                        "id": f"{c['brand']}|{c['cat']}|{c['gender']}|{cc}"})
    return out


def iso(v: str | None) -> str | None:
    return (v or "")[:19].replace("T", " ") or None


def visit_cell(api: Api, conn, cell: dict) -> dict:
    status, data = api.call("/buy/browse/v1/item_summary/search", {
        "q": cell["brand"], "category_ids": cell["cat_id"], "limit": PAGE_LIMIT, "sort": "newlyListed",
        "filter": f"conditionIds:{{{CONDITIONS}}},itemLocationCountry:{cell['market']}"}, cell["market"], "eb_arama")
    if status != 200:
        return {"okundu": False, "n": 0, "yeni": 0}
    items = data.get("itemSummaries", []) or []
    first = conn.execute("SELECT 1 FROM eb_cells WHERE cell=?", (cell["id"],)).fetchone() is None
    conn.execute("INSERT INTO eb_cells VALUES (?, datetime('now'), datetime('now'), ?, 1) ON CONFLICT(cell) DO "
                 "UPDATE SET last_visit=datetime('now'), last_total=excluded.last_total, visits=visits+1",
                 (cell["id"], data.get("total")))
    ids = [i["itemId"] for i in items]
    seen = {r[0] for r in conn.execute(f"SELECT item_id FROM eb_items WHERE item_id IN ({','.join('?'*len(ids))})",
                                       ids)} if ids else set()
    bad_cond, new_ids = 0, []
    for it in items:
        if it.get("conditionId") not in CONDITIONS.split("|"):
            bad_cond += 1
            continue
        ship = (it.get("shippingOptions") or [{}])[0]
        cost = ship.get("shippingCost", {}).get("value")
        seller = it.get("seller", {})
        loc = it.get("itemLocation", {})
        auction = "AUCTION" in it.get("buyingOptions", [])
        price = it.get("currentBidPrice") if auction and it.get("currentBidPrice") else it.get("price", {})
        conn.execute(
            "INSERT INTO eb_items (item_id, cell, brand, cat, gender, url, title, price, currency, buying, "
            "condition_id, condition, ship_cost, ship_type, country, postal, seller, seller_score, seller_pct, "
            "created, end_date, category_id, title_brand, baseline, first_seen, last_seen, market, bid_count) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'),datetime('now'),?,?) "
            "ON CONFLICT(item_id) DO UPDATE SET last_seen=datetime('now'), price=excluded.price, "
            "buying=excluded.buying, bid_count=excluded.bid_count, ship_cost=excluded.ship_cost",
            (it["itemId"], cell["id"], cell["brand"], cell["cat"], cell["gender"], it.get("itemWebUrl"),
             it.get("title"), float(price["value"]) if price.get("value") else None, price.get("currency"),
             ",".join(it.get("buyingOptions", [])), it.get("conditionId"), it.get("condition"),
             float(cost) if cost is not None else None, ship.get("shippingCostType"), loc.get("country"),
             loc.get("postalCode"), seller.get("username"), seller.get("feedbackScore"),
             float(seller["feedbackPercentage"]) if seller.get("feedbackPercentage") else None,
             iso(it.get("itemCreationDate")), iso(it.get("itemEndDate")),
             (it.get("categories") or [{}])[0].get("categoryId"),
             1 if K.title_has_brand(it.get("title", ""), cell["aliases"]) else 0, 1 if first else 0,
             cell["market"], it.get("bidCount")))
        if not first and it["itemId"] not in seen:
            new_ids.append(it["itemId"])
    # takip: yalnizca takip basladiktan sonra ilk kez gorulen ilanlar (yasi bilinir); hucre basina sinirli
    tracked = conn.execute("SELECT COUNT(*) FROM eb_track WHERE state='active'").fetchone()[0]
    for iid in random.sample(new_ids, min(len(new_ids), ENROLL_PER_VISIT)):
        if tracked >= MAX_TRACKED:
            break
        conn.execute("INSERT OR IGNORE INTO eb_track (item_id, market, enrolled) VALUES (?,?,datetime('now'))",
                     (iid, cell["market"]))
        tracked += 1
    conn.commit()
    K.note(conn, "eb_okuma", "eksik" if bad_cond else "ok", f"ilk 3 disi kondisyon {bad_cond}" if bad_cond else "")
    return {"okundu": True, "n": len(items), "yeni": len(new_ids), "toplam": data.get("total")}


def track_interval_days(age_days: float) -> float:
    return 1 if age_days <= 3 else 2 if age_days <= 10 else 4


def due_tracks(conn, limit: int) -> list:
    rows = conn.execute(
        "SELECT t.item_id, t.market, t.enrolled, t.last_check, e.end_date, e.buying FROM eb_track t "
        "JOIN eb_items e USING(item_id) WHERE t.state='active' ORDER BY t.last_check IS NOT NULL, t.last_check "
        "LIMIT ?", (limit * 4,)).fetchall()
    now = datetime.now(timezone.utc)
    out = []
    for r in rows:
        enrolled = datetime.strptime(r["enrolled"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        age = (now - enrolled).total_seconds() / 86400
        if r["last_check"] is None:
            out.append(r)
        else:
            last = datetime.strptime(r["last_check"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            end = datetime.strptime(r["end_date"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc) \
                if r["end_date"] else None
            # bitis zamani gectiyse hemen bak: artirma sonucu ve "bitti" ayrimi bitiste netlesir
            if (end and now >= end + END_GRACE and last < end + END_GRACE) or (now - last).total_seconds() / 86400 >= track_interval_days(age):
                out.append(r)
        if len(out) >= limit:
            break
    return out


def note_raw(conn, status: str, example: str) -> None:
    conn.execute("INSERT INTO eb_track_raw VALUES (?,1,?) ON CONFLICT(status) DO UPDATE SET n=n+1",
                 (status[:120], example[:300]))


def check_track(api: Api, conn, row) -> str:
    status, data = api.call(f"/buy/browse/v1/item/{urllib.parse.quote(row['item_id'])}", {}, row["market"],
                            "eb_takip")
    if status is None:
        return "ag"
    now = datetime.now(timezone.utc)
    now_s = now.strftime("%Y-%m-%d %H:%M:%S")
    enrolled = datetime.strptime(row["enrolled"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    end = datetime.strptime(row["end_date"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc) \
        if row["end_date"] else None
    if status == 200:
        av = (data.get("estimatedAvailabilities") or [{}])[0]
        sold = av.get("estimatedSoldQuantity") or 0
        st = av.get("estimatedAvailabilityStatus")
        bids = data.get("bidCount")
        price = (data.get("currentBidPrice") or data.get("price") or {}).get("value")
        reserve_met = data.get("reservePriceMet")
        new_end = iso(data.get("itemEndDate"))
        if new_end and new_end != row["end_date"]:
            # uzatilan / yeniden listelenen ilan: bitis zamani guncellenir, yanlis kapanmaz
            conn.execute("UPDATE eb_items SET end_date=? WHERE item_id=?", (new_end, row["item_id"]))
            end = datetime.strptime(new_end, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        note_raw(conn, f"200:{st}:sold>0={sold > 0}:bids>0={bool(bids)}:reserve={reserve_met}", row["item_id"])
        state, reason = "active", None
        ended = end is not None and now >= end + END_GRACE
        if sold > 0:
            state, reason = "sold", "satis adedi"
        elif ended and bids and reserve_met is not False:
            state, reason = "sold", "artirma teklifle bitti"
        elif ended and bids:
            state, reason = "ended", "teklif var ama rezerv fiyat karsilanmadi"
        elif ended:
            state, reason = "ended", "bitti, satis yok"
        elif st == "OUT_OF_STOCK":
            state, reason = "gone", "stok bitti, satis adedi yok"
        conn.execute("UPDATE eb_track SET last_check=?, checks=checks+1, sold_qty=?, bid_count=?, last_price=?, "
                     "avail_raw=?, last_http=200, state=?, close_reason=?, closed_at=CASE WHEN ?<>'active' THEN ? END,"
                     " days_to_close=CASE WHEN ?<>'active' THEN ? END WHERE item_id=?",
                     (now_s, sold, bids, float(price) if price else None, st, state, reason, state, now_s,
                      state, (now - enrolled).total_seconds() / 86400, row["item_id"]))
    else:
        errs = (data or {}).get("errors") or [{}]
        err = f"{errs[0].get('errorId')}:{errs[0].get('message', '')[:60]}"
        note_raw(conn, f"{status}:{errs[0].get('errorId')}", f"{row['item_id']} {err}")
        if status == 404:
            ended = end is not None and now >= end + END_GRACE
            state = "ended" if ended else "gone"
            reason = "bitis sonrasi bulunamadi" if ended else "bitis oncesi kayboldu (satildi veya kaldirildi)"
            conn.execute("UPDATE eb_track SET last_check=?, checks=checks+1, last_http=404, err_raw=?, state=?, "
                         "close_reason=?, closed_at=?, days_to_close=? WHERE item_id=?",
                         (now_s, err, state, reason, now_s, (now - enrolled).total_seconds() / 86400, row["item_id"]))
        else:
            conn.execute("UPDATE eb_track SET last_check=?, last_http=?, err_raw=? WHERE item_id=?",
                         (now_s, status, err, row["item_id"]))
    # 30 gunu dolan takip biter (sansur)
    if (now - enrolled).days >= TRACK_DAYS:
        conn.execute("UPDATE eb_track SET state='expired' WHERE item_id=? AND state='active'", (row["item_id"],))
    conn.commit()
    return "ok"


def due_cells(conn, cells):
    last = {r[0]: r[1] for r in conn.execute("SELECT cell, last_visit FROM eb_cells")}
    now = datetime.now(timezone.utc)
    out = []
    for c in cells:
        lv = last.get(c["id"])
        if lv is None:
            out.append((0 if c["market"] == "DE" else 1, random.random(), c))
        elif now - datetime.strptime(lv, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc) \
                >= timedelta(hours=c["hours"]):
            out.append((2, random.random(), c))
    return [c for _, _, c in sorted(out, key=lambda x: (x[0], x[1]))]


def calls_today(conn) -> int:
    return conn.execute("SELECT COALESCE(SUM(n),0) FROM health WHERE day=date('now') "
                        "AND stage IN ('eb_arama','eb_takip')").fetchone()[0]


def track_calls_today(conn) -> int:
    return conn.execute("SELECT COALESCE(SUM(n),0) FROM health WHERE day=date('now') AND stage='eb_takip'"
                        ).fetchone()[0]


def run(limit: int | None) -> None:
    conn = connect()
    api = Api(conn)
    cells = build_cells()
    log(f"basladi: {len(cells)} hucre ({len(MARKETS)} ulke)")
    searches = checks = 0
    while True:
        if limit is not None and searches >= limit and checks >= limit:
            break
        if calls_today(conn) >= CALLS_PER_DAY:
            time.sleep(900)
            continue
        did = False
        # once takip (satis olcumu gecikmesin), gunluk payini asmadan
        track_room = int(CALLS_PER_DAY * TRACK_SHARE) - track_calls_today(conn)
        if track_room > 0 and (limit is None or checks < limit):
            for row in due_tracks(conn, min(20, track_room)):
                check_track(api, conn, row)
                checks += 1
                did = True
                time.sleep(random.uniform(*CALL_GAP))
                if limit is not None and checks >= limit:
                    break
        if limit is None or searches < limit:
            todo = due_cells(conn, cells)
            if todo:
                cell = todo[0]
                res = visit_cell(api, conn, cell)
                searches += 1
                did = True
                log(f"{cell['id']}: {res}")
                time.sleep(random.uniform(*CALL_GAP))
            elif limit is not None:
                searches = limit
        if not did:
            if limit is not None:
                break
            time.sleep(600)
    log(f"bitti: arama {searches}, takip {checks}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tek-tur", type=int, metavar="N")
    args = ap.parse_args()
    run(args.tek_tur)
