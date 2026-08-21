# Accounts V1.5.0 — Cash-flow and Navigation

## Cash-flow forecast

- A new **Cash Flow** screen shows expected money in, planned money out and net movement for the next 30, 60 and 90 days.
- Incoming money is calculated from actual outstanding invoice balances and final-payment due dates.
- Paid, cancelled, void and refunded invoices are excluded.
- An invoice without a due date is clearly listed for review and is never guessed into the forecast.
- Optional one-off or recurring planned outgoings can be added for weekly, monthly, quarterly or yearly commitments.
- An optional current bank balance enables estimated future balances.
- Forecast commitments are planning records only: they do not create expenses, transactions or tax entries.

## Navigation and daily workflow

- Back and Forward controls are available at the top of every screen.
- Whole-system search finds invoices, expenses, bank transactions, mileage and planned outgoings.
- Search results open the correct area and highlight the relevant record.
- The Dashboard includes quick actions for a new invoice, expense, planned outgoing and statement import.
- The Dashboard includes the six most recently changed records.
- Dashboard, invoice, expense, transaction and mileage filters/searches are retained in the page address, so refresh and browser navigation preserve the working view.

## Round-trip mileage

- The mileage form now has a clear **Round trip - double this mileage** option.
- Entering the one-way distance shows the full mileage and estimated claim before saving.
- The saved entry retains both the full mileage and original one-way mileage.
- Round trips are visibly labelled in the mileage table for a clear HMRC audit trail.
- Existing mileage entries are unchanged.

## Safety and compatibility

- Existing accounts records and calculations are not rewritten.
- Existing tax-year close protections remain unchanged.
- Cash-flow commitments are included in complete backups and restores.
- Booking-system integration remains disabled.
- No manual database migration is required; the new planning index is created safely at startup.

## Build

`2026.08.21-cash-flow-navigation-round-trip-v1.5.0`
