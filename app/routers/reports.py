"""Laporan progres sesuai permintaan (admin & viewer): ringkasan JSON, PDF siap kirim, Excel untuk diolah.

Definisi (lihat docs/plans/reporting.md):
- Tanggal aktivasi = field tanggal ber-role 'activation' (db.activation_key).
- NIS (node in service) = tanggal aktivasi terisi dan <= tanggal akhir laporan.
- Dokumen selesai = locations.complete_at (pertama kali lengkap 100%).
- Lama penyelesaian = tanggal selesai - tanggal aktivasi (hari kalender, 0 boleh).
- Selesai sebelum aktivasi / selesai tanpa tanggal aktivasi = data perlu dicek (tidak ikut rata-rata).
"""
from __future__ import annotations

import io
import json
import statistics as st
from datetime import date, datetime, timedelta

import sqlite3
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from .. import db
from ..deps import audit, get_db
from . import progress as pg
from .locations import wil_where

router = APIRouter(prefix="/api/reports", tags=["reports"])

SECTIONS = ("kpi", "weekly", "completion", "operator", "wilayah", "backlog", "missing", "errors", "locations")
BUCKETS = (("0-3", 0, 3), ("4-7", 4, 7), ("8-14", 8, 14), ("15-30", 15, 30), (">30", 31, 10 ** 6))
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _d(v) -> date | None:
    try:
        return date.fromisoformat(str(v)[:10]) if v else None
    except ValueError:
        return None


def _rows(conn, wil: str, owner: int) -> list[dict]:
    """Semua lokasi aktif (sesuai filter) + kelengkapan, tanggal aktivasi & tanggal dokumen selesai."""
    where, params = ["l.deleted_at IS NULL"], []
    if wil.strip():
        w, p = wil_where(wil, "l.")
        where.append(w); params += p
    if owner:
        where.append("l.owner_id=?"); params.append(owner)
    rows = conn.execute(
        "SELECT l.*, COALESCE(NULLIF(TRIM(u.full_name),''), u.username, '—') owner_name FROM locations l "
        "LEFT JOIN users u ON u.id=l.owner_id WHERE " + " AND ".join(where) + " ORDER BY l.id", params).fetchall()
    ids = [r["id"] for r in rows] or [0]
    q = ",".join("?" * len(ids))
    inv: dict[int, list] = {}
    for r in conn.execute(f"SELECT * FROM inventory_items WHERE location_id IN ({q}) ORDER BY sort_order,id", ids):
        inv.setdefault(r["location_id"], []).append(r)
    pc: dict[int, set] = {}
    for r in conn.execute(f"SELECT location_id, category FROM photos WHERE location_id IN ({q})", ids):
        pc.setdefault(r["location_id"], set()).add(r["category"])
    scans = {r[0] for r in conn.execute(f"SELECT location_id FROM scan_docs WHERE location_id IN ({q})", ids)}
    fields, cats = db.req_fields(conn), db.get_setting(conn, "photo_categories", []) or []
    wreq, sreq, akey = db.wil_counted(conn), db.scan_counted(conn), db.activation_key(conn)
    out = []
    for r in rows:
        data = json.loads(r["data_json"] or "{}")
        pct, miss = pg._completeness(r, fields, cats, inv.get(r["id"], []), pc.get(r["id"], set()),
                                     r["id"] in scans, wreq, sreq)
        ca = pg._local(r["complete_at"]) if r["complete_at"] else None
        out.append({"id": r["id"], "code": r["code"], "sid": r["sid"] or "",
                    "name": (r["name"] or data.get("nama_lokasi") or "").strip(),
                    "status": r["status"], "owner": r["owner_name"], "prov": r["wil_prov"] or "",
                    "kab": r["wil_kab"] or "", "kec": r["wil_kec"] or "", "desa": r["wil_desa"] or "",
                    "act": _d(data.get(akey)) if akey else None, "comp": ca.date() if ca else None,
                    "pct": pct, "miss": [_miss_id(m) for m in miss], "data": data})
    return out


