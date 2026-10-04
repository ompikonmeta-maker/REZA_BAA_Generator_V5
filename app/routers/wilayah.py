"""Pencarian & ringkasan wilayah (Desa/Kelurahan → Provinsi) untuk project aktif."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, Query

from ..deps import current_user, get_db
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
