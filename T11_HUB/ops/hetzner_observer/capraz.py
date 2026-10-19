#!/usr/bin/env python3
"""
Capraz platform karlilik (PC'de, arsivler uzerinde). Karar vermez; her alis ilanini tum satis yonleriyle yan yana koyar.

    python capraz.py [--arsiv <arsiv.db>] [--alis <alis_arsiv.db>] [--csv <klasor>]

ALIS ILANLARI: Kleinanzeigen (DE), eBay (7 AB ulkesi, satici ulkesi), Sellpy (DE).
SATIS TAHMINI: YALNIZCA GERCEK SATISLARDAN. Bugun olculen satis Vinted'de (7 ulke). eBay satis takibi sonuc
  verdikce eBay ulkeleri ayni tabloya satis yonu olarak eklenecek; o zamana kadar eBay ILAN fiyati satis sayilmaz.
  Hiyerarsi: marka+model (en az 5 satis) -> marka+seri (8; Air Max, Originals, WIP, Gel...) -> marka+tur (8)
  -> marka+kategori (20).
  ILAN FIYATI KALIBRASYONU KULLANILMAZ: satis/ilan orani markaya gore 0,48-1,25 arasi degisiyor (2026-10-13 olculdu,
  16 grup, P25-P75 0,72-0,97); tek oran bazi markalarda satis fiyatini %50'ye kadar yanlis tahmin ettirir.
  SIRALAMA 7 ulkenin HAVUZUYLA yapilir (DE tabani). Ulke ancak KENDI satisi yeterliyse ayrica gosterilir;
  havuz tahmini ulke carpaniyla sisirilip "en iyi ulke" SECILMEZ (en yuksek gurultuyu secmek = kazananin laneti).
  KONDISYON: once ayni kondisyonda gercek satis aranir. Yoksa urun cok_iyi satis fiyatiyla hesaplanir
  (YUKARI carpan uygulanmaz: ilan fiyatindan cikan 2x etiketli carpani satista dogrulanmadi) ve isaretlenir.
KONDISYON (3 kademe, tutucu): Neu mit Etikett / eBay 1000 -> yeni_etiketli; Neu / eBay 1500 -> yeni;
  Sehr gut / eBay 2990 / Sellpy Sehr gut VE Neuwertig -> cok_iyi (Neuwertig'i yukari almak kari sisirirdi).
MALIYET: maliyet.json (kaynaklariyla). Kleinanzeigen elden teslimde kargo/koruma 0 (yol masrafi haric, isaretli).
  eBay ilaninda DE'ye kargo ucreti yoksa (gondermiyor) alinmaz.
PUAN: beklenen 30 gun kar = 30 gunde satilma olasiligi (motor.py) x net kar. En iyi satis ulkesi secilir.
ISARETLER (eleme degil): kusur kelimesi/kaydi, VB (pazarlik), elden teslim, yeni satici hesabi, teklif verilebilir,
  dusuk satici puani, Neuwertig, az satis (n<10), on sonuc (kontrol gecikmesi).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sqlite3
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
import analyze as A  # noqa: E402
import motor as M  # noqa: E402

ROOT = os.path.abspath(os.path.join(BASE_DIR, "..", "..", "..", "istatistik"))
VINTED_COUNTRIES = ("DE", "AT", "FR", "BE", "NL", "IT", "SE")
# seviye basina en az gercek satis: karisik turden az satisla tahmin yapilmaz
MIN_SALES = {"marka·model": 5, "marka·seri": 8, "marka·tur": 8, "marka·kategori": 20}
MIN_PRICE = 5.0
CAT_MAP = {"hoodies": "oberteile"}            # Vinted hucre kategorisi -> ortak kategori
KA_COND = {"neu mit etikett": "yeni_etiketli", "neu": "yeni", "sehr gut": "cok_iyi"}
EB_COND = {"1000": "yeni_etiketli", "1500": "yeni", "2990": "cok_iyi"}
SP_COND = {"Neuwertig": "cok_iyi", "Sehr gut": "cok_iyi"}


# Tur -> ait oldugu kategori(ler). polar / esofman hem ust giyim hem ceket olabilir.
TYPE_CAT = {
    **{t: {"jacken"} for t in ("kaz_tuyu", "kislik", "deri", "kayak", "parka", "yagmurluk", "softshell",
                               "ruzgarlik", "yelek", "kaban", "bomber", "kot_ceket")},
    **{t: {"oberteile"} for t in ("kapusonlu", "sweatshirt", "triko")},
    "polar": {"jacken", "oberteile"}, "esofman": {"jacken", "oberteile"},
    "kot_pantolon": {"jeans"},
    **{t: {"schuhe"} for t in ("sneaker", "bot", "topuklu", "babet", "loafer", "klasik", "espadril", "terlik",
                               "kosu", "trekking", "sandalet", "krampon")},
}
# Basliktaki genel kategori kelimeleri (cok dilli). Tur taninmasa da kategori teyit edilebilir.
CAT_WORDS = {
    "jacken": re.compile(r"(jacke|jacket|veste|giacca|giubbott|jas\b|jacka|parka|mantel|coat|manteau|cappotto|"
                         r"weste|gilet|blouson|anorak|chaqueta|abrigo)"),
    "schuhe": re.compile(r"(schuh|shoe|sneaker|chaussure|scarpe|schoen|skor|boot|stiefel|sandal|trainer|zapat)"),
    "oberteile": re.compile(r"(pullover|pulli|hoodie|sweat|strick|knit|maglion|felpa|\bpull\b|trui|troja|"
                            r"cardigan|jumper|jersey)"),
    "jeans": re.compile(r"(jeans|\bjean\b|denim)"),
}


def category_check(cat: str, typ: str | None, title: str, structured: bool) -> str:
    """'ok' | 'baska' (turu baska kategoriye ait) | 'teyitsiz' (ne tur ne kategori kelimesi)."""
    if typ and typ in TYPE_CAT:
        return "ok" if cat in TYPE_CAT[typ] else "baska"
    if structured:
        return "ok"
    return "ok" if CAT_WORDS.get(cat) and CAT_WORDS[cat].search(A.norm_text(title or "")) else "teyitsiz"


# KULLANICI KARARLARI 2026-10-16 (siralama disi = silinmez, isaretiyle listenin sonuna iner):
#  - Alis fiyati < 5 EUR: Kleinanzeigen/Vinted'de pazarlik/yem fiyati (gercek fiyat degil).
#  - Aciklamada "satin almadan once yaz / kaufen nicht" kalibi: ilan farkli amacla konmus.
#  - Yalniz marka+kategori karsilastirmasi: zayif (farkli urun turleri karisik) -> en karli siralamasina girmez.
BAIT_PRICE = 5.0
LOW_PRICE = 10.0
CONTACT_RE = re.compile(
    r"(vor dem kauf|erst anschreiben|bitte (vorher )?(an)?schreiben|nicht (direkt |sofort )?kaufen|vorher (melden|fragen|kontakt)|"
    r"contacte[rz]?[- ]moi avant|me contacter avant|ne pas acheter|avant (tout )?achat|contact(ez)? (me )?before|"
    r"message (me )?before|don.?t buy|do not buy|non acquistare|contattatemi prima|scrivetemi prima|eerst (contact|bericht)|"
    r"niet (direct )?kopen|napisz przed|pytaj przed|nie kupuj|kontakt przed|prix (a|à) discuter|preis (vb|verhandelbar)|"
    r"zum verhandeln)", re.I)
STRONG_LEVELS = ("marka·model", "marka·seri", "marka·tur")


def quantile(vals: list[float], q: float) -> float:
    v = sorted(vals)
    pos = (len(v) - 1) * q
    lo, hi = int(pos), min(int(pos) + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (pos - lo)


# Basliktaki cocuk isareti: eBay'de beden alani yok, beden kurali tek basina yetmiyor
# (2026-10-16: "Jeansjacke Levis For Girls Gr. S" karli listeye girdi). Cocuk beden numaralari 104-176.
CHILD_TITLE_RE = re.compile(
    r"\b(kinder\w*|kids?|girls?|boys?|jungen|madchen|mädchen|maedchen|baby|babies|enfants?|fille|garcon|garçon|"
    r"bambin[oai]|ragazz[oai]|junior|teen|youth|kinderjacke|kindermantel)\b|"
    r"\b(gr\.?|größe|grosse|size|taille|taglia)\s*(104|110|116|122|128|134|140|146|152|158|164|170|176)\b",
    re.I)


def costs() -> dict:
    raw = json.load(open(os.path.join(BASE_DIR, "maliyet.json"), encoding="utf-8"))
    return {k: v["deger"] for k, v in raw.items() if not k.startswith("_")}


def keys_for(brand: str, cat: str | None, model: str | None, typ: str | None, line: str | None = None) -> list[tuple]:
    b = brand.lower()
    out = []
    if model:
        out.append(("marka·model", b, model.lower()))
    if line:
        out.append(("marka·seri", b, line.lower()))
    if typ:
        out.append(("marka·tur", b, typ))
    if cat:
        out.append(("marka·kategori", b, cat))
    return out


class SellRef:
    """Gercek Vinted satislari -> grup x (ulke, kondisyon) fiyat referansi."""

    def __init__(self, conn, matcher, rates, cond_f, market_f, until: str | None = None):
        """until: yalniz bu zamandan ONCE kapanan satislar (geritest.py: gelecegi gormeden sinav)."""
        self.cond_f, self.market_f = cond_f, market_f
        # ref[grup][(ulke|'*', kondisyon|'*')] -> fiyatlar. '*' ulke: DE tabanina cevrilmis havuz;
        # '*' kondisyon: cok_iyi tabanina cevrilmis (yalnizca ASAGI cevirme: etiketli satis / 2.0 gibi).
        self.ref: dict[tuple, dict[tuple, list[float]]] = defaultdict(lambda: defaultdict(list))
        n = 0
        sql = ("SELECT cell, title, size, condition, country, COALESCE(final_price, price) p, "
               "COALESCE(currency,'EUR') cur FROM listings WHERE state='sold'")
        for r in conn.execute(sql + (" AND closed_at < ?" if until else ""), (until,) if until else ()):
            brand, cat, _ = (r["cell"].split("|") + ["", ""])[:3]
            cat = None if cat.startswith("model:") else CAT_MAP.get(cat, cat)
            if A.is_child_size(r["size"], cat or ""):
                continue
            tier = A.norm_condition(r["condition"])
            rate = rates.get(r["cur"]) or 0
            if not tier or not rate or not r["p"]:
                continue
            price = r["p"] / rate
            if price < MIN_PRICE:
                continue
            model, line = matcher.match(brand, r["title"] or "")
            typ = A.match_type(A.norm_text(r["title"] or ""))
            cc = r["country"]
            pooled = price / self.f(market_f, cc)
            for k in keys_for(brand, cat, model, typ, line):
                g = self.ref[k]
                g[(cc, tier)].append(price)
                g[("*", tier)].append(pooled)
                g[(cc, "*")].append(price / self.f(cond_f, tier))
                g[("*", "*")].append(pooled / self.f(cond_f, tier))
            n += 1
        self.n_sales = n

    @staticmethod
    def f(table: dict, key) -> float:
        return (table.get(key) or (1.0, 0))[0] or 1.0

    def estimate(self, keys: list[tuple], tier: str, country: str = "*"):
        """
        (gercek satis fiyatlari listesi, satis sayisi, seviye, kondisyon kapsami) veya None.
        country='*' -> 7 ulke havuzu (DE tabani). Ayni kondisyon yoksa cok_iyi tabani, YUKARI carpan yok.
        """
        for k in keys:
            g = self.ref.get(k)
            if not g:
                continue
            need = MIN_SALES[k[0]]
            same = g.get((country, tier), [])
            if len(same) >= need:
                return same, len(same), k[0], "ayni kondisyon"
            # daha iyi kondisyondaki urun: kendi kademesinde satis yoksa cok_iyi GERCEK satislari (yukari carpan yok).
            # Tutarlilik: yeni urun hicbir zaman ayni gruptaki cok_iyi satistan dusuk degerlenmez.
            if tier != "cok_iyi":
                ok = g.get((country, "cok_iyi"), [])
                if len(ok) >= need:
                    return ok, len(ok), k[0], "cok_iyi satislari (tutucu)"
            base = g.get((country, "*"), [])
            if len(base) >= need:
                # cok_iyi tabani; urun daha iyi kondisyondaysa bile yukari cevrilmez (tutucu)
                return base, len(base), k[0], "cok_iyi tabani (tutucu)"
        return None


def col(row, name):
    return row[name] if name in row.keys() else None


def load_buys(alis, matcher, rates, c) -> list[dict]:
    out = []
    now = datetime.utcnow()
    # Kleinanzeigen
    for r in alis.execute("SELECT * FROM ka_ads WHERE detail_status='ok' AND COALESCE(marke_ok,1)=1 "
                          "AND detail_price >= ?", (MIN_PRICE,)):
        tier = KA_COND.get((r["zustand"] or "").strip().lower())
        if not tier or A.is_child_size(r["groesse"], r["cat"]):
            continue
        price, flags = r["detail_price"], []
        if r["shipping"] == "versand" and r["ship_cost"] is not None:
            cost = price + r["ship_cost"] + c["ka_koruma_sabit"] + c["ka_koruma_oran"] * price
        else:
            cost = price + c["ka_abholung_ucret"]
            flags.append(f"elden teslim PLZ {r['plz']}")
        if r["price_type"] == "vb":
            flags.append("VB pazarlik")
        if r["defect_words"]:
            flags.append(f"kusur: {r['defect_words']}")
        if r["seller_since"] and r["seller_since"] > (now - timedelta(days=90)).strftime("%Y-%m-%d"):
            flags.append("yeni satici hesabi")
        model, line = matcher.match(r["brand"], r["title"] or "")
        out.append({"platform": "Kleinanzeigen", "sid": "KA-" + r["adid"], "img": col(r, "image_url"),
                    "line": line, "country": "DE", "url": r["url"], "brand": r["brand"],
                    "cat": r["cat"], "gender": r["gender"], "title": r["title"], "model": model,
                    "type": A.match_type(A.norm_text(r["title"] or "")), "tier": tier, "size": r["groesse"],
                    "price": price, "cost": cost, "flags": flags, "structured": False, "descr": r["descr"]})
    # eBay: yalnizca sabit fiyatli (artirmanin fiyati nihai degil), DE'ye kargo ucreti bilinen
    for r in alis.execute("SELECT * FROM eb_items WHERE title_brand=1 AND buying LIKE '%FIXED_PRICE%' "
                          "AND ship_cost IS NOT NULL AND price IS NOT NULL"):
        tier = EB_COND.get(r["condition_id"])
        rate = rates.get(r["currency"] or "EUR") or 0
        if not tier or not rate:
            continue
        price = r["price"] / rate
        if price < MIN_PRICE:
            continue
        flags = []
        if "BEST_OFFER" in (r["buying"] or ""):
            flags.append("teklif verilebilir")
        # Satis gecmisi olmayan satici (puan 0 / degerlendirme yok): replika riski. 2026-10-16: Estonya'dan
        # puansiz satici "Arc'teryx Beta LT"yi ayni ilanla 7 adet satiyordu (gercek fiyatin cok altinda).
        if (r["seller_score"] is not None and r["seller_score"] <= 0) or r["seller_pct"] == 0:
            flags.append("REPLIKA RISKI: saticinin satis gecmisi yok")
        elif r["seller_pct"] is not None and r["seller_pct"] < 97:
            flags.append(f"satici puani %{r['seller_pct']:.0f}")
        model, line = matcher.match(r["brand"], r["title"] or "")
        out.append({"platform": "eBay", "sid": "EB-" + r["item_id"].replace("|", "-"), "img": col(r, "image_url"),
                    "line": line, "country": r["country"], "url": r["url"], "brand": r["brand"],
                    "cat": r["cat"], "gender": r["gender"], "title": r["title"], "model": model,
                    "type": A.match_type(A.norm_text(r["title"] or "")), "tier": tier, "size": None,
                    "price": price, "cost": price * (1 + c["ebay_alici_ucret_oran"]) + r["ship_cost"] / rate,
                    "flags": flags, "structured": False})
    # Sellpy
    for r in alis.execute("SELECT * FROM sp_items WHERE brand_ok=1 AND for_sale=1 AND reserved=0 AND price >= ?",
                          (MIN_PRICE,)):
        tier = SP_COND.get(r["condition"])
        if not tier or A.is_child_size(r["size"], r["cat"]):
            continue
        flags = []
        if r["condition"] == "Neuwertig":
            flags.append("Neuwertig (cok_iyi sayildi)")
        if r["defect_n"]:
            flags.append(f"kusur: {r['defects']}")
        title = f"{r['brand']} {r['type'] or ''}"
        out.append({"platform": "Sellpy", "sid": "SP-" + r["object_id"], "img": col(r, "image_url"),
                    "line": None, "country": "DE", "url": r["url"], "brand": r["brand_q"], "cat": r["cat"],
                    "gender": r["gender"], "title": title, "model": None,
                    "type": A.match_type(A.norm_text(r["type"] or "")), "tier": tier, "size": r["size"],
                    "price": r["price"], "cost": r["price"] + c["sellpy_kargo"], "flags": flags, "structured": True})
    return out


DB_OUT = os.path.join(ROOT, "capraz.db")
KEEP_RUNS = 10
# 'Cok karli' (Nokta Atis ana ekrani): kullanici karari 2026-10-16 -> TUTUCU net kar >= 20 EUR VE tahmin
# KESIN marka+model eslesmesinden (ayni marka ve modelin gercek satislari). Tur/seri/kategori ortalamasi girmez.
COK_KARLI = {"net_min": 20.0, "seviye": "marka·model"}


def save_db(rows: list[dict], n_sales: int, n_buys: int, stats: dict, late: bool) -> str:
    """
    Her calisma bir TARAMA kimligi alir (TRM-YYYYMMDD-HHMM). TATANGA 'Nokta Atis' ekrani bu tabloyu SALT OKUR.
    Son 10 tarama tutulur.
    """
    from datetime import datetime as _dt, timezone as _tz
    run_id = "TRM-" + _dt.now(_tz.utc).strftime("%Y%m%d-%H%M")
    db = sqlite3.connect(DB_OUT)
    db.executescript("""
    CREATE TABLE IF NOT EXISTS taramalar (run_id TEXT PRIMARY KEY, ts TEXT, alis_ilan INTEGER, tahminli INTEGER,
        karli INTEGER, cok_karli INTEGER, vinted_satis INTEGER, durum TEXT, platform_json TEXT);
    CREATE TABLE IF NOT EXISTS firsatlar (run_id TEXT, firsat_id TEXT, platform TEXT, ulke TEXT, marka TEXT,
        kategori TEXT, cinsiyet TEXT, baslik TEXT, model TEXT, seri TEXT, tur TEXT, kondisyon TEXT, beden TEXT,
        fiyat REAL, alis_toplam REAL, satis_p25 REAL, satis_medyan REAL, net_kar_tutucu REAL, net_kar_medyan REAL,
        p30 REAL, beklenen_kar_30g REAL, tahmin_seviye TEXT, tahmin_kapsam TEXT, satis_n INTEGER,
        ulke_net TEXT, isaretler TEXT, durum TEXT, url TEXT, gorsel TEXT, kanit_json TEXT, cok_karli INTEGER,
        siralama_disi INTEGER DEFAULT 0, PRIMARY KEY (run_id, firsat_id));
    CREATE INDEX IF NOT EXISTS ix_firsat_run ON firsatlar (run_id, cok_karli, beklenen_kar_30g);
    """)
    def is_top(r):
        return (r["net_kar_tutucu"] >= COK_KARLI["net_min"] and r["tahmin_seviye"] == COK_KARLI["seviye"]
                and "supheli" not in r["isaretler"] and "REPLIKA" not in r["isaretler"] and not r["siralama_disi"])
    if "siralama_disi" not in {x[1] for x in db.execute("PRAGMA table_info(firsatlar)")}:
        db.execute("ALTER TABLE firsatlar ADD COLUMN siralama_disi INTEGER DEFAULT 0")
    karli = sum(1 for r in rows if r["net_kar_tutucu"] > 0 and not r["siralama_disi"])
    top = sum(1 for r in rows if is_top(r))
    db.execute("INSERT OR REPLACE INTO taramalar VALUES (?,?,?,?,?,?,?,?,?)",
               (run_id, _dt.now(_tz.utc).strftime("%Y-%m-%d %H:%M:%S"), n_buys, len(rows), karli, top, n_sales,
                "on sonuc (kontrol gecikmesi)" if late else "olculdu",
                json.dumps({p: dict(v) for p, v in stats.items()}, ensure_ascii=False)))
    for r in rows:
        db.execute("INSERT OR REPLACE INTO firsatlar VALUES (" + ",".join("?" * 32) + ")", (
            run_id, r["firsat_id"], r["platform"], r["ulke"], r["marka"], r["kategori"], r["cinsiyet"], r["baslik"],
            r["model"], r["seri"], r["tur"], r["kondisyon"], r["beden"], r["fiyat"], r["alis_toplam"], r["satis_p25"],
            r["satis_medyan"], r["net_kar_tutucu"], r["net_kar_medyan"], r["p30"], r["beklenen_kar_30g"],
            r["tahmin_seviye"], r["tahmin_kapsam"], r["satis_n"], r["ulke_net_kendi_verisi"], r["isaretler"],
            r["durum"], r["url"], r["gorsel"], json.dumps(r["kanit"][:60]), 1 if is_top(r) else 0,
            r["siralama_disi"]))
    old = [x[0] for x in db.execute("SELECT run_id FROM taramalar ORDER BY run_id DESC").fetchall()[KEEP_RUNS:]]
    for o in old:
        db.execute("DELETE FROM firsatlar WHERE run_id=?", (o,))
        db.execute("DELETE FROM taramalar WHERE run_id=?", (o,))
    db.commit()
    db.close()
    print(f"TARAMA {run_id}: {len(rows)} degerleme, {karli} karli, {top} cok karli -> {DB_OUT}")
    return run_id


class Engine:
    """Gercek satis zekasi: bir kez kurulur, her alis ilanini ayni kurallarla degerlendirir (Nokta Atis + TATANGA urunleri)."""

    def __init__(self, conn):
        self.conn = conn
        matcher = A.ModelMatcher()
        rates = A.fx_rates(conn)
        c = costs()
        samples, _ = A.samples(conn, matcher, rates)
        cond_f, market_f, _ = A.factors(samples)
        ref = SellRef(conn, matcher, rates, cond_f, market_f)
        from saglama import FAIL, run_checks
        late = any(code == "T14" and lvl == FAIL for lvl, code, _ in run_checks(conn))
        prob = {(r["seviye"], r["grup"].lower()): r for r in M.build(M.load(conn, matcher, rates))}
        self.matcher, self.rates, self.c, self.ref, self.late, self.prob = matcher, rates, c, ref, late, prob
        # SIFIR URUN TALEBI (sifir_talep.py): yalniz BILGI; ikinci el satis fiyatina girmez.
        self.sifir = {}
        try:
            sdb = sqlite3.connect(os.path.join(ROOT, "capraz.db"))
            for r in sdb.execute("SELECT marka, seviye, grup, kondisyon, ilan, haftalik_talep, guven FROM sifir_talep"):
                key = (r[0], r[1], str(r[2]).lower())
                cur = self.sifir.get(key)
                if cur is None or r[5] > cur[0]:
                    self.sifir[key] = (r[5], r[4], r[3], r[6])
            sdb.close()
        except sqlite3.OperationalError:
            pass

    def sifir_talep(self, b) -> tuple | None:
        """Ayni marka + ayni model/seri/tur icin magaza (sifir urun) talebi: (haftalik, ilan, kondisyon, guven)."""
        brand = (b["brand"] or "").lower()
        for level, key in (("model", b["model"]), ("seri", b["line"]), ("tur", b["type"])):
            if key:
                hit = self.sifir.get((brand, level, str(key).lower()))
                if hit:
                    return hit
        return None

    def p30(self, b) -> tuple[float | None, str | None]:
        brand = b["brand"].lower()
        cands = []
        if b["model"]:
            cands.append(("marka·model", f"{brand} · {b['model'].lower()}"))
        if b["type"]:
            cands.append(("marka·kategori·tip", f"{brand} · {b['cat']} · {b['type']}"))
        cands += [("marka·kategori", f"{brand} · {b['cat']}"), ("kategori", b["cat"])]
        for lv, g in cands:
            r = self.prob.get((lv, g))
            if r:
                return r["p30_duzeltilmis"], lv
        return None, None

    def evaluate(self, b, stats) -> dict | None:
        ref, c, late = self.ref, self.c, self.late
        stats[b["platform"]]["ilan"] += 1
        chk = category_check(b["cat"], b["type"], b["title"], b["structured"])
        if chk == "baska":
            stats[b["platform"]]["kategori_uyusmaz"] += 1
            return None
        keys = keys_for(b["brand"], b["cat"] if chk == "ok" else None, b["model"], b["type"], b["line"])
        prob30, plevel = self.p30(b)
        sell_cost = lambda sell: c["paketleme"] + (c["iade_payi_oran"] + c["satis_komisyonu_oran"]) * sell \
            + c["giden_kargo"]
        est = ref.estimate(keys, b["tier"], "*")
        if not est:
            stats[b["platform"]]["tahmin_yok"] += 1
            return None
        vals, n, level, scope = est
        kanit = sorted(round(v) for v in vals)
        sell, low = statistics.median(vals), quantile(vals, 0.25)
        spread = (quantile(vals, 0.75) - low) / sell if sell else 0
        net = sell - b["cost"] - sell_cost(sell)
        net_low = low - b["cost"] - sell_cost(low)
        # SIRALAMA TUTUCU: satislarin alt ceyregi (P25) ile; medyan bilgi olarak gosterilir
        best = {"sell": sell, "low": low, "spread": spread, "n": n, "level": level, "scope": scope,
                "net": net, "net_low": net_low, "exp": net_low * prob30 if prob30 is not None else None}
        per_country = {}
        for cc in VINTED_COUNTRIES:
            e = ref.estimate(keys, b["tier"], cc)          # yalnizca o ulkenin KENDI satislari
            if e:
                m = statistics.median(e[0])
                per_country[cc] = (m - b["cost"] - sell_cost(m), e[1])
        stats[b["platform"]]["tahminli"] += 1
        flags = list(b["flags"])
        disi = []          # siralama disi nedenleri
        if b["price"] < BAIT_PRICE:
            disi.append(f"PAZARLIK/YEM FIYATI ({b['price']:.2f} EUR < {BAIT_PRICE:.0f}): gercek fiyat degil")
        elif b["price"] < LOW_PRICE:
            flags.append(f"dusuk fiyat ({b['price']:.2f} EUR): pazarlik olabilir")
        if CONTACT_RE.search(b.get("descr") or ""):
            disi.append(f"ACIKLAMA: '{CONTACT_RE.search(b['descr']).group(0)}' -> farkli amacli ilan")
        if best["level"] not in STRONG_LEVELS:
            disi.append("ZAYIF KARSILASTIRMA: yalniz marka+kategori (farkli urun turleri karisik)")
        st = self.sifir_talep(b)
        if st:
            flags.append(f"sifir urun talebi: haftada {st[0]:.1f} adet ({st[1]} magaza ilani, {st[2]}, {st[3]})")
        flags = disi + flags
        if best["n"] < 10:
            flags.append(f"az satis (n={best['n']})")
        if best["scope"] != "ayni kondisyon" and b["tier"] != "cok_iyi":  # cok_iyi satislari veya tabani
            flags.append("ayni kondisyonda satis yok: cok_iyi fiyatiyla hesaplandi")
        if best["net_low"] > 3 * b["cost"] or best["low"] < MIN_PRICE:
            flags.append("supheli: fark asiri buyuk, veriyi kontrol et")
        if best["spread"] > 0.6:
            flags.append(f"satis fiyatlari dagınık (P25 {best['low']:.0f} / medyan {best['sell']:.0f})")
        if best["net_low"] > 0:
            stats[b["platform"]]["kar>0"] += 1
        return {
            "platform": b["platform"], "ulke": b["country"], "marka": b["brand"], "kategori": b["cat"],
            "cinsiyet": b["gender"], "baslik": (b["title"] or "")[:80], "model": b["model"], "seri": b["line"],
            "tur": b["type"],
            "kondisyon": b["tier"], "beden": b["size"], "fiyat": b["price"], "alis_toplam": b["cost"],
            "satis_yonu": "Vinted (7 ulke havuzu)", "satis_p25": best["low"], "satis_medyan": best["sell"],
            "net_kar_tutucu": best["net_low"], "net_kar_medyan": best["net"],
            "p30": prob30, "beklenen_kar_30g": best["exp"], "tahmin_seviye": best["level"],
            "tahmin_kapsam": best["scope"], "satis_n": best["n"],
            "ulke_net_kendi_verisi": " ".join(f"{k}:{v[0]:+.0f}(n{v[1]})" for k, v in
                                              sorted(per_country.items(), key=lambda x: -x[1][0])),
            "isaretler": "; ".join(flags), "durum": "on sonuc (kontrol gecikmesi)" if late else "olculdu",
            "url": b["url"], "firsat_id": b["sid"], "gorsel": b["img"], "kanit": kanit,
            "siralama_disi": 1 if disi else 0,
        }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arsiv", default=os.path.join(ROOT, "arsiv.db"))
    ap.add_argument("--alis", default=os.path.join(ROOT, "alis_arsiv.db"))
    ap.add_argument("--csv", metavar="KLASOR")
    args = ap.parse_args()

    conn = A.connect(args.arsiv)
    alis = sqlite3.connect(args.alis)
    alis.row_factory = sqlite3.Row
    eng = Engine(conn)
    matcher, rates, c, ref, late = eng.matcher, eng.rates, eng.c, eng.ref, eng.late

    buys = [b for b in load_buys(alis, matcher, rates, c) if not CHILD_TITLE_RE.search(b["title"] or "")]
    rows, stats = [], defaultdict(lambda: defaultdict(int))
    for b in buys:
        r = eng.evaluate(b, stats)
        if r:
            rows.append(r)

    def rank(r):
        v = r["beklenen_kar_30g"] if r["beklenen_kar_30g"] is not None else r["net_kar_tutucu"] * 0.1
        return v - (1e6 if r["siralama_disi"] else 0)

    rows.sort(key=rank, reverse=True)
    print(f"CAPRAZ: Vinted gercek satis {ref.n_sales} (referans) | alis ilani {len(buys)}"
          + (" | UYARI: kontrol gecikmesi, sonuclar on sonuc" if late else ""))
    for p, s in stats.items():
        print(f"  {p:14} ilan {s['ilan']:>6} | kategori uyusmaz {s['kategori_uyusmaz']:>5} | tahmin edilebilen "
              f"{s['tahminli']:>6} | tutucu net kar > 0: {s['kar>0']:>5}")
    clean = [r for r in rows if not r["isaretler"].count("supheli")]
    print(f"\nEN IYI 15 (beklenen 30 gun kar = p30 x TUTUCU net; satis = gercek satislarin P25 / medyani; supheli haric)")
    print(f"{'platform':13}{'ulke':5}{'marka':16}{'tur/model':18}{'kond':8}{'alis':>7}{'P25/med':>10}{'net':>7}"
          f"{'p30':>5}{'bekl':>6}  seviye (kondisyon) n | kendi verisi olan ulkeler")
    for r in clean[:15]:
        print(f"{r['platform']:13}{r['ulke']:5}{r['marka'][:15]:16}{(r['model'] or r['tur'] or '-')[:17]:18}"
              f"{r['kondisyon'][:7]:8}{r['alis_toplam']:>6.0f}€{r['satis_p25']:>5.0f}/{r['satis_medyan']:<4.0f}"
              f"{r['net_kar_tutucu']:>6.0f}€"
              f"{(r['p30'] or 0)*100:>4.0f}%{(r['beklenen_kar_30g'] or 0):>5.0f}€  "
              f"{r['tahmin_seviye']} ({r['tahmin_kapsam']}) n={r['satis_n']} | ulke: {r['ulke_net_kendi_verisi'] or '-'}")
    save_db(rows, ref.n_sales, len(buys), stats, late)
    if args.csv:
        os.makedirs(args.csv, exist_ok=True)
        cols = [k for k in (rows[0].keys() if rows else []) if k != "kanit"]  # siralama_disi dahil
        with open(os.path.join(args.csv, "capraz_firsatlar.csv"), "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.writer(fh, delimiter=";")
            w.writerow(cols)
            for r in rows:
                w.writerow([str(round(v * 100, 1) if k == "p30" else round(v, 2)).replace(".", ",")
                            if isinstance(v, float) else ("" if v is None else v) for k, v in r.items() if k != "kanit"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
