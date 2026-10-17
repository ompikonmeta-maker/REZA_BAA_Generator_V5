# Rencana: Rapikan UI (penjaga simpan, animasi dropdown, sidebar)

Status: **Selesai diimplementasi** · 2026-10-05

## 1. Sidebar: bagian bawah selalu terlihat — selesai (3bd67b9)
- Footer sidebar (timer, lonceng, ganti password, tema, keluar) dibuat menempel di bawah.
- Bila menu panjang (mis. Settings terbuka di layar pendek), hanya menu di atasnya yang di-scroll.

## 2. Notifikasi simpan selalu muncul untuk perubahan di field mana pun
**Masalah:** di Settings › Project & status, admin mengubah field lalu pindah menu tanpa Save → dialog "perubahan belum disimpan" tidak muncul, perubahan hilang diam-diam.

**Kondisi sekarang:** penjaga (`guardLeave` / `dirtyCtx`) baru mencakup BAA Entry, Location data (Fields · Photos · Inventory), mapping Template, dan foto pending di drawer.

**Yang perlu ditambah (semua form dengan tombol Save):**
| Halaman / form | Field |
|---|---|
| Project & status / All projects (editor project) | nama, warna, target, tanggal, sakelar Wilayah, akses user |
| Setup › Target | target, tanggal |
| Team | form akun baru yang sudah diketik tapi belum di-Add |
| Users (dialog user) | semua field |
| Dialog Freeze / ganti prefix | pesan / prefix yang sudah diketik (konfirmasi sebelum ditutup) |
| Form lain dengan Save yang ditemukan saat audit | — |

**Aturan:**
- Satu mekanisme bersama: tiap form mendaftarkan "dirty" saat ada input/change, bersih lagi setelah Save berhasil atau dibuang.
- Berlaku untuk semua jalan keluar: klik menu sidebar, sub-menu Settings, tab Location data, langkah mode Setup (Back/Next), pindah project, keluar (logout), tutup/refresh tab (`beforeunload`).
- Dialog sama seperti yang sudah ada: **Save** · **Discard** · **Cancel**.
- Indikator "Unsaved / Saved" di title bar seperti di Location data, dipakai juga di form lain.
- Audit seluruh app untuk form dengan Save yang belum terjaga, lalu uji tiap form: ubah → pindah menu → dialog muncul.

## 3. Animasi dropdown seragam di semua field
**Acuan:** mesin menu MDMenu (`mdmenu.js` / `mdmenu.css`, dari template dropdown toolkit) yang sudah dipakai `MDSelect` dan menu ⋮:
- tumbuh dari anchor (origin = posisi field), fade + scale dengan easing spring, durasi ±520 ms;
- sudut panel menyesuaikan, panel menempel di field;
- tutup = collapse + fade cepat ke arah anchor;
- elevasi, ripple item, item terpilih (tertiary container), navigasi keyboard sama.

**Dropdown yang belum mengikuti acuan (dicek saat implementasi):**
- pemilih lokasi di BAA Entry (`LocationPicker`);
- popover pencarian Wilayah (`.wl-pop`);
- date picker (field tanggal & filter Date created);
- pemilih project (`.pj-pop`) di sidebar;
- `<select>` bawaan browser yang masih tersisa (±4);
- dropdown lain yang ditemukan saat audit.

**Aturan:**
- Yang berupa daftar pilihan → pakai MDMenu/MDSelect langsung.
- Yang berupa popover khusus (Wilayah, date picker, project) → tetap kontennya, tapi animasi buka/tutup, origin, durasi, easing, elevasi, dan radius disamakan dengan MDMenu (token motion bersama).
- Animasi dengan toggle class/attribute pada elemen yang sama (tidak render ulang DOM); hormati `prefers-reduced-motion`.
- Uji di tema terang & gelap, mode rail, dan layar pendek (panel membalik ke atas bila ruang di bawah kurang).

## 4. Label "Location code prefix" → "Project code" — selesai
- Label baru **Project code**; keterangan: `2–4 letters · used as prefix for location codes · first code: KDMP_00001`.
- Berlaku di semua tempat: layar Create your first project, editor project (label + teks terkunci), link `Change project code…`, dialog ganti kode ("Change project code" / "New project code"), pesan error server, checklist Setup.
- Panduan (HTML + PDF) ikut diperbarui: teks & screenshot yang memuat label lama.
- Kolom database tetap `prefix` (hanya tampilan).

## 5. Field tanggal target pakai date picker aplikasi — selesai (2026-10-06)
**Masalah:** field "Target date" masih input tanggal bawaan browser: tanpa dropdown kalender ala aplikasi, format `mm/dd/yyyy` (gaya AS), tampilan beda dengan field tanggal lain.

