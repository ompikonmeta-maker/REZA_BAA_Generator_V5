"""Sinkron progres BAPB ke Google Sheet (lewat Apps Script Web App milik pemilik sheet).

Tahap 2: koneksi, baca sheet, rekonsiliasi (Check only) + alarm, ambil SID/SO dari sheet.
BAA Flow tidak pernah mengubah nama, ID, atau kolom lain di sheet; perbedaan hanya jadi alarm.
Semua nama kolom diatur per project (setting ``gsheet_config``), dicari lewat judul header baris 1.
"""
from __future__ import annotations

import json
import re
import sqlite3
import urllib.error
import urllib.request
from datetime import date, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from .. import db
from ..deps import audit, get_db, require_admin
from .locations import check_sid_free, norm_sid

router = APIRouter(prefix="/api/gsheet", tags=["gsheet"])

SCRIPT = Path(__file__).resolve().parent.parent / "data" / "gsheet_apps_script.gs"
DEFAULT = {
    "url": "", "secret": "",
    "key_col": "ID Node Link", "name_col": "Nama Lokasi", "desa_col": "Desa", "kec_col": "Kecamatan",
    "kab_col": "Kabupaten", "prov_col": "Provinsi", "so_col": "SO",
    "status_col": "STATUS BAPB", "date_col": "TANGGAL BAPB", "link_col": "LINK BAPB",
    # dibaca saja: tanggal link terpasang/online -> tanggal aktivasi (bila kosong) + tanda "cari eviden"
    "online_col": "Tanggal Terpasang/ Integrasi",
    "date_fmt": "dd-MMM-yyyy",
    # aturan STATUS BAPB: dibaca dari atas, aturan pertama yang cocok dipakai; tidak ada yang cocok = kosong
    "status_rules": [{"text": "Done", "when": "complete"}, {"text": "Undone", "when": "activation"}],
}
# syarat yang bisa dipilih per aturan (pct memakai angka "n")
CONDS = {
    "complete": "Document 100% (activation date filled)",
    "pct": "Completeness at least n%",
    "scan": "Signed scan uploaded",
    "done": "Marked Done in BAA Flow",
    "activation": "Activation date filled",
    "no_activation": "No activation date",
    "any": "Any location",
}
COLS = ("key_col", "name_col", "desa_col", "kec_col", "kab_col", "prov_col", "so_col", "status_col", "date_col", "link_col",
        "online_col")
DATE_FMTS = {"dd-MMM-yyyy": None, "yyyy-mm-dd": "%Y-%m-%d", "dd/mm/yyyy": "%d/%m/%Y"}
_MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
_MON_ID = {"mei": 5, "agu": 8, "agt": 8, "okt": 10, "des": 12}


def config(conn) -> dict:
    cfg = {**DEFAULT, **(db.get_setting(conn, "gsheet_config") or {})}
    if "status_rules" not in (db.get_setting(conn, "gsheet_config") or {}) and "done_text" in cfg:
        # setting lama (Done/Undone tetap) -> aturan
        cfg["status_rules"] = [{"text": cfg.get("done_text") or "Done", "when": "complete"},
                               {"text": cfg.get("undone_text") or "Undone", "when": "activation"}]
    return cfg


def _rules(raw) -> list[dict]:
    out = []
    for r in raw or []:
        when = str((r or {}).get("when") or "")
        if when not in CONDS:
            continue
        try:
            n = max(0, min(100, int((r or {}).get("n") or 0)))
        except (TypeError, ValueError):
            n = 0
        out.append({"text": str(r.get("text") or "").strip()[:80], "when": when, **({"n": n} if when == "pct" else {})})
    return out[:20]


def _public(cfg: dict) -> dict:
    out = {k: v for k, v in cfg.items() if k != "secret"}
    out["has_secret"] = bool(cfg.get("secret"))
    return out


