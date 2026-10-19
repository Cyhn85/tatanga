#!/usr/bin/env python3
"""
Alis toplayicilari saglama araci. Tek bakista: hangi asamada ne kadar basari / hata var.

    python saglama_alis.py          -> testler + son hatalar   (cikis: 0 tamam, 1 uyari, 2 hata)

K1/E1/S1 zamani gelmis is zamaninda yapiliyor mu (butce dolu / gece / tum hucreler taze = planli bekleme)
K2 bugun liste okuma basarisi            K3 bugun ilan okuma basarisi
K4 son 24 saatte engel                   K5 kayit doluluk: fiyat, kondisyon, beden, marka teyidi
K6 marka teyidi: ilan sayfasindaki Marke alani bizim marka mi (basliga gore secim dogru mu)
K7 kondisyon filtresi tutuyor mu: ilk 3 disi kondisyon orani (filtre bozulursa artar)
E1 eBay son basarili arama kac dakika once (> 90 dk = hata)   E2 bugun eBay arama basarisi
E3 eBay'de AB disi ilan (0 olmali)                              E4 eBay token (401 = anahtar gecersiz)
E5 eBay satis takibi: aktif/kapanan, gecikmis kontrol, ulke dagilimi
S1 Sellpy son basarili okuma (aktif saatte > 90 dk = hata)     S2 bugun Sellpy okuma basarisi
S3 Sellpy filtre/siralama tuttu mu (eksik = adres parametresi bozulmus)   S4 Sellpy kayit doluluk
"""

from __future__ import annotations

import os
import sqlite3
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "alis.db")
OK, WARN, FAIL = "✔", "⚠", "✘"
TOP3 = ("Neu mit Etikett", "Neu", "Sehr Gut")


def one(conn, sql, args=()):
    r = conn.execute(sql, args).fetchone()
    return (r[0] if r and r[0] is not None else 0)


def rate(conn, stage):
    rows = dict(conn.execute("SELECT outcome, n FROM health WHERE day=date('now') AND stage=?", (stage,)).fetchall())
    total = sum(rows.values())
    return total, rows.get("ok", 0), rows


def due_check(conn, code: str, cells: str, due_h: float, late_h: float, budget_sql: str | None, budget_max: int,
              hour: int, active: tuple[int, int] | None, label: str):
    """
    "Zamani gelmis is zamaninda yapiliyor mu?" (2026-10-19: eski test 'son 90 dk okuma yok'u hata sayiyordu;
    toplayicilar butce dolunca ya da tum hucreler taraninca BILEREK bekler -> yanlis alarm).
    HATA: (a) aktif saatte, zamani gelmis hucre varken ve butce dolmamisken 2 saattir okuma yok, ya da
          (b) hucrelerin %10'undan fazlasi tarama araliginin cok gerisinde (late_h saatten eski).
    """
    row = conn.execute(f"SELECT COUNT(*), (julianday('now') - julianday(MAX(last_visit))) * 1440, "
                       f"SUM(last_visit < datetime('now','-{due_h} hours')), "
                       f"SUM(last_visit < datetime('now','-{late_h} hours')) FROM {cells}").fetchone()
    n, idle, due, late = row[0] or 0, row[1], row[2] or 0, row[3] or 0
    if not n or idle is None:
        return (FAIL, code, f"{label}: hic hucre taranmamis")
    used = one(conn, budget_sql) if budget_sql else 0
    full = budget_sql is not None and used >= budget_max
    in_hours = active is None or active[0] <= hour < active[1]
    stuck = in_hours and idle > 120 and due > 0 and not full
    behind = late / n > 0.10
    why = (f"{label}: son okuma {idle:.0f} dk once | zamani gelmis hucre {due}/{n} | geride kalan {late}"
           + (f" | gunluk butce doldu ({used}/{budget_max}, planli bekleme)" if full else "")
           + ("" if in_hours else " | gece molasi (planli)"))
    if stuck:
        return (FAIL, code, why + " -> TAKILMIS: zamani gelmis is var ama okuma yok")
    if behind:
        return (FAIL, code, why + f" -> hucrelerin %{late / n * 100:.0f}'i {late_h:.0f} saatten eski")
    return (OK, code, why)