def _miss_id(m: str) -> str:
    """Label kekurangan (UI berbahasa Inggris) -> bahasa laporan."""
    import re
    if m == "Scan PDF":
        return "Scan BAA"
    if m == "Location data":
        return "Data lokasi"
    return re.sub(r"^(\d+) photos$", r"\1 foto", m)


def _avg(v: list[int]):
    return round(st.mean(v), 1) if v else None


def _med(v: list[int]):
    return st.median(v) if v else None


def build(conn, frm: str = "", to: str = "", wil: str = "", owner: int = 0) -> dict:
    pg.backfill_complete_at(conn)
    rows = _rows(conn, wil, owner)
    today = pg._today()
    d_to = _d(to) or today
    dates = [x["act"] for x in rows if x["act"]] + [x["comp"] for x in rows if x["comp"]]
    d_from = _d(frm) or (min(dates) if dates else d_to)
    if d_from > d_to:
        raise HTTPException(400, "'From' is after 'To'")
    inp = lambda d: d is not None and d_from <= d <= d_to      # noqa: E731
    akey = db.activation_key(conn)
    for x in rows:
        a, c = x["act"], x["comp"] if (x["comp"] and x["comp"] <= d_to) else None
        x["nis"] = bool(a and a <= d_to)
        x["done"] = bool(c)
        x["days"] = (c - a).days if (a and c) else None
        x["err"] = ("before" if x["days"] is not None and x["days"] < 0 else "noact" if (c and not a) else "")
        x["valid"] = x["days"] is not None and x["days"] >= 0
        x["backlog"] = x["nis"] and not x["done"]
        x["age"] = (d_to - a).days if (x["backlog"] and a) else None
    nis = [x for x in rows if x["nis"]]
    done = [x for x in rows if x["done"]]
    valid_p = [x["days"] for x in rows if x["valid"] and inp(x["comp"])]
    goal = pg._goal(conn)["total"] if not (wil.strip() or owner) else None
    # minggu (Senin) dalam periode
    w0 = d_from - timedelta(days=d_from.weekday())
    weeks = []
    while w0 <= d_to:
        we = w0 + timedelta(days=6)
        weeks.append({"week": w0.isoformat(),
                      "nis": sum(1 for x in rows if x["act"] and max(w0, d_from) <= x["act"] <= min(we, d_to)),
                      "done": sum(1 for x in rows if x["done"] and max(w0, d_from) <= x["comp"] <= min(we, d_to))})
        w0 += timedelta(days=7)
    hist = [{"label": lab, "n": sum(1 for v in valid_p if a <= v <= b)} for lab, a, b in BUCKETS]

    def group(keyf):
        g: dict = {}
        for x in rows:
            k = keyf(x)
            o = g.setdefault(k, {"n": 0, "nis": 0, "done": 0, "backlog": 0, "days": []})
            o["n"] += 1; o["nis"] += x["nis"]; o["done"] += x["done"]; o["backlog"] += x["backlog"]
            if x["valid"] and inp(x["comp"]):
                o["days"].append(x["days"])
        return [{"key": k, "n": o["n"], "nis": o["nis"], "done": o["done"], "backlog": o["backlog"],
                 "pct_nis": round(min(o["done"], o["nis"]) / o["nis"] * 100) if o["nis"] else None,
                 "avg": _avg(o["days"]), "med": _med(o["days"]), "docs": len(o["days"])} for k, o in g.items()]
    ops = sorted(group(lambda x: x["owner"]), key=lambda o: (-o["n"], o["key"]))
    wils = sorted(group(lambda x: (x["prov"] or "—", x["kab"] or "Tanpa wilayah")), key=lambda o: (-o["nis"], -o["n"]))
    for w in wils:
        w["prov"], w["kab"] = w.pop("key")
    lite = lambda x: {k: (v.isoformat() if isinstance(v, date) else v) for k, v in x.items() if k != "data"}  # noqa: E731
    return {
        "from": d_from.isoformat(), "to": d_to.isoformat(), "today": today.isoformat(),
        "activation_field": akey, "activation_label": next((f.get("label") for f in (db.get_setting(conn, "location_fields", []) or []) if f.get("key") == akey), None),
        "filtered": bool(wil.strip() or owner),
        "kpi": {"target": goal, "locations": len(rows), "nis": len(nis), "done": len(done),
                "backlog": sum(1 for x in rows if x["backlog"]),
                # rincian supaya bisa dijumlah: NIS = done_nis + backlog ; done = done_nis + done tanpa aktivasi
                "done_nis": sum(1 for x in rows if x["done"] and x["nis"]),
                "not_active": sum(1 for x in rows if not x["nis"]),
                "nis_new": sum(1 for x in rows if inp(x["act"])), "done_new": sum(1 for x in rows if x["done"] and inp(x["comp"])),
                "avg": _avg(valid_p), "med": _med(valid_p), "docs": len(valid_p),
                "err_before": sum(1 for x in rows if x["err"] == "before"), "err_noact": sum(1 for x in rows if x["err"] == "noact"),
                # berstatus Done tetapi belum lengkap 100% saat ini (mis. di-Done sebelum scan diwajibkan)
                "done_incomplete": sum(1 for x in rows if x["status"] == "selesai" and x["pct"] < 100)},
        "weekly": weeks, "hist": hist, "operators": ops, "wilayah": wils,
        "backlog": [lite(x) for x in sorted((x for x in rows if x["backlog"]), key=lambda x: -(x["age"] or 0))],
        "missing": [lite(x) for x in sorted((x for x in rows if x["pct"] < 100), key=lambda x: (x["pct"], x["code"]))],
        "errors": [lite(x) for x in rows if x["err"]],
        "_rows": rows,
    }


