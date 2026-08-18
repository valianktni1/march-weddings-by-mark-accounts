"""Safe, idempotent importer for Mark's retired Emergent Accounts app.

The source is a set of mongoexport JSON arrays plus copied invoice/expense
files beneath STORAGE_ROOT.  A normal run is validation-only.  Applying an
import requires the exact preview digest and confirmation phrase.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import os
import re
import shutil
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

BUILD = "2026.08.18-old-accounts-migration-ready-v1.4.5"
IMPORT_BATCH = "old-accounts-2026-08-18"
CONFIRMATION = "IMPORT OLD ACCOUNTS DATA"
EXPECTED_SOURCE_COUNTS = {
    "invoices": 103,
    "expenses": 153,
    "mileage": 40,
    "recurring_expenses": 1,
}


def money(value: Any) -> float:
    try:
        return round(float(value or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def parse_date(value: Any) -> date | None:
    if not value:
        return None
    text = str(value).strip()[:10]
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def normalise_text(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def useful_tokens(value: Any) -> set[str]:
    ignored = {
        "the", "and", "for", "from", "payment", "card", "purchase", "direct",
        "debit", "online", "ltd", "limited", "co", "uk", "invoice", "receipt",
    }
    return {item for item in normalise_text(value).split() if len(item) >= 3 and item not in ignored}


def stable_id(kind: str, source_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"weddings-by-mark:old-accounts:{kind}:{source_id}"))


def safe_name(value: Any, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value or "")).strip(".-")
    return cleaned or fallback


def load_json_array(path: Path) -> list[dict]:
    if not path.is_file():
        raise ValueError(f"Missing source export: {path}")
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, list):
        raise ValueError(f"Source export is not a JSON array: {path}")
    return [dict(item) for item in data if isinstance(item, dict)]


def source_record_id(record: dict, kind: str, position: int) -> str:
    value = str(record.get("id") or "").strip()
    if value:
        return value
    canonical = json.dumps({key: value for key, value in record.items() if key != "_id"}, sort_keys=True, default=str)
    return hashlib.sha256(f"{kind}:{position}:{canonical}".encode()).hexdigest()[:32]


def build_file_index(directory: Path) -> dict[str, list[Path]]:
    index: dict[str, list[Path]] = {}
    if directory.is_dir():
        for path in directory.rglob("*"):
            if path.is_file():
                index.setdefault(path.name.lower(), []).append(path)
    return index


def resolve_source_file(record: dict, index: dict[str, list[Path]], source_root: Path) -> tuple[Path | None, str]:
    raw_path = str(record.get("file_path") or "").replace("\\", "/")
    for marker in ("/uploads/invoices/", "/uploads/expenses/"):
        if marker in raw_path:
            relative = raw_path.split(marker, 1)[1].lstrip("/")
            direct = (source_root / relative).resolve()
            if source_root.resolve() in direct.parents and direct.is_file():
                return direct, "matched"
    candidates = []
    for value in (record.get("file_name"), Path(str(record.get("file_path") or "")).name):
        name = str(value or "").strip().lower()
        if name and name not in candidates:
            candidates.append(name)
    for name in candidates:
        matches = index.get(name, [])
        if len(matches) == 1:
            return matches[0], "matched"
        if len(matches) > 1:
            return None, "ambiguous"
    return None, "missing" if candidates else "not_supplied"


def match_expense_to_bank(expense: dict, transactions: list[dict]) -> dict:
    amount = money(expense.get("amount"))
    expense_date = parse_date(expense.get("date"))
    if not expense_date or amount <= 0:
        return {"status": "unmatched", "target_id": None, "candidate_count": 0}

    candidates = [
        tx for tx in transactions
        if str(tx.get("transaction_type") or "").lower() == "expense"
        and not tx.get("excluded_from_totals")
        and money(tx.get("amount")) == amount
        and parse_date(tx.get("date")) == expense_date
    ]
    if len(candidates) == 1:
        return {"status": "exact", "target_id": str(candidates[0].get("id") or ""), "candidate_count": 1}
    if len(candidates) > 1:
        source_tokens = useful_tokens(f"{expense.get('supplier', '')} {expense.get('description', '')}")
        scored = []
        for tx in candidates:
            overlap = len(source_tokens & useful_tokens(tx.get("description")))
            scored.append((overlap, str(tx.get("id") or ""), tx))
        scored.sort(key=lambda item: (-item[0], item[1]))
        if scored and scored[0][0] > 0 and (len(scored) == 1 or scored[0][0] > scored[1][0]):
            return {"status": "exact_text", "target_id": str(scored[0][2].get("id") or ""), "candidate_count": len(candidates)}
        return {"status": "ambiguous", "target_id": None, "candidate_count": len(candidates)}
    return {"status": "unmatched", "target_id": None, "candidate_count": 0}


def canonical_digest(plan: dict) -> str:
    digestable = {key: value for key, value in plan.items() if key not in {"generated_at", "digest"}}
    payload = json.dumps(digestable, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def load_source(source_dir: Path) -> dict[str, list[dict]]:
    return {
        name: load_json_array(source_dir / f"{name}.json")
        for name in EXPECTED_SOURCE_COUNTS
    }


def build_plan(source: dict[str, list[dict]], target: dict[str, list[dict]], source_dir: Path) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    invoice_files = build_file_index(source_dir / "files" / "invoices")
    expense_files = build_file_index(source_dir / "files" / "expenses")

    for name, expected in EXPECTED_SOURCE_COUNTS.items():
        actual = len(source.get(name, []))
        if actual != expected:
            errors.append(f"Expected {expected} {name} records but found {actual}")

    target_legacy = {
        name: {str(item.get("legacy_id") or "") for item in target.get(name, []) if item.get("legacy_source") == "old_accounts"}
        for name in ("invoices", "expenses", "mileage", "recurring_expenses")
    }
    target_numbers = {
        str(item.get("invoice_number") or "").strip()
        for item in target.get("invoices", [])
        if item.get("invoice_number")
    }
    target_transactions = target.get("transactions", [])
    target_transactions_by_id = {str(item.get("id") or ""): item for item in target_transactions}

    actions: list[dict] = []
    seen_numbers: set[str] = set()
    for position, invoice in enumerate(source["invoices"]):
        legacy_id = source_record_id(invoice, "invoice", position)
        number = str(invoice.get("invoice_number") or "").strip()
        source_file, file_status = resolve_source_file(invoice, invoice_files, source_dir / "files" / "invoices")
        if not number:
            errors.append(f"Invoice source record {legacy_id} has no invoice number")
        elif number in seen_numbers:
            errors.append(f"Duplicate source invoice number: {number}")
        seen_numbers.add(number)
        if file_status != "matched":
            errors.append(f"Invoice {number or legacy_id} PDF is {file_status}")
        if legacy_id in target_legacy["invoices"]:
            action = "skip_existing"
        elif number in target_numbers:
            action = "number_conflict"
            errors.append(f"Target already contains invoice number {number}")
        else:
            action = "import"
        actions.append({
            "kind": "invoice",
            "legacy_id": legacy_id,
            "source_position": position,
            "action": action,
            "invoice_number": number,
            "source_file": str(source_file.relative_to(source_dir)) if source_file else "",
        })

    manual_expenses = [(position, item) for position, item in enumerate(source["expenses"]) if not item.get("is_from_bank")]
    bank_classifications = [item for item in source["expenses"] if item.get("is_from_bank")]
    if len(manual_expenses) != 60 or len(bank_classifications) != 93:
        errors.append(
            f"Expected 60 manual and 93 bank-linked source expenses; found {len(manual_expenses)} and {len(bank_classifications)}"
        )
    for original_position, expense in manual_expenses:
        legacy_id = source_record_id(expense, "expense", original_position)
        source_file, file_status = resolve_source_file(expense, expense_files, source_dir / "files" / "expenses")
        match = match_expense_to_bank(expense, target_transactions)
        if legacy_id in target_legacy["expenses"]:
            action = "skip_existing"
        elif match["status"] in {"exact", "exact_text"}:
            action = "import_linked_receipt"
        else:
            action = "import_excluded_review"
        if file_status == "ambiguous":
            errors.append(f"Expense receipt for source record {legacy_id} is ambiguous")
        elif file_status == "missing":
            warnings.append(f"Expense source record {legacy_id} references a missing receipt")
        target_tx = target_transactions_by_id.get(str(match.get("target_id") or ""), {})
        source_category = str(expense.get("category") or "").strip()
        target_category = str(target_tx.get("category") or "").strip()
        category_update = bool(
            action == "import_linked_receipt"
            and source_category
            and (not target_category or target_category.lower() == "other")
        )
        actions.append({
            "kind": "expense",
            "legacy_id": legacy_id,
            "source_position": original_position,
            "action": action,
            "date": str(expense.get("date") or ""),
            "amount": money(expense.get("amount")),
            "match_status": match["status"],
            "target_transaction_id": match.get("target_id") or "",
            "candidate_count": match["candidate_count"],
            "category_update": category_update,
            "source_file": str(source_file.relative_to(source_dir)) if source_file else "",
            "file_status": file_status,
        })

    for position, entry in enumerate(source["mileage"]):
        legacy_id = source_record_id(entry, "mileage", position)
        actions.append({
            "kind": "mileage",
            "legacy_id": legacy_id,
            "source_position": position,
            "action": "skip_existing" if legacy_id in target_legacy["mileage"] else "import",
            "date": str(entry.get("date") or ""),
            "miles": money(entry.get("miles")),
            "amount": money(entry.get("amount")),
        })

    for position, template in enumerate(source["recurring_expenses"]):
        legacy_id = source_record_id(template, "recurring_expense", position)
        actions.append({
            "kind": "recurring_expense",
            "legacy_id": legacy_id,
            "source_position": position,
            "action": "skip_existing" if legacy_id in target_legacy["recurring_expenses"] else "import",
            "amount": money(template.get("amount")),
        })

    def count(kind: str, action: str | None = None) -> int:
        return sum(1 for item in actions if item["kind"] == kind and (action is None or item["action"] == action))

    summary = {
        "source_invoices": len(source["invoices"]),
        "invoices_to_import": count("invoice", "import"),
        "source_manual_expenses": len(manual_expenses),
        "linked_receipts_to_import": count("expense", "import_linked_receipt"),
        "manual_expenses_awaiting_review": count("expense", "import_excluded_review"),
        "source_bank_classifications_skipped": len(bank_classifications),
        "mileage_to_import": count("mileage", "import"),
        "recurring_templates_to_import": count("recurring_expense", "import"),
        "already_imported": sum(1 for item in actions if item["action"] == "skip_existing"),
        "target_bank_transactions_untouched": len(target_transactions),
    }
    plan = {
        "format": "weddings-by-mark-old-accounts-import",
        "version": 1,
        "build": BUILD,
        "import_batch": IMPORT_BATCH,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_counts": {name: len(rows) for name, rows in source.items()},
        "target_counts": {name: len(rows) for name, rows in target.items()},
        "summary": summary,
        "errors": sorted(set(errors)),
        "warnings": sorted(set(warnings)),
        "actions": actions,
    }
    plan["digest"] = canonical_digest(plan)
    return plan


def load_target(db) -> dict[str, list[dict]]:
    projections = {"_id": 0}
    return {
        "invoices": list(db.invoices.find({}, projections)),
        "expenses": list(db.expenses.find({}, projections)),
        "mileage": list(db.mileage.find({}, projections)),
        "recurring_expenses": list(db.recurring_expenses.find({}, projections)),
        "transactions": list(db.transactions.find({}, projections)),
        "bank_statements": list(db.bank_statements.find({}, projections)),
    }


def verify_backups(storage_root: Path) -> list[str]:
    backup_dir = storage_root / "migration-from-old-accounts" / "backups"
    expected = [
        backup_dir / "old-accounts-before-migration-2026-08-18.archive.gz",
        backup_dir / "new-accounts-before-old-data-import-2026-08-18.archive.gz",
    ]
    errors = []
    for path in expected:
        if not path.is_file() or path.stat().st_size == 0:
            errors.append(f"Missing backup: {path}")
            continue
        try:
            with gzip.open(path, "rb") as handle:
                handle.read(1024)
        except OSError:
            errors.append(f"Backup failed gzip validation: {path}")
    return errors


def copy_source_file(source_dir: Path, relative_path: str, destination: Path) -> Path | None:
    if not relative_path:
        return None
    source = (source_dir / relative_path).resolve()
    if source_dir.resolve() not in source.parents or not source.is_file():
        raise ValueError(f"Unsafe or missing staged file: {relative_path}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        shutil.copy2(source, destination)
    return destination


def invoice_document(source: dict, action: dict, source_dir: Path, storage_root: Path) -> dict:
    legacy_id = action["legacy_id"]
    number = action["invoice_number"]
    new_id = stable_id("invoice", legacy_id)
    source_relative = action.get("source_file") or ""
    source_path = source_dir / source_relative if source_relative else None
    extension = source_path.suffix.lower() if source_path else ".pdf"
    original_destination = storage_root / "uploads" / "invoices" / "legacy-originals" / f"{safe_name(number, 'invoice')}--{new_id[:8]}{extension}"
    copied = copy_source_file(source_dir, source_relative, original_destination)
    document = {key: value for key, value in source.items() if key != "_id"}
    document.update({
        "id": new_id,
        "invoice_number": number,
        "legacy_invoice_number": number,
        "legacy_id": legacy_id,
        "legacy_source": "old_accounts",
        "source_system": "old_accounts",
        "import_batch": IMPORT_BATCH,
        "include_in_totals": False,
        "legacy_pdf_path": str(copied) if copied else None,
        "legacy_pdf_file_name": str(source.get("file_name") or (copied.name if copied else "")),
        "file_path": str(copied) if copied else None,
        "file_name": str(source.get("file_name") or (copied.name if copied else f"{number}.pdf")),
        "pdf_format_version": 0,
        "imported_at": datetime.now(timezone.utc).isoformat(),
    })
    return document


def expense_document(source: dict, action: dict, source_dir: Path, storage_root: Path) -> dict:
    legacy_id = action["legacy_id"]
    new_id = stable_id("expense", legacy_id)
    source_relative = action.get("source_file") or ""
    source_path = source_dir / source_relative if source_relative else None
    extension = source_path.suffix.lower() if source_path else ""
    tax_year = str(source.get("tax_year") or "unknown")
    destination = storage_root / "uploads" / "expenses" / safe_name(tax_year, "unknown") / f"legacy-{new_id[:12]}{extension}"
    copied = copy_source_file(source_dir, source_relative, destination) if source_relative else None
    linked = action["action"] == "import_linked_receipt"
    document = {key: value for key, value in source.items() if key != "_id"}
    document.update({
        "id": new_id,
        "legacy_id": legacy_id,
        "legacy_source": "old_accounts",
        "import_batch": IMPORT_BATCH,
        "is_from_bank": linked,
        "source_transaction_id": action.get("target_transaction_id") if linked else None,
        "include_in_totals": False,
        "migration_review_status": "bank_linked" if linked else "awaiting_review",
        "file_path": str(copied) if copied else None,
        "file_name": str(source.get("file_name") or (copied.name if copied else "")) or None,
        "imported_at": datetime.now(timezone.utc).isoformat(),
    })
    return document


def simple_document(source: dict, action: dict, kind: str) -> dict:
    legacy_id = action["legacy_id"]
    document = {key: value for key, value in source.items() if key != "_id"}
    document.update({
        "id": stable_id(kind, legacy_id),
        "legacy_id": legacy_id,
        "legacy_source": "old_accounts",
        "import_batch": IMPORT_BATCH,
        "imported_at": datetime.now(timezone.utc).isoformat(),
    })
    return document


def write_audit(plan: dict, output_dir: Path, label: str) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"old-accounts-import-{label}-{plan['digest'][:12]}"
    json_path = output_dir / f"{stem}.json"
    csv_path = output_dir / f"{stem}.csv"
    json_path.write_text(json.dumps(plan, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    headers = [
        "kind", "legacy_id", "action", "invoice_number", "date", "amount", "miles",
        "match_status", "target_transaction_id", "candidate_count", "file_status",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(plan["actions"])
    return json_path, csv_path


def apply_plan(db, source: dict[str, list[dict]], plan: dict, source_dir: Path, storage_root: Path) -> dict:
    applied = {"invoices": 0, "expenses": 0, "mileage": 0, "recurring_expenses": 0, "categories_updated": 0}
    for action in plan["actions"]:
        if action["action"] in {"skip_existing", "number_conflict"}:
            continue
        kind = action["kind"]
        position = int(action["source_position"])
        if kind == "invoice" and action["action"] == "import":
            document = invoice_document(source["invoices"][position], action, source_dir, storage_root)
            if not db.invoices.find_one({"legacy_source": "old_accounts", "legacy_id": action["legacy_id"]}):
                db.invoices.insert_one(document)
                db.invoice_audit_logs.insert_one({
                    "id": str(uuid.uuid4()),
                    "invoice_id": document["id"],
                    "action": "old_accounts_import",
                    "reason": "Imported from retired Accounts application",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "snapshot": {"legacy_invoice_number": document["legacy_invoice_number"]},
                })
                applied["invoices"] += 1
        elif kind == "expense" and action["action"] in {"import_linked_receipt", "import_excluded_review"}:
            document = expense_document(source["expenses"][position], action, source_dir, storage_root)
            if not db.expenses.find_one({"legacy_source": "old_accounts", "legacy_id": action["legacy_id"]}):
                db.expenses.insert_one(document)
                applied["expenses"] += 1
            if action.get("category_update") and action.get("target_transaction_id"):
                source_category = str(source["expenses"][position].get("category") or "").strip()
                result = db.transactions.update_one(
                    {
                        "id": action["target_transaction_id"],
                        "$or": [{"category": {"$exists": False}}, {"category": None}, {"category": ""}, {"category": "Other"}],
                    },
                    {"$set": {"category": source_category, "updated_at": datetime.now(timezone.utc).isoformat()}},
                )
                applied["categories_updated"] += int(result.modified_count)
        elif kind == "mileage" and action["action"] == "import":
            document = simple_document(source["mileage"][position], action, "mileage")
            if not db.mileage.find_one({"legacy_source": "old_accounts", "legacy_id": action["legacy_id"]}):
                db.mileage.insert_one(document)
                applied["mileage"] += 1
        elif kind == "recurring_expense" and action["action"] == "import":
            document = simple_document(source["recurring_expenses"][position], action, "recurring_expense")
            if not db.recurring_expenses.find_one({"legacy_source": "old_accounts", "legacy_id": action["legacy_id"]}):
                db.recurring_expenses.insert_one(document)
                applied["recurring_expenses"] += 1
    db.migration_audits.insert_one({
        "id": str(uuid.uuid4()),
        "migration": IMPORT_BATCH,
        "digest": plan["digest"],
        "build": BUILD,
        "applied": applied,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return applied


def main() -> int:
    parser = argparse.ArgumentParser(description="Import the retired Weddings By Mark Accounts data safely")
    parser.add_argument("--source-dir", default="")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-digest", default="")
    parser.add_argument("--confirmation", default="")
    parser.add_argument("--confirm-backups", action="store_true")
    args = parser.parse_args()

    storage_root = Path(os.environ.get("STORAGE_ROOT", "/app/storage")).resolve()
    source_dir = Path(args.source_dir or storage_root / "migration-from-old-accounts" / "source").resolve()
    output_dir = storage_root / "migration-from-old-accounts" / "reports"
    if storage_root not in source_dir.parents:
        print("STOPPED SAFELY: source directory must be inside STORAGE_ROOT", file=sys.stderr)
        return 2

    try:
        from pymongo import MongoClient

        source = load_source(source_dir)
        mongo_client = MongoClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=10000)
        db = mongo_client[os.environ["DB_NAME"]]
        mongo_client.admin.command("ping")
        target = load_target(db)
        plan = build_plan(source, target, source_dir)
    except Exception as error:
        print(f"STOPPED SAFELY: {error}", file=sys.stderr)
        return 2

    label = "applied" if args.apply else "preview"
    json_path, csv_path = write_audit(plan, output_dir, label)
    print("Weddings By Mark old Accounts migration")
    print("Bank statements and bank transactions: NEVER IMPORTED")
    print("Client emails and Booking integration: NOT CONTACTED")
    print(f"Build: {BUILD}")
    print(f"Digest: {plan['digest']}")
    for key, value in plan["summary"].items():
        print(f"{key}: {value}")
    print(f"Warnings: {len(plan['warnings'])}")
    print(f"Errors: {len(plan['errors'])}")
    print(f"JSON audit: {json_path}")
    print(f"CSV audit:  {csv_path}")
    if plan["errors"]:
        for error in plan["errors"]:
            print(f"ERROR: {error}")
        print("STOPPED SAFELY: validation errors must be resolved before import", file=sys.stderr)
        return 2
    if not args.apply:
        print("DRY RUN ONLY - the target database and files were not changed.")
        return 0

    backup_errors = verify_backups(storage_root)
    if not args.confirm_backups or backup_errors:
        for error in backup_errors:
            print(f"ERROR: {error}")
        print("STOPPED SAFELY: both verified backups and --confirm-backups are required", file=sys.stderr)
        return 2
    if args.expected_digest != plan["digest"]:
        print("STOPPED SAFELY: preview digest does not match current data", file=sys.stderr)
        return 2
    if args.confirmation != CONFIRMATION:
        print(f'STOPPED SAFELY: confirmation must be exactly "{CONFIRMATION}"', file=sys.stderr)
        return 2

    try:
        applied = apply_plan(db, source, plan, source_dir, storage_root)
    except Exception as error:
        print(f"STOPPED SAFELY: import interrupted: {error}", file=sys.stderr)
        print("The importer is idempotent; correct the problem and rerun with a fresh dry run.", file=sys.stderr)
        return 2
    print("IMPORT COMPLETE")
    print(json.dumps(applied, sort_keys=True))
    print("All imported invoice and unmatched expense income/amounts remain excluded from totals until reviewed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