**Lokasi (3):**
| Tempat | Elemen |
|---|---|
| Mode Setup › Target | `#sxDate` |
| Settings › Project & status / All projects (editor project) | `#pjm-date` |
| Progress › ubah target (edit cepat tanggal) | `pgInline(..., 'date')` |

**Usul:** pakai date picker yang sama dengan *Tanggal Aktivasi* di BAA Entry dan filter *Date created* (`DP`): klik → kalender dropdown (animasi MDMenu), format tampil `31 Dec 2026`, tombol Today/Clear, tersimpan tetap `YYYY-MM-DD`. Penjaga "Unsaved" tetap jalan. Uji tema terang & gelap.

## 6. Preview Log Sheet kosong di project baru — selesai (2026-10-06)
**Masalah:** Template BAA › Log Sheet › *Preview* menampilkan "No locations yet to preview". Preview & **Test .xlsx** butuh minimal 1 lokasi (`_trial_build` di `app/routers/templates.py` menolak bila belum ada lokasi). Di mode Setup project baru selalu belum ada lokasi → admin tidak bisa mengecek hasil mapping sebelum project aktif.

**Usul:** bila belum ada lokasi, preview & Test .xlsx memakai **2 lokasi contoh** yang dibuat dari pengaturan project (tidak disimpan):
- kode `KODE_00001`, `KODE_00002` sesuai Project code;
- field lokasi diisi contoh (mis. *Nama Lokasi* → "Contoh Lokasi 1", tanggal hari ini, teknisi/PIC contoh);
- wilayah contoh (bila Wilayah aktif), inventory bawaan dengan SN contoh, status foto per kategori;
- label jelas di atas preview: **"Sample data — no locations yet"**.
Setelah ada lokasi nyata, preview kembali memakai 2 lokasi terbaru.

## 7. Lokasi baru sudah 3% padahal belum diisi — diabaikan (2026-10-06)
**Penyebab (bukan disengaja):** baris inventory bawaan sudah terisi otomatis *Qty = 1* dan *Notes = OK*. Rumus kelengkapan menganggap baris yang punya isi apa pun sebagai "inventory mulai diisi" → dapat nilai setengah (0,5 dari 18 bagian: 4 field + wilayah + inventory + 11 foto + scan) = 2,8% → dibulatkan **3%**. Server memakai rumus yang sama, jadi Location Log/Progress juga 3% setelah auto-save.

**Usul:** isian bawaan (nama item bawaan, Qty 1, Notes OK) tidak dihitung. Inventory baru dapat nilai setengah setelah operator mengisi **Brand/Type** atau **SN**; penuh bila semua kolom lengkap. Lokasi baru = **0%**. Berlaku di BAA Entry, Location Log, panel detail, Progress/Dashboard (server).

## 8. Template BAA: Detail Sheet "nyangkut" & blur saat pindah langkah cepat — selesai (2026-10-06)
**Cara memicu:** di Template BAA klik cepat Detail Sheet → Log Sheet → Template (sebelum animasi ±0,5 dtk selesai).
**Penyebab:** `mapGo()` menjadwalkan "bersih-bersih" panel lama (sembunyikan + hapus efek keluar) dengan satu timer. Klik berikutnya membatalkan timer itu (`clearTimeout`) dan hanya membersihkan panel terakhir, sehingga panel Detail Sheet tertinggal dalam keadaan animasi keluar (transparan/blur, tidak bisa diklik) di atas panel aktif.
**Usul:** setiap pindah langkah, panel selain tujuan langsung dibereskan (panel yang sedang keluar tetap animasi, sisanya disembunyikan), dan timer membersihkan **semua** panel selain langkah aktif. Uji: klik cepat bolak-balik 1↔2↔3 berkali-kali → tidak ada panel tertinggal; animasi normal tetap sama.

**Catatan implementasi (5, 6, 8):**
- 5: `dateBox()` + `dpOpenBox()` dipakai di Setup › Target dan editor project; edit cepat tanggal di Progress membuka kalender yang sama. Penjaga "Unsaved" tetap jalan. Ikut diperbaiki: toast yang tersembunyi tidak lagi menghalangi klik di bawah layar.
- 6: tanpa lokasi, preview & Test .xlsx memakai 2 lokasi contoh (`_sample_locations`), label "Sample data — no locations yet", file uji `Test_BAA_sample.xlsx`. Foto contoh = placeholder sementara, langsung dihapus.
- 8: `mapGo()` membereskan semua panel selain tujuan; uji klik cepat 1↔2↔3 berulang → tidak ada panel tertinggal.
- 6 (lanjutan): preview terasa lambat → preview kini hanya membangun sheet LOG (`build_workbook(log_only=True)`) dan memakai satu gambar contoh untuk semua kategori. Waktu server: data contoh ±1,1 dtk → ±0,1 dtk; data nyata ±0,65 dtk → ±0,05 dtk. Isi LOG identik; Test .xlsx tetap lengkap (LOG + Detail).

