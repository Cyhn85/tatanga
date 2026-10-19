#!/usr/bin/env python3
"""
PC tarafi istatistik arsivi: sunucudaki gozlemciden paketleri ceker, arsive aktarir,
eksiksiz geldigini dogrular, sunucuya onay verir ve okunabilir tablolar uretir.

    python cek.py            -> bekleyen + yeni paketleri cek, aktar, onayla, temizlet, tablolari yaz
    python cek.py --durum    -> arsiv ozeti (ag baglantisi gerekmez)

Arsiv:   <tatanga>/istatistik/arsiv.db      (tum gecmis)
Tablolar:<tatanga>/istatistik/tablolar/*.csv (Excel ile acilir, ; ayracli, UTF-8 BOM)
Gunluk:  <tatanga>/istatistik/cek.log

KURAL: Bir paket ancak icindeki her satirin arsivde oldugu dogrulandiktan sonra onaylanir.
Onaylanmayan veri sunucudan silinmez; PC kapali kalsa da hicbir sey kaybolmaz.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

SERVER = "root@195.201.146.224"
REMOTE_DIR = "/opt/tatanga-observer"
ROOT = Path(__file__).resolve().parents[3] / "istatistik"
ARCHIVE = ROOT / "arsiv.db"
TABLES_DIR = ROOT / "tablolar"
INBOX = ROOT / "gelen"
LOG = ROOT / "cek.log"
ALIS_ARCHIVE = ROOT / "alis_arsiv.db"
# 2026-10-19: Vinted gozlemcisi PC'de (pc_gozlemci.py). Paketler yerel; sunucuya gidilmez.
OBS_LOCAL_DB = ROOT / "vinted" / "observe.db"
OBS_DIR = Path(__file__).resolve().parents[1] / "hetzner_observer"
ALIS_REMOTE = "/opt/tatanga-alis"

# Gorev pythonw ile (konsolsuz) calisir; ssh/scp gibi konsol programlari her cagrida bos bir pencere acip
# kapatiyordu (kullanici 2026-10-16'da fark etti). Windows'ta alt surecler pencere acmadan calistirilir.
NO_WINDOW = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}

# tablo -> (benzersiz anahtar, cakisma davranisi). listings/health guncellenir, digerleri bir kez yazilir.
KEYS = {
    "catalog_samples": ("item_id", "IGNORE"),
    "events": ("id", "IGNORE"),
    "cell_snapshots": ("id", "IGNORE"),
    "pauses": ("id", "IGNORE"),
    "listings": ("item_id", "REPLACE"),
    "health": ("day, market, stage, outcome", "REPLACE"),
}
# Alis toplayicilari (Kleinanzeigen / eBay / Sellpy): satirlar her goruldukce guncellenir -> hep uzerine yazilir
ALIS_KEYS = {
    "ka_ads": ("adid", "REPLACE"), "eb_items": ("item_id", "REPLACE"), "sp_items": ("object_id", "REPLACE"),
    "eb_track": ("item_id", "REPLACE"), "eb_track_raw": ("status", "REPLACE"),
    "ka_cells": ("cell", "REPLACE"), "eb_cells": ("cell", "REPLACE"), "sp_cells": ("cell", "REPLACE"),
    "health": ("day, stage, outcome", "REPLACE"),
}


def log(msg: str) -> None:
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}"
    print(line, flush=True)
    ROOT.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def ssh(cmd: str, timeout: int = 600) -> str:
    res = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ServerAliveInterval=30", SERVER, cmd],
                         capture_output=True, text=True, encoding="utf-8", timeout=timeout, **NO_WINDOW)
    if res.returncode != 0:
        raise RuntimeError(f"ssh hatasi ({res.returncode}): {res.stderr.strip()[:300]}")
    return res.stdout


def scp(remote: str, local: Path) -> None:
    res = subprocess.run(["scp", "-q", "-o", "BatchMode=yes", f"{SERVER}:{remote}", str(local)],
                         capture_output=True, text=True, timeout=1800, **NO_WINDOW)
    if res.returncode != 0:
        raise RuntimeError(f"scp hatasi: {res.stderr.strip()[:300]}")


def import_package(path: Path, archive: Path = ARCHIVE, keys: dict = KEYS) -> dict:
    """Paketi arsive aktarir ve dogrular. Eksik satir varsa hata firlatir (onay verilmez)."""
    conn = sqlite3.connect(archive)
    conn.execute("ATTACH DATABASE ? AS p", (str(path),))
    tables = [r[0] for r in conn.execute("SELECT name FROM p.sqlite_master WHERE type='table'")]
    result = {}
    for table in tables:
        if table not in keys:
            continue
        key, mode = keys[table]
        conn.execute(f"CREATE TABLE IF NOT EXISTS main.{table} AS SELECT * FROM p.{table} WHERE 0")
        # Sunucuda sonradan eklenen sutunlar arsive de eklenir
        have = {r[1] for r in conn.execute(f"PRAGMA main.table_info({table})")}
        for name, decl in [(r[1], r[2]) for r in conn.execute(f"PRAGMA p.table_info({table})")]:
            if name not in have:
                conn.execute(f"ALTER TABLE main.{table} ADD COLUMN {name} {decl}")
        idx = f"ux_{table}"
        conn.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS {idx} ON {table} ({key})")
        cols = [r[1] for r in conn.execute(f"PRAGMA p.table_info({table})")]
        collist = ", ".join(cols)
        conn.execute(f"INSERT OR {mode} INTO main.{table} ({collist}) SELECT {collist} FROM p.{table}")
        # Dogrulama: paketteki her anahtar arsivde var mi
        key_cols = [k.strip() for k in key.split(",")]
        join = " AND ".join(f"m.{k} = x.{k}" for k in key_cols)
        missing = conn.execute(
            f"SELECT COUNT(*) FROM p.{table} x WHERE NOT EXISTS (SELECT 1 FROM main.{table} m WHERE {join})"
        ).fetchone()[0]
        total = conn.execute(f"SELECT COUNT(*) FROM p.{table}").fetchone()[0]
        if missing:
            conn.rollback()
            raise RuntimeError(f"{table}: {missing}/{total} satir arsive yazilamadi")
        result[table] = total
    conn.commit()
    conn.execute("DETACH DATABASE p")
    conn.close()
    return result


def write_tables() -> None:
    """Excel'de acilan ozet tablolar. Ayrac ';' ve UTF-8 BOM: Almanca/Turkce Excel dogru acar."""
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(ARCHIVE)
    conn.row_factory = sqlite3.Row
    queries = {
        "gunluk_ozet.csv": """
            SELECT substr(ts,1,10) gun,
                   CASE WHEN instr(substr(cell, instr(cell,'|')+1), 'model:')=1 THEN 'model'
                        ELSE substr(substr(cell, instr(cell,'|')+1), 1, instr(substr(cell, instr(cell,'|')+1),'|')-1) END kategori,
                   COUNT(*) ornek, ROUND(AVG(price),1) ort_fiyat
            FROM catalog_samples GROUP BY 1,2 ORDER BY 1 DESC, 2""",
        "satislar.csv": """
            SELECT substr(closed_at,1,10) satis_gunu, substr(cell,1,instr(cell,'|')-1) marka,
                   substr(cell, instr(cell,'|')+1) kategori_pazar, title baslik, condition kondisyon, size beden,
                   COALESCE(final_price, price) fiyat, currency para, ROUND(days_to_close,1) gun,
                   CASE WHEN COALESCE(close_uncertain,0)=1 THEN 'belirsiz' ELSE 'kesin' END zaman, url
            FROM listings WHERE state='sold' ORDER BY closed_at DESC""",
        "marka_ozet.csv": """
            SELECT substr(cell,1,instr(cell,'|')-1) marka, COUNT(*) takip,
                   SUM(state='sold') satildi, SUM(state='gone') silindi, SUM(state='active') aktif,
                   ROUND(100.0*SUM(state='sold')/COUNT(*),1) satis_orani,
                   ROUND(AVG(CASE WHEN state='sold' THEN COALESCE(final_price,price) END),1) ort_satis_fiyati
            FROM listings WHERE state IN ('active','sold','gone') GROUP BY 1 ORDER BY satis_orani DESC""",
    }
    for name, sql in queries.items():
        rows = conn.execute(sql).fetchall()
        with open(TABLES_DIR / name, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.writer(fh, delimiter=";")
            if rows:
                w.writerow(rows[0].keys())
                for r in rows:
                    w.writerow([str(v).replace(".", ",") if isinstance(v, float) else v for v in r])
    conn.close()


def run_trends() -> None:
    """
    Ek trend verileri: Wikipedia ilgi endeksi (T1) ve Vinted etiketli-yeni endeksi (T2).
    Hata cekme islemini bozmaz; sadece gunluge yazilir.
    """
    here = Path(__file__).resolve().parent
    obs = here.parent / "hetzner_observer"
    for name, cmd in (
        ("wikipedia", [sys.executable, str(here / "trend_wiki.py")]),
        ("etiketli-yeni", [sys.executable, str(obs / "analyze.py"), "--db", str(ARCHIVE),
                           "--etiketli", "--csv", str(TABLES_DIR)]),
        ("motor", [sys.executable, str(obs / "motor.py"), "--db", str(ARCHIVE), "--csv", str(TABLES_DIR)]),
        ("firsat", [sys.executable, str(obs / "firsat.py"), "--db", str(ARCHIVE), "--csv", str(TABLES_DIR)]),
        ("sifir-talep", [sys.executable, str(obs / "sifir_talep.py"), "--alis", str(ALIS_ARCHIVE), "--csv", str(TABLES_DIR)]),
        # fiyat / satis hizi trendi + Wikipedia onculuk testi (sifir-talep tablosundan sonra)
        ("trend", [sys.executable, str(obs / "trend.py"), "--arsiv", str(ARCHIVE), "--alis", str(ALIS_ARCHIVE), "--csv", str(TABLES_DIR)]),
        ("capraz", [sys.executable, str(obs / "capraz.py"), "--arsiv", str(ARCHIVE), "--alis", str(ALIS_ARCHIVE),
                    "--csv", str(TABLES_DIR)]),
        ("zeka-urunler", [sys.executable, str(obs / "zeka_urunler.py"), "--arsiv", str(ARCHIVE)]),
        # gorsel arama dizini: yalniz YENI aktif ilanlar + aktiflik guncellemesi (gorsel saklanmaz)
        ("gorsel-indeks", [sys.executable, str(obs / "gorsel_zeka.py"), "indeks"]),
        # zaman sirali fiyat/hiz geritesti -> karne C5
        ("geritest", [sys.executable, str(obs / "geritest.py"), "--arsiv", str(ARCHIVE), "--csv", str(TABLES_DIR)]),
        ("karne", [sys.executable, str(obs / "karne.py"), "--arsiv", str(ARCHIVE), "--alis", str(ALIS_ARCHIVE),
                   "--csv", str(TABLES_DIR)]),
    ):
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                                 timeout=5400 if name == "gorsel-indeks" else 1200, **NO_WINDOW,
                                 env={**os.environ, "PYTHONIOENCODING": "utf-8"})
            last = (res.stdout or res.stderr).strip().splitlines()[-1:] or ["-"]
            log(f"trend {name}: {'tamam' if res.returncode == 0 else 'HATA'} | {last[0][:120]}")
        except Exception as exc:
            log(f"trend {name}: HATA {type(exc).__name__}: {exc}")


