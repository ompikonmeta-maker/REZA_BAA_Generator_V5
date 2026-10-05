"""Entrypoint FastAPI: init DB, daftarkan router, sajikan frontend statis."""
from __future__ import annotations

# Build marker: memicu workflow Build Windows EXE untuk branch ini.

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config, db
from .routers import (auth, backup, export, import_loc, locations, notifications, ocr, photos, progress, projects, scan, settings, stats, templates, users, wilayah)

app = FastAPI(title="BAA Generator", version="0.1.0")


@app.on_event("startup")
def _startup() -> None:
    config.ensure_dirs()
    db.init_db()


from fastapi import Depends  # noqa: E402

from .deps import data_gate  # noqa: E402

# Router data: tulis & export dijaga status project (Setup/Frozen) di server
_GATED = (import_loc.router, locations.router, photos.router, export.router, ocr.router,
          notifications.router, scan.router)
for r in (auth.router, settings.router, templates.router, import_loc.router, locations.router,
          photos.router, users.router, export.router, backup.router, ocr.router, stats.router,
          notifications.router, progress.router, projects.router, scan.router, wilayah.router):
    app.include_router(r, dependencies=[Depends(data_gate)] if r in _GATED else [])


@app.get("/api/health")
def health():
    from .services import ocr
    return {"ok": True, "ocr_available": ocr.available()}


# --- Frontend statis ---
if config.WEB_DIR.exists():
    assets = config.WEB_DIR / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")
    guide = config.WEB_DIR / "guide"
    if guide.exists():   # panduan Admin & Operator (HTML + PDF), dibuka dari tombol Help
        app.mount("/guide", StaticFiles(directory=str(guide), html=True), name="guide")

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon():
        return FileResponse(str(assets / "favicon.ico"), media_type="image/x-icon")

    @app.get("/")
    def index():
        idx = config.WEB_DIR / "index.html"
        if idx.exists():
            return FileResponse(str(idx))
        return JSONResponse({"ok": True, "msg": "Backend aktif. Frontend belum dipasang."})