def run_checks(conn) -> list[tuple[str, str, str]]:
    out = []
    hour = datetime.now(ZoneInfo("Europe/Berlin")).hour
    # Kleinanzeigen: hucre araligi 24-48 saat, gunluk 1.500 sayfa, 07-23 Berlin
    out.append(due_check(conn, "K1", "ka_cells", 24, 60, "SELECT pages FROM budget WHERE day=date('now')", 2200,
                         hour, (7, 23), "Kleinanzeigen"))
    for code, stage in (("K2", "liste_okuma"), ("K3", "ilan_okuma")):
        total, ok, rows = rate(conn, stage)
        if total == 0:
            out.append((WARN, code, f"{stage}: bugun kayit yok"))
            continue
        share = ok / total
        bad = ", ".join(f"{k} {v}" for k, v in rows.items() if k != "ok")
        out.append((OK if share >= 0.9 else WARN if share >= 0.7 else FAIL, code,
                    f"{stage}: %{share*100:.0f} basarili ({ok}/{total})" + (f" | {bad}" if bad else "")))
    blocks = one(conn, "SELECT COUNT(*) FROM pauses WHERE ts >= datetime('now','-1 day')")
    out.append((OK if blocks == 0 else WARN if blocks < 3 else FAIL, "K4", f"son 24 saatte engel: {blocks}"))
    n = one(conn, "SELECT COUNT(*) FROM ka_ads WHERE detail_status='ok'")
    if n:
        fill = {k: one(conn, f"SELECT COUNT(*) FROM ka_ads WHERE detail_status='ok' AND {k} IS NOT NULL") / n
                for k in ("detail_price", "zustand", "groesse", "marke")}
        weak = min(fill, key=fill.get)
        out.append((OK if fill["zustand"] >= 0.95 and fill["detail_price"] >= 0.8 else WARN, "K5",
                    "doluluk " + ", ".join(f"{k} %{v*100:.0f}" for k, v in fill.items()) + f" (n={n})"))
        bad = one(conn, "SELECT COUNT(*) FROM ka_ads WHERE detail_status='ok' AND marke_ok=0")
        known = one(conn, "SELECT COUNT(*) FROM ka_ads WHERE detail_status='ok' AND marke_ok IS NOT NULL")
        if known:
            out.append((OK if bad / known <= 0.1 else WARN, "K6",
                        f"Marke alani baska marka: %{bad/known*100:.0f} ({bad}/{known})"))
        off = one(conn, f"SELECT COUNT(*) FROM ka_ads WHERE detail_status='ok' AND zustand NOT IN "
                        f"({','.join('?'*len(TOP3))})", TOP3)
        out.append((OK if off / n <= 0.05 else FAIL, "K7", f"ilk 3 disi kondisyon: %{off/n*100:.0f} ({off}/{n})"))
    else:
        out.append((WARN, "K5", "henuz okunmus ilan sayfasi yok"))
    try:
        # eBay: DE hucreleri 12-24 saat, diger ulkeler 48 saat; gunluk 4.500 cagri; 7/24
        out.append(due_check(conn, "E1", "eb_cells", 24, 60,
                             "SELECT COALESCE(SUM(n),0) FROM health WHERE day=date('now') AND stage IN ('eb_arama','eb_takip')",
                             4500, hour, None, "eBay"))
        total, ok, rows = rate(conn, "eb_arama")
        bad = ", ".join(f"{k} {v}" for k, v in rows.items() if k != "ok")
        if total:
            out.append((OK if ok / total >= 0.95 else FAIL, "E2",
                        f"eBay arama: %{ok/total*100:.0f} basarili ({ok}/{total})" + (f" | {bad}" if bad else "")))
        eu = ("DE","AT","FR","BE","NL","IT","PL","ES","PT","LU","DK","SE","FI","IE","CZ","SK","SI","HU","RO","BG",
              "HR","GR","CY","MT","EE","LV","LT")
        non_eu = one(conn, f"SELECT COUNT(*) FROM eb_items WHERE country NOT IN ({','.join('?'*len(eu))})", eu)
        out.append((OK if non_eu == 0 else FAIL, "E3", f"eBay AB disi ilan: {non_eu}"))
        unauth = one(conn, "SELECT COUNT(*) FROM error_log WHERE stage='eb_arama' AND detail LIKE 'HTTP 401%' "
                           "AND ts >= datetime('now','-3 hours')")
        tr = dict(conn.execute("SELECT COALESCE(sinif,'takipte')||':'||state, COUNT(*) FROM eb_track GROUP BY 1").fetchall())
        act = one(conn, "SELECT COUNT(*) FROM eb_track WHERE state='active'")
        late = one(conn, "SELECT COUNT(*) FROM eb_track WHERE state='active' AND "
                         "(last_check IS NULL AND enrolled < datetime('now','-1 day') OR last_check < datetime('now','-5 day'))")
        share = late / act if act else 0
        # oran: binlerce takipte birkac gecikme normaldir (kontrol payi gunluk cagrilarin %40'i)
        out.append((FAIL if share > 0.10 else WARN if share > 0.02 else OK, "E5",
                    "eBay takip: " + ", ".join(f"{k} {v}" for k, v in sorted(tr.items()))
                    + f" | gecikmis {late}/{act} (%{share * 100:.1f})"))
        out.append((OK if unauth == 0 else FAIL, "E4", "eBay anahtar gecerli" if unauth == 0
                    else f"eBay 401 x{unauth}: anahtar gecersiz/degismis -> ebay.env guncellenmeli"))
    except sqlite3.OperationalError:
        out.append((WARN, "E1", "eBay tablolari henuz yok"))
    try:
        # Sellpy: hucre araligi 12-24 saat, gunluk 1.500 sayfa, 07-23 Berlin
        out.append(due_check(conn, "S1", "sp_cells", 24, 48, "SELECT pages FROM sp_budget WHERE day=date('now')", 1500,
                             hour, (7, 23), "Sellpy"))
        total, ok, rows = rate(conn, "sp_okuma")
        bad = ", ".join(f"{k} {v}" for k, v in rows.items() if k != "ok")
        if total:
            out.append((OK if ok / total >= 0.9 else WARN if ok / total >= 0.7 else FAIL, "S2",
                        f"Sellpy okuma: %{ok/total*100:.0f} basarili ({ok}/{total})" + (f" | {bad}" if bad else "")))
        broken = one(conn, "SELECT COUNT(*) FROM error_log WHERE stage='sp_okuma' AND detail LIKE 'filtre/siralama%' "
                           "AND ts >= datetime('now','-1 day')")
        out.append((OK if broken == 0 else FAIL, "S3", "Sellpy filtre ve siralama tutuyor" if broken == 0
                    else f"Sellpy filtre/siralama TUTMADI x{broken}: adres parametreleri degismis olabilir"))
        n = one(conn, "SELECT COUNT(*) FROM sp_items")
        if n:
            fill = {k: one(conn, f"SELECT COUNT(*) FROM sp_items WHERE {k} IS NOT NULL") / n
                    for k in ("price", "condition", "brand", "size", "type")}
            out.append((OK if min(fill.values()) >= 0.9 else WARN, "S4",
                        "doluluk " + ", ".join(f"{k} %{v*100:.0f}" for k, v in fill.items()) + f" (n={n})"))
    except sqlite3.OperationalError:
        out.append((WARN, "S1", "Sellpy tablolari henuz yok"))
    # B1 bekci: zaman siniri asilip tarayici yeniden kurulan isler (donma belirtisi)
    try:
        # oran: mudahale / okunan sayfa (mutlak sayi yerine; 1.500 sayfalik gunde 20 mudahale %1,3'tur)
        hung = one(conn, "SELECT COALESCE(SUM(n),0) FROM health WHERE stage='bekci' AND day >= date('now','-1 day')")
        reads = one(conn, "SELECT COALESCE(SUM(n),0) FROM health WHERE day >= date('now','-1 day') "
                          "AND stage IN ('liste','ilan','sp_liste')")
        ratio = hung / reads if reads else 0
        out.append((FAIL if ratio > 0.05 else WARN if ratio > 0.02 else OK, "B1",
                    f"bekci mudahalesi (24 saat): {hung} / {reads} sayfa = %{ratio * 100:.1f}"))
    except sqlite3.OperationalError:
        pass
    return out


