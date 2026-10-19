"""
TEKLIF AKISI (2026-10-19). Saticiya teklif HAZIRLAR; hicbir mesaji GONDERMEZ.

Kurallar:
  - Giris yok / otomatik mesaj yok: taslak kullaniciya gosterilir, kullanici kopyalayip platformda ELLE gonderir.
  - Teklif tutari kar zekasina baglidir: her tutar icin tutucu net kar yeniden hesaplanir (zeka_net_kar, gercek
    Vinted satislarinin P25'i). Onerilen tutar: 20 EUR tutucu kar birakan fiyat, ilan fiyatinin %70'inden asagi degil
    (daha dusugu cogu satici icin hakaret sayilir ve Vinted teklif kutusu cok dusuk teklifi reddeder).
  - Groq'a giden veri: YALNIZ ilan basligi, ilan fiyati, teklif tutari, para birimi, dil. Kullanici/satici verisi yok.
    Ayrica onay bayragi gerekir: GROQ_API_KEY + GROQ_MESSAGE_DRAFT_ENABLED=true. Kapaliysa / hata olursa sablon.

Durumlar: hazir -> gonderildi -> (karsi_teklif) -> kabul | ret -> alindi | vazgecildi
"""

from __future__ import annotations

import json
import math
import os
from datetime import datetime

DURUMLAR = ("hazir", "gonderildi", "karsi_teklif", "kabul", "ret", "alindi", "vazgecildi")
BEKLEYEN = ("hazir", "gonderildi", "karsi_teklif", "kabul")       # "teklif bekliyor" sekmesi
HEDEF_KAR = 20.0           # kullanici kurali: cok karli = tutucu net >= 20 EUR
MIN_ORAN = 0.70            # ilan fiyatinin altina inilmeyecek oran

# Alis tarafinda fiyata bagli ucret orani (sabit kisim zaten zeka_alis_toplam icinde; maliyet.json ile ayni)
UCRET_ORANI = {"vinted": 0.05, "kleinanzeigen": 0.045}

# Platform -> saticinin dili (Vinted alan adi ulkesi). BE: Vinted Belcika'da arayuz FR/NL; FR secilir.
DIL = {"vinted": "de", "vinted_at": "de", "vinted_fr": "fr", "vinted_be": "fr", "vinted_it": "it",
       "vinted_es": "es", "vinted_nl": "nl", "vinted_pl": "pl", "vinted_se": "sv", "vinted_uk": "en",
       "kleinanzeigen": "de", "ebay": "de", "sellpy": "de", "willhaben": "de", "leboncoin": "fr", "tradera": "sv"}
DIL_ADI = {"de": "Deutsch", "fr": "Französisch", "it": "Italienisch", "es": "Spanisch", "nl": "Niederländisch",
           "pl": "Polnisch", "sv": "Schwedisch", "en": "Englisch"}

# Sablon yedegi (Groq kapali/hatali). Kisa, kibar, baski yok.
SABLON = {
    "de": "Hallo! Ich interessiere mich für „{title}“. Wäre {offer} für Sie in Ordnung? Ich würde direkt kaufen. Danke!",
    "fr": "Bonjour ! Je suis intéressé(e) par « {title} ». Seriez-vous d'accord pour {offer} ? J'achète tout de suite. Merci !",
    "it": "Ciao! Sono interessato/a a “{title}”. Andrebbe bene {offer}? Acquisterei subito. Grazie!",
    "es": "¡Hola! Me interesa «{title}». ¿Te parecería bien {offer}? Lo compraría enseguida. ¡Gracias!",
    "nl": "Hoi! Ik heb interesse in „{title}”. Zou {offer} oké zijn? Dan koop ik het direct. Bedankt!",
    "pl": "Dzień dobry! Interesuje mnie „{title}”. Czy {offer} byłoby w porządku? Kupię od razu. Dziękuję!",
    "sv": "Hej! Jag är intresserad av ”{title}”. Skulle {offer} vara okej? Då köper jag direkt. Tack!",
    "en": "Hi! I'm interested in “{title}”. Would {offer} work for you? I'd buy right away. Thanks!",
}
SABLON_TR = "Merhaba! '{title}' ile ilgileniyorum. {offer} sizin için uygun olur mu? Hemen satın alırım. Teşekkürler!"

