"""Backup & restore data (admin): unduh ZIP berisi DB + foto + template."""
from __future__ import annotations

import io
import sqlite3
import zipfile
from datetime import datetime
from pathlib import Path

import os
import time

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from fastapi.responses import StreamingResponse

from .. import config, db
from ..services import imgstore
from ..deps import audit, get_hub, require_admin

router = APIRouter(prefix="/api", tags=["backup"])

# Yang di-backup (relatif terhadap DATA_DIR)
_INCLUDE = ["app.db", "projects"]   # projects/pN/ = DB + foto + template per project


def _checkpoint(conn: sqlite3.Connection) -> None:
    """Tulis isi WAL ke file .db utama: salinan backup lengkap tanpa -wal/-shm,
    dan saat restore tidak ada WAL lama yang menimpa file hasil pulih."""
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    for p in conn.execute("SELECT * FROM projects").fetchall():
        pc = db.connect_project(p)
        try:
            pc.execute("PRAGMA main.wal_checkpoint(TRUNCATE)")
        finally:
            pc.close()


@router.get("/backup")
def backup(conn: sqlite3.Connection = Depends(get_hub), user=Depends(require_admin)):
    _checkpoint(conn)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in _INCLUDE:
            p = config.DATA_DIR / name
            if p.is_file():
                zf.write(p, name)
            elif p.is_dir():
                for f in p.rglob("*"):
                    if f.is_file() and not f.name.endswith(("-wal", "-shm")):
                        zf.write(f, str(f.relative_to(config.DATA_DIR)))
    buf.seek(0)
    audit(conn, user, "backup", "data")
    fname = f"baa_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    return StreamingResponse(buf, media_type="application/zip",
                             headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@router.post("/restore")
def restore(file: UploadFile = File(...), conn: sqlite3.Connection = Depends(get_hub),
            user=Depends(require_admin)):
    if not (file.filename or "").lower().endswith(".zip"):
        raise HTTPException(400, "Must be a backup .zip file")
    data = file.file.read()
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except Exception:
        raise HTTPException(400, "Invalid ZIP")
    # Validasi: hanya path aman di dalam DATA_DIR
    names = zf.namelist()
    if not any(n == "app.db" or n.startswith(("projects/", "images/", "templates/")) for n in names):
        raise HTTPException(400, "Unknown ZIP content (use a file from Backup)")
    for n in names:
        dest = (config.DATA_DIR / n).resolve()
        if not str(dest).startswith(str(config.DATA_DIR.resolve())):
            raise HTTPException(400, "Unsafe path inside the ZIP")
    _checkpoint(conn)
    zf.extractall(config.DATA_DIR)
    audit(conn, user, "restore", "data", detail=file.filename or "")
    return {"ok": True, "restart": True,
            "msg": "Data dipulihkan. Tutup lalu jalankan ulang aplikasi agar semua data termuat."}


# ---- Kompres foto lama (sekali jalan, bertahap per panggilan agar tidak timeout) ----
@router.get("/photos/storage")
def photo_storage(hub: sqlite3.Connection = Depends(get_hub), user=Depends(require_admin)):
    """Jumlah & total ukuran foto di semua project."""
    n = size = 0
    for p in hub.execute("SELECT * FROM projects ORDER BY id").fetchall():
        d = db.project_dir(p) / "images"
        if d.is_dir():
            for f in d.rglob("*"):
                if f.is_file():
                    n += 1
                    size += f.stat().st_size
    return {"photos": n, "bytes": size}


class CompressIn(BaseModel):
    cursor: str = ""        # "projectId:photoId" terakhir yang sudah diperiksa
    limit: int = 30


@router.post("/photos/compress-all")
def compress_all(body: CompressIn, hub: sqlite3.Connection = Depends(get_hub), user=Depends(require_admin)):
    try:
        pid0, ph0 = (int(x) for x in (body.cursor or "0:0").split(":"))
    except ValueError:
        pid0, ph0 = 0, 0
    checked = changed = saved = 0
    t0, cursor = time.monotonic(), f"{pid0}:{ph0}"
    for p in hub.execute("SELECT * FROM projects WHERE id>=? ORDER BY id", (pid0,)).fetchall():
        pc = db.connect_project(p)
        try:
            start = ph0 if p["id"] == pid0 else 0
            for r in pc.execute("SELECT id,path FROM photos WHERE id>? ORDER BY id", (start,)).fetchall():
                if checked >= max(1, min(body.limit, 100)) or time.monotonic() - t0 > 8:
                    return {"done": False, "cursor": cursor, "checked": checked, "changed": changed, "saved": saved}
                checked += 1
                cursor = f"{p['id']}:{r['id']}"
                src = db.fpath(pc, r["path"])
                if not src.is_file() or not imgstore.needs_check(src):
                    continue
                data = src.read_bytes()
                small = imgstore.compress(data)
                if not small:
                    continue
                nb, ext = small
                dst = src.with_suffix(ext)
                tmp = dst.with_name(dst.name + ".tmp")
                tmp.write_bytes(nb)
                os.replace(tmp, dst)
                if dst != src:
                    pc.execute("UPDATE photos SET filename=?, path=? WHERE id=?", (dst.name, db.rel_path(pc, dst), r["id"]))
                    pc.commit()
                    src.unlink(missing_ok=True)
                changed += 1
                saved += len(data) - len(nb)
        finally:
            pc.close()
    audit(hub, user, "compress", "photos", "", "done")
    return {"done": True, "cursor": cursor, "checked": checked, "changed": changed, "saved": saved}
