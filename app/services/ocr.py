"""Baca serial number (SN) dari foto: barcode dulu, lalu OCR Tesseract.

Urutan:
1. Barcode/QR/DataMatrix dibaca di server (zxing-cpp). Hasil barcode akurat,
   jadi selalu menang dari teks OCR.
2. OCR Tesseract beberapa lintasan (skala & mode berbeda); token dikumpulkan,
   dipilih lewat voting + skor (kata kunci "SN", prefix, panjang, campuran
   huruf-angka). Teks watermark kamera GPS (tanggal, koordinat, ketinggian,
   alamat) dan baris MAC / model / password dibuang atau diturunkan.
3. Aturan SN per kategori foto (opsional, diatur admin): prefix, panjang
   min–max, huruf yang tidak pernah dipakai (dibaca sebagai angka mirip),
   dan apakah akhiran "/r2" ikut disimpan.

Semua bagian opsional: tanpa zxing-cpp barcode dilewati, tanpa Tesseract
hanya barcode; ``available()`` False bila keduanya tidak ada.
"""
from __future__ import annotations

import os
import re
from collections import defaultdict
from pathlib import Path

try:
    import pytesseract
    from PIL import Image, ImageFilter, ImageOps
    _IMPORT_OK = True
except Exception:  # pragma: no cover
    _IMPORT_OK = False

try:
    import zxingcpp
    _ZX_OK = True
except Exception:  # pragma: no cover
    _ZX_OK = False


def _configure_tesseract() -> None:
    """Cari binary Tesseract secara portabel (tanpa install admin).

    Prioritas: env REZA_BAA_TESSERACT > folder ``tesseract/`` di samping exe/app
    > biarkan PATH sistem yang menentukan.
    """
    if not _IMPORT_OK:
        return
    from .. import config
    candidates = []
    env = os.environ.get("REZA_BAA_TESSERACT")
    if env:
        candidates.append(Path(env))
    for name in ("tesseract.exe", "tesseract"):
        candidates.append(config.BASE_DIR / "tesseract" / name)
    for cand in candidates:
        if cand and cand.exists():
            pytesseract.pytesseract.tesseract_cmd = str(cand)
            return


if _IMPORT_OK:
    _configure_tesseract()

# Tesseract + OpenMP multi-thread bisa melambat drastis (puluhan detik) saat CPU dipakai proses lain;
# satu thread per panggilan justru stabil ±1 detik.
os.environ.setdefault("OMP_THREAD_LIMIT", "1")

_TESS: bool | None = None


def tesseract_available() -> bool:
    global _TESS
    if _TESS is None:
        if not _IMPORT_OK:
            _TESS = False
        else:
            try:
                pytesseract.get_tesseract_version()
                _TESS = True
            except Exception:
                _TESS = False
    return _TESS


def barcode_available() -> bool:
    return _IMPORT_OK and _ZX_OK


def available() -> bool:
    """Ada mesin pembaca SN (OCR atau barcode)."""
    return tesseract_available() or barcode_available()


# ---------------------------------------------------------------- aturan SN
DEFAULT_MIN_LEN = 5
MIN_SHOW = -1.0      # skor minimum untuk ditawarkan sebagai kandidat
MIN_AUTO = 1.5       # skor minimum untuk diisikan otomatis sebagai SN
# huruf -> angka yang bentuknya mirip (dipakai bila admin menandai huruf itu tidak pernah ada di SN)
_LOOKALIKE = {"O": "0", "Q": "0", "D": "0", "I": "1", "L": "1", "Z": "2", "S": "5", "B": "8", "G": "6", "T": "7", "A": "4"}
# bentuk kanonik untuk mengelompokkan bacaan yang hanya beda huruf/angka mirip
_CANON = str.maketrans(_LOOKALIKE)


def rule_of(cat: dict | None) -> dict:
    """Aturan SN dari dict kategori foto (kunci opsional; bawaan = tanpa aturan)."""
    cat = cat or {}

    def _int(v):
        try:
            v = int(v)
            return v if v > 0 else None
        except (TypeError, ValueError):
            return None
    no = "".join(ch for ch in str(cat.get("sn_no") or "").upper() if ch in _LOOKALIKE)
    lo, hi = _int(cat.get("sn_min")), _int(cat.get("sn_max"))
    if lo and hi and lo > hi:
        lo, hi = hi, lo
    chars = str(cat.get("sn_chars") or "").lower()
    return {"prefixes": [str(p).upper().strip() for p in (cat.get("prefixes") or []) if str(p).strip()],
            "min": lo, "max": hi, "no": no, "chars": chars if chars in ("hex", "digits") else "",
            "suffix": bool(cat.get("sn_suffix"))}


