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

## Tahap 1: SO di project & per lokasi (2026-11-09, ✅)
- **Project:** isian chip "SO / internal order numbers" di Settings › All projects / Project & status, opsional, bisa lebih dari satu.
  - Disimpan sebagai setting project `so_list`.
  - SO yang masih dipakai lokasi tidak bisa dihapus (400).
  - Tidak ikut tersalin saat project disalin (order berbeda per project).
- **Lokasi:**
  - kolom `locations.so`;
  - Entry punya pilihan **SO / order** di bawah SID; daftar dari project, tersimpan langsung (`PUT /api/locations/{id}/so`, aktivitas "SO set to …");
  - API create/update menerima `so`, dan nilainya harus terdaftar di project.
- **Import Excel:**
  - kolom **SO** di template (judul dikenali: SO, No SO, Nomor SO, Order, No Order);
  - angka Excel 11803.0 dibaca "11803";
  - SO yang belum terdaftar ditandai "new" di preview, lalu otomatis masuk daftar SO project saat import.
- **Filter SO** (termasuk "No SO yet"):
  - Location Log, dengan chip SO di kolom kode;
  - export massal Excel / PDF / ZIP mengikuti filter;
  - Reports: preview, PDF, dan Excel. Sheet Lokasi diberi kolom SO, dan label filter di laporan menyebut SO.
- Belum: filter SO di Dashboard (Dashboard belum punya filter apa pun). SO dari Google Sheet ditangani di tahap 2.

## Tahap 2: koneksi sheet + Check only + alarm (2026-11-09, ✅)
- **Apps Script** (`app/data/gsheet_apps_script.gs`, tombol *Copy Apps Script*):
  - aksi `ping`, `read`, `update`, `upload` (dua aksi terakhir dipakai di tahap 3);
  - dilindungi SECRET; menulis hanya kolom yang diminta, dicari lewat header baris 1;
  - `update` mengecek ID baris dulu supaya baris yang bergeser tidak tertimpa;
  - `upload` menimpa file bernama sama lewat Drive API, sehingga link tetap.
- **Menu Google Sheet** (admin), dengan panel *Settings*:
  - URL Web App, kode rahasia (tidak pernah dikirim balik ke browser);
  - 9 nama kolom, teks Done/Undone, format tanggal;
  - langkah pasang untuk pemilik sheet, tombol *Test connection* (menyebut kolom yang tidak ditemukan).
- **Check only** (`POST /api/gsheet/check`), tidak menulis apa pun ke sheet:
  - **Pencocokan:** ID sheet = SID lokasi; lokasi tanpa SID dicocokkan lewat nama (tanpa spasi/tanda baca). Nama kembar dipilah dengan desa + kecamatan.
  - **Ringkasan:** jumlah BAA Flow, baris sheet ber-SO project, yang cocok (by ID / by name), perubahan yang akan dikirim (Done / Undone / kosong, tanggal), PDF yang perlu diunggah.
  - **Alarm:**
    - kolom tidak ditemukan;
    - SID ≠ ID sheet (termasuk SID yang menunjuk baris lokasi lain);
    - jumlah berbeda;
    - hanya di sheet / hanya di BAA Flow;
    - nama beda (pasangan desa + kecamatan sama, tidak dicocokkan otomatis);
    - nama sama tetapi wilayah beda;
    - ID kembar di sheet;
    - beberapa baris cocok;
    - SO beda.
  - **"Take from the sheet"** (admin, `POST /api/gsheet/apply`):
    - mengisi SID kosong dari ID sheet dan SO kosong dari sheet;
    - SO baru otomatis masuk daftar project;
    - nilai yang sudah ada tidak ditimpa;
    - baris dengan wilayah beda tidak dicentang otomatis;
    - dicek ulang dengan data sheet terbaru sebelum menyimpan.
- Hasil cek terakhir (waktu, oleh siapa, jumlah alarm) disimpan; jumlah alarm tampil sebagai angka di menu.
- **Diuji** dengan tiruan Apps Script lokal + 188 lokasi dari file import KDKMP dan 5 kasus alarm sengaja. Semua kasus terdeteksi; 181 SID dan 186 SO terisi.

## Tahap 3: tulis ke sheet + PDF ke Drive + log + buat lokasi dari sheet (2026-11-09, ✅, belum di-build)
- **Tombol Update to GSheet:**
  - jalankan Check (bila hasil terakhir lebih dari 5 menit), lalu konfirmasi jumlah baris dan PDF;
  - baris tanpa PDF dikirim per 50 sekaligus; PDF per lokasi satu per satu dengan progress bar dan tombol **Stop**;
  - lokasi yang beralarm tidak disentuh.
- **Nilai yang ditulis:**
  - STATUS: Done (100%) / Undone (tanggal aktivasi terisi) / kosong;
  - TANGGAL: tanggal aktivasi, format mengikuti setting;
  - LINK: URL file Drive.
- **Keamanan baris:** Apps Script mengecek ID di baris itu sebelum menulis. Baris yang bergeser dilewati dan dilaporkan "run Check again".
- **PDF:**
  - PDF gabungan yang sama dengan tombol PDF di Entry (lampiran sebelum, scan, BAA, lampiran sesudah);
  - nama `Nama Lokasi-SID.pdf`, satu folder;
  - file bernama sama ditimpa lewat Drive API, sehingga link tetap;
  - unggah ulang hanya bila lokasi berubah sejak PDF terakhir (`gsheet_sync.pdf_at` dibanding `modified_at`), tampil sebagai "replace PDF (changed)".
