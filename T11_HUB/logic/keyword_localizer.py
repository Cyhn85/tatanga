"""
Yerel-dil arama kelimesi cevirici (saf, additive, ucretsiz).

SORUN: scrape_platform tum platformlara ayni keyword'u gonderiyor; yerel dile
ceviri yok. Marka/model isimleri tum dillerde ayni oldugu icin (Nike, North Face,
Levi's) marka-bazli aramada sorun yok. Ama KATEGORI/TIP kelimeleri (jacket, canta,
ayakkabi) hedef sitede yerel dilde olmali (Leboncoin=FR, Tradera=SE ...).

Bu modul: keyword icindeki TIP kelimelerini hedef dile cevirir, marka/model
token'larini oldugu gibi birakir. Statik sozluk — API/kayit gerektirmez.
"""

from __future__ import annotations

import re
from typing import Optional

from .brand_catalog import canonical_brand

# Platform -> hedef dil kodu. Almanca konusan siteler ceviri gerektirmez.
PLATFORM_LANG: dict[str, str] = {
    "vinted": "de",          # DE varsayilan (domain'e gore degisebilir)
    "vinted_be": "fr",       # Belcika (fr/nl) — fr aliyoruz
    "vinted_fr": "fr",
    "vinted_pl": "pl",       # Polonya (TYPE_WORDS'te pl yoksa token korunur)
    "vinted_uk": "en",       # Birlesik Krallik
    "kleinanzeigen": "de",
    "markt": "nl",           # Hollanda/Belcika
    "ebay": "de",
    "willhaben": "de",       # Avusturya = Almanca
    "tradera": "sv",         # Isvec
    "sellpy": "sv",          # Isvec
    "leboncoin": "fr",       # Fransa
    "percentil": "es",       # Ispanya
    "depop": "en",
}

# Tip/kategori kelimeleri: kanonik -> {dil: karsilik}. Anahtarlar tum dillerdeki
# yazimlari da icerir (girdi hangi dilde olursa olsun taninsin).
TYPE_WORDS: dict[str, dict[str, str]] = {
    "jacket": {"de": "jacke", "fr": "veste", "sv": "jacka", "nl": "jas", "es": "chaqueta", "en": "jacket", "pl": "kurtka"},
    "coat":   {"de": "mantel", "fr": "manteau", "sv": "kappa", "nl": "jas", "es": "abrigo", "en": "coat", "pl": "plaszcz"},
    "shoes":  {"de": "schuhe", "fr": "chaussures", "sv": "skor", "nl": "schoenen", "es": "zapatos", "en": "shoes", "pl": "buty"},
    "sneakers": {"de": "sneaker", "fr": "baskets", "sv": "sneakers", "nl": "sneakers", "es": "zapatillas", "en": "sneakers", "pl": "sneakersy"},
    "bag":    {"de": "tasche", "fr": "sac", "sv": "vaska", "nl": "tas", "es": "bolso", "en": "bag", "pl": "torba"},
    "backpack": {"de": "rucksack", "fr": "sac a dos", "sv": "ryggsack", "nl": "rugzak", "es": "mochila", "en": "backpack", "pl": "plecak"},
    "trousers": {"de": "hose", "fr": "pantalon", "sv": "byxor", "nl": "broek", "es": "pantalon", "en": "trousers", "pl": "spodnie"},
    "jeans":  {"de": "jeans", "fr": "jean", "sv": "jeans", "nl": "spijkerbroek", "es": "vaqueros", "en": "jeans", "pl": "jeansy"},
    "hoodie": {"de": "hoodie", "fr": "sweat a capuche", "sv": "huvtroja", "nl": "hoodie", "es": "sudadera", "en": "hoodie", "pl": "bluza z kapturem"},
    "sweater": {"de": "pullover", "fr": "pull", "sv": "trOja", "nl": "trui", "es": "jersey", "en": "sweater", "pl": "sweter"},
    "shirt":  {"de": "hemd", "fr": "chemise", "sv": "skjorta", "nl": "overhemd", "es": "camisa", "en": "shirt", "pl": "koszula"},
    "tshirt": {"de": "t-shirt", "fr": "t-shirt", "sv": "t-shirt", "nl": "t-shirt", "es": "camiseta", "en": "t-shirt", "pl": "t-shirt"},
    "dress":  {"de": "kleid", "fr": "robe", "sv": "klanning", "nl": "jurk", "es": "vestido", "en": "dress", "pl": "sukienka"},
    "watch":  {"de": "uhr", "fr": "montre", "sv": "klocka", "nl": "horloge", "es": "reloj", "en": "watch", "pl": "zegarek"},

    # --- Cinsiyet/beden hedefi ---------------------------------------------
    # "columbia herren jacke" aramasinda 'herren' cevrilmezse Fransiz/Isvec
    # sitesine ALMANCA kelime gider ve sonuc kumesi coker. Gercek kayip buydu.
    "mens":   {"de": "herren", "fr": "homme", "sv": "herr", "nl": "heren", "es": "hombre", "en": "mens", "pl": "meska"},
    "womens": {"de": "damen", "fr": "femme", "sv": "dam", "nl": "dames", "es": "mujer", "en": "womens", "pl": "damska"},
    "kids":   {"de": "kinder", "fr": "enfant", "sv": "barn", "nl": "kinderen", "es": "nino", "en": "kids", "pl": "dziecieca"},

    # --- Durum (condition) kelimeleri --------------------------------------
    # Arbitrajda durum aramanin bir parcasi: "neu mit etikett" gibi ifadeler
    # her sitede yerel karsiligiyla aranmali.
    "new_with_tags": {"de": "neu mit etikett", "fr": "neuf avec etiquette",
                      "sv": "ny med etikett", "nl": "nieuw met label",
                      "es": "nuevo con etiqueta", "en": "new with tags",
                      "pl": "nowy z metka"},
    "new":        {"de": "neu", "fr": "neuf", "sv": "ny", "nl": "nieuw", "es": "nuevo", "en": "new", "pl": "nowy"},
    "very_good":  {"de": "sehr gut", "fr": "tres bon etat", "sv": "mycket bra skick",
                   "nl": "zeer goed", "es": "muy bueno", "en": "very good",
                   "pl": "bardzo dobry"},
    "like_new":   {"de": "neuwertig", "fr": "comme neuf", "sv": "nyskick",
                   "nl": "zo goed als nieuw", "es": "como nuevo", "en": "like new",
                   "pl": "jak nowy"},
}

