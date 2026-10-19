#!/usr/bin/env python3
"""
ONERI RAPORU: bir TATANGA kazimasinin (hub veritabani) zekayla puanlanmis sonuclarini, her oneri icin KANITIYLA
(alis linki, dayandigi gercek Vinted satislari, 30 gun satis olasiligi, gorsel benzerler) tek HTML sayfada gosterir.

    python oneri_rapor.py --hub <hub.db> --since "2026-10-19 17:15" [--ust 15] [--cikti <dosya.html>]

Once zeka_urunler.py ayni hub'da calismis olmali (zeka_* sutunlari). Rapor yalniz OKUR.
Ayni Vinted ilani birden cok ulke alan adinda gorunur (vinted.de / .fr / .be ...): ilan numarasina gore TEKILLESTIRILIR.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sqlite3
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.abspath(os.path.join(BASE_DIR, "..", "..")))
import analyze as A  # noqa: E402
import capraz as C  # noqa: E402
import zeka_urunler as Z  # noqa: E402

FMT = "%Y-%m-%d %H:%M:%S"
CEK_KAR = 20.0           # kullanici kurali: cok karli = tutucu net >= 20 EUR + birebir marka+model


def item_key(url: str) -> str:
    m = re.search(r"/items/(\d+)", url or "")
    return f"vinted:{m.group(1)}" if m else (url or "")


def sold_index(conn, matcher, rates) -> dict:
    """anahtar (keys_for) -> gercek Vinted satislari [(url, fiyat EUR, kondisyon, ulke, kapanis)]."""
    idx = defaultdict(list)
    for r in conn.execute("SELECT cell, title, size, condition, country, url, COALESCE(final_price, price) p, "
                          "COALESCE(currency,'EUR') cur, closed_at FROM listings WHERE state='sold'"):
        brand, cat, _ = (r["cell"].split("|") + ["", ""])[:3]
        cat = None if cat.startswith("model:") else C.CAT_MAP.get(cat, cat)
        rate = rates.get(r["cur"]) or 0
        if not rate or not r["p"] or A.is_child_size(r["size"], cat or ""):
            continue
        model, line = matcher.match(brand, r["title"] or "")
        typ = A.match_type(A.norm_text(r["title"] or ""))
        sale = (r["url"], round(r["p"] / rate, 2), A.norm_condition(r["condition"]) or "?", r["country"],
                (r["closed_at"] or "")[:10], r["title"] or "")
        for k in C.keys_for(brand, cat, model, typ, line):
            idx[k].append(sale)
    return idx


def product_key(p, matcher, table, model_cat):
    title = p["title"] or ""
    brand = Z.canonical_brand(p["brand"], title, table)
    if not brand:
        return None, None
    model, line = matcher.match(brand, title)
    typ = A.match_type(A.norm_text(title))
    cat = next(iter(C.TYPE_CAT[typ]), None) if typ in C.TYPE_CAT and len(C.TYPE_CAT[typ]) == 1 else None
    if cat is None:
        nt = A.norm_text(title)
        cat = next((k for k, rx in C.CAT_WORDS.items() if rx.search(nt)), None)
    if cat is None and model:
        cat = model_cat.get((brand.lower(), model.lower()))
    level = (p["zeka_seviye"] or "").split(" (")[0]
    for k in C.keys_for(brand, cat, model, typ, line):
        if k[0] == level:
            return k, brand
    return None, brand


def visual(p) -> list[dict]:
    try:
        from logic import gorsel_arama as G
    except Exception as exc:
        print(f"  gorsel arama yuklenemedi: {type(exc).__name__}: {exc}")
        return []
    try:
        res = G.similar_to_product(dict(p), k=4)
    except Exception as exc:
        print(f"  gorsel arama hatasi ({p['id']}): {type(exc).__name__}: {exc}")
        return []
    return res.get("sonuclar", []) if res.get("status") == "ok" else []


def esc(v) -> str:
    return html.escape(str(v if v is not None else ""))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hub", required=True)
    ap.add_argument("--since", required=True, help="kazimanin baslangici (products.created_at, UTC)")
    ap.add_argument("--ust", type=int, default=15)
    ap.add_argument("--arsiv", default=os.path.join(C.ROOT, "arsiv.db"))
    ap.add_argument("--cikti", default=os.path.join(C.ROOT, "raporlar", f"oneri_{datetime.now():%Y%m%d_%H%M}.html"))
    ap.add_argument("--gorsel", action="store_true", help="gorsel benzerleri ekle (CLIP, yavas)")
    args = ap.parse_args()

    conn = A.connect(args.arsiv)
    matcher, rates = A.ModelMatcher(), A.fx_rates(conn)
    ref = C.SellRef(conn, matcher, rates, {}, {})
    model_cat = ref.model_cat
    table = Z.brand_table()
    idx = sold_index(conn, matcher, rates)
    hub = sqlite3.connect(args.hub)
    hub.row_factory = sqlite3.Row
    rows = hub.execute("SELECT * FROM products WHERE created_at >= ?", (args.since,)).fetchall()

    # ---- ozet
    seen, uniq = set(), []
    for p in sorted(rows, key=lambda r: -(r["zeka_net_kar"] if r["zeka_net_kar"] is not None else -1e9)):
        k = item_key(p["source_url"])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(p)
    per_platform = Counter((p["source_platform"] or "?").split("_")[0] for p in uniq)
    scored = [p for p in uniq if p["zeka_net_kar"] is not None]
    ranked = [p for p in scored if p["zeka_sirala"] == 1]
    pos = [p for p in ranked if p["zeka_net_kar"] > 0]
    top = [p for p in pos if p["zeka_net_kar"] >= CEK_KAR and (p["zeka_seviye"] or "").startswith("marka·model")]
    reasons = Counter((p["zeka_isaret"] or "?").split(" (")[0] for p in uniq if p["zeka_net_kar"] is None)
    disi = Counter()
    for p in scored:
        if p["zeka_sirala"] != 1:
            m = re.search(r"(PAZARLIK/YEM FIYATI|ZAYIF KARSILASTIRMA|ACIKLAMA|REPLIKA|supheli)", p["zeka_isaret"] or "")
            disi[m.group(1) if m else "diger"] += 1
    gt = None
    try:
        gt = sqlite3.connect(os.path.join(C.ROOT, "capraz.db")).execute(
            "SELECT n, bantta_oran, hata, sapma FROM geritest WHERE olcum='fiyat' AND seviye='HEPSI'").fetchone()
    except sqlite3.OperationalError:
        pass

    # ---- kartlar
    cards = []
    for p in pos[:args.ust]:
        key, brand = product_key(p, matcher, table, model_cat)
        sales = sorted(idx.get(key, []), key=lambda s: s[1]) if key else []
        img = ""
        try:
            imgs = json.loads(p["images_json"] or "[]")
            img = next((i for i in imgs if isinstance(i, str) and i.startswith("http")), "")
        except ValueError:
            pass
        sims = visual(p) if args.gorsel else []
        sale_rows = "".join(
            f"<tr><td><a href='{esc(s[0])}' target='_blank'>{esc(s[5][:60])}</a></td><td>{s[1]:.2f} €</td>"
            f"<td>{esc(s[2])}</td><td>{esc(s[3])}</td><td>{esc(s[4])}</td></tr>" for s in sales[:12])
        sim_html = "".join(
            f"<a class='sim' href='{esc(s.get('ilan_url'))}' target='_blank'><img src='{esc(s.get('gorsel_url'))}' "
            f"loading='lazy'><span>{esc(s.get('platform'))} · {esc(s.get('fiyat'))} · {esc(s.get('etiket'))}</span></a>"
            for s in sims)
        warn = p["zeka_isaret"] or ""
        level = p["zeka_seviye"] or ""
        strong = level.startswith("marka·model")
        cards.append(f"""
