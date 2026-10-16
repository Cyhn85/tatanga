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
    "vinted": "de",          # vinted.de
    "vinted_at": "de",       # vinted.at (Avusturya = Almanca)
    "vinted_be": "fr",       # Belcika (fr/nl) — fr aliyoruz
    "vinted_fr": "fr",
    "vinted_it": "it",
    "vinted_nl": "nl",
    "vinted_es": "es",
    "vinted_se": "sv",
    "vinted_pl": "pl",
    "vinted_uk": "en",       # Birlesik Krallik
    "kleinanzeigen": "de",
    "markt": "nl",           # Marktplaats (Hollanda)
    "ebay": "de",
    "willhaben": "de",       # Avusturya = Almanca
    "tradera": "sv",         # Isvec
    "sellpy": "de",          # TATANGA sellpy.DE'yi kaziyor (2026-10-16 duzeltildi; eskiden 'sv' -> Isvecce aranyordu)
    "leboncoin": "fr",       # Fransa
    "percentil": "es",       # Ispanya
    "depop": "en",
}

# Tip/kategori kelimeleri: kanonik -> {dil: karsilik}. Anahtarlar tum dillerdeki
# yazimlari da icerir (girdi hangi dilde olursa olsun taninsin).
TYPE_WORDS: dict[str, dict[str, str]] = {
    # --- Temel tipler (it eklendi 2026-10-16) ------------------------------
    "jacket": {"de": "jacke", "fr": "veste", "it": "giacca", "sv": "jacka", "nl": "jas", "es": "chaqueta", "en": "jacket", "pl": "kurtka"},
    "coat":   {"de": "mantel", "fr": "manteau", "it": "cappotto", "sv": "kappa", "nl": "jas", "es": "abrigo", "en": "coat", "pl": "plaszcz"},
    "shoes":  {"de": "schuhe", "fr": "chaussures", "it": "scarpe", "sv": "skor", "nl": "schoenen", "es": "zapatos", "en": "shoes", "pl": "buty"},
    "sneakers": {"de": "sneaker", "fr": "baskets", "it": "sneakers", "sv": "sneakers", "nl": "sneakers", "es": "zapatillas", "en": "sneakers", "pl": "sneakersy"},
    "bag":    {"de": "tasche", "fr": "sac", "it": "borsa", "sv": "väska", "nl": "tas", "es": "bolso", "en": "bag", "pl": "torba"},
    "backpack": {"de": "rucksack", "fr": "sac a dos", "it": "zaino", "sv": "ryggsäck", "nl": "rugzak", "es": "mochila", "en": "backpack", "pl": "plecak"},
    "trousers": {"de": "hose", "fr": "pantalon", "it": "pantaloni", "sv": "byxor", "nl": "broek", "es": "pantalon", "en": "trousers", "pl": "spodnie"},
    "jeans":  {"de": "jeans", "fr": "jean", "it": "jeans", "sv": "jeans", "nl": "spijkerbroek", "es": "vaqueros", "en": "jeans", "pl": "jeansy"},
    "hoodie": {"de": "hoodie", "fr": "sweat a capuche", "it": "felpa con cappuccio", "sv": "huvtröja", "nl": "hoodie", "es": "sudadera con capucha", "en": "hoodie", "pl": "bluza z kapturem"},
    "sweater": {"de": "pullover", "fr": "pull", "it": "maglione", "sv": "tröja", "nl": "trui", "es": "jersey", "en": "sweater", "pl": "sweter"},
    "sweatshirt": {"de": "sweatshirt", "fr": "sweat", "it": "felpa", "sv": "sweatshirt", "nl": "sweater", "es": "sudadera", "en": "sweatshirt", "pl": "bluza"},
    "shirt":  {"de": "hemd", "fr": "chemise", "it": "camicia", "sv": "skjorta", "nl": "overhemd", "es": "camisa", "en": "shirt", "pl": "koszula"},
    "tshirt": {"de": "t-shirt", "fr": "t-shirt", "it": "t-shirt", "sv": "t-shirt", "nl": "t-shirt", "es": "camiseta", "en": "t-shirt", "pl": "t-shirt"},
    "dress":  {"de": "kleid", "fr": "robe", "it": "vestito", "sv": "klänning", "nl": "jurk", "es": "vestido", "en": "dress", "pl": "sukienka"},
    "watch":  {"de": "uhr", "fr": "montre", "it": "orologio", "sv": "klocka", "nl": "horloge", "es": "reloj", "en": "watch", "pl": "zegarek"},

    # --- Almanca BIRLESIK mont/ust/ayakkabi tipleri (2026-10-16) -----------
    # "Columbia Regenjacke" Vinted.fr'ye Almanca gidiyordu; sonuc kumesi cokuyordu.
    "down_jacket": {"de": "daunenjacke", "fr": "doudoune", "it": "piumino", "sv": "dunjacka", "nl": "donsjas", "es": "plumifero", "en": "puffer jacket", "pl": "kurtka puchowa"},
    "fleece":     {"de": "fleecejacke", "fr": "polaire", "it": "pile", "sv": "fleecejacka", "nl": "fleece vest", "es": "forro polar", "en": "fleece jacket", "pl": "polar"},
    "rain_jacket": {"de": "regenjacke", "fr": "impermeable", "it": "impermeabile", "sv": "regnjacka", "nl": "regenjas", "es": "chubasquero", "en": "rain jacket", "pl": "kurtka przeciwdeszczowa"},
    "winter_jacket": {"de": "winterjacke", "fr": "veste d'hiver", "it": "giacca invernale", "sv": "vinterjacka", "nl": "winterjas", "es": "chaqueta de invierno", "en": "winter jacket", "pl": "kurtka zimowa"},
    "leather_jacket": {"de": "lederjacke", "fr": "veste en cuir", "it": "giacca di pelle", "sv": "skinnjacka", "nl": "leren jas", "es": "chaqueta de cuero", "en": "leather jacket", "pl": "kurtka skorzana"},
    "softshell":  {"de": "softshelljacke", "fr": "softshell", "it": "softshell", "sv": "softshelljacka", "nl": "softshell jas", "es": "softshell", "en": "softshell jacket", "pl": "softshell"},
    "parka":      {"de": "parka", "fr": "parka", "it": "parka", "sv": "parkas", "nl": "parka", "es": "parka", "en": "parka", "pl": "parka"},
    "bomber":     {"de": "bomberjacke", "fr": "bombers", "it": "bomber", "sv": "bomberjacka", "nl": "bomberjack", "es": "bomber", "en": "bomber jacket", "pl": "kurtka bomber"},
    "denim_jacket": {"de": "jeansjacke", "fr": "veste en jean", "it": "giacca di jeans", "sv": "jeansjacka", "nl": "spijkerjas", "es": "chaqueta vaquera", "en": "denim jacket", "pl": "kurtka jeansowa"},
    "windbreaker": {"de": "windjacke", "fr": "coupe-vent", "it": "giacca a vento", "sv": "vindjacka", "nl": "windjack", "es": "cortavientos", "en": "windbreaker", "pl": "wiatrowka"},
    "vest":       {"de": "weste", "fr": "gilet", "it": "gilet", "sv": "väst", "nl": "bodywarmer", "es": "chaleco", "en": "gilet", "pl": "kamizelka"},
    "ski_jacket": {"de": "skijacke", "fr": "veste de ski", "it": "giacca da sci", "sv": "skidjacka", "nl": "ski jas", "es": "chaqueta de esqui", "en": "ski jacket", "pl": "kurtka narciarska"},
    "track_jacket": {"de": "trainingsjacke", "fr": "veste de survetement", "it": "giacca tuta", "sv": "träningsjacka", "nl": "trainingsjack", "es": "chaqueta de chandal", "en": "track jacket", "pl": "bluza dresowa"},
    "hoodie_de":  {"de": "kapuzenpullover", "fr": "sweat a capuche", "it": "felpa con cappuccio", "sv": "huvtröja", "nl": "hoodie", "es": "sudadera con capucha", "en": "hoodie", "pl": "bluza z kapturem"},
    "cardigan":   {"de": "strickjacke", "fr": "gilet", "it": "cardigan", "sv": "kofta", "nl": "vest", "es": "chaqueta de punto", "en": "cardigan", "pl": "kardigan"},
    "knit":       {"de": "strickpullover", "fr": "pull en maille", "it": "maglione", "sv": "stickad tröja", "nl": "gebreide trui", "es": "jersey de punto", "en": "knit sweater", "pl": "sweter"},
    "boots":      {"de": "stiefel", "fr": "bottes", "it": "stivali", "sv": "kängor", "nl": "laarzen", "es": "botas", "en": "boots", "pl": "botki"},
    "ankle_boots": {"de": "stiefeletten", "fr": "bottines", "it": "stivaletti", "sv": "boots", "nl": "enkellaarsjes", "es": "botines", "en": "ankle boots", "pl": "botki"},
    "running_shoes": {"de": "laufschuhe", "fr": "chaussures de course", "it": "scarpe da corsa", "sv": "löparskor", "nl": "hardloopschoenen", "es": "zapatillas de running", "en": "running shoes", "pl": "buty do biegania"},
    "hiking_shoes": {"de": "wanderschuhe", "fr": "chaussures de randonnee", "it": "scarpe da trekking", "sv": "vandringskängor", "nl": "wandelschoenen", "es": "botas de montana", "en": "hiking shoes", "pl": "buty trekkingowe"},
    "trainers":   {"de": "turnschuhe", "fr": "baskets", "it": "scarpe da ginnastica", "sv": "gympaskor", "nl": "sportschoenen", "es": "zapatillas", "en": "trainers", "pl": "buty sportowe"},
    "loafers":    {"de": "loafer", "fr": "mocassins", "it": "mocassini", "sv": "loafers", "nl": "loafers", "es": "mocasines", "en": "loafers", "pl": "mokasyny"},
    "sandals":    {"de": "sandalen", "fr": "sandales", "it": "sandali", "sv": "sandaler", "nl": "sandalen", "es": "sandalias", "en": "sandals", "pl": "sandaly"},
    "pumps":      {"de": "pumps", "fr": "escarpins", "it": "decollete", "sv": "pumps", "nl": "pumps", "es": "zapatos de tacon", "en": "heels", "pl": "szpilki"},

    # --- Cinsiyet/beden hedefi ---------------------------------------------
    # "columbia herren jacke" aramasinda 'herren' cevrilmezse Fransiz/Isvec
    # sitesine ALMANCA kelime gider ve sonuc kumesi coker. Gercek kayip buydu.
    "mens":   {"de": "herren", "fr": "homme", "it": "uomo", "sv": "herr", "nl": "heren", "es": "hombre", "en": "mens", "pl": "meska"},
    "womens": {"de": "damen", "fr": "femme", "it": "donna", "sv": "dam", "nl": "dames", "es": "mujer", "en": "womens", "pl": "damska"},
    "kids":   {"de": "kinder", "fr": "enfant", "it": "bambini", "sv": "barn", "nl": "kinderen", "es": "nino", "en": "kids", "pl": "dziecieca"},

    # --- Durum (condition) kelimeleri --------------------------------------
    "new_with_tags": {"de": "neu mit etikett", "fr": "neuf avec etiquette", "it": "nuovo con cartellino",
                      "sv": "ny med prislapp", "nl": "nieuw met prijskaartje",
                      "es": "nuevo con etiquetas", "en": "new with tags",
                      "pl": "nowy z metka"},
    "new":        {"de": "neu", "fr": "neuf", "it": "nuovo", "sv": "ny", "nl": "nieuw", "es": "nuevo", "en": "new", "pl": "nowy"},
    "very_good":  {"de": "sehr gut", "fr": "tres bon etat", "it": "ottime condizioni", "sv": "mycket bra skick",
                   "nl": "heel goed", "es": "muy bueno", "en": "very good",
                   "pl": "bardzo dobry"},
    "like_new":   {"de": "neuwertig", "fr": "comme neuf", "it": "come nuovo", "sv": "nyskick",
                   "nl": "zo goed als nieuw", "es": "como nuevo", "en": "like new",
                   "pl": "jak nowy"},
}

