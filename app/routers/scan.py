"""Dokumen scan PDF per lokasi (wajib; halaman pertama saat export PDF).

Satu file per lokasi, upload ulang = ganti. Kekurangan scan hanya ditandai
(kelengkapan), tidak memblok status Done maupun export.
"""
from __future__ import annotations

import sqlite3
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response

from .. import config, db
from ..deps import audit, current_user, get_db, loc_access, require_editor
from ..services import pdfdoc

router = APIRouter(prefix="/api/locations", tags=["scan"])


def _loc(conn, loc_id: int, user, *, write: bool):
    loc = conn.execute("SELECT * FROM locations WHERE id=? AND deleted_at IS NULL", (loc_id,)).fetchone()
    if not loc:
        raise HTTPException(404, "Location not found")
    if not loc_access(user, loc["owner_id"], write=write):
        raise HTTPException(403, "Not your location")
    return loc


def scan_info(conn, loc_id: int) -> dict | None:
    r = conn.execute(
        "SELECT s.*, COALESCE(NULLIF(TRIM(u.full_name),''), u.username) AS by_name "
        "FROM scan_docs s LEFT JOIN users u ON u.id=s.uploaded_by WHERE s.location_id=?", (loc_id,)).fetchone()
    if not r:
        return None
    return {"orig_name": r["orig_name"], "pages": r["pages"], "size": r["size"],
            "by": r["by_name"], "created_at": r["created_at"]}


def _remove_file(conn, loc_id: int) -> None:
    r = conn.execute("SELECT path FROM scan_docs WHERE location_id=?", (loc_id,)).fetchone()
    if r:
        db.fpath(conn, r["path"]).unlink(missing_ok=True)


@router.post("/{loc_id}/scan")
def upload_scan(loc_id: int, file: UploadFile = File(...), conn: sqlite3.Connection = Depends(get_db),
                user=Depends(require_editor)):
    loc = _loc(conn, loc_id, user, write=True)
    name = (file.filename or "").replace("\\", "/").split("/")[-1]
    if not name.lower().endswith(".pdf"):
        raise HTTPException(400, "Scan must be a .pdf file")
    data = file.file.read()
    if len(data) > config.MAX_IMAGE_MB * 1024 * 1024:
        raise HTTPException(400, f"PDF is larger than {config.MAX_IMAGE_MB} MB")
    if not data.startswith(b"%PDF"):
        raise HTTPException(400, "Not a valid PDF file")
    dest_dir = db.docs_dir(conn) / loc["code"]
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"scan_{uuid.uuid4().hex}.pdf"
    dest.write_bytes(data)
    try:
        pages = pdfdoc.page_count(dest)
    except ValueError as e:
        dest.unlink(missing_ok=True)
        raise HTTPException(400, str(e))
    _remove_file(conn, loc_id)
    conn.execute(
        "INSERT INTO scan_docs(location_id, orig_name, path, pages, size, uploaded_by, created_at) "
        "VALUES(?,?,?,?,?,?,?) ON CONFLICT(location_id) DO UPDATE SET orig_name=excluded.orig_name, "
        "path=excluded.path, pages=excluded.pages, size=excluded.size, uploaded_by=excluded.uploaded_by, "
        "created_at=excluded.created_at",
        (loc_id, name, db.rel_path(conn, dest), pages, len(data), user["id"], db.now_iso()))
    db.touch_modified(conn, loc_id, user["id"], "scan_add", name)
    conn.commit()
    audit(conn, user, "upload_scan", "location", loc_id, f"{name} ({pages} p)")
    return {"ok": True, "scan": scan_info(conn, loc_id)}


@router.delete("/{loc_id}/scan")
def delete_scan(loc_id: int, conn: sqlite3.Connection = Depends(get_db), user=Depends(require_editor)):
    _loc(conn, loc_id, user, write=True)
    _remove_file(conn, loc_id)
    conn.execute("DELETE FROM scan_docs WHERE location_id=?", (loc_id,))
    db.touch_modified(conn, loc_id, user["id"], "scan_del")
    conn.commit()
    audit(conn, user, "delete_scan", "location", loc_id)
    return {"ok": True}


def _scan_path(conn, loc_id: int, user):
    _loc(conn, loc_id, user, write=False)
    r = conn.execute("SELECT * FROM scan_docs WHERE location_id=?", (loc_id,)).fetchone()
    p = db.fpath(conn, r["path"]) if r else None
    if not p or not p.exists():
        raise HTTPException(404, "Scan PDF not found")
    return r, p


@router.get("/{loc_id}/scan/file")
def scan_file(loc_id: int, conn: sqlite3.Connection = Depends(get_db), user=Depends(current_user)):
    r, p = _scan_path(conn, loc_id, user)
    # inline: dibuka di tab browser; id lokasi sama antar project -> selalu validasi ulang
    return FileResponse(p, media_type="application/pdf", filename=r["orig_name"] or "scan.pdf",
                        content_disposition_type="inline", headers={"Cache-Control": "private, no-cache"})


@router.get("/{loc_id}/scan/thumb")
def scan_thumb(loc_id: int, conn: sqlite3.Connection = Depends(get_db), user=Depends(current_user)):
    _, p = _scan_path(conn, loc_id, user)
    jpg = pdfdoc.first_page_thumb(p)
    if not jpg:
        raise HTTPException(404, "No preview")
    return Response(jpg, media_type="image/jpeg", headers={"Cache-Control": "private, no-cache"})
