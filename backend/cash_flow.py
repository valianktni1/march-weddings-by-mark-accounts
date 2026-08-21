"""Cash-flow projections built from outstanding invoices and planned commitments.

This module is deliberately side-effect free so projections can be tested
without a database. Forecast figures are planning aids, not tax totals.
"""

from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from typing import Any


CLOSED_STATUSES = {"paid", "paid in full", "cancelled", "canceled", "void", "refunded"}
RECURRENCES = {"none", "weekly", "monthly", "quarterly", "yearly"}


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


def display_date(value: date) -> str:
    return value.strftime("%d/%m/%Y")


def add_months(value: date, months: int, anchor_day: int | None = None) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, min(anchor_day or value.day, calendar.monthrange(year, month)[1]))


def outstanding_balance(invoice: dict) -> float:
    status = str(invoice.get("status") or "").strip().lower().replace("_", " ")
    if status in CLOSED_STATUSES:
        return 0.0
    if invoice.get("balance_remaining") is not None:
        return max(0.0, money(invoice.get("balance_remaining")))
    total = money(invoice.get("total_price") or invoice.get("amount"))
    received = money(invoice.get("deposit_amount")) + money(invoice.get("interim_payment"))
    return max(0.0, round(total - received, 2))


def invoice_due_date(invoice: dict) -> date | None:
    due = parse_date(invoice.get("final_payment_due") or invoice.get("due_date"))
    if due:
        return due
    wedding = parse_date(invoice.get("wedding_date") or invoice.get("date"))
    return wedding - timedelta(days=45) if wedding else None


def commitment_dates(commitment: dict, today: date, horizon_end: date) -> list[date]:
    due = parse_date(commitment.get("next_due_date"))
    recurrence = str(commitment.get("recurrence") or "none").lower()
    if not due or recurrence not in RECURRENCES or not commitment.get("active", True):
        return []
    if recurrence == "none":
        return [due] if due <= horizon_end else []

    step_days = {"weekly": 7}.get(recurrence)
    step_months = {"monthly": 1, "quarterly": 3, "yearly": 12}.get(recurrence)
    anchor_day = due.day
    while due < today:
        due = due + timedelta(days=step_days) if step_days else add_months(due, step_months or 1, anchor_day)
    dates: list[date] = []
    while due <= horizon_end:
        dates.append(due)
        due = due + timedelta(days=step_days) if step_days else add_months(due, step_months or 1, anchor_day)
    return dates


def build_cash_flow_forecast(
    *, invoices: list[dict], commitments: list[dict], today: date,
    starting_balance: float | None = None, horizon_days: int = 90,
) -> dict:
    horizon_days = max(1, min(int(horizon_days), 365))
    horizon_end = today + timedelta(days=horizon_days)
    incoming: list[dict] = []
    missing_due_dates: list[dict] = []

    for invoice in invoices:
        amount = outstanding_balance(invoice)
        if amount <= 0.009:
            continue
        due = invoice_due_date(invoice)
        row = {
            "id": str(invoice.get("id") or ""),
            "invoice_number": str(invoice.get("invoice_number") or ""),
            "description": str(invoice.get("couple_names") or invoice.get("client_name") or "Invoice balance"),
            "amount": amount,
            "wedding_date": str(invoice.get("wedding_date") or ""),
            "path": f"/invoices?focus={invoice.get('id', '')}",
        }
        if not due:
            missing_due_dates.append(row)
            continue
        if due > horizon_end:
            continue
        incoming.append({
            **row,
            "due_date": display_date(due),
            "days_from_today": (due - today).days,
            "overdue": due < today,
        })

    outgoing: list[dict] = []
    for commitment in commitments:
        for due in commitment_dates(commitment, today, horizon_end):
            outgoing.append({
                "id": str(commitment.get("id") or ""),
                "description": str(commitment.get("description") or "Planned outgoing"),
                "category": str(commitment.get("category") or ""),
                "amount": abs(money(commitment.get("amount"))),
                "due_date": display_date(due),
                "days_from_today": (due - today).days,
                "overdue": due < today,
                "recurrence": str(commitment.get("recurrence") or "none"),
            })

    incoming.sort(key=lambda item: (item["days_from_today"], item["description"]))
    outgoing.sort(key=lambda item: (item["days_from_today"], item["description"]))
    windows = []
    for days in (30, 60, 90):
        if days > horizon_days:
            continue
        money_in = round(sum(row["amount"] for row in incoming if row["days_from_today"] <= days), 2)
        money_out = round(sum(row["amount"] for row in outgoing if row["days_from_today"] <= days), 2)
        net = round(money_in - money_out, 2)
        windows.append({
            "days": days,
            "incoming": money_in,
            "outgoing": money_out,
            "net": net,
            "projected_balance": round(starting_balance + net, 2) if starting_balance is not None else None,
        })

    return {
        "as_of": display_date(today),
        "horizon_days": horizon_days,
        "starting_balance": round(starting_balance, 2) if starting_balance is not None else None,
        "starting_balance_configured": starting_balance is not None,
        "windows": windows,
        "incoming": incoming,
        "outgoing": outgoing,
        "missing_due_dates": missing_due_dates,
        "totals": {
            "incoming": round(sum(row["amount"] for row in incoming), 2),
            "outgoing": round(sum(row["amount"] for row in outgoing), 2),
            "net": round(sum(row["amount"] for row in incoming) - sum(row["amount"] for row in outgoing), 2),
        },
    }
