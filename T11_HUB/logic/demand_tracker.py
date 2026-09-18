"""
Talep takibi — kazidigimiz ilanlarin SATILDIGINI arama sonucu farkindan cikarir.

PROBLEM: Havuzumuzdaki 3639 urun hep AKTIF ilanlardan olusuyor, yani
"henuz satilmamis olanlar". Bu sistematik bir yanlilik: neyin sattigini degil,
neyin satmadigini biliyoruz. Fiyat modelimiz (sabit 1.40 carpani) bu yanli
veriye dayaniyor.

NEDEN TEKIL URL YOKLAMASI DEGIL: source_checks tablosunda 8502 kayit var ve
son kayitlar 403 donuyor — Vinted tekil ilan sayfalarini engelliyor. Ayrica
3639 URL/gun cok agir. Bunun yerine ZATEN yaptigimiz arama kaziyisinin
sonucunu kaydedip bir sonraki turla karsilastiriyoruz:

    tur N   : {ilan_1, ilan_2, ilan_3}
    tur N+1 : {ilan_1,          ilan_3, ilan_4}
    -> ilan_2 aramadan dustu   -> satildi VEYA kaldirildi
    -> ilan_4 yeni             -> havuza girdi

Gunde ~20-40 istek (sorgu sayisi kadar), 3639 degil. Ek engelleme riski yok,
cunku arama sayfalarini zaten basariyla kaziyoruz.

SINIR — bu veri %100 degil:
  Aramadan dusmek "satildi" demek DEGILDIR. Ilan suresi dolmus, satici
  kaldirmis, fiyat degistirip yeniden listelemis de olabilir. Bu yuzden
  kayitlar `dusme_nedeni='bilinmiyor'` ile tutulur ve istatistik "kaybolma
  hizi" olarak yorumlanir, "satis hizi" olarak degil. Yine de elimizde
  bugun hic olmayan bir sinyaldir.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Iterable, Optional

SEMA = """
CREATE TABLE IF NOT EXISTS search_snapshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    tur_id      TEXT NOT NULL,          -- kazima turunun kimligi
    platform    TEXT NOT NULL,
    keyword     TEXT NOT NULL,
    source_id   TEXT NOT NULL,          -- ilanin platformdaki kimligi
    gorulme     TEXT NOT NULL           -- ISO zaman
);
CREATE INDEX IF NOT EXISTS idx_snap_tur ON search_snapshots(platform, keyword, tur_id);
CREATE INDEX IF NOT EXISTS idx_snap_sid ON search_snapshots(source_id);

