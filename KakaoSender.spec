# KakaoSender.spec
# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all

hiddenimports = []
datas = []
binaries = []

for pkg in ["pywinauto", "comtypes", "PIL"]:
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

# ✅ 핵심: exclude_binaries=True (그래야 dist/app 루트에 exe가 “따로” 안 떨어짐)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="KakaoCampaignSender",   # ✅ EXE 이름 통일
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,                # ✅ GUI
    icon="installer/KakaoSender.ico",  # (있으면 적용, 없으면 이 줄 제거)
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="KakaoCampaignSender",   # ✅ 폴더명 통일
)