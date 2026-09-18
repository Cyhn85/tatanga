"""
Manager is handler'lari (Faz 3) — additive.

Her handler bir ScheduledJob alir, GUVENLI/deterministik is yapar, metric dondurur
ve olay otobusune yazar. Sadece KENDI urunlerimizi/fiyatlarimizi degistirir; dis
servis/LLM gerektirmez. Manager import-time'da bu handler'lari taniyacak sekilde
`register_handler` cagrilir; `install_jobs()` tekrarlayan isleri kaydeder.

Not: site tarafina (cssberlin) fiyat yansitma AYRI bir adim (repricing API, #147).
Bu handler TATANGA-yerel products fiyatini gunceller + olay yazar.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import aiosqlite

from . import event_bus as bus
from . import manager as mgr

# --- aging_reprice ayarlari ---
AGING_DAYS = 30                 # bu kadar gundur yayindaysa marj kisilir
REPRICE_STEP = 0.10             # her turda %10
REPRICE_MIN_INTERVAL_DAYS = 7   # ayni urun en fazla 7 gunde bir yeniden fiyatlanir
COST_FLOOR_FACTOR = 1.02        # maliyetin %2 ustunun ALTINA asla inme


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


async def _ensure_reprice_columns(db_file: str) -> None:
    """products'a additive listed_at/last_reprice_at ekler (yoksa). Veri kaybi yok."""
    async with aiosqlite.connect(db_file) as db:
        cur = await db.execute("PRAGMA table_info(products)")
        cols = {r[1] for r in await cur.fetchall()}
        if "listed_at" not in cols:
            await db.execute("ALTER TABLE products ADD COLUMN listed_at TEXT")
        if "last_reprice_at" not in cols:
            await db.execute("ALTER TABLE products ADD COLUMN last_reprice_at TEXT")
        # Indirim iddiasinin KANITI: kampanya motoru "%X reduziert" diyebilmek icin
        # onceki fiyati bilmek zorunda. Yoksa indirim iddiasi kanitsiz kalir.
        if "price_before_reprice" not in cols:
            await db.execute("ALTER TABLE products ADD COLUMN price_before_reprice REAL")
        await db.commit()


async def aging_reprice(job: bus.ScheduledJob) -> dict:
    """
    30 gunden uzun yayinda kalan (published) ve maliyetin uzerinde marji olan
    urunlerin fiyatini %10 kisar — ama ASLA maliyetin %2 ustunun altina inmez.
    listed_at bos ise created_at ile doldurur (source_recheck'in bozmadigi stabil
    saat). Ayni urunu 7 gunde bir defadan fazla dusurmez.
    """
    db_file = bus.DEFAULT_DB_FILE
    await _ensure_reprice_columns(db_file)
    now = _now()
    aging_cutoff = _iso(now - timedelta(days=AGING_DAYS))
    reprice_cutoff = _iso(now - timedelta(days=REPRICE_MIN_INTERVAL_DAYS))
    repriced = 0

    async with aiosqlite.connect(db_file) as db:
        db.row_factory = aiosqlite.Row
        # stabil yayin saati: bos listed_at'i created_at ile doldur
        await db.execute(
            "UPDATE products SET listed_at=created_at "
            "WHERE status='published' AND (listed_at IS NULL OR listed_at='')"
        )
        await db.commit()

        cur = await db.execute(
            """SELECT id, price, total_cost FROM products
               WHERE status='published' AND total_cost > 0
                 AND listed_at <= ? AND price > total_cost * ?
                 AND (last_reprice_at IS NULL OR last_reprice_at <= ?)""",
            (aging_cutoff, COST_FLOOR_FACTOR, reprice_cutoff),
        )
        rows = await cur.fetchall()
        for r in rows:
            floor = round(r["total_cost"] * COST_FLOOR_FACTOR, 2)
            new_price = max(round(r["price"] * (1 - REPRICE_STEP), 2), floor)
            if new_price >= r["price"]:
                continue  # zaten tabanda
            # price_before_reprice ILK indirimde yazilir (COALESCE ile korunur):
            # boylece "%X reduziert" her zaman ORIJINAL fiyata gore hesaplanir,
            # ust uste indirimlerde referans kaymaz.
            await db.execute(
                "UPDATE products SET price=?, last_reprice_at=?, updated_at=?, "
                "price_before_reprice=COALESCE(price_before_reprice, ?) WHERE id=?",
                (new_price, _iso(now), _iso(now), r["price"], r["id"]),
            )
            repriced += 1
        await db.commit()

    if repriced:
        await bus.emit(
            "reprice", "ok",
            metric={"repriced": repriced, "aging_days": AGING_DAYS,
                    "step_pct": int(REPRICE_STEP * 100)},
            message=f"{repriced} eski ilanin marji %{int(REPRICE_STEP*100)} kisildi (maliyet tabani korundu)",
            db_file=db_file,
        )
    return {"repriced": repriced}


