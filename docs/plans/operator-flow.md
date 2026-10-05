# Rencana: Alur kerja operator lebih efisien

Status: **Mockup** · 2026-10-05 · menunggu "gas" per nomor

Dasar: tes Playwright alur operator end-to-end (login → lokasi baru → data → wilayah → inventory → 11 foto → scan → Save → Log → export).

## 0. Bug: tombol Bulk export ikut tampil di BAA Entry
Location Log → panel detail → **Edit in BAA Entry** → bar atas memuat picker lokasi **dan** Bulk export (Excel/PDF ZIP/Ask where to save) bertumpuk. Penyebab: `gotoEntry()` tidak menyembunyikan `#locTools` / `#setSaveWrap`. Perbaikan 1 baris.

## 1. Simpan otomatis untuk draft
**Masalah:** foto & scan langsung tersimpan, tapi data lokasi, wilayah, inventory baru tersimpan saat **Save BAA** → operator mengira semua sudah aman (akar bug wilayah hilang, sudah diperbaiki 953dc1d).
**Usul:**
- Data, wilayah, inventory tersimpan otomatis ±1 detik setelah berhenti mengetik/memilih (hanya untuk draft).
- Indikator di bar atas: `Saving…` → `Saved · just now` (sama gaya dengan Settings).
- Tombol **Save BAA** menjadi **Finish BAA** (menandai Done); bila belum lengkap tetap menyimpan & menyebut yang kurang.
- Gagal simpan (offline/423 frozen) → indikator merah `Not saved — retry`, data tidak dibuang.
- Lokasi yang sudah Done tetap memakai Save manual (hindari perubahan tak sengaja).

## 2. Status Done harus jujur
**Masalah:** Done bisa tercapai di 93% (scan PDF & wilayah tidak memblok Done) → status Done tapi masih ada chip kekurangan.
**Opsi:**
- **A (disarankan):** Done hanya bila 100% dari yang dihitung (mengikuti sakelar Scan PDF / Wilayah / field Required). Tombol: `Finish BAA · 2 left`.
- **B:** Done tetap seperti sekarang, tapi label jelas `DONE · Scan missing` di Log, drawer, Summary.

## 3. Foto berurutan (guided capture)
**Masalah:** kategori otomatis mengandalkan nama file; foto HP (`IMG_1234.jpg`) masuk *Uncategorized* → dipindah satu per satu.
**Usul:** tombol **Take photos in order** → kartu "Next: Foto SN Router (3/11)" → kamera/galeri → otomatis masuk kategori itu → lanjut ke kategori kosong berikutnya. Ada **Skip** dan **Retake**. OCR SN tetap jalan. Catatan: tampilan app belum responsif untuk layar HP (sidebar menutupi layar) — mockup dibuat di desktop; versi HP perlu keputusan terpisah.

## 4. Export lebih singkat
**Masalah:** Excel/PDF → dialog "Yes" → dialog pilih folder (Ask where to save default ON) = 3 langkah.
**Usul:** export satu lokasi langsung jalan tanpa dialog "Yes"; **Ask where to save** default OFF (pilihan tetap diingat per user). Export massal tetap pakai konfirmasi.

## 5. Lanjut ke draft berikutnya
**Usul:** setelah Finish (Done), muncul baris `BAA complete ✓ · Next draft: LOK_00065 Kopdes … →` (draft milik operator, terlama dulu). Tombol ‹ › tetap ada.

## Urutan kerja yang disarankan
0 (bug) → 1 & 2 dulu (kepercayaan data) → 4 & 5 (cepat) → 3 (perlu uji di HP).
