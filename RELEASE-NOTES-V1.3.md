# Accounts 2026 V1.3 — Booking integration

- Receives exact WBM invoice numbers from BookingSystem2026 V8.10.
- Idempotent batch imports cannot duplicate or renumber linked invoices.
- Includes only genuine WBM wedding jobs in the agreed 2025/26-onward scope.
- Mirrors signed payment entries, cancellations and negative refund entries.
- Cancelled invoices show zero due while preserving original totals and history.
- Linked invoices are read-only in Accounts and stay controlled by BookingSystem2026.
- Mirrored invoices remain excluded from income totals so Tide bank credits are
  not counted twice; cash reporting continues to use real bank transaction dates.
- No email, reminder, portal or calendar action is performed.

## V1.3.1 dashboard status hotfix

- Paid, cancelled, void and refunded booking invoices are no longer shown as overdue.
- Overdue alerts now use the authoritative balance transferred by the booking system.
- Existing linked records are corrected immediately after deployment; no re-import or database edit is required.

Build: `2026.08.17-booking-status-hotfix-v1.3.1`
