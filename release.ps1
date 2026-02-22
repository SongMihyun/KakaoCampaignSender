Param(
  [Parameter(Mandatory=$true)]
  [string]$Version,                 # 예: 0.1.18 (v 없이)

  [string]$Remote  = "origin",
  [string]$Branch  = "main",
  [string]$Message = "",            # 비우면 자동: release: vX.Y.Z

  [switch]$ForceTag                 # 이미 태그 있으면 삭제 후 재생성(비권장)
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Run([string]$cmd) {
  Write-Host ">> $cmd" -ForegroundColor Cyan
  Invoke-Expression $cmd
}

# --- 0) 입력 검증 ---
if ($Version -notmatch '^\d+\.\d+\.\d+$') {
  throw "Version must be like 0.1.18 (v 없이). 입력값: $Version"
}
$tag = "v$Version"

# --- 1) git repo 확인 ---
Run "git rev-parse --is-inside-work-tree > `$null"

# --- 2) 최신화 ---
Run "git fetch $Remote --tags"
Run "git checkout $Branch"
Run "git pull $Remote $Branch"

# --- 3) 릴리즈 필수 파일(태그 커밋에 포함돼야 함) 사전 점검 ---
$mustFiles = @(
  "KakaoSender.spec",
  "installer/KakaoCampaignSender.iss",
  "installer/KakaoSender.ico",
  ".github/workflows/release.yml"
)

foreach ($f in $mustFiles) {
  if (-not (Test-Path $f)) { throw "Missing file in working tree: $f" }
  $tracked = (git ls-files -- "$f")
  if (-not $tracked) { throw "File is not tracked by git (git add 필요): $f" }
}

# --- 4) 스테이지 ---
Run "git add -A"

if ([string]::IsNullOrWhiteSpace($Message)) {
  $Message = "release: $tag"
}

# --- 5) 커밋(변경 없어도 릴리즈 커밋을 남김) ---
$staged = (git diff --cached --name-only)
if ($staged) {
  Run "git commit -m `"$Message`""
} else {
  Write-Host "No staged changes. Creating an empty release commit: $Message" -ForegroundColor Yellow
  Run "git commit --allow-empty -m `"$Message`""
}

# --- 6) 브랜치 push ---
Run "git push $Remote $Branch"

# --- 7) 태그 처리 ---
$existing = (git tag -l $tag)
if ($existing) {
  if ($ForceTag) {
    Write-Host "Tag $tag already exists. Replacing it (--ForceTag)." -ForegroundColor Yellow
    Run "git tag -d $tag"
    Run "git push $Remote :refs/tags/$tag"
  } else {
    throw "Tag $tag already exists. 새 버전으로 진행하거나 -ForceTag(비권장) 사용."
  }
}

Run "git tag -a $tag -m `"$tag`""
Run "git push $Remote $tag"

Write-Host ""
Write-Host "✅ DONE: pushed $tag (and $Branch). Actions will run on tag push." -ForegroundColor Green