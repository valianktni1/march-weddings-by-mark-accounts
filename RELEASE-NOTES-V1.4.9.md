# Accounts V1.4.9 — Close Checks Action Centre and Historical Tidy-up

## What changed

- Tax Year Close now shows every affected record instead of only five examples.
- Each expense-related blocker or warning has a **Review & fix** action in the same screen.
- Manual expenses can be marked paid personally, categorised, excluded, linked to the exact matching bank payment, or deleted when genuinely duplicated.
- Missing receipts can be attached directly from the Action Centre.
- Several similar uncategorised expenses can be selected and categorised together.
- Equipment purchases can be recorded as **Reviewed — keep current treatment** or **Flag for accountant / capital review**. The decision is audited and does not make an automatic tax judgement.
- A new **Tidy Up** dashboard checks every populated tax year and shows blockers, warnings, affected records and the exact outstanding checks.
- Opening a year from Tidy Up takes the administrator straight to that year’s Action Centre.

## Safety and compatibility

- Existing invoices, invoice numbering, payments, expenses, receipts, statements, mileage and evidence packs are unchanged.
- Linking a manual expense to a bank payment retains the receipt record but counts the bank payment only once.
- Existing personally-paid expense behaviour is preserved.
- Closed tax years remain protected and must be deliberately reopened before a record can change.
- Review actions are included in complete application backups.
- Booking integration remains disabled and unchanged.
- No database migration command is required; the new audit index is created safely on startup.

## Build

`2026.08.21-close-check-action-centre-v1.4.9`
