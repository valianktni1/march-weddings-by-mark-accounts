# Accounts V1.4.8 - Personally Paid Expenses

## What changed

- Manual expenses now have a **Paid personally / personal credit card** option.
- Existing manual expenses can be reviewed and marked personally paid from the Expenses screen.
- New manual expenses can be marked personally paid when they are added, with or without a receipt upload.
- Personally paid expenses remain included in allowable-expense and tax-year totals.
- The Tax Year Close checker no longer falsely matches them to an unrelated business-bank payment with the same date and amount.
- Genuine unlinked manual/bank duplicates still remain blocking checks.
- Personally paid expenses are labelled clearly in the expense list and year-end evidence ledger.

## Safety and compatibility

- Existing expenses, receipts, bank statements, transactions, invoices and mileage are unchanged.
- No database migration is required. Existing records default safely to not personally paid until Mark selects the option.
- No automatic records are reclassified.
- Booking integration remains unchanged and should stay disabled.
- Existing V1.4.7 invoice import and Accounts renumbering behaviour is preserved.

## Build

`2026.08.19-paid-personally-expenses-v1.4.8`
