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
os.environ.setdefault("DB_NAME", "accounts_expense_ledger_test")
os.environ.setdefault("BOOKING_INTEGRATION_ENABLED", "false")

server = importlib.import_module("server")


def test_unified_expense_ledger_includes_bank_and_manual_rows_once():
    transactions = [
        {
            "id": "bank-1",
            "date": "17/08/2026",
            "description": "Adobe",
            "amount": 19.99,
            "transaction_type": "expense",
            "category": "Software & Subscriptions",
            "tax_year": "2026-27",
            "excluded_from_totals": False,
        }
    ]
    expenses = [
        {
            "id": "receipt-1",
            "date": "17/08/2026",
            "description": "Adobe receipt",
            "amount": 19.99,
            "category": "Software & Subscriptions",
            "tax_year": "2026-27",
            "is_from_bank": True,
            "source_transaction_id": "bank-1",
            "supplier": "Adobe",
            "file_path": "/app/storage/receipt.pdf",
        },
        {
            "id": "manual-1",
            "date": "16/08/2026",
            "description": "Cash parking",
            "amount": 8.5,
            "category": "Travel & Mileage",
            "tax_year": "2026-27",
            "is_from_bank": False,
        },
    ]

    rows = server.build_expense_ledger_rows(transactions, expenses)

    assert len(rows) == 2
    assert [row["source"] for row in rows] == ["bank", "manual"]
    assert rows[0]["receipt_expense_id"] == "receipt-1"
    assert rows[0]["has_receipt"] is True
    assert sum(row["amount"] for row in rows if row["included_in_totals"]) == 28.49


def test_unified_expense_ledger_keeps_excluded_bank_amount_visible_but_out_of_totals():
    rows = server.build_expense_ledger_rows(
        [
            {
                "id": "bank-personal",
                "date": "01/05/2026",
                "description": "Personal transfer",
                "amount": 250,
                "transaction_type": "expense",
                "category": None,
                "tax_year": "2026-27",
                "excluded_from_totals": True,
            },
            {
                "id": "income-ignored",
                "date": "02/05/2026",
                "description": "Wedding payment",
                "amount": 100,
                "transaction_type": "income",
                "tax_year": "2026-27",
            },
        ],
        [],
    )

    assert len(rows) == 1
    assert rows[0]["amount"] == 250
    assert rows[0]["included_in_totals"] is False
    assert rows[0]["excluded_from_totals"] is True


def test_unified_expense_ledger_respects_manual_review_exclusion():
    rows = server.build_expense_ledger_rows(
        [],
        [
            {
                "id": "manual-review",
                "date": "02/06/2026",
                "description": "Receipt awaiting bank match",
                "amount": 45,
                "category": "Other",
                "tax_year": "2026-27",
                "is_from_bank": False,
                "include_in_totals": False,
            }
        ],
    )

    assert len(rows) == 1
    assert rows[0]["amount"] == 45
    assert rows[0]["included_in_totals"] is False
    assert rows[0]["excluded_from_totals"] is True


def test_unified_expense_ledger_marks_personally_paid_manual_expense():
    rows = server.build_expense_ledger_rows(
        [],
        [{
            "id": "manual-personal-card",
            "date": "17/06/2026",
            "description": "Awards accommodation",
            "amount": 80,
            "category": "Travel & Mileage",
            "tax_year": "2026-27",
            "paid_personally": True,
        }],
    )

    assert len(rows) == 1
    assert rows[0]["included_in_totals"] is True
    assert rows[0]["paid_personally"] is True
