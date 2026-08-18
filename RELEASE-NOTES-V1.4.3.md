# Weddings By Mark Accounts V1.4.3

Build: `2026.08.18-combined-bank-matching-v1.4.3`

This cumulative release includes Tax Year Close V1.4, cash reconciliation
V1.4.1, native cancelled-wedding invoices V1.4.2 and combined bank matching.

- Two or more unmatched Booking payments can be linked to one real bank-income
  transaction when their combined value agrees exactly.
- The match never creates cash income, changes an invoice or adds turnover. The
  existing bank receipt remains the single source of income.
- Used bank receipts and Booking payments cannot be linked twice.
- Cash-confirmed payments cannot also be bank-matched.
- Every match requires a private reason and exact confirmation phrase.
- Active combined matches are visible in Tax Year Close and can be undone while
  the tax year remains open.
- Create and remove actions are retained in dedicated audit collections and in
  complete application backups.
- The accountant reconciliation CSV identifies combined-bank matches clearly.
- A stale or invalid match blocks tax-year closure until corrected.

No existing bank transaction, invoice, payment, total or tax-year pack is
rewritten by deployment. No YAML changes are required.
