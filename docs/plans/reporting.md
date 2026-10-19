# Reporting & status Node aktif (rencana, 2026-10-19)

Status: **diskusi → mockup** (belum "gas").

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

## Pertanyaan terbuka
- Tampilan peta: tombol ganti mode (BAA ↔ Node aktif) atau digabung dalam satu tampilan?
- Patokan "dokumen selesai": BAA Done (Finish) atau saat pertama kali diekspor/dikirim?
