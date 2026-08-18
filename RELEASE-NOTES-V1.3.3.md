# Accounts 2026 V1.3.3

This cumulative release adds controlled emergency invoice editing and voiding
without weakening the Booking-to-Accounts link.

- Accounts-created invoices can still be edited normally and can now be voided
  with a mandatory reason.
- Booking-linked invoices can be corrected in Accounts through a clearly marked
  emergency override. The Booking record is never changed.
- A later Booking synchronisation updates the saved source snapshot while leaving
  an active Accounts override untouched.
- **Restore Booking Values** removes the active override and applies the latest
  source values received from Booking.
- Every emergency edit, void and restore is written to a permanent audit history
  with the reason, administrator and timestamp.
- A voided PDF visibly records the reason and confirms that no further payment is
  due on the Accounts copy.
- Booking-linked invoices remain protected from deletion and remain excluded from
  income totals to avoid double counting bank transactions.
- No safeguard action sends client email, changes a portal or writes back to the
  Booking application.

V1.3.2 chronological numbering and V1.3.1 overdue-status handling remain included.

