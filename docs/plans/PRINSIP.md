# Prinsip desain BAA.flow (berlaku untuk setiap rencana & perubahan)

Ditetapkan pengguna, 2026-10-17: **tool ini harus selalu configurable dan futureproof.**

Turunan praktisnya — dicek di setiap catatan rencana sebelum "gas":

1. **Tidak ada nilai klien yang di-hardcode.** Label, istilah (mis. "SID"), format, daftar pilihan, aturan wajib/tidak, dan batas ukuran diatur admin per project (Settings), dengan nilai bawaan yang mempertahankan perilaku lama.
2. **Pola yang sama dipakai ulang.** Fitur baru mengikuti mekanisme yang sudah ada (field lokasi, kategori foto, mapping template, dsb.), bukan jalur khusus.
3. **Pengaturan ikut terbawa.** Setiap pengaturan baru ikut disalin saat project baru memakai project lain sebagai sumber, ikut backup/restore, dan bisa diekspor.
4. **Data lama aman.** Perubahan skema lewat migrasi otomatis; data lama tetap terbaca; fitur baru default-nya mati/opsional sampai diaktifkan.
5. **Identitas internal tidak berubah.** `id` lokasi tetap kunci internal; kode, SID, atau nama hanya tampilan/kunci pencocokan yang bisa diganti tanpa memutus relasi (foto, inventory, riwayat).
6. **Keluaran lewat template, bukan kode.** Isi Excel/PDF, nama file, dan kolom import/ekspor memakai placeholder/mapping yang bisa diubah admin.
7. **Peran & izin eksplisit.** Siapa yang boleh mengisi/mengubah/menghapus diatur per fitur (admin / operator / viewer), tidak diasumsikan.
8. **Mudah dikembangkan.** API & struktur data diberi ruang untuk tipe baru (mis. tipe lampiran, tipe field) tanpa mengubah yang lama.
