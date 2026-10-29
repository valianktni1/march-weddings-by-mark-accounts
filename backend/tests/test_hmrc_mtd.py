"""Offline regression tests. No HMRC requests or taxpayer data are used."""
import asyncio
import copy
import os
import sys
import time
import uuid
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlparse, parse_qs
from unittest.mock import AsyncMock

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "hmrc_offline_test")
import hmrc_mtd as hmrc
import server

CONTEXT = {
    "device_id": "1a9ab1e0-7465-4c2f-85b8-07d4f793d9dc", "user_agent": "Offline test browser",
    "timezone": "UTC+00:00", "screen_width": 1920, "screen_height": 1080,
    "colour_depth": 24, "scale": 1, "window_width": 1200, "window_height": 800,
}
SNAPSHOT = {
    "income_ledger": [{"date": "07/04/2026", "amount": 200, "included": True}, {"date": "07/07/2026", "amount": 300, "included": True}, {"date": "07/10/2026", "amount": 400, "included": True}, {"date": "07/04/2026", "amount": 999, "included": False}],
    "expense_ledger": [{"date": "09/04/2026", "amount": 50, "included": True}, {"date": "09/07/2026", "amount": 60, "included": True}, {"date": "09/07/2026", "amount": 60, "included": False}],
    "mileage_ledger": [{"date": "10/07/2026", "amount": 5.5}], "validation": {"blocker_count": 0},
}


def matches(row, query):
    for key, value in query.items():
        if isinstance(value, dict):
            if "$gt" in value and not row.get(key, 0) > value["$gt"]:
                return False
        elif row.get(key) != value:
            return False
    return True


class Cursor:
    def __init__(self, rows): self.rows = rows
    def sort(self, key, direction):
        self.rows.sort(key=lambda x: x.get(key, ""), reverse=direction < 0)
        return self
    async def to_list(self, limit): return copy.deepcopy(self.rows[:limit])


class Collection:
    def __init__(self): self.rows = []
    async def find_one(self, query, projection=None):
        return copy.deepcopy(next((r for r in self.rows if matches(r, query)), None))
    def find(self, query, projection=None):
        rows = [copy.deepcopy(r) for r in self.rows if matches(r, query)]
        if projection:
            for r in rows:
                for k, v in projection.items():
                    if v == 0: r.pop(k, None)
        return Cursor(rows)
    async def insert_one(self, row): self.rows.append(copy.deepcopy(row))
    async def update_one(self, query, update, upsert=False):
        row = next((r for r in self.rows if matches(r, query)), None)
        if row is None and upsert:
            row = dict(query); self.rows.append(row)
        if row is not None: row.update(copy.deepcopy(update.get("$set", {})))
    async def find_one_and_delete(self, query):
        row = next((r for r in self.rows if matches(r, query)), None)
        if row is None: return None
        self.rows.remove(row); return copy.deepcopy(row)
    async def delete_one(self, query): await self.find_one_and_delete(query)
    async def delete_many(self, query): self.rows = [r for r in self.rows if not matches(r, query)]
    async def find_one_and_update(self, query, update, **kwargs):
        row = next((r for r in self.rows if matches(r, query)), None)
        if row is None: return None
        row.update(copy.deepcopy(update.get("$set", {})))
        return copy.deepcopy(row)


