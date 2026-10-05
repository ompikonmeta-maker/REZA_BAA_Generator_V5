"""Bangun panduan BAA.flow (HTML + gambar) dari screenshot + meta penanda + content.py.

python3 build_guide.py <folder_shots> <meta.json> <out_dir>
Hasil: <out_dir>/index.html, <out_dir>/img/*.jpg  (PDF dibuat terpisah oleh make_pdf.cjs)
"""
import html, json, os, re, sys
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from content import ADMIN, OPERATOR, STATUS  # noqa: E402

SHOTS, META, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
meta = json.load(open(META))
os.makedirs(os.path.join(OUT, 'img'), exist_ok=True)


def md(t):
    t = html.escape(t)
    t = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', t)
    return re.sub(r'\*(.+?)\*', r'<i>\1</i>', t)


def img(name):
    src = os.path.join(SHOTS, name + '.jpg')
    im = Image.open(src).convert('RGB')
    if im.width > 1600:
        im = im.resize((1600, round(im.height * 1600 / im.width)), Image.LANCZOS)
    im.save(os.path.join(OUT, 'img', name + '.jpg'), 'JPEG', quality=80, optimize=True, progressive=True)
    return f'img/{name}.jpg'


def flow(steps, cls=''):
    out = []
    for i, (ic, label) in enumerate(steps):
        if i:
            out.append('<span class="fl-ar" aria-hidden="true"><span class="mi">arrow_forward</span></span>')
        out.append(f'<span class="fl-st"><span class="fl-n">{i + 1}</span><span class="mi">{ic}</span><span class="fl-t">{md(label)}</span></span>')
    return f'<div class="flow {cls}">{"".join(out)}</div>'


def figure(t):
    m = meta[t['shot']]
    W, H = m['w'], m['h']
    pairs = [(mk, nt) for mk, nt in zip(m['marks'], t['notes']) if mk and nt]
    marks, legend = [], []
    for i, (r, note) in enumerate(pairs, 1):
        x, y, w, h = (max(0, r['x'] - 4), max(0, r['y'] - 4), r['w'] + 8, r['h'] + 8)
        w, h = min(w, W - x), min(h, H - y)
        st = f'left:{x / W * 100:.3f}%;top:{y / H * 100:.3f}%;width:{w / W * 100:.3f}%;height:{h / H * 100:.3f}%'
        marks.append(f'<span class="mk" style="{st}"><b>{i}</b></span>')
        legend.append(f'<li><b class="ln">{i}</b><span>{md(note)}</span></li>')
    return (f'<figure class="shot"><div class="frame"><img src="{img(t["shot"])}" width="{W}" height="{H}" alt="{html.escape(t["title"])}" loading="lazy">{"".join(marks)}</div></figure>'
            f'<ol class="legend">{"".join(legend)}</ol>')


def callouts(t):
    out = ''
    for tip in t.get('tips', []):
        out += f'<div class="note tip"><span class="mi">lightbulb</span><p>{md(tip)}</p></div>'
    for w in t.get('warn', []):
        out += f'<div class="note warn"><span class="mi">warning</span><p>{md(w)}</p></div>'
    return out


def section(R, idx):
    topics = ''.join(
        f'''<article class="topic" id="{t['id']}"><header><span class="tn">{idx}.{n}</span><h3>{md(t['title'])}</h3></header>
        <p class="lead">{md(t['lead'])}</p>{flow(t['flow'], 'sm') if t.get('flow') else ''}{figure(t)}{callouts(t)}</article>'''
        for n, t in enumerate(R['topics'], 1))
    toc = ''.join(f'<a href="#{t["id"]}"><span>{idx}.{n}</span>{md(t["title"])}</a>' for n, t in enumerate(R['topics'], 1))
    cheat = ''.join(f'<div class="cs-row"><span class="cs-q">{md(q)}</span><span class="cs-a">{md(a)}</span></div>' for q, a in R['cheat'])
    return f'''<section class="role {R['id']}" id="{R['id']}">
      <div class="role-head"><span class="role-ic"><span class="mi">{R['icon']}</span></span><div><div class="eyebrow">Panduan {idx}</div><h2>{R['role']}</h2><p>{md(R['lead'])}</p></div></div>
      <div class="big-flow"><div class="bf-lab">Alur kerja {R['role'].lower()}</div>{flow(R['flow'])}</div>
      <nav class="toc">{toc}</nav>
      {topics}
      <div class="cheat" id="{R['id']}-ringkas"><div class="cs-head"><span class="mi">bolt</span><div><h3>Ringkasan {R['role']} — 1 halaman</h3><p>Saya ingin… → caranya</p></div></div>{cheat}</div>
    </section>'''


status = ''.join(f'<div class="st"><span class="chip {c}">{n}</span><span>{md(d)}</span></div>' for n, d, c in STATUS)
page = f'''<!doctype html><html lang="id"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Panduan BAA.flow</title><link rel="stylesheet" href="../assets/fonts.css"><link rel="icon" href="../assets/favicon.png">
<style>{open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'guide.css')).read()}</style></head><body>
<header class="top"><div class="wrap"><span class="brand"><b>BAA</b><i>.</i><em>flow</em> <span>Panduan</span></span>
<nav><a href="#admin">Admin</a><a href="#operator">Operator</a><a class="pdf" href="panduan.pdf" download><span class="mi">picture_as_pdf</span>PDF</a></nav></div></header>
<main class="wrap">
<section class="hero"><div class="eyebrow">Panduan penggunaan</div><h1>BAA.flow — cara pakai untuk Admin & Operator</h1>
<p>BAA.flow membantu tim lapangan mengisi Berita Acara (BAA) per lokasi — data, wilayah, inventory, foto, dan scan PDF — lalu mengekspornya ke template Excel/PDF resmi. Pilih panduan sesuai peran Anda.</p>
<div class="roles"><a class="rc admin" href="#admin"><span class="mi">shield_person</span><b>Admin</b><span>Menyiapkan project, tim, template, memantau progres.</span><span class="go">Buka panduan →</span></a>
<a class="rc operator" href="#operator"><span class="mi">engineering</span><b>Operator</b><span>Mengisi BAA per lokasi sampai lengkap.</span><span class="go">Buka panduan →</span></a></div>
<div class="legend-st"><div class="ls-h">Arti status</div>{status}</div>
<div class="note tip"><span class="mi">lightbulb</span><p>Kotak bernomor <b class="ln">1</b> pada gambar menunjuk tombol atau bagian yang dijelaskan di bawah gambar.</p></div>
</section>
{section(ADMIN, 1)}
{section(OPERATOR, 2)}
<footer>BAA.flow · panduan dibuat dari tampilan aplikasi asli (data contoh).</footer>
</main>
<script>/* buka langsung bagian sesuai peran (#admin / #operator), tetap tepat walau gambar dimuat belakangan */
try{{const go=()=>{{const e=location.hash&&document.getElementById(location.hash.slice(1));if(e)e.scrollIntoView({{behavior:'instant'}});}};
addEventListener('load',go);setTimeout(go,60);}}catch(e){{}}</script>
</body></html>'''
open(os.path.join(OUT, 'index.html'), 'w').write(page)
print('ok', os.path.join(OUT, 'index.html'))
