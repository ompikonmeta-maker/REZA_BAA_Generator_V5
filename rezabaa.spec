# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — bundel REZA BAA Generator jadi satu executable.

One-file: semua dependensi + aset frontend (app/web) tertanam. Data runtime
(data/) dibuat di samping executable saat pertama dijalankan.
"""
from PyInstaller.utils.hooks import collect_all, collect_submodules

datas = [("app/web", "app/web"), ("app/data", "app/data")]   # app/data: referensi wilayah
binaries = []
hiddenimports = []

for pkg in ("uvicorn", "fastapi", "starlette", "pydantic", "openpyxl",
            "reportlab", "PIL", "pytesseract", "anyio", "multipart"):
    try:
        d, b, h = collect_all(pkg)
        datas += d; binaries += b; hiddenimports += h
    except Exception:
        pass

hiddenimports += collect_submodules("uvicorn")

a = Analysis(
    ["run.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy.tests"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="BAA_Generator",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
