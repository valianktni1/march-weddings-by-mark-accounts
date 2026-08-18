import asyncio
import importlib
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

os.environ.update(
    {
        "APP_ENV": "testing",
        "APP_URL": "http://localhost",
        "ALLOWED_HOSTS": "localhost,127.0.0.1",
        "CORS_ORIGINS": "http://localhost",
        "COOKIE_SECURE": "false",
        "SESSION_SECRET": "test-session-secret-that-is-long-enough",
        "ADMIN_EMAIL": "mark@perfectweddingsbymark.uk",
        "ADMIN_PASSWORD": "correct-test-password",
        "MONGO_URL": "mongodb://127.0.0.1:27017",
        "DB_NAME": "accounts_security_test",
        "BOOKING_INTEGRATION_ENABLED": "false",
    }
)

server = importlib.import_module("server")


class DummyRequest:
    def __init__(self, path="/", method="GET", headers=None, session=None):
        self.url = SimpleNamespace(path=path)
        self.method = method
        self.headers = headers or {}
        self.session = session or {}
        self.client = SimpleNamespace(host="127.0.0.1")


def test_financial_api_requires_authentication():
    async def run():
        response = await server.protect_application(
            DummyRequest(path="/api/invoices"),
            lambda _: None,
        )
        assert response.status_code == 401

    asyncio.run(run())


def test_wrong_password_is_rejected():
    async def run():
        request = DummyRequest(path="/api/auth/login", method="POST")
        credentials = server.LoginRequest(email="mark@perfectweddingsbymark.uk", password="wrong")
        try:
            await server.login(credentials, request)
        except server.HTTPException as error:
            assert error.status_code == 401
        else:
            raise AssertionError("Wrong password was accepted")

    asyncio.run(run())


def test_login_creates_private_session_and_csrf_token():
    async def run():
        request = DummyRequest(path="/api/auth/login", method="POST")
        credentials = server.LoginRequest(
            email="mark@perfectweddingsbymark.uk",
            password="correct-test-password",
        )
        result = await server.login(credentials, request)
        assert result["csrf_token"]
        assert request.session["admin_email"] == "mark@perfectweddingsbymark.uk"
        assert request.session["csrf_token"] == result["csrf_token"]

        me = await server.auth_me(request)
        assert me["email"] == "mark@perfectweddingsbymark.uk"

    asyncio.run(run())


def test_mutation_without_csrf_is_blocked():
    async def run():
        response = await server.protect_application(
            DummyRequest(
                path="/api/settings",
                method="POST",
                session={"admin_email": "mark@perfectweddingsbymark.uk", "csrf_token": "expected"},
            ),
            lambda _: None,
        )
        assert response.status_code == 403

    asyncio.run(run())


def test_booking_integration_is_disabled_by_default():
    async def run():
        response = await server.protect_application(
            DummyRequest(
                path="/api/integrations/booking/health",
                headers={"x-accounts-integration-key": "not-enabled"},
            ),
            lambda _: None,
        )
        assert response.status_code == 401

    asyncio.run(run())