# Manager import-time'da handler'i tanisin
mgr.register_handler("aging_reprice", aging_reprice)


# --- unsold_research ayarlari ---
UNSOLD_AGE_DAYS = 45                    # aging_reprice (30 gun) zaten calisip fiyat kismis olmali
UNSOLD_RESEARCH_BATCH = 5               # her turda arastirilan urun sayisi (platformlari yormamak icin)
UNSOLD_RESEARCH_MIN_INTERVAL_DAYS = 7   # ayni urun 7 gunde bir arastirilir
UNSOLD_OVERPRICE_FACTOR = 1.15          # canli medyanin %15 ustundeysek "fiyat_yuksek"


async def _ensure_research_columns(db_file: str) -> None:
    """products'a additive last_research_at/research_note ekler (yoksa). Veri kaybi yok."""
    async with aiosqlite.connect(db_file) as db:
        cur = await db.execute("PRAGMA table_info(products)")
        cols = {r[1] for r in await cur.fetchall()}
        if "last_research_at" not in cols:
            await db.execute("ALTER TABLE products ADD COLUMN last_research_at TEXT")
        if "research_note" not in cols:
            await db.execute("ALTER TABLE products ADD COLUMN research_note TEXT")
        await db.commit()


async def unsold_research(job: bus.ScheduledJob) -> dict:
    """
    aging_reprice'in marji kistigi halde HALA satilmayan (45+ gundur yayinda) urunler
    icin GERCEK bir pazar arastirmasi yapar: ayni kaynak platformda, urunun
    marka+baslik'indan turetilen gercek bir anahtar kelimeyle taze, tek sayfalik bir
    kazima calistirir (app.scrape_platform - alaka filtresi zaten icinde calisir).
    Canli rakip ilan sayisi + medyan fiyati hesaplayip bulguyu urune yazar.

    HICBIR otomatik fiyat/durum degisikligi YAPMAZ — "fiyat mi yuksek yoksa gercekten
    talep mi yok" ayrimi burada sadece ARASTIRILIR, karar insan/diagnostician'a birakilir
    (aging_reprice zaten fiyat tarafini kendi basina yonetiyor). Sahte veri yok: ya
    gercek canli sonuc doner ya da bos liste (aksiyon almadan not dusulur).
    """
    db_file = bus.DEFAULT_DB_FILE
    await _ensure_research_columns(db_file)
    now = _now()
    age_cutoff = _iso(now - timedelta(days=UNSOLD_AGE_DAYS))
    research_cutoff = _iso(now - timedelta(days=UNSOLD_RESEARCH_MIN_INTERVAL_DAYS))

    async with aiosqlite.connect(db_file) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """SELECT id, title, brand, source_platform, price FROM products
               WHERE status='published' AND listed_at IS NOT NULL AND listed_at <= ?
                 AND (last_research_at IS NULL OR last_research_at <= ?)
               ORDER BY (last_research_at IS NULL) DESC, last_research_at ASC
               LIMIT ?""",
            (age_cutoff, research_cutoff, UNSOLD_RESEARCH_BATCH),
        )
        rows = await cur.fetchall()

    # app.py'ye lazy import: circular import onlenir (app.py core.manager'i, o da
    # run_loop icinde core.handlers'i import eder; bu noktada app zaten yuklu).
    import app as _app

    researched = 0
    overpriced = 0
    low_demand = 0
    for r in rows:
        keyword = (f"{r['brand']} {r['title']}" if r["brand"] else (r["title"] or "")).strip()
        keyword = " ".join(keyword.split()[:5])
        if not keyword or not r["source_platform"]:
            continue
        try:
            live = await _app.scrape_platform(r["source_platform"], keyword, max_pages=1)
        except Exception:
            live = []

        prices = sorted(p["price"] for p in live if p.get("price"))
        note_parts = [f"canli_rakip={len(prices)}"]
        if prices:
            market_median = prices[len(prices) // 2]
            note_parts.append(f"medyan={market_median:.2f}")
            if r["price"] and r["price"] > market_median * UNSOLD_OVERPRICE_FACTOR:
                overpriced += 1
                note_parts.append("fiyat_yuksek")
        else:
            low_demand += 1
            note_parts.append("talep_sinyali_zayif")

        async with aiosqlite.connect(db_file) as db:
            await db.execute(
                "UPDATE products SET last_research_at=?, research_note=? WHERE id=?",
                (_iso(now), ",".join(note_parts), r["id"]),
            )
            await db.commit()
        researched += 1

    if researched:
        await bus.emit(
            "unsold_research", "ok",
            metric={"researched": researched, "overpriced": overpriced, "low_demand": low_demand},
            message=(f"{researched} eski/satilmamis urun arastirildi "
                     f"({overpriced} fiyat-yuksek, {low_demand} zayif-talep sinyali)"),
            db_file=db_file,
        )
    return {"researched": researched, "overpriced": overpriced, "low_demand": low_demand}


mgr.register_handler("unsold_research", unsold_research)


# =============================================================
# Kampanya + video handler'lari (#143, #144)
# =============================================================
CAMPAIGN_PRODUCT_LIMIT = 200      # kampanya hesabina giren urun tavani
CAMPAIGN_MIN_INTERVAL_H = 24      # ayni tur+dil icin gunde 1 taslak (spam yok)
VIDEO_MAX_IMAGES = 5              # video basina gorsel tavani
VIDEO_QC_MAX_BLACK_RATIO = 0.30   # karenin %30'undan fazlasi siyahsa QC kalir


async def _ensure_campaign_table(db_file: str) -> None:
    """Kampanya taslaklari tablosu (additive, var olan veriye dokunmaz)."""
    async with aiosqlite.connect(db_file) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS campaign_drafts (
                id TEXT PRIMARY KEY,
                kind TEXT, lang TEXT,
                headline TEXT, body TEXT, cta TEXT,
                evidence TEXT, warnings TEXT,
                product_ids TEXT,
                status TEXT DEFAULT 'draft',
                video_path TEXT, video_qc TEXT,
                created_at TEXT
            )
        """)
        await db.commit()


def _draft_id(kind: str, lang: str, now: datetime) -> str:
    return f"CMP-{now.strftime('%Y%m%d%H%M%S')}-{kind[:4]}-{lang}"


async def ad_generate(job: bus.ScheduledJob) -> dict:
    """
    GERCEK urun verisinden EN/DE/TR kampanya TASLAKLARI uretir.

    Metinler logic/campaign_engine tarafindan deterministik uretilir ve marka
    iddia bekcisinden gecer — kanitsiz iddia (ustunluk, ucretsiz kargo, sabit
    istatistik, rakip fiyati) tasiyan varyant DB'ye hic yazilmaz.
    Ciktilar 'draft' durumundadir: insan onayi olmadan hicbir yere gitmez.
    """
    db_file = bus.DEFAULT_DB_FILE
    await _ensure_reprice_columns(db_file)
    await _ensure_campaign_table(db_file)
    now = _now()

    from logic.campaign_engine import generate_all_languages

    async with aiosqlite.connect(db_file) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """SELECT id, title, price, price_before_reprice, category, listed_at
               FROM products WHERE status='published'
               ORDER BY listed_at DESC LIMIT ?""",
            (CAMPAIGN_PRODUCT_LIMIT,),
        )
        products = [dict(r) for r in await cur.fetchall()]

        cutoff = _iso(now - timedelta(hours=CAMPAIGN_MIN_INTERVAL_H))
        cur = await db.execute(
            "SELECT kind, lang FROM campaign_drafts WHERE created_at > ?", (cutoff,))
        recent = {(r["kind"], r["lang"]) for r in await cur.fetchall()}

    if not products:
        return {"created": 0, "reason": "yayinda urun yok"}

    results = generate_all_languages(products)
    created = 0
    rejected: list[str] = []

    async with aiosqlite.connect(db_file) as db:
        for lang, result in results.items():
            rejected.extend(result.rejected)
            for draft in result.drafts:
                if (draft.kind, lang) in recent:
                    continue  # bugun bu tur+dil zaten uretilmis
                await db.execute(
                    """INSERT OR REPLACE INTO campaign_drafts
                       (id, kind, lang, headline, body, cta, evidence, warnings,
                        product_ids, status, created_at)
                       VALUES (?,?,?,?,?,?,?,?,?,'draft',?)""",
                    (_draft_id(draft.kind, lang, now), draft.kind, lang,
                     draft.headline, draft.body, draft.cta, draft.evidence,
                     ", ".join(draft.warnings), json.dumps(draft.product_ids), _iso(now)),
                )
                created += 1
        await db.commit()

    if created or rejected:
        await bus.emit(
            "ad_generate", "ok",
            metric={"created": created, "rejected": len(rejected)},
            message=(f"{created} kampanya taslagi uretildi (insan onayi bekliyor)"
                     + (f" | bekci {len(rejected)} varyanti dusurdu: {'; '.join(rejected[:3])}"
                        if rejected else "")),
            level="warning" if rejected else "info",
            db_file=db_file,
        )
    return {"created": created, "rejected": len(rejected)}


async def video_generate(job: bus.ScheduledJob) -> dict:
    """
    Videosu olmayan kampanya taslaklari icin GERCEK urun gorsellerinden
    kompozisyon videosu kurgular (uretken model YOK). Gorseli olmayan taslak
    atlanir — temsili/stok gorsel ASLA kullanilmaz.
    """
    db_file = bus.DEFAULT_DB_FILE
    await _ensure_campaign_table(db_file)

    from media.video_composer import compose_product_video
    from media import voice as tts
    from logic.brand_identity import palette

    media_dir = Path(bus.DEFAULT_DB_FILE).resolve().parent / "videos"
    media_dir.mkdir(parents=True, exist_ok=True)
    brand_color = "0x" + palette().get("orange", "#E8651A").lstrip("#")

    async with aiosqlite.connect(db_file) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """SELECT id, kind, lang, headline, body, cta, product_ids
               FROM campaign_drafts
               WHERE video_path IS NULL AND kind != 'eco'
               ORDER BY created_at DESC LIMIT 3""")
        drafts = [dict(r) for r in await cur.fetchall()]

    made = 0
    skipped = 0
    for draft in drafts:
        try:
            product_ids = json.loads(draft["product_ids"] or "[]")
        except Exception:
            product_ids = []
        if not product_ids:
            skipped += 1
            continue

        placeholders = ",".join("?" * len(product_ids))
        async with aiosqlite.connect(db_file) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                f"SELECT processed_images_json FROM products WHERE id IN ({placeholders})",
                product_ids,
            )
            rows = await cur.fetchall()

        images: list[str] = []
        for row in rows:
            try:
                for path in json.loads(row["processed_images_json"] or "[]"):
                    if path and Path(path).exists():
                        images.append(path)
            except Exception:
                continue
            if len(images) >= VIDEO_MAX_IMAGES:
                break

        if not images:
            skipped += 1
            continue  # gercek gorsel yok -> video URETILMEZ

        speech = tts.synthesize(f"{draft['headline']}. {draft['body']}",
                                media_dir / f"{draft['id']}.wav", lang=draft["lang"])
        result = compose_product_video(
            images[:VIDEO_MAX_IMAGES], media_dir / f"{draft['id']}.mp4",
            headline=draft["headline"], cta=draft["cta"], brand_color=brand_color,
            audio_path=speech.path if speech else None,
            voice_matched=speech.voice_matched if speech else True,
        )
        if not result:
            skipped += 1
            continue

        note = f"ses={'var' if result.has_audio else 'yok'}"
        if result.has_audio and not result.voice_matched:
            note += f",dil_sesi_YOK({draft['lang']})"  # yanlis aksan riski isaretlenir
        async with aiosqlite.connect(db_file) as db:
            await db.execute(
                "UPDATE campaign_drafts SET video_path=?, video_qc=? WHERE id=?",
                (str(result.path), f"pending|{note}", draft["id"]),
            )
            await db.commit()
        made += 1

    if made or skipped:
        await bus.emit(
            "video_generate", "ok",
            metric={"made": made, "skipped": skipped},
            message=f"{made} kampanya videosu kurgulandi, {skipped} atlandi (gercek gorsel yok)",
            db_file=db_file,
        )
    return {"made": made, "skipped": skipped}


def _probe_video(path: str) -> dict:
    """
    ffmpeg ile GERCEK QC olcumu: sure + siyah kare orani (blackdetect).
    ffmpeg yoksa/okunamazsa {'ok': False, ...} doner — tahmin YAPILMAZ.
    """
    from media.video_composer import ffmpeg_exe
    exe = ffmpeg_exe()
    if not exe or not Path(path).exists():
        return {"ok": False, "reason": "ffmpeg yok veya dosya bulunamadi"}

    proc = subprocess.run(
        [exe, "-i", path, "-vf", "blackdetect=d=0.3:pix_th=0.10", "-f", "null", "-"],
        capture_output=True, text=True, timeout=180,
    )
    err = proc.stderr or ""

    duration = 0.0
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", err)
    if m:
        duration = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    has_video = "Video:" in err
    black = sum(float(x) for x in re.findall(r"black_duration:(\d+\.?\d*)", err))
    ratio = (black / duration) if duration > 0 else 0.0
    return {"ok": True, "duration": round(duration, 2), "has_video": has_video,
            "black_ratio": round(ratio, 3)}


async def video_qc(job: bus.ScheduledJob) -> dict:
    """
    Kurgulanan videolari GERCEKTEN olcer (sure/video akisi/siyah kare orani).
    Kalan video 'fail' isaretlenir ve video_path temizlenir -> bir sonraki turda
    yeniden kurgulanabilir. Gecen video 'pass' olur ama HALA insan onayi bekler.
    """
    db_file = bus.DEFAULT_DB_FILE
    await _ensure_campaign_table(db_file)

    async with aiosqlite.connect(db_file) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT id, video_path, video_qc FROM campaign_drafts "
            "WHERE video_path IS NOT NULL AND (video_qc IS NULL OR video_qc LIKE 'pending%') "
            "LIMIT 5")
        rows = [dict(r) for r in await cur.fetchall()]

    passed = failed = 0
    for row in rows:
        try:
            probe = _probe_video(row["video_path"])
        except Exception as exc:
            probe = {"ok": False, "reason": str(exc)[:120]}

        note = (row["video_qc"] or "").split("|", 1)[-1] if row["video_qc"] else ""
        problems = []
        if not probe.get("ok"):
            problems.append(probe.get("reason", "olculemedi"))
        else:
            if not probe.get("has_video"):
                problems.append("video akisi yok")
            if probe.get("duration", 0) < 1.0:
                problems.append(f"sure cok kisa ({probe.get('duration')}s)")
            if probe.get("black_ratio", 0) > VIDEO_QC_MAX_BLACK_RATIO:
                problems.append(f"siyah kare orani yuksek (%{probe['black_ratio'] * 100:.0f})")

        if problems:
            verdict = "fail|" + "; ".join(problems)
            failed += 1
            async with aiosqlite.connect(db_file) as db:
                await db.execute(
                    "UPDATE campaign_drafts SET video_qc=?, video_path=NULL WHERE id=?",
                    (verdict, row["id"]))
                await db.commit()
        else:
            verdict = f"pass|{probe['duration']}s,{note}"
            passed += 1
            async with aiosqlite.connect(db_file) as db:
                await db.execute("UPDATE campaign_drafts SET video_qc=? WHERE id=?",
                                 (verdict, row["id"]))
                await db.commit()

    if passed or failed:
        await bus.emit(
            "video_qc", "ok" if not failed else "escalated",
            error_code="qc_hole" if failed else None,
            metric={"passed": passed, "failed": failed},
            message=f"Video QC: {passed} gecti, {failed} kaldi",
            level="warning" if failed else "info",
            db_file=db_file,
        )
    return {"passed": passed, "failed": failed}


MAIL_RELAY_BATCH = 15


async def _ensure_mail_table(db_file: str) -> None:
    async with aiosqlite.connect(db_file) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS mail_events (
                uid TEXT PRIMARY KEY,
                category TEXT, source TEXT, intent TEXT,
                sender TEXT, subject TEXT, summary TEXT,
                draft_reply TEXT, draft_lang TEXT, warnings TEXT,
                status TEXT DEFAULT 'new',
                created_at TEXT
            )
        """)
        await db.commit()


