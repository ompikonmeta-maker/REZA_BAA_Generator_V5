"""Lonceng notifikasi per user (admin & operator).

Contoh: lokasi milik operator menjadi online menurut Google Sheet (tanggal terpasang) saat dokumen
BAA belum lengkap, atau auto-check Google Sheet gagal (ke admin). Permintaan edit (admin) tetap di
/api/edit-requests; frontend menggabungkan hitungannya di lonceng.
"""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends

from .. import db
from ..deps import current_user, get_db

router = APIRouter(prefix="/api/notices", tags=["notices"])


@router.get("")
def my_notices(conn: sqlite3.Connection = Depends(get_db), user=Depends(current_user)):
    rows = conn.execute(
        """SELECT n.id, n.kind, n.location_id, n.text, n.created_at, n.read_at, l.code, l.name
           FROM notices n LEFT JOIN locations l ON l.id = n.location_id AND l.deleted_at IS NULL
           WHERE n.user_id=? ORDER BY n.id DESC LIMIT 60""", (user["id"],)).fetchall()
    unread = conn.execute("SELECT COUNT(*) FROM notices WHERE user_id=? AND read_at IS NULL", (user["id"],)).fetchone()[0]
    return {"rows": [dict(r) for r in rows], "unread": unread}


@router.get("/count")
def notice_count(conn: sqlite3.Connection = Depends(get_db), user=Depends(current_user)):
    return {"unread": conn.execute("SELECT COUNT(*) FROM notices WHERE user_id=? AND read_at IS NULL",
                                   (user["id"],)).fetchone()[0]}


@router.post("/read")
def mark_read(conn: sqlite3.Connection = Depends(get_db), user=Depends(current_user)):
    conn.execute("UPDATE notices SET read_at=? WHERE user_id=? AND read_at IS NULL", (db.now_iso(), user["id"]))
    conn.commit()
    return {"ok": True}
