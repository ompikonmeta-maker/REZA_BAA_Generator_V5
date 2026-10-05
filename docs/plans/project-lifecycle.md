# Rencana: Setup → Active ⇄ Frozen + Ganti Prefix Kode

Status: **Selesai diimplementasi** · 2026-10-05 · revisi: flow admin, mode Setup di sidebar, susunan menu baru

## Tujuan
Tidak ada yang bisa entry BAA sebelum admin selesai menyiapkan project. Admin bisa membekukan project kapan saja untuk konfigurasi ulang, termasuk mengganti prefix kode pada project yang sudah berisi data.

## Keputusan
| Topik | Keputusan |
|---|---|
| Item wajib sebelum Activate | **Location data** (min. 1 field + 1 kategori foto), **template BAA + mapping**, **akses tim** (min. 1 operator) |
| Password admin | **Dipaksa diganti saat login pertama** (bukan item checklist, karena berlaku per akun, bukan per project) |
| Target & deadline | **Opsional**, boleh menyusul (variabel yang bisa berubah) |
| Field lokasi · kategori foto · inventory untuk project baru | **Revisi 2026-10-05** (menggantikan "selalu mulai kosong"): project **pertama** memakai **pengaturan bawaan BAA**; project **berikutnya** admin memilih sumber: *Pengaturan bawaan BAA* · *Salin dari project lain* · *Kosong*. Nama Lokasi tetap field sistem terkunci. Wilayah default ON |
| Admin sebelum Activate | **Ikut diblokir** entry |
| Frozen: operator & viewer | **Semua diblokir**: entry, edit, upload foto/scan, import, **export**. Masih bisa melihat data |
| Frozen: admin | Boleh ubah konfigurasi **dan** edit data lokasi |
| Pesan Freeze | Wajib tampil ke user. Admin bisa mengedit pesan (chip cepat: Template revision, Code prefix change, Data check); ada preview banner |
| Ganti kode | **Hanya prefix** (LOK → KMP). Nomor urut & 5 digit tetap |
| Syarat ganti prefix | Project harus **Frozen** |
| Project yang sudah ada | Migrasi otomatis → **Active** dan **tetap memakai pengaturan lama** (field, foto, inventory, template, akses) — dikonfirmasi |
| Instalasi baru | Tidak lagi membuat "Project 1" otomatis → admin langsung diarahkan membuat project pertama |
| Project baru berikutnya | Lewat flow yang sama (mulai dari Setup) |

## Flow admin
### Masalah flow lama
- Settings mencampur pengaturan **global** (Projects, Users, Backup) dan **per project** (Template, Fields, Photo, Inventory) tanpa pembeda; konteks project hanya dari pemilih di sidebar → rawan mengedit project yang salah.
- Setup project butuh ±6 perpindahan halaman + 1 reload (Manage template = pindah project), dan bolak-balik Users ↔ Projects untuk memberi akses.
- Checklist tanpa "rumah": tiap link membawa admin keluar tanpa jalan kembali.

### Instalasi baru
```
Login → wajib ganti password (layar penuh, langkah 1/2)
→ "Create your first project" (nama · prefix · warna, langkah 2/2)
→ langsung masuk mode Setup
```

### Mode Setup (sidebar = langkah)
Saat project yang dipilih berstatus Setup, menu operasional (Dashboard, Progress, BAA Entry, Location Log) **disembunyikan**; sidebar berubah menjadi:
```
[BTS] BTS Jatim · SETUP
SET UP THIS PROJECT
  ● Overview        ← progres x/3, kartu tiap langkah, tombol Activate project
  ○ Location data   ← tab Location fields · Photos · Inventory (mulai kosong)
  ○ Template BAA    ← upload + mapping (butuh Location data dulu)
  ○ Team            ← akses + "+ New user" langsung di sini
  ○ Target          (optional)
WORKSPACE
  All projects · Users
```
- **Urutan**: Location data → Template BAA, karena mapping template butuh field & kategori foto yang sudah ada.
- Tiap langkah punya status (✓ / ! / –) dan tombol **Back / Next: …** di bawah halaman → admin cukup turun dari atas ke bawah.
- Location data kosong: Nama Lokasi (sistem, terkunci) + empty state "Add the fields technicians must fill" dengan **chip saran** (Tanggal Aktivasi, Teknisi, PIC Lokasi, No. HP PIC, Alamat, Koordinat) + "Add field". Syarat: min. 1 field + 1 kategori foto.
- Team: form inline (Full name · Username · Role · Add) → akun baru langsung dapat akses ke project ini + password sementara untuk dibagikan; user lain lewat switch. Syarat: min. 1 operator.
- Pindah antar langkah **tanpa reload** dan tanpa pindah project.
- Setelah **Activate**, sidebar kembali ke menu normal dan admin mendarat di Dashboard project.
- Project ke-2 dst.: "New project" → flow yang sama (mulai kosong).

### Susunan menu baru (project Active)
```
Portfolio · Dashboard · Progress · BAA Entry · Location Log · Settings
Settings
  [LOK] THIS PROJECT → Project & status · Template BAA · Location data · Team
  WORKSPACE          → All projects · Users · Backup & Restore
```
- **Import Locations** → tombol "Import locations" di Location Log.
- **Deleted Locations** → tab segmented **Active · N | Deleted · N** di Location Log.
- **Notifications** → ikon lonceng + badge di footer sidebar (samping ganti password/tema/logout).
- "Location data" menyatukan Location Fields, Inventory Fields, Photo & Capture Fields (tab).
- "Project & status" = editor project + strip status (Freeze/Unfreeze, Change prefix).
- Chip project di judul grup "This project" → admin selalu tahu project mana yang diedit.

