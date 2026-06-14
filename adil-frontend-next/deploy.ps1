# adil-frontend-next/deploy.ps1 — deploy the Next.js frontend (askadil.org).
#
# The service has rootDirectory=adil-frontend-next, so it deploys the REPO ROOT
# (not the subdir). The shared root .railwayignore must include ONLY
# adil-frontend-next for this upload; this script toggles it, deploys, and
# ALWAYS reverts (leaving it flipped breaks the next GitHub build of
# adil-rag-api / adil-landing — incident 2026-06-12).
#
# Usage (from anywhere):  .\adil-frontend-next\deploy.ps1
# If you see "operation timed out" on /up, that's a transient Railway
# upload-endpoint issue — just re-run (it lands intermittently).

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Push-Location $repo
try {
    $ign = Join-Path $repo ".railwayignore"
    $orig = [IO.File]::ReadAllText($ign)
    $toggled = ($orig -split "`r?`n" | ForEach-Object {
        switch ($_.Trim()) {
            "# adil-rag-api/"     { "adil-rag-api/" }       # ignore rag-api
            "adil-frontend-next/" { "# adil-frontend-next/" } # un-ignore frontend
            default              { $_ }
        }
    }) -join "`n"
    [IO.File]::WriteAllText($ign, $toggled)   # no BOM
    try {
        Write-Host "Deploying adil-frontend-next from repo root..." -ForegroundColor Cyan
        railway up --service adil-frontend-next
    }
    finally {
        git checkout -- .railwayignore
        Write-Host ".railwayignore reverted to safe state." -ForegroundColor Green
    }
}
finally { Pop-Location }