def rule_for(categories, key: str) -> dict:
    """Aturan SN untuk kategori foto ``key`` dari daftar setting photo_categories."""
    return rule_of(next((c for c in categories or [] if c.get("key") == key), None))


def _fix_prefix(tok: str, prefixes) -> tuple[str, bool]:
    for p in prefixes:
        if len(tok) > len(p) and tok[:len(p)].translate(_CANON) == p.translate(_CANON):
            return p + tok[len(p):], True
    return tok, False


def _apply_rule(tok: str, rule) -> tuple[str, bool]:
    """Normalisasi token sesuai aturan -> (token, cocok_prefix)."""
    tok, pref = _fix_prefix(tok, rule["prefixes"])
    bad = set(rule["no"])
    if rule["chars"] == "hex":
        bad |= set(_LOOKALIKE) - set("ABCDEF")
    elif rule["chars"] == "digits":
        bad |= set(_LOOKALIKE)
    if bad:
        head = max([len(p) for p in rule["prefixes"] if tok.startswith(p)] or [0]) if pref else 0
        tail = "".join(_LOOKALIKE[c] if c in bad else c for c in tok[head:])
        tok = tok[:head] + tail
    return tok, pref


def _chars_ok(sn: str, rule) -> bool:
    body = sn
    for p in rule["prefixes"]:
        if sn.startswith(p):
            body = sn[len(p):]
            break
    if rule["chars"] == "hex":
        return all(c in "0123456789ABCDEF-" for c in body)
    if rule["chars"] == "digits":
        return all(c.isdigit() or c == "-" for c in body)
    return not any(c in rule["no"] for c in body)


# ---------------------------------------------------------------- pola teks
_SN_KW = re.compile(r"(?:\bS\s*/\s*N|\bS\.?N\b|\bSN(?=[:#.\s]|$)|SERIAL\s*(?:NO\.?|NUMBER|NUM\.?)?|\bSER\.?\s*NO)\s*[:#.]?\s*")
# baris yang hampir pasti bukan SN (bila tidak ada kata kunci SN di baris itu)
_NEG_LINE = re.compile(r"(?:\bMODEL\b|\bP\s*/\s*N\b|\bPN\b|PART\s*NO|\bMAC\b|\bE\d{2}\s*:|PASS(?:WORD)?|\bSSID\b|\bWI-?FI\b|"
                       r"\bKEY\b|\bPIN\b|\bUSER(?:NAME)?\b|\bFCC\b|\bIC\s*:|\bINPUT\b|\bOUTPUT\b|\bDC\b|\bAC\b|\bCMIIT\b|"
                       r"\bSKU\b|\bIMEI\b|\bHW\b|\bFW\b|\bVER(?:SION)?\b|\bREV\b|\bPOWER\b|\bMADE IN\b)")
# watermark aplikasi kamera GPS / timestamp
_MONTHS = "JAN|FEB|MAR|APR|MAY|MEI|JUN|JUL|AUG|AGU|AGS|SEP|OCT|OKT|NOV|DEC|DES"
_WATERMARK = re.compile(r"(?:ALTITUDE|ALTITUD|KETINGGIAN|SPEED|KECEPATAN|LATITUDE|LONGITUDE|\bLAT\b|\bLONG?\b|"
                        r"KM\s*/\s*H|MSNM|MDPL|INDEX\s*NUMBER|\bJALAN\b|\bJL\.?\b|\bKOTA\b|\bKAB(?:UPATEN)?\b|"
                        r"\bKEC(?:AMATAN)?\b|\bDESA\b|\bKEL(?:URAHAN)?\b|PROVIN|INDONESIA|\bGPS\b|"
                        r"\b\d{1,2}\s+(?:" + _MONTHS + r")[A-Z]*\s+\d{2,4}\b|\b\d{1,2}[:.]\d{2}[:.]\d{2}\b|"
                        r"\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b|\d+[.,]\d{3,}\s*[NSEWTUBLS]\b)")