@pytest.fixture
def workspace(monkeypatch):
    monkeypatch.setenv("HMRC_SANDBOX_ENABLED", "true")
    monkeypatch.setenv("HMRC_ENVIRONMENT", "sandbox")
    monkeypatch.setenv("HMRC_SANDBOX_CLIENT_ID", "offline-client")
    monkeypatch.setenv("HMRC_SANDBOX_CLIENT_SECRET", "offline-secret")
    monkeypatch.setenv("HMRC_TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("HMRC_SANDBOX_NINO", "AA123456A")
    monkeypatch.setenv("HMRC_SANDBOX_TEST_USER_CONFIRMED", "true")
    db = SimpleNamespace(hmrc_connections=Collection(), hmrc_oauth_states=Collection(), hmrc_submissions=Collection())
    snapshot = AsyncMock(return_value=copy.deepcopy(SNAPSHOT))
    app = FastAPI()
    app.middleware("http")(server.protect_application)
    @app.post("/login")
    async def login(request: server.Request):
        request.session.update(admin_email="test@example.test", csrf_token="offline-csrf")
        return {"ok": True}
    app.include_router(hmrc.create_router(lambda: db, snapshot, "https://accounts.example.test", "offline-build"))
    app.add_middleware(SessionMiddleware, secret_key="offline-session-secret", same_site="strict")
    client = TestClient(app)
    client.post("/login")
    client.headers["x-csrf-token"] = "offline-csrf"
    config = hmrc.Settings()
    db.hmrc_connections.rows.append({"_id": "sandbox", "binding": config.binding(), "encrypted_tokens": config.encrypt({"access_token": "offline-access", "refresh_token": "offline-refresh", "expires_at": time.time()+5000})})
    return SimpleNamespace(client=client, db=db, snapshot=snapshot, config=config)


def draft_body(**overrides):
    return {"context": CONTEXT, "tax_year": "2026-27", "quarter": "Q2", "business_id": "XBIS12345678901", **overrides}


def test_cumulative_preview_uses_paid_ledger_and_excludes_linked_receipts():
    q1 = hmrc.local_preview(SNAPSHOT, "2026-27", "Q1")
    q2 = hmrc.local_preview(SNAPSHOT, "2026-27", "Q2")
    assert q1["income"] == 200 and q1["expenses"] == 50
    assert q2["income"] == 500 and q2["expenses"] == 115.5
    assert q2["end"] == "2026-10-05" and q2["can_submit"] is False


@pytest.mark.parametrize("year,quarter", [("2026-28", "Q1"), ("2024-25", "Q1"), ("2026-27", "Q9"), ("../../etc", "Q1")])
def test_bad_reporting_periods_are_rejected(year, quarter):
    with pytest.raises(ValueError): hmrc.period(year, quarter)


def test_preview_detects_missing_dates_and_nonfinite_amounts():
    snapshot = {"income_ledger": [{"included": True, "date": "", "amount": 1}, {"included": True, "date": "07/04/2026", "amount": float("nan")}]}
    result = hmrc.local_preview(snapshot, "2026-27", "Q1")
    assert len(result["problems"]) == 2
    assert result["income"] == 0


def test_sandbox_is_disabled_by_default_and_production_has_no_switch(workspace, monkeypatch):
    monkeypatch.delenv("HMRC_SANDBOX_ENABLED")
    assert workspace.client.post("/api/hmrc/connect").status_code == 409
    monkeypatch.setenv("HMRC_SANDBOX_ENABLED", "true")
    monkeypatch.setenv("HMRC_ENVIRONMENT", "production")
    assert workspace.client.post("/api/hmrc/sandbox/review", json=draft_body()).status_code == 409
    assert workspace.client.get("/api/hmrc/status").json()["production_supported"] is False


def test_authentication_and_csrf_protect_hmrc_routes(workspace):
    workspace.client.cookies.clear()
    assert workspace.client.get("/api/hmrc/status").status_code == 401
    workspace.client.post("/login")
    workspace.client.headers.pop("x-csrf-token")
    assert workspace.client.post("/api/hmrc/connect").status_code == 403


def test_status_and_history_do_not_return_tokens_or_identifiers(workspace):
    status = workspace.client.get("/api/hmrc/status").text
    history = workspace.client.get("/api/hmrc/history").text
    for secret in ("offline-access", "offline-refresh", "offline-secret", "AA123456A", workspace.config.key):
        assert secret not in status + history
    assert "offline-access" not in workspace.db.hmrc_connections.rows[0]["encrypted_tokens"]


def test_oauth_uses_pkce_one_time_state_and_works_without_session_cookie(workspace, monkeypatch):
    token_call = AsyncMock(return_value=httpx.Response(200, json={"access_token": "new-access", "refresh_token": "new-refresh", "expires_in": 3600}))
    monkeypatch.setattr(hmrc, "transport", token_call)
    response = workspace.client.post("/api/hmrc/connect").json()
    query = parse_qs(urlparse(response["url"]).query)
    assert urlparse(response["url"]).hostname == "test-api.service.hmrc.gov.uk"
    assert query["code_challenge_method"] == ["S256"]
    assert "offline-secret" not in response["url"]
    workspace.client.cookies.clear()  # SameSite Strict drops cookies on return.
    callback = workspace.client.get("/api/hmrc/callback", params={"state": query["state"][0], "code": "test-code"}, follow_redirects=False)
    assert callback.status_code == 303 and callback.headers["location"] == "/hmrc?connection=success"
    assert workspace.client.get("/api/hmrc/callback", params={"state": query["state"][0], "code": "test-code"}).status_code == 400
    assert token_call.await_count == 1
    assert "code_verifier" in token_call.call_args.kwargs["data"]


def test_expired_or_invented_oauth_state_cannot_connect(workspace, monkeypatch):
    call = AsyncMock(); monkeypatch.setattr(hmrc, "transport", call)
    url = workspace.client.post("/api/hmrc/connect").json()["url"]
    state = parse_qs(urlparse(url).query)["state"][0]
    workspace.db.hmrc_oauth_states.rows[0]["expires_at"] = 0
    assert workspace.client.get("/api/hmrc/callback", params={"state": state, "code": "x"}).status_code == 400
    assert workspace.client.get("/api/hmrc/callback", params={"state": "invented", "code": "x"}).status_code == 400
    call.assert_not_awaited()


def test_own_accounts_preview_never_calls_hmrc(workspace, monkeypatch):
    call = AsyncMock(); monkeypatch.setattr(hmrc, "transport", call)
    result = workspace.client.get("/api/hmrc/preview/2026-27/Q2")
    assert result.status_code == 200 and result.json()["income"] == 500
    call.assert_not_awaited()


def test_submit_requires_explicit_confirmation_and_sends_only_server_sample(workspace, monkeypatch):
    call = AsyncMock(return_value=httpx.Response(204, headers={"X-CorrelationId": "test-correlation"}))
    monkeypatch.setattr(hmrc, "transport", call)
    review = workspace.client.post("/api/hmrc/sandbox/review", json=draft_body()).json()
    body = {"review_id": review["id"], "context": CONTEXT, "confirmation": "wrong"}
    assert workspace.client.post("/api/hmrc/sandbox/submit", json=body).status_code == 422
    call.assert_not_awaited()
    body.update(confirmation="SEND SAMPLE TO SANDBOX", payload={"periodIncome": {"turnover": 999999}})
    response = workspace.client.post("/api/hmrc/sandbox/submit", json=body)
    assert response.json()["status"] == "accepted"
    assert call.call_args.args[:2] == ("PUT", "/individuals/business/self-employment/AA123456A/XBIS12345678901/cumulative/2026-27")
    assert call.call_args.kwargs["json_body"]["periodIncome"]["turnover"] == 2000
    assert call.call_args.kwargs["headers"]["Accept"] == "application/vnd.hmrc.5.0+json"
    assert workspace.client.post("/api/hmrc/sandbox/submit", json=body).json()["already_processed"] is True
    assert call.await_count == 1
    assert workspace.db.hmrc_submissions.rows[0]["correlation_id"] == "test-correlation"


def test_expired_or_tampered_reviews_are_not_sent(workspace, monkeypatch):
    call = AsyncMock(); monkeypatch.setattr(hmrc, "transport", call)
    for tampered in (False, True):
        review = workspace.client.post("/api/hmrc/sandbox/review", json=draft_body()).json()
        row = workspace.db.hmrc_submissions.rows[-1]
        if tampered: row["payload"]["periodIncome"]["turnover"] = 999999
        else: row["expires_at"] = 0
        assert workspace.client.post("/api/hmrc/sandbox/submit", json={"review_id": review["id"], "context": CONTEXT, "confirmation": "SEND SAMPLE TO SANDBOX"}).status_code == 409
    call.assert_not_awaited()


@pytest.mark.parametrize("outcome,expected", [(400, "rejected"), (503, "unknown"), ("timeout", "unknown")])
def test_failures_are_recorded_and_not_silently_retried(workspace, monkeypatch, outcome, expected):
    call = AsyncMock(side_effect=httpx.ReadTimeout("offline") if outcome == "timeout" else None, return_value=None if outcome == "timeout" else httpx.Response(outcome, json={"code": "TEST_ERROR", "message": "secret should not leak"}))
    monkeypatch.setattr(hmrc, "transport", call)
    review = workspace.client.post("/api/hmrc/sandbox/review", json=draft_body()).json()
    body = {"review_id": review["id"], "context": CONTEXT, "confirmation": "SEND SAMPLE TO SANDBOX"}
    response = workspace.client.post("/api/hmrc/sandbox/submit", json=body)
    assert response.json()["status"] == expected
    assert "secret should not leak" not in response.text
    assert workspace.client.post("/api/hmrc/sandbox/submit", json=body).status_code == 409
    assert call.await_count == 1


def test_header_validator_does_not_treat_http_200_as_valid_headers(workspace, monkeypatch):
    call = AsyncMock(side_effect=[httpx.Response(200, json={"access_token": "application-token"}), httpx.Response(200, json={"code": "INVALID_HEADERS", "errors": []})])
    monkeypatch.setattr(hmrc, "transport", call)
    result = workspace.client.post("/api/hmrc/sandbox/check-headers", json={"tax_year": "2026-27", "context": CONTEXT}).json()
    assert result["valid"] is False
    assert "Gov-Client-Multi-Factor" in result["missing_headers"]
    assert call.call_args.kwargs["headers"]["Authorization"] == "Bearer application-token"


def test_forwarded_headers_are_not_trusted_unless_explicitly_configured(monkeypatch):
    monkeypatch.delenv("HMRC_TRUST_EDGE_HEADERS", raising=False)
    req = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1", port=1234), headers={"x-hmrc-client-ip": "8.8.8.8", "x-hmrc-client-port": "443"}, session={"admin_email": "test@example.test"})
    headers, missing = hmrc.fraud_headers(req, hmrc.BrowserContext(**CONTEXT), "test")
    assert "Gov-Client-Public-IP" not in headers
    assert "Gov-Client-Public-IP" in missing
    assert "Gov-Client-Multi-Factor" not in headers


def test_transport_has_fixed_sandbox_host_and_never_follows_redirects(monkeypatch):
    real_client = httpx.AsyncClient
    seen = []
    def handler(req):
        seen.append(req)
        return httpx.Response(302, headers={"location": "https://api.service.hmrc.gov.uk/"})
    monkeypatch.setattr(hmrc.httpx, "AsyncClient", lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))
    response = asyncio.run(hmrc.transport("GET", "/test/fraud-prevention-headers/validate"))
    assert response.status_code == 302
    assert len(seen) == 1 and seen[0].url.host == "test-api.service.hmrc.gov.uk"
    with pytest.raises(ValueError): asyncio.run(hmrc.transport("GET", "https://api.service.hmrc.gov.uk"))
    with pytest.raises(ValueError): asyncio.run(hmrc.transport("GET", "//api.service.hmrc.gov.uk"))