def main() -> int:
    conn = sqlite3.connect(DB_FILE)
    checks = run_checks(conn)
    print("ALIS  " + "  ".join(f"{lvl}{code}" for lvl, code, _ in checks))
    for lvl, code, text in checks:
        if lvl != OK:
            print(f"  {lvl} {code} {text}")
    for lvl, code, text in checks:
        if lvl == OK:
            print(f"  {lvl} {code} {text}")
    print("ozet: " + " | ".join(f"{r[0]} {r[1]}" for r in conn.execute(
        "SELECT 'ka-'||cat, COUNT(*) FROM ka_ads GROUP BY 1 UNION ALL SELECT 'eb-'||cat, COUNT(*) FROM eb_items GROUP BY 1 UNION ALL SELECT 'sp-'||cat, COUNT(*) FROM sp_items GROUP BY 1")) + f" | hucre {one(conn, 'SELECT COUNT(*) FROM ka_cells')}"
          + f" | bugun sayfa {one(conn, 'SELECT pages FROM budget WHERE day=date(?)', ('now',))}")
    errs = conn.execute("SELECT ts, stage, outcome, detail FROM error_log ORDER BY id DESC LIMIT 5").fetchall()
    if errs:
        print("son hatalar:")
        for e in errs:
            print(f"  {e[0]} {e[1]}/{e[2]} {e[3][:110]}")
    levels = {lvl for lvl, _, _ in checks}
    return 2 if FAIL in levels else 1 if WARN in levels else 0


if __name__ == "__main__":
    sys.exit(main())
