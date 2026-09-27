"""Progress (admin & viewer), Supervisor Console (admin), dashboard operator.

Hari kerja = Senin–Jumat. Waktu disimpan UTC (ISO), dihitung per hari lokal.
"""
from __future__ import annotations

import json
import math
import sqlite3
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import db
from ..deps import audit, current_user, get_db, require_admin

router = APIRouter(prefix="/api", tags=["progress"])

DEFAULT_AGING = {"fresh": 2, "warm": 7, "stale": 14}
CONTENT_KINDS = ("create", "data", "inventory", "photo_add", "photo_del", "photo_move", "sn", "done", "reopen")


# ---------- util waktu ----------
def _local(iso: str | None) -> datetime | None:
    if not iso:
        return None
    try:
        d = datetime.fromisoformat(iso)
    except Exception:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone()


def _today() -> date:
    return datetime.now().astimezone().date()


def _is_wd(d: date) -> bool:
    return d.weekday() < 5


def _wd_between(a: date, b: date) -> int:
    """Jumlah hari kerja setelah a sampai dengan b (a < b). 0 bila b <= a."""
    if b <= a:
        return 0
    n, d = 0, a + timedelta(days=1)
    while d <= b:
        if _is_wd(d):
            n += 1
        d += timedelta(days=1)
    return n


def _wd_left(today: date, target: date) -> int:
    """Hari kerja tersisa dari hari ini (termasuk) sampai target (termasuk)."""
    if target < today:
        return 0
    n, d = 0, today
    while d <= target:
        if _is_wd(d):
            n += 1
        d += timedelta(days=1)
    return n


def _last_wds(today: date, n: int) -> list[date]:
    out, d = [], today
    while len(out) < n:
        if _is_wd(d):
            out.append(d)
        d -= timedelta(days=1)
    return list(reversed(out))


def _streak(days_with_done: set[date], today: date) -> tuple[int, int]:
    """(streak sekarang, rekor) dalam hari kerja. Hari ini belum selesai tidak memutus streak."""
    d = today
    while not _is_wd(d):
        d -= timedelta(days=1)
    if d not in days_with_done:
        d -= timedelta(days=1)
        while not _is_wd(d):
            d -= timedelta(days=1)
    cur = 0
    while d in days_with_done:
        cur += 1
        d -= timedelta(days=1)
        while not _is_wd(d):
            d -= timedelta(days=1)
    best, run, prev = 0, 0, None
    for x in sorted(x for x in days_with_done if _is_wd(x)):
        run = run + 1 if prev and _wd_between(prev, x) == 1 else 1
        best, prev = max(best, run), x
    return cur, max(best, cur)


# ---------- setting ----------
def _goal(conn) -> dict:
    g = db.get_setting(conn, "progress_goal", None) or {}
    return {"total": g.get("total"), "target_date": g.get("target_date")}


def _aging(conn) -> dict:
    a = db.get_setting(conn, "aging_days", None) or {}
    return {k: int(a.get(k, v)) for k, v in DEFAULT_AGING.items()}


def _bucket(idle: int, ag: dict) -> str:
    if idle <= ag["fresh"]:
        return "fresh"
    if idle <= ag["warm"]:
        return "warm"
    if idle <= ag["stale"]:
        return "stale"
    return "cold"