## 9. Lebar & posisi kartu di Settings seragam — selesai (2026-10-06)
**Temuan (ukur 1366 & 1920 px):** lebar kartu ada 4 macam (880 · 990–1200 · lebar penuh · 2 kolom); Location data, Users, Backup ditengahkan (maks 1200) sementara halaman lain rata kiri → di layar lebar kartu "meloncat" saat pindah menu; jarak atas 196 / 202 / 254 px; hanya Template BAA yang punya judul besar sendiri.

**Keputusan:**
| Aturan | Nilai |
|---|---|
| Posisi | **Rata kiri**, sejajar judul di bar atas — tidak ada yang ditengahkan |
| Lebar maksimal | **1200 px** untuk semua halaman Settings (Project & status, Team, All projects, Template BAA, Location data, Users, Backup) |
| Halaman 2 kolom | All projects & Template BAA dibagi di dalam lebar 1200 px yang sama |
| Judul | Judul besar "BAA Template / Manage Excel templates…" di Template **dihapus**; cukup judul di bar atas |
| Jarak atas | Disamakan untuk semua halaman (banner Frozen / tab Location data tetap di atas kartu) |

Uji: 1366, 1600, 1920 px; tema terang & gelap; mode Setup (Location data, Template, Team, Target) ikut aturan yang sama.

**Hasil (9):** semua halaman Settings & mode Setup rata kiri di x=338 px (sejajar judul) dengan lebar maks 1200 px (diukur di 1366/1600/1920). Jarak atas kini sama (201 px; Location data 253 px karena baris tab). Penyebab selisih 6 px: bar atas lebih tinggi saat chip project tampil → bar atas diberi tinggi tetap. Banner Frozen di halaman Settings ikut 1200 px. Judul besar Template dihapus; status "All changes saved / Unsaved changes" pindah ke kolom Steps di atas tombol Save mapping.

## 10. Sub menu awal Settings — selesai (2026-10-06)
Klik **Settings** pertama kali (setelah login/refresh) membuka item teratas **Project & status** (sebelumnya Location data). Setelah itu tetap membuka sub menu terakhir yang dipakai.

## 11. Template BAA › Detail Sheet & Log Sheet: render mengikuti lebar window — selesai (2026-10-12)
**Permintaan:** render template lebih besar dengan memanfaatkan **lebar** window (tinggi tidak diubah).
**Sekarang:** semua halaman Settings dibatasi lebar **1200 px** (aturan no. 9), jadi di layar lebar sisi kanan kosong. Tinggi area render `min(72vh, 780px)`. Preview Log Sheet diperkecil agar muat (skala 75–100%).
**Keputusan:**
| Langkah | Yang melebar mengikuti window | Yang tetap |
|---|---|---|
| **Detail Sheet** | Kartu Detail Sheet (area render sel) memakai lebar penuh area kerja | Tinggi area render tetap |
| **Log Sheet** | **Hanya bagian Preview** (render sheet LOG) | Tabel mapping "template header → field" tetap selebar sekarang; tinggi tetap |
| Template & Worksheet, halaman Settings lain | — | Tetap maks 1200 px (aturan no. 9) |

**Catatan:**
- Tetap rata kiri, jarak tepi kanan sama dengan halaman lain.
- Preview Log Sheet makin jarang diperkecil/menggulung ke samping di layar lebar (skala maks tetap 100%).
- Perpindahan antar langkah: lebar berubah halus, sorotan sel (highlight) ikut posisi baru; klik cepat antar langkah (no. 8) tetap aman.

**Uji:** 1366, 1600, 1920 px; tema terang & gelap; mode Setup › Template.

## 12. Tombol Save: status Unsaved/Saved & tombol ganda — selesai, A (2026-10-12)
**Laporan (video):** Setup › Target — klik **Save target** di kartu: data tersimpan, tetapi status di bar atas tetap **Unsaved** (tombol merah) sampai user mengklik lagi di halaman (klik kedua = simpan kedua).
**Penyebab:** status bar atas dihitung ulang hanya saat ada klik/ketik di halaman. Tombol Save di kartu menyimpan lalu tidak menghitung ulang status. Tombol Save di bar atas sudah benar (menghitung ulang setelah simpan).

