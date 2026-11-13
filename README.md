# BAA.flow — Generator Berita Acara Aktivasi

Aplikasi web untuk mengelola **BAA (Berita Acara Aktivasi)** per lokasi: input data lapangan oleh operator,
pemantauan progres oleh admin dan atasan, lalu keluaran dokumen Excel/PDF dari template klien.
Satu server melayani banyak user lewat browser (LAN atau internet).

- **Backend:** Python · FastAPI + Uvicorn · SQLite (satu file database per project)
- **Frontend:** satu file `app/web/index.html` (vanilla JS, gaya Material Design 3), tanpa build step
- **Distribusi saat ini:** Windows `.exe` portabel (PyInstaller) yang dibuild lewat GitHub Actions

---

## Fitur utama

| Area | Isi |
|---|---|
| **Multi-project** | Tiap project punya database, template, field, kategori foto, daftar SO, dan tim sendiri. Project baru bisa menyalin pengaturan dari project lain. |
| **BAA Entry** | Form lokasi (field bisa diatur), tanggal aktivasi (wajib sebelum simpan), SID, SO, wilayah Kemendagri, inventory, foto per kategori, scan BAA bertanda tangan, lampiran PDF. **Autosave**, dan data hanya tersimpan setelah tanggal aktivasi terisi. |
| **OCR SN** | Baca serial number dari foto label: barcode (zxing-cpp) lebih diutamakan, lalu Tesseract multi-pass. Aturan SN per kategori (awalan, panjang, karakter). Ada pilihan potong area (ROI). |
| **Location Log** | Daftar lokasi + filter (pembuat, pemilik, wilayah, SO, tanggal, status), aksi massal (set wilayah, transfer, **Reset BAA**), dan sampah (soft-delete, restore, purge). |
| **Import lokasi** | Template Excel → preview (dry-run + validasi) → commit. Mendukung kolom SO, SID, wilayah, dan pemilik. |
| **Export** | Excel dari template klien (placeholder/mapping) dan PDF gabungan per lokasi (scan + BAA + foto + lampiran). Konversi template→PDF memakai Excel (Windows) atau LibreOffice, dengan fallback reportlab. |
| **Progress & Dashboard** | Peta Indonesia per provinsi/kab-kota (% Done, NIS, Drafts, Stale), target dan pace, road-to-target, pipeline, ritme kerja tim, dan dashboard pribadi operator. |
| **Reports** | Laporan progres siap kirim (PDF) dan Excel untuk diolah, bisa difilter per SO. |
| **Google Sheet sync** | Tulis STATUS/TANGGAL/LINK BAPB ke Google Sheet lewat Apps Script Web App milik pemilik sheet. Mencocokkan ID/nama, memberi alarm perbedaan, dan mengunggah PDF ke folder Drive (file ditimpa, link tetap). Aturan status bisa diatur berurutan. |
| **Reset BAA** | Mengosongkan isian lokasi (identitas tetap). Satu lokasi: admin atau operator pemilik selama belum Done. Bulk: admin. Permanen, dengan kotak konfirmasi. |
| **Backup** | Unduh/restore ZIP (database + foto + template) dan kompres foto lama. |
| **Panduan** | Panduan pengguna HTML/PDF di `app/web/guide/` (ikon **?** di sidebar), plus intro interaktif untuk user baru. |

## Peran user

| Role | Akses |
|---|---|
| **Admin** | Semua: project, user, template, pengaturan, import, Google Sheet, bulk action, sampah, backup. |
| **Operator** | Dashboard pribadi, BAA Entry, Location Log. Mengedit lokasi miliknya sendiri; untuk lokasi orang lain bisa *request edit*. |
| **Viewer** (mode atasan) | Progress (halaman pembuka), Reports, Location Log (hanya lihat). Tidak ada BAA Entry. |

Login awal: `admin` / `admin`, dan password wajib diganti saat login pertama.

---

## Menjalankan

### Dari source (dev / server)

```bash
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python run.py                                      # http://localhost:8000
```

Bisa juga langsung lewat uvicorn:

