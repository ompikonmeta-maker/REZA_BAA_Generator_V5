# Rencana: Setup → Active ⇄ Frozen + Ganti Prefix Kode

Status: **Disetujui (mockup), belum diimplementasi** · 2026-10-05

## Tujuan
Tidak ada yang bisa entry BAA sebelum admin selesai menyiapkan project. Admin bisa membekukan project kapan saja untuk konfigurasi ulang, termasuk mengganti prefix kode pada project yang sudah berisi data.

## Keputusan
| Topik | Keputusan |
|---|---|
| Item wajib sebelum Activate | Nama & prefix, **template BAA + mapping**, **akses tim** (min. 1 operator), **password admin sudah diganti** dari default |
| Target & deadline | **Opsional**, boleh menyusul (variabel yang bisa berubah) |
| Field lokasi · kategori foto · inventory · wilayah | Sudah terisi default, hanya ditandai "Review" (tidak memblok) |
| Admin sebelum Activate | **Ikut diblokir** entry |
| Frozen: operator & viewer | **Semua diblokir**: entry, edit, upload foto/scan, import, **export**. Masih bisa melihat data |
| Frozen: admin | Boleh ubah konfigurasi **dan** edit data lokasi |
| Pesan Freeze | Wajib tampil ke user. Admin bisa mengedit pesan (chip cepat: Template revision, Code prefix change, Data check); ada preview banner |
| Ganti kode | **Hanya prefix** (LOK → KMP). Nomor urut & 5 digit tetap |
| Syarat ganti prefix | Project harus **Frozen** |
| Project yang sudah ada | Migrasi otomatis → **Active** (tidak mengganggu data) |
| Instalasi baru | Tidak lagi membuat "Project 1" otomatis → admin langsung diarahkan membuat project pertama |
| Project baru berikutnya | Lewat flow yang sama (mulai dari Setup) |

## Status project
| Status | Perilaku |
|---|---|
| **Setup** | Belum pernah aktif. Tidak ada yang bisa entry (termasuk admin). Admin mengisi checklist. Operator/viewer yang tidak punya project Active melihat layar "No project is ready yet". |
| **Active** | Normal. Tombol **Freeze** di strip status. |
| **Frozen** | Read-only untuk operator/viewer. Banner biru berisi pesan admin + "by · since". Strip status admin: pesan + **Edit message** + **Unfreeze**. Link **Change prefix…** tersedia. |

- Setup → Active: tombol **Activate project** (aktif bila semua item wajib ✓). Satu arah.
- Active ⇄ Frozen: satu tombol Freeze / Unfreeze.
- Operator yang sedang mengisi BAA saat project di-freeze: diberi tahu, draf yang belum disimpan tidak hilang tapi tidak bisa disimpan.
- Setup/Frozen dijaga **di server** (bukan hanya UI): semua endpoint tulis (lokasi, foto, scan, inventory, import, wilayah-bulk) dan export menolak bila project tidak Active (kecuali admin saat Frozen untuk edit data/konfigurasi).

## UI
- **Settings › Projects (editor):** strip status (pill SETUP / ACTIVE / FROZEN + teks + aksi) di atas form.
- **Checklist Setup:** "Ready to activate? · x of 4 required" + bar; tiap baris punya status (✓ / ! / –), tag Required/Optional/Review, dan link langsung ke pengaturannya (Upload, Set, Review). Footer: "Nobody can enter BAA (including admin) until the project is activated" + **Activate project**.
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
- Password admin: item checklist tercentang bila password akun admin sudah bukan default `admin123`.
- Prefix yang belum pernah menerbitkan kode tetap bisa diganti langsung seperti sekarang (tanpa Freeze/analisa).
- Mockup: Setup checklist, layar "not ready", Active, dialog Freeze, Frozen, analisa ganti prefix, operator Dashboard & BAA Entry saat Frozen.
