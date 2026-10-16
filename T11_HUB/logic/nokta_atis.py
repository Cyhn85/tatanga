"""
Nokta Atis: capraz platform degerlemelerini TATANGA'da gosterir.

Kaynak: <tatanga>/istatistik/capraz.db (capraz.py her calismada yazar; her calisma bir TARAMA kimligi alir).
Bu modul o tabloyu SALT OKUR. Tek yazma: kullanicinin "TATANGA'ya Al" dedigi firsati TATANGA urun tablosuna
(kaniti ile) eklemek. Karar vermez, otomatik yayin yapmaz; favori/yayin sureclerinin disindadir.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path

CAPRAZ_DB = Path(__file__).resolve().parents[2] / "istatistik" / "capraz.db"
KOND_TR = {"yeni_etiketli": "Neu mit Etikett", "yeni": "Neu", "cok_iyi": "Sehr gut"}
PUBLISH_COND = {"yeni_etiketli": "new_with_tags", "yeni": "new_with_tags", "cok_iyi": "very_good"}
SIRALAMA = {
    "beklenen": "beklenen_kar_30g IS NULL, beklenen_kar_30g DESC",
    "net": "net_kar_tutucu DESC",
    "ucuz": "alis_toplam ASC",
    "hiz": "p30 IS NULL, p30 DESC",
}


def _conn() -> sqlite3.Connection | None:
    if not CAPRAZ_DB.exists():
        return None
    c = sqlite3.connect(f"file:{CAPRAZ_DB}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    return c


def runs() -> list[dict]:
    c = _conn()
    if not c:
        return []
    out = [dict(r) for r in c.execute("SELECT * FROM taramalar ORDER BY run_id DESC")]
    for r in out:
        try:
            r["platform"] = json.loads(r.pop("platform_json") or "{}")
        except ValueError:
            r["platform"] = {}
    c.close()
    return out


def firsatlar(run_id: str, sadece_cok_karli: bool, platform: str = "", kategori: str = "", marka: str = "",
              min_net: float | None = None, sira: str = "beklenen", limit: int = 120) -> list[dict]:
    c = _conn()
    if not c:
        return []
    where, args = ["run_id=?"], [run_id]
    if sadece_cok_karli:
        where.append("cok_karli=1")
    else:
        where.append("net_kar_tutucu > 0 AND COALESCE(siralama_disi,0)=0")
    if platform:
        where.append("platform=?")
        args.append(platform)
    if kategori:
        where.append("kategori=?")
        args.append(kategori)
    if marka:
        where.append("LOWER(marka) LIKE ?")
        args.append(f"%{marka.lower()}%")
    if min_net is not None:
        where.append("net_kar_tutucu >= ?")
        args.append(min_net)
    order = SIRALAMA.get(sira, SIRALAMA["beklenen"])
    rows = [dict(r) for r in c.execute(
        f"SELECT * FROM firsatlar WHERE {' AND '.join(where)} ORDER BY {order} LIMIT ?", args + [limit])]
    c.close()
    for r in rows:
        r["kanit"] = json.loads(r.get("kanit_json") or "[]")
        r["kondisyon_tr"] = KOND_TR.get(r["kondisyon"], r["kondisyon"])
        r["isaret_list"] = [x.strip() for x in (r.get("isaretler") or "").split(";") if x.strip()]
    return rows


def firsat(run_id: str, firsat_id: str) -> dict | None:
    c = _conn()
    if not c:
        return None
    r = c.execute("SELECT * FROM firsatlar WHERE run_id=? AND firsat_id=?", (run_id, firsat_id)).fetchone()
    c.close()
    return dict(r) if r else None


def facets(run_id: str) -> dict:
    c = _conn()
    if not c:
        return {}
    out = {
        "platform": [r[0] for r in c.execute("SELECT DISTINCT platform FROM firsatlar WHERE run_id=? ORDER BY 1", (run_id,))],
        "kategori": [r[0] for r in c.execute("SELECT DISTINCT kategori FROM firsatlar WHERE run_id=? ORDER BY 1", (run_id,))],
    }
    c.close()
    return out


COST = {k: v["deger"] for k, v in json.load(open(Path(__file__).resolve().parents[1] / "ops" / "hetzner_observer" /
                                                  "maliyet.json", encoding="utf-8")).items() if not k.startswith("_")}


def arb_rows(f: dict) -> list[dict]:
    """Detay tablosu satirlari: Vinted tutucu (P25), Vinted medyan, kendi satis verisi olan ulkeler."""
    alis = f["alis_toplam"] or 0

    def row(platform, sell, net):
        fee = max(0.0, sell - alis - net)          # paketleme + iade payi + komisyon (maliyet.json)
        return {"platform": platform, "est_sell_price": round(sell, 2), "outbound_shipping": 0.0,
                "sell_fee": round(fee, 2), "sell_fee_rate": round(fee / sell, 3) if sell else 0,
                "net_profit": round(net, 2), "margin": round(net / alis * 100, 1) if alis else 0}

    out = [row("vinted", f["satis_p25"], f["net_kar_tutucu"]),
           row("vinted (medyan)", f["satis_medyan"], f["net_kar_medyan"])]
    for cc, net, n in re.findall(r"([A-Z]{2}):([+-]?\d+)\(n(\d+)\)", f.get("ulke_net") or ""):
        # net = satis - alis - (paketleme + (iade + komisyon) * satis)  ->  satis geri hesaplanir (maliyet.json)
        sell = (float(net) + alis + COST["paketleme"] + COST["giden_kargo"]) / (1 - COST["iade_payi_oran"] - COST["satis_komisyonu_oran"])
        out.append(row(f"vinted.{cc.lower()} (n={n})", sell, float(net)))
    return out


def product_row(f: dict, gen_id) -> dict:
    """Firsattan TATANGA urun kaydi. Fiyat onerisi = gercek satislarin medyani; kar = TUTUCU (P25) kar."""
    title = f["baslik"] or f"{f['marka']} {f.get('tur') or ''}".strip()
    if f["platform"] == "Sellpy" and f.get("beden"):
        title = f"{title}, Größe {f['beden'].split('-')[-1]}"
    alis = f["alis_toplam"] or 0
    return {
        "id": gen_id("PROD"),
        "source_platform": f["platform"].lower(),
        "source_url": f["url"],
        "source_id": f["firsat_id"],
        "title": title,
        "price": f["fiyat"],
        "brand": f["marka"],
        "size": f.get("beden"),
        "condition": KOND_TR.get(f["kondisyon"], f["kondisyon"]),
        "category": f["kategori"],
        "images_json": json.dumps([f["gorsel"]] if f.get("gorsel") else []),
        "estimated_sell_price": round(f["satis_medyan"] or 0, 2),
        "profit_euro": round(f["net_kar_tutucu"] or 0, 2),
        "profit_margin": round((f["net_kar_tutucu"] or 0) / alis * 100, 1) if alis else 0,
        "total_cost": round(alis, 2),
        "recommendation": "buy",
        "best_sell_platform": "vinted",
        # urun detayindaki "Platform Bazli Arbitraj" tablosu satir listesi bekler
        "arbitrage_json": json.dumps(arb_rows(f), ensure_ascii=False),
        "kanit_json": json.dumps({
            "kaynak": "nokta_atis", "tarama": f["run_id"], "firsat_id": f["firsat_id"],
            "satis_yonu": "Vinted (7 ulke havuzu)", "satis_p25": f["satis_p25"], "satis_medyan": f["satis_medyan"],
            "net_kar_tutucu": f["net_kar_tutucu"], "net_kar_medyan": f["net_kar_medyan"], "p30": f["p30"],
            "beklenen_kar_30g": f["beklenen_kar_30g"], "tahmin": f"{f['tahmin_seviye']} ({f['tahmin_kapsam']})",
            "satis_n": f["satis_n"], "kanit_satis_fiyatlari": json.loads(f.get("kanit_json") or "[]"),
            "ulke_net": f.get("ulke_net"), "isaretler": f.get("isaretler"), "alis_ulke": f["ulke"],
        }, ensure_ascii=False),
        "scraped_at": datetime.now().isoformat(),
        "status": "scraped",
        "publish_condition": PUBLISH_COND.get(f["kondisyon"], "very_good"),
    }
