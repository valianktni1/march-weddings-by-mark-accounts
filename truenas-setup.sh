#!/usr/bin/env bash
set -euo pipefail

# Creates only the isolated staging folders. It does not deploy containers,
# alter the live accounts app, migrate data or write secrets.

APP_DATASET="/mnt/apps/newaccounts-v2"
FILE_DATASET="/mnt/temp-tntermediate/newaccounts-v2/data"

mkdir -p "${APP_DATASET}/mongodb"
mkdir -p "${FILE_DATASET}/uploads/invoices"
mkdir -p "${FILE_DATASET}/uploads/expenses"
mkdir -p "${FILE_DATASET}/uploads/bank_statements"
mkdir -p "${FILE_DATASET}/backups"
mkdir -p "/mnt/temp-tntermediate/newaccounts-v2/migration"

chown -R 999:999 "${APP_DATASET}/mongodb"
chown -R 10001:10001 "${FILE_DATASET}"

echo "Staging folders created."
echo "Now edit every placeholder in docker-compose-truenas.yml before deploying."
echo "The live accounts app and its data were not changed."
