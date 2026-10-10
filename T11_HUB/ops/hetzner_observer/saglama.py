#!/usr/bin/env python3
"""
Gozlemci saglama araci: tek komut, kisa cikti.

    saglama.py            -> bugunun matrisi + testler + son hatalar
    saglama.py --gun 2026-10-04
    saglama.py --hatalar 20

Cikis kodu: 0 = temiz, 1 = uyari var, 2 = durdurucu hata var.
analyze.py ayni testleri calistirir; durdurucu hata varsa istatistik URETMEZ.

Neden var: 10 gun boyunca 'ilan sayfasi geldi (HTTP 200) ama durum okunamadi' hatasi
sessizce 1397 yanlis kayit uretti. Bu arac o tur hatayi ilk turda yakalar:
HTTP basarisi ile OKUMA basarisi ayri satirlarda gorunur.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "observe.db")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")

STAGES = ["oturum", "katalog", "katalog_okuma", "ilan", "ilan_okuma"]
STAGE_LABEL = {"oturum": "oturum", "katalog": "katalog", "katalog_okuma": "kat.oku",
               "ilan": "ilan", "ilan_okuma": "ilan.oku"}
FAIL_OUTCOMES = ("http", "ag", "bos", "eksik", "okunamadi", "engel")
KNOWN_AVAILABILITY = {"InStock", "SoldOut", "OutOfStock", "Discontinued", "LimitedAvailability"}

OK, WARN, FAIL = "✔", "⚠", "✘"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def _one(conn, sql, *args):
    row = conn.execute(sql, args).fetchone()
    return row[0] if row and row[0] is not None else 0


def _rate(conn, day: str, stage: str) -> tuple[int, int]:
    """(basarisiz, toplam) — 'yok' (404) basari sayilir: silinmis ilan normal sonuctur."""
    rows = conn.execute(
        "SELECT outcome, SUM(n) n FROM health WHERE day=? AND stage=? GROUP BY outcome", (day, stage)
    ).fetchall()
    total = sum(r["n"] for r in rows)
    bad = sum(r["n"] for r in rows if r["outcome"] in FAIL_OUTCOMES)
    return bad, total


def run_checks(conn: sqlite3.Connection, day: str | None = None) -> list[tuple[str, str, str]]:
    """Imkansizlik ve sagiklik testleri. (seviye, kod, aciklama) listesi doner."""
    day = day or utcnow().strftime("%Y-%m-%d")
    out: list[tuple[str, str, str]] = []

    # T1 kapanma orani: neredeyse her ilanin kapanmasi imkansizdir (10 gunluk hatanin imzasi)
    checked = _one(conn, "SELECT COUNT(*) FROM listings WHERE checks > 0")
    closed = _one(conn, "SELECT COUNT(*) FROM listings WHERE checks > 0 AND state IN ('gone','sold')")
    if checked >= 50:
        p = closed / checked
        lvl = FAIL if p > 0.95 else WARN if p > 0.7 else OK
        out.append((lvl, "T1", f"kapanma orani %{p*100:.0f} ({closed}/{checked})"))

    # T2 kalkan cok ama satis hic yok: satis tespiti calismiyor olabilir
    gone = _one(conn, "SELECT COUNT(*) FROM listings WHERE state='gone'")
    sold = _one(conn, "SELECT COUNT(*) FROM listings WHERE state='sold'")
    if gone >= 50:
        out.append((WARN if sold == 0 else OK, "T2", f"satis/kalkti {sold}/{gone}"))

    # T3 ilan okuma basarisi: HTTP 200 gelip durum okunamiyorsa veri uretilmez
    bad, tot = _rate(conn, day, "ilan_okuma")
    if tot >= 20:
        p = 1 - bad / tot
        lvl = FAIL if p < 0.6 else WARN if p < 0.8 else OK
        out.append((lvl, "T3", f"ilan okuma basarisi %{p*100:.0f} ({tot-bad}/{tot})"))

    # T4 katalog okuma: sayfa geliyor ama ilan cikmiyorsa site yapisi degismis
    bad, tot = _rate(conn, day, "katalog_okuma")
    if tot >= 5:
        p = bad / tot
        out.append((FAIL if p > 0.2 else OK, "T4", f"bos katalog %{p*100:.0f} ({bad}/{tot})"))

    # T5 genel hata orani
    req = _one(conn, "SELECT requests FROM budget WHERE day=?", day)
    err = _one(conn, "SELECT errors FROM budget WHERE day=?", day)
    if req >= 20:
        p = err / req
        lvl = FAIL if p > 0.10 else WARN if p > 0.05 else OK
        out.append((lvl, "T5", f"hata orani %{p*100:.1f} ({err}/{req})"))

    # T6 takip durmus mu: son kontrolden bu yana 2 saatten fazla gectiyse dongu takilmistir
    last = conn.execute("SELECT MAX(last_check) FROM listings").fetchone()[0]
    if last:
        age_h = (utcnow() - datetime.strptime(last, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                 ).total_seconds() / 3600
        paused_row = conn.execute("SELECT value FROM meta WHERE key='paused_until'").fetchone()
        planned = bool(paused_row and paused_row[0] > utcnow().strftime("%Y-%m-%d %H:%M:%S"))
        # Planli duraklamada kontrolun durmasi beklenen davranistir: kirmizi degil sari (sahte alarm olmasin)
        lvl = OK if age_h <= 2 else (WARN if planned else FAIL)
        out.append((lvl, "T6", f"son kontrol {age_h:.1f} saat once" + (" (planli duraklama)" if planned else "")))

    # T13 bosta gecen zaman: son 24 saatte duraklamalarin toplami
    try:
        mins = _one(conn, "SELECT SUM(minutes) FROM pauses WHERE ts >= datetime('now','-1 day')")
        share = mins / 1440
        out.append((FAIL if share > 0.3 else WARN if share > 0.15 else OK, "T13",
                    f"son 24 saatte duraklama {mins} dk (%{share*100:.0f})"))
    except sqlite3.OperationalError:
        pass

    # T7 bilinmeyen ham durum degeri: platform yeni bir deger dondurmeye baslamis
    raws = [r[0] for r in conn.execute("SELECT DISTINCT avail_raw FROM listings WHERE avail_raw IS NOT NULL")]
    # 'SUCCESS:<dile gore baslik>' satildi demektir; baslik dili onemsiz, tema belirleyici
    unknown = [r for r in raws if r not in KNOWN_AVAILABILITY and not r.startswith("SUCCESS:")]
    themes = sorted({r.split(":")[0] if ":" in r else r for r in raws})
    out.append((WARN if unknown else OK, "T7",
                f"durum turleri: {', '.join(themes) or '-'}" + (f" | BILINMEYEN: {unknown[:5]}" if unknown else "")))

    # T8 duraklatma
    paused = conn.execute("SELECT value FROM meta WHERE key='paused_until'").fetchone()
    if paused and paused[0] and paused[0] > utcnow().strftime("%Y-%m-%d %H:%M:%S"):
        out.append((WARN, "T8", f"engel korumasi aktif: {paused[0]} UTC'ye kadar"))

    # T9 akis hizi: gunun bu saatinde beklenenin cok altindaysa sistem yavaslamis/takilmis
    try:
        budget = json.load(open(CONFIG_FILE, encoding="utf-8"))["budget"]["max_requests_per_day"]
        hours = utcnow().hour + utcnow().minute / 60
        expected = budget * hours / 24 * 0.25
        if hours > 2 and day == utcnow().strftime("%Y-%m-%d"):
            out.append((WARN if req < expected else OK, "T9",
                        f"akis {req} istek (bu saate kadar beklenen en az {expected:.0f})"))
    except Exception:
        pass

    # T12 bot korumasi: HTTP 200 ama dogrulama sayfasi (2026-10-07'de 36 saat boyunca oldu)
    eng = _one(conn, "SELECT SUM(n) FROM health WHERE day=? AND outcome='engel'", day)
    tot = _one(conn, "SELECT SUM(n) FROM health WHERE day=? AND stage IN ('katalog','ilan')", day)
    if tot >= 20:
        p = eng / tot
        out.append((FAIL if p > 0.2 else WARN if p > 0.05 else OK, "T12", f"engel sayfasi %{p*100:.0f} ({eng}/{tot})"))

    # T11 (B3) dar arama hucreleri gercek arz sayisi veriyor mu (sinira takilmayan oran)
    snap = conn.execute(
        "SELECT COUNT(*) n, SUM(capped=0) real FROM cell_snapshots "
        "WHERE cell LIKE '%|model:%' AND ts >= datetime('now', '-3 days')").fetchone()
    if snap and snap[0] and snap[0] >= 20:
        p = (snap[1] or 0) / snap[0]
        out.append((WARN if p < 0.7 else OK, "T11", f"dar arama gercek arz %{p*100:.0f} ({snap[1]}/{snap[0]})"))

    # T10 servis
    try:
        state = subprocess.run(["systemctl", "is-active", "tatanga-observer"],
                               capture_output=True, text=True, timeout=5).stdout.strip()
        out.append((OK if state == "active" else FAIL, "T10", f"servis {state}"))
    except Exception:
        pass
    return out


def matrix(conn: sqlite3.Connection, day: str) -> list[str]:
    rows = conn.execute(
        "SELECT market, stage, outcome, SUM(n) n FROM health WHERE day=? GROUP BY 1,2,3", (day,)
    ).fetchall()
    data: dict[str, dict[str, dict[str, int]]] = {}
    for r in rows:
        data.setdefault(r["market"], {}).setdefault(r["stage"], {})[r["outcome"]] = r["n"]
    lines = [f"{'pazar':13}" + "".join(f"{STAGE_LABEL[s]:>15}" for s in STAGES)]
    for market in sorted(m for m in data if m != "gorsel-cdn"):
        cells = []
        for s in STAGES:
            d = data[market].get(s, {})
            tot = sum(d.values())
            bad = sum(v for k, v in d.items() if k in FAIL_OUTCOMES)
            if not tot:
                cells.append(f"{'-':>15}")
            elif bad:
                cells.append(f"{tot:>6} {FAIL}%{bad*100//tot:<3}".rjust(15))
            else:
                cells.append(f"{tot:>6} {OK}".rjust(15))
        lines.append(f"{market:13}" + "".join(cells))
    g = data.get("gorsel-cdn", {})
    if g:
        parts = []
        for s in ("gorsel", "gorsel_okuma"):
            d = g.get(s, {})
            tot = sum(d.values())
            bad = sum(v for k, v in d.items() if k in FAIL_OUTCOMES)
            parts.append(f"{s} {tot} {FAIL + '%' + str(bad*100//tot) if bad else OK}" if tot else f"{s} -")
        lines.append(f"{'gorsel-cdn':13}  " + "   ".join(parts))
    return lines


def main() -> int:
    ap = argparse.ArgumentParser(description="Gozlemci saglama")
    ap.add_argument("--gun", help="YYYY-MM-DD (varsayilan bugun, UTC)")
    ap.add_argument("--hatalar", type=int, default=3, help="gosterilecek son hata sayisi")
    args = ap.parse_args()
    conn = connect()
    day = args.gun or utcnow().strftime("%Y-%m-%d")

    req = _one(conn, "SELECT requests FROM budget WHERE day=?", day)
    print(f"SAGLAMA {day} | istek {req} | {utcnow():%H:%M} UTC")
    for line in matrix(conn, day):
        print(line)

    checks = run_checks(conn, day)
    print("TESTLER  " + "  ".join(f"{lvl}{code}" for lvl, code, _ in checks))
    for lvl, code, text in checks:
        if lvl != OK:
            print(f"  {lvl} {code} {text}")

    errs = conn.execute(
        "SELECT ts, market, stage, outcome, detail FROM error_log ORDER BY id DESC LIMIT ?",
        (args.hatalar,)).fetchall()
    if errs:
        print("SON HATALAR")
        for e in errs:
            print(f"  {e['ts'][11:16]} {e['market']:11} {e['stage']:12} {e['outcome']:9} {e['detail'][:60]}")

    levels = {lvl for lvl, _, _ in checks}
    return 2 if FAIL in levels else 1 if WARN in levels else 0


if __name__ == "__main__":
    sys.exit(main())
