# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller ONE-FILE spec for the ENCHANTER-CAD 2D self-installer.

Produces a single ENCHANTER-CAD-Installer.exe that carries the app payload
embedded (extracted at runtime).  uac_admin=True => Windows auto-prompts
for admin on launch.
"""
import os

HERE = os.path.dirname(os.path.abspath(SPEC))
ASSETS = os.path.abspath(os.path.join(HERE, "..", "assets"))
PAYLOAD = os.path.abspath(os.path.join(HERE, "..", "dist", "ENCHANTER-CAD"))

block_cipher = None

a = Analysis(
    [os.path.join(HERE, "installer_app.py")],
    pathex=[HERE],
    binaries=[],
    datas=[
        (ASSETS, "assets"),
        (PAYLOAD, os.path.join("payload", "ENCHANTER-CAD")),
    ],
    hiddenimports=["win32com", "win32com.client"],
    hookspath=[],
    runtime_hooks=[],
    excludes=["PyQt6.QtDesigner", "PyQt6.QtQml", "PyQt6.QtMultimedia",
              "PyQt6.QtNetwork", "PyQt6.QtWebEngineCore", "PyQt6.QtWebEngineWidgets",
              "PyQt6.QtWebChannel", "PyQt6.QtPositioning", "PyQt6.QtLocation",
              "PyQt6.QtBluetooth", "PyQt6.QtSerialPort", "PyQt6.QtSql",
              "PyQt6.QtTest", "PyQt6.QtSvgWidgets", "tkinter"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name="ENCHANTER-CAD-Installer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(ASSETS, "icons", "appicon.ico"),
    uac_admin=True,
)
