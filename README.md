# Weddings By Mark Accounts 2026

Independent, self-hosted accounts manager for Weddings By Mark. This secure successor is based on the original application but has no Emergent runtime dependency.

## Included

- Invoices and payment tracking
- Expenses, receipt uploads and recurring expenses
- Mileage calculations
- Tide CSV and optional Gemini PDF/image bank-statement parsing
- Bank transactions and UK tax-year summaries
- Complete backup/restore, including mileage, settings, recurring expenses and uploaded files
- Administrator login, signed secure sessions, CSRF protection and login throttling
- Disabled-by-default API for synchronising invoices from the booking system
- Mobile and desktop navigation

## Important safety rules

- Never commit `.env` files, passwords, API keys, database dumps or account backups.
- Deploy the replacement alongside the existing accounts app first.
- Keep `BOOKING_INTEGRATION_ENABLED=false` until both systems have been tested.
- Do not switch `accounts.weddingsbymark.co.uk` until record counts and totals match.

## Deployment

Use `docker-compose-truenas.yml` as the Dockge template. Replace every `CHANGE_TO_...`, `YOUR-TRUENAS-IP` and `REPLACE-WITH-NEW-CLEAN-REPO` value before deployment.

The staging defaults are deliberately separate from the live Emergent installation:

- Port: `30050`
- MongoDB: `/mnt/apps/newaccounts-v2/mongodb`
- Files/backups: `/mnt/temp-tntermediate/newaccounts-v2/data`

See `TRUENAS-STAGING-AND-MIGRATION.md` for the exact safe deployment and migration sequence.

## Integration contract

See `docs/BOOKING-INTEGRATION.md`. The endpoint is authenticated with its own long random key, is idempotent, never sends client email and never modifies the booking-system database.