<article class="card">
  <div class="head">
    {'<img class="thumb" src="' + esc(img) + '" loading="lazy">' if img else '<div class="thumb none">gorsel yok</div>'}
    <div class="meta">
      <h3><a href="{esc(p['source_url'])}" target="_blank">{esc(p['title'])}</a></h3>
      <div class="row"><span class="pill">{esc(p['source_platform'])}</span><span class="pill">{esc(p['condition'])}</span>
        <span class="pill {'ok' if strong else 'weak'}">{esc(level)}</span></div>
      <dl>
        <dt>Alis</dt><dd>{p['price']:.2f} {esc(p['currency'])} → toplam maliyet {p['zeka_alis_toplam']:.2f} €</dd>
        <dt>Satis (gercek Vinted)</dt><dd>P25 {p['zeka_satis_p25']:.2f} € · medyan {p['zeka_satis_medyan']:.2f} € · {p['zeka_n']} satis</dd>
        <dt>Tutucu net kar</dt><dd class="kar">{p['zeka_net_kar']:+.2f} €</dd>
        <dt>30 gunde satilma</dt><dd>{(p['zeka_p30'] or 0) * 100:.0f}% · beklenen kar {(p['zeka_beklenen'] or 0):+.2f} €</dd>
        <dt>Uyari</dt><dd class="warn">{esc(warn) or '-'}</dd>
      </dl>
    </div>
  </div>
  <details><summary>Dayandigi gercek satislar ({len(sales)}{', ilk 12' if len(sales) > 12 else ''}) — anahtar: {esc(' / '.join(key[1:]) if key else '?')}</summary>
    <table><tr><th>Satilan ilan</th><th>Fiyat</th><th>Kondisyon</th><th>Ulke</th><th>Satis</th></tr>{sale_rows}</table>
  </details>
  {('<div class="sims"><b>Gorsel benzer aktif ilanlar</b>' + sim_html + '</div>') if sim_html else ''}
