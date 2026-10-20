"""Baca SN dari area terpilih (ROI). Frontend mengirim potongan gambar (PNG) + kategori foto."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, File, Form, UploadFile

from .. import db
from ..deps import current_user, get_db
from ..services import ocr as ocr_svc

router = APIRouter(prefix="/api", tags=["ocr"])


@router.post("/ocr")
def ocr_region(file: UploadFile = File(...), cat: str = Form(""),
               conn: sqlite3.Connection = Depends(get_db), user=Depends(current_user)):
    data = file.file.read()
    rule = ocr_svc.rule_for(db.get_setting(conn, "photo_categories", []), cat)
    r = ocr_svc.read_bytes(data, rule)
    return {"available": ocr_svc.available(), "text": r["text"], "serial": r["serial"],
            "candidates": r["candidates"], "barcodes": r["barcodes"]}
