"""Lokasi (BAA per lokasi) + item inventory."""
from __future__ import annotations

import json
import re
import shutil
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from .. import config, db
from ..deps import audit, current_user, get_db, require_admin, require_editor

from ..services import wilayah
from .attachments import attachment_list
from .scan import scan_info

router = APIRouter(prefix="/api/locations", tags=["locations"])

def _format_code(conn, n: int) -> str:
    """Kode urut dari nomor baris + awalan project, mis. LOK_00001. Minimal 5
    digit (auto melebar kalau > 99999)."""
    return db.format_code(conn, n)


def _scope(user):
    """Semua user boleh MELIHAT lokasi siapa pun (read-all). Pembatasan hanya
    berlaku pada aksi tulis (lihat _can_write)."""
    return "", []


def _can_write(user, row) -> bool:
    """Boleh mengubah/hapus lokasi ini? admin selalu; operator hanya miliknya.
    (viewer sudah ditolak oleh require_editor)."""
    return user["role"] == "admin" or row["owner_id"] == user["id"]


class LocationIn(BaseModel):
    name: str = ""
    data: dict = {}
    status: str = "draft"
    wil: dict | None = None           # {mode, kode, desa, kec, kab, prov}; None = tidak diubah, {} = kosongkan
    wil_kode: str | None = None       # (lama) pilih desa resmi lewat kode saja
    sid: str | None = None            # identitas lokasi dari klien; None = tidak diubah, "" = kosongkan (admin)


WIL_MODES = ("official", "desa_manual", "manual")


def _wil_values(w: dict | None, kode: str | None = None):
    """Kolom (kode, desa, kec, kab, prov, mode) dari isian wilayah, atau None bila tidak diubah.
    Nama disimpan sesuai tulisan teknisi; kosong = pakai nama resmi."""
    if w is None and kode is not None:
        w = {"mode": "official", "kode": kode} if kode.strip() else {}
    if w is None:
        return None
    mode = (w.get("mode") or "").strip()
    if not mode:
        return (None,) * 6
    if mode not in WIL_MODES:
        raise HTTPException(400, "Invalid wilayah mode")
    t = {k: re.sub(r"\s+", " ", str(w.get(k) or "")).strip()[:120] for k in ("desa", "kec", "kab", "prov")}
    k = str(w.get("kode") or "").strip()
    if mode == "official":
        off = wilayah.info(k)
        if not off:
            raise HTTPException(400, "Unknown wilayah code")
        off["kab"] = wilayah.short_kab(off["kab"])
    elif mode == "desa_manual":
        off = wilayah.kec_info(k)
        if not off:
            raise HTTPException(400, "Pick an official kecamatan")
        off["kab"] = wilayah.short_kab(off["kab"])
        off["desa"] = ""
        if not t["desa"]:
            raise HTTPException(400, "Type the desa/kelurahan name")
    else:
        off = {"kode": None, "desa": "", "kec": "", "kab": "", "prov": ""}
        if not all(t.values()):
            raise HTTPException(400, "Fill desa, kecamatan, kab/kota and provinsi")
    return (off["kode"], t["desa"] or off["desa"], t["kec"] or off["kec"], t["kab"] or off["kab"],
            t["prov"] or off["prov"], mode)


# ---------- SID (identitas lokasi dari klien; label & aturan di pengaturan project 'sid_config') ----------
def norm_sid(conn, v) -> str:
    """Rapikan & validasi SID: tanpa spasi, huruf/angka saja, panjang maks sesuai pengaturan,
    kapital bila 'uppercase' aktif. Kosong = tidak ada SID."""
    cfg = db.sid_config(conn)
    s = re.sub(r"\s+", "", str(v or ""))
    if cfg.get("uppercase", True):
        s = s.upper()
    if not s:
        return ""
    lab = cfg.get("label") or "SID"
    if not re.fullmatch(r"[A-Za-z0-9]+", s):
        raise HTTPException(400, f"{lab} may only contain letters and numbers")
    if len(s) > int(cfg.get("max_len") or 20):
        raise HTTPException(400, f"{lab} is longer than {int(cfg.get('max_len') or 20)} characters")
    return s


def sid_owner(conn, sid: str, exclude: int = 0):
    """Lokasi aktif lain yang sudah memakai SID ini (huruf besar/kecil dianggap sama), atau None."""
    if not sid:
        return None
    return conn.execute("SELECT id, code FROM locations WHERE deleted_at IS NULL AND id<>? AND upper(sid)=upper(?)",
                        (exclude, sid)).fetchone()


