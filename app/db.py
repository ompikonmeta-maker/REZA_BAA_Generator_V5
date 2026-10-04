"""Lapisan database SQLite (file tunggal, zero-config).

Menyediakan koneksi, inisialisasi skema, dan seed data default (kategori foto,
peta kata kunci auto-sort, akun admin awal).
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import config
from .auth import hash_password

# Hub (data/app.db): akun, sesi, audit, daftar project + akses. Data kerja
# (lokasi, foto, template, pengaturan) ada di DB per project: data/projects/pN.db.
HUB_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'operator',   -- 'admin' | 'operator' | 'viewer'
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

CREATE TABLE IF NOT EXISTS settings (
    key        TEXT PRIMARY KEY,
    value_json TEXT NOT NULL
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

CREATE TABLE IF NOT EXISTS projects (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    prefix     TEXT UNIQUE NOT NULL COLLATE NOCASE,  -- awalan kode lokasi, mis. LOK -> LOK_00001
    color      TEXT NOT NULL DEFAULT '#0aa39d',
    db_file    TEXT NOT NULL,
    archived   INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS project_members (
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    PRIMARY KEY (project_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
"""

# Tabel per project. Kolom *_by/owner_id menyimpan id user di hub (tanpa FK:
# SQLite tidak mendukung foreign key lintas file database).
PROJECT_SCHEMA = """
CREATE TABLE IF NOT EXISTS templates (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    filename    TEXT NOT NULL,
    path        TEXT NOT NULL,
    sheet_log   TEXT NOT NULL,
    sheet_detail TEXT NOT NULL,
    config_json TEXT NOT NULL DEFAULT '{}',   -- mapping kolom/anchor foto
    active      INTEGER NOT NULL DEFAULT 0,
    uploaded_by INTEGER,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS locations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT UNIQUE NOT NULL,             -- mis. LOK_00043
    name        TEXT NOT NULL DEFAULT '',
    data_json   TEXT NOT NULL DEFAULT '{}',       -- field lokasi + custom fields
    status      TEXT NOT NULL DEFAULT 'draft',    -- draft | selesai
    created_by  INTEGER,
    owner_id    INTEGER,                          -- pemilik saat ini (bisa ditransfer admin)
    deleted_at  TEXT,                             -- soft-delete (NULL = aktif)
    deleted_by  INTEGER,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    modified_at TEXT,
    modified_by INTEGER,
    done_at     TEXT
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
    uploaded_by INTEGER,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key        TEXT PRIMARY KEY,
    value_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS edit_requests (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    location_id  INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
    requester_id INTEGER NOT NULL,
    owner_id     INTEGER,                         -- pemilik saat request dibuat
    message      TEXT DEFAULT '',
    status       TEXT NOT NULL DEFAULT 'pending', -- pending | approved | rejected
    created_at   TEXT NOT NULL,
    resolved_at  TEXT,
    resolved_by  INTEGER
);

CREATE TABLE IF NOT EXISTS activity (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER,
    location_id INTEGER REFERENCES locations(id) ON DELETE CASCADE,
    kind        TEXT NOT NULL,
    detail      TEXT DEFAULT '',
    created_at  TEXT NOT NULL
);

-- Dokumen scan PDF (wajib, satu per lokasi): halaman pertama saat export PDF
CREATE TABLE IF NOT EXISTS scan_docs (
    location_id INTEGER PRIMARY KEY REFERENCES locations(id) ON DELETE CASCADE,
    orig_name   TEXT DEFAULT '',
    path        TEXT NOT NULL,                   -- relatif ke folder project: docs/<KODE>/scan_x.pdf
    pages       INTEGER NOT NULL DEFAULT 1,
    size        INTEGER NOT NULL DEFAULT 0,
    uploaded_by INTEGER,
    created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_inv_loc ON inventory_items(location_id);
CREATE INDEX IF NOT EXISTS idx_photo_loc ON photos(location_id);
CREATE INDEX IF NOT EXISTS ix_activity_time ON activity(created_at);
"""

# Tabel data kerja yang dulu ada di app.db (pra multi-project)
_LEGACY_TABLES = ["templates", "locations", "inventory_items", "photos", "edit_requests", "activity"]
MAX_PROJECTS = 5
PROJECT_COLORS = ["#0aa39d", "#7b5cd6", "#d07a1f", "#3b7be0", "#d0496a", "#5a9e3a"]

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


def _has_table(conn: sqlite3.Connection, table: str, schema: str = "main") -> bool:
    return conn.execute(f"SELECT 1 FROM {schema}.sqlite_master WHERE type='table' AND name=?",
                        (table,)).fetchone() is not None


