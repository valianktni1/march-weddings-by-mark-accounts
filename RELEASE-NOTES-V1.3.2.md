# Accounts 2026 V1.3.2

This cumulative release prepares Accounts for the controlled chronological invoice
renumber performed by BookingSystem2026 V8.10.1.

- Existing linked invoices are matched by immutable booking invoice ID and updated
  in place, regardless of their former displayed number.
- Booking's original issue date is stored and printed on the regenerated PDF.
- The original Studio Ninja number is retained as a private UI reference.
- A successfully generated replacement PDF removes the obsolete managed filename.
- The V1.3.1 paid/cancelled/void/refunded overdue-status fix remains included.
- Linked invoices remain excluded from income totals to prevent double counting bank
  transactions, and they remain protected from manual deletion or renumbering.