def check_sid_free(conn, sid: str, exclude: int = 0) -> None:
    o = sid_owner(conn, sid, exclude)
    if o:
        raise HTTPException(409, f"{db.sid_config(conn).get('label') or 'SID'} {sid} is already used by {o['code']}")


def _apply_sid(conn, user, row, raw) -> bool:
    """SID: admin bebas; operator hanya boleh MENGISI yang masih kosong (ubah -> lewat permintaan ke admin).
    True bila berubah (belum di-commit)."""
    new_sid, cur_sid = norm_sid(conn, raw), (row["sid"] or "")
    if new_sid == cur_sid:
        return False
    if user["role"] != "admin" and cur_sid:
        raise HTTPException(403, f"{db.sid_config(conn).get('label') or 'SID'} is already filled — request a change from the admin")
    check_sid_free(conn, new_sid, row["id"])
    conn.execute("UPDATE locations SET sid=?, updated_at=? WHERE id=?", (new_sid or None, db.now_iso(), row["id"]))
    db.log_activity(conn, row["id"], user["id"], "sid", f"{cur_sid or '—'} -> {new_sid or '—'}")
    return True


_WIL_PREFIX = re.compile(r"^(kabupaten|kab|kota|kecamatan|kec|desa|kelurahan|kel)\b\s*")


def _norm_txt(s: str, prefix: bool = False) -> str:
    """Huruf kecil, tanda baca jadi spasi, spasi dirapatkan (opsional buang 'Kab.'/'Kec.'/'Desa')."""
    s = re.sub(r"[^\w]+", " ", str(s or "").lower()).strip()
    s = re.sub(r"\s+", " ", s)
    return _WIL_PREFIX.sub("", s).strip() if prefix else s


def dup_key(name: str, desa: str = "", kec: str = "", kab: str = "") -> str | None:
    """Kunci lokasi kembar = nama + wilayah (desa|kec|kab, tanpa awalan). Tanpa nama = tidak dicek.
    Nama sama di desa lain bukan kembar (mis. 'SD NEGERI 1' wajar ada di banyak desa)."""
    n = _norm_txt(name)
    if not n:
        return None
    return n + "#" + "|".join(_norm_txt(x, True) for x in (desa, kec, kab))


def _row_name(r) -> str:
    nm = (r["name"] or "").strip()
    if not nm:
        try:
            nm = ((json.loads(r["data_json"]) or {}).get("nama_lokasi") or "").strip()
        except Exception:
            nm = ""
    return nm


def dup_groups(conn) -> dict[str, list]:
    """{kunci: [baris lokasi aktif]} — hanya kunci yang dipakai ≥ 2 lokasi."""
    g: dict[str, list] = {}
    for r in conn.execute(
            """SELECT l.id, l.code, l.name, l.data_json, l.status, l.wil_desa, l.wil_kec, l.wil_kab,
                      COALESCE(NULLIF(TRIM(o.full_name),''), o.username, '—') AS owner_name
               FROM locations l LEFT JOIN users o ON o.id = l.owner_id WHERE l.deleted_at IS NULL"""):
        k = dup_key(_row_name(r), r["wil_desa"], r["wil_kec"], r["wil_kab"])
        if k:
            g.setdefault(k, []).append(r)
    return {k: v for k, v in g.items() if len(v) > 1}


def _dup_brief(r) -> dict:
    return {"id": r["id"], "code": r["code"], "name": _row_name(r), "status": r["status"],
            "desa": r["wil_desa"] or "", "kab": r["wil_kab"] or "", "owner_name": r["owner_name"]}


def _wil_dict(row) -> dict | None:
    if "wil_desa" not in row.keys() or not row["wil_desa"]:
        return None
    mode = row["wil_mode"] or ("official" if row["wil_kode"] else "manual")
    k = row["wil_kode"]
    off = (wilayah.info(k) if mode == "official" else wilayah.kec_info(k) if mode == "desa_manual" else None) or {}
    if off.get("kab"):
        off["kab"] = wilayah.short_kab(off["kab"])
    return {"mode": mode, "kode": k, "desa": row["wil_desa"], "kec": row["wil_kec"], "kab": row["wil_kab"],
            "prov": row["wil_prov"], "kel": bool(k and mode == "official" and k.split(".")[-1].startswith("1")),
            "off": {x: off.get(x, "") for x in ("desa", "kec", "kab", "prov")}}


_WIL_SET = "wil_kode=?,wil_desa=?,wil_kec=?,wil_kab=?,wil_prov=?,wil_mode=?"


class InventoryItem(BaseModel):
    nama_barang: str = ""
    merk_type: str = ""
    jumlah: str = ""
    sn_tagging: str = ""
    keterangan: str = ""


class InventoryIn(BaseModel):
    items: list[InventoryItem]


