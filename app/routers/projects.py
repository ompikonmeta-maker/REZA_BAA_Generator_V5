"""Multi-project: daftar project milik user, portfolio, dan setup project (admin).

Tiap project = satu file SQLite (data/projects/pN.db) dengan template, lokasi,
foto & pengaturannya sendiri. Akun & akses ada di hub (app.db). Admin selalu
bisa membuka semua project; operator/viewer hanya project yang diberikan admin.
"""
from __future__ import annotations

import re
import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import db
from ..deps import accessible_projects, audit, current_user, get_hub, require_admin
from . import progress as pg

router = APIRouter(prefix="/api/projects", tags=["projects"])

_PREFIX = re.compile(r"^[A-Z]{2,4}$")
_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


def _public(p) -> dict:
    return {"id": p["id"], "name": p["name"], "prefix": p["prefix"], "color": p["color"],
            "archived": bool(p["archived"]), "wilayah_on": bool(p["wilayah_on"]),
            "wilayah_progress": bool(p["wilayah_progress"])}


def _seq(pc) -> int:
    """Nomor kode terakhir yang pernah terbit (termasuk lokasi yang sudah dihapus)."""
    r = pc.execute("SELECT seq FROM sqlite_sequence WHERE name='locations'").fetchone()
    return r["seq"] if r else 0


def _summary(p, user, *, detail: bool = False) -> dict:
    """Angka ringkas satu project (dibuka langsung dari file DB-nya)."""
    pc = db.connect_project(p)
    try:
        t = pg._team(pc)
        out = {**_public(p), "done": t["done"], "total": t["total"], "target_date": t["target_date"],
               "locations": t["locations"]}
        out["drafts"] = pc.execute("SELECT COUNT(*) c FROM locations WHERE deleted_at IS NULL "
                                   "AND status!='selesai'").fetchone()["c"]
        if user["role"] == "operator":
            out["my_drafts"] = pc.execute("SELECT COUNT(*) c FROM locations WHERE deleted_at IS NULL "
                                          "AND status!='selesai' AND owner_id=?", (user["id"],)).fetchone()["c"]
        if user["role"] == "admin":
            out["pending"] = pc.execute("SELECT COUNT(*) c FROM edit_requests WHERE status='pending'"
                                        ).fetchone()["c"]
        if detail:
            today = pg._today()
            days = pg._last_wds(today, 10)
            dd = pg._done_days(pc)
            out["spark"] = [sum(1 for d in dd if d == x) for x in days]
            short = t["total"] - t["projection"] if t["projection"] is not None else None
            if t["done"] >= t["total"]:
                state = "good"
            elif short is None or (not t["pace_now"] and not t["done"]):
                state = "none"
            elif short <= 0:
                state = "good"
            elif t["projection"] >= 0.85 * t["total"]:
                state = "warn"
            else:
                state = "bad"
            out.update(state=state, short=short, pace_now=t["pace_now"], pace_needed=t["pace_needed"])
        return out
    finally:
        pc.close()


@router.get("/mine")
def my_projects(hub: sqlite3.Connection = Depends(get_hub), user=Depends(current_user)):
    """Project yang boleh dibuka user ini (untuk pemilih project)."""
    return {"projects": [_summary(p, user) for p in accessible_projects(hub, user)]}


@router.get("/portfolio")
def portfolio(hub: sqlite3.Connection = Depends(get_hub), user=Depends(current_user)):
    """Ringkasan visual semua project yang boleh dilihat (admin & viewer)."""
    if user["role"] not in ("admin", "viewer"):
        raise HTTPException(403, "Admins and viewers only")
    rows = [p for p in accessible_projects(hub, user) if not p["archived"]]
    return {"projects": [_summary(p, user, detail=True) for p in rows]}


# ---------- setup (admin) ----------
class ProjectIn(BaseModel):
    name: str
    prefix: str
    color: str = db.PROJECT_COLORS[0]
    total: int | None = None
    target_date: str | None = None
    members: list[int] | None = None
    archived: bool | None = None
    wilayah_on: bool | None = None
    wilayah_progress: bool | None = None


def _members(hub, pid: int) -> list[int]:
    return [r["user_id"] for r in hub.execute(
        "SELECT user_id FROM project_members WHERE project_id=? ORDER BY user_id", (pid,))]


def _admin_row(hub, p) -> dict:
    pc = db.connect_project(p)
    try:
        seq = _seq(pc)
        tpl = pc.execute("SELECT name FROM templates WHERE active=1 ORDER BY id DESC LIMIT 1").fetchone()
        g = pg._goal(pc)
        n = pc.execute("SELECT COUNT(*) c, SUM(CASE WHEN status='selesai' THEN 1 ELSE 0 END) d "
                       "FROM locations WHERE deleted_at IS NULL").fetchone()
        return {**_public(p), "members": _members(hub, p["id"]), "prefix_locked": seq > 0,
                "next_code": db.format_code(pc, seq + 1), "template": tpl["name"] if tpl else None,
                "total": g["total"], "target_date": g["target_date"],
                "locations": n["c"] or 0, "done": n["d"] or 0,
                "wil_missing": pc.execute("SELECT COUNT(*) c FROM locations WHERE deleted_at IS NULL "
                                          "AND (wil_kode IS NULL OR wil_kode='')").fetchone()["c"]}
    finally:
        pc.close()


