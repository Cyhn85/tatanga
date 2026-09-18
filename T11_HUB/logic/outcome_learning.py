"""
Sonuc ogrenme — hangi kazimanin GERCEKTEN para getirdigini olcer.

BUGUNKU EKSIK: Sistem kaziyor, fiyatliyor, yayinliyor — ama hicbir yerde
"bu anahtar kelime/platform/marka gercekten satti mi?" sorusunun cevabi
tutulmuyor. Ayni verimsiz aramalar tekrar tekrar kosuluyor.

NE YAPAR: Her urun icin (platform, marka, fiyat bandi, durum skoru) baglamini
ve sonucunu (satildi / satilmadi / zarar) kaydeder; bu baglamlarin gercek
basari oranini cikarir.

EN ONEMLI OZELLIK — ORNEKLEM KAPISI:
2 veriyle karar vermez. Bir baglamin onerilebilmesi icin en az MIN_SAMPLE
gozlem gerekir. Az veriyle "bu platform harika" demek, kumarbaz yanilgisidir;
sistemi yanlis yone kilitler ve kotu kararlari kendi kendine onaylatir.
Yeterli veri yoksa acikca "henuz bilmiyorum" der.

Saf modul: DB baglantisi disaridan verilir -> izole test edilir.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Optional

# Bir baglam hakkinda konusabilmek icin gereken en az gozlem sayisi.
# Dusuk tutulursa sistem gurultuye tepki verir; yuksek tutulursa hicbir sey
# ogrenemez. 8, kucuk bir katalog icin makul bir orta yol.
MIN_SAMPLE = 8
# Bu oranin altindaki baglamlar "kacinilmali" sayilir.
POOR_SUCCESS_RATE = 0.15
GOOD_SUCCESS_RATE = 0.40

PRICE_BANDS = ((0, 20), (20, 35), (35, 50), (50, 100), (100, 10_000))


@dataclass
class ContextStats:
    context_key: str
    platform: str = ""
    brand: str = ""
    price_band: str = ""
    samples: int = 0
    sold: int = 0
    profit_sum: float = 0.0

    @property
    def success_rate(self) -> float:
        return (self.sold / self.samples) if self.samples else 0.0

    @property
    def avg_profit(self) -> float:
        return (self.profit_sum / self.samples) if self.samples else 0.0

    @property
    def confident(self) -> bool:
        """Yeterli gozlem var mi — yoksa bu istatistik KULLANILMAZ."""
        return self.samples >= MIN_SAMPLE


@dataclass
class Recommendation:
    verdict: str            # "prefer" | "avoid" | "unknown"
    reason: str
    stats: Optional[ContextStats] = None
    alternatives: list[str] = field(default_factory=list)


def price_band(price: float) -> str:
    for alt, ust in PRICE_BANDS:
        if alt <= price < ust:
            return f"{alt}-{ust}"
    return "bilinmiyor"


def context_key(platform: str, brand: str, price: float) -> str:
    """Baglam anahtari: cok dar olursa hicbir zaman yeterli ornek birikmez."""
    marka = (brand or "genel").strip().lower()[:20]
    return f"{(platform or '?').lower()}|{marka}|{price_band(price or 0)}"


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Additive — var olan tablolara dokunmaz."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS outcome_stats (
            context_key TEXT PRIMARY KEY,
            platform TEXT, brand TEXT, price_band TEXT,
            samples INTEGER DEFAULT 0,
            sold INTEGER DEFAULT 0,
            profit_sum REAL DEFAULT 0,
            updated_at TEXT
        )
    """)
    conn.commit()