# Girdi kelime (herhangi dilde) -> kanonik tip. Ters indeks.
_WORD_TO_CANON: dict[str, str] = {}
for _canon, _langs in TYPE_WORDS.items():
    _WORD_TO_CANON[_canon] = _canon
    for _w in _langs.values():
        _WORD_TO_CANON.setdefault(_w.lower(), _canon)
# Turkce yaygin karsiliklar (girdi Turkce olabilir)
_WORD_TO_CANON.update({
    "mont": "jacket", "ceket": "jacket", "kaban": "coat", "palto": "coat",
    "ayakkabi": "shoes", "spor ayakkabi": "sneakers", "canta": "bag",
    "sirt cantasi": "backpack", "pantolon": "trousers", "kot": "jeans",
    "kazak": "sweater", "gomlek": "shirt", "tisort": "tshirt", "elbise": "dress",
    "saat": "watch",
    # cinsiyet
    "erkek": "mens", "kadin": "womens", "cocuk": "kids",
    # durum
    "sifir": "new", "etiketli": "new_with_tags", "etiketli yeni": "new_with_tags",
    "cok iyi": "very_good", "az kullanilmis": "like_new",
})

# Uc kelimelik tip ifadeleri ("neu mit etikett", "neuf avec etiquette",
# "tres bon etat"). Iki-kelime denemesi bunlari yakalayamiyordu.
_MAX_PHRASE_LEN = max(
    (len(w.split()) for w in _WORD_TO_CANON), default=1
)


def localize_keyword(keyword: str, platform: str) -> str:
    """
    keyword icindeki tip kelimelerini hedef platformun diline cevirir; marka/model
    token'larini korur. Almanca/varsayilan platformlarda cogu kez ayni kalir.
    """
    lang = PLATFORM_LANG.get(platform.lower(), "de")
    if not keyword:
        return keyword

    tokens = keyword.split()
    out: list[str] = []
    i = 0
    while i < len(tokens):
        # En UZUN ifadeden basla: "neu mit etikett" (3) once denenmezse
        # "neu" (1) eslesir ve "mit etikett" cevrilmeden kalirdi.
        eslesti = False
        for n in range(min(_MAX_PHRASE_LEN, len(tokens) - i), 1, -1):
            ifade = " ".join(tokens[i:i + n]).lower()
            if ifade in _WORD_TO_CANON:
                canon = _WORD_TO_CANON[ifade]
                out.append(TYPE_WORDS[canon].get(lang, ifade))
                i += n
                eslesti = True
                break
        if eslesti:
            continue

        tok = tokens[i]
        low = tok.lower()
        if low in _WORD_TO_CANON:
            canon = _WORD_TO_CANON[low]
            out.append(TYPE_WORDS[canon].get(lang, tok))
        else:
            out.append(tok)  # marka/model/diger -> oldugu gibi
        i += 1
    return " ".join(out)


def detected_type(keyword: str) -> Optional[str]:
    """keyword'de bir tip kelimesi var mi (kanonik) — kategori tahmini icin."""
    low = (keyword or "").lower()
    for word, canon in _WORD_TO_CANON.items():
        if word in low:
            return canon
    return None
