"""
Olay otobüsü + kendi-kendini-planlayan is kaydi (additive, Faz 0).

Bu modul, tum sistemin "sinir sistemi"dir. Iki gorevi var:
  1) EVENTS: her asama (scrape/score/image/video/social/reprice/manager...) ne
     yaptigini YAPISAL yazar (status + makine-okunur metrik/hata kodu). Manager
     ve teshis-LLM'i dogal-dil sohbet yerine bu otobusu okur. Ucuz, deterministik.
  2) SCHEDULED_JOBS: "gunde 5 reklam", "satilmayan urun arastirmasi", "aging
     reprice" gibi tekrarlayan isler burada kayitli. Manager dongusu vadesi
     gelenleri tetikler. Hafif periyot (cron degil) — gereksiz yuk yok.

Additive: app.py'ye dokunmaz, ayni aiosqlite hub.db'ye iki yeni tablo acar.
Dis hesap/anahtar/servis gerektirmez. Telegram/oda katmani sonradan bu otobusun
UZERINE oturur (sifir refactor).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import aiosqlite
from pydantic import BaseModel

_BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_FILE = str(_BASE_DIR / "data" / "hub.db")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _parse(s: str) -> datetime:
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return _now()


# --------------------------------------------------------------------------
# Modeller
# --------------------------------------------------------------------------
class Event(BaseModel):
    id: Optional[int] = None
    stage: str
    status: str            # started|ok|warn|failed|blocked|escalated
    level: str = "info"    # info|warning|error
    product_id: Optional[str] = None
    error_code: Optional[str] = None   # makine-okunur: vinted_blocked, low_yield, qc_hole...
    metric: dict = {}
    message: Optional[str] = None
    created_at: Optional[str] = None


class ScheduledJob(BaseModel):
    id: str                # benzersiz ad: daily_ads, unsold_research, aging_reprice
    kind: str              # manager'in tanidigi eylem turu
    interval_seconds: int
    daily_cap: Optional[int] = None    # gunluk ust sinir (ör. 5 reklam)
    enabled: bool = True
    last_run: Optional[str] = None
    next_run: Optional[str] = None
    runs_today: int = 0
    config: dict = {}


# --------------------------------------------------------------------------
# Sema (additive)
# --------------------------------------------------------------------------
async def init_bus(db_file: str = DEFAULT_DB_FILE) -> None:
    async with aiosqlite.connect(db_file) as db:
        await db.executescript(
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                stage TEXT NOT NULL,
                status TEXT NOT NULL,
                level TEXT DEFAULT 'info',
                product_id TEXT,
                error_code TEXT,
                metric_json TEXT DEFAULT '{}',
                message TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_events_stage ON events(stage, created_at);
            CREATE INDEX IF NOT EXISTS idx_events_status ON events(status, created_at);

            CREATE TABLE IF NOT EXISTS scheduled_jobs (
                id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                interval_seconds INTEGER NOT NULL,
                daily_cap INTEGER,
                enabled INTEGER DEFAULT 1,
                last_run TEXT,
                next_run TEXT,
                runs_today INTEGER DEFAULT 0,
                today_date TEXT,
                config_json TEXT DEFAULT '{}',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        await db.commit()


# --------------------------------------------------------------------------
# EVENTS
# --------------------------------------------------------------------------
async def emit(
    stage: str,
    status: str,
    *,
    level: str = "info",
    product_id: Optional[str] = None,
    error_code: Optional[str] = None,
    metric: Optional[dict] = None,
    message: Optional[str] = None,
    db_file: str = DEFAULT_DB_FILE,
) -> int:
    """Yapisal bir olay yazar; olay id'sini dondurur."""
    async with aiosqlite.connect(db_file) as db:
        cur = await db.execute(
            """INSERT INTO events
               (stage, status, level, product_id, error_code, metric_json, message, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (stage, status, level, product_id, error_code,
             json.dumps(metric or {}), message, _iso(_now())),
        )
        await db.commit()
        return cur.lastrowid


async def recent(
    *,
    stage: Optional[str] = None,
    status: Optional[str] = None,
    since_minutes: Optional[int] = None,
    limit: int = 100,
    db_file: str = DEFAULT_DB_FILE,
) -> list[Event]:
    where, params = [], []
    if stage:
        where.append("stage = ?"); params.append(stage)
    if status:
        where.append("status = ?"); params.append(status)
    if since_minutes:
        cutoff = _iso(_now() - timedelta(minutes=since_minutes))
        where.append("created_at >= ?"); params.append(cutoff)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    async with aiosqlite.connect(db_file) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            f"SELECT * FROM events {where_sql} ORDER BY id DESC LIMIT ?",
            (*params, limit),
        )
        rows = await cur.fetchall()
    out = []
    for r in rows:
        out.append(Event(
            id=r["id"], stage=r["stage"], status=r["status"], level=r["level"],
            product_id=r["product_id"], error_code=r["error_code"],
            metric=json.loads(r["metric_json"] or "{}"),
            message=r["message"], created_at=r["created_at"],
        ))
    return out


async def summarize(
    stage: str, *, since_minutes: int = 60, db_file: str = DEFAULT_DB_FILE
) -> dict:
    """
    Manager karari icin ozet: son X dakikada stage'in status dagilimi + son hata.
    Ornek: {"failed": 3, "blocked": 1, "ok": 12, "last_error_code": "vinted_blocked"}.
    """
    cutoff = _iso(_now() - timedelta(minutes=since_minutes))
    async with aiosqlite.connect(db_file) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT status, COUNT(*) c FROM events WHERE stage=? AND created_at>=? GROUP BY status",
            (stage, cutoff),
        )
        counts = {r["status"]: r["c"] for r in await cur.fetchall()}
        cur = await db.execute(
            "SELECT error_code FROM events WHERE stage=? AND created_at>=? AND error_code IS NOT NULL "
            "ORDER BY id DESC LIMIT 1", (stage, cutoff),
        )
        row = await cur.fetchone()
    counts["last_error_code"] = row["error_code"] if row else None
    counts["window_minutes"] = since_minutes
    return counts


# --------------------------------------------------------------------------
# SCHEDULED JOBS (kendi-kendini planlama)
# --------------------------------------------------------------------------
async def register_job(
    job_id: str,
    kind: str,
    *,
    interval_seconds: Optional[int] = None,
    daily_cap: Optional[int] = None,
    config: Optional[dict] = None,
    enabled: bool = True,
    db_file: str = DEFAULT_DB_FILE,
) -> None:
    """
    Tekrarlayan is kaydeder/gunceller (idempotent). interval_seconds verilmezse
    daily_cap'ten hesaplanir (gunu esit araliga boler — ör. 5 reklam -> her ~4.8s).
    """
    if interval_seconds is None:
        if not daily_cap:
            raise ValueError("interval_seconds veya daily_cap gerekli")
        interval_seconds = max(1, 86400 // daily_cap)
    now = _now()
    async with aiosqlite.connect(db_file) as db:
        await db.execute(
            """INSERT INTO scheduled_jobs
               (id, kind, interval_seconds, daily_cap, enabled, next_run, today_date, config_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 kind=excluded.kind, interval_seconds=excluded.interval_seconds,
                 daily_cap=excluded.daily_cap, enabled=excluded.enabled,
                 config_json=excluded.config_json""",
            (job_id, kind, interval_seconds, daily_cap, 1 if enabled else 0,
             _iso(now), now.strftime("%Y-%m-%d"), json.dumps(config or {})),
        )
        await db.commit()


async def due_jobs(db_file: str = DEFAULT_DB_FILE) -> list[ScheduledJob]:
    """Vadesi gelmis (next_run<=now), aktif ve gunluk kotasi dolmamis isler."""
    now = _now()
    today = now.strftime("%Y-%m-%d")
    async with aiosqlite.connect(db_file) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM scheduled_jobs WHERE enabled=1 AND (next_run IS NULL OR next_run<=?)",
            (_iso(now),),
        )
        rows = await cur.fetchall()
    out = []
    for r in rows:
        runs_today = r["runs_today"] if r["today_date"] == today else 0
        if r["daily_cap"] and runs_today >= r["daily_cap"]:
            continue  # gunluk kota dolu
        out.append(ScheduledJob(
            id=r["id"], kind=r["kind"], interval_seconds=r["interval_seconds"],
            daily_cap=r["daily_cap"], enabled=bool(r["enabled"]),
            last_run=r["last_run"], next_run=r["next_run"],
            runs_today=runs_today, config=json.loads(r["config_json"] or "{}"),
        ))
    return out


async def mark_ran(job_id: str, db_file: str = DEFAULT_DB_FILE) -> None:
    """Is calisti: last_run/next_run guncelle, gunluk sayaci (gun degistiyse sifirla) artir."""
    now = _now()
    today = now.strftime("%Y-%m-%d")
    async with aiosqlite.connect(db_file) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT interval_seconds, runs_today, today_date FROM scheduled_jobs WHERE id=?", (job_id,))
        row = await cur.fetchone()
        if not row:
            return
        runs_today = (row["runs_today"] if row["today_date"] == today else 0) + 1
        next_run = _iso(now + timedelta(seconds=row["interval_seconds"]))
        await db.execute(
            "UPDATE scheduled_jobs SET last_run=?, next_run=?, runs_today=?, today_date=? WHERE id=?",
            (_iso(now), next_run, runs_today, today, job_id),
        )
        await db.commit()


async def set_enabled(job_id: str, enabled: bool, db_file: str = DEFAULT_DB_FILE) -> None:
    async with aiosqlite.connect(db_file) as db:
        await db.execute("UPDATE scheduled_jobs SET enabled=? WHERE id=?", (1 if enabled else 0, job_id))
        await db.commit()
