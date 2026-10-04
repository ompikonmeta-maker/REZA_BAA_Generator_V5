"""Referensi wilayah Kemendagri (provinsi → kab/kota → kecamatan → desa/kelurahan)
dan pencarian cepat untuk field "Wilayah".

Data: app/data/wilayah.tsv.gz (dibangun oleh tools/build_wilayah.py), dimuat
sekali ke memori (±84 rb desa). Pencarian:
- beberapa kata, urutan bebas; tiap kata = awalan kata di desa/kec/kab/prov,
  semua kata harus cocok ("cibodas lembang");
- singkatan provinsi (jabar, jatim, …) dan kata umum (kab, kec, desa, …);
- toleran salah ketik ringan (dikoreksi ke kata terdekat di kamus);
- kode wilayah ("32.17.01") = semua desa di bawahnya;
- urutan: kecocokan nama desa + wilayah yang sering dipakai di project.
"""
from __future__ import annotations

import difflib
import gzip
import re
import threading
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data" / "wilayah.tsv.gz"

_ALIAS = {
    "aceh": "11", "nad": "11", "sumut": "12", "sumbar": "13", "riau": "14", "jambi": "15", "sumsel": "16",
    "bengkulu": "17", "lampung": "18", "babel": "19", "kepri": "21", "dki": "31", "jakarta": "31",
    "jabar": "32", "jateng": "33", "diy": "34", "jogja": "34", "yogya": "34", "jatim": "35", "banten": "36",
    "bali": "51", "ntb": "52", "ntt": "53", "kalbar": "61", "kalteng": "62", "kalsel": "63", "kaltim": "64",
    "kaltara": "65", "sulut": "71", "sulteng": "72", "sulsel": "73", "sultra": "74", "gorontalo": "75",
    "sulbar": "76", "maluku": "81", "malut": "82", "papua": "91", "pabar": "92", "papsel": "93",
    "papteng": "94", "pappeg": "95", "pbd": "96",
}
_STOP = {"kab", "kabupaten", "kec", "kecamatan", "desa", "ds", "kel", "kelurahan", "prov", "provinsi",
         "propinsi", "dan", "di"}
_CODE = re.compile(r"^\d{2}(\.\d{1,4}){0,3}\.?$")

_lock = threading.Lock()
_D: dict | None = None


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", (s or "").lower())).strip()


def short_kab(nama: str) -> str:
    return re.sub(r"^Kabupaten\s+", "Kab. ", nama or "")


def _load() -> dict:
    global _D
    if _D is not None:
        return _D
    with _lock:
        if _D is not None:
            return _D
        names: dict[str, str] = {}
        version = ""
        with gzip.open(DATA, "rt", encoding="utf-8") as f:
            for line in f:
                k, _, v = line.rstrip("\n").partition("\t")
                if k == "#version":
                    version = v
                elif k:
                    names[k] = v
        desa = []           # (kode, hay, desa_norm)
        kecs = []           # kecamatan: (kode, hay, kec_norm) — untuk isian "desa manual"
        vocab: set[str] = set()
        for k, v in names.items():
            if k.count(".") == 2:
                p = k.split(".")
                kab_, prov_ = names.get(".".join(p[:2]), ""), names.get(p[0], "")
                kecs.append((k, " " + " ".join([_norm(v), _norm(kab_), _norm(prov_)]) + " ", _norm(v)))
                continue
            if k.count(".") != 3:
                continue
            p = k.split(".")
            kec, kab, prov = names.get(".".join(p[:3]), ""), names.get(".".join(p[:2]), ""), names.get(p[0], "")
            dn = _norm(v)
            hay = " " + " ".join([dn, _norm(kec), _norm(kab), _norm(prov)]) + " "
            desa.append((k, hay, dn))
            vocab.update(hay.split())
        by_first: dict[str, list[str]] = {}
        for w in vocab:
            by_first.setdefault(w[0], []).append(w)
        _D = {"names": names, "version": version, "desa": desa, "kec": kecs, "vocab": vocab, "by_first": by_first,
              "counts": {lv: sum(1 for k in names if k.count(".") == lv - 1) for lv in (1, 2, 3, 4)}}
        return _D


def meta() -> dict:
    d = _load()
    return {"version": d["version"], "provinsi": d["counts"][1], "kabkota": d["counts"][2],
            "kecamatan": d["counts"][3], "desa": d["counts"][4]}


def info(kode: str) -> dict | None:
    """Nama keempat tingkat untuk kode desa/kelurahan, atau None bila tak dikenal."""
    d = _load()
    kode = (kode or "").strip()
    if kode.count(".") != 3 or kode not in d["names"]:
        return None
    p = kode.split(".")
    n = d["names"]
    return {"kode": kode, "desa": n[kode], "kec": n.get(".".join(p[:3]), ""),
            "kab": n.get(".".join(p[:2]), ""), "prov": n.get(p[0], ""), "kel": p[3].startswith("1")}


