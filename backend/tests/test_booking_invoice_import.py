import importlib
import asyncio
import inspect
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
    assert "Next available number — assigned on Save" in source
    assert "Create Accounts Invoice" in source
    assert "ACCOUNTS COPY" in source


def test_accounts_sequence_ignores_booking_and_old_source_numbers():
    invoices = [
        {"invoice_number": "WBM01104"},
        {"invoice_number": "WBM01109", "source_system": "old_accounts"},
    ]

    assert server._highest_accounts_invoice_number(invoices) == 1109


def test_public_invoice_hides_private_source_evidence_fields():
    public = server._public_invoice({
        "invoice_number": "WBM01110",
        "source_invoice_number": "WBM02545",
        "source_pdf_path": "/private/source.pdf",
        "source_pdf_sha256": "abc123",
    })

    assert public == {"invoice_number": "WBM01110"}


def test_manual_import_duplicate_check_allows_accounts_number_source_collision():
    class FakeInvoices:
        def __init__(self):
            self.queries = []

        async def find_one(self, query, projection=None):
            self.queries.append(query)
            if "$or" in query:
                return None
            return {
                "invoice_number": "WBM01208",
                "source_invoice_number": "WBM02577",
            }

    fake = FakeInvoices()

    duplicate = asyncio.run(
        server._find_manual_pdf_duplicate(fake, "WBM01208", "new-pdf-hash")
    )

    assert duplicate is None
    assert fake.queries[1]["invoice_number"] == "WBM01208"


def test_manual_import_duplicate_check_keeps_v146_legacy_protection():
    class FakeInvoices:
        async def find_one(self, query, projection=None):
            if "$or" in query:
                return None
            return {"invoice_number": "WBM01205"}

    duplicate = asyncio.run(
        server._find_manual_pdf_duplicate(FakeInvoices(), "WBM01205", "changed-pdf-hash")
    )

    assert duplicate == {"invoice_number": "WBM01205"}


def test_manual_import_duplicate_check_blocks_same_retained_source_number():
    class FakeInvoices:
        async def find_one(self, query, projection=None):
            return {
                "invoice_number": "WBM01207",
                "source_invoice_number": "WBM02577",
            }

    duplicate = asyncio.run(
        server._find_manual_pdf_duplicate(FakeInvoices(), "WBM02577", "new-pdf-hash")
    )

    assert duplicate["invoice_number"] == "WBM01207"


def test_manual_import_keeps_duplicate_metadata_but_not_source_pdf_bytes():
    source = inspect.getsource(server.import_invoice_pdf)

    assert '"source_invoice_number": source_invoice_number' in source
    assert '"source_pdf_sha256": source_pdf_sha256' in source
    assert "source_pdf_path" not in source
    assert "source_pdf_preserved" not in source
    assert "source-booking-pdfs" not in source


def test_existing_manual_source_pdf_copies_are_removed(monkeypatch):
    class FakeCursor:
        async def to_list(self, _limit):
            return [{"source_pdf_path": "/managed/uploads/source.pdf"}]

    class FakeInvoices:
        def __init__(self):
            self.update = None

        def find(self, query, projection=None):
            return FakeCursor()

        async def update_one(self, query, update):
            self.update = (query, update)

    fake_invoices = FakeInvoices()
    monkeypatch.setattr(server.db, "invoices", fake_invoices)
    monkeypatch.setattr(server, "_delete_managed_upload", lambda _path: True)

    removed = asyncio.run(server._remove_manual_import_source_pdf_copies())

    assert removed == 1
    assert fake_invoices.update[0]["source_pdf_path"] == "/managed/uploads/source.pdf"
    assert "source_pdf_path" in fake_invoices.update[1]["$unset"]
    assert "source_pdf_sha256" not in fake_invoices.update[1]["$unset"]


def test_tax_pack_accepts_accounts_copy_and_rejects_booking_originals(monkeypatch, tmp_path):
    monkeypatch.setattr(server, "UPLOAD_DIR", tmp_path)
    accounts_pdf = tmp_path / "invoices" / "WBM01211.pdf"
    accounts_pdf.parent.mkdir(parents=True)
    accounts_pdf.write_bytes(b"%PDF-accounts-copy")
    booking_source = tmp_path / "invoices" / "source-booking-pdfs" / "WBM01208.pdf"
    booking_source.parent.mkdir(parents=True)
    booking_source.write_bytes(b"%PDF-booking-source")

    assert server._accounts_invoice_evidence_source({
        "source_system": "manual_pdf_import",
        "file_path": str(accounts_pdf),
    }) == accounts_pdf
    assert server._accounts_invoice_evidence_source({
        "source_system": "booking_system",
        "file_path": str(accounts_pdf),
    }) is None
    assert server._accounts_invoice_evidence_source({
        "source_system": "manual_pdf_import",
        "file_path": str(booking_source),
    }) is None


def test_recreated_pdf_keeps_layout_and_replaces_every_source_number(tmp_path):
    import pymupdf

    source_number = "WBM02545"
    accounts_number = "WBM01110"
    source = pymupdf.open()
    first = source.new_page()
    first.insert_text((72, 90), "Number", fontsize=9)
    first.insert_text((150, 90), source_number, fontsize=9)
    second = source.new_page()
    second.insert_text((72, 90), f"Please use {source_number} as your reference.", fontsize=9)
    source.set_metadata({"title": source_number})
    source_bytes = source.tobytes()
    source.close()
    output = tmp_path / f"{accounts_number}.pdf"

    replacements = server.recreate_booking_invoice_pdf(
        source_bytes, source_number, accounts_number, output
    )

    assert replacements == 2
    with pymupdf.open(output) as recreated:
        text = "\n".join(page.get_text() for page in recreated)
        assert len(recreated) == 2
        assert recreated.metadata["title"] == accounts_number
    assert source_number not in text
    assert text.count(accounts_number) == 2