@router.get("")
def list_projects(hub: sqlite3.Connection = Depends(get_hub), user=Depends(require_admin)):
    rows = hub.execute("SELECT * FROM projects ORDER BY archived, id").fetchall()
    return {"projects": [_admin_row(hub, p) for p in rows], "max": db.MAX_PROJECTS,
            "colors": db.PROJECT_COLORS}


def _validate(hub, body: ProjectIn, pid: int | None = None) -> tuple[str, str]:
    name = body.name.strip()
    prefix = body.prefix.strip().upper()
    if not name:
        raise HTTPException(400, "Project name is required")
    if not _PREFIX.match(prefix):
        raise HTTPException(400, "Code prefix must be 2–4 letters (A–Z)")
    if hub.execute("SELECT 1 FROM projects WHERE prefix=? AND id IS NOT ?", (prefix, pid)).fetchone():
        raise HTTPException(400, f"Prefix {prefix} is already used by another project")
    if hub.execute("SELECT 1 FROM projects WHERE name=? COLLATE NOCASE AND id IS NOT ?", (name, pid)).fetchone():
        raise HTTPException(400, "Another project already has this name")
    if not _COLOR.match(body.color or ""):
        raise HTTPException(400, "Invalid color")
    return name, prefix


def _set_members(hub, pid: int, members: list[int] | None) -> None:
    if members is None:
        return
    ok = {r["id"] for r in hub.execute("SELECT id FROM users WHERE role <> 'admin'")}
    hub.execute("DELETE FROM project_members WHERE project_id=?", (pid,))
    hub.executemany("INSERT INTO project_members(project_id, user_id) VALUES(?,?)",
                    [(pid, u) for u in set(members) if u in ok])


def _active_count(hub) -> int:
    return hub.execute("SELECT COUNT(*) c FROM projects WHERE archived=0").fetchone()["c"]


@router.post("")
def create_project(body: ProjectIn, hub: sqlite3.Connection = Depends(get_hub), user=Depends(require_admin)):
    if _active_count(hub) >= db.MAX_PROJECTS:
        raise HTTPException(400, f"Maximum {db.MAX_PROJECTS} active projects")
    name, prefix = _validate(hub, body)
    # Pengaturan (field lokasi, kategori foto, inventory) disalin dari project
    # pertama: saat ini antar project hanya berbeda template.
    first = hub.execute("SELECT * FROM projects ORDER BY id LIMIT 1").fetchone()
    base = db.project_settings(first) if first else None
    pid = db.create_project(hub, name, prefix, body.color, base)
    hub.execute("UPDATE projects SET wilayah_on=?, wilayah_progress=? WHERE id=?",
                (int(body.wilayah_on if body.wilayah_on is not None else True),
                 int(body.wilayah_progress if body.wilayah_progress is not None else True), pid))
    _set_members(hub, pid, body.members)
    hub.commit()
    p = hub.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
    if body.total is not None or body.target_date:
        pc = db.connect_project(p)
        try:
            pg.apply_goal(pc, user, body.total, body.target_date or None)
        finally:
            pc.close()
    audit(hub, user, "create", "project", pid, f"{name} ({prefix})")
    return _admin_row(hub, p)


@router.put("/{pid}")
def update_project(pid: int, body: ProjectIn, hub: sqlite3.Connection = Depends(get_hub),
                   user=Depends(require_admin)):
    p = hub.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
    if not p:
        raise HTTPException(404, "Project not found")
    name, prefix = _validate(hub, body, pid)
    pc = db.connect_project(p)
    try:
        if prefix != p["prefix"].upper() and _seq(pc) > 0:
            raise HTTPException(400, "Prefix is locked: location codes were already issued")
        archived = p["archived"] if body.archived is None else int(body.archived)
        if p["archived"] and not archived and _active_count(hub) >= db.MAX_PROJECTS:
            raise HTTPException(400, f"Maximum {db.MAX_PROJECTS} active projects")
        if archived and not p["archived"] and _active_count(hub) <= 1:
            raise HTTPException(400, "At least one project must stay active")
        if body.total is not None or body.target_date:
            pg.apply_goal(pc, user, body.total, body.target_date or None)
    finally:
        pc.close()
    w_on = p["wilayah_on"] if body.wilayah_on is None else int(body.wilayah_on)
    w_pr = p["wilayah_progress"] if body.wilayah_progress is None else int(body.wilayah_progress)
    hub.execute("UPDATE projects SET name=?, prefix=?, color=?, archived=?, wilayah_on=?, wilayah_progress=? "
                "WHERE id=?", (name, prefix, body.color, archived, w_on, w_pr, pid))
    _set_members(hub, pid, body.members)
    hub.commit()
    audit(hub, user, "update", "project", pid, f"{name} ({prefix})")
    return _admin_row(hub, hub.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone())
