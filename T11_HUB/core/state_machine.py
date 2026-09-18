"""
TATANGA urun yasam-dongusu durum makinesi (additive katman).

Bu modul mevcut app.py'ye DOKUNMAZ. Ayni aiosqlite veritabanini (data/hub.db)
kullanir ve products.status alanini kanonik bir durum sozlugu ile yonetir.
Mevcut kodun yazdigi status degerleri (scraped, published, sold, failed) bu
sozlugun ICINDEDIR; yeni ara durumlar (analyzing, awaiting_approval, purchased,
inbound, quality_check, shipped ...) bunlarin ustune eklenir. Boylece eski akis
bozulmaz, yeni orkestrasyon akislari validasyonlu gecisler kullanabilir.

Iki YENI, additive tablo acar (mevcut tablolara dokunmadan):
  - state_transitions : her durum gecisinin denetim (audit) kaydi + crash gorunurlugu
  - product_locks     : soft-lock (ayni urunu iki akisin ayni anda islememesi icin)

Hicbir dis hesap/anahtar/kimlik bilgisi gerektirmez.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

import aiosqlite
from pydantic import BaseModel, Field

# --------------------------------------------------------------------------
# Veritabani yolu — app.py ile ayni dosya (data/hub.db).
# core/ dizini T11_HUB/ altinda oldugu icin parent.parent = T11_HUB.
# --------------------------------------------------------------------------
_BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_FILE = str(_BASE_DIR / "data" / "hub.db")


def _now_iso() -> str:
    """app.py'nin TEXT/ISO zaman bicimiyle uyumlu UTC damgasi."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


# --------------------------------------------------------------------------
# Kanonik durum sozlugu (mevcut degerlerin UST KUMESI)
# --------------------------------------------------------------------------
class ProductState(str, Enum):
    # -- Mevcut app.py'nin zaten yazdiklari (asla degistirilmez) --
    SCRAPED = "scraped"          # kazindi (mevcut varsayilan)
    PUBLISHED = "published"      # bizim tarafta/dis platformda yayinda (mevcut)
    SOLD = "sold"                # satildi (mevcut)
    FAILED = "failed"            # hata (mevcut)

    # -- Arbitraj/envanter icin eklenen ara durumlar --
    ANALYZING = "analyzing"          # kar/skor analizi yapiliyor
    AWAITING_APPROVAL = "awaiting_approval"  # insan onayi bekleniyor
    APPROVED = "approved"            # kullanici onayladi
    OFFER_SENT = "offer_sent"        # saticiya teklif/mesaj gonderildi (Kleinanzeigen vb.)
    PURCHASED = "purchased"          # kaynaktan satin alindi
    INBOUND = "inbound"              # bize dogru kargoda
    QUALITY_CHECK = "quality_check"  # depoya geldi, kalite kontrolde
    SHIPPED = "shipped"              # alici tarafina gonderildi
    REJECTED = "rejected"            # elendi (dusuk skor / iptal)
    ARCHIVED = "archived"            # arsivlendi (terminal)


TERMINAL_STATES: frozenset[ProductState] = frozenset(
    {ProductState.ARCHIVED}
)

# Izin verilen gecisler. Eski kisayollar (scraped->published, published->sold)
# bilincli olarak korunur ki mevcut davranisla celismesin.
TRANSITIONS: dict[ProductState, frozenset[ProductState]] = {
    ProductState.SCRAPED: frozenset({
        ProductState.ANALYZING,
        ProductState.PUBLISHED,   # legacy kisayol (app.py bunu yapiyor)
        ProductState.FAILED,
        ProductState.REJECTED,
        ProductState.ARCHIVED,
    }),
    ProductState.ANALYZING: frozenset({
        ProductState.AWAITING_APPROVAL,
        ProductState.REJECTED,
        ProductState.FAILED,
        ProductState.ARCHIVED,
    }),
    ProductState.AWAITING_APPROVAL: frozenset({
        ProductState.APPROVED,
        ProductState.REJECTED,
        ProductState.FAILED,
    }),
    ProductState.APPROVED: frozenset({
        ProductState.OFFER_SENT,
        ProductState.PURCHASED,
        ProductState.REJECTED,
        ProductState.FAILED,
    }),
    ProductState.OFFER_SENT: frozenset({
        ProductState.APPROVED,     # karsi teklif turu
        ProductState.PURCHASED,
        ProductState.REJECTED,
        ProductState.FAILED,
    }),
    ProductState.PURCHASED: frozenset({
        ProductState.INBOUND,
        ProductState.PUBLISHED,    # stoklamadan direkt yayina alma senaryosu
        ProductState.FAILED,
    }),
    ProductState.INBOUND: frozenset({
        ProductState.QUALITY_CHECK,
        ProductState.FAILED,
    }),
    ProductState.QUALITY_CHECK: frozenset({
        ProductState.PUBLISHED,
        ProductState.REJECTED,
        ProductState.ARCHIVED,
    }),
    ProductState.PUBLISHED: frozenset({
        ProductState.SOLD,         # legacy (app.py bunu yapiyor)
        ProductState.ARCHIVED,
        ProductState.FAILED,
    }),
    ProductState.SOLD: frozenset({
        ProductState.SHIPPED,
        ProductState.ARCHIVED,
    }),
    ProductState.SHIPPED: frozenset({
        ProductState.ARCHIVED,
    }),
    ProductState.REJECTED: frozenset({
        ProductState.ARCHIVED,
    }),
    ProductState.FAILED: frozenset({
        ProductState.ANALYZING,    # yeniden deneme
        ProductState.ARCHIVED,
    }),
    ProductState.ARCHIVED: frozenset(),  # terminal
}


