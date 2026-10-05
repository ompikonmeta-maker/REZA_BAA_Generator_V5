# Rencana: Kompres foto otomatis saat upload

Status: **Dicatat** · 2026-10-05 · menunggu jawaban pertanyaan + "gas"

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
