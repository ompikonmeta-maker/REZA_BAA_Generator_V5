"""Konfigurasi & path terpusat.

Semua data disimpan di folder ``data/`` di samping executable / project root,
sehingga app portabel: cukup pindahkan folder, data ikut. Tanpa hak admin.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _base_dir() -> Path:
    """Root tempat folder ``data/`` diletakkan.

    - Saat dibundel PyInstaller: folder tempat ``app.exe`` berada.
    - Saat dev (python): root repository.
    Bisa dioverride lewat env ``REZA_BAA_HOME``.
    """
    override = os.environ.get("REZA_BAA_HOME")
    if override:
        return Path(override).resolve()
    if getattr(sys, "frozen", False):  # PyInstaller
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = _base_dir()
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "app.db"
OUTPUT_DIR = DATA_DIR / "output"       # hasil export sementara (bersama)
# Satu folder per project: projects/pN/{project.db, images/, templates/} (lihat db.project_dir)
PROJECTS_DIR = DATA_DIR / "projects"
# Lokasi lama (pra multi-project) — hanya dibaca saat migrasi ke folder project
TEMPLATES_DIR = DATA_DIR / "templates"
IMAGES_DIR = DATA_DIR / "images"

# Direktori aset frontend (dikemas bersama app)
WEB_DIR = Path(__file__).resolve().parent / "web"

# Server
HOST = os.environ.get("REZA_BAA_HOST", "0.0.0.0")  # 0.0.0.0 => bisa diakses di LAN
PORT = int(os.environ.get("REZA_BAA_PORT", "8000"))

# Sesi login
SESSION_COOKIE = "reza_baa_session"
SESSION_TTL_HOURS = int(os.environ.get("REZA_BAA_SESSION_TTL", "12"))

# Batas upload gambar (MB)
MAX_IMAGE_MB = int(os.environ.get("REZA_BAA_MAX_IMAGE_MB", "25"))
ALLOWED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}


def ensure_dirs() -> None:
    for d in (DATA_DIR, OUTPUT_DIR, PROJECTS_DIR):
        d.mkdir(parents=True, exist_ok=True)
