#!/usr/bin/env python3
"""
Haftalik ZEKA KARNESI (PC'de). "Zeka hazir mi, TATANGA'ya kopru kurulabilir mi?" sorusunu olcumle cevaplar.
Kopru ancak TUM kriterler gectiginde onerilir; karar yine kullanicinindir.

    python karne.py [--arsiv ...] [--alis ...] [--csv <klasor>]

KRITERLER (esikler asagida sabit; degistirmek bilincli bir karar olmali):
  C1 TEMIZ VERI   : son 28 gunde temiz gun >= 24. Temiz gun = Vinted katalog ornegi >= 10.000 VE ilan kontrolu >= 400.
  C2 GUVENILIR    : 30 gun satilma olasiligi %95 araligi +-10 puan icinde olan grup sayisi >= 50 (motor.py).
  C3 KAPSAM       : mont / ayakkabi / kot / ust giyim kategorilerinin HER BIRINDE >= 5 guvenilir grup.
  C4 SATIS HACMI  : son 7 gunde zamani kesin Vinted satisi >= 700 (gunde ~100).
  C5 KALIBRASYON  : 30+ gun once kaydedilen tahminler (marka x kategori, p30) ile o haftadan sonra giren ilanlarin
                    GERCEKLESEN 30 gun satis orani arasindaki ortalama mutlak fark <= 10 puan (en az 10 grup, grupta >= 20 ilan).
                    Tahmin kaydi her hafta otomatik yapilir (karne.db); ilk olcum ilk kayittan 37 gun sonra mumkun olur.
  C6 ONERI ISABETI: kullanicinin gercek alim/satis kaydi basladiginda olculur (simdilik olculemez).
"""

from __future__ import annotations

import argparse
import csv
import os
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
import analyze as A  # noqa: E402
import motor as M  # noqa: E402

ROOT = os.path.abspath(os.path.join(BASE_DIR, "..", "..", "..", "istatistik"))
CLEAN_SAMPLES, CLEAN_CHECKS, CLEAN_DAYS_NEED = 10_000, 400, 24
RELIABLE_NEED, CAT_NEED, SALES_7D_NEED = 50, 5, 700
CALIB_MAX_ERR, CALIB_MIN_GROUPS, CALIB_MIN_N = 0.10, 10, 20
CATS = {"jacken": "mont", "schuhe": "ayakkabi", "jeans": "kot", "oberteile": "ust giyim"}


def week_id(d: datetime) -> str:
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def snapshot(kdb, rows: list[dict], today: datetime) -> bool:
    """Bu haftanin tahminlerini (marka x kategori p30) bir kez kaydeder."""
    wk = week_id(today)
    if kdb.execute("SELECT 1 FROM preds WHERE week=? LIMIT 1", (wk,)).fetchone():
        return False
    for r in rows:
        if r["seviye"] == "marka·kategori":
            kdb.execute("INSERT INTO preds VALUES (?,?,?,?,?)",
                        (wk, today.strftime("%Y-%m-%d"), r["grup"].lower(), r["p30_duzeltilmis"], r["takip"]))
    kdb.commit()
    return True


