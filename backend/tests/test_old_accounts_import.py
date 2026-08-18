import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import old_accounts_import as importer


def test_expense_bank_match_requires_a_unique_date_and_amount():
    expense = {"date": "10/06/2026", "amount": 12.34, "description": "Adobe", "supplier": "Adobe"}
    transactions = [
        {"id": "tx-1", "date": "10/06/2026", "amount": 12.34, "description": "Adobe", "transaction_type": "expense"},
        {"id": "tx-2", "date": "11/06/2026", "amount": 12.34, "description": "Adobe", "transaction_type": "expense"},
    ]

    match = importer.match_expense_to_bank(expense, transactions)

    assert match == {"status": "exact", "target_id": "tx-1", "candidate_count": 1}


def test_expense_bank_match_does_not_guess_between_ambiguous_rows():
    expense = {"date": "10/06/2026", "amount": 20, "description": "Parking", "supplier": ""}
    transactions = [
        {"id": "tx-1", "date": "10/06/2026", "amount": 20, "description": "Car park", "transaction_type": "expense"},
        {"id": "tx-2", "date": "10/06/2026", "amount": 20, "description": "Car park", "transaction_type": "expense"},
    ]

    match = importer.match_expense_to_bank(expense, transactions)

    assert match["status"] == "ambiguous"
    assert match["target_id"] is None


def test_complete_source_plan_matches_verified_inventory(tmp_path):
    source_dir = tmp_path / "source"
    invoice_dir = source_dir / "files" / "invoices"
    expense_dir = source_dir / "files" / "expenses" / "2025-26"
    invoice_dir.mkdir(parents=True)
    expense_dir.mkdir(parents=True)

    invoices = []
    for index in range(103):
        file_name = f"old-{index:03d}.pdf"
        (invoice_dir / file_name).write_bytes(b"pdf")
        invoices.append({
            "id": f"invoice-{index}",
            "invoice_number": f"OLD{index:03d}",
            "file_name": file_name,
            "file_path": f"/app/uploads/invoices/{file_name}",
        })

    expenses = []
    transactions = []
    for index in range(60):
        file_name = f"expense-{index:03d}.pdf" if index < 57 else None
        if file_name:
            (expense_dir / file_name).write_bytes(b"receipt")
        expenses.append({
            "id": f"expense-{index}",
            "is_from_bank": False,
            "date": "01/05/2026",
            "amount": index + 1,
            "category": "Other",
            "tax_year": "2026-27",
            "file_name": file_name,
            "file_path": f"/app/uploads/expenses/2025-26/{file_name}" if file_name else None,
        })
        transactions.append({
            "id": f"tx-{index}",
            "date": "01/05/2026",
            "amount": index + 1,
            "category": None,
            "transaction_type": "expense",
            "excluded_from_totals": False,
        })
    expenses.extend({"id": f"bank-{index}", "is_from_bank": True} for index in range(93))

    source = {
        "invoices": invoices,
        "expenses": expenses,
        "mileage": [{"id": f"trip-{index}", "miles": 10, "amount": 4.5} for index in range(40)],
        "recurring_expenses": [{"id": "template-1", "amount": 10}],
    }
    target = {
        "invoices": [],
        "expenses": [],
        "mileage": [],
        "recurring_expenses": [],
        "transactions": transactions,
        "bank_statements": [],
    }

    plan = importer.build_plan(source, target, source_dir)

    assert plan["errors"] == []
    assert plan["summary"]["invoices_to_import"] == 103
    assert plan["summary"]["linked_receipts_to_import"] == 60
    assert plan["summary"]["manual_expenses_awaiting_review"] == 0
    assert plan["summary"]["source_bank_classifications_skipped"] == 93
    assert plan["summary"]["mileage_to_import"] == 40
    assert plan["summary"]["recurring_templates_to_import"] == 1

