from datetime import date
from pathlib import Path

from cash_flow import build_cash_flow_forecast, commitment_dates, outstanding_balance
from mileage_calculator import normalise_trip_miles


ROOT = Path(__file__).resolve().parents[2]


def test_forecast_uses_real_outstanding_balances_and_due_dates():
    forecast = build_cash_flow_forecast(
        invoices=[
            {
                "id": "invoice-1",
                "invoice_number": "WBM01001",
                "couple_names": "Alex & Sam",
                "total_price": 1200,
                "deposit_amount": 200,
                "interim_payment": 100,
                "final_payment_due": "20/09/2026",
                "status": "part_paid",
            },
            {
                "id": "paid",
                "total_price": 999,
                "final_payment_due": "01/09/2026",
                "status": "Paid in Full",
            },
        ],
        commitments=[
            {"id": "software", "description": "Software", "amount": 50, "next_due_date": "25/08/2026", "recurrence": "monthly", "active": True},
        ],
        today=date(2026, 8, 21),
        starting_balance=500,
        horizon_days=90,
    )

    assert outstanding_balance({"total_price": 1200, "deposit_amount": 200, "interim_payment": 100}) == 900
    assert forecast["totals"] == {"incoming": 900.0, "outgoing": 150.0, "net": 750.0}
    assert forecast["windows"][0]["incoming"] == 900.0
    assert forecast["windows"][0]["outgoing"] == 50.0
    assert forecast["windows"][0]["projected_balance"] == 1350.0


def test_missing_due_dates_are_shown_but_never_guessed():
    forecast = build_cash_flow_forecast(
        invoices=[{"id": "invoice-2", "invoice_number": "WBM01002", "total_price": 500, "status": "Pending"}],
        commitments=[],
        today=date(2026, 8, 21),
    )
    assert forecast["incoming"] == []
    assert forecast["totals"]["incoming"] == 0
    assert forecast["missing_due_dates"][0]["invoice_number"] == "WBM01002"


def test_recurring_month_end_dates_are_safe():
    dates = commitment_dates(
        {"next_due_date": "31/08/2026", "recurrence": "monthly", "active": True},
        date(2026, 8, 21),
        date(2026, 11, 30),
    )
    assert dates == [date(2026, 8, 31), date(2026, 9, 30), date(2026, 10, 31), date(2026, 11, 30)]


def test_cash_flow_and_navigation_are_wired_without_enabling_booking_sync():
    app = (ROOT / "frontend" / "src" / "App.js").read_text()
    layout = (ROOT / "frontend" / "src" / "components" / "Layout.jsx").read_text()
    dashboard = (ROOT / "frontend" / "src" / "pages" / "Dashboard.jsx").read_text()
    cash_flow = (ROOT / "frontend" / "src" / "pages" / "CashFlow.jsx").read_text()
    server = (ROOT / "backend" / "server.py").read_text()
    compose = (ROOT / "docker-compose-truenas.yml").read_text()

    assert 'path="cash-flow"' in app
    assert 'path: "/cash-flow"' in layout
    assert "global-search" in layout
    assert "navigate(-1)" in layout and "navigate(1)" in layout
    assert "Quick actions" in dashboard and "Recent records" in dashboard
    assert "Planning only" in cash_flow
    assert '"cash_flow_commitments"' in server
    assert 'BOOKING_INTEGRATION_ENABLED: "false"' in compose


def test_round_trip_mileage_is_saved_as_an_explicit_audit_field():
    server = (ROOT / "backend" / "server.py").read_text()
    mileage = (ROOT / "frontend" / "src" / "pages" / "Mileage.jsx").read_text()

    assert 'round_trip = entry.get("round_trip") is True' in server
    assert '"one_way_miles": one_way_miles' in server
    assert "Round trip - double this mileage" in mileage
    assert "each way" in mileage


def test_round_trip_mileage_doubles_once_and_preserves_one_way_evidence():
    assert normalise_trip_miles("42.7", True) == (85.4, 42.7)
    assert normalise_trip_miles("42.7", False) == (42.7, None)