CREATE TABLE IF NOT EXISTS demand_observations (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id      TEXT NOT NULL,
    platform       TEXT NOT NULL,
    keyword        TEXT,
    product_id     TEXT,                -- products.id (varsa)
    title          TEXT,
    brand          TEXT,
    category       TEXT,
    size           TEXT,
    price          REAL,
    ilk_gorulme    TEXT,                -- ilanin ilk goruldugu an
    son_gorulme    TEXT,                -- aramada son goruldugu an
    kaybolma_gun   REAL,                -- son_gorulme - ilk_gorulme (gun)
    dusme_nedeni   TEXT DEFAULT 'bilinmiyor',
    kaydedildi     TEXT NOT NULL,
    UNIQUE(source_id, platform)
);
CREATE INDEX IF NOT EXISTS idx_gozlem_marka ON demand_observations(brand, category);
"""


def semayi_kur(db: sqlite3.Connection) -> None:
    db.executescript(SEMA)
    db.commit()


def _simdi() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _zaman(deger) -> Optional[datetime]:
    """ISO metni datetime'a cevirir ve HEP saat dilimsiz (naive) dondurur.

    Gerekli, cunku products.scraped_at dilimsiz ('2026-02-28T16:48:15.612550')
    ama bizim damgamiz dilimli. Ikisini cikarmak TypeError atiyor ve
    kaybolma_gun sessizce None kaliyordu."""
    if not deger:
        return None
    try:
        d = datetime.fromisoformat(str(deger).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d.replace(tzinfo=None) if d.tzinfo else d


def tur_kaydet(db: sqlite3.Connection, *, tur_id: str, platform: str,
               keyword: str, source_idler: Iterable[str]) -> int:
    """Bir kazima turunda GORULEN ilan kimliklerini kaydeder."""
    semayi_kur(db)
    an = _simdi()
    satirlar = [(tur_id, platform, keyword, str(s), an) for s in source_idler if s]
    if not satirlar:
        return 0
    db.executemany(
        "INSERT INTO search_snapshots (tur_id, platform, keyword, source_id, gorulme)"
        " VALUES (?,?,?,?,?)", satirlar)
    db.commit()
    return len(satirlar)


def _onceki_tur(db: sqlite3.Connection, platform: str, keyword: str,
                mevcut_tur: str) -> Optional[str]:
    r = db.execute(
        "SELECT tur_id FROM search_snapshots WHERE platform=? AND keyword=? AND tur_id!=?"
        " ORDER BY gorulme DESC LIMIT 1", (platform, keyword, mevcut_tur)).fetchone()
    return r[0] if r else None


def dusenleri_isle(db: sqlite3.Connection, *, tur_id: str, platform: str,
                   keyword: str) -> dict:
    """Bir onceki turda olup bu turda OLMAYAN ilanlari gozlem olarak yazar."""
    semayi_kur(db)
    onceki = _onceki_tur(db, platform, keyword, tur_id)
    if not onceki:
        return {"durum": "ilk_tur", "dusenler": 0}

    db.row_factory = sqlite3.Row
    dusenler = db.execute("""
        SELECT s.source_id, MIN(s.gorulme) ilk, MAX(s.gorulme) son
        FROM search_snapshots s
        WHERE s.platform=? AND s.keyword=?
          AND s.source_id NOT IN (
              SELECT source_id FROM search_snapshots
              WHERE platform=? AND keyword=? AND tur_id=?)
        GROUP BY s.source_id
    """, (platform, keyword, platform, keyword, tur_id)).fetchall()

    an = _simdi()
    yazilan = 0
    for d in dusenler:
        u = db.execute(
            "SELECT id, title, brand, category, size, price, scraped_at"
            " FROM products WHERE source_platform=? AND source_id=? LIMIT 1",
            (platform, d["source_id"])).fetchone()

        ilk = (u["scraped_at"] if u and u["scraped_at"] else d["ilk"])
        t_ilk, t_son = _zaman(ilk), _zaman(d["son"])
        gun = (t_son - t_ilk).total_seconds() / 86400 if (t_ilk and t_son) else None

        db.execute("""
            INSERT OR IGNORE INTO demand_observations
            (source_id, platform, keyword, product_id, title, brand, category,
             size, price, ilk_gorulme, son_gorulme, kaybolma_gun, kaydedildi)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (d["source_id"], platform, keyword,
              u["id"] if u else None, u["title"] if u else None,
              u["brand"] if u else None, u["category"] if u else None,
              u["size"] if u else None, u["price"] if u else None,
              str(ilk), d["son"], round(gun, 2) if gun is not None else None, an))
        yazilan += db.total_changes and 1 or 0
    db.commit()
    return {"durum": "tamam", "onceki_tur": onceki, "dusenler": len(dusenler)}


def istatistik(db: sqlite3.Connection, *, min_ornek: int = 3) -> list[dict]:
    """Marka+kategori kiriliminda kaybolma hizi. Az orneklem gizlenir."""
    semayi_kur(db)
    db.row_factory = sqlite3.Row
    rows = db.execute("""
        SELECT COALESCE(NULLIF(brand,''),'(marka yok)') marka,
               COALESCE(NULLIF(category,''),'(kategori yok)') kategori,
               COUNT(*) n,
               ROUND(AVG(kaybolma_gun),1) ort_gun,
               ROUND(MIN(price),2) min_fiyat,
               ROUND(MAX(price),2) max_fiyat,
               ROUND(AVG(price),2) ort_fiyat
        FROM demand_observations
        WHERE kaybolma_gun IS NOT NULL
        GROUP BY marka, kategori
        HAVING n >= ?
        ORDER BY ort_gun ASC
    """, (min_ornek,)).fetchall()
    return [dict(r) for r in rows]