def calibration(conn, kdb, today: datetime):
    """En eski olgun tahmin haftasi icin (tahmin, gerceklesen) farklari. Olgun = kayittan >= 37 gun gecmis."""
    mature = kdb.execute("SELECT week, MIN(day) FROM preds GROUP BY week HAVING MIN(day) <= ? ORDER BY week DESC",
                         ((today - timedelta(days=37)).strftime("%Y-%m-%d"),)).fetchone()
    if not mature:
        first = kdb.execute("SELECT MIN(day) FROM preds").fetchone()[0]
        return None, first
    wk, day = mature
    start = datetime.strptime(day, "%Y-%m-%d")
    end = start + timedelta(days=7)
    pred = {g: p for g, p in kdb.execute("SELECT grup, p30 FROM preds WHERE week=?", (wk,))}
    real = defaultdict(lambda: [0, 0])          # grup -> [30 gunde satilan, 30 gun satilmadan kalan]
    for r in conn.execute(
            "SELECT cell, state, days_to_close, first_seen, last_active_at, last_check FROM listings "
            "WHERE cohort IS NOT 'baseline' AND first_seen >= ? AND first_seen < ?",
            (start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))):
        brand, cat, _ = (r["cell"].split("|") + ["", ""])[:3]
        g = f"{brand} · {cat}".lower()
        if g not in pred:
            continue
        if r["state"] == "sold" and r["days_to_close"] is not None and r["days_to_close"] <= 30:
            real[g][0] += 1
        else:
            seen = r["last_active_at"] or r["last_check"]
            if seen and (datetime.strptime(seen, "%Y-%m-%d %H:%M:%S")
                         - datetime.strptime(r["first_seen"], "%Y-%m-%d %H:%M:%S")).days >= 30:
                real[g][1] += 1                 # 30 gun boyunca satilmadan izlendi
    pairs = [(pred[g], s / (s + u), s + u) for g, (s, u) in real.items() if s + u >= CALIB_MIN_N]
    return (wk, pairs), None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arsiv", default=os.path.join(ROOT, "arsiv.db"))
    ap.add_argument("--alis", default=os.path.join(ROOT, "alis_arsiv.db"))
    ap.add_argument("--csv", metavar="KLASOR")
    args = ap.parse_args()
    today = datetime.now(timezone.utc).replace(tzinfo=None)
    conn = A.connect(args.arsiv)
    kdb = sqlite3.connect(os.path.join(ROOT, "karne.db"))
    kdb.execute("CREATE TABLE IF NOT EXISTS preds (week TEXT, day TEXT, grup TEXT, p30 REAL, n INTEGER)")
    kdb.execute("CREATE TABLE IF NOT EXISTS karne (week TEXT, kriter TEXT, deger TEXT, hedef TEXT, durum TEXT, "
                "PRIMARY KEY (week, kriter))")
    out = []

    # C1 temiz gunler
    since = (today - timedelta(days=28)).strftime("%Y-%m-%d")
    samples = dict(conn.execute("SELECT substr(ts,1,10), COUNT(*) FROM catalog_samples WHERE ts >= ? GROUP BY 1",
                                (since,)).fetchall())
    checks = dict(conn.execute("SELECT day, SUM(n) FROM health WHERE stage='ilan_okuma' AND outcome='ok' "
                               "AND day >= ? GROUP BY day", (since,)).fetchall())
    days = [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(1, 29)]
    clean = sum(1 for d in days if samples.get(d, 0) >= CLEAN_SAMPLES and (checks.get(d) or 0) >= CLEAN_CHECKS)
    out.append(("C1 temiz veri gunu (son 28)", f"{clean}/28", f">= {CLEAN_DAYS_NEED}", clean >= CLEAN_DAYS_NEED))

    # C2 / C3 guvenilir gruplar
    matcher, rates = A.ModelMatcher(), A.fx_rates(conn)
    rows = M.build(M.load(conn, matcher, rates))
    rel = [r for r in rows if r["durum"] == "guvenilir" and r["seviye"] not in ("kategori", "pazar", "kondisyon")]
    out.append(("C2 guvenilir grup (+-10 puan)", str(len(rel)), f">= {RELIABLE_NEED}", len(rel) >= RELIABLE_NEED))
    per_cat = defaultdict(int)
    for r in rel:
        parts = r["grup"].split(" · ")
        cat = parts[1] if r["seviye"] in ("marka·kategori", "marka·kategori·tip") and len(parts) > 1 else None
        if cat:
            per_cat["oberteile" if cat == "hoodies" else cat] += 1
    cov = ", ".join(f"{name} {per_cat.get(c, 0)}" for c, name in CATS.items())
    out.append(("C3 kategori kapsami", cov, f"her biri >= {CAT_NEED}", all(per_cat.get(c, 0) >= CAT_NEED for c in CATS)))

    # C4 satis hacmi (zamani kesin)
    s7 = conn.execute("SELECT COUNT(*) FROM listings WHERE state='sold' AND COALESCE(close_uncertain,0)=0 "
                      "AND closed_at >= ?", ((today - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S"),)).fetchone()[0]
    eb_sold = None
    if os.path.exists(args.alis):
        try:
            eb_sold = sqlite3.connect(args.alis).execute(
                "SELECT COUNT(*) FROM eb_track WHERE state='sold' AND closed_at >= ?",
                ((today - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S"),)).fetchone()[0]
        except sqlite3.OperationalError:
            pass
    out.append(("C4 satis hacmi (7 gun)", f"Vinted {s7}" + (f" | eBay {eb_sold}" if eb_sold is not None else ""),
                f"Vinted >= {SALES_7D_NEED}", s7 >= SALES_7D_NEED))

    # C5 kalibrasyon (tahmin kaydi + olgun hafta)
    new_snap = snapshot(kdb, rows, today)
    cal, first = calibration(conn, kdb, today)
    if cal is None:
        ready = (datetime.strptime(first, "%Y-%m-%d") + timedelta(days=37)).strftime("%Y-%m-%d") if first else "-"
        out.append(("C5 kalibrasyon", f"henuz olculemez (ilk tahmin kaydi {first}; ilk olcum {ready})",
                    f"ort. fark <= {CALIB_MAX_ERR*100:.0f} puan", False))
    else:
        wk, pairs = cal
        if len(pairs) < CALIB_MIN_GROUPS:
            out.append(("C5 kalibrasyon", f"{wk}: yalnizca {len(pairs)} grup olculebildi",
                        f">= {CALIB_MIN_GROUPS} grup", False))
        else:
            err = sum(abs(p - q) for p, q, _ in pairs) / len(pairs)
            out.append(("C5 kalibrasyon", f"{wk}: ort. fark {err*100:.1f} puan ({len(pairs)} grup)",
                        f"<= {CALIB_MAX_ERR*100:.0f} puan", err <= CALIB_MAX_ERR))
    out.append(("C6 oneri isabeti", "olculemez: kullanici alim/satis kaydi yok", ">= %60 iki hafta ust uste", False))

    wk = week_id(today)
    print(f"ZEKA KARNESI {wk}  ({today:%Y-%m-%d})" + ("  | bu haftanin tahminleri kaydedildi" if new_snap else ""))
    for name, val, target, ok in out:
        print(f"  {'✔' if ok else '✘'} {name:30} {val:52} hedef {target}")
        kdb.execute("INSERT OR REPLACE INTO karne VALUES (?,?,?,?,?)", (wk, name, val, target, "gecti" if ok else "gecmedi"))
    kdb.commit()
    passed = sum(1 for *_, ok in out if ok)
    print(f"SONUC: {passed}/{len(out)} kriter gecti -> "
          + ("KOPRU ONERILIR (karar kullanicinin)" if passed == len(out) else "kopru HENUZ ONERILMEZ"))
    if args.csv:
        os.makedirs(args.csv, exist_ok=True)
        with open(os.path.join(args.csv, "zeka_karnesi.csv"), "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.writer(fh, delimiter=";")
            w.writerow(["hafta", "kriter", "deger", "hedef", "durum"])
            for r in kdb.execute("SELECT * FROM karne ORDER BY week DESC, kriter"):
                w.writerow(r)
    return 0


if __name__ == "__main__":
    sys.exit(main())
