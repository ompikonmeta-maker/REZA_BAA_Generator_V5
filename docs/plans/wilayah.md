# Rencana: Data Wilayah + Infografis Peta

Status: **Tahap 1 selesai** (referensi, pencarian, sakelar per project, kelengkapan, filter, isi massal) · tahap 2–3 belum · 2026-10-04

## Keputusan
| Topik | Keputusan |
|---|---|
| Tingkat wilayah | Desa/Kelurahan, Kecamatan, Kab/Kota, Provinsi — satu kesatuan (dipilih sekaligus) |
| Per project | Sakelar **Wilayah data** on/off + sub-sakelar **Count in location progress** (lihat bawah). Bawaan project baru & Project 1: **ON + ON** (tool belum dipakai) |
| Scan PDF | Tetap wajib di semua project (tidak ikut sakelar ini) |
| Template BAA | Belum punya sel wilayah → data dipakai di dalam app; target mapping Excel tetap disediakan (opsional) |
| Data awal | Mungkin ada dari pemberi kerja → Import Locations mencocokkan otomatis |
| Foto via WhatsApp | GPS EXIF hilang → **tanpa** fitur koordinat/titik lokasi; peta murni per wilayah |
| Pengguna peta | Admin & viewer |

## Sakelar per project (Settings › Projects › Features)
| Wilayah data | Count in progress | Perilaku |
|---|---|---|
| OFF | (nonaktif) | Field, filter, isi massal, peta, Team by wilayah, peta mini Portfolio disembunyikan untuk project ini. Data yang sudah ada **tetap disimpan** dan muncul lagi bila dinyalakan. |
| ON | ON | Field wajib (*), masuk % kelengkapan, chip "Wilayah" bila kosong (tidak memblok Done/export). |
| ON | OFF | Field **opsional** (tanpa *), tidak memengaruhi %, tanpa chip. Peta tetap jalan; lokasi tanpa wilayah = kelompok "Belum ada wilayah". |
- Menyalakan "Count in progress" saat sudah ada lokasi tanpa wilayah → konfirmasi berisi jumlah lokasi terdampak + saran pakai "Set wilayah".
- Peta/peringkat memakai status Done lokasi (bukan kelengkapan wilayah), jadi tetap berguna saat sub-sakelar OFF.
- Hanya admin yang bisa mengubah; server mengikuti sakelar (validasi wajib, perhitungan %, kolom export).

## Penanganan data
- **Referensi resmi** kode wilayah Kemendagri (≈84 rb desa) dibundel offline (SQLite, ±3–5 MB, berversi untuk pemekaran).
- **Input**: satu field "Wilayah" dengan pencarian (ketik desa → pilih) → keempat tingkat terisi sekaligus.
- **Pencarian cepat** (offline, instan untuk ±84 rb desa):
  - beberapa kata, urutan bebas; tiap kata dicocokkan ke semua tingkat dan semua harus cocok — `cibodas lembang`, `sukamaju cianjur`;
  - singkatan provinsi dikenali (`jabar`, `jateng`, `jatim`, `sulsel`, `ntb`, `ntt`, `dki`, `diy`, …); kata `kab`, `kec`, `desa`, titik & huruf besar diabaikan;
  - toleran salah ketik ringan (`cibodaz`, `lembng`), diurutkan di bawah yang persis cocok; baris "Matched:" menjelaskan kata mana cocok ke apa;
  - urutan pintar: kecamatan/kab yang sering dipakai di project ini (terutama oleh user tsb) di atas, ditandai "used in this project";
  - tombol penyempit bila hasil banyak: provinsi (dengan jumlah) → klik → kab/kota; bisa dilepas (✕);
  - ketik kode wilayah (mis. `32.17.01`) → desa di kecamatan itu.