def _admin_or_viewer(user=Depends(pg._require_admin_or_viewer)):
    return user


@router.get("/summary")
def summary(frm: str = Query("", alias="from"), to: str = "", wil: str = "", owner: int = 0,
            conn: sqlite3.Connection = Depends(get_db), user=Depends(_admin_or_viewer)):
    r = build(conn, frm, to, wil, owner)
    r.pop("_rows")
    for k in ("backlog", "missing", "errors"):
        r[k + "_n"] = len(r[k])
        r[k] = r[k][:10]
    return r


def _fname(conn, r, ext: str) -> str:
    pre = (getattr(conn, "project", None) or {}).get("prefix") or "BAA"
    return f"Laporan BAA {pre} {r['to']}.{ext}"


def _secs(sections: str) -> set[str]:
    s = {x for x in sections.split(",") if x in SECTIONS}
    return s or set(SECTIONS) - {"locations"}


def _filt_label(conn, wil: str, owner: int) -> str:
    from ..services import wilayah
    w = "Belum ada wilayah" if wil == "none" else "Wilayah manual" if wil == "manual" else \
        (wilayah.name_of(wil) or wil) if wil else "Semua wilayah"
    o = "Semua owner"
    if owner:
        u = conn.execute("SELECT COALESCE(NULLIF(TRIM(full_name),''), username) n FROM users WHERE id=?", (owner,)).fetchone()
        o = "Owner: " + (u["n"] if u else str(owner))
    return f"{w} · {o}"


@router.get("/xlsx")
def report_xlsx(frm: str = Query("", alias="from"), to: str = "", wil: str = "", owner: int = 0, sections: str = "",
                conn: sqlite3.Connection = Depends(get_db), user=Depends(_admin_or_viewer)):
    r = build(conn, frm, to, wil, owner)
    buf = _xlsx(conn, r, _secs(sections), _filt_label(conn, wil, owner))
    audit(conn, user, "report_xlsx", "report", "", f"{r['from']}..{r['to']}")
    name = _fname(conn, r, "xlsx")
    return StreamingResponse(buf, media_type=XLSX_MIME,
                             headers={"Content-Disposition": f"attachment; filename*=utf-8''{_q(name)}"})


