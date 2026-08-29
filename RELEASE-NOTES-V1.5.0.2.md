# Accounts V1.5.0.2 - Booking source-number collision hotfix

## What was wrong

- Accounts correctly assigned its own chronological invoice numbers, but its pre-import duplicate check also compared the BookingSystem source number with the visible Accounts number.
- Once the Accounts sequence reached a number also used by BookingSystem, a genuinely new Booking PDF could be mistaken for an invoice already imported.
- WBM01208 exposed this collision because WBM01208 already exists in the Accounts-owned WBM01101-WBM01210 range.

## What changed

- A Booking PDF is now considered a duplicate when its retained Booking source number matches, or when the exact source PDF fingerprint matches.
- The older V1.4.6 fallback remains protected for the one legacy manual import that did not yet have a separate source-number field.
- A visible Accounts number matching a different Booking source number no longer blocks the import.
- The accepted PDF is still recreated under the next free Accounts number and its original Booking PDF is retained privately.
- The Accounts copy's PDF title metadata is updated as well, so a browser or PDF viewer cannot display the old Booking number while viewing the renumbered copy.

## Safety

- No existing invoice number, PDF, payment, tax record or account record is changed.
- No database migration is required.
- Automatic Booking integration remains disabled and unchanged.
- Genuine repeat imports remain blocked by both source number and PDF fingerprint.

## Build

`2026.08.28-booking-source-number-collision-v1.5.0.2`