# ---------- kelengkapan (sama dengan locDetailState di UI) ----------
def _completeness(loc, fields, cats, inv_rows, photo_cats) -> tuple[int, list[str]]:
    data = json.loads(loc["data_json"] or "{}")
    miss_f = [f for f in fields if not str(data.get(f["key"], "") or "").strip()]
    filled_f = len(fields) - len(miss_f)
    cells = filled = items = 0
    bad_rows = []
    for r in inv_rows:
        vals = [str(r[k] or "").strip() for k in ("nama_barang", "merk_type", "jumlah", "sn_tagging", "keterangan")]
        if any(vals):
            items += 1
            cells += len(vals)
            filled += sum(1 for v in vals if v)
            if not all(vals):
                bad_rows.append((r, vals))
    inv_ok = items > 0 and filled == cells
    miss_c = [c for c in cats if c["key"] not in photo_cats]
    total = (len(fields) or 1) + 1 + len(cats)
    done = filled_f + (1 if inv_ok else (0.5 if items else 0)) + (len(cats) - len(miss_c))
    pct = min(100, round(done / total * 100))
    miss: list[str] = []
    if miss_c:
        miss.append(miss_c[0]["label"] if len(miss_c) == 1 else f"{len(miss_c)} photos")
    if miss_f:
        miss += [f["label"] for f in miss_f] if len(miss_f) <= 2 else ["Location data"]
    if not items:
        miss.append("Inventory")
    elif bad_rows:
        if len(bad_rows) == 1 and [i for i, v in enumerate(bad_rows[0][1]) if not v] == [3]:
            miss.append("SN " + (bad_rows[0][0]["nama_barang"] or "").strip())
        else:
            miss.append("Inventory")
    return pct, miss


def _loc_label(loc) -> dict:
    data = json.loads(loc["data_json"] or "{}") if "data_json" in loc.keys() else {}
    return {"id": loc["id"], "code": loc["code"], "name": (data.get("nama_lokasi") or loc["name"] or "").strip()}


def _open_drafts(conn, where: str = "", params: tuple = ()) -> list[dict]:
    """Draft aktif + kelengkapan, kekurangan, dan umur (hari kerja sejak last modified)."""
    fields = db.get_setting(conn, "location_fields", []) or []
    cats = db.get_setting(conn, "photo_categories", []) or []
    rows = conn.execute(
        "SELECT l.*, COALESCE(NULLIF(TRIM(o.full_name),''), o.username, '—') owner_name "
        "FROM locations l LEFT JOIN users o ON o.id=l.owner_id "
        f"WHERE l.deleted_at IS NULL AND l.status!='selesai' {where}", params).fetchall()
    ids = [r["id"] for r in rows] or [0]
    q = ",".join("?" * len(ids))
    inv: dict[int, list] = {}
    for r in conn.execute(f"SELECT * FROM inventory_items WHERE location_id IN ({q}) ORDER BY sort_order,id", ids):
        inv.setdefault(r["location_id"], []).append(r)
    pc: dict[int, set] = {}
    for r in conn.execute(f"SELECT location_id, category FROM photos WHERE location_id IN ({q})", ids):
        pc.setdefault(r["location_id"], set()).add(r["category"])
    today, ag = _today(), _aging(conn)
    out = []
    for r in rows:
        pct, miss = _completeness(r, fields, cats, inv.get(r["id"], []), pc.get(r["id"], set()))
        lm = _local(r["modified_at"] or r["updated_at"])
        idle = _wd_between(lm.date(), today) if lm else 0
        out.append({**_loc_label(r), "pct": pct, "missing": miss, "idle": idle, "aging": _bucket(idle, ag),
                    "owner_id": r["owner_id"], "owner": r["owner_name"]})
    return out


def _done_days(conn, where: str = "", params: tuple = ()) -> list[date]:
    out = []
    for r in conn.execute(f"SELECT done_at FROM locations WHERE deleted_at IS NULL AND status='selesai' "
                          f"AND done_at IS NOT NULL {where}", params):
        d = _local(r["done_at"])
        if d:
            out.append(d.date())
    return out


