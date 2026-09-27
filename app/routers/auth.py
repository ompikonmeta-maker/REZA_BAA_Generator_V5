"""Login / logout / profil / ganti password."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from .. import auth, config
from ..deps import audit, current_user, get_db

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    username: str
    password: str


class ChangePwIn(BaseModel):
    old_password: str
    new_password: str


class PeekIn(BaseModel):
    username: str


@router.post("/peek")
def peek(body: PeekIn, conn: sqlite3.Connection = Depends(get_db)):
    """Cek ringan apakah username (aktif) bertipe admin — untuk aksen 'zona' di
    layar login. Hanya balas admin true/false (tanpa info keberadaan user)."""
    row = conn.execute(
        "SELECT role FROM users WHERE username=? AND active=1", (body.username.strip(),)
    ).fetchone()
    return {"admin": bool(row and row["role"] == "admin")}


def _public(user) -> dict:
    return {
        "id": user["id"],
        "username": user["username"],
        "role": user["role"],
        "full_name": user["full_name"],
        "must_change": bool(user["must_change"]),
    }


@router.post("/login")
def login(body: LoginIn, response: Response, conn: sqlite3.Connection = Depends(get_db)):
    row = conn.execute(
        "SELECT * FROM users WHERE username=? AND active=1", (body.username.strip(),)
    ).fetchone()
    if not row or not auth.verify_password(body.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Wrong username or password")
    token = auth.create_session(conn, row["id"])
    response.set_cookie(
        config.SESSION_COOKIE, token, httponly=True, samesite="lax",
        max_age=config.SESSION_TTL_HOURS * 3600,
    )
    audit(conn, row, "login", "user", row["id"])
    return _public(row)


@router.post("/logout")
def logout(response: Response, conn: sqlite3.Connection = Depends(get_db),
           user=Depends(current_user)):
    # token diambil ulang dari cookie oleh dependency; hapus semua sesi user ini
    conn.execute("DELETE FROM sessions WHERE user_id=?", (user["id"],))
    conn.commit()
    response.delete_cookie(config.SESSION_COOKIE)
    return {"ok": True}


@router.get("/me")
def me(user=Depends(current_user)):
    return _public(user)


@router.post("/change-password")
def change_password(body: ChangePwIn, conn: sqlite3.Connection = Depends(get_db),
                    user=Depends(current_user)):
    if not auth.verify_password(body.old_password, user["password_hash"]):
        raise HTTPException(status_code=400, detail="Current password is wrong")
    if len(body.new_password) < 4:
        raise HTTPException(status_code=400, detail="New password is too short")
    conn.execute(
        "UPDATE users SET password_hash=?, must_change=0 WHERE id=?",
        (auth.hash_password(body.new_password), user["id"]),
    )
    conn.commit()
    audit(conn, user, "change_password", "user", user["id"])
    return {"ok": True}
