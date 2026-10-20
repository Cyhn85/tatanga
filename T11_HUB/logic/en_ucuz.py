"""
EN UCUZU BUL (Chrome eklentisi -> TATANGA, 2026-10-20). Web'de gorulen bir urunun ayni/benzerini, toplayicilarimizin
TUM platform arsivlerinde (Vinted 7 ulke + KA + eBay 7 pazar + Sellpy) ve gorsel dizininde arar; alis TOPLAM
maliyetine (alici ucreti + kargo dahil) gore siralar ve gercek Vinted satis fiyatiyla karsilastirir.

Eslesme kaliteleri (en guclu -> zayif):
  model   : marka + model sozlugunde ayni model (ModelMatcher)          -> fiyat karsilastirmasi gecerli
  gorsel  : CLIP 'ayni fotograf' / 'ayni urun olabilir' / 'cok benzer'   -> goz kontrolu gerekir
  kelime  : marka + basliktaki anlamli kelimelerin cogu                  -> zayif, bilgi amacli
Uydurma yok: model bulunamazsa sonuc 'kelime' / 'gorsel' olarak etiketlenir.
"""

from __future__ import annotations

import base64
import io
import json
import re
import sqlite3
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "istatistik"
OBS = Path(__file__).resolve().parents[1] / "ops" / "hetzner_observer"
VINTED_TLD = {"DE": "de", "AT": "at", "FR": "fr", "BE": "be", "NL": "nl", "IT": "it", "SE": "se", "PL": "pl",
              "ES": "es", "GB": "co.uk", "UK": "co.uk"}
DUR = {"ve", "und", "the", "and", "mit", "for", "für", "gr", "size", "grosse", "größe", "neu", "new", "herren",
       "damen", "men", "women", "der", "die", "das", "de", "la", "le", "et", "von", "in", "a", "en", "original"}


def _ctx():
    sys.path.insert(0, str(OBS))
    import analyze as A
    import capraz as C
    import zeka_urunler as Z
    return A, C, Z


def _maliyet(platform: str, fiyat: float, kargo: float | None, c: dict) -> float:
    if platform == "Vinted":
        return fiyat + c["alici_koruma_sabit"] + c["alici_koruma_oran"] * fiyat + c["gelen_kargo"]
    if platform == "Kleinanzeigen":
        return fiyat + c["ka_koruma_sabit"] + c["ka_koruma_oran"] * fiyat + c["gelen_kargo"]
    if platform == "Sellpy":
        return fiyat + c["sellpy_kargo"]
    return fiyat + (kargo if kargo is not None else c["gelen_kargo"])


_BEDEN_RE = re.compile(r"(?:\bgr\.?|\bgröße|\bgroesse|\bsize|\btaille|\btaglia|\btalla|\beu|\bstorlek|\brozmiar)\s*:?\s*"
                       r"(\d{2}(?:[.,]5)?|xxs|xs|s|m|l|xl|xxl|3xl)\b", re.I)


def _beden(t: str | None) -> str | None:
    m = _BEDEN_RE.search(t or "")
    return m.group(1).upper().replace(",", ".") if m else None


# Renk esanlamlilari (ayni varyant icin baslik dili farkli olabilir)
RENK = [
    {"schwarz", "black", "noir", "noire", "noires", "nero", "nera", "negro", "negra", "zwart", "svart", "czarny", "czarne"},
    {"weiss", "weiß", "white", "blanc", "blanche", "bianco", "bianca", "blanco", "wit", "vit", "vita", "bialy", "białe"},
    {"rot", "red", "rouge", "rosso", "rojo", "rood", "röd", "czerwony"},
    {"blau", "blue", "bleu", "blu", "azul", "blauw", "blå", "niebieski", "navy", "marine"},
    {"grün", "gruen", "green", "vert", "verde", "groen", "grön", "zielony", "olive", "khaki"},
    {"braun", "brown", "marron", "marrone", "marrón", "bruin", "brun", "brazowy", "cognac", "tan"},
    {"grau", "grey", "gray", "gris", "grigio", "grijs", "grå", "szary"},
    {"beige", "creme", "cream", "ecru", "sand"},
    {"rosa", "pink", "rose", "roze"},
]
_RENK_KOK = {w: i for i, grup in enumerate(RENK) for w in grup}


def _varyant_kelimeleri(baslik: str, brand: str | None, model: str | None, A) -> list[str]:
    """Sorgunun ayirt edici kelimeleri: marka/model/tur/beden/genel kelimeler disinda kalanlar (desen, seri, renk)."""
    cikar = set(_kelimeler(brand or "")) | set(_kelimeler(model or ""))
    genel = {"schuhe", "schuh", "shoes", "sneaker", "sneakers", "boots", "stiefel", "jacke", "jacket", "classic",
             "herren", "damen", "unisex", "gr", "size", "eu", "uk", "us", "low", "high", "mid", "neu", "neuwertig",
             "original", "orginal", "top", "zustand", "sehr", "gut", "vintage"}
    out = []
    for w in _kelimeler(baslik):
        if w in cikar or w in genel or w.isdigit() or A.match_type(w):
            continue
        out.append(w)
    return out


