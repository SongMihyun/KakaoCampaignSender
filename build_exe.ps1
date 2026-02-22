Param(
  [string]$Spec = "KakaoSender.spec",
  [string]$DistPath = "dist/app",
  [switch]$NoClean
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Remove-DirSafe([string]$Path) {
  if (Test-Path $Path) {
    Write-Host ">> remove: $Path" -ForegroundColor Cyan
    try {
      Remove-Item $Path -Recurse -Force -ErrorAction Stop
    } catch {
      # 폴더 잠김/권한 이슈 대비: 1회 재시도
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

# 2) dist/build 정리
if (-not $NoClean) {
  Remove-DirSafe "dist"
  Remove-DirSafe "build"
}

# 3) PyInstaller 빌드
Write-Host ">> build exe: poetry run pyinstaller ..." -ForegroundColor Cyan
poetry run pyinstaller -y --clean --distpath $DistPath $Spec

# 4) 산출물 검증(현재 통일 기준)
$exePath = Join-Path $DistPath "KakaoCampaignSender/KakaoCampaignSender.exe"
if (-not (Test-Path $exePath)) {
  Write-Host "----- dist/app tree -----" -ForegroundColor Yellow
  if (Test-Path $DistPath) { Get-ChildItem -Recurse $DistPath | Select-Object FullName }
  throw "Expected EXE not found: $exePath"
}

Write-Host ""
Write-Host "✅ OK: $exePath" -ForegroundColor Green