_TOKEN = re.compile(r"[A-Z0-9](?:[A-Z0-9\-]*[A-Z0-9])?(?:/[A-Z0-9]{1,5})*")
_MAC_RE = re.compile(r"^(?:[0-9A-F]{2}[-:.]){5}[0-9A-F]{2}$")
# simbol yang sering dibaca Tesseract sebagai pengganti huruf/angka di tengah SN (mis. 0 -> "@")
_GLYPH = {"@": "0", "§": "S", "$": "S", "€": "E", "£": "E", "|": "I"}
_GLYPH_RE = re.compile(r"(?<=[A-Z0-9])[@§$€£|](?=[A-Z0-9])|(?<=[A-Z0-9]{2})[@§$€£](?=\b)|(?<=[\s:])[@§$€£](?=[A-Z0-9]{2})", re.I)


def _fix_glyphs(line: str) -> str:
    return _GLYPH_RE.sub(lambda m: _GLYPH[m.group(0)], line)


def _line_tokens(line: str, min_len: int, orig: str | None = None):
    """-> [(base, full)] token mirip-SN dalam satu baris (huruf besar).

    ``orig`` = baris yang sama dengan huruf asli: akhiran "/r2" disimpan apa adanya (tidak jadi "/R2").
    """
    out = []
    for m in _TOKEN.finditer(line):
        full = m.group(0).strip("-")
        base = full.split("/")[0].strip("-")
        if orig is not None and len(full) > len(base):
            i = m.start() + m.group(0).index(full) + len(base)
            full = base + orig[i:i + len(full) - len(base)]
        if len(base) < min_len or _MAC_RE.match(base):
            continue
        # angka desimal / koordinat yang tersambung tanda baca
        s, e = m.span()
        if (s > 0 and line[s - 1] in ".," and line[s - 2:s - 1].isdigit()) or \
                (e < len(line) - 1 and line[e] in ".," and line[e + 1].isdigit()):
            continue
        out.append((base, full))
    return out


def _observe(text: str, rule, weight: float = 1.0):
    """Teks OCR -> daftar observasi (base, full, bobot, anchored, negatif)."""
    min_len = max(3, min(DEFAULT_MIN_LEN, rule["min"] or DEFAULT_MIN_LEN))
    obs = []
    lines = []
    for raw in (text or "").splitlines():
        lo = _fix_glyphs(raw.strip())
        up = lo.upper()
        if up:
            lines.append((up, lo if len(lo) == len(up) else up))
    anchor_next = False
    for ln, lo in lines:
        if _WATERMARK.search(ln):
            anchor_next = False
            continue
        kw = _SN_KW.search(ln)
        neg = bool(_NEG_LINE.search(ln)) and not kw
        if kw:
            before = ln[:kw.start()]
            after = ln[kw.end():]
            toks_after = _line_tokens(after, min_len, lo[kw.end():])
            for i, (b, f) in enumerate(toks_after):
                obs.append((b, f, weight, i == 0, False))
            for b, f in _line_tokens(before, min_len):
                obs.append((b, f, weight, False, False))
            anchor_next = not toks_after
            continue
        toks = _line_tokens(ln, min_len, lo)
        for i, (b, f) in enumerate(toks):
            obs.append((b, f, weight, anchor_next and i == 0, neg))
        anchor_next = False
        # "KIT 303891256" -> prefix terpisah spasi: gabungkan
        words = ln.split()
        for a, b in zip(words, words[1:]):
            for p in rule["prefixes"]:
                if a.translate(_CANON) == p.translate(_CANON) and _TOKEN.fullmatch(b):
                    obs.append((p + b.split("/")[0], p + b, weight * 0.8, False, neg))
    return obs


def _vote(spellings: list[tuple[str, float]]) -> str:
    """Pilih ejaan per posisi karakter (bobot terbesar) di antara bacaan sepanjang sama."""
    by_len = defaultdict(float)
    for s, w in spellings:
        by_len[len(s)] += w
    L = max(by_len.items(), key=lambda kv: kv[1])[0]
    same = [(s, w) for s, w in spellings if len(s) == L]
    out = []
    for i in range(L):
        cnt = defaultdict(float)
        for s, w in same:
            cnt[s[i]] += w
        out.append(max(cnt.items(), key=lambda kv: kv[1])[0])
    return "".join(out)