def _location_dict(conn: sqlite3.Connection, row, user=None) -> dict:
    import json
    owner_id = row["owner_id"] if "owner_id" in row.keys() else None
    owner_name = None
    if owner_id:
        o = conn.execute("SELECT COALESCE(NULLIF(TRIM(full_name),''),username) nm FROM users WHERE id=?",
                         (owner_id,)).fetchone()
        owner_name = o["nm"] if o else None
    can_edit = bool(user) and (user["role"] == "admin" or (user["role"] == "operator" and owner_id == user["id"]))
    my_request = None
    if user:
        rr = conn.execute(
            "SELECT status FROM edit_requests WHERE location_id=? AND requester_id=? AND kind='edit' "
            "ORDER BY id DESC LIMIT 1", (row["id"], user["id"]),
        ).fetchone()
        my_request = rr["status"] if rr else None
    sr = conn.execute("SELECT value_new, requester_id FROM edit_requests WHERE location_id=? AND kind='sid' "
                      "AND status='pending' ORDER BY id DESC LIMIT 1", (row["id"],)).fetchone()
    inv = conn.execute(
        "SELECT id,nama_barang,merk_type,jumlah,sn_tagging,keterangan,sort_order "
        "FROM inventory_items WHERE location_id=? ORDER BY sort_order,id", (row["id"],)
    ).fetchall()
    photos = conn.execute(
        "SELECT id,category,orig_name,filename,ocr_serial,matched_by,created_at "
        "FROM photos WHERE location_id=? ORDER BY id", (row["id"],)
    ).fetchall()
    return {
        "id": row["id"], "code": row["code"], "name": row["name"],
        "data": json.loads(row["data_json"]), "status": row["status"],
        "created_at": row["created_at"], "updated_at": row["updated_at"],
        "owner_id": owner_id, "owner_name": owner_name, "can_edit": can_edit,
        "my_request": my_request,
        "inventory": [dict(i) for i in inv],
        "photos": [dict(p) for p in photos],
        "scan": scan_info(conn, row["id"]),
        "wilayah": _wil_dict(row),
        "sid": row["sid"] or "" if "sid" in row.keys() else "",
        "complete_at": row["complete_at"] if "complete_at" in row.keys() else None,
        "sid_request": {"value": sr["value_new"], "mine": bool(user) and sr["requester_id"] == user["id"]} if sr else None,
        "attachments": attachment_list(conn, row["id"]),
    }


