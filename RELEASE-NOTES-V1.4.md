# Accounts 2026 — Tax Year Close v1.4

Build: `2026.08.18-tax-year-close-v1.4`

## What is new

- A clean, mobile-friendly **Tax Year Close** workspace replaces the old estimated-tax screen.
- One authoritative cash-basis calculation is now used by Tax Year Close, Dashboard totals and the summary API.
- Bank-linked receipt records are supporting evidence and are no longer counted as a second expense.
- Close checks identify uncategorised expenses, likely duplicates, invalid dates, missing receipts, unmatched Booking payments, failed statements and equipment needing review.
- Transactions can be reclassified, categorised, excluded or deleted when a genuine duplicate was imported.
- Closing creates a versioned evidence ZIP containing:
  - branded annual PDF;
  - annual and quarterly figures;
  - income, expense and mileage CSV ledgers;
  - expense-category summary;
  - Booking invoice/payment audit and bank reconciliation;
  - receipt index and exceptions report;
  - available receipts, invoice PDFs and bank statements;
  - exact JSON snapshot, manifest and SHA-256 checksums.
- A closed year is locked against accidental changes to bank transactions, expenses, mileage and relevant invoice records.
- Reopening requires an exact confirmation and written reason. The old evidence pack is retained and the action is audited.
- Tax-close records and evidence packs are included in the app's portable backup/restore feature.

## Important boundaries

- This prepares an accountant-ready evidence pack. It does **not** submit Self Assessment or MTD data directly to HMRC.
- Booking-linked invoices remain supporting records; bank receipts are the primary cash-basis income source.
- Booking synchronisation and Accounts emergency overrides remain intact.
- No YAML additions or database reset are required.

## Verification completed

- 16 backend security, Booking integration, calculation and evidence-pack tests pass.
- Frontend production build compiles successfully.
- Python compilation and whitespace checks pass.
- The generated A4 annual PDF was rendered and visually checked page by page.