@router.get("/pdf")
def report_pdf(frm: str = Query("", alias="from"), to: str = "", wil: str = "", owner: int = 0, sections: str = "",
               conn: sqlite3.Connection = Depends(get_db), user=Depends(_admin_or_viewer)):
    r = build(conn, frm, to, wil, owner)
    pj = getattr(conn, "project", None) or {}
    from ..services import report_pdf
    buf = report_pdf.build(r, _secs(sections), title=f"Laporan Progres BAA — {pj.get('name') or ''} ({pj.get('prefix') or ''})",
                           filt=_filt_label(conn, wil, owner), by=(user["full_name"] or user["username"]), app=db.app_title(conn))
    audit(conn, user, "report_pdf", "report", "", f"{r['from']}..{r['to']}")
    name = _fname(conn, r, "pdf")
    return StreamingResponse(buf, media_type="application/pdf",
                             headers={"Content-Disposition": f"attachment; filename*=utf-8''{_q(name)}"})


def _q(s: str) -> str:
    from urllib.parse import quote
    return quote(s)


def _xlsx(conn, r: dict, secs: set[str], filt: str) -> io.BytesIO:
    """Tiap bagian = satu sheet tabel polos (baris judul, tanpa merge) agar mudah difilter & di-pivot."""
    import openpyxl
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    head_fill = PatternFill("solid", fgColor="E3EEEC")
    k = r["kpi"]

    def sheet(title, header, rows, widths=None):
        ws = wb.create_sheet(title)
        ws.append(header)
        for c in ws[1]:
            c.font = Font(bold=True)
            c.fill = head_fill
        for row in rows:
            ws.append(list(row))
        ws.freeze_panes = "A2"
        if rows:
            ws.auto_filter.ref = ws.dimensions
        for i, h in enumerate(header, start=1):
            ws.column_dimensions[get_column_letter(i)].width = (widths or {}).get(i, max(12, min(40, len(str(h)) + 4)))
        return ws
    if "kpi" in secs:
        sheet("Ringkasan", ["Ukuran", "Nilai", "Keterangan"], [
            ("Periode", f"{r['from']} s/d {r['to']}", filt),
            ("Target", k["target"] if k["target"] is not None else "", "target project (tanpa filter)"),
            ("Lokasi", k["locations"], ""),
            ("NIS (node in service)", k["nis"], f"tanggal aktivasi terisi s/d {r['to']}"),
            ("  NIS dokumen selesai", k["done_nis"], ""),
            ("  NIS backlog", k["backlog"], "dokumen belum selesai"),
            ("Belum aktif", k["not_active"], "tanggal aktivasi belum diisi"),
            ("NIS baru dalam periode", k["nis_new"], ""),
            ("Dokumen BAA selesai", k["done"], f"lengkap 100% s/d {r['to']}"),
            ("  dari NIS", k["done_nis"], ""),
            ("  tanpa tanggal aktivasi", k["done"] - k["done_nis"], "data perlu dicek"),
            ("Dokumen selesai dalam periode", k["done_new"], ""),
            ("Backlog", k["backlog"], "NIS, dokumen belum selesai"),
            ("Rata-rata penyelesaian (hari)", k["avg"] if k["avg"] is not None else "", f"{k['docs']} dokumen selesai dalam periode"),
            ("Median penyelesaian (hari)", k["med"] if k["med"] is not None else "", ""),
            ("Selesai sebelum aktivasi", k["err_before"], "data perlu dicek, tidak ikut rata-rata"),
            ("Selesai tanpa tanggal aktivasi", k["err_noact"], "data perlu dicek, tidak ikut rata-rata"),
            ("Status Done tetapi belum lengkap", k["done_incomplete"], "belum dihitung sebagai dokumen selesai"),
        ], {1: 32, 2: 24, 3: 44})
    if "weekly" in secs:
        sheet("Mingguan", ["Minggu mulai (Senin)", "NIS baru", "Dokumen selesai"],
              [(date.fromisoformat(w["week"]), w["nis"], w["done"]) for w in r["weekly"]], {1: 22})
    if "completion" in secs:
        sheet("Lama penyelesaian", ["Rentang (hari)", "Dokumen"], [(h["label"], h["n"]) for h in r["hist"]])
    if "operator" in secs:
        sheet("Per operator", ["Operator", "Lokasi", "NIS", "Dokumen selesai", "Backlog", "Rata-rata hari", "Median hari", "Dokumen dihitung"],
              [(o["key"], o["n"], o["nis"], o["done"], o["backlog"], o["avg"], o["med"], o["docs"]) for o in r["operators"]], {1: 24})
    if "wilayah" in secs:
        sheet("Per wilayah", ["Provinsi", "Kab/Kota", "Lokasi", "NIS", "Dokumen selesai", "% selesai dari NIS", "Backlog", "Rata-rata hari", "Median hari"],
              [(w["prov"], w["kab"], w["n"], w["nis"], w["done"], w["pct_nis"], w["backlog"], w["avg"], w["med"]) for w in r["wilayah"]],
              {1: 22, 2: 26})
    if "backlog" in secs:
        sheet("Backlog", ["Kode", "SID", "Lokasi", "Kab/Kota", "Owner", "Tanggal aktivasi", "Hari sejak aktivasi", "Kelengkapan %", "Kurang"],
              [(x["code"], x["sid"], x["name"], x["kab"], x["owner"], date.fromisoformat(x["act"]), x["age"], x["pct"], ", ".join(x["miss"]))
               for x in r["backlog"]], {3: 40, 4: 22, 9: 40})
    if "missing" in secs:
        sheet("Kekurangan", ["Kode", "SID", "Lokasi", "Owner", "Status", "Kelengkapan %", "Kurang"],
              [(x["code"], x["sid"], x["name"], x["owner"], "Done" if x["status"] == "selesai" else "Draft", x["pct"], ", ".join(x["miss"]))
               for x in r["missing"]], {3: 40, 7: 44})
    if "errors" in secs:
        sheet("Data perlu dicek", ["Kode", "SID", "Lokasi", "Owner", "Tanggal aktivasi", "Dokumen selesai", "Selisih hari", "Masalah"],
              [(x["code"], x["sid"], x["name"], x["owner"], date.fromisoformat(x["act"]) if x["act"] else "", date.fromisoformat(x["comp"]) if x["comp"] else "",
                x["days"] if x["days"] is not None else "",
                "Selesai sebelum tanggal aktivasi" if x["err"] == "before" else "Tanggal aktivasi kosong") for x in r["errors"]],
              {3: 40, 8: 32})
    if "locations" in secs:
        fields = db.get_setting(conn, "location_fields", []) or []
        hdr = ["Kode", "SID", "Status", "Owner", "Provinsi", "Kab/Kota", "Kecamatan", "Desa"] + \
              [f.get("label") or f["key"] for f in fields] + ["NIS", "Dokumen selesai", "Lama hari", "Kelengkapan %", "Kurang"]
        body = []
        for x in r["_rows"]:
            vals = []
            for f in fields:
                v = x["data"].get(f["key"], "")
                vals.append(_d(v) if f.get("type") == "date" and _d(v) else v)
            body.append([x["code"], x["sid"], "Done" if x["status"] == "selesai" else "Draft", x["owner"], x["prov"], x["kab"], x["kec"], x["desa"],
                         *vals, "Ya" if x["nis"] else "", x["comp"] if x["done"] else "", x["days"] if x["valid"] else "", x["pct"], ", ".join(x["miss"])])
        sheet("Lokasi", hdr, body)
    for ws in wb.worksheets:
        for row in ws.iter_rows(min_row=2):
            for c in row:
                if isinstance(c.value, (date, datetime)):
                    c.number_format = "yyyy-mm-dd"
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf
