#!/usr/bin/env pwsh
# Deploy adil-document-uploader to Railway.
#
# MUST be invoked from the repo root, not from this directory.
# Background: `railway up` from inside adil-document-uploader/ wraps the upload
# bundle in a subdirectory named after the folder, which breaks Railway's
# rootDirectory resolution (Dockerfile reported as "does not exist").
# See [[2576]] for the original incident.
#
# The service instance has rootDirectory=adil-document-uploader and
# railwayConfigFile=adil-document-uploader/railway.toml set via the Railway API.
# This wrapper just ensures we're at the repo root before invoking the CLI.

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir

Push-Location $repoRoot
try {
    $service = if ($args[0]) { $args[0] } else { "adil-document-uploader" }
    Write-Host "Deploying $service from $repoRoot ..." -ForegroundColor Cyan
    & railway up --service $service
    if ($LASTEXITCODE -ne 0) {
        throw "railway up failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}