def _team(conn) -> dict:
    """Angka tim vs target: dipakai Progress, Supervisor, dan operator."""
    today = _today()
    goal = _goal(conn)
    n_loc = conn.execute("SELECT COUNT(*) c FROM locations WHERE deleted_at IS NULL").fetchone()["c"]
    done_days = _done_days(conn)
    done = len(done_days)
    total = goal["total"] or n_loc
    last10 = _last_wds(today, 10)
    pace_now = round(sum(1 for d in done_days if d >= last10[0]) / 10, 2)
    tgt = date.fromisoformat(goal["target_date"]) if goal["target_date"] else None
    wd_left = _wd_left(today, tgt) if tgt else None
    remain = max(0, total - done)
    need = round(remain / wd_left, 2) if wd_left else None
    proj = round(done + pace_now * wd_left) if wd_left is not None else None
    # posisi yang seharusnya hari ini (garis ideal dari lokasi pertama dibuat)
    first = conn.execute("SELECT MIN(created_at) m FROM locations WHERE deleted_at IS NULL").fetchone()["m"]
    ideal_today = None
    if tgt and first:
        st = _local(first).date()
        span = _wd_between(st - timedelta(days=1), tgt) or 1
        ideal_today = round(total * min(1, _wd_between(st - timedelta(days=1), today) / span))
    wk0 = today - timedelta(days=today.weekday())
    return {"total": total, "total_set": goal["total"] is not None, "target_date": goal["target_date"],
            "done": done, "remain": remain, "locations": n_loc, "pace_now": pace_now, "pace_needed": need,
            "wd_left": wd_left, "days_left": (tgt - today).days if tgt else None, "projection": proj,
            "ideal_today": ideal_today,
            "done_this_week": sum(1 for d in done_days if d >= wk0),
            "done_last_week": sum(1 for d in done_days if wk0 - timedelta(days=7) <= d < wk0),
            "streak": _streak(set(done_days), today)}


# ---------- Progress ----------
def _require_admin_or_viewer(user=Depends(current_user)):
    if user["role"] not in ("admin", "viewer"):
        raise HTTPException(403, "Admins and viewers only")
    return user


@router.get("/progress")
def progress(conn: sqlite3.Connection = Depends(get_db), user=Depends(_require_admin_or_viewer)):
    today = _today()
    team = _team(conn)
    drafts = _open_drafts(conn)
    ready = sum(1 for d in drafts if d["pct"] >= 100)
    # deret kumulatif harian: done & created
    rows = conn.execute("SELECT created_at, done_at, status FROM locations WHERE deleted_at IS NULL").fetchall()
    cr = sorted(_local(r["created_at"]).date() for r in rows if _local(r["created_at"]))
    dn = sorted(_local(r["done_at"]).date() for r in rows if r["status"] == "selesai" and _local(r["done_at"]))
    series = []
    if cr:
        d, ci, di = cr[0], 0, 0
        while d <= today:
            while ci < len(cr) and cr[ci] <= d:
                ci += 1
            while di < len(dn) and dn[di] <= d:
                di += 1
            series.append({"d": d.isoformat(), "created": ci, "done": di})
            d += timedelta(days=1)
    # cycle time created -> done (hari kalender)
    cyc = []
    for r in conn.execute("SELECT created_at, done_at FROM locations WHERE deleted_at IS NULL AND status='selesai' "
                          "AND done_at IS NOT NULL"):
        a, b = _local(r["created_at"]), _local(r["done_at"])
        if a and b:
            cyc.append(max(0, (b.date() - a.date()).days))
    return {"team": team, "aging": _aging(conn), "history": db.get_setting(conn, "progress_history", []) or [],
            "pipeline": {"done": team["done"], "ready": ready, "progress": len(drafts) - ready,
                         "notyet": max(0, team["total"] - team["done"] - len(drafts))},
            "drafts": drafts, "series": series, "cycle": cyc, "can_edit": user["role"] == "admin"}


class GoalIn(BaseModel):
    total: int | None = None
    target_date: str | None = None


@router.put("/progress/goal")
def set_goal(body: GoalIn, conn: sqlite3.Connection = Depends(get_db), user=Depends(require_admin)):
    g = _goal(conn)
    hist = db.get_setting(conn, "progress_history", []) or []
    name = (user["full_name"] or user["username"]).strip()
    if body.total is not None:
        if body.total < 1:
            raise HTTPException(400, "Total must be at least 1")
        if body.total != g["total"]:
            hist.append({"at": db.now_iso(), "by": name, "field": "total", "old": g["total"], "new": body.total})
            g["total"] = body.total
    if body.target_date is not None:
        try:
            date.fromisoformat(body.target_date)
        except ValueError:
            raise HTTPException(400, "Invalid date")
        if body.target_date != g["target_date"]:
            hist.append({"at": db.now_iso(), "by": name, "field": "target_date", "old": g["target_date"],
                         "new": body.target_date})
            g["target_date"] = body.target_date
    db.set_setting(conn, "progress_goal", g)
    db.set_setting(conn, "progress_history", hist[-200:])
    conn.commit()
    audit(conn, user, "set_goal", "settings", "progress_goal", json.dumps(g))
    return {"ok": True, "goal": g}


