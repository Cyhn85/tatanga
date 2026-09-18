"""
Reklam/kampanya motoru — EN/DE/TR (saf, deterministik, ucretsiz).

Marka kimlik kartindan (logic/brand_identity.py) beslenir. LLM KULLANMAZ:
sablon + gercek urun verisi. "API en sonda" kuralina sadik — ileride Groq
sadece varyasyon zenginlestirmek icin EKLENEBILIR, zorunlu degil.

TEMEL KURAL — KANITSIZ IDDIA URETILMEZ:
  1. Her kampanya bir GERCEK veri alanina dayanir (indirim yuzdesi ancak
     price_before_reprice varsa hesaplanir; eco sayilari ancak canli uctan
     gelirse yazilir).
  2. Uretilen HER metin `brand_identity.check_claim()` bekcisinden gecer.
     'forbidden' ihlali olan varyant YAYINLANMAZ — sessizce duzeltilmez,
     dusurulur ve gerekcesi `rejected` listesinde raporlanir.
  3. Ciktilar TASLAK'tir (status="draft"). Insan onayi olmadan hicbir yere
     gitmez (Telegram onay odasi #151, ticker #145).

Saf modul: DB/ag bilmez. Urunler disaridan dict listesi olarak verilir.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from . import brand_identity as brand

SUPPORTED_LANGS = ("de", "en", "tr")

# Bir indirimi duyurmaya deger kilan alt esik (altinda kampanya uretilmez —
# "%3 indirim" duyurusu markayi ucuzlatir, kullaniciyi da yanlis yonlendirir).
MIN_DISCOUNT_PCT = 15


@dataclass
class CampaignDraft:
    kind: str                  # "sale" | "new_arrival" | "category_spotlight" | "eco"
    lang: str
    headline: str
    body: str
    cta: str
    evidence: str              # bu iddianin NEDEN dogru oldugu (denetlenebilirlik)
    product_ids: list[str] = field(default_factory=list)
    status: str = "draft"      # insan onayi bekler — asla otomatik yayinlanmaz
    warnings: list[str] = field(default_factory=list)


@dataclass
class CampaignResult:
    drafts: list[CampaignDraft] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)   # bekcinin dusurdukleri
    skipped: list[str] = field(default_factory=list)    # veri yetersizligi


# --------------------------------------------------------------------- sablonlar
# {n}=adet, {pct}=yuzde, {cat}=kategori, {items}/{co2}=canli eco sayilari
_T: dict[str, dict[str, dict[str, str]]] = {
    "sale": {
        "de": {"headline": "Bis zu {pct}% reduziert",
               "body": "{n} Artikel im Preis gesenkt. Gebraucht, geprueft, aus Berlin.",
               "cta": "Zu den reduzierten Artikeln"},
        "en": {"headline": "Up to {pct}% off",
               "body": "{n} items reduced. Second-hand, checked, from Berlin.",
               "cta": "See reduced items"},
        "tr": {"headline": "{pct}%'e varan indirim",
               "body": "{n} urunun fiyati dustu. Ikinci el, kontrol edilmis, Berlin'den.",
               "cta": "Indirimli urunlere git"},
    },
    "new_arrival": {
        "de": {"headline": "Neu eingetroffen",
               "body": "{n} neue Artikel warten auf dich.",
               "cta": "Neuheiten ansehen"},
        "en": {"headline": "Just arrived",
               "body": "{n} new items are waiting for you.",
               "cta": "See what's new"},
        "tr": {"headline": "Yeni geldi",
               "body": "{n} yeni urun seni bekliyor.",
               "cta": "Yenilere goz at"},
    },
    "category_spotlight": {
        "de": {"headline": "{cat} bei uns",
               "body": "{n} Artikel in {cat}. Gebrauchte Mode aus Berlin.",
               "cta": "{cat} entdecken"},
        "en": {"headline": "{cat} at our shop",
               "body": "{n} items in {cat}. Second-hand fashion from Berlin.",
               "cta": "Explore {cat}"},
        "tr": {"headline": "{cat} kategorisi",
               "body": "{cat} icinde {n} urun. Berlin'den ikinci el moda.",
               "cta": "{cat} kesfet"},
    },
    "eco": {
        "de": {"headline": "Gemeinsam wiederverwendet",
               "body": "{items} Artikel wiederverwendet, {co2} kg CO2 eingespart.",
               "cta": "Unsere Bilanz ansehen"},
        "en": {"headline": "Reused together",
               "body": "{items} items reused, {co2} kg CO2 saved.",
               "cta": "See our impact"},
        "tr": {"headline": "Birlikte yeniden kullandik",
               "body": "{items} urun yeniden kullanildi, {co2} kg CO2 tasarrufu.",
               "cta": "Bilancoyu gor"},
    },
    # Marka anlatisi: "Climate Smart Solutions" ne demek. Bilincli olarak SAYISIZ
    # ve ölçüsüz — "klimaneutral", "CO2-frei", "%100 surdurulebilir" gibi ifadeler
    # somut hesap ister ve bekci bunlari isaretler. Burada yalnizca ISIN KENDISI
    # anlatiliyor: kullanilmis bir urunu yeniden dolasima sokmak yeni uretim
    # gerektirmez. Bu iddia degil, tanimdir.
    "eco_story": {
        "de": {"headline": "Climate Smart Solutions",
               "body": "Jedes Teil, das weiterlebt, muss nicht neu produziert werden. "
                       "Wir pruefen, fotografieren und bringen Gebrauchtes zurueck in Umlauf.",
               "cta": "Mehr ueber uns"},
        "en": {"headline": "Climate Smart Solutions",
               "body": "Every item that lives on does not have to be produced again. "
                       "We check, photograph and bring used goods back into circulation.",
               "cta": "More about us"},
        "tr": {"headline": "Climate Smart Solutions",
               "body": "Yasamaya devam eden her parca, yeniden uretilmek zorunda kalmaz. "
                       "Kontrol ediyor, fotografliyor ve kullanilmis esyayi tekrar dolasima sokuyoruz.",
               "cta": "Hakkimizda"},
    },
    # Fiyat vurgusu: ustunluk iddiasi ("en ucuz") YASAK. Onun yerine GERCEK
    # veriden gelen en dusuk fiyat gosterilir — dogrulanabilir ve yasal.
    "price_focus": {
        "de": {"headline": "Schon ab {min_price} EUR",
               "body": "{n} Artikel im Angebot. Preis steht dran, kein Kleingedrucktes.",
               "cta": "Preise ansehen"},
        "en": {"headline": "From {min_price} EUR",
               "body": "{n} items available. The price you see is the price.",
               "cta": "See prices"},
        "tr": {"headline": "{min_price} EUR'dan baslayan",
               "body": "{n} urun listede. Fiyat ne yaziyorsa o, surpriz yok.",
               "cta": "Fiyatlara bak"},
    },
}


def _guard(draft: CampaignDraft, template: dict) -> Optional[str]:
    """
    Taslagi bekciden gecirir. Yasak ihlal varsa gerekce dondurur (=dusur).

    Sayilar iki farkli yerden gelebilir ve ikisi ayni sey DEGIL:
      - SABIT sayi: sablon metninin kendisine yazilmis -> yasak (gercekle kayar).
      - HESAPLANAN sayi: gercek urun verisinden turetilip yerlestirilmis -> serbest.
    Bu yuzden sabit-sayi denetimi HAM SABLON uzerinde, digerleri islenmis metin
    uzerinde yapilir. (Aksi halde "{n} Artikel" sablonu, dogru calisirken bile
    'sabit istatistik' sanilip dusuyordu.)
    """
    rendered = f"{draft.headline}. {draft.body} {draft.cta}"
    raw = " ".join(template.values())

    violations = brand.check_claim(rendered, lang=draft.lang, stats_from_live_source=True)
    violations += [v for v in brand.check_claim(raw, lang=draft.lang)
                   if v.category == "hardcoded_stat"]

    forbidden = [v for v in violations if v.severity == "forbidden"]
    if forbidden:
        return f"{draft.kind}/{draft.lang}: " + "; ".join(
            f"{v.category}('{v.matched}')" for v in forbidden)
    draft.warnings = [f"{v.category}: {v.matched}" for v in violations if v.severity == "warn"]
    return None


def _discount_pct(product: dict) -> Optional[int]:
    """Gercek indirim yuzdesi — SADECE onceki fiyat kayitliysa. Yoksa None."""
    before = product.get("price_before_reprice")
    now = product.get("price")
    if not before or not now or before <= 0 or now >= before:
        return None
    return int(round((before - now) / before * 100))


def generate_campaigns(
    products: list[dict],
    *,
    lang: str = "de",
    eco_stats: Optional[dict] = None,
    top_category: bool = True,
) -> CampaignResult:
    """
    Gercek urun verisinden kampanya TASLAKLARI uretir.

    products: her biri en az {id, title, price} — indirim icin ayrica
              price_before_reprice, kategori icin category, yenilik icin listed_at.
    eco_stats: {"items": int, "co2": float} — SADECE canli uctan okunmus
               degerler verilmeli (brand_identity.dynamic_claim('eco_stats')).
               None ise eco kampanyasi hic uretilmez.
    """
    result = CampaignResult()
    if lang not in SUPPORTED_LANGS:
        result.skipped.append(f"desteklenmeyen dil: {lang}")
        return result
    products = products or []

    # --- 1) Indirim kampanyasi: sadece KANITLI yuzdeler ---
    discounted = [(p, pct) for p in products if (pct := _discount_pct(p)) is not None]
    meaningful = [(p, pct) for p, pct in discounted if pct >= MIN_DISCOUNT_PCT]
    if meaningful:
        best = max(pct for _, pct in meaningful)
        t = _T["sale"][lang]
        draft = CampaignDraft(
            kind="sale", lang=lang,
            headline=t["headline"].format(pct=best),
            body=t["body"].format(n=len(meaningful)),
            cta=t["cta"],
            evidence=f"{len(meaningful)} urunde price_before_reprice kayitli; "
                     f"en yuksek gercek indirim %{best}",
            product_ids=[p["id"] for p, _ in meaningful],
        )
        if (reason := _guard(draft, t)):
            result.rejected.append(reason)
        else:
            result.drafts.append(draft)
    elif discounted:
        result.skipped.append(
            f"indirim var ama hepsi %{MIN_DISCOUNT_PCT} esiginin altinda -> duyurulmadi")
    else:
        result.skipped.append(
            "indirim kampanyasi yok: hicbir uruns price_before_reprice kayitli degil "
            "(aging_reprice calisincaya kadar indirim iddiasi KANITSIZ)")

    # --- 2) Yeni gelenler ---
    fresh = [p for p in products if p.get("listed_at")]
    if fresh:
        t = _T["new_arrival"][lang]
        draft = CampaignDraft(
            kind="new_arrival", lang=lang,
            headline=t["headline"], body=t["body"].format(n=len(fresh)), cta=t["cta"],
            evidence=f"{len(fresh)} urunde gercek listed_at damgasi var",
            product_ids=[p["id"] for p in fresh],
        )
        if (reason := _guard(draft, t)):
            result.rejected.append(reason)
        else:
            result.drafts.append(draft)
    else:
        result.skipped.append("yeni gelen kampanyasi yok: listed_at damgali urun yok")

    # --- 3) Kategori vitrini (en dolu kategori) ---
    if top_category:
        counts: dict[str, list[str]] = {}
        for p in products:
            cat = (p.get("category") or "").strip()
            if cat:
                counts.setdefault(cat, []).append(p["id"])
        if counts:
            cat, ids = max(counts.items(), key=lambda kv: len(kv[1]))
            t = _T["category_spotlight"][lang]
            draft = CampaignDraft(
                kind="category_spotlight", lang=lang,
                headline=t["headline"].format(cat=cat),
                body=t["body"].format(n=len(ids), cat=cat),
                cta=t["cta"].format(cat=cat),
                evidence=f"'{cat}' kategorisinde gercekten {len(ids)} urun var",
                product_ids=ids,
            )
            if (reason := _guard(draft, t)):
                result.rejected.append(reason)
            else:
                result.drafts.append(draft)
        else:
            result.skipped.append("kategori vitrini yok: urunlerde kategori bos")

    # --- 3b) Marka anlatisi (Climate Smart Solutions) ---
    # Sayi icermez, olcum iddia etmez -> her zaman uretilebilir. Marka ne is
    # yaptigini anlatmadan sadece urun listelerse akilda kalmaz.
    if products:
        t = _T["eco_story"][lang]
        draft = CampaignDraft(
            kind="eco_story", lang=lang,
            headline=t["headline"], body=t["body"], cta=t["cta"],
            evidence="marka anlatisi — sayisal iddia icermez, is modelinin tanimi",
        )
        if (reason := _guard(draft, t)):
            result.rejected.append(reason)
        else:
            result.drafts.append(draft)

    # --- 3c) Fiyat vurgusu: GERCEK en dusuk fiyattan ---
    # "En ucuz biziz" YASAK (kanitlanamaz). "12 EUR'dan baslayan" ise
    # katalogdan dogrulanabilir bir olgu.
    fiyatlar = [p["price"] for p in products if p.get("price") and p["price"] > 0]
    if fiyatlar:
        min_price = min(fiyatlar)
        t = _T["price_focus"][lang]
        draft = CampaignDraft(
            kind="price_focus", lang=lang,
            headline=t["headline"].format(min_price=f"{min_price:.0f}"),
            body=t["body"].format(n=len(fiyatlar)),
            cta=t["cta"],
            evidence=f"katalogdaki gercek en dusuk fiyat {min_price:.2f} EUR "
                     f"({len(fiyatlar)} urun uzerinden)",
            product_ids=[p["id"] for p in products if p.get("price") == min_price],
        )
        if (reason := _guard(draft, t)):
            result.rejected.append(reason)
        else:
            result.drafts.append(draft)
    else:
        result.skipped.append("fiyat vurgusu yok: gecerli fiyatli urun bulunamadi")

    # --- 4) Eco: SADECE canli sayilarla ---
    if eco_stats and (eco_stats.get("items") or eco_stats.get("co2")):
        t = _T["eco"][lang]
        draft = CampaignDraft(
            kind="eco", lang=lang,
            headline=t["headline"],
            body=t["body"].format(items=eco_stats.get("items", 0), co2=eco_stats.get("co2", 0)),
            cta=t["cta"],
            evidence="sayilar canli /api/eco-impact ucundan okundu (sabit yazilmadi)",
        )
        if (reason := _guard(draft, t)):
            result.rejected.append(reason)
        else:
            result.drafts.append(draft)
    else:
        result.skipped.append(
            "eco kampanyasi yok: canli sayi verilmedi (sabit sayi yazmak YASAK)")

    return result


def generate_all_languages(products: list[dict], **kw) -> dict[str, CampaignResult]:
    """DE/EN/TR uc dilde ayni gercek veriden taslak uretir."""
    return {lang: generate_campaigns(products, lang=lang, **kw) for lang in SUPPORTED_LANGS}