**Hasil cek semua tombol Save (uji di browser, data salinan):**
| Halaman | Tombol | Hasil |
|---|---|---|
| Setup › Target | kartu "Save target" + bar "Save target" | ❌ Save di kartu: status tetap Unsaved |
| Progress › edit target cepat (✓) | ✓ inline + bar "Save target" | ❌ setelah ✓, bar tetap "Unsaved / Save target" walau isian sudah tertutup; klik bar = simpan nilai lama lagi |
| Location data › Fields / Inventory / Photo categories | hanya bar (tombol kartu sudah disembunyikan) | ✅ normal · ⚠️ bila simpan **gagal**, status tetap jadi **Saved** |
| Team (Setup & Settings) | kartu "Add" + bar "Add account" | ✅ status benar · bar berlabel "Add account / Unsaved" terasa janggal (ini aksi buat akun, bukan simpan form) |
| Settings › Project & status | kartu "Save project" + bar "Save project" | ✅ status benar |
| BAA Entry | Finish BAA + simpan otomatis | ✅ tidak memakai bar (sudah diperbaiki di sesi duplikat request) |

**Apakah tombol ganda perlu?** Tidak. Location data sudah memakai satu tombol (di bar atas); halaman lain belum seragam.
**Keputusan (2026-10-12): A** — satu tombol per form di bar atas; pengecualian Team & Progress ✓ seperti di bawah.
**Usul:**
- A. **Satu tombol per form, di bar atas** (seperti Location data): sembunyikan Save di kartu Target & Project & status. Bar atas selalu terlihat + status Unsaved/Saved.
- B. **Satu tombol per form, di kartu**: bar atas hanya status (tanpa tombol).
- Pengecualian yang diusulkan: Team "Add" tetap di kartu (aksi), bar tidak menampilkan "Add account"; Progress ✓ tetap inline, bar tidak muncul untuk edit cepat. Penjaga "perubahan belum disimpan" saat pindah halaman tetap jalan.
- Semua jalur simpan: status dihitung ulang **setelah** server menjawab; bila gagal tetap **Unsaved** + pesan gagal.

## 13. Isian angka: tombol panah atas/bawah tidak senada tema — selesai (2026-10-12)
**Laporan (gambar):** Setup › Target, isian **Target (BAA)** menampilkan tombol panah atas/bawah bawaan browser (kotak putih abu-abu) yang tidak senada dengan tema gelap/terang.
**Penyebab:** isian bertipe angka (`type=number`) memakai spinner bawaan browser (Chromium/Edge), tidak ikut warna tema.
**Isian angka lain yang sama:** Settings › Project & status (Target BAA), Progress (edit target cepat; batas umur draf Fresh/Warm), Template BAA (Header row, Data starts, Inventory row, max, Photo size).
**Usul:** sembunyikan spinner bawaan di **semua** isian angka (tetap bisa ketik angka, panah ↑/↓ keyboard & scroll tetap bekerja seperti biasa); keyboard angka di layar sentuh tetap muncul. Bila perlu tombol +/−, pakai tombol kecil yang mengikuti warna tema — **default: tanpa tombol** (lebih bersih, angka target biasanya diketik).
**Uji:** tema terang & gelap; ketik, panah keyboard, nilai minimum tetap dijaga.

**Hasil (11–13):**
- 11: di langkah Log Sheet & Detail Sheet halaman Template melepas batas 1200 px (transisi halus). Diukur di 1920 px: halaman 1544 px; Log Sheet — tabel mapping tetap 930 px, Preview 1232 px (tampil 100%); Detail Sheet — area render ikut melebar. Langkah Template & halaman Settings lain tetap 1200 px. Di 1366 px tidak berubah (window sudah jadi batas). Klik cepat antar langkah tetap aman.
- 12: Save di kartu Target & editor project disembunyikan → simpan lewat bar atas (label "Create project" untuk project baru). Status dihitung ulang setelah server menjawab: berhasil = Saved, gagal = tetap Unsaved. Location data: Saved hanya bila server berhasil; dialog "Unsaved changes" › Save menunggu server (gagal = tetap di halaman). Team: bar tidak muncul, tombol Add tetap di kartu, penjaga pindah halaman tetap jalan. Progress: edit cepat tanpa bar, ✓ menyimpan & membersihkan penjaga.
- 13: spinner bawaan disembunyikan di semua isian angka (komponen md-text-field & input biasa); ketik & panah keyboard tetap jalan.

## 14. Peta wilayah: pin per provinsi dengan angka — selesai, warna B (2026-10-16)
**Permintaan:** peta lebih informatif dengan **pin per provinsi** dan angka di ujung pin.
**Mockup (peta asli, data demo):** pin jatuh di titik dalam wilayah (bukan sekadar tengah kotak), kepala pin berisi angka sesuai mode: **% Done** → persen selesai, **Drafts** → jumlah draf, **Stale** → jumlah draf basi (provinsi bernilai 0 tidak diberi pin di mode Drafts/Stale). Saat zoom ke provinsi, pin per kab/kota. Ukuran pin tetap di layar (tidak ikut membesar saat zoom). Tooltip & klik tetap seperti sekarang.
**Perlu diputuskan:**
- Warna pin: (A) warna mode (seperti mockup), atau (B) status terhadap target hari ini — hijau on-track / kuning tertinggal / merah jauh tertinggal (sama dengan bar "Furthest behind").
- Pin berdekatan (mis. Jawa/Kota & Kab. Bandung) saling menimpa → usul: label digeser ke atas otomatis dengan garis penunjuk, ujung pin tetap di lokasi.

