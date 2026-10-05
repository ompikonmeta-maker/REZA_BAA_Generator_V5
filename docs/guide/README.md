# Panduan pengguna (Admin & Operator)

Hasil jadi: `app/web/guide/` → `index.html`, `img/*.jpg`, `panduan.pdf`.
Di aplikasi dibuka lewat ikon **(?)** di bawah sidebar (`/guide/#admin` atau `/guide/#operator`).
Ikut terbawa di build Windows (folder `app/web` dibundel).

## Membuat ulang (setelah tampilan aplikasi berubah)
Semua skrip di folder ini, dijalankan dari satu folder kerja (mis. scratch):

1. Siapkan data demo di `REZA_BAA_HOME` terpisah (salinan data contoh), lalu `python3 mkimg.py` (foto contoh per kategori).
2. Jalankan server data demo di port 8140 dan instalasi kosong di port 8141, lalu `python3 prep.py`
   (akun operator baru, permintaan edit, project berstatus Setup).
3. `node shots.cjs fresh|admin|op|extra` → `shots/*.jpg` + `meta.json` (posisi penanda bernomor diambil otomatis dari elemen layar, tema terang).
4. `python3 build_guide.py shots meta.json <repo>/app/web/guide` → HTML + gambar.
5. `node make_pdf.cjs http://localhost:8140/guide/ <repo>/app/web/guide/panduan.pdf` → PDF A4.

Isi teks ada di `content.py` (satu teks per penanda, urutan sama dengan daftar penanda di `shots.cjs`).
