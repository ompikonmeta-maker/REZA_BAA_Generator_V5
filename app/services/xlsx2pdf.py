"""Konversi .xlsx (hasil isi template) menjadi PDF.

Strategi berlapis dengan fallback aman:
  A. Microsoft Excel via COM (pywin32)   -> paling persis, butuh Excel (Windows)
  B. LibreOffice headless (soffice)      -> persis, butuh LibreOffice terpasang
Bila keduanya gagal/absen, ``xlsx_to_pdf`` mengembalikan False sehingga pemanggil
bisa fallback ke generator PDF sendiri (reportlab).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def _recenter_shapes(wb, anchor_cells=None) -> None:
    """Pusatkan tiap gambar tepat di tengah area fotonya (unit points, diambil
    dari Excel => bebas font). Skalakan turun bila lebih besar dari area.

    Area = range eksplisit ("B12:H26") atau MergeArea dari sel anchor tunggal.
    Bila ``anchor_cells`` diberikan, hanya gambar di area anchor tsb yang
    dipusatkan (agar logo/gambar bawaan template tidak ikut dipindah)."""
    for ws in wb.Worksheets:
        try:
            shapes = list(ws.Shapes)
        except Exception:
            continue
        areas = []
        for a in (anchor_cells or []):
            try:
                areas.append(ws.Range(a) if ":" in a else ws.Range(a).MergeArea)
            except Exception:
                pass
        for shp in shapes:
            try:
                if shp.Type != 13:            # 13 = msoPicture
                    continue
                cell = shp.TopLeftCell
                area = None
                for ar in areas:
                    if ws.Application.Intersect(cell, ar) is not None:
                        area = ar
                        break
                if area is None:
                    if anchor_cells:
                        continue               # bukan area foto kita -> lewati
                    area = cell.MergeArea
                aw, ah = float(area.Width), float(area.Height)
                shp.LockAspectRatio = True     # -1 (msoTrue) juga boleh
                w, h = float(shp.Width), float(shp.Height)
                margin = 4.0
                if w > aw - margin or h > ah - margin:
                    s = min((aw - margin) / w, (ah - margin) / h)
                    shp.Width = max(1.0, w * s)   # tinggi ikut karena aspect terkunci
                    w, h = float(shp.Width), float(shp.Height)
                shp.Left = float(area.Left) + (aw - w) / 2.0
                shp.Top = float(area.Top) + (ah - h) / 2.0
            except Exception:
                continue


def recenter_images_excel(xlsx: str, anchor_cells=None) -> bool:
    """Buka .xlsx di Excel, pusatkan gambar foto di sel merge, simpan. True bila sukses."""
    if sys.platform != "win32":
        return False
    try:
        import pythoncom  # type: ignore
        import win32com.client  # type: ignore
    except Exception:
        return False
    xl = wb = None
    try:
        pythoncom.CoInitialize()
        xl = win32com.client.DispatchEx("Excel.Application")
        xl.Visible = False
        xl.DisplayAlerts = False
        wb = xl.Workbooks.Open(str(Path(xlsx).resolve()))
        _recenter_shapes(wb, anchor_cells)
        wb.Save()
        return True
    except Exception:
        return False
    finally:
        try:
            if wb is not None:
                wb.Close(SaveChanges=False)
        except Exception:
            pass
        try:
            if xl is not None:
                xl.Quit()
        except Exception:
            pass
        try:
            import pythoncom  # type: ignore
            pythoncom.CoUninitialize()
        except Exception:
            pass


def _excel_com(xlsx: str, pdf: str, anchor_cells=None) -> bool:
    """Konversi via MS Excel (COM). Hanya jalan di Windows + Excel terpasang.
    Sekaligus memusatkan gambar di sel merge sebelum ekspor."""
    if sys.platform != "win32":
        return False
    try:
        import pythoncom  # type: ignore
        import win32com.client  # type: ignore
    except Exception:
        return False
    xl = None
    wb = None
    try:
        pythoncom.CoInitialize()
        xl = win32com.client.DispatchEx("Excel.Application")
        xl.Visible = False
        xl.DisplayAlerts = False
        wb = xl.Workbooks.Open(str(Path(xlsx).resolve()))
        try:
            _recenter_shapes(wb, anchor_cells)   # center akurat sebelum jadi PDF
        except Exception:
            pass
        # 0 = xlTypePDF ; export seluruh sheet yang ada (LOG sudah dibuang pemanggil)
        wb.ExportAsFixedFormat(0, str(Path(pdf).resolve()))
        return Path(pdf).exists()
    except Exception:
        return False
    finally:
        try:
            if wb is not None:
                wb.Close(SaveChanges=False)
        except Exception:
            pass
        try:
            if xl is not None:
                xl.Quit()
        except Exception:
            pass
        try:
            import pythoncom  # type: ignore
            pythoncom.CoUninitialize()
        except Exception:
            pass


def _find_soffice() -> str | None:
    for name in ("soffice", "soffice.exe", "soffice.bin"):
        p = shutil.which(name)
        if p:
            return p
    # lokasi umum di Windows
    for c in (
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    ):
        if os.path.exists(c):
            return c
    return None


def _libreoffice(xlsx: str, pdf: str) -> bool:
    soffice = _find_soffice()
    if not soffice:
        return False
    outdir = str(Path(pdf).resolve().parent)
    prof = Path(outdir) / "_lo_profile"
    try:
        subprocess.run(
            [soffice, f"-env:UserInstallation=file://{prof.resolve()}",
             "--headless", "--norestore", "--nologo", "--nofirststartwizard",
             "--convert-to", "pdf:calc_pdf_Export",
             "--outdir", outdir, str(Path(xlsx).resolve())],
            check=True, timeout=120,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception:
        return False
    produced = Path(outdir) / (Path(xlsx).stem + ".pdf")
    if not produced.exists():
        return False
    try:
        if produced.resolve() != Path(pdf).resolve():
            shutil.move(str(produced), str(pdf))
    except Exception:
        return False
    return Path(pdf).exists()


def xlsx_to_pdf(xlsx: str, pdf: str, anchor_cells=None) -> bool:
    """Coba Excel COM (center foto dulu) -> LibreOffice. True bila salah satu berhasil."""
    if _excel_com(xlsx, pdf, anchor_cells):
        return True
    if _libreoffice(xlsx, pdf):
        return True
    return False


def available() -> bool:
    """True bila ada mesin konversi (Excel di Windows atau LibreOffice)."""
    if sys.platform == "win32":
        try:
            import win32com.client  # noqa: F401
            return True
        except Exception:
            pass
    return _find_soffice() is not None


# ---------- cek ukuran kertas PDF vs Page Setup template ----------
# kode paperSize Excel -> (nama, lebar mm, tinggi mm) — ukuran yang umum dipakai
PAPER_MM = {1: ("Letter", 215.9, 279.4), 5: ("Legal", 215.9, 355.6), 8: ("A3", 297, 420), 9: ("A4", 210, 297),
            11: ("A5", 148, 210), 12: ("B4", 257, 364), 13: ("B5", 182, 257), 14: ("F4/Folio", 215.9, 330.2)}
_PT = 72 / 25.4


def expected_paper(xlsx: str) -> list[tuple[str, str, float, float]]:
    """[(sheet, nama kertas, lebar pt, tinggi pt)] dari Page Setup tiap sheet (orientasi diterapkan).
    Sheet dengan kode kertas tak dikenal dilewati."""
    import openpyxl
    out = []
    wb = openpyxl.load_workbook(xlsx, read_only=False)
    for ws in wb.worksheets:
        try:
            code = int(ws.page_setup.paperSize or 9)       # kosong = default Excel (A4 di Indonesia)
        except Exception:
            continue
        if code not in PAPER_MM:
            continue
        name, w, h = PAPER_MM[code]
        land = (ws.page_setup.orientation or "portrait") == "landscape"
        w, h = (h, w) if land else (w, h)
        out.append((ws.title, f"{name} {'landscape' if land else 'portrait'}", w * _PT, h * _PT))
    return out


def pdf_page_sizes(pdf: str) -> list[tuple[float, float]]:
    """Ukuran halaman (pt) dari /MediaBox, termasuk yang tersimpan di object stream terkompresi."""
    import re
    import zlib
    data = Path(pdf).read_bytes()
    blobs = [data]
    for m in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", data, re.S):
        try:
            blobs.append(zlib.decompress(m.group(1)))
        except Exception:
            pass
    sizes = []
    rx = re.compile(rb"/Type\s*/Page(?!s)[^>]*?/MediaBox\s*\[\s*([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s*\]"
                    rb"|/MediaBox\s*\[\s*([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s*\][^>]*?/Type\s*/Page(?!s)", re.S)
    for b in blobs:
        for m in rx.finditer(b):
            g = [x for x in m.groups() if x is not None]
            x0, y0, x1, y1 = map(float, g)
            sizes.append((abs(x1 - x0), abs(y1 - y0)))
    if not sizes:                                            # MediaBox diwariskan dari /Pages
        for b in blobs:
            for m in re.finditer(rb"/MediaBox\s*\[\s*([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s*\]", b):
                x0, y0, x1, y1 = map(float, m.groups())
                sizes.append((abs(x1 - x0), abs(y1 - y0)))
    return sizes


def _paper_name(w: float, h: float) -> str:
    for name, a, b in PAPER_MM.values():
        A, B = a * _PT, b * _PT
        if abs(w - A) < 6 and abs(h - B) < 6:
            return f"{name} portrait"
        if abs(w - B) < 6 and abs(h - A) < 6:
            return f"{name} landscape"
    return f"{w / _PT:.0f}x{h / _PT:.0f} mm"


def paper_warning(xlsx: str, pdf: str) -> str:
    """'' bila ukuran halaman PDF sesuai Page Setup template; selain itu pesan singkat (ASCII)."""
    try:
        exp = expected_paper(xlsx)
        got = pdf_page_sizes(pdf)
    except Exception:
        return ""
    if not exp or not got:
        return ""
    for w, h in got:
        if not any(abs(w - ew) < 6 and abs(h - eh) < 6 for _, _, ew, eh in exp):
            want = exp[0][1]
            return (f"Template paper is {want}, but the PDF came out {_paper_name(w, h)}. "
                    f"Check that the default printer in Windows supports {want.split()[0]} "
                    f"(or set 'Microsoft Print to PDF' as default), then export again.")
    return ""
