"""Lapisan database SQLite (file tunggal, zero-config).

Menyediakan koneksi, inisialisasi skema, dan seed data default (kategori foto,
peta kata kunci auto-sort, akun admin awal).
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from . import config
from .auth import hash_password

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'operator',   -- 'admin' | 'operator'
    full_name     TEXT DEFAULT '',
    active        INTEGER NOT NULL DEFAULT 1,
    must_change   INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token      TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS templates (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    filename    TEXT NOT NULL,
    path        TEXT NOT NULL,
    sheet_log   TEXT NOT NULL,
    sheet_detail TEXT NOT NULL,
    config_json TEXT NOT NULL DEFAULT '{}',   -- mapping kolom/anchor foto
    active      INTEGER NOT NULL DEFAULT 0,
    uploaded_by INTEGER REFERENCES users(id),
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS locations (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    code       TEXT UNIQUE NOT NULL,             -- mis. Lokasi_0043
    name       TEXT NOT NULL DEFAULT '',
    data_json  TEXT NOT NULL DEFAULT '{}',       -- field lokasi + custom fields
    status     TEXT NOT NULL DEFAULT 'draft',    -- draft | complete
    created_by INTEGER REFERENCES users(id),
    owner_id   INTEGER REFERENCES users(id),     -- pemilik saat ini (bisa ditransfer admin)
    deleted_at TEXT,                              -- soft-delete (NULL = aktif)
    deleted_by INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS inventory_items (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
    nama_barang TEXT DEFAULT '',
    merk_type   TEXT DEFAULT '',
    jumlah      TEXT DEFAULT '',
    sn_tagging  TEXT DEFAULT '',
    keterangan  TEXT DEFAULT '',
    sort_order  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS photos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    location_id INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
    category    TEXT NOT NULL DEFAULT 'uncategorized',
    orig_name   TEXT DEFAULT '',
    filename    TEXT NOT NULL,                   -- nama file tersimpan di data/images
    path        TEXT NOT NULL,
    ocr_text    TEXT DEFAULT '',
    ocr_serial  TEXT DEFAULT '',
    matched_by  TEXT DEFAULT '',                 -- filename | folder | manual
    uploaded_by INTEGER REFERENCES users(id),
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key        TEXT PRIMARY KEY,
    value_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS edit_requests (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    location_id  INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
    requester_id INTEGER NOT NULL REFERENCES users(id),
    owner_id     INTEGER REFERENCES users(id),      -- pemilik saat request dibuat
    message      TEXT DEFAULT '',
    status       TEXT NOT NULL DEFAULT 'pending',   -- pending | approved | rejected
    created_at   TEXT NOT NULL,
    resolved_at  TEXT,
    resolved_by  INTEGER REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS audit_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER REFERENCES users(id),
    username   TEXT DEFAULT '',
    action     TEXT NOT NULL,
    entity     TEXT DEFAULT '',
    entity_id  TEXT DEFAULT '',
    detail     TEXT DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_inv_loc ON inventory_items(location_id);
CREATE INDEX IF NOT EXISTS idx_photo_loc ON photos(location_id);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
"""

# --- Default kategori foto (sesuai Template_BAA.xlsx) ---
DEFAULT_PHOTO_CATEGORIES = [
    {"key": "dashboard", "label": "Capture Dashboard (STARMON)", "ocr": False, "keywords": ["dashboard", "starmon"]},
    {"key": "tampak_depan", "label": "Foto Tampak Depan / Plang Lokasi", "ocr": False, "keywords": ["plang", "depan", "tampak"]},
    {"key": "teknisi", "label": "Foto Teknisi + PIC", "ocr": False, "keywords": ["teknisi", "pic"]},
    {"key": "outdoor", "label": "Perangkat Outdoor Terpasang", "ocr": False, "keywords": ["outdoor"]},
    {"key": "indoor", "label": "Perangkat Indoor Terpasang", "ocr": False, "keywords": ["indoor"]},
    {"key": "sn_kit", "label": "Foto SN Kit Starlink", "ocr": True, "keywords": ["sn_kit", "snkit", "kit"], "prefixes": ["KIT", "KITX"], "sn_item": "Kit Starlink"},
    {"key": "sn_router", "label": "Foto SN Router", "ocr": True, "keywords": ["sn_router", "snrtr", "router"], "prefixes": ["RTR"], "sn_item": "Router"},
    {"key": "sn_ap", "label": "Foto SN Access Point", "ocr": True, "keywords": ["sn_ap", "sn_access", "accesspoint", "access_point"], "prefixes": ["AP", "TLSAT"], "sn_item": "Access Point"},
    {"key": "ping", "label": "Capture Tes Ping", "ocr": False, "keywords": ["ping"]},
    {"key": "speed", "label": "Capture Tes Bandwidth / Speed", "ocr": False, "keywords": ["speed", "bandwidth", "speedtest"]},
    {"key": "simkopdes", "label": "Capture Buka Situs SIMKOPDES", "ocr": False, "keywords": ["simkopdes"]},
]