# Girdi kelime (herhangi dilde) -> kanonik tip. Ters indeks.
_WORD_TO_CANON: dict[str, str] = {}
for _canon, _langs in TYPE_WORDS.items():
    _WORD_TO_CANON[_canon] = _canon
    for _w in _langs.values():
        _WORD_TO_CANON.setdefault(_w.lower(), _canon)
# Ek girdi yazimlari (ayni anlam, farkli yazim) + Turkce yaygin karsiliklar
_WORD_TO_CANON.update({
    "daunen jacke": "down_jacket", "steppjacke": "down_jacket", "pufferjacke": "down_jacket", "puffer": "down_jacket",
    "fleece": "fleece", "fleece jacke": "fleece", "regen jacke": "rain_jacket", "funktionsjacke": "rain_jacket",
    "outdoorjacke": "rain_jacket", "winter jacke": "winter_jacket", "leder jacke": "leather_jacket",
    "kapuzenjacke": "hoodie_de", "kapuzen pullover": "hoodie_de", "hoody": "hoodie", "pulli": "sweater",
    "boots": "boots", "sneakers": "sneakers", "jeanshose": "jeans",
    "sisme mont": "down_jacket", "polar": "fleece", "yagmurluk": "rain_jacket", "deri ceket": "leather_jacket",
    "yelek": "vest", "bot": "boots", "cizme": "boots", "kosu ayakkabisi": "running_shoes", "hirka": "cardigan",
    "kapusonlu": "hoodie", "esofman ustu": "track_jacket",
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
