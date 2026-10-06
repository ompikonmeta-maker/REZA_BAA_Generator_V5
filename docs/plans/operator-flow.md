# Rencana: Alur kerja operator lebih efisien

Status: 0, 1, 2A, 4, 5 **selesai** · 3 **dibatalkan** · 2026-10-05 · desktop saja

Dasar: tes Playwright alur operator end-to-end (login → lokasi baru → data → wilayah → inventory → 11 foto → scan → Save → Log → export).

## 0. Bug: tombol Bulk export ikut tampil di BAA Entry — selesai
Location Log → panel detail → **Edit in BAA Entry** → bar atas memuat picker lokasi **dan** Bulk export (Excel/PDF ZIP/Ask where to save) bertumpuk. Penyebab: `gotoEntry()` tidak menyembunyikan `#locTools` / `#setSaveWrap`. Perbaikan 1 baris.

## 1. Simpan otomatis untuk draft — selesai
**Masalah:** foto & scan langsung tersimpan, tapi data lokasi, wilayah, inventory baru tersimpan saat **Save BAA** → operator mengira semua sudah aman (akar bug wilayah hilang, sudah diperbaiki 953dc1d).
**Usul:**
- Data, wilayah, inventory tersimpan otomatis ±1 detik setelah berhenti mengetik/memilih (hanya untuk draft).
- Indikator di bar atas: `Saving…` → `Saved · just now` (sama gaya dengan Settings).
- Tombol **Save BAA** menjadi **Finish BAA** (menandai Done); bila belum lengkap tetap menyimpan & menyebut yang kurang.
- Gagal simpan (offline/423 frozen) → indikator merah `Not saved — retry`, data tidak dibuang.
- Lokasi yang sudah Done tetap memakai Save manual (hindari perubahan tak sengaja).

## 2. Status Done harus jujur — opsi A, selesai
**Masalah:** Done bisa tercapai di 93% (scan PDF & wilayah tidak memblok Done) → status Done tapi masih ada chip kekurangan.
**Opsi:**
- **A (disarankan):** Done hanya bila 100% dari yang dihitung (mengikuti sakelar Scan PDF / Wilayah / field Required). Tombol: `Finish BAA · 2 left`.
- **B:** Done tetap seperti sekarang, tapi label jelas `DONE · Scan missing` di Log, drawer, Summary.

## 3. Foto berurutan (guided capture) — dibatalkan (desktop: klik kotak kosong sudah cukup)
**Masalah:** kategori otomatis mengandalkan nama file; foto HP (`IMG_1234.jpg`) masuk *Uncategorized* → dipindah satu per satu.
**Usul:** tombol **Take photos in order** → kartu "Next: Foto SN Router (3/11)" → kamera/galeri → otomatis masuk kategori itu → lanjut ke kategori kosong berikutnya. Ada **Skip** dan **Retake**. OCR SN tetap jalan. Catatan: tampilan app belum responsif untuk layar HP (sidebar menutupi layar) — mockup dibuat di desktop; versi HP perlu keputusan terpisah.

## 4. Export lebih singkat — selesai
**Masalah:** Excel/PDF → dialog "Yes" → dialog pilih folder (Ask where to save default ON) = 3 langkah.
**Usul:** export satu lokasi langsung jalan tanpa dialog "Yes"; **Ask where to save** default OFF (pilihan tetap diingat per user). Export massal tetap pakai konfirmasi.

## 5. Lanjut ke draft berikutnya — selesai
**Usul:** setelah Finish (Done), muncul baris `BAA complete ✓ · Next draft: LOK_00065 Kopdes … →` (draft milik operator, terlama dulu). Tombol ‹ › tetap ada.

## Urutan kerja yang disarankan
0 (bug) → 1 & 2 dulu (kepercayaan data) → 4 & 5 (cepat) → 3 (perlu uji di HP).

## Hasil implementasi (2026-10-05)
- Auto-save draft ±1 dtk (data, wilayah, inventory); indikator `Saving… / Saved · just now / Not saved — retry` di bar atas BAA Entry; pindah menu/lokasi tidak lagi memunculkan dialog untuk draft (disimpan dulu).
- Tombol **Finish BAA · N left** (tonal) → **Finish BAA** (filled) di 100%; lokasi Done memakai **Save changes** (manual); bila tidak lengkap lagi, kembali Draft.
- Server menolak status Done bila kelengkapan < 100% (rumus sama dengan Progress).
- Lokasi lama yang sudah Done di bawah 100% tetap Done sampai diubah & disimpan.
- Export Excel/PDF satu lokasi langsung terunduh; *Ask where to save* default OFF (pilihan ON tetap diingat).
- Setelah Finish: baris **Next draft** (draft milik user, terlama diubah dulu) atau "No drafts left".
- Panduan operator (teks + screenshot) diperbarui.

## Cek alur admin (2026-10-06) — selesai
Uji end-to-end instalasi baru (14 langkah) lulus. Perbaikan:
1. Chip Dashboard: "No locations yet" (belum ada lokasi), "No open drafts" (draft 0 tapi target belum tercapai), bukan "All locations done".
2. Pill jumlah di menu Location Log disembunyikan bila 0.
3. Template: bila deteksi otomatis 100% tanpa konflik, mapping langsung tersimpan saat upload (langkah Template langsung ✓); bila belum, muncul petunjuk untuk melengkapi lalu Save mapping.
