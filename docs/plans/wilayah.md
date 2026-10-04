# Rencana: Data Wilayah + Infografis Peta

Status: **dicatat (belum dikerjakan)** · mockup disetujui untuk dibahas · 2026-10-04

## Keputusan
| Topik | Keputusan |
|---|---|
| Tingkat wilayah | Desa/Kelurahan, Kecamatan, Kab/Kota, Provinsi — **semua wajib** |
| Template BAA | Belum punya sel wilayah → data dipakai di dalam app; target mapping Excel tetap disediakan (opsional) |
| Data awal | Mungkin ada dari pemberi kerja → Import Locations mencocokkan otomatis |
| Foto via WhatsApp | GPS EXIF hilang → **tanpa** fitur koordinat/titik lokasi; peta murni per wilayah |
| Pengguna peta | Admin & viewer |

## Penanganan data
- **Referensi resmi** kode wilayah Kemendagri (≈84 rb desa) dibundel offline (SQLite, ±3–5 MB, berversi untuk pemekaran).
- **Input**: satu field "Wilayah" dengan pencarian (ketik desa → pilih) → keempat tingkat terisi sekaligus.
- **Simpan**: `wilayah_kode` (kolom ber-index di `locations`) + snapshot nama 4 tingkat (BAA lama tidak berubah saat referensi diperbarui).
- **Kelengkapan**: dihitung 1 item "Wilayah" (bukan 4); hanya ditandai kurang, tidak memblok Done/export.
- **Isi massal** di Location Log: centang lokasi → "Set wilayah" (untuk 60+ lokasi lama).
- **Import**: kolom Desa/Kec/Kab/Prov → dicocokkan ke kode; hasil ✓ cocok / ? ambigu (pilih) / ✗ tidak ditemukan (perbaiki). Tidak ada penyimpanan diam-diam.
- **Excel**: 4 target mapping (Log & Detail), opsional.
- **Export ZIP**: opsi folder per wilayah, mis. `Jawa Barat/Kab. Bandung/LOK_00012 ….pdf`.
- **Filter** Location Log per provinsi/kab/kota.

## Infografis
- **Progress (admin & viewer)** — hero card:
  - peta Indonesia per provinsi, warna = % Done (skala sekuensial dari warna primer project), hover = kartu ringkas, klik = drill-down;
  - drill-down kab/kota sebagai **treemap** (ukuran = target, warna = % done) → klik = daftar kecamatan;
  - toggle: % Done / Drafts / Behind;
  - "Furthest behind (kab/kota)" dengan penanda posisi seharusnya hari ini; klik = filter Location Log;
  - cakupan: "412 dari 640 kecamatan terjangkau".
- **Supervisor (admin)** — "Team by wilayah": draft per operator per kab/kota; amber = tidak berubah ≥ 7 hari kerja.
- **Portfolio** — peta mini area kerja per kartu project.
- Peta digambar sendiri (SVG, tanpa CDN/internet). Batas wilayah dari data terbuka (mis. geoBoundaries, CC BY) yang disederhanakan: provinsi ±1 MB, kab/kota ±5 MB; kecamatan/desa = daftar/treemap (bukan peta). Nama batas wilayah diselaraskan sekali ke kode Kemendagri.

## Tahapan
1. Referensi wilayah, field pencarian di BAA Entry, kelengkapan, filter & isi massal Location Log.
2. Import (pencocokan), target mapping Excel, folder per wilayah di ZIP.
3. Peta Progress + drill-down, peringkat, cakupan, Team by wilayah, peta mini Portfolio.

## Mockup
Snapshot (Playwright, di app nyata dengan data demo): cari desa, wilayah terpilih, isi massal + dialog,
peta Progress, drill-down Jawa Barat (treemap), Team by wilayah.