SEMA = (
    """CREATE TABLE IF NOT EXISTS teklifler (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id TEXT NOT NULL,
        tt_no TEXT,
        platform TEXT, kaynak_url TEXT, baslik TEXT,
        ilan_fiyat REAL, para TEXT, kur_eur REAL,
        teklif REAL, karsi_teklif REAL, anlasilan REAL,
        net_kar_teklif REAL,
        durum TEXT NOT NULL DEFAULT 'hazir',
        dil TEXT, mesaj TEXT, mesaj_tr TEXT, mesaj_kaynak TEXT,
        not_ TEXT,
        olusturma TEXT, guncelleme TEXT, gonderim TEXT, kapanis TEXT
    )""",
    "CREATE INDEX IF NOT EXISTS idx_teklif_urun ON teklifler(product_id)",
    "CREATE INDEX IF NOT EXISTS idx_teklif_durum ON teklifler(durum)",
    "CREATE TABLE IF NOT EXISTS teklif_olay (teklif_id INTEGER, ts TEXT, durum TEXT, tutar REAL, aciklama TEXT)",
)

# Urun numarasi: her urune kalici kisa numara. Tetikleyici TUM ekleme yollarini (kazima, nokta atis, senkron) kapsar.
TT_TETIK = """CREATE TRIGGER IF NOT EXISTS trg_products_tt_no AFTER INSERT ON products
    WHEN NEW.tt_no IS NULL BEGIN
      UPDATE products SET tt_no = 'TT-' || printf('%05d',
        COALESCE((SELECT MAX(CAST(substr(tt_no, 4) AS INTEGER)) FROM products WHERE tt_no IS NOT NULL), 0) + 1)
      WHERE rowid = NEW.rowid;
    END"""


async def sema(db) -> None:
    """Idempotent: teklif tablolari + products.tt_no + tetikleyici + eski urunlere numara (eklenme sirasiyla)."""
    for sql in SEMA:
        await db.execute(sql)
    cols = {r[1] for r in await (await db.execute("PRAGMA table_info(products)")).fetchall()}
    if "tt_no" not in cols:
        await db.execute("ALTER TABLE products ADD COLUMN tt_no TEXT")
    await db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_products_tt_no ON products(tt_no)")
    eksik = await (await db.execute("SELECT COUNT(*) FROM products WHERE tt_no IS NULL")).fetchone()
    if eksik[0]:
        mx = await (await db.execute(
            "SELECT COALESCE(MAX(CAST(substr(tt_no, 4) AS INTEGER)), 0) FROM products WHERE tt_no IS NOT NULL")).fetchone()
        rows = await (await db.execute(
            "SELECT rowid FROM products WHERE tt_no IS NULL ORDER BY COALESCE(created_at, scraped_at), rowid")).fetchall()
        n = mx[0]
        for (rid,) in rows:
            n += 1
            await db.execute("UPDATE products SET tt_no=? WHERE rowid=?", (f"TT-{n:05d}", rid))
    await db.execute(TT_TETIK)
    await db.commit()


def platform_kok(platform: str) -> str:
    return "vinted" if (platform or "").lower().startswith("vinted") else (platform or "").lower()


def net_at(p: dict, teklif_yerel: float, kur: float) -> float | None:
    """Teklif tutarinda tutucu net kar. kur: 1 yerel birim kac EUR. Zeka puani yoksa None."""
    if p.get("zeka_net_kar") is None or not kur:
        return None
    oran = UCRET_ORANI.get(platform_kok(p.get("source_platform")), 0.0)
    fark_eur = ((p.get("price") or 0) - teklif_yerel) * kur
    return round(p["zeka_net_kar"] + fark_eur * (1 + oran), 2)


def oneri(p: dict, kur: float) -> dict:
    """Onerilen teklif: HEDEF_KAR tutucu net birakan tutar; ilan fiyatinin %70'i ile ilan fiyati arasinda."""
    fiyat = p.get("price") or 0
    taban = round(fiyat * MIN_ORAN, 0)
    if p.get("zeka_net_kar") is None or not kur or not fiyat:
        return {"teklif": taban, "neden": "zeka puani yok: ilan fiyatinin %70'i (kar bilinmiyor)", "net": None}
    oran = UCRET_ORANI.get(platform_kok(p.get("source_platform")), 0.0)
    eksik = HEDEF_KAR - p["zeka_net_kar"]                 # EUR
    if eksik <= 0:
        return {"teklif": fiyat, "neden": f"ilan fiyatinda zaten tutucu kar >= {HEDEF_KAR:.0f} EUR",
                "net": net_at(p, fiyat, kur)}
    gerekli = fiyat - eksik / (kur * (1 + oran))          # hedef kar icin yerel tutar
    hedef = math.floor(gerekli)
    if hedef >= taban:
        return {"teklif": float(hedef), "neden": f"{HEDEF_KAR:.0f} EUR tutucu kar birakan tutar",
                "net": net_at(p, hedef, kur)}
    return {"teklif": taban, "neden": (f"{HEDEF_KAR:.0f} EUR kar icin {gerekli:.0f} gerekir; ilan fiyatinin %70'inin "
                                       f"altina inilmez -> bu urun teklifle bile cok karli olmaz"),
            "net": net_at(p, taban, kur)}


