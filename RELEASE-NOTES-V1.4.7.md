# Accounts V1.4.7 — Accounts-Numbered Booking PDF Import

## What changed

- A manually uploaded BookingSystem2026 invoice is now recreated with the next available Accounts invoice number.
- The recreated invoice keeps the uploaded PDF's pages, branding, spacing, line items, payment schedule and footer; only printed occurrences of the invoice number are changed.
- The original Booking invoice number and untouched source PDF are retained privately for audit evidence and duplicate protection.
- The import review screen clearly separates the private Booking PDF number from the new Accounts number.
- The Accounts number is allocated only when **Create Accounts Invoice** is pressed, so previewing a PDF does not consume a number.
- Future manual imports use an atomic Accounts sequence and skip any number already present.
- Uploading the same Booking invoice number or same PDF twice is blocked.

## Safety and compatibility

- Existing invoices are not migrated, renumbered or regenerated.
- The existing manually imported WBM01205 record remains unchanged.
- Booking-to-Accounts automatic integration is unchanged and remains controlled by `BOOKING_INTEGRATION_ENABLED`. Keep it set to `false`.
- No database migration command is required; indexes and the numbering counter are created safely on startup.

## Build

`2026.08.19-accounts-renumbered-pdf-import-v1.4.7`
