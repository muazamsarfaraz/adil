# adil-frontend-next/deploy.ps1 — deploy the Next.js frontend (askadil.org).
#
# The service's rootDirectory is UNSET, so this deploys from THIS subdir: a small,
# self-contained snapshot built straight from adil-frontend-next/ (its own
# Dockerfile + railway.toml + .railwayignore). No repo-root upload, no shared
# root-.railwayignore toggle, no .claude worktree bloat, no GitHub-build landmine.
#
# Usage:  .\adil-frontend-next\deploy.ps1   (or: cd adil-frontend-next; railway up --service adil-frontend-next)

$ErrorActionPreference = "Stop"
Push-Location $PSScriptRoot
try {
    # idempotent — links this dir to the project if not already linked
    railway link --project 3b3ce312-40a1-4fba-9367-6e2939ce4404 --environment production --service adil-frontend-next | Out-Null
    Write-Host "Deploying adil-frontend-next from its own subdir..." -ForegroundColor Cyan
    railway up --service adil-frontend-next
}
finally { Pop-Location }