# --------------------------------------------------------------------------
# Pydantic modelleri (yapisal donusler)
# --------------------------------------------------------------------------
class TransitionResult(BaseModel):
    product_id: str
    from_state: Optional[str] = None
    to_state: str
    ok: bool
    forced: bool = False
    reason: Optional[str] = None
    at: str = Field(default_factory=_now_iso)


class LockInfo(BaseModel):
    product_id: str
    owner: str
    reason: Optional[str] = None
    locked_at: str
    expires_at: str

    def is_expired(self, now: Optional[datetime] = None) -> bool:
        now = now or datetime.now(timezone.utc)
        try:
            exp = datetime.strptime(self.expires_at, "%Y-%m-%d %H:%M:%S").replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            return True
        return now >= exp


# --------------------------------------------------------------------------
# Sema kurulumu (additive — mevcut tablolara dokunmaz)
# --------------------------------------------------------------------------
async def init_state_tables(db_file: str = DEFAULT_DB_FILE) -> None:
    """Iki yeni additive tabloyu (idempotent) olusturur."""
    async with aiosqlite.connect(db_file) as db:
        await db.executescript(
            """
            CREATE TABLE IF NOT EXISTS state_transitions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id TEXT NOT NULL,
                from_state TEXT,
                to_state TEXT NOT NULL,
                actor TEXT DEFAULT 'system',
                forced INTEGER DEFAULT 0,
                reason TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_state_tx_product
                ON state_transitions(product_id);

            CREATE TABLE IF NOT EXISTS product_locks (
                product_id TEXT PRIMARY KEY,
                owner TEXT NOT NULL,
                reason TEXT,
                locked_at TEXT DEFAULT CURRENT_TIMESTAMP,
                expires_at TEXT NOT NULL
            );
            """
        )
        await db.commit()


# --------------------------------------------------------------------------
# Durum okuma / gecis
# --------------------------------------------------------------------------
def can_transition(from_state: str, to_state: str) -> bool:
    """Gecis izinli mi? Bilinmeyen from_state serbest birakilir (eski veriler)."""
    try:
        src = ProductState(from_state)
    except ValueError:
        return True  # eski/bilinmeyen durumdan cikisa izin ver
    try:
        dst = ProductState(to_state)
    except ValueError:
        return False
    return dst in TRANSITIONS.get(src, frozenset())


async def get_status(product_id: str, db_file: str = DEFAULT_DB_FILE) -> Optional[str]:
    async with aiosqlite.connect(db_file) as db:
        cur = await db.execute(
            "SELECT status FROM products WHERE id = ?", (product_id,)
        )
        row = await cur.fetchone()
        return row[0] if row else None


