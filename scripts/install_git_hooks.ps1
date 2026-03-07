# FILE: scripts/install_git_hooks.ps1
$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "== Git hooks path setting ==" -ForegroundColor Cyan

git rev-parse --show-toplevel *> $null
if ($LASTEXITCODE -ne 0) {
    throw "현재 위치가 Git 저장소가 아닙니다."
}

if (-not (Test-Path ".githooks")) {
    New-Item -ItemType Directory -Path ".githooks" | Out-Null
}

if (-not (Test-Path "scripts")) {
    New-Item -ItemType Directory -Path "scripts" | Out-Null
}

if (-not (Test-Path ".githooks/prepare-commit-msg")) {
    throw ".githooks/prepare-commit-msg 파일이 없습니다."
}

if (-not (Test-Path "scripts/commit_message_helper.py")) {
    throw "scripts/commit_message_helper.py 파일이 없습니다."
}

# 핵심: hook 파일을 LF / UTF-8 no BOM 형태로 다시 씀
$hookPath = Resolve-Path ".githooks/prepare-commit-msg"
$hookContent = Get-Content $hookPath -Raw
$hookContent = $hookContent -replace "`r`n", "`n"
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($hookPath, $hookContent, $utf8NoBom)

git config core.hooksPath .githooks

Write-Host "Git hooks path가 '.githooks' 로 설정되었습니다." -ForegroundColor Green
Write-Host "prepare-commit-msg hook를 LF/UTF-8(no BOM)로 정규화했습니다." -ForegroundColor Green
Write-Host ""
Write-Host "이제 'git commit' 실행 시 커밋 메시지 선택 메뉴가 자동으로 표시됩니다." -ForegroundColor Green
Write-Host "단, 'git commit -m ""...""' 처럼 메시지를 직접 주면 helper는 뜨지 않습니다." -ForegroundColor Yellow
Write-Host ""
Write-Host "테스트 명령:" -ForegroundColor Cyan
Write-Host "  git add ." -ForegroundColor Gray
Write-Host "  git commit" -ForegroundColor Gray
Write-Host ""