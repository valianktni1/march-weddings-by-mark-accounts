"""HMRC MTD sandbox workbench. There is deliberately no production transport.

Only server-generated fictional figures can reach HMRC. Local account figures
are preview-only. OAuth tokens and PKCE verifiers are encrypted server-side.
Official API specifications reviewed 2026-10-29; see docs/HMRC-SANDBOX.md.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import ipaddress
import json
import os
import re
import secrets
import time
import uuid
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Literal
from urllib.parse import quote, urlencode

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from pymongo import ReturnDocument

SANDBOX = "https://test-api.service.hmrc.gov.uk"
SCOPES = "read:self-assessment write:self-assessment"
TOKEN_LOCK = asyncio.Lock()  # Deployment uses one Uvicorn worker.


def canonical_hash(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def period(tax_year: str, quarter: str) -> tuple[str, str]:
    if not re.fullmatch(r"20\d{2}-\d{2}", tax_year):
        raise ValueError("Choose a valid tax year")
    year = int(tax_year[:4])
    if year < 2025 or tax_year[-2:] != f"{(year + 1) % 100:02d}" or quarter not in {"Q1", "Q2", "Q3", "Q4"}:
        raise ValueError("Choose a tax year from 2025/26 and a standard quarter")
    return f"{year}-04-06", {
        "Q1": f"{year}-07-05", "Q2": f"{year}-10-05",
        "Q3": f"{year+1}-01-05", "Q4": f"{year+1}-04-05",
    }[quarter]


def money(value) -> Decimal:
    try:
        result = Decimal(str(value))
        if not result.is_finite() or abs(result) > Decimal("99999999999.99"):
            raise ValueError("Amount is outside HMRC's supported range")
        return result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError) as exc:
        raise ValueError("Amount is not valid money") from exc


def row_date(value) -> date:
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(value or "")[:10], fmt).date()
        except ValueError:
            pass
    raise ValueError("An included record has a missing or invalid date")


def local_preview(snapshot: dict, tax_year: str, quarter: str) -> dict:
    start, end = period(tax_year, quarter)
    lower, upper = date.fromisoformat(start), date.fromisoformat(end)
    problems = []

    def total(rows, included=True):
        amount = Decimal("0.00")
        for row in rows:
            if included and not row.get("included"):
                continue
            try:
                when = row_date(row.get("date"))
                value = money(row.get("amount"))
                if lower <= when <= upper:
                    amount += value
            except ValueError as exc:
                problems.append(str(exc))
        return amount

    income = total(snapshot.get("income_ledger", []))
    expenses = total(snapshot.get("expense_ledger", [])) + total(snapshot.get("mileage_ledger", []), included=False)
    return {
        "source": "local_accounts", "can_submit": False,
        "tax_year": tax_year, "quarter": quarter, "start": start, "end": end,
        "income": float(income), "expenses": float(expenses), "profit": float(income-expenses),
        "problems": sorted(set(problems)),
        "close_blockers": int(snapshot.get("validation", {}).get("blocker_count", 0)),
        "notice": "Local preview only. These figures cannot be sent by this sandbox workbench. No tax liability is calculated here.",
    }


def sample_payload(tax_year: str, quarter: str) -> dict:
    start, end = period(tax_year, quarter)
    # Entirely fictional cumulative figures. Never accept an accounts payload.
    multiple = int(quarter[1])
    return {
        "periodDates": {"periodStartDate": start, "periodEndDate": end},
        "periodIncome": {"turnover": 1000 * multiple, "other": 0},
        "periodExpenses": {"consolidatedExpenses": 100 * multiple},
    }


class BrowserContext(BaseModel):
    device_id: uuid.UUID
    user_agent: str = Field(min_length=1, max_length=1000, pattern=r"^[^\x00-\x1f\x7f]+$")
    timezone: str = Field(pattern=r"^UTC[+-]\d{2}:\d{2}$")
    screen_width: int = Field(gt=0, le=100000)
    screen_height: int = Field(gt=0, le=100000)
    colour_depth: int = Field(gt=0, le=128)
    scale: float = Field(gt=0, le=20, allow_inf_nan=False)
    window_width: int = Field(gt=0, le=100000)
    window_height: int = Field(gt=0, le=100000)


class InspectRequest(BaseModel):
    context: BrowserContext
    tax_year: str = Field(pattern=r"^20\d{2}-\d{2}$")
    scenario: Literal["DEFAULT", "STATEFUL"] = "DEFAULT"


class DraftRequest(InspectRequest):
    quarter: Literal["Q1", "Q2", "Q3", "Q4"]
    business_id: str = Field(pattern=r"^X[A-Z0-9]{14}$")


class SubmitRequest(BaseModel):
    review_id: uuid.UUID
    confirmation: str
    context: BrowserContext


class Settings:
    """No configurable URL: a production hostname is never accepted."""
    def __init__(self):
        self.enabled = os.getenv("HMRC_SANDBOX_ENABLED", "false").lower() == "true"
        self.environment = os.getenv("HMRC_ENVIRONMENT", "sandbox")
        self.client_id = os.getenv("HMRC_SANDBOX_CLIENT_ID", "")
        self.client_secret = os.getenv("HMRC_SANDBOX_CLIENT_SECRET", "")
        self.key = os.getenv("HMRC_TOKEN_ENCRYPTION_KEY", "")
        self.nino = os.getenv("HMRC_SANDBOX_NINO", "").replace(" ", "").upper()
        self.test_confirmed = os.getenv("HMRC_SANDBOX_TEST_USER_CONFIRMED", "false").lower() == "true"

    def missing(self):
        missing = []
        if self.environment != "sandbox":
            missing.append("HMRC_ENVIRONMENT must be sandbox; production is unsupported")
        for name, value in (("HMRC_SANDBOX_CLIENT_ID", self.client_id), ("HMRC_SANDBOX_CLIENT_SECRET", self.client_secret), ("HMRC_TOKEN_ENCRYPTION_KEY", self.key)):
            if not value:
                missing.append(name)
        if self.key:
            try:
                Fernet(self.key.encode())
            except (ValueError, TypeError):
                missing.append("HMRC_TOKEN_ENCRYPTION_KEY must be a valid Fernet key")
        if not re.fullmatch(r"[A-CEGHJ-PR-TW-Z]{2}\d{6}[A-D]", self.nino):
            missing.append("HMRC_SANDBOX_NINO (from a generated test user)")
        if not self.test_confirmed:
            missing.append("HMRC_SANDBOX_TEST_USER_CONFIRMED")
        return missing

    def require(self):
        if not self.enabled or self.missing():
            raise HTTPException(409, "HMRC sandbox setup is incomplete. Check the setup checklist.")

    def binding(self):
        return canonical_hash({"client_id": self.client_id, "test_nino": self.nino})

    def encrypt(self, data):
        return Fernet(self.key.encode()).encrypt(json.dumps(data).encode()).decode()

    def decrypt(self, data):
        try:
            return json.loads(Fernet(self.key.encode()).decrypt(data.encode()))
        except (InvalidToken, ValueError, TypeError, KeyError) as exc:
            raise HTTPException(409, "The test connection cannot be decrypted. Disconnect and reconnect with the configured encryption key.") from exc


async def transport(method, path, *, headers=None, data=None, json_body=None, params=None):
    # Callers supply paths, never arbitrary URLs. Redirects remain disabled.
    if not path.startswith("/") or path.startswith("//") or ":" in path:
        raise ValueError("Only fixed sandbox paths are supported")
    async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
        return await client.request(method, SANDBOX + path, headers=headers, data=data, json=json_body, params=params)


def result_json(response):
    try:
        result = response.json() if response.content else {}
        return result if isinstance(result, dict) else {}
    except ValueError:
        return {}


def remote_error(response):
    # Do not surface upstream descriptions: they may contain identifiers.
    body = result_json(response)
    raw_code = body.get("code", "HMRC_REQUEST_FAILED") if isinstance(body, dict) else "HMRC_REQUEST_FAILED"
    code = raw_code if isinstance(raw_code, str) and re.fullmatch(r"[A-Za-z0-9_]{1,100}", raw_code) else "HMRC_REQUEST_FAILED"
    return {"code": code, "status": response.status_code, "correlation_id": response.headers.get("X-CorrelationId", "")}


def fraud_headers(request: Request, context: BrowserContext, build: str) -> tuple[dict, list]:
    enc = lambda value: quote(str(value), safe="")
    headers = {
        "Gov-Client-Connection-Method": "WEB_APP_VIA_SERVER",
        "Gov-Client-Browser-JS-User-Agent": "".join(c if ord(c) < 128 else enc(c) for c in context.user_agent),
        "Gov-Client-Device-ID": str(context.device_id),
        "Gov-Client-Timezone": context.timezone,
        "Gov-Client-User-IDs": "accounts=" + enc(request.session.get("admin_email", "")),
        "Gov-Client-Screens": f"width={context.screen_width}&height={context.screen_height}&scaling-factor={context.scale}&colour-depth={context.colour_depth}",
        "Gov-Client-Window-Size": f"width={context.window_width}&height={context.window_height}",
        "Gov-Vendor-Product-Name": "Weddings%20By%20Mark",
        "Gov-Vendor-Version": f"accounts-web={enc(build)}&accounts-server={enc(build)}",
    }
    missing = ["Gov-Client-Multi-Factor", "Gov-Vendor-License-IDs"]
    # Only trust edge-supplied headers when the deployment explicitly enables
    # them. The outermost proxy must overwrite these values, never append.
    if os.getenv("HMRC_TRUST_EDGE_HEADERS", "false").lower() == "true":
        client_ip = request.headers.get("x-hmrc-client-ip", "")
        port = request.headers.get("x-hmrc-client-port", "")
    else:
        client_ip = request.client.host if request.client else ""
        port = str(request.client.port) if request.client else ""
    try:
        public_client = ipaddress.ip_address(client_ip)
        if not public_client.is_global:
            raise ValueError("Not a public client address")
        headers["Gov-Client-Public-IP"] = str(public_client)
        headers["Gov-Client-Public-IP-Timestamp"] = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        if not port.isdigit() or not 1 <= int(port) <= 65535:
            raise ValueError("Missing client port")
        headers["Gov-Client-Public-Port"] = port
    except ValueError:
        missing.extend(name for name in ("Gov-Client-Public-IP", "Gov-Client-Public-IP-Timestamp", "Gov-Client-Public-Port") if name not in headers)
    vendor = os.getenv("HMRC_VENDOR_PUBLIC_IP", "")
    try:
        if not ipaddress.ip_address(vendor).is_global:
            raise ValueError("Not public")
        headers["Gov-Vendor-Public-IP"] = vendor
        if "Gov-Client-Public-IP" in headers:
            headers["Gov-Vendor-Forwarded"] = "by=" + enc(vendor) + "&for=" + enc(headers["Gov-Client-Public-IP"])
        else:
            missing.append("Gov-Vendor-Forwarded")
    except ValueError:
        missing.extend(["Gov-Vendor-Public-IP", "Gov-Vendor-Forwarded"])
    # Omit unavailable data instead of inventing placeholder security metadata.
    return headers, sorted(set(missing))


def create_router(get_db, load_snapshot, app_url: str, build: str):
    router = APIRouter(prefix="/api/hmrc", tags=["HMRC sandbox"])
    redirect_uri = app_url.rstrip("/") + "/api/hmrc/callback"

    async def tokens(settings):
        async with TOKEN_LOCK:
            row = await get_db().hmrc_connections.find_one({"_id": "sandbox"})
            if not row:
                raise HTTPException(409, "Connect an HMRC test user first")
            if row.get("binding") != settings.binding():
                raise HTTPException(409, "The HMRC test-user settings changed. Disconnect and reconnect.")
            token = settings.decrypt(row["encrypted_tokens"])
            if float(token.get("expires_at", 0)) > time.time() + 60:
                return token["access_token"]
            try:
                response = await transport("POST", "/oauth/token", data={
                    "grant_type": "refresh_token", "client_id": settings.client_id,
                    "client_secret": settings.client_secret, "refresh_token": token["refresh_token"],
                })
            except httpx.RequestError as exc:
                raise HTTPException(502, "HMRC test connection could not be refreshed. Try again later.") from exc
            if response.status_code != 200:
                raise HTTPException(409, "HMRC test connection expired. Disconnect and reconnect.")
            await save_tokens(settings, result_json(response))
            row = await get_db().hmrc_connections.find_one({"_id": "sandbox"})
            return settings.decrypt(row["encrypted_tokens"])["access_token"]

    async def save_tokens(settings, body):
        if not body.get("access_token") or not body.get("refresh_token"):
            raise HTTPException(502, "HMRC did not return the expected test connection tokens")
        stored = {"access_token": body["access_token"], "refresh_token": body["refresh_token"], "expires_at": time.time()+int(body.get("expires_in", 14400))}
        await get_db().hmrc_connections.update_one({"_id": "sandbox"}, {"$set": {
            "encrypted_tokens": settings.encrypt(stored), "connected_at": datetime.now(timezone.utc).isoformat(),
            "binding": settings.binding(),
        }}, upsert=True)

    async def request_api(request, context, method, path, version, *, params=None, body=None, scenario="DEFAULT"):
        settings = Settings()
        settings.require()
        headers, missing = fraud_headers(request, context, build)
        headers.update(Authorization="Bearer " + await tokens(settings), Accept=f"application/vnd.hmrc.{version}+json")
        if scenario != "DEFAULT":
            headers["Gov-Test-Scenario"] = scenario
        try:
            response = await transport(method, path, headers=headers, params=params, json_body=body)
        except httpx.RequestError as exc:
            raise HTTPException(502, "The HMRC sandbox could not be reached") from exc
        if not 200 <= response.status_code < 300:
            raise HTTPException(502, remote_error(response))
        return {"data": result_json(response), "correlation_id": response.headers.get("X-CorrelationId", ""), "missing_headers": missing, "environment": "sandbox"}

    @router.get("/status")
    async def status():
        settings = Settings()
        connection = await get_db().hmrc_connections.find_one({"_id": "sandbox"}, {"binding": 1})
        connected = bool(connection and connection.get("binding") == settings.binding())
        return {"environment": "sandbox", "production_supported": False, "enabled": settings.enabled,
                "setup_missing": settings.missing(), "connected": connected, "redirect_uri": redirect_uri,
                "notice": "Testing only. Real filing and annual tax returns are unavailable. Only fictional sample figures can be sent."}

    @router.post("/connect")
    async def connect(request: Request):
        settings = Settings()
        settings.require()
        state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        await get_db().hmrc_oauth_states.insert_one({
            "_id": hashlib.sha256(state.encode()).hexdigest(), "verifier": settings.encrypt(verifier),
            "expires_at": time.time()+600,
            "cleanup_at": datetime.now(timezone.utc) + timedelta(minutes=10),
            "binding": settings.binding(),
        })
        return {"url": SANDBOX + "/oauth/authorize?" + urlencode({
            "response_type": "code", "client_id": settings.client_id, "scope": SCOPES,
            "redirect_uri": redirect_uri, "state": state, "code_challenge": challenge, "code_challenge_method": "S256",
        })}

    @router.get("/callback")
    async def callback(state: str = "", code: str = "", error: str = ""):
        settings = Settings()
        settings.require()
        if not state or len(state) > 200:
            raise HTTPException(400, "The HMRC connection request is invalid or expired")
        async with TOKEN_LOCK:
            pending = await get_db().hmrc_oauth_states.find_one_and_delete({"_id": hashlib.sha256(state.encode()).hexdigest(), "expires_at": {"$gt": time.time()}})
            if not pending or pending.get("binding") != settings.binding():
                raise HTTPException(400, "The HMRC connection request is invalid or expired")
            if error or not code:
                return RedirectResponse("/hmrc?connection=cancelled", status_code=303)
            try:
                response = await transport("POST", "/oauth/token", data={
                    "grant_type": "authorization_code", "client_id": settings.client_id, "client_secret": settings.client_secret,
                    "redirect_uri": redirect_uri, "code": code, "code_verifier": settings.decrypt(pending["verifier"]),
                })
                if response.status_code != 200:
                    return RedirectResponse("/hmrc?connection=failed", status_code=303)
                await save_tokens(settings, result_json(response))
            except httpx.RequestError:
                return RedirectResponse("/hmrc?connection=failed", status_code=303)
        return RedirectResponse("/hmrc?connection=success", status_code=303)

    @router.delete("/connection")
    async def disconnect():
        async with TOKEN_LOCK:
            await get_db().hmrc_connections.delete_one({"_id": "sandbox"})
            await get_db().hmrc_oauth_states.delete_many({})
        return {"disconnected": True, "notice": "Local test tokens removed. You can also revoke authority in your HMRC test account."}

    @router.get("/preview/{tax_year}/{quarter}")
    async def preview(tax_year: str, quarter: str):
        try:
            period(tax_year, quarter)
            return local_preview(await load_snapshot(tax_year), tax_year, quarter)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @router.post("/sandbox/businesses")
    async def businesses(payload: InspectRequest, request: Request):
        settings = Settings()
        settings.require()
        return await request_api(request, payload.context, "GET", f"/individuals/business/details/{settings.nino}/list", "2.0", scenario=payload.scenario)

    @router.post("/sandbox/obligations")
    async def obligations(payload: InspectRequest, request: Request):
        settings = Settings()
        settings.require()
        try:
            start, end = period(payload.tax_year, "Q4")
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return await request_api(request, payload.context, "GET", f"/obligations/details/{settings.nino}/income-and-expenditure", "3.0", params={"fromDate": start, "toDate": end, "typeOfBusiness": "self-employment"}, scenario="CUMULATIVE")

    @router.post("/sandbox/check-headers")
    async def check_headers(payload: InspectRequest, request: Request):
        settings = Settings()
        settings.require()
        headers, missing = fraud_headers(request, payload.context, build)
        try:
            app_token = await transport("POST", "/oauth/token", data={"grant_type": "client_credentials", "client_id": settings.client_id, "client_secret": settings.client_secret})
            if app_token.status_code != 200:
                raise HTTPException(502, remote_error(app_token))
            token = result_json(app_token).get("access_token")
            if not token:
                raise HTTPException(502, "HMRC did not return an application test token")
            headers.update(Authorization="Bearer " + token, Accept="application/vnd.hmrc.1.0+json")
            response = await transport("GET", "/test/fraud-prevention-headers/validate", headers=headers)
        except httpx.RequestError as exc:
            raise HTTPException(502, "The HMRC header test could not be reached") from exc
        if response.status_code != 200:
            raise HTTPException(502, remote_error(response))
        # A 200 response is not proof of valid headers: inspect its code.
        data = result_json(response)
        return {"data": data, "missing_headers": missing, "valid": data.get("code") == "VALID_HEADERS", "environment": "sandbox"}

    @router.post("/sandbox/review")
    async def review(payload: DraftRequest):
        settings = Settings()
        settings.require()
        try:
            body = sample_payload(payload.tax_year, payload.quarter)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        draft = {"id": str(uuid.uuid4()), "status": "review", "source": "fictional_sample", "environment": "sandbox",
                 "tax_year": payload.tax_year, "quarter": payload.quarter, "business_id": payload.business_id,
                 "scenario": payload.scenario, "payload": body, "payload_hash": canonical_hash(body),
                 "binding": settings.binding(),
                 "created_at": datetime.now(timezone.utc).isoformat(), "expires_at": time.time()+900}
        await get_db().hmrc_submissions.insert_one(dict(draft))
        return {**draft, "confirmation": "SEND SAMPLE TO SANDBOX"}

    @router.post("/sandbox/submit")
    async def submit(payload: SubmitRequest, request: Request):
        settings = Settings()
        settings.require()
        if payload.confirmation != "SEND SAMPLE TO SANDBOX":
            raise HTTPException(422, 'Type "SEND SAMPLE TO SANDBOX" to send the fictional test figures')
        draft = await get_db().hmrc_submissions.find_one({"id": str(payload.review_id)}, {"_id": 0})
        if not draft or draft.get("source") != "fictional_sample" or draft.get("environment") != "sandbox":
            raise HTTPException(404, "Sample review not found")
        if draft.get("binding") != settings.binding():
            raise HTTPException(409, "The test-user settings changed. Prepare a new sample review.")
        expected = sample_payload(draft["tax_year"], draft["quarter"])
        if draft["payload"] != expected or draft["payload_hash"] != canonical_hash(expected):
            raise HTTPException(409, "The sample review has changed. Prepare a new review.")
        if draft["status"] == "accepted":
            return {"status": "accepted", "already_processed": True, "environment": "sandbox"}
        # Get the connection before claiming the review. Setup failures must not
        # consume a review or trigger a blind retry of a submitted request.
        headers, missing = fraud_headers(request, payload.context, build)
        headers.update(Authorization="Bearer " + await tokens(settings), Accept="application/vnd.hmrc.5.0+json")
        if draft["scenario"] != "DEFAULT":
            headers["Gov-Test-Scenario"] = draft["scenario"]
        claimed = await get_db().hmrc_submissions.find_one_and_update(
            {"id": draft["id"], "status": "review", "expires_at": {"$gt": time.time()}},
            {"$set": {"status": "sending"}}, return_document=ReturnDocument.AFTER,
        )
        if not claimed:
            raise HTTPException(409, "This review has expired or has already been sent. Check history before preparing another.")
        path = f'/individuals/business/self-employment/{settings.nino}/{draft["business_id"]}/cumulative/{draft["tax_year"]}'
        try:
            response = await transport("PUT", path, headers=headers, json_body=expected)
            accepted = response.status_code == 204
            state = "accepted" if accepted else ("rejected" if 400 <= response.status_code < 500 else "unknown")
            details = {"status": state, "http_status": response.status_code, "correlation_id": response.headers.get("X-CorrelationId", ""), "missing_headers": missing}
            if not accepted:
                details["error"] = remote_error(response)
        except httpx.RequestError:
            details = {"status": "unknown", "missing_headers": missing, "error": {"code": "NETWORK_OUTCOME_UNKNOWN"}}
        details["completed_at"] = datetime.now(timezone.utc).isoformat()
        await get_db().hmrc_submissions.update_one({"id": draft["id"]}, {"$set": details})
        return {**details, "environment": "sandbox", "scenario": draft["scenario"],
                "notice": "HMRC test environment only. DEFAULT responses are simulated and do not prove persistence. No real tax obligation is fulfilled."}

    @router.post("/sandbox/retrieve")
    async def retrieve(payload: DraftRequest, request: Request):
        settings = Settings()
        settings.require()
        try:
            period(payload.tax_year, payload.quarter)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        path = f"/individuals/business/self-employment/{settings.nino}/{payload.business_id}/cumulative/{payload.tax_year}"
        return await request_api(request, payload.context, "GET", path, "5.0", scenario=payload.scenario)

    @router.get("/history")
    async def history():
        return await get_db().hmrc_submissions.find({}, {"_id": 0, "expires_at": 0, "binding": 0}).sort("created_at", -1).to_list(50)

    return router