def _arsiv_local(*args: str) -> str:
    """PC'deki gozlemci veritabani uzerinde arsiv.py (paketle / onayla / temizle)."""
    env = {**os.environ, "TATANGA_OBS_DB": str(OBS_LOCAL_DB), "PYTHONIOENCODING": "utf-8"}
    res = subprocess.run([sys.executable, str(OBS_DIR / "arsiv.py"), *args], capture_output=True, text=True,
                         encoding="utf-8", timeout=1800, env=env, **NO_WINDOW)
    if res.returncode != 0:
        raise RuntimeError(f"arsiv.py {args[0]} hatasi: {(res.stderr or res.stdout).strip()[-300:]}")
    return res.stdout


def pull() -> int:
    ROOT.mkdir(parents=True, exist_ok=True)
    INBOX.mkdir(parents=True, exist_ok=True)
    total = {}
    if OBS_LOCAL_DB.exists():
        pkg_dir = OBS_LOCAL_DB.parent / "arsiv_paketleri"
        pending = sorted(p.name for p in pkg_dir.glob("*.db")) if pkg_dir.exists() else []
        info = json.loads(_arsiv_local("paketle").strip().splitlines()[-1])
        names = sorted(set(pending) | {info["paket"]})
        log(f"cekilecek paket (PC gozlemcisi): {len(names)}")
        for name in names:
            counts = import_package(pkg_dir / name)
            _arsiv_local("onayla", name)
            for k, v in counts.items():
                total[k] = total.get(k, 0) + v
            log(f"  {name}: {counts} -> onaylandi")
        log(f"gozlemci temizligi: {_arsiv_local('temizle').strip()[-200:]}")
    else:
        log("UYARI: PC gozlemci veritabani yok (istatistik/vinted/observe.db)")
    try:
        pull_alis()
    except Exception as exc:          # alis cekimi gozlemci arsivini bozmasin; hata gunluge, onay verilmez
        log(f"ALIS HATA: {type(exc).__name__}: {exc}")
    write_tables()
    run_trends()
    log(f"bitti: {total} | arsiv {ARCHIVE.stat().st_size // 1024 // 1024} MB | tablolar: {TABLES_DIR}")
    return 0


