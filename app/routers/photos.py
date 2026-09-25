"""Upload foto: auto-sort by nama file/folder + auto-OCR untuk slot SN.

Selalu ada opsi upload manual per kategori (parameter ``category``).
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path

from fastapi import (APIRouter, Depends, File, Form, HTTPException, UploadFile)
from fastapi.responses import FileResponse

from .. import config, db
from ..deps import audit, current_user, get_db, loc_access, require_editor
from ..services import autosort, ocr

router = APIRouter(prefix="/api", tags=["photos"])


def _guard_photo(conn, user, photo_row, *, write: bool):
    """Batasi akses foto sesuai kepemilikan lokasinya (operator hanya miliknya)."""
    loc = conn.execute("SELECT owner_id FROM locations WHERE id=?", (photo_row["location_id"],)).fetchone()
    owner = loc["owner_id"] if loc else None
    if not loc_access(user, owner, write=write):
        raise HTTPException(403 if write else 404, "Tidak diizinkan" if write else "Foto tidak ditemukan")


def _safe_ext(name: str) -> str:
    ext = Path(name).suffix.lower()
    return ext if ext in config.ALLOWED_IMAGE_EXT else ""


@router.post("/locations/{loc_id}/photos")
def upload_photos(
    loc_id: int,
    files: list[UploadFile] = File(...),
    category: str = Form(default=""),          # jika diisi -> paksa ke kategori ini (upload manual per-slot)
    relpaths: str = Form(default="[]"),        # opsional: path relatif per file (untuk deteksi subfolder)
    conn: sqlite3.Connection = Depends(get_db),
    user=Depends(require_editor),
):
    loc = conn.execute("SELECT * FROM locations WHERE id=? AND deleted_at IS NULL", (loc_id,)).fetchone()
    if not loc:
        raise HTTPException(404, "Lokasi tidak ditemukan")
    if not loc_access(user, loc["owner_id"], write=True):
        raise HTTPException(403, "Bukan pekerjaan Anda")

    categories = db.get_setting(conn, "photo_categories", [])
    try:
        paths = json.loads(relpaths) if relpaths else []
    except Exception:
        paths = []

    dest_dir = config.IMAGES_DIR / loc["code"]
    dest_dir.mkdir(parents=True, exist_ok=True)

    results = []
    batch_used: set[str] = set()          # kategori yg sudah terisi oleh file lain di batch ini
    for idx, up in enumerate(files):
        ext = _safe_ext(up.filename or "")
        if not ext:
            results.append({"orig_name": up.filename, "error": "format tidak didukung"})
            continue
        data = up.file.read()
        if len(data) > config.MAX_IMAGE_MB * 1024 * 1024:
            results.append({"orig_name": up.filename, "error": "file terlalu besar"})
            continue

        rel = paths[idx] if idx < len(paths) else (up.filename or "")
        folder = str(Path(rel).parent) if rel else ""

        if category:
            cat_key, matched_by = category, "manual"
        else:
            cat_key, matched_by = autosort.match_category(up.filename or "", categories, folder)
            # Cegah kehilangan diam-diam: bila kategori (auto) sudah dipakai file
            # lain dalam batch yang sama, jangan menimpa — alihkan ke
            # "uncategorized" agar foto tetap tampil & bisa dipindah manual.
            if cat_key and cat_key != "uncategorized" and cat_key in batch_used:
                cat_key, matched_by = "uncategorized", "batch-dup"
            elif cat_key and cat_key != "uncategorized":
                batch_used.add(cat_key)

        fname = f"{uuid.uuid4().hex}{ext}"
        fpath = dest_dir / fname
        fpath.write_bytes(data)

        ocr_serial, ocr_text = "", ""
        if autosort.category_needs_ocr(cat_key, categories):
            ocr_serial, ocr_text = ocr.read_serial(fpath)

        # Satu kategori = maksimal satu foto: buang foto lama di kategori yang
        # sama (kecuali "uncategorized" yang boleh menampung banyak).
        if cat_key and cat_key != "uncategorized":
            for old in conn.execute(
                "SELECT id,path FROM photos WHERE location_id=? AND category=?",
                (loc_id, cat_key),
            ).fetchall():
                try:
                    Path(old["path"]).unlink(missing_ok=True)
                except Exception:
                    pass
                conn.execute("DELETE FROM photos WHERE id=?", (old["id"],))

        cur = conn.execute(
            "INSERT INTO photos(location_id,category,orig_name,filename,path,ocr_text,"
            "ocr_serial,matched_by,uploaded_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (loc_id, cat_key, up.filename or fname, fname, str(fpath), ocr_text,
             ocr_serial, matched_by, user["id"], db.now_iso()),
        )
        results.append({
            "id": cur.lastrowid, "orig_name": up.filename, "category": cat_key,
            "matched_by": matched_by, "ocr_serial": ocr_serial,
        })

    conn.execute("UPDATE locations SET updated_at=? WHERE id=?", (db.now_iso(), loc_id))
    conn.commit()
    audit(conn, user, "upload_photos", "location", loc_id, f"{len(results)} file")
    return {"ok": True, "results": results, "ocr_available": ocr.available()}


@router.patch("/photos/{photo_id}")
def reassign_photo(photo_id: int, payload: dict, conn: sqlite3.Connection = Depends(get_db),
                   user=Depends(require_editor)):
    """Pindahkan foto ke kategori lain (drag manual). Re-OCR bila perlu."""
    row = conn.execute("SELECT * FROM photos WHERE id=?", (photo_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Foto tidak ditemukan")
    _guard_photo(conn, user, row, write=True)
    # Set serial manual (dari barcode/OCR area/edit) tanpa memindah kategori
    if "ocr_serial" in payload and "category" not in payload:
        conn.execute("UPDATE photos SET ocr_serial=? WHERE id=?",
                     (str(payload.get("ocr_serial", "")), photo_id))
        conn.commit()
        audit(conn, user, "set_serial", "photo", photo_id, str(payload.get("ocr_serial", "")))
        return {"ok": True, "ocr_serial": str(payload.get("ocr_serial", ""))}
    new_cat = str(payload.get("category", "")).strip()
    if not new_cat:
        raise HTTPException(400, "category wajib diisi")
    categories = db.get_setting(conn, "photo_categories", [])
    ocr_serial, ocr_text = row["ocr_serial"], row["ocr_text"]
    if autosort.category_needs_ocr(new_cat, categories) and not ocr_serial:
        ocr_serial, ocr_text = ocr.read_serial(row["path"])
    conn.execute(
        "UPDATE photos SET category=?,matched_by='manual',ocr_serial=?,ocr_text=? WHERE id=?",
        (new_cat, ocr_serial, ocr_text, photo_id),
    )
    conn.commit()
    audit(conn, user, "reassign_photo", "photo", photo_id, new_cat)
    return {"ok": True, "category": new_cat, "ocr_serial": ocr_serial}


@router.post("/photos/{photo_id}/reocr")
def reocr_photo(photo_id: int, conn: sqlite3.Connection = Depends(get_db),
                user=Depends(require_editor)):
    row = conn.execute("SELECT * FROM photos WHERE id=?", (photo_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Foto tidak ditemukan")
    _guard_photo(conn, user, row, write=True)
    serial, text = ocr.read_serial(row["path"])
    conn.execute("UPDATE photos SET ocr_serial=?,ocr_text=? WHERE id=?", (serial, text, photo_id))
    conn.commit()
    return {"ok": True, "ocr_serial": serial, "ocr_available": ocr.available()}


@router.get("/photos/{photo_id}/file")
def photo_file(photo_id: int, conn: sqlite3.Connection = Depends(get_db),
               user=Depends(current_user)):
    row = conn.execute("SELECT * FROM photos WHERE id=?", (photo_id,)).fetchone()
    if not row or not Path(row["path"]).exists():
        raise HTTPException(404, "File tidak ditemukan")
    _guard_photo(conn, user, row, write=False)
    return FileResponse(row["path"])


@router.delete("/photos/{photo_id}")
def delete_photo(photo_id: int, conn: sqlite3.Connection = Depends(get_db),
                 user=Depends(require_editor)):
    row = conn.execute("SELECT * FROM photos WHERE id=?", (photo_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Foto tidak ditemukan")
    _guard_photo(conn, user, row, write=True)
    try:
        Path(row["path"]).unlink(missing_ok=True)
    except Exception:
        pass
    conn.execute("DELETE FROM photos WHERE id=?", (photo_id,))
    conn.commit()
    audit(conn, user, "delete_photo", "photo", photo_id)
    return {"ok": True}
