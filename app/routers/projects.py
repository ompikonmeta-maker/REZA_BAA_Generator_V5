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
            "wilayah_progress": bool(p["wilayah_progress"]), "status": p["status"] or "active",
            "freeze_msg": p["freeze_msg"] or "", "frozen_by": p["frozen_by"] or "", "frozen_at": p["frozen_at"]}


def _readiness(hub, pc, pid: int) -> dict:
    """Status langkah mode Setup. Wajib: data (field + kategori foto), template
    (aktif & sudah dipetakan), tim (min. 1 operator). Target opsional."""
    import json
    fields = [f for f in (db.get_setting(pc, "location_fields") or []) if f.get("key") != "nama_lokasi"]
    cats = db.get_setting(pc, "photo_categories") or []
    inv = db.get_setting(pc, "default_inventory_items") or []
    tpl = pc.execute("SELECT name, config_json FROM templates WHERE active=1 ORDER BY id DESC LIMIT 1").fetchone()
    cfg = json.loads(tpl["config_json"] or "{}") if tpl else {}
    mapped = bool(cfg.get("mapped") or cfg.get("log") or cfg.get("detail"))
    team = {r["role"]: r["n"] for r in hub.execute(
        "SELECT u.role, COUNT(*) n FROM project_members m JOIN users u ON u.id=m.user_id "
        "WHERE m.project_id=? AND u.active=1 GROUP BY u.role", (pid,))}
    g = db.get_setting(pc, "progress_goal", None) or {}      # target yang benar-benar diisi admin
    steps = {
        "data": {"ok": bool(fields) and bool(cats), "fields": len(fields), "photos": len(cats), "inventory": len(inv)},
        "template": {"ok": bool(tpl) and mapped, "name": tpl["name"] if tpl else None, "mapped": mapped},
        "team": {"ok": team.get("operator", 0) > 0, "operators": team.get("operator", 0), "viewers": team.get("viewer", 0)},
        "target": {"ok": bool(g.get("total")), "total": g.get("total"), "target_date": g.get("target_date")},
    }
    steps["ready"] = all(steps[k]["ok"] for k in ("data", "template", "team"))
    return steps


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
            if p["wilayah_on"]:
                prov: dict[str, list[int]] = {}
                for r in pc.execute("SELECT substr(wil_kode,1,2) k, COUNT(*) n, SUM(status='selesai') d FROM locations "
                                    "WHERE deleted_at IS NULL AND wil_kode IS NOT NULL AND wil_kode<>'' GROUP BY k"):
                    prov[r["k"]] = [r["n"], r["d"] or 0]
                out["peta"] = prov
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
    rows = [p for p in accessible_projects(hub, user) if not p["archived"] and p["status"] != "setup"]
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
                "setup": _readiness(hub, pc, p["id"]),
                "next_code": db.format_code(pc, seq + 1), "template": tpl["name"] if tpl else None,
                "total": g["total"], "target_date": g["target_date"],
                "locations": n["c"] or 0, "done": n["d"] or 0,
                "wil_missing": pc.execute("SELECT COUNT(*) c FROM locations WHERE deleted_at IS NULL "
                                          "AND (wil_desa IS NULL OR wil_desa='')").fetchone()["c"]}
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
    # Project baru selalu mulai kosong (hanya field sistem Nama Lokasi) dan berstatus
    # Setup: belum ada yang bisa entry sampai admin menyiapkan & mengaktifkannya.
    nama = [f for f in db.DEFAULT_LOCATION_FIELDS if f["key"] == "nama_lokasi"]
    base = {**db.EMPTY_PROJECT_SETTINGS, "location_fields": nama}
    pid = db.create_project(hub, name, prefix, body.color, base, status="setup")
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
            raise HTTPException(400, "Prefix is locked: location codes were already issued. "
                                     "Freeze the project and use Change prefix.")
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


# ---------- siklus project: Setup -> Active <-> Frozen ----------
def _project_or_404(hub, pid: int):
    p = hub.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
    if not p:
        raise HTTPException(404, "Project not found")
    return p


