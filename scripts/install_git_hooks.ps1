# FILE: scripts/install_git_hooks.ps1
$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "== Git hooks / editor setup ==" -ForegroundColor Cyan

git rev-parse --show-toplevel *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Current directory is not a Git repository."
}

$repoRoot = (git rev-parse --show-toplevel).Trim()
Set-Location $repoRoot

if (-not (Test-Path ".githooks")) {
    New-Item -ItemType Directory -Path ".githooks" | Out-Null
}

if (-not (Test-Path "scripts/commit_message_helper.py")) {
    throw "Missing scripts/commit_message_helper.py"
}

if (-not (Test-Path "scripts/git_editor_wrapper.py")) {
    throw "Missing scripts/git_editor_wrapper.py"
}

if (-not (Test-Path "scripts/check_mojibake.py")) {
    throw "Missing scripts/check_mojibake.py"
}

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)

$prepareCommitMsg = @'
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

if [ -t 0 ] && [ -r /dev/tty ] && [ -w /dev/tty ]; then
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

$preCommit = @'
#!/bin/sh

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
if [ -z "$REPO_ROOT" ]; then
  exit 0
fi

run_check() {
  "$1" -c "import runpy, sys; sys.argv=['scripts/check_mojibake.py']; runpy.run_path('scripts/check_mojibake.py', run_name='__main__')"
}

if [ -x "$REPO_ROOT/.venv/Scripts/python.exe" ]; then
  cd "$REPO_ROOT" && run_check "$REPO_ROOT/.venv/Scripts/python.exe"
  exit $?
fi

if command -v py >/dev/null 2>&1; then
  cd "$REPO_ROOT" && py -3 scripts/check_mojibake.py
  exit $?
fi

if command -v python >/dev/null 2>&1; then
  cd "$REPO_ROOT" && python scripts/check_mojibake.py
  exit $?
fi

echo "Python not found; skipped mojibake check." >&2
exit 0
'@

$prepareCommitMsgLf = $prepareCommitMsg -replace "`r`n", "`n"
$preCommitLf = $preCommit -replace "`r`n", "`n"
[System.IO.File]::WriteAllText((Join-Path $repoRoot ".githooks/prepare-commit-msg"), $prepareCommitMsgLf, $utf8NoBom)
[System.IO.File]::WriteAllText((Join-Path $repoRoot ".githooks/pre-commit"), $preCommitLf, $utf8NoBom)

$gitattributesPath = Join-Path $repoRoot ".gitattributes"
$attrLines = @()
if (Test-Path $gitattributesPath) {
    $attrLines = Get-Content $gitattributesPath -Encoding UTF8
}

$needed = @(
    ".githooks/* text eol=lf",
    "*.sh text eol=lf",
    "*.py text working-tree-encoding=UTF-8"
)

$newAttrLines = @($attrLines)
foreach ($line in $needed) {
    if (($newAttrLines | ForEach-Object { $_.Trim() }) -notcontains $line) {
        $newAttrLines += $line
    }
}

$attrContent = (($newAttrLines | Where-Object { $_ -ne $null }) -join "`n").TrimEnd() + "`n"
[System.IO.File]::WriteAllText($gitattributesPath, $attrContent, $utf8NoBom)

git config core.hooksPath .githooks
git config core.editor "py -3 scripts/git_editor_wrapper.py"

Write-Host "Git hooks path set to .githooks" -ForegroundColor Green
Write-Host "prepare-commit-msg and pre-commit hooks written as UTF-8(no BOM), LF." -ForegroundColor Green
Write-Host "pre-commit runs scripts/check_mojibake.py to block broken UI strings." -ForegroundColor Green
Write-Host ".gitattributes updated with hook LF and Python UTF-8 rules." -ForegroundColor Green
Write-Host "core.editor set to: py -3 scripts/git_editor_wrapper.py" -ForegroundColor Green
Write-Host ""
Write-Host "Recommended next commands:" -ForegroundColor Cyan
Write-Host "  git add --renormalize .githooks .gitattributes scripts" -ForegroundColor Gray
Write-Host "  git commit" -ForegroundColor Gray
Write-Host ""