async def transition(
    product_id: str,
    to_state: str,
    *,
    reason: Optional[str] = None,
    actor: str = "system",
    force: bool = False,
    db_file: str = DEFAULT_DB_FILE,
) -> TransitionResult:
    """
    products.status'i gunceller ve state_transitions'a audit kaydi yazar.
    Izinsiz gecisi force=True olmadan reddeder (ok=False dondurur, yazmaz).
    """
    to_norm = to_state.value if isinstance(to_state, ProductState) else str(to_state)
    current = await get_status(product_id, db_file)

    if current is None:
        return TransitionResult(
            product_id=product_id, from_state=None, to_state=to_norm,
            ok=False, reason="urun bulunamadi",
        )

    allowed = can_transition(current, to_norm)
    if not allowed and not force:
        return TransitionResult(
            product_id=product_id, from_state=current, to_state=to_norm,
            ok=False, reason=f"izinsiz gecis: {current} -> {to_norm}",
        )

    now = _now_iso()
    async with aiosqlite.connect(db_file) as db:
        await db.execute(
            "UPDATE products SET status = ?, updated_at = ? WHERE id = ?",
            (to_norm, now, product_id),
        )
        await db.execute(
            """INSERT INTO state_transitions
               (product_id, from_state, to_state, actor, forced, reason, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (product_id, current, to_norm, actor, 1 if (force and not allowed) else 0,
             reason, now),
        )
        await db.commit()

    return TransitionResult(
        product_id=product_id, from_state=current, to_state=to_norm,
        ok=True, forced=(force and not allowed), reason=reason, at=now,
    )


async def get_history(
    product_id: str, db_file: str = DEFAULT_DB_FILE
) -> list[dict]:
    async with aiosqlite.connect(db_file) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """SELECT from_state, to_state, actor, forced, reason, created_at
               FROM state_transitions WHERE product_id = ?
               ORDER BY id ASC""",
            (product_id,),
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


# --------------------------------------------------------------------------
# Soft-lock (ayni urunu iki akisin ayni anda islememesi icin)
# --------------------------------------------------------------------------
async def acquire_lock(
    product_id: str,
    owner: str,
    *,
    ttl_hours: int = 48,
    reason: Optional[str] = None,
    db_file: str = DEFAULT_DB_FILE,
) -> bool:
    """
    Urun icin soft-lock alir. Aktif (suresi dolmamis) bir kilit varsa False doner.
    Suresi dolmus kilit varsa devralir. Basarida True.
    """
    now_dt = datetime.now(timezone.utc)
    now = now_dt.strftime("%Y-%m-%d %H:%M:%S")
    expires = (now_dt + timedelta(hours=ttl_hours)).strftime("%Y-%m-%d %H:%M:%S")

    async with aiosqlite.connect(db_file) as db:
        cur = await db.execute(
            "SELECT owner, expires_at FROM product_locks WHERE product_id = ?",
            (product_id,),
        )
        row = await cur.fetchone()
        if row is not None:
            exp_str = row[1]
            try:
                exp_dt = datetime.strptime(exp_str, "%Y-%m-%d %H:%M:%S").replace(
                    tzinfo=timezone.utc
                )
            except ValueError:
                exp_dt = now_dt  # bozuk damga -> suresi dolmus say
            if now_dt < exp_dt:
                return False  # aktif kilit var
        await db.execute(
            """INSERT INTO product_locks (product_id, owner, reason, locked_at, expires_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(product_id) DO UPDATE SET
                   owner=excluded.owner, reason=excluded.reason,
                   locked_at=excluded.locked_at, expires_at=excluded.expires_at""",
            (product_id, owner, reason, now, expires),
        )
        await db.commit()
        return True


async def release_lock(
    product_id: str, owner: Optional[str] = None, db_file: str = DEFAULT_DB_FILE
) -> bool:
    """Kilidi birakir. owner verilirse sadece o sahibin kilidini siler."""
    async with aiosqlite.connect(db_file) as db:
        if owner is None:
            cur = await db.execute(
                "DELETE FROM product_locks WHERE product_id = ?", (product_id,)
            )
        else:
            cur = await db.execute(
                "DELETE FROM product_locks WHERE product_id = ? AND owner = ?",
                (product_id, owner),
            )
        await db.commit()
        return cur.rowcount > 0


async def get_lock(
    product_id: str, db_file: str = DEFAULT_DB_FILE
) -> Optional[LockInfo]:
    async with aiosqlite.connect(db_file) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT product_id, owner, reason, locked_at, expires_at "
            "FROM product_locks WHERE product_id = ?",
            (product_id,),
        )
        row = await cur.fetchone()
        return LockInfo(**dict(row)) if row else None


async def is_locked(product_id: str, db_file: str = DEFAULT_DB_FILE) -> bool:
    info = await get_lock(product_id, db_file)
    return bool(info) and not info.is_expired()


async def expire_stale_locks(db_file: str = DEFAULT_DB_FILE) -> int:
    """Suresi dolmus kilitleri temizler. Zamanlayici bunu periyodik cagirir."""
    now = _now_iso()
    async with aiosqlite.connect(db_file) as db:
        cur = await db.execute(
            "DELETE FROM product_locks WHERE expires_at <= ?", (now,)
        )
        await db.commit()
        return cur.rowcount
