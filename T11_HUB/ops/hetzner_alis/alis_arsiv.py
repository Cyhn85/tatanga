#!/usr/bin/env python3
"""
Alis verisi arsiv protokolu (sunucu tarafi). Gozlemcinin arsiv.py'si ile ayni kural:
ONAYLANMAYAN VERI SILINMEZ. PC paketi ceker, her satirin arsivde oldugunu dogrular, sonra onaylar.

    python alis_arsiv.py paketle          -> son onaydan beri degisen satirlar -> arsiv_paketleri/alis-<zaman>.db
    python alis_arsiv.py onayla <paket>   -> imleci paketin zamanina ilerletir, paketi siler
    python alis_arsiv.py temizle          -> onayli ve 30 gundur gorulmeyen satirlari siler (+ VACUUM)
    python alis_arsiv.py durum

Degisen satir: zaman damgasi imlecten yeni olan (last_seen / detail_at / last_check). Ilanlar her gorulduklerinde
guncellendigi icin (fiyat, favori, teklif) degisen satir tekrar gonderilir; PC'de birincil anahtarla uzerine yazilir.
Sunucu toplayicilari "daha once gorduk mu" kararini bu tablolardan verir: 30 gunden yeni satirlar sunucuda kalir.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "alis.db")
OUT_DIR = os.path.join(BASE_DIR, "arsiv_paketleri")
KEEP_DAYS = 30

# tablo -> (degisim zamani ifadesi, temizlik kosulu)
TABLES = {
    "ka_ads": ("max(COALESCE(last_seen,''), COALESCE(detail_at,''))", "last_seen < datetime('now','-30 day')"),
    "eb_items": ("COALESCE(last_seen,'')", "last_seen < datetime('now','-30 day')"),
    "sp_items": ("COALESCE(last_seen,'')", "last_seen < datetime('now','-30 day')"),
    "eb_track": ("max(COALESCE(last_check,''), COALESCE(enrolled,''))",
                 "state <> 'active' AND closed_at < datetime('now','-30 day')"),
    "ka_cells": ("COALESCE(last_visit,'')", None),
    "eb_cells": ("COALESCE(last_visit,'')", None),
    "sp_cells": ("COALESCE(last_visit,'')", None),
}
FULL_TABLES = ("eb_track_raw",)           # kucuk: her pakette tamami
HEALTH_DAYS = 3


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_FILE, timeout=60)
    conn.execute("CREATE TABLE IF NOT EXISTS arsiv_meta (key TEXT PRIMARY KEY, value TEXT)")
    return conn


def cursor(conn) -> str:
    r = conn.execute("SELECT value FROM arsiv_meta WHERE key='imlec'").fetchone()
    return r[0] if r else ""


def existing(conn, names) -> list[str]:
    have = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    return [n for n in names if n in have]


def paketle() -> dict:
    conn = connect()
    os.makedirs(OUT_DIR, exist_ok=True)
    # imlec: paket anindan 2 sn once (ayni saniyede yazilan satir kacmasin; bir sonraki pakette tekrar gelir, zararsiz)
    stamp = conn.execute("SELECT datetime('now','-2 seconds')").fetchone()[0]
    name = f"alis-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}.db"
    path = os.path.join(OUT_DIR, name)
    since = cursor(conn)
    conn.execute("ATTACH DATABASE ? AS p", (path,))
    counts = {}
    for t in existing(conn, TABLES):
        expr = TABLES[t][0]
        conn.execute(f"CREATE TABLE p.{t} AS SELECT * FROM main.{t} WHERE {expr} > ? AND {expr} <= ?", (since, stamp))
        counts[t] = conn.execute(f"SELECT COUNT(*) FROM p.{t}").fetchone()[0]
    for t in existing(conn, FULL_TABLES):
        conn.execute(f"CREATE TABLE p.{t} AS SELECT * FROM main.{t}")
        counts[t] = conn.execute(f"SELECT COUNT(*) FROM p.{t}").fetchone()[0]
    conn.execute(f"CREATE TABLE p.health AS SELECT * FROM main.health WHERE day >= date('now','-{HEALTH_DAYS} day')")
    counts["health"] = conn.execute("SELECT COUNT(*) FROM p.health").fetchone()[0]
    conn.execute("CREATE TABLE p.paket_meta (key TEXT, value TEXT)")
    conn.execute("INSERT INTO p.paket_meta VALUES ('imlec_bitis', ?), ('imlec_baslangic', ?)", (stamp, since))
    conn.commit()
    conn.execute("DETACH DATABASE p")
    return {"paket": name, "satir": counts, "imlec": [since, stamp]}


def onayla(name: str) -> dict:
    path = os.path.join(OUT_DIR, os.path.basename(name))
    if not os.path.exists(path):
        return {"hata": "paket yok", "paket": name}
    p = sqlite3.connect(path)
    stamp = p.execute("SELECT value FROM paket_meta WHERE key='imlec_bitis'").fetchone()[0]
    p.close()
    conn = connect()
    if stamp > cursor(conn):          # imlec yalnizca ileri gider
        conn.execute("INSERT INTO arsiv_meta VALUES ('imlec', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                     (stamp,))
        conn.commit()
    os.remove(path)
    return {"onaylandi": name, "imlec": cursor(conn)}


def temizle() -> dict:
    conn = connect()
    cur = cursor(conn)
    if not cur:
        return {"silinen": {}, "not": "henuz onay yok, hicbir sey silinmedi"}
    out = {}
    for t in existing(conn, TABLES):
        expr, cond = TABLES[t]
        if not cond:
            continue
        # yalnizca onaylanmis (degisimi imlecten eski) VE eskimis satirlar
        out[t] = conn.execute(f"DELETE FROM {t} WHERE {cond} AND {expr} <= ?", (cur,)).rowcount
    out["health"] = conn.execute("DELETE FROM health WHERE day < date('now','-60 day')").rowcount
    conn.commit()
    if sum(out.values()):
        conn.execute("VACUUM")
    return {"silinen": out}


def durum() -> dict:
    conn = connect()
    return {"imlec": cursor(conn), "boyut_mb": round(os.path.getsize(DB_FILE) / 1e6, 1),
            "bekleyen_paket": sorted(os.listdir(OUT_DIR)) if os.path.isdir(OUT_DIR) else [],
            "satir": {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in existing(conn, TABLES)}}


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "durum"
    res = {"paketle": paketle, "temizle": temizle, "durum": durum}.get(cmd)
    print(json.dumps(onayla(sys.argv[2]) if cmd == "onayla" else res() if res else {"hata": "komut?"},
                     ensure_ascii=False))
