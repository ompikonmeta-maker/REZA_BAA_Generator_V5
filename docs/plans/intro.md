# Rencana: Intro animasi sebelum Dashboard

Status: **Mockup** · 2026-10-09 · mockup: https://claude.ai/artifact/M7C8oLJ6du5tHeSvqGKRPr

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

## Alur
1. Login (username/password diketik, Sign in) → 2. logo login terangkat jadi logo 3D, bola merah mengitari → 3. morph pin "Isi data." → kamera "Foto." → segel "Selesai." → 4. logo mendarat di logo sidebar Dashboard → 5. tur spotlight per bab → 6. bola kembali jadi titik logo, sorotan melebar, Dashboard siap.

## Catatan teknis
- Posisi sorotan diambil dari `getBoundingClientRect()` elemen asli (bukan perkiraan) → di aplikasi nyata sorotan menempel ke elemen hidup, bukan screenshot.
- Morph bentuk ditulis sendiri (sampel titik path), tanpa library; semua aset lokal (offline).
- `prefers-reduced-motion`: tanpa morph/lompatan, hanya pergantian halus.
