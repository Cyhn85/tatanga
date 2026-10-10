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

# tablo -> (benzersiz anahtar, cakisma davranisi). listings/health guncellenir, digerleri bir kez yazilir.
KEYS = {
    "catalog_samples": ("item_id", "IGNORE"),
    "events": ("id", "IGNORE"),
    "cell_snapshots": ("id", "IGNORE"),
    "pauses": ("id", "IGNORE"),
    "listings": ("item_id", "REPLACE"),
    "health": ("day, market, stage, outcome", "REPLACE"),
}


def log(msg: str) -> None:
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}"
    print(line, flush=True)
    ROOT.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def ssh(cmd: str, timeout: int = 600) -> str:
    res = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ServerAliveInterval=30", SERVER, cmd],
                         capture_output=True, text=True, encoding="utf-8", timeout=timeout)
    if res.returncode != 0:
        raise RuntimeError(f"ssh hatasi ({res.returncode}): {res.stderr.strip()[:300]}")
    return res.stdout


def scp(remote: str, local: Path) -> None:
    res = subprocess.run(["scp", "-q", "-o", "BatchMode=yes", f"{SERVER}:{remote}", str(local)],
                         capture_output=True, text=True, timeout=1800)
    if res.returncode != 0:
        raise RuntimeError(f"scp hatasi: {res.stderr.strip()[:300]}")


def import_package(path: Path) -> dict:
    """Paketi arsive aktarir ve dogrular. Eksik satir varsa hata firlatir (onay verilmez)."""
    conn = sqlite3.connect(ARCHIVE)
    conn.execute("ATTACH DATABASE ? AS p", (str(path),))
    tables = [r[0] for r in conn.execute("SELECT name FROM p.sqlite_master WHERE type='table'")]
    result = {}
    for table in tables:
        if table not in KEYS:
            continue
        key, mode = KEYS[table]
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
    ):
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=1200,
                                 env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"})
            last = (res.stdout or res.stderr).strip().splitlines()[-1:] or ["-"]
            log(f"trend {name}: {'tamam' if res.returncode == 0 else 'HATA'} | {last[0][:120]}")
        except Exception as exc:
            log(f"trend {name}: HATA {type(exc).__name__}: {exc}")


def pull() -> int:
    ROOT.mkdir(parents=True, exist_ok=True)
    INBOX.mkdir(parents=True, exist_ok=True)
    pending = ssh(f"ls {REMOTE_DIR}/arsiv_paketleri 2>/dev/null || true").split()
    info = json.loads(ssh(f"cd {REMOTE_DIR} && ./venv/bin/python arsiv.py paketle").strip().splitlines()[-1])
    names = sorted(set(p for p in pending if p.endswith(".db")) | {info["paket"]})
    log(f"cekilecek paket: {len(names)}")
    total = {}
    for name in names:
        local = INBOX / name
        scp(f"{REMOTE_DIR}/arsiv_paketleri/{name}", local)
        counts = import_package(local)
        ssh(f"cd {REMOTE_DIR} && ./venv/bin/python arsiv.py onayla {name}")
        local.unlink(missing_ok=True)
        for k, v in counts.items():
            total[k] = total.get(k, 0) + v
        log(f"  {name}: {counts} -> onaylandi")
    cleaned = ssh(f"cd {REMOTE_DIR} && ./venv/bin/python arsiv.py temizle").strip()
    log(f"sunucu temizligi: {cleaned}")
    write_tables()
    run_trends()
    log(f"bitti: {total} | arsiv {ARCHIVE.stat().st_size // 1024 // 1024} MB | tablolar: {TABLES_DIR}")
    return 0


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
