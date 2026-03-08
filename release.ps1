# FILE: release.ps1
# Git tag 기반 릴리즈 커밋/태그 생성 스크립트
# 전제:
# - main 브랜치에 릴리즈 기준 커밋을 먼저 push
# - semver tag(vX.Y.Z)를 push하면
#   .github/workflows/windows-release-build.yml 이 실행되어
#   Windows 릴리즈 빌드 및 GitHub Release 생성 수행

Param(
  [Parameter(Mandatory = $true)]
  [string]$Version,                 # 예: 0.1.35 (v 없이)

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

if ($Version -notmatch '^\d+\.\d+\.\d+$') {
  throw "Version must be like 0.1.35 (v 없이). 입력값: $Version"
}

$tag = "v$Version"

Run "git rev-parse --is-inside-work-tree > `$null"

Run "git fetch $Remote --tags"
Run "git checkout $Branch"
Run "git pull $Remote $Branch"

$mustFiles = @(
  "KakaoSender.spec",
  "installer/KakaoCampaignSender.iss",
  "installer/KakaoSender.ico",
  ".github/workflows/build-check.yml",
  ".github/workflows/windows-release-build.yml",
  ".github/release.yml"
)

foreach ($f in $mustFiles) {
  if (-not (Test-Path $f)) {
    throw "Missing file in working tree: $f"
  }

  $tracked = (git ls-files -- "$f")
  if (-not $tracked) {
    throw "File is not tracked by git (git add 필요): $f"
  }
}

Run "git add -A"

if ([string]::IsNullOrWhiteSpace($Message)) {
  $Message = "release: $tag"
}

$staged = (git diff --cached --name-only)
if ($staged) {
  Run "git commit -m `"$Message`""
}
else {
  Write-Host "No staged changes. Creating an empty release commit: $Message" -ForegroundColor Yellow
  Run "git commit --allow-empty -m `"$Message`""
}

Run "git push $Remote $Branch"

$existing = (git tag -l $tag)
if ($existing) {
  if ($ForceTag) {
    Write-Host "Tag $tag already exists. Replacing it (--ForceTag)." -ForegroundColor Yellow
    Run "git tag -d $tag"
    Run "git push $Remote :refs/tags/$tag"
  }
  else {
    throw "Tag $tag already exists. 새 버전으로 진행하거나 -ForceTag(비권장) 사용."
  }
}

Run "git tag -a $tag -m `"$tag`""
Run "git push $Remote $tag"

Write-Host ""
Write-Host "✅ DONE: pushed $tag (and $Branch)." -ForegroundColor Green
Write-Host "   main push 후 build-check가 수행되고, 태그 push 시 windows-release-build가 실행됩니다." -ForegroundColor Green