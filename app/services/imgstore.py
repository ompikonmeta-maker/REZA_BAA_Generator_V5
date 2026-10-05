"""Kompres foto saat disimpan agar folder data tidak cepat penuh.

- Sisi terpanjang maks 2000 px; foto (JPEG/WEBP) -> JPEG kualitas 85.
- Screenshot (PNG/GIF/BMP) tetap lossless sebagai PNG agar teks tetap tajam.
- Rotasi HP (EXIF orientation) diterapkan; metadata kamera (tanggal, GPS) dipertahankan.
- Foto yang sudah kecil (<= 2000 px dan <= 1 MB, tanpa rotasi), atau yang tidak jadi lebih kecil, tidak diubah.
"""
from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageOps

MAX_SIDE = 2000
SMALL_BYTES = 1024 * 1024
JPEG_QUALITY = 85
_LOSSLESS = {"PNG", "GIF", "BMP"}
_ORIENT = 0x0112


def compress(data: bytes) -> tuple[bytes, str] | None:
    """(bytes baru, ekstensi) bila foto perlu & bisa dikecilkan, selain itu None (simpan apa adanya)."""
    try:
        im = Image.open(BytesIO(data))
        if getattr(im, "is_animated", False):
            return None
        fmt = (im.format or "").upper()
        exif = im.getexif()
        orient = exif.get(_ORIENT, 1)
        w, h = im.size
        rotate = orient not in (0, 1)
        if max(w, h) <= MAX_SIDE and len(data) <= SMALL_BYTES and not rotate:
            return None
        im = ImageOps.exif_transpose(im)
        if _ORIENT in exif:
            exif[_ORIENT] = 1
        if max(im.size) > MAX_SIDE:
            im.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
        out = BytesIO()
        if fmt in _LOSSLESS:
            if im.mode not in ("RGB", "RGBA", "L", "LA", "P"):
                im = im.convert("RGBA")
            im.save(out, "PNG", optimize=True)
            ext = ".png"
        else:
            if im.mode in ("RGBA", "LA", "P"):
                rgba = im.convert("RGBA")
                bg = Image.new("RGB", rgba.size, (255, 255, 255))
                bg.paste(rgba, mask=rgba.split()[-1])
                im = bg
            elif im.mode not in ("RGB", "L"):
                im = im.convert("RGB")
            kw = {"quality": JPEG_QUALITY, "optimize": True, "progressive": True}
            if len(exif):
                kw["exif"] = exif.tobytes()
            im.save(out, "JPEG", **kw)
            ext = ".jpg"
        nb = out.getvalue()
        if len(nb) >= len(data) and not rotate:
            return None                     # tidak lebih kecil -> pertahankan asli
        return nb, ext
    except Exception:
        return None


def needs_check(path) -> bool:
    """Cek cepat (header saja) apakah file lama perlu dikompres."""
    try:
        size = path.stat().st_size
        with Image.open(path) as im:
            w, h = im.size
            orient = im.getexif().get(_ORIENT, 1)
        return max(w, h) > MAX_SIDE or size > SMALL_BYTES or orient not in (0, 1)
    except Exception:
        return False