@router.get("")
def list_locations(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    q: str = Query(""),
    status: str = Query("all"),
    creator: int = Query(0),          # filter berdasarkan pembuat (user id); 0 = semua
    owner: int = Query(0),            # filter berdasarkan pemilik saat ini (user id); 0 = semua
    date: str = Query(""),            # filter tanggal dibuat (YYYY-MM-DD, waktu lokal)
    wil: str = Query(""),             # filter wilayah: kode provinsi/kab/kec, atau "none" = belum diisi
    dup: int = Query(0),              # 1 = hanya lokasi yang kemungkinan kembar (nama + wilayah sama)
    conn: sqlite3.Connection = Depends(get_db),
    user=Depends(current_user),
):
    """Daftar lokasi terpaginasi + agregat (foto, inventory) dihitung di SQL.

    Ringan walau data ribuan: hanya ``size`` baris per halaman, tanpa N+1.
    """
    import json
    where, params = ["l.deleted_at IS NULL"], []
    sc, scp = _scope(user)
    if sc:
        where.append(sc); params.extend(scp)
    if q.strip():
        like = f"%{q.strip()}%"
        where.append("(l.code LIKE ? OR l.name LIKE ? OR l.old_codes LIKE ? OR l.sid LIKE ?)")
        params += [like, like, like, like]
    if status in ("draft", "selesai"):
        where.append("l.status = ?")
        params.append(status)
    if creator:
        where.append("l.created_by = ?")
        params.append(creator)
    if owner:
        where.append("l.owner_id = ?")
        params.append(owner)
    if date.strip():
        where.append("date(l.created_at,'localtime') = ?")
        params.append(date.strip())
    if wil.strip():
        w, p = wil_where(wil, "l.")
        where.append(w); params += p
    groups = dup_groups(conn)
    dup_n = {r["id"]: len(v) for v in groups.values() for r in v}
    if dup:
        where.append(f"l.id IN ({','.join(str(i) for i in dup_n) or '0'})")
    wsql = ("WHERE " + " AND ".join(where)) if where else ""

    total = conn.execute(
        f"SELECT COUNT(*) AS c FROM locations l {wsql}", params
    ).fetchone()["c"]

    offset = (page - 1) * size
    rows = conn.execute(
        f"""SELECT l.id, l.code, l.name, l.status, l.data_json, l.created_by, l.owner_id, l.sid,
              l.created_at, l.updated_at, l.modified_at, l.modified_by,
              COALESCE(NULLIF(TRIM(m.full_name),''), m.username) AS modifier_name,
              COALESCE(NULLIF(TRIM(u.full_name),''), u.username, '—') AS creator_name,
              COALESCE(NULLIF(TRIM(o.full_name),''), o.username, '—') AS owner_name,
              (SELECT COUNT(*) FROM photos p WHERE p.location_id = l.id) AS photo_count,
              (SELECT GROUP_CONCAT(DISTINCT category) FROM photos p WHERE p.location_id = l.id) AS photo_cats,
              (SELECT COUNT(*) FROM inventory_items i WHERE i.location_id = l.id) AS inv_count,
              EXISTS(SELECT 1 FROM scan_docs s WHERE s.location_id = l.id) AS has_scan,
              l.wil_kode, l.wil_desa, l.wil_kab, l.wil_mode,
              (SELECT COUNT(*) FROM inventory_items i WHERE i.location_id = l.id AND (
                   TRIM(COALESCE(i.nama_barang,'')) = '' OR TRIM(COALESCE(i.merk_type,'')) = '' OR
                   TRIM(COALESCE(i.jumlah,'')) = '' OR TRIM(COALESCE(i.sn_tagging,'')) = '' OR
                   TRIM(COALESCE(i.keterangan,'')) = '')) AS inv_bad
            FROM locations l LEFT JOIN users u ON u.id = l.created_by
                              LEFT JOIN users o ON o.id = l.owner_id
                              LEFT JOIN users m ON m.id = l.modified_by
            {wsql} ORDER BY l.id DESC LIMIT ? OFFSET ?""",
        params + [size, offset],
    ).fetchall()

    is_admin = user["role"] == "admin"
    result = [
        {
            "id": r["id"], "code": r["code"], "name": r["name"], "status": r["status"],
            "data": json.loads(r["data_json"]), "photo_count": r["photo_count"],
            "inv_count": r["inv_count"], "updated_at": r["updated_at"],
            "created_at": r["created_at"], "created_by": r["created_by"],
            "modified_at": r["modified_at"], "modifier_name": r["modifier_name"],
            "creator_name": r["creator_name"],
            "owner_id": r["owner_id"], "owner_name": r["owner_name"],
            "photo_cats": (r["photo_cats"].split(",") if r["photo_cats"] else []),
            "inv_ok": r["inv_count"] > 0 and r["inv_bad"] == 0,
            "inv_full": max(0, r["inv_count"] - r["inv_bad"]),
            "has_scan": bool(r["has_scan"]),
            "wil_kode": r["wil_kode"], "wil_desa": r["wil_desa"], "wil_kab": r["wil_kab"] or "",
            "wil_mode": (r["wil_mode"] or ("official" if r["wil_kode"] else None)) if r["wil_desa"] else None,
            "can_delete": is_admin or r["owner_id"] == user["id"],
            "dup_n": dup_n.get(r["id"], 0),
            "sid": r["sid"] or "",
        }
        for r in rows
    ]
    return {"rows": result, "total": total, "page": page, "size": size, "dup_total": len(dup_n)}


@router.get("/creators")
def location_creators(conn: sqlite3.Connection = Depends(get_db), user=Depends(current_user)):
    """Daftar pembuat & pemilik entry (untuk filter Log Lokasi)."""
    sc, scp = _scope(user)
    extra = (" AND " + sc) if sc else ""
    def by(col):
        return [dict(r) for r in conn.execute(
            f"""SELECT u.id, COALESCE(NULLIF(TRIM(u.full_name),''), u.username) AS name,
                      COUNT(l.id) AS n
               FROM users u JOIN locations l ON l.{col} = u.id
               WHERE l.deleted_at IS NULL{extra}
               GROUP BY u.id ORDER BY name COLLATE NOCASE""", scp).fetchall()]
    return {"creators": by("created_by"), "owners": by("owner_id")}


@router.get("/sid-check")
def sid_check(sid: str = "", exclude: int = 0, conn: sqlite3.Connection = Depends(get_db), user=Depends(current_user)):
    """Cek SID saat diketik: bentuk rapi + sudah dipakai lokasi lain atau belum."""
    try:
        v = norm_sid(conn, sid)
    except HTTPException as e:
        return {"sid": sid, "ok": False, "error": e.detail}
    o = sid_owner(conn, v, exclude)
    return {"sid": v, "ok": not o, "used_by": o["code"] if o else None}


class SidIn(BaseModel):
    sid: str = ""


