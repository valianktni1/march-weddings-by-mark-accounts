import importlib
import os
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("APP_ENV", "testing")
os.environ.setdefault("APP_URL", "http://localhost")
os.environ.setdefault("ALLOWED_HOSTS", "localhost,127.0.0.1")
os.environ.setdefault("CORS_ORIGINS", "http://localhost")
os.environ.setdefault("COOKIE_SECURE", "false")
os.environ.setdefault("SESSION_SECRET", "test-session-secret-that-is-long-enough")
os.environ.setdefault("ADMIN_EMAIL", "mark@perfectweddingsbymark.uk")
os.environ.setdefault("ADMIN_PASSWORD", "correct-test-password")
os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "accounts_invoice_import_test")
os.environ.setdefault("BOOKING_INTEGRATION_ENABLED", "false")

server = importlib.import_module("server")


BOOKING_INVOICE_TEXT = """
Mark Adam Powell
INVOICE
BILL TO
Number   WBM01205
Issue date   18 August 2026
Booking fee due   19 August 2026
Final balance due   31 March 2027
Supply date   15 May 2027
Example Couple
couple@example.com
07000000000
14 Example Close, Manchester, M22 5SS
DESCRIPTION
AMOUNT
Bronze Package 1 2026/27/28
£475.00
Half Day Photography
- Up to 4 hours coverage
- Ceremony photos
- Minimum of 300+ photos
A £100 deposit secures your date.
2 extra hours — 1 Photographer
£155.00
2 Extra hours for 1 photographer
Subtotal
£630.00
VAT
£0.00
Paid
£100.00
TOTAL OUTSTANDING
£530.00
PAYMENT SCHEDULE
"""


def test_booking_invoice_parser_extracts_number_money_dates_and_full_items():
    result = server.parse_booking_invoice_text(BOOKING_INVOICE_TEXT)

    assert result["ready_for_review"] is True
    assert result["invoice_number"] == "WBM01205"
    assert result["issue_date"] == "18/08/2026"
    assert result["wedding_date"] == "15/05/2027"
    assert result["final_payment_due"] == "31/03/2027"
    assert result["couple_names"] == "Example Couple"
    assert result["client_email"] == "couple@example.com"
    assert result["client_phone"] == "07000000000"
    assert result["total_price"] == 630.0
    assert result["deposit_amount"] == 100.0
    assert result["balance_remaining"] == 530.0
    assert result["deposit_paid_date"] == "18/08/2026"
    assert len(result["line_items"]) == 2
    assert result["line_items"][0]["description"] == "Bronze Package 1 2026/27/28"
    assert result["line_items"][0]["amount"] == 475.0
    assert "Up to 4 hours coverage" in result["line_items"][0]["detail"]
    assert result["line_items"][1]["description"] == "2 extra hours — 1 Photographer"
    assert result["line_items"][1]["amount"] == 155.0
    assert "Bronze Package 1" in result["notes"]
    assert "2 extra hours" in result["notes"]


def test_frontend_requires_review_before_manual_pdf_import():
    source = (BACKEND_DIR.parent / "frontend" / "src" / "pages" / "Invoices.jsx").read_text()

    assert "/invoices/import-pdf" in source
    assert "nothing is saved yet" in source
    assert "review before saving" in source
    assert "original PDF" in source