def _migrate_legacy(conn: sqlite3.Connection) -> None:
    """Migrasi kolom untuk app.db lama (pra multi-project) sebelum datanya
    dipindah ke project pertama. Idempoten."""
    if not _has_column(conn, "locations", "owner_id"):
        conn.execute("ALTER TABLE locations ADD COLUMN owner_id INTEGER REFERENCES users(id)")
        conn.execute("UPDATE locations SET owner_id = created_by WHERE owner_id IS NULL")
    if not _has_column(conn, "locations", "deleted_at"):
        conn.execute("ALTER TABLE locations ADD COLUMN deleted_at TEXT")
    if not _has_column(conn, "locations", "deleted_by"):
        conn.execute("ALTER TABLE locations ADD COLUMN deleted_by INTEGER REFERENCES users(id)")
    if not _has_column(conn, "locations", "modified_at"):
        conn.execute("ALTER TABLE locations ADD COLUMN modified_at TEXT")
        conn.execute("UPDATE locations SET modified_at = updated_at WHERE modified_at IS NULL")
    if not _has_column(conn, "locations", "modified_by"):
        conn.execute("ALTER TABLE locations ADD COLUMN modified_by INTEGER REFERENCES users(id)")
    if not _has_column(conn, "locations", "done_at"):
        conn.execute("ALTER TABLE locations ADD COLUMN done_at TEXT")
        conn.execute("UPDATE locations SET done_at = updated_at WHERE status='selesai' AND done_at IS NULL")
    conn.commit()


def _migrate_hub(conn: sqlite3.Connection) -> None:
    if not _has_column(conn, "users", "last_seen_at"):
        conn.execute("ALTER TABLE users ADD COLUMN last_seen_at TEXT")
    if not _has_column(conn, "audit_log", "project_id"):
        conn.execute("ALTER TABLE audit_log ADD COLUMN project_id INTEGER")
    conn.commit()


# ---------- project ----------
class ProjectConn(sqlite3.Connection):
    """Koneksi ke DB satu project; hub ter-ATTACH sebagai skema ``hub``.

    Nama tabel tanpa skema dicari di main dulu lalu hub, jadi ``users`` /
    ``audit_log`` / ``sessions`` otomatis ke hub, sedangkan ``settings`` ke
    pengaturan project. ``pm_users`` = user yang punya akses ke project ini
    (admin + anggota)."""
    project: dict | None = None


# Satu project = satu folder: data/projects/pN/{project.db, images/<KODE>/, templates/}.
# Path file di DB disimpan RELATIF terhadap folder project (mis. images/LOK_00012/x.jpg),
# jadi folder project/data bisa dipindah atau dipulihkan di PC lain tanpa path rusak.
def project_dir(p) -> Path:
    return config.PROJECTS_DIR / f"p{int(p['id'])}"


def project_path(p) -> Path:
    return project_dir(p) / "project.db"


def images_dir(conn) -> Path:
    return project_dir(conn.project) / "images"


def docs_dir(conn) -> Path:
    return project_dir(conn.project) / "docs"


def templates_dir(conn) -> Path:
    return project_dir(conn.project) / "templates"


def fpath(conn, stored: str) -> Path:
    """Path absolut dari path tersimpan (relatif ke folder project)."""
    p = Path(stored or "")
    return p if p.is_absolute() else project_dir(conn.project) / p


def rel_path(conn, absolute) -> str:
    return Path(absolute).relative_to(project_dir(conn.project)).as_posix()


def connect_project(p) -> ProjectConn:
    config.ensure_dirs()
    conn = sqlite3.connect(project_path(p), check_same_thread=False, factory=ProjectConn)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("ATTACH DATABASE ? AS hub", (str(config.DB_PATH),))
    conn.project = dict(p)
    conn.execute(
        "CREATE TEMP VIEW IF NOT EXISTS pm_users AS SELECT * FROM hub.users WHERE role='admin' "
        f"OR id IN (SELECT user_id FROM hub.project_members WHERE project_id={int(p['id'])})")
    return conn


def format_code(conn, n: int) -> str:
    """Kode urut per project dari nomor baris, mis. LOK_00001 (min. 5 digit)."""
    pj = getattr(conn, "project", None) or {}
    return f"{(pj.get('prefix') or 'LOK').upper()}_{n:05d}"


def app_title(conn) -> str:
    """Judul app global (disimpan di hub)."""
    sch = "hub." if getattr(conn, "project", None) else ""
    row = conn.execute(f"SELECT value_json FROM {sch}settings WHERE key='app_title'").fetchone()
    return json.loads(row["value_json"]) if row else "BAA Generator"