# Default baris inventory untuk lokasi baru (prefilled nama perangkat)
DEFAULT_INVENTORY_ITEMS = ["Kit Starlink", "Router", "Access Point"]

# Field lokasi default (bisa ditambah custom field lewat Pengaturan)
DEFAULT_LOCATION_FIELDS = [
    {"key": "nama_lokasi", "label": "Nama Lokasi / Koperasi", "type": "text", "required": True, "builtin": True},
    {"key": "tanggal", "label": "Tanggal Aktivasi", "type": "date", "required": False, "builtin": True},
    {"key": "teknisi", "label": "Teknisi", "type": "text", "required": False, "builtin": True},
    {"key": "pic", "label": "PIC Lokasi", "type": "text", "required": False, "builtin": True},
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect() -> sqlite3.Connection:
    config.ensure_dirs()
    # check_same_thread=False: FastAPI menyelesaikan tiap dependency sync di thread
    # pool yang bisa berbeda, sedangkan koneksi dibuat per-request & dipakai
    # berurutan (bukan paralel), jadi aman melintasi thread.
    conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def get_setting(conn: sqlite3.Connection, key: str, default: Any = None) -> Any:
    row = conn.execute("SELECT value_json FROM settings WHERE key=?", (key,)).fetchone()
    return json.loads(row["value_json"]) if row else default


def set_setting(conn: sqlite3.Connection, key: str, value: Any) -> None:
    conn.execute(
        "INSERT INTO settings(key, value_json) VALUES(?,?) "
        "ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json",
        (key, json.dumps(value, ensure_ascii=False)),
    )


def _has_column(conn: sqlite3.Connection, table: str, col: str) -> bool:
    return any(r["name"] == col for r in conn.execute(f"PRAGMA table_info({table})").fetchall())


def _migrate(conn: sqlite3.Connection) -> None:
    """Migrasi ringan & idempoten untuk DB lama."""
    # Kepemilikan lokasi: owner_id (transfer bisa mengubah tanpa hilangkan created_by)
    if not _has_column(conn, "locations", "owner_id"):
        conn.execute("ALTER TABLE locations ADD COLUMN owner_id INTEGER REFERENCES users(id)")
        conn.execute("UPDATE locations SET owner_id = created_by WHERE owner_id IS NULL")
    # Soft-delete lokasi (Task #9) — disiapkan sekarang agar aman dipakai nanti
    if not _has_column(conn, "locations", "deleted_at"):
        conn.execute("ALTER TABLE locations ADD COLUMN deleted_at TEXT")
    if not _has_column(conn, "locations", "deleted_by"):
        conn.execute("ALTER TABLE locations ADD COLUMN deleted_by INTEGER REFERENCES users(id)")
    conn.commit()


def init_db() -> None:
    conn = connect()
    try:
        conn.executescript(SCHEMA)
        _migrate(conn)
        # Seed settings
        if get_setting(conn, "photo_categories") is None:
            set_setting(conn, "photo_categories", DEFAULT_PHOTO_CATEGORIES)
        if get_setting(conn, "location_fields") is None:
            set_setting(conn, "location_fields", DEFAULT_LOCATION_FIELDS)
        if get_setting(conn, "default_inventory_items") is None:
            set_setting(conn, "default_inventory_items", DEFAULT_INVENTORY_ITEMS)
        if get_setting(conn, "item_merks") is None:
            set_setting(conn, "item_merks", {})
        if get_setting(conn, "inventory_keterangan") is None:
            set_setting(conn, "inventory_keterangan", ["OK"])
        _title = get_setting(conn, "app_title")
        if _title is None or _title == "REZA BAA Generator":
            set_setting(conn, "app_title", "BAA Generator")
        # Seed admin default (admin/admin, wajib ganti saat login pertama)
        has_user = conn.execute("SELECT 1 FROM users LIMIT 1").fetchone()
        if not has_user:
            conn.execute(
                "INSERT INTO users(username, password_hash, role, full_name, must_change, created_at) "
                "VALUES(?,?,?,?,?,?)",
                ("admin", hash_password("admin"), "admin", "Administrator", 1, now_iso()),
            )
        conn.commit()
    finally:
        conn.close()
