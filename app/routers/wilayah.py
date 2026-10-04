"""Pencarian & ringkasan wilayah (Desa/Kelurahan → Provinsi) untuk project aktif."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse

from ..deps import current_user, get_db, require_admin
from ..services import wilayah

router = APIRouter(prefix="/api/wilayah", tags=["wilayah"])


@router.get("/meta")
def wil_meta(user=Depends(current_user)):
    return wilayah.meta()


@router.get("/search")
def wil_search(q: str = Query(""), prov: str = Query(""), kab: str = Query(""), limit: int = Query(30),
               level: str = Query("desa"), under: str = Query(""),
               conn: sqlite3.Connection = Depends(get_db), user=Depends(current_user)):
    """Cari desa/kelurahan. Wilayah yang sering dipakai di project ini (terutama
    oleh user ini) diurutkan lebih atas."""
    boost: dict[str, int] = {}
    for r in conn.execute("SELECT wil_kode, created_by FROM locations WHERE deleted_at IS NULL "
                          "AND wil_kode IS NOT NULL AND wil_kode<>''"):
        w = 2 if r["created_by"] == user["id"] else 1
        for k in (r["wil_kode"][:8], r["wil_kode"][:5]):
            boost[k] = boost.get(k, 0) + w
    return wilayah.search(q, prov.strip(), kab.strip(), limit, boost, level, under.strip())


@router.get("/regions")
def wil_regions(conn: sqlite3.Connection = Depends(get_db), user=Depends(current_user)):
    """Provinsi & kab/kota yang dipakai lokasi di project ini (untuk filter Location Log)."""
    prov: dict[str, int] = {}
    kab: dict[str, int] = {}
    none = manual = 0
    for r in conn.execute("SELECT wil_kode, wil_desa, wil_mode FROM locations WHERE deleted_at IS NULL"):
        k = r["wil_kode"]
        if not r["wil_desa"]:
            none += 1
            continue
        if r["wil_mode"] in ("desa_manual", "manual"):
            manual += 1
        if not k:
            continue
        prov[k[:2]] = prov.get(k[:2], 0) + 1
        kab[k[:5]] = kab.get(k[:5], 0) + 1
    out = []
    for p in sorted(prov, key=lambda x: wilayah.name_of(x)):
        out.append({"kode": p, "nama": wilayah.name_of(p), "n": prov[p], "level": "prov"})
        for k in sorted([k for k in kab if k.startswith(p + ".")], key=lambda x: wilayah.name_of(x)):
            out.append({"kode": k, "nama": wilayah.short_kab(wilayah.name_of(k)), "n": kab[k], "level": "kab"})
    return {"regions": out, "none": none, "manual": manual}


# ---------- infografis (tahap 3) ----------
_PETA = Path(__file__).resolve().parent.parent / "data" / "peta.json"


@router.get("/peta")
def wil_peta(user=Depends(current_user)):
    """Path SVG batas provinsi & kab/kota (statis, boleh di-cache)."""
    return FileResponse(_PETA, media_type="application/json", headers={"Cache-Control": "private, max-age=86400"})


def _region_stats(conn) -> dict:
    """Agregat lokasi per provinsi / kab-kota / kecamatan untuk project aktif."""
    from . import progress as pg
    ag = pg._aging(conn)
    today = pg._today()
    prov: dict[str, dict] = {}
    kab: dict[str, dict] = {}
    kec: dict[str, dict] = {}
    manual = none = 0

    def add(m, k, done, draft, stale):
        x = m.setdefault(k, {"n": 0, "done": 0, "drafts": 0, "stale": 0})
        x["n"] += 1; x["done"] += done; x["drafts"] += draft; x["stale"] += stale
    for r in conn.execute("SELECT wil_kode, wil_desa, wil_mode, status, modified_at, updated_at FROM locations "
                          "WHERE deleted_at IS NULL"):
        if not r["wil_desa"]:
            none += 1
            continue
        k = r["wil_kode"] or ""
        if not k:
            manual += 1
            continue
        done = 1 if r["status"] == "selesai" else 0
        lm = pg._local(r["modified_at"] or r["updated_at"])
        idle = pg._wd_between(lm.date(), today) if lm else 0
        stale = 1 if (not done and idle >= ag["warm"]) else 0
        add(prov, k[:2], done, 1 - done, stale)
        add(kab, k[:5], done, 1 - done, stale)
        add(kec, k[:8], done, 1 - done, stale)
    names = wilayah._load()["names"]
    kec_total = sum(1 for c in names if c.count(".") == 2 and c[:5] in kab)
    team = pg._team(conn)
    ideal = round(team["ideal_today"] / team["total"] * 100) if team.get("ideal_today") is not None and team["total"] else None
    for m in (prov, kab, kec):
        for c, x in m.items():
            x["nama"] = wilayah.short_kab(names.get(c, c))
    return {"prov": prov, "kab": kab, "kec": kec, "manual": manual, "none": none,
            "kec_reached": len(kec), "kec_total": kec_total, "ideal_pct": ideal, "warm": ag["warm"]}


@router.get("/stats")
def wil_stats(conn: sqlite3.Connection = Depends(get_db), user=Depends(current_user)):
    return _region_stats(conn)


@router.get("/team")
def wil_team(conn: sqlite3.Connection = Depends(get_db), user=Depends(require_admin)):
    """Draft terbuka per operator per kab/kota (amber = tanpa perubahan ≥ batas 'warm')."""
    from . import progress as pg
    ag = pg._aging(conn)
    today = pg._today()
    out: dict[int, dict] = {}
    for r in conn.execute(
            "SELECT l.owner_id, l.wil_kode, l.wil_kab, l.modified_at, l.updated_at, "
            "COALESCE(NULLIF(TRIM(u.full_name),''), u.username, '—') nm FROM locations l "
            "LEFT JOIN users u ON u.id=l.owner_id WHERE l.deleted_at IS NULL AND l.status!='selesai'"):
        o = out.setdefault(r["owner_id"] or 0, {"name": r["nm"], "drafts": 0, "kab": {}})
        o["drafts"] += 1
        k = (r["wil_kode"] or "")[:5]
        label = wilayah.short_kab(wilayah.name_of(k)) if k else (r["wil_kab"] or "No wilayah yet")
        lm = pg._local(r["modified_at"] or r["updated_at"])
        idle = pg._wd_between(lm.date(), today) if lm else 0
        x = o["kab"].setdefault(label, {"n": 0, "stale": 0, "kode": k})
        x["n"] += 1
        x["stale"] += 1 if idle >= ag["warm"] else 0
    rows = []
    for o in sorted(out.values(), key=lambda o: -o["drafts"]):
        rows.append({"name": o["name"], "drafts": o["drafts"],
                     "kab": sorted(({"nama": k, **v} for k, v in o["kab"].items()), key=lambda x: -x["n"])})
    return {"team": rows, "warm": ag["warm"]}
