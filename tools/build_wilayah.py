"""Bangun app/data/wilayah.tsv.gz dari dump SQL data wilayah Kemendagri.

Sumber: https://github.com/cahyadsn/wilayah (db/wilayah.sql, lisensi MIT),
mengikuti Kepmendagri tentang kode & data wilayah. Jalankan ulang saat ada
Kepmendagri baru, lalu build aplikasi (EXE memperbarui referensi saat start):

    python tools/build_wilayah.py path/to/wilayah.sql "Kepmendagri 300.2.2-2138 Tahun 2025"
"""
from __future__ import annotations

import gzip
import re
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "app" / "data" / "wilayah.tsv.gz"


def main(sql_path: str, version: str) -> None:
    s = Path(sql_path).read_text(encoding="utf-8")
    rows = re.findall(r"\('([0-9.]+)','((?:[^'\\]|\\.|'')*)'\)", s)
    seen: dict[str, str] = {}
    for kode, nama in rows:
        nama = nama.replace("''", "'").replace("\\'", "'").strip()
        nama = re.sub(r"\s+", " ", nama)
        seen[kode] = nama
    lv = {}
    for k in seen:
        lv[len(k.split("."))] = lv.get(len(k.split(".")), 0) + 1
    if lv.get(1, 0) < 30 or lv.get(4, 0) < 50000:
        raise SystemExit(f"Data tidak lengkap: {lv}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(OUT, "wt", encoding="utf-8", compresslevel=9) as f:
        f.write(f"#version\t{version}\n")
        for k in sorted(seen, key=lambda x: [int(p) for p in x.split(".")]):
            f.write(f"{k}\t{seen[k]}\n")
    print(f"{OUT} · {lv} · {OUT.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "Kepmendagri")
