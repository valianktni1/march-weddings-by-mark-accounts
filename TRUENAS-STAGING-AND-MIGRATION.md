# Safe TrueNAS staging and migration

This process leaves the current Emergent accounts app, current MongoDB and `accounts.weddingsbymark.co.uk` untouched.

## 1. Create isolated staging storage

```bash
mkdir -p /mnt/apps/newaccounts-v2/mongodb
mkdir -p /mnt/temp-tntermediate/newaccounts-v2/data/uploads/invoices
mkdir -p /mnt/temp-tntermediate/newaccounts-v2/data/uploads/expenses
mkdir -p /mnt/temp-tntermediate/newaccounts-v2/data/uploads/bank_statements
mkdir -p /mnt/temp-tntermediate/newaccounts-v2/data/backups
chown -R 999:999 /mnt/apps/newaccounts-v2/mongodb
chown -R 10001:10001 /mnt/temp-tntermediate/newaccounts-v2/data
```

## 2. Prepare the Dockge stack

Use `docker-compose-truenas.yml`, replace all placeholder passwords/secrets, set `YOUR-TRUENAS-IP` and enter the name of the new clean repository. Leave these values unchanged during the initial test:

```yaml
COOKIE_SECURE: "false"
BOOKING_INTEGRATION_ENABLED: "false"
BOOKING_INTEGRATION_KEY: ""
```

The staging app is then available internally at `http://YOUR-TRUENAS-IP:30050`.

## 3. Back up the current MongoDB without stopping it

```bash
mkdir -p /mnt/temp-tntermediate/newaccounts-v2/migration

docker exec new-weddings-db mongodump \
  --db weddings_by_mark \
  --archive \
  --gzip \
  > /mnt/temp-tntermediate/newaccounts-v2/migration/accounts-before-v2.archive.gz

ls -lh /mnt/temp-tntermediate/newaccounts-v2/migration/accounts-before-v2.archive.gz
```

Do not continue if that backup file is empty.

## 4. Dry-check file copying

```bash
rsync -an --itemize-changes /mnt/nextcloud/newaccountsaveddata/invoices/ \
  /mnt/temp-tntermediate/newaccounts-v2/data/uploads/invoices/

rsync -an --itemize-changes /mnt/nextcloud/newaccountsaveddata/expenses/ \
  /mnt/temp-tntermediate/newaccounts-v2/data/uploads/expenses/

rsync -an --itemize-changes /mnt/nextcloud/newaccountsaveddata/bank_statements/ \
  /mnt/temp-tntermediate/newaccounts-v2/data/uploads/bank_statements/
```

These commands make no changes because they include `-n`.

## 5. Migration day

Only after staging has been tested, restore the archive into the separate v2 database. The password is read inside the container and is not printed:

```bash
docker exec -i wbm-accounts-v2-db sh -lc \
  'mongorestore --username "$MONGO_INITDB_ROOT_USERNAME" --password "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin --archive --gzip --nsFrom="weddings_by_mark.*" --nsTo="weddings_by_mark_accounts_v2.*"' \
  < /mnt/temp-tntermediate/newaccounts-v2/migration/accounts-before-v2.archive.gz
```

Then repeat the three `rsync` commands without `-n` and restore ownership:

```bash
chown -R 10001:10001 /mnt/temp-tntermediate/newaccounts-v2/data
```

## 6. Verification before switching the domain

Compare counts for invoices, expenses, transactions, bank statements, mileage, recurring expenses and settings in both MongoDB databases. Also compare uploaded-file counts and dashboard totals for every tax year.

Do not enable booking integration or change the public domain until those checks match.

## 7. Production switch (later)

After approval:

- Set `APP_URL` and `CORS_ORIGINS` to `https://accounts.weddingsbymark.co.uk`.
- Set `ALLOWED_HOSTS` to `accounts.weddingsbymark.co.uk`.
- Set `COOKIE_SECURE` to `"true"`.
- Point the reverse proxy to staging port `30050`.
- Keep the old containers and data stopped but intact for rollback.