async def mail_relay(job: bus.ScheduledJob) -> dict:
    """
    Posta kutusunu okur, siniflandirir, kayda gecer ve INSAN ONAYINA sunar.

    Bu hat bilerek TEK YONLU: okur, ozetler, taslak hazirlar — hicbir yanit
    gondermez, hicbir islem tetiklemez. Gelen e-posta guvenilmez girdidir;
    icerigindeki "sunu yap" ifadeleri komut olarak islenmez (bkz. mail_triage).

    Yapilandirma yoksa sessizce 0 doner — kurulmamis olmak hata degildir.
    """
    db_file = bus.DEFAULT_DB_FILE
    await _ensure_mail_table(db_file)

    from social import mailbox
    from logic.mail_triage import classify_mail

    if not mailbox.is_configured():
        return {"read": 0, "reason": mailbox.status()["reason"]}

    messages = await asyncio.to_thread(mailbox.fetch_unseen, MAIL_RELAY_BATCH)
    if not messages:
        return {"read": 0}

    now = _iso(_now())
    sayac: dict = {}
    kaydedilen = 0

    async with aiosqlite.connect(db_file) as db:
        for msg in messages:
            verdict = classify_mail(sender=msg.sender, subject=msg.subject,
                                    body=msg.body, headers=msg.headers)
            sayac[verdict.category] = sayac.get(verdict.category, 0) + 1
            await db.execute(
                """INSERT OR IGNORE INTO mail_events
                   (uid, category, source, intent, sender, subject, summary,
                    draft_reply, draft_lang, warnings, status, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,'new',?)""",
                (msg.uid, verdict.category, verdict.source, verdict.intent,
                 msg.sender[:200], msg.subject[:300], verdict.summary,
                 verdict.draft_reply, verdict.draft_lang,
                 ", ".join(verdict.warnings), now))
            kaydedilen += 1
        await db.commit()

    musteri = sayac.get("customer_message", 0)
    await bus.emit(
        "mail_relay", "ok",
        metric={"read": kaydedilen, **sayac},
        message=(f"{kaydedilen} yeni posta okundu — "
                 + ", ".join(f"{k}:{v}" for k, v in sayac.items())
                 + (f" | {musteri} musteri mesaji onay bekliyor" if musteri else "")),
        level="warning" if musteri else "info",
        db_file=db_file,
    )
    return {"read": kaydedilen, **sayac}


