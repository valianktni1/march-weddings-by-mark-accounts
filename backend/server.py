from fastapi import FastAPI, APIRouter, UploadFile, File, HTTPException, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError
import os
import logging
import shutil
import zipfile
import json
import asyncio
import mimetypes
import re
import secrets
import time
import hashlib
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import Any, Dict, List, Optional
import uuid
from datetime import datetime, timezone, timedelta
from bson import ObjectId
from tax_year_close import (
    build_evidence_pack,
    build_tax_snapshot,
    snapshot_digest,
    tax_year_bounds,
)

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Runtime configuration. Secrets are supplied by Docker/TrueNAS and are never
# committed to the repository.
APP_ENV = os.environ.get("APP_ENV", "development").lower()
APP_URL = os.environ.get("APP_URL", "http://localhost:3000").rstrip("/")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "mark@perfectweddingsbymark.uk").strip().lower()
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
SESSION_SECRET = os.environ.get("SESSION_SECRET", "")
SESSION_HOURS = max(1, int(os.environ.get("SESSION_HOURS", "12")))
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "true").lower() == "true"
INTEGRATION_ENABLED = os.environ.get("BOOKING_INTEGRATION_ENABLED", "false").lower() == "true"
INTEGRATION_KEY = os.environ.get("BOOKING_INTEGRATION_KEY", "")
MAX_RESTORE_MB = max(1, int(os.environ.get("MAX_RESTORE_MB", "250")))
MAX_UPLOAD_MB = max(1, int(os.environ.get("MAX_UPLOAD_MB", "50")))
BUILD_ID = "2026.08.19-accounts-renumbered-pdf-import-v1.4.7"
INVOICE_PDF_FORMAT_VERSION = 2

# Create the main app. Documentation is disabled in production so financial
# API routes are not advertised publicly.
app = FastAPI(
    title="Weddings by Mark Accounts",
    docs_url=None if APP_ENV == "production" else "/docs",
    redoc_url=None if APP_ENV == "production" else "/redoc",
    openapi_url=None if APP_ENV == "production" else "/openapi.json",
)

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

FAILED_LOGINS: Dict[str, List[float]] = {}
LOGIN_WINDOW_SECONDS = 15 * 60
MAX_LOGIN_ATTEMPTS = 5

# All user-owned files live beneath one configurable storage root. TrueNAS
# mounts the Nextcloud dataset at /app/storage; local development continues to
# use the backend directory unless STORAGE_ROOT is explicitly supplied.
STORAGE_ROOT = Path(os.environ.get("STORAGE_ROOT", str(ROOT_DIR))).resolve()
UPLOAD_DIR = STORAGE_ROOT / "uploads"
BACKUP_DIR = STORAGE_ROOT / "backups"
RESTORE_DIR = STORAGE_ROOT / "temp_restore"
TAX_PACK_DIR = STORAGE_ROOT / "tax_year_packs"
for storage_dir in (UPLOAD_DIR, BACKUP_DIR, RESTORE_DIR, TAX_PACK_DIR):
    storage_dir.mkdir(parents=True, exist_ok=True)

# Owner withdrawal patterns to exclude from expenses
OWNER_WITHDRAWAL_PATTERNS = ["HMRC", "MARK POWELL", "MARK ADAM POWELL"]

# UK Tax Years
UK_TAX_YEARS = [
    {"id": "2023-24", "label": "2023/24", "start": "2023-04-06", "end": "2024-04-05"},
    {"id": "2024-25", "label": "2024/25", "start": "2024-04-06", "end": "2025-04-05"},
    {"id": "2025-26", "label": "2025/26", "start": "2025-04-06", "end": "2026-04-05"},
    {"id": "2026-27", "label": "2026/27", "start": "2026-04-06", "end": "2027-04-05"},
    {"id": "2027-28", "label": "2027/28", "start": "2027-04-06", "end": "2028-04-05"},
    {"id": "2028-29", "label": "2028/29", "start": "2028-04-06", "end": "2029-04-05"},
    {"id": "2029-30", "label": "2029/30", "start": "2029-04-06", "end": "2030-04-05"},
]

# UK Expense Categories
UK_EXPENSE_CATEGORIES = [
    "Travel & Mileage",
    "Equipment & Gear",
    "Software & Subscriptions",
    "Professional Services",
    "Marketing & Advertising",
    "Office & Supplies",
    "Insurance",
    "Training & Development",
    "Venue & Location Fees",
    "Utilities",
    "Bank Fees",
    "Other"
]


