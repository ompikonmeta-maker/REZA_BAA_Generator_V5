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