def _seed_project(conn: sqlite3.Connection, base: dict | None = None) -> None:
    """Isi pengaturan default project (dari ``base`` bila ada, mis. salinan
    pengaturan project pertama — saat ini antar project hanya beda template)."""
    base = base or {}
    defaults = {
        "photo_categories": DEFAULT_PHOTO_CATEGORIES,
        "location_fields": DEFAULT_LOCATION_FIELDS,
        "default_inventory_items": DEFAULT_INVENTORY_ITEMS,
        "item_merks": {},
        "inventory_keterangan": ["OK"],
    }
    for k, v in defaults.items():
        if get_setting(conn, k) is None:
            set_setting(conn, k, base.get(k, v))
    for k in ("aging_days",):
        if k in base and get_setting(conn, k) is None:
            set_setting(conn, k, base[k])
    conn.commit()


def init_project_db(p, base: dict | None = None) -> None:
    for d in (project_dir(p), project_dir(p) / "images", project_dir(p) / "templates"):
        d.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(project_path(p))
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(PROJECT_SCHEMA)
        _seed_project(conn, base)
    finally:
        conn.close()


def project_settings(p) -> dict:
    conn = sqlite3.connect(project_path(p))
    conn.row_factory = sqlite3.Row
    try:
        return {r["key"]: json.loads(r["value_json"])
                for r in conn.execute("SELECT key, value_json FROM settings")}
    finally:
        conn.close()


def _move_legacy_to_project(hub: sqlite3.Connection, p) -> None:
    """Pindahkan data kerja dari app.db lama ke DB project pertama, lalu ganti
    nama tabel lama menjadi legacy_* (disimpan sebagai cadangan)."""
    _migrate_legacy(hub)
    init_project_db(p)
    pc = sqlite3.connect(project_path(p))
    pc.row_factory = sqlite3.Row
    try:
        pc.execute("PRAGMA foreign_keys = OFF")
        pc.execute("ATTACH DATABASE ? AS old", (str(config.DB_PATH),))
        for t in _LEGACY_TABLES:
            if not _has_table(pc, t, "old"):
                continue
            new_cols = {r["name"] for r in pc.execute(f"PRAGMA main.table_info({t})")}
            cols = [r["name"] for r in pc.execute(f"PRAGMA old.table_info({t})") if r["name"] in new_cols]
            cl = ",".join(f'"{c}"' for c in cols)
            pc.execute(f"DELETE FROM main.{t}")
            pc.execute(f"INSERT INTO main.{t}({cl}) SELECT {cl} FROM old.{t}")
        # Lanjutkan penomoran lama (kode lokasi yang pernah terbit tidak dipakai ulang)
        for r in pc.execute("SELECT name, seq FROM old.sqlite_sequence").fetchall():
            if r["name"] in _LEGACY_TABLES:
                pc.execute("UPDATE main.sqlite_sequence SET seq=MAX(seq, ?) WHERE name=?", (r["seq"], r["name"]))
        pc.execute("DELETE FROM main.settings")
        pc.execute("INSERT INTO main.settings(key, value_json) SELECT key, value_json FROM old.settings "
                   "WHERE key <> 'app_title'")
        pc.commit()
        pc.execute("DETACH DATABASE old")
        _seed_project(pc)
    finally:
        pc.close()
    hub.execute("PRAGMA foreign_keys = OFF")
    for t in _LEGACY_TABLES:
        if _has_table(hub, t):
            hub.execute(f'ALTER TABLE "{t}" RENAME TO "legacy_{t}"')
    hub.commit()
    hub.execute("PRAGMA foreign_keys = ON")


def create_project(hub: sqlite3.Connection, name: str, prefix: str, color: str,
                   base: dict | None = None) -> int:
    cur = hub.execute("INSERT INTO projects(name, prefix, color, db_file, created_at) VALUES(?,?,?,?,?)",
                      (name, prefix.upper(), color, "", now_iso()))
    pid = cur.lastrowid
    hub.execute("UPDATE projects SET db_file=? WHERE id=?", (f"p{pid}/project.db", pid))
    hub.commit()
    init_project_db({"id": pid}, base)
    return pid