# Models
class Invoice(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    invoice_number: Optional[str] = None
    issue_date: Optional[str] = None
    couple_names: str = ""
    client_address: Optional[str] = None
    client_email: Optional[str] = None
    client_phone: Optional[str] = None
    wedding_date: Optional[str] = None
    venue: Optional[str] = None
    total_price: float = 0
    deposit_amount: float = 0
    deposit_paid_date: Optional[str] = None
    deposit_tax_year: Optional[str] = None
    interim_payment: float = 0
    interim_payment_date: Optional[str] = None
    interim_tax_year: Optional[str] = None
    final_payment_due: Optional[str] = None
    final_payment_paid_date: Optional[str] = None
    final_tax_year: Optional[str] = None
    balance_remaining: float = 0
    status: str = "Deposit Paid"
    tax_year: str = ""
    package_name: Optional[str] = None
    notes: Optional[str] = None
    line_items: List[Dict[str, Any]] = Field(default_factory=list)
    file_path: Optional[str] = None
    file_name: Optional[str] = None
    include_in_totals: bool = False
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class InvoiceCreate(BaseModel):
    invoice_number: Optional[str] = None
    issue_date: Optional[str] = None
    couple_names: str
    client_address: Optional[str] = None
    client_email: Optional[str] = None
    client_phone: Optional[str] = None
    wedding_date: str
    venue: Optional[str] = None
    total_price: float
    deposit_amount: float = 0
    deposit_paid_date: Optional[str] = None
    interim_payment: float = 0
    interim_payment_date: Optional[str] = None
    final_payment_paid_date: Optional[str] = None
    final_payment_due: Optional[str] = None
    package_name: Optional[str] = None
    notes: Optional[str] = None
    line_items: List[Dict[str, Any]] = Field(default_factory=list)
    include_in_totals: bool = False


class Expense(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    description: str
    amount: float
    category: str
    date: str  # DD/MM/YYYY format
    tax_year: str
    supplier: Optional[str] = None
    file_path: Optional[str] = None
    file_name: Optional[str] = None
    is_from_bank: bool = False
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ExpenseCreate(BaseModel):
    description: str
    amount: float
    category: str
    date: str
    tax_year: str
    supplier: Optional[str] = None
    include_amount: bool = True


class ExpenseUpdate(BaseModel):
    description: str = Field(min_length=1, max_length=500)
    category: str = Field(min_length=1, max_length=160)
    supplier: Optional[str] = Field(default=None, max_length=200)
    include_in_totals: Optional[bool] = None


class Transaction(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    date: str  # DD/MM/YYYY format
    description: str
    amount: float
    transaction_type: str  # income, expense, owner_withdrawal, tax_payment
    category: Optional[str] = None
    tax_year: str
    source: str = "bank_statement"
    bank_statement_id: Optional[str] = None
    excluded_from_totals: bool = False
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class BankStatement(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    file_name: str
    file_path: str
    upload_date: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    processed: bool = False
    transaction_count: int = 0
    parse_status: str = "pending"  # pending, processing, success, error
    parse_error: Optional[str] = None


class MileageEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    date: str  # DD/MM/YYYY
    description: str
    from_location: str
    to_location: str
    miles: float
    rate: float = 0.45  # HMRC rate
    amount: float = 0  # auto-calculated
    tax_year: str
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class RecurringExpenseTemplate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    description: str
    amount: float
    category: str
    supplier: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class LoginRequest(BaseModel):
    email: str
    password: str


class BookingPaymentSync(BaseModel):
    id: str
    amount: float
    paid_date: str
    payment_type: Optional[str] = None
    reference: Optional[str] = Field(default=None, max_length=200)
    notes: Optional[str] = Field(default=None, max_length=2000)


class BookingInvoiceSync(BaseModel):
    """Stable, versioned contract used by the booking system only."""

    event_id: str = Field(min_length=8, max_length=160)
    source_invoice_id: str = Field(min_length=1, max_length=160)
    source_booking_id: str = Field(min_length=1, max_length=160)
    invoice_number: str = Field(min_length=1, max_length=40)
    legacy_invoice_number: Optional[str] = Field(default=None, max_length=80)
    issue_date: Optional[str] = None
    brand: str = Field(default="wbm", max_length=20)
    record_kind: str = Field(default="wedding", max_length=40)
    is_test: bool = False
    is_legacy_import: bool = False
    scope_reason: str = Field(default="wedding_date", max_length=80)
    couple_names: str = Field(default="", max_length=300)
    client_address: Optional[str] = Field(default=None, max_length=1000)
    client_email: Optional[str] = Field(default=None, max_length=320)
    client_phone: Optional[str] = Field(default=None, max_length=80)
    wedding_date: Optional[str] = None
    venue: Optional[str] = Field(default=None, max_length=500)
    package_name: Optional[str] = Field(default=None, max_length=500)
    description: Optional[str] = Field(default=None, max_length=10000)
    line_items: List[Dict[str, Any]] = Field(default_factory=list)
    total_price: float = 0
    due_date: Optional[str] = None
    status: str = Field(default="Pending", max_length=80)
    payments: List[BookingPaymentSync] = Field(default_factory=list)
    void_reason: Optional[str] = Field(default=None, max_length=2000)
    cancellation_date: Optional[str] = None
    cancellation_reason: Optional[str] = Field(default=None, max_length=2000)
    updated_at: Optional[str] = None


class BookingInvoiceBatchSync(BaseModel):
    invoices: List[BookingInvoiceSync] = Field(min_length=1, max_length=500)


class TaxYearCloseRequest(BaseModel):
    confirmation: str = Field(min_length=1, max_length=80)
    reason: str = Field(min_length=5, max_length=2000)
    acknowledge_warnings: bool = False


class TaxYearReopenRequest(BaseModel):
    confirmation: str = Field(min_length=1, max_length=80)
    reason: str = Field(min_length=5, max_length=2000)


class CashPaymentAction(BaseModel):
    source_invoice_id: str = Field(min_length=1, max_length=160)
    source_payment_id: str = Field(min_length=1, max_length=160)
    confirmation: str = Field(min_length=1, max_length=40)
    reason: str = Field(min_length=5, max_length=1000)


class CombinedBankPaymentRef(BaseModel):
    source_invoice_id: str = Field(min_length=1, max_length=160)
    source_payment_id: str = Field(min_length=1, max_length=160)


class CombinedBankMatchCreate(BaseModel):
    bank_transaction_id: str = Field(min_length=1, max_length=160)
    payments: List[CombinedBankPaymentRef] = Field(min_length=2, max_length=20)
    confirmation: str = Field(min_length=1, max_length=40)
    reason: str = Field(min_length=5, max_length=1000)


class CombinedBankMatchRemove(BaseModel):
    match_id: str = Field(min_length=1, max_length=160)
    confirmation: str = Field(min_length=1, max_length=40)
    reason: str = Field(min_length=5, max_length=1000)


class TransactionUpdate(BaseModel):
    transaction_type: str = Field(pattern="^(income|expense|owner_withdrawal|tax_payment)$")
    category: Optional[str] = Field(default=None, max_length=160)
    excluded_from_totals: bool = False


def _expense_date_key(value: Optional[str]) -> datetime:
    try:
        return datetime.strptime(str(value or ""), "%d/%m/%Y")
    except (TypeError, ValueError):
        return datetime.min


def build_expense_ledger_rows(
    transactions: List[Dict[str, Any]],
    expenses: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Combine bank and manual expenses without duplicating bank-linked receipts."""
    linked_receipts = {
        str(expense.get("source_transaction_id")): expense
        for expense in expenses
        if expense.get("source_transaction_id")
    }
    rows: List[Dict[str, Any]] = []

    for transaction in transactions:
        if transaction.get("transaction_type") != "expense":
            continue
        transaction_id = str(transaction.get("id") or "")
        receipt = linked_receipts.get(transaction_id)
        rows.append(
            {
                "id": transaction_id,
                "record_id": transaction_id,
                "source": "bank",
                "source_label": "Bank statement",
                "date": transaction.get("date") or "",
                "description": transaction.get("description") or "",
                "supplier": (receipt or {}).get("supplier") or "",
                "category": transaction.get("category"),
                "tax_year": transaction.get("tax_year") or "",
                "amount": float(transaction.get("amount") or 0),
                "included_in_totals": not bool(transaction.get("excluded_from_totals")),
                "excluded_from_totals": bool(transaction.get("excluded_from_totals")),
                "has_receipt": bool(receipt and receipt.get("file_path")),
                "receipt_expense_id": (receipt or {}).get("id"),
                "created_at": transaction.get("created_at"),
            }
        )

    for expense in expenses:
        # A bank-linked expense is supporting receipt metadata for the original
        # bank transaction. It must never appear as a second expense row.
        if expense.get("source_transaction_id") or expense.get("is_from_bank"):
            continue
        amount = float(expense.get("amount") or 0)
        included_in_totals = expense.get("include_in_totals") is not False and amount != 0
        expense_id = str(expense.get("id") or "")
        rows.append(
            {
                "id": expense_id,
                "record_id": expense_id,
                "source": "manual",
                "source_label": "Manual expense",
                "date": expense.get("date") or "",
                "description": expense.get("description") or "",
                "supplier": expense.get("supplier") or "",
                "category": expense.get("category"),
                "tax_year": expense.get("tax_year") or "",
                "amount": amount,
                "included_in_totals": included_in_totals,
                "excluded_from_totals": not included_in_totals,
                "has_receipt": bool(expense.get("file_path")),
                "receipt_expense_id": expense_id if expense.get("file_path") else None,
                "created_at": expense.get("created_at"),
            }
        )

    return sorted(
        rows,
        key=lambda row: (_expense_date_key(row.get("date")), row.get("created_at") or ""),
        reverse=True,
    )


# Helper functions
def get_tax_year_from_date(date_str: str) -> str:
    """Determine UK tax year from date (DD/MM/YYYY format)"""
    try:
        day, month, year = map(int, date_str.split('/'))
        date_obj = datetime(year, month, day)
        
        # UK tax year runs from 6th April to 5th April
        if month < 4 or (month == 4 and day < 6):
            tax_year_start = year - 1
        else:
            tax_year_start = year
        
        return f"{tax_year_start}-{str(tax_year_start + 1)[-2:]}"
    except Exception:
        return "2025-26"


def is_owner_withdrawal(description: str) -> bool:
    """Check if transaction is an owner withdrawal or HMRC payment"""
    desc_upper = description.upper()
    for pattern in OWNER_WITHDRAWAL_PATTERNS:
        if pattern in desc_upper:
            return True
    return False


def format_date_uk(date_str: str) -> str:
    """Ensure date is in DD/MM/YYYY format"""
    try:
        # Try parsing various formats
        for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y"]:
            try:
                dt = datetime.strptime(date_str, fmt)
                return dt.strftime("%d/%m/%Y")
            except ValueError:
                continue
        return date_str
    except Exception:
        return date_str


CLOSED_INVOICE_STATUSES = {
    "paid",
    "paid in full",
    "cancelled",
    "canceled",
    "void",
    "refunded",
}


def _normalised_invoice_status(invoice: dict) -> str:
    return str(invoice.get("status") or "").strip().lower().replace("_", " ")


def _invoice_outstanding_balance(invoice: dict) -> float:
    """Return the authoritative outstanding amount used by dashboard alerts.

    Booking-linked invoices already contain a calculated balance that accounts
    for every payment, refund, cancellation and write-off. Older manually
    entered invoices retain the original fallback calculation.
    """
    if _normalised_invoice_status(invoice) in CLOSED_INVOICE_STATUSES:
        return 0.0
    if invoice.get("balance_remaining") is not None:
        return round(max(0.0, float(invoice.get("balance_remaining") or 0)), 2)
    total = float(invoice.get("total_price", 0) or invoice.get("amount", 0) or 0)
    deposit = float(invoice.get("deposit_amount", 0) or 0)
    interim = float(invoice.get("interim_payment", 0) or 0)
    return round(max(0.0, total - deposit - interim), 2)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    return forwarded or (request.client.host if request.client else "unknown")


def _password_matches(candidate: str) -> bool:
    password_hash = os.environ.get("ADMIN_PASSWORD_HASH", "")
    if password_hash:
        try:
            import bcrypt
            return bcrypt.checkpw(candidate.encode("utf-8"), password_hash.encode("utf-8"))
        except Exception:
            logger.exception("ADMIN_PASSWORD_HASH could not be checked")
            return False
    return bool(ADMIN_PASSWORD) and secrets.compare_digest(candidate, ADMIN_PASSWORD)


def _integration_authorised(request: Request) -> bool:
    provided = request.headers.get("x-accounts-integration-key", "")
    return (
        INTEGRATION_ENABLED
        and bool(INTEGRATION_KEY)
        and secrets.compare_digest(provided, INTEGRATION_KEY)
    )


async def _read_upload(file: UploadFile, allowed_extensions: set[str], limit_mb: int = MAX_UPLOAD_MB) -> tuple[bytes, str, str]:
    original_name = Path(file.filename or "upload").name
    extension = Path(original_name).suffix.lower()
    if extension not in allowed_extensions:
        allowed = ", ".join(sorted(allowed_extensions))
        raise HTTPException(status_code=400, detail=f"Unsupported file type. Allowed: {allowed}")
    content = await file.read(limit_mb * 1024 * 1024 + 1)
    if len(content) > limit_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"File exceeds {limit_mb} MB")
    return content, extension, original_name


def _delete_managed_upload(file_path: Optional[str]) -> bool:
    """Delete an uploaded file only when it is inside the managed upload root."""
    if not file_path:
        return False
    upload_root = UPLOAD_DIR.resolve()
    target = Path(file_path).resolve()
    try:
        target.relative_to(upload_root)
    except ValueError:
        logger.warning("Refused to delete a file outside the managed upload directory: %s", target)
        return False
    if target.is_file():
        target.unlink()
        return True
    return False


INVOICE_OVERRIDE_INTERNAL_FIELDS = {
    "_id",
    "accounts_override",
    "booking_source_snapshot",
    "file_path",
    "file_name",
    "last_booking_sync_at",
    "updated_at",
}


def _invoice_source_snapshot(invoice: dict) -> dict:
    """Return the booking-controlled values that can safely be restored later."""
    return {
        key: value
        for key, value in invoice.items()
        if key not in INVOICE_OVERRIDE_INTERNAL_FIELDS
    }


def _override_reason(body: dict) -> str:
    reason = str(body.get("reason") or "").strip()
    if len(reason) < 5:
        raise HTTPException(status_code=422, detail="Please enter a clear reason (at least 5 characters)")
    if len(reason) > 2000:
        raise HTTPException(status_code=422, detail="Reason must be 2,000 characters or fewer")
    return reason


def _admin_from_request(request: Request) -> str:
    return str(request.session.get("admin_email") or ADMIN_EMAIL).strip().lower()


async def _record_invoice_audit(
    *, invoice_id: str, invoice_number: str, action: str, reason: str,
    admin_email: str, before: dict, after: dict,
) -> None:
    await db.invoice_audit_logs.insert_one({
        "id": str(uuid.uuid4()),
        "invoice_id": invoice_id,
        "invoice_number": invoice_number,
        "action": action,
        "reason": reason,
        "admin_email": admin_email,
        "before": _invoice_source_snapshot(before),
        "after": _invoice_source_snapshot(after),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })


def _is_cancelled_wedding_invoice(invoice: dict) -> bool:
    status_text = str(invoice.get("status") or "").strip().lower()
    cancellation_evidence = " ".join(str(invoice.get(key) or "") for key in (
        "cancellation_reason", "void_reason", "notes",
    )).lower()
    return (
        status_text == "cancelled"
        or bool(invoice.get("cancellation_date") or invoice.get("cancellation_reason"))
        or "wedding cancelled" in cancellation_evidence
        or "wedding canceled" in cancellation_evidence
        or "job was cancelled" in cancellation_evidence
        or "job was canceled" in cancellation_evidence
        or "source job was cancelled" in cancellation_evidence
        or "source job was canceled" in cancellation_evidence
    )


def _regenerate_invoice_pdf(invoice: dict) -> dict:
    inv_num = str(invoice.get("invoice_number") or "invoice")
    safe_number = re.sub(r"[^A-Za-z0-9_.-]", "_", inv_num)
    pdf_dir = UPLOAD_DIR / "invoices"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = pdf_dir / f"{safe_number}.pdf"
    generate_invoice_pdf(invoice, str(pdf_path))
    invoice["file_path"] = str(pdf_path)
    invoice["file_name"] = f"{safe_number}.pdf"
    invoice["pdf_format_version"] = INVOICE_PDF_FORMAT_VERSION
    return invoice


async def _ensure_invoice_pdf_current(invoice: dict) -> dict:
    if int(invoice.get("pdf_format_version") or 0) >= INVOICE_PDF_FORMAT_VERSION:
        return invoice
    _regenerate_invoice_pdf(invoice)
    await db.invoices.update_one({"id": invoice.get("id")}, {"$set": {
        "file_path": invoice.get("file_path"),
        "file_name": invoice.get("file_name"),
        "pdf_format_version": INVOICE_PDF_FORMAT_VERSION,
    }})
    return invoice


@app.middleware("http")
async def protect_application(request: Request, call_next):
    """Require an admin session for all financial API routes.

    Booking integration routes use a separate server-to-server key and never
    inherit the browser administrator session.
    """

    path = request.url.path
    public_api = {"/api/health", "/api/auth/login", "/api/auth/me"}

    if path.startswith("/api/integrations/booking/"):
        if not _integration_authorised(request):
            return JSONResponse({"detail": "Integration is disabled or unauthorised"}, status_code=401)
    elif path.startswith("/api/") and path not in public_api:
        if not request.session.get("admin_email"):
            return JSONResponse({"detail": "Authentication required"}, status_code=401)

        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            supplied = request.headers.get("x-csrf-token", "")
            expected = request.session.get("csrf_token", "")
            if not supplied or not expected or not secrets.compare_digest(supplied, expected):
                return JSONResponse({"detail": "Invalid security token"}, status_code=403)

    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive, nosnippet"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline' "
        "https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; "
        "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'"
    )
    return response


# API Routes
@api_router.get("/health")
async def health():
    await db.command("ping")
    return {
        "status": "ok",
        "build": BUILD_ID,
        "authentication": True,
        "booking_integration_enabled": INTEGRATION_ENABLED,
    }


@api_router.post("/auth/login")
async def login(credentials: LoginRequest, request: Request):
    ip = _client_ip(request)
    now = time.time()
    attempts = [stamp for stamp in FAILED_LOGINS.get(ip, []) if now - stamp < LOGIN_WINDOW_SECONDS]
    FAILED_LOGINS[ip] = attempts

    if len(attempts) >= MAX_LOGIN_ATTEMPTS:
        raise HTTPException(status_code=429, detail="Too many attempts. Please wait 15 minutes.")

    email_ok = secrets.compare_digest(credentials.email.strip().lower(), ADMIN_EMAIL)
    if not email_ok or not _password_matches(credentials.password):
        attempts.append(now)
        FAILED_LOGINS[ip] = attempts
        await asyncio.sleep(0.35)
        raise HTTPException(status_code=401, detail="Email address or password is incorrect")

    FAILED_LOGINS.pop(ip, None)
    request.session.clear()
    request.session["admin_email"] = ADMIN_EMAIL
    request.session["csrf_token"] = secrets.token_urlsafe(32)
    request.session["signed_in_at"] = datetime.now(timezone.utc).isoformat()
    return {
        "email": ADMIN_EMAIL,
        "csrf_token": request.session["csrf_token"],
        "expires_in_hours": SESSION_HOURS,
    }


@api_router.get("/auth/me")
async def auth_me(request: Request):
    if not request.session.get("admin_email"):
        raise HTTPException(status_code=401, detail="Authentication required")
    return {
        "email": request.session["admin_email"],
        "csrf_token": request.session.get("csrf_token"),
        "signed_in_at": request.session.get("signed_in_at"),
    }


@api_router.post("/auth/logout")
async def logout(request: Request):
    request.session.clear()
    return {"status": "signed_out"}


@api_router.get("/")
async def root():
    return {"message": "Weddings by Mark - Accounting API"}


@api_router.get("/tax-years")
async def get_tax_years():
    return UK_TAX_YEARS


@api_router.get("/expense-categories")
async def get_expense_categories():
    return UK_EXPENSE_CATEGORIES



@api_router.get("/settings")
async def get_settings():
    settings = await db.settings.find_one({}, {"_id": 0})
    if not settings:
        settings = {
            "business_name": "Weddings by Mark",
            "brand_color": "#C7A76D",
            "currency": "GBP",
            "date_format": "DD/MM/YYYY",
            "current_tax_year": "2025-26",
            "excluded_names": ["HMRC", "MARK POWELL", "MARK ADAM POWELL"],
            "mileage_rate": 0.45
        }
    return settings

@api_router.post("/settings")
async def update_settings(settings: dict):
    await db.settings.update_one({}, {"$set": settings}, upsert=True)
    return settings


# MTD Tax Preparation endpoints
@api_router.get("/tax-prep/{tax_year}")
async def get_tax_prep(tax_year: str):
    """Get quarterly and annual tax summary for MTD"""
    # Parse tax year (e.g., "2025-26" -> start April 2025)
    try:
        start_year = int(tax_year.split("-")[0])
    except (ValueError, IndexError):
        raise HTTPException(status_code=400, detail="Invalid tax year format")
    
    # UK tax quarters
    quarters = [
        {"name": "Q1", "label": f"6 Apr - 5 Jul {start_year}", "start": f"06/04/{start_year}", "end": f"05/07/{start_year}"},
        {"name": "Q2", "label": f"6 Jul - 5 Oct {start_year}", "start": f"06/07/{start_year}", "end": f"05/10/{start_year}"},
        {"name": "Q3", "label": f"6 Oct {start_year} - 5 Jan {start_year+1}", "start": f"06/10/{start_year}", "end": f"05/01/{start_year+1}"},
        {"name": "Q4", "label": f"6 Jan - 5 Apr {start_year+1}", "start": f"06/01/{start_year+1}", "end": f"05/04/{start_year+1}"},
    ]
    
    transactions = await db.transactions.find({"tax_year": tax_year}, {"_id": 0}).to_list(10000)
    expenses = await db.expenses.find({"tax_year": tax_year}, {"_id": 0}).to_list(10000)
    invoices = await db.invoices.find({"tax_year": tax_year, "include_in_totals": True}, {"_id": 0}).to_list(10000)
    invoice_income = sum(inv.get("total_price", 0) for inv in invoices)
    mileage_entries = await db.mileage.find({"tax_year": tax_year}, {"_id": 0}).to_list(10000)
    
    def parse_date(d):
        if not d:
            return None
        for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(d, fmt)
            except:
                continue
        return None
    
    def in_quarter(date_str, q_start, q_end):
        dt = parse_date(date_str)
        qs = parse_date(q_start)
        qe = parse_date(q_end)
        if dt and qs and qe:
            return qs <= dt <= qe
        return False
    
    quarter_data = []
    annual_income = 0
    annual_expenses = 0
    annual_tax_payments = 0
    
    for q in quarters:
        q_txns = [t for t in transactions if in_quarter(t.get("date", ""), q["start"], q["end"])]
        q_exps = [e for e in expenses if in_quarter(e.get("date", ""), q["start"], q["end"])]
        
        q_income = sum(t["amount"] for t in q_txns if t.get("transaction_type") == "income" and not t.get("excluded_from_totals"))
        q_expense_txns = sum(t["amount"] for t in q_txns if t.get("transaction_type") == "expense" and not t.get("excluded_from_totals"))
        q_expense_manual = sum(e.get("amount", 0) for e in q_exps)
        q_mileage = sum(m.get("amount", 0) for m in mileage_entries if in_quarter(m.get("date", ""), q["start"], q["end"]))
        q_total_expenses = q_expense_txns + q_expense_manual + q_mileage
        q_tax = sum(t["amount"] for t in q_txns if t.get("transaction_type") == "tax_payment")
        
        annual_income += q_income
        annual_expenses += q_total_expenses
        annual_tax_payments += q_tax
        
        # Expense breakdown by category
        category_breakdown = {}
        for t in q_txns:
            if t.get("transaction_type") == "expense" and not t.get("excluded_from_totals"):
                cat = t.get("category") or "Uncategorised"
                category_breakdown[cat] = category_breakdown.get(cat, 0) + t["amount"]
        for e in q_exps:
            cat = e.get("category") or "Uncategorised"
            category_breakdown[cat] = category_breakdown.get(cat, 0) + e.get("amount", 0)
        if q_mileage > 0:
            category_breakdown["Travel & Mileage"] = category_breakdown.get("Travel & Mileage", 0) + q_mileage
        
        quarter_data.append({
            "name": q["name"],
            "label": q["label"],
            "income": round(q_income, 2),
            "expenses": round(q_total_expenses, 2),
            "profit": round(q_income - q_total_expenses, 2),
            "tax_payments": round(q_tax, 2),
            "transaction_count": len(q_txns),
            "category_breakdown": category_breakdown
        })
    
    return {
        "tax_year": tax_year,
        "quarters": quarter_data,
        "annual": {
            "income": round(annual_income + invoice_income, 2),
            "bank_income": round(annual_income, 2),
            "invoice_income": round(invoice_income, 2),
            "expenses": round(annual_expenses, 2),
            "profit": round(annual_income + invoice_income - annual_expenses, 2),
            "tax_payments": round(annual_tax_payments, 2),
            "tax_due_estimate": round(max(0, (annual_income + invoice_income - annual_expenses) - 12570) * 0.20, 2)
        }
    }


@api_router.get("/tax-prep/{tax_year}/export")
async def export_tax_prep(tax_year: str):
    """Export tax data as CSV for MTD submission"""
    import csv
    import io
    
    data = await get_tax_prep(tax_year)
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Header
    writer.writerow(["Weddings by Mark - Tax Summary"])
    writer.writerow([f"Tax Year: {tax_year}"])
    writer.writerow([])
    
    # Annual Summary
    writer.writerow(["ANNUAL SUMMARY"])
    writer.writerow(["Total Income", f"{data['annual']['income']:.2f}"])
    writer.writerow(["Total Expenses", f"{data['annual']['expenses']:.2f}"])
    writer.writerow(["Net Profit", f"{data['annual']['profit']:.2f}"])
    writer.writerow(["Estimated Tax Due (20%)", f"{data['annual']['tax_due_estimate']:.2f}"])
    writer.writerow([])
    
    # Quarterly Breakdown
    writer.writerow(["QUARTERLY BREAKDOWN"])
    writer.writerow(["Quarter", "Period", "Income", "Expenses", "Profit"])
    for q in data["quarters"]:
        writer.writerow([q["name"], q["label"], f"{q['income']:.2f}", f"{q['expenses']:.2f}", f"{q['profit']:.2f}"])
    writer.writerow([])
    
    # Expense Categories per Quarter
    writer.writerow(["EXPENSE BREAKDOWN BY CATEGORY"])
    for q in data["quarters"]:
        if q["category_breakdown"]:
            writer.writerow([f"{q['name']} - {q['label']}"])
            for cat, amount in sorted(q["category_breakdown"].items()):
                writer.writerow(["", cat, f"{amount:.2f}"])
    
    # Individual expenses
    expenses = await db.expenses.find({"tax_year": tax_year}, {"_id": 0}).to_list(10000)
    if expenses:
        writer.writerow([])
        writer.writerow(["EXPENSES"])
        writer.writerow(["Date", "Description", "Category", "Supplier", "Amount"])
        for e in sorted(expenses, key=lambda x: x.get("date", ""), reverse=True):
            writer.writerow([e.get("date",""), e.get("description",""), e.get("category",""), e.get("supplier",""), f"{e.get('amount',0):.2f}"])
    
    # Individual invoices
    invoices = await db.invoices.find({"tax_year": tax_year}, {"_id": 0}).to_list(10000)
    if invoices:
        writer.writerow([])
        writer.writerow(["INVOICES"])
        writer.writerow(["Date", "Client", "Description", "Invoice #", "Amount", "In Totals"])
        for inv in sorted(invoices, key=lambda x: x.get("date", ""), reverse=True):
            writer.writerow([inv.get("date",""), inv.get("client_name",""), inv.get("description",""), inv.get("invoice_number",""), f"{inv.get('amount',0):.2f}", "Yes" if inv.get("include_in_totals") else "No"])
    
    csv_content = output.getvalue()
    
    # Save to temp file and return
    temp_path = BACKUP_DIR / f"tax_return_{tax_year}.csv"
    temp_path.parent.mkdir(parents=True, exist_ok=True)
    with open(temp_path, "w") as f:
        f.write(csv_content)
    
    return FileResponse(
        str(temp_path),
        media_type="text/csv",
        filename=f"weddings_by_mark_tax_{tax_year}.csv"
    )

@api_router.get("/tax-prep/{tax_year}/export/{quarter}")
async def export_quarter(tax_year: str, quarter: str):
    """Export a single quarter as CSV"""
    import csv, io
    
    data = await get_tax_prep(tax_year)
    q_data = next((q for q in data["quarters"] if q["name"] == quarter), None)
    if not q_data:
        raise HTTPException(status_code=404, detail="Quarter not found")
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Weddings by Mark - Quarterly Tax Return"])
    writer.writerow([f"Tax Year: {tax_year}", f"Quarter: {quarter}", q_data["label"]])
    writer.writerow([])
    writer.writerow(["Income", f"{q_data['income']:.2f}"])
    writer.writerow(["Expenses", f"{q_data['expenses']:.2f}"])
    writer.writerow(["Net Profit", f"{q_data['profit']:.2f}"])
    writer.writerow([])
    
    if q_data.get("category_breakdown"):
        writer.writerow(["EXPENSE BREAKDOWN"])
        for cat, amount in sorted(q_data["category_breakdown"].items()):
            writer.writerow([cat, f"{amount:.2f}"])
    
    # Add individual transactions
    writer.writerow([])
    writer.writerow(["TRANSACTIONS"])
    writer.writerow(["Date", "Description", "Type", "Amount"])
    
    transactions = await db.transactions.find({"tax_year": tax_year}, {"_id": 0}).to_list(10000)
    
    def parse_date(d):
        if not d:
            return None
        for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(d, fmt)
            except:
                continue
        return None
    def in_q(date_str):
        dt = parse_date(date_str)
        qs = parse_date(q_data["_start"])
        qe = parse_date(q_data["_end"])
        if dt and qs and qe:
            return qs <= dt <= qe
        return False
    
    # Get quarter date range from the parent function's quarters list
    try:
        start_year = int(tax_year.split("-")[0])
    except:
        start_year = 2025
    
    q_ranges = {
        "Q1": (f"06/04/{start_year}", f"05/07/{start_year}"),
        "Q2": (f"06/07/{start_year}", f"05/10/{start_year}"),
        "Q3": (f"06/10/{start_year}", f"05/01/{start_year+1}"),
        "Q4": (f"06/01/{start_year+1}", f"05/04/{start_year+1}"),
    }
    q_start, q_end = q_ranges.get(quarter, ("", ""))
    qs = parse_date(q_start)
    qe = parse_date(q_end)
    
    for t in transactions:
        dt = parse_date(t.get("date", ""))
        if dt and qs and qe and qs <= dt <= qe and not t.get("excluded_from_totals"):
            writer.writerow([t["date"], t.get("description",""), t.get("transaction_type",""), f"{t.get('amount',0):.2f}"])
    
    # Add expenses for this quarter
    expenses = await db.expenses.find({"tax_year": tax_year}, {"_id": 0}).to_list(10000)
    quarter_expenses = [e for e in expenses if parse_date(e.get("date","")) and qs and qe and qs <= parse_date(e.get("date","")) <= qe]
    if quarter_expenses:
        writer.writerow([])
        writer.writerow(["EXPENSES"])
        writer.writerow(["Date", "Description", "Category", "Supplier", "Amount"])
        for e in sorted(quarter_expenses, key=lambda x: x.get("date", ""), reverse=True):
            writer.writerow([e.get("date",""), e.get("description",""), e.get("category",""), e.get("supplier",""), f"{e.get('amount',0):.2f}"])
    
    csv_content = output.getvalue()
    temp_path = BACKUP_DIR / f"tax_return_{tax_year}_{quarter}.csv"
    temp_path.parent.mkdir(parents=True, exist_ok=True)
    with open(temp_path, "w") as f:
        f.write(csv_content)
    
    return FileResponse(str(temp_path), media_type="text/csv", filename=f"weddings_by_mark_{tax_year}_{quarter}.csv")





async def _tax_close_snapshot(tax_year: str) -> dict:
    """Load every source ledger and build one authoritative cash-basis view."""
    try:
        tax_year_bounds(tax_year)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid tax year") from exc
    settings = await get_settings()
    transactions = await db.transactions.find({"tax_year": tax_year}, {"_id": 0}).to_list(100000)
    expenses = await db.expenses.find({"tax_year": tax_year}, {"_id": 0}).to_list(100000)
    mileage_entries = await db.mileage.find({"tax_year": tax_year}, {"_id": 0}).to_list(100000)
    invoices = await db.invoices.find({}, {"_id": 0}).to_list(100000)
    bank_statements = await db.bank_statements.find({}, {"_id": 0}).to_list(10000)
    cash_confirmations = await db.cash_payment_confirmations.find(
        {"tax_year": tax_year, "active": True}, {"_id": 0}
    ).to_list(100000)
    bank_matches = await db.booking_bank_matches.find(
        {"tax_year": tax_year, "active": True}, {"_id": 0}
    ).to_list(100000)
    return build_tax_snapshot(
        tax_year=tax_year,
        business_name=str(settings.get("business_name") or "Weddings by Mark"),
        transactions=transactions,
        expenses=expenses,
        mileage=mileage_entries,
        invoices=invoices,
        bank_statements=bank_statements,
        cash_confirmations=cash_confirmations,
        generated_at=datetime.now(timezone.utc).isoformat(),
        bank_matches=bank_matches,
    )


async def _tax_year_close_state(tax_year: str) -> dict:
    record = await db.tax_year_closes.find_one({"tax_year": tax_year}, {"_id": 0})
    return record or {"tax_year": tax_year, "status": "open", "versions": []}


def _public_tax_year_close_state(state: dict) -> dict:
    public = json.loads(json.dumps(state, default=str))
    if isinstance(public.get("pack"), dict):
        public["pack"].pop("pack_path", None)
    for version in public.get("versions") or []:
        if isinstance(version, dict):
            version.pop("pack_path", None)
    if public.get("pack"):
        public["download_url"] = f"/api/tax-year-close/{public['tax_year']}/download"
    return public


async def _assert_tax_year_open(tax_year: Optional[str]) -> None:
    """Prevent accidental changes to records in a formally closed tax year."""
    if not tax_year:
        return
    record = await db.tax_year_closes.find_one({"tax_year": tax_year, "status": "closed"}, {"_id": 0, "tax_year": 1})
    if record:
        raise HTTPException(
            status_code=423,
            detail=f"Tax year {tax_year} is closed. Reopen it from Tax Year Close before changing its records.",
        )


async def _assert_tax_years_open(tax_years: set[str]) -> None:
    for tax_year in sorted(item for item in tax_years if item):
        await _assert_tax_year_open(tax_year)


def _invoice_cash_tax_years(invoice: dict) -> set[str]:
    years = {
        invoice.get("deposit_tax_year"),
        invoice.get("interim_tax_year"),
        calc_tax_year_from_date(invoice.get("final_payment_paid_date")) if invoice.get("final_payment_paid_date") else None,
    }
    for payment in invoice.get("payments") or []:
        if payment.get("paid_date"):
            years.add(calc_tax_year_from_date(format_date_uk(payment.get("paid_date"))))
    if invoice.get("include_in_totals") and invoice.get("tax_year"):
        years.add(invoice.get("tax_year"))
    return {str(item) for item in years if item}


def _safe_evidence_source(file_path: Any) -> Optional[Path]:
    if not file_path:
        return None
    source = Path(str(file_path)).resolve()
    try:
        source.relative_to(UPLOAD_DIR.resolve())
    except ValueError:
        logger.warning("Tax pack skipped evidence outside the managed upload root: %s", source)
        return None
    return source if source.is_file() else None


async def _tax_pack_evidence(snapshot: dict) -> list[dict]:
    evidence: list[dict] = []
    expenses_by_id = {
        row.get("id"): row
        for row in await db.expenses.find({"tax_year": snapshot["tax_year"]}, {"_id": 0}).to_list(100000)
    }
    for indexed in snapshot.get("receipt_index", []):
        record = expenses_by_id.get(indexed.get("expense_id")) or {}
        source = _safe_evidence_source(record.get("file_path"))
        if source:
            evidence.append({
                "category": "receipts",
                "source_path": str(source),
                "file_name": record.get("file_name") or source.name,
                "record_id": record.get("id"),
            })

    statement_ids = {row.get("bank_statement_id") for row in snapshot.get("transaction_ledger", []) if row.get("bank_statement_id")}
    statements = await db.bank_statements.find({"id": {"$in": list(statement_ids)}}, {"_id": 0}).to_list(10000) if statement_ids else []
    for record in statements:
        source = _safe_evidence_source(record.get("file_path"))
        if source:
            evidence.append({
                "category": "bank-statements",
                "source_path": str(source),
                "file_name": record.get("file_name") or source.name,
                "record_id": record.get("id"),
            })

    invoice_ids = {row.get("invoice_id") for row in snapshot.get("invoice_payment_audit", []) if row.get("invoice_id")}
    invoices = await db.invoices.find({"id": {"$in": list(invoice_ids)}}, {"_id": 0}).to_list(100000) if invoice_ids else []
    for record in invoices:
        record = await _ensure_invoice_pdf_current(record)
        source = _safe_evidence_source(record.get("file_path"))
        if source:
            evidence.append({
                "category": "invoices",
                "source_path": str(source),
                "file_name": record.get("file_name") or source.name,
                "record_id": record.get("id"),
            })
    return evidence


@api_router.get("/tax-year-close/{tax_year}")
async def get_tax_year_close(tax_year: str):
    snapshot = await _tax_close_snapshot(tax_year)
    close_state = await _tax_year_close_state(tax_year)
    public_snapshot = {
        key: value for key, value in snapshot.items()
        if key not in {"transaction_ledger", "income_ledger", "expense_ledger", "mileage_ledger", "invoice_payment_audit", "receipt_index", "bank_statements"}
    }
    if isinstance(public_snapshot.get("booking_reconciliation"), dict):
        public_snapshot["booking_reconciliation"].pop("matched_rows", None)
    return {"close": _public_tax_year_close_state(close_state), "review": public_snapshot}


@api_router.get("/tax-year-close/{tax_year}/history")
async def get_tax_year_close_history(tax_year: str):
    try:
        tax_year_bounds(tax_year)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid tax year") from exc
    return await db.tax_year_close_audit.find(
        {"tax_year": tax_year}, {"_id": 0}
    ).sort("created_at", -1).to_list(1000)


def _booking_payment_from_invoice(invoice: dict, source_payment_id: str) -> Optional[dict]:
    return next(
        (item for item in invoice.get("payments") or [] if str(item.get("id") or "") == source_payment_id),
        None,
    )


@api_router.post("/tax-year-close/{tax_year}/cash-payments/confirm")
async def confirm_booking_cash_payment(tax_year: str, payload: CashPaymentAction, request: Request):
    if payload.confirmation.strip() != "CONFIRM CASH":
        raise HTTPException(status_code=422, detail='Type "CONFIRM CASH" exactly')
    await _assert_tax_year_open(tax_year)
    invoice = await db.invoices.find_one({
        "id": payload.source_invoice_id,
        "source_system": "booking_system",
    }, {"_id": 0})
    if not invoice:
        raise HTTPException(status_code=404, detail="Linked Booking invoice not found")
    payment = _booking_payment_from_invoice(invoice, payload.source_payment_id)
    if not payment or float(payment.get("amount") or 0) <= 0:
        raise HTTPException(status_code=404, detail="Positive Booking payment not found")
    payment_year = calc_tax_year_from_date(format_date_uk(payment.get("paid_date")))
    if payment_year != tax_year:
        raise HTTPException(status_code=409, detail=f"This payment belongs to tax year {payment_year}")

    now_iso = datetime.now(timezone.utc).isoformat()
    admin_email = _admin_from_request(request)
    key = {
        "tax_year": tax_year,
        "source_invoice_id": payload.source_invoice_id,
        "source_payment_id": payload.source_payment_id,
    }
    existing = await db.cash_payment_confirmations.find_one(key, {"_id": 0})
    confirmation_id = (existing or {}).get("id") or str(uuid.uuid4())
    record = {
        **key,
        "id": confirmation_id,
        "invoice_number": invoice.get("invoice_number"),
        "client": invoice.get("couple_names") or invoice.get("client_name") or "",
        "amount": round(float(payment.get("amount") or 0), 2),
        "paid_date": payment.get("paid_date"),
        "reason": payload.reason.strip(),
        "confirmed_by": admin_email,
        "created_at": now_iso,
        "active": True,
    }
    await db.cash_payment_confirmations.update_one(key, {"$set": record}, upsert=True)
    await db.cash_payment_audit.insert_one({
        "id": str(uuid.uuid4()), **key, "action": "confirmed_cash",
        "reason": payload.reason.strip(), "admin_email": admin_email, "created_at": now_iso,
    })
    return record


@api_router.post("/tax-year-close/{tax_year}/cash-payments/revoke")
async def revoke_booking_cash_payment(tax_year: str, payload: CashPaymentAction, request: Request):
    if payload.confirmation.strip() != "REMOVE CASH":
        raise HTTPException(status_code=422, detail='Type "REMOVE CASH" exactly')
    await _assert_tax_year_open(tax_year)
    key = {
        "tax_year": tax_year,
        "source_invoice_id": payload.source_invoice_id,
        "source_payment_id": payload.source_payment_id,
    }
    existing = await db.cash_payment_confirmations.find_one({**key, "active": True}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Active cash confirmation not found")
    now_iso = datetime.now(timezone.utc).isoformat()
    admin_email = _admin_from_request(request)
    await db.cash_payment_confirmations.update_one(key, {"$set": {
        "active": False,
        "revoked_at": now_iso,
        "revoked_by": admin_email,
        "revocation_reason": payload.reason.strip(),
    }})
    await db.cash_payment_audit.insert_one({
        "id": str(uuid.uuid4()), **key, "action": "cash_confirmation_removed",
        "reason": payload.reason.strip(), "admin_email": admin_email, "created_at": now_iso,
    })
    return {"status": "removed", **key}


@api_router.post("/tax-year-close/{tax_year}/combined-bank-matches")
async def create_combined_bank_match(tax_year: str, payload: CombinedBankMatchCreate, request: Request):
    if payload.confirmation.strip() != "MATCH BANK":
        raise HTTPException(status_code=422, detail='Type "MATCH BANK" exactly')
    await _assert_tax_year_open(tax_year)

    payment_refs = [item.model_dump() for item in payload.payments]
    payment_keys = [f"{item['source_invoice_id']}:{item['source_payment_id']}" for item in payment_refs]
    if len(set(payment_keys)) != len(payment_keys):
        raise HTTPException(status_code=422, detail="Select each Booking payment only once")

    bank = await db.transactions.find_one({
        "id": payload.bank_transaction_id,
        "tax_year": tax_year,
    }, {"_id": 0})
    if not bank:
        raise HTTPException(status_code=404, detail="Bank transaction not found in this tax year")
    if str(bank.get("transaction_type") or "").lower() != "income" or bank.get("excluded_from_totals"):
        raise HTTPException(status_code=409, detail="The selected bank transaction must be included income")

    selected_payments = []
    for item, payment_key in zip(payment_refs, payment_keys):
        invoice = await db.invoices.find_one({
            "id": item["source_invoice_id"],
            "source_system": "booking_system",
        }, {"_id": 0})
        if not invoice:
            raise HTTPException(status_code=404, detail="One of the linked Booking invoices was not found")
        payment = _booking_payment_from_invoice(invoice, item["source_payment_id"])
        if not payment or float(payment.get("amount") or 0) <= 0:
            raise HTTPException(status_code=404, detail="One of the selected positive Booking payments was not found")
        if str(payment.get("payment_type") or "").lower() == "cash":
            raise HTTPException(status_code=409, detail="A cash payment cannot be linked to a bank receipt")
        payment_year = calc_tax_year_from_date(format_date_uk(payment.get("paid_date")))
        if payment_year != tax_year:
            raise HTTPException(status_code=409, detail=f"A selected payment belongs to tax year {payment_year}")
        selected_payments.append({
            "payment_key": payment_key,
            "source_invoice_id": item["source_invoice_id"],
            "source_payment_id": item["source_payment_id"],
            "invoice_number": invoice.get("invoice_number"),
            "client": invoice.get("couple_names") or invoice.get("client_name") or "",
            "amount": round(float(payment.get("amount") or 0), 2),
            "paid_date": payment.get("paid_date"),
        })

    selected_total = round(sum(item["amount"] for item in selected_payments), 2)
    bank_amount = round(float(bank.get("amount") or 0), 2)
    if abs(selected_total - bank_amount) > 0.009:
        raise HTTPException(
            status_code=409,
            detail=f"Selected Booking payments total £{selected_total:.2f}, but the bank receipt is £{bank_amount:.2f}",
        )

    duplicate_bank = await db.booking_bank_matches.find_one({
        "tax_year": tax_year,
        "bank_transaction_id": payload.bank_transaction_id,
        "active": True,
    }, {"_id": 0, "id": 1})
    if duplicate_bank:
        raise HTTPException(status_code=409, detail="That bank receipt is already used by a combined match")
    duplicate_payment = await db.booking_bank_matches.find_one({
        "tax_year": tax_year,
        "payment_keys": {"$in": payment_keys},
        "active": True,
    }, {"_id": 0, "id": 1})
    if duplicate_payment:
        raise HTTPException(status_code=409, detail="One of those Booking payments is already bank-matched")
    cash_conflict = await db.cash_payment_confirmations.find_one({
        "tax_year": tax_year,
        "active": True,
        "$or": [
            {"source_invoice_id": item["source_invoice_id"], "source_payment_id": item["source_payment_id"]}
            for item in payment_refs
        ],
    }, {"_id": 0, "id": 1})
    if cash_conflict:
        raise HTTPException(status_code=409, detail="Undo the existing cash confirmation before matching this bank receipt")

    now_iso = datetime.now(timezone.utc).isoformat()
    admin_email = _admin_from_request(request)
    match_id = str(uuid.uuid4())
    record = {
        "id": match_id,
        "tax_year": tax_year,
        "bank_transaction_id": payload.bank_transaction_id,
        "bank_description": bank.get("description") or "",
        "bank_date": bank.get("date") or "",
        "bank_amount": bank_amount,
        "payment_keys": payment_keys,
        "payments": selected_payments,
        "reason": payload.reason.strip(),
        "created_by": admin_email,
        "created_at": now_iso,
        "active": True,
    }
    await db.booking_bank_matches.insert_one(record)
    await db.booking_bank_match_audit.insert_one({
        "id": str(uuid.uuid4()),
        "tax_year": tax_year,
        "match_id": match_id,
        "action": "combined_bank_match_created",
        "bank_transaction_id": payload.bank_transaction_id,
        "bank_amount": bank_amount,
        "payment_keys": payment_keys,
        "reason": payload.reason.strip(),
        "admin_email": admin_email,
        "created_at": now_iso,
    })
    record.pop("_id", None)
    return record


@api_router.post("/tax-year-close/{tax_year}/combined-bank-matches/remove")
async def remove_combined_bank_match(tax_year: str, payload: CombinedBankMatchRemove, request: Request):
    if payload.confirmation.strip() != "REMOVE BANK MATCH":
        raise HTTPException(status_code=422, detail='Type "REMOVE BANK MATCH" exactly')
    await _assert_tax_year_open(tax_year)
    existing = await db.booking_bank_matches.find_one({
        "id": payload.match_id,
        "tax_year": tax_year,
        "active": True,
    }, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Active combined bank match not found")
    now_iso = datetime.now(timezone.utc).isoformat()
    admin_email = _admin_from_request(request)
    await db.booking_bank_matches.update_one({"id": payload.match_id}, {"$set": {
        "active": False,
        "removed_at": now_iso,
        "removed_by": admin_email,
        "removal_reason": payload.reason.strip(),
    }})
    await db.booking_bank_match_audit.insert_one({
        "id": str(uuid.uuid4()),
        "tax_year": tax_year,
        "match_id": payload.match_id,
        "action": "combined_bank_match_removed",
        "bank_transaction_id": existing.get("bank_transaction_id"),
        "bank_amount": existing.get("bank_amount"),
        "payment_keys": existing.get("payment_keys") or [],
        "reason": payload.reason.strip(),
        "admin_email": admin_email,
        "created_at": now_iso,
    })
    return {"status": "removed", "match_id": payload.match_id}


@api_router.post("/tax-year-close/{tax_year}/close")
async def close_tax_year(tax_year: str, payload: TaxYearCloseRequest, request: Request):
    expected = f"CLOSE {tax_year}"
    if payload.confirmation.strip() != expected:
        raise HTTPException(status_code=422, detail=f'Type "{expected}" exactly to close this tax year')
    state = await _tax_year_close_state(tax_year)
    if state.get("status") == "closed":
        raise HTTPException(status_code=409, detail=f"Tax year {tax_year} is already closed")
    snapshot = await _tax_close_snapshot(tax_year)
    validation = snapshot["validation"]
    if validation["blocker_count"]:
        raise HTTPException(status_code=409, detail={
            "message": "Resolve every blocking check before closing this tax year",
            "validation": validation,
        })
    if validation["warning_count"] and not payload.acknowledge_warnings:
        raise HTTPException(status_code=422, detail="Review and acknowledge the warnings before closing")

    version_number = len(state.get("versions") or []) + 1
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = TAX_PACK_DIR / tax_year
    output_path = output_dir / f"weddings_by_mark_tax_year_{tax_year}_v{version_number}_{stamp}.zip"
    evidence_files = await _tax_pack_evidence(snapshot)
    pack = await asyncio.to_thread(
        build_evidence_pack,
        snapshot=snapshot,
        output_path=output_path,
        build_id=BUILD_ID,
        evidence_files=evidence_files,
        logo_path=ROOT_DIR / "logo.png",
    )
    now_iso = datetime.now(timezone.utc).isoformat()
    admin_email = _admin_from_request(request)
    version = {
        "version": version_number,
        "closed_at": now_iso,
        "closed_by": admin_email,
        "reason": payload.reason.strip(),
        "summary": snapshot["summary"],
        "validation": validation,
        "source_counts": snapshot["source_counts"],
        **pack,
    }
    await db.tax_year_closes.update_one(
        {"tax_year": tax_year},
        {
            "$set": {
                "tax_year": tax_year,
                "status": "closed",
                "active_version": version_number,
                "closed_at": now_iso,
                "closed_by": admin_email,
                "reason": payload.reason.strip(),
                "summary": snapshot["summary"],
                "validation": validation,
                "pack": pack,
                "snapshot_sha256": snapshot_digest(snapshot),
                "updated_at": now_iso,
            },
            "$push": {"versions": version},
        },
        upsert=True,
    )
    await db.tax_year_close_audit.insert_one({
        "id": str(uuid.uuid4()),
        "tax_year": tax_year,
        "action": "closed",
        "version": version_number,
        "reason": payload.reason.strip(),
        "admin_email": admin_email,
        "snapshot_sha256": pack["snapshot_sha256"],
        "pack_sha256": pack["pack_sha256"],
        "created_at": now_iso,
    })
    return _public_tax_year_close_state(await _tax_year_close_state(tax_year))


@api_router.post("/tax-year-close/{tax_year}/reopen")
async def reopen_tax_year(tax_year: str, payload: TaxYearReopenRequest, request: Request):
    expected = f"REOPEN {tax_year}"
    if payload.confirmation.strip() != expected:
        raise HTTPException(status_code=422, detail=f'Type "{expected}" exactly to reopen this tax year')
    state = await _tax_year_close_state(tax_year)
    if state.get("status") != "closed":
        raise HTTPException(status_code=409, detail=f"Tax year {tax_year} is not closed")
    now_iso = datetime.now(timezone.utc).isoformat()
    admin_email = _admin_from_request(request)
    await db.tax_year_closes.update_one(
        {"tax_year": tax_year},
        {"$set": {
            "status": "open",
            "reopened_at": now_iso,
            "reopened_by": admin_email,
            "reopen_reason": payload.reason.strip(),
            "updated_at": now_iso,
        }},
    )
    await db.tax_year_close_audit.insert_one({
        "id": str(uuid.uuid4()),
        "tax_year": tax_year,
        "action": "reopened",
        "version": state.get("active_version"),
        "reason": payload.reason.strip(),
        "admin_email": admin_email,
        "created_at": now_iso,
    })
    return _public_tax_year_close_state(await _tax_year_close_state(tax_year))


@api_router.get("/tax-year-close/{tax_year}/download")
async def download_tax_year_pack(tax_year: str):
    state = await _tax_year_close_state(tax_year)
    pack = state.get("pack") or {}
    file_path = Path(str(pack.get("pack_path") or "")).resolve()
    pack_root = TAX_PACK_DIR.resolve()
    try:
        file_path.relative_to(pack_root)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="No closed tax-year pack is available") from exc
    if state.get("status") not in {"closed", "open"} or not file_path.is_file():
        raise HTTPException(status_code=404, detail="No closed tax-year pack is available")
    return FileResponse(file_path, filename=pack.get("pack_filename") or file_path.name, media_type="application/zip")


# Invoice endpoints


def _invoice_pdf_date(value: str) -> Optional[str]:
    """Return a PDF date as DD/MM/YYYY, accepting long UK and numeric dates."""
    cleaned = re.sub(r"\s+", " ", str(value or "").strip())
    for fmt in ("%d %B %Y", "%d %b %Y", "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(cleaned, fmt).strftime("%d/%m/%Y")
        except ValueError:
            continue
    return None


def _invoice_pdf_money(value: str) -> float:
    return round(float(str(value).replace(",", "").strip()), 2)


def parse_booking_invoice_text(text: str) -> dict:
    """Parse a native BookingSystem2026 invoice without AI or external services."""
    if not str(text or "").strip():
        raise ValueError("The PDF does not contain selectable text")

    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines() if line.strip()]
    result: Dict[str, Any] = {
        "invoice_number": "",
        "issue_date": "",
        "booking_fee_due": "",
        "final_payment_due": "",
        "couple_names": "",
        "client_address": "",
        "client_email": "",
        "client_phone": "",
        "wedding_date": "",
        "venue": "",
        "total_price": 0.0,
        "deposit_amount": 0.0,
        "deposit_paid_date": "",
        "balance_remaining": 0.0,
        "package_name": "",
        "notes": "",
        "line_items": [],
        "warnings": [],
        "parser": "bookingsystem2026-native-v1",
    }

    def labelled(label: str) -> str:
        match = re.search(rf"(?im)^\s*{label}\s+(.+?)\s*$", text)
        return match.group(1).strip() if match else ""

    number = labelled(r"Number") or labelled(r"Invoice\s*(?:number|no\.?)")
    if number:
        number_match = re.search(r"\bWBM\d{4,8}\b", number, re.IGNORECASE)
        result["invoice_number"] = number_match.group(0).upper() if number_match else number.strip()

    for key, label in (
        ("issue_date", r"Issue\s+date"),
        ("booking_fee_due", r"Booking\s+fee\s+due"),
        ("final_payment_due", r"Final\s+balance\s+due"),
        ("wedding_date", r"Supply\s+date"),
    ):
        raw = labelled(label)
        parsed = _invoice_pdf_date(raw)
        if parsed:
            result[key] = parsed

    bill_to_at = next((idx for idx, line in enumerate(lines) if line.upper() == "BILL TO"), -1)
    description_at = next((idx for idx, line in enumerate(lines) if line.upper() == "DESCRIPTION"), len(lines))
    client_lines = lines[bill_to_at + 1:description_at] if bill_to_at >= 0 else lines[:description_at]
    client_email_index = next(
        (idx for idx, line in enumerate(client_lines) if re.fullmatch(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", line)),
        -1,
    )
    if client_email_index >= 0:
        result["client_email"] = client_lines[client_email_index]
        metadata = re.compile(
            r"^(?:Number|Issue date|Booking fee due|Final balance due|Supply date)\b",
            re.IGNORECASE,
        )
        for candidate in reversed(client_lines[:client_email_index]):
            if candidate.upper() != "INVOICE" and not metadata.match(candidate):
                result["couple_names"] = candidate
                break
        after_email = client_lines[client_email_index + 1:]
        if after_email and re.fullmatch(r"[+\d][\d\s()-]{7,}", after_email[0]):
            result["client_phone"] = re.sub(r"\s+", "", after_email.pop(0))
        if after_email:
            result["client_address"] = ", ".join(after_email)

    def amount_after(label: str) -> float:
        match = re.search(rf"(?im)^\s*{label}\s*$\s*^\s*£([\d,]+(?:\.\d{{1,2}})?)\s*$", text)
        return _invoice_pdf_money(match.group(1)) if match else 0.0

    result["total_price"] = amount_after("Subtotal") or amount_after("Total")
    result["deposit_amount"] = amount_after("Paid")
    result["balance_remaining"] = amount_after("TOTAL OUTSTANDING")

    try:
        desc_start = next(idx for idx, line in enumerate(lines) if line.upper() == "DESCRIPTION")
        amount_header = next(idx for idx in range(desc_start + 1, len(lines)) if lines[idx].upper() == "AMOUNT")
        subtotal_at = next(idx for idx in range(amount_header + 1, len(lines)) if lines[idx].upper() == "SUBTOTAL")
        section = lines[amount_header + 1:subtotal_at]
        money_indexes = [
            idx for idx, line in enumerate(section)
            if re.fullmatch(r"£[\d,]+(?:\.\d{1,2})?", line)
        ]
        items = []
        for position, money_idx in enumerate(money_indexes):
            name_idx = 0 if position == 0 else money_idx - 1
            if position > 0:
                name_idx = money_idx - 1
            name = section[name_idx].strip()
            if not name or name.startswith("£"):
                continue
            next_money = money_indexes[position + 1] if position + 1 < len(money_indexes) else len(section)
            description_end = next_money - 1 if position + 1 < len(money_indexes) else next_money
            description = section[money_idx + 1:description_end]
            items.append({
                "description": name,
                "detail": "\n".join(description).strip(),
                "amount": _invoice_pdf_money(section[money_idx][1:]),
            })
        result["line_items"] = items
        if items:
            result["package_name"] = " + ".join(item["description"] for item in items)
            note_parts = []
            for item in items:
                part = f'{item["description"]} — £{item["amount"]:,.2f}'
                if item["detail"]:
                    part += f'\n{item["detail"]}'
                note_parts.append(part)
            result["notes"] = "\n\n".join(note_parts)
    except (StopIteration, ValueError):
        result["warnings"].append("Package lines could not be separated; please enter them manually.")

    if result["deposit_amount"] > 0 and result["issue_date"]:
        result["deposit_paid_date"] = result["issue_date"]
        result["warnings"].append(
            "The PDF shows an amount paid but not its exact payment date. The issue date was pre-filled; please check it."
        )
    if not result["venue"]:
        result["warnings"].append("The venue is not printed on this invoice; enter it if you want it in Accounts.")

    required = ("invoice_number", "couple_names", "wedding_date", "total_price")
    missing = [field.replace("_", " ") for field in required if not result.get(field)]
    if missing:
        result["warnings"].append("Please complete: " + ", ".join(missing) + ".")
    result["ready_for_review"] = not missing
    return result


@api_router.post("/invoices/scan-pdf")
async def scan_invoice_pdf(file: UploadFile = File(...)):
    """Preview a BookingSystem invoice locally. This endpoint never saves data or files."""
    try:
        import pymupdf
    except ImportError:
        raise HTTPException(status_code=500, detail="pymupdf not installed")

    content, _, original_name = await _read_upload(file, {".pdf"})
    if not content.startswith(b"%PDF-"):
        raise HTTPException(status_code=400, detail="The selected file is not a valid PDF")
    try:
        with pymupdf.open(stream=content, filetype="pdf") as doc:
            if doc.needs_pass:
                raise HTTPException(status_code=400, detail="Password-protected PDFs cannot be imported")
            text = "\n".join(page.get_text() for page in doc)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail="The PDF could not be read") from exc

    if not text.strip():
        raise HTTPException(status_code=400, detail="Could not extract text from PDF. This may be a scanned image.")
    try:
        result = parse_booking_invoice_text(text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    result["file_name"] = original_name
    result["file_sha256"] = hashlib.sha256(content).hexdigest()
    return result


@api_router.post("/invoices/import-pdf")
async def import_invoice_pdf(invoice_json: str = Form(...), file: UploadFile = File(...)):
    """Recreate one reviewed Booking PDF under the next Accounts invoice number."""
    try:
        invoice = InvoiceCreate.model_validate_json(invoice_json)
    except Exception as exc:
        raise HTTPException(status_code=422, detail="The reviewed invoice fields are invalid") from exc

    content, _, original_name = await _read_upload(file, {".pdf"})
    if not content.startswith(b"%PDF-"):
        raise HTTPException(status_code=400, detail="The selected file is not a valid PDF")
    try:
        import pymupdf
        with pymupdf.open(stream=content, filetype="pdf") as doc:
            if doc.needs_pass:
                raise HTTPException(status_code=400, detail="Password-protected PDFs cannot be imported")
            text = "\n".join(page.get_text() for page in doc)
        parsed = parse_booking_invoice_text(text)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail="The PDF could not be verified") from exc

    source_invoice_number = str(invoice.invoice_number or "").strip().upper()
    if not re.fullmatch(r"WBM\d{4,8}", source_invoice_number):
        raise HTTPException(status_code=422, detail="Use the WBM invoice number printed on the PDF")
    if parsed.get("invoice_number") != source_invoice_number:
        raise HTTPException(
            status_code=422,
            detail=f'The PDF is {parsed.get("invoice_number") or "missing its number"}, not {source_invoice_number}',
        )
    source_pdf_sha256 = hashlib.sha256(content).hexdigest()
    duplicate = await db.invoices.find_one(
        {
            "$or": [
                {"source_system": "manual_pdf_import", "source_invoice_number": source_invoice_number},
                {"source_system": "manual_pdf_import", "invoice_number": source_invoice_number},
                {"source_system": "manual_pdf_import", "source_pdf_sha256": source_pdf_sha256},
            ]
        },
        {"_id": 0, "invoice_number": 1},
    )
    if duplicate:
        raise HTTPException(
            status_code=409,
            detail=f"That Booking invoice is already in Accounts as {duplicate.get('invoice_number', 'an invoice')}",
        )

    final_due = invoice.final_payment_due or calc_final_payment_due(invoice.wedding_date)
    balance = round(invoice.total_price - invoice.deposit_amount - invoice.interim_payment, 2)
    deposit_tax_year = calc_tax_year_from_date(invoice.deposit_paid_date) if invoice.deposit_paid_date else None
    interim_tax_year = calc_tax_year_from_date(invoice.interim_payment_date) if invoice.interim_payment_date else None
    final_tax_year = (
        calc_tax_year_from_date(invoice.final_payment_paid_date)
        if invoice.final_payment_paid_date
        else calc_tax_year_from_date(final_due) if final_due else None
    )
    if invoice.final_payment_paid_date:
        status = "Paid in Full"
    elif invoice.interim_payment > 0 and invoice.interim_payment_date:
        status = "Interim Paid"
    elif invoice.deposit_paid_date:
        status = "Deposit Paid"
    else:
        status = "Pending"
    main_tax_year = deposit_tax_year or calc_tax_year_from_date(invoice.wedding_date) or ""
    if invoice.include_in_totals:
        await _assert_tax_years_open({deposit_tax_year, interim_tax_year, final_tax_year, main_tax_year})

    pdf_dir = UPLOAD_DIR / "invoices"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    source_dir = pdf_dir / "source-booking-pdfs"
    source_dir.mkdir(parents=True, exist_ok=True)

    invoice_number = await allocate_next_invoice_number()
    pdf_path = pdf_dir / f"{invoice_number}.pdf"
    source_pdf_path = source_dir / f"{source_invoice_number}-{source_pdf_sha256[:12]}.pdf"
    if pdf_path.exists():
        raise HTTPException(status_code=409, detail=f"A stored PDF already exists for {invoice_number}")

    source_pdf_created = False
    try:
        recreate_booking_invoice_pdf(content, source_invoice_number, invoice_number, pdf_path)
        if not source_pdf_path.exists():
            source_pdf_path.write_bytes(content)
            source_pdf_created = True
    except Exception as exc:
        pdf_path.unlink(missing_ok=True)
        if source_pdf_created:
            source_pdf_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="The Accounts copy of the PDF could not be created") from exc

    invoice_data = {
        "id": str(uuid.uuid4()),
        "invoice_number": invoice_number,
        "issue_date": invoice.issue_date,
        "couple_names": invoice.couple_names,
        "client_address": invoice.client_address,
        "client_email": invoice.client_email,
        "client_phone": invoice.client_phone,
        "wedding_date": invoice.wedding_date,
        "venue": invoice.venue,
        "total_price": invoice.total_price,
        "deposit_amount": invoice.deposit_amount,
        "deposit_paid_date": invoice.deposit_paid_date,
        "deposit_tax_year": deposit_tax_year,
        "interim_payment": invoice.interim_payment,
        "interim_payment_date": invoice.interim_payment_date,
        "interim_tax_year": interim_tax_year,
        "final_payment_due": final_due,
        "final_payment_paid_date": invoice.final_payment_paid_date,
        "final_tax_year": final_tax_year,
        "balance_remaining": balance,
        "status": status,
        "tax_year": main_tax_year,
        "package_name": invoice.package_name,
        "notes": invoice.notes,
        "line_items": invoice.line_items,
        "include_in_totals": invoice.include_in_totals,
        "file_path": str(pdf_path),
        "file_name": f"{invoice_number}.pdf",
        "original_file_name": original_name,
        "source_system": "manual_pdf_import",
        "source_invoice_number": source_invoice_number,
        "source_pdf_path": str(source_pdf_path),
        "source_pdf_sha256": source_pdf_sha256,
        "source_pdf_preserved": True,
        "source_pdf_recreated": True,
        "imported_at": datetime.now(timezone.utc).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        await db.invoices.insert_one(invoice_data)
    except DuplicateKeyError as exc:
        pdf_path.unlink(missing_ok=True)
        if source_pdf_created:
            source_pdf_path.unlink(missing_ok=True)
        raise HTTPException(status_code=409, detail="That Booking invoice has already been imported") from exc
    except Exception:
        pdf_path.unlink(missing_ok=True)
        if source_pdf_created:
            source_pdf_path.unlink(missing_ok=True)
        raise
    invoice_data.pop("_id", None)
    return _public_invoice(invoice_data)


def _highest_accounts_invoice_number(invoices: List[dict]) -> int:
    """Return the highest number in the Accounts-owned WBM sequence."""
    max_num = 1100
    for inv in invoices:
        match = re.fullmatch(r"WBM(\d{4,8})", str(inv.get("invoice_number") or "").upper())
        if match:
            max_num = max(max_num, int(match.group(1)))
    return max_num


async def _seed_accounts_invoice_counter() -> None:
    if await db.counters.find_one({"_id": "accounts_invoice_number"}, {"_id": 1}):
        return
    invoices = await db.invoices.find(
        {
            "invoice_number": {"$regex": "^WBM"},
            "source_system": {"$nin": ["booking_system", "manual_pdf_import"]},
        },
        {"invoice_number": 1, "_id": 0},
    ).to_list(10000)
    try:
        await db.counters.insert_one({
            "_id": "accounts_invoice_number",
            "value": _highest_accounts_invoice_number(invoices),
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    except DuplicateKeyError:
        pass


async def allocate_next_invoice_number() -> str:
    """Atomically reserve the next free Accounts invoice number."""
    await _seed_accounts_invoice_counter()
    while True:
        counter = await db.counters.find_one_and_update(
            {"_id": "accounts_invoice_number"},
            {"$inc": {"value": 1}, "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}},
            return_document=ReturnDocument.AFTER,
        )
        candidate = f"WBM{int(counter['value']):05d}"
        if not await db.invoices.find_one({"invoice_number": candidate}, {"_id": 1}):
            return candidate


async def get_next_invoice_number():
    """Backward-compatible alias which now reserves a concurrency-safe number."""
    return await allocate_next_invoice_number()


def _pdf_text_colour(value: int) -> tuple:
    return (((value >> 16) & 255) / 255, ((value >> 8) & 255) / 255, (value & 255) / 255)


def recreate_booking_invoice_pdf(content: bytes, source_number: str, accounts_number: str, output_path: Path) -> int:
    """Preserve the source design while replacing every printed invoice-number occurrence."""
    import pymupdf

    replacements = 0
    with pymupdf.open(stream=content, filetype="pdf") as doc:
        for page in doc:
            spans = [
                span
                for block in page.get_text("dict").get("blocks", [])
                for line in block.get("lines", [])
                for span in line.get("spans", [])
                if source_number in span.get("text", "")
            ]
            occurrences = page.search_for(source_number)
            replacements += len(occurrences)
            styled_occurrences = []
            for rect in occurrences:
                span = next(
                    (item for item in spans if pymupdf.Rect(item["bbox"]).intersects(rect)),
                    {},
                )
                styled_occurrences.append((rect, span))
                page.add_redact_annot(
                    rect + (-0.35, -0.35, 0.35, 0.35),
                    fill=None,
                    cross_out=False,
                )
            if occurrences:
                page.apply_redactions(
                    images=pymupdf.PDF_REDACT_IMAGE_NONE,
                    graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
                    text=pymupdf.PDF_REDACT_TEXT_REMOVE,
                )
            for rect, span in styled_occurrences:
                font_name = "hebo" if "bold" in str(span.get("font", "")).lower() else "helv"
                font_size = float(span.get("size") or 9)
                colour = _pdf_text_colour(int(span.get("color") or 0))
                baseline = float((span.get("origin") or (rect.x0, rect.y1 - 2))[1])
                page.insert_text(
                    (rect.x0, baseline),
                    accounts_number,
                    fontname=font_name,
                    fontsize=font_size,
                    color=colour,
                    overlay=True,
                )
        if replacements == 0:
            raise ValueError("The printed Booking invoice number could not be located")
        doc.save(str(output_path), garbage=4, deflate=True)

    with pymupdf.open(str(output_path)) as recreated:
        recreated_text = "\n".join(page.get_text() for page in recreated)
    if source_number in recreated_text or accounts_number not in recreated_text:
        output_path.unlink(missing_ok=True)
        raise ValueError("The recreated invoice number could not be verified")
    return replacements


def _public_invoice(invoice: dict) -> dict:
    public = dict(invoice)
    public.pop("source_invoice_number", None)
    public.pop("source_pdf_path", None)
    public.pop("source_pdf_sha256", None)
    return public


def generate_invoice_pdf(invoice_data: dict, output_path: str):
    """Generate a professional PDF invoice with logo"""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT

    doc = SimpleDocTemplate(output_path, pagesize=A4, topMargin=20*mm, bottomMargin=20*mm, leftMargin=20*mm, rightMargin=20*mm)
    elements = []
    styles = getSampleStyleSheet()

    brand_color = colors.HexColor("#C7A76D")
    dark = colors.HexColor("#1c1917")
    grey = colors.HexColor("#78716c")

    heading_style = ParagraphStyle("Heading", parent=styles["Normal"], fontSize=11, textColor=dark, fontName="Helvetica-Bold", spaceBefore=14, spaceAfter=6)
    normal_style = ParagraphStyle("Body", parent=styles["Normal"], fontSize=9, textColor=dark, leading=13)
    small_style = ParagraphStyle("Small", parent=styles["Normal"], fontSize=8, textColor=grey, leading=11)
    right_style = ParagraphStyle("Right", parent=styles["Normal"], fontSize=9, textColor=dark, alignment=TA_RIGHT)
    center_style = ParagraphStyle("Center", parent=styles["Normal"], fontSize=9, textColor=dark, alignment=TA_CENTER)

    def public_invoice_text(value: Any, fallback: str = "") -> str:
        text = str(value or "").strip()
        return fallback if re.search(r"studio\s*ninja", text, flags=re.IGNORECASE) else text

    status_text = str(invoice_data.get("status") or "").strip().lower()
    wedding_cancelled = _is_cancelled_wedding_invoice(invoice_data)
    closed_status = wedding_cancelled or status_text == "void"

    # Logo
    logo_path = Path(__file__).parent / "logo.png"
    if logo_path.exists():
        logo_size = 44*mm if wedding_cancelled else 60*mm
        logo = Image(str(logo_path), width=logo_size, height=logo_size)
        logo.hAlign = "LEFT"
        elements.append(logo)
        elements.append(Spacer(1, 1*mm if wedding_cancelled else 4*mm))
    else:
        title_style = ParagraphStyle("Title", parent=styles["Title"], fontSize=22, textColor=brand_color, spaceAfter=2)
        subtitle_style = ParagraphStyle("Subtitle", parent=styles["Normal"], fontSize=9, textColor=grey, spaceAfter=12)
        elements.append(Paragraph("Weddings By Mark", title_style))
        elements.append(Paragraph("Professional Wedding Photographers", subtitle_style))

    if wedding_cancelled:
        retained_amount = float(invoice_data.get("amount_retained") or 0)
        if not retained_amount:
            retained_amount = max(0.0, float(invoice_data.get("gross_received") or 0) - float(invoice_data.get("total_refunded") or 0))
        banner_title = ParagraphStyle(
            "CancelledBannerTitle", parent=styles["Normal"], fontName="Helvetica-Bold",
            fontSize=20, leading=23, textColor=colors.HexColor("#991b1b"), alignment=TA_CENTER,
        )
        banner_detail = ParagraphStyle(
            "CancelledBannerDetail", parent=styles["Normal"], fontName="Helvetica-Bold",
            fontSize=10, leading=14, textColor=colors.HexColor("#7f1d1d"), alignment=TA_CENTER,
        )
        cancellation_banner = Table([
            [Paragraph("CANCELLED WEDDING", banner_title)],
            [Paragraph(f"PAYMENT RETAINED: £{retained_amount:,.2f} &nbsp;&nbsp;•&nbsp;&nbsp; NO FURTHER PAYMENT DUE", banner_detail)],
        ], colWidths=[170*mm])
        cancellation_banner.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fef2f2")),
            ("BOX", (0, 0), (-1, -1), 2, colors.HexColor("#b91c1c")),
            ("TOPPADDING", (0, 0), (-1, 0), 9),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 4),
            ("TOPPADDING", (0, 1), (-1, 1), 3),
            ("BOTTOMPADDING", (0, 1), (-1, 1), 9),
        ]))
        elements.append(cancellation_banner)
        elements.append(Spacer(1, 3*mm))

    # Invoice info row
    inv_num = invoice_data.get("invoice_number", "")
    issue_date = invoice_data.get("issue_date") or (
        invoice_data.get("created_at", "")[:10] if invoice_data.get("created_at") else ""
    )
    try:
        from datetime import datetime as dt_mod
        d = dt_mod.strptime(issue_date, "%d/%m/%Y") if "/" in issue_date else dt_mod.fromisoformat(issue_date)
        issue_date = d.strftime("%d %b %Y")
    except:
        pass

    closed_label = "CANCELLED WEDDING RECORD" if wedding_cancelled else "VOID INVOICE" if status_text == "void" else "INVOICE"
    info_data = [
        [Paragraph(f"<b>{closed_label}:</b> {inv_num}", normal_style), Paragraph(f"<b>Issue Date:</b> {issue_date}", right_style)],
    ]
    info_table = Table(info_data, colWidths=[270, 270])
    info_table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    elements.append(info_table)
    elements.append(Spacer(1, 3*mm if wedding_cancelled else 6*mm))

    # FROM and INVOICE FOR
    from_text = "Weddings By Mark\n07712117357\nmarkpowell121@googlemail.com\nAshurst Road, Manchester\nM22 5AX"
    client_text = f"{invoice_data.get('couple_names', '')}"
    if invoice_data.get("client_address"):
        client_text += f"\n{invoice_data['client_address']}"
    if invoice_data.get("client_email"):
        client_text += f"\n{invoice_data['client_email']}"
    if invoice_data.get("client_phone"):
        client_text += f"\n{invoice_data['client_phone']}"
    client_text += "\n"
    if invoice_data.get("venue"):
        client_text += f"\nVenue: {invoice_data['venue']}"
    if invoice_data.get("wedding_date"):
        client_text += f"\nWedding Date: {invoice_data['wedding_date']}"

    addr_data = [
        [Paragraph("<b>FROM</b>", ParagraphStyle("h", parent=small_style, textColor=brand_color, fontName="Helvetica-Bold")),
         Paragraph("<b>INVOICE FOR</b>", ParagraphStyle("h", parent=small_style, textColor=brand_color, fontName="Helvetica-Bold"))],
        [Paragraph(from_text.replace("\n", "<br/>"), small_style),
         Paragraph(client_text.replace("\n", "<br/>"), normal_style)],
    ]
    addr_table = Table(addr_data, colWidths=[270, 270])
    addr_table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    elements.append(addr_table)
    elements.append(Spacer(1, 3*mm if wedding_cancelled else 6*mm))

    # Package / Line items
    elements.append(Paragraph("Package Details", heading_style))
    pkg_name = invoice_data.get("package_name") or "Wedding Photography Package"
    notes = public_invoice_text(invoice_data.get("notes"), "")
    total = invoice_data.get("total_price", 0)

    line_data = [
        [Paragraph("<b>Package</b>", small_style), Paragraph("<b>Description</b>", small_style), Paragraph("<b>Amount</b>", ParagraphStyle("rh", parent=small_style, alignment=TA_RIGHT))],
        [Paragraph(pkg_name, normal_style), Paragraph(notes[:300].replace("\n", "<br/>") if notes else "-", small_style), Paragraph(f"£{total:,.2f}", right_style)],
    ]
    line_table = Table(line_data, colWidths=[120, 320, 100])
    line_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f5f5f4")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e7e5e4")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    elements.append(line_table)

    # Total
    total_data = [
        ["", Paragraph("<b>Total</b>", right_style), Paragraph(f"<b>£{total:,.2f}</b>", right_style)],
    ]
    total_table = Table(total_data, colWidths=[320, 120, 100])
    total_table.setStyle(TableStyle([("TOPPADDING", (0, 0), (-1, -1), 6)]))
    elements.append(total_table)
    elements.append(Spacer(1, 4*mm if wedding_cancelled else 8*mm))

    # Payment schedule
    elements.append(Paragraph("Payment Schedule", heading_style))
    deposit = invoice_data.get("deposit_amount", 0)
    interim = invoice_data.get("interim_payment", 0)
    linked = invoice_data.get("source_system") == "booking_system"
    balance = invoice_data.get("balance_remaining", total - deposit - interim) if linked else total - deposit - interim
    dep_date = invoice_data.get("deposit_paid_date") or "-"
    int_date = invoice_data.get("interim_payment_date") or "-"
    final_due = invoice_data.get("final_payment_due") or "-"
    final_paid = invoice_data.get("final_payment_paid_date") or "-"

    dep_status = "Paid" if dep_date != "-" else "Unpaid"
    int_status = "Paid" if int_date != "-" else ("N/A" if interim == 0 else "Unpaid")
    bal_status = "Paid" if final_paid != "-" else "Unpaid"

    pay_data = [
        [Paragraph("<b>Payment</b>", small_style), Paragraph("<b>Amount</b>", ParagraphStyle("r", parent=small_style, alignment=TA_RIGHT)),
         Paragraph("<b>Status</b>", ParagraphStyle("c", parent=small_style, alignment=TA_CENTER)), Paragraph("<b>Date</b>", ParagraphStyle("c", parent=small_style, alignment=TA_CENTER))],
    ]
    if linked:
        gross = invoice_data.get("gross_received", 0) or 0
        refunded = invoice_data.get("total_refunded", 0) or 0
        retained = invoice_data.get("amount_retained", 0) or 0
        itemised_payments = [row for row in (invoice_data.get("payments") or []) if float(row.get("amount") or 0) != 0]
        if itemised_payments:
            for payment in itemised_payments:
                amount = float(payment.get("amount") or 0)
                method = str(payment.get("payment_type") or ("refund" if amount < 0 else "payment")).replace("_", " ").title()
                paid_date = format_date_uk(payment.get("paid_date")) or "Date recorded privately"
                label = "Refund" if amount < 0 else f"Payment received — {method}"
                pay_data.append([
                    Paragraph(label, normal_style),
                    Paragraph(f"-£{abs(amount):,.2f}" if amount < 0 else f"£{amount:,.2f}", right_style),
                    Paragraph("Refunded" if amount < 0 else "Recorded", center_style),
                    Paragraph(paid_date, center_style),
                ])
        else:
            received_date = invoice_data.get("final_payment_paid_date") or invoice_data.get("interim_payment_date") or invoice_data.get("deposit_paid_date") or "Date recorded privately"
            pay_data.append([Paragraph("Payments received", normal_style), Paragraph(f"£{gross:,.2f}", right_style), Paragraph("Recorded", center_style), Paragraph(str(received_date), center_style)])
            if refunded > 0:
                pay_data.append([Paragraph("Refunded", normal_style), Paragraph(f"-£{refunded:,.2f}", right_style), Paragraph("Refunded", center_style), Paragraph("Date recorded privately", center_style)])
        pay_data.append([Paragraph("Payment retained", normal_style), Paragraph(f"£{retained:,.2f}", right_style), Paragraph("Recorded", center_style), Paragraph("-", center_style)])
        pay_data.append([Paragraph("Remaining Balance", normal_style), Paragraph(f"£{balance:,.2f}", right_style), Paragraph("Closed" if closed_status else ("Paid" if balance <= 0 else "Unpaid"), center_style), Paragraph("-" if closed_status or balance <= 0 else f"Due: {final_due}", center_style)])
    else:
        pay_data.append([Paragraph("Deposit", normal_style), Paragraph(f"£{deposit:,.2f}", right_style), Paragraph(dep_status, center_style), Paragraph(dep_date, center_style)])
        if interim > 0:
            pay_data.append([Paragraph("Interim Payment", normal_style), Paragraph(f"£{interim:,.2f}", right_style), Paragraph(int_status, center_style), Paragraph(int_date, center_style)])
        pay_data.append([Paragraph("Remaining Balance", normal_style), Paragraph(f"£{balance:,.2f}", right_style), Paragraph(bal_status, center_style), Paragraph(f"Due: {final_due}" if bal_status == "Unpaid" else final_paid, center_style)])

    pay_table = Table(pay_data, colWidths=[160, 110, 100, 170])
    pay_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f5f5f4")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e7e5e4")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    elements.append(pay_table)

    if linked and wedding_cancelled:
        cancellation_text = public_invoice_text(
            invoice_data.get("cancellation_reason") or invoice_data.get("void_reason"),
            "Wedding cancelled by the client. The payment shown was retained.",
        )
        cancellation_date = invoice_data.get("cancellation_date") or "Not recorded"
        elements.append(Spacer(1, 4*mm))
        cancellation_heading = (
            f"Wedding cancellation recorded {cancellation_date}."
            if cancellation_date != "Not recorded"
            else "Wedding cancellation recorded."
        )
        elements.append(Paragraph(f"<b>{cancellation_heading}</b> {cancellation_text}<br/><b>This cancelled invoice and its retained payment remain preserved for the financial record. No further payment is due.</b>", small_style))

    if status_text == "void" and not wedding_cancelled:
        void_text = public_invoice_text(invoice_data.get("void_reason"), "Invoice voided; the original number remains preserved for the financial record.")
        elements.append(Spacer(1, 4*mm))
        elements.append(Paragraph(f"<b>Invoice voided.</b> {void_text}<br/>No further payment is due.", small_style))

    # Balance due
    if balance > 0 and bal_status == "Unpaid":
        elements.append(Spacer(1, 4*mm))
        bal_data = [["", Paragraph(f"<b>Balance Due: £{balance:,.2f}</b>", ParagraphStyle("bd", parent=right_style, fontSize=12, textColor=brand_color))]]
        bal_table = Table(bal_data, colWidths=[340, 200])
        elements.append(bal_table)

    # Footer
    elements.append(Spacer(1, 4*mm if closed_status else 10*mm))
    if closed_status:
        elements.append(Paragraph("CLOSED FINANCIAL RECORD — NO PAYMENT REQUESTED", ParagraphStyle("ft-closed", parent=normal_style, fontName="Helvetica-Bold", textColor=colors.HexColor("#991b1b"))))
    else:
        elements.append(Paragraph("Pay by Bank Transfer", ParagraphStyle("ft", parent=normal_style, fontName="Helvetica-Bold", textColor=brand_color)))
        elements.append(Spacer(1, 4*mm))
        elements.append(Paragraph("Thank you for choosing Weddings By Mark as your Photographer for the big day.", small_style))

    def draw_status_watermark(canvas, _doc):
        if not wedding_cancelled:
            return
        canvas.saveState()
        try:
            canvas.setFillAlpha(0.08)
        except Exception:
            pass
        canvas.setFillColor(colors.HexColor("#b91c1c"))
        canvas.translate(A4[0] / 2, A4[1] / 2)
        canvas.rotate(32)
        canvas.setFont("Helvetica-Bold", 38)
        canvas.drawCentredString(0, 0, "CANCELLED WEDDING")
        canvas.restoreState()

    doc.build(elements, onFirstPage=draw_status_watermark, onLaterPages=draw_status_watermark)


def calc_final_payment_due(wedding_date_str):
    """Calculate 45 days before wedding date"""
    try:
        wedding = datetime.strptime(wedding_date_str, "%d/%m/%Y")
        due = wedding - timedelta(days=45)
        return due.strftime("%d/%m/%Y")
    except:
        return None


def calc_tax_year_from_date(date_str):
    """Calculate UK tax year from a DD/MM/YYYY date. Tax year runs 6 Apr - 5 Apr."""
    try:
        dt = datetime.strptime(date_str, "%d/%m/%Y")
        year = dt.year
        # If date is between 6 Apr and 31 Dec, tax year starts this year
        # If date is between 1 Jan and 5 Apr, tax year started previous year
        apr6 = datetime(year, 4, 6)
        if dt >= apr6:
            start = year
        else:
            start = year - 1
        end = (start + 1) % 100
        return f"{start}-{end:02d}"
    except:
        return None


@api_router.post("/invoices")
async def create_invoice(invoice: InvoiceCreate):
    inv_num = await get_next_invoice_number()
    final_due = invoice.final_payment_due or calc_final_payment_due(invoice.wedding_date)
    balance = invoice.total_price - invoice.deposit_amount - invoice.interim_payment

    # Auto-calculate tax year per payment
    deposit_tax_year = calc_tax_year_from_date(invoice.deposit_paid_date) if invoice.deposit_paid_date else None
    interim_tax_year = calc_tax_year_from_date(invoice.interim_payment_date) if invoice.interim_payment_date else None
    final_tax_year = calc_tax_year_from_date(invoice.final_payment_paid_date) if invoice.final_payment_paid_date else calc_tax_year_from_date(final_due) if final_due else None

    # Determine status
    if invoice.final_payment_paid_date:
        status = "Paid in Full"
    elif invoice.interim_payment > 0 and invoice.interim_payment_date:
        status = "Interim Paid"
    elif invoice.deposit_paid_date:
        status = "Deposit Paid"
    else:
        status = "Pending"

    # Main tax_year = deposit tax year for filtering
    main_tax_year = deposit_tax_year or calc_tax_year_from_date(invoice.wedding_date) or ""
    if invoice.include_in_totals:
        await _assert_tax_years_open({deposit_tax_year, interim_tax_year, final_tax_year, main_tax_year})

    invoice_data = {
        "id": str(uuid.uuid4()),
        "invoice_number": inv_num,
        "issue_date": invoice.issue_date,
        "couple_names": invoice.couple_names,
        "client_address": invoice.client_address,
        "client_email": invoice.client_email,
        "client_phone": invoice.client_phone,
        "wedding_date": invoice.wedding_date,
        "venue": invoice.venue,
        "total_price": invoice.total_price,
        "deposit_amount": invoice.deposit_amount,
        "deposit_paid_date": invoice.deposit_paid_date,
        "deposit_tax_year": deposit_tax_year,
        "interim_payment": invoice.interim_payment,
        "interim_payment_date": invoice.interim_payment_date,
        "interim_tax_year": interim_tax_year,
        "final_payment_due": final_due,
        "final_payment_paid_date": invoice.final_payment_paid_date,
        "final_tax_year": final_tax_year,
        "balance_remaining": round(balance, 2),
        "status": status,
        "tax_year": main_tax_year,
        "package_name": invoice.package_name,
        "notes": invoice.notes,
        "line_items": invoice.line_items,
        "include_in_totals": invoice.include_in_totals,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    # Generate PDF
    pdf_dir = UPLOAD_DIR / "invoices"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = pdf_dir / f"{inv_num}.pdf"
    generate_invoice_pdf(invoice_data, str(pdf_path))

    invoice_data["file_path"] = str(pdf_path)
    invoice_data["file_name"] = f"{inv_num}.pdf"

    await db.invoices.insert_one(invoice_data)
    invoice_data.pop("_id", None)
    return invoice_data


@api_router.get("/invoices")
async def get_invoices(tax_year: Optional[str] = None):
    query = {}
    if tax_year:
        query["tax_year"] = tax_year
    invoices = await db.invoices.find(query, {"_id": 0}).to_list(10000)
    return [_public_invoice(invoice) for invoice in invoices]


@api_router.put("/invoices/{invoice_id}")
async def update_invoice(invoice_id: str, body: dict):
    """Update invoice — recalculates tax years, status, balance, and regenerates PDF"""
    existing = await db.invoices.find_one({"id": invoice_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if existing.get("source_system") == "booking_system":
        raise HTTPException(status_code=409, detail="Linked invoices are edited in the booking system")
    await _assert_tax_years_open(_invoice_cash_tax_years(existing))

    # Merge updates
    for key in ["issue_date", "couple_names", "client_address", "client_email", "client_phone",
                 "wedding_date", "venue", "total_price", "deposit_amount",
                 "deposit_paid_date", "interim_payment", "interim_payment_date",
                 "final_payment_due", "final_payment_paid_date", "package_name", "notes",
                 "line_items", "include_in_totals"]:
        if key in body:
            existing[key] = body[key]

    total = existing.get("total_price", 0) or 0
    deposit = existing.get("deposit_amount", 0) or 0
    interim = existing.get("interim_payment", 0) or 0
    balance = total - deposit - interim

    # Auto-calculate tax years from payment dates
    dep_date = existing.get("deposit_paid_date")
    int_date = existing.get("interim_payment_date")
    final_paid_date = existing.get("final_payment_paid_date")
    wedding_date = existing.get("wedding_date")
    final_due = existing.get("final_payment_due") or (calc_final_payment_due(wedding_date) if wedding_date else None)

    deposit_ty = calc_tax_year_from_date(dep_date) if dep_date else None
    interim_ty = calc_tax_year_from_date(int_date) if int_date else None
    final_ty = calc_tax_year_from_date(final_paid_date) if final_paid_date else (calc_tax_year_from_date(final_due) if final_due else None)

    # Status
    if final_paid_date:
        status = "Paid in Full"
    elif interim > 0 and int_date:
        status = "Interim Paid"
    elif dep_date:
        status = "Deposit Paid"
    else:
        status = "Pending"

    updates = {
        "issue_date": existing.get("issue_date"),
        "couple_names": existing.get("couple_names", ""),
        "client_address": existing.get("client_address"),
        "client_email": existing.get("client_email"),
        "client_phone": existing.get("client_phone"),
        "wedding_date": wedding_date,
        "venue": existing.get("venue"),
        "total_price": total,
        "deposit_amount": deposit,
        "deposit_paid_date": dep_date,
        "deposit_tax_year": deposit_ty,
        "interim_payment": interim,
        "interim_payment_date": int_date,
        "interim_tax_year": interim_ty,
        "final_payment_due": final_due,
        "final_payment_paid_date": final_paid_date,
        "final_tax_year": final_ty,
        "balance_remaining": round(balance, 2),
        "status": status,
        "tax_year": deposit_ty or calc_tax_year_from_date(wedding_date) or existing.get("tax_year", ""),
        "package_name": existing.get("package_name"),
        "notes": existing.get("notes"),
        "line_items": existing.get("line_items") or [],
        "include_in_totals": existing.get("include_in_totals", False),
    }

    await db.invoices.update_one({"id": invoice_id}, {"$set": updates})

    # Regenerate PDF if invoice has a number
    inv_num = existing.get("invoice_number")
    if inv_num and existing.get("source_system") != "manual_pdf_import":
        merged = {**existing, **updates}
        pdf_dir = UPLOAD_DIR / "invoices"
        pdf_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = pdf_dir / f"{inv_num}.pdf"
        generate_invoice_pdf(merged, str(pdf_path))
        await db.invoices.update_one({"id": invoice_id}, {"$set": {"file_path": str(pdf_path), "file_name": f"{inv_num}.pdf"}})

    updated = await db.invoices.find_one({"id": invoice_id}, {"_id": 0})
    return updated


@api_router.put("/invoices/{invoice_id}/emergency-edit")
async def emergency_edit_linked_invoice(invoice_id: str, body: dict, request: Request):
    """Edit only the Accounts copy of a booking-linked invoice, with an audit lock."""
    existing = await db.invoices.find_one({"id": invoice_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if existing.get("source_system") != "booking_system":
        raise HTTPException(status_code=409, detail="Use the normal edit control for an Accounts-created invoice")
    if _normalised_invoice_status(existing) == "void":
        raise HTTPException(status_code=409, detail="Restore the Booking values before editing a voided linked invoice")
    await _assert_tax_years_open(_invoice_cash_tax_years(existing))

    reason = _override_reason(body)
    before = dict(existing)
    source_snapshot = existing.get("booking_source_snapshot") or _invoice_source_snapshot(existing)
    editable_fields = [
        "couple_names", "client_address", "client_email", "client_phone",
        "wedding_date", "venue", "total_price", "deposit_amount",
        "deposit_paid_date", "interim_payment", "interim_payment_date",
        "final_payment_paid_date", "package_name", "notes",
    ]
    changed_fields = []
    for key in editable_fields:
        if key in body and body[key] != existing.get(key):
            existing[key] = body[key]
            changed_fields.append(key)
    if not changed_fields:
        raise HTTPException(status_code=422, detail="No invoice values were changed")

    try:
        total = round(float(existing.get("total_price") or 0), 2)
        deposit = round(float(existing.get("deposit_amount") or 0), 2)
        interim = round(float(existing.get("interim_payment") or 0), 2)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Invoice amounts must be valid numbers") from exc
    if min(total, deposit, interim) < 0:
        raise HTTPException(status_code=422, detail="Invoice amounts cannot be negative")

    wedding_date = existing.get("wedding_date")
    final_due = calc_final_payment_due(wedding_date) if wedding_date else existing.get("final_payment_due")
    dep_date = existing.get("deposit_paid_date")
    int_date = existing.get("interim_payment_date")
    final_paid_date = existing.get("final_payment_paid_date")
    balance = round(max(0, total - deposit - interim), 2)
    if final_paid_date or balance <= 0.009:
        status = "Paid in Full"
        balance = 0
    elif interim > 0 and int_date:
        status = "Interim Paid"
    elif deposit > 0 or dep_date:
        status = "Deposit Paid"
    else:
        status = "Pending"

    now_iso = datetime.now(timezone.utc).isoformat()
    existing.update({
        "total_price": total,
        "deposit_amount": deposit,
        "interim_payment": interim,
        "final_payment_due": final_due,
        "deposit_tax_year": calc_tax_year_from_date(dep_date) if dep_date else None,
        "interim_tax_year": calc_tax_year_from_date(int_date) if int_date else None,
        "final_tax_year": calc_tax_year_from_date(final_paid_date) if final_paid_date else (calc_tax_year_from_date(final_due) if final_due else None),
        "balance_remaining": balance,
        "status": status,
        "tax_year": (calc_tax_year_from_date(dep_date) if dep_date else None) or calc_tax_year_from_date(wedding_date) or existing.get("tax_year", ""),
        "include_in_totals": False,
        "booking_source_snapshot": source_snapshot,
        "accounts_override": {
            "active": True,
            "action": "edit",
            "reason": reason,
            "admin_email": _admin_from_request(request),
            "changed_fields": changed_fields,
            "created_at": now_iso,
        },
        "updated_at": now_iso,
    })
    _regenerate_invoice_pdf(existing)
    await db.invoices.update_one({"id": invoice_id}, {"$set": existing})
    await _record_invoice_audit(
        invoice_id=invoice_id,
        invoice_number=existing.get("invoice_number", ""),
        action="emergency_edit",
        reason=reason,
        admin_email=_admin_from_request(request),
        before=before,
        after=existing,
    )
    existing.pop("_id", None)
    return existing


@api_router.post("/invoices/{invoice_id}/void")
async def void_accounts_invoice(invoice_id: str, body: dict, request: Request):
    """Void the Accounts copy only. This never changes Booking or emails a client."""
    existing = await db.invoices.find_one({"id": invoice_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if _normalised_invoice_status(existing) == "void":
        raise HTTPException(status_code=409, detail="Invoice is already void")
    await _assert_tax_years_open(_invoice_cash_tax_years(existing))
    reason = _override_reason(body)
    before = dict(existing)
    now_iso = datetime.now(timezone.utc).isoformat()
    linked = existing.get("source_system") == "booking_system"
    source_snapshot = existing.get("booking_source_snapshot") or _invoice_source_snapshot(existing)
    existing.update({
        "status": "void",
        "balance_remaining": 0,
        "void_reason": reason,
        "include_in_totals": False,
        "accounts_override": {
            "active": True,
            "action": "void",
            "reason": reason,
            "admin_email": _admin_from_request(request),
            "changed_fields": ["status", "balance_remaining", "void_reason"],
            "created_at": now_iso,
        },
        "updated_at": now_iso,
    })
    if linked:
        existing["booking_source_snapshot"] = source_snapshot
    _regenerate_invoice_pdf(existing)
    await db.invoices.update_one({"id": invoice_id}, {"$set": existing})
    await _record_invoice_audit(
        invoice_id=invoice_id,
        invoice_number=existing.get("invoice_number", ""),
        action="void",
        reason=reason,
        admin_email=_admin_from_request(request),
        before=before,
        after=existing,
    )
    existing.pop("_id", None)
    return existing


@api_router.post("/invoices/{invoice_id}/restore-booking")
async def restore_booking_invoice_values(invoice_id: str, body: dict, request: Request):
    """Remove an Accounts override and restore the latest saved Booking values."""
    existing = await db.invoices.find_one({"id": invoice_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if existing.get("source_system") != "booking_system":
        raise HTTPException(status_code=409, detail="Only booking-linked invoices have Booking values to restore")
    if not (existing.get("accounts_override") or {}).get("active"):
        raise HTTPException(status_code=409, detail="This invoice has no active Accounts override")
    await _assert_tax_years_open(_invoice_cash_tax_years(existing))
    snapshot = existing.get("booking_source_snapshot")
    if not snapshot:
        raise HTTPException(status_code=409, detail="No saved Booking values are available")

    reason = _override_reason(body)
    before = dict(existing)
    now_iso = datetime.now(timezone.utc).isoformat()
    restored = {**existing, **snapshot}
    restored["include_in_totals"] = False
    restored["booking_source_snapshot"] = snapshot
    restored["accounts_override"] = {
        "active": False,
        "action": "restored",
        "reason": reason,
        "admin_email": _admin_from_request(request),
        "restored_at": now_iso,
    }
    restored["void_reason"] = snapshot.get("void_reason")
    restored["updated_at"] = now_iso
    _regenerate_invoice_pdf(restored)
    await db.invoices.update_one({"id": invoice_id}, {"$set": restored})
    await _record_invoice_audit(
        invoice_id=invoice_id,
        invoice_number=restored.get("invoice_number", ""),
        action="restore_booking",
        reason=reason,
        admin_email=_admin_from_request(request),
        before=before,
        after=restored,
    )
    restored.pop("_id", None)
    return restored


@api_router.get("/invoices/{invoice_id}/audit")
async def get_invoice_audit_history(invoice_id: str):
    existing = await db.invoices.find_one({"id": invoice_id}, {"_id": 0, "id": 1})
    if not existing:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return await db.invoice_audit_logs.find(
        {"invoice_id": invoice_id}, {"_id": 0}
    ).sort("created_at", -1).to_list(1000)


@api_router.get("/invoices/{invoice_id}/pdf")
async def get_invoice_pdf(invoice_id: str):
    invoice = await db.invoices.find_one({"id": invoice_id}, {"_id": 0})
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    invoice = await _ensure_invoice_pdf_current(invoice)
    file_path = invoice.get("file_path")
    if not file_path or not Path(file_path).exists():
        raise HTTPException(status_code=404, detail="PDF not found")
    return FileResponse(str(file_path), media_type="application/pdf", filename=invoice.get("file_name", "invoice.pdf"))


@api_router.delete("/invoices/{invoice_id}")
async def delete_invoice(invoice_id: str):
    invoice = await db.invoices.find_one({"id": invoice_id}, {"_id": 0})
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if invoice.get("source_system") == "booking_system":
        raise HTTPException(status_code=409, detail="Linked invoices are retained and controlled by the booking system")
    await _assert_tax_years_open(_invoice_cash_tax_years(invoice))
    result = await db.invoices.delete_one({"id": invoice_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Invoice not found")
    _delete_managed_upload(invoice.get("file_path"))
    _delete_managed_upload(invoice.get("source_pdf_path"))
    return {"status": "deleted"}


@api_router.post("/invoices/migrate-numbers")
async def migrate_invoice_numbers():
    """One-time migration: re-number all invoices chronologically by deposit date, starting from WBM01101"""
    import random
    invoices = await db.invoices.find(
        {"source_system": {"$ne": "booking_system"}}, {"_id": 0}
    ).to_list(10000)
    
    # Sort by deposit_paid_date (earliest first), fallback to created_at
    def sort_key(inv):
        dep_date = inv.get("deposit_paid_date")
        if dep_date:
            try:
                return datetime.strptime(dep_date, "%d/%m/%Y").isoformat()
            except:
                pass
        created = inv.get("created_at", "2099-01-01")
        return created
    
    invoices.sort(key=sort_key)
    
    results = []
    for i, inv in enumerate(invoices):
        new_num = f"WBM{1101 + i:05d}"
        old_num = inv.get("invoice_number", "")
        
        # Calculate tax years
        dep_date = inv.get("deposit_paid_date")
        int_date = inv.get("interim_payment_date")
        final_paid = inv.get("final_payment_paid_date")
        wedding = inv.get("wedding_date")
        final_due = calc_final_payment_due(wedding) if wedding else inv.get("final_payment_due")
        
        deposit_ty = calc_tax_year_from_date(dep_date) if dep_date else None
        interim_ty = calc_tax_year_from_date(int_date) if int_date else None
        final_ty = calc_tax_year_from_date(final_paid) if final_paid else (calc_tax_year_from_date(final_due) if final_due else None)
        
        total = inv.get("total_price", 0) or inv.get("amount", 0) or 0
        deposit = inv.get("deposit_amount", 0) or 0
        interim = inv.get("interim_payment", 0) or 0
        balance = total - deposit - interim
        
        if final_paid:
            status = "Paid in Full"
        elif interim > 0 and int_date:
            status = "Interim Paid"
        elif dep_date:
            status = "Deposit Paid"
        else:
            status = "Pending"
        
        # Set created_at to the deposit paid date with a random time so PDFs look naturally issued
        fake_created_at = inv.get("created_at", "")
        if dep_date:
            try:
                dep_dt = datetime.strptime(dep_date, "%d/%m/%Y")
                hour = random.randint(9, 17)
                minute = random.randint(0, 59)
                second = random.randint(0, 59)
                fake_created_at = dep_dt.replace(hour=hour, minute=minute, second=second, tzinfo=timezone.utc).isoformat()
            except:
                pass
        
        update_fields = {
            "invoice_number": new_num,
            "deposit_tax_year": deposit_ty,
            "interim_tax_year": interim_ty,
            "final_tax_year": final_ty,
            "final_payment_due": final_due,
            "balance_remaining": round(balance, 2),
            "status": status,
            "tax_year": deposit_ty or calc_tax_year_from_date(wedding) or inv.get("tax_year", ""),
            "created_at": fake_created_at,
        }
        
        await db.invoices.update_one({"id": inv["id"]}, {"$set": update_fields})
        
        # Generate new PDF with the backdated created_at
        merged = {**inv, **update_fields}
        pdf_dir = UPLOAD_DIR / "invoices"
        pdf_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = pdf_dir / f"{new_num}.pdf"
        generate_invoice_pdf(merged, str(pdf_path))
        await db.invoices.update_one({"id": inv["id"]}, {"$set": {"file_path": str(pdf_path), "file_name": f"{new_num}.pdf"}})
        
        results.append({"old": old_num, "new": new_num, "couple": inv.get("couple_names", inv.get("client_name", "?")), "deposit_date": dep_date, "issue_date": fake_created_at[:10]})
    
    return {"migrated": len(results), "invoices": results}




@api_router.put("/invoices/{invoice_id}/status")
async def update_invoice_status(invoice_id: str, body: dict):
    existing = await db.invoices.find_one({"id": invoice_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if existing.get("source_system") == "booking_system":
        raise HTTPException(status_code=409, detail="Linked invoice status is controlled by the booking system")
    await _assert_tax_years_open(_invoice_cash_tax_years(existing))
    status = body.get("status", "pending")
    result = await db.invoices.update_one(
        {"id": invoice_id},
        {"$set": {"status": status}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return {"status": status}

@api_router.put("/invoices/{invoice_id}/paid")
async def update_invoice_paid(invoice_id: str, body: dict):
    existing = await db.invoices.find_one({"id": invoice_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if existing.get("source_system") == "booking_system":
        raise HTTPException(status_code=409, detail="Linked invoice payments are controlled by the booking system")
    await _assert_tax_years_open(_invoice_cash_tax_years(existing))
    paid = body.get("paid", 0)
    result = await db.invoices.update_one(
        {"id": invoice_id},
        {"$set": {"paid": paid}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Invoice not found")
    updated = await db.invoices.find_one({"id": invoice_id}, {"_id": 0})
    return updated


@api_router.get("/integrations/booking/health")
async def booking_integration_health():
    return {"status": "ready", "enabled": True, "version": 2, "build": BUILD_ID}


async def _sync_booking_invoice(payload: BookingInvoiceSync):
    """Idempotently mirror one booking-system invoice into accounts.

    This route never sends email, creates a client portal or changes the
    booking system. Imported invoices are tracking records and are excluded
    from income totals by default to avoid double-counting bank credits.
    """

    if payload.brand != "wbm" or payload.record_kind != "wedding" or payload.is_test:
        raise HTTPException(status_code=422, detail="Only genuine Weddings By Mark wedding jobs can be mirrored")

    cutoff = datetime(2025, 4, 6).date()
    wedding_iso = payload.wedding_date[:10] if payload.wedding_date else None
    try:
        wedding_in_scope = bool(wedding_iso and datetime.fromisoformat(wedding_iso).date() >= cutoff)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid wedding date") from exc
    payment_in_scope = False
    for payment in payload.payments:
        try:
            payment_in_scope = payment_in_scope or datetime.fromisoformat(payment.paid_date[:10]).date() >= cutoff
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Invalid payment date") from exc
    if not wedding_in_scope and not payment_in_scope:
        raise HTTPException(status_code=422, detail="Wedding is outside the agreed 2025/26 accounting scope")

    processed = await db.integration_events.find_one({"event_id": payload.event_id}, {"_id": 0})
    if processed:
        current = await db.invoices.find_one(
            {"source_system": "booking_system", "source_invoice_id": payload.source_invoice_id},
            {"_id": 0},
        )
        return {"status": "already_processed", "source_invoice_id": payload.source_invoice_id, "invoice": current}

    payments = [item.model_dump() for item in payload.payments]
    payments.sort(key=lambda item: (item.get("paid_date") or "", item.get("id") or ""))
    received_payments = [item for item in payments if float(item.get("amount", 0)) > 0]
    refund_payments = [item for item in payments if float(item.get("amount", 0)) < 0]
    gross_received = round(sum(float(item.get("amount", 0)) for item in received_payments), 2)
    total_refunded = round(sum(-float(item.get("amount", 0)) for item in refund_payments), 2)
    net_received = round(max(0, gross_received - total_refunded), 2)
    total_price = round(max(0, payload.total_price), 2)
    closed = payload.status.lower() in {"cancelled", "void"}
    balance = 0 if closed else round(max(0, total_price - net_received), 2)
    first_payment = received_payments[0] if received_payments else None
    remaining_payments = received_payments[1:] if len(received_payments) > 1 else []
    interim_total = round(sum(float(item.get("amount", 0)) for item in remaining_payments), 2)
    paid_in_full = not closed and balance <= 0.009 and total_price > 0
    wedding_date = format_date_uk(payload.wedding_date) if payload.wedding_date else None
    due_date = format_date_uk(payload.due_date) if payload.due_date else (
        calc_final_payment_due(wedding_date) if wedding_date else None
    )
    now_iso = datetime.now(timezone.utc).isoformat()

    existing = await db.invoices.find_one(
        {"source_system": "booking_system", "source_invoice_id": payload.source_invoice_id},
        {"_id": 0},
    )
    invoice_id = existing.get("id") if existing else str(uuid.uuid4())
    invoice_data = {
        "id": invoice_id,
        "invoice_number": payload.invoice_number,
        "legacy_invoice_number": payload.legacy_invoice_number,
        "issue_date": payload.issue_date,
        "source_booking_id": payload.source_booking_id,
        "couple_names": payload.couple_names,
        "client_address": payload.client_address,
        "client_email": payload.client_email,
        "client_phone": payload.client_phone,
        "wedding_date": wedding_date,
        "venue": payload.venue,
        "package_name": payload.package_name,
        "notes": payload.description,
        "line_items": payload.line_items,
        "total_price": total_price,
        "deposit_amount": round(float(first_payment.get("amount", 0)), 2) if first_payment else 0,
        "deposit_paid_date": format_date_uk(first_payment.get("paid_date")) if first_payment else None,
        "deposit_tax_year": calc_tax_year_from_date(format_date_uk(first_payment.get("paid_date"))) if first_payment else None,
        "interim_payment": interim_total,
        "interim_payment_date": format_date_uk(remaining_payments[-1].get("paid_date")) if remaining_payments else None,
        "interim_tax_year": calc_tax_year_from_date(format_date_uk(remaining_payments[-1].get("paid_date"))) if remaining_payments else None,
        "final_payment_due": due_date,
        "final_payment_paid_date": format_date_uk(received_payments[-1].get("paid_date")) if paid_in_full and received_payments else None,
        "final_tax_year": calc_tax_year_from_date(format_date_uk(received_payments[-1].get("paid_date"))) if paid_in_full and received_payments else (calc_tax_year_from_date(due_date) if due_date else None),
        "balance_remaining": balance,
        "amount_paid": net_received,
        "gross_received": gross_received,
        "total_refunded": total_refunded,
        "amount_retained": net_received,
        "payments": payments,
        "status": payload.status,
        "void_reason": payload.void_reason,
        "cancellation_date": format_date_uk(payload.cancellation_date) if payload.cancellation_date else None,
        "cancellation_reason": payload.cancellation_reason,
        "tax_year": calc_tax_year_from_date(format_date_uk(first_payment.get("paid_date"))) if first_payment else (calc_tax_year_from_date(wedding_date) if wedding_date else ""),
        "include_in_totals": False,
        "source_system": "booking_system",
        "source_invoice_id": payload.source_invoice_id,
        "source_scope_reason": payload.scope_reason,
        "source_is_legacy_import": payload.is_legacy_import,
        "source_updated_at": payload.updated_at,
        "updated_at": now_iso,
        "created_at": existing.get("created_at", now_iso) if existing else now_iso,
    }

    source_snapshot = _invoice_source_snapshot(invoice_data)
    if existing and (existing.get("accounts_override") or {}).get("active"):
        await db.invoices.update_one(
            {"id": existing["id"]},
            {"$set": {
                "booking_source_snapshot": source_snapshot,
                "source_updated_at": payload.updated_at,
                "last_booking_sync_at": now_iso,
            }},
        )
        await db.integration_events.insert_one({
            "event_id": payload.event_id,
            "source_invoice_id": payload.source_invoice_id,
            "invoice_number": payload.invoice_number,
            "processed_at": now_iso,
            "manual_override_preserved": True,
        })
        current = await db.invoices.find_one({"id": existing["id"]}, {"_id": 0})
        return {
            "status": "synchronised",
            "source_invoice_id": payload.source_invoice_id,
            "manual_override_preserved": True,
            "invoice": current,
        }

    invoice_data["booking_source_snapshot"] = source_snapshot

    safe_number = re.sub(r"[^A-Za-z0-9_.-]", "_", payload.invoice_number)
    pdf_dir = UPLOAD_DIR / "invoices"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = pdf_dir / f"{safe_number}.pdf"
    generate_invoice_pdf(invoice_data, str(pdf_path))
    invoice_data["file_path"] = str(pdf_path)
    invoice_data["file_name"] = f"{safe_number}.pdf"
    invoice_data["pdf_format_version"] = INVOICE_PDF_FORMAT_VERSION
    old_pdf_path = existing.get("file_path") if existing else None

    await db.invoices.update_one(
        {"source_system": "booking_system", "source_invoice_id": payload.source_invoice_id},
        {"$set": invoice_data},
        upsert=True,
    )
    await db.integration_events.insert_one({
        "event_id": payload.event_id,
        "source_invoice_id": payload.source_invoice_id,
        "invoice_number": payload.invoice_number,
        "processed_at": now_iso,
    })
    if old_pdf_path and Path(old_pdf_path).resolve() != pdf_path.resolve():
        _delete_managed_upload(old_pdf_path)
    invoice_data.pop("_id", None)
    return {"status": "synchronised", "source_invoice_id": payload.source_invoice_id, "invoice": invoice_data}


@api_router.post("/integrations/booking/invoices/sync")
async def sync_booking_invoice(payload: BookingInvoiceSync):
    return await _sync_booking_invoice(payload)


@api_router.post("/integrations/booking/invoices/batch")
async def sync_booking_invoice_batch(payload: BookingInvoiceBatchSync):
    """Mirror a controlled batch while preserving idempotency per invoice revision."""
    results = []
    for invoice in payload.invoices:
        results.append(await _sync_booking_invoice(invoice))
    return {"status": "complete", "count": len(results), "results": results}


# Expense endpoints
@api_router.post("/expenses/scan-pdf")
async def scan_expense_pdf(file: UploadFile = File(...)):
    """Extract expense data from a PDF using pymupdf — zero credits, fully local"""
    import re
    try:
        import pymupdf
    except ImportError:
        raise HTTPException(status_code=500, detail="pymupdf not installed")

    content, _, _ = await _read_upload(file, {".pdf"})
    doc = pymupdf.open(stream=content, filetype="pdf")
    text = ""
    for page in doc:
        text += page.get_text()
    doc.close()

    if not text.strip():
        raise HTTPException(status_code=400, detail="Could not extract text from PDF. This may be a scanned image — use LLM parsing instead.")

    # Parse common invoice patterns
    result = {"description": "", "amount": 0, "supplier": "", "date": "", "raw_text": text[:500]}

    # Try to find grand total / total amount
    total_patterns = [
        r'GRAND\s*TOTAL\s*\(?GBP\)?\s*[£]?\s*([\d,]+\.?\d*)',
        r'GRAND\s*TOTAL\s*[£]?\s*([\d,]+\.?\d*)',
        r'Total\s*(?:Amount|Due|Charged|Payable)\s*[:\s]*[£]?\s*([\d,]+\.?\d*)',
        r'Amount\s*Due\s*[:\s]*[£]?\s*([\d,]+\.?\d*)',
        r'TOTAL\s*[£]?\s*([\d,]+\.?\d*)',
        r'Total\s*[:\s]*£\s*([\d,]+\.?\d*)',
    ]
    for pattern in total_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            result["amount"] = float(match.group(1).replace(",", ""))
            break

    # Try to find date
    date_patterns = [
        (r'(?:Invoice\s*Date|Date\s*of\s*Invoice|Billing\s*Date|Date)\s*[:\s]*(\d{1,2}[-/]\w{3,9}[-/]\d{4})', "mixed"),
        (r'(?:Invoice\s*Date|Date)\s*[:\s]*(\d{1,2}[-/]\d{1,2}[-/]\d{4})', "numeric"),
        (r'(\d{1,2}[-/]\w{3,9}[-/]\d{4})', "mixed"),
        (r'(\d{1,2}/\d{1,2}/\d{4})', "numeric"),
    ]
    months = {"jan": "01", "feb": "02", "mar": "03", "apr": "04", "may": "05", "jun": "06",
              "jul": "07", "aug": "08", "sep": "09", "oct": "10", "nov": "11", "dec": "12"}

    for pattern, fmt in date_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            date_str = match.group(1)
            try:
                if fmt == "mixed":
                    parts = re.split(r'[-/]', date_str)
                    day = parts[0].zfill(2)
                    mon = months.get(parts[1][:3].lower(), parts[1])
                    year = parts[2]
                    result["date"] = f"{day}/{mon}/{year}"
                else:
                    result["date"] = date_str.replace("-", "/")
                break
            except:
                pass

    # Try to find supplier/company name (first few lines often have it)
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    # Look for company-like names
    supplier_patterns = [
        r'(?:From|Seller|Supplier|Company|Billed\s*By)\s*[:\s]*(.+)',
    ]
    for pattern in supplier_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            result["supplier"] = match.group(1).strip()[:100]
            break

    # Fallback: look for known company patterns like "Ltd", "Inc", "Limited"
    if not result["supplier"]:
        for line in lines:
            if re.search(r'\b(Ltd|Limited|Inc|LLC|PLC|Corp|GmbH|Ireland|Software)\b', line, re.IGNORECASE) and len(line) < 80:
                result["supplier"] = line.strip()
                break

    # Product description
    desc_patterns = [
        r'PRODUCT\s*DESCRIPTION\s*\n?\s*(.+)',
        r'Description\s*[:\s]*\n?\s*(.+)',
    ]
    for pattern in desc_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            result["description"] = match.group(1).strip()[:200]
            break

    if not result["description"] and result["supplier"]:
        result["description"] = f"Invoice from {result['supplier']}"

    return result


@api_router.post("/expenses", response_model=Expense)
async def create_expense(expense: ExpenseCreate):
    expense_data = expense.model_dump()
    await _assert_tax_year_open(expense_data.get("tax_year"))
    include_amount = expense_data.pop("include_amount", True)
    
    if not include_amount:
        expense_data["amount"] = 0
    
    expense_obj = Expense(**expense_data)
    doc = expense_obj.model_dump()
    await db.expenses.insert_one(doc)
    return expense_obj


@api_router.post("/expenses/upload")
async def upload_expense(
    file: UploadFile = File(...),
    description: str = Form(...),
    amount: float = Form(...),
    category: str = Form(...),
    date: str = Form(...),
    tax_year: str = Form(...),
    supplier: Optional[str] = Form(None),
    include_amount: bool = Form(True)
):
    await _assert_tax_year_open(tax_year)
    # Save file
    file_id = str(uuid.uuid4())
    content, file_ext, original_name = await _read_upload(file, {".pdf", ".png", ".jpg", ".jpeg", ".webp"})
    file_path = UPLOAD_DIR / "expenses" / tax_year / f"{file_id}{file_ext}"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(file_path, "wb") as f:
        f.write(content)
    
    final_amount = amount if include_amount else 0
    
    expense_obj = Expense(
        description=description,
        amount=final_amount,
        category=category,
        date=format_date_uk(date),
        tax_year=tax_year,
        supplier=supplier,
        file_path=str(file_path),
        file_name=original_name
    )
    
    doc = expense_obj.model_dump()
    await db.expenses.insert_one(doc)
    return expense_obj


@api_router.get("/expenses")
async def get_expenses(tax_year: Optional[str] = None):
    query = {}
    if tax_year:
        query["tax_year"] = tax_year
    expenses = await db.expenses.find(query, {"_id": 0}).to_list(10000)
    return expenses


@api_router.get("/expense-ledger")
async def get_expense_ledger(tax_year: Optional[str] = None):
    transaction_query: Dict[str, Any] = {"transaction_type": "expense"}
    expense_query: Dict[str, Any] = {}
    if tax_year:
        transaction_query["tax_year"] = tax_year
        expense_query["tax_year"] = tax_year
    transactions = await db.transactions.find(transaction_query, {"_id": 0}).to_list(10000)
    expenses = await db.expenses.find(expense_query, {"_id": 0}).to_list(10000)
    return build_expense_ledger_rows(transactions, expenses)


@api_router.put("/expenses/{expense_id}")
async def update_expense(expense_id: str, payload: ExpenseUpdate):
    expense = await db.expenses.find_one({"id": expense_id}, {"_id": 0})
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")
    if expense.get("source_transaction_id") or expense.get("is_from_bank"):
        raise HTTPException(
            status_code=409,
            detail="Edit the original bank transaction instead of its supporting receipt",
        )
    await _assert_tax_year_open(expense.get("tax_year"))
    updates = {
        "description": payload.description.strip(),
        "category": payload.category.strip(),
        "supplier": (payload.supplier or "").strip() or None,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if payload.include_in_totals is not None:
        updates["include_in_totals"] = payload.include_in_totals
    await db.expenses.update_one({"id": expense_id}, {"$set": updates})
    return await db.expenses.find_one({"id": expense_id}, {"_id": 0})


@api_router.get("/expenses/{expense_id}/file")
async def get_expense_file(expense_id: str):
    expense = await db.expenses.find_one({"id": expense_id}, {"_id": 0})
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")
    file_path = expense.get("file_path")
    if not file_path or not Path(file_path).exists():
        raise HTTPException(status_code=404, detail="File not found")
    media_type = mimetypes.guess_type(expense.get("file_name", ""))[0] or "application/octet-stream"
    return FileResponse(str(file_path), media_type=media_type, filename=expense.get("file_name", "receipt"))


@api_router.delete("/expenses/{expense_id}")
async def delete_expense(expense_id: str):
    expense = await db.expenses.find_one({"id": expense_id}, {"_id": 0})
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")
    await _assert_tax_year_open(expense.get("tax_year"))
    result = await db.expenses.delete_one({"id": expense_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Expense not found")
    _delete_managed_upload(expense.get("file_path"))
    return {"status": "deleted"}


# Transaction endpoints
@api_router.get("/transactions")
async def get_transactions(tax_year: Optional[str] = None):
    query = {}
    if tax_year:
        query["tax_year"] = tax_year
    transactions = await db.transactions.find(query, {"_id": 0}).to_list(10000)
    return transactions


@api_router.put("/transactions/{transaction_id}")
async def update_transaction(transaction_id: str, payload: TransactionUpdate):
    transaction = await db.transactions.find_one({"id": transaction_id}, {"_id": 0})
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
    await _assert_tax_year_open(transaction.get("tax_year"))
    category = (payload.category or "").strip() or None
    if payload.transaction_type == "expense" and not payload.excluded_from_totals and not category:
        raise HTTPException(status_code=422, detail="Choose a category for an included expense")
    updates = {
        "transaction_type": payload.transaction_type,
        "category": category,
        "excluded_from_totals": payload.excluded_from_totals,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.transactions.update_one({"id": transaction_id}, {"$set": updates})
    return await db.transactions.find_one({"id": transaction_id}, {"_id": 0})


@api_router.delete("/transactions/{transaction_id}")
async def delete_transaction(transaction_id: str):
    transaction = await db.transactions.find_one({"id": transaction_id}, {"_id": 0})
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
    await _assert_tax_year_open(transaction.get("tax_year"))
    await db.transactions.delete_one({"id": transaction_id})
    await db.expenses.delete_many({"source_transaction_id": transaction_id, "is_from_bank": True})
    return {"status": "deleted"}


# Bank Statement endpoints
@api_router.delete("/bank-statements/all")
async def delete_all_bank_data():
    """Delete all bank statements and their associated transactions"""
    tax_years = set(await db.transactions.distinct("tax_year", {"source": "bank_statement"}))
    await _assert_tax_years_open(tax_years)
    statements = await db.bank_statements.find({}, {"_id": 0, "file_path": 1}).to_list(10000)
    tx_result = await db.transactions.delete_many({"source": "bank_statement"})
    bs_result = await db.bank_statements.delete_many({})
    files_deleted = sum(1 for statement in statements if _delete_managed_upload(statement.get("file_path")))
    return {
        "status": "deleted",
        "transactions_deleted": tx_result.deleted_count,
        "statements_deleted": bs_result.deleted_count,
        "files_deleted": files_deleted,
    }

@api_router.post("/bank-statements/upload")
async def upload_bank_statement(file: UploadFile = File(...)):
    # Save file
    file_id = str(uuid.uuid4())
    content, file_ext, original_name = await _read_upload(file, {".csv", ".pdf", ".png", ".jpg", ".jpeg"})
    file_path = UPLOAD_DIR / "bank_statements" / f"{file_id}{file_ext}"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(file_path, "wb") as f:
        f.write(content)
    
    statement = BankStatement(
        id=file_id,
        file_name=original_name,
        file_path=str(file_path)
    )
    
    doc = statement.model_dump()
    await db.bank_statements.insert_one(doc)
    
    return statement


@api_router.post("/bank-statements/{statement_id}/parse")
async def parse_bank_statement(statement_id: str):
    """Parse bank statement - CSV locally, PDF/images via AI"""
    statement = await db.bank_statements.find_one({"id": statement_id}, {"_id": 0})
    if not statement:
        raise HTTPException(status_code=404, detail="Statement not found")
    
    if statement.get("parse_status") == "processing":
        return {"status": "processing", "message": "Already parsing this statement"}
    
    if statement.get("processed"):
        return {"status": "already_processed", "message": "Statement already processed", "transaction_count": statement.get("transaction_count", 0)}
    
    file_path = statement["file_path"]
    file_ext = Path(file_path).suffix.lower()
    
    if file_ext == ".csv":
        # Parse CSV locally - no AI, no cost
        try:
            transactions = parse_tide_csv(file_path)
            await _assert_tax_years_open({tx.tax_year for tx in transactions})
            created_count = 0
            skipped = 0
            for tx in transactions:
                # Check for duplicates - same date, description, amount
                existing = await db.transactions.find_one({
                    "date": tx.date,
                    "description": tx.description,
                    "amount": tx.amount
                })
                if existing:
                    skipped += 1
                    continue
                doc = tx.model_dump()
                await db.transactions.insert_one(doc)
                created_count += 1
            
            await db.bank_statements.update_one(
                {"id": statement_id},
                {"$set": {
                    "processed": True,
                    "transaction_count": created_count,
                    "parse_status": "success",
                    "parse_error": None
                }}
            )
            return {"status": "success", "transactions_count": created_count, "duplicates_skipped": skipped}
        except Exception as e:
            logger.error(f"CSV parse error: {e}")
            await db.bank_statements.update_one(
                {"id": statement_id},
                {"$set": {"parse_status": "error", "parse_error": str(e)}}
            )
            raise HTTPException(status_code=500, detail=f"Failed to parse CSV: {str(e)}")
    else:
        # PDF/image - use AI in background thread
        await db.bank_statements.update_one(
            {"id": statement_id},
            {"$set": {"parse_status": "processing", "parse_error": None}}
        )
        import threading
        thread = threading.Thread(target=_run_parse_in_thread, args=(statement_id, file_path))
        thread.daemon = True
        thread.start()
        return {"status": "processing", "message": "Parsing PDF with AI. Poll /parse-status for progress."}


def parse_tide_csv(file_path: str) -> list:
    """Parse Tide bank CSV locally - zero cost"""
    import csv
    
    transactions = []
    
    with open(file_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        
        for row in reader:
            # Get the date - Tide format: "2025-04-30 22:03:52"
            raw_date = row.get("Date", "").strip().strip('"')
            if not raw_date:
                continue
            
            # Convert to DD/MM/YYYY
            try:
                dt = datetime.strptime(raw_date.split(" ")[0], "%Y-%m-%d")
                date_str = dt.strftime("%d/%m/%Y")
            except ValueError:
                date_str = format_date_uk(raw_date)
            
            description = row.get("Transaction description", "").strip().strip('"')
            if not description:
                description = row.get("Description", "").strip().strip('"')
            
            # Amount: Tide has "Paid in" and "Paid out" columns
            paid_in = row.get("Paid in", "").strip().strip('"').replace(",", "")
            paid_out = row.get("Paid out", "").strip().strip('"').replace(",", "")
            
            if paid_in and float(paid_in) > 0:
                amount = float(paid_in)
                tx_type_raw = "credit"
            elif paid_out and float(paid_out) > 0:
                amount = float(paid_out)
                tx_type_raw = "debit"
            else:
                # Try single Amount column as fallback
                amt_str = row.get("Amount", "0").strip().strip('"').replace(",", "")
                try:
                    amount = abs(float(amt_str))
                except ValueError:
                    continue
                tx_type_raw = "debit" if float(amt_str) < 0 else "credit"
            
            if amount == 0:
                continue
            
            # Auto-exclude HMRC and owner withdrawals
            excluded = is_owner_withdrawal(description)
            
            if excluded:
                if "HMRC" in description.upper():
                    transaction_type = "tax_payment"
                else:
                    transaction_type = "owner_withdrawal"
            elif tx_type_raw == "credit":
                transaction_type = "income"
            else:
                transaction_type = "expense"
            
            tax_year = get_tax_year_from_date(date_str)
            
            # Read Tide's category
            tide_category = row.get("Category name", "").strip().strip('"') or None
            
            transaction = Transaction(
                date=date_str,
                description=description,
                amount=amount,
                transaction_type=transaction_type,
                category=tide_category,
                tax_year=tax_year,
                source="bank_statement",
                bank_statement_id=Path(file_path).stem,
                excluded_from_totals=excluded
            )
            transactions.append(transaction)
    
    return transactions


def _run_parse_in_thread(statement_id: str, file_path: str):
    """Run the parse in a separate thread with its own event loop"""
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(parse_statement_background(statement_id, file_path))
    finally:
        loop.close()


async def parse_statement_background(statement_id: str, file_path: str):
    """Background task to parse bank statement with retries (runs in separate thread)"""
    # Create a separate MongoDB client for this thread's event loop
    thread_client = AsyncIOMotorClient(os.environ.get("MONGO_URL"))
    thread_db = thread_client[os.environ.get("DB_NAME", "weddings_by_mark")]
    max_retries = 3
    
    for attempt in range(max_retries):
        try:
            import google.generativeai as genai

            api_key = os.environ.get("GEMINI_API_KEY")
            if not api_key:
                await thread_db.bank_statements.update_one(
                    {"id": statement_id},
                    {"$set": {"parse_status": "error", "parse_error": "GEMINI_API_KEY is not configured"}}
                )
                return

            genai.configure(api_key=api_key)
            file_ext = Path(file_path).suffix.lower()
            mime_types = {
                ".pdf": "application/pdf",
                ".csv": "text/csv",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".png": "image/png"
            }
            mime_type = mime_types.get(file_ext, "application/pdf")

            uploaded_file = await asyncio.to_thread(
                genai.upload_file,
                path=file_path,
                mime_type=mime_type,
                display_name=f"bank-statement-{statement_id}",
            )
            model = genai.GenerativeModel(
                "gemini-2.5-flash",
                system_instruction=(
                    "Extract every transaction from the supplied bank statement. "
                    "Return only a JSON array using this exact shape: "
                    '[{"date":"DD/MM/YYYY","description":"Transaction description",'
                    '"amount":123.45,"type":"credit"}]. '
                    "The type must be credit or debit and dates must use UK format."
                ),
            )
            response = await asyncio.to_thread(
                model.generate_content,
                [uploaded_file, "Extract all transactions. Return only the JSON array."],
            )
            response_text = (response.text or "").strip()
            if response_text.startswith("```json"):
                response_text = response_text[7:]
            if response_text.startswith("```"):
                response_text = response_text[3:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]

            parsed_transactions = json.loads(response_text.strip())

            affected_years = {
                get_tax_year_from_date(format_date_uk(item.get("date", "")))
                for item in parsed_transactions
            }
            closed_year = await thread_db.tax_year_closes.find_one(
                {"tax_year": {"$in": list(affected_years)}, "status": "closed"},
                {"_id": 0, "tax_year": 1},
            )
            if closed_year:
                await thread_db.bank_statements.update_one(
                    {"id": statement_id},
                    {"$set": {
                        "parse_status": "error",
                        "parse_error": f"Tax year {closed_year['tax_year']} is closed. Reopen it before importing this statement.",
                    }},
                )
                thread_client.close()
                return
            
            # Process transactions
            created_count = 0
            for tx in parsed_transactions:
                tx_date = format_date_uk(tx.get("date", ""))
                tx_desc = tx.get("description", "")
                tx_amount = abs(float(tx.get("amount", 0)))
                tx_type = tx.get("type", "debit")
                
                excluded = is_owner_withdrawal(tx_desc)
                
                if excluded:
                    if "HMRC" in tx_desc.upper():
                        transaction_type = "tax_payment"
                    else:
                        transaction_type = "owner_withdrawal"
                elif tx_type == "credit":
                    transaction_type = "income"
                else:
                    transaction_type = "expense"
                
                tax_year = get_tax_year_from_date(tx_date)
                
                transaction = Transaction(
                    date=tx_date,
                    description=tx_desc,
                    amount=tx_amount,
                    transaction_type=transaction_type,
                    tax_year=tax_year,
                    source="bank_statement",
                    bank_statement_id=statement_id,
                    excluded_from_totals=excluded
                )
                
                doc = transaction.model_dump()
                duplicate = await thread_db.transactions.find_one({
                    "date": doc["date"],
                    "description": doc["description"],
                    "amount": doc["amount"],
                })
                if duplicate:
                    continue
                await thread_db.transactions.insert_one(doc)
                created_count += 1
            
            # Mark as success
            await thread_db.bank_statements.update_one(
                {"id": statement_id},
                {"$set": {
                    "processed": True,
                    "transaction_count": created_count,
                    "parse_status": "success",
                    "parse_error": None
                }}
            )
            try:
                await asyncio.to_thread(genai.delete_file, uploaded_file.name)
            except Exception:
                logger.warning("Temporary Gemini upload could not be deleted immediately")
            logger.info(f"Successfully parsed statement {statement_id}: {created_count} transactions")
            thread_client.close()
            return
            
        except json.JSONDecodeError as e:
            logger.error(f"Attempt {attempt + 1}: Failed to parse LLM response: {e}")
            if attempt == max_retries - 1:
                await thread_db.bank_statements.update_one(
                    {"id": statement_id},
                    {"$set": {"parse_status": "error", "parse_error": "Failed to parse AI response"}}
                )
        except Exception as e:
            logger.error(f"Attempt {attempt + 1}: Error parsing statement {statement_id}: {e}")
            if attempt < max_retries - 1:
                wait_time = 2 ** (attempt + 1)
                logger.info(f"Retrying in {wait_time} seconds...")
                await asyncio.sleep(wait_time)
            else:
                await thread_db.bank_statements.update_one(
                    {"id": statement_id},
                    {"$set": {"parse_status": "error", "parse_error": str(e)}}
                )
    
    thread_client.close()


@api_router.delete("/bank-statements/{statement_id}")
async def delete_bank_statement(statement_id: str):
    """Delete a bank statement and all its transactions"""
    statement = await db.bank_statements.find_one({"id": statement_id}, {"_id": 0})
    if not statement:
        raise HTTPException(status_code=404, detail="Statement not found")
    tax_years = set(await db.transactions.distinct("tax_year", {"bank_statement_id": statement_id}))
    await _assert_tax_years_open(tax_years)
    
    # Delete all transactions from this statement
    result = await db.transactions.delete_many({"bank_statement_id": statement_id})
    deleted_txns = result.deleted_count

    # Delete the statement itself
    await db.bank_statements.delete_one({"id": statement_id})
    _delete_managed_upload(statement.get("file_path"))
    
    return {"status": "deleted", "transactions_removed": deleted_txns}



@api_router.get("/bank-statements/{statement_id}/parse-status")
async def get_parse_status(statement_id: str):
    """Check the parsing status of a bank statement"""
    statement = await db.bank_statements.find_one({"id": statement_id}, {"_id": 0})
    if not statement:
        raise HTTPException(status_code=404, detail="Statement not found")
    
    return {
        "id": statement_id,
        "parse_status": statement.get("parse_status", "pending"),
        "parse_error": statement.get("parse_error"),
        "processed": statement.get("processed", False),
        "transaction_count": statement.get("transaction_count", 0)
    }


@api_router.get("/bank-statements")
async def get_bank_statements():
    statements = await db.bank_statements.find({}, {"_id": 0}).to_list(1000)
    return statements


# Summary endpoints
@api_router.get("/summary/{tax_year}")
async def get_summary(tax_year: str):
    """Return the same authoritative cash-basis figures used at tax-year close."""
    snapshot = await _tax_close_snapshot(tax_year)
    summary = snapshot["summary"]
    return {
        "tax_year": tax_year,
        "total_income": summary["turnover"],
        "bank_income": summary["bank_income"],
        "invoice_income": summary["other_cash_income"],
        "total_expenses": summary["allowable_expenses"],
        "manual_expenses": round(summary["manual_expenses"] + summary["mileage"], 2),
        "bank_expenses": summary["bank_expenses"],
        "net_profit": summary["net_profit"],
        "owner_withdrawals": summary["owner_withdrawals"],
        "tax_payments": summary["tax_payments"],
        "invoice_count": snapshot["source_counts"]["invoices_reviewed"],
        "expense_count": snapshot["source_counts"]["manual_expenses"],
        "transaction_count": snapshot["source_counts"]["transactions"],
    }



@api_router.get("/dashboard-extras/{tax_year}")
async def get_dashboard_extras(tax_year: str):
    """Extra dashboard data: monthly P&L, expense categories, overdue invoices"""
    try:
        start_year = int(tax_year.split("-")[0])
    except (ValueError, IndexError):
        raise HTTPException(status_code=400, detail="Invalid tax year format")

    def parse_date(d):
        if not d:
            return None
        for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(d, fmt)
            except:
                continue
        return None

    # Monthly P&L data (Apr-Mar)
    months = []
    for m_offset in range(12):
        month = ((4 + m_offset - 1) % 12) + 1
        year = start_year if month >= 4 else start_year + 1
        months.append({"year": year, "month": month})

    snapshot = await _tax_close_snapshot(tax_year)
    income_rows = [row for row in snapshot["income_ledger"] if row.get("included")]
    expense_rows = [row for row in snapshot["expense_ledger"] if row.get("included")]
    mileage_entries = snapshot["mileage_ledger"]

    month_labels = ["Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar"]
    monthly_data = []
    for i, m in enumerate(months):
        m_income = 0
        m_expenses = 0
        for row in income_rows:
            dt = parse_date(row.get("date", ""))
            if dt and dt.month == m["month"] and dt.year == m["year"]:
                m_income += row.get("amount", 0)
        for row in expense_rows:
            dt = parse_date(row.get("date", ""))
            if dt and dt.month == m["month"] and dt.year == m["year"]:
                m_expenses += row.get("amount", 0)
        for ml in mileage_entries:
            dt = parse_date(ml.get("date", ""))
            if dt and dt.month == m["month"] and dt.year == m["year"]:
                m_expenses += ml.get("amount", 0)
        monthly_data.append({
            "month": month_labels[i],
            "income": round(m_income, 2),
            "expenses": round(m_expenses, 2),
            "profit": round(m_income - m_expenses, 2)
        })

    # Expense category breakdown
    categories = [
        {"name": item["category"], "value": item["amount"]}
        for item in snapshot["category_summary"]
    ]

    # Overdue invoices
    all_invoices = await db.invoices.find({}, {"_id": 0}).to_list(10000)
    today = datetime.now()
    overdue = []
    for inv in all_invoices:
        balance = _invoice_outstanding_balance(inv)
        if balance <= 0.009:
            continue
        due_date = parse_date(inv.get("final_payment_due", ""))
        if due_date and due_date < today:
            overdue.append({
                "id": inv.get("id"),
                "invoice_number": inv.get("invoice_number"),
                "couple_names": inv.get("couple_names"),
                "total_price": inv.get("total_price", 0),
                "balance": balance,
                "due_date": inv.get("final_payment_due"),
                "days_overdue": (today - due_date).days
            })
    overdue.sort(key=lambda x: -x["days_overdue"])

    return {
        "monthly": monthly_data,
        "categories": categories,
        "overdue": overdue
    }



# Mileage endpoints
@api_router.get("/mileage")
async def get_mileage(tax_year: str = None):
    query = {"tax_year": tax_year} if tax_year else {}
    entries = await db.mileage.find(query, {"_id": 0}).to_list(10000)
    # Calculate totals
    total_miles = sum(e.get("miles", 0) for e in entries)
    total_amount = sum(e.get("amount", 0) for e in entries)
    return {"entries": entries, "total_miles": round(total_miles, 1), "total_amount": round(total_amount, 2)}

@api_router.post("/mileage")
async def create_mileage(entry: dict):
    miles = float(entry.get("miles", 0))
    tax_year = entry.get("tax_year", "")
    await _assert_tax_year_open(tax_year)
    existing = await db.mileage.find({"tax_year": tax_year}, {"_id": 0}).to_list(10000)
    total_existing = sum(e.get("miles", 0) for e in existing)

    # HMRC rates: 55p from 2026-27 onwards, 45p before
    try:
        ty_start = int(tax_year.split("-")[0])
    except:
        ty_start = 0
    high_rate = 0.55 if ty_start >= 2026 else 0.45

    if total_existing + miles <= 10000:
        rate = high_rate
        amount = round(miles * high_rate, 2)
    elif total_existing >= 10000:
        rate = 0.25
        amount = round(miles * 0.25, 2)
    else:
        miles_at_high = 10000 - total_existing
        miles_at_low = miles - miles_at_high
        rate = high_rate
        amount = round(miles_at_high * high_rate + miles_at_low * 0.25, 2)

    mileage_data = {
        "id": str(uuid.uuid4()),
        "date": entry.get("date", ""),
        "description": entry.get("description", ""),
        "from_location": entry.get("from_location", ""),
        "to_location": entry.get("to_location", ""),
        "miles": miles,
        "rate": rate,
        "amount": amount,
        "tax_year": tax_year,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.mileage.insert_one(mileage_data)
    mileage_data.pop("_id", None)
    return mileage_data

@api_router.delete("/mileage/{entry_id}")
async def delete_mileage(entry_id: str):
    entry = await db.mileage.find_one({"id": entry_id}, {"_id": 0})
    if not entry:
        raise HTTPException(status_code=404, detail="Mileage entry not found")
    await _assert_tax_year_open(entry.get("tax_year"))
    await db.mileage.delete_one({"id": entry_id})
    return {"status": "deleted"}


@api_router.post("/mileage/recalculate/{tax_year}")
async def recalculate_mileage(tax_year: str):
    """Recalculate all mileage amounts for a tax year using the correct HMRC rate"""
    await _assert_tax_year_open(tax_year)
    entries = await db.mileage.find({"tax_year": tax_year}, {"_id": 0}).to_list(10000)
    if not entries:
        return {"recalculated": 0}

    try:
        ty_start = int(tax_year.split("-")[0])
    except:
        ty_start = 0
    high_rate = 0.55 if ty_start >= 2026 else 0.45

    # Sort by date to apply cumulative miles correctly
    entries.sort(key=lambda e: e.get("date", ""))
    cumulative = 0
    results = []
    for e in entries:
        miles = e.get("miles", 0)
        if cumulative + miles <= 10000:
            rate = high_rate
            amount = round(miles * high_rate, 2)
        elif cumulative >= 10000:
            rate = 0.25
            amount = round(miles * 0.25, 2)
        else:
            miles_at_high = 10000 - cumulative
            miles_at_low = miles - miles_at_high
            rate = high_rate
            amount = round(miles_at_high * high_rate + miles_at_low * 0.25, 2)
        cumulative += miles
        await db.mileage.update_one({"id": e["id"]}, {"$set": {"rate": rate, "amount": amount}})
        results.append({"id": e["id"], "miles": miles, "old_amount": e.get("amount", 0), "new_amount": amount, "rate": rate})

    return {"recalculated": len(results), "rate": high_rate, "entries": results}


# Recurring expense template endpoints
@api_router.get("/recurring-expenses")
async def get_recurring_templates():
    templates = await db.recurring_expenses.find({}, {"_id": 0}).to_list(10000)
    return templates

@api_router.post("/recurring-expenses")
async def create_recurring_template(template: dict):
    data = {
        "id": str(uuid.uuid4()),
        "description": template.get("description", ""),
        "amount": float(template.get("amount", 0)),
        "category": template.get("category", "Other"),
        "supplier": template.get("supplier"),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.recurring_expenses.insert_one(data)
    data.pop("_id", None)
    return data

@api_router.delete("/recurring-expenses/{template_id}")
async def delete_recurring_template(template_id: str):
    await db.recurring_expenses.delete_one({"id": template_id})
    return {"status": "deleted"}

@api_router.post("/recurring-expenses/{template_id}/create")
async def create_from_recurring(template_id: str, body: dict):
    template = await db.recurring_expenses.find_one({"id": template_id}, {"_id": 0})
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    date = body.get("date", datetime.now().strftime("%d/%m/%Y"))
    tax_year = body.get("tax_year", get_tax_year_from_date(date))
    await _assert_tax_year_open(tax_year)
    expense_data = {
        "id": str(uuid.uuid4()),
        "description": template["description"],
        "amount": template["amount"],
        "category": template["category"],
        "supplier": template.get("supplier"),
        "date": date,
        "tax_year": tax_year,
        "is_from_bank": False,
        "file_path": None,
        "file_name": None,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.expenses.insert_one(expense_data)
    expense_data.pop("_id", None)
    return expense_data


# Quick expense from transaction
@api_router.post("/transactions/{transaction_id}/to-expense")
async def transaction_to_expense(transaction_id: str, body: dict):
    tx = await db.transactions.find_one({"id": transaction_id}, {"_id": 0})
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    await _assert_tax_year_open(tx.get("tax_year"))
    category = body.get("category", "Other")
    expense_data = {
        "id": str(uuid.uuid4()),
        "description": tx.get("description", ""),
        "amount": abs(tx.get("amount", 0)),
        "category": category,
        "supplier": body.get("supplier", ""),
        "date": tx.get("date", ""),
        "tax_year": tx.get("tax_year", ""),
        "is_from_bank": True,
        "source_transaction_id": transaction_id,
        "file_path": None,
        "file_name": None,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.expenses.insert_one(expense_data)
    expense_data.pop("_id", None)
    # Mark the transaction as categorised
    await db.transactions.update_one({"id": transaction_id}, {"$set": {"category": category}})
    return expense_data


# Backup/Restore endpoints
BACKUP_COLLECTIONS = [
    "invoices",
    "expenses",
    "transactions",
    "bank_statements",
    "settings",
    "mileage",
    "recurring_expenses",
    "integration_events",
    "invoice_audit_logs",
    "tax_year_closes",
    "tax_year_close_audit",
    "cash_payment_confirmations",
    "cash_payment_audit",
    "booking_bank_matches",
    "booking_bank_match_audit",
    "migration_audits",
]
BACKUP_FILENAME_RE = re.compile(r"^weddings_by_mark_backup_\d{8}_\d{6}\.zip$")


async def _build_backup() -> tuple[str, Dict[str, int]]:
    backup_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"weddings_by_mark_backup_{backup_id}"
    backup_root = BACKUP_DIR
    temp_backup_dir = backup_root / backup_name
    backup_root.mkdir(parents=True, exist_ok=True)
    temp_backup_dir.mkdir(parents=True, exist_ok=False)

    totals: Dict[str, int] = {}
    try:
        for collection_name in BACKUP_COLLECTIONS:
            data = await db[collection_name].find({}, {"_id": 0}).to_list(100000)
            totals[collection_name] = len(data)
            with open(temp_backup_dir / f"{collection_name}.json", "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2, default=str)

        manifest = {
            "format": "weddings-by-mark-accounts-backup",
            "version": 3,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "build": BUILD_ID,
            "collections": totals,
        }
        with open(temp_backup_dir / "manifest.json", "w", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2)

        if UPLOAD_DIR.exists():
            shutil.copytree(UPLOAD_DIR, temp_backup_dir / "uploads", dirs_exist_ok=True)
        if TAX_PACK_DIR.exists():
            shutil.copytree(TAX_PACK_DIR, temp_backup_dir / "tax_year_packs", dirs_exist_ok=True)

        zip_path = backup_root / f"{backup_name}.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for backup_file in temp_backup_dir.rglob("*"):
                if backup_file.is_file():
                    archive.write(backup_file, backup_file.relative_to(temp_backup_dir))
    finally:
        shutil.rmtree(temp_backup_dir, ignore_errors=True)

    return backup_name, totals


@api_router.post("/backup")
async def create_backup():
    """Create a complete portable backup, including files and every collection."""
    try:
        backup_name, totals = await _build_backup()
        return {
            "status": "success",
            "backup_name": backup_name,
            "totals": totals,
            "download_url": f"/api/backup/download/{backup_name}.zip"
        }
        
    except Exception as e:
        logger.error(f"Backup failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.get("/backup/download/{filename}")
async def download_backup(filename: str):
    """Download a backup file"""
    if not BACKUP_FILENAME_RE.fullmatch(filename):
        raise HTTPException(status_code=400, detail="Invalid backup filename")
    backup_root = BACKUP_DIR.resolve()
    file_path = (backup_root / filename).resolve()
    if file_path.parent != backup_root:
        raise HTTPException(status_code=400, detail="Invalid backup filename")
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Backup file not found")
    return FileResponse(file_path, filename=filename, media_type="application/zip")


@api_router.post("/restore")
async def restore_backup(file: UploadFile = File(...)):
    """Safely restore a complete backup after first taking a rollback backup."""
    restore_root = RESTORE_DIR
    restore_id = str(uuid.uuid4())
    work_root = restore_root / restore_id
    temp_zip = work_root / "restore.zip"
    extract_dir = work_root / "extracted"
    try:
        work_root.mkdir(parents=True, exist_ok=False)
        size = 0
        with open(temp_zip, "wb") as handle:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_RESTORE_MB * 1024 * 1024:
                    raise HTTPException(status_code=413, detail=f"Backup exceeds {MAX_RESTORE_MB} MB")
                handle.write(chunk)

        if not zipfile.is_zipfile(temp_zip):
            raise HTTPException(status_code=400, detail="The selected file is not a valid backup ZIP")

        extract_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(temp_zip, "r") as archive:
            base = extract_dir.resolve()
            for member in archive.infolist():
                target = (base / member.filename).resolve()
                if target != base and base not in target.parents:
                    raise HTTPException(status_code=400, detail="Unsafe path found in backup")
            archive.extractall(extract_dir)

        # A valid v2 backup has a manifest. Legacy backups are still accepted
        # when they contain at least one known collection.
        manifest_path = extract_dir / "manifest.json"
        present_collections = [name for name in BACKUP_COLLECTIONS if (extract_dir / f"{name}.json").exists()]
        if not manifest_path.exists() and not present_collections:
            raise HTTPException(status_code=400, detail="This ZIP does not contain an accounts backup")

        restore_payloads: Dict[str, List[Dict[str, Any]]] = {}
        for collection_name in BACKUP_COLLECTIONS:
            json_file = extract_dir / f"{collection_name}.json"
            if json_file.exists():
                with open(json_file, "r", encoding="utf-8") as handle:
                    data = json.load(handle)
                if not isinstance(data, list):
                    raise HTTPException(status_code=400, detail=f"Invalid {collection_name}.json")
                if any(not isinstance(item, dict) for item in data):
                    raise HTTPException(status_code=400, detail=f"Invalid record in {collection_name}.json")
                restore_payloads[collection_name] = data

        # Only mutate the database after every JSON file has been validated and
        # a complete automatic rollback backup exists.
        rollback_backup_name, _ = await _build_backup()
        restored_counts: Dict[str, int] = {}
        for collection_name, data in restore_payloads.items():
            await db[collection_name].delete_many({})
            if data:
                await db[collection_name].insert_many(data)
            restored_counts[collection_name] = len(data)

        uploads_dir = extract_dir / "uploads"
        if uploads_dir.exists():
            shutil.copytree(uploads_dir, UPLOAD_DIR, dirs_exist_ok=True)
        tax_packs_dir = extract_dir / "tax_year_packs"
        if tax_packs_dir.exists():
            shutil.copytree(tax_packs_dir, TAX_PACK_DIR, dirs_exist_ok=True)

        return {
            "status": "success",
            "restored_counts": restored_counts,
            "rollback_backup": rollback_backup_name,
            "message": "Data restored successfully",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Restore failed: {e}")
        raise HTTPException(status_code=500, detail="Restore failed. Use the automatic rollback backup if any collection had already changed.")
    finally:
        shutil.rmtree(work_root, ignore_errors=True)


# Include the router
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=[origin.strip() for origin in os.environ.get("CORS_ORIGINS", APP_URL).split(",") if origin.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=[host.strip() for host in os.environ.get(
        "ALLOWED_HOSTS", "accounts2026.weddingsbymark.uk,192.168.24.10,localhost,127.0.0.1"
    ).split(",") if host.strip()],
)

# Add the signed, HttpOnly session cookie last so it wraps the authentication
# middleware and request.session is always available.
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET or secrets.token_urlsafe(48),
    session_cookie="wbm_accounts_session",
    max_age=SESSION_HOURS * 60 * 60,
    same_site="strict",
    https_only=COOKIE_SECURE,
)

# Serve frontend static files (if available)
STATIC_DIR = ROOT_DIR / "static_frontend"
if STATIC_DIR.exists():
    # Serve static assets (JS, CSS, etc.)
    static_assets = STATIC_DIR / "static"
    if static_assets.exists():
        app.mount("/static", StaticFiles(directory=str(static_assets)), name="static")
    
    # Catch-all: serve index.html for any non-API route (SPA support)
    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        # If it's a file that exists, serve it
        file_path = STATIC_DIR / full_path
        if full_path and file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path))
        # Otherwise serve index.html for SPA routing
        index_path = STATIC_DIR / "index.html"
        if index_path.exists():
            return HTMLResponse(index_path.read_text())
        return HTMLResponse("<h1>Frontend not found</h1>", status_code=404)


@app.on_event("startup")
async def startup_checks():
    if APP_ENV == "production":
        if len(SESSION_SECRET) < 32:
            raise RuntimeError("SESSION_SECRET must be at least 32 characters in production")
        if not ADMIN_PASSWORD and not os.environ.get("ADMIN_PASSWORD_HASH"):
            raise RuntimeError("ADMIN_PASSWORD or ADMIN_PASSWORD_HASH is required in production")
        if "*" in os.environ.get("CORS_ORIGINS", ""):
            raise RuntimeError("Wildcard CORS is not permitted in production")
    if INTEGRATION_ENABLED and len(INTEGRATION_KEY) < 32:
        raise RuntimeError("BOOKING_INTEGRATION_KEY must be at least 32 characters when enabled")

    await db.invoices.create_index(
        [("source_system", 1), ("source_invoice_id", 1)],
        unique=True,
        partialFilterExpression={
            "source_system": {"$type": "string"},
            "source_invoice_id": {"$type": "string"},
        },
        name="unique_booking_source_invoice",
    )
    await db.invoices.create_index(
        [("source_system", 1), ("source_invoice_number", 1)],
        unique=True,
        partialFilterExpression={
            "source_system": "manual_pdf_import",
            "source_invoice_number": {"$type": "string"},
        },
        name="unique_manual_booking_invoice_number",
    )
    await db.invoices.create_index(
        [("source_system", 1), ("source_pdf_sha256", 1)],
        unique=True,
        partialFilterExpression={
            "source_system": "manual_pdf_import",
            "source_pdf_sha256": {"$type": "string"},
        },
        name="unique_manual_booking_invoice_pdf",
    )
    await db.integration_events.create_index("event_id", unique=True, name="unique_integration_event")
    await db.invoice_audit_logs.create_index(
        [("invoice_id", 1), ("created_at", -1)],
        name="invoice_audit_history",
    )
    await db.tax_year_closes.create_index("tax_year", unique=True, name="unique_tax_year_close")
    await db.tax_year_close_audit.create_index(
        [("tax_year", 1), ("created_at", -1)],
        name="tax_year_close_history",
    )
    await db.cash_payment_confirmations.create_index(
        [("tax_year", 1), ("source_invoice_id", 1), ("source_payment_id", 1)],
        unique=True,
        name="unique_cash_payment_confirmation",
    )
    await db.cash_payment_audit.create_index(
        [("tax_year", 1), ("created_at", -1)],
        name="cash_payment_audit_history",
    )
    await db.booking_bank_matches.create_index(
        [("tax_year", 1), ("bank_transaction_id", 1)],
        name="combined_bank_match_lookup",
    )
    await db.booking_bank_match_audit.create_index(
        [("tax_year", 1), ("created_at", -1)],
        name="combined_bank_match_audit_history",
    )


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
