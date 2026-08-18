# Weddings By Mark Accounts V1.4.4

Build: `2026.08.18-unified-expense-ledger-v1.4.4`

This cumulative release includes every change from V1.4 through V1.4.3 and
adds one complete Expenses ledger.

- Bank-statement expenses and manually entered expenses now appear together on
  the Expenses page.
- Every row is clearly labelled `Bank statement` or `Manual expense`.
- Bank expense categories can be corrected directly from the Expenses page.
  The original bank transaction is updated, so Dashboard and Tax Year Close
  figures immediately use the corrected category.
- Manual expense descriptions, suppliers and categories can also be edited.
- Bank-linked receipt records remain attached to their original transaction and
  are never displayed or totalled as a second expense.
- Search plus tax-year, source and category filters make historical expenses
  easy to drill into.
- Summary cards separate bank and manual totals and flag records which still
  need a category.
- Bank transactions cannot be deleted from the Expenses page. Only genuine
  manual records have a delete control.
- The layout remains usable on mobile, with responsive filters and a safely
  scrollable detail table.

Deployment does not alter, recategorise or delete any existing transaction or
expense. No YAML changes are required.
