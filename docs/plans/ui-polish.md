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
