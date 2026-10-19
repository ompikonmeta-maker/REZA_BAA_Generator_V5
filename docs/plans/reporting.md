# Reporting & status Node aktif (rencana, 2026-10-19)

Status: **✅ dikerjakan 2026-10-19** ("gas" atas mockup).

## Keputusan pengguna
1. Laporan sebisa mungkin informatif untuk semua pihak/stakeholder.
2. Dibuat **sesuai permintaan** (klik → unduh), bukan terjadwal.
3. Laporan = **data jadi** (PDF siap kirim) **+ Excel yang bisa diolah** (kebutuhan data sering berubah).
4. Rekonsiliasi SID **tidak perlu**. Tambah **rata-rata penyelesaian dokumen**, dihitung dari **tanggal aktivasi link**.
5. Format laporan dari klien **boleh** (upload Excel klien → petakan, pola sama dengan template BAA).
6. Peta: tambah status **Node aktif** berdasarkan tanggal aktivasi yang diisi operator saat entry BAA.

## Rancangan awal
- **Peran field (configurable):** di Settings › Location fields, satu field tanggal ditandai sebagai *Tanggal aktivasi*.
  Bawaan: field `tanggal` ("Tanggal Aktivasi"). Tidak ada nama field yang di-hardcode.
- **Definisi:**
  - *Node aktif* = lokasi yang tanggal aktivasinya terisi dan ≤ tanggal laporan.
  - *Lama penyelesaian dokumen* = tanggal BAA pertama kali Done − tanggal aktivasi (hari kalender).
  - *Backlog* = node aktif yang BAA-nya belum Done, beserta umurnya sejak aktivasi.
  - Data janggal (Done sebelum aktivasi, Done tanpa tanggal aktivasi) dipisahkan & ditandai, tidak ikut rata-rata.
- **Menu Reports (admin/viewer):** pilih periode + filter (wilayah, owner, status) → unduh PDF dan/atau Excel.
  - PDF: ringkasan KPI (target · node aktif · BAA Done · backlog · rata-rata/median hari), tren mingguan
    (aktivasi vs Done), rekap per wilayah, rekap per operator, distribusi lama penyelesaian, daftar backlog terlama,
    daftar kekurangan per lokasi.
  - Excel: sheet yang sama dalam bentuk tabel mentah + satu sheet data per lokasi (semua kolom) untuk diolah.
  - Template klien (opsional, tahap berikutnya): Excel klien dipetakan ke angka/tabel laporan.
- **Peta:** status Node aktif per wilayah (jumlah aktif vs BAA Done), dengan legenda warna sendiri.

## Temuan dari data demo (project LOK, 85 lokasi)
- 63 lokasi punya tanggal aktivasi; 27 di antaranya sudah Done → rata-rata bisa dihitung.
- 36 node aktif belum Done (backlog). 3 lokasi Done tanpa tanggal aktivasi.
- Sebagian Done tercatat **sebelum** tanggal aktivasi (selisih negatif) → perlu aturan data janggal (lihat atas).

## Keputusan lanjutan (2026-10-19)
- BAA selesai **sebelum** tanggal aktivasi = kesalahan data. Selesai di hari yang sama atau sesudahnya = normal (0 hari boleh).
- Peta: tombol baru **NIS** (node in service) → 4 tombol: **% Done · NIS · Drafts · Stale**.
- Patokan dokumen selesai: saat dokumen BAA lengkap 100% (scan BAA bertanda tangan sudah di-upload + BAA hasil generate),
  bukan saat tombol Finish/Done. Waktu pertama kali mencapai 100% perlu dicatat (kolom baru, isi awal dari riwayat).

**Mockup (2026-10-19):** https://claude.ai/artifact/3591eHiZyBgnnnsf398Ejy — peta mode NIS (warna wilayah = jumlah NIS,
hover: NIS · dokumen selesai · % dari NIS · backlog), menu Reports (periode, wilayah, owner, pilih bagian, preview KPI,
unduh PDF/Excel, kartu format klien), contoh PDF 2 halaman dari data demo (rata-rata 11,1 hari, median 10, 13 dokumen;
17 data perlu dicek). Usulan: peringatan di Entry bila tanggal aktivasi di masa depan. Menunggu "gas".

## Dikerjakan (2026-10-19)
- **Tanggal aktivasi:** Settings › Location fields → pil *Activation date* pada field bertipe Date (satu saja). Disimpan sebagai
  `role: "activation"`; belum pernah diatur → field `tanggal`. Semua dimatikan → NIS & lama penyelesaian nonaktif.
- **Dokumen selesai:** kolom `locations.complete_at`, diisi otomatis di `db.touch_modified` saat kelengkapan pertama kali 100%,
  dikosongkan bila turun < 100% (mis. scan dihapus). Data lama diisi sekali dari riwayat aktivitas (`backfill_complete_at`).
- **Peta:** tombol NIS (% Done · NIS · Drafts · Stale), hanya muncul bila tanggal aktivasi aktif. Hover: NIS, dokumen selesai, % dari NIS, backlog.
- **Reports** (menu baru, admin & viewer): periode, wilayah, owner, pilih bagian, preview angka; unduh PDF (reportlab, offline)
  dan Excel (satu sheet per bagian, tabel polos + sheet Lokasi berisi semua kolom). API: `/api/reports/summary|pdf|xlsx`.
- **Catatan angka:** lokasi berstatus Done tetapi belum 100% (mis. di-Done sebelum scan diwajibkan) tidak dihitung selesai
  dan disebut terpisah di laporan.
- **Entry:** peringatan (tidak memblokir) bila tanggal aktivasi di masa depan atau setelah dokumen lengkap.
- Format laporan klien: belum (tahap berikutnya).

## 25. Tanggal aktivasi wajib sebelum simpan (2026-10-19, ✅)
- Keputusan: lokasi dari BAA Entry baru tersimpan setelah tanggal aktivasi diisi → setiap draf = NIS.
  Import tetap boleh tanpa tanggal (lokasi "belum aktif"). Data lama tanpa tanggal dibiarkan (data simulasi),
  tetapi edit berikutnya wajib mengisi tanggal aktivasi dulu.
- Sakelar per project: Settings › Location fields › *Activation date · Required before saving* (bawaan aktif),
  setting `activation_rule`, ikut tersalin saat project disalin.
- Server menolak (400) simpan data, inventory, upload foto/scan/lampiran bila tanggal aktivasi kosong.
- Entry: field tanggal aktivasi tampil pertama + banner; autosave ditahan ("Fill in … to save"), upload & Save
  membuka date picker; begitu tanggal diisi, kode dibuat dan draf tersimpan otomatis.
- Laporan: NIS = dokumen selesai dari NIS + backlog; Dokumen selesai = dari NIS + tanpa tanggal aktivasi;
  jumlah lokasi belum aktif ditampilkan.
