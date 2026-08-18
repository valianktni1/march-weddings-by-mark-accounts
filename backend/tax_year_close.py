"""Authoritative cash-basis tax-year review and evidence-pack generation.

This module deliberately prepares records; it does not submit a Self Assessment
or a Making Tax Digital update to HMRC.  Bank transactions are the primary
cash-basis ledger.  Booking invoices are retained as supporting evidence and
are never counted a second time.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import shutil
import tempfile
import zipfile
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable


PACK_FORMAT = "weddings-by-mark-tax-year-close"
PACK_VERSION = 1


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


def iso_date(value: Any) -> str:
    parsed = parse_date(value)
    return parsed.isoformat() if parsed else ""


def display_date(value: Any) -> str:
    parsed = parse_date(value)
    return parsed.strftime("%d/%m/%Y") if parsed else str(value or "")


def tax_year_bounds(tax_year: str) -> tuple[date, date]:
    if not re.fullmatch(r"20\d{2}-\d{2}", tax_year or ""):
        raise ValueError("Invalid tax year")
    start_year = int(tax_year[:4])
    expected_end = (start_year + 1) % 100
    if int(tax_year[-2:]) != expected_end:
        raise ValueError("Invalid tax year")
    return date(start_year, 4, 6), date(start_year + 1, 4, 5)


def date_in_tax_year(value: Any, tax_year: str) -> bool:
    parsed = parse_date(value)
    if not parsed:
        return False
    start, end = tax_year_bounds(tax_year)
    return start <= parsed <= end


def _normalise_text(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _csv_bytes(headers: list[str], rows: Iterable[Iterable[Any]]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(list(row))
    return output.getvalue().encode("utf-8-sig")


def _summary_csv(snapshot: dict) -> bytes:
    summary = snapshot["summary"]
    rows = [
        ["Business", snapshot["business_name"]],
        ["Tax year", snapshot["tax_year"]],
        ["Basis", "Cash basis - income received and expenses paid"],
        ["Bank income received", f"{summary['bank_income']:.2f}"],
        ["Other cash income", f"{summary['other_cash_income']:.2f}"],
        ["Total turnover", f"{summary['turnover']:.2f}"],
        ["Bank expenses", f"{summary['bank_expenses']:.2f}"],
        ["Independent manual expenses", f"{summary['manual_expenses']:.2f}"],
        ["Mileage claim", f"{summary['mileage']:.2f}"],
        ["Total allowable expenses", f"{summary['allowable_expenses']:.2f}"],
        ["Net business profit", f"{summary['net_profit']:.2f}"],
        ["Owner withdrawals excluded", f"{summary['owner_withdrawals']:.2f}"],
        ["HMRC payments excluded", f"{summary['tax_payments']:.2f}"],
        ["Blocking issues at close", snapshot["validation"]["blocker_count"]],
        ["Warnings acknowledged", snapshot["validation"]["warning_count"]],
    ]
    return _csv_bytes(["Annual summary", "Value"], rows)


def _payment_rows(invoice: dict, tax_year: str) -> list[dict]:
    rows: list[dict] = []
    if invoice.get("payments"):
        for payment in invoice.get("payments") or []:
            paid_date = payment.get("paid_date")
            if date_in_tax_year(paid_date, tax_year):
                rows.append({
                    "id": str(payment.get("id") or ""),
                    "date": display_date(paid_date),
                    "amount": money(payment.get("amount")),
                    "type": str(payment.get("payment_type") or ("refund" if money(payment.get("amount")) < 0 else "payment")),
                    "reference": str(payment.get("reference") or ""),
                })
        return rows

    candidates = [
        ("deposit", invoice.get("deposit_paid_date"), invoice.get("deposit_amount")),
        ("interim", invoice.get("interim_payment_date"), invoice.get("interim_payment")),
    ]
    total = money(invoice.get("total_price"))
    earlier = money(invoice.get("deposit_amount")) + money(invoice.get("interim_payment"))
    final_amount = max(0.0, round(total - earlier, 2))
    candidates.append(("final", invoice.get("final_payment_paid_date"), final_amount))
    for kind, paid_date, amount in candidates:
        if paid_date and amount and date_in_tax_year(paid_date, tax_year):
            rows.append({
                "id": f"{invoice.get('id', '')}-{kind}",
                "date": display_date(paid_date),
                "amount": money(amount),
                "type": kind,
                "reference": "",
            })
    return rows


def _issue(code: str, severity: str, title: str, records: list[dict], guidance: str) -> dict:
    return {
        "code": code,
        "severity": severity,
        "title": title,
        "count": len(records),
        "amount": round(sum(abs(money(item.get("amount"))) for item in records), 2),
        "examples": records[:5],
        "guidance": guidance,
    }


def _quarter_for(value: Any, tax_year: str) -> str | None:
    parsed = parse_date(value)
    if not parsed:
        return None
    start_year = int(tax_year[:4])
    boundaries = [
        ("Q1", date(start_year, 4, 6), date(start_year, 7, 5)),
        ("Q2", date(start_year, 7, 6), date(start_year, 10, 5)),
        ("Q3", date(start_year, 10, 6), date(start_year + 1, 1, 5)),
        ("Q4", date(start_year + 1, 1, 6), date(start_year + 1, 4, 5)),
    ]
    for name, start, end in boundaries:
        if start <= parsed <= end:
            return name
    return None


def _match_cash_items(source_rows: list[dict], bank_rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """One-to-one match by reference first, then exact date and amount."""
    unmatched_bank = {row["id"]: row for row in bank_rows}
    matched: list[dict] = []
    unmatched: list[dict] = []
    for source in sorted(source_rows, key=lambda row: (iso_date(row.get("date")), row.get("id", ""))):
        source_ref = _normalise_text(source.get("reference"))
        invoice_number = _normalise_text(source.get("invoice_number"))
        candidate = None
        if source_ref or invoice_number:
            for bank in unmatched_bank.values():
                description = _normalise_text(bank.get("description"))
                if money(bank.get("amount")) != money(source.get("amount")):
                    continue
                if (source_ref and source_ref in description) or (invoice_number and invoice_number in description):
                    candidate = bank
                    break
        if not candidate:
            for bank in unmatched_bank.values():
                if iso_date(bank.get("date")) == iso_date(source.get("date")) and money(bank.get("amount")) == money(source.get("amount")):
                    candidate = bank
                    break
        if candidate:
            unmatched_bank.pop(candidate["id"], None)
            matched.append({**source, "bank_transaction_id": candidate["id"], "bank_description": candidate.get("description", "")})
        else:
            unmatched.append(source)
    return matched, unmatched


def build_tax_snapshot(
    *,
    tax_year: str,
    business_name: str,
    transactions: list[dict],
    expenses: list[dict],
    mileage: list[dict],
    invoices: list[dict],
    bank_statements: list[dict],
    cash_confirmations: list[dict] | None = None,
    generated_at: str,
    bank_matches: list[dict] | None = None,
) -> dict:
    """Build an auditable, cash-basis snapshot without mutating source records."""
    tax_year_bounds(tax_year)
    checks: list[dict] = []
    invalid_records: list[dict] = []
    mismatched_year: list[dict] = []
    negative_records: list[dict] = []
    active_cash_confirmations = {
        f"{item.get('source_invoice_id', '')}:{item.get('source_payment_id', '')}": item
        for item in (cash_confirmations or [])
        if item.get("active", True)
    }

    def validate(records: list[dict], kind: str) -> None:
        for record in records:
            record_date = record.get("date")
            if record_date and not parse_date(record_date):
                invalid_records.append({"kind": kind, "id": record.get("id", ""), "date": record_date, "description": record.get("description", "")})
            if record_date and parse_date(record_date) and not date_in_tax_year(record_date, tax_year):
                mismatched_year.append({"kind": kind, "id": record.get("id", ""), "date": record_date, "description": record.get("description", "")})
            if money(record.get("amount")) < 0 and kind != "invoice payment":
                negative_records.append({"kind": kind, "id": record.get("id", ""), "date": record_date, "description": record.get("description", ""), "amount": record.get("amount")})

    validate(transactions, "bank transaction")
    validate(expenses, "expense")
    validate(mileage, "mileage")
    if invalid_records:
        checks.append(_issue("invalid_dates", "blocker", "Records have invalid dates", invalid_records, "Correct these dates before closing the year."))
    if mismatched_year:
        checks.append(_issue("wrong_tax_year", "blocker", "Dates do not belong to the selected tax year", mismatched_year, "Correct the date or tax-year assignment before closing."))
    if negative_records:
        checks.append(_issue("negative_amounts", "blocker", "Unexpected negative amounts", negative_records, "Correct the amount or record the item as a refund."))

    transaction_ledger: list[dict] = []
    income_ledger: list[dict] = []
    expense_ledger: list[dict] = []
    owner_withdrawals = 0.0
    tax_payments = 0.0
    uncategorised: list[dict] = []

    for tx in transactions:
        amount = money(tx.get("amount"))
        tx_type = str(tx.get("transaction_type") or "").lower()
        excluded = bool(tx.get("excluded_from_totals"))
        base = {
            "id": str(tx.get("id") or ""),
            "date": display_date(tx.get("date")),
            "description": str(tx.get("description") or ""),
            "amount": amount,
            "category": str(tx.get("category") or ""),
            "transaction_type": tx_type,
            "included": not excluded and tx_type in {"income", "expense"},
            "source": "bank",
            "bank_statement_id": str(tx.get("bank_statement_id") or ""),
        }
        transaction_ledger.append(base)
        if excluded or tx_type in {"owner_withdrawal", "tax_payment"}:
            if tx_type == "owner_withdrawal":
                owner_withdrawals += amount
            if tx_type == "tax_payment":
                tax_payments += amount
            continue
        if tx_type == "income":
            income_ledger.append({**base, "income_source": "bank receipt", "included": True})
        elif tx_type == "expense":
            if not base["category"]:
                uncategorised.append(base)
            expense_ledger.append({**base, "expense_source": "bank payment", "included": True, "exclusion_reason": ""})

    for expense in expenses:
        amount = money(expense.get("amount"))
        linked_to_bank = bool(expense.get("is_from_bank") or expense.get("source_transaction_id"))
        explicitly_excluded = expense.get("include_in_totals") is False or amount <= 0
        included = not linked_to_bank and not explicitly_excluded
        row = {
            "id": str(expense.get("id") or ""),
            "date": display_date(expense.get("date")),
            "description": str(expense.get("description") or ""),
            "supplier": str(expense.get("supplier") or ""),
            "amount": amount,
            "category": str(expense.get("category") or ""),
            "expense_source": "bank-linked receipt" if linked_to_bank else "manual/cash expense",
            "source": "manual expense",
            "included": included,
            "exclusion_reason": "Represented by the linked bank transaction" if linked_to_bank else ("Marked not included" if explicitly_excluded else ""),
            "source_transaction_id": str(expense.get("source_transaction_id") or ""),
            "receipt_file": str(expense.get("file_name") or ""),
        }
        expense_ledger.append(row)
        if included and not row["category"]:
            uncategorised.append(row)

    if uncategorised:
        checks.append(_issue("uncategorised_expenses", "blocker", "Included expenses need a category", uncategorised, "Categorise each expense so the year-end totals can be checked."))

    # Duplicate bank rows are always blockers. Bank-linked supporting expense
    # records are intentionally excluded from totals and are not duplicates.
    tx_groups: dict[tuple, list[dict]] = defaultdict(list)
    for row in transaction_ledger:
        tx_groups[(iso_date(row["date"]), _normalise_text(row["description"]), row["amount"], row["transaction_type"])].append(row)
    duplicate_transactions = [item for rows in tx_groups.values() if len(rows) > 1 for item in rows]
    if duplicate_transactions:
        checks.append(_issue("duplicate_bank_transactions", "blocker", "Possible duplicate bank transactions", duplicate_transactions, "Review the originating statement and remove the duplicated import."))

    manual_groups: dict[tuple, list[dict]] = defaultdict(list)
    for row in expense_ledger:
        if row["source"] == "manual expense" and row["included"]:
            manual_groups[(iso_date(row["date"]), _normalise_text(row["description"]), row["amount"])].append(row)
    duplicate_manual = [item for rows in manual_groups.values() if len(rows) > 1 for item in rows]
    if duplicate_manual:
        checks.append(_issue("duplicate_manual_expenses", "blocker", "Possible duplicate manual expenses", duplicate_manual, "Delete or exclude the duplicated expense before closing."))

    bank_expense_keys = defaultdict(list)
    for row in expense_ledger:
        if row["source"] == "bank" and row["included"]:
            bank_expense_keys[(iso_date(row["date"]), row["amount"])].append(row)
    possible_double_count = []
    for row in expense_ledger:
        if row["source"] == "manual expense" and row["included"] and bank_expense_keys.get((iso_date(row["date"]), row["amount"])):
            possible_double_count.append(row)
    if possible_double_count:
        checks.append(_issue("manual_bank_duplicates", "blocker", "Manual expenses may duplicate bank payments", possible_double_count, "Delete the duplicate manual record or link it to the bank transaction."))

    missing_receipts = [row for row in expense_ledger if row["source"] == "manual expense" and row["included"] and not row.get("receipt_file")]
    if missing_receipts:
        checks.append(_issue("missing_receipts", "warning", "Manual expenses without an uploaded receipt", missing_receipts, "Keep suitable evidence and upload it where available."))

    # Explicit manual invoice income is only added when no matching bank receipt
    # exists. This preserves cash income without double counting bank transfers.
    manual_invoice_payments: list[dict] = []
    invoice_payment_audit: list[dict] = []
    booking_positive_payments: list[dict] = []
    booking_cash_payments: list[dict] = []
    for invoice in invoices:
        payment_rows = _payment_rows(invoice, tax_year)
        relevant = bool(payment_rows) or invoice.get("tax_year") == tax_year
        if not relevant:
            continue
        for payment in payment_rows or [{"date": "", "amount": 0, "type": "no payment in year", "reference": "", "id": ""}]:
            audit_row = {
                "invoice_id": str(invoice.get("id") or ""),
                "invoice_number": str(invoice.get("invoice_number") or ""),
                "legacy_invoice_number": str(invoice.get("legacy_invoice_number") or ""),
                "client": str(invoice.get("couple_names") or invoice.get("client_name") or ""),
                "status": str(invoice.get("status") or ""),
                "payment_id": payment.get("id", ""),
                "payment_date": payment.get("date", ""),
                "payment_amount": money(payment.get("amount")),
                "payment_type": payment.get("type", ""),
                "reference": payment.get("reference", ""),
                "source_system": str(invoice.get("source_system") or "accounts"),
                "file_name": str(invoice.get("file_name") or ""),
            }
            invoice_payment_audit.append(audit_row)
            if money(payment.get("amount")) <= 0:
                continue
            match_row = {
                "id": f"{invoice.get('id', '')}:{payment.get('id', '')}",
                "source_invoice_id": str(invoice.get("id") or ""),
                "source_payment_id": str(payment.get("id") or ""),
                "date": payment.get("date", ""),
                "description": audit_row["client"],
                "amount": money(payment.get("amount")),
                "reference": payment.get("reference", ""),
                "invoice_number": audit_row["invoice_number"],
                "payment_type": audit_row["payment_type"],
            }
            if invoice.get("source_system") == "booking_system":
                confirmation = active_cash_confirmations.get(match_row["id"])
                is_cash = str(audit_row["payment_type"] or "").lower() == "cash" or bool(confirmation)
                if is_cash:
                    booking_cash_payments.append({
                        **match_row,
                        "confirmation_id": str((confirmation or {}).get("id") or ""),
                        "confirmation_reason": str((confirmation or {}).get("reason") or "Recorded as cash in the Booking system"),
                        "confirmed_by": str((confirmation or {}).get("confirmed_by") or "Booking system"),
                        "confirmed_at": str((confirmation or {}).get("created_at") or ""),
                    })
                else:
                    booking_positive_payments.append(match_row)
            elif invoice.get("include_in_totals"):
                manual_invoice_payments.append(match_row)

    matched_manual, unmatched_manual = _match_cash_items(manual_invoice_payments, income_ledger)
    for row in unmatched_manual:
        income_ledger.append({
            **row,
            "category": "Other business income",
            "transaction_type": "income",
            "included": True,
            "source": "manual invoice",
            "income_source": "explicit manual cash receipt",
            "description": f"{row.get('invoice_number', '')} - {row.get('description', '')}".strip(" -"),
        })
    if unmatched_manual:
        checks.append(_issue("manual_income_not_in_bank", "warning", "Manual invoice income is not present in the bank ledger", unmatched_manual, "Confirm this was cash or other genuine income before relying on the total."))

    bank_income_for_matching = [
        row for row in income_ledger
        if row.get("source") == "bank" and row.get("included")
    ]
    booking_by_key = {row["id"]: row for row in booking_positive_payments}
    bank_by_id = {row["id"]: row for row in bank_income_for_matching}
    used_booking_keys: set[str] = set()
    used_bank_ids: set[str] = set()
    manual_matched_booking: list[dict] = []
    valid_combined_matches: list[dict] = []
    invalid_combined_matches: list[dict] = []

    for match in (bank_matches or []):
        match_id = str(match.get("id") or "")
        payment_keys = [str(item) for item in (match.get("payment_keys") or [])]
        bank_id = str(match.get("bank_transaction_id") or "")
        selected = [booking_by_key.get(key) for key in payment_keys]
        bank_row = bank_by_id.get(bank_id)
        problem = ""
        if len(payment_keys) < 2 or len(set(payment_keys)) != len(payment_keys):
            problem = "The combined match must contain at least two unique Booking payments."
        elif any(item is None for item in selected):
            problem = "One or more Booking payments no longer exists in this tax year."
        elif not bank_row:
            problem = "The linked bank-income transaction no longer exists in this tax year."
        elif used_bank_ids.intersection({bank_id}) or used_booking_keys.intersection(payment_keys):
            problem = "A bank transaction or Booking payment is used by more than one combined match."
        elif money(sum(item["amount"] for item in selected if item)) != money(bank_row.get("amount")):
            problem = "The selected Booking payments no longer equal the linked bank receipt."
        if problem:
            invalid_combined_matches.append({
                "id": match_id,
                "date": str(match.get("created_at") or ""),
                "description": str(match.get("bank_description") or "Combined bank match"),
                "amount": money(match.get("bank_amount")),
                "problem": problem,
            })
            continue

        used_bank_ids.add(bank_id)
        used_booking_keys.update(payment_keys)
        matched_rows = []
        for row in selected:
            matched_row = {
                **row,
                "bank_transaction_id": bank_id,
                "bank_description": bank_row.get("description", ""),
                "match_type": "combined bank receipt",
                "combined_match_id": match_id,
            }
            manual_matched_booking.append(matched_row)
            matched_rows.append(matched_row)
        valid_combined_matches.append({
            "id": match_id,
            "bank_transaction_id": bank_id,
            "bank_description": bank_row.get("description", ""),
            "bank_date": bank_row.get("date", ""),
            "bank_amount": money(bank_row.get("amount")),
            "payment_keys": payment_keys,
            "payments": matched_rows,
            "reason": str(match.get("reason") or ""),
            "created_at": str(match.get("created_at") or ""),
            "created_by": str(match.get("created_by") or ""),
        })

    automatic_booking_rows = [row for row in booking_positive_payments if row["id"] not in used_booking_keys]
    automatic_bank_rows = [row for row in bank_income_for_matching if row["id"] not in used_bank_ids]
    automatic_matched_booking, unmatched_booking = _match_cash_items(automatic_booking_rows, automatic_bank_rows)
    matched_booking = manual_matched_booking + automatic_matched_booking
    automatically_used_bank_ids = {str(row.get("bank_transaction_id") or "") for row in automatic_matched_booking}
    bank_match_candidates = [
        row for row in automatic_bank_rows
        if row["id"] not in automatically_used_bank_ids
    ]
    if invalid_combined_matches:
        checks.append(_issue(
            "invalid_combined_bank_matches",
            "blocker",
            "Combined bank-payment matches need attention",
            invalid_combined_matches,
            "Remove the invalid match and create it again against the correct bank receipt.",
        ))
    if unmatched_booking:
        checks.append(_issue("unmatched_booking_payments", "warning", "Booking payments not matched to an imported bank receipt", unmatched_booking, "Check that every relevant bank statement has been imported; timing and combined payments can also cause unmatched items."))

    # Cash handed over in person is genuine income even though no bank receipt
    # exists. It is included exactly once after either being recorded as Cash
    # in Booking or explicitly confirmed in Accounts.
    for row in booking_cash_payments:
        income_ledger.append({
            **row,
            "category": "Other business income",
            "transaction_type": "income",
            "included": True,
            "source": "booking cash",
            "income_source": "confirmed cash receipt",
            "description": f"{row.get('invoice_number', '')} - {row.get('description', '')}".strip(" -"),
        })

    possible_cash_bank_duplicates = []
    bank_income_rows = [row for row in income_ledger if row.get("source") == "bank" and row.get("included")]
    for cash_row in booking_cash_payments:
        if any(
            money(bank_row.get("amount")) == money(cash_row.get("amount"))
            and iso_date(bank_row.get("date")) == iso_date(cash_row.get("date"))
            for bank_row in bank_income_rows
        ):
            possible_cash_bank_duplicates.append(cash_row)
    if possible_cash_bank_duplicates:
        checks.append(_issue(
            "cash_bank_duplicates",
            "blocker",
            "Cash receipts may also be present in the bank ledger",
            possible_cash_bank_duplicates,
            "If the cash was paid into the bank, exclude that bank deposit from totals; otherwise undo the cash confirmation.",
        ))

    pending_statements = [
        {
            "id": item.get("id", ""),
            "description": item.get("file_name", ""),
            "status": item.get("parse_status", "pending"),
            "amount": 0,
        }
        for item in bank_statements
        if not item.get("processed") or item.get("parse_status") == "error"
    ]
    if pending_statements:
        checks.append(_issue("unprocessed_statements", "warning", "Bank statements are pending or failed", pending_statements, "Check whether these statements belong to this tax year and extract them if required."))

    capital_review = [row for row in expense_ledger if row["included"] and row.get("category") == "Equipment & Gear"]
    if capital_review:
        checks.append(_issue("capital_items_review", "warning", "Equipment purchases may need capital treatment", capital_review, "Review equipment purchases before filing, particularly higher-value items."))

    bank_income = round(sum(row["amount"] for row in income_ledger if row["included"] and row.get("source") == "bank"), 2)
    other_income = round(sum(row["amount"] for row in income_ledger if row["included"] and row.get("source") != "bank"), 2)
    bank_expenses = round(sum(row["amount"] for row in expense_ledger if row["included"] and row.get("source") == "bank"), 2)
    manual_expenses = round(sum(row["amount"] for row in expense_ledger if row["included"] and row.get("source") == "manual expense"), 2)
    mileage_total = round(sum(money(row.get("amount")) for row in mileage), 2)
    turnover = round(bank_income + other_income, 2)
    allowable_expenses = round(bank_expenses + manual_expenses + mileage_total, 2)
    profit = round(turnover - allowable_expenses, 2)

    category_totals: dict[str, float] = defaultdict(float)
    for row in expense_ledger:
        if row["included"]:
            category_totals[row.get("category") or "Uncategorised"] += row["amount"]
    if mileage_total:
        category_totals["Travel & Mileage"] += mileage_total
    category_summary = [
        {"category": category, "amount": round(amount, 2)}
        for category, amount in sorted(category_totals.items(), key=lambda item: (-item[1], item[0]))
    ]

    quarters = []
    start_year = int(tax_year[:4])
    quarter_labels = {
        "Q1": f"6 Apr - 5 Jul {start_year}",
        "Q2": f"6 Jul - 5 Oct {start_year}",
        "Q3": f"6 Oct {start_year} - 5 Jan {start_year + 1}",
        "Q4": f"6 Jan - 5 Apr {start_year + 1}",
    }
    for quarter in ("Q1", "Q2", "Q3", "Q4"):
        q_income = round(sum(row["amount"] for row in income_ledger if row["included"] and _quarter_for(row.get("date"), tax_year) == quarter), 2)
        q_expenses = round(sum(row["amount"] for row in expense_ledger if row["included"] and _quarter_for(row.get("date"), tax_year) == quarter), 2)
        q_mileage = round(sum(money(row.get("amount")) for row in mileage if _quarter_for(row.get("date"), tax_year) == quarter), 2)
        quarters.append({
            "name": quarter,
            "label": quarter_labels[quarter],
            "income": q_income,
            "expenses": round(q_expenses + q_mileage, 2),
            "profit": round(q_income - q_expenses - q_mileage, 2),
        })

    blockers = [item for item in checks if item["severity"] == "blocker"]
    warnings = [item for item in checks if item["severity"] == "warning"]
    receipt_index = [
        {
            "expense_id": row["id"],
            "date": row["date"],
            "description": row["description"],
            "supplier": row.get("supplier", ""),
            "amount": row["amount"],
            "included": row["included"],
            "file_name": row.get("receipt_file", ""),
        }
        for row in expense_ledger if row.get("source") == "manual expense"
    ]

    return {
        "format": PACK_FORMAT,
        "version": PACK_VERSION,
        "tax_year": tax_year,
        "business_name": business_name,
        "generated_at": generated_at,
        "basis": "cash",
        "submission_status": "preparation_only",
        "summary": {
            "bank_income": bank_income,
            "other_cash_income": other_income,
            "turnover": turnover,
            "bank_expenses": bank_expenses,
            "manual_expenses": manual_expenses,
            "mileage": mileage_total,
            "allowable_expenses": allowable_expenses,
            "net_profit": profit,
            "owner_withdrawals": round(owner_withdrawals, 2),
            "tax_payments": round(tax_payments, 2),
        },
        "quarters": quarters,
        "category_summary": category_summary,
        "income_ledger": income_ledger,
        "expense_ledger": expense_ledger,
        "transaction_ledger": transaction_ledger,
        "mileage_ledger": mileage,
        "invoice_payment_audit": invoice_payment_audit,
        "booking_reconciliation": {
            "booking_payments": len(booking_positive_payments) + len(booking_cash_payments),
            "matched": len(matched_booking),
            "unmatched": len(unmatched_booking),
            "confirmed_cash": len(booking_cash_payments),
            "matched_rows": matched_booking,
            "unmatched_rows": unmatched_booking,
            "cash_rows": booking_cash_payments,
            "combined_matches": valid_combined_matches,
            "bank_match_candidates": bank_match_candidates,
        },
        "manual_income_reconciliation": {
            "manual_payments": len(manual_invoice_payments),
            "matched_to_bank": len(matched_manual),
            "included_as_other_cash_income": len(unmatched_manual),
        },
        "receipt_index": receipt_index,
        "bank_statements": [
            {
                "id": str(item.get("id") or ""),
                "file_name": str(item.get("file_name") or ""),
                "processed": bool(item.get("processed")),
                "parse_status": str(item.get("parse_status") or ""),
                "transaction_count": int(item.get("transaction_count") or 0),
            }
            for item in bank_statements
        ],
        "validation": {
            "ready_to_close": not blockers,
            "blocker_count": len(blockers),
            "warning_count": len(warnings),
            "checks": checks,
        },
        "source_counts": {
            "transactions": len(transactions),
            "manual_expenses": len(expenses),
            "mileage_entries": len(mileage),
            "invoices_reviewed": len(invoices),
            "bank_statements": len(bank_statements),
            "cash_confirmations": len(active_cash_confirmations),
            "combined_bank_matches": len(valid_combined_matches),
        },
    }


def snapshot_digest(snapshot: dict) -> str:
    canonical = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def generate_summary_pdf(snapshot: dict, output_path: Path, logo_path: Path | None = None) -> None:
    import reportlab
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    output_path.parent.mkdir(parents=True, exist_ok=True)
    font_dir = Path(reportlab.__file__).resolve().parent / "fonts"
    body_font = "TaxVera"
    bold_font = "TaxVeraBold"
    if body_font not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(body_font, str(font_dir / "Vera.ttf")))
    if bold_font not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(bold_font, str(font_dir / "VeraBd.ttf")))
    styles = getSampleStyleSheet()
    title = ParagraphStyle("TaxTitle", parent=styles["Title"], fontName=bold_font, fontSize=22, leading=26, textColor=colors.HexColor("#1f2933"), alignment=TA_LEFT)
    heading = ParagraphStyle("TaxHeading", parent=styles["Heading2"], fontName=bold_font, fontSize=12, leading=15, textColor=colors.HexColor("#1f2933"), spaceBefore=6, spaceAfter=6)
    normal = ParagraphStyle("TaxNormal", parent=styles["BodyText"], fontName=body_font, fontSize=9, leading=13, textColor=colors.HexColor("#475569"))
    small = ParagraphStyle("TaxSmall", parent=normal, fontSize=7.5, leading=10, textColor=colors.HexColor("#64748b"))
    right = ParagraphStyle("TaxRight", parent=normal, alignment=TA_RIGHT)
    gold = colors.HexColor("#b38a3e")
    pale = colors.HexColor("#f7f3ea")

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#e7e5e4"))
        canvas.line(18 * mm, 14 * mm, 192 * mm, 14 * mm)
        canvas.setFont(body_font, 7)
        canvas.setFillColor(colors.HexColor("#78716c"))
        canvas.drawString(18 * mm, 9 * mm, f"{snapshot['business_name']} - Tax year {snapshot['tax_year']} - Preparation record")
        canvas.drawRightString(192 * mm, 9 * mm, f"Page {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(str(output_path), pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm, topMargin=16 * mm, bottomMargin=20 * mm, title=f"Tax Year {snapshot['tax_year']} Annual Summary")
    story = []
    if logo_path and logo_path.is_file():
        story.append(Image(str(logo_path), width=48 * mm, height=28 * mm, kind="proportional"))
        story.append(Spacer(1, 2 * mm))
    story.append(Paragraph("Tax Year Close", title))
    story.append(Paragraph(f"{snapshot['business_name']} | {snapshot['tax_year']}", heading))
    story.append(Paragraph("Cash-basis preparation pack. Income is recorded when received and expenses when paid. This document is supporting working paper and is not proof that a tax return or MTD update has been submitted to HMRC.", normal))
    story.append(Spacer(1, 6 * mm))

    summary = snapshot["summary"]
    summary_rows = [
        [Paragraph("Turnover", heading), Paragraph(f"GBP {summary['turnover']:,.2f}", right)],
        [Paragraph("Allowable expenses", heading), Paragraph(f"GBP {summary['allowable_expenses']:,.2f}", right)],
        [Paragraph("Net business profit", heading), Paragraph(f"GBP {summary['net_profit']:,.2f}", right)],
    ]
    summary_table = Table(summary_rows, colWidths=[110 * mm, 58 * mm])
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), pale),
        ("BOX", (0, 0), (-1, -1), 0.75, gold),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#ded7c8")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 7 * mm))

    story.append(Paragraph("Income and expense sources", heading))
    detail_rows = [
        ["Bank income received", f"GBP {summary['bank_income']:,.2f}"],
        ["Other genuine cash income", f"GBP {summary['other_cash_income']:,.2f}"],
        ["Bank expenses", f"GBP {summary['bank_expenses']:,.2f}"],
        ["Independent manual expenses", f"GBP {summary['manual_expenses']:,.2f}"],
        ["Mileage claim", f"GBP {summary['mileage']:,.2f}"],
        ["Owner withdrawals excluded", f"GBP {summary['owner_withdrawals']:,.2f}"],
        ["HMRC payments excluded", f"GBP {summary['tax_payments']:,.2f}"],
    ]
    detail_table = Table([[Paragraph(str(a), normal), Paragraph(str(b), right)] for a, b in detail_rows], colWidths=[110 * mm, 58 * mm])
    detail_table.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, -1), 0.35, colors.HexColor("#e7e5e4")),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(detail_table)
    story.append(Spacer(1, 7 * mm))

    story.append(Paragraph("Quarterly view", heading))
    quarter_rows = [["Quarter", "Period", "Income", "Expenses", "Profit"]]
    for item in snapshot["quarters"]:
        quarter_rows.append([item["name"], item["label"], f"{item['income']:,.2f}", f"{item['expenses']:,.2f}", f"{item['profit']:,.2f}"])
    quarter_table = Table(quarter_rows, colWidths=[15 * mm, 63 * mm, 30 * mm, 30 * mm, 30 * mm], repeatRows=1)
    quarter_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2933")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), bold_font),
        ("FONTNAME", (0, 1), (-1, -1), body_font),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#d6d3d1")),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(quarter_table)

    story.append(PageBreak())
    story.append(Paragraph("Expense categories", title))
    story.append(Spacer(1, 3 * mm))
    if snapshot["category_summary"]:
        category_rows = [["Category", "Amount"]] + [[item["category"], f"GBP {item['amount']:,.2f}"] for item in snapshot["category_summary"]]
        category_table = Table(category_rows, colWidths=[125 * mm, 43 * mm], repeatRows=1)
        category_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2933")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), bold_font),
            ("FONTNAME", (0, 1), (-1, -1), body_font),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ALIGN", (1, 1), (1, -1), "RIGHT"),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#d6d3d1")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#fafaf9")]),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(category_table)
    else:
        story.append(Paragraph("No included expenses were recorded for this tax year.", normal))
    story.append(Spacer(1, 8 * mm))
    story.append(Paragraph("Close checks", heading))
    story.append(Spacer(1, 3 * mm))
    validation = snapshot["validation"]
    story.append(Paragraph(f"Blocking issues: {validation['blocker_count']} | Warnings recorded: {validation['warning_count']}", normal))
    for item in validation["checks"]:
        label = "BLOCKER" if item["severity"] == "blocker" else "WARNING"
        story.append(Paragraph(f"<b>{label}: {item['title']}</b> - {item['count']} record(s). {item['guidance']}", small))
        story.append(Spacer(1, 2 * mm))
    if not validation["checks"]:
        story.append(Paragraph("No exceptions were found when this tax year was closed.", normal))
    story.append(Spacer(1, 8 * mm))
    story.append(Paragraph("Audit information", heading))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(f"Snapshot generated: {snapshot['generated_at']}<br/>Source records: {json.dumps(snapshot['source_counts'], sort_keys=True)}<br/>The full ledgers, evidence index, reconciliation results and immutable manifest are included in the accompanying ZIP.", small))

    doc.build(story, onFirstPage=footer, onLaterPages=footer)


def _safe_name(value: str, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(str(value or "")).name).strip("._")
    return cleaned[:160] or fallback


def build_evidence_pack(
    *,
    snapshot: dict,
    output_path: Path,
    build_id: str,
    evidence_files: list[dict],
    logo_path: Path | None = None,
) -> dict:
    """Create an immutable ZIP and return its manifest metadata."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="tax-close-", dir=str(output_path.parent)) as folder:
        root = Path(folder)
        reports = root / "reports"
        evidence = root / "evidence"
        reports.mkdir(parents=True, exist_ok=True)
        evidence.mkdir(parents=True, exist_ok=True)

        pdf_path = reports / "annual-summary.pdf"
        generate_summary_pdf(snapshot, pdf_path, logo_path=logo_path)
        (reports / "annual-summary.csv").write_bytes(_summary_csv(snapshot))
        (reports / "income-ledger.csv").write_bytes(_csv_bytes(
            ["Date", "Description", "Source", "Amount", "Included"],
            ([row.get("date", ""), row.get("description", ""), row.get("income_source", row.get("source", "")), f"{money(row.get('amount')):.2f}", "Yes" if row.get("included") else "No"] for row in snapshot["income_ledger"]),
        ))
        (reports / "expense-ledger.csv").write_bytes(_csv_bytes(
            ["Date", "Description", "Supplier", "Category", "Source", "Amount", "Included", "Exclusion reason"],
            ([row.get("date", ""), row.get("description", ""), row.get("supplier", ""), row.get("category", ""), row.get("expense_source", row.get("source", "")), f"{money(row.get('amount')):.2f}", "Yes" if row.get("included") else "No", row.get("exclusion_reason", "")] for row in snapshot["expense_ledger"]),
        ))
        (reports / "expense-category-summary.csv").write_bytes(_csv_bytes(
            ["Category", "Amount"],
            ([row["category"], f"{row['amount']:.2f}"] for row in snapshot["category_summary"]),
        ))
        (reports / "mileage.csv").write_bytes(_csv_bytes(
            ["Date", "Description", "From", "To", "Miles", "Rate", "Claim"],
            ([display_date(row.get("date")), row.get("description", ""), row.get("from_location", ""), row.get("to_location", ""), row.get("miles", 0), row.get("rate", 0), f"{money(row.get('amount')):.2f}"] for row in snapshot["mileage_ledger"]),
        ))
        (reports / "invoice-payment-audit.csv").write_bytes(_csv_bytes(
            ["Invoice", "Previous reference", "Client", "Status", "Payment date", "Payment amount", "Payment type", "Reference", "Source"],
            ([row.get("invoice_number", ""), row.get("legacy_invoice_number", ""), row.get("client", ""), row.get("status", ""), row.get("payment_date", ""), f"{money(row.get('payment_amount')):.2f}", row.get("payment_type", ""), row.get("reference", ""), row.get("source_system", "")] for row in snapshot["invoice_payment_audit"]),
        ))
        reconciliation_rows = (
            snapshot["booking_reconciliation"]["matched_rows"]
            + snapshot["booking_reconciliation"]["unmatched_rows"]
            + snapshot["booking_reconciliation"].get("cash_rows", [])
        )
        matched_ids = {row.get("id") for row in snapshot["booking_reconciliation"]["matched_rows"]}
        cash_ids = {row.get("id") for row in snapshot["booking_reconciliation"].get("cash_rows", [])}
        (reports / "booking-bank-reconciliation.csv").write_bytes(_csv_bytes(
            ["Invoice", "Payment date", "Amount", "Treatment", "Bank description", "Cash confirmation reason"],
            ([row.get("invoice_number", ""), row.get("date", ""), f"{money(row.get('amount')):.2f}", "Combined bank receipt" if row.get("match_type") == "combined bank receipt" else ("Matched to bank" if row.get("id") in matched_ids else ("Cash received" if row.get("id") in cash_ids else "Unmatched")), row.get("bank_description", ""), row.get("confirmation_reason", "")] for row in reconciliation_rows),
        ))
        (reports / "receipt-index.csv").write_bytes(_csv_bytes(
            ["Date", "Description", "Supplier", "Amount", "Included", "Evidence file"],
            ([row.get("date", ""), row.get("description", ""), row.get("supplier", ""), f"{money(row.get('amount')):.2f}", "Yes" if row.get("included") else "No", row.get("file_name", "")] for row in snapshot["receipt_index"]),
        ))
        exception_rows = []
        for check in snapshot["validation"]["checks"]:
            exception_rows.append([check["severity"], check["code"], check["title"], check["count"], f"{check['amount']:.2f}", check["guidance"]])
        (reports / "exceptions-and-warnings.csv").write_bytes(_csv_bytes(
            ["Severity", "Code", "Check", "Records", "Amount", "Guidance"], exception_rows,
        ))

        copied_files = []
        used_names: set[str] = set()
        for item in evidence_files:
            source = Path(str(item.get("source_path") or ""))
            if not source.is_file():
                continue
            category = _safe_name(str(item.get("category") or "other"), "other")
            desired = _safe_name(str(item.get("file_name") or source.name), source.name)
            key = f"{category}/{desired}".lower()
            if key in used_names:
                desired = f"{_safe_name(str(item.get('record_id') or ''), 'record')}_{desired}"
                key = f"{category}/{desired}".lower()
            used_names.add(key)
            target = evidence / category / desired
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            copied_files.append({"category": category, "file": f"evidence/{category}/{desired}", "size": target.stat().st_size})

        snapshot_path = root / "snapshot.json"
        snapshot_path.write_text(json.dumps(snapshot, indent=2, sort_keys=True, default=str), encoding="utf-8")
        readme = root / "README-FIRST.txt"
        readme.write_text(
            f"{snapshot['business_name']} - Tax Year {snapshot['tax_year']}\n"
            "============================================================\n\n"
            "This is an immutable cash-basis preparation and evidence pack.\n"
            "It does not prove that a Self Assessment return or Making Tax Digital update was submitted to HMRC.\n\n"
            "Start with reports/annual-summary.pdf and reports/exceptions-and-warnings.csv.\n"
            "The snapshot digest in manifest.json can be used to verify that the close snapshot has not changed.\n"
            "Keep this pack together with the original records for the statutory retention period.\n",
            encoding="utf-8",
        )

        file_hashes = {}
        for file_path in sorted(path for path in root.rglob("*") if path.is_file()):
            relative = file_path.relative_to(root).as_posix()
            file_hashes[relative] = {
                "sha256": hashlib.sha256(file_path.read_bytes()).hexdigest(),
                "size": file_path.stat().st_size,
            }
        manifest = {
            "format": PACK_FORMAT,
            "version": PACK_VERSION,
            "build": build_id,
            "business_name": snapshot["business_name"],
            "tax_year": snapshot["tax_year"],
            "created_at": snapshot["generated_at"],
            "snapshot_sha256": snapshot_digest(snapshot),
            "summary": snapshot["summary"],
            "validation": snapshot["validation"],
            "evidence_files": copied_files,
            "files": file_hashes,
        }
        (root / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

        temp_zip = output_path.with_suffix(".tmp")
        with zipfile.ZipFile(temp_zip, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
            for file_path in sorted(path for path in root.rglob("*") if path.is_file()):
                archive.write(file_path, file_path.relative_to(root).as_posix())
        with zipfile.ZipFile(temp_zip, "r") as archive:
            bad = archive.testzip()
            if bad:
                raise RuntimeError(f"Evidence pack failed ZIP verification at {bad}")
        temp_zip.replace(output_path)
        return {
            "pack_path": str(output_path),
            "pack_filename": output_path.name,
            "pack_size": output_path.stat().st_size,
            "pack_sha256": hashlib.sha256(output_path.read_bytes()).hexdigest(),
            "snapshot_sha256": manifest["snapshot_sha256"],
            "evidence_file_count": len(copied_files),
        }