</article>""")

    verdict = (f"<b>{len(top)}</b> ilan 'cok karli' kuralini geciyor (tutucu net ≥ {CEK_KAR:.0f} € + birebir marka+model)."
               if top else f"<b>Hicbir ilan 'cok karli' kuralini gecmiyor</b> (tutucu net ≥ {CEK_KAR:.0f} € + birebir marka+model).")
    gt_txt = (f"Fiyat geritesti (zaman sirali, {gt[0]} satis): tahminlerin %{gt[1] * 100:.0f}'i P25-P75 bandinda "
              f"(hedef ≥ %50), medyan hata %{gt[2] * 100:.0f}, sapma %{gt[3] * 100:+.0f} (tahmin gercegin altinda = tutucu)."
              if gt else "Fiyat geritesti sonucu yok.")
    page = f"""<!doctype html><html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Oneri Kazimasi</title><style>
:root{{--bg:#f6f6f4;--fg:#1d1d1b;--mut:#6b6b66;--card:#fff;--line:#e3e2dd;--ok:#1f7a4d;--weak:#a35a00;--bad:#b3261e}}
@media (prefers-color-scheme:dark){{:root{{--bg:#151514;--fg:#ecebe6;--mut:#9b9a94;--card:#1f1f1d;--line:#33332f;--ok:#5fc48f;--weak:#e0a050;--bad:#f08a80}}}}
body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif}}
main{{max-width:1080px;margin:0 auto;padding:24px 16px}} h1{{font-size:24px;margin:0 0 4px}} .mut{{color:var(--mut)}}
.box{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px;margin:16px 0}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}} .kpi b{{font-size:22px;display:block}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px;margin:12px 0;overflow:hidden}}
.head{{display:flex;gap:14px}} .thumb{{width:120px;height:150px;object-fit:cover;border-radius:6px;flex:none;background:var(--line)}}
.thumb.none{{display:flex;align-items:center;justify-content:center;font-size:12px;color:var(--mut)}}
h3{{margin:0 0 6px;font-size:16px}} a{{color:inherit}} .row{{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:6px}}
.pill{{border:1px solid var(--line);border-radius:99px;padding:1px 8px;font-size:12px}} .pill.ok{{color:var(--ok)}} .pill.weak{{color:var(--weak)}}
dl{{display:grid;grid-template-columns:150px 1fr;gap:2px 10px;margin:0}} dt{{color:var(--mut)}} dd{{margin:0;min-width:0;overflow-wrap:anywhere}} .meta{{min-width:0;flex:1}}
.kar{{font-weight:700;color:var(--ok)}} .warn{{color:var(--weak);font-size:13px}}
details{{margin-top:8px}} table{{width:100%;border-collapse:collapse;font-size:13px;margin-top:6px}} td,th{{border-bottom:1px solid var(--line);padding:4px;text-align:left}}
.sims{{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px;font-size:12px}} .sim{{width:110px;text-decoration:none}} .sim img{{width:110px;height:130px;object-fit:cover;border-radius:6px;display:block}}
@media (max-width:600px){{.head{{flex-direction:column}} .thumb{{width:100%;height:220px}} dl{{grid-template-columns:1fr}}}}
</style></head><body><main>
<h1>Oneri kazimasi</h1><div class="mut">Kazima {esc(args.since)} sonrasi · rapor {datetime.now():%Y-%m-%d %H:%M} · kaynak: TATANGA test kopyasi</div>
<div class="box"><p>{verdict}</p><p class="mut">{gt_txt} Tum kar hesaplari GERCEK Vinted satislarinin alt ceyregiyle (P25) yapilir;
maliyet: alis + alici koruma (0,70 € + %5, olculdu) + gelen kargo 5,00 € (olculdu) + paketleme + iade payi.</p>
<div class="grid">
<div class="kpi"><b>{len(uniq)}</b>tekil ilan</div><div class="kpi"><b>{len(scored)}</b>gercek satisla puanlandi</div>
<div class="kpi"><b>{len(ranked)}</b>siralamaya girdi</div><div class="kpi"><b>{len(pos)}</b>tutucu kar &gt; 0</div>
<div class="kpi"><b>{sum(1 for p in pos if p['zeka_net_kar'] >= 10)}</b>kar ≥ 10 €</div><div class="kpi"><b>{len(top)}</b>cok karli (≥ 20 € + model)</div>
</div>
<p class="mut">Platform: {esc(', '.join(f'{k} {v}' for k, v in per_platform.most_common()))}<br>
Puanlanamayan nedenleri: {esc(', '.join(f'{k} {v}' for k, v in reasons.most_common(6)))}<br>
Siralama disi: {esc(', '.join(f'{k} {v}' for k, v in disi.most_common()))}</p></div>
<h2>En iyi {len(cards)} oneri (tutucu kara gore)</h2>
{''.join(cards) or '<p>Pozitif tutucu karli ilan yok.</p>'}
</main></body></html>"""
    os.makedirs(os.path.dirname(args.cikti), exist_ok=True)
    open(args.cikti, "w", encoding="utf-8").write(page)
    print(f"RAPOR: {args.cikti} | tekil {len(uniq)} | puanli {len(scored)} | kar>0 {len(pos)} | cok karli {len(top)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
