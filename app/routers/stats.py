"""Statistik dashboard (role-aware).

Admin  : agregat seluruh lokasi + leaderboard + aktivitas global.
Operator: agregat di-scope ke lokasi miliknya (created_by = user) + streak.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends

from .. import db
from ..deps import current_user, get_db

router = APIRouter(prefix="/api", tags=["stats"])

_EMPTY_INV = (
    "TRIM(COALESCE(i.nama_barang,''))='' OR TRIM(COALESCE(i.merk_type,''))='' OR "
    "TRIM(COALESCE(i.jumlah,''))='' OR TRIM(COALESCE(i.sn_tagging,''))='' OR "
    "TRIM(COALESCE(i.keterangan,''))=''"
)


def _day_series(rows: dict, days: int) -> list[int]:
    """Kembalikan list hitungan per hari (lama -> baru) untuk `days` terakhir."""
    today = date.today()
    return [rows.get((today - timedelta(days=days - 1 - i)).isoformat(), 0) for i in range(days)]


@router.get("/stats")
def stats(conn: sqlite3.Connection = Depends(get_db), user=Depends(current_user)):
    is_admin = user["role"] == "admin"
    see_all = user["role"] in ("admin", "viewer")   # viewer = mode bos: lihat semua
    uid = user["id"]
    scope = " AND l.deleted_at IS NULL" + ("" if see_all else " AND l.owner_id = :uid")
    own = "" if see_all else " AND owner_id=:uid"  # untuk subquery locations tanpa alias
    p = {"uid": uid, "pid": conn.project["id"]}

    # --- ringkasan lokasi ---
    tot = conn.execute(
        f"SELECT COUNT(*) c, "
        f"SUM(CASE WHEN status='selesai' THEN 1 ELSE 0 END) done "
        f"FROM locations l WHERE 1=1{scope}", p
    ).fetchone()
    total = tot["c"] or 0
    done = tot["done"] or 0
    draft = total - done
    pct = round(done / total * 100) if total else 0

    photos = conn.execute(
        f"SELECT COUNT(*) c FROM photos ph WHERE 1=1" +
        f" AND ph.location_id IN (SELECT id FROM locations WHERE deleted_at IS NULL{own})", p
    ).fetchone()["c"] or 0

    users_active = conn.execute("SELECT COUNT(*) c FROM pm_users WHERE active=1").fetchone()["c"] or 0
    template_active = conn.execute("SELECT COUNT(*) c FROM templates WHERE active=1").fetchone()["c"] or 0
    inv_items = conn.execute(
        f"SELECT COUNT(*) c FROM inventory_items i WHERE 1=1" +
        f" AND i.location_id IN (SELECT id FROM locations WHERE deleted_at IS NULL{own})", p
    ).fetchone()["c"] or 0

    # --- butuh perhatian (draft, terlama dulu) ---
    attn_rows = conn.execute(
        f"""SELECT l.id,l.code,l.name,l.data_json,
              (SELECT GROUP_CONCAT(DISTINCT category) FROM photos p WHERE p.location_id=l.id) photo_cats,
              (SELECT COUNT(*) FROM inventory_items i WHERE i.location_id=l.id) inv_count,
              (SELECT COUNT(*) FROM inventory_items i WHERE i.location_id=l.id AND ({_EMPTY_INV})) inv_bad
            FROM locations l WHERE l.status!='selesai'{scope}
            ORDER BY l.updated_at ASC LIMIT 8""", p
    ).fetchall()
    attention = [{
        "id": r["id"], "code": r["code"], "name": r["name"],
        "data": json.loads(r["data_json"]),
        "photo_cats": (r["photo_cats"].split(",") if r["photo_cats"] else []),
        "inv_ok": r["inv_count"] > 0 and r["inv_bad"] == 0,
    } for r in attn_rows]

    # --- leaderboard (admin) ---
    leaderboard = []
    if is_admin:
        for r in conn.execute(
            "SELECT COALESCE(NULLIF(u.full_name,''),u.username) nm, COUNT(l.id) total, "
            "SUM(CASE WHEN l.status='selesai' THEN 1 ELSE 0 END) done "
            "FROM users u JOIN locations l ON l.owner_id=u.id AND l.deleted_at IS NULL "
            "GROUP BY u.id HAVING total>0 ORDER BY done DESC, total DESC LIMIT 6"
        ).fetchall():
            leaderboard.append({"name": r["nm"], "total": r["total"], "done": r["done"] or 0})

    # --- aktivitas terbaru ---
    feed_scope = " WHERE project_id=:pid" + ("" if see_all else " AND user_id=:uid")
    feed = [dict(r) for r in conn.execute(
        f"SELECT username,action,entity,entity_id,detail,created_at FROM audit_log{feed_scope} "
        f"ORDER BY id DESC LIMIT 8", p
    ).fetchall()]

    # --- tren: lokasi selesai per hari (14 hari) ---
    cutoff14 = (date.today() - timedelta(days=13)).isoformat()
    trend_rows = {r["d"]: r["c"] for r in conn.execute(
        f"SELECT date(updated_at) d, COUNT(*) c FROM locations l "
        f"WHERE status='selesai' AND date(updated_at)>=:c14{scope} GROUP BY d",
        {**p, "c14": cutoff14}
    ).fetchall()}
    trend = _day_series(trend_rows, 14)

    # --- heatmap: aktivitas per hari (~6 bulan, rolling) dari audit ---
    cutoff56 = (date.today() - timedelta(days=196)).isoformat()  # ~6 bulan + buffer minggu
    heat_scope = "" if see_all else " AND user_id=:uid"
    heat_rows = {r["d"]: r["c"] for r in conn.execute(
        f"SELECT date(created_at) d, COUNT(*) c FROM audit_log "
        f"WHERE project_id=:pid AND date(created_at)>=:c56{heat_scope} GROUP BY d",
        {**p, "c56": cutoff56}
    ).fetchall()}
    heat = _day_series(heat_rows, 197)

    out = {
        "role": user["role"],
        "name": user["full_name"] or user["username"],
        "totals": {"locations": total, "done": done, "draft": draft, "photos": photos,
                   "users_active": users_active, "template_active": template_active,
                   "inv_items": inv_items},
        "pct": pct,
        "attention": attention,
        "leaderboard": leaderboard,
        "feed": feed,
        "trend": trend,
        "heat": heat,
    }

    # --- streak + minggu ini (operator) ---
    if not is_admin:
        act_days = {r["d"] for r in conn.execute(
            "SELECT DISTINCT date(created_at) d FROM audit_log WHERE user_id=:uid", p
        ).fetchall()}
        streak = 0
        cur = date.today()
        while cur.isoformat() in act_days:
            streak += 1
            cur -= timedelta(days=1)
        week = [1 if (date.today() - timedelta(days=6 - i)).isoformat() in act_days else 0 for i in range(7)]
        out["streak"] = streak
        out["week"] = week

    return out


@router.get("/stats/supervisor")
def supervisor(conn: sqlite3.Connection = Depends(get_db), user=Depends(current_user)):
    """Metrik performa untuk konsol supervisor (admin) & dashboard viewer (bos).

    Perhitungan per-user (peringkat & 'perlu perhatian') hanya menghitung user
    tipe **operator** — admin & viewer dikecualikan karena bukan pelaksana
    lapangan. Metrik tim (total, velocity, throughput, bottleneck) tetap
    mencakup seluruh lokasi.
    """
    from fastapi import HTTPException
    if user["role"] not in ("admin", "viewer"):
        raise HTTPException(403, "Admins and viewers only")
    import json
    today = date.today()
    monday = today - timedelta(days=today.weekday())      # Senin minggu ini
    cutoff7 = (today - timedelta(days=7)).isoformat()

    def wk(i):  # awal minggu i-minggu lalu (i=0 -> Senin ini)
        return monday - timedelta(days=7 * i)

    def completed(a, b, uid=None):
        q = ("SELECT COUNT(*) c FROM locations WHERE deleted_at IS NULL AND status='selesai' "
             "AND date(updated_at)>=? AND date(updated_at)<?")
        pr = [a.isoformat(), b.isoformat()]
        if uid is not None:
            q += " AND owner_id=?"; pr.append(uid)
        return conn.execute(q, pr).fetchone()["c"] or 0

    tot = conn.execute(
        "SELECT COUNT(*) c, SUM(CASE WHEN status='selesai' THEN 1 ELSE 0 END) d FROM locations WHERE deleted_at IS NULL"
    ).fetchone()
    total = tot["c"] or 0
    done = tot["d"] or 0
    pct = round(done / total * 100) if total else 0
    vel_this = completed(wk(0), wk(-1))
    vel_prev = completed(wk(1), wk(0))
    ct = conn.execute(
        "SELECT AVG(julianday(updated_at)-julianday(created_at)) a FROM locations WHERE deleted_at IS NULL AND status='selesai'"
    ).fetchone()["a"]
    cycle = round(ct, 1) if ct and ct > 0 else 0
    stalled = conn.execute(
        "SELECT COUNT(*) c FROM locations WHERE deleted_at IS NULL AND status!='selesai' AND date(updated_at)<?", [cutoff7]
    ).fetchone()["c"] or 0
    # Hanya operator yang dihitung sebagai 'tim lapangan' (exclude admin & viewer).
    users_active = conn.execute(
        "SELECT COUNT(*) c FROM pm_users WHERE active=1 AND role='operator'").fetchone()["c"] or 0
    users_total = conn.execute(
        "SELECT COUNT(*) c FROM pm_users WHERE role='operator'").fetchone()["c"] or 0
    throughput = [completed(wk(j), wk(j - 1)) for j in range(7, -1, -1)]

    # per-user (khusus operator — admin & viewer dikecualikan dari peringkat/perhatian)
    users = []
    for u in conn.execute(
        "SELECT id, COALESCE(NULLIF(full_name,''),username) nm FROM pm_users "
        "WHERE active=1 AND role='operator'"
    ).fetchall():
        r = conn.execute(
            "SELECT COUNT(*) t, SUM(CASE WHEN status='selesai' THEN 1 ELSE 0 END) d "
            "FROM locations WHERE deleted_at IS NULL AND owner_id=?", [u["id"]]
        ).fetchone()
        t = r["t"] or 0
        if t == 0:
            continue
        d = r["d"] or 0
        load = conn.execute(
            "SELECT COUNT(*) c FROM locations WHERE deleted_at IS NULL AND owner_id=? AND status!='selesai'", [u["id"]]
        ).fetchone()["c"] or 0
        stalled_u = conn.execute(
            "SELECT COUNT(*) c FROM locations WHERE deleted_at IS NULL AND owner_id=? AND status!='selesai' AND date(updated_at)<?",
            [u["id"], cutoff7]
        ).fetchone()["c"] or 0
        vel = [completed(wk(j), wk(j - 1), u["id"]) for j in range(3, -1, -1)]
        vt, vp = vel[-1], vel[-2]
        if (vt == 0 and load > 0) or stalled_u >= 3 or (vp > 0 and vt < vp * 0.6):
            health = "b"
        elif vp > 0 and vt < vp:
            health = "w"
        else:
            health = "g"
        reasons = []
        if vp > 0 and vt < vp:
            reasons.append(f"velocity −{round((vp - vt) / vp * 100)}%")
        if vt == 0 and load > 0:
            reasons.append("0 done this week")
        if stalled_u > 0:
            reasons.append(f"{stalled_u} stalled drafts")
        users.append({
            "id": u["id"], "name": u["nm"], "done": d, "total": t,
            "pct": round(d / t * 100), "vel": vel, "load": load,
            "stalled": stalled_u, "health": health, "reason": " · ".join(reasons),
        })

    # bottleneck dari draft
    cats = db.get_setting(conn, "photo_categories", [])
    fields = db.get_setting(conn, "location_fields", [])
    drafts = conn.execute("SELECT id, data_json FROM locations WHERE deleted_at IS NULL AND status!='selesai'").fetchall()
    nd = len(drafts)
    miss = {}
    inv_bad = 0
    field_bad = 0
    for dr in drafts:
        present = {x["category"] for x in conn.execute(
            "SELECT DISTINCT category FROM photos WHERE location_id=?", [dr["id"]]).fetchall()}
        for c in cats:
            if c.get("key") not in present:
                lbl = c.get("label", c.get("key"))
                miss[lbl] = miss.get(lbl, 0) + 1
        icnt = conn.execute("SELECT COUNT(*) c FROM inventory_items WHERE location_id=?", [dr["id"]]).fetchone()["c"] or 0
        ibad = conn.execute(
            f"SELECT COUNT(*) c FROM inventory_items i WHERE location_id=? AND ({_EMPTY_INV})", [dr["id"]]
        ).fetchone()["c"] or 0
        if not (icnt > 0 and ibad == 0):
            inv_bad += 1
        try:
            data = json.loads(dr["data_json"] or "{}")
        except Exception:
            data = {}
        if any(not str(data.get(f["key"], "")).strip() for f in fields):
            field_bad += 1
    items = [(l, c, "foto") for l, c in miss.items() if c > 0]
    if inv_bad:
        items.append(("Inventory incomplete", inv_bad, "inv"))
    if field_bad:
        items.append(("Empty location fields", field_bad, "data"))
    items.sort(key=lambda x: -x[1])
    bottleneck = [{"label": l, "count": c, "total": nd,
                   "pct": round(c / nd * 100), "kind": k}
                  for l, c, k in items[:6]] if nd else []

    # aktivitas terkini tim (global) untuk 'denyut pekerjaan' di dashboard viewer
    feed = [dict(r) for r in conn.execute(
        "SELECT username,action,entity,entity_id,detail,created_at FROM audit_log "
        "WHERE project_id=? ORDER BY id DESC LIMIT 8", (conn.project["id"],)
    ).fetchall()]

    # momentum/streak tim: hari beruntun (mundur dari hari ini) yang ADA lokasi selesai
    done_days = {r["d"] for r in conn.execute(
        "SELECT DISTINCT date(updated_at) d FROM locations WHERE deleted_at IS NULL AND status='selesai'"
    ).fetchall()}
    streak = 0
    cur = today
    while cur.isoformat() in done_days:
        streak += 1
        cur -= timedelta(days=1)
    week = [1 if (today - timedelta(days=6 - i)).isoformat() in done_days else 0 for i in range(7)]

    return {
        "name": user["full_name"] or user["username"],
        "role": user["role"],
        "summary": {"total": total, "done": done, "pct": pct,
                    "vel_this": vel_this, "vel_prev": vel_prev, "cycle": cycle,
                    "stalled": stalled, "users_active": users_active, "users_total": users_total},
        "users": users,
        "bottleneck": bottleneck,
        "throughput": throughput,
        "feed": feed,
        "streak": streak,
        "week": week,
    }