## 15. PDF: foto & capture buram — selesai (2026-10-16)
**Laporan:** tulisan pada capture di PDF (tombol PDF) buram/tidak terbaca; Excel terlihat baik.
**Penyebab (dibuktikan):** setiap foto disisipkan ke workbook sebagai gambar **600×450 px** (setelan "Photo size"), apa pun resolusi aslinya — capture HP tegak bahkan hanya ±200 px lebarnya. Di Excel zoom 100% gambar tampil 1:1 sehingga terlihat tajam; di PDF halaman diperbesar oleh viewer → piksel terlihat → buram. PDF dibuat dari workbook yang sama (Excel/LibreOffice).
**Usul:**
- Ukuran **tampil** di sel tetap (layout template tidak berubah), tetapi gambar yang disisipkan memakai resolusi **hingga 3×** (maks 1800×1350 px; tidak diperbesar melebihi foto asli).
- Capture/screenshot (PNG) tetap PNG agar tulisan tajam; foto kamera JPEG kualitas tinggi (≈92) agar ukuran file wajar.
- Ekspor PDF via Excel: kualitas "Standard" (bukan "Minimum size") ditetapkan eksplisit dan kompresi gambar otomatis workbook dimatikan.
- Dampak: file Excel/PDF lebih besar (perkiraan ±2–4× dari sekarang per lokasi). Uji: bandingkan resolusi gambar di dalam PDF sebelum/sesudah; konversi Excel (Windows) diuji di build.

## 16. Nama file download Excel & PDF mengikuti nama lokasi — selesai, A (2026-10-16)
**Sekarang:** `LOK_00003_20261016_170354.xlsx` (kode + jam). PDF di ZIP sudah `LOK_00003 Natlan.pdf`.
**Usul (pilih):** (A) `Natlan - LOK_00003.xlsx` (nama dulu, kode menjamin unik), (B) `LOK_00003 Natlan.xlsx` (sama dengan isi ZIP). Karakter terlarang di nama file dibersihkan; nama kosong → kode saja. Berlaku untuk tombol Excel & PDF (per lokasi) dan saran nama di dialog "Save as". Ekspor banyak lokasi tetap `Log_BAA_…` / ZIP.

**Hasil (14–16):**
- 14: pin per provinsi (nasional) / kab-kota (saat zoom), angka sesuai mode, **warna = status terhadap target hari ini** (on track / behind / far behind, sama dengan bar "Furthest behind"; tanpa target = warna utama). Label bertumpuk dinaikkan otomatis dengan garis penunjuk; pin disembunyikan selama animasi zoom lalu muncul lagi; ikut menyesuaikan saat ukuran window berubah. Hover/klik label = hover/klik wilayahnya. Legenda "Pin: on track · behind · far behind".
- 15: foto disisipkan hingga 3× ukuran tampil (mis. 1800×1350 px, sebelumnya 600×450; capture HP tegak ±620 px lebar, sebelumnya ±200), PNG tetap PNG, foto JPEG q92; workbook `autoCompressPictures="0"`; ekspor via Excel dengan kualitas Standard. Ukuran tampil di template tidak berubah. Contoh 2 foto: Excel 260 KB → 1,5 MB. Konversi PDF via Excel (Windows) diverifikasi lewat build (LibreOffice di lingkungan uji tidak berfungsi).
- 16: unduhan per lokasi bernama `Nama Lokasi - KODE.xlsx` / `.pdf` (karakter terlarang dibersihkan, nama kosong → kode); saran nama di dialog Save as sama; nama berspasi/non-ASCII terbaca benar oleh aplikasi.

