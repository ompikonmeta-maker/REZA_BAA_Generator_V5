# 28. Update progres BAPB ke Google Sheet + PDF ke Google Drive (rencana, 2026-11-09)

Status: **dicatat, menunggu mockup disetujui lalu "gas"**.

Mockup: https://claude.ai/artifact/EufjdGmi8PMtAiApUsQT5Y (layar update + alarm, Settings › Google Sheet, isian SO di project baru).

## Sheet tujuan
- "KDKMP Project", satu tab **Master**, header di baris 1, sekitar 349 baris, berisi beberapa SO (kolom T "SO").
- Pemilik sheet **bukan** tim BAA Flow. Perubahan sel bisa dilacak dari riwayat sel di Google Sheets.
- Kolom yang dipakai (dicari berdasarkan **judul header**, bukan huruf kolom):

| Header | Kolom (saat dicek) | Dipakai untuk |
|---|---|---|
| ID Node Link | C | kunci; = SID di BAA Flow |
| Nama Lokasi | D | pencocokan awal |
| Desa / Kecamatan / Kabupaten | F / G / H | pencocokan awal (pembeda nama kembar) |
| SO | T | lingkup project (boleh beberapa SO) |
| STATUS BAPB | BC | **ditulis** |
| TANGGAL BAPB | BD | **ditulis** |
| LINK BAPB | BE | **ditulis** |

## Keputusan pengguna
1. **Kunci = ID Node Link ↔ SID BAA Flow.**
   - Lokasi BAA Flow yang belum punya SID dicocokkan lewat Nama + Desa/Kec/Kab.
   - SID diambil dari sheet hanya dengan persetujuan admin.
   - Kalau SID BAA Flow berbeda dengan ID Node Link di baris yang cocok → alarm.
2. **BAA Flow hanya menulis tiga kolom: STATUS, TANGGAL, LINK BAPB.**
   - Nama lokasi, ID, dan kolom lain tidak pernah diubah di sheet.
   - Perbedaan cukup ditampilkan sebagai alarm.
3. **Satu project bisa berisi beberapa SO.**
   - Saat membuat (atau mengedit) project ada isian opsional **Nomor SO / order internal**, bisa lebih dari satu.
   - Kalau diisi, sheet dibatasi ke baris dengan SO tersebut untuk rekonsiliasi jumlah.
4. **STATUS BAPB:**
   - **Done** saat dokumen lengkap 100%;
   - **Undone** saat tanggal aktivasi sudah diisi tetapi dokumen belum 100%;
   - **kosong** kalau tanggal aktivasi belum diisi (lokasi hasil import yang belum di-entry).
   - Kalau dokumen turun lagi di bawah 100%, status kembali ke Undone.
5. **TANGGAL BAPB** = tanggal aktivasi BAA Flow, ditulis sebagai tanggal (format mengikuti sheet, mis. 23-Oct-2026).
6. **LINK BAPB:**
   - PDF gabungan diunggah ke **satu folder Google Drive** yang ditentukan, tanpa subfolder;
   - nama file **`Nama Lokasi-SID.pdf`**;
   - kalau dokumen berubah, file yang sama ditimpa sehingga link tetap.
7. **Sel yang sudah diisi orang lain boleh ditimpa.** Siapa yang mengubah bisa dilihat dari riwayat sel di sheet.
8. **Update manual**: tombol **"Update to GSheet"** disertai log (kapan terakhir, oleh siapa, berapa baris diubah, berapa PDF diunggah, apa yang gagal).
9. **Alarm rekonsiliasi:**
   - jumlah lokasi BAA Flow dibanding jumlah baris sheet (dalam SO project);
   - lokasi yang hanya ada di BAA Flow, dan baris yang hanya ada di sheet;
   - SID ≠ ID Node Link;
   - nama atau ID kembar di salah satu sisi;
   - nama sama tetapi desa/kecamatan berbeda;
   - baris yang tidak bisa dicocokkan (dilewati, tidak ditebak).
10. PC BAA Flow selalu online.

## Rancangan teknis (usulan)
- **Apps Script** ditempel sekali di sheet oleh pemiliknya, lalu di-deploy sebagai Web App (jalan atas nama pemilik, dilindungi kode rahasia). Aksinya:
  - `read`: mengirim baris (ID, nama, wilayah, SO, 3 kolom BAPB) untuk rekonsiliasi;
  - `update`: menulis kolom BC–BE per ID;
  - `upload`: menyimpan/menimpa PDF di folder Drive dan mengembalikan link.
- **Settings › Google Sheet** (per project):
  - URL Web App dan kode rahasia;
  - nama header kunci, nama, wilayah, SO, dan tiga kolom tujuan;
  - teks Done/Undone;
  - ID folder Drive.
  - Semua bisa diatur, tanpa nama kolom yang ditanam di kode.
- **BAA Flow** mencatat sidik (hash) terakhir yang terkirim per lokasi, jadi yang dikirim hanya yang berubah. PDF hanya diunggah ulang kalau isinya berubah.
- Log update disimpan per project.

## Keputusan lanjutan (2026-11-09)
- **Update pertama:** operator menyelesaikan lokasi satu per satu, jadi PDF terunggah bertahap. Yang dikirim hanya yang berubah.
- **SO baru:** ditambah di pengaturan project (chip SO yang sama dengan saat buat project), kapan saja.
- **Lokasi baru dari sheet:** baris ber-SO project yang belum ada di BAA Flow muncul di alarm "Only in sheet".
  - Admin mencentang lalu klik **Create in BAA Flow**.
  - Lokasi draf dibuat dengan nama, desa/kec/kab/prov, SID = ID Node Link, dan SO dari sheet.
  - Tanggal aktivasi tetap diisi operator.
  - Import Excel dan tambah manual tetap ada.
- **SO per lokasi:**
  - disimpan per lokasi; sumber utamanya kolom SO di sheet, dan template import juga diberi kolom **SO**;
  - Locations dan Reports bisa difilter per SO.
