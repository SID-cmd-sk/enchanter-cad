# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for ENCHANTER-CAD 2D V1.1.

Run:  pyinstaller pycad.spec --noconfirm
Output: dist/ENCHANTER-CAD/ENCHANTER-CAD.exe
"""
import os

HERE = os.path.dirname(os.path.abspath(SPEC))
ASSETS = os.path.abspath(os.path.join(HERE, "..", "assets"))

block_cipher = None

a = Analysis(
    [os.path.join(HERE, "enchantr_app.py")],
    pathex=[HERE],
    binaries=[],
    datas=[
        (os.path.join(HERE, "posts"), "posts"),
        (os.path.join(HERE, "fonts"), "fonts"),
        (os.path.join(HERE, "assets", "fonts"), "assets/fonts"),
        (ASSETS, "assets"),
        (os.path.join(HERE, "README.md"), "."),
        (os.path.join(os.path.dirname(os.__file__), "unittest"), "unittest"),
    ],
    hiddenimports=[
        "posts", "posts.base", "posts.fanuc", "posts.haas", "posts.grbl",
        "posts.mach3", "posts.linuxcnc", "posts.siemens", "posts.heidenhain",
        "posts.waterjet", "command_table", "gcode", "gcode_dialog",
        "dim_dialog", "constraint_manager", "io_dxf", "ribbon", "canvas",
        "entities", "commands", "constraints",         "fonts", "main",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["PyQt6.QtDesigner", "PyQt6.QtQml", "PyQt6.QtMultimedia",
              "PyQt6.QtNetwork", "PyQt6.QtWebEngineCore", "PyQt6.QtWebEngineWidgets",
              "PyQt6.QtWebChannel", "PyQt6.QtPositioning", "PyQt6.QtLocation",
              "PyQt6.QtBluetooth", "PyQt6.QtSerialPort", "PyQt6.QtSql",
              "PyQt6.QtTest",         "PyQt6.QtSvgWidgets", "tkinter"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ENCHANTER-CAD",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(ASSETS, "icons", "appicon.ico"),
    version=os.path.join(HERE, "version_info.txt"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="ENCHANTER-CAD",
)

