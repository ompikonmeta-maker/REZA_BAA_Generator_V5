"""Auto-sort foto ke kategori berdasarkan konvensi nama file / subfolder.

Cocokkan kata kunci (dari settings ``photo_categories``) terhadap nama file dan
nama folder asal. Kategori pertama yang cocok menang. Tidak cocok => 'uncategorized'.
"""
from __future__ import annotations

import re
from typing import Iterable

_norm_re = re.compile(r"[^a-z0-9]+")


def _normalize(text: str) -> str:
    return _norm_re.sub(" ", (text or "").lower()).strip()


def match_category(
    filename: str,
    categories: Iterable[dict],
    folder: str = "",
) -> tuple[str, str]:
    """Kembalikan (category_key, matched_by).

    matched_by: 'filename' | 'folder' | '' (tak cocok).

    Nama file diprioritaskan karena lebih spesifik: saat mengunggah satu
    folder berisi banyak foto dgn nama berbeda (mis. 'Foto SN Router.jpg'),
    setiap foto tetap masuk kategorinya sendiri. Nama folder hanya dipakai
    sebagai fallback bila nama file tak mengandung kata kunci apa pun
    (mis. foto diorganisir per-subfolder dgn nama file acak).
    """
    fname = _normalize(filename)
    fdir = _normalize(folder)

    # 1) cocokkan berdasar nama file dulu (paling spesifik per-foto)
    for cat in categories:
        for kw in cat.get("keywords", []):
            k = _normalize(kw)
            if k and k in fname:
                return cat["key"], "filename"
    # 2) fallback: nama folder/subfolder asal
    for cat in categories:
        for kw in cat.get("keywords", []):
            k = _normalize(kw)
            if k and k in fdir:
                return cat["key"], "folder"
    return "uncategorized", ""


def category_needs_ocr(category_key: str, categories: Iterable[dict]) -> bool:
    for cat in categories:
        if cat["key"] == category_key:
            return bool(cat.get("ocr"))
    return False
