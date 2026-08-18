import importlib
import os
import sys
from pathlib import Path

import fitz


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
os.environ.setdefault("DB_NAME", "accounts_pdf_test")
os.environ.setdefault("BOOKING_INTEGRATION_ENABLED", "false")

server = importlib.import_module("server")


def _pdf_text(path: Path) -> tuple[int, str]:
    with fitz.open(path) as document:
        return len(document), "\n".join(page.get_text() for page in document)


def _base_invoice() -> dict:
    return {
        "id": "invoice-test",
        "invoice_number": "WBM02419",
        "issue_date": "2024-08-13",
        "couple_names": "Example Couple",
        "client_email": "couple@example.com",
        "client_phone": "07000000000",
        "client_address": "1 Example Road, Manchester",
        "venue": "Example Wedding Venue",
        "wedding_date": "29/08/2026",
        "package_name": "Gold Package",
        "total_price": 949.0,
        "gross_received": 100.0,
        "total_refunded": 0.0,
        "amount_retained": 100.0,
        "balance_remaining": 0.0,
        "source_system": "booking_system",
        "payments": [
            {
                "id": "payment-test",
                "amount": 100.0,
                "payment_type": "bank_transfer",
                "paid_date": "2024-08-14",
            }
        ],
    }


def test_cancelled_wedding_pdf_is_clear_original_and_private(tmp_path):
    invoice = _base_invoice()
    invoice.update({
        "status": "void",
        "notes": "Imported package notes from Studio Ninja",
        "void_reason": (
            "Original Studio Ninja financial record retained. "
            "The source job was cancelled by the client."
        ),
    })
    output = tmp_path / "cancelled-wedding.pdf"

    server.generate_invoice_pdf(invoice, str(output))
    page_count, text = _pdf_text(output)

    assert page_count == 1
    assert "CANCELLED WEDDING" in text
    assert "CANCELLED WEDDING RECORD: WBM02419" in text
    assert "PAYMENT RETAINED: £100.00" in text
    assert "NO FURTHER PAYMENT DUE" in text
    assert "Payment received — Bank Transfer" in text
    assert "14/08/2024" in text
    assert "CLOSED FINANCIAL RECORD — NO PAYMENT REQUESTED" in text
    assert "Studio Ninja" not in text
    assert "See booking system" not in text
    assert "Pay by Bank Transfer" not in text


def test_genuine_void_invoice_remains_void_not_cancelled(tmp_path):
    invoice = _base_invoice()
    invoice.update({
        "status": "void",
        "void_reason": "Test invoice created in error",
        "amount_retained": 0.0,
        "gross_received": 0.0,
        "payments": [],
    })
    output = tmp_path / "void-invoice.pdf"

    server.generate_invoice_pdf(invoice, str(output))
    _, text = _pdf_text(output)

    assert "VOID INVOICE: WBM02419" in text
    assert "Invoice voided." in text
    assert "CANCELLED WEDDING RECORD" not in text
    assert "Studio Ninja" not in text
    assert "Pay by Bank Transfer" not in text


def test_active_invoice_never_exposes_private_legacy_wording(tmp_path):
    invoice = _base_invoice()
    invoice.update({
        "status": "part_paid",
        "notes": "Original Studio Ninja package record",
        "balance_remaining": 849.0,
        "final_payment_due": "2026-07-15",
    })
    output = tmp_path / "active-invoice.pdf"

    server.generate_invoice_pdf(invoice, str(output))
    _, text = _pdf_text(output)

    assert "INVOICE: WBM02419" in text
    assert "Studio Ninja" not in text
    assert "CANCELLED WEDDING" not in text
