# KakaoSender.spec
# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all

hiddenimports = []
datas = []
binaries = []

for pkg in ["pywinauto", "comtypes", "PIL"]:
    # PyInstaller 6.19+ : collect_all() returns a tuple: (datas, binaries, hiddenimports)
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    ["src/app/main.py"],
    pathex=["src"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="KakaoCampaignSender",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # GUI
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="KakaoCampaignSender",
)