@router.put("/{loc_id}/sid")
def set_sid(loc_id: int, body: SidIn, conn: sqlite3.Connection = Depends(get_db), user=Depends(require_editor)):
    row = conn.execute("SELECT * FROM locations WHERE id=? AND deleted_at IS NULL", (loc_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Location not found")
    if not _can_write(user, row):
        raise HTTPException(403, "Not your location")
    if _apply_sid(conn, user, row, body.sid):
        conn.commit()
        audit(conn, user, "set_sid", "location", loc_id, f"{row['code']}: {row['sid'] or '—'} -> {norm_sid(conn, body.sid) or '—'}")
    return _location_dict(conn, conn.execute("SELECT * FROM locations WHERE id=?", (loc_id,)).fetchone(), user)


@router.get("/options")
def location_options(conn: sqlite3.Connection = Depends(get_db), user=Depends(current_user)):
    """Daftar ringan (id, code, nama) untuk dropdown pemilih lokasi di Entry BAA."""
    import json
    sc, scp = _scope(user)
    wsql = "WHERE l.deleted_at IS NULL" + ((" AND " + sc) if sc else "")
    rows = conn.execute(
        f"SELECT l.id, l.code, l.name, l.status, l.data_json, l.sid FROM locations l {wsql} ORDER BY l.id DESC", scp
    ).fetchall()
    opts = []
    for r in rows:
        nama = r["name"] or ""
        if not nama:
            try:
                nama = (json.loads(r["data_json"]) or {}).get("nama_lokasi", "") or ""
            except Exception:
                nama = ""
        opts.append({"id": r["id"], "code": r["code"], "nama": nama, "status": r["status"], "sid": r["sid"] or ""})
    return {"options": opts, "total": len(opts)}


@router.post("")
def create_location(body: LocationIn, conn: sqlite3.Connection = Depends(get_db),
                    user=Depends(require_editor)):
    import json
    now = db.now_iso()
    # Insert dulu dengan placeholder unik, lalu kunci kode dari id AUTOINCREMENT.
    # id dijamin unik & monoton oleh SQLite (write ter-serialisasi), jadi kode
    # urut aman dibuat paralel banyak user tanpa koordinasi.
    wv = _wil_values(body.wil, body.wil_kode) or (None,) * 6
    sid = norm_sid(conn, body.sid) if body.sid else ""
    check_sid_free(conn, sid)
    cur = conn.execute(
        "INSERT INTO locations(code,name,data_json,status,created_by,owner_id,created_at,updated_at,"
        "wil_kode,wil_desa,wil_kec,wil_kab,wil_prov,wil_mode,sid) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("", body.name, json.dumps(body.data, ensure_ascii=False), body.status,
         user["id"], user["id"], now, now, *wv, sid or None),
    )
    code = _format_code(conn, cur.lastrowid)
    conn.execute("UPDATE locations SET code=?, modified_at=?, modified_by=? WHERE id=?",
                 (code, now, user["id"], cur.lastrowid))
    db.log_activity(conn, cur.lastrowid, user["id"], "create", "", now)
    conn.commit()
    audit(conn, user, "create", "location", cur.lastrowid, code)
    row = conn.execute("SELECT * FROM locations WHERE id=?", (cur.lastrowid,)).fetchone()
    return _location_dict(conn, row, user)


def wil_where(wil: str, alias: str = "") -> tuple[str, list]:
    """Klausa filter wilayah: 'none' = belum diisi; selain itu kode prefiks (prov/kab/kec/desa)."""
    wil = wil.strip()
    if wil == "none":
        return f"({alias}wil_desa IS NULL OR {alias}wil_desa = '')", []
    if wil == "manual":
        return f"({alias}wil_mode IN ('desa_manual','manual'))", []
    return f"({alias}wil_kode = ? OR {alias}wil_kode LIKE ?)", [wil, wil + ".%"]


class WilBulkIn(BaseModel):
    ids: list[int]
    wil_kode: str


@router.post("/wilayah-bulk")
def set_wilayah_bulk(body: WilBulkIn, conn: sqlite3.Connection = Depends(get_db),
                     user=Depends(require_admin)):
    """Admin mengisi wilayah banyak lokasi sekaligus (mengganti yang sudah ada)."""
    wv = _wil_values({"mode": "official", "kode": body.wil_kode})
    n = 0
    for lid in body.ids:
        r = conn.execute("SELECT id, wil_kode, wil_mode FROM locations WHERE id=? AND deleted_at IS NULL",
                         (lid,)).fetchone()
        if not r:
            continue
        if r["wil_kode"] != wv[0] or (r["wil_mode"] or "official") != "official":
            conn.execute(f"UPDATE locations SET {_WIL_SET} WHERE id=?", (*wv, lid))
            db.touch_modified(conn, lid, user["id"], "data", "wilayah")
        n += 1
    conn.commit()
    audit(conn, user, "set_wilayah", "location", ",".join(map(str, body.ids)), f"{n} lokasi -> {wv[0]} {wv[1]}")
    return {"ok": True, "count": n}


class WilLinkIn(BaseModel):
    wil_kode: str


@router.get("/{loc_id}/wilayah-suggest")
def wilayah_suggest(loc_id: int, conn: sqlite3.Connection = Depends(get_db), user=Depends(require_admin)):
    """Saran desa resmi untuk lokasi dengan isian wilayah manual."""
    r = conn.execute("SELECT * FROM locations WHERE id=? AND deleted_at IS NULL", (loc_id,)).fetchone()
    if not r or not r["wil_desa"]:
        raise HTTPException(404, "No wilayah to link")
    under = r["wil_kode"] if r["wil_mode"] == "desa_manual" else ""
    return {"items": wilayah.suggest(r["wil_desa"], under, f'{r["wil_kec"] or ""} {r["wil_kab"] or ""}'),
            "under": under}


@router.post("/{loc_id}/wilayah-link")
def wilayah_link(loc_id: int, body: WilLinkIn, conn: sqlite3.Connection = Depends(get_db),
                 user=Depends(require_admin)):
    """Tautkan isian manual ke desa resmi. Tulisan teknisi (nama) dipertahankan."""
    r = conn.execute("SELECT * FROM locations WHERE id=? AND deleted_at IS NULL", (loc_id,)).fetchone()
    if not r:
        raise HTTPException(404, "Location not found")
    off = wilayah.info(body.wil_kode)
    if not off:
        raise HTTPException(400, "Unknown wilayah code")
    keep = {k: r[f"wil_{k}"] for k in ("desa", "kec", "kab", "prov")}
    wv = _wil_values({"mode": "official", "kode": off["kode"], **keep})
    conn.execute(f"UPDATE locations SET {_WIL_SET} WHERE id=?", (*wv, loc_id))
    db.touch_modified(conn, loc_id, user["id"], "data", "wilayah link")
    conn.commit()
    audit(conn, user, "link_wilayah", "location", loc_id, f"{r['wil_desa']} -> {off['kode']}")
    return {"ok": True, "wilayah": _wil_dict(conn.execute("SELECT * FROM locations WHERE id=?", (loc_id,)).fetchone())}


class TransferIn(BaseModel):
    ids: list[int]
    to_user_id: int


@router.post("/transfer")
def transfer_locations(body: TransferIn, conn: sqlite3.Connection = Depends(get_db),
                       user=Depends(require_admin)):
    """Admin mengalihkan kepemilikan beberapa lokasi ke user lain."""
    tgt = conn.execute("SELECT id, username, full_name, role, active FROM pm_users WHERE id=?",
                       (body.to_user_id,)).fetchone()
    if not tgt:
        raise HTTPException(404, "Target user not found in this project")
    if not tgt["active"]:
        raise HTTPException(400, "Target user is inactive")
    if tgt["role"] == "viewer":
        raise HTTPException(400, "Target user is a viewer (can't work on locations)")
    n = 0
    for lid in body.ids:
        r = conn.execute("SELECT id FROM locations WHERE id=? AND deleted_at IS NULL", (lid,)).fetchone()
        if not r:
            continue
        conn.execute("UPDATE locations SET owner_id=?, updated_at=? WHERE id=?",
                     (body.to_user_id, db.now_iso(), lid))
        n += 1
    conn.commit()
    name = (tgt["full_name"] or tgt["username"]).strip()
    audit(conn, user, "transfer", "location", ",".join(map(str, body.ids)),
          f"{n} lokasi -> {name}")
    return {"ok": True, "count": n, "to": {"id": tgt["id"], "name": name}}


@router.get("/dups")
def location_dups(name: str = Query(""), desa: str = Query(""), kec: str = Query(""), kab: str = Query(""),
                  exclude: int = Query(0), conn: sqlite3.Connection = Depends(get_db), user=Depends(current_user)):
    """Lokasi lain dengan nama + wilayah yang sama (peringatan di BAA Entry; tidak memblokir simpan)."""
    k = dup_key(name, desa, kec, kab)
    if not k:
        return {"rows": []}
    out = []
    for r in conn.execute(
            """SELECT l.id, l.code, l.name, l.data_json, l.status, l.wil_desa, l.wil_kec, l.wil_kab,
                      COALESCE(NULLIF(TRIM(o.full_name),''), o.username, '—') AS owner_name
               FROM locations l LEFT JOIN users o ON o.id = l.owner_id
               WHERE l.deleted_at IS NULL AND l.id <> ?""", (exclude,)):
        if dup_key(_row_name(r), r["wil_desa"], r["wil_kec"], r["wil_kab"]) == k:
            out.append(_dup_brief(r))
    return {"rows": out}


@router.get("/{loc_id}")
def get_location(loc_id: int, conn: sqlite3.Connection = Depends(get_db),
                 user=Depends(current_user)):
    row = conn.execute("SELECT * FROM locations WHERE id=? AND deleted_at IS NULL", (loc_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Location not found")
    return _location_dict(conn, row, user)


@router.put("/{loc_id}")
def update_location(loc_id: int, body: LocationIn, conn: sqlite3.Connection = Depends(get_db),
                    user=Depends(require_editor)):
    import json
    row = conn.execute("SELECT * FROM locations WHERE id=? AND deleted_at IS NULL", (loc_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Location not found")
    if not _can_write(user, row):
        raise HTTPException(403, "Not your location")
    new_json = json.dumps(body.data, ensure_ascii=False)
    wv = _wil_values(body.wil, body.wil_kode)
    wil_changed = wv is not None and tuple(x or None for x in wv) != tuple(
        row[c] or None for c in ("wil_kode", "wil_desa", "wil_kec", "wil_kab", "wil_prov", "wil_mode"))
    if wil_changed:
        conn.execute(f"UPDATE locations SET {_WIL_SET} WHERE id=?", (*wv, loc_id))
    sid_changed = body.sid is not None and _apply_sid(conn, user, row, body.sid)
    changed = (body.name != row["name"] or body.status != row["status"] or wil_changed or sid_changed
               or json.loads(new_json) != json.loads(row["data_json"] or "{}"))
    conn.execute(
        "UPDATE locations SET name=?,data_json=?,status=?,updated_at=? WHERE id=?",
        (body.name, new_json, body.status, db.now_iso(), loc_id),
    )
    if body.status == "selesai" and row["status"] != "selesai":
        # Done hanya bila kelengkapan 100% (data Required, wilayah, inventory, foto, scan — sesuai sakelar project)
        from .progress import loc_completeness
        pct, miss = loc_completeness(conn, conn.execute("SELECT * FROM locations WHERE id=?", (loc_id,)).fetchone())
        if pct < 100:
            conn.rollback()
            raise HTTPException(400, f"Not complete yet ({pct}%) — missing: {', '.join(miss)}")
        conn.execute("UPDATE locations SET done_at=? WHERE id=?", (db.now_iso(), loc_id))
    elif body.status != "selesai" and row["status"] == "selesai":
        conn.execute("UPDATE locations SET done_at=NULL WHERE id=?", (loc_id,))
    if changed:
        data_changed = (json.loads(new_json) != json.loads(row["data_json"] or "{}")
                        or body.name != row["name"] or wil_changed)
        if body.status != row["status"]:
            db.touch_modified(conn, loc_id, user["id"], "done" if body.status == "selesai" else "reopen")
            if data_changed:
                db.log_activity(conn, loc_id, user["id"], "data")
        else:
            db.touch_modified(conn, loc_id, user["id"], "data")
    conn.commit()
    audit(conn, user, "update", "location", loc_id, row["code"])
    return _location_dict(conn, conn.execute("SELECT * FROM locations WHERE id=?", (loc_id,)).fetchone(), user)


@router.put("/{loc_id}/inventory")
def save_inventory(loc_id: int, body: InventoryIn, conn: sqlite3.Connection = Depends(get_db),
                   user=Depends(require_editor)):
    row = conn.execute("SELECT owner_id FROM locations WHERE id=? AND deleted_at IS NULL", (loc_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Location not found")
    if not _can_write(user, row):
        raise HTTPException(403, "Not your location")
    cols = ("nama_barang", "merk_type", "jumlah", "sn_tagging", "keterangan")
    old = [tuple(str(r[c] or "") for c in cols) for r in conn.execute(
        "SELECT * FROM inventory_items WHERE location_id=? ORDER BY sort_order,id", (loc_id,)).fetchall()]
    new = [tuple(str(getattr(it, c) or "") for c in cols) for it in body.items]
    conn.execute("DELETE FROM inventory_items WHERE location_id=?", (loc_id,))
    for i, it in enumerate(body.items):
        conn.execute(
            "INSERT INTO inventory_items(location_id,nama_barang,merk_type,jumlah,"
            "sn_tagging,keterangan,sort_order) VALUES(?,?,?,?,?,?,?)",
            (loc_id, it.nama_barang, it.merk_type, it.jumlah, it.sn_tagging, it.keterangan, i),
        )
    if old != new:
        db.touch_modified(conn, loc_id, user["id"], "inventory", str(len(new)))
    conn.commit()
    audit(conn, user, "save_inventory", "location", loc_id, f"{len(body.items)} item")
    return {"ok": True, "count": len(body.items)}


@router.delete("/{loc_id}")
def delete_location(loc_id: int, conn: sqlite3.Connection = Depends(get_db),
                    user=Depends(require_editor)):
    """Soft-delete: pindahkan ke 'Lokasi Terhapus' (data & foto tetap ada,
    bisa dipulihkan admin). Tidak menghapus baris/relasi/foto."""
    row = conn.execute("SELECT * FROM locations WHERE id=? AND deleted_at IS NULL", (loc_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Location not found")
    if not _can_write(user, row):
        raise HTTPException(403, "Only an admin or the owner can delete this")
    conn.execute("UPDATE locations SET deleted_at=?, deleted_by=? WHERE id=?",
                 (db.now_iso(), user["id"], loc_id))
    conn.commit()
    audit(conn, user, "delete", "location", loc_id, row["code"])
    return {"ok": True}


# ===== Lokasi Terhapus (soft-delete) — admin only =====
@router.get("/trash/list")
def list_deleted(conn: sqlite3.Connection = Depends(get_db), user=Depends(require_admin)):
    rows = conn.execute(
        """SELECT l.id, l.code, l.name, l.data_json, l.deleted_at,
                  COALESCE(NULLIF(TRIM(d.full_name),''), d.username, '—') AS deleted_by_name,
                  COALESCE(NULLIF(TRIM(o.full_name),''), o.username, '—') AS owner_name,
                  (SELECT COUNT(*) FROM inventory_items i WHERE i.location_id=l.id) AS inv_count,
                  (SELECT COUNT(*) FROM photos p WHERE p.location_id=l.id) AS photo_count
           FROM locations l LEFT JOIN users d ON d.id=l.deleted_by
                            LEFT JOIN users o ON o.id=l.owner_id
           WHERE l.deleted_at IS NOT NULL ORDER BY l.deleted_at DESC"""
    ).fetchall()
    import json
    out = []
    for r in rows:
        nama = r["name"] or ""
        if not nama:
            try:
                nama = (json.loads(r["data_json"]) or {}).get("nama_lokasi", "") or ""
            except Exception:
                nama = ""
        out.append({"id": r["id"], "code": r["code"], "name": nama, "deleted_at": r["deleted_at"],
                    "deleted_by_name": r["deleted_by_name"], "owner_name": r["owner_name"],
                    "inv_count": r["inv_count"], "photo_count": r["photo_count"]})
    return {"rows": out, "total": len(out)}


@router.post("/{loc_id}/restore")
def restore_location(loc_id: int, conn: sqlite3.Connection = Depends(get_db),
                     user=Depends(require_admin)):
    row = conn.execute("SELECT code, sid FROM locations WHERE id=? AND deleted_at IS NOT NULL", (loc_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Deleted location not found")
    # SID-nya sudah dipakai lokasi lain selama terhapus -> dipulihkan tanpa SID (SID harus unik)
    clash = sid_owner(conn, row["sid"] or "", loc_id)
    conn.execute("UPDATE locations SET deleted_at=NULL, deleted_by=NULL, updated_at=?" + (", sid=NULL" if clash else "")
                 + " WHERE id=?", (db.now_iso(), loc_id))
    if clash:
        db.log_activity(conn, loc_id, user["id"], "sid", f"{row['sid']} -> — (used by {clash['code']})")
    conn.commit()
    audit(conn, user, "restore", "location", loc_id, row["code"])
    return {"ok": True, "sid_cleared": row["sid"] if clash else None, "sid_used_by": clash["code"] if clash else None}


@router.delete("/{loc_id}/purge")
def purge_location(loc_id: int, conn: sqlite3.Connection = Depends(get_db),
                   user=Depends(require_admin)):
    """Hapus permanen (baris + relasi + folder foto). Hanya dari trash."""
    row = conn.execute("SELECT code FROM locations WHERE id=? AND deleted_at IS NOT NULL", (loc_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Deleted location not found")
    conn.execute("DELETE FROM locations WHERE id=?", (loc_id,))  # cascade -> inventory & photos
    conn.commit()
    shutil.rmtree(db.images_dir(conn) / row["code"], ignore_errors=True)
    shutil.rmtree(db.docs_dir(conn) / row["code"], ignore_errors=True)
    audit(conn, user, "purge", "location", loc_id, row["code"])
    return {"ok": True}
