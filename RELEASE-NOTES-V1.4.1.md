# Weddings By Mark Accounts V1.4.1

Build: `2026.08.18-cash-payment-reconciliation-v1.4.1`

This cumulative release keeps the complete Tax Year Close V1.4 feature and adds
safe treatment for occasional cash wedding payments.

- Booking payments recorded as Cash are counted exactly once as cash-basis income.
- Existing unmatched Booking payments can be explicitly confirmed as cash inside
  Tax Year Close, with a mandatory reason and exact confirmation phrase.
- Cash confirmations can be undone while the tax year is open; both actions are
  retained in the audit trail.
- A same-date, same-value bank receipt blocks closing the year until the possible
  duplicate is resolved, preventing cash that was later deposited from being
  counted twice.
- Confirmed cash appears in the annual summary, quarterly totals, income ledger,
  reconciliation CSV and immutable evidence pack.
- App backup/restore now includes the cash confirmation and audit collections.

No existing transaction, invoice, payment, tax-year pack or Booking override is
rewritten by deployment. No YAML changes are required.