def record_outcome(
    conn: sqlite3.Connection,
    *,
    platform: str,
    brand: str,
    price: float,
    sold: bool,
    profit: float = 0.0,
) -> str:
    """
    Bir urunun GERCEKLESEN sonucunu isler. Tahmin degil, olan biten kaydedilir:
    satildiysa sold=True ve gercek kar; satilmadiysa sold=False.
    """
    ensure_schema(conn)
    key = context_key(platform, brand, price)
    conn.execute("""
        INSERT INTO outcome_stats (context_key, platform, brand, price_band,
                                   samples, sold, profit_sum, updated_at)
        VALUES (?,?,?,?,1,?,?,datetime('now'))
        ON CONFLICT(context_key) DO UPDATE SET
            samples = samples + 1,
            sold = sold + ?,
            profit_sum = profit_sum + ?,
            updated_at = datetime('now')
    """, (key, (platform or "").lower(), (brand or "genel").lower(),
          price_band(price or 0), 1 if sold else 0, profit,
          1 if sold else 0, profit))
    conn.commit()
    return key


def get_stats(conn: sqlite3.Connection, key: str) -> Optional[ContextStats]:
    ensure_schema(conn)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM outcome_stats WHERE context_key=?", (key,)).fetchone()
    if not row:
        return None
    return ContextStats(
        context_key=row["context_key"], platform=row["platform"],
        brand=row["brand"], price_band=row["price_band"],
        samples=row["samples"], sold=row["sold"], profit_sum=row["profit_sum"])


def recommend(conn: sqlite3.Connection, *, platform: str, brand: str,
              price: float) -> Recommendation:
    """
    Bu baglamda kazima/alim yapilmali mi?

    Yeterli gozlem yoksa "unknown" doner — bu bir kusur degil, DURUSTLUK:
    az veriyle verilen karar, sistemi yanlis yone kilitler.
    """
    key = context_key(platform, brand, price)
    stats = get_stats(conn, key)

    if stats is None or not stats.confident:
        var_olan = stats.samples if stats else 0
        return Recommendation(
            verdict="unknown",
            reason=(f"yeterli gozlem yok ({var_olan}/{MIN_SAMPLE}) — "
                    "bu baglam hakkinda konusmak icin erken"),
            stats=stats)

    if stats.success_rate < POOR_SUCCESS_RATE:
        return Recommendation(
            verdict="avoid",
            reason=(f"{stats.samples} gozlemde satis orani %{stats.success_rate*100:.0f} "
                    f"(esik %{POOR_SUCCESS_RATE*100:.0f}), ortalama kar "
                    f"{stats.avg_profit:+.2f} EUR"),
            stats=stats,
            alternatives=_better_contexts(conn, stats))

    if stats.success_rate >= GOOD_SUCCESS_RATE:
        return Recommendation(
            verdict="prefer",
            reason=(f"{stats.samples} gozlemde satis orani %{stats.success_rate*100:.0f}, "
                    f"ortalama kar {stats.avg_profit:+.2f} EUR"),
            stats=stats)

    return Recommendation(
        verdict="unknown",
        reason=(f"{stats.samples} gozlemde satis orani %{stats.success_rate*100:.0f} — "
                "ne iyi ne kotu, belirgin bir sinyal yok"),
        stats=stats)


def _better_contexts(conn: sqlite3.Connection, worse: ContextStats,
                     limit: int = 3) -> list[str]:
    """Kacinilmasi onerilen bir baglamin yerine ne denenebilir."""
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT context_key, samples, sold FROM outcome_stats
        WHERE samples >= ? AND context_key != ?
        ORDER BY (CAST(sold AS REAL)/samples) DESC LIMIT ?
    """, (MIN_SAMPLE, worse.context_key, limit)).fetchall()
    return [f"{r['context_key']} (%{100*r['sold']/r['samples']:.0f})" for r in rows]


def top_contexts(conn: sqlite3.Connection, limit: int = 10) -> list[ContextStats]:
    """En iyi calisan baglamlar — SADECE yeterli gozlemi olanlar."""
    ensure_schema(conn)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT * FROM outcome_stats WHERE samples >= ?
        ORDER BY (CAST(sold AS REAL)/samples) DESC, profit_sum DESC LIMIT ?
    """, (MIN_SAMPLE, limit)).fetchall()
    return [ContextStats(context_key=r["context_key"], platform=r["platform"],
                         brand=r["brand"], price_band=r["price_band"],
                         samples=r["samples"], sold=r["sold"],
                         profit_sum=r["profit_sum"]) for r in rows]
