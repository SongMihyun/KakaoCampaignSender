# KakaoSender.spec
# -*- mode: python ; coding: utf-8 -*-

import os
from PyInstaller.utils.hooks import collect_all

hiddenimports, datas, binaries = [], [], []

for pkg in ["pywinauto", "comtypes", "PIL"]:
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# ✅ 레포 루트 기준(= pyinstaller 실행한 현재 폴더)
REPO_DIR = os.path.abspath(os.getcwd())
ICON_PATH = os.path.join(REPO_DIR, "installer", "KakaoSender.ico")

if not os.path.exists(ICON_PATH):
    raise SystemExit(f"[spec] icon not found: {ICON_PATH} (cwd={os.getcwd()})")

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
    [],
    exclude_binaries=True,
    name="KakaoCampaignSender",
    console=False,
    icon=ICON_PATH,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="KakaoCampaignSender",
)