@router.post("/{pid}/activate")
def activate(pid: int, hub: sqlite3.Connection = Depends(get_hub), user=Depends(require_admin)):
    p = _project_or_404(hub, pid)
    if p["status"] != "setup":
        raise HTTPException(400, "Project is already active")
    pc = db.connect_project(p)
    try:
        ready = _readiness(hub, pc, pid)
    finally:
        pc.close()
    if not ready["ready"]:
        left = [n for k, n in (("data", "Location data"), ("template", "Template BAA"), ("team", "Team"))
                if not ready[k]["ok"]]
        raise HTTPException(400, "Finish first: " + ", ".join(left))
    hub.execute("UPDATE projects SET status='active' WHERE id=?", (pid,))
    hub.commit()
    audit(hub, user, "activate", "project", pid, p["name"])
    return _admin_row(hub, _project_or_404(hub, pid))


class FreezeIn(BaseModel):
    message: str = ""


@router.post("/{pid}/freeze")
def freeze(pid: int, body: FreezeIn, hub: sqlite3.Connection = Depends(get_hub), user=Depends(require_admin)):
    p = _project_or_404(hub, pid)
    if p["status"] == "setup":
        raise HTTPException(400, "Project is not active yet")
    msg = body.message.strip()[:300]
    if p["status"] == "frozen":       # sudah frozen -> hanya ubah pesan
        hub.execute("UPDATE projects SET freeze_msg=? WHERE id=?", (msg, pid))
        action = "freeze_message"
    else:
        hub.execute("UPDATE projects SET status='frozen', freeze_msg=?, frozen_by=?, frozen_at=? WHERE id=?",
                    (msg, (user["full_name"] or "").strip() or user["username"], db.now_iso(), pid))
        action = "freeze"
    hub.commit()
    audit(hub, user, action, "project", pid, msg)
    return _admin_row(hub, _project_or_404(hub, pid))


@router.post("/{pid}/unfreeze")
def unfreeze(pid: int, hub: sqlite3.Connection = Depends(get_hub), user=Depends(require_admin)):
    p = _project_or_404(hub, pid)
    if p["status"] != "frozen":
        raise HTTPException(400, "Project is not frozen")
    hub.execute("UPDATE projects SET status='active' WHERE id=?", (pid,))
    hub.commit()
    audit(hub, user, "unfreeze", "project", pid, p["name"])
    return _admin_row(hub, _project_or_404(hub, pid))


# ---------- ganti prefix kode untuk project yang sudah berisi data ----------
def _recode_plan(hub, p, new: str) -> dict:
    """Analisa ganti prefix (tanpa mengubah apa pun)."""
    new = (new or "").strip().upper()
    old = p["prefix"].upper()
    if not _PREFIX.match(new):
        raise HTTPException(400, "Code prefix must be 2–4 letters (A–Z)")
    if new == old:
        raise HTTPException(400, "That is already the current prefix")
    if hub.execute("SELECT 1 FROM projects WHERE prefix=? AND id<>?", (new, p["id"])).fetchone():
        raise HTTPException(400, f"Prefix {new} is already used by another project")
    base = db.project_dir(p)
    pc = db.connect_project(p)
    try:
        rows = pc.execute("SELECT id, code, deleted_at FROM locations ORDER BY id").fetchall()
        codes = {r["code"] for r in rows}
        mapping, skipped = [], []
        for r in rows:
            head, sep, num = r["code"].partition("_")
            if sep and head.upper() == old:
                mapping.append((r["id"], r["code"], f"{new}_{num}", bool(r["deleted_at"])))
            else:
                skipped.append(r["code"])
        conflicts = [n for _, o, n, _ in mapping if n in codes]
        folders = size = 0
        for _, o, n, _ in mapping:
            for sub in ("images", "docs"):
                src = base / sub / o
                if src.is_dir():
                    folders += 1
                    size += sum(f.stat().st_size for f in src.rglob("*") if f.is_file())
                if (base / sub / n).exists():
                    conflicts.append(f"{sub}/{n}")
        ids = [m[0] for m in mapping] or [0]
        qs = ",".join("?" * len(ids))
        photos = pc.execute(f"SELECT COUNT(*) c FROM photos WHERE location_id IN ({qs})", ids).fetchone()["c"]
        scans = pc.execute(f"SELECT COUNT(*) c FROM scan_docs WHERE location_id IN ({qs})", ids).fetchone()["c"]
        exported = pc.execute(f"SELECT COUNT(DISTINCT location_id) c FROM export_log WHERE location_id IN ({qs})",
                              ids).fetchone()["c"]
    finally:
        pc.close()
    sample = [{"old": o, "new": n} for _, o, n, _ in (mapping[:2] + mapping[-1:] if len(mapping) > 3 else mapping)]
    return {"old": old, "new": new, "count": len(mapping), "deleted": sum(1 for m in mapping if m[3]),
            "photos": photos, "scans": scans, "folders": folders, "size": size, "exported": exported,
            "conflicts": conflicts[:10], "skipped": skipped[:10], "sample": sample, "_mapping": mapping}


