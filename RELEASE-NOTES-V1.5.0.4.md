# Accounts v1.5.0.4 — PDF address import

Fixes customer address extraction from the redesigned BookingSystem invoice.
The PDF text stream places invoice metadata after the client's contact details;
these lines were previously included in the address field.

- Stop address extraction at invoice number/date metadata or invoice page markers.
- Preserve genuine multiline customer addresses.
- Leave an absent customer address blank and show a review warning.
- Retain the previous invoice layout's address extraction.
- Rejoin a UK postcode wrapped across two PDF lines.
- Keep manual upload, pre-save review, next Accounts numbering, duplicate checks
  and PDF recreation unchanged.

No database migration. Existing saved records are not altered. The uploaded
customer PDF and its contact details are not included in this source package.

This update was compared with GitHub main, which matched the v1.5.0.3 base.
Deployment to TrueNAS is a separate step; commands are in the deployment notes.

Validation: all 57 backend tests passed. Both supplied PDFs were also parsed
directly: customer address presence/absence, wedding dates, package counts and
£699 total / £100 paid / £599 outstanding were verified. No frontend changes.