```bash
REZA_BAA_HOME=/path/data-root python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Dependensi sistem yang opsional:
- **Tesseract OCR**, untuk baca SN dari teks (barcode tetap jalan tanpa Tesseract).
  - Windows: dibundel di folder `tesseract/`.
  - Linux: `apt install tesseract-ocr`.
- **Microsoft Excel** (Windows) atau **LibreOffice** (`soffice`), untuk PDF dari template Excel yang persis sama dengan aslinya.

### Windows `.exe`

Build lewat GitHub Actions (`.github/workflows/build-windows.yml`, dijalankan manual lewat tombol *Run workflow*, atau otomatis saat push tag `v*`).
Hasilnya terbit di GitHub Release dengan tag `build-<nama-branch>`:

- `BAA_Generator.exe` — portabel. Data disimpan di folder `data\` di samping exe. File sementara PyInstaller ada di `%LOCALAPPDATA%\BAA_Generator`.
- `BAA_Generator-windows.zip` — exe + Tesseract + `Template_BAA.xlsx` + `CARA_PAKAI.txt`.

### Variabel lingkungan

| Variabel | Default | Fungsi |
|---|---|---|
| `REZA_BAA_HOME` | folder exe / root repo | Lokasi folder induk `data/` |
| `REZA_BAA_HOST` | `0.0.0.0` | Alamat bind server |
| `REZA_BAA_PORT` | `8000` | Port |
| `REZA_BAA_SESSION_TTL` | `12` | Masa berlaku login (jam) |
| `REZA_BAA_MAX_IMAGE_MB` | `25` | Batas ukuran foto upload |
| `REZA_BAA_NO_BROWSER` | — | `1` = jangan buka browser otomatis |

---

## Struktur folder

```
run.py                  entry point (uvicorn + buka browser)
rezabaa.spec            konfigurasi PyInstaller (onefile)
requirements.txt
app/
  main.py               FastAPI app, registrasi router, preload wilayah
  config.py             path & env
  db.py                 skema + migrasi SQLite, helper (SO, SID, aktivasi, path file)
  auth.py, deps.py      sesi login, role guard, audit
  routers/              API per area: locations, photos, scan, attachments, import_loc,
                        export, reports, progress, stats, projects, users, settings,
                        templates, wilayah, ocr, gsheet, notifications, backup, auth
  services/             ocr, excel, pdf/pdfdoc/report_pdf, xlsx2pdf, imgstore, autosort, wilayah
  data/                 wilayah.tsv.gz (Kemendagri), peta.json (geoBoundaries), gsheet_apps_script.gs
  web/                  index.html (seluruh UI) + guide/
docs/
  plans/                catatan rencana & keputusan per fitur (PRINSIP.md wajib dibaca)
  guide/                generator panduan pengguna (HTML + PDF)
  Template_BAA.xlsx     contoh template
tools/                  build_wilayah.py, build_peta.py (generator data statis)
```

### Data runtime (`$REZA_BAA_HOME/data/`)

```
app.db                  hub: user, sesi, project, keanggotaan, audit
projects/pN/
  project.db            lokasi, inventory, foto, scan, lampiran, aktivitas, pengaturan project, gsheet_sync/log
  images/<KODE>/        foto per lokasi
  docs/<KODE>/          scan & lampiran PDF
  templates/            template Excel project
output/                 hasil export sementara
```

Pindah server atau backup cukup dengan menyalin seluruh folder `data/`, atau memakai menu Backup (ZIP).

---

## Prinsip pengembangan

Ringkasan dari [`docs/plans/PRINSIP.md`](docs/plans/PRINSIP.md). Tool ini harus selalu **configurable dan futureproof**:

1. Tidak ada nilai klien yang di-hardcode. Label, format, daftar, dan aturan diatur admin per project.
2. Fitur baru memakai ulang mekanisme yang sudah ada.
3. Pengaturan baru ikut tersalin ke project baru, ikut backup/restore, dan bisa diekspor.
4. Data lama aman. Migrasi skema otomatis, dan fitur baru default-nya mati.
5. `id` lokasi adalah kunci internal. Kode, SID, dan nama hanya tampilan yang bisa diganti.
6. Keluaran lewat template/mapping, bukan kode.

Catatan per fitur ada di `docs/plans/`:
- `ocr-sn.md`: OCR serial number
- `gsheet-sync.md`: sinkron Google Sheet
- `reporting.md`: laporan
- `wilayah.md`: data wilayah
- `project-lifecycle.md`: siklus project
- `operator-flow.md`: alur kerja operator
- `photo-storage.md`: penyimpanan foto
- `intro.md`: intro interaktif
- `ui-polish.md`: penyempurnaan UI

## Rencana berikutnya

- **Versi server Linux** (Docker + nginx + HTTPS + domain) agar bisa diakses dari luar kantor, menggantikan `.exe`.
  Kode sudah lintas platform; yang tinggal disiapkan adalah paket deploy, LibreOffice untuk PDF template, dan pengamanan cookie/proxy.

## Lisensi data

- Batas wilayah peta: [geoBoundaries](https://www.geoboundaries.org/) (CC BY 4.0).
- Kode & nama wilayah: Kemendagri.