def _varyant_uyumu(sorgu_var: list[str], t: str) -> float | None:
    if not sorgu_var:
        return None
    kel = set(_kelimeler(t))
    renkler = {_RENK_KOK[w] for w in kel if w in _RENK_KOK}
    tut = 0
    for w in sorgu_var:
        if w in kel or (w in _RENK_KOK and _RENK_KOK[w] in renkler):
            tut += 1
    return tut / len(sorgu_var)


def _kelimeler(t: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9äöüß]+", (t or "").lower()) if len(w) > 2 and w not in DUR]


def ara(baslik: str, marka: str | None = None, fiyat: float | None = None, para: str = "EUR",
        gorsel_url: str | None = None, gorsel_b64: str | None = None, en_fazla: int = 30,
        kaynak_url: str | None = None) -> dict:
    A, C, Z = _ctx()
    mt = A.ModelMatcher()
    c = C.costs()
    arsiv = sqlite3.connect(f"file:{ROOT / 'arsiv.db'}?mode=ro", uri=True)
    arsiv.row_factory = sqlite3.Row
    rates = A.fx_rates(arsiv)
    table = Z.brand_table()
    brand = Z.canonical_brand(marka or "", baslik or "", table)
    model, line = mt.match(brand, baslik or "") if brand else (None, None)
    typ = A.match_type(A.norm_text(baslik or ""))
    sorgu_kel = [w for w in _kelimeler(baslik) if not brand or w not in brand.lower()]
    sorgu_beden = _beden(baslik)
    sorgu_var = _varyant_kelimeleri(baslik, brand, model, A) if model else []
    km = re.search(r"vinted\.[a-z.]+/items/(\d+)", kaynak_url or "")
    kaynak_anahtar = ("vinted:" + km.group(1)) if km else (kaynak_url or "").split("?")[0]
    ayakkabi = typ in C.TYPE_CAT and "schuhe" in C.TYPE_CAT[typ]
    sonuc: dict[str, dict] = {}
    elenen = {"cocuk": 0, "kondisyon": 0, "yem_fiyat": 0}

    def ekle(platform, ulke, url, t, p, cur, kond, eslesme, kargo=None, gorsel=None, benzerlik=None, beden=None):
        rate = rates.get((cur or "EUR").upper()) or (1.0 if (cur or "EUR").upper() == "EUR" else 0)
        if not url or not p or not rate:
            return
        eur = p / rate
        if eur < C.BAIT_PRICE:
            elenen["yem_fiyat"] += 1
            return                                  # 1 EUR "pazarlik yemi" ilanlari (kullanici kurali)
        # cocuk urunu: baslik (yas / Kinder ...) ya da 35 alti ayakkabi numarasi ya da cocuk bedeni
        b_ilan = str(beden or _beden(t) or "").strip()
        try:
            kucuk_ayak = bool(re.match(r"^\d{2}(\.5)?$", b_ilan)) and float(b_ilan) < 35
        except ValueError:
            kucuk_ayak = False
        if C.CHILD_TITLE_RE.search(t or "") or kucuk_ayak or A.is_child_size(beden, "schuhe" if ayakkabi else ""):
            elenen["cocuk"] += 1
            return
        kt = " ".join(re.findall(r"[^\W_]+", (kond or "").lower()))
        tier = (A.norm_condition(kond) or Z.KOND_EXTRA.get(A.norm_text(kond or "")) or A.norm_condition(kt)
                or Z.KOND_EXTRA.get(kt))
        if kond and not tier:
            elenen["kondisyon"] += 1               # yalniz ilk 3 kondisyon (yeni etiketli / yeni / cok iyi)
            return
        vm = re.search(r"vinted\.[a-z.]+/items/(\d+)", url)
        url_anahtar = ("vinted:" + vm.group(1)) if vm else url   # ayni Vinted ilani farkli alan adlarinda tek
        if kaynak_anahtar and (url_anahtar == kaynak_anahtar or url.split("?")[0] == kaynak_anahtar):
            return                                   # kullanicinin baktigi ilanin kendisi
        kayit = {"platform": platform, "ulke": ulke, "url": url, "baslik": (t or "")[:120], "fiyat": round(p, 2),
                 "para": (cur or "EUR").upper(), "fiyat_eur": round(eur, 2), "kondisyon": kond, "kademe": tier,
                 "toplam_eur": round(_maliyet(platform, eur, kargo, c), 2), "eslesme": eslesme, "gorsel": gorsel,
                 "benzerlik": benzerlik, "beden": b_ilan or None,
                 "varyant": _varyant_uyumu(sorgu_var, t),
                 "beden_uyumu": (None if not sorgu_beden or not b_ilan else b_ilan.upper() == sorgu_beden)}
        eski = sonuc.get(url_anahtar)
        sira = {"model": 0, "gorsel": 1, "kelime": 2}
        if not eski or sira[eslesme] < sira[eski["eslesme"]] or (
                sira[eslesme] == sira[eski["eslesme"]] and kayit["toplam_eur"] < eski["toplam_eur"]):
            sonuc[url_anahtar] = kayit

    def esles(b, t):
        """('model'|'kelime'|None) - ayni marka sart."""
        if not brand or (b or "").strip().lower() != brand.lower() and not (b or "").lower().startswith(brand.lower()):
            return None
        if model:
            m2, _ = mt.match(brand, t or "")
            return "model" if m2 == model else None
        kel = _kelimeler(t)
        if sorgu_kel and sum(1 for w in sorgu_kel if w in kel) >= max(1, round(len(sorgu_kel) * 0.6)):
            return "kelime"
        return None

    if brand:
        # Vinted: son 7 gun katalog ornekleri + takipteki aktif ilanlar (gozlemci)
        for r in arsiv.execute("SELECT item_id, cell, title, price, COALESCE(currency,'EUR') cur, condition, country, size "
                               "FROM catalog_samples WHERE lower(brand)=lower(?) AND ts >= datetime('now','-7 day') "
                               "AND COALESCE(is_child,0)=0", (brand,)):
            e = esles(brand, r["title"])
            if e:
                tld = VINTED_TLD.get(r["country"], "de")
                ekle("Vinted", r["country"], f"https://www.vinted.{tld}/items/{r['item_id']}", r["title"], r["price"],
                     r["cur"], r["condition"], e, beden=r["size"])
        obs = ROOT / "vinted" / "observe.db"
        if obs.exists():
            o = sqlite3.connect(f"file:{obs}?mode=ro", uri=True)
            o.row_factory = sqlite3.Row
            for r in o.execute("SELECT url, title, price, COALESCE(currency,'EUR') cur, condition, country, brand, size "
                               "FROM listings WHERE state='active' AND lower(brand)=lower(?)", (brand,)):
                e = esles(r["brand"], r["title"])
                if e:
                    ekle("Vinted", r["country"], r["url"], r["title"], r["price"], r["cur"], r["condition"], e,
                         beden=r["size"])
            o.close()
        alis = ROOT / "alis_arsiv.db"
        if alis.exists():
            a = sqlite3.connect(f"file:{alis}?mode=ro", uri=True)
            a.row_factory = sqlite3.Row
            for r in a.execute("SELECT url, title, COALESCE(detail_price, price) p, zustand, COALESCE(marke, brand) b, groesse "
                               "FROM ka_ads WHERE detail_status='ok' AND last_seen >= datetime('now','-3 day') "
                               "AND lower(COALESCE(marke, brand))=lower(?)", (brand,)):
                e = esles(r["b"], r["title"])
                if e:
                    ekle("Kleinanzeigen", "DE", r["url"], r["title"], r["p"], "EUR", r["zustand"], e, beden=r["groesse"])
            for r in a.execute("SELECT e.url, e.title, e.price, COALESCE(e.currency,'EUR') cur, e.condition, e.country, "
                               "e.ship_cost, e.brand FROM eb_items e LEFT JOIN eb_track t USING(item_id) "
                               "WHERE lower(e.brand)=lower(?) AND e.last_seen >= datetime('now','-3 day') "
                               "AND (e.end_date IS NULL OR e.end_date > datetime('now')) "
                               "AND COALESCE(t.state,'active')='active'", (brand,)):
                e = esles(r["brand"], r["title"])
                if e:
                    ekle("eBay", r["country"], r["url"], r["title"], r["price"], r["cur"], r["condition"], e,
                         kargo=r["ship_cost"])
            if not model:
                for r in a.execute("SELECT url, brand, type, price, condition FROM sp_items WHERE for_sale=1 AND "
                                   "reserved=0 AND last_seen >= datetime('now','-3 day') AND lower(brand)=lower(?)",
                                   (brand,)):
                    t = f"{r['brand']} {r['type'] or ''}"
                    e = esles(r["brand"], t)
                    if e:
                        ekle("Sellpy", "DE", r["url"], t, r["price"], "EUR", r["condition"], e)
            a.close()

    # GORSEL: sayfanin ana gorseli ya da ekran goruntusu -> CLIP dizini (hala yayinda olan ilanlar)
    gorsel_not = None
    try:
        if gorsel_b64 is None and gorsel_url:
            import requests
            rr = requests.get(gorsel_url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
            if rr.status_code == 200 and len(rr.content) > 2000:
                gorsel_b64 = base64.b64encode(rr.content).decode()
        if gorsel_b64:
            from logic import gorsel_arama as G
            g = G.similar_to_upload(gorsel_b64, k=40)
            for s in g.get("sonuclar", []):
                if s.get("etiket") in ("ayni fotograf", "ayni urun olabilir", "cok benzer"):
                    plat = s.get("platform") or "?"
                    ekle(plat, s.get("ulke"), s.get("ilan_url"), s.get("baslik"), s.get("fiyat"), s.get("para"),
                         s.get("kondisyon"), "gorsel", gorsel=s.get("gorsel_url"), benzerlik=s.get("benzerlik"))
            gorsel_not = f"{g.get('dizin_aktif', 0)} aktif ilanda gorsel arandi"
    except Exception as exc:
        gorsel_not = f"gorsel arama yapilamadi: {type(exc).__name__}"

    # gercek Vinted satislari (ayni model)
    satis = None
    if brand and model:
        fiyatlar = []
        for r in arsiv.execute("SELECT title, COALESCE(final_price, price) p, COALESCE(currency,'EUR') cur FROM listings "
                               "WHERE state='sold' AND lower(brand)=lower(?)", (brand,)):
            m2, _ = mt.match(brand, r["title"] or "")
            rate = rates.get(r["cur"]) or 0
            if m2 == model and rate and r["p"]:
                fiyatlar.append(r["p"] / rate)
        if fiyatlar:
            fiyatlar.sort()
            satis = {"n": len(fiyatlar), "medyan": round(statistics.median(fiyatlar), 2),
                     "p25": round(fiyatlar[len(fiyatlar) // 4], 2),
                     "guven": "yeterli" if len(fiyatlar) >= C.MIN_SALES["marka·model"] else "az veri"}
    arsiv.close()

    # sira: guclu eslesme once; beden verildiyse ayni beden once (bilinmeyen ortada, uyusmayan sonda); sonra toplam
    for r in sonuc.values():
        r["ayni_varyant"] = None if r["varyant"] is None else r["varyant"] >= 0.5
    sirali = sorted(sonuc.values(), key=lambda r: ({"model": 0, "gorsel": 1, "kelime": 2}[r["eslesme"]] > 1,
                                                    {True: 0, None: 1, False: 2}[r["ayni_varyant"]] if sorgu_var else 0,
                                                    {True: 0, None: 1, False: 2}[r["beden_uyumu"]] if sorgu_beden else 0,
                                                    r["toplam_eur"]))
    platform_en_ucuz = {}
    for r in sirali:
        if r["eslesme"] != "kelime" and r["platform"] not in platform_en_ucuz:
            platform_en_ucuz[r["platform"]] = {"toplam_eur": r["toplam_eur"], "url": r["url"]}
    sayfa_eur = None
    if fiyat:
        rate = rates.get((para or "EUR").upper()) or 0
        sayfa_eur = round(fiyat / rate, 2) if rate else None
    def _iyi(r, beden_sart):
        return (r["eslesme"] != "kelime" and (not sorgu_var or r["ayni_varyant"] or r["eslesme"] == "gorsel")
                and (not beden_sart or not sorgu_beden or r["beden_uyumu"] is True))
    en_ucuz = next((r for r in sirali if _iyi(r, True)), None) or next((r for r in sirali if _iyi(r, False)), None)
    ayni_varyant_yok = bool(sorgu_var) and en_ucuz is None
    return {
        "ayni_varyant_yok": ayni_varyant_yok,
        "sorgu": {"baslik": baslik, "marka": brand, "model": model, "seri": line, "tur": typ, "beden": sorgu_beden,
                  "varyant": sorgu_var,
                  "sayfa_fiyat_eur": sayfa_eur},
        "elenen": elenen,
        "eslesme_seviyesi": "model" if model else ("marka+kelime" if brand else "yalniz gorsel"),
        "en_ucuz": en_ucuz,
        "tasarruf_eur": round(sayfa_eur - en_ucuz["toplam_eur"], 2) if (sayfa_eur and en_ucuz) else None,
        "platform_en_ucuz": platform_en_ucuz,
        "gercek_satis": satis,
        "gorsel_not": gorsel_not,
        "toplam_sonuc": len(sirali),
        "sonuclar": sirali[:en_fazla],
        "not": ("Toplam = alis + alici ucreti + kargo (olculmus degerler). 'gorsel' eslesmeleri goz kontrolu ister; "
                "'kelime' eslesmeleri zayiftir. Arsiv toplayicilarin son 3-7 gununu kapsar; guncel olmayan ilan "
                "olabilir -> 'Canli tara' ile yenile."),
    }
