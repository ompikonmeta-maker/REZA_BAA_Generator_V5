"""Import massal lokasi dari Excel (admin only).

Alur: unduh template (2 sheet) -> isi -> upload -> preview (dry-run, validasi)
-> commit (buat lokasi + inventory, kode urut otomatis).
"""
from __future__ import annotations

import datetime as _dt
import io
import json
import sqlite3

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

import re

from .. import db
from ..deps import audit, get_db, require_admin
from ..services import wilayah
from .locations import _format_code, _wil_values, _WIL_SET

router = APIRouter(prefix="/api/locations/import", tags=["locations-import"])

INV_COLS = ["nama_barang", "merk_type", "jumlah", "sn_tagging", "keterangan"]
# Kolom wilayah (bila fitur wilayah aktif di project): judul template + pengenal judul
WIL_COLS = [("kode", "Kode Wilayah", r"kode\s*wilayah|kode\s*desa"), ("desa", "Desa/Kelurahan", r"desa|kelurahan"), ("kec", "Kecamatan", r"kecamatan|\bkec\b"),
            ("kab", "Kab/Kota", r"kabupaten|\bkab\b|kota"), ("prov", "Provinsi", r"provinsi|propinsi|\bprov\b")]


def _wil_on(conn) -> bool:
    return bool((getattr(conn, "project", None) or {}).get("wilayah_on", 1))
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _fields(conn):
    return db.get_setting(conn, "location_fields", []) or []


def _norm(v) -> str:
    return str(v).strip() if v is not None else ""


def _to_iso(v):
    """Kembalikan (iso, ok). Terima date/datetime atau string beberapa format."""
    if v is None or v == "":
        return "", True
    if isinstance(v, (_dt.datetime, _dt.date)):
        return v.strftime("%Y-%m-%d"), True
    s = str(v).strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return _dt.datetime.strptime(s, fmt).strftime("%Y-%m-%d"), True
        except ValueError:
            pass
    return s, False


@router.get("/template")
def template(conn: sqlite3.Connection = Depends(get_db), user=Depends(require_admin)):
    import openpyxl
    from openpyxl.utils import get_column_letter
    fields = _fields(conn)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Lokasi"
    wcols = [w[1] for w in WIL_COLS[1:]] + [WIL_COLS[0][1]] if _wil_on(conn) else []
    ws.append(["ref"] + [(_norm(f.get("label")) or f.get("key")) for f in fields] + wcols)
    ex = ["L1"]
    for f in fields:
        if f.get("key") == "nama_lokasi":
            ex.append("Contoh: Desa Sukamaju")
        elif f.get("type") == "date":
            ex.append("2026-09-01")
        else:
            ex.append("")
    if wcols:
        ex += ["Cibodas", "Lembang", "Kab. Bandung Barat", "Jawa Barat", ""]
    ws.append(ex)
    wi = wb.create_sheet("Inventory")
    wi.append(["ref"] + INV_COLS)
    wi.append(["L1", "Access Point", "Starlink", "1", "SN-CONTOH", "Baik"])
    for w in (ws, wi):
        for c in range(1, w.max_column + 1):
            w.column_dimensions[get_column_letter(c)].width = 20
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf, media_type=XLSX_MIME,
        headers={"Content-Disposition": "attachment; filename=Template_Import_Lokasi.xlsx"},
    )


