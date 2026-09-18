#!/usr/bin/env python3
"""
TATANGA urun senkron sunucusu — iki (veya daha fazla) Hub'in urunlerini tek havuzda toplar.

Sadece veri tasir: cssberlin'e yayin yapmaz, hicbir islem tetiklemez.
Tekillestirme kaynak linki (source_url) uzerinden; bir linki ilk gonderen dugum o urunun
sahibidir ve yalnizca sahibi guncelleyebilir (iki makine ayni kaydi birbirine ezdirmesin).
Veritabani yalnizca bu klasorde; servis 127.0.0.1'e baglanir, disari nginx ile acilir.
Yalnizca Python standart kutuphanesi.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sqlite3
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.environ.get("TATANGA_SYNC_DB", os.path.join(BASE_DIR, "sync.db"))
HOST = os.environ.get("TATANGA_SYNC_HOST", "127.0.0.1")
PORT = int(os.environ.get("TATANGA_SYNC_PORT", "8610"))
PREFIX = "/tatanga-sync"

MAX_BODY_BYTES = 4 * 1024 * 1024
MAX_PUSH_ITEMS = 500
MAX_PULL_LIMIT = 500
MAX_STR_LEN = 20000

ALLOWED_FIELDS = frozenset({
    "id", "source_platform", "source_url", "source_id", "title", "description", "price",
    "currency", "brand", "size", "color", "condition", "category", "images_json",
    "seo_title", "seo_description", "seo_keywords", "seo_tags", "estimated_sell_price",
    "profit_margin", "profit_euro", "recommendation", "best_sell_platform", "shipping_cost",
    "platform_fee", "status", "source_status", "last_source_check", "published_to",
    "cssberlin_id", "scraped_at", "created_at", "updated_at", "total_cost", "arbitrage_json",
    "listed_at", "condition_score", "return_risk", "image_hash", "curation_status",
    "manual_price",
})

_write_lock = threading.Lock()


def _load_keys() -> dict[str, str]:
    """TATANGA_SYNC_KEYS='dugum1:anahtar1,dugum2:anahtar2' -> {anahtar: dugum}."""
    keys: dict[str, str] = {}
    for part in os.environ.get("TATANGA_SYNC_KEYS", "").split(","):
        node, _, key = part.strip().partition(":")
        if node and len(key) >= 32:
            keys[key] = node
    return keys


KEYS = _load_keys()


def _node_for(key: str) -> str | None:
    for known, node in KEYS.items():
        if hmac.compare_digest(known.encode(), key.encode()):
            return node
    return None


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_FILE, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """CREATE TABLE IF NOT EXISTS products (
                   source_url TEXT PRIMARY KEY,
                   owner_node TEXT NOT NULL,
                   data_json TEXT NOT NULL,
                   data_hash TEXT NOT NULL,
                   rev INTEGER NOT NULL,
                   first_seen TEXT NOT NULL,
                   updated_at TEXT NOT NULL)"""
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_products_rev ON products(rev)")


def _clean(item: object) -> dict | None:
    if not isinstance(item, dict):
        return None
    url = item.get("source_url")
    if not isinstance(url, str) or not url.startswith(("http://", "https://")) or len(url) > 2000:
        return None
    out: dict = {}
    for k, v in item.items():
        if k not in ALLOWED_FIELDS:
            continue
        if isinstance(v, str):
            out[k] = v[:MAX_STR_LEN]
        elif v is None or isinstance(v, (int, float)) and not isinstance(v, bool):
            out[k] = v
    return out


def push(node: str, items: list) -> dict:
    stats = {"inserted": 0, "updated": 0, "unchanged": 0, "foreign": 0, "rejected": 0}
    now = _now()
    with _write_lock, _connect() as conn:
        rev = conn.execute("SELECT COALESCE(MAX(rev), 0) FROM products").fetchone()[0]
        for raw in items:
            data = _clean(raw)
            if data is None:
                stats["rejected"] += 1
                continue
            data_json = json.dumps(data, sort_keys=True, ensure_ascii=False)
            data_hash = hashlib.sha1(data_json.encode()).hexdigest()
            row = conn.execute(
                "SELECT owner_node, data_hash FROM products WHERE source_url=?",
                (data["source_url"],),
            ).fetchone()
            if row is None:
                rev += 1
                conn.execute(
                    "INSERT INTO products VALUES (?,?,?,?,?,?,?)",
                    (data["source_url"], node, data_json, data_hash, rev, now, now),
                )
                stats["inserted"] += 1
            elif row["owner_node"] != node:
                stats["foreign"] += 1
            elif row["data_hash"] == data_hash:
                stats["unchanged"] += 1
            else:
                rev += 1
                conn.execute(
                    "UPDATE products SET data_json=?, data_hash=?, rev=?, updated_at=? "
                    "WHERE source_url=?",
                    (data_json, data_hash, rev, now, data["source_url"]),
                )
                stats["updated"] += 1
    return stats


def pull(node: str, since: int, limit: int) -> dict:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT source_url, owner_node, data_json, rev FROM products "
            "WHERE rev > ? ORDER BY rev LIMIT ?",
            (since, limit),
        ).fetchall()
    products = [
        {"owner": r["owner_node"], "rev": r["rev"], "data": json.loads(r["data_json"])}
        for r in rows
        if r["owner_node"] != node
    ]
    next_cursor = rows[-1]["rev"] if rows else since
    return {"products": products, "next": next_cursor, "more": len(rows) == limit}


def stats() -> dict:
    with _connect() as conn:
        by_node = conn.execute(
            "SELECT owner_node, COUNT(*) c, MAX(updated_at) last FROM products GROUP BY owner_node"
        ).fetchall()
    return {"nodes": {r["owner_node"]: {"products": r["c"], "last_update": r["last"]} for r in by_node}}


class Handler(BaseHTTPRequestHandler):
    server_version = "tatanga-sync/1"

    def log_message(self, fmt: str, *args) -> None:
        print(f"{self.address_string()} {fmt % args}", flush=True)

    def _send(self, code: int, body: dict) -> None:
        payload = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _auth(self) -> str | None:
        node = _node_for(self.headers.get("X-Sync-Key", ""))
        if node is None:
            time.sleep(1)
            self._send(401, {"error": "gecersiz anahtar"})
        return node

    def _route(self) -> tuple[str, dict]:
        parsed = urlparse(self.path)
        path = parsed.path
        if path.startswith(PREFIX):
            path = path[len(PREFIX):]
        return path or "/", parse_qs(parsed.query)

    def do_GET(self) -> None:
        path, query = self._route()
        if path == "/health":
            self._send(200, {"ok": True})
            return
        node = self._auth()
        if node is None:
            return
        if path == "/pull":
            try:
                since = max(0, int(query.get("since", ["0"])[0]))
                limit = min(MAX_PULL_LIMIT, max(1, int(query.get("limit", ["200"])[0])))
            except ValueError:
                self._send(400, {"error": "since/limit sayi olmali"})
                return
            self._send(200, pull(node, since, limit))
        elif path == "/stats":
            self._send(200, {"node": node, **stats()})
        else:
            self._send(404, {"error": "bulunamadi"})

    def do_POST(self) -> None:
        path, _ = self._route()
        node = self._auth()
        if node is None:
            return
        if path != "/push":
            self._send(404, {"error": "bulunamadi"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = -1
        if length <= 0 or length > MAX_BODY_BYTES:
            self._send(413, {"error": f"govde 1..{MAX_BODY_BYTES} bayt olmali"})
            return
        try:
            body = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._send(400, {"error": "gecersiz JSON"})
            return
        items = body.get("products") if isinstance(body, dict) else None
        if not isinstance(items, list) or len(items) > MAX_PUSH_ITEMS:
            self._send(400, {"error": f"'products' en fazla {MAX_PUSH_ITEMS} ogeli liste olmali"})
            return
        self._send(200, {"node": node, **push(node, items)})


def main() -> None:
    if not KEYS:
        raise SystemExit("TATANGA_SYNC_KEYS tanimli degil (dugum:anahtar, anahtar >= 32 karakter)")
    init_db()
    print(f"tatanga-sync {HOST}:{PORT} dugumler={sorted(set(KEYS.values()))}", flush=True)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