def _clean_barcode(t: str) -> str:
    t = re.sub(r"\s+", "", t or "").upper()
    t = re.sub(r"^(?:S/?N|SERIAL(?:NO|NUMBER)?)[:#.]?", "", t)
    return t


def _rank(obs, barcodes, rule) -> list[dict]:
    """-> [{sn, full, score, src}] terurut; src 'barcode' / 'ocr'."""
    groups = defaultdict(list)
    for b, f, w, anc, neg in obs:
        nb, pref = _apply_rule(b, rule)
        nf = nb + f[len(b):]
        groups[nb.translate(_CANON)].append((nb, nf, w, anc, neg, pref, any(c.isdigit() for c in b)))
    scored = {}
    for key, items in groups.items():
        sn = _vote([(i[0], i[2]) for i in items])
        fulls = defaultdict(float)
        for i in items:
            if i[1].startswith(sn) or len(i[1]) > len(i[0]):
                fulls[sn + i[1][len(i[0]):]] += i[2]
        full = max(fulls.items(), key=lambda kv: kv[1])[0] if fulls else sn
        # angka dihitung dari bacaan asli: kata biasa ("COMPLIES") tidak jadi mirip-SN karena aturan O -> 0
        alpha, digit = any(c.isalpha() for c in sn), any(i[6] for i in items)
        s = min(4.0, sum(i[2] for i in items))
        s += 0.6 * min(len(sn), 16) / 16
        if alpha and digit:
            s += 2.0
        elif digit:
            s += 0.5 if len(sn) >= 8 else -1.5
        else:
            s -= 3.0
        if any(i[3] for i in items):
            s += 4.0
        if all(i[4] for i in items):
            s -= 2.5
        if any(i[5] for i in items):
            s += 4.0
        if "-" in sn and not alpha:
            s -= 1.0                                            # pola P/N "58-5872-10"
        s += _len_score(sn, rule)
        if not _chars_ok(sn, rule):
            s -= 4.0
        if not alpha and not digit:
            continue
        scored[key] = {"sn": sn, "full": full, "score": s, "src": "ocr"}
    for raw in barcodes:
        b = _clean_barcode(raw)
        base = b.split("/")[0]
        if not base or not _TOKEN.fullmatch(b) or _MAC_RE.match(base) or len(base) < 3:
            continue                                            # URL, teks panjang, MAC
        nb, pref = _apply_rule(base, rule)
        key = nb.translate(_CANON)
        # barcode akurat -> selalu di atas bacaan teks (skor teks maks ±17)
        s = 20.0 + (4.0 if pref else 0.0) + _len_score(nb, rule)
        if key in scored:
            s += 2.0                                            # dikonfirmasi teks OCR
        if not any(c.isdigit() for c in nb):
            s -= 3.0
        if not _chars_ok(nb, rule):
            s -= 4.0
        prev = scored.get(key)
        full = nb + b[len(base):]
        if prev and len(prev["full"]) > len(prev["sn"]) and len(full) == len(nb):
            full = nb + prev["full"][len(prev["sn"]):]          # akhiran "/r2" dari teks label
        scored[key] = {"sn": nb, "full": full, "score": max(s, prev["score"] if prev else s), "src": "barcode"}
    return sorted(scored.values(), key=lambda d: -d["score"])


def _len_score(sn: str, rule) -> float:
    lo, hi = rule["min"], rule["max"]
    if not lo and not hi:
        return 0.0
    n = len(sn)
    if (lo and n < lo) or (hi and n > hi):
        return -4.0 - min(3, abs(n - (lo if lo and n < lo else hi)))
    return 1.5


# ---------------------------------------------------------------- gambar
def _gray(img):
    img = ImageOps.exif_transpose(img)
    return img.convert("L")


