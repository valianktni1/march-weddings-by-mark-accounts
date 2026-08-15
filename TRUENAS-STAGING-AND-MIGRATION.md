# Safe TrueNAS staging and migration

This procedure keeps the existing accounts application live while Accounts 2026 is tested separately.

## 1. Create the agreed storage folders

```bash
mkdir -p /mnt/apps/accounts-2026-use/mongodb
mkdir -p /mnt/nextcloud/accounts-2026-saved-data/uploads/invoices
mkdir -p /mnt/nextcloud/accounts-2026-saved-data/uploads/expenses
mkdir -p /mnt/nextcloud/accounts-2026-saved-data/uploads/bank_statements
mkdir -p /mnt/nextcloud/accounts-2026-saved-data/backups
mkdir -p /mnt/nextcloud/accounts-2026-saved-data/temp_restore
mkdir -p /mnt/nextcloud/accounts-2026-saved-data/migration

chown -R 999:999 /mnt/apps/accounts-2026-use/mongodb
chown -R 10001:10001 /mnt/nextcloud/accounts-2026-saved-data
```

The included `truenas-setup.sh` creates these folders only. It does not start containers or alter the old system.

## 2. Put the complete YAML into Dockge

Use `docker-compose-truenas.yml`. Before deployment, replace:

- `CHANGE_TO_A_LONG_RANDOM_DATABASE_PASSWORD` in both locations with the same password
- `CHANGE_TO_A_DIFFERENT_LONG_RANDOM_SESSION_SECRET`
- `CHANGE_TO_A_NEW_STRONG_ADMIN_PASSWORD`

Leave these disabled:

```yaml
BOOKING_INTEGRATION_ENABLED: "false"
BOOKING_INTEGRATION_KEY: ""
```

Deploy with:

```bash
docker compose -f /mnt/apps/dockge/data/accounts-2026/compose.yaml down
docker compose -f /mnt/apps/dockge/data/accounts-2026/compose.yaml build --no-cache backend frontend
docker compose -f /mnt/apps/dockge/data/accounts-2026/compose.yaml up -d
docker compose -f /mnt/apps/dockge/data/accounts-2026/compose.yaml ps
curl -fsS http://127.0.0.1:30053/api/health
```

If your Dockge stack folder has a different name, change only `/mnt/apps/dockge/data/accounts-2026/compose.yaml` in those commands.

Test locally at `http://192.168.24.10:30053`.

## 3. Configure the domain

Create the DNS record for `accounts2026.weddingsbymark.uk`, then point the existing reverse proxy to:

```text
http://192.168.24.10:30053
```

Enable HTTPS at the reverse proxy. The application already accepts both the domain and local IP.

## 4. Back up the current accounts database

The following example uses the old container and database names recorded in the existing deployment. Check them with `docker ps` before running it.

```bash
docker exec new-weddings-db mongodump \
  --db weddings_by_mark \
  --archive \
  --gzip \
  > /mnt/nextcloud/accounts-2026-saved-data/migration/accounts-before-2026.archive.gz

ls -lh /mnt/nextcloud/accounts-2026-saved-data/migration/accounts-before-2026.archive.gz
```

Stop if the archive is empty.

## 5. Dry-run the uploaded-file transfer

```bash
rsync -an --itemize-changes /mnt/nextcloud/newaccountsaveddata/invoices/ \
  /mnt/nextcloud/accounts-2026-saved-data/uploads/invoices/

rsync -an --itemize-changes /mnt/nextcloud/newaccountsaveddata/expenses/ \
  /mnt/nextcloud/accounts-2026-saved-data/uploads/expenses/

rsync -an --itemize-changes /mnt/nextcloud/newaccountsaveddata/bank_statements/ \
  /mnt/nextcloud/accounts-2026-saved-data/uploads/bank_statements/
```

These are read-only dry runs because they include `-n`.

## 6. Restore into the separate Accounts 2026 database

Do this only after the new empty application has passed basic testing:

```bash
docker exec -i accounts-2026-db sh -lc \
  'mongorestore --username "$MONGO_INITDB_ROOT_USERNAME" --password "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin --archive --gzip --nsFrom="weddings_by_mark.*" --nsTo="weddings_by_mark_accounts_2026.*"' \
  < /mnt/nextcloud/accounts-2026-saved-data/migration/accounts-before-2026.archive.gz
```

Repeat the three `rsync` commands without `-n`, then restore ownership:

```bash
chown -R 10001:10001 /mnt/nextcloud/accounts-2026-saved-data
```

## 7. Verify before changing normal usage

Compare both systems for:

- invoice counts, totals and payment status
- expenses and uploaded receipts
- transactions and bank statements
- mileage and recurring expenses
- settings and every UK tax-year summary
- physical file counts beneath the old and new saved-data folders

Keep the old application available until these checks match. Do not enable booking integration yet.

## Local HTTP security note

`COOKIE_SECURE` is `"false"` because local access is ordinary HTTP while the public domain is HTTPS. The session remains HttpOnly and SameSite Strict. The strongest final arrangement is local HTTPS or using the HTTPS domain on the LAN; at that point change `COOKIE_SECURE` to `"true"`.