def _parse(conn: sqlite3.Connection, data: bytes) -> dict:
    import openpyxl
    fields = _fields(conn)
    label_to_field = {}
    for f in fields:
        label_to_field[_norm(f.get("label")).lower()] = f
        label_to_field[_norm(f.get("key")).lower()] = f
    try:
        wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
    except Exception:
        raise HTTPException(400, "Can't read the file — make sure it's .xlsx")
    if "Lokasi" not in wb.sheetnames:
        raise HTTPException(400, "Sheet 'Lokasi' not found. Download the template first.")

    rows = list(wb["Lokasi"].iter_rows(values_only=True))
    if not rows:
        return {"locations": [], "summary": {"total": 0, "ready": 0, "items": 0, "errors": 0, "dup": 0}}
    header = [_norm(h) for h in rows[0]]
    col_field, ref_idx, wil_idx = {}, None, {}
    for idx, h in enumerate(header):
        hl = h.lower()
        if hl == "ref":
            ref_idx = idx
        elif hl in label_to_field:
            col_field[idx] = label_to_field[hl]
        elif _wil_on(conn):
            for key, _lab, rx in WIL_COLS:
                if key not in wil_idx.values() and re.search(rx, hl) and not (key == "kab" and "kode" in hl):
                    wil_idx[idx] = key
                    break

    # Inventory dikelompokkan per ref
    inv_by_ref: dict[str, list] = {}
    if "Inventory" in wb.sheetnames:
        irows = list(wb["Inventory"].iter_rows(values_only=True))
        if irows:
            ih = [_norm(h).lower() for h in irows[0]]
            cref = ih.index("ref") if "ref" in ih else None
            cmap = {c: (ih.index(c) if c in ih else None) for c in INV_COLS}
            for r in irows[1:]:
                if r is None:
                    continue
                ref = _norm(r[cref]) if (cref is not None and cref < len(r)) else ""
                item = {c: (_norm(r[cmap[c]]) if (cmap[c] is not None and cmap[c] < len(r)) else "") for c in INV_COLS}
                if not any(item.values()):
                    continue
                inv_by_ref.setdefault(ref, []).append(item)

    # Peta kanonik untuk auto-correct
    merks = db.get_setting(conn, "item_merks", {}) or {}
    kets = db.get_setting(conn, "inventory_keterangan", []) or []
    ket_map = {k.lower(): k for k in kets}

    def fix_merk(nama, val):
        for o in merks.get(_norm(nama), []):
            if o.lower() == val.lower():
                return o
        return val

    # Nama lokasi yang sudah ada (untuk deteksi duplikat)
    existing = set()
    for r in conn.execute("SELECT name, data_json FROM locations WHERE deleted_at IS NULL"):
        nm = _norm(r["name"])
        if not nm:
            try:
                nm = _norm((json.loads(r["data_json"]) or {}).get("nama_lokasi"))
            except Exception:
                nm = ""
        if nm:
            existing.add(nm.lower())

    out, seen_ref = [], {}
    for ri, r in enumerate(rows[1:], start=2):
        if r is None or all(_norm(c) == "" for c in r):
            continue
        data, errors = {}, []
        for idx, f in col_field.items():
            val = r[idx] if idx < len(r) else None
            if f.get("type") == "date":
                iso, ok = _to_iso(val)
                if not ok:
                    errors.append(f"Tanggal '{f.get('label')}' tidak valid")
                data[f.get("key")] = iso
            else:
                data[f.get("key")] = _norm(val)
        nama = _norm(data.get("nama_lokasi"))
        if not nama:
            errors.append("Nama lokasi wajib")
        ref = _norm(r[ref_idx]) if (ref_idx is not None and ref_idx < len(r)) else ""
        if ref:
            if ref in seen_ref:
                errors.append(f"ref '{ref}' dipakai lebih dari sekali")
            seen_ref[ref] = ri
        inv = []
        for it in (inv_by_ref.get(ref, []) if ref else []):
            it = dict(it)
            it["merk_type"] = fix_merk(it.get("nama_barang", ""), it.get("merk_type", ""))
            it["keterangan"] = ket_map.get(it.get("keterangan", "").lower(), it.get("keterangan", ""))
            inv.append(it)
        wil = None
        if wil_idx:
            wv = {k: _norm(r[i]) if i < len(r) else "" for i, k in wil_idx.items()}
            wil = wilayah.match(wv.get("desa", ""), wv.get("kec", ""), wv.get("kab", ""), wv.get("prov", ""),
                                wv.get("kode", ""))
            wil["raw"] = {k: wv.get(k, "") for k in ("desa", "kec", "kab", "prov")}
        out.append({"row": ri, "nama": nama, "data": data, "inventory": inv,
                    "errors": errors, "dup": nama.lower() in existing, "wil": wil})

    ok_rows = [x for x in out if not x["errors"]]
    return {"locations": out, "summary": {
        "total": len(out),
        "ready": len(ok_rows),
        "items": sum(len(x["inventory"]) for x in ok_rows),
        "errors": sum(1 for x in out if x["errors"]),
        "dup": sum(1 for x in ok_rows if x["dup"]),
        "wil_cols": bool(wil_idx),
        "wil_ok": sum(1 for x in ok_rows if x["wil"] and x["wil"]["status"] == "ok"),
        "wil_manual": sum(1 for x in ok_rows if x["wil"] and x["wil"]["status"] == "desa_manual"),
        "wil_check": sum(1 for x in ok_rows if x["wil"] and x["wil"]["status"] in ("ambiguous", "notfound")),
    }}


