# Weddings By Mark Accounts V1.4.2

Build: `2026.08.18-cancelled-invoice-stamp-v1.4.2`

This cumulative release includes Tax Year Close V1.4, cash reconciliation V1.4.1
and the revised native invoice PDFs.

- Client-cancelled weddings receive a large `CANCELLED WEDDING` banner and
  watermark.
- The retained payment and `NO FURTHER PAYMENT DUE` are shown prominently.
- The payment method and recorded payment date are itemised on linked invoices.
- Genuine void invoices remain clearly labelled `VOID INVOICE` rather than being
  misclassified as wedding cancellations.
- Customer and accountant-facing invoice PDFs contain no Studio Ninja wording.
  Private legacy references remain available internally for audit traceability.
- Existing invoice PDFs are safely regenerated into the new format the first
  time they are opened or included in a Tax Year evidence pack.
- Closed invoices no longer display bank-payment instructions.

No invoice numbers, issue dates, payments, totals, statuses or private audit
references are changed by deployment. No YAML changes are required.
