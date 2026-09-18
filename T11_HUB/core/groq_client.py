"""
Groq istemcisi — ANAHTARSIZ calisir (fallback), acik onayla devreye girer.

Proje kurali "API en sonda": bu modul varsayilan olarak HICBIR SEY YAPMAZ.
Iki kosul birden saglanmadikca disariya tek bir istek bile gitmez:
  1. GROQ_API_KEY tanimli, VE
  2. GROQ_SECOND_OPINION_ENABLED=true

Sadece anahtar koymak yetmez. Anahtarin varligini "izin" saymak, kullanicinin
verisini haber vermeden disari gondermek olurdu; ayri bir bayrak bunu acik bir
karara donusturur.

VERI SINIRI (onemli): buradan disariya SADECE teknik metadata gider —
asama adi, hata kodu ve kuralin kendi onerisi. Urun basliklari, URL'ler, log
metinleri, musteri/kullanici verisi ASLA gonderilmez. Groq'a gidilen sey
"su hata koduna ne denir" sorusudur, isin verisi degil.
"""

from __future__ import annotations

import json
import os
from typing import Optional

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = "llama-3.3-70b-versatile"
TIMEOUT_S = 20

# Groq'un secebilecegi direktifler — kural motorununkiyle AYNI kapali kume.
# Ayni kumeden secmezse capraz-dogrulama anlamsiz olurdu.
ALLOWED_DIRECTIVES = (
    "backoff_and_notify",
    "backoff_and_retry_later",
    "widen_search",
    "retry_once_then_notify",
    "register_handler",
    "requeue_or_human_review",
    "collect_logs_then_human",
)

_SYSTEM = (
    "Du bist ein nuechterner Betriebsdiagnostiker fuer einen Web-Scraper. "
    "Antworte AUSSCHLIESSLICH mit einem JSON-Objekt der Form "
    '{"directive": "<einer der erlaubten Werte>", "directive_label": "<kurze Begruendung>"}. '
    "Waehle den Wert nur aus der vorgegebenen Liste. Bei Verdacht auf Sperre oder "
    "Bot-Schutz ist Zurueckziehen immer richtig - schlage niemals vor, eine Sperre "
    "oder ein CAPTCHA zu umgehen."
)


def is_enabled() -> bool:
    """Anahtar VE acik onay bayragi birlikte gerekli."""
    return bool(os.getenv("GROQ_API_KEY")) and \
        os.getenv("GROQ_SECOND_OPINION_ENABLED", "").lower() == "true"


def status() -> dict:
    """Arayuz/teshis icin: neden kapali oldugu acikca gorunsun."""
    has_key = bool(os.getenv("GROQ_API_KEY"))
    consented = os.getenv("GROQ_SECOND_OPINION_ENABLED", "").lower() == "true"
    if has_key and consented:
        reason = "aktif"
    elif not has_key and not consented:
        reason = "GROQ_API_KEY yok ve onay bayragi kapali -> kural-tabanli calisiyor"
    elif not has_key:
        reason = "onay verilmis ama GROQ_API_KEY yok"
    else:
        reason = "anahtar var ama GROQ_SECOND_OPINION_ENABLED=true degil (bilincli kapali)"
    return {"enabled": has_key and consented, "has_key": has_key,
            "consented": consented, "reason": reason}


def second_opinion(stage: str, error_code: Optional[str],
                   rule_directive: str) -> Optional[dict]:
    """
    Kural motorunun teshisi icin ikinci gorus ister.
    Kapaliysa / hata olursa / gecersiz yanit gelirse None -> sistem kural-tabanli
    calismaya devam eder. Hicbir kosulda istisna firlatmaz.
    """
    if not is_enabled():
        return None

    import requests

    prompt = (
        f"Stage: {stage}\n"
        f"Error code: {error_code or 'unbekannt'}\n"
        f"Regelbasierter Vorschlag: {rule_directive}\n"
        f"Erlaubte Werte: {', '.join(ALLOWED_DIRECTIVES)}"
    )
    try:
        resp = requests.post(
            GROQ_URL,
            headers={"Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}",
                     "Content-Type": "application/json"},
            json={
                "model": os.getenv("GROQ_MODEL", DEFAULT_MODEL),
                "messages": [{"role": "system", "content": _SYSTEM},
                             {"role": "user", "content": prompt}],
                "temperature": 0,
                "max_tokens": 200,
                "response_format": {"type": "json_object"},
            },
            timeout=TIMEOUT_S,
        )
        if resp.status_code != 200:
            return None
        content = resp.json()["choices"][0]["message"]["content"]
        parsed = json.loads(content)
    except Exception:
        return None

    directive = str(parsed.get("directive", "")).strip()
    if directive not in ALLOWED_DIRECTIVES:
        return None  # kume disi cevap -> yok say, kural gecerli kalir
    return {"directive": directive,
            "directive_label": str(parsed.get("directive_label", ""))[:200]}
