"""Permintaan edit lokasi (edit_requests) + notifikasi admin.

Alur: operator yang BUKAN pemilik sebuah lokasi menekan "Request edit" di drawer
Log Lokasi -> baris pending masuk ke sini. Admin melihatnya di menu Notifikasi dan
bisa MENYETUJUI (kepemilikan lokasi dialihkan ke peminta) atau MENOLAK.
"""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import db
from ..deps import audit, current_user, get_db, require_admin, require_editor

router = APIRouter(prefix="/api/edit-requests", tags=["edit-requests"])


class RequestIn(BaseModel):
    location_id: int
    message: str = ""


def _row(conn: sqlite3.Connection, rid: int):
    return conn.execute(
        """SELECT r.*, l.code AS loc_code, l.name AS loc_name, l.data_json AS loc_data,
                  l.deleted_at AS loc_deleted,
                  COALESCE(NULLIF(TRIM(rq.full_name),''), rq.username) AS requester_name,
                  COALESCE(NULLIF(TRIM(ow.full_name),''), ow.username) AS owner_name
           FROM edit_requests r
                LEFT JOIN locations l ON l.id = r.location_id
                LEFT JOIN users rq ON rq.id = r.requester_id
                LEFT JOIN users ow ON ow.id = r.owner_id
           WHERE r.id=?""",
        (rid,),
    ).fetchone()


def _serialize(r) -> dict:
    import json
    nama = r["loc_name"] or ""
    if not nama:
        try:
            nama = (json.loads(r["loc_data"] or "{}") or {}).get("nama_lokasi", "") or ""
        except Exception:
            nama = ""
    return {
        "id": r["id"], "location_id": r["location_id"], "loc_code": r["loc_code"],
        "loc_name": nama, "requester_id": r["requester_id"], "requester_name": r["requester_name"],
        "owner_name": r["owner_name"], "message": r["message"] or "", "status": r["status"],
        "created_at": r["created_at"], "resolved_at": r["resolved_at"],
    }


@router.post("")
def create_request(body: RequestIn, conn: sqlite3.Connection = Depends(get_db),
                   user=Depends(require_editor)):
    loc = conn.execute("SELECT id, code, owner_id FROM locations WHERE id=? AND deleted_at IS NULL",
                       (body.location_id,)).fetchone()
    if not loc:
        raise HTTPException(404, "Location not found")
    if loc["owner_id"] == user["id"]:
        raise HTTPException(400, "You already own this location")
    # Dedupe: satu permintaan pending per (lokasi, peminta)
    dup = conn.execute(
        "SELECT id FROM edit_requests WHERE location_id=? AND requester_id=? AND status='pending'",
        (body.location_id, user["id"]),
    ).fetchone()
    if dup:
        return {"ok": True, "id": dup["id"], "status": "pending", "duplicate": True}
    now = db.now_iso()
    cur = conn.execute(
        "INSERT INTO edit_requests(location_id,requester_id,owner_id,message,status,created_at) "
        "VALUES(?,?,?,?,'pending',?)",
        (body.location_id, user["id"], loc["owner_id"], (body.message or "").strip(), now),
    )
    conn.commit()
    audit(conn, user, "edit_request", "location", body.location_id, loc["code"])
    return {"ok": True, "id": cur.lastrowid, "status": "pending"}


@router.get("")
def list_requests(status: str = "pending", conn: sqlite3.Connection = Depends(get_db),
                  user=Depends(require_admin)):
    where = "" if status == "all" else "WHERE r.status=?"
    params: list = [] if status == "all" else [status]
    rows = conn.execute(
        f"""SELECT r.id FROM edit_requests r {where}
            ORDER BY (r.status='pending') DESC, r.id DESC LIMIT 200""", params
    ).fetchall()
    out = [_serialize(_row(conn, r["id"])) for r in rows]
    return {"rows": out, "total": len(out)}


@router.get("/pending-count")
def pending_count(conn: sqlite3.Connection = Depends(get_db), user=Depends(require_admin)):
    n = conn.execute("SELECT COUNT(*) c FROM edit_requests WHERE status='pending'").fetchone()["c"]
    return {"count": n}


@router.get("/mine")
def my_requests(conn: sqlite3.Connection = Depends(get_db), user=Depends(current_user)):
    """Status permintaan milik user aktif (untuk menandai drawer)."""
    rows = conn.execute(
        "SELECT location_id, status FROM edit_requests WHERE requester_id=? AND status='pending'",
        (user["id"],),
    ).fetchall()
    return {"pending": [r["location_id"] for r in rows]}


@router.post("/{rid}/approve")
def approve_request(rid: int, conn: sqlite3.Connection = Depends(get_db),
                    user=Depends(require_admin)):
    r = _row(conn, rid)
    if not r:
        raise HTTPException(404, "Request not found")
    if r["status"] != "pending":
        raise HTTPException(400, "Request already handled")
    if r["loc_deleted"] is not None:
        raise HTTPException(400, "Location was deleted")
    tgt = conn.execute("SELECT id, active, role FROM pm_users WHERE id=?", (r["requester_id"],)).fetchone()
    if not tgt or not tgt["active"]:
        raise HTTPException(400, "Requester is inactive")
    now = db.now_iso()
    # Setujui = alihkan kepemilikan lokasi ke peminta
    conn.execute("UPDATE locations SET owner_id=?, updated_at=? WHERE id=?",
                 (r["requester_id"], now, r["location_id"]))
    conn.execute("UPDATE edit_requests SET status='approved', resolved_at=?, resolved_by=? WHERE id=?",
                 (now, user["id"], rid))
    # Batalkan permintaan pending lain untuk lokasi yang sama (sudah tak relevan)
    conn.execute("UPDATE edit_requests SET status='rejected', resolved_at=?, resolved_by=? "
                 "WHERE location_id=? AND status='pending' AND id<>?",
                 (now, user["id"], r["location_id"], rid))
    conn.commit()
    audit(conn, user, "edit_request_approve", "location", r["location_id"],
          f"{r['loc_code']} -> {r['requester_name']}")
    return {"ok": True, "to": {"id": r["requester_id"], "name": r["requester_name"]}}


@router.post("/{rid}/reject")
def reject_request(rid: int, conn: sqlite3.Connection = Depends(get_db),
                   user=Depends(require_admin)):
    r = _row(conn, rid)
    if not r:
        raise HTTPException(404, "Request not found")
    if r["status"] != "pending":
        raise HTTPException(400, "Request already handled")
    conn.execute("UPDATE edit_requests SET status='rejected', resolved_at=?, resolved_by=? WHERE id=?",
                 (db.now_iso(), user["id"], rid))
    conn.commit()
    audit(conn, user, "edit_request_reject", "location", r["location_id"], r["loc_code"])
    return {"ok": True}
