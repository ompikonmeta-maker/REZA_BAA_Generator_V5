"""Dokumen scan PDF per lokasi: validasi, thumbnail halaman 1, dan penggabungan
(scan di depan halaman BAA) saat export PDF. Murni Python (pypdf + Pillow)."""
from __future__ import annotations

import io
import sys
from pathlib import Path


def _pypdf():
    try:
        import pypdf
    except BaseException:  # pustaka 'cryptography' rusak di sebagian sistem -> pakai provider bawaan pypdf
        for k in [k for k in sys.modules if k == "pypdf" or k.startswith(("pypdf.", "cryptography"))]:
            sys.modules.pop(k, None)
        sys.modules["cryptography"] = None  # type: ignore[assignment]
        import pypdf
    return pypdf


def page_count(path) -> int:
    """Jumlah halaman; melempar ValueError bila bukan PDF yang bisa dibaca."""
    pypdf = _pypdf()
    try:
        r = pypdf.PdfReader(str(path))
        if r.is_encrypted:
            r.decrypt("")
        n = len(r.pages)
    except Exception as e:
        raise ValueError(f"Can't read the PDF ({e.__class__.__name__})") from e
    if n < 1:
        raise ValueError("The PDF has no pages")
    return n


def first_page_thumb(path, width: int = 360) -> bytes | None:
    """JPEG halaman 1 untuk pratinjau. Scan biasanya berupa satu gambar per
    halaman -> gambar terbesar di halaman 1 diambil. None bila tidak ada gambar."""
    from PIL import Image
    try:
        page = _pypdf().PdfReader(str(path)).pages[0]
        best = None
        for im in page.images:
            pil = im.image
            if best is None or pil.width * pil.height > best.width * best.height:
                best = pil
        if best is None:
            return None
        rot = int(page.get("/Rotate", 0) or 0) % 360
        if rot:
            best = best.rotate(-rot, expand=True)
        best = best.convert("RGB")
        best.thumbnail((width, width * 2), Image.LANCZOS)
        buf = io.BytesIO()
        best.save(buf, "JPEG", quality=82)
        return buf.getvalue()
    except Exception:
        return None


def first_page_size(path) -> tuple[float, float] | None:
    """(lebar, tinggi) pt halaman 1, rotasi diterapkan."""
    try:
        page = _pypdf().PdfReader(str(path)).pages[0]
        w, h = float(page.mediabox.width), float(page.mediabox.height)
        if int(page.get("/Rotate", 0) or 0) % 180:
            w, h = h, w
        return w, h
    except Exception:
        return None


def concat(parts: list, out_path) -> list[str]:
    """Gabungkan PDF berurutan ke out_path. Bagian yang gagal dibaca dilewati;
    kembalikan daftar nama file yang dilewati."""
    pypdf = _pypdf()
    w = pypdf.PdfWriter()
    skipped: list[str] = []
    for p in parts:
        try:
            r = pypdf.PdfReader(str(p))
            if r.is_encrypted:
                r.decrypt("")
            for pg in r.pages:
                w.add_page(pg)
        except Exception:
            skipped.append(Path(p).name)
    with open(out_path, "wb") as f:
        w.write(f)
    return skipped