def test_booking_invoice_sync_is_idempotent_and_preserves_payments():
    class Result:
        def __init__(self, matched_count=1):
            self.matched_count = matched_count

    class Collection:
        def __init__(self):
            self.rows = []

        async def find_one(self, query, projection=None):
            for row in self.rows:
                if all(row.get(key) == value for key, value in query.items()):
                    return dict(row)
            return None

        async def update_one(self, query, update, upsert=False):
            for row in self.rows:
                if all(row.get(key) == value for key, value in query.items()):
                    row.update(update.get("$set", {}))
                    return Result()
            if upsert:
                self.rows.append({**query, **update.get("$set", {})})
                return Result(matched_count=0)
            return Result(matched_count=0)

        async def insert_one(self, document):
            self.rows.append(dict(document))
            return Result()

    class FakeDB:
        def __init__(self):
            self.invoices = Collection()
            self.integration_events = Collection()
            self.invoice_audit_logs = Collection()

    async def run():
        original_db = server.db
        original_upload = server.UPLOAD_DIR
        original_pdf = server.generate_invoice_pdf
        try:
            fake_db = FakeDB()
            server.db = fake_db
            with tempfile.TemporaryDirectory() as folder:
                server.UPLOAD_DIR = Path(folder)
                server.generate_invoice_pdf = lambda data, output: Path(output).write_bytes(b"test-pdf")
                payload = server.BookingInvoiceSync(
                    event_id="event-invoice-123-revision-2",
                    source_invoice_id="invoice-123",
                    source_booking_id="booking-123",
                    invoice_number="WBM02059",
                    legacy_invoice_number="WBM01647",
                    issue_date="2026-08-14",
                    couple_names="Example Couple",
                    wedding_date="2027-08-21",
                    total_price=1000,
                    due_date="2027-07-07",
                    status="part_paid",
                    payments=[
                        {"id": "payment-1", "amount": 100, "paid_date": "2026-08-14"},
                        {"id": "payment-2", "amount": 50, "paid_date": "2026-09-01"},
                    ],
                )
                first = await server.sync_booking_invoice(payload)
                assert first["status"] == "synchronised"
                assert first["invoice"]["amount_paid"] == 150
                assert first["invoice"]["balance_remaining"] == 850
                assert len(first["invoice"]["payments"]) == 2
                assert first["invoice"]["include_in_totals"] is False
                assert first["invoice"]["gross_received"] == 150
                assert first["invoice"]["total_refunded"] == 0
                assert first["invoice"]["issue_date"] == "2026-08-14"
                assert first["invoice"]["legacy_invoice_number"] == "WBM01647"

                second = await server.sync_booking_invoice(payload)
                assert second["status"] == "already_processed"
                assert len(fake_db.invoices.rows) == 1
                assert len(fake_db.integration_events.rows) == 1

                renumbered = payload.model_copy(update={
                    "event_id": "event-invoice-123-chronological-number",
                    "invoice_number": "WBM02001",
                })
                renumbered_result = await server.sync_booking_invoice(renumbered)
                assert renumbered_result["invoice"]["invoice_number"] == "WBM02001"
                assert len(fake_db.invoices.rows) == 1
                assert not (Path(folder) / "invoices" / "WBM02059.pdf").exists()
                assert (Path(folder) / "invoices" / "WBM02001.pdf").exists()

                admin_request = DummyRequest(session={"admin_email": "mark@perfectweddingsbymark.uk"})
                accounts_invoice_id = renumbered_result["invoice"]["id"]
                edited = await server.emergency_edit_linked_invoice(
                    accounts_invoice_id,
                    {"reason": "Corrected after checking the original invoice", "total_price": 950},
                    admin_request,
                )
                assert edited["total_price"] == 950
                assert edited["balance_remaining"] == 800
                assert edited["accounts_override"]["active"] is True
                assert edited["accounts_override"]["action"] == "edit"

                booking_changed = renumbered.model_copy(update={
                    "event_id": "event-invoice-123-booking-change-during-override",
                    "total_price": 1100,
                })
                preserved = await server.sync_booking_invoice(booking_changed)
                assert preserved["status"] == "synchronised"
                assert preserved["manual_override_preserved"] is True
                assert preserved["invoice"]["total_price"] == 950
                assert preserved["invoice"]["booking_source_snapshot"]["total_price"] == 1100

                voided = await server.void_accounts_invoice(
                    accounts_invoice_id,
                    {"reason": "Emergency precaution while checking the records"},
                    admin_request,
                )
                assert voided["status"] == "void"
                assert voided["balance_remaining"] == 0
                assert voided["void_reason"] == "Emergency precaution while checking the records"

                restored = await server.restore_booking_invoice_values(
                    accounts_invoice_id,
                    {"reason": "Checks completed; return to the Booking record"},
                    admin_request,
                )
                assert restored["total_price"] == 1100
                assert restored["balance_remaining"] == 950
                assert restored["accounts_override"]["active"] is False
                assert [row["action"] for row in fake_db.invoice_audit_logs.rows] == [
                    "emergency_edit", "void", "restore_booking"
                ]

                cancelled = server.BookingInvoiceSync(
                    event_id="event-invoice-123-cancelled-refunded",
                    source_invoice_id="invoice-123",
                    source_booking_id="booking-123",
                    invoice_number="WBM02001",
                    legacy_invoice_number="WBM01647",
                    issue_date="2026-08-14",
                    couple_names="Example Couple",
                    wedding_date="2027-08-21",
                    total_price=1000,
                    due_date="2027-07-07",
                    status="cancelled",
                    cancellation_date="2026-08-17",
                    cancellation_reason="Wedding cancelled and deposit returned",
                    payments=[
                        {"id": "payment-1", "amount": 100, "paid_date": "2026-08-14"},
                        {"id": "refund-1", "amount": -100, "paid_date": "2026-08-17", "payment_type": "refund"},
                    ],
                )
                cancelled_result = await server.sync_booking_invoice(cancelled)
                assert cancelled_result["invoice"]["status"] == "cancelled"
                assert cancelled_result["invoice"]["gross_received"] == 100
                assert cancelled_result["invoice"]["total_refunded"] == 100
                assert cancelled_result["invoice"]["amount_retained"] == 0
                assert cancelled_result["invoice"]["balance_remaining"] == 0
                assert len(fake_db.invoices.rows) == 1
        finally:
            server.db = original_db
            server.UPLOAD_DIR = original_upload
            server.generate_invoice_pdf = original_pdf

    asyncio.run(run())


def test_dashboard_overdue_balance_honours_booking_status_and_balance():
    assert server._invoice_outstanding_balance({
        "status": "paid",
        "total_price": 899,
        "balance_remaining": 799,
    }) == 0
    assert server._invoice_outstanding_balance({
        "status": "cancelled",
        "total_price": 899,
        "balance_remaining": 799,
    }) == 0
    assert server._invoice_outstanding_balance({
        "status": "void",
        "total_price": 899,
    }) == 0
    assert server._invoice_outstanding_balance({
        "status": "part_paid",
        "total_price": 899,
        "balance_remaining": 499,
    }) == 499


def test_complete_backup_collection_list():
    assert set(server.BACKUP_COLLECTIONS) >= {
        "invoices",
        "expenses",
        "transactions",
        "bank_statements",
        "settings",
        "mileage",
        "recurring_expenses",
        "integration_events",
        "invoice_audit_logs",
    }


def test_invoice_controls_are_present_in_the_admin_interface():
    source = (BACKEND_DIR.parent / "frontend" / "src" / "pages" / "Invoices.jsx").read_text()
    assert "/emergency-edit" in source
    assert "/${route}" in source
    assert "Void in Accounts" in source
    assert "Restore Booking Values" in source
    assert "ACCOUNTS OVERRIDE" in source


def test_date_and_backup_filename_validation():
    assert server.format_date_uk("2027-08-21") == "21/08/2027"
    assert server.BACKUP_FILENAME_RE.fullmatch("weddings_by_mark_backup_20260814_120000.zip")
    assert not server.BACKUP_FILENAME_RE.fullmatch("../../etc/passwd")


if __name__ == "__main__":
    tests = [value for name, value in globals().items() if name.startswith("test_") and callable(value)]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"{len(tests)} tests passed")
