"""
Gozlem deposu — kategori bazli, cok kucuk, insan-okunur urun gecmisi.

TASARIM KARARI (mimari gerekce):

  1. NE SAKLANIR: Urunun TAM kaydi degil, ilanin YASAM DONGUSU gozlemi.
     Istatistik icin gereken 12 alan: kategori, cinsiyet, marka, beden,
     fiyat bandi, durum skoru, platform, ilk gorulme, son gorulme,
     satildi mi, kac gunde, gercek fiyat. Satir ~60 bayt.
     100.000 gozlem = ~6 MB. Ayni veriyi tam urun satiri olarak tutmak
     ~180 MB olurdu (goruntu URL'leri, aciklamalar, arbitraj JSON'lari).

  2. FORMAT — IKI KATMAN, her biri kendi isini yapar:
     a) TSV log (KAYNAK GERCEK): ekleme-only, kategori basina bir dosya.
        Notepad'de acilir, grep'lenir, diff'lenir, elle duzeltilebilir.
        Bozulma riski en dusuk format: bir satir bozulsa digerleri saglam.
     b) SQLite (TURETILMIS INDEKS): TSV'den yeniden uretilebilir.
        DBeaver dogrudan acar; capraz sorgular (kategori x beden x fiyat)
        SQL'le yapilir. Kaybolursa TSV'den 1 komutla geri kurulur.
     Bu, "write-ahead log + materialized view" deseninin sade halidir.
     Tek bir SQLite'a yazmak da olurdu ama insan gozuyle okunamaz ve
     bozulursa gecmis tamamen gider.

  3. NEDEN KATEGORI BASINA DOSYA: Bir kategoriyi incelerken 100.000 satir
     okumak gerekmez. "Herren > Jacken" sorusu 3.000 satirlik tek dosyayi
     acar. Ayrica dosya kilitleri kategori bazinda kalir.

Saf modul: yol disaridan verilir -> izole test edilir.
"""

from __future__ import annotations

import csv
import re
import sqlite3
from dataclasses import dataclass, asdict, fields
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Iterator, Optional

SCHEMA_VERSION = 1

# Alan sirasi DOSYADA sabittir — yeni alan yalnizca SONA eklenir ki eski
# satirlar okunmaya devam etsin (ileri uyumluluk).
COLUMNS = [
    "obs_id",         # platform:source_id — tekillik anahtari
    "category",       # cssberlin ana kategori (normalize)
    "subcategory",
    "gender",         # herren | damen | kinder | unisex
    "brand",
    "size",           # normalize edilmis beden (S/M/L/...)
    "price_band",     # "30-50"
    "price_eur",      # gercek fiyat (EUR'a cevrilmis)
    "condition_score",  # 1-5 veya bos
    "platform",
    "first_seen",     # YYYY-MM-DD
    "last_seen",      # YYYY-MM-DD
    "sold",           # 1 | 0
    "days_to_sell",   # satildiysa gun sayisi, degilse bos
]


@dataclass
class Observation:
    obs_id: str
    category: str = ""
    subcategory: str = ""
    gender: str = ""
    brand: str = ""
    size: str = ""
    price_band: str = ""
    price_eur: float = 0.0
    condition_score: Optional[int] = None
    platform: str = ""
    first_seen: str = ""
    last_seen: str = ""
    sold: int = 0
    days_to_sell: Optional[int] = None

    def to_row(self) -> list[str]:
        d = asdict(self)
        return ["" if d[c] is None else str(d[c]) for c in COLUMNS]

    @staticmethod
    def from_row(row: dict) -> "Observation":
        def sayi(v, tip):
            try:
                return tip(v) if str(v).strip() != "" else None
            except (TypeError, ValueError):
                return None
        return Observation(
            obs_id=row.get("obs_id", ""),
            category=row.get("category", ""),
            subcategory=row.get("subcategory", ""),
            gender=row.get("gender", ""),
            brand=row.get("brand", ""),
            size=row.get("size", ""),
            price_band=row.get("price_band", ""),
            price_eur=sayi(row.get("price_eur"), float) or 0.0,
            condition_score=sayi(row.get("condition_score"), int),
            platform=row.get("platform", ""),
            first_seen=row.get("first_seen", ""),
            last_seen=row.get("last_seen", ""),
            sold=sayi(row.get("sold"), int) or 0,
            days_to_sell=sayi(row.get("days_to_sell"), int),
        )