def read_barcodes(img, roi: bool = False) -> list[str]:
    """Isi semua barcode/QR/DataMatrix (unik, urut kemunculan)."""
    if not barcode_available():
        return []
    g = img if img.mode == "L" else _gray(img)
    out: list[str] = []

    def scan(im) -> bool:
        try:
            res = zxingcpp.read_barcodes(im)
        except Exception:
            return False
        for r in res:
            t = (r.text or "").strip()
            if t and t not in out:
                out.append(t)
        return bool(res)

    def tries(im):
        # foto kecil / terkompres: garis barcode terlalu tipis -> perbesar 2x, 3x (maks ±2400 px)
        yield im
        yield ImageOps.autocontrast(im, cutoff=1)
        for f in (2, 3):
            if max(im.size) * f <= 2600:
                yield im.resize((im.width * f, im.height * f), Image.LANCZOS)
        if max(im.size) > 2600:
            yield im.resize((im.width // 2, im.height // 2), Image.LANCZOS)

    for im in tries(g):
        if scan(im) and not roi:
            return out
    if out or roi:
        return out
    # tidak ketemu: potong jadi 3x3 ubin bertumpuk (60%, geser 20%), perbesar tiap ubin
    w, h = g.size
    for ty in (0, 0.2, 0.4):
        for tx in (0, 0.2, 0.4):
            tile = g.crop((int(tx * w), int(ty * h), int((tx + 0.6) * w), int((ty + 0.6) * h)))
            for im in tries(tile):
                if scan(im):
                    break
    return out


def _tess(img, psm: int) -> str:
    try:
        return pytesseract.image_to_string(img, config=f"--psm {psm}", timeout=20) or ""
    except Exception:
        return ""


def _scaled(g, long_side: int):
    w, h = g.size
    s = long_side / max(w, h)
    if abs(s - 1) < 0.05:
        return g
    return g.resize((max(1, int(w * s)), max(1, int(h * s))), Image.LANCZOS)


def _to_height(g, h: int, max_w: int = 3200):
    s = min(h / g.height, max_w / g.width)
    if s <= 1.05 and s >= 0.95:
        return g
    return g.resize((max(1, int(g.width * s)), max(1, int(g.height * s))), Image.LANCZOS)


def _prep(g):
    g = ImageOps.autocontrast(g, cutoff=1)
    # tulisan terang di label gelap -> balik warna. Tulisan = piksel minoritas yang jauh dari median.
    px = sorted(g.resize((64, 64)).getdata())
    med = px[len(px) // 2]
    bright = sum(1 for v in px if v > med + 70)
    dark = sum(1 for v in px if v < med - 70)
    if bright > dark * 1.5 and bright > 40:
        g = ImageOps.invert(g)
    return g


def _words(img, psm: int) -> list[tuple]:
    """-> [(teks, conf, x, y, w, h)] kata dari Tesseract."""
    try:
        d = pytesseract.image_to_data(img, config=f"--psm {psm}", output_type=pytesseract.Output.DICT, timeout=30)
    except Exception:
        return []
    out = []
    for i, t in enumerate(d["text"]):
        t = (t or "").strip()
        if t:
            try:
                c = float(d["conf"][i])
            except (TypeError, ValueError):
                c = -1.0
            out.append((t, c, d["left"][i], d["top"][i], d["width"][i], d["height"][i]))
    return out


def _lines(words) -> list[dict]:
    """Kelompokkan kata jadi baris (tumpang-tindih vertikal + jarak horizontal dekat)."""
    lines: list[dict] = []
    for w in sorted(words, key=lambda w: (w[3] + w[5] / 2, w[2])):
        cy, x0, x1 = w[3] + w[5] / 2, w[2], w[2] + w[4]
        for ln in lines:
            hh = max(ln["h"], w[5])
            gap = max(x0 - ln["x1"], ln["x0"] - x1)
            if abs(ln["cy"] - cy) < 0.6 * hh and gap < 3 * hh:
                ln["words"].append(w)
                ln["x0"], ln["x1"] = min(ln["x0"], x0), max(ln["x1"], x1)
                ln["y0"], ln["y1"] = min(ln["y0"], w[3]), max(ln["y1"], w[3] + w[5])
                ln["h"] = max(ln["h"], w[5])
                break
        else:
            lines.append({"words": [w], "cy": cy, "h": w[5], "x0": x0, "x1": x1, "y0": w[3], "y1": w[3] + w[5]})
    for ln in lines:
        ln["words"].sort(key=lambda w: w[2])
        ln["text"] = " ".join(w[0] for w in ln["words"])
    return lines


def _interest(text: str, rule) -> int:
    """Seberapa layak sebuah baris dibaca ulang lebih detail (0 = tidak)."""
    t = _fix_glyphs(text.upper())
    if _WATERMARK.search(t):
        return 0
    if _SN_KW.search(t):
        return 3
    if _NEG_LINE.search(t):
        return 0
    best = 0
    for b, _ in _line_tokens(t, 5):
        alpha, digit = any(c.isalpha() for c in b), any(c.isdigit() for c in b)
        if _fix_prefix(b, rule["prefixes"])[1]:
            best = max(best, 2)
        elif (alpha and digit) or (digit and len(b) >= 8):
            best = max(best, 1)
    return best


def _unframe(g):
    """Hapus garis lurus panjang (bingkai label, garis tabel): Tesseract sering gagal total bila teks dibingkai.

    Garis datar dicek per segmen (4 potong) supaya garis yang sedikit miring tetap terdeteksi.
    Dipakai hanya sebagai cadangan (bacaan pertama kosong), karena bisa ikut menghapus goresan huruf.
    """
    w, h = g.size
    if w < 16 or h < 16:
        return g
    bw = g.point(lambda v: 255 if v < 128 else 0)
    from PIL import ImageDraw
    out, d = None, None
    pad = max(1, min(w, h) // 80)
    n = 4
    for i in range(n):
        x0, x1 = w * i // n, w * (i + 1) // n
        rows = bw.crop((x0, 0, x1, h)).resize((1, h), Image.BOX).getdata()
        for y, v in enumerate(rows):
            if v > 255 * 0.7:
                if out is None:
                    out = g.copy()
                    d = ImageDraw.Draw(out)
                d.rectangle((x0, y - pad, x1, y + pad), fill=255)
    # garis tegak: harus hampir setinggi gambar (batang huruf lebih pendek)
    for x, v in enumerate(bw.resize((w, 1), Image.BOX).getdata()):
        if v > 255 * 0.8:
            if out is None:
                out = g.copy()
                d = ImageDraw.Draw(out)
            d.rectangle((x - pad, 0, x + pad, h), fill=255)
    return out or g


def _ocr_whole(g, rule) -> tuple[list, list[str]]:
    """Seluruh foto: cari baris teks yang mirip SN, lalu baca ulang tiap baris itu lebih detail (auto-ROI)."""
    p = _prep(g)
    long_side = max(p.size)
    target = 2000 if long_side < 1400 else min(2400, max(1600, long_side))
    sc = target / long_side
    big = _scaled(p, target).filter(ImageFilter.SHARPEN)
    lines = _lines(_words(big, 11))
    texts = [ln["text"] for ln in lines]
    obs = _observe("\n".join(texts), rule, 0.6)
    picks = sorted((ln for ln in lines if _interest(ln["text"], rule)),
                   key=lambda ln: (-_interest(ln["text"], rule), -ln["h"]))[:4]
    for ln in picks:
        h = ln["h"]
        kw = _SN_KW.search(ln["text"].upper()) is not None
        box = (ln["x0"] - 1.0 * h, ln["y0"] - 0.6 * h, ln["x1"] + (12 if kw else 1.0) * h, ln["y1"] + 0.6 * h)
        crop = p.crop(tuple(int(max(0, v) / sc) for v in box))
        if crop.width < 8 or crop.height < 6:
            continue
        o, ts = _ocr_line(crop, rule)
        obs += o
        texts += ts
    return obs, texts


def _ocr_line(crop, rule) -> tuple[list, list[str]]:
    obs, texts = [], []
    for unframe in (False, True):
        for hh in (90, 140):
            im = _to_height(crop, hh)
            im = (_unframe(im) if unframe else im).filter(ImageFilter.SHARPEN)
            for psm in (7, 6):
                t = _tess(im, psm)
                texts.append(t)
                obs += _observe(t, rule, 1.0)
        if obs:
            break
    return obs, texts


def _ocr_roi(g, rule) -> tuple[list, list[str]]:
    p = _prep(g)
    w, h = p.size
    rots = [0]
    if h > w * 1.3:
        rots = [90, 270]                                         # teks vertikal
    obs, texts = [], []

    def run(img):
        o, ts = [], []
        aspect = img.width / max(1, img.height)
        heights = (110, 220) if aspect >= 2.5 else (300, 600)
        big = None
        for unframe in (False, True):                           # bingkai label: coba hapus bila kosong
            for hh in heights:
                im = _to_height(img, hh)
                im = (_unframe(im) if unframe else im).filter(ImageFilter.SHARPEN)
                big = im
                for psm in ((7, 6) if aspect >= 6 else (6, 11)):
                    t = _tess(im, psm)
                    ts.append(t)
                    o += _observe(t, rule, 1.0)
            if o:
                break
        # area berisi beberapa baris: baca ulang baris yang mirip SN satu per satu
        if aspect < 6 and big is not None:
            sc = big.height / img.height
            lines = [ln for ln in _lines(_words(big, 6)) if _interest(ln["text"], rule)]
            for ln in sorted(lines, key=lambda ln: -_interest(ln["text"], rule))[:3]:
                hh = ln["h"]
                box = (ln["x0"] - hh, ln["y0"] - 0.6 * hh, ln["x1"] + hh, ln["y1"] + 0.6 * hh)
                crop = img.crop(tuple(int(max(0, v) / sc) for v in box))
                if crop.width >= 8 and crop.height >= 6:
                    lo, lt = _ocr_line(crop, rule)
                    o += lo
                    ts += lt
        return o, ts

    for r in rots:
        o, ts = run(p.rotate(r, expand=True) if r else p)
        obs += o
        texts += ts
    if not obs and rots == [0]:
        o, ts = run(p.rotate(180, expand=True))                 # label terbalik
        obs += o
        texts += ts
    return obs, texts


def analyze(img, rule: dict | None = None, roi: bool = False) -> dict:
    """-> {serial, full, candidates:[{sn,full,src}], barcodes, text}."""
    rule = rule or rule_of(None)
    g = _gray(img)
    barcodes = read_barcodes(g, roi=roi)
    obs, texts = [], []
    ranked = _rank([], barcodes, rule)
    # barcode yang memenuhi aturan kategori (prefix / panjang) -> cukup, OCR dilewati (cepat)
    sure = bool(ranked) and ranked[0]["score"] >= 24
    if tesseract_available() and not sure:
        obs, texts = (_ocr_roi if roi else _ocr_whole)(g, rule)
        ranked = _rank(obs, barcodes, rule)
        if not roi and (not ranked or ranked[0]["score"] < 4):
            for r in (90, 270):                                 # label miring / foto diputar
                o, ts = _ocr_whole(g.rotate(r, expand=True), rule)
                obs += o
                texts += ts
            ranked = _rank(obs, barcodes, rule)
    text = "\n".join(dict.fromkeys([b for b in barcodes] + [ln for t in texts for ln in t.splitlines() if ln.strip()]))
    # kandidat lemah (kata biasa, potongan) tidak ditawarkan; SN otomatis hanya bila cukup yakin
    cands = [{"sn": c["full"] if rule["suffix"] else c["sn"], "full": c["full"], "src": c["src"], "score": c["score"]}
             for c in ranked if c["score"] >= MIN_SHOW]
    seen, uniq = set(), []
    for c in cands:
        if c["sn"] not in seen:
            seen.add(c["sn"])
            uniq.append(c)
    best = uniq[0] if uniq and uniq[0]["score"] >= MIN_AUTO else None
    for c in uniq:
        c.pop("score", None)
    return {"serial": best["sn"] if best else "", "full": best["full"] if best else "",
            "candidates": uniq[:12], "barcodes": barcodes, "text": text}


def _empty() -> dict:
    return {"serial": "", "full": "", "candidates": [], "barcodes": [], "text": ""}


def read_image(image_path: str | Path, rule: dict | None = None) -> dict:
    """Seluruh foto (dipakai saat upload foto kategori OCR / baca ulang)."""
    if not available():
        return _empty()
    try:
        with Image.open(image_path) as img:
            img.load()
            return analyze(img, rule)
    except Exception:
        return _empty()


def read_bytes(data: bytes, rule: dict | None = None, roi: bool = True) -> dict:
    """Potongan area pilihan user (ROI) dari frontend."""
    if not data or not available():
        return _empty()
    try:
        from io import BytesIO
        with Image.open(BytesIO(data)) as img:
            img.load()
            return analyze(img, rule, roi=roi)
    except Exception:
        return _empty()


def read_serial(image_path: str | Path, rule: dict | None = None) -> tuple[str, str]:
    """Kembalikan (serial, raw_text) — untuk kolom photos.ocr_serial / ocr_text."""
    r = read_image(image_path, rule)
    return r["serial"], r["text"]
