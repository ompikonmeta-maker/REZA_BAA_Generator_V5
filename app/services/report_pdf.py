"""PDF laporan progres (reportlab, offline). Data dari routers.reports.build()."""
from __future__ import annotations

import io
from datetime import date, datetime

# Warna seri (lolos cek buta warna terhadap latar putih): NIS baru / dokumen selesai
C_NIS, C_DONE = "#008f87", "#d0621b"
INK, MUT, LINE, HEAD = "#1d2524", "#5b6664", "#dde3e2", "#0b5f5b"
MAX_ROWS = 60          # daftar panjang dipotong di PDF; isi lengkap ada di Excel

MON = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]


def _fd(s: str) -> str:
    d = date.fromisoformat(s[:10])
    return f"{d.day} {MON[d.month - 1]} {d.year}"


def _n(v, suf=""):
    return "—" if v is None else (f"{v:g}{suf}" if isinstance(v, float) else f"{v}{suf}")


def build(r: dict, secs: set[str], title: str, filt: str, by: str, app: str) -> io.BytesIO:
    from reportlab.graphics.shapes import Drawing, Line, Rect, String
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle)

    C = colors.HexColor
    base = ParagraphStyle("b", fontName="Helvetica", fontSize=8.5, leading=11, textColor=C(INK))
    small = ParagraphStyle("s", parent=base, fontSize=7.5, leading=9.5, textColor=C(MUT))
    h1 = ParagraphStyle("h1", parent=base, fontName="Helvetica-Bold", fontSize=15, leading=19)
    h2 = ParagraphStyle("h2", parent=base, fontName="Helvetica-Bold", fontSize=9.5, leading=12, textColor=C(HEAD),
                        spaceBefore=10, spaceAfter=5)
    W = A4[0] - 30 * mm
    k = r["kpi"]
    story = []
    story.append(Paragraph(title, h1))
    story.append(Paragraph(f"Periode {_fd(r['from'])} – {_fd(r['to'])} · {filt} · dibuat "
                           f"{datetime.now().strftime('%d-%m-%Y %H:%M')} oleh {by}", small))
    story.append(Spacer(1, 4))
    line = Table([[""]], colWidths=[W], rowHeights=[2])
    line.setStyle(TableStyle([("LINEABOVE", (0, 0), (-1, 0), 1.6, C(C_NIS))]))
    story.append(line)

    def tbl(head, rows, widths, num=(), zebra=True):
        data = [[Paragraph(f"<b>{h}</b>", small) for h in head]] + \
               [[Paragraph(str(c) if c not in (None, "") else "—", base) for c in row] for row in rows]
        t = Table(data, colWidths=widths, repeatRows=1)
        st = [("LINEBELOW", (0, 0), (-1, 0), 0.8, C("#9aa5a3")), ("LINEBELOW", (0, 1), (-1, -1), 0.3, C(LINE)),
              ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5)]
        for i in num:
            st.append(("ALIGN", (i, 0), (i, -1), "RIGHT"))
        t.setStyle(TableStyle(st))
        for i in num:                 # Paragraph tidak ikut ALIGN -> ganti gaya per sel angka
            for row in data:
                row[i].style = ParagraphStyle("r", parent=row[i].style, alignment=2)
        return t

    if "kpi" in secs:
        tiles = [("Target", _n(k["target"]), "lokasi" if k["target"] is not None else "tidak dipakai saat difilter"),
                 ("NIS (node in service)", _n(k["nis"]), f"{k['done_nis']} dokumen selesai · {k['backlog']} backlog"),
                 ("Dokumen BAA selesai", _n(k["done"]), f"{k['done_nis']} dari NIS" + (f" · {k['done'] - k['done_nis']} tanpa tgl aktivasi" if k['done'] - k['done_nis'] else "")),
                 ("Backlog", _n(k["backlog"]), "NIS, dokumen belum selesai"),
                 ("Rata-rata penyelesaian", _n(k["avg"], " hari"), f"median {_n(k['med'], ' hari')} · {k['docs']} dokumen"),
                 ("Data perlu dicek", _n(k["err_before"] + k["err_noact"]), "tidak ikut rata-rata")]
        big = ParagraphStyle("kb", parent=base, fontName="Helvetica-Bold", fontSize=17, leading=21)
        cells = [[[Paragraph(a, small), Paragraph(b, big), Paragraph(c, small)] for a, b, c in tiles[i:i + 3]] for i in (0, 3)]
        t = Table(cells, colWidths=[W / 3] * 3)
        t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, C(LINE)), ("INNERGRID", (0, 0), (-1, -1), 0.5, C(LINE)),
                               ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                               ("LEFTPADDING", (0, 0), (-1, -1), 8)]))
        story += [Spacer(1, 8), t,
                  Paragraph(f"NIS {_pct(k['nis'], k['target'] or k['locations'])} dan dokumen selesai {_pct(k['done'], k['target'] or k['locations'])} "
                            f"dari {'target' if k['target'] else 'lokasi'} · {k['not_active']} lokasi belum aktif (tanggal aktivasi belum diisi). "
                            f"Dalam periode: {k['nis_new']} NIS baru · {k['done_new']} dokumen selesai."
                            + (f" {k['done_incomplete']} lokasi berstatus Done tetapi belum lengkap 100% (belum dihitung selesai)."
                               if k.get("done_incomplete") else ""), small)]

    if "weekly" in secs and r["weekly"]:
        wk = r["weekly"]
        dw, dh, pl, pb = W, 54 * mm, 22, 16
        d = Drawing(dw, dh)
        mx = max([1] + [max(w["nis"], w["done"]) for w in wk])
        step = max(1, -(-mx // 4))
        ymax = step * 4
        y = lambda v: pb + v / ymax * (dh - pb - 12)  # noqa: E731
        for t_ in range(0, ymax + 1, step):
            d.add(Line(pl, y(t_), dw - 4, y(t_), strokeColor=C("#e6eaea"), strokeWidth=0.5))
            d.add(String(pl - 4, y(t_) - 2.5, str(t_), fontName="Helvetica", fontSize=6.5, fillColor=C(MUT), textAnchor="end"))
        gw = (dw - pl - 6) / len(wk)
        bw = min(10, gw / 2 - 2)
        every = max(1, len(wk) // 12)
        for i, w in enumerate(wk):
            cx = pl + gw * i + gw / 2
            for j, (v, col) in enumerate(((w["nis"], C_NIS), (w["done"], C_DONE))):
                if v:
                    x0 = cx - bw - 0.5 + j * (bw + 1)
                    d.add(Rect(x0, pb, bw, y(v) - pb, fillColor=C(col), strokeColor=None))
                    if len(wk) <= 16:
                        d.add(String(x0 + bw / 2, y(v) + 2, str(v), fontName="Helvetica", fontSize=6, fillColor=C(INK), textAnchor="middle"))
            if i % every == 0:
                dd = date.fromisoformat(w["week"])
                d.add(String(cx, pb - 9, f"{dd.day} {MON[dd.month - 1]}", fontName="Helvetica", fontSize=6.5, fillColor=C(MUT), textAnchor="middle"))
        d.add(Line(pl, pb, dw - 4, pb, strokeColor=C("#9aa5a3"), strokeWidth=0.6))
        leg = Paragraph(f"<font color='{C_NIS}'>■</font> NIS baru (tanggal aktivasi) &nbsp;&nbsp; "
                        f"<font color='{C_DONE}'>■</font> Dokumen BAA selesai", small)
        story.append(KeepTogether([Paragraph("Tren mingguan — NIS baru vs dokumen selesai", h2), leg, d]))

    if "completion" in secs:
        hs = r["hist"]
        dw, dh, pb = W * 0.42, 44 * mm, 14
        d = Drawing(dw, dh)
        mx = max([1] + [h["n"] for h in hs])
        gw = dw / len(hs)
        bw = gw * 0.62
        for i, h in enumerate(hs):
            x0 = gw * i + (gw - bw) / 2
            hh = h["n"] / mx * (dh - pb - 12)
            if h["n"]:
                d.add(Rect(x0, pb, bw, hh, fillColor=C(C_NIS), strokeColor=None))
            d.add(String(x0 + bw / 2, pb + hh + 2, str(h["n"]), fontName="Helvetica", fontSize=6.5, fillColor=C(INK), textAnchor="middle"))
            d.add(String(x0 + bw / 2, pb - 9, f"{h['label']} hari", fontName="Helvetica", fontSize=6.5, fillColor=C(MUT), textAnchor="middle"))
        d.add(Line(0, pb, dw, pb, strokeColor=C("#9aa5a3"), strokeWidth=0.6))
        left = [Paragraph("Lama penyelesaian dokumen", h2), d,
                Paragraph("Dari tanggal aktivasi sampai dokumen BAA lengkap 100% (scan bertanda tangan + BAA hasil generate). "
                          "Hari kalender; selesai di hari yang sama = 0 hari.", small)]
        if "operator" in secs:
            ops = r["operators"]
            right = [Paragraph("Per operator", h2),
                     tbl(["Operator", "Lokasi", "NIS", "Selesai", "Backlog", "Rata² hari"],
                         [(o["key"], o["n"], o["nis"], o["done"], o["backlog"], _n(o["avg"])) for o in ops],
                         [W * 0.56 * f for f in (.27, .13, .1, .15, .16, .19)], num=(1, 2, 3, 4, 5))]
            t = Table([[left, right]], colWidths=[W * 0.43, W * 0.57])
            t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
            story.append(t)
        else:
            story += left
    elif "operator" in secs:
        story += [Paragraph("Per operator", h2),
                  tbl(["Operator", "Lokasi", "NIS", "Selesai", "Backlog", "Rata² hari"],
                      [(o["key"], o["n"], o["nis"], o["done"], o["backlog"], _n(o["avg"])) for o in r["operators"]],
                      [W * f for f in (.4, .12, .12, .12, .12, .12)], num=(1, 2, 3, 4, 5))]

    if "wilayah" in secs:
        ws = r["wilayah"]
        story += [Paragraph(f"Per wilayah (kab/kota{', 15 dengan NIS terbanyak' if len(ws) > 15 else ''})", h2),
                  tbl(["Provinsi", "Kab/Kota", "Lokasi", "NIS", "Dokumen selesai", "% selesai dari NIS", "Rata² hari"],
                      [(w["prov"], w["kab"], w["n"], w["nis"], w["done"], _n(w["pct_nis"], "%"), _n(w["avg"])) for w in ws[:15]],
                      [W * f for f in (.2, .24, .1, .09, .13, .13, .11)], num=(2, 3, 4, 5, 6))]
    story.append(Spacer(1, 8))
    story.append(Paragraph("<b>Definisi.</b> NIS = lokasi yang tanggal aktivasinya sudah diisi. Dokumen selesai = scan BAA "
                           "bertanda tangan + BAA hasil generate lengkap (100%). Backlog = NIS yang dokumennya belum selesai. "
                           "Selesai sebelum tanggal aktivasi atau tanpa tanggal aktivasi = data perlu dicek, tidak ikut rata-rata.", small))

    def more(n):
        return [Paragraph(f"… {n - MAX_ROWS} baris lagi — lihat file Excel.", small)] if n > MAX_ROWS else []
    if "backlog" in secs:
        b = r["backlog"]
        story += [Paragraph(f"Backlog — NIS yang dokumennya belum selesai ({len(b)})", h2),
                  tbl(["Kode", "Lokasi", "Kab/Kota", "Owner", "Aktivasi", "Hari", "Kurang"],
                      [(x["code"], x["name"], x["kab"], x["owner"], x["act"], x["age"], ", ".join(x["miss"])) for x in b[:MAX_ROWS]],
                      [W * f for f in (.125, .235, .14, .11, .11, .06, .22)], num=(5,))] + more(len(b))
    if "missing" in secs:
        m = r["missing"]
        story += [Paragraph(f"Kekurangan per lokasi ({len(m)} belum 100%)", h2),
                  tbl(["Kode", "Lokasi", "Owner", "%", "Kurang"],
                      [(x["code"], x["name"], x["owner"], x["pct"], ", ".join(x["miss"])) for x in m[:MAX_ROWS]],
                      [W * f for f in (.125, .315, .14, .07, .35)], num=(3,))] + more(len(m))
    if "errors" in secs:
        e = r["errors"]
        story += [Paragraph(f"Data perlu dicek ({len(e)}) — tidak ikut rata-rata", h2)]
        story += ([tbl(["Kode", "Lokasi", "Owner", "Aktivasi", "Dokumen selesai", "Masalah"],
                       [(x["code"], x["name"], x["owner"], x["act"], x["comp"],
                         f"<font color='#a3312a'>Selesai {-x['days']} hari sebelum aktivasi</font>" if x["err"] == "before"
                         else "<font color='#a3312a'>Tanggal aktivasi kosong</font>") for x in e[:MAX_ROWS]],
                       [W * f for f in (.125, .285, .13, .12, .13, .21)])] + more(len(e))
                  if e else [Paragraph("Tidak ada.", small)])
        if e:
            story.append(Paragraph("Perbaiki tanggal aktivasi di BAA Entry; angka laporan ikut terkoreksi saat diunduh ulang.", small))

    def foot(cv, doc):
        cv.saveState()
        cv.setFont("Helvetica", 7)
        cv.setFillColor(C("#8a9492"))
        cv.drawString(15 * mm, 9 * mm, f"{app} · Laporan Progres · {_fd(r['from'])} – {_fd(r['to'])}")
        cv.drawRightString(A4[0] - 15 * mm, 9 * mm, f"Halaman {doc.page}")
        cv.restoreState()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=13 * mm, bottomMargin=15 * mm, leftMargin=15 * mm,
                            rightMargin=15 * mm, title=title, author=by)
    doc.build(story, onFirstPage=foot, onLaterPages=foot)
    buf.seek(0)
    return buf


def _pct(a, b):
    return f"{round(a / b * 100)}%" if b else "—"
