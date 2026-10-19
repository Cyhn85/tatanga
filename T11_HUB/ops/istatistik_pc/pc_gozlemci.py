#!/usr/bin/env python3
"""
Vinted gozlemcisi PC'de (ev WiFi IP'si). Kullanici karari 2026-10-19: sunucu IP'si Vinted'de engelli, tunel
pencere kapaninca duruyordu; gozlemci artik PC'de AYNI kodla calisir. Gorev Zamanlayici oturum acilinca
pythonw ile (pencere yok) baslatir.

    pythonw pc_gozlemci.py

- Veritabani: <tatanga>/istatistik/vinted/observe.db (depo disi). Arsiv paketleri ayni klasorde.
- Gunluk:     <tatanga>/istatistik/vinted/gozlemci.log (20 MB'ta eski dosya .1 olur).
- Tek kopya:  gozlemci.lock (ikinci kopya hemen cikar; cift sayim olmaz).
- Cokerse 120 sn sonra yeniden baslar; hata gunluge yazilir.
"""

from __future__ import annotations

import io
import os
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "istatistik" / "vinted"
OBS_DIR = Path(__file__).resolve().parents[1] / "hetzner_observer"
LOG = DATA / "gozlemci.log"
LOCK = DATA / "gozlemci.lock"
MAX_LOG = 20 * 1024 * 1024


def _open_log():
    DATA.mkdir(parents=True, exist_ok=True)
    if LOG.exists() and LOG.stat().st_size > MAX_LOG:
        old = LOG.with_suffix(".log.1")
        if old.exists():
            old.unlink()
        LOG.rename(old)
    f = open(LOG, "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = f
    return f


def _lock():
    """Windows: dosyanin ilk baytina ozel kilit. Kilit alinamazsa baska kopya calisiyordur."""
    import msvcrt
    fh = open(LOCK, "a+")
    try:
        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} baska bir gozlemci kopyasi calisiyor; cikiliyor", flush=True)
        sys.exit(0)
    return fh


def main() -> int:
    _open_log()
    _lock_fh = _lock()   # noqa: F841  (surec boyunca acik kalmali)
    os.environ["TATANGA_OBS_DB"] = str(DATA / "observe.db")
    sys.path.insert(0, str(OBS_DIR))
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} PC gozlemcisi basliyor | db {os.environ['TATANGA_OBS_DB']}", flush=True)
    import observer
    while True:
        try:
            sys.argv = ["observer.py"]
            observer.main()
        except SystemExit:
            raise
        except Exception:
            print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} GOZLEMCI COKTU, 120 sn sonra yeniden:\n"
                  + traceback.format_exc(), flush=True)
            time.sleep(120)


if __name__ == "__main__":
    sys.exit(main())