## Status project
| Status | Perilaku |
|---|---|
| **Setup** | Belum pernah aktif. Tidak ada yang bisa entry (termasuk admin). Admin bekerja di **mode Setup** (lihat Flow admin). Operator/viewer yang tidak punya project Active melihat layar "No project is ready yet". |
| **Active** | Normal. Tombol **Freeze** di strip status. |
| **Frozen** | Read-only untuk operator/viewer. Banner biru berisi pesan admin + "by · since". Strip status admin: pesan + **Edit message** + **Unfreeze**. Link **Change prefix…** tersedia. |

- Setup → Active: tombol **Activate project** di Overview mode Setup (aktif bila semua langkah wajib ✓). Satu arah.
- Active ⇄ Frozen: satu tombol Freeze / Unfreeze.
- Operator yang sedang mengisi BAA saat project di-freeze: diberi tahu, draf yang belum disimpan tidak hilang tapi tidak bisa disimpan.
- Setup/Frozen dijaga **di server** (bukan hanya UI): semua endpoint tulis (lokasi, foto, scan, inventory, import, wilayah-bulk) dan export menolak bila project tidak Active (kecuali admin saat Frozen untuk edit data/konfigurasi).

## UI
- **Settings › This project › Project & status:** strip status (pill ACTIVE / FROZEN + teks + aksi Freeze/Unfreeze) di atas form; link **Change prefix…** saat Frozen.
- **Setup:** tidak memakai checklist di Settings › Projects (mockup pertama) — digantikan **Overview** di mode Setup (lihat Flow admin).
- **Dialog Freeze:** penjelasan dampak, textarea pesan, chip pesan cepat, preview banner, tombol **Freeze project**.
- **Operator saat Frozen:**
  - Dashboard: banner di atas; New location / Continue dimatikan.
  - BAA Entry: layar "Input is paused" + pesan admin; Add Location dimatikan.
  - Location Log / drawer: tombol upload & edit disembunyikan (seperti mode read-only).
- **Pemilih project & Portfolio:** label status kecil untuk Setup/Frozen.

## Ganti prefix (re-code)
1. Admin klik **Change prefix…** (hanya saat Frozen) → isi prefix baru (2–4 huruf, unik antar project).
2. **Analisa** (tanpa mengubah apa pun):
   - jumlah lokasi yang ganti kode (termasuk yang terhapus/di tong sampah);
   - jumlah foto & scan PDF, folder yang dipindah, total ukuran file;
   - contoh pemetaan `LOK_00001 → KMP_00001 … LOK_00070 → KMP_00070`;
   - cek konflik (kode tujuan / prefix dipakai project lain, folder tujuan sudah ada);
   - jumlah lokasi yang **sudah pernah di-export** → file yang sudah terkirim tetap memakai kode lama.
3. **Re-code N locations**: satu transaksi — update `locations.code`, ganti nama folder `images/<KODE>/` & `docs/<KODE>/`, update path relatif foto/scan, update prefix project. Gagal di tengah → semua dikembalikan (DB rollback + folder dikembalikan).
4. Audit log: `recode` prefix lama → baru, jumlah lokasi.
5. Kode lama tetap bisa dicari di Location Log (simpan riwayat kode lama per lokasi).

## Catatan
- Pencatatan export **belum ada** saat ini → perlu log export baru (lokasi + jenis + waktu + user). Peringatan "sudah di-export" hanya akurat untuk export setelah fitur ini aktif.
- Prefix yang belum pernah menerbitkan kode tetap bisa diganti langsung seperti sekarang (tanpa Freeze/analisa).
- Mockup: Setup checklist, layar "not ready", Active, dialog Freeze, Frozen, analisa ganti prefix, operator Dashboard & BAA Entry saat Frozen; revisi: ganti password login pertama, buat project pertama, mode Setup (Overview, Location data, Team), menu baru.

## Revisi: isi awal project baru (2026-10-05) — dicatat, menunggu "gas"
| Topik | Keputusan |
|---|---|
| Project pertama (layar Create your first project) | Langsung terisi **pengaturan bawaan BAA**: 4 field (Nama Lokasi, Tanggal Aktivasi, Teknisi, PIC Lokasi), 11 kategori foto, 3 inventory (Kit Starlink, Router, Access Point) — sesuai template BAA resmi, sehingga mapping template hampir langsung cocok |
| Project ke-2 dst. (New project) | Pilihan **Mulai dari**: `Pengaturan bawaan BAA` (default) · `Salin dari project lain` (pilih project; menyalin field, kategori foto, inventory, notes/merk) · `Kosong` (hanya Nama Lokasi) |
| Konfirmasi Location data | Bila project terisi dari bawaan/salinan, langkah **Location data** berstatus **Check** (oranye, belum ✓). Admin wajib membuka sekali, meninjau, lalu klik **Looks good — confirm** → baru ✓. Banner di atas tab: "Default BAA settings are filled in. Check …, then confirm." Pilihan *Kosong* tetap memakai syarat lama (min. 1 field + 1 kategori foto) |
| Activate | Tetap butuh Location data ✓ (terkonfirmasi) + Template + Team |
| Panduan | Topik Setup & Location data diperbarui (teks + screenshot) |