def pull_alis() -> None:
    """Kleinanzeigen / eBay / Sellpy paketleri: ayni kural, ayri arsiv (istatistik/alis_arsiv.db)."""
    pending = ssh(f"ls {ALIS_REMOTE}/arsiv_paketleri 2>/dev/null || true").split()
    info = json.loads(ssh(f"cd {ALIS_REMOTE} && ./venv/bin/python alis_arsiv.py paketle").strip().splitlines()[-1])
    names = sorted(set(p for p in pending if p.endswith(".db")) | {info["paket"]})
    log(f"alis: cekilecek paket {len(names)}")
    for name in names:
        local = INBOX / name
        scp(f"{ALIS_REMOTE}/arsiv_paketleri/{name}", local)
        counts = import_package(local, ALIS_ARCHIVE, ALIS_KEYS)
        ssh(f"cd {ALIS_REMOTE} && ./venv/bin/python alis_arsiv.py onayla {name}")
        local.unlink(missing_ok=True)
        log(f"  alis {name}: {counts} -> onaylandi")
    log(f"alis sunucu temizligi: {ssh(f'cd {ALIS_REMOTE} && ./venv/bin/python alis_arsiv.py temizle').strip()}")
    log(f"alis arsiv {ALIS_ARCHIVE.stat().st_size // 1024 // 1024} MB")


def status() -> int:
    if not ARCHIVE.exists():
        print("arsiv henuz yok")
        return 0
    conn = sqlite3.connect(ARCHIVE)
    for t in KEYS:
        try:
            n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            print(f"{t:16} {n}")
        except sqlite3.OperationalError:
            print(f"{t:16} -")
    print("boyut:", ARCHIVE.stat().st_size // 1024 // 1024, "MB")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--durum", action="store_true")
    args = ap.parse_args()
    try:
        sys.exit(status() if args.durum else pull())
    except Exception as exc:
        log(f"HATA: {type(exc).__name__}: {exc}")
        sys.exit(1)
