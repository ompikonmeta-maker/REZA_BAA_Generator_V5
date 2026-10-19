"""Lampiran tambahan per lokasi (opsional, banyak file).

Selalu disimpan sebagai PDF (gambar dikonversi saat upload) supaya bisa ikut
PDF gabungan. Letak per file: 'before' / 'after' Dokumen BAA (scan bertanda
tangan + BAA hasil generate); urutan dalam satu letak = urutan upload.
Jenis file & batas ukuran diatur di setting 'attach_config'.
"""
from __future__ import annotations

import io
import sqlite3
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .. import db
from ..deps import audit, current_user, get_db, require_editor
from ..services import pdfdoc
from .scan import _loc

router = APIRouter(prefix="/api/locations", tags=["attachments"])

POSITIONS = ("before", "after")
# Jenis yang bisa digabung ke PDF: pdf apa adanya, gambar dikonversi ke PDF
SUPPORTED = {"pdf", "jpg", "jpeg", "png"}


def attachment_list(conn, loc_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT a.*, COALESCE(NULLIF(TRIM(u.full_name),''), u.username) AS by_name "
        "FROM attachments a LEFT JOIN users u ON u.id=a.uploaded_by WHERE a.location_id=? "
        "ORDER BY a.position='after', a.sort_order, a.id", (loc_id,)).fetchall()
    return [{"id": r["id"], "orig_name": r["orig_name"], "pages": r["pages"], "size": r["size"],
             "position": r["position"], "by": r["by_name"], "created_at": r["created_at"]} for r in rows]


def attachment_paths(conn, loc_id: int) -> dict[str, list]:
    """{'before': [Path..], 'after': [Path..]} untuk PDF gabungan (file hilang dilewati)."""
    out: dict[str, list] = {"before": [], "after": []}
    for r in conn.execute("SELECT path, position FROM attachments WHERE location_id=? "
                          "ORDER BY sort_order, id", (loc_id,)):
        p = db.fpath(conn, r["path"])
        if p.exists():
            out["after" if r["position"] != "before" else "before"].append(p)
    return out


def _types(cfg) -> list[str]:
    return [t for t in (str(x).lower().lstrip(".") for x in cfg.get("types") or ["pdf"]) if t in SUPPORTED] or ["pdf"]


def _to_pdf(data: bytes, ext: str) -> bytes:
    if ext == "pdf":
        if not data.startswith(b"%PDF"):
            raise HTTPException(400, "Not a valid PDF file")
        return data
    from PIL import Image
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
    except Exception:
        raise HTTPException(400, "Can't read the image")
    buf = io.BytesIO()
    im.convert("RGB").save(buf, "PDF", resolution=150)
    return buf.getvalue()


def _next_order(conn, loc_id: int, position: str) -> int:
    return conn.execute("SELECT COALESCE(MAX(sort_order),0)+1 FROM attachments WHERE location_id=? AND position=?",
                        (loc_id, position)).fetchone()[0]


@router.post("/{loc_id}/attachments")
def upload_attachment(loc_id: int, file: UploadFile = File(...), position: str = Form("after"),
                      conn: sqlite3.Connection = Depends(get_db), user=Depends(require_editor)):
    cfg = db.attach_config(conn)
    if not cfg.get("enabled", True):
        raise HTTPException(400, f"{cfg['label']} are turned off for this project")
    if position not in POSITIONS:
        raise HTTPException(400, "Position must be 'before' or 'after'")
    loc = _loc(conn, loc_id, user, write=True)
    from .locations import require_activation
    require_activation(conn, loc["data_json"])
    name = (file.filename or "").replace("\\", "/").split("/")[-1]
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    types = _types(cfg)
    if ext not in types:
        raise HTTPException(400, "Allowed file types: " + ", ".join("." + t for t in types))
    max_mb = float(cfg.get("max_mb") or 5)
    data = file.file.read()
    if len(data) > max_mb * 1024 * 1024:
        raise HTTPException(400, f"File is larger than {max_mb:g} MB")
    pdf = _to_pdf(data, ext)
    dest_dir = db.docs_dir(conn) / loc["code"]
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"att_{uuid.uuid4().hex}.pdf"
    dest.write_bytes(pdf)
    try:
        pages = pdfdoc.page_count(dest)
    except ValueError as e:
        dest.unlink(missing_ok=True)
        raise HTTPException(400, str(e))
    conn.execute(
        "INSERT INTO attachments(location_id, orig_name, path, pages, size, position, sort_order, uploaded_by, created_at) "
        "VALUES(?,?,?,?,?,?,?,?,?)",
        (loc_id, name, db.rel_path(conn, dest), pages, len(data), position, _next_order(conn, loc_id, position),
         user["id"], db.now_iso()))
    db.touch_modified(conn, loc_id, user["id"], "att_add", name)
    conn.commit()
    audit(conn, user, "upload_attachment", "location", loc_id, f"{name} ({pages} p, {position})")
    return {"ok": True, "attachments": attachment_list(conn, loc_id)}


def _att(conn, loc_id: int, att_id: int):
    r = conn.execute("SELECT * FROM attachments WHERE id=? AND location_id=?", (att_id, loc_id)).fetchone()
    if not r:
        raise HTTPException(404, "Attachment not found")
    return r


class AttachmentPatch(BaseModel):
    position: str


@router.patch("/{loc_id}/attachments/{att_id}")
def move_attachment(loc_id: int, att_id: int, body: AttachmentPatch, conn: sqlite3.Connection = Depends(get_db),
                    user=Depends(require_editor)):
    if body.position not in POSITIONS:
        raise HTTPException(400, "Position must be 'before' or 'after'")
    _loc(conn, loc_id, user, write=True)
    r = _att(conn, loc_id, att_id)
    if r["position"] != body.position:
        # pindah letak -> taruh di akhir letak tujuan
        conn.execute("UPDATE attachments SET position=?, sort_order=? WHERE id=?",
                     (body.position, _next_order(conn, loc_id, body.position), att_id))
        db.touch_modified(conn, loc_id, user["id"], "att_move", f"{r['orig_name']} → {body.position}")
        conn.commit()
    return {"ok": True, "attachments": attachment_list(conn, loc_id)}


@router.delete("/{loc_id}/attachments/{att_id}")
def delete_attachment(loc_id: int, att_id: int, conn: sqlite3.Connection = Depends(get_db),
                      user=Depends(require_editor)):
    _loc(conn, loc_id, user, write=True)
    r = _att(conn, loc_id, att_id)
    db.fpath(conn, r["path"]).unlink(missing_ok=True)
    conn.execute("DELETE FROM attachments WHERE id=?", (att_id,))
    db.touch_modified(conn, loc_id, user["id"], "att_del", r["orig_name"])
    conn.commit()
    audit(conn, user, "delete_attachment", "location", loc_id, r["orig_name"])
    return {"ok": True, "attachments": attachment_list(conn, loc_id)}


@router.get("/{loc_id}/attachments/{att_id}/file")
def attachment_file(loc_id: int, att_id: int, conn: sqlite3.Connection = Depends(get_db),
                    user=Depends(current_user)):
    _loc(conn, loc_id, user, write=False)
    r = _att(conn, loc_id, att_id)
    p = db.fpath(conn, r["path"])
    if not p.exists():
        raise HTTPException(404, "Attachment file not found")
    name = r["orig_name"] or "attachment.pdf"
    if not name.lower().endswith(".pdf"):
        name = name.rsplit(".", 1)[0] + ".pdf"
    return FileResponse(p, media_type="application/pdf", filename=name,
                        content_disposition_type="inline", headers={"Cache-Control": "private, no-cache"})
