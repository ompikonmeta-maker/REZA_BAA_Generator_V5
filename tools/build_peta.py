"""Bangun app/data/peta.json: path SVG batas kab/kota + provinsi (38 provinsi terkini).

Sumber geometri: geoBoundaries IDN ADM2 (gbOpen, CC BY 4.0, https://www.geoboundaries.org),
dicocokkan ke kode kab/kota Kemendagri (app/data/wilayah.tsv.gz) lewat nama. Provinsi =
gabungan kab/kota per kode provinsi Kemendagri (jadi pemekaran Papua ikut benar).
Butuh shapely (hanya saat build, bukan saat aplikasi berjalan):

    python tools/build_peta.py path/to/geoBoundaries-IDN-ADM2_simplified.geojson
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from shapely.geometry import shape
from shapely.ops import unary_union

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.services import wilayah  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "app" / "data" / "peta.json"
LON0, LON1, LAT0, LAT1, W = 94.6, 141.4, 6.3, -11.2, 1000.0
H = round(W * (LAT0 - LAT1) / (LON1 - LON0), 1)
SKIP = {"danau", "danau toba", "hutan", "waduk cirata", "wadung kedungombo"}
RENAMED = {"maluku tenggara barat": "kepulauan tanimbar", "mamuju utara": "pasangkayu", "toba samosir": "toba",
           "siau tagulandang biaro": "kep siau tagulandang biaro", "mahakam hulu": "mahakam ulu",
           "kota baru": "kotabaru"}


def key(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def build_index():
    kabs = {k: v for k, v in wilayah._load()["names"].items() if k.count(".") == 1}
    idx: dict[str, list[str]] = {}
    for k, v in kabs.items():
        base = re.sub(r"^(kabupaten administrasi|kota administrasi|kabupaten|kota) ", "", v.lower())
        is_kota = v.lower().startswith("kota")
        for name in ({("kota " if is_kota else "") + base, base} if is_kota else {base, "kabupaten " + base}):
            idx.setdefault(key(name), []).append(k)
    return kabs, idx


def match(name: str, kabs, idx) -> str | None:
    n = name.lower().strip()
    if n in SKIP:
        return None
    n = RENAMED.get(n, n)
    c = list(dict.fromkeys(idx.get(key(n), [])))
    if len(c) > 1:                          # "Bandung" -> Kabupaten (kota selalu ber-prefiks "Kota")
        c = [k for k in c if not kabs[k].lower().startswith("kota")] or c
    return c[0] if len(c) == 1 else None


def path(geom, tol: float) -> str:
    g = geom.simplify(tol, preserve_topology=True)
    polys = [g] if g.geom_type == "Polygon" else list(getattr(g, "geoms", []))
    out = []
    for p in polys:
        if p.is_empty or p.area < tol * tol * 4:
            continue
        pts = [(((x - LON0) / (LON1 - LON0)) * W, ((LAT0 - y) / (LAT0 - LAT1)) * H) for x, y in p.exterior.coords]
        out.append("M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + "Z")
    return "".join(out)


def box(geom) -> list[float]:
    x0, y0, x1, y1 = geom.bounds
    a = ((x0 - LON0) / (LON1 - LON0)) * W, ((LAT0 - y1) / (LAT0 - LAT1)) * H
    b = ((x1 - LON0) / (LON1 - LON0)) * W, ((LAT0 - y0) / (LAT0 - LAT1)) * H
    return [round(a[0], 1), round(a[1], 1), round(b[0] - a[0], 1), round(b[1] - a[1], 1)]


def main(src: str) -> None:
    kabs, idx = build_index()
    feats = json.load(open(src, encoding="utf-8"))["features"]
    geoms: dict[str, list] = {}
    miss = []
    for f in feats:
        k = match(f["properties"]["shapeName"], kabs, idx)
        if not k:
            if f["properties"]["shapeName"].lower() not in SKIP:
                miss.append(f["properties"]["shapeName"])
            continue
        geoms.setdefault(k, []).append(shape(f["geometry"]).buffer(0))
    kab_out, by_prov = {}, {}
    for k, gs in geoms.items():
        g = unary_union(gs)
        kab_out[k] = {"d": path(g, 0.008), "b": box(g)}
        by_prov.setdefault(k[:2], []).append(g)
    prov_out = {}
    for p, gs in by_prov.items():
        g = unary_union([x.buffer(0.002) for x in gs])
        prov_out[p] = {"d": path(g, 0.02), "b": box(g)}
    data = {"source": "geoBoundaries IDN ADM2 (CC BY 4.0) · kode Kemendagri", "w": W, "h": H,
            "prov": prov_out, "kab": kab_out}
    OUT.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    print(f"{OUT} · {len(prov_out)} prov · {len(kab_out)}/{len(kabs)} kab/kota · {OUT.stat().st_size // 1024} KB")
    if miss:
        print("tidak cocok:", miss)
    print("kab tanpa geometri:", [kabs[k] for k in kabs if k not in kab_out])


if __name__ == "__main__":
    main(sys.argv[1])