def slug(text: str) -> str:
    """Dosya adi icin guvenli kategori anahtari."""
    t = (text or "genel").lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss"),
                 ("ı", "i"), ("ş", "s"), ("ç", "c"), ("ğ", "g")):
        t = t.replace(a, b)
    t = re.sub(r"[^a-z0-9]+", "_", t).strip("_")
    return t or "genel"


class ObservationStore:
    """Kategori basina TSV log + tek SQLite indeks."""

    def __init__(self, root: Path | str):
        self.root = Path(root)
        self.log_dir = self.root / "gozlemler"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / "gozlem_index.db"

    # ---------- TSV katmani (kaynak gercek) ----------

    def _path(self, category: str) -> Path:
        return self.log_dir / f"{slug(category)}.tsv"

    def append(self, obs: Observation) -> Path:
        """
        Tek gozlem ekler. Dosya yoksa basligi yazar — dosya kendi kendini
        aciklar, notepad'de acan biri ne oldugunu anlar.
        """
        p = self._path(obs.category)
        yeni = not p.exists()
        with p.open("a", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh, delimiter="\t", lineterminator="\n")
            if yeni:
                w.writerow(COLUMNS)
            w.writerow(obs.to_row())
        return p

    def append_many(self, observations: Iterable[Observation]) -> dict[str, int]:
        """Kategoriye gore gruplayip tek acilista yazar (disk dostu)."""
        gruplar: dict[str, list[Observation]] = {}
        for o in observations:
            gruplar.setdefault(o.category, []).append(o)
        sayim = {}
        for kat, liste in gruplar.items():
            p = self._path(kat)
            yeni = not p.exists()
            with p.open("a", encoding="utf-8", newline="") as fh:
                w = csv.writer(fh, delimiter="\t", lineterminator="\n")
                if yeni:
                    w.writerow(COLUMNS)
                for o in liste:
                    w.writerow(o.to_row())
            sayim[kat] = len(liste)
        return sayim

    def read(self, category: str) -> Iterator[Observation]:
        p = self._path(category)
        if not p.exists():
            return iter(())
        def gen():
            with p.open("r", encoding="utf-8", newline="") as fh:
                for row in csv.DictReader(fh, delimiter="\t"):
                    yield Observation.from_row(row)
        return gen()

    def categories(self) -> list[str]:
        return sorted(p.stem for p in self.log_dir.glob("*.tsv"))

    # ---------- SQLite katmani (turetilmis, DBeaver icin) ----------

    def rebuild_index(self) -> int:
        """
        TSV'lerden SQLite'i sifirdan kurar. Indeks her zaman ATILABILIR:
        gercek TSV'de. Bu, semayi degistirmeyi risksiz kilar.
        """
        con = sqlite3.connect(self.db_path)
        con.execute("DROP TABLE IF EXISTS observations")
        con.execute(f"""
            CREATE TABLE observations (
                {', '.join(f'{c} TEXT' if c not in ('price_eur','condition_score','sold','days_to_sell')
                           else (f'{c} REAL' if c == 'price_eur' else f'{c} INTEGER')
                           for c in COLUMNS)}
            )
        """)
        toplam = 0
        yer = ",".join("?" * len(COLUMNS))
        for p in self.log_dir.glob("*.tsv"):
            with p.open("r", encoding="utf-8", newline="") as fh:
                satirlar = []
                for row in csv.DictReader(fh, delimiter="\t"):
                    o = Observation.from_row(row)
                    satirlar.append(o.to_row())
                if satirlar:
                    con.executemany(
                        f"INSERT INTO observations VALUES ({yer})", satirlar)
                    toplam += len(satirlar)
        # Capraz sorgularin hizli olmasi icin gercek is desenine gore indeksler
        for idx in (
            "CREATE INDEX ix_kat ON observations(category, subcategory)",
            "CREATE INDEX ix_kat_beden ON observations(category, size)",
            "CREATE INDEX ix_marka ON observations(brand)",
            "CREATE INDEX ix_satildi ON observations(sold, category)",
            "CREATE INDEX ix_bant ON observations(price_band, category)",
        ):
            con.execute(idx)
        con.commit()
        con.close()
        return toplam

    def cross_query(self, dimensions: list[str], *, min_trials: int = 1,
                    where: str = "", params: tuple = ()) -> list[dict]:
        """
        Capraz sorgu: istenen kirilimlarda satis orani.
        dimensions ornegi: ["category", "gender", "size"] veya
                           ["brand", "price_band"]

        Boyut adlari BEYAZ LISTEDEN gecer — kullanici girdisi SQL'e gomulmez.
        """
        gecerli = [d for d in dimensions if d in COLUMNS]
        if not gecerli:
            return []
        sec = ", ".join(gecerli)
        sorgu = f"""
            SELECT {sec},
                   COUNT(*) AS trials,
                   SUM(sold) AS successes,
                   ROUND(AVG(price_eur), 2) AS avg_price,
                   ROUND(AVG(CASE WHEN sold=1 THEN days_to_sell END), 1) AS avg_days
            FROM observations
            {('WHERE ' + where) if where else ''}
            GROUP BY {sec}
            HAVING COUNT(*) >= ?
            ORDER BY successes DESC, trials DESC
        """
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        try:
            rows = con.execute(sorgu, tuple(params) + (min_trials,)).fetchall()
        finally:
            con.close()
        return [dict(r) for r in rows]

    def size_on_disk(self) -> dict:
        tsv = sum(p.stat().st_size for p in self.log_dir.glob("*.tsv"))
        db = self.db_path.stat().st_size if self.db_path.exists() else 0
        return {"tsv_bytes": tsv, "index_bytes": db,
                "tsv_mb": round(tsv / 1024 / 1024, 3),
                "index_mb": round(db / 1024 / 1024, 3)}


