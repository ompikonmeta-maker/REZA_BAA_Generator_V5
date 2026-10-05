"""Dependency FastAPI: koneksi DB per-request, user aktif, guard role, audit."""
from __future__ import annotations

import sqlite3
from typing import Optional

from fastapi import Cookie, Depends, HTTPException, Request, status

from . import auth, config, db

PROJECT_HEADER = "X-Project"
PROJECT_COOKIE = "baa_project"


def get_hub():
    """Koneksi ke hub (akun, sesi, audit, daftar project)."""
    conn = db.connect()
    try:
        yield conn
    finally:
        conn.close()


def current_user(
    request: Request,
    conn: sqlite3.Connection = Depends(get_hub),
    reza_baa_session: Optional[str] = Cookie(default=None),
):
    user = auth.get_session_user(conn, reza_baa_session)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not signed in")
    # Password default/sementara wajib diganti dulu: semua API lain ditolak di server
    if user["must_change"] and not request.url.path.startswith("/api/auth/"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Change your password first")
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


def accessible_projects(hub: sqlite3.Connection, user) -> list:
    """Project yang boleh dibuka user: admin semua (termasuk arsip & Setup), lainnya
    hanya project tidak diarsip, sudah diaktifkan (bukan Setup), tempat ia jadi anggota."""
    if user["role"] == "admin":
        return hub.execute("SELECT * FROM projects ORDER BY archived, id").fetchall()
    return hub.execute(
        "SELECT p.* FROM projects p JOIN project_members m ON m.project_id=p.id "
        "WHERE m.user_id=? AND p.archived=0 AND p.status<>'setup' ORDER BY p.id", (user["id"],)).fetchall()


def current_project(request: Request, hub: sqlite3.Connection = Depends(get_hub),
                    user=Depends(current_user)):
    """Project aktif request ini: header X-Project (dipakai fetch), lalu cookie
    baa_project (untuk <img>/unduhan), lalu project pertama yang boleh diakses.
    Akses selalu dicek di server — header/cookie hanya pilihan, bukan izin."""
    rows = accessible_projects(hub, user)
    if not rows:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="No project access")
    by_id = {str(r["id"]): r for r in rows}
    want = request.headers.get(PROJECT_HEADER)
    if want:
        if want not in by_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="No access to this project")
        return by_id[want]
    return by_id.get(request.cookies.get(PROJECT_COOKIE) or "", rows[0])


def gate_reason(project, user) -> str | None:
    """Alasan input data ditolak untuk project ini, atau None bila boleh.
    Setup: semua (termasuk admin). Frozen: semua kecuali admin."""
    st = project["status"] if "status" in project.keys() else "active"
    if st == "setup":
        return "This project is still being set up. Input opens once admin activates it."
    if st == "frozen" and user["role"] != "admin":
        msg = (project["freeze_msg"] or "").strip()
        return "Project is frozen — input is paused." + (f" {msg}" if msg else "")
    return None


def data_gate(request: Request, project=Depends(current_project), user=Depends(current_user)):
    """Dipasang di router data (lokasi, foto, scan, import, export, permintaan edit).
    Baca (GET) tetap boleh; tulis & semua export ditolak bila project Setup/Frozen."""
    path = request.url.path
    if path.startswith("/api/export/jobs/"):          # status/batal/unduh job yang sudah berjalan
        return
    if request.method in ("GET", "HEAD") and not path.startswith("/api/export/"):
        return
    why = gate_reason(project, user)
    if why:
        raise HTTPException(status.HTTP_423_LOCKED, detail=why)


def get_db(project=Depends(current_project)):
    """Koneksi ke DB project aktif (hub ter-ATTACH)."""
    conn = db.connect_project(project)
    try:
        yield conn
    finally:
        conn.close()


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
        "INSERT INTO audit_log(user_id, username, action, entity, entity_id, detail, created_at, project_id) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (
            user["id"] if user else None,
            user["username"] if user else "",
            action,
            entity,
            str(entity_id),
            detail,
            db.now_iso(),
            (getattr(conn, "project", None) or {}).get("id"),
        ),
    )
    conn.commit()
