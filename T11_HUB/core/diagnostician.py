"""
Teshis katmani (Faz 2) — olay-tetikli, ANAHTARSIZ calisir.

Manager bir asamada hata esigini asinca 'escalated' olayi basar. Bu modul o
olaylari okur, hatanin nedenini KURAL-TABANLI teshis eder ve yapisal bir direktif
uretir ('diagnosed' olayi). %95 zaman sifir LLM maliyeti.

Groq ikinci-gorus (llm-council mini) icin dikis hazir: `_llm_second_opinion`
anahtar YOKSA None doner (bugun kural-tabanli calisir); anahtar gelince kural +
Groq capraz-dogrulanir. "API en sonda" kuralina sadik.

GUVENLIK: ban benzeri hatada direktif her zaman GERI CEKIL + BILDIR (backoff),
otomatik agresif atlatma asla onerilmez. Riskli/dusuk-guven direktifler
`needs_human=True` ile insana birakilir (ileride Telegram onay odasi).
"""

from __future__ import annotations

import asyncio
from typing import Optional

from pydantic import BaseModel

from . import event_bus as bus

WINDOW_MIN = 30  # 'escalated' olaylarini bu pencerede tara


class Diagnosis(BaseModel):
    stage: str
    error_code: Optional[str] = None
    cause: str
    directive: str            # makine-okunur eylem ipucu
    directive_label: str      # insan-okunur
    confidence: float         # 0-1
    backoff: bool = False     # ban benzeri -> geri cekil
    needs_human: bool = False
    auto_applicable: bool = False   # guvenli, otomatik uygulanabilir mi
    source: str = "rule"      # "rule" | "rule+groq"


# error_code (kucuk harf) -> teshis kurali. Bilinmeyen -> _DEFAULT.
_RULES: dict[str, dict] = {
    # --- Platform blok / bot-koruma: DAIMA geri cekil + bildir ---
    "vinted_blocked": dict(
        cause="Vinted bot-koruması/geçici blok",
        directive="backoff_and_notify",
        directive_label="Bu platformda kazımayı duraklat, oturumu soğut, kullanıcıya bildir",
        confidence=0.9, backoff=True, needs_human=True, auto_applicable=True),
    "akamai_blocked": dict(
        cause="Kleinanzeigen/Akamai bot-koruma",
        directive="backoff_and_notify",
        directive_label="Duraklat + soğut + bildir",
        confidence=0.9, backoff=True, needs_human=True, auto_applicable=True),
    "blocked": dict(
        cause="Platform bloğu",
        directive="backoff_and_notify",
        directive_label="Duraklat + bildir",
        confidence=0.85, backoff=True, needs_human=True, auto_applicable=True),
    "captcha": dict(
        cause="CAPTCHA duvarı",
        directive="backoff_and_notify",
        directive_label="Otomatik çözme YOK — duraklat + kullanıcıya bildir",
        confidence=0.95, backoff=True, needs_human=True, auto_applicable=True),
    "rate_limited": dict(
        cause="Hız sınırı (429)",
        directive="backoff_and_retry_later",
        directive_label="Bekleme süresini artır, daha sonra tekrar dene",
        confidence=0.85, backoff=True, needs_human=False, auto_applicable=True),

    # --- Az verim: filtre/facet/dil ---
    "low_yield": dict(
        cause="Az ürün: filtre çok sıkı, facet tükenmiş ya da yerel-dil arama eksik olabilir",
        directive="widen_search",
        directive_label="Facet döndür (renk/fiyat/sıralama), min_quality gevşet, yerel-dil doğrula",
        confidence=0.6, backoff=False, needs_human=False, auto_applicable=False),

    # --- Kod/handler sorunlari ---
    "handler_exception": dict(
        cause="Modül kodu çalışırken hata verdi",
        directive="retry_once_then_notify",
        directive_label="Bir kez yeniden dene; yine olursa kullanıcıya bildir",
        confidence=0.7, backoff=False, needs_human=True, auto_applicable=True),
    "no_handler": dict(
        cause="Bu iş türü için kayıtlı handler yok (geliştirme eksiği)",
        directive="register_handler",
        directive_label="Handler ekle — otomatik düzeltilemez",
        confidence=1.0, backoff=False, needs_human=True, auto_applicable=False),

    # --- Gorsel QC ---
    "qc_hole": dict(
        cause="Görsel kesimi şüpheli (delikli maske / düşük kaplama)",
        directive="requeue_or_human_review",
        directive_label="Farklı matting modeliyle yeniden dene ya da insan onayına al",
        confidence=0.7, backoff=False, needs_human=True, auto_applicable=False),
}

