"""Lokasi (BAA per lokasi) + item inventory."""
from __future__ import annotations

import shutil
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from .. import config, db
from ..deps import audit, current_user, get_db, require_admin, require_editor

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
            "SELECT status FROM edit_requests WHERE location_id=? AND requester_id=? "
            "ORDER BY id DESC LIMIT 1", (row["id"], user["id"]),
        ).fetchone()
        my_request = rr["status"] if rr else None
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
    }


@router.get("")
def list_locations(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    q: str = Query(""),
    status: str = Query("all"),
    creator: int = Query(0),          # filter berdasarkan pembuat (user id); 0 = semua
    date: str = Query(""),            # filter tanggal dibuat (YYYY-MM-DD, waktu lokal)
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
        where.append("(l.code LIKE ? OR l.name LIKE ?)")
        params += [like, like]
    if status in ("draft", "selesai"):
        where.append("l.status = ?")
        params.append(status)
    if creator:
        where.append("l.created_by = ?")
        params.append(creator)
    if date.strip():
        where.append("date(l.created_at,'localtime') = ?")
        params.append(date.strip())
    wsql = ("WHERE " + " AND ".join(where)) if where else ""

    total = conn.execute(
        f"SELECT COUNT(*) AS c FROM locations l {wsql}", params
    ).fetchone()["c"]

    offset = (page - 1) * size
    rows = conn.execute(
        f"""SELECT l.id, l.code, l.name, l.status, l.data_json, l.created_by, l.owner_id,
              l.created_at, l.updated_at, l.modified_at, l.modified_by,
              COALESCE(NULLIF(TRIM(m.full_name),''), m.username) AS modifier_name,
              COALESCE(NULLIF(TRIM(u.full_name),''), u.username, '—') AS creator_name,
              COALESCE(NULLIF(TRIM(o.full_name),''), o.username, '—') AS owner_name,
              (SELECT COUNT(*) FROM photos p WHERE p.location_id = l.id) AS photo_count,
              (SELECT GROUP_CONCAT(DISTINCT category) FROM photos p WHERE p.location_id = l.id) AS photo_cats,
              (SELECT COUNT(*) FROM inventory_items i WHERE i.location_id = l.id) AS inv_count,
              EXISTS(SELECT 1 FROM scan_docs s WHERE s.location_id = l.id) AS has_scan,
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
            "can_delete": is_admin or r["owner_id"] == user["id"],
        }
        for r in rows
    ]
    return {"rows": result, "total": total, "page": page, "size": size}


@router.get("/creators")
def location_creators(conn: sqlite3.Connection = Depends(get_db), user=Depends(current_user)):
    """Daftar pembuat entry (untuk filter Log Lokasi)."""
    sc, scp = _scope(user)
    extra = (" AND " + sc) if sc else ""
    rows = conn.execute(
        f"""SELECT u.id, COALESCE(NULLIF(TRIM(u.full_name),''), u.username) AS name,
                  COUNT(l.id) AS n
           FROM users u JOIN locations l ON l.owner_id = u.id
           WHERE l.deleted_at IS NULL{extra}
           GROUP BY u.id ORDER BY name COLLATE NOCASE""", scp
    ).fetchall()
    return {"creators": [dict(r) for r in rows]}


@router.get("/options")
def location_options(conn: sqlite3.Connection = Depends(get_db), user=Depends(current_user)):
    """Daftar ringan (id, code, nama) untuk dropdown pemilih lokasi di Entry BAA."""
    import json
    sc, scp = _scope(user)
    wsql = "WHERE l.deleted_at IS NULL" + ((" AND " + sc) if sc else "")
    rows = conn.execute(
        f"SELECT l.id, l.code, l.name, l.status, l.data_json FROM locations l {wsql} ORDER BY l.id DESC", scp
    ).fetchall()
    opts = []
    for r in rows:
        nama = r["name"] or ""
        if not nama:
            try:
                nama = (json.loads(r["data_json"]) or {}).get("nama_lokasi", "") or ""
            except Exception:
                nama = ""
        opts.append({"id": r["id"], "code": r["code"], "nama": nama, "status": r["status"]})
    return {"options": opts, "total": len(opts)}


@router.post("")
def create_location(body: LocationIn, conn: sqlite3.Connection = Depends(get_db),
                    user=Depends(require_editor)):
    import json
    now = db.now_iso()
    # Insert dulu dengan placeholder unik, lalu kunci kode dari id AUTOINCREMENT.
    # id dijamin unik & monoton oleh SQLite (write ter-serialisasi), jadi kode
    # urut aman dibuat paralel banyak user tanpa koordinasi.
    cur = conn.execute(
        "INSERT INTO locations(code,name,data_json,status,created_by,owner_id,created_at,updated_at) "
        "VALUES(?,?,?,?,?,?,?,?)",
        ("", body.name, json.dumps(body.data, ensure_ascii=False), body.status,
         user["id"], user["id"], now, now),
    )
    code = _format_code(conn, cur.lastrowid)
    conn.execute("UPDATE locations SET code=?, modified_at=?, modified_by=? WHERE id=?",
                 (code, now, user["id"], cur.lastrowid))
    db.log_activity(conn, cur.lastrowid, user["id"], "create", "", now)
    conn.commit()
    audit(conn, user, "create", "location", cur.lastrowid, code)
    row = conn.execute("SELECT * FROM locations WHERE id=?", (cur.lastrowid,)).fetchone()
    return _location_dict(conn, row, user)


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
    changed = (body.name != row["name"] or body.status != row["status"]
               or json.loads(new_json) != json.loads(row["data_json"] or "{}"))
    conn.execute(
        "UPDATE locations SET name=?,data_json=?,status=?,updated_at=? WHERE id=?",
        (body.name, new_json, body.status, db.now_iso(), loc_id),
    )
    if body.status == "selesai" and row["status"] != "selesai":
        conn.execute("UPDATE locations SET done_at=? WHERE id=?", (db.now_iso(), loc_id))
    elif body.status != "selesai" and row["status"] == "selesai":
        conn.execute("UPDATE locations SET done_at=NULL WHERE id=?", (loc_id,))
    if changed:
        data_changed = json.loads(new_json) != json.loads(row["data_json"] or "{}") or body.name != row["name"]
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
    row = conn.execute("SELECT code FROM locations WHERE id=? AND deleted_at IS NOT NULL", (loc_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Deleted location not found")
    conn.execute("UPDATE locations SET deleted_at=NULL, deleted_by=NULL, updated_at=? WHERE id=?",
                 (db.now_iso(), loc_id))
    conn.commit()
    audit(conn, user, "restore", "location", loc_id, row["code"])
    return {"ok": True}


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