def test_test_user_change_invalidates_connection_and_prepared_review(workspace, monkeypatch):
    review = workspace.client.post("/api/hmrc/sandbox/review", json=draft_body()).json()
    monkeypatch.setenv("HMRC_SANDBOX_NINO", "AA999999A")
    assert workspace.client.get("/api/hmrc/status").json()["connected"] is False
    assert workspace.client.post("/api/hmrc/sandbox/submit", json={"review_id": review["id"], "confirmation": "SEND SAMPLE TO SANDBOX", "context": CONTEXT}).status_code == 409


def test_expired_token_is_refreshed_and_only_encrypted_values_are_stored(workspace, monkeypatch):
    workspace.db.hmrc_connections.rows[0]["encrypted_tokens"] = workspace.config.encrypt({"access_token": "old-access", "refresh_token": "old-refresh", "expires_at": 0})
    call = AsyncMock(side_effect=[httpx.Response(200, json={"access_token": "refreshed-access", "refresh_token": "refreshed-refresh", "expires_in": 3600}), httpx.Response(200, json={"listOfBusinesses": []})])
    monkeypatch.setattr(hmrc, "transport", call)
    response = workspace.client.post("/api/hmrc/sandbox/businesses", json={"tax_year": "2026-27", "context": CONTEXT})
    assert response.status_code == 200
    assert call.call_args.kwargs["headers"]["Authorization"] == "Bearer refreshed-access"
    row = workspace.db.hmrc_connections.rows[0]
    assert "refreshed-access" not in str(row)
    assert workspace.config.decrypt(row["encrypted_tokens"])["refresh_token"] == "refreshed-refresh"


