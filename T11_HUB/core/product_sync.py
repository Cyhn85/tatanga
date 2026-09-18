"""
Urun senkronu: bu Hub'in kendi urunlerini sunucudaki ortak havuza gonderir, diger
Hub'larin urunlerini buraya ceker. YALNIZCA veri aktarir — hicbir sey yayinlamaz.

Karsidan gelen urunler status='synced' ve sync_origin=<dugum> ile yazilir. Boylece
status='published'/'scraped' secen zamanlanmis isler (fiyat indirimi, siteden kaldirma,
sosyal paylasim, video) onlara hic dokunmaz; _try_auto_publish de sync_origin'i reddeder.
Karsidaki orijinal durum sync_peer_status'ta saklanir.

Yapilandirma (.env): TATANGA_SYNC_URL=https://cssberlin.de/tatanga-sync, TATANGA_SYNC_KEY=...
Ikisi bos ise is sessizce atlanir. Elle calistirma: python -m core.product_sync
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import secrets
import urllib.error
import urllib.request
from datetime import datetime

import aiosqlite

from . import event_bus as bus

PUSH_BATCH = 100
PULL_LIMIT = 200
HTTP_TIMEOUT = 60

SYNC_FIELDS = (
    "id", "source_platform", "source_url", "source_id", "title", "description", "price",
    "currency", "brand", "size", "color", "condition", "category", "images_json",
    "seo_title", "seo_description", "seo_keywords", "seo_tags", "estimated_sell_price",
    "profit_margin", "profit_euro", "recommendation", "best_sell_platform", "shipping_cost",
    "platform_fee", "status", "source_status", "last_source_check", "published_to",
    "cssberlin_id", "scraped_at", "created_at", "updated_at", "total_cost", "arbitrage_json",
    "listed_at", "condition_score", "return_risk", "image_hash", "curation_status",
    "manual_price",
)
# Karsidan gelen veride yerel anlami olmayan ya da yerelde yonetilen alanlar.
PULL_SKIP_FIELDS = {"id", "status"}


def _config() -> tuple[str, str] | None:
    url = os.getenv("TATANGA_SYNC_URL", "").strip().rstrip("/")
    key = os.getenv("TATANGA_SYNC_KEY", "").strip()
    return (url, key) if url and key else None


def _http(method: str, url: str, key: str, body: dict | None = None) -> dict:
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "X-Sync-Key": key,
        "Content-Type": "application/json",
        "User-Agent": "tatanga-hub-sync/1",
    })
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        detail = e.read()[:200].decode(errors="replace")
        raise RuntimeError(f"senkron sunucusu {e.code}: {detail}") from None


async def _ensure_schema(db: aiosqlite.Connection) -> None:
    cols = {r[1] for r in await (await db.execute("PRAGMA table_info(products)")).fetchall()}
    if "sync_origin" not in cols:
        await db.execute("ALTER TABLE products ADD COLUMN sync_origin TEXT")
    if "sync_peer_status" not in cols:
        await db.execute("ALTER TABLE products ADD COLUMN sync_peer_status TEXT")
    await db.execute(
        "CREATE TABLE IF NOT EXISTS sync_pushed (source_url TEXT PRIMARY KEY, hash TEXT NOT NULL)"
    )
    await db.execute(
        "CREATE TABLE IF NOT EXISTS sync_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    )
    await db.commit()


def _payload(row: aiosqlite.Row) -> tuple[dict, str]:
    data = {k: row[k] for k in SYNC_FIELDS if k in row.keys()}
    digest = hashlib.sha1(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return data, digest


async def _push(db: aiosqlite.Connection, url: str, key: str) -> dict:
    pushed = dict(await (await db.execute("SELECT source_url, hash FROM sync_pushed")).fetchall())
    rows = await (await db.execute(
        "SELECT * FROM products WHERE sync_origin IS NULL "
        "AND source_url LIKE 'http%'"
    )).fetchall()
    pending = []
    for row in rows:
        data, digest = _payload(row)
        if pushed.get(data["source_url"]) != digest:
            pending.append((data, digest))

    totals = {"sent": 0, "inserted": 0, "updated": 0, "unchanged": 0, "foreign": 0, "rejected": 0}
    for i in range(0, len(pending), PUSH_BATCH):
        batch = pending[i:i + PUSH_BATCH]
        result = await asyncio.to_thread(
            _http, "POST", f"{url}/push", key, {"products": [d for d, _ in batch]}
        )
        for k in ("inserted", "updated", "unchanged", "foreign", "rejected"):
            totals[k] += int(result.get(k, 0))
        totals["sent"] += len(batch)
        await db.executemany(
            "INSERT INTO sync_pushed (source_url, hash) VALUES (?, ?) "
            "ON CONFLICT(source_url) DO UPDATE SET hash=excluded.hash",
            [(d["source_url"], h) for d, h in batch],
        )
        await db.commit()
    return totals


async def _apply_remote(db: aiosqlite.Connection, owner: str, data: dict, columns: set[str]) -> str:
    source_url = data.get("source_url")
    if not isinstance(source_url, str):
        return "skipped"
    local = await (await db.execute(
        "SELECT id, sync_origin FROM products WHERE source_url=?", (source_url,)
    )).fetchone()
    fields = {k: v for k, v in data.items() if k in columns and k not in PULL_SKIP_FIELDS}
    fields["sync_origin"] = owner
    fields["sync_peer_status"] = data.get("status")

    if local is not None:
        if local["sync_origin"] is None:
            return "own"  # ayni linki bu makine de kazimis: yerel kayit esastir
        sets = ", ".join(f"{k}=?" for k in fields)
        await db.execute(f"UPDATE products SET {sets} WHERE id=?", (*fields.values(), local["id"]))
        return "updated"

    product_id = data.get("id") if isinstance(data.get("id"), str) else None
    if not product_id or await (await db.execute(
        "SELECT 1 FROM products WHERE id=?", (product_id,)
    )).fetchone():
        product_id = f"SYNC-{datetime.now():%Y%m%d%H%M%S}-{secrets.token_hex(3)}"
    fields.update({
        "id": product_id,
        "status": "synced",
        "raw_images_json": "[]",
        "processed_images_json": "[]",
        "bg_removed": 0,
    })
    cols = ", ".join(fields)
    marks = ", ".join("?" * len(fields))
    await db.execute(f"INSERT INTO products ({cols}) VALUES ({marks})", tuple(fields.values()))
    return "inserted"


async def _pull(db: aiosqlite.Connection, url: str, key: str) -> dict:
    columns = {r[1] for r in await (await db.execute("PRAGMA table_info(products)")).fetchall()}
    row = await (await db.execute("SELECT value FROM sync_meta WHERE key='pull_cursor'")).fetchone()
    cursor = int(row[0]) if row else 0
    totals = {"inserted": 0, "updated": 0, "own": 0, "skipped": 0}
    while True:
        page = await asyncio.to_thread(
            _http, "GET", f"{url}/pull?since={cursor}&limit={PULL_LIMIT}", key
        )
        for item in page.get("products", []):
            outcome = await _apply_remote(db, str(item.get("owner")), item.get("data") or {}, columns)
            totals[outcome] += 1
        cursor = int(page.get("next", cursor))
        await db.execute(
            "INSERT INTO sync_meta (key, value) VALUES ('pull_cursor', ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (str(cursor),),
        )
        await db.commit()
        if not page.get("more"):
            return totals


async def run_sync(db_file: str = bus.DEFAULT_DB_FILE) -> dict:
    cfg = _config()
    if cfg is None:
        return {"skipped": "TATANGA_SYNC_URL/TATANGA_SYNC_KEY tanimli degil"}
    url, key = cfg
    async with aiosqlite.connect(db_file, timeout=30) as db:
        db.row_factory = aiosqlite.Row
        await _ensure_schema(db)
        pushed = await _push(db, url, key)
        pulled = await _pull(db, url, key)
    return {"push": pushed, "pull": pulled}


async def product_sync(job: bus.ScheduledJob) -> dict:
    result = await run_sync()
    if "skipped" not in result:
        p, q = result["push"], result["pull"]
        await bus.emit(
            "product_sync", "ok",
            metric={"pushed_new": p["inserted"], "pushed_updated": p["updated"],
                    "pulled_new": q["inserted"], "pulled_updated": q["updated"]},
            message=(f"senkron: {p['inserted']} yeni/{p['updated']} guncel gonderildi, "
                     f"{q['inserted']} yeni/{q['updated']} guncel alindi"),
        )
    return result


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    print(json.dumps(asyncio.run(run_sync()), ensure_ascii=False, indent=2))