def kec_info(kode: str) -> dict | None:
    """Nama kecamatan, kab/kota, provinsi untuk kode kecamatan (xx.xx.xx)."""
    d = _load()
    kode = (kode or "").strip()
    if kode.count(".") != 2 or kode not in d["names"]:
        return None
    p = kode.split(".")
    n = d["names"]
    return {"kode": kode, "kec": n[kode], "kab": n.get(".".join(p[:2]), ""), "prov": n.get(p[0], "")}


def name_of(kode: str) -> str:
    return _load()["names"].get(kode, "")


def _fix(t: str, d: dict) -> list[str]:
    """Kata terdekat di kamus untuk token salah ketik (awalan huruf sama)."""
    pool = d["by_first"].get(t[0], [])
    return difflib.get_close_matches(t, pool, n=3, cutoff=0.78)


def search(q: str, prov: str = "", kab: str = "", limit: int = 30, boost: dict | None = None,
           level: str = "desa", under: str = "") -> dict:
    """level='desa' (default) atau 'kec' (cari kecamatan); under = batasi ke kode induk."""
    d = _load()
    boost = boost or {}
    q = (q or "").strip()
    is_kec = level == "kec"
    rows = d["kec"] if is_kec else d["desa"]
    if under:
        rows = [r for r in rows if r[0].startswith(under.rstrip(".") + ".")]
    matched: list[dict] = []
    prefix = ""
    if _CODE.match(q):
        prefix = q.rstrip(".")
        toks: list[str] = []
    else:
        toks = [t for t in _norm(q).split() if t not in _STOP]
        for t in list(toks):
            if t in _ALIAS and not (prov and prov != _ALIAS[t]):
                prov = prov or _ALIAS[t]
                toks.remove(t)
                matched.append({"t": t, "w": d["names"].get(_ALIAS[t], "")})
    if not toks and not prefix and not prov and not under:
        return {"total": 0, "items": [], "facets": [], "facet_level": "prov", "matched": matched}
    cand = rows
    if prefix:
        cand = [r for r in cand if r[0] == prefix or r[0].startswith(prefix + ".")]
    if prov:
        cand = [r for r in cand if r[0].startswith(prov + ".")]
    words: dict[str, list[str]] = {}
    for t in toks:
        hit = [r for r in cand if " " + t in r[1]]
        alts = [t]
        if not hit and len(t) >= 4:
            alts = _fix(t, d)
            if alts:
                hit = [r for r in cand if any(" " + a + " " in r[1] for a in alts)]
                best = max(alts, key=lambda a: sum(1 for r in hit if " " + a + " " in r[1]))
                matched.append({"t": t, "w": best})
        cand = hit
        words[t] = alts
        if not cand:
            break
    # facet (sebelum filter kab): provinsi, atau kab/kota bila provinsi sudah dipilih
    lvl = "kab" if prov else "prov"
    fc: dict[str, int] = {}
    for r in cand:
        k = r[0][:5] if prov else r[0][:2]
        fc[k] = fc.get(k, 0) + 1
    facets = sorted(({"kode": k, "nama": short_kab(d["names"].get(k, k)), "n": n} for k, n in fc.items()),
                    key=lambda x: -x["n"])
    if kab:
        cand = [r for r in cand if r[0].startswith(kab + ".")]
    phrase = " " + " ".join(toks) + " " if len(toks) > 1 else ""

    def score(r):
        s = 0.0
        dn = " " + r[2] + " "
        for t in toks:
            ws = words.get(t, [t])
            if any(r[2] == w for w in ws):
                s += 100                                   # nama desa persis
            elif any(dn.startswith(" " + w) for w in ws):
                s += 40                                    # awal nama desa
            elif any(" " + w in dn for w in ws):
                s += 20                                    # bagian nama desa
        if phrase and phrase in r[1]:
            s += 120                                       # frasa utuh, mis. "kota bandung"
        s += min(40, boost.get(r[0][:8], 0) * 8) + min(20, boost.get(r[0][:5], 0) * 2)
        return -s, r[0]

    cand = sorted(cand, key=score)
    items = []
    for r in cand[:max(1, min(limit, 100))]:
        it = kec_info(r[0]) if is_kec else info(r[0])
        it["kab"] = short_kab(it["kab"])
        it["used"] = bool(boost.get(r[0][:8]))
        if is_kec:
            it["desa"] = ""
        items.append(it)
    return {"total": len(cand), "items": items, "facets": facets, "facet_level": lvl, "matched": matched}


