/* =====================================================================
   BAA.flow — Intro animasi (logo 3D + bola merah + spotlight di UI asli)
   Alur: logo sidebar terangkat jadi logo 3D -> titik merah lepas jadi bola
   (pantulan kartun + riak) -> mengitari logo -> morph pin/kamera/segel ->
   logo kembali ke sidebar -> tur spotlight pada elemen hidup -> bola pulang
   jadi titik logo -> pendaran merah melingkar membuka layar -> sapaan.
   API:
     BFIntro.veil()            gelapkan layar lebih dulu (dipanggil saat login)
     BFIntro.unveil()          batalkan veil tanpa menjalankan intro
     BFIntro.run(opts)         -> Promise<'done'|'skip'>
       opts.logo()             elemen logo sidebar (svg 44x44, titik di 33,12.5 r3)
       opts.chapters[]         {label,title,text,go?:async fn,target:fn->Element|Element[]|null,pad?}
       opts.name               nama untuk sapaan akhir
       opts.restore()          async: kembalikan tampilan semula (di bawah overlay)
       opts.onEnd(kind)        dipanggil sekali saat selesai / dilewati
     BFIntro.active            true selama intro berjalan
   ===================================================================== */
(function () {
  'use strict';
  const NS = 'http://www.w3.org/2000/svg';
  const RM = () => matchMedia('(prefers-reduced-motion: reduce)').matches;
  class Cancel extends Error {}
  let RUN = 0, root = null, ui = {}, O = { x: 0, y: 0, s: 0, lift: 0 }, H = { x: 0, y: 0, w: 0, h: 0, r: 0 };
  let reduce = false, nextFn = null, skipFn = null, active = false;

  /* ---------- waktu & easing ---------- */
  const E = {
    io: t => t < .5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2, out: t => 1 - Math.pow(1 - t, 3), in: t => t * t * t,
    spring: t => 1 - Math.pow(1 - t, 2.6) * Math.cos(t * Math.PI * 1.15) * (1 - t * .2), lin: t => t
  };
  const L = (a, b, t) => a + (b - a) * t;
  function tween(ms, fn, ez, r, keep) {
    return new Promise((res, rej) => {
      if (r !== RUN) return rej(new Cancel());
      if (ms <= 0 || (reduce && !keep)) { fn(1); return res(); }
      const t0 = performance.now();
      const f = now => {
        if (r !== RUN) return rej(new Cancel());
        const k = Math.min(1, (now - t0) / ms); fn((ez || E.io)(k));
        if (k >= 1) res(); else requestAnimationFrame(f);
      };
      f(t0);
    });
  }
  const wait = (ms, r) => tween(ms, () => {}, E.lin, r, true);
  const frame = () => new Promise(r => requestAnimationFrame(() => r()));

  /* ---------- morph bentuk (sampel titik path, tanpa library) ---------- */
  const SHP = {
    tile: 'M72.4 24 L127.6 24 C154.3 24 176 45.7 176 72.4 L176 127.6 C176 154.3 154.3 176 127.6 176 L72.4 176 C45.7 176 24 154.3 24 127.6 L24 72.4 C24 45.7 45.7 24 72.4 24 Z',
    pin: 'M100 16 C142 16 168 46 168 84 C168 124 124 158 100 184 C76 158 32 124 32 84 C32 46 58 16 100 16 Z',
    camera: 'M72 50 L128 50 L138 68 L160 68 C170 68 176 74 176 84 L176 150 C176 160 170 166 160 166 L40 166 C30 166 24 160 24 150 L24 84 C24 74 30 68 40 68 L62 68 Z',
    seal: 'M100 16 L124 32 L152 32 L162 60 L182 84 L170 110 L174 140 L148 154 L132 178 L100 170 L68 178 L52 154 L26 140 L30 110 L18 84 L38 60 L48 32 L76 32 Z'
  };
  const GLY = {
    tile: '<text x="100" y="127.6" text-anchor="middle" font-family="system-ui,Segoe UI,Roboto,sans-serif" font-weight="800" font-size="65.6" letter-spacing="-3.45" fill="#fff">bf</text>',
    pin: '<circle cx="100" cy="84" r="24" fill="#fff"/>',
    camera: '<circle cx="100" cy="116" r="30" fill="none" stroke="#fff" stroke-width="13"/>',
    seal: '<path d="M64 98 L90 124 L138 74" fill="none" stroke="#fff" stroke-width="17" stroke-linecap="round" stroke-linejoin="round"/>'
  };
  /* warna merek (sama dengan logo sidebar), bukan warna tema */
  const COL = { tile: ['#0aa39d', '#04726f'], pin: ['#2cc4a2', '#0a6a55'], camera: ['#8c7bf2', '#4532b0'], seal: ['#3fcf8e', '#0d7446'] };
  const DOT = { cx: 138, cy: 67.2, r: 10.4 };     // titik merah = (33,12.5,r3) pada logo 44x44
  const TILE = 152 / 200;                          // ubin logo mengisi 152 dari 200 unit viewBox
  const WORDS = [['pin', 'Isi data.', 'Lokasi, wilayah, inventory'], ['camera', 'Foto.', 'Upload sekaligus, scan PDF'], ['seal', 'Selesai.', 'Finish di 100%, export 1 klik']];
  const PTS = {}, NP = 150; let tmp = null;
  function pts(n) {
    if (PTS[n]) return PTS[n];
    if (!tmp) { tmp = document.createElementNS(NS, 'svg'); tmp.style.cssText = 'position:absolute;width:0;height:0'; document.body.appendChild(tmp); }
    const p = document.createElementNS(NS, 'path'); p.setAttribute('d', SHP[n]); tmp.appendChild(p);
    const len = p.getTotalLength(), a = [];
    for (let i = 0; i < NP; i++) { const q = p.getPointAtLength(len * i / NP); a.push([q.x, q.y]); }
    p.remove(); let s = 0;
    for (let i = 0; i < NP; i++) { const q = a[i], w = a[(i + 1) % NP]; s += q[0] * w[1] - w[0] * q[1]; }
    if (s < 0) a.reverse();
    let top = 0; a.forEach((q, i) => { if (q[1] < a[top][1] - .01 || (Math.abs(q[1] - a[top][1]) < .01 && q[0] < a[top][0])) top = i; });
    return PTS[n] = a.slice(top).concat(a.slice(0, top));
  }
  const toD = a => 'M' + a.map(p => p[0].toFixed(1) + ' ' + p[1].toFixed(1)).join('L') + 'Z';
  function setShape(a) { const d = toD(a); ['fc', 'hl', 'ex1', 'ex2', 'ex3'].forEach(i => ui[i].setAttribute('d', d)); ui.pts = a; }

  /* ---------- gaya ---------- */
  const CSS = `
#bfi{position:fixed;inset:0;z-index:10000;user-select:none;-webkit-user-select:none;font-family:inherit}
#bfi.bfi-pass{pointer-events:none}
#bfi .bfi-dk{position:absolute;inset:0;background:radial-gradient(70% 80% at 50% 45%,#0b3a39 0%,#061314 60%,#030909 100%);opacity:0}
#bfi .bfi-gl{position:absolute;pointer-events:none;left:50%;top:40%;width:min(46vw,80vh);aspect-ratio:1;border-radius:50%;filter:blur(60px);opacity:0;transform:translate(-50%,-50%)}
#bfi svg.bfi-ov{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}
#bfi .bfi-ring{position:absolute;border:2px solid rgba(255,120,145,.95);box-shadow:0 0 0 5px rgba(255,93,126,.16),0 0 34px rgba(255,93,126,.35);pointer-events:none;opacity:0}
#bfi .bfi-tip{position:absolute;width:min(340px,calc(100vw - 32px));background:var(--md-sys-color-surface-container-high,#fff);color:var(--md-sys-color-on-surface,#102526);
  border-radius:var(--md-sys-shape-corner-large,16px);padding:16px 18px 12px;box-shadow:var(--md-sys-elevation-level3,0 18px 44px rgba(0,0,0,.38));opacity:0;pointer-events:none}
#bfi .bfi-tip.bfi-on{pointer-events:auto}
#bfi .bfi-tip .bfi-n{display:block;font:600 11px/1.2 var(--md-sys-typescale-label-small-font,inherit);letter-spacing:.08em;text-transform:uppercase;color:var(--brand-accent,#ec5a73);margin-bottom:6px}
#bfi .bfi-tip h3{margin:0 0 4px;font:var(--md-sys-typescale-title-medium,600 16px/1.3 inherit);font-weight:700}
#bfi .bfi-tip p{margin:0;font:var(--md-sys-typescale-body-medium,14px/1.45 inherit);color:var(--md-sys-color-on-surface-variant,#3b5558)}
#bfi .bfi-tip .bfi-act{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-top:12px}
#bfi .bfi-tip .bfi-dots{display:flex;gap:4px;flex-wrap:wrap}
#bfi .bfi-tip .bfi-dots i{width:6px;height:6px;border-radius:50%;background:var(--md-sys-color-outline-variant,#c4d0cf)}
#bfi .bfi-tip .bfi-dots i.bfi-on{background:var(--brand-accent,#ec5a73)}
#bfi .bfi-skip{position:absolute;top:16px;right:20px;z-index:40;border:0;border-radius:99px;padding:8px 16px;font:600 13px/1 inherit;cursor:pointer;
  background:rgba(10,30,32,.6);color:#fff;backdrop-filter:blur(8px)}
#bfi .bfi-skip:hover{background:rgba(10,30,32,.8)}
#bfi .bfi-skip:focus-visible{outline:2px solid #7ff0e9;outline-offset:2px}
#bfi .bfi-lg3{position:absolute;pointer-events:none;transform-style:preserve-3d;will-change:transform;z-index:10;opacity:0}
#bfi .bfi-lg3 svg{width:100%;height:100%;overflow:visible}
#bfi .bfi-word{position:absolute;pointer-events:none;left:0;right:0;text-align:center;color:#fff;font-weight:700;font-size:clamp(22px,3.2vw,42px);line-height:1.1;letter-spacing:-.02em;opacity:0}
#bfi .bfi-word small{display:block;margin-top:.45em;font-weight:500;font-size:clamp(12px,1.3vw,16px);letter-spacing:0;color:rgba(255,255,255,.72)}
#bfi .bfi-orb{position:absolute;border-radius:50%;opacity:0;pointer-events:none;z-index:20;
  background:radial-gradient(circle at 34% 30%,#fff 0 6%,#ffc2cf 10%,#ff6b8b 30%,#e3355c 55%,#a3123a 80%,#5e0820 100%);
  box-shadow:inset -.18em -.25em .5em rgba(60,0,15,.45),0 .1em .35em rgba(120,0,30,.35)}
#bfi .bfi-osh{position:absolute;border-radius:50%;background:radial-gradient(closest-side,rgba(0,0,0,.45),rgba(0,0,0,0));opacity:0;pointer-events:none;z-index:19}
#bfi .bfi-rip{position:absolute;border-radius:50%;pointer-events:none;z-index:18;opacity:0;border:6px solid #ff5a7e;box-shadow:0 0 10px rgba(255,70,115,.55),inset 0 0 8px rgba(255,70,115,.45)}
#bfi .bfi-zap{position:absolute;height:3px;border-radius:3px;background:#ffe0e7;box-shadow:0 0 6px rgba(255,90,125,.9);pointer-events:none;z-index:21;transform-origin:0 50%;opacity:0}
#bfi .bfi-sweep{position:absolute;border-radius:50%;pointer-events:none;opacity:0;z-index:15}
#bfi .bfi-bloom{position:absolute;border-radius:50%;pointer-events:none;opacity:0;z-index:16;
  background:radial-gradient(closest-side,rgba(255,120,150,.95),rgba(255,62,104,.6) 34%,rgba(255,45,92,.22) 66%,rgba(255,40,90,0))}
#bfi .bfi-done{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);z-index:30;pointer-events:none;background:rgba(14,52,52,.92);color:#fff;border-radius:18px;
  padding:.75em 1.4em;font-weight:700;font-size:clamp(18px,2.2vw,28px);letter-spacing:-.01em;box-shadow:0 20px 50px rgba(0,0,0,.35);opacity:0;white-space:nowrap;backdrop-filter:blur(8px)}
#bfi .bfi-done b{color:#7ff0e9}`;

  function ensureCss() {
    if (document.getElementById('bfiCss')) return;
    const s = document.createElement('style'); s.id = 'bfiCss'; s.textContent = CSS; document.head.appendChild(s);
  }
  function mount() {
    ensureCss();
    if (root) return root;
    root = document.createElement('div'); root.id = 'bfi'; root.setAttribute('role', 'dialog'); root.setAttribute('aria-label', 'Intro BAA.flow');
    root.innerHTML = `
  <div class="bfi-dk" id="bfiDk"></div><div class="bfi-gl" id="bfiGl"></div>
  <svg class="bfi-ov" id="bfiOv" style="opacity:0"><defs><mask id="bfiMk"><rect width="100%" height="100%" fill="#fff"/><rect id="bfiHole" fill="#000"/></mask></defs><rect width="100%" height="100%" fill="rgba(3,12,14,.66)" mask="url(#bfiMk)"/></svg>
  <div class="bfi-ring" id="bfiRing"></div>
  <div class="bfi-lg3" id="bfiLg"><svg viewBox="0 0 200 200"><defs><linearGradient id="bfiG" x1="0" y1="0" x2="1" y2="1"><stop offset="0" id="bfiC1" stop-color="#16b8b0"/><stop offset="1" id="bfiC2" stop-color="#036e6c"/></linearGradient>
    <linearGradient id="bfiS" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".42"/><stop offset=".55" stop-color="#fff" stop-opacity="0"/></linearGradient>
    <radialGradient id="bfiDtG" cx=".34" cy=".3" r=".75"><stop offset="0" stop-color="#ffd0da"/><stop offset=".35" stop-color="#ff6b8b"/><stop offset=".75" stop-color="#ec5a73"/><stop offset="1" stop-color="#a3123a"/></radialGradient></defs>
    <path id="bfiEx3" fill="#02403f" transform="translate(0 9)"/><path id="bfiEx2" fill="#03504e" transform="translate(0 6)"/><path id="bfiEx1" fill="#04605e" transform="translate(0 3)"/>
    <path id="bfiFc" fill="url(#bfiG)"/><path id="bfiHl" fill="url(#bfiS)"/><g id="bfiGy"></g><circle id="bfiDt" cx="${DOT.cx}" cy="${DOT.cy}" r="${DOT.r}" fill="url(#bfiDtG)"/></svg></div>
  <div class="bfi-word" id="bfiWd"></div>
  <div class="bfi-osh" id="bfiOsh"></div><div class="bfi-orb" id="bfiOrb"></div>
  <div class="bfi-sweep" id="bfiSw"></div><div class="bfi-bloom" id="bfiBl"></div>
  <div class="bfi-tip" id="bfiTip" aria-live="polite"><span class="bfi-n"></span><h3></h3><p></p><div class="bfi-act"><span class="bfi-dots"></span><md-button variant="filled" id="bfiNext">Lanjut</md-button></div></div>
  <div class="bfi-done" id="bfiDn"></div>
  <button type="button" class="bfi-skip" id="bfiSkip">Lewati intro</button>`;
    document.body.appendChild(root);
    const q = id => root.querySelector('#' + id);
    ui = {
      dk: q('bfiDk'), gl: q('bfiGl'), ov: q('bfiOv'), hole: q('bfiHole'), ring: q('bfiRing'), lg: q('bfiLg'), wd: q('bfiWd'), osh: q('bfiOsh'), orb: q('bfiOrb'),
      sw: q('bfiSw'), bl: q('bfiBl'), tip: q('bfiTip'), dn: q('bfiDn'), skip: q('bfiSkip'), next: q('bfiNext'),
      fc: q('bfiFc'), hl: q('bfiHl'), ex1: q('bfiEx1'), ex2: q('bfiEx2'), ex3: q('bfiEx3'), gy: q('bfiGy'), dt: q('bfiDt'), c1: q('bfiC1'), c2: q('bfiC2')
    };
    setShape(pts('tile')); ui.gy.innerHTML = GLY.tile;
    ui.skip.addEventListener('click', () => skipFn && skipFn());
    ui.next.addEventListener('click', () => nextFn && nextFn());
    return root;
  }
  function unmount() { if (root) root.remove(); root = null; ui = {}; O = { x: 0, y: 0, s: 0, lift: 0 }; }
  /* tombol: Enter / Spasi / panah kanan = lanjut, Esc = lewati; jangan bocor ke aplikasi */
  function onKey(e) {
    if (!active) return;
    if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); skipFn && skipFn(); return; }
    if ((e.key === 'Enter' || e.key === ' ' || e.key === 'ArrowRight') && nextFn) { e.preventDefault(); e.stopPropagation(); nextFn(); return; }
    e.stopPropagation();
    // fokus tertinggal di aplikasi (mis. input form): jangan sampai ketikan masuk ke data
    if (!root || !root.contains(e.target) || e.ctrlKey || e.metaKey) { e.preventDefault(); try { ui.next.focus({ preventScroll: true }); } catch (x) {} }
  }

  /* ---------- sorotan ---------- */
  function setHole(h, ring) {
    H = h; const o = ui.hole;
    o.setAttribute('x', h.x); o.setAttribute('y', h.y); o.setAttribute('width', Math.max(0, h.w)); o.setAttribute('height', Math.max(0, h.h)); o.setAttribute('rx', h.r);
    const g = ui.ring.style; g.left = h.x + 'px'; g.top = h.y + 'px'; g.width = Math.max(0, h.w) + 'px'; g.height = Math.max(0, h.h) + 'px'; g.borderRadius = h.r + 'px';
    g.opacity = ring !== false && h.w > 4 ? 1 : 0;
  }
  const closeTo = (hs, u) => ({ x: L(hs.x, O.x, u), y: L(hs.y, O.y, u), w: L(hs.w, 0, u), h: L(hs.h, 0, u), r: L(hs.r, 0, u) });

  /* ---------- bola merah: x,y = pusat; s = diameter; lift = tinggi di atas lantai ---------- */
  function setOrb(o) {
    O = { ...O, ...o }; const s = O.s, b = ui.orb.style;
    b.width = b.height = s + 'px'; b.left = (O.x - s / 2) + 'px'; b.top = (O.y - s / 2 - O.lift) + 'px'; b.fontSize = s + 'px'; b.opacity = s > 0 ? 1 : 0;
    const Hh = innerHeight, sh = ui.osh.style, sw = s * (1.25 - Math.min(.6, O.lift / (Hh * .4)));
    sh.width = sw + 'px'; sh.height = sw * .32 + 'px'; sh.left = (O.x - sw / 2) + 'px'; sh.top = (O.y + s * .42 - sw * .16) + 'px';
    sh.opacity = s > 0 ? Math.max(.15, .8 - O.lift / (Hh * .3)) : 0;
  }
  const ORB = () => Math.max(18, Math.min(28, innerWidth * .017));
  /* pantulan kartun: tinggi lompat (x ukuran bola), pantulan susulan [tinggi, durasi, kekuatan] */
  const BN = { pk: 2.3, fly: 640, p: 3, seq: [[.42, 400, .7], [.16, 250, .4], [.05, 150, .15]] };
  const arc = t => 1 - Math.pow(Math.abs(2 * t - 1), BN.p);   // melayang lebih lama di puncak
  function stretch(v) { if (reduce) return; const o = ui.orb.style; o.transformOrigin = '50% 50%'; o.transform = v > .01 ? `scale(${1 - .32 * .55 * v},${1 + .32 * v})` : ''; }
  async function fly(ms, f, h, r) {
    ui.orb.getAnimations().forEach(a => a.cancel());
    await tween(ms, t => { setOrb(f(t)); stretch(Math.pow(Math.abs(2 * t - 1), BN.p - 1) * Math.min(1, h * 2.2)); }, E.lin, r);
    ui.orb.style.transform = '';
  }
  async function land(e, n, r) { setOrb({ lift: 0 }); squash(e); ripples(O.x, O.y, e, n); await wait(reduce ? 0 : 50 + 70 * e, r); }
  async function crouch(r) {
    if (reduce) return; const o = ui.orb; o.getAnimations().forEach(a => a.cancel()); o.style.transformOrigin = '50% 100%';
    await tween(130, t => { o.style.transform = `scale(${1 + .26 * t},${1 - .26 * t})`; }, E.out, r);
  }
  async function bounceSeq(H0, r, rip) { for (const [h, d, e] of BN.seq) { await fly(d, t => ({ lift: h * H0 * arc(t) }), h, r); await land(e, rip ? Math.round(3 * e) : 0, r); } }
  async function hop(x, y, r) {
    const a = { ...O }, d = Math.hypot(x - a.x, y - a.y), peak = Math.min(innerHeight * .22, 40 + d * .32);
    await crouch(r);
    await fly(Math.min(900, 420 + d * .6), t => { const u = E.io(t); return { x: L(a.x, x, u), y: L(a.y, y, u), lift: Math.sin(Math.PI * t) * peak, s: L(a.s, ORB(), u) * (1 + Math.sin(Math.PI * t) * .38) }; }, 1, r);
    setOrb({ x, y, s: ORB() }); await land(1, 2, r);
  }
  function squash(e) {
    if (reduce) return; e = e == null ? 1 : Math.min(1, e);
    const o = ui.orb; o.getAnimations().forEach(a => a.cancel()); o.style.transform = ''; o.style.transformOrigin = '50% 100%';
    const q = .42 * e;   // gepeng besar lalu bergoyang seperti jeli
    o.animate([{ transform: 'none' }, { transform: `scale(${1 + q * 1.15},${1 - q})`, offset: .16 }, { transform: `scale(${1 - q * .5},${1 + q * .6})`, offset: .4 },
      { transform: `scale(${1 + q * .22},${1 - q * .22})`, offset: .62 }, { transform: `scale(${1 - q * .08},${1 + q * .08})`, offset: .82 }, { transform: 'none' }], { duration: 380 + 280 * e, easing: 'linear' });
  }
  async function bounceTo(x, y, r) {
    const a = { ...O }, H0 = ORB() * BN.pk, sm = t => t * t * (3 - 2 * t);
    await fly(BN.fly, t => ({ x: L(a.x, x, sm(t)), y: L(a.y, y, sm(t)), lift: H0 * arc(t), s: ORB() }), 1, r);
    await land(1, 3, r); await bounceSeq(H0, r, false);
  }
  /* riak di lantai (elips = lantai dilihat miring, sama seperti bayangan bola) */
  function ripples(x, y, e, n) {
    if (reduce || !n || !root) return; const s0 = O.s || ORB(), cy = y + s0 * .42;
    for (let i = 0; i < n; i++) {
      const el = document.createElement('div'); el.className = 'bfi-rip';
      const w = s0 * 3.3 * (.6 + .5 * e) * (1 + i * .5), h = w * .4;
      Object.assign(el.style, { width: w + 'px', height: h + 'px', left: (x - w / 2) + 'px', top: (cy - h / 2) + 'px' }); root.appendChild(el);
      el.animate([{ transform: 'scale(.1)', opacity: 1, borderWidth: '8px' }, { transform: 'scale(.78)', opacity: 1, borderWidth: '4.5px', offset: .55 }, { transform: 'scale(1.02)', opacity: 0, borderWidth: '2px' }],
        { duration: 520 + i * 70, delay: i * 100, easing: 'cubic-bezier(.12,.85,.3,1)', fill: 'backwards' }).onfinish = () => el.remove();
    }
    if (e > .55) zaps(x, cy, s0);
  }
  /* garis benturan ala kartun */
  function zaps(x, y, s0) {
    for (const a of [200, 232, 308, 340]) {
      const el = document.createElement('div'); el.className = 'bfi-zap';
      Object.assign(el.style, { left: x + 'px', top: (y - 1.5) + 'px', width: s0 * .5 + 'px' }); root.appendChild(el);
      el.animate([{ opacity: 1, transform: `rotate(${a}deg) translateX(${s0 * .55}px) scaleX(1)` }, { opacity: 0, transform: `rotate(${a}deg) translateX(${s0 * 1.35}px) scaleX(.15)` }],
        { duration: 340, easing: 'cubic-bezier(.2,.8,.3,1)' }).onfinish = () => el.remove();
    }
  }

  /* ---------- target hidup ---------- */
  const els = c => { let v = c.target && c.target(); if (!v) return []; if (!Array.isArray(v)) v = [v]; return v.filter(e => { if (!e) return false; const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; }); };
  function rectOf(list, pad) {
    const p = pad == null ? 8 : pad, rs = list.map(e => e.getBoundingClientRect());
    let x = Math.min(...rs.map(r => r.left)) - p, y = Math.min(...rs.map(r => r.top)) - p, R = Math.max(...rs.map(r => r.right)) + p, B = Math.max(...rs.map(r => r.bottom)) + p;
    x = Math.max(6, x); y = Math.max(6, y); R = Math.min(innerWidth - 6, R); B = Math.min(innerHeight - 6, B);
    const w = Math.max(0, R - x), h = Math.max(0, B - y); return { x, y, w, h, r: Math.min(16, h / 2) };
  }
  async function findTarget(c, r) {
    for (let t = 0; t < 2600; t += 100) { const l = els(c); if (l.length) return l; await wait(100, r); }
    return null;
  }
  const corner = h => { const m = ORB() * .6 + 4; return { x: Math.min(innerWidth - m, h.x + h.w), y: Math.max(m, h.y) }; };
  function placeTip(h) {
    const W = innerWidth, Hh = innerHeight, tip = ui.tip, tw = tip.offsetWidth, th = tip.offsetHeight, g = 18; let x, y;
    if (h.x + h.w + g + tw < W - 10) { x = h.x + h.w + g; y = h.y; }
    else if (h.x - g - tw > 10) { x = h.x - g - tw; y = h.y; }
    else { x = h.x + h.w / 2 - tw / 2; y = (h.y + h.h + g + th < Hh - 10) ? h.y + h.h + g : h.y - g - th; }
    x = Math.min(W - tw - 10, Math.max(10, x)); y = Math.min(Hh - th - 10, Math.max(10, y));
    tip.style.left = x + 'px'; tip.style.top = y + 'px';
  }
  function fillTip(c, i, n) {
    const t = ui.tip; t.querySelector('.bfi-n').textContent = `${String(i + 1).padStart(2, '0')} / ${n}${c.label ? ' · ' + c.label : ''}`;
    t.querySelector('h3').textContent = c.title; t.querySelector('p').textContent = c.text;
    t.querySelector('.bfi-dots').innerHTML = Array.from({ length: n }, (_, k) => `<i class="${k === i ? 'bfi-on' : ''}"></i>`).join('');
    ui.next.textContent = i === n - 1 ? 'Selesai' : 'Lanjut';
  }
  function hideTip() { const t = ui.tip; t.getAnimations().forEach(a => a.cancel()); t.style.opacity = '0'; t.style.visibility = 'hidden'; t.classList.remove('bfi-on'); nextFn = null; }

  /* ---------- adegan ---------- */
  function put(x, y, s, rx, ry) {
    const lg = ui.lg.style; lg.width = lg.height = s + 'px'; lg.left = (x - s / 2) + 'px'; lg.top = (y - s / 2) + 'px';
    lg.transform = `perspective(${innerWidth * 1.2}px) rotateX(${rx}deg) rotateY(${ry}deg)`;
  }
  /* logo sidebar -> ukuran & pusat logo 3D (ubin 3D = logo 44x44 asli) */
  const home = el => { const b = el.getBoundingClientRect(); return { x: b.left + b.width / 2, y: b.top + b.height / 2, w: b.width, s: b.width / TILE, b }; };

  async function opener(o, r) {
    const W = innerWidth, Hh = innerHeight, from = home(o.logo());
    const to = { x: W / 2, y: Hh * .4, s: Math.min(W * .17, Hh * .32) }, lg = ui.lg.style;
    ui.c1.setAttribute('stop-color', COL.tile[0]); ui.c2.setAttribute('stop-color', COL.tile[1]); setShape(pts('tile')); ui.gy.innerHTML = GLY.tile;
    put(from.x, from.y, from.s, 0, 0); lg.opacity = 1; ui.dt.style.opacity = 1; ui.gl.style.background = COL.tile[0];
    const dk0 = +getComputedStyle(ui.dk).opacity || 0;
    await tween(1100, t => {
      ui.dk.style.opacity = Math.max(dk0, t); ui.gl.style.opacity = t * .5;
      put(L(from.x, to.x, t), L(from.y, to.y, t), L(from.s, to.s, t), Math.sin(Math.PI * t) * -18, Math.sin(Math.PI * t) * 32);
    }, E.io, r);
    put(to.x, to.y, to.s, 0, 0); await wait(600, r);
    // titik merah lepas: bola muncul tepat di posisi & ukuran titik
    const dotPos = () => { const s = parseFloat(lg.width), x = parseFloat(lg.left), y = parseFloat(lg.top); return { x: x + s * DOT.cx / 200, y: y + s * DOT.cy / 200, d: s * DOT.r * 2 / 200 }; };
    const d = dotPos(); setOrb({ x: d.x, y: d.y, s: d.d, lift: 0 }); ui.dt.style.opacity = 0;
    const cx = to.x, cy = to.y, Rx = to.s * .8, Ry = to.s * .2, yo = to.s * .04, BIG = ORB() * 1.3;
    const orbitAt = a => ({ x: cx + Math.cos(a) * Rx, y: cy + yo + Math.sin(a) * Ry, front: Math.sin(a) });   // depan = bawah, belakang = atas
    const aL = Math.PI * .28, pL = orbitAt(aL), dep = a => BIG * (.62 + .5 * (Math.sin(a) + 1) / 2), sL = dep(aL);
    const zs = z => { ui.orb.style.zIndex = z; ui.osh.style.zIndex = z - 1; }; zs(20);
    // ancang-ancang, melompat keluar dari logo, jatuh ke lantai di depan logo, memantul + riak
    await crouch(r); const h0 = pL.y - d.y, Hp = to.s * .46;
    await fly(820, t => ({ x: L(d.x, pL.x, t), y: pL.y, lift: h0 * (1 - t) + 4 * Hp * t * (1 - t), s: L(d.d, sL, Math.min(1, t * 1.5)) }), 1, r);
    await land(1, 3, r); await bounceSeq(sL * BN.pk * 1.25, r, true); await wait(120, r);
    // mengelilingi logo: mengecil & tertutup logo saat lewat di belakang
    const span = Math.PI * 2.4, ez = t => (t < .2 ? t * t / .4 : t - .1) / .9;
    await tween(2800, t => {
      const a = aL + ez(t) * span, p = orbitAt(a), depth = (p.front + 1) / 2;
      setOrb({ x: p.x, y: p.y, lift: 0, s: dep(a) }); zs(p.front < 0 ? 5 : 20); ui.orb.style.filter = `brightness(${.72 + .28 * depth})`; ui.osh.style.opacity = p.front < 0 ? 0 : .35 * depth;
      put(cx, cy, to.s, -4 * Math.sin(a), 9 * Math.cos(a));
    }, E.lin, r);
    zs(20); ui.orb.style.filter = '';
    // morph: Isi data. Foto. Selesai.
    const wd = ui.wd.style; wd.top = (Hh * .62) + 'px';
    for (const [shape, word, sub] of (o.words || WORDS)) {
      if (r !== RUN) throw new Cancel();
      const a = ui.pts, b = pts(shape); ui.gy.style.opacity = 0; ui.gl.style.transition = 'background .7s'; ui.gl.style.background = COL[shape][0];
      ui.c1.setAttribute('stop-color', COL[shape][0]); ui.c2.setAttribute('stop-color', COL[shape][1]);
      ui.wd.innerHTML = `${word}<small>${sub}</small>`;
      ui.wd.animate([{ opacity: 0, transform: 'translateY(14px)', filter: 'blur(8px)' }, { opacity: 1, transform: 'none', filter: 'blur(0)' }], { duration: 520, fill: 'forwards', easing: 'cubic-bezier(.2,.8,.2,1)' });
      const o0 = { ...O }, dp = dotPos();
      await tween(760, t => {
        setShape(a.map((p, j) => [L(p[0], b[j][0], t), L(p[1], b[j][1], t)])); put(cx, cy, to.s, Math.sin(Math.PI * t) * 10, Math.sin(Math.PI * t) * -14);
        setOrb({ x: L(o0.x, dp.x + to.s * .08, t), y: L(o0.y, dp.y - to.s * .06, t), lift: L(o0.lift, to.s * .1, t), s: L(o0.s, ORB() * 1.2, t) });
      }, E.spring, r);
      ui.gy.innerHTML = GLY[shape]; ui.gy.style.opacity = 1; await wait(520, r);
    }
    // kembali menjadi logo, lalu mendarat di logo sidebar (bola = titik merahnya)
    ui.wd.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 300, fill: 'forwards' });
    const a = ui.pts, b = pts('tile'); ui.gy.style.opacity = 0; ui.c1.setAttribute('stop-color', COL.tile[0]); ui.c2.setAttribute('stop-color', COL.tile[1]);
    await tween(620, t => setShape(a.map((p, j) => [L(p[0], b[j][0], t), L(p[1], b[j][1], t)])), E.spring, r); ui.gy.innerHTML = GLY.tile; ui.gy.style.opacity = 1;
    const dst = home(o.logo()), o0 = { ...O };
    setHole({ x: dst.x, y: dst.y, w: 0, h: 0, r: 0 }, false); ui.ov.style.opacity = 1;   // layar redup menunggu di bawah gelap
    await tween(1150, t => {
      const x = L(cx, dst.x, t), y = L(cy, dst.y, t) - Math.sin(Math.PI * t) * Hh * .06, s = L(to.s, dst.s, t), w = s * TILE;
      put(x, y, s, Math.sin(Math.PI * t) * 14, Math.sin(Math.PI * t) * -20);
      ui.dk.style.opacity = 1 - t; ui.gl.style.opacity = .5 * (1 - t);
      setOrb({ x: L(o0.x, x + w * .25, t), y: L(o0.y, y - w * .216, t), lift: L(o0.lift, 0, t), s: L(o0.s, Math.max(4, w * .136), t) });
    }, E.io, r);
    await tween(300, t => { lg.opacity = 1 - t; }, E.io, r);
    setHole({ x: O.x, y: O.y, w: 0, h: 0, r: 0 }); await wait(200, r);
  }

  /* satu bab tur: sorotan menutup ke bola -> pindah layar -> bola melompat ke target ->
     sorotan membuka & bola duduk di pojok kanan atas -> tip menunggu "Lanjut" */
  async function chapter(c, i, n, r) {
    hideTip();
    const hs = { ...H }; await tween(300, u => setHole(closeTo(hs, u)), E.in, r);
    if (c.go) await c.go();
    let list = await findTarget(c, r); if (!list) return false;
    list[0].scrollIntoView({ block: 'center', inline: 'nearest', behavior: 'instant' });
    await frame(); await wait(c.settle == null ? 420 : c.settle, r);
    list = els(c); if (!list.length) return false;
    let h = rectOf(list, c.pad), cn = corner(h);
    const cx = h.x + h.w / 2, cy = h.y + h.h / 2;
    if (reduce) { setOrb({ x: cn.x, y: cn.y, s: ORB(), lift: 0 }); setHole(h); }
    else {
      if (O.s <= 0) setOrb({ x: innerWidth / 2, y: innerHeight / 2, s: ORB(), lift: 0 });
      await hop(cx, cy, r);
      const bt = bounceTo(cn.x, cn.y, r); bt.catch(() => {});
      await tween(700, u => { const s = Math.min(1, u); setHole({ x: L(cx, h.x, s), y: L(cy, h.y, s), w: L(0, h.w, s), h: L(0, h.h, s), r: L(ORB() / 2, h.r, s) }); }, E.spring, r);
      c._bt = bt;
    }
    fillTip(c, i, n); ui.tip.style.visibility = 'hidden'; ui.tip.style.opacity = '1'; placeTip(h); ui.tip.style.visibility = 'visible'; ui.tip.classList.add('bfi-on');
    if (!reduce) ui.tip.animate([{ opacity: 0, transform: 'translateY(8px)' }, { opacity: 1, transform: 'none' }], { duration: 380, easing: 'ease-out' });
    try { ui.next.focus({ preventScroll: true }); } catch (e) {}
    // ikuti target bila tata letak bergeser (kartu muncul, ukuran jendela berubah)
    let follow = true, bounced = false; if (c._bt) c._bt.then(() => { bounced = true; }, () => {}); else bounced = true;
    (function track() {
      if (!follow || r !== RUN) return; const l = els(c);
      if (l.length) { const nh = rectOf(l, c.pad); if (Math.abs(nh.x - h.x) + Math.abs(nh.y - h.y) + Math.abs(nh.w - h.w) + Math.abs(nh.h - h.h) > 1.5) { h = nh; setHole(h); placeTip(h); if (bounced) { const k = corner(h); setOrb({ x: k.x, y: k.y }); } } }
      requestAnimationFrame(track);
    })();
    await new Promise((res, rej) => { nextFn = res; const chkR = () => { if (r !== RUN) { follow = false; rej(new Cancel()); } else setTimeout(chkR, 200); }; chkR(); });
    follow = false; hideTip(); if (c._bt) await c._bt;
    return true;
  }

  async function ending(o, r) {
    hideTip(); const W = innerWidth, Hh = innerHeight;
    const hs = { ...H }; await tween(300, u => setHole(closeTo(hs, u), false), E.in, r);
    if (o.restore) await o.restore(); await wait(350, r);
    const m = o.logo().getBoundingClientRect(), dX = m.left + m.width * 33 / 44, dY = m.top + m.height * 12.5 / 44, dD = m.width * 6 / 44;
    setHole({ x: dX, y: dY, w: 0, h: 0, r: 0 }, false);
    if (O.s <= 0) setOrb({ x: W / 2, y: Hh / 2, s: ORB(), lift: 0 });
    // bola pulang tanpa memantul, langsung mengecil menjadi titik merah logo
    const a = { ...O }, Hp = Math.min(Hh * .2, 60 + Math.hypot(dX - a.x, dY - a.y) * .22);
    await crouch(r);
    await fly(820, t => { const u = E.io(t); return { x: L(a.x, dX, u), y: L(a.y, dY, u), lift: Hp * Math.sin(Math.PI * t), s: L(ORB(), dD, Math.max(0, (t - .4) / .6)) }; }, .35, r);
    setOrb({ x: dX, y: dY, lift: 0, s: dD }); await wait(140, r);
    // pendaran merah dari titik, lalu sapuan lingkaran membuka layar
    const Rmax = Math.hypot(Math.max(dX, W - dX), Math.max(dY, Hh - dY)) + 30, sp = ui.sw.style, bl = ui.bl.style;
    if (!reduce) {
      const b = Math.min(W * .42, 620); bl.width = bl.height = b + 'px'; bl.left = (dX - b / 2) + 'px'; bl.top = (dY - b / 2) + 'px';
      ui.bl.animate([{ opacity: 0, transform: 'scale(.05)' }, { opacity: 1, transform: 'scale(.6)', offset: .35 }, { opacity: 0, transform: 'scale(1.3)' }], { duration: 1100, easing: 'cubic-bezier(.2,.8,.2,1)' });
    }
    await tween(1400, u => {
      const rr = Rmax * u; setHole({ x: dX - rr, y: dY - rr, w: 2 * rr, h: 2 * rr, r: rr }, false);
      const band = 36 + rr * .5, Re = rr + band * .75, pc = v => Math.max(0, Math.min(100, v / Re * 100)).toFixed(2) + '%';
      sp.width = sp.height = 2 * Re + 'px'; sp.left = (dX - Re) + 'px'; sp.top = (dY - Re) + 'px'; sp.opacity = u < .65 ? 1 : Math.max(0, (1 - u) / .35);
      sp.background = `radial-gradient(circle closest-side,rgba(255,50,95,0) ${pc(rr - band * 1.4)},rgba(255,55,100,.1) ${pc(rr - band * .8)},rgba(255,60,104,.3) ${pc(rr - band * .3)},rgba(255,78,118,.55) ${pc(rr)},rgba(255,55,100,.32) ${pc(rr + band * .35)},rgba(255,45,92,0) 100%)`;
    }, E.io, r);
    ui.ov.style.opacity = 0; sp.opacity = 0; setOrb({ s: 0 }); ui.skip.style.display = 'none'; root.classList.add('bfi-pass');
    ui.dn.innerHTML = `Siap! Selamat bekerja, <b></b>`; ui.dn.querySelector('b').textContent = o.name || 'Teman';
    const an = ui.dn.animate([{ opacity: 0, transform: 'translate(-50%,-50%) scale(.92)', filter: 'blur(6px)' }, { opacity: 1, transform: 'translate(-50%,-50%) scale(1)', filter: 'blur(0)', offset: .18 },
      { opacity: 1, offset: .82 }, { opacity: 0, transform: 'translate(-50%,-50%) scale(1.02)' }], { duration: 3000, fill: 'forwards', easing: 'ease-out' });
    return an.finished.catch(() => {});
  }

  /* ---------- publik ---------- */
  function veil() {
    mount(); ui.dk.style.opacity = 0; ui.skip.style.display = 'none';
    ui.dk.animate([{ opacity: 0 }, { opacity: 1 }], { duration: RM() ? 0 : 280, fill: 'forwards' }).finished.then(() => { if (ui.dk) { ui.dk.style.opacity = 1; ui.dk.getAnimations().forEach(a => a.cancel()); } });
  }
  function unveil() {
    if (active || !root) return; const el = root;
    el.animate([{ opacity: 1 }, { opacity: 0 }], { duration: RM() ? 0 : 260, fill: 'forwards' }).finished.then(() => { if (root === el) unmount(); });
  }
  async function run(o) {
    if (active) return 'busy';
    reduce = RM(); active = true; const r = ++RUN; mount(); ui.skip.style.display = '';
    document.addEventListener('keydown', onKey, true);
    let ended = false; const end = kind => { if (ended) return; ended = true; try { o.onEnd && o.onEnd(kind); } catch (e) {} };
    const skipped = new Promise(res => { skipFn = () => { if (r !== RUN) return; RUN++; res('skip'); }; });
    const main = (async () => {
      if (reduce) { ui.dk.style.opacity = 0; ui.ov.style.opacity = 1; setHole({ x: innerWidth / 2, y: innerHeight / 2, w: 0, h: 0, r: 0 }, false); }
      else await opener(o, r);
      const ch = o.chapters || [];
      for (let i = 0; i < ch.length; i++) await chapter(ch[i], i, ch.length, r);
      end('done'); await ending(o, r); return 'done';
    })().catch(e => { if (!(e instanceof Cancel)) { console.error('intro', e); return 'error'; } return 'cancel'; });
    let res = await Promise.race([main, skipped]);
    if (res === 'skip' || res === 'error') {
      end('skip'); hideTip(); ui.skip.style.display = 'none';
      try { if (o.restore) await o.restore(); } catch (e) {}
      const el = root; if (el) await el.animate([{ opacity: 1 }, { opacity: 0 }], { duration: reduce ? 0 : 280, fill: 'forwards' }).finished.catch(() => {});
    }
    document.removeEventListener('keydown', onKey, true); nextFn = skipFn = null; active = false; unmount();
    return res === 'error' ? 'skip' : res;
  }
  window.BFIntro = { run, veil, unveil, get active() { return active; } };
})();
