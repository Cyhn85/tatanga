#!/usr/bin/env python3
"""
Sunucu tarafi arsiv aktarimi: sunucu toplar, PC saklar.

    arsiv.py paketle         -> son onaydan bu yana yeni/degisen satirlari tek bir paket dosyasina yazar
    arsiv.py onayla <paket>  -> PC paketi ice aktardigini dogruladi: imleci ilerlet
    arsiv.py temizle         -> onaylanmis ve yeterince eski veriyi sunucudan sil
    arsiv.py durum           -> imlecler, bekleyen paket, tablo boyutlari

KURAL: Onaylanmamis hicbir satir silinmez. PC gunlerce kapali kalsa bile veri kaybolmaz;
paketler biriktirilir, PC acildiginda hepsi sirayla cekilir.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Veritabani yolu: sunucuda betik klasoru; PC'de TATANGA_OBS_DB (istatistik/vinted/observe.db, depo disi).
DB_FILE = os.environ.get("TATANGA_OBS_DB") or os.path.join(BASE_DIR, "observe.db")
EXPORT_DIR = os.path.join(os.path.dirname(DB_FILE), "arsiv_paketleri")

# Artimli aktarilan tablolar: imlec sutunu. catalog_samples'in rowid'si Vinted ilan kimligidir
# (ekleme sirasi DEGIL): sonradan bulunan eski kimlikli ilan atlanirdi. Bu yuzden zaman imleci.
INCREMENTAL = {"catalog_samples": "ts", "events": "id", "cell_snapshots": "id", "pauses": "id"}
# Her pakette tamami (kucuk ve guncellenen) giden tablolar
FULL = ["listings"]
HEALTH_DAYS = 3                  # saglik matrisinin son N gunu her pakette tekrar gider (upsert)
KEEP_RAW_DAYS = 14               # ham veri sunucuda bu kadar gun tutulur (onaylandiysa)
KEEP_CLOSED_LISTING_DAYS = 30    # kapanmis ilan: tekrar yayin tespiti icin daha uzun


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_FILE, timeout=60)
    conn.row_factory = sqlite3.Row
    return conn


def meta(conn, key, default="0"):
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row[0] if row else default


def set_meta(conn, key, value):
    conn.execute("INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                 (key, str(value)))


def paketle() -> None:
    os.makedirs(EXPORT_DIR, exist_ok=True)
    conn = connect()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = os.path.join(EXPORT_DIR, f"paket-{stamp}.db")
    conn.execute(f"ATTACH DATABASE ? AS p", (path,))
    counts, cursors = {}, {}
    # Zaman imlecinin ust siniri 'simdi - 2 sn': ayni saniyede paketten SONRA yazilan satir kacmasin
    ts_end = conn.execute("SELECT datetime('now', '-2 seconds')").fetchone()[0]
    for table, key in INCREMENTAL.items():
        if key == "ts":
            start, end = meta(conn, f"arsiv_acked:{table}"), ts_end
        else:
            start = int(meta(conn, f"arsiv_acked:{table}"))
            end = conn.execute(f"SELECT COALESCE(MAX({key}), 0) FROM main.{table}").fetchone()[0]
        conn.execute(f"CREATE TABLE p.{table} AS SELECT * FROM main.{table} WHERE {key} > ? AND {key} <= ?",
                     (start, end))
        counts[table] = conn.execute(f"SELECT COUNT(*) FROM p.{table}").fetchone()[0]
        cursors[table] = end
    for table in FULL:
        conn.execute(f"CREATE TABLE p.{table} AS SELECT * FROM main.{table}")
        counts[table] = conn.execute(f"SELECT COUNT(*) FROM p.{table}").fetchone()[0]
    conn.execute("CREATE TABLE p.health AS SELECT * FROM main.health WHERE day >= date('now', ?)",
                 (f"-{HEALTH_DAYS} days",))
    counts["health"] = conn.execute("SELECT COUNT(*) FROM p.health").fetchone()[0]
    conn.execute("CREATE TABLE p.paket_bilgi (anahtar TEXT, deger TEXT)")
    info = {"paket": os.path.basename(path), "olusturma": utcnow(), "imlecler": cursors, "sayilar": counts}
    conn.execute("INSERT INTO p.paket_bilgi VALUES ('bilgi', ?)", (json.dumps(info),))
    conn.commit()
    conn.execute("DETACH DATABASE p")
    set_meta(conn, f"arsiv_pending:{os.path.basename(path)}", json.dumps(cursors))
    conn.commit()
    print(json.dumps(info, ensure_ascii=False))


def onayla(name: str) -> None:
    conn = connect()
    raw = meta(conn, f"arsiv_pending:{name}", "")
    if not raw:
        sys.exit(f"bekleyen paket bulunamadi: {name}")
    for table, end in json.loads(raw).items():
        # imlec yalnizca ileri gider: eski bir paketin gec onayi yeniyi geri almaz
        if INCREMENTAL.get(table) == "ts":
            set_meta(conn, f"arsiv_acked:{table}", max(meta(conn, f"arsiv_acked:{table}"), str(end)))
        else:
            set_meta(conn, f"arsiv_acked:{table}", max(int(meta(conn, f"arsiv_acked:{table}")), int(end)))
    set_meta(conn, "arsiv_last_ack", utcnow())
    conn.execute("DELETE FROM meta WHERE key=?", (f"arsiv_pending:{name}",))
    conn.commit()
    path = os.path.join(EXPORT_DIR, name)
    if os.path.exists(path):
        os.remove(path)
    print(f"onaylandi: {name}")


def temizle() -> None:
    conn = connect()
    removed = {}
    for table, key in INCREMENTAL.items():
        raw = meta(conn, f"arsiv_acked:{table}")
        acked = raw if key == "ts" else int(raw)
        cur = conn.execute(f"DELETE FROM {table} WHERE {key} <= ? AND ts < datetime('now', ?)",
                           (acked, f"-{KEEP_RAW_DAYS} days"))
        removed[table] = cur.rowcount
    last_ack = meta(conn, "arsiv_last_ack", "")
    if last_ack:
        # kapanmis ilan, son onaydan once kapanmis ve yeterince eskiyse silinir (PC'de tam kopyasi var)
        cur = conn.execute(
            "DELETE FROM listings WHERE state IN ('sold','gone','expired','relisted') "
            "AND closed_at IS NOT NULL AND closed_at < ? AND closed_at < datetime('now', ?)",
            (last_ack, f"-{KEEP_CLOSED_LISTING_DAYS} days"))
        removed["listings"] = cur.rowcount
    conn.execute("DELETE FROM health WHERE day < date('now', '-30 days')")
    conn.commit()
    conn.execute("VACUUM")
    print(json.dumps({"silinen": removed}, ensure_ascii=False))


def durum() -> None:
    conn = connect()
    print("imlecler:", {t: meta(conn, f"arsiv_acked:{t}") for t in INCREMENTAL}, "| son onay:", meta(conn, "arsiv_last_ack", "-"))
    pend = [r[0].split(":", 1)[1] for r in conn.execute("SELECT key FROM meta WHERE key LIKE 'arsiv_pending:%'")]
    print("bekleyen paketler:", pend or "-")
    print("tablolar:", {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                        for t in list(INCREMENTAL) + FULL})
    print("veritabani:", round(os.path.getsize(DB_FILE) / 1024 / 1024, 1), "MB")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "durum"
    if cmd == "paketle":
        paketle()
    elif cmd == "onayla" and len(sys.argv) > 2:
        onayla(sys.argv[2])
    elif cmd == "temizle":
        temizle()
    else:
        durum()
