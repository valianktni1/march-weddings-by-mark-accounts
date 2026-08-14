# Booking-system integration (disabled by default)

## Purpose

The booking system remains the source of truth for wedding quotes, invoices and payments. This accounts app receives a mirrored tracking record.

The integration:

- does not create booking-system invoice numbers;
- does not email clients;
- does not create or change portal links;
- does not modify booking-system records;
- does not add mirrored invoices to income totals by default, preventing duplicated bank income;
- processes each `event_id` once.

## Endpoint

`POST /api/integrations/booking/invoices/sync`

Required header:

`X-Accounts-Integration-Key: <long random shared secret>`

Example body:

```json
{
  "event_id": "invoice-updated:booking-invoice-id:revision-3",
  "source_invoice_id": "booking-invoice-id",
  "invoice_number": "WBM02059",
  "couple_names": "Example Couple",
  "client_email": "couple@example.invalid",
  "wedding_date": "2027-08-21",
  "venue": "Example Venue",
  "package_name": "Gold Package",
  "description": "Full package and add-on wording",
  "total_price": 1099.0,
  "due_date": "2027-07-07",
  "status": "part_paid",
  "payments": [
    {
      "id": "payment-id",
      "amount": 100.0,
      "paid_date": "2026-08-14",
      "payment_type": "bank_transfer"
    }
  ],
  "updated_at": "2026-08-14T12:00:00Z"
}
```

## Enabling it later

Generate one new random secret of at least 32 characters and place the same value in both applications. In this app set:

```yaml
BOOKING_INTEGRATION_ENABLED: "true"
BOOKING_INTEGRATION_KEY: "the-new-shared-secret"
```

Do not enable this until the accounts migration has been verified and the booking-system sender has passed its tests.
