"""Entrypoint FastAPI: init DB, daftarkan router, sajikan frontend statis."""
from __future__ import annotations

# Build marker: memicu workflow Build Windows EXE untuk branch ini.

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config, db
from .routers import (auth, backup, export, import_loc, locations, notifications, ocr, photos, progress, projects, settings, stats, templates, users)

app = FastAPI(title="BAA Generator", version="0.1.0")


@app.on_event("startup")
def _startup() -> None:
    config.ensure_dirs()
    db.init_db()


for r in (auth.router, settings.router, templates.router, import_loc.router, locations.router,
          photos.router, users.router, export.router, backup.router, ocr.router, stats.router,
          notifications.router, progress.router, projects.router):
    app.include_router(r)


@app.get("/api/health")
def health():
    from .services import ocr
    return {"ok": True, "ocr_available": ocr.available()}


# --- Frontend statis ---
if config.WEB_DIR.exists():
    assets = config.WEB_DIR / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon():
        return FileResponse(str(assets / "favicon.ico"), media_type="image/x-icon")

    @app.get("/")
    def index():
        idx = config.WEB_DIR / "index.html"
        if idx.exists():
            return FileResponse(str(idx))
        return JSONResponse({"ok": True, "msg": "Backend aktif. Frontend belum dipasang."})