@router.post("/preview")
async def preview(file: UploadFile = File(...), conn: sqlite3.Connection = Depends(get_db),
                  user=Depends(require_admin)):
    return _parse(conn, await file.read())


@router.post("/commit")
async def commit(file: UploadFile = File(...), skip_dup: bool = Form(True), wil_choices: str = Form("{}"),
                 conn: sqlite3.Connection = Depends(get_db), user=Depends(require_admin)):
    """wil_choices: {baris: {"kode": desa resmi} | {"manual": 1} | {}}. Baris wilayah yang perlu dicek
    tanpa pilihan disimpan TANPA wilayah (tidak ada penyimpanan diam-diam)."""
    res = _parse(conn, await file.read())
    try:
        choices = {str(k): v for k, v in (json.loads(wil_choices or "{}") or {}).items()}
    except Exception:
        choices = {}
    created = skipped = 0
    now = db.now_iso()
    for loc in res["locations"]:
        if loc["errors"] or (loc["dup"] and skip_dup):
            skipped += 1
            continue
        cur = conn.execute(
            "INSERT INTO locations(code,name,data_json,status,created_by,owner_id,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?)",
            ("", "", json.dumps(loc["data"], ensure_ascii=False), "draft",
             user["id"], user["id"], now, now),
        )
        lid = cur.lastrowid
        conn.execute("UPDATE locations SET code=?, modified_at=?, modified_by=? WHERE id=?",
                     (_format_code(conn, lid), now, user["id"], lid))
        wv = _import_wil(loc.get("wil"), choices.get(str(loc["row"])) or {})
        if wv:
            conn.execute(f"UPDATE locations SET {_WIL_SET} WHERE id=?", (*wv, lid))
        db.log_activity(conn, lid, user["id"], "create", "import", now)
        for i, it in enumerate(loc["inventory"]):
            conn.execute(
                "INSERT INTO inventory_items(location_id,nama_barang,merk_type,jumlah,"
                "sn_tagging,keterangan,sort_order) VALUES(?,?,?,?,?,?,?)",
                (lid, it.get("nama_barang", ""), it.get("merk_type", ""), it.get("jumlah", ""),
                 it.get("sn_tagging", ""), it.get("keterangan", ""), i),
            )
        created += 1
    conn.commit()
    audit(conn, user, "import", "location", "", f"{created} lokasi, {skipped} dilewati")
    return {"ok": True, "created": created, "skipped": skipped}


def _import_wil(w: dict | None, ch: dict):
    """Kolom wilayah untuk satu baris import (atau None = tanpa wilayah)."""
    if not w or w.get("status") == "empty":
        return None
    raw = w.get("raw") or {}
    try:
        if ch.get("kode"):
            return _wil_values({"mode": "official", "kode": ch["kode"], **raw})
        if ch.get("manual") and all(raw.get(k) for k in ("desa", "kec", "kab", "prov")):
            return _wil_values({"mode": "manual", **raw})
        if ch.get("empty"):
            return None
        if w.get("status") in ("ok", "desa_manual"):
            return _wil_values(w["wil"])
    except HTTPException:
        return None
    return None