def observation_from_product(p: dict, *, category: str = "", subcategory: str = "",
                             gender: str = "", price_eur: Optional[float] = None,
                             today: Optional[str] = None) -> Observation:
    """
    products satirindan gozlem uretir.
    Gorsel/aciklama/JSON alanlari ALINMAZ — gozlem deposunun kucuk kalmasi
    bilincli: istatistik icin gereksiz, ama boyutu 30 kat buyutur.
    """
    from .demand_stats import price_band, normalize_size

    bugun = today or date.today().isoformat()
    ilk = (p.get("scraped_at") or "")[:10] or bugun
    son = (p.get("last_source_check") or p.get("updated_at") or "")[:10] or bugun
    satildi = 1 if (p.get("source_status") or "") == "sold" else 0

    gun = None
    if satildi and ilk and son:
        try:
            gun = max(0, (datetime.fromisoformat(son) - datetime.fromisoformat(ilk)).days)
        except ValueError:
            gun = None

    fiyat = price_eur if price_eur is not None else float(p.get("price") or 0)
    return Observation(
        obs_id=f"{p.get('source_platform','')}:{p.get('source_id','')}",
        category=category or (p.get("category") or "genel"),
        subcategory=subcategory,
        gender=gender,
        brand=(p.get("brand") or "").strip().lower()[:24],
        size=normalize_size(p.get("size") or ""),
        price_band=price_band(fiyat),
        price_eur=round(fiyat, 2),
        condition_score=p.get("condition_score"),
        platform=p.get("source_platform") or "",
        first_seen=ilk, last_seen=son,
        sold=satildi, days_to_sell=gun,
    )
