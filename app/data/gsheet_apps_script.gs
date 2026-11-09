/**
 * BAA Flow ↔ Google Sheet (dipasang sekali oleh pemilik sheet).
 *
 * Pasang:
 *  1. Di sheet: Extensions › Apps Script › hapus isi Code.gs › tempel seluruh file ini.
 *  2. Isi SECRET (kode rahasia, sama dengan di BAA Flow) dan FOLDER_ID (folder Google Drive untuk PDF BAPB).
 *  3. Services (+) › Drive API › Add   (dipakai untuk menimpa PDF tanpa mengubah link).
 *  4. Deploy › New deployment › Web app · Execute as: Me · Who has access: Anyone › Deploy › salin URL /exec ke BAA Flow.
 *  Setelah mengubah script: Deploy › Manage deployments › Edit › Version: New version.
 *
 * BAA Flow hanya MENULIS kolom yang diminta (STATUS/TANGGAL/LINK BAPB), mencari kolom lewat judul header di baris 1.
 */
const SECRET = 'GANTI_DENGAN_KODE_RAHASIA';
const SHEET_NAME = 'Master';
const FOLDER_ID = '';

function doPost(e) {
  let req = {};
  try { req = JSON.parse((e && e.postData && e.postData.contents) || '{}'); } catch (err) { return out_({ ok: false, error: 'Bad request' }); }
  if (!SECRET || SECRET === 'GANTI_DENGAN_KODE_RAHASIA' || req.secret !== SECRET) return out_({ ok: false, error: 'Wrong secret code' });
  try {
    if (req.action === 'ping') return out_(ping_());
    if (req.action === 'read') return out_(read_(req.columns || []));
    if (req.action === 'update') return out_(update_(req));
    if (req.action === 'upload') return out_(upload_(req));
    return out_({ ok: false, error: 'Unknown action' });
  } catch (err) {
    return out_({ ok: false, error: String(err && err.message || err) });
  }
}

function doGet() { return out_({ ok: true, app: 'BAA Flow sheet link', hint: 'use POST' }); }

function out_(o) { return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON); }

function sheet_() {
  const sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(SHEET_NAME);
  if (!sh) throw new Error('Tab "' + SHEET_NAME + '" not found');
  return sh;
}

function headers_(sh) {
  return sh.getRange(1, 1, 1, sh.getLastColumn()).getDisplayValues()[0].map(function (h) { return String(h).trim(); });
}

function ping_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet(), sh = sheet_();
  return { ok: true, file: ss.getName(), sheet: SHEET_NAME, rows: Math.max(0, sh.getLastRow() - 1),
           headers: headers_(sh), folder: FOLDER_ID ? DriveApp.getFolderById(FOLDER_ID).getName() : '' };
}

/** Kolom yang diminta (judul header) sebagai teks tampilan, per baris data. */
function read_(columns) {
  const sh = sheet_(), hdr = headers_(sh), n = sh.getLastRow() - 1;
  const idx = columns.map(function (c) { return hdr.indexOf(c); });
  const rows = [];
  if (n > 0) {
    const vals = sh.getRange(2, 1, n, hdr.length).getDisplayValues();
    for (let i = 0; i < n; i++) {
      const r = {}; let any = false;
      columns.forEach(function (c, k) { const v = idx[k] >= 0 ? String(vals[i][idx[k]]).trim() : ''; r[c] = v; if (v) any = true; });
      if (any) rows.push({ row: i + 2, v: r });
    }
  }
  return { ok: true, file: SpreadsheetApp.getActiveSpreadsheet().getName(), sheet: SHEET_NAME, headers: hdr,
           missing: columns.filter(function (c, k) { return idx[k] < 0; }), rows: rows };
}

/** updates: [{row, key, values:{header: value}}]; key_col dicek supaya baris yang bergeser tidak tertimpa. */
function update_(req) {
  const sh = sheet_(), hdr = headers_(sh), kc = hdr.indexOf(req.key_col);
  if (kc < 0) throw new Error('Key column not found: ' + req.key_col);
  const lock = LockService.getDocumentLock(); lock.waitLock(20000);
  const done = [], skipped = [];
  try {
    (req.updates || []).forEach(function (u) {
      const key = String(sh.getRange(u.row, kc + 1).getDisplayValue()).trim();
      if (key !== String(u.key)) { skipped.push({ row: u.row, key: u.key, found: key }); return; }
      Object.keys(u.values || {}).forEach(function (h) {
        const c = hdr.indexOf(h);
        if (c >= 0) sh.getRange(u.row, c + 1).setValue(u.values[h]);
      });
      done.push(u.row);
    });
  } finally { lock.releaseLock(); }
  return { ok: true, updated: done.length, skipped: skipped };
}

/** PDF base64 -> folder; file dengan nama sama ditimpa isinya (link tetap). */
function upload_(req) {
  if (!FOLDER_ID) throw new Error('FOLDER_ID is empty in the script');
  const folder = DriveApp.getFolderById(FOLDER_ID);
  const blob = Utilities.newBlob(Utilities.base64Decode(req.data), 'application/pdf', req.name);
  const it = folder.getFilesByName(req.name);
  let file;
  if (it.hasNext()) {
    file = it.next();
    Drive.Files.update({}, file.getId(), blob);
  } else {
    file = folder.createFile(blob);
  }
  return { ok: true, id: file.getId(), url: file.getUrl() };
}