def suggest(desa: str, under: str = "", extra: str = "", limit: int = 6) -> list[dict]:
    """Saran desa resmi untuk isian manual: di dalam kecamatan `under` diurutkan
    menurut kemiripan nama; tanpa `under` dicari global (desa + kata tambahan)."""
    d = _load()
    target = _norm(desa)
    if under:
        pool = [r for r in d["desa"] if r[0].startswith(under.rstrip(".") + ".")]
    else:
        pool = [r for r in d["desa"]]
        for t in [t for t in _norm(f"{desa} {extra}").split() if t not in _STOP][:4]:
            hit = [r for r in pool if " " + t in r[1]]
            if hit:
                pool = hit
        if len(pool) > 3000:
            return []
    scored = sorted(pool, key=lambda r: -difflib.SequenceMatcher(None, target, r[2]).ratio())[:limit]
    out = []
    for r in scored:
        it = info(r[0])
        it["kab"] = short_kab(it["kab"])
        it["score"] = round(difflib.SequenceMatcher(None, target, r[2]).ratio(), 2)
        out.append(it)
    return out


# ---------- pencocokan untuk Import Locations ----------
def _kab_norm(s: str) -> tuple[str, bool]:
    """('kabupaten x' | 'kota x' | 'x', ada_prefiks)."""
    n = _norm(s)
    for a, b in (("kabupaten ", "kabupaten "), ("kab ", "kabupaten "), ("kotamadya ", "kota "), ("kota ", "kota ")):
        if n.startswith(a):
            return b + n[len(a):], True
    return n, False


def _codes(level: int) -> list[tuple[str, str]]:
    d = _load()
    if "lv" not in d:
        d["lv"] = {lv: [(k, _norm(v)) for k, v in d["names"].items() if k.count(".") == lv - 1] for lv in (1, 2, 3, 4)}
    return d["lv"][level]


def match(desa: str, kec: str = "", kab: str = "", prov: str = "", kode: str = "") -> dict:
    """Cocokkan isian wilayah (mis. dari Excel) ke data resmi.
    status: ok (1 desa resmi) · desa_manual (kecamatan resmi, desa tak ada) · ambiguous (pilih dari cands)
    · notfound · empty. Nama tertulis = isian apa adanya (kosong -> nama resmi)."""
    raw = {"desa": (desa or "").strip(), "kec": (kec or "").strip(), "kab": (kab or "").strip(), "prov": (prov or "").strip()}
    kode = (kode or "").strip()
    if not any(raw.values()) and not kode:
        return {"status": "empty"}

    def written(off: dict, mode: str, k: str) -> dict:
        return {"mode": mode, "kode": k, **{f: raw[f] or off.get(f, "") for f in ("desa", "kec", "kab", "prov")}}

    if kode:
        i = info(kode)
        if i:
            i["kab"] = short_kab(i["kab"])
            return {"status": "ok", "wil": written(i, "official", i["kode"])}
    # provinsi
    provs = None
    if raw["prov"]:
        n = _norm(raw["prov"])
        provs = {k for k, v in _codes(1) if v == n or n in v} | ({_ALIAS[n]} if n in _ALIAS else set())
    # kab/kota
    kabs = None
    if raw["kab"]:
        n, pref = _kab_norm(raw["kab"])
        kabs = {k for k, v in _codes(2) if (v == n if pref else v in ("kabupaten " + n, "kota " + n))
                and (provs is None or k[:2] in provs)}
    # kecamatan
    kecs = None
    if raw["kec"]:
        n = _norm(raw["kec"])
        kecs = {k for k, v in _codes(3) if v == n and (kabs is None or k[:5] in kabs)
                and (provs is None or k[:2] in provs)}
    if not raw["desa"]:
        return {"status": "notfound", "msg": "Desa/Kelurahan is empty"}
    n = _norm(raw["desa"])
    hits = [k for k, v in _codes(4) if v == n and (kecs is None or k[:8] in kecs)
            and (kabs is None or k[:5] in kabs) and (provs is None or k[:2] in provs)]

    def cand(ks):
        out = []
        for k in ks[:6]:
            i = info(k)
            i["kab"] = short_kab(i["kab"])
            out.append(i)
        return out
    if len(hits) == 1:
        i = cand(hits)[0]
        return {"status": "ok", "wil": written(i, "official", i["kode"])}
    if len(hits) > 1:
        return {"status": "ambiguous", "cands": cand(hits), "msg": f"{len(hits)} desa named like this — pick one"}
    if kecs and len(kecs) == 1:
        kc = next(iter(kecs))
        sg = [x for x in suggest(raw["desa"], kc) if x["score"] >= 0.85]
        if sg:
            return {"status": "ambiguous", "cands": sg[:4], "kec": kc, "msg": "Close spelling found — pick one or keep as written"}
        k = kec_info(kc)
        k["kab"] = short_kab(k["kab"])
        k["desa"] = ""
        return {"status": "desa_manual", "wil": written(k, "desa_manual", kc), "msg": "Desa not in Kemendagri list — kept as written"}
    if kecs and len(kecs) > 1:
        return {"status": "notfound", "msg": "Kecamatan name exists in several kab/kota — fill Kab/Kota", "cands": []}
    sg = suggest(raw["desa"], "", f"{raw['kec']} {raw['kab']}", 4)
    return {"status": "notfound", "cands": [x for x in sg if x["score"] >= 0.7],
            "msg": "Not found in Kemendagri data", "full": all(raw.values())}
