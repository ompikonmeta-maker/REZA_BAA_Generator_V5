"""Backup & restore data (admin): unduh ZIP berisi DB + foto + template."""
from __future__ import annotations

import io
import sqlite3
import zipfile
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from .. import config
from ..deps import audit, get_db, require_admin

router = APIRouter(prefix="/api", tags=["backup"])

# Yang di-backup (relatif terhadap DATA_DIR)
_INCLUDE = ["app.db", "images", "templates"]


@router.get("/backup")
def backup(conn: sqlite3.Connection = Depends(get_db), user=Depends(require_admin)):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in _INCLUDE:
            p = config.DATA_DIR / name
            if p.is_file():
                zf.write(p, name)
            elif p.is_dir():
                for f in p.rglob("*"):
                    if f.is_file():
                        zf.write(f, str(f.relative_to(config.DATA_DIR)))
    buf.seek(0)
    audit(conn, user, "backup", "data")
    fname = f"baa_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    return StreamingResponse(buf, media_type="application/zip",
                             headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@router.post("/restore")
def restore(file: UploadFile = File(...), conn: sqlite3.Connection = Depends(get_db),
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
    if not any(n == "app.db" or n.startswith(("images/", "templates/")) for n in names):
        raise HTTPException(400, "Unknown ZIP content (use a file from Backup)")
    for n in names:
        dest = (config.DATA_DIR / n).resolve()
        if not str(dest).startswith(str(config.DATA_DIR.resolve())):
            raise HTTPException(400, "Unsafe path inside the ZIP")
    zf.extractall(config.DATA_DIR)
    audit(conn, user, "restore", "data", detail=file.filename or "")
    return {"ok": True, "restart": True,
            "msg": "Data dipulihkan. Tutup lalu jalankan ulang aplikasi agar semua data termuat."}
