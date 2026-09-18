"""
Platform hiz koruyucusu — kaynagi yakmadan kazimak icin.

BUGUNKU ACI DERS: Gelistirme sirasinda eBay'e 555+, Leboncoin'e onlarca ardisik
istek atildi. Ikisi de ayni oturum icinde engelledi. Kod DOGRUYDU; sorun
kodun ne kadar HIZLI calistigiydi. Engellenen platform saatlerce (bazen gunlerce)
kapali kalir — yani "hizli kazimak" toplamda daha az veri getirir.

Bu modul iki sey yapar:
  1. Platform basina en az bekleme suresini uygular (sabit degil, aralikli
     rastgele — sabit ritim insan degildir, tespit sinyalidir).
  2. Engel tespit edilince o platformu SOGUMAYA alir; sogumadaki platforma
     hic istek atilmaz, "sonra dene" denir. Engelli kapiyi tekrar tekrar
     calmak engeli uzatir.

Saf modul: saat fonksiyonu disaridan verilebilir -> izole test edilir.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

# Platform basina istekler arasi en az bekleme (saniye). API uclari daha
# toleransli, HTML/tarayici yollari daha kirilgan.
MIN_GAP: dict[str, float] = {
    "vinted": 1.5, "vinted_fr": 1.5, "vinted_be": 1.5,
    "vinted_pl": 1.5, "vinted_uk": 1.5,
    "markt": 1.5,                 # kendi JSON API'si, toleransli
    "kleinanzeigen": 3.0,
    "tradera": 3.0, "willhaben": 3.0,
    "ebay": 8.0,                  # bugun 555 istekten sonra engelledi
    "leboncoin": 10.0,            # Datadome; tarayici yolu, cok kirilgan
    "depop": 8.0, "sellpy": 6.0, "percentil": 6.0,
}
DEFAULT_GAP = 4.0

# Engel tespitinde uygulanan sogutma. Ust uste engel gelirse katlanir —
# platform "hayir" demeye devam ediyorsa daha uzun beklemek gerekir.
BASE_COOLDOWN = 900.0        # 15 dakika
MAX_COOLDOWN = 6 * 3600.0    # 6 saat

# Bir yanitin "engellendik" demek oldugunu gosteren isaretler.
BLOCK_CODES = {403, 429, 418, 503}
BLOCK_MARKS = ("error page", "access denied", "datadome", "captcha",
               "unusual traffic", "pardon our interruption", "just a moment",
               "zugriff verweigert", "es-tu un humain", "forbidden")


@dataclass
class PlatformState:
    last_request: float = 0.0
    cooldown_until: float = 0.0
    consecutive_blocks: int = 0
    total_requests: int = 0
    total_blocks: int = 0


@dataclass
class RateGuard:
    now: Callable[[], float] = time.time
    sleeper: Callable[[float], None] = time.sleep
    jitter: Callable[[], float] = random.random
    states: dict[str, PlatformState] = field(default_factory=dict)

    def _state(self, platform: str) -> PlatformState:
        return self.states.setdefault(platform, PlatformState())

    def cooling(self, platform: str) -> float:
        """Sogumada kalan saniye (0 = hazir)."""
        return max(0.0, self._state(platform).cooldown_until - self.now())

    def wait_time(self, platform: str) -> float:
        """Bir sonraki istege kadar beklenmesi gereken sure."""
        st = self._state(platform)
        soguma = self.cooling(platform)
        if soguma > 0:
            return soguma
        gap = MIN_GAP.get(platform, DEFAULT_GAP)
        # +%0-60 rastgele: sabit ritim bot imzasidir.
        gap *= 1.0 + 0.6 * self.jitter()
        gecen = self.now() - st.last_request
        return max(0.0, gap - gecen)

    def acquire(self, platform: str) -> tuple[bool, str]:
        """
        Istek atmadan once cagrilir. Sogumadaysa (False, sebep) doner ve
        BEKLEMEZ — cagiran taraf o platformu atlar. Aksi halde gerekli
        araligi bekler ve (True, "") doner.
        """
        soguma = self.cooling(platform)
        if soguma > 0:
            return False, f"sogumada, {int(soguma // 60)} dk {int(soguma % 60)} sn kaldi"
        bekle = self.wait_time(platform)
        if bekle > 0:
            self.sleeper(bekle)
        st = self._state(platform)
        st.last_request = self.now()
        st.total_requests += 1
        return True, ""

    def report(self, platform: str, *, status: int = 200, body: str = "",
               got_results: bool = True) -> bool:
        """
        Istekten SONRA cagrilir. Engel tespit edilirse sogumaya alir ve
        True doner. Basarili yanit ardisik engel sayacini sifirlar.
        """
        st = self._state(platform)
        engel = status in BLOCK_CODES
        if not engel and body:
            dusuk = body[:4000].lower()
            engel = any(m in dusuk for m in BLOCK_MARKS)
        # Cok kisa govde + sonuc yok: sessiz engel sayilir (Leboncoin'in
        # 1,2 MB yerine 1,5 KB dondurmesi tam olarak buydu).
        if not engel and body and len(body) < 3000 and not got_results:
            engel = True

        if engel:
            st.consecutive_blocks += 1
            st.total_blocks += 1
            sure = min(BASE_COOLDOWN * (2 ** (st.consecutive_blocks - 1)), MAX_COOLDOWN)
            st.cooldown_until = self.now() + sure
            return True
        st.consecutive_blocks = 0
        return False

    def summary(self) -> list[dict]:
        cikti = []
        for ad, st in sorted(self.states.items()):
            cikti.append({
                "platform": ad,
                "requests": st.total_requests,
                "blocks": st.total_blocks,
                "cooling_seconds": round(self.cooling(ad)),
            })
        return cikti


# Surec genelinde tek koruyucu.
GUARD = RateGuard()