def _para(tutar: float, para: str, dil: str) -> str:
    sembol = {"EUR": "€", "GBP": "£", "PLN": "zł", "SEK": "kr"}.get((para or "EUR").upper(), para)
    t = f"{tutar:.0f}" if float(tutar).is_integer() else f"{tutar:.2f}"
    if dil in ("en",) and sembol == "£":
        return f"£{t}"
    return f"{t} {sembol}"


def groq_acik() -> bool:
    return bool(os.getenv("GROQ_API_KEY")) and os.getenv("GROQ_MESSAGE_DRAFT_ENABLED", "").lower() == "true"


def taslak(baslik: str, platform: str, ilan_fiyat: float, teklif: float, para: str) -> dict:
    """{dil, mesaj, mesaj_tr, kaynak}. Groq acik ve basariliysa Groq, degilse sablon. Asla gondermez."""
    dil = DIL.get((platform or "").lower(), "de")
    kisa = (baslik or "").strip()[:70]
    t_txt = _para(teklif, para, dil)
    sablon = {"dil": dil, "mesaj": SABLON[dil].format(title=kisa, offer=t_txt),
              "mesaj_tr": SABLON_TR.format(title=kisa, offer=t_txt), "kaynak": "sablon"}
    if not groq_acik():
        sablon["kaynak"] = "sablon (Groq kapali: GROQ_MESSAGE_DRAFT_ENABLED)"
        return sablon
    import requests
    sistem = ("Du schreibst kurze, freundliche Kaufanfragen für Second-Hand-Marktplätze. "
              "Regeln: höchstens 2 Sätze, kein Druck, keine Erwähnung von Weiterverkauf, keine persönlichen Daten, "
              "keine Emojis außer höchstens einem, der genannte Betrag wird EXAKT übernommen. "
              'Antworte NUR mit JSON: {"mesaj": "<Nachricht in der Zielsprache>", "turkce": "<türkische Übersetzung>"}')
    istek = (f"Zielsprache: {DIL_ADI[dil]}\nArtikel: {kisa}\nAngebotspreis: {_para(ilan_fiyat, para, dil)}\n"
             f"Mein Angebot: {t_txt}")
    # 2026-10-19 olculdu: llama-3.3-70b Groq'tan kaldirilmis (HTTP 404); qwen3.8-27b dogal ve dogru dilde yaziyor,
    # gpt-oss-120b bu istemde 400 veriyor (akil yurutme token sinirini dolduruyor) -> yedek.
    modeller = [m for m in (os.getenv("GROQ_DRAFT_MODEL"), "qwen/qwen3.8-27b", "openai/gpt-oss-120b") if m]
    rakam = t_txt.split()[0].lstrip("£")
    son_hata = ""
    for model in dict.fromkeys(modeller):
        try:
            r = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}", "Content-Type": "application/json"},
                json={"model": model,
                      "messages": [{"role": "system", "content": sistem}, {"role": "user", "content": istek}],
                      "temperature": 0.4, "max_tokens": 600, "response_format": {"type": "json_object"}},
                timeout=25)
            if r.status_code != 200:
                son_hata = f"{model} HTTP {r.status_code}"
                continue
            js = json.loads(r.json()["choices"][0]["message"]["content"])
            mesaj, tr = str(js.get("mesaj", "")).strip(), str(js.get("turkce", "")).strip()
            if not mesaj or rakam not in mesaj or len(mesaj) > 400:
                son_hata = f"{model}: yanit tutari icermiyor / gecersiz"
                continue
            return {"dil": dil, "mesaj": mesaj, "mesaj_tr": tr, "kaynak": f"groq ({model})"}
        except Exception as exc:  # ag / JSON hatasi -> siradaki model, en sonda sablon
            son_hata = f"{model}: {type(exc).__name__}"
    sablon["kaynak"] = f"sablon (Groq: {son_hata})"
    return sablon


def simdi() -> str:
    return datetime.now().isoformat(timespec="seconds")
