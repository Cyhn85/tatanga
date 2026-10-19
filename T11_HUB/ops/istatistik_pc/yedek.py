#!/usr/bin/env python3
"""
DIS YEDEK (2026-10-20). Bu PC tek nokta: gozlemci, alis/satis arsivleri ve hub yalniz burada. Disk giderse veri gider.

    python yedek.py              -> gerekiyorsa (bugun yoksa) gunluk yedek; pazar gunu ayrica haftalik
    python yedek.py --zorla      -> simdi yedek al
    python yedek.py --geri-test  -> en son yedegi Drive'dan indir, coz, ac, her veritabaninda integrity_check

Akis: SQLite backup API ile tutarli anlik goruntu (gozlemci yazarken duz kopya bozuk olabilir) -> integrity_check ->
tar.gz -> AES-256 (openssl, PBKDF2 200k) BU PC'de sifrelenir -> ssh ile sunucudaki rclone'a akitilir (sunucu diskine
ara dosya YAZILMAZ) -> gdrive:TATANGA_yedek -> Drive md5 ile yerel md5 karsilastirilir -> eski yedekler silinir.

Kapsam: gunluk = yeri doldurulamayan (observe, arsiv, alis_arsiv, hub, karne); haftalik = gorsel.db (yeniden
uretilebilir ama saatler suruyor). capraz.db turetilmis veridir (cek.py her gun yeniden uretir), yedeklenmez.
Anahtar: %USERPROFILE%\\.tatanga_yedek_anahtar (ilk calismada uretilir). ANAHTAR YOKSA YEDEK ACILAMAZ: kopyasini
sifre yoneticisinde sakla.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import secrets
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3] / "istatistik"
HUB = Path(__file__).resolve().parents[2] / "data" / "hub.db"
KEY = Path.home() / ".tatanga_yedek_anahtar"
LOG = ROOT / "yedek.log"
SSH = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=20", "root@195.201.146.224"]
UZAK = "gdrive:TATANGA_yedek"
GUNLUK = {"observe.db": ROOT / "vinted" / "observe.db", "arsiv.db": ROOT / "arsiv.db",
          "alis_arsiv.db": ROOT / "alis_arsiv.db", "hub.db": HUB, "karne.db": ROOT / "karne.db"}
HAFTALIK = {"gorsel.db": ROOT / "gorsel.db"}
# Drive kotasi (2026-10-20): Gmail+Fotograflar 13,6 GB kapliyor, Drive'da ~470 MB bos. Gunluk ~51 MB.
# Gmail temizlenene kadar 5 gunluk + 1 haftalik (~400 MB). Yer acilinca gunluk 14d yapilabilir.
SAKLA = {"gunluk": "5d", "haftalik": "8d"}
NO_WINDOW = {"creationflags": 0x08000000} if os.name == "nt" else {}


def log(msg: str) -> None:
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def anahtar() -> Path:
    if not KEY.exists():
        KEY.write_text(secrets.token_urlsafe(48), encoding="ascii")
        log(f"YENI ANAHTAR uretildi: {KEY} -> kopyasini sifre yoneticisinde sakla (anahtarsiz yedek acilamaz)")
    return KEY


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, **NO_WINDOW, **kw)


def md5(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def paketle(dosyalar: dict, tur: str) -> tuple[Path, dict]:
    tmp = Path(tempfile.mkdtemp(prefix="tatanga_yedek_"))
    bilgi = {}
    for ad, src in dosyalar.items():
        if not src.exists():
            log(f"  UYARI: {src} yok, atlandi")
            continue
        dst = tmp / ad
        s = sqlite3.connect(f"file:{src}?mode=ro", uri=True, timeout=60)
        d = sqlite3.connect(dst)
        s.backup(d)
        s.close()
        ok = d.execute("PRAGMA integrity_check").fetchone()[0]
        d.close()
        if ok != "ok":
            raise RuntimeError(f"{ad} anlik goruntusu bozuk: {ok}")
        bilgi[ad] = dst.stat().st_size
    tgz = tmp / f"tatanga_{tur}.tgz"
    with tarfile.open(tgz, "w:gz", compresslevel=6) as tf:
        for ad in bilgi:
            tf.add(tmp / ad, arcname=ad)
    enc = tmp / (tgz.name + ".enc")
    r = run(["openssl", "enc", "-aes-256-cbc", "-salt", "-pbkdf2", "-iter", "200000", "-in", str(tgz),
             "-out", str(enc), "-pass", f"file:{anahtar()}"])
    if r.returncode != 0:
        raise RuntimeError("openssl: " + r.stderr.decode(errors="replace")[:200])
    return enc, bilgi


def yukle(enc: Path, tur: str) -> str:
    ad = f"tatanga_{tur}_{datetime.now():%Y%m%d_%H%M}.tgz.enc"
    hedef = f"{UZAK}/{tur}/{ad}"
    import time
    for deneme in range(4):
        with open(enc, "rb") as fh:
            r = subprocess.run(SSH + [f"rclone rcat {hedef}"], stdin=fh, capture_output=True, timeout=3600, **NO_WINDOW)
        if r.returncode == 0:
            break
        hata = r.stderr.decode(errors="replace")
        if "rateLimitExceeded" in hata or "RATE_LIMIT" in hata:
            time.sleep(90 * (deneme + 1))          # paylasilan rclone kimliginin hiz siniri: bekle, tekrar dene
            continue
        raise RuntimeError("rclone rcat: " + hata[-300:])
    else:
        raise RuntimeError("rclone rcat: Google hiz siniri (4 deneme)")
    r = run(SSH + [f"rclone md5sum {hedef} 2>/dev/null"], timeout=300)
    uzak = r.stdout.decode().split()[0] if r.stdout else ""
    yerel = md5(enc)
    if uzak != yerel:
        raise RuntimeError(f"md5 uyusmuyor: yerel {yerel} / Drive {uzak or 'yok'}")
    run(SSH + [f"rclone delete {UZAK}/{tur} --min-age {SAKLA[tur]} 2>/dev/null"], timeout=300)
    return hedef


def yedek_al(tur: str, dosyalar: dict) -> None:
    enc, bilgi = paketle(dosyalar, tur)
    try:
        hedef = yukle(enc, tur)
        log(f"YEDEK {tur} OK: {hedef} | {enc.stat().st_size / 1e6:.1f} MB sifreli | "
            + ", ".join(f"{k} {v / 1e6:.0f}MB" for k, v in bilgi.items()) + " | md5 dogrulandi")
    finally:
        for f in enc.parent.iterdir():
            f.unlink()
        enc.parent.rmdir()


def geri_test() -> int:
    r = run(SSH + [f"rclone lsf {UZAK}/gunluk 2>/dev/null | sort | tail -1"], timeout=120)
    son = r.stdout.decode().strip()
    if not son:
        log("GERI TEST: Drive'da yedek yok")
        return 1
    tmp = Path(tempfile.mkdtemp(prefix="tatanga_geri_"))
    enc, tgz = tmp / son, tmp / "y.tgz"
    with open(enc, "wb") as fh:
        r = subprocess.run(SSH + [f"rclone cat {UZAK}/gunluk/{son}"], stdout=fh, stderr=subprocess.PIPE,
                           timeout=3600, **NO_WINDOW)
    r = run(["openssl", "enc", "-d", "-aes-256-cbc", "-pbkdf2", "-iter", "200000", "-in", str(enc), "-out", str(tgz),
             "-pass", f"file:{anahtar()}"])
    if r.returncode != 0:
        log("GERI TEST HATA: sifre cozulemedi (anahtar yanlis?)")
        return 1
    with tarfile.open(tgz) as tf:
        tf.extractall(tmp, filter="data")
    sonuc = []
    for db in sorted(tmp.glob("*.db")):
        c = sqlite3.connect(db)
        ok = c.execute("PRAGMA integrity_check").fetchone()[0]
        tablolar = c.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
        c.close()
        sonuc.append(f"{db.name}:{ok}({tablolar} tablo)")
    for f in tmp.iterdir():
        f.unlink()
    tmp.rmdir()
    hepsi = all(":ok(" in s for s in sonuc)
    log(f"GERI TEST {'OK' if hepsi else 'HATA'}: {son} -> " + ", ".join(sonuc))
    return 0 if hepsi else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--zorla", action="store_true")
    ap.add_argument("--geri-test", action="store_true")
    args = ap.parse_args()
    if args.geri_test:
        return geri_test()
    bugun = datetime.now().strftime("%Y-%m-%d")
    hata = 0
    # gunluk: bugun alinmadiysa
    d_gun = ROOT / "yedek_son.txt"
    if args.zorla or not (d_gun.exists() and d_gun.read_text().strip() == bugun):
        try:
            yedek_al("gunluk", GUNLUK)
            d_gun.write_text(bugun)
        except Exception as exc:
            log(f"YEDEK HATA (gunluk): {type(exc).__name__}: {str(exc)[-300:]}")
            hata = 1
    else:
        print("bugunun gunluk yedegi zaten alindi")
    # haftalik: son basarili haftalik 7 gunden eskiyse (basarisizsa bir sonraki calismada yeniden denenir)
    d_haf = ROOT / "yedek_haftalik_son.txt"
    son = d_haf.read_text().strip() if d_haf.exists() else ""
    if args.zorla or not son or (datetime.now() - datetime.strptime(son, "%Y-%m-%d")).days >= 7:
        try:
            yedek_al("haftalik", HAFTALIK)
            d_haf.write_text(bugun)
        except Exception as exc:
            log(f"YEDEK HATA (haftalik): {type(exc).__name__}: {str(exc)[-300:]}")
            hata = 1
    return hata


if __name__ == "__main__":
    sys.exit(main())