ATTENDED_POST_BATCH = 2      # her turda en fazla 2 paket (Telegram'i bogmamak icin)
ATTENDED_PLATFORMS = ("instagram", "tiktok", "pinterest")   # youtube zaten otomatik


async def attended_post(job: bus.ScheduledJob) -> dict:
    """
    ONAYLANMIS + videosu QC'den gecmis kampanyalari, her platformun adetine gore
    paketleyip Telegram'a duser: video dosyasi + kopyalanmaya hazir metin.

    NEDEN BOYLE: Instagram ve TikTok'ta otomatik yayin icin uygulama incelemesi
    bekleniyor. Bu hat o sureyi bos gecirmemek icin var — sistem her seyi
    hazirlar, insan tek dokunusla yayinlar. Otomasyonla giris YAPILMAZ, platform
    kurallari ihlal edilmez, hesap riske atilmaz.

    YouTube listede yok: orada resmi API ile zaten dogrudan yukleyebiliyoruz.
    """
    db_file = bus.DEFAULT_DB_FILE
    await _ensure_campaign_table(db_file)

    from logic.post_formatter import format_for_platform

    async with aiosqlite.connect(db_file) as db:
        cur = await db.execute("PRAGMA table_info(campaign_drafts)")
        cols = {r[1] for r in await cur.fetchall()}
        if "attended_sent_at" not in cols:
            await db.execute("ALTER TABLE campaign_drafts ADD COLUMN attended_sent_at TEXT")
            await db.commit()

        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """SELECT id, kind, lang, headline, body, cta, video_path
               FROM campaign_drafts
               WHERE status='approved' AND video_path IS NOT NULL
                 AND video_qc LIKE 'pass%' AND attended_sent_at IS NULL
               ORDER BY created_at DESC LIMIT ?""", (ATTENDED_POST_BATCH,))
        drafts = [dict(r) for r in await cur.fetchall()]

    if not drafts:
        return {"sent": 0}

    # telegram_bot lazy import: bot yoksa handler yine de cokmez
    try:
        import telegram_bot as tg
        tg.load_config()
        bot = tg.TelegramBot(tg.BOT_TOKEN)
        oda = tg.CHANNELS.get("kampanya", tg.CHANNELS.get("admin"))
    except Exception as exc:
        return {"sent": 0, "error": f"telegram yuklenemedi: {str(exc)[:120]}"}

    gonderilen = 0
    engellenen: list[str] = []

    for draft in drafts:
        video = Path(draft["video_path"] or "")
        if not video.exists():
            continue

        # Video bir kere yuklenir, paketler ona yanit olarak gider.
        try:
            with open(video, "rb") as fh:
                await asyncio.to_thread(
                    bot.api, "sendVideo",
                    {"chat_id": oda,
                     "caption": f"🎬 {draft['headline']} [{draft['lang']}]",
                     "parse_mode": "HTML"},
                    {"video": fh})
        except Exception:
            continue

        for platform in ATTENDED_PLATFORMS:
            paket = format_for_platform(
                platform=platform, lang=draft["lang"],
                headline=draft["headline"], body=draft["body"], cta=draft["cta"])
            if paket.blocked:
                engellenen.append(f"{platform}/{draft['lang']}: {paket.blocked}")
                continue

            satirlar = [f"📤 <b>{platform.upper()}</b> — {paket.video_requirements}"]
            if paket.title:
                satirlar += [f"<b>Baslik:</b>", f"<code>{paket.title}</code>"]
            satirlar += ["<b>Aciklama (kopyala):</b>",
                         f"<code>{paket.full_caption}</code>",
                         f'<a href="{paket.upload_url}">{platform} yukleme sayfasi</a>']
            if paket.warnings:
                satirlar.append(f"⚑ {', '.join(paket.warnings)[:150]}")
            await asyncio.to_thread(bot.send_message, oda, "\n".join(satirlar))
            gonderilen += 1

        async with aiosqlite.connect(db_file) as db:
            await db.execute("UPDATE campaign_drafts SET attended_sent_at=? WHERE id=?",
                             (_iso(_now()), draft["id"]))
            await db.commit()

    await bus.emit(
        "attended_post", "ok",
        metric={"packages": gonderilen, "blocked": len(engellenen)},
        message=(f"{gonderilen} yayin paketi Telegram'a gonderildi (insan yayinlayacak)"
                 + (f" | bekci {len(engellenen)} paketi engelledi" if engellenen else "")),
        level="warning" if engellenen else "info",
        db_file=db_file,
    )
    return {"sent": gonderilen, "blocked": len(engellenen)}