_DEFAULT = dict(
    cause="Bilinmeyen tekrarlayan hata",
    directive="collect_logs_then_human",
    directive_label="Daha fazla log topla, kullanıcıya danış",
    confidence=0.3, backoff=False, needs_human=True, auto_applicable=False)


async def _llm_second_opinion(
    stage: str, error_code: Optional[str], *, db_file: str,
    rule_directive: str = "",
) -> Optional[dict]:
    """
    Groq ikinci-gorusu (llm-council mini).

    ANAHTAR YOKSA ya da acik onay bayragi kapaliysa None doner ve sistem
    kural-tabanli calismaya devam eder — bugunku varsayilan durum budur.

    Disariya SADECE asama adi, hata kodu ve kuralin kendi onerisi gider; log
    metni/urun verisi gonderilmez (bkz. core/groq_client.py veri siniri).
    Ag cagrisi bloklayici oldugu icin ayri bir is parcaciginda calistirilir.
    """
    from . import groq_client

    if not groq_client.is_enabled():
        return None
    return await asyncio.to_thread(
        groq_client.second_opinion, stage, error_code, rule_directive)


async def diagnose(
    stage: str, error_code: Optional[str], *, db_file: str = bus.DEFAULT_DB_FILE
) -> Diagnosis:
    rule = _RULES.get((error_code or "").lower(), _DEFAULT)
    d = Diagnosis(stage=stage, error_code=error_code, source="rule", **rule)

    second = await _llm_second_opinion(stage, error_code, db_file=db_file,
                                       rule_directive=d.directive)
    if second:
        d.source = "rule+groq"
        # capraz-dogrulama: ayni direktifte anlasirlarsa guven artar; celisirse insana
        if second.get("directive") == d.directive:
            d.confidence = min(1.0, d.confidence + 0.2)
        else:
            d.needs_human = True
            d.auto_applicable = False
            d.directive_label += f" (Groq farklı görüşte: {second.get('directive_label','?')})"
    return d


async def process_escalations(db_file: str = bus.DEFAULT_DB_FILE) -> list[Diagnosis]:
    """
    Son pencerede teshis edilmemis 'escalated' olaylarini isler, 'diagnosed'
    olayi basar. Ayni asama icin pencerede zaten teshis varsa atlar (spam yok).
    """
    out: list[Diagnosis] = []
    escalated = await bus.recent(status="escalated", since_minutes=WINDOW_MIN,
                                 limit=50, db_file=db_file)
    seen: set[str] = set()
    for ev in escalated:
        if ev.stage in seen:
            continue
        seen.add(ev.stage)
        prior = await bus.recent(stage=ev.stage, status="diagnosed",
                                 since_minutes=WINDOW_MIN, limit=1, db_file=db_file)
        if prior:
            continue
        d = await diagnose(ev.stage, ev.error_code, db_file=db_file)
        await bus.emit(
            ev.stage, "diagnosed",
            level="warning" if d.needs_human else "info",
            error_code=ev.error_code,
            metric={"directive": d.directive, "confidence": d.confidence,
                    "backoff": d.backoff, "needs_human": d.needs_human,
                    "auto": d.auto_applicable, "source": d.source},
            message=f"{d.cause} -> {d.directive_label}",
            db_file=db_file,
        )
        out.append(d)
    return out