## 17. Peta: pin terlalu ramai — opsi desain (mockup, 2026-10-17)
**Masalah:** dengan 25 provinsi, pin di semua provinsi membuat peta ramai.
**Mockup interaktif:** https://claude.ai/artifact/7Ay7hRj3X73iZawMVZFM19 (batas wilayah asli, data contoh 25 provinsi)
| Opsi | Ide |
|---|---|
| ★ Rekomendasi | B + A + D: sapaan awal ±3 dtk → jadi titik; hover = sorot + pin; klik = zoom ke kab/kota |
| A Sorot saat hover | Tanpa pin; hover meredupkan provinsi lain dan memunculkan satu pin + nama |
| B Sapa lalu titik | Pin jatuh berurutan barat → timur, tampil ±3 dtk, lalu mengecil jadi titik status |
| C Fokus perhatian | Pin angka hanya 4 paling tertinggal + 1 terbaik; sisanya titik; tombol "Semua angka" |
| D Klik untuk zoom | Nasional hanya warna + titik; klik → zoom halus + pin per kab/kota |
| E Label di tepi | Angka berjajar di atas & bawah peta, garis tipis ke provinsinya |
| F Gelembung | Lingkaran sebesar jumlah lokasi, warna status, angka di gelembung besar |
**Pilihan (2026-10-17):** sisakan ★ Gabungan, Rekomendasi, Fokus perhatian (opsi lain dihapus dari mockup). **★ Gabungan** = Rekomendasi + Fokus perhatian:
1. Pin jatuh barat → timur, **2× lebih cepat** (jeda 40 ms/pin, animasi 0,28 dtk), angka terlihat ±3 dtk.
2. Pin mengecil jadi titik warna status.
3. Lalu pin angka muncul hanya untuk **4 provinsi paling tertinggal**.
4. Provinsi lain titik warna; hover provinsi **dan kab/kota** → wilayah lain meredup, pin berwarna status (bukan tooltip gelap) terbuka dengan detail lengkap: angka mode, nama, selesai/total · %, draf · basi; label dekat tepi otomatis bergeser / pindah ke bawah. Ganti mode tidak memutar ulang animasi awal.
5. Tombol **Semua angka** ↔ **Hanya 4 tertinggal**; **Putar ulang**.
6. Klik → zoom ke provinsi, pin per kab/kota lengkap dengan nama dan selesai/total; "← Indonesia" kembali ke tampilan 4 tertinggal.
**Final (2026-10-17):** hanya ★ Gabungan yang dipertahankan (Rekomendasi & Fokus perhatian dihapus dari mockup).

**Perbaikan label kab/kota terpotong & bertumpuk saat zoom** (contoh NTT):
- Ukuran label diukur langsung (bukan ditebak dari jumlah huruf).
- Tiap label mencoba posisi di sekitar titik: atas, diagonal atas, samping, bawah, diagonal bawah, dengan garis penunjuk makin panjang (12–116 px). Diterima bila utuh di dalam peta, tidak menabrak label lain, titik lain, garis penunjuk lain, maupun tombol "← Indonesia".
- Prioritas: paling tertinggal ditempatkan dulu. Gagal → garis boleh lewat di belakang label lain → label ringkas (angka saja) → titik (hover untuk detail).
- Label selalu di atas garis penunjuk; detail hover juga dicarikan posisi yang utuh di dalam peta.
- Kab/kota tanpa geometri (mis. Kepulauan Seribu di data contoh) tidak diberi pin.
- **Detail hover tidak menutupi wilayah yang di-hover**: bentuk asli wilayah (+4 px) dirender ke kanvas tersembunyi, tiap kandidat posisi dicek berapa piksel wilayah yang tertutup; dipilih posisi terdekat yang 0 piksel (jarak garis penunjuk sampai 400 px), kalau tak ada ambil yang paling sedikit menutup. Diuji di 25 provinsi + semua kab/kota, lebar 1400 & 900: 0 tertutup, hover terlama 22 ms.
- **Hover wilayah** (provinsi & kab/kota): pin dan angka wilayah lain memudar (0,25 dtk, tidak menangkap kursor), muncul lagi saat kursor lepas; hanya pin wilayah yang di-hover yang tampil.
- Diuji Playwright di 25 provinsi, lebar 1400 & 900: 0 label keluar peta, 0 tumpang tindih, 0 jatuh ke titik; detail hover tiap kab/kota utuh di dalam peta.

- **Legenda per pill** (% Done / Drafts / Stale): tiap pill diberi titik warna modenya; baris legenda pertama berganti mengikuti pill aktif: "Wilayah · % selesai 0% → 100%", "Wilayah · jumlah draf 0 → maks draf", "Wilayah · jumlah basi 0 → maks basi" (maks dihitung per level nasional / kab-kota) + "tanpa lokasi". Baris kedua: "Pin · status % Done" (warna pin tetap status target di semua mode).
- Warna Stale diganti dari merah (error) ke magenta (`--stale`) supaya tidak tertukar dengan pin "jauh tertinggal"; Drafts tetap biru-ungu (`--drafts`). Di aplikasi nanti: Drafts = tertiary, Stale perlu token baru (bukan error).

