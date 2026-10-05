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