- **Simpan**: `wilayah_kode` (kolom ber-index di `locations`) + snapshot nama 4 tingkat (BAA lama tidak berubah saat referensi diperbarui).
- **Kelengkapan** (bila Count in progress ON): dihitung 1 item "Wilayah" (bukan 4); hanya ditandai kurang, tidak memblok Done/export.
- **Isi massal** di Location Log: centang lokasi → "Set wilayah" (untuk 60+ lokasi lama).
- **Import**: kolom Desa/Kec/Kab/Prov → dicocokkan ke kode; hasil ✓ cocok / ? ambigu (pilih) / ✗ tidak ditemukan (perbaiki). Tidak ada penyimpanan diam-diam.
- **Excel**: 4 target mapping (Log & Detail), opsional.
- **Export ZIP**: opsi folder per wilayah, mis. `Jawa Barat/Kab. Bandung/LOK_00012 ….pdf`.
- **Filter** Location Log per provinsi/kab/kota.

## Wilayah yang tidak ada di data Kemendagri (rencana, belum dikerjakan)
Keputusan: kasus utama = desa tidak ada tapi kecamatan ada; kasus "tidak cocok sama sekali" tetap didukung.
**Nama yang dicetak di Excel/BAA = sesuai tulisan teknisi.** Operator boleh mengisi manual; admin meninjau.

| Kasus | Cara isi | Simpan | Rekap / peta |
|---|---|---|---|
| 1. Desa tak ada, kecamatan ada | Opsi "Desa not in the list? Enter it manually" di bawah hasil → pilih **kecamatan resmi** + ketik desa | kode kecamatan + nama desa manual, badge **Desa manual** | ikut kecamatan/kab/prov resmi (tetap masuk peta) |
| 2. Tidak cocok sama sekali | "Switch to fully manual" → 4 kolom diketik | tanpa kode, badge **Unverified** | kelompok "Belum terverifikasi" |
| 3. Resmi ada, ejaan beda | pilih resmi → "As written by technician" (4 kolom, terisi nama resmi, bisa diubah; tampil "Official: …") | kode resmi + nama tertulis | pakai kode resmi |

- Semua kasus dihitung "terisi" untuk kelengkapan.
- **Excel/BAA mencetak nama tertulis** (default = nama resmi bila tidak diubah).
- Location Log: badge Desa manual / Unverified, filter **"Manual wilayah"**.
- Admin: **"Link to official wilayah"** per lokasi/massal dengan saran (kecocokan nama di kecamatan yang sama); tulisan teknisi tetap dipertahankan. Saat update data Kemendagri, aplikasi menyarankan pasangan untuk isian manual.

## Update data Kemendagri
- **Jalur A (dipakai):** data wilayah baru disiapkan di repo → build → EXE baru mendeteksi versi data lebih baru saat start dan memperbarui referensi otomatis. Data lokasi tidak diubah diam-diam.
- **Jalur B (ditunda):** upload paket wilayah oleh admin (Settings › Wilayah, pratinjau perubahan) — ditambahkan hanya bila nanti dibutuhkan.
- Settings menampilkan versi data aktif (mis. "Kepmendagri 2025 · 83.7xx desa").
- Tiap lokasi menyimpan kode + snapshot nama saat input → BAA lama tidak berubah. Setelah update dibuat laporan dampak:

| Kasus | Penanganan |
|---|---|
| Desa baru | Langsung bisa dicari |
| Ganti nama, kode sama | Lokasi tetap valid; **admin memutuskan** "Perbarui nama" (massal) atau tetap nama lama — tidak otomatis |
| Pindah induk / kode berubah (pemekaran) | Ditandai **"Wilayah perlu dicek"** + saran pengganti (cocok nama & induk), konfirmasi lewat isi massal |
| Kode dihapus / digabung | Ditandai sama; admin memilih pengganti |

- "Perlu dicek" hanya pemberitahuan: tidak memblok Done/export, tidak mengurangi progres; muncul di Notifications admin + filter Location Log.
- Batas peta punya versi sendiri (ikut jalur A); wilayah baru yang belum ada batas petanya tampil sebagai daftar.

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
Snapshot (Playwright, di app nyata dengan data demo): panel Features (ON+ON, ON+opsional, OFF) + konfirmasi, cari desa, wilayah terpilih, tombol penyempit (provinsi → kab/kota),
beberapa kata + singkatan + salah ketik, isi massal + dialog,
peta Progress, drill-down Jawa Barat (treemap), Team by wilayah.