SOCIAL_PUBLISH_BATCH = 2


async def social_publish(job: bus.ScheduledJob) -> dict:
    """
    ONAYLANMIS + QC gecmis videolari, BAGLI olan platformlara resmi API ile yukler.

    KAPILAR (hepsi gecilmeden hicbir sey yayinlanmaz):
      1. status='approved'      -> insan onayladi
      2. video_qc LIKE 'pass%'  -> video olculdu, saglam
      3. platform bagli         -> OAuth yetkisi var
      4. gunluk kota dolmamis   -> platformu yormuyoruz

    Bagli olmayan platform sessizce atlanir — kurulmamis olmak hata degildir.
    Her denemenin GERCEK sonucu (basari/hata) kaydedilir; "yayinlandi" yazip
    aslinda gitmemis olma durumu olmaz.
    """
    db_file = bus.DEFAULT_DB_FILE
    await _ensure_campaign_table(db_file)

    from social import youtube, tiktok, instagram, pinterest  # noqa: F401
    from logic.post_formatter import format_for_platform

    async with aiosqlite.connect(db_file) as db:
        cur = await db.execute("PRAGMA table_info(campaign_drafts)")
        cols = {r[1] for r in await cur.fetchall()}
        if "published_json" not in cols:
            await db.execute("ALTER TABLE campaign_drafts ADD COLUMN published_json TEXT")
            await db.commit()

        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """SELECT id, lang, headline, body, cta, video_path, published_json
               FROM campaign_drafts
               WHERE status='approved' AND video_path IS NOT NULL
                 AND video_qc LIKE 'pass%'
               ORDER BY created_at DESC LIMIT ?""", (SOCIAL_PUBLISH_BATCH,))
        drafts = [dict(r) for r in await cur.fetchall()]

    if not drafts:
        return {"published": 0}

    published_total = 0
    failures: list[str] = []

    for draft in drafts:
        video = Path(draft["video_path"] or "")
        if not video.exists():
            continue
        try:
            already = json.loads(draft["published_json"] or "{}")
        except Exception:
            already = {}

        # --- YouTube: dosyayi dogrudan yukler ---
        if "youtube" not in already and youtube.is_connected():
            paket = format_for_platform(platform="youtube", lang=draft["lang"],
                                        headline=draft["headline"], body=draft["body"],
                                        cta=draft["cta"])
            if paket.blocked:
                failures.append(f"youtube: bekci engelledi — {paket.blocked}")
            else:
                sonuc = await asyncio.to_thread(
                    youtube.upload_video, video, title=paket.title,
                    description=paket.full_caption, tags=paket.hashtags,
                    privacy="private")
                if sonuc.ok:
                    already["youtube"] = sonuc.url
                    published_total += 1
                else:
                    failures.append(f"youtube: {sonuc.error}")

        # --- TikTok: iki asamali yukleme, denetim oncesi SELF_ONLY ---
        if "tiktok" not in already and tiktok.is_connected():
            paket = format_for_platform(platform="tiktok", lang=draft["lang"],
                                        headline=draft["headline"], body=draft["body"],
                                        cta=draft["cta"])
            if paket.blocked:
                failures.append(f"tiktok: bekci engelledi — {paket.blocked}")
            else:
                sonuc = await asyncio.to_thread(
                    tiktok.upload_video, video, title=paket.full_caption)
                if sonuc.ok:
                    already["tiktok"] = sonuc.publish_id
                    published_total += 1
                else:
                    failures.append(f"tiktok: {sonuc.error}")

        # --- Instagram: DOSYA kabul etmiyor, herkese acik URL gerekiyor ---
        if "instagram" not in already and instagram.is_connected():
            public_url = os.getenv("VIDEO_PUBLIC_BASE_URL")
            if not public_url:
                failures.append("instagram: VIDEO_PUBLIC_BASE_URL tanimli degil "
                                "(video herkese acik bir adreste durmali)")
            else:
                paket = format_for_platform(platform="instagram", lang=draft["lang"],
                                            headline=draft["headline"], body=draft["body"],
                                            cta=draft["cta"])
                if paket.blocked:
                    failures.append(f"instagram: bekci engelledi — {paket.blocked}")
                else:
                    sonuc = await asyncio.to_thread(
                        instagram.publish_reel,
                        video_url=f"{public_url.rstrip('/')}/{video.name}",
                        caption=paket.full_caption)
                    if sonuc.ok:
                        already["instagram"] = sonuc.media_id
                        published_total += 1
                    else:
                        failures.append(f"instagram: {sonuc.error}")

        async with aiosqlite.connect(db_file) as db:
            await db.execute("UPDATE campaign_drafts SET published_json=? WHERE id=?",
                             (json.dumps(already), draft["id"]))
            await db.commit()

    if published_total or failures:
        await bus.emit(
            "social_publish", "ok" if not failures else "escalated",
            error_code="handler_exception" if failures else None,
            metric={"published": published_total, "failed": len(failures)},
            message=(f"{published_total} yayin yapildi"
                     + (f" | {len(failures)} hata: {'; '.join(failures[:2])}" if failures else "")),
            level="warning" if failures else "info",
            db_file=db_file,
        )
    return {"published": published_total, "failed": len(failures)}


