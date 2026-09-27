"""Manajemen user (khusus admin) + audit log."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import auth, db
from ..deps import audit, current_user, get_db, require_admin

router = APIRouter(prefix="/api", tags=["users"])

ROLES = ("admin", "operator", "viewer")


class UserIn(BaseModel):
    username: str
    password: str = ""
    role: str = "operator"
    full_name: str = ""
    active: bool = True


@router.get("/users")
def list_users(conn: sqlite3.Connection = Depends(get_db), user=Depends(require_admin)):
    rows = conn.execute(
        "SELECT id,username,role,full_name,active,must_change,created_at FROM users ORDER BY id"
    ).fetchall()
    return [dict(r) for r in rows]


@router.post("/users")
def create_user(body: UserIn, conn: sqlite3.Connection = Depends(get_db),
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
    conn.commit()
    audit(conn, user, "create", "user", cur.lastrowid, body.username)
    return {"ok": True, "id": cur.lastrowid}


@router.put("/users/{uid}")
def update_user(uid: int, body: UserIn, conn: sqlite3.Connection = Depends(get_db),
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
    conn.commit()
    audit(conn, user, "update", "user", uid, row["username"])
    return {"ok": True}


@router.delete("/users/{uid}")
def delete_user(uid: int, conn: sqlite3.Connection = Depends(get_db),
                user=Depends(require_admin)):
    if uid == user["id"]:
        raise HTTPException(400, "You can't delete your own account")
    row = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if not row:
        raise HTTPException(404, "User not found")
    conn.execute("DELETE FROM users WHERE id=?", (uid,))
    conn.commit()
    audit(conn, user, "delete", "user", uid, row["username"])
    return {"ok": True}


@router.get("/audit")
def list_audit(limit: int = 200, conn: sqlite3.Connection = Depends(get_db),
               user=Depends(require_admin)):
    rows = conn.execute(
        "SELECT id,username,action,entity,entity_id,detail,created_at "
        "FROM audit_log ORDER BY id DESC LIMIT ?", (min(limit, 1000),)
    ).fetchall()
    return [dict(r) for r in rows]