class RecodeIn(BaseModel):
    prefix: str


@router.get("/{pid}/recode")
def recode_preview(pid: int, prefix: str, hub: sqlite3.Connection = Depends(get_hub), user=Depends(require_admin)):
    p = _project_or_404(hub, pid)
    plan = _recode_plan(hub, p, prefix)
    plan.pop("_mapping")
    return plan


@router.post("/{pid}/recode")
def recode_apply(pid: int, body: RecodeIn, hub: sqlite3.Connection = Depends(get_hub), user=Depends(require_admin)):
    """Ganti prefix + semua kode lokasi + folder foto/scan dalam satu langkah.
    Hanya saat Frozen. Gagal di tengah -> DB di-rollback & folder dikembalikan."""
    import shutil
    p = _project_or_404(hub, pid)
    if p["status"] != "frozen":
        raise HTTPException(400, "Freeze the project before changing its code prefix")
    plan = _recode_plan(hub, p, body.prefix)
    if plan["conflicts"]:
        raise HTTPException(400, "Conflict: " + ", ".join(plan["conflicts"][:3]))
    base = db.project_dir(p)
    moved: list[tuple] = []
    pc = db.connect_project(p)
    try:
        for _, o, n, _ in plan["_mapping"]:
            for sub in ("images", "docs"):
                src, dst = base / sub / o, base / sub / n
                if src.is_dir():
                    shutil.move(str(src), str(dst))
                    moved.append((dst, src))
        for lid, o, n, _ in plan["_mapping"]:
            pc.execute("UPDATE locations SET code=?, old_codes=TRIM(COALESCE(old_codes,'') || ' ' || ?) WHERE id=?",
                       (n, o, lid))
            pc.execute("UPDATE photos SET path = 'images/' || ? || substr(path, ?) WHERE location_id=? AND path LIKE ?",
                       (n, len("images/" + o) + 1, lid, f"images/{o}/%"))
            pc.execute("UPDATE scan_docs SET path = 'docs/' || ? || substr(path, ?) WHERE location_id=? AND path LIKE ?",
                       (n, len("docs/" + o) + 1, lid, f"docs/{o}/%"))
        hub.execute("UPDATE projects SET prefix=? WHERE id=?", (plan["new"], pid))
        pc.commit()
        hub.commit()
    except Exception as e:
        pc.rollback()
        hub.rollback()
        for dst, src in reversed(moved):
            try:
                shutil.move(str(dst), str(src))
            except Exception:
                pass
        raise HTTPException(500, f"Re-code failed, nothing was changed ({e.__class__.__name__})")
    finally:
        pc.close()
    audit(hub, user, "recode", "project", pid, f"{plan['old']} → {plan['new']} · {plan['count']} locations")
    return _admin_row(hub, _project_or_404(hub, pid))


class MembersIn(BaseModel):
    members: list[int]


@router.put("/{pid}/members")
def set_members(pid: int, body: MembersIn, hub: sqlite3.Connection = Depends(get_hub), user=Depends(require_admin)):
    """Akses tim (langkah Team) tanpa mengirim ulang seluruh form project."""
    p = _project_or_404(hub, pid)
    _set_members(hub, pid, body.members)
    hub.commit()
    audit(hub, user, "members", "project", pid, f"{p['name']}: {len(body.members)}")
    return _admin_row(hub, _project_or_404(hub, pid))


class TargetIn(BaseModel):
    total: int | None = None
    target_date: str | None = None


@router.put("/{pid}/target")
def set_target(pid: int, body: TargetIn, hub: sqlite3.Connection = Depends(get_hub), user=Depends(require_admin)):
    p = _project_or_404(hub, pid)
    pc = db.connect_project(p)
    try:
        pg.apply_goal(pc, user, body.total, body.target_date or None)
    finally:
        pc.close()
    return _admin_row(hub, _project_or_404(hub, pid))
