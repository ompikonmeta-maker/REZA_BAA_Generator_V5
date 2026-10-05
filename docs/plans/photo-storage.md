# Rencana: Kompres foto otomatis saat upload

Status: **Selesai** · 2026-10-05

## Masalah
Foto disimpan ukuran asli (3–5 MB/foto, maks 25 MB). 11 foto × 120 lokasi ≈ 6 GB → backup lambat, disk PC cepat penuh.
Export Excel sudah mengecilkan gambar saat export, jadi ukuran asli tidak dibutuhkan untuk dokumen BAA.

## Usul
- Saat upload: sisi terpanjang maks **2000 px**, simpan **JPEG kualitas 85** (±300–500 KB/foto) → ±85–90% lebih hemat.
- Rotasi HP (EXIF orientation) diterapkan dulu agar foto tidak miring.
- **OCR dibaca dari foto asli** sebelum dikompres (akurasi SN tetap).
- Foto yang sudah kecil (≤ 2000 px dan ≤ 1 MB) tidak diubah.
- Berlaku juga untuk upload dari panel detail Location Log, ganti foto, dan editor foto.
- Scan PDF tidak diubah.

## Pertanyaan
1. Foto lama yang sudah tersimpan: ikut dikompres (tombol sekali jalan di Backup) atau hanya foto baru?
2. Screenshot (PNG: dashboard, tes ping, speed test): tetap PNG agar teks tajam, atau ikut jadi JPEG?
3. Metadata foto (tanggal & GPS kamera): dibuang (privasi, lebih kecil) atau disimpan (bukti lokasi)?
4. Sakelar admin "Compress photos" per project, atau selalu aktif?

## Keputusan (ikut saran)
1. Foto lama: tombol **Compress existing photos** di Settings › Backup & Restore (semua project, bertahap, ada progres).
2. Screenshot PNG/GIF/BMP tetap PNG (lossless), hanya dikecilkan ke 2000 px; dibiarkan bila hasilnya tidak lebih kecil.
3. Metadata kamera (tanggal, GPS) dipertahankan; orientasi diterapkan lalu di-reset.
4. Selalu aktif, tanpa sakelar.

## Implementasi
- `app/services/imgstore.py` — `compress()` & `needs_check()`.
- Upload foto (`POST /api/locations/{id}/photos`, dipakai BAA Entry, panel detail, editor foto): OCR membaca file asli, lalu disimpan versi kompres.
- `GET /api/photos/storage`, `POST /api/photos/compress-all` (admin, kursor per project/foto, maks ±8 dtk per panggilan).
- Uji: foto HP 6,9 MB 4000×3000 (miring, GPS) → 584 KB 1500×2000 tegak, tanggal & GPS tetap; foto lama 6,9 MB → 581 KB; semua foto tetap tampil.