class AgingIn(BaseModel):
    fresh: int
    warm: int
    stale: int


@router.put("/progress/aging")
def set_aging(body: AgingIn, conn: sqlite3.Connection = Depends(get_db), user=Depends(require_admin)):
    if not (0 <= body.fresh < body.warm < body.stale):
        raise HTTPException(400, "Use increasing values: Fresh < Warm < Stale")
    db.set_setting(conn, "aging_days", body.model_dump())
    conn.commit()
    audit(conn, user, "set_aging", "settings", "aging_days", json.dumps(body.model_dump()))
    return {"ok": True}


# ---------- aktivitas ----------
def _feed(conn, where: str, params: tuple, limit: int) -> list[dict]:
    rows = conn.execute(
        "SELECT a.kind, a.detail, a.created_at, a.user_id, a.location_id, "
        "COALESCE(NULLIF(TRIM(u.full_name),''), u.username, '—') uname, l.code, l.name, l.data_json "
        "FROM activity a LEFT JOIN users u ON u.id=a.user_id LEFT JOIN locations l ON l.id=a.location_id "
        f"WHERE 1=1 {where} ORDER BY a.created_at DESC, a.id DESC LIMIT ?", params + (limit,)).fetchall()
    out = []
    for r in rows:
        data = json.loads(r["data_json"] or "{}") if r["data_json"] else {}
        out.append({"kind": r["kind"], "detail": r["detail"], "at": r["created_at"], "user": r["uname"],
                    "loc": {"id": r["location_id"], "code": r["code"] or "",
                            "name": (data.get("nama_lokasi") or r["name"] or "").strip()}})
    return out


