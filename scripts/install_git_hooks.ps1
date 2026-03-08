# FILE: scripts/install_git_hooks.ps1
$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "== Git hooks / editor setup ==" -ForegroundColor Cyan

git rev-parse --show-toplevel *> $null
if ($LASTEXITCODE -ne 0) {
    throw "현재 위치가 Git 저장소가 아닙니다."
}

$repoRoot = (git rev-parse --show-toplevel).Trim()
Set-Location $repoRoot

if (-not (Test-Path ".githooks")) {
    New-Item -ItemType Directory -Path ".githooks" | Out-Null
}

if (-not (Test-Path "scripts")) {
    New-Item -ItemType Directory -Path "scripts" | Out-Null
}

if (-not (Test-Path "scripts/commit_message_helper.py")) {
    throw "scripts/commit_message_helper.py 파일이 없습니다."
}

if (-not (Test-Path "scripts/git_editor_wrapper.py")) {
    throw "scripts/git_editor_wrapper.py 파일이 없습니다."
}

$hookContent = @'
#!/bin/sh
MSG_FILE="$1"
SOURCE="$2"

if [ -z "$MSG_FILE" ]; then
  exit 0
fi

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
if [ -z "$REPO_ROOT" ]; then
  exit 0
fi

if [ -e /dev/tty ]; then
  if command -v py >/dev/null 2>&1; then
    py -3 "$REPO_ROOT/scripts/commit_message_helper.py" "$MSG_FILE" "$SOURCE" < /dev/tty > /dev/tty 2>&1
    exit $?
  fi

  if command -v python >/dev/null 2>&1; then
    python "$REPO_ROOT/scripts/commit_message_helper.py" "$MSG_FILE" "$SOURCE" < /dev/tty > /dev/tty 2>&1
    exit $?
  fi
fi

exit 0
'@

$hookPath = Join-Path $repoRoot ".githooks/prepare-commit-msg"
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$hookContentLf = $hookContent -replace "`r`n", "`n"
[System.IO.File]::WriteAllText($hookPath, $hookContentLf, $utf8NoBom)

$gitattributesPath = Join-Path $repoRoot ".gitattributes"
$attrLines = @()
if (Test-Path $gitattributesPath) {
    $attrLines = Get-Content $gitattributesPath -Encoding UTF8
}

$needHookRule = $true
$needShRule = $true

foreach ($line in $attrLines) {
    $trimmed = $line.Trim()
    if ($trimmed -eq ".githooks/* text eol=lf") {
        $needHookRule = $false
    }
    if ($trimmed -eq "*.sh text eol=lf") {
        $needShRule = $false
    }
}

$newAttrLines = @($attrLines)
if ($needHookRule) {
    $newAttrLines += ".githooks/* text eol=lf"
}
if ($needShRule) {
    $newAttrLines += "*.sh text eol=lf"
}

$attrContent = (($newAttrLines | Where-Object { $_ -ne $null }) -join "`n").TrimEnd() + "`n"
[System.IO.File]::WriteAllText($gitattributesPath, $attrContent, $utf8NoBom)

git config core.hooksPath .githooks
git config core.editor "py -3 scripts/git_editor_wrapper.py"

Write-Host "Git hooks path가 '.githooks' 로 설정되었습니다." -ForegroundColor Green
Write-Host "prepare-commit-msg hook를 LF/UTF-8(no BOM)로 재생성했습니다." -ForegroundColor Green
Write-Host ".gitattributes에 hooks LF 고정 규칙을 반영했습니다." -ForegroundColor Green
Write-Host "core.editor를 'py -3 scripts/git_editor_wrapper.py' 로 설정했습니다." -ForegroundColor Green
Write-Host ""
Write-Host "권장 후속 명령:" -ForegroundColor Cyan
Write-Host "  git add --renormalize .githooks .gitattributes" -ForegroundColor Gray
Write-Host "  git add scripts/commit_message_helper.py scripts/git_editor_wrapper.py scripts/install_git_hooks.ps1" -ForegroundColor Gray
Write-Host "  git commit" -ForegroundColor Gray
Write-Host ""