# ---------------------------------------------------------------- panggilan ke Apps Script
def call(cfg: dict, action: str, timeout: int = 90, **kw) -> dict:
    url = (cfg.get("url") or "").strip()
    # script.google.com = Web App asli; http://127.0.0.1 / localhost hanya untuk uji lokal (tiruan Apps Script)
    if not re.match(r"^(https://script\.google(usercontent)?\.com/|http://(127\.0\.0\.1|localhost):\d+/)", url):
        raise HTTPException(400, "Fill in the Web App URL (https://script.google.com/macros/s/…/exec)")
    if not cfg.get("secret"):
        raise HTTPException(400, "Fill in the secret code")
    body = json.dumps({"action": action, "secret": cfg["secret"], **kw}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        # Apps Script membalas 302 ke googleusercontent; urllib mengikutinya sebagai GET (sesuai yang diminta Google)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raise HTTPException(502, f"Google Sheet replied HTTP {e.code} — check the Web App URL and that it is deployed for 'Anyone'")
    except Exception as e:
        raise HTTPException(502, f"Can't reach Google Sheet: {e}")
    try:
        res = json.loads(raw)
    except ValueError:
        raise HTTPException(502, "Google Sheet did not answer with data — redeploy the Web App with access 'Anyone'")
    if not res.get("ok"):
        raise HTTPException(502, "Google Sheet: " + str(res.get("error") or "error"))
    return res


# ---------------------------------------------------------------- bantu
def _key(v) -> str:
    return re.sub(r"\s+", "", str(v or "")).upper()


_WILP = re.compile(r"^(desa|kelurahan|kel|ds|kecamatan|kec|kabupaten|kab|kota)\s+")


def _cmp(v) -> str:
    """Bentuk pembanding: huruf kecil, tanpa spasi & tanda baca."""
    return re.sub(r"[^a-z0-9]+", "", str(v or "").lower())


def _wil_same(x: dict, s: dict) -> bool:
    """Desa & kecamatan sama (abaikan awalan Desa/Kec., spasi, tanda baca); kolom kosong di salah satu sisi dilewati."""
    for a, b in ((x["desa"], s["desa"]), (x["kec"], s["kec"])):
        a, b = _cmp(_WILP.sub("", str(a or "").lower().strip())), _cmp(_WILP.sub("", str(b or "").lower().strip()))
        if a and b and a != b:
            return False
    return True


def _so(v) -> str:
    return db.norm_so(v).upper()


def fmt_date(d: date | None, fmt: str) -> str:
    if not d:
        return ""
    if fmt == "dd-MMM-yyyy" or fmt not in DATE_FMTS:
        return f"{d.day:02d}-{_MON[d.month - 1]}-{d.year}"
    return d.strftime(DATE_FMTS[fmt])


def parse_date(s: str) -> date | None:
    s = (s or "").strip()
    if not s:
        return None
    m = re.match(r"^(\d{1,2})[-/ ]([A-Za-z]{3,})[-/ ](\d{4})$", s)
    if m:
        mon = m.group(2)[:3].lower()
        mi = next((i + 1 for i, x in enumerate(_MON) if x.lower() == mon), _MON_ID.get(mon))
        if mi:
            try:
                return date(int(m.group(3)), mi, int(m.group(1)))
            except ValueError:
                return None
    for f in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(s, f).date()
        except ValueError:
            pass
    return None


def _cond(x: dict, r: dict) -> bool:
    w = r["when"]
    if w == "complete":
        return x["pct"] >= 100 and bool(x["act"])
    if w == "pct":
        return x["pct"] >= r.get("n", 0)
    if w == "scan":
        return bool(x.get("has_scan"))
    if w == "done":
        return x["status"] == "selesai"
    if w == "activation":
        return bool(x["act"])
    if w == "no_activation":
        return not x["act"]
    return w == "any"


def wanted(x: dict, cfg: dict) -> dict:
    """Nilai BAPB yang seharusnya ada di sheet untuk satu lokasi BAA Flow.
    PDF diunggah hanya untuk dokumen 100% (terlepas dari teks status)."""
    st = next((r["text"] for r in _rules(cfg.get("status_rules")) if _cond(x, r)), "")
    return {"status": st, "date": x["act"], "pdf": x["pct"] >= 100 and bool(x["act"])}


# ---------------------------------------------------------------- rekonsiliasi
def reconcile(conn, cfg: dict, res: dict) -> dict:
    from .reports import _rows
    sos = {_so(s) for s in db.so_list(conn)}
    C = {k: cfg[k] for k in COLS}
    sheet = []
    for r in res.get("rows", []):
        v = r["v"]
        sheet.append({"row": r["row"], "key": (v.get(C["key_col"]) or "").strip(), "name": (v.get(C["name_col"]) or "").strip(),
                      "desa": v.get(C["desa_col"]) or "", "kec": v.get(C["kec_col"]) or "", "kab": v.get(C["kab_col"]) or "",
                      "prov": v.get(C["prov_col"]) or "",
                      "so": (v.get(C["so_col"]) or "").strip(), "status": (v.get(C["status_col"]) or "").strip(),
                      "date": (v.get(C["date_col"]) or "").strip(), "link": (v.get(C["link_col"]) or "").strip(),
                      "online": (v.get(C["online_col"]) or "").strip() if C["online_col"] else ""})
    scope = [s for s in sheet if not sos or _so(s["so"]) in sos]
    by_key, dup_keys = {}, {}
    for s in sheet:
        k = _key(s["key"])
        if not k:
            continue
        if k in by_key:
            dup_keys.setdefault(k, [by_key[k]]).append(s)
        else:
            by_key[k] = s
    # pencocokan nama: huruf kecil, tanpa spasi/tanda baca ("Tanjung Karang" = "Tanjungkarang")
    by_nm = {}
    for s in sheet:
        if _cmp(s["name"]):
            by_nm.setdefault(_cmp(s["name"]), []).append(s)
    locs = _rows(conn, "", 0)
    mod = {r[0]: r[1] for r in conn.execute("SELECT id, modified_at FROM locations WHERE deleted_at IS NULL")}
    pdfs = {r[0]: (r[1], r[2]) for r in conn.execute("SELECT location_id, pdf_url, pdf_at FROM gsheet_sync")}
    used_sid = {_key(x["sid"]) for x in locs if x["sid"]}
    A = {k: [] for k in ("sid_diff", "take_sid", "only_sheet", "only_baa", "wil_diff", "dup_sheet",
                         "ambiguous", "so_diff", "fill_so", "name_diff", "online_bad")}
    online = []   # lokasi cocok + tanggal terpasang di sheet: {id, date|None, act}
    matched, changes, hows, claimed = {}, [], {"id": 0, "name": 0}, set()
    brief = lambda s: {"row": s["row"], "key": s["key"], "name": s["name"], "desa": s["desa"], "kec": s["kec"], "so": s["so"]}  # noqa: E731

    def by_name(x):
        """Baris sheet untuk lokasi x lewat nama; nama kembar dipilah dengan desa+kecamatan."""
        c = by_nm.get(_cmp(x["name"]), [])
        if len(c) > 1:
            c2 = [s for s in c if _wil_same(x, s)]
            return c2 if c2 else c
        return c

    for x in locs:
        lb = {"id": x["id"], "code": x["code"], "name": x["name"], "sid": x["sid"], "so": x["so"],
              "desa": x["desa"], "kec": x["kec"]}
        s, how = None, ""
        if x["sid"]:
            s = by_key.get(_key(x["sid"]))
            if s and _key(x["sid"]) in dup_keys:
                continue                                   # ID kembar di sheet: dilaporkan sekali di bawah
            if s and _cmp(s["name"]) != _cmp(x["name"]):
                c = by_name(x)
                if len(c) == 1 and c[0] is not s:
                    # SID menunjuk baris lokasi lain, nama cocok dengan baris berbeda
                    A["sid_diff"].append({**lb, "sheet": brief(c[0]), "sid_row": brief(s)})
                    claimed.add(id(c[0]))
                    continue
                A["name_diff"].append({**lb, "sheet": brief(s)})
            if not s:
                c = by_name(x)
                if len(c) == 1 and c[0]["key"]:
                    A["sid_diff"].append({**lb, "sheet": brief(c[0])})
                    claimed.add(id(c[0]))
                else:
                    A["only_baa"].append(lb)
                continue
            how = "id"
        else:
            c = by_name(x)
            if len(c) == 1:
                s, how = c[0], "name"
                ok = bool(s["key"]) and _key(s["key"]) not in used_sid and _key(s["key"]) not in dup_keys
                if ok:
                    A["take_sid"].append({**lb, "sheet": brief(s), "wil_ok": _wil_same(x, s)})
            elif len(c) > 1:
                A["ambiguous"].append({**lb, "rows": [r["row"] for r in c]})
                continue
            else:
                A["only_baa"].append(lb)
                continue
        if (x["desa"] or x["kec"]) and not _wil_same(x, s):
            A["wil_diff"].append({**lb, "sheet": brief(s)})
        matched[id(s)] = True
        hows[how] += 1
        od = parse_date(s["online"])
        if s["online"] and not od:
            A["online_bad"].append({**lb, "sheet": brief(s), "value": s["online"]})
        online.append({"id": x["id"], "date": od, "act": x["act"], "pct": x["pct"]})
        if s["so"]:
            if not x["so"]:
                A["fill_so"].append({**lb, "sheet": brief(s), "known": db.so_match(conn, s["so"]) is not None})
            elif _so(x["so"]) != _so(s["so"]):
                A["so_diff"].append({**lb, "sheet": brief(s)})
        w = wanted(x, cfg)
        ch = {}
        if w["status"] != s["status"] and (w["status"] or s["status"]):
            ch["status"] = [s["status"], w["status"]]
        if w["date"] != parse_date(s["date"]):
            ch["date"] = [s["date"], fmt_date(w["date"], cfg["date_fmt"])]
        if w["pdf"] and s["key"]:
            url, at = pdfs.get(x["id"], (None, None))
            if not s["link"] or not url:
                ch["link"] = [s["link"], "upload PDF"]
            elif (mod.get(x["id"]) or "") > (at or ""):
                ch["link"] = [s["link"], "replace PDF (changed)"]
            elif s["link"] != url:
                ch["link"] = [s["link"], url]
        if ch:
            changes.append({**lb, "row": s["row"], "key": s["key"], "how": how, "ch": ch})
    rest = [s for s in scope if id(s) not in matched and id(s) not in claimed and not (s["key"] and _key(s["key"]) in dup_keys)]
    # nama beda tetapi desa + kecamatan sama dan hanya satu kandidat -> kemungkinan pasangan (tidak dicocokkan otomatis)
    keep_baa = []
    for lb in A["only_baa"]:
        c = [s for s in rest if lb["desa"] and _cmp(s["desa"]) == _cmp(lb["desa"]) and _wil_same(lb, s)]
        if len(c) == 1:
            A["name_diff"].append({**lb, "sheet": brief(c[0]), "pair": True})
            rest.remove(c[0])
        else:
            keep_baa.append(lb)
    A["only_baa"] = keep_baa
    A["only_sheet"] = [brief(s) for s in rest]
    for k, lst in dup_keys.items():
        if any(_so(r["so"]) in sos or not sos for r in lst):
            A["dup_sheet"].append({"key": lst[0]["key"], "name": lst[0]["name"], "rows": [r["row"] for r in lst]})
    n_ch = lambda f, v=None: sum(1 for c in changes if f in c["ch"] and (v is None or c["ch"][f][1] == v))  # noqa: E731
    return {
        "checked_at": db.now_iso(), "file": res.get("file"), "sheet": res.get("sheet"),
        "missing_cols": res.get("missing", []), "so_scope": sorted(db.so_list(conn)),
        "counts": {"baa": len(locs), "sheet": len(sheet), "scope": len(scope), "matched": len(matched),
                   "by_id": hows["id"], "by_name": hows["name"], "changes": len(changes),
                   "to": {v: n_ch("status", v) for v in dict.fromkeys(c["ch"]["status"][1] for c in changes if "status" in c["ch"])},
                   "pdf": n_ch("link")},
        "changes": changes, "alarms": A, "online": online,
        "alarm_n": sum(len(v) for k, v in A.items() if k not in ("take_sid", "fill_so")) + len(res.get("missing", [])),
    }


# ---------------------------------------------------------------- endpoint
class CfgIn(BaseModel):
    url: str = ""
    secret: str | None = None          # None = tidak diubah
    key_col: str = DEFAULT["key_col"]
    name_col: str = DEFAULT["name_col"]
    desa_col: str = DEFAULT["desa_col"]
    kec_col: str = DEFAULT["kec_col"]
    kab_col: str = DEFAULT["kab_col"]
    prov_col: str = DEFAULT["prov_col"]
    so_col: str = DEFAULT["so_col"]
    status_col: str = DEFAULT["status_col"]
    online_col: str = DEFAULT["online_col"]
    date_col: str = DEFAULT["date_col"]
    link_col: str = DEFAULT["link_col"]
    status_rules: list[dict] = DEFAULT["status_rules"]
    date_fmt: str = DEFAULT["date_fmt"]


@router.get("/config")
def get_config(conn: sqlite3.Connection = Depends(get_db), user=Depends(require_admin)):
    return {"config": _public(config(conn)), "date_fmts": list(DATE_FMTS), "conds": CONDS,
            "last": db.get_setting(conn, "gsheet_last_check"), "log": log_rows(conn, 10)}


@router.put("/config")
def put_config(body: CfgIn, conn: sqlite3.Connection = Depends(get_db), user=Depends(require_admin)):
    cur = config(conn)
    new = {k: (str(v).strip() if isinstance(v, str) else v) for k, v in body.model_dump().items() if k != "secret"}
    new["status_rules"] = _rules(body.status_rules)
    if any(not r["text"] for r in new["status_rules"]):
        raise HTTPException(400, "Each status rule needs a value")
    if new["date_fmt"] not in DATE_FMTS:
        raise HTTPException(400, "Unknown date format")
    new["secret"] = cur.get("secret", "") if body.secret is None else body.secret.strip()
    db.set_setting(conn, "gsheet_config", new)
    conn.commit()
    audit(conn, user, "update", "settings", "gsheet_config")
    return {"ok": True, "config": _public(new)}


@router.post("/test")
def test(conn: sqlite3.Connection = Depends(get_db), user=Depends(require_admin)):
    cfg = config(conn)
    r = call(cfg, "ping", timeout=45)
    hdr = r.get("headers") or []
    return {"ok": True, "file": r.get("file"), "sheet": r.get("sheet"), "rows": r.get("rows"), "folder": r.get("folder"),
            "headers": [h for h in hdr if h], "missing": [cfg[k] for k in COLS if cfg[k] and _hk(cfg[k]) not in {_hk(h) for h in hdr}]}


def _hk(h: str) -> str:
    """Kunci judul kolom: huruf kecil tanpa spasi ('Tanggal Terpasang/ Integrasi' = 'tanggal terpasang/integrasi')."""
    return re.sub(r"\s+", "", str(h or "")).lower()


def read_sheet(cfg: dict) -> tuple[dict, dict]:
    """Baca kolom yang dikonfigurasi. Judul yang beda spasi/huruf besar dicocokkan ulang ke judul asli di sheet."""
    res = call(cfg, "read", columns=[cfg[k] for k in COLS if cfg[k]])
    miss = res.get("missing", [])
    if miss:
        hk = {_hk(h): h for h in res.get("headers") or [] if h}
        fix = {k: hk[_hk(cfg[k])] for k in COLS if cfg[k] in miss and _hk(cfg[k]) in hk}
        if fix:
            cfg = {**cfg, **fix}
            res = call(cfg, "read", columns=[cfg[k] for k in COLS if cfg[k]])
    return cfg, res


def apply_online(conn, user, items: list[dict]) -> dict:
    """Tanggal terpasang dari sheet: simpan per lokasi (tanda link online) dan jadikan tanggal aktivasi
    bila BAA Flow belum punya. Tanggal aktivasi yang sudah ada di BAA Flow tidak pernah ditimpa."""
    import json
    akey = db.activation_key(conn)
    now = db.now_iso()
    old = {r[0]: r[1] for r in conn.execute("SELECT location_id, online_date FROM gsheet_sync")}
    filled = 0
    for it in items:
        od = it["date"].isoformat() if it["date"] else None
        if od != old.get(it["id"]):
            conn.execute("INSERT INTO gsheet_sync(location_id, online_date, online_seen) VALUES(?,?,?) "
                         "ON CONFLICT(location_id) DO UPDATE SET online_date=excluded.online_date, "
                         "online_seen=COALESCE(gsheet_sync.online_seen, excluded.online_seen)", (it["id"], od, now))
        if od and akey and not it["act"]:
            r = conn.execute("SELECT data_json FROM locations WHERE id=? AND deleted_at IS NULL", (it["id"],)).fetchone()
            if not r:
                continue
            data = json.loads(r[0] or "{}")
            if data.get(akey):
                continue
            data[akey] = od
            conn.execute("UPDATE locations SET data_json=? WHERE id=?", (json.dumps(data, ensure_ascii=False), it["id"]))
            db.touch_modified(conn, it["id"], user["id"], "act_sheet", od)
            filled += 1
    conn.commit()
    return {"seen": sum(1 for it in items if it["date"]), "filled": filled,
            "flag": sum(1 for it in items if it["date"] and it["pct"] < 100)}


@router.post("/check")
def check(conn: sqlite3.Connection = Depends(get_db), user=Depends(require_admin)):
    cfg, res = read_sheet(config(conn))
    if cfg["key_col"] in res.get("missing", []) or cfg["name_col"] in res.get("missing", []):
        raise HTTPException(400, f"Column '{cfg['key_col']}' or '{cfg['name_col']}' not found in row 1 of the sheet")
    out = reconcile(conn, cfg, res)
    on = apply_online(conn, user, out.pop("online"))
    if on["filled"]:
        out = reconcile(conn, cfg, res)          # tanggal aktivasi baru -> TANGGAL/STATUS BAPB ikut berubah
        out.pop("online")
    out["online"] = on
    db.set_setting(conn, "gsheet_last_check", {"at": out["checked_at"], "by": user["full_name"] or user["username"],
                                                "counts": out["counts"], "alarms": out["alarm_n"]})
    conn.commit()
    return out


@router.get("/script", response_class=PlainTextResponse)
def script(user=Depends(require_admin)):
    return SCRIPT.read_text(encoding="utf-8")


class ApplyIn(BaseModel):
    sid: list[int] = []      # lokasi: isi SID dari ID sheet (dicocokkan ulang di server)
    so: list[int] = []       # lokasi: isi SO dari sheet


@router.post("/apply")
def apply(body: ApplyIn, conn: sqlite3.Connection = Depends(get_db), user=Depends(require_admin)):
    """Ambil SID / SO dari sheet untuk lokasi terpilih (persetujuan admin). Dicek ulang dengan data sheet terbaru."""
    cfg, res = read_sheet(config(conn))
    out = reconcile(conn, cfg, res)
    A = out["alarms"]
    sid_ok = {x["id"]: x["sheet"]["key"] for x in A["take_sid"]}
    so_ok = {x["id"]: x["sheet"]["so"] for x in A["fill_so"]}
    # lokasi yang SID-nya baru diambil: SO ikut dari baris yang sama bila diminta
    for x in A["take_sid"]:
        if x["sheet"]["so"] and not x["so"]:
            so_ok.setdefault(x["id"], x["sheet"]["so"])
    done_sid, done_so, skipped, add_so = [], [], [], []
    now = db.now_iso()
    for lid in body.sid:
        if lid not in sid_ok:
            skipped.append(lid)
            continue
        try:
            sid = norm_sid(conn, sid_ok[lid])
            check_sid_free(conn, sid, lid)
        except HTTPException:
            skipped.append(lid)
            continue
        conn.execute("UPDATE locations SET sid=? WHERE id=? AND (sid IS NULL OR sid='')", (sid, lid))
        db.touch_modified(conn, lid, user["id"], "sid", f"{sid} (from Google Sheet)")
        done_sid.append(lid)
    for lid in body.so:
        v = so_ok.get(lid)
        if not v:
            skipped.append(lid)
            continue
        s = db.so_match(conn, v)
        if not s:
            s = db.norm_so(v)
            db.set_setting(conn, "so_list", db.so_list(conn) + [s])
            add_so.append(s)
        conn.execute("UPDATE locations SET so=? WHERE id=? AND (so IS NULL OR so='')", (s, lid))
        db.touch_modified(conn, lid, user["id"], "so", s)
        done_so.append(lid)
    conn.commit()
    audit(conn, user, "gsheet_apply", "location", "", f"SID {len(done_sid)}, SO {len(done_so)}")
    return {"ok": True, "sid": len(done_sid), "so": len(done_so), "skipped": len(set(skipped)), "so_added": add_so, "at": now}


# ---------------------------------------------------------------- tahap 3: tulis ke sheet + PDF ke Drive
def _pdf_name(name: str, sid: str) -> str:
    """Nama file di Drive: 'Nama Lokasi-SID.pdf' (karakter terlarang dibuang)."""
    nm = re.sub(r'[\\/:*?"<>|]+', " ", f"{name}-{sid}").strip()
    return re.sub(r"\s+", " ", nm)[:150] + ".pdf"


def _make_pdf(conn, lid: int) -> bytes:
    """PDF gabungan satu lokasi — sama dengan tombol PDF di Entry (lampiran, scan, BAA)."""
    from .export import _gather_locations, _render_pdf, _stamp
    locs = _gather_locations(conn, "one", lid)
    out = _stamp(locs[0]["code"] + "_gs", "pdf")
    try:
        _render_pdf(conn, locs, out, db.get_setting(conn, "photo_categories", []), db.app_title(conn))
        return out.read_bytes()
    finally:
        out.unlink(missing_ok=True)


class PushItem(BaseModel):
    id: int
    row: int
    key: str
    pdf: bool = False


class PushIn(BaseModel):
    items: list[PushItem]


@router.post("/push")
def push(body: PushIn, conn: sqlite3.Connection = Depends(get_db), user=Depends(require_admin)):
    """Tulis STATUS/TANGGAL/LINK BAPB untuk lokasi terpilih (baris & ID dari hasil Check terakhir).
    Apps Script mencocokkan ulang ID di baris itu, jadi baris yang bergeser tidak tertimpa."""
    import base64
    from .reports import _rows
    cfg = config(conn)
    want = {x["id"]: x for x in _rows(conn, "", 0)}
    mod = {r[0]: r[1] for r in conn.execute("SELECT id, modified_at FROM locations WHERE deleted_at IS NULL")}
    updates, res = [], []
    for it in body.items:
        x = want.get(it.id)
        if not x:
            res.append({"id": it.id, "ok": False, "error": "Location not found"})
            continue
        w = wanted(x, cfg)
        vals = {cfg["status_col"]: w["status"], cfg["date_col"]: fmt_date(w["date"], cfg["date_fmt"])}
        if it.pdf and w["pdf"]:
            try:
                data = _make_pdf(conn, it.id)
                up = call(cfg, "upload", timeout=180, name=_pdf_name(x["name"], it.key),
                          data=base64.b64encode(data).decode())
            except HTTPException as e:
                res.append({"id": it.id, "ok": False, "error": str(e.detail)})
                continue
            except Exception as e:  # render PDF gagal
                res.append({"id": it.id, "ok": False, "error": f"PDF: {e}"})
                continue
            vals[cfg["link_col"]] = up["url"]
            conn.execute("INSERT INTO gsheet_sync(location_id,pdf_url,pdf_at,sent_at) VALUES(?,?,?,?) "
                         "ON CONFLICT(location_id) DO UPDATE SET pdf_url=excluded.pdf_url, pdf_at=excluded.pdf_at",
                         (it.id, up["url"], mod.get(it.id) or db.now_iso(), db.now_iso()))
            conn.commit()
        else:
            known = conn.execute("SELECT pdf_url FROM gsheet_sync WHERE location_id=?", (it.id,)).fetchone()
            if known and known[0] and w["pdf"]:
                vals[cfg["link_col"]] = known[0]
        updates.append({"row": it.row, "key": it.key, "values": vals, "_id": it.id})
    if updates:
        r = call(cfg, "update", key_col=cfg["key_col"],
                 updates=[{k: v for k, v in u.items() if k != "_id"} for u in updates])
        moved = {(s["row"], str(s["key"])) for s in r.get("skipped", [])}
        now = db.now_iso()
        for u in updates:
            if (u["row"], str(u["key"])) in moved:
                res.append({"id": u["_id"], "ok": False, "error": "Row moved in the sheet — run Check again"})
            else:
                conn.execute("INSERT INTO gsheet_sync(location_id,sent_at) VALUES(?,?) "
                             "ON CONFLICT(location_id) DO UPDATE SET sent_at=excluded.sent_at", (u["_id"], now))
                res.append({"id": u["_id"], "ok": True, "pdf": cfg["link_col"] in u["values"] and any(
                    i.pdf for i in body.items if i.id == u["_id"])})
        conn.commit()
    return {"ok": True, "results": res}


class LogIn(BaseModel):
    rows: int = 0
    pdf: int = 0
    failed: int = 0
    alarms: int = 0
    errors: list[str] = []


@router.post("/log")
def add_log(body: LogIn, conn: sqlite3.Connection = Depends(get_db), user=Depends(require_admin)):
    conn.execute("INSERT INTO gsheet_log(at,by_name,rows,pdf,failed,alarms,detail) VALUES(?,?,?,?,?,?,?)",
                 (db.now_iso(), user["full_name"] or user["username"], body.rows, body.pdf, body.failed, body.alarms,
                  json.dumps(body.errors[:200], ensure_ascii=False)))
    conn.commit()
    audit(conn, user, "gsheet_update", "settings", "", f"{body.rows} rows, {body.pdf} PDF, {body.failed} failed")
    return {"ok": True, "log": log_rows(conn)}


def log_rows(conn, n: int = 20) -> list[dict]:
    return [{**dict(r), "detail": json.loads(r["detail"] or "[]")} for r in
            conn.execute("SELECT * FROM gsheet_log ORDER BY id DESC LIMIT ?", (n,))]


@router.get("/log")
def get_log(conn: sqlite3.Connection = Depends(get_db), user=Depends(require_admin)):
    return {"log": log_rows(conn)}


class CreateIn(BaseModel):
    rows: list[int]


@router.post("/create")
def create_from_sheet(body: CreateIn, conn: sqlite3.Connection = Depends(get_db), user=Depends(require_admin)):
    """Buat lokasi draf dari baris sheet yang belum ada di BAA Flow (nama, wilayah, SID = ID, SO).
    Tanggal aktivasi tetap diisi operator saat entry."""
    from ..services import wilayah
    from .import_loc import _import_wil
    from .locations import _WIL_SET, _format_code
    cfg = config(conn)
    res = call(cfg, "read", columns=[cfg[k] for k in COLS if cfg[k]])
    out = reconcile(conn, cfg, res)
    allowed = {s["row"] for s in out["alarms"]["only_sheet"]}
    rows = {r["row"]: r["v"] for r in res.get("rows", [])}
    made, skipped, add_so = [], [], []
    now = db.now_iso()
    for rn in body.rows:
        v = rows.get(rn)
        if rn not in allowed or not v:
            skipped.append(rn)
            continue
        name = (v.get(cfg["name_col"]) or "").strip()
        key = (v.get(cfg["key_col"]) or "").strip()
        sid = ""
        if key:
            try:
                sid = norm_sid(conn, key)
                check_sid_free(conn, sid)
            except HTTPException:
                sid = ""
        so_raw = db.norm_so(v.get(cfg["so_col"]) or "")
        so = db.so_match(conn, so_raw) if so_raw else ""
        if so_raw and not so:
            so = so_raw
            db.set_setting(conn, "so_list", db.so_list(conn) + [so])
            add_so.append(so)
        w = wilayah.match(v.get(cfg["desa_col"]) or "", v.get(cfg["kec_col"]) or "", v.get(cfg["kab_col"]) or "",
                          v.get(cfg["prov_col"]) or "")
        w["raw"] = {k: (v.get(cfg[k + "_col"]) or "").strip() for k in ("desa", "kec", "kab", "prov")}
        cur = conn.execute(
            "INSERT INTO locations(code,name,data_json,status,created_by,owner_id,created_at,updated_at,sid,so) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            ("", name, json.dumps({"nama_lokasi": name}, ensure_ascii=False), "draft", user["id"], user["id"],
             now, now, sid or None, so or None))
        lid = cur.lastrowid
        conn.execute("UPDATE locations SET code=?, modified_at=?, modified_by=? WHERE id=?",
                     (_format_code(conn, lid), now, user["id"], lid))
        wv = _import_wil(w, {})
        if wv:
            conn.execute(f"UPDATE locations SET {_WIL_SET} WHERE id=?", (*wv, lid))
        db.log_activity(conn, lid, user["id"], "create", "Google Sheet", now)
        made.append(lid)
    conn.commit()
    audit(conn, user, "gsheet_create", "location", "", f"{len(made)} from Google Sheet")
    return {"ok": True, "created": len(made), "skipped": len(skipped), "so_added": add_so}
