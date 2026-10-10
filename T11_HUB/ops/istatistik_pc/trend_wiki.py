#!/usr/bin/env python3
"""
Wikipedia ilgi endeksi (ucretsiz, resmi Wikimedia API'leri). PC'de calisir, sunucuyu kullanmaz.

    python trend_wiki.py            -> eslestirme (gerekirse) + goruntulenme guncelle + tablo
    python trend_wiki.py --eslestir -> marka/model -> Wikidata eslestirmesini bastan kur

NE ICIN: Sifir urundeki ilgi, ikinci el talebinin oncu sinyali olabilir. Bu bir ek veridir:
hicbir oneri yalnizca bu sinyalle olusmaz, ikinci el satis verisiyle dogrulanir.
Ilk calismada 365 gunluk gecmis cekilir; oncu-gecikme testi icin haftalarca beklemek gerekmez.

YANLIS ESLESME KORUMASI: "Samba" bir danstir. Aday ancak etiketi marka/model adini iceriyor VE
aciklamasi ayakkabi/giyim/marka/sirket gibi bir kelime iceriyorsa kabul edilir.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import ssl
import time
import unicodedata
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OBS_DIR = ROOT / "T11_HUB" / "ops" / "hetzner_observer"
ARCHIVE = ROOT / "istatistik" / "arsiv.db"
MAP_FILE = ROOT / "istatistik" / "wiki_eslestirme.json"
TABLES = ROOT / "istatistik" / "tablolar"
LOG = ROOT / "istatistik" / "trend.log"

LANGS = ["de", "fr", "it", "nl", "sv", "en"]
UA = "TATANGA-istatistik/1.0 (+https://cssberlin.de; ikinci el pazar arastirmasi)"
HISTORY_DAYS = 365
RELEVANT = re.compile(
    r"shoe|sneaker|boot|footwear|trainer|sandal|clothing|apparel|fashion|jacket|coat|parka|jeans|"
    r"sweater|hoodie|brand|company|manufacturer|retailer|outdoor|sportswear|luxury|handbag|bag|watch|"
    r"corporation|multinational|enterprise|fashion house|design house|garment|textile",
    re.I)
# Kisi sayfasi (tasarimcinin kendisi) marka ilgisini olcmez; olum/haber sicramasi sahte trend uretir
# (Valentino: "Italian fashion designer (1932-2026)"). Muzik/film/universite sayfalari da reddedilir
# (Columbia -> "Columbia Records" eslesmisti).
REJECT = re.compile(
    r"\(born|\(\d{4}\s*[–-]\s*\d{4}\)|\bdesigner\b(?!.*(brand|house|company))|record label|music|"
    r"\bfilm\b|\bband\b|university|\bcity\b|\briver\b|football club|software|television", re.I)
# Belirsiz marka adlari icin Wikidata'da kesin arama
QUERY_OVERRIDE = {
    "Columbia": "Columbia Sportswear", "Valentino": "Valentino fashion house",
    "Alexander McQueen": "Alexander McQueen fashion house", "Ralph Lauren": "Ralph Lauren Corporation",
    "Saint Laurent": "Yves Saint Laurent fashion house", "Dior": "Christian Dior SE",
    "Armani": "Giorgio Armani S.p.A.", "On Running": "On Holding", "Diesel": "Diesel clothing brand",
    "Puma": "Puma SE", "Timberland": "Timberland company", "Salomon": "Salomon Group",
    "Michael Kors": "Michael Kors Holdings", "Barbour": "J. Barbour and Sons", "Mammut": "Mammut Sports Group",
    "Veja": "Veja shoes", "Adidas": "Adidas",
}


def ctx():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30, context=ctx()) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return {}
            if e.code == 429 and attempt < 2:
                time.sleep(5 * (attempt + 1))
                continue
            raise
    return {}


def log(msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def norm(s: str) -> str:
    s = "".join(c for c in unicodedata.normalize("NFD", s.lower()) if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def targets() -> list[dict]:
    cfg = json.load(open(OBS_DIR / "config.json", encoding="utf-8"))
    models = json.load(open(OBS_DIR / "models.json", encoding="utf-8"))
    out = []
    for tier in ("core", "watch", "luxury"):
        for brand in cfg["brands"].get(tier, []):
            out.append({"kind": "marka", "brand": brand, "model": None,
                        "query": QUERY_OVERRIDE.get(brand, brand)})
            if tier == "luxury":
                continue      # luks modeller (canta) ikinci el hedef bandimiz disinda
            for model in models.get(brand, {}).get("models", {}):
                out.append({"kind": "model", "brand": brand, "model": model, "query": f"{brand} {model}"})
    return out


def match_entity(t: dict) -> dict | None:
    q = urllib.parse.urlencode({"action": "wbsearchentities", "search": t["query"], "language": "en",
                                "limit": 7, "format": "json", "type": "item"})
    res = get_json(f"https://www.wikidata.org/w/api.php?{q}")
    brand_n, model_n = norm(t["brand"]), norm(t["model"] or "")
    for cand in res.get("search", []):
        label = norm(cand.get("label", ""))
        desc = cand.get("description", "") or ""
        if not RELEVANT.search(desc) or REJECT.search(desc):
            continue
        if t["kind"] == "marka":
            # "Puma SE", "Timberland LLC", "Christian Dior SE": marka adi etiketin icinde gecmeli
            ok = label == brand_n or label.startswith(brand_n) or f" {brand_n.split()[-1]}" in f" {label}"
        else:
            # model sayfasi: etiket model adini icermeli; marka etikette ya da aciklamada gecmeli
            ok = model_n and model_n in label and (brand_n.split()[0] in label or brand_n.split()[0] in norm(desc))
        if ok:
            return {"qid": cand["id"], "label": cand.get("label"), "description": desc}
    return None


def build_map() -> dict:
    items = targets()
    log(f"eslestirme: {len(items)} hedef Wikidata'da araniyor")
    found, seen = [], set()
    for i, t in enumerate(items, 1):
        m = match_entity(t)
        if m and m["qid"] not in seen:    # ayni sayfa iki kez sayilmasin (Gel-Kayano / Gel-Kayano 14)
            seen.add(m["qid"])
            found.append({**t, **m})
        time.sleep(0.2)
        if i % 50 == 0:
            log(f"  {i}/{len(items)} | bulunan {len(found)}")
    # her varlik icin dillere gore Wikipedia sayfa adlari
    qids = [f["qid"] for f in found]
    sitelinks = {}
    for i in range(0, len(qids), 50):
        q = urllib.parse.urlencode({"action": "wbgetentities", "ids": "|".join(qids[i:i + 50]),
                                    "props": "sitelinks", "format": "json"})
        for qid, ent in get_json(f"https://www.wikidata.org/w/api.php?{q}").get("entities", {}).items():
            links = ent.get("sitelinks", {})
            sitelinks[qid] = {lang: links[f"{lang}wiki"]["title"] for lang in LANGS if f"{lang}wiki" in links}
        time.sleep(0.3)
    for f in found:
        f["pages"] = sitelinks.get(f["qid"], {})
    found = [f for f in found if f["pages"]]
    data = {"olusturma": time.strftime("%Y-%m-%d"), "varliklar": found}
    MAP_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    kinds = {"marka": 0, "model": 0}
    for f in found:
        kinds[f["kind"]] += 1
    log(f"eslestirme bitti: {kinds['marka']} marka, {kinds['model']} model Wikipedia sayfasiyla eslesti")
    return data


def ensure_tables(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS wiki_entities (
            qid TEXT PRIMARY KEY, kind TEXT, brand TEXT, model TEXT, label TEXT, description TEXT);
        CREATE TABLE IF NOT EXISTS wiki_views (
            qid TEXT, lang TEXT, day TEXT, views INTEGER, PRIMARY KEY (qid, lang, day));
    """)


def update_views(data: dict) -> int:
    conn = sqlite3.connect(ARCHIVE)
    ensure_tables(conn)
    # Eslestirmeden cikan (yanlis) varliklarin verisi de silinir: eski hatali sinyal kalmasin
    keep = {e["qid"] for e in data["varliklar"]}
    stale = [r[0] for r in conn.execute("SELECT qid FROM wiki_entities") if r[0] not in keep]
    for qid in stale:
        conn.execute("DELETE FROM wiki_views WHERE qid=?", (qid,))
        conn.execute("DELETE FROM wiki_entities WHERE qid=?", (qid,))
    if stale:
        log(f"eslestirmeden cikan {len(stale)} varligin verisi silindi")
    conn.commit()
    end = date.today() - timedelta(days=1)
    added = 0
    for ent in data["varliklar"]:
        conn.execute("INSERT OR REPLACE INTO wiki_entities VALUES (?,?,?,?,?,?)",
                     (ent["qid"], ent["kind"], ent["brand"], ent["model"], ent["label"], ent["description"]))
        for lang, title in ent["pages"].items():
            last = conn.execute("SELECT MAX(day) FROM wiki_views WHERE qid=? AND lang=?",
                                (ent["qid"], lang)).fetchone()[0]
            start = (date.fromisoformat(last) + timedelta(days=1)) if last else end - timedelta(days=HISTORY_DAYS)
            if start > end:
                continue
            art = urllib.parse.quote(title.replace(" ", "_"), safe="")
            url = (f"https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/{lang}.wikipedia/"
                   f"all-access/user/{art}/daily/{start:%Y%m%d}00/{end:%Y%m%d}00")
            items = get_json(url).get("items", [])
            rows = [(ent["qid"], lang, f"{it['timestamp'][:4]}-{it['timestamp'][4:6]}-{it['timestamp'][6:8]}",
                     int(it["views"])) for it in items]
            conn.executemany("INSERT OR REPLACE INTO wiki_views VALUES (?,?,?,?)", rows)
            added += len(rows)
            time.sleep(0.1)
        conn.commit()
    conn.close()
    return added


def write_table() -> None:
    """Haftalik ilgi (tum diller toplami), son 12 hafta ve 4 haftalik degisim. Excel icin ; ve virgul."""
    conn = sqlite3.connect(ARCHIVE)
    rows = conn.execute("""
        SELECT e.kind, e.brand, COALESCE(e.model,'') model, strftime('%Y-%W', v.day) hafta, SUM(v.views) n
        FROM wiki_views v JOIN wiki_entities e ON e.qid = v.qid
        WHERE v.day >= date('now', '-84 days') GROUP BY 1,2,3,4 ORDER BY 2,3,4""").fetchall()
    conn.close()
    series: dict[tuple, list[tuple[str, int]]] = {}
    for kind, brand, model, week, n in rows:
        series.setdefault((kind, brand, model), []).append((week, n))
    TABLES.mkdir(parents=True, exist_ok=True)
    with open(TABLES / "trend_wikipedia.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["tur", "marka", "model", "son_4_hafta", "onceki_4_hafta", "degisim_yuzde"])
        out = []
        for (kind, brand, model), s in series.items():
            vals = [n for _, n in s]
            last4, prev4 = sum(vals[-4:]), sum(vals[-8:-4])
            change = round(100 * (last4 - prev4) / prev4, 1) if prev4 else None
            out.append((kind, brand, model, last4, prev4, change))
        out.sort(key=lambda r: -(r[5] if r[5] is not None else -999))
        for r in out:
            w.writerow([str(x).replace(".", ",") if isinstance(x, float) else x for x in r])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--eslestir", action="store_true")
    args = ap.parse_args()
    if args.eslestir or not MAP_FILE.exists():
        data = build_map()
    else:
        data = json.loads(MAP_FILE.read_text(encoding="utf-8"))
    added = update_views(data)
    write_table()
    log(f"goruntulenme: {added} yeni gunluk kayit | tablo: {TABLES / 'trend_wikipedia.csv'}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        log(f"HATA: {type(exc).__name__}: {exc}")
        raise SystemExit(1)
