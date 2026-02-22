Param(
  [string]$Spec = "KakaoSender.spec",
  [string]$DistPath = "dist/app",
  [switch]$NoClean
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ✅ 항상 이 스크립트가 있는 폴더(=레포 루트)에서 실행되도록 고정
Set-Location $PSScriptRoot

function Remove-DirSafe([string]$Path) {
  if (Test-Path $Path) {
    Write-Host ">> remove: $Path" -ForegroundColor Cyan
    try {
      Remove-Item $Path -Recurse -Force -ErrorAction Stop
    } catch {
      Start-Sleep -Milliseconds 500
      Remove-Item $Path -Recurse -Force
    }
  } else {
    Write-Host ">> skip(remove): $Path (not found)" -ForegroundColor DarkGray
  }
}

# 1) spec 존재 확인
if (-not (Test-Path $Spec)) {
  throw "Spec not found: $Spec (레포 루트에 있는지 파일명 확인)"
}

# 2) 아이콘 존재 확인(로컬 기준)
$icon = Join-Path $PSScriptRoot "installer\KakaoSender.ico"
if (-not (Test-Path $icon)) {
  throw "Icon not found: $icon"
}

# 3) dist/build 정리
if (-not $NoClean) {
  Remove-DirSafe "dist"
  Remove-DirSafe "build"
}

# 4) PyInstaller 빌드
Write-Host ">> build exe: poetry run pyinstaller ..." -ForegroundColor Cyan
poetry run pyinstaller -y --clean --distpath $DistPath $Spec

# 5) 산출물 검증(통일 기준)
$exePath = Join-Path $DistPath "KakaoCampaignSender\KakaoCampaignSender.exe"
if (-not (Test-Path $exePath)) {
  Write-Host "----- dist/app tree -----" -ForegroundColor Yellow
  if (Test-Path $DistPath) { Get-ChildItem -Recurse $DistPath | Select-Object FullName }
  throw "Expected EXE not found: $exePath"
}

Write-Host ""
Write-Host "✅ OK: $exePath" -ForegroundColor Green