mgr.register_handler("social_publish", social_publish)
mgr.register_handler("attended_post", attended_post)
mgr.register_handler("mail_relay", mail_relay)
mgr.register_handler("ad_generate", ad_generate)
mgr.register_handler("video_generate", video_generate)
mgr.register_handler("video_qc", video_qc)


async def install_jobs(db_file: str = bus.DEFAULT_DB_FILE) -> None:
    """Tekrarlayan is handler'larini kaydeder (manager run_loop bunu cagirir)."""
    await bus.register_job("aging_reprice", kind="aging_reprice",
                           interval_seconds=86400, db_file=db_file)  # gunde 1
    await bus.register_job("unsold_research", kind="unsold_research",
                           interval_seconds=86400, db_file=db_file)  # gunde 1
    await bus.register_job("social_publish", kind="social_publish",
                           interval_seconds=7200, db_file=db_file)   # 2 saatte 1
    await bus.register_job("attended_post", kind="attended_post",
                           interval_seconds=10800, db_file=db_file)  # 3 saatte 1
    await bus.register_job("mail_relay", kind="mail_relay",
                           interval_seconds=600, db_file=db_file)   # 10 dk
    await bus.register_job("ad_generate", kind="ad_generate",
                           interval_seconds=86400, db_file=db_file)   # gunde 1
    await bus.register_job("video_generate", kind="video_generate",
                           interval_seconds=21600, db_file=db_file)   # 6 saatte 1
    await bus.register_job("video_qc", kind="video_qc",
                           interval_seconds=3600, db_file=db_file)    # saatte 1
