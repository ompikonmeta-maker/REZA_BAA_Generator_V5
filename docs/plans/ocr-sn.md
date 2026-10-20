# 27. Baca SN: barcode dulu + OCR tahan kondisi terburuk (2026-10-20, ✅)

## Latar
- Paket `BAA_OCR_upgrade.zip` dari obrolan claude.ai dievaluasi, tidak dipakai utuh. Kenaikannya hampir semua dari
  barcode, sedangkan pada label teks SN malah terpotong (`A5E2E46`). Yang diambil hanya idenya: barcode di server (zxing-cpp).
- Uji pakai 13 foto asli (`contoh_foto_ocr.zip`). 9 di antaranya kecil (±400–676 px, terkompres WhatsApp), jadi diperlakukan
  sebagai **kondisi terburuk**. Kunci jawaban: 12 dan 13 tertukar, 4 = `HJD0A0YY1VY`, 13 = `HJF0ARYC9GN`.

## Keputusan pengguna
- Tahap 1–3 disetujui: barcode di server, OCR lama diperkuat, aturan SN per kategori.
- Target: tetap terbaca pada foto terburuk; foto yang lebih bagus otomatis lebih mudah.

## Dikerjakan
- **Barcode di server** (`zxing-cpp`, tanpa numpy, ±50 ms):
  - dibaca saat upload, di dialog Read SN, dan di area pilihan;
  - foto kecil diperbesar 2×/3×; bila belum ketemu, dicoba ubin 3×3 bertumpuk;
  - hasil barcode selalu menang dari teks.
  - `BarcodeDetector` di browser tidak dipakai lagi (tidak ada di Chrome/Edge Windows).
- **OCR seluruh foto (auto-ROI):**
  - kata dibaca dengan Tesseract, lalu dikelompokkan jadi baris;
  - baris yang mirip SN (ada "SN"/"S/N"/"SERIAL", cocok prefix, campuran huruf-angka) dipotong dan dibaca ulang lebih detail;
  - bila tidak ada hasil yakin, foto diputar 90°/270°.
- **OCR area pilihan:**
  - beberapa skala dan mode Tesseract, lalu voting per karakter;
  - area tinggi diputar (teks tegak), dan dicoba 180° bila kosong;
  - area berisi beberapa baris dibaca ulang per baris;
  - crop dikirim sebagai PNG (sebelumnya JPEG 92).
- **Pembersih:**
  - teks watermark kamera GPS dibuang (tanggal, jam, koordinat, Altitude/msnm, Speed, Jalan/Kota/Kab, Index number);
  - baris MAC/E01:, Model, P/N, Password, SSID, dsb. diturunkan;
  - "@" di tengah SN dibaca 0;
  - label gelap dibalik warnanya;
  - bingkai kotak di sekitar SN dihapus bila bacaan pertama kosong (Tesseract gagal total bila teks dibingkai).
- **Ambang yakin:**
  - SN hanya diisi otomatis bila skornya cukup;
  - kandidat lemah atau kata biasa tidak ditawarkan;
  - lebih baik kosong ("SN not read yet") daripada salah.
- **Aturan SN per kategori** (Settings › Location data › Photo & Capture Fields › kolom *SN Prefix & rule* › *Add rule*):
  - panjang min–max;
  - karakter Any / Hex / Digits;
  - huruf yang tidak pernah dipakai (dibaca sebagai angka mirip, mis. O → 0);
  - simpan akhiran "/r2" (bawaan: tidak).
  - Disimpan di `photo_categories` (`sn_min`, `sn_max`, `sn_chars`, `sn_no`, `sn_suffix`) dan ikut tersalin saat project disalin.
- **Dialog Read SN:**
  - saat dibuka langsung membaca seluruh foto di server, lalu menampilkan sumbernya (barcode / teks);
  - kandidat berupa chip (ikon barcode untuk hasil barcode);
  - "Read area" untuk label sulit.
  - API baru `GET /api/photos/{id}/sn-read` (tanpa menyimpan); `/api/ocr` menerima `cat`.
- **Tesseract dikunci 1 thread** (`OMP_THREAD_LIMIT=1`). Dengan OpenMP bawaan, satu panggilan bisa macet 30 detik saat CPU
  dipakai proses lain; dengan 1 thread ±1 detik.
- **Build:** `zxing-cpp==3.1.1` (wheel Windows cp311 tersedia) di `requirements.txt`, hidden import `zxingcpp` di `rezabaa.spec`.

## Hasil pada 13 foto asli (cocok persis)
| Cara | OCR lama | Sekarang |
|---|---|---|
| Otomatis saat upload (seluruh foto, dengan aturan kategori) | 1 benar, 12 terisi salah | 7 benar, 1 terisi salah, 5 dikosongkan |
| Read SN area pilihan | 4 | 7 (+1 benar di daftar kandidat) |
| Dialog Read SN (seluruh foto lalu area) | – | 8 (+1 benar di daftar kandidat) |

Waktu ±1–3 detik per foto SN (barcode yang cocok aturan: ±0,1 detik).

Sisa gagal (resolusi terlalu rendah / huruf tertukar):
- 2: tulisan ±10 px;
- 8: tulisan miring, terbaca `3HI4NMS`;
- 10: terbaca `WS1809`;
- 13: J terbaca I.

## Syarat ideal foto SN
1. **Resolusi:** kirim foto asli dari kamera, bukan lewat WhatsApp. Tinggi huruf SN di foto minimal ±20 px (ideal 30–40 px);
   app menyimpan sampai 2000 px sisi panjang.
2. **Isi bingkai:** label SN mengisi ±1/3–1/2 lebar foto; dekatkan kamera, jangan memotret seluruh perangkat.
3. **Fokus & diam:** ketuk layar pada label sebelum memotret; tidak blur/goyang.
4. **Lurus:** kamera sejajar label (tidak miring > ±15°), teks horizontal.
5. **Cahaya:** merata, tanpa pantulan lampu/flash di stiker mengilap; hindari bayangan tangan.
6. **Barcode utuh:** bila label punya barcode/QR, pastikan seluruh garis barcode masuk foto; ini cara paling akurat.
7. **Watermark GPS:** letakkan teks watermark jauh dari label SN (mis. pojok bawah), jangan menimpa label.
8. **Admin:** isi aturan SN per kategori (prefix, panjang, huruf yang tidak dipakai); ini yang membetulkan O/0, I/1, S/5.
