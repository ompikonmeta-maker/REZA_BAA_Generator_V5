"""Pengaturan aplikasi: field lokasi (custom fields), kategori foto + kata kunci."""
from __future__ import annotations

import json
import sqlite3

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from .. import db
from ..deps import audit, current_user, get_db, require_admin

router = APIRouter(prefix="/api/settings", tags=["settings"])


class LocationFields(BaseModel):
    fields: list[dict]


class PhotoCategories(BaseModel):
    categories: list[dict]


class AppTitle(BaseModel):
    title: str


class InvItems(BaseModel):
    items: list[str]


class ItemMerks(BaseModel):
    merks: dict[str, list[str]]


class InvKeterangan(BaseModel):
    keterangan: list[str]


@router.get("")
def get_settings(conn: sqlite3.Connection = Depends(get_db), user=Depends(current_user)):
    return {
        "app_title": db.app_title(conn),
        "location_fields": db.get_setting(conn, "location_fields", []),
        "photo_categories": db.get_setting(conn, "photo_categories", []),
        "default_inventory_items": db.get_setting(conn, "default_inventory_items", []),
        "item_merks": db.get_setting(conn, "item_merks", {}),
        "inventory_keterangan": db.get_setting(conn, "inventory_keterangan", []),
        "ocr_available": _ocr_available(),
    }


def _ocr_available() -> bool:
    from ..services import ocr
    return ocr.available()


@router.put("/location-fields")
def update_location_fields(body: LocationFields, conn: sqlite3.Connection = Depends(get_db),
                           user=Depends(require_admin)):
    db.set_setting(conn, "location_fields", body.fields)
    conn.commit()
    audit(conn, user, "update", "settings", "location_fields")
    return {"ok": True, "location_fields": body.fields}


@router.put("/photo-categories")
def update_photo_categories(body: PhotoCategories, conn: sqlite3.Connection = Depends(get_db),
                            user=Depends(require_admin)):
    db.set_setting(conn, "photo_categories", body.categories)
    conn.commit()
    audit(conn, user, "update", "settings", "photo_categories")
    return {"ok": True, "photo_categories": body.categories}


@router.put("/app-title")
def update_app_title(body: AppTitle, conn: sqlite3.Connection = Depends(get_db),
                     user=Depends(require_admin)):
    conn.execute("INSERT INTO hub.settings(key, value_json) VALUES('app_title', ?) "
                 "ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json",
                 (json.dumps(body.title.strip() or "BAA Generator"),))
    conn.commit()
    return {"ok": True}


@router.put("/default-inventory-items")
def update_default_inventory(body: InvItems, conn: sqlite3.Connection = Depends(get_db),
                             user=Depends(require_admin)):
    items = [x.strip() for x in body.items if x.strip()]
    db.set_setting(conn, "default_inventory_items", items)
    conn.commit()
    audit(conn, user, "update", "settings", "default_inventory_items")
    return {"ok": True, "items": items}


@router.put("/item-merks")
def update_item_merks(body: ItemMerks, conn: sqlite3.Connection = Depends(get_db),
                      user=Depends(require_admin)):
    merks = {
        k.strip(): [x.strip() for x in v if x.strip()]
        for k, v in body.merks.items() if k.strip()
    }
    db.set_setting(conn, "item_merks", merks)
    conn.commit()
    audit(conn, user, "update", "settings", "item_merks")
    return {"ok": True, "merks": merks}


@router.put("/inventory-keterangan")
def update_inventory_keterangan(body: InvKeterangan, conn: sqlite3.Connection = Depends(get_db),
                                user=Depends(require_admin)):
    """Opsi Keterangan global (satu daftar, dipakai semua item). Urutan
    dipertahankan sesuai kiriman (untuk fitur drag-reorder), dedup + trim."""
    seen, ket = set(), []
    for x in body.keterangan:
        s = x.strip()
        if s and s.lower() not in seen:
            seen.add(s.lower())
            ket.append(s)
    db.set_setting(conn, "inventory_keterangan", ket)
    conn.commit()
    audit(conn, user, "update", "settings", "inventory_keterangan")
    return {"ok": True, "keterangan": ket}
