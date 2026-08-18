import hashlib
import json
import sys
import zipfile
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from tax_year_close import build_evidence_pack, build_tax_snapshot  # noqa: E402


def snapshot(**overrides):
    values = {
        "tax_year": "2025-26",
        "business_name": "Weddings By Mark",
        "transactions": [],
        "expenses": [],
        "mileage": [],
        "invoices": [],
        "bank_statements": [],
        "generated_at": "2026-04-06T09:00:00+00:00",
    }
    values.update(overrides)
    return build_tax_snapshot(**values)


def test_bank_linked_receipt_is_not_double_counted():
    result = snapshot(
        transactions=[{
            "id": "tx-1", "date": "10/05/2025", "description": "Camera shop",
            "amount": 100, "transaction_type": "expense", "category": "Equipment & Gear",
            "tax_year": "2025-26", "excluded_from_totals": False,
        }],
        expenses=[{
            "id": "expense-1", "date": "10/05/2025", "description": "Camera shop",
            "amount": 100, "category": "Equipment & Gear", "tax_year": "2025-26",
            "is_from_bank": True, "source_transaction_id": "tx-1", "file_name": "receipt.pdf",
        }],
    )
    assert result["summary"]["bank_expenses"] == 100
    assert result["summary"]["manual_expenses"] == 0
    assert result["summary"]["allowable_expenses"] == 100


def test_unlinked_manual_and_bank_expense_collision_blocks_close():
    result = snapshot(
        transactions=[{
            "id": "tx-1", "date": "10/05/2025", "description": "Supplier",
            "amount": 75, "transaction_type": "expense", "category": "Other",
            "tax_year": "2025-26", "excluded_from_totals": False,
        }],
        expenses=[{
            "id": "expense-1", "date": "10/05/2025", "description": "Supplier receipt",
            "amount": 75, "category": "Other", "tax_year": "2025-26", "file_name": "receipt.pdf",
        }],
    )
    codes = {item["code"] for item in result["validation"]["checks"]}
    assert "manual_bank_duplicates" in codes
    assert result["validation"]["ready_to_close"] is False


def test_booking_payments_reconcile_but_never_add_invoice_income_twice():
    result = snapshot(
        transactions=[{
            "id": "tx-1", "date": "14/08/2025", "description": "WBM02001 Mark Gina",
            "amount": 100, "transaction_type": "income", "tax_year": "2025-26",
            "excluded_from_totals": False,
        }],
        invoices=[{
            "id": "inv-1", "invoice_number": "WBM02001", "couple_names": "Mark & Gina",
            "source_system": "booking_system", "include_in_totals": False,
            "payments": [{"id": "pay-1", "paid_date": "14/08/2025", "amount": 100}],
        }],
    )
    assert result["summary"]["turnover"] == 100
    assert result["summary"]["other_cash_income"] == 0
    assert result["booking_reconciliation"]["matched"] == 1


def test_explicit_cash_invoice_is_included_once_when_not_in_bank():
    result = snapshot(invoices=[{
        "id": "inv-2", "invoice_number": "CASH1", "couple_names": "Cash client",
        "include_in_totals": True, "deposit_amount": 50, "deposit_paid_date": "20/06/2025",
    }])
    assert result["summary"]["turnover"] == 50
    assert result["summary"]["other_cash_income"] == 50
    assert result["manual_income_reconciliation"]["included_as_other_cash_income"] == 1


def test_uncategorised_included_expense_blocks_close():
    result = snapshot(transactions=[{
        "id": "tx-1", "date": "10/05/2025", "description": "Unknown supplier",
        "amount": 10, "transaction_type": "expense", "category": None,
        "tax_year": "2025-26", "excluded_from_totals": False,
    }])
    assert result["validation"]["blocker_count"] == 1
    assert result["validation"]["checks"][0]["code"] == "uncategorised_expenses"


def test_evidence_pack_contains_reports_evidence_and_verifiable_manifest(tmp_path):
    result = snapshot(
        transactions=[{
            "id": "tx-income", "date": "10/05/2025", "description": "Client transfer",
            "amount": 200, "transaction_type": "income", "tax_year": "2025-26",
            "excluded_from_totals": False,
        }],
        expenses=[{
            "id": "expense-1", "date": "11/05/2025", "description": "Stationery",
            "amount": 20, "category": "Office & Supplies", "tax_year": "2025-26",
            "file_name": "receipt.pdf",
        }],
    )
    evidence = tmp_path / "receipt.pdf"
    evidence.write_bytes(b"receipt evidence")
    output = tmp_path / "tax-pack.zip"
    metadata = build_evidence_pack(
        snapshot=result,
        output_path=output,
        build_id="test-build",
        evidence_files=[{
            "category": "receipts", "source_path": str(evidence),
            "file_name": "receipt.pdf", "record_id": "expense-1",
        }],
    )
    assert metadata["pack_sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
        names = set(archive.namelist())
        assert "reports/annual-summary.pdf" in names
        assert "reports/income-ledger.csv" in names
        assert "reports/expense-ledger.csv" in names
        assert "reports/booking-bank-reconciliation.csv" in names
        assert "evidence/receipts/receipt.pdf" in names
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["format"] == "weddings-by-mark-tax-year-close"
        for name, details in manifest["files"].items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == details["sha256"]
