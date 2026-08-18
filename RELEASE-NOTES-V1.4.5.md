# Weddings By Mark Accounts V1.4.5

Build: `2026.08.18-old-accounts-migration-ready-v1.4.5`

This cumulative release includes all V1.4 through V1.4.4 changes and adds a
purpose-built, guarded migration tool for the retired Emergent Accounts app.

- Validates the agreed source inventory: 103 invoices, 153 expense records,
  40 mileage trips and one recurring-expense template.
- Imports all 103 invoice records while preserving original numbers and source
  PDFs privately for the later chronological renumbering.
- Imported invoices are excluded from income totals because the bank ledger is
  the authoritative cash-basis income source.
- Considers only the 60 genuine manual expense records. The 93 old bank-linked
  classification duplicates are never imported as extra expenses.
- Links a manual receipt to an existing bank expense only when date and amount
  identify a unique transaction. Ambiguous or unmatched records are retained
  with their files but excluded pending review.
- Imports all 40 mileage trips with their original dates, distances, rates and
  claim amounts.
- Imports the recurring-expense template.
- Never imports or alters the retired app's bank statements or bank
  transactions.
- Uses deterministic record IDs, duplicate checks, a stable preview digest,
  exact confirmation text and verified pre-migration backups.
- Writes permanent JSON and CSV migration audits.
- Adds a manual-expense totals toggle so an unmatched imported record can be
  reviewed before being included.
- Adds tax year 2022/23 to historical invoice filtering.

No YAML changes are required. Booking integration remains disabled and is not
contacted by the migration.
