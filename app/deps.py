"""Dependency FastAPI: koneksi DB per-request, user aktif, guard role, audit."""
from __future__ import annotations

import sqlite3
from typing import Optional

from fastapi import Cookie, Depends, HTTPException, status

from . import auth, config, db


def get_db():
    conn = db.connect()
    try:
        yield conn
    finally:
        conn.close()


def current_user(
    conn: sqlite3.Connection = Depends(get_db),
    reza_baa_session: Optional[str] = Cookie(default=None),
):
    user = auth.get_session_user(conn, reza_baa_session)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Belum login")
    return user


def require_admin(user=Depends(current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Butuh hak admin")
    return user


def require_editor(user=Depends(current_user)):
    """Boleh menulis (buat/ubah/hapus data entry): admin & operator.

    Viewer (mode bos) hanya boleh melihat — semua endpoint tulis memakai guard
    ini agar viewer ditolak di sisi server, bukan sekadar disembunyikan di UI.
    """
    if user["role"] not in ("admin", "operator"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Akun ini hanya bisa melihat (viewer)")
    return user


def loc_access(user, owner_id, *, write: bool) -> bool:
    """Aturan kepemilikan lokasi. admin: selalu. viewer: baca semua (tulis sudah
    ditolak require_editor). operator: hanya lokasi miliknya (owner_id)."""
    if user["role"] == "admin":
        return True
    if user["role"] == "operator":
        return owner_id == user["id"]
    # viewer: hanya baca
    return not write


def audit(conn: sqlite3.Connection, user, action: str, entity: str = "", entity_id="", detail: str = ""):
    conn.execute(
        "INSERT INTO audit_log(user_id, username, action, entity, entity_id, detail, created_at) "
        "VALUES(?,?,?,?,?,?,?)",
        (
            user["id"] if user else None,
            user["username"] if user else "",
            action,
            entity,
            str(entity_id),
            detail,
            db.now_iso(),
        ),
    )
    conn.commit()
