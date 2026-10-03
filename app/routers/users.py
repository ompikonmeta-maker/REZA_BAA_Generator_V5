"""Manajemen user (khusus admin) + audit log."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import auth, db
from ..deps import audit, current_user, get_hub, require_admin

router = APIRouter(prefix="/api", tags=["users"])

ROLES = ("admin", "operator", "viewer")


class UserIn(BaseModel):
    username: str
    password: str = ""
    role: str = "operator"
    full_name: str = ""
    active: bool = True
    projects: list[int] | None = None   # akses project (None = tidak diubah)


def _set_projects(conn: sqlite3.Connection, uid: int, pids: list[int] | None) -> None:
    if pids is None:
        return
    valid = {r["id"] for r in conn.execute("SELECT id FROM projects")}
    conn.execute("DELETE FROM project_members WHERE user_id=?", (uid,))
    conn.executemany("INSERT INTO project_members(project_id, user_id) VALUES(?,?)",
                     [(pid, uid) for pid in set(pids) if pid in valid])


@router.get("/users")
def list_users(conn: sqlite3.Connection = Depends(get_hub), user=Depends(require_admin)):
    rows = conn.execute(
        "SELECT id,username,role,full_name,active,must_change,created_at FROM users ORDER BY id"
    ).fetchall()
    mem: dict[int, list[int]] = {}
    for r in conn.execute("SELECT user_id, project_id FROM project_members ORDER BY project_id"):
        mem.setdefault(r["user_id"], []).append(r["project_id"])
    return [{**dict(r), "projects": mem.get(r["id"], [])} for r in rows]


@router.post("/users")
def create_user(body: UserIn, conn: sqlite3.Connection = Depends(get_hub),
                user=Depends(require_admin)):
    if body.role not in ROLES:
        raise HTTPException(400, "Invalid role")
    if conn.execute("SELECT 1 FROM users WHERE username=?", (body.username.strip(),)).fetchone():
        raise HTTPException(400, "Username already taken")
    if len(body.password) < 4:
        raise HTTPException(400, "Password needs at least 4 characters")
    cur = conn.execute(
        "INSERT INTO users(username,password_hash,role,full_name,active,must_change,created_at) "
        "VALUES(?,?,?,?,?,?,?)",
        (body.username.strip(), auth.hash_password(body.password), body.role,
         body.full_name, 1 if body.active else 0, 1, db.now_iso()),
    )
    _set_projects(conn, cur.lastrowid, body.projects)
    conn.commit()
    audit(conn, user, "create", "user", cur.lastrowid, body.username)
    return {"ok": True, "id": cur.lastrowid}


@router.put("/users/{uid}")
def update_user(uid: int, body: UserIn, conn: sqlite3.Connection = Depends(get_hub),
                user=Depends(require_admin)):
    if body.role not in ROLES:
        raise HTTPException(400, "Invalid role")
    row = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if not row:
        raise HTTPException(404, "User not found")
    conn.execute(
        "UPDATE users SET role=?,full_name=?,active=? WHERE id=?",
        (body.role, body.full_name, 1 if body.active else 0, uid),
    )
    if body.password:
        conn.execute("UPDATE users SET password_hash=?,must_change=1 WHERE id=?",
                     (auth.hash_password(body.password), uid))
    _set_projects(conn, uid, body.projects)
    conn.commit()
    audit(conn, user, "update", "user", uid, row["username"])
    return {"ok": True}


@router.delete("/users/{uid}")
def delete_user(uid: int, conn: sqlite3.Connection = Depends(get_hub),
                user=Depends(require_admin)):
    if uid == user["id"]:
        raise HTTPException(400, "You can't delete your own account")
    row = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if not row:
        raise HTTPException(404, "User not found")
    # Data lokasi ada di DB tiap project (tanpa FK lintas file): tolak hapus bila
    # user masih tercatat di data project mana pun — nonaktifkan saja.
    for p in conn.execute("SELECT * FROM projects").fetchall():
        pc = db.connect_project(p)
        try:
            used = pc.execute("SELECT 1 FROM locations WHERE created_by=? OR owner_id=? LIMIT 1",
                              (uid, uid)).fetchone()
        finally:
            pc.close()
        if used:
            raise HTTPException(400, f"User still has locations in {p['name']}. Deactivate instead.")
    conn.execute("DELETE FROM users WHERE id=?", (uid,))
    conn.commit()
    audit(conn, user, "delete", "user", uid, row["username"])
    return {"ok": True}


@router.get("/audit")
def list_audit(limit: int = 200, conn: sqlite3.Connection = Depends(get_hub),
               user=Depends(require_admin)):
    rows = conn.execute(
        "SELECT id,username,action,entity,entity_id,detail,created_at "
        "FROM audit_log ORDER BY id DESC LIMIT ?", (min(limit, 1000),)
    ).fetchall()
    return [dict(r) for r in rows]
