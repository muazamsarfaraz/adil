#!/usr/bin/env bash
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

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

SERVICE="${1:-adil-document-uploader}"

echo "Deploying $SERVICE from $REPO_ROOT ..."
cd "$REPO_ROOT"
railway up --service "$SERVICE"