def test_two_simultaneous_submissions_make_one_remote_request(workspace, monkeypatch):
    review = workspace.client.post("/api/hmrc/sandbox/review", json=draft_body()).json()
    calls = []
    async def remote(*args, **kwargs):
        calls.append(args)
        await asyncio.sleep(0.02)
        return httpx.Response(204)
    monkeypatch.setattr(hmrc, "transport", remote)
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=workspace.client.app), base_url="http://testserver", cookies=workspace.client.cookies, headers={"x-csrf-token": "offline-csrf"}) as client:
            body = {"review_id": review["id"], "confirmation": "SEND SAMPLE TO SANDBOX", "context": CONTEXT}
            return await asyncio.gather(client.post("/api/hmrc/sandbox/submit", json=body), client.post("/api/hmrc/sandbox/submit", json=body))
    responses = asyncio.run(run())
    assert sorted(r.status_code for r in responses) == [200, 409]
    assert len(calls) == 1


def test_disconnect_removes_pending_states_and_local_tokens(workspace, monkeypatch):
    url = workspace.client.post("/api/hmrc/connect").json()["url"]
    state = parse_qs(urlparse(url).query)["state"][0]
    assert workspace.client.delete("/api/hmrc/connection").status_code == 200
    assert not workspace.db.hmrc_connections.rows and not workspace.db.hmrc_oauth_states.rows
    assert workspace.client.get("/api/hmrc/callback", params={"state": state, "code": "old-code"}).status_code == 400


def test_foreign_or_local_accounts_review_can_never_be_submitted(workspace, monkeypatch):
    review = workspace.client.post("/api/hmrc/sandbox/review", json=draft_body()).json()
    workspace.db.hmrc_submissions.rows[-1]["source"] = "local_accounts"
    call = AsyncMock(); monkeypatch.setattr(hmrc, "transport", call)
    response = workspace.client.post("/api/hmrc/sandbox/submit", json={"review_id": review["id"], "context": CONTEXT, "confirmation": "SEND SAMPLE TO SANDBOX"})
    assert response.status_code == 404
    call.assert_not_awaited()
