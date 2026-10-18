#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
mkdir -p backups
# Ensure uid 10001 (the app container) can write to this directory during setup.
name="/backups/warehouse-$(date -u +%Y%m%dT%H%M%SZ).swh"
docker compose exec -T app python -m server.cli backup --file "$name"
# Copy backups to a separate storage destination under the operator's policy.