def _to_folder(hub: sqlite3.Connection, p) -> None:
    """Tata letak awal (data/projects/pN.db) -> folder data/projects/pN/project.db."""
    old = config.PROJECTS_DIR / f"p{int(p['id'])}.db"
    new = project_path(p)
    if old.exists() and not new.exists():
        c = sqlite3.connect(old)
        try:
            c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            c.close()
        new.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(old), str(new))
        for ext in ("-wal", "-shm"):
            Path(str(old) + ext).unlink(missing_ok=True)
    if p["db_file"] != f"p{int(p['id'])}/project.db":
        hub.execute("UPDATE projects SET db_file=? WHERE id=?", (f"p{int(p['id'])}/project.db", p["id"]))
        hub.commit()


def _relocate_files(p) -> None:
    """Pindahkan foto & template yang masih di folder global lama (data/images,
    data/templates) atau tersimpan dengan path absolut ke folder project, lalu
    simpan path-nya relatif. Idempoten: baris yang sudah relatif dilewati."""
    base = project_dir(p)
    conn = sqlite3.connect(project_path(p))
    conn.row_factory = sqlite3.Row
    try:
        jobs = [("photos", "images/", lambda src: base / "images" / src.parent.name / src.name,
                 lambda src: config.IMAGES_DIR / src.parent.name / src.name),
                ("templates", "templates/", lambda src: base / "templates" / src.name,
                 lambda src: config.TEMPLATES_DIR / src.name)]
        for table, pre, dest_of, legacy_of in jobs:
            rows = conn.execute(f"SELECT id, path FROM {table} WHERE path NOT LIKE ?", (pre + "%",)).fetchall()
            for r in rows:
                src = Path((r["path"] or "").replace("\\", "/") if os.sep == "/" else (r["path"] or ""))
                dest = dest_of(src)
                if not dest.exists():
                    for cand in (legacy_of(src), src):
                        if cand.is_file():
                            dest.parent.mkdir(parents=True, exist_ok=True)
                            # di dalam folder data -> pindah; di luar (path absolut lama) -> salin saja
                            inside = config.DATA_DIR.resolve() in cand.resolve().parents
                            (shutil.move if inside else shutil.copy2)(str(cand), str(dest))
                            break
                conn.execute(f"UPDATE {table} SET path=? WHERE id=?", (dest.relative_to(base).as_posix(), r["id"]))
            if rows:
                conn.commit()
    finally:
        conn.close()
    # Bersihkan folder global lama yang sudah kosong
    for d in (config.IMAGES_DIR, config.TEMPLATES_DIR):
        if d.is_dir():
            for sub in sorted(d.rglob("*"), key=lambda x: -len(x.parts)):
                if sub.is_dir():
                    try:
                        sub.rmdir()
                    except OSError:
                        pass
            try:
                d.rmdir()
            except OSError:
                pass


def touch_modified(conn: sqlite3.Connection, loc_id: int, user_id, kind: str = "edit",
                   detail: str = "") -> None:
    """Catat perubahan isi lokasi (data, inventory, foto): waktu + pengubah,
    plus satu baris activity (feed & ritme kerja)."""
    now = now_iso()
    conn.execute("UPDATE locations SET modified_at=?, modified_by=?, updated_at=? WHERE id=?",
                 (now, user_id, now, loc_id))
    log_activity(conn, loc_id, user_id, kind, detail, now)


def log_activity(conn: sqlite3.Connection, loc_id: int, user_id, kind: str, detail: str = "",
                 at: str | None = None) -> None:
    conn.execute("INSERT INTO activity(user_id, location_id, kind, detail, created_at) VALUES(?,?,?,?,?)",
                 (user_id, loc_id, kind, detail, at or now_iso()))


def init_db() -> None:
    conn = connect()
    try:
        conn.executescript(HUB_SCHEMA)
        _migrate_hub(conn)
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
        # Project pertama: dari data lama (bila ada) atau kosong untuk instalasi baru.
        if not conn.execute("SELECT 1 FROM projects LIMIT 1").fetchone():
            pid = create_project(conn, "Project 1", "LOK", PROJECT_COLORS[0])
            p = conn.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
            if _has_table(conn, "locations"):
                _move_legacy_to_project(conn, p)
                conn.execute("UPDATE audit_log SET project_id=? WHERE project_id IS NULL "
                             "AND entity NOT IN ('user','data')", (pid,))
            # Semua user lama mendapat akses ke project pertama (perilaku sama seperti sebelumnya)
            conn.execute("INSERT OR IGNORE INTO project_members(project_id, user_id) "
                         "SELECT ?, id FROM users WHERE role <> 'admin'", (pid,))
            conn.commit()
        for p in conn.execute("SELECT * FROM projects").fetchall():
            _to_folder(conn, p)
            init_project_db(p)
            _relocate_files(p)
    finally:
        conn.close()
