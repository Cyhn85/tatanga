"""
Deterministik Manager (Faz 1) — kod, LLM DEGIL.

Gorevi: olay otobusunu ve is kaydini yoneten "yonetici". Her tick'te:
  1) Vadesi gelen isleri (event_bus.due_jobs) ilgili handler'a dagitir, sonucu
     yapisal olay olarak yazar, is'i mark_ran eder.
  2) Eskalasyon taramasi: bir asamada son pencerede hata esigi asildiysa
     "escalated" olayi basar. Faz 2'de teshis-LLM'i (ucretsiz Groq) bu olayi
     dinleyip nedeni okuyacak ve direktif onerecek. Faz 1'de LLM YOK — sadece
     yapisal isaret + (ban ise) geri-cekil sinyali.

Handler'lar `register_handler(kind, async_fn)` ile kaydedilir; her handler bir
ScheduledJob alir ve istege bagli bir metric dict dondurur. Boylece video/sosyal/
reprice modulleri de sadece birer handler olarak eklenir — manager degismez.

Additive: app.py'ye dokunmaz. Dis servis/LLM gerektirmez.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable, Optional

import aiosqlite

from . import event_bus as bus
from . import state_machine as sm

Handler = Callable[[bus.ScheduledJob], Awaitable[Optional[dict]]]

_HANDLERS: dict[str, Handler] = {}

# Bir asamada son ESCALATION_WINDOW dk'da bu kadar 'failed' olursa eskale et.
ESCALATION_THRESHOLD = 3
ESCALATION_WINDOW_MIN = 30
# Ban benzeri hatalar: eskalasyonda "geri cekil" isareti tasinir (agresif atlatma YOK).
BACKOFF_ERROR_CODES = {"vinted_blocked", "blocked", "captcha", "rate_limited", "akamai_blocked"}


def register_handler(kind: str, fn: Handler) -> None:
    _HANDLERS[kind] = fn


def registered_kinds() -> list[str]:
    return sorted(_HANDLERS.keys())


# --------------------------------------------------------------------------
# Tek tur (tick)
# --------------------------------------------------------------------------
async def tick(db_file: str = bus.DEFAULT_DB_FILE) -> dict:
    """Bir yonetim turu: vadesi gelen isleri calistir + eskalasyon tara."""
    ran = failed = 0
    for job in await bus.due_jobs(db_file=db_file):
        handler = _HANDLERS.get(job.kind)
        await bus.emit(job.kind, "started", db_file=db_file)
        if handler is None:
            await bus.emit(job.kind, "failed", level="error", error_code="no_handler",
                           message=f"'{job.kind}' icin handler kayitli degil", db_file=db_file)
            await bus.mark_ran(job.id, db_file=db_file)
            failed += 1
            continue
        try:
            result = await handler(job)
            await bus.emit(job.kind, "ok",
                           metric=result if isinstance(result, dict) else {},
                           db_file=db_file)
            ran += 1
        except Exception as e:  # handler patlarsa sistem cokmesin
            await bus.emit(job.kind, "failed", level="error",
                           error_code="handler_exception", message=str(e)[:300],
                           db_file=db_file)
            failed += 1
        finally:
            await bus.mark_ran(job.id, db_file=db_file)

    escalations = await _scan_escalations(db_file=db_file)
    return {"ran": ran, "failed": failed, "escalations": escalations}


async def _distinct_failed_stages(db_file: str, since_min: int) -> list[str]:
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=since_min)).strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(db_file) as db:
        cur = await db.execute(
            "SELECT DISTINCT stage FROM events WHERE status='failed' AND created_at>=?",
            (cutoff,),
        )
        return [r[0] for r in await cur.fetchall()]


async def _scan_escalations(db_file: str = bus.DEFAULT_DB_FILE) -> list[dict]:
    """
    Hata esigi asan asamalar icin 'escalated' olayi basar (tekrar-eskale etmemek
    icin son pencerede zaten escalated varsa atlar). Ban kodu varsa backoff=True.
    """
    out: list[dict] = []
    for stage in await _distinct_failed_stages(db_file, ESCALATION_WINDOW_MIN):
        summ = await bus.summarize(stage, since_minutes=ESCALATION_WINDOW_MIN, db_file=db_file)
        if summ.get("failed", 0) < ESCALATION_THRESHOLD:
            continue
        # zaten eskale edilmis mi?
        already = await bus.recent(stage=stage, status="escalated",
                                   since_minutes=ESCALATION_WINDOW_MIN, limit=1, db_file=db_file)
        if already:
            continue
        err = summ.get("last_error_code")
        backoff = err in BACKOFF_ERROR_CODES
        await bus.emit(
            stage, "escalated", level="warning", error_code=err,
            metric={"failed": summ.get("failed"), "backoff": backoff,
                    "window_min": ESCALATION_WINDOW_MIN},
            message=("BAN suphesi -> geri cekil + kullaniciya bildir"
                     if backoff else "tekrarlayan hata -> teshis gerekli"),
            db_file=db_file,
        )
        out.append({"stage": stage, "failed": summ.get("failed"),
                    "error_code": err, "backoff": backoff})
    return out


# --------------------------------------------------------------------------
# Yerlesik guvenli handler'lar + varsayilan isler
# --------------------------------------------------------------------------
async def _handler_expire_locks(job: bus.ScheduledJob) -> dict:
    """Suresi gecmis soft-lock'lari temizler (state_machine). Tamamen guvenli."""
    n = await sm.expire_stale_locks()
    return {"expired_locks": n}


register_handler("expire_locks", _handler_expire_locks)


async def install_default_jobs(db_file: str = bus.DEFAULT_DB_FILE) -> None:
    """
    Uygulama acilisinda cagrilir: guvenli tekrarlayan isleri kaydeder. Simdilik
    sadece kilit temizligi; video/reklam/reprice handler'lari eklendikce buraya
    register_job satirlari eklenir.
    """
    await bus.init_bus(db_file=db_file)
    await bus.register_job("expire_locks", kind="expire_locks",
                           interval_seconds=600, db_file=db_file)  # her 10 dk


async def run_loop(
    interval_seconds: int = 60,
    db_file: str = bus.DEFAULT_DB_FILE,
) -> None:
    """
    Canli yonetici dongusu (app.py startup'inda asyncio task olarak baslatilir).
    Her turda: vadesi gelen isleri calistir (tick) + eskalasyonlari teshis et.
    Dongu ASLA olmez — bir tur patlarsa loglar, bekler, devam eder.
    """
    import asyncio
    from . import diagnostician as dx  # lazy import (dongusel bagimliligi onler)
    from . import handlers as _handlers  # import: is handler'larini register eder

    try:
        await install_default_jobs(db_file=db_file)
        await _handlers.install_jobs(db_file=db_file)  # aging_reprice vb.
        await bus.emit("manager", "started",
                       message=f"yonetici dongusu ({interval_seconds}s), handler'lar: {registered_kinds()}",
                       db_file=db_file)
    except Exception as e:
        print(f"[MANAGER] baslangic hatasi: {e}")

    while True:
        try:
            await tick(db_file=db_file)
            await dx.process_escalations(db_file=db_file)
        except Exception as e:  # dongu hayatta kalsin
            try:
                await bus.emit("manager", "failed", level="error",
                               error_code="loop_exception", message=str(e)[:200],
                               db_file=db_file)
            except Exception:
                pass
        await asyncio.sleep(interval_seconds)