**Dipasang di aplikasi (2026-10-17, "gas")** — `app/web/index.html`, menggantikan pin lama (item 14):
- Sapaan pin hanya saat halaman Progress dibuka (bukan refresh 60 dtk); refresh tanpa perubahan data tidak menggambar ulang peta (hover tidak terputus).
- Tooltip gelap lama dihapus; hover = detail di pin (+ baris "Click to open kab/kota →" / "Click for kecamatan →"). Wilayah tanpa pin (mis. 0 draf di mode Drafts) tetap dapat detail lewat pin sementara.
- Tanpa target (ideal_pct kosong): "4 paling tertinggal" = 4 % Done terendah di bawah 100%.
- Tombol "All numbers" ↔ "Only 4 behind" dan "Replay" di baris legenda (hanya level nasional). Resize di tengah sapaan langsung ke tampilan akhir.
- Warna Stale: token baru `--wm-stale` (terang #a3459a / gelap #ec9fe0); Drafts tetap tertiary.
- Class animasi `wm-drop` (bukan `drop`, yang bentrok dengan gaya kotak upload).
- Diuji Playwright (data demo, terang & gelap): sapaan 8 → 4 pin + 4 titik; hover 8 provinsi & semua kab/kota: 0 piksel wilayah tertutup, detail utuh di peta, pin lain memudar dan kembali; zoom ke tiap provinsi: 0 label keluar/tumpang tindih; ganti mode, All numbers, Replay, klik baris Furthest behind, klik kab → kecamatan: OK; tanpa error JS.

## 18. Nama lokasi panjang — area yang terlalu sempit (catatan, 2026-10-17)
**Permintaan:** dropdown pilih lokasi (BAA Entry) terlalu sempit untuk nama panjang; cek bagian lain yang juga butuh area lebih lebar.

**Cara cek (tanpa asumsi):** aplikasi dijalankan dengan salinan data demo, 12 lokasi diberi nama panjang (19–102 huruf, mis. "SMK NEGERI 1 KALUMPANG BIDANG KEAHLIAN TEKNOLOGI DAN REKAYASA KABUPATEN MAMUJU PROVINSI SULAWESI BARAT"; aplikasi tidak membatasi panjang nama). Playwright memindai semua halaman di lebar 1366 & 1920 dan mencatat teks yang terpotong (lebar isi > lebar kotak).

| # | Bagian | Temuan (diukur) |
|---|---|---|
| a | **Dropdown lokasi — panel daftar** | Lebar panel = lebar tombol, minimal 300 px (sama di 1366 & 1920). Kolom nama hanya **111–124 px**; nama 19 huruf (229 px) pun terpotong. Kode + badge status memakan sisa lebar. |
| b | **Dropdown lokasi — tombol** | Lebar 280 px (kosong) s/d maks 460 px; nama tampil **322 px**. |
| c | **BAA Summary** (kartu kanan, nama lokasi) | Nama dipotong di **240 px**, satu baris. |
| d | **Progress › "Almost there, gone quiet"** | Kolom nama **144 px** di 1366 → semua 8 nama terpotong, termasuk nama demo pendek ("Kopdes Karya 2…"); 375 px di 1920. |
| e | **Dashboard › Team › "Last change"** | Kolom dibatasi **300 px** (337 px di 1920); nama panjang terpotong dan **kode lokasi ikut hilang** (kode ditulis setelah nama). |
| f | BAA Entry › strip SN foto ("SN not read yet — Read SN") | 96–103 px, butuh 166 px (bukan nama lokasi, tapi area sempit). |
| — | Location Log, Portfolio, kolom input "Nama Lokasi" | Tidak terpotong (tabel Log membungkus nama penuh). |

**Usulan (menunggu keputusan):**
- a. Panel daftar lebarnya sendiri (mis. ±560 px, dibatasi lebar layar), tidak ikut tombol. Tiap baris 2 tingkat: nama penuh (boleh 2 baris) di atas, kode + status di bawah; hasil pencarian disorot.
- b. Tombol melebar mengikuti ruang kosong di bar atas (batas atas lebih besar dari 460 px); nama penuh di tooltip.
- c. Nama di BAA Summary boleh 2 baris (sisanya "…"), nama penuh di tooltip.
- d. Nama dipindah ke baris sendiri di atas bar (selebar kartu), atau kartu dilebarkan.
- e. Kode ditulis lebih dulu (selalu terlihat), nama menyusul dengan "…"; kolom boleh melebar.
- f. Teks strip SN dipendekkan atau strip boleh 2 baris.

**Belum diketahui:** nama terpanjang di data asli pengguna (contoh di gambar: "SMPN 9 KALUM…").

**Mockup dropdown (a+b):** https://claude.ai/artifact/YLReJjpxKZxFFVJ8ag4bx3 — Sekarang vs **A** (panel 560 px sendiri, nama 2 baris, kode + status di baris kedua, teks cocok disorot, tombol melebar s/d 640 px mengisi bar) vs **B** (panel 640 px satu baris, nama ±440 px, disorot). Pencarian tetap kode/nama seperti sekarang (data picker hanya kode, nama, status). **Dipilih: A** (2026-10-17). Menunggu "gas"; bagian c–f belum diputuskan.

## 19. Transfer lokasi antar user — cek & verifikasi (catatan, 2026-10-17)
**Laporan:** transfer antar user masih belum jalan.

**Cara cek:** aplikasi dijalankan dengan salinan data demo; Playwright (UI) + panggilan API sebagai admin, Sari, Budi.

| Jalur | Hasil | Bukti |
|---|---|---|
| **Location Log › ⋮ › "Transfer to…"** (admin, per lokasi) | ❌ **Tidak jalan.** Klik "Transfer to…" → daftar user tidak pernah muncul, tanpa pesan. | `MDMenu.open` dipanggil dengan 7 target (Administrator, Sari · owner, Budi, Rina, Andi, Dewi Lestari, Tes Intro), tapi 300 ms kemudian 0 panel menu. |
| **Dashboard › saran "Move them to Budi" › Transfer…** | ❌ **Alur tidak ada.** Tombol membuka Location Log + pesan "Filter by owner, select the drafts, then Transfer", tetapi: filter yang ada hanya *Created by* (bukan pemilik), dan bar pilihan massal hanya punya *Set wilayah* — tidak ada tombol Transfer massal. | Bar massal: "1 selected · Set wilayah"; filter: search, Created by, Wilayah, Date created. |
| Backend `POST /api/locations/transfer` | ✅ Benar. Pemilik berganti; pemilik lama `can_edit=false` dan simpan ditolak 403 "Not your location"; pemilik baru bisa simpan (200). Ke viewer → 400, ke user di luar project → 404, operator memanggil → 403. | Uji API LOK_00077 Sari → Budi. |
| **Request edit** (operator) → **Approve** (admin, Notifications) | ✅ Jalan. Pemilik berganti ke peminta, peminta langsung bisa edit di BAA Entry. | LOK_00077 Budi → Sari lewat UI. |

**Akar masalah jalur 1:** `transferMenu()` membuka menu kedua dari dalam item menu pertama. Di `assets/mdmenu.js`, setelah `onSelect` item dijalankan, `closeAll()` dipanggil → menu kedua yang baru dibuka ikut tertutup. Selain itu `openRoot` menganggap tombol pembuka yang sama sebagai "toggle off". Regresi sejak menu diseragamkan ke MDMenu.
**Ikut kena pola yang sama:** foto tanpa kategori › ⋮ › **"Move category"** (`uncatMenu` → `reassignMenu`) — diuji: menu kedua 0 panel.

**Temuan terkait:**
- Location Log hanya menampilkan kolom *Created by*; pemilik (owner) tidak terlihat di tabel, jadi hasil transfer tidak tampak (contoh: LOK_00077 creator Sari, owner Budi). Pemilik hanya terlihat di drawer.

**Usulan perbaikan (menunggu keputusan):**
1. Menu kedua dibuka setelah menu pertama selesai menutup (atau `MDMenu` mendukung submenu), berlaku untuk "Transfer to…" dan "Move category".
2. Transfer massal: tombol **Transfer…** di bar pilihan massal Location Log + filter **Owner** (pakai endpoint yang sudah ada, `ids` bisa banyak); tombol saran Dashboard langsung memfilter pemilik draf Cold tersebut.
3. Kolom **Owner** di Location Log (atau tampil di bawah Created by bila berbeda).

## Ringkasan: belum dijalankan (2026-10-17)
| # | Catatan | Status |
|---|---|---|
| 18a–b | Dropdown pilih lokasi untuk nama panjang | **Dipilih A**, menunggu "gas" |
| 18c | BAA Summary: nama 2 baris + tooltip | menunggu keputusan |
| 18d | Progress "Almost there, gone quiet": nama terpotong (144 px) | menunggu keputusan |
| 18e | Dashboard Team "Last change": kode lokasi hilang | menunggu keputusan |
| 18f | Strip SN foto terlalu sempit | menunggu keputusan |
| 19-1 | Perbaiki menu kedua yang langsung tertutup ("Transfer to…", "Move category") | menunggu keputusan |
| 19-2 | Transfer massal + filter Owner + tombol saran Dashboard | menunggu keputusan |
| 19-3 | Kolom Owner di Location Log | menunggu keputusan |
| — | Build Windows: perubahan sejak build #24 (foto tajam & nama file download, peta Gabungan) belum di-build; ketajaman PDF perlu dicek dari build | menunggu "build" |
| — | Request ganda `dash/today` di Dashboard admin (pra-ada) | ditawarkan, belum dijawab |
