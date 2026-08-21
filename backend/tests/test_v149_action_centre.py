from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_action_centre_and_tidy_up_are_wired_into_the_frontend():
    tax_prep = (ROOT / "frontend" / "src" / "pages" / "TaxPrep.jsx").read_text()
    tidy_up = (ROOT / "frontend" / "src" / "pages" / "TidyUp.jsx").read_text()
    app = (ROOT / "frontend" / "src" / "App.js").read_text()
    layout = (ROOT / "frontend" / "src" / "components" / "Layout.jsx").read_text()

    assert "Close Checks Action Centre" in tax_prep
    assert "Save and recheck" in tax_prep
    assert "Paid personally / personal credit card" in tax_prep
    assert "Attach the missing receipt" in tax_prep
    assert "Link to the matching business-bank payment" in tax_prep
    assert "Batch categorise similar records" in tax_prep
    assert "Accounts Tidy-up" in tidy_up
    assert 'path="tidy-up"' in app
    assert 'path: "/tidy-up"' in layout


def test_booking_integration_remains_disabled_in_the_truenas_compose_file():
    compose = (ROOT / "docker-compose-truenas.yml").read_text()
    assert 'BOOKING_INTEGRATION_ENABLED: "false"' in compose
