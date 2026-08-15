#!/usr/bin/env bash
set -euo pipefail

# Creates only the isolated staging folders. It does not deploy containers,
# alter the live accounts app, migrate data or write secrets.

APP_DATASET="/mnt/apps/accounts-2026-use"
FILE_DATASET="/mnt/nextcloud/accounts-2026-saved-data"

mkdir -p "${APP_DATASET}/mongodb"
mkdir -p "${FILE_DATASET}/uploads/invoices"
mkdir -p "${FILE_DATASET}/uploads/expenses"
mkdir -p "${FILE_DATASET}/uploads/bank_statements"
mkdir -p "${FILE_DATASET}/backups"
mkdir -p "${FILE_DATASET}/temp_restore"
mkdir -p "${FILE_DATASET}/migration"

chown -R 999:999 "${APP_DATASET}/mongodb"
chown -R 10001:10001 "${FILE_DATASET}"

echo "Staging folders created."
echo "Now edit every placeholder in docker-compose-truenas.yml before deploying."
echo "The live accounts app and its data were not changed."
