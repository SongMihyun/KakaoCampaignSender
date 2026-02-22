Param(
  [Parameter(Mandatory=$true)]
  [string]$Version,                 # 예: 0.1.16 (v 없이)

  [string]$Remote  = "origin",
  [string]$Branch  = "main",
  [string]$Message = "",            # 비우면 자동: release: vX.Y.Z

  # ✅ 선택 옵션
  [switch]$BuildLocal,              # 로컬에서 exe 빌드도 같이 하고 싶으면
  [string]$Spec = "KakaoSender.spec",
  [string]$DistPath = "dist/app",
  [switch]$NoClean,                 # BuildLocal일 때 dist/build 삭제 스킵

  [switch]$ForceTag                 # 이미 태그 있으면 지우고 재생성(비권장)
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Run([string]$cmd) {
  Write-Host ">> $cmd" -ForegroundColor Cyan
  Invoke-Expression $cmd
}

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

function Build-Exe([string]$Spec, [string]$DistPath, [bool]$NoClean) {
  if (-not (Test-Path $Spec)) { throw "Spec not found: $Spec" }

  if (-not $NoClean) {
    Remove-DirSafe "dist"
    Remove-DirSafe "build"
  }

  Write-Host ">> build exe: poetry run pyinstaller ..." -ForegroundColor Cyan
  Run "poetry run pyinstaller -y --clean --distpath `"$DistPath`" `"$Spec`""

  $exePath = Join-Path $DistPath "KakaoCampaignSender/KakaoCampaignSender.exe"
  if (-not (Test-Path $exePath)) {
    Write-Host "----- dist/app tree -----" -ForegroundColor Yellow
    if (Test-Path $DistPath) { Get-ChildItem -Recurse $DistPath | Select-Object FullName }
    throw "Expected EXE not found: $exePath"
  }
  Write-Host "✅ OK: $exePath" -ForegroundColor Green
}

# --- 0) 입력 검증 ---
if ($Version -notmatch '^\d+\.\d+\.\d+$') {
  throw "Version must be like 0.1.16 (v 없이). 입력값: $Version"
}
$tag = "v$Version"

# --- 1) git repo 확인 ---
Run "git rev-parse --is-inside-work-tree > `$null"

# --- 2) 원격/브랜치 최신화 ---
Run "git fetch $Remote --tags"
Run "git checkout $Branch"
Run "git pull $Remote $Branch"

# --- 3) (선택) 로컬 빌드 ---
if ($BuildLocal) {
  Build-Exe -Spec $Spec -DistPath $DistPath -NoClean:$NoClean
}

# --- 4) 커밋/푸시 ---
Run "git add -A"

if ([string]::IsNullOrWhiteSpace($Message)) {
  $Message = "release: $tag"
}

$staged = (git diff --cached --name-only)
if ($staged) {
  Run "git commit -m `"$Message`""
} else {
  Write-Host "스테이징된 변경이 없어 commit은 스킵합니다." -ForegroundColor Yellow
}

Run "git push $Remote $Branch"

# --- 5) 태그 생성/푸시 ---
$existing = (git tag -l $tag)
if ($existing) {
  if ($ForceTag) {
    Write-Host "태그 $tag 이미 존재. --ForceTag로 재지정합니다(주의)." -ForegroundColor Yellow
    Run "git tag -d $tag"
    Run "git push $Remote :refs/tags/$tag"
  } else {
    throw "태그 $tag 가 이미 존재합니다. 새 버전으로 진행하거나 -ForceTag(비권장) 사용."
  }
}

Run "git tag -a $tag -m `"$tag`""
Run "git push $Remote $tag"

Write-Host ""
Write-Host "✅ 완료: $tag 푸시됨. GitHub Actions가 태그 트리거로 빌드/릴리즈를 시작합니다." -ForegroundColor Green
Write-Host "   GitHub → Actions 탭에서 실행 상태를 확인하세요."