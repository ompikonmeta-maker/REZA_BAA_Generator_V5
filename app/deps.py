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
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not signed in")
    _touch_seen(conn, user)
    return user


def _touch_seen(conn: sqlite3.Connection, user) -> None:
    """Last seen: catat waktu permintaan terakhir (maks. sekali per menit)."""
    from datetime import datetime, timezone
    try:
        last = user["last_seen_at"] if "last_seen_at" in user.keys() else None
        now = datetime.now(timezone.utc)
        if last and (now - datetime.fromisoformat(last)).total_seconds() < 60:
            return
        conn.execute("UPDATE users SET last_seen_at=? WHERE id=?", (now.isoformat(), user["id"]))
        conn.commit()
    except Exception:
        pass


def require_admin(user=Depends(current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    return user


def require_editor(user=Depends(current_user)):
    """Boleh menulis (buat/ubah/hapus data entry): admin & operator.

    Viewer (mode bos) hanya boleh melihat — semua endpoint tulis memakai guard
    ini agar viewer ditolak di sisi server, bukan sekadar disembunyikan di UI.
    """
    if user["role"] not in ("admin", "operator"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="This account is view-only")
    return user


def loc_access(user, owner_id, *, write: bool) -> bool:
    """Aturan akses lokasi.
    - Baca: SEMUA user boleh melihat lokasi siapa pun.
    - Tulis: admin selalu; operator hanya miliknya; viewer tidak pernah."""
    if not write:
        return True
    if user["role"] == "admin":
        return True
    if user["role"] == "operator":
        return owner_id == user["id"]
    return False


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
