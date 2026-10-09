# Rencana: Intro animasi sebelum Dashboard

Status: **Terpasang** · 2026-10-09 · mockup: https://claude.ai/artifact/M7C8oLJ6du5tHeSvqGKRPr

## Keputusan
| Topik | Keputusan |
|---|---|
| Gaya | **A + C**: logo morph (pembuka) + spotlight di layar asli (tur fitur) |
| Bahasa | Indonesia |
| Admin | Intro pendek sendiri: Setup, Activate, Team, Template BAA, Freeze, Progress, Bantuan |
| Operator | Mulai BAA baru, Draf saya, Isi data & wilayah, Tersimpan otomatis, Foto, Scan PDF, Yang masih kurang, Finish 100%, Export 1 klik, Location Log, Bantuan |
| Kapan muncul | **Sekali** per user setelah login pertama; bisa diputar ulang dari tombol ? |
| Skip | Selalu ada |
| 3D | Logo bf terangkat & berputar (perspektif + ketebalan); **titik merah logo** lepas menjadi bola 3D (bayangan, pantulan, squash saat mendarat) yang memandu sorotan dan duduk di pojok kanan atas tiap sorotan |
| Pantulan | **Kartun**: ancang-ancang, melar saat melayang, gepeng & goyang jeli saat mendarat, riak tebal + garis benturan (keluar dari logo: tiap pantulan beriak; spotlight: benturan pertama) |
| Akhir | Bola pulang tanpa memantul, mengecil jadi titik merah logo sidebar → pendaran merah lebar melingkar membuka layar → sapaan di tengah |

## Alur
1. Login (username/password diketik, Sign in) → 2. logo login terangkat jadi logo 3D, bola merah mengitari → 3. morph pin "Isi data." → kamera "Foto." → segel "Selesai." → 4. logo mendarat di logo sidebar Dashboard → 5. tur spotlight per bab → 6. bola kembali jadi titik logo, sorotan melebar, Dashboard siap.

## Catatan teknis
- Posisi sorotan diambil dari `getBoundingClientRect()` elemen asli (bukan perkiraan) → di aplikasi nyata sorotan menempel ke elemen hidup, bukan screenshot.
- Morph bentuk ditulis sendiri (sampel titik path), tanpa library; semua aset lokal (offline).
- `prefers-reduced-motion`: tanpa morph/lompatan, hanya pergantian halus.

## Implementasi
- Mesin: `app/web/assets/intro.js` (`BFIntro.run/veil/unveil`), CSS disuntik sendiri dengan prefix `bfi-` (tidak bentrok dengan class aplikasi).
- Bab & pemicu: `app/web/index.html` (`introOp`, `introAd`, `introStart`, `introRestore`). Target sorotan = elemen hidup (`getBoundingClientRect`), sorotan mengikuti bila tata letak bergeser.
- Tip menunggu tombol **Lanjut** (Enter / Spasi / → juga bisa); **Esc** atau "Lewati intro" = lewati.
- Bab yang tidak relevan dilewati otomatis: Scan PDF off, project Frozen (operator: bab isian), admin di project aktif (bab Setup/Activate), admin di mode Setup (Freeze/Progress).
- BAA Entry dibuka pada draf milik user (tanpa lokasi: form baru di memori, tidak dibuat di server). Setelah intro, tampilan dikembalikan seperti semula.
- Server: `users.intro_seen_at`, `/api/auth/me` → `intro_seen`, `POST /api/auth/intro-seen` (dipanggil saat selesai atau dilewati).
- Login pertama: layar langsung digelapkan (`BFIntro.veil`) agar Dashboard tidak berkedip; bila wajib ganti password, intro mulai setelah password diganti.
- Putar ulang: tombol ? → menu **User guide** / **Replay intro**.
- `prefers-reduced-motion`: tanpa pembuka 3D & lompatan, sorotan langsung pindah.
- Skrip foto panduan (`docs/guide/shots.cjs`) menandai akun sudah melihat intro agar tidak ikut terfoto.
