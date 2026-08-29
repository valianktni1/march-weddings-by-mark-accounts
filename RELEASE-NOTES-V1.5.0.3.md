# Accounts V1.5.0.3 - Booking invoice recreation correction

## What was wrong

- The Booking PDF duplicate check compared its source number with Accounts' own visible invoice numbers.
- Accounts already has a genuine Accounts invoice numbered `WBM01208`, so Rebecca & Adam's new BookingSystem invoice with the same source number was rejected before Accounts could allocate its next free number.

## What changed

- A Booking PDF is now a duplicate only when the retained Booking source number or the exact PDF fingerprint has already been imported.
- A matching Accounts-owned display number no longer blocks a different Booking invoice.
- After review, the invoice is recreated with the next free chronological Accounts number.
- Accounts retains only the source number and one-way PDF fingerprint for duplicate protection. It does not store the original BookingSystem PDF.
- Redundant source-PDF copies left by earlier manual imports are removed on startup; their source number and fingerprint remain for safe duplicate protection.
- The recreated PDF title metadata is changed to the new Accounts number as well as the printed invoice number.
- Every future tax-year evidence pack excludes all BookingSystem-linked invoice PDFs and any legacy source-PDF path. Only the Accounts-owned, renumbered invoice PDF can be placed in the accountant's invoice evidence folder.

## Safety

- Existing Accounts invoice numbers, recreated PDFs, payments, tax records and account records are unchanged.
- No database migration command is required.
- Automatic Booking integration remains disabled and unchanged.
- Genuine repeat imports remain blocked.
- The tax-pack protection applies to the older linked Booking invoices already in Accounts as well as future records.

## Build

`2026.08.28-booking-invoice-recreation-v1.5.0.3`
