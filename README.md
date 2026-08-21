# Weddings By Mark Accounts 2026

Independent, self-hosted accounts manager for Weddings By Mark. This is a secured successor to the existing application and has no Emergent runtime dependency.

## Included

- Invoices and payment tracking
- Expenses, receipts and recurring expenses
- Personally paid business expenses that stay in tax totals without false bank-duplicate blocks
- Close Checks Action Centre with direct record fixes and receipt-to-bank linking
- Historical tidy-up dashboard covering every populated tax year
- Mileage calculations
- Tide CSV and optional direct Gemini bank-statement parsing
- Bank transactions and UK tax-year summaries
- Complete backup and restore of all records and uploaded files
- Administrator login, signed sessions, CSRF protection and login throttling
- Disabled-by-default booking-system integration API
- Responsive mobile and desktop navigation

## Agreed TrueNAS layout

- Local address: `http://192.168.24.10:30053`
- Domain: `https://accounts2026.weddingsbymark.uk`
- MongoDB data: `/mnt/apps/accounts-2026-use/mongodb`
- Invoices, receipts, statements and backups: `/mnt/nextcloud/accounts-2026-saved-data`
- Source repository: `https://github.com/valianktni1/march-weddings-by-mark-accounts`

Use `docker-compose-truenas.yml` as the complete Dockge YAML. Change every `CHANGE_TO_...` value before deployment. Do not change the repeated database password in only one place: the MongoDB password and the password inside `MONGO_URL` must match exactly.

Both the local address and HTTPS domain are allowed. `COOKIE_SECURE` is therefore set to `"false"`; otherwise an ordinary HTTP browser at the local IP cannot keep the login cookie. The cookie remains HttpOnly and SameSite Strict. Once local access is also HTTPS, change it to `"true"`.

## Important safety rules

- Keep the old accounts application running while this replacement is tested.
- Keep `BOOKING_INTEGRATION_ENABLED: "false"` until the accounts migration is verified.
- Never commit `.env` files, passwords, API keys, database archives, invoices, receipts or account backups.
- Read `SECURITY-NOTICE.md` before updating the existing GitHub repository.

The exact staging, backup, migration and verification sequence is in `TRUENAS-STAGING-AND-MIGRATION.md`.

## Booking integration

The future integration contract is documented in `docs/BOOKING-INTEGRATION.md`. It is authenticated, idempotent and deliberately switched off. No booking records or client emails are affected by deploying this package.