- **Log update** (`gsheet_log`): waktu, oleh siapa, jumlah baris, PDF, gagal (dengan detail), alarm.
- **Create in BAA Flow:**
  - baris yang hanya ada di sheet dicentang → lokasi draf dengan nama, wilayah (dicocokkan ke data Kemendagri), SID = ID, dan SO (SO baru masuk daftar project);
  - owner = admin; tanggal aktivasi diisi operator.
- **Kolom baru di setting:** Provinsi (untuk pencocokan wilayah lokasi baru).
- **Diuji** dengan tiruan Apps Script:
  - 5 baris ditulis dan 2 PDF diunggah (masing-masing 3 halaman: scan + BAA);
  - cek ulang menghasilkan 0 perubahan;
  - setelah lokasi diedit, muncul "replace PDF";
  - status Done yang diketik manual di sheet ditimpa menjadi Undone;
  - 1 lokasi dibuat dari sheet.
- **Belum diuji dengan Google asli.** Perlu dicek saat pemasangan: parsing tanggal oleh locale sheet, Drive API (`Drive.Files.update`), dan batas waktu Apps Script (6 menit per panggilan; satu PDF per panggilan, aman).

## Revisi: nilai STATUS bisa ditambah (2026-11-09)
- "Values written" diganti **daftar aturan**: tiap baris = teks nilai + syarat. Dibaca dari atas, aturan pertama yang cocok ditulis; tidak ada yang cocok = kosong.
- **Syarat yang tersedia:**
  - dokumen 100% (tanggal aktivasi terisi);
  - kelengkapan ≥ n%;
  - scan bertanda tangan sudah di-upload;
  - ditandai Done di BAA Flow;
  - tanggal aktivasi terisi;
  - tanpa tanggal aktivasi;
  - semua lokasi.
- Tombol *Add value*, naik urutan, dan hapus. Bawaan: Done (100%) lalu Undone (tanggal aktivasi terisi). Setting lama (Done/Undone) otomatis diubah jadi aturan.
- Unggah PDF tetap hanya untuk dokumen 100%, tidak bergantung pada teks status.
- Ringkasan "Will change" menghitung per nilai.

## Revisi 2026-11-13 — Tanggal Terpasang/Integrasi & flag Done

Keputusan pengguna:
- Kolom sheet **"Tanggal Terpasang/ Integrasi"** (nama kolom bisa diatur: *Installed date (read only)*) dibaca saat **Check**, format `10-Nov-2026`. Judul kolom dicocokkan toleran spasi/huruf besar.
- **Tanpa persetujuan admin:** lokasi cocok yang belum punya tanggal aktivasi langsung diisi tanggal itu (riwayat: "Activation date … from Google Sheet"). Tanggal aktivasi yang sudah ada di BAA Flow **tidak pernah ditimpa** — tanggal BAA bisa beda dari tanggal terpasang, BAA Flow yang berlaku. Sheet kosong tidak menghapus apa pun. Nilai yang tidak terbaca → alarm.
- Tanggal terpasang = **link sudah online**. Selama dokumen belum 100%, lokasi diberi tanda **Online** (LED merah berpendar), naik ke paling atas di Location Log, pemilih lokasi Entry, dan "My drafts" operator; ada filter **Online · n** dan banner di Entry. Tanda hilang otomatis saat dokumen lengkap 100%.
- **Update to GSheet** menulis TANGGAL BAPB = tanggal aktivasi → STATUS BAPB ikut berubah menurut aturan status. Kolom Tanggal Terpasang di sheet tidak pernah ditulis. Apps Script tidak berubah (tidak perlu tempel ulang).

## Flag Done: Clean / With notes (BAA Flow saja)
- Saat **Finish BAA** (100%) operator memilih **Clean** (siap ke customer) atau **With notes** (catatan wajib; pilihan cepat per project, diatur admin dari dialog itu).
- Banner di Entry: **Mark as clean** / Edit note / Add note — operator pemilik atau admin. Reopen atau Reset BAA menghapus flag. Done lama tanpa flag = Clean.
- Sweeping: filter **Notes · n** di Location Log + chip "notes", kolom *Flag Done* & *Catatan* di Reports Excel, angka di Progress.
- Google Sheet **tidak** menerima syarat clean/notes: 100% tetap Done; PDF tetap diunggah dan diganti bila ada perubahan.

## Auto-check terjadwal (2026-11-13)
- *Settings › Project & status › Google Sheet auto-check* (admin, per project): On/Off, **jam tetap** (mis. 07:00, 13:00) atau **interval** (tiap N jam antara jam mulai–selesai), Senin–Jumat atau setiap hari. Ada *Next*, *Last* (hasil/galat) dan **Run now**.
- Hanya **Check** yang otomatis (tanggal terpasang → tanggal aktivasi, tanda Online). **Update to GSheet tetap manual.**
- Thread latar belakang memeriksa jadwal tiap menit untuk semua project aktif; jadwal yang terlewat saat server mati dijalankan sekali begitu server hidup. Pelaku tercatat "Auto-check". Jadwal baru dihitung mulai saat disimpan.
- **Lonceng** (admin & operator, tabel `notices`): pemilik lokasi diberi tahu saat lokasinya baru online dan BAA belum lengkap (klik → buka lokasi); admin diberi tahu bila auto-check gagal (sekali per jenis galat). Admin tetap melihat *Edit requests* di lonceng yang sama.
- **LED** berpendar di menu **Location Log** selama ada lokasi online yang BAA-nya belum lengkap.