# ---------- Supervisor Console ----------
@router.get("/dash/supervisor")
def supervisor(conn: sqlite3.Connection = Depends(get_db), user=Depends(require_admin)):
    today = _today()
    team = _team(conn)
    drafts = _open_drafts(conn)
    users = conn.execute("SELECT id, username, full_name, role, last_seen_at FROM users "
                         "WHERE active=1 AND role IN ('admin','operator') ORDER BY id").fetchall()
    wk0 = today - timedelta(days=today.weekday())
    last10 = _last_wds(today, 10)
    now = datetime.now(timezone.utc)
    done_by = {}
    for r in conn.execute("SELECT owner_id, done_at FROM locations WHERE deleted_at IS NULL AND status='selesai' "
                          "AND done_at IS NOT NULL"):
        d = _local(r["done_at"])
        if d:
            done_by.setdefault(r["owner_id"], []).append(d.date())
    # heatmap edit per user per hari kerja (10 hari kerja terakhir)
    edits: dict[tuple, int] = {}
    last_act: dict[int, dict] = {}
    for r in conn.execute("SELECT a.user_id, a.created_at, a.location_id, l.code, l.name, l.data_json FROM activity a "
                          "LEFT JOIN locations l ON l.id=a.location_id WHERE a.created_at >= ? ORDER BY a.id",
                          ((datetime.combine(last10[0], datetime.min.time()).astimezone() - timedelta(days=60))
                           .astimezone(timezone.utc).isoformat(),)):
        d = _local(r["created_at"])
        if not d:
            continue
        if d.date() >= last10[0]:
            edits[(r["user_id"], d.date())] = edits.get((r["user_id"], d.date()), 0) + 1
        data = json.loads(r["data_json"] or "{}") if r["data_json"] else {}
        last_act[r["user_id"]] = {"at": r["created_at"], "code": r["code"] or "",
                                  "name": (data.get("nama_lokasi") or r["name"] or "").strip(), "id": r["location_id"]}
    n_workers = sum(1 for u in users if u["role"] == "operator") or len(users) or 1
    part10 = (team["pace_needed"] or 0) * 10 / n_workers
    rows = []
    for u in users:
        seen = _local(u["last_seen_at"])
        mins = (now - seen.astimezone(timezone.utc)).total_seconds() / 60 if seen else None
        state = "online" if mins is not None and mins <= 5 else "idle" if mins is not None and mins <= 60 else "offline"
        mine = [d for d in drafts if d["owner_id"] == u["id"]]
        ag = {k: sum(1 for d in mine if d["aging"] == k) for k in ("fresh", "warm", "stale", "cold")}
        dd = done_by.get(u["id"], [])
        done10 = sum(1 for d in dd if d >= last10[0])
        la = last_act.get(u["id"])
        inactive = _wd_between(_local(la["at"]).date(), today) if la else None
        rows.append({"id": u["id"], "name": (u["full_name"] or u["username"]).strip(), "role": u["role"],
                     "state": state, "last_seen": u["last_seen_at"], "done_week": sum(1 for d in dd if d >= wk0),
                     "open": len(mine), "aging": ag, "last": la,
                     "share": round(done10 / part10, 2) if part10 else None,
                     "inactive_wd": inactive,
                     "heat": [edits.get((u["id"], d), 0) for d in last10]})
    # saran transfer: pemilik draft Cold terbanyak & tidak aktif -> user online dgn draft paling sedikit
    tip = None
    src = sorted([r for r in rows if r["aging"]["cold"] and (r["inactive_wd"] or 0) >= 3],
                 key=lambda r: -r["aging"]["cold"])
    dst = sorted([r for r in rows if r["state"] != "offline" and r["role"] == "operator"], key=lambda r: r["open"])
    if src and dst and src[0]["id"] != dst[0]["id"]:
        tip = {"from": src[0]["name"], "from_id": src[0]["id"], "cold": src[0]["aging"]["cold"],
               "inactive_wd": src[0]["inactive_wd"], "to": dst[0]["name"], "to_id": dst[0]["id"], "to_open": dst[0]["open"]}
    t0 = datetime.combine(today, datetime.min.time()).astimezone().astimezone(timezone.utc).isoformat()
    return {"team": team, "users": rows, "days": [d.isoformat() for d in last10],
            "feed": _feed(conn, "AND a.created_at >= ?", (t0,), 40), "tip": tip, "aging": _aging(conn)}


# ---------- dashboard operator ----------
@router.get("/dash/me")
def my_dash(conn: sqlite3.Connection = Depends(get_db), user=Depends(current_user)):
    today = _today()
    team = _team(conn)
    mine = _open_drafts(conn, "AND l.owner_id=?", (user["id"],))
    mine.sort(key=lambda d: (-d["pct"], d["idle"]))
    dd = _done_days(conn, "AND owner_id=?", (user["id"],))
    wk0 = today - timedelta(days=today.weekday())
    week = []
    for i in range(5):
        d = wk0 + timedelta(days=i)
        n_ed = conn.execute("SELECT COUNT(*) c FROM activity WHERE user_id=? AND created_at>=? AND created_at<?",
                            (user["id"], datetime.combine(d, datetime.min.time()).astimezone().astimezone(timezone.utc).isoformat(),
                             datetime.combine(d + timedelta(days=1), datetime.min.time()).astimezone().astimezone(timezone.utc).isoformat())).fetchone()["c"]
        week.append({"d": d.isoformat(), "done": sum(1 for x in dd if x == d), "edits": n_ed, "today": d == today,
                     "future": d > today})
    n_workers = conn.execute("SELECT COUNT(*) c FROM users WHERE active=1 AND role='operator'").fetchone()["c"] or 1
    part = math.ceil((team["pace_needed"] or 0) * 5 / n_workers) if team["pace_needed"] else None
    cur, best = _streak(set(dd), today)
    return {"name": (user["full_name"] or user["username"]).strip(), "team": team, "drafts": mine,
            "week": week, "week_done": sum(w["done"] for w in week), "week_part": part,
            "streak": cur, "best": best, "aging": _aging(conn),
            "feed": _feed(conn, "AND a.user_id=?", (user["id"],), 12)}
