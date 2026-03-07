# FILE: scripts/set_github_merge_defaults.ps1
param(
    [Parameter(Mandatory = $true)]
    [string]$Owner,

    [Parameter(Mandatory = $true)]
    [string]$Repo
)

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "== GitHub squash merge 기본값 설정 ==" -ForegroundColor Cyan
Write-Host "대상: $Owner/$Repo"
Write-Host ""

$gh = Get-Command gh -ErrorAction SilentlyContinue
if (-not $gh) {
    throw "GitHub CLI(gh)가 설치되어 있지 않습니다."
}

$authStatus = gh auth status 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "gh auth login 으로 먼저 로그인해주세요."
}

# squash merge default:
# title   -> PR_TITLE
# message -> PR_BODY
#
# 이렇게 설정하면 GitHub의 squash merge 기본 메시지가
# 자동 갱신된 PR 제목/본문을 우선 사용하게 됩니다.
gh api `
  -X PATCH `
  "repos/$Owner/$Repo" `
  -f squash_merge_commit_title=PR_TITLE `
  -f squash_merge_commit_message=PR_BODY `
  -f allow_squash_merge=true

if ($LASTEXITCODE -ne 0) {
    throw "저장소 설정 업데이트에 실패했습니다."
}

Write-Host "완료되었습니다." -ForegroundColor Green
Write-Host "이제 squash merge 기본값은 PR 제목 + PR 본문을 사용합니다." -ForegroundColor Green
Write-Host ""
Write-Host "권장 확인 사항:" -ForegroundColor Cyan
Write-Host "1. develop -> main PR 생성" -ForegroundColor Gray
Write-Host "2. PR 본문에 자동 요약/릴리즈 노트/스쿼시 제안이 생성되는지 확인" -ForegroundColor Gray
Write-Host "3. squash merge 화면에서 기본 제목/본문이 PR 제목/본문으로 잡히는지 확인" -ForegroundColor Gray
Write-Host ""