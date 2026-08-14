# Secure Foundation V1

## Completed

- Removed the Emergent runtime key and package dependency.
- Removed Emergent browser scripts, visual-edit tooling and PostHog tracking.
- Added administrator login, signed HttpOnly session cookies, strict same-site cookies, CSRF checks and login throttling.
- Added security headers, private/no-index directives and an internal-only MongoDB service.
- Added MongoDB authentication and removed the backend host port from the TrueNAS staging stack.
- Added complete backup/restore coverage for invoices, expenses, transactions, bank statements, settings, mileage, recurring expenses, integration events and uploaded files.
- Added restore size limits, ZIP path validation, filename validation and automatic pre-restore rollback backups.
- Replaced Emergent AI bank-statement parsing with an optional direct Gemini key; Tide CSV parsing remains fully local.
- Added a disabled-by-default, idempotent booking-invoice synchronisation endpoint.
- Added a responsive login and navigation layout.
- Added separate staging datasets and a migration guide that does not touch the live application.

## Verification

- Backend compiled successfully.
- Eight security/integration tests passed.
- Frontend production build compiled successfully.
- Both YAML files parsed successfully.
- Clean package scanned with no embedded API key or password.

## Intentionally not done

- No live containers were changed.
- No live MongoDB data or uploaded files were read, copied or migrated.
- The domain was not switched.
- Booking synchronisation was not enabled.
- No client emails were sent.
