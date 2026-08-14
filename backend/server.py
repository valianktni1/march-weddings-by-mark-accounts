from fastapi import FastAPI, APIRouter, UploadFile, File, HTTPException, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
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
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import Any, Dict, List, Optional
import uuid
from datetime import datetime, timezone, timedelta
from bson import ObjectId

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
BUILD_ID = "2026.08.14-secure-foundation-v1"

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

# Uploads directory
UPLOAD_DIR = ROOT_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

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
    file_path: Optional[str] = None
    file_name: Optional[str] = None
    include_in_totals: bool = False
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class InvoiceCreate(BaseModel):
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
    package_name: Optional[str] = None
    notes: Optional[str] = None
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


class BookingInvoiceSync(BaseModel):
    """Stable, versioned contract used by the booking system only."""

    event_id: str = Field(min_length=8, max_length=160)
    source_invoice_id: str = Field(min_length=1, max_length=160)
    invoice_number: str = Field(min_length=1, max_length=40)
    couple_names: str = Field(default="", max_length=300)
    client_address: Optional[str] = Field(default=None, max_length=1000)
    client_email: Optional[str] = Field(default=None, max_length=320)
    client_phone: Optional[str] = Field(default=None, max_length=80)
    wedding_date: Optional[str] = None
    venue: Optional[str] = Field(default=None, max_length=500)
    package_name: Optional[str] = Field(default=None, max_length=500)
    description: Optional[str] = Field(default=None, max_length=10000)
    total_price: float = 0
    due_date: Optional[str] = None
    status: str = Field(default="Pending", max_length=80)
    payments: List[BookingPaymentSync] = Field(default_factory=list)
    void_reason: Optional[str] = Field(default=None, max_length=2000)
    updated_at: Optional[str] = None


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
    temp_path = ROOT_DIR / "temp_backup" / f"tax_return_{tax_year}.csv"
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
    temp_path = ROOT_DIR / "temp_backup" / f"tax_return_{tax_year}_{quarter}.csv"
    temp_path.parent.mkdir(parents=True, exist_ok=True)
    with open(temp_path, "w") as f:
        f.write(csv_content)
    
    return FileResponse(str(temp_path), media_type="text/csv", filename=f"weddings_by_mark_{tax_year}_{quarter}.csv")





# Invoice endpoints

@api_router.post("/invoices/scan-pdf")
async def scan_invoice_pdf(file: UploadFile = File(...)):
    """Extract invoice/booking data from a PDF using pymupdf — zero credits, fully local"""
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
        raise HTTPException(status_code=400, detail="Could not extract text from PDF. This may be a scanned image.")

    result = {
        "couple_names": "",
        "total_price": 0,
        "deposit_amount": 0,
        "venue": "",
        "wedding_date": "",
        "package_name": "",
        "notes": "",
        "client_address": "",
        "client_email": "",
        "client_phone": "",
        "raw_text": text[:800],
    }

    lines = [l.strip() for l in text.split("\n") if l.strip()]

    months_map = {"jan": "01", "feb": "02", "mar": "03", "apr": "04", "may": "05", "jun": "06",
                  "jul": "07", "aug": "08", "sep": "09", "oct": "10", "nov": "11", "dec": "12"}

    # --- Couple Names: first line after "INVOICE FOR" that isn't metadata ---
    for i, line in enumerate(lines):
        if re.match(r'INVOICE\s*FOR', line, re.IGNORECASE):
            for j in range(i + 1, min(i + 3, len(lines))):
                c = lines[j].strip()
                if c and not c.lower().startswith(("phone", "email", "invoice id", "issue date", "from")) and "@" not in c and not c.startswith("£"):
                    result["couple_names"] = c
                    break
            break

    # --- Phone & Email ---
    # pymupdf interleaves columns: CLIENT info appears FIRST, BUSINESS info SECOND
    phones = re.findall(r'Phone\s*number:\s*([\d\s]+)', text, re.IGNORECASE)
    emails = re.findall(r'Email:\s*([\w.+-]+@[\w-]+\.[\w.-]+)', text, re.IGNORECASE)

    # First phone/email = client, filter out business ones
    for p in phones:
        p = p.strip()
        if "07712117357" not in p:
            result["client_phone"] = p
            break
    for e in emails:
        if "markpowell" not in e.lower() and "googlemail" not in e.lower() and "weddingsbymark" not in e.lower():
            result["client_email"] = e.strip()
            break

    # --- Client Address: lines between client email and FROM/business markers ---
    addr_parts = []
    collecting = False
    for i, line in enumerate(lines):
        if result["client_email"] and result["client_email"] in line:
            collecting = True
            continue
        if collecting:
            if line in ("FROM", "Weddings By Mark") or line.lower().startswith("phone number: 07712") or "Enquiry Form" in line:
                continue
            if re.match(r'(Wedding|Product|Package|Description|Subtotal|Total|NOTES|Status|Business Number)', line, re.IGNORECASE):
                break
            if line.startswith("£") or line == "Invoice" or "M22 5AX" in line or "Ashurst" in line or "Kingdom" in line or "manchester" in line.lower():
                continue
            if "Stacey" in line or (result["couple_names"] and result["couple_names"] in line):
                continue
            addr_parts.append(line)
    if addr_parts:
        result["client_address"] = re.sub(r',\s*,', ',', ", ".join(addr_parts)).strip(', ')

    # --- Wedding Date: find "DD Mon YYYY" date pattern near "Wedding" line ---
    for i, line in enumerate(lines):
        if line.strip() == "Wedding":
            # Search nearby lines (interleaved columns may put other lines between)
            for j in range(i + 1, min(i + 4, len(lines))):
                match = re.match(r'^(\d{1,2})\s+(\w{3,9})\s+(\d{4})$', lines[j].strip())
                if match:
                    day = match.group(1).zfill(2)
                    mon = months_map.get(match.group(2).lower()[:3], "01")
                    year = match.group(3)
                    result["wedding_date"] = f"{day}/{mon}/{year}"
                    break
            break
    # Fallback: "Wedding Date: DD/MM/YYYY"
    if not result["wedding_date"]:
        wd = re.search(r'Wedding\s*Date[:\s]*(\d{1,2}[/\-]\d{1,2}[/\-]\d{4})', text, re.IGNORECASE)
        if wd:
            result["wedding_date"] = wd.group(1).replace("-", "/")

    # --- Venue: look for a line with hotel/hall/barn/castle type keywords ---
    venue_keywords = r'\b(Hotel|Hall|Barn|Castle|Manor|House|Farm|Lodge|Estate|Centre|Club|Gardens|Church|Chapel|Registry)\b'
    for line in lines:
        if re.search(venue_keywords, line, re.IGNORECASE) and "Ashurst" not in line and "MANCHESTER" not in line:
            v = line.strip().rstrip(',')
            # Check next line for continuation (e.g., "UK")
            idx = lines.index(line)
            if idx + 1 < len(lines):
                nxt = lines[idx + 1].strip()
                if nxt in ("UK", "United Kingdom", "England") or (len(nxt) < 15 and not re.match(r'(Product|Package|Description|Ashurst)', nxt)):
                    v = v + ", " + nxt
            result["venue"] = v
            break
    # Fallback: "Venue:" label
    if not result["venue"]:
        vm = re.search(r'Venue[:\s]+(.+?)(?:\n|$)', text, re.IGNORECASE)
        if vm:
            result["venue"] = vm.group(1).strip()

    # --- Total Price ---
    total_match = re.search(r'\bTotal\b\s*\n?\s*£([\d,]+\.?\d*)', text)
    if total_match:
        result["total_price"] = float(total_match.group(1).replace(",", ""))

    # --- Deposit: look for deposit keyword or first substantial payment ---
    dep_match = re.search(r'(?:Deposit|Booking\s*Fee|Retainer)\s*[:\s]*£?([\d,]+\.?\d*)', text, re.IGNORECASE)
    if dep_match:
        val = float(dep_match.group(1).replace(",", ""))
        if 0 < val < result.get("total_price", 99999):
            result["deposit_amount"] = val

    # --- Package Name: first content line after header row in Product/Package section ---
    for i, line in enumerate(lines):
        if line == "Amount" and i > 0:
            # Check if this is in the Product/Package section
            nearby = " ".join(lines[max(0, i-4):i])
            if "Product" in nearby or "Package" in nearby:
                for j in range(i + 1, min(i + 3, len(lines))):
                    ln = lines[j].strip()
                    if ln and not ln.startswith("£") and ln not in ("Description", "Unit Price", "Quantity"):
                        result["package_name"] = ln
                        break
                break

    return result


async def get_next_invoice_number():
    """Get next auto-incrementing invoice number starting from WBM01101"""
    invoices = await db.invoices.find({"invoice_number": {"$regex": "^WBM"}}, {"invoice_number": 1, "_id": 0}).to_list(10000)
    max_num = 1100
    for inv in invoices:
        num_str = inv.get("invoice_number", "").replace("WBM", "")
        try:
            num = int(num_str)
            if num > max_num:
                max_num = num
        except (ValueError, TypeError):
            pass
    return f"WBM{max_num + 1:05d}"


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

    # Logo
    logo_path = Path(__file__).parent / "logo.png"
    if logo_path.exists():
        logo = Image(str(logo_path), width=60*mm, height=60*mm)
        logo.hAlign = "LEFT"
        elements.append(logo)
        elements.append(Spacer(1, 4*mm))
    else:
        title_style = ParagraphStyle("Title", parent=styles["Title"], fontSize=22, textColor=brand_color, spaceAfter=2)
        subtitle_style = ParagraphStyle("Subtitle", parent=styles["Normal"], fontSize=9, textColor=grey, spaceAfter=12)
        elements.append(Paragraph("Weddings By Mark", title_style))
        elements.append(Paragraph("Professional Wedding Photographers", subtitle_style))

    # Invoice info row
    inv_num = invoice_data.get("invoice_number", "")
    issue_date = invoice_data.get("created_at", "")[:10] if invoice_data.get("created_at") else ""
    try:
        from datetime import datetime as dt_mod
        d = dt_mod.fromisoformat(issue_date)
        issue_date = d.strftime("%d %b %Y")
    except:
        pass

    info_data = [
        [Paragraph(f"<b>Invoice:</b> {inv_num}", normal_style), Paragraph(f"<b>Issue Date:</b> {issue_date}", right_style)],
    ]
    info_table = Table(info_data, colWidths=[270, 270])
    info_table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    elements.append(info_table)
    elements.append(Spacer(1, 6*mm))

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
    elements.append(Spacer(1, 6*mm))

    # Package / Line items
    elements.append(Paragraph("Package Details", heading_style))
    pkg_name = invoice_data.get("package_name") or "Wedding Photography Package"
    notes = invoice_data.get("notes") or ""
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
    elements.append(Spacer(1, 8*mm))

    # Payment schedule
    elements.append(Paragraph("Payment Schedule", heading_style))
    deposit = invoice_data.get("deposit_amount", 0)
    interim = invoice_data.get("interim_payment", 0)
    balance = total - deposit - interim
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
        [Paragraph("Deposit", normal_style), Paragraph(f"£{deposit:,.2f}", right_style), Paragraph(dep_status, center_style), Paragraph(dep_date, center_style)],
    ]
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

    # Balance due
    if balance > 0 and bal_status == "Unpaid":
        elements.append(Spacer(1, 4*mm))
        bal_data = [["", Paragraph(f"<b>Balance Due: £{balance:,.2f}</b>", ParagraphStyle("bd", parent=right_style, fontSize=12, textColor=brand_color))]]
        bal_table = Table(bal_data, colWidths=[340, 200])
        elements.append(bal_table)

    # Footer
    elements.append(Spacer(1, 10*mm))
    elements.append(Paragraph("Pay by Bank Transfer", ParagraphStyle("ft", parent=normal_style, fontName="Helvetica-Bold", textColor=brand_color)))
    elements.append(Spacer(1, 4*mm))
    elements.append(Paragraph("Thank you for choosing Weddings By Mark as your Photographer for the big day.", small_style))

    doc.build(elements)


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
    final_due = calc_final_payment_due(invoice.wedding_date)
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

    invoice_data = {
        "id": str(uuid.uuid4()),
        "invoice_number": inv_num,
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
    return invoices


@api_router.put("/invoices/{invoice_id}")
async def update_invoice(invoice_id: str, body: dict):
    """Update invoice — recalculates tax years, status, balance, and regenerates PDF"""
    existing = await db.invoices.find_one({"id": invoice_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Invoice not found")

    # Merge updates
    for key in ["couple_names", "client_address", "client_email", "client_phone",
                 "wedding_date", "venue", "total_price", "deposit_amount",
                 "deposit_paid_date", "interim_payment", "interim_payment_date",
                 "final_payment_paid_date", "package_name", "notes", "include_in_totals"]:
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
    final_due = calc_final_payment_due(wedding_date) if wedding_date else existing.get("final_payment_due")

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
        "include_in_totals": existing.get("include_in_totals", False),
    }

    await db.invoices.update_one({"id": invoice_id}, {"$set": updates})

    # Regenerate PDF if invoice has a number
    inv_num = existing.get("invoice_number")
    if inv_num:
        merged = {**existing, **updates}
        pdf_dir = UPLOAD_DIR / "invoices"
        pdf_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = pdf_dir / f"{inv_num}.pdf"
        generate_invoice_pdf(merged, str(pdf_path))
        await db.invoices.update_one({"id": invoice_id}, {"$set": {"file_path": str(pdf_path), "file_name": f"{inv_num}.pdf"}})

    updated = await db.invoices.find_one({"id": invoice_id}, {"_id": 0})
    return updated


@api_router.get("/invoices/{invoice_id}/pdf")
async def get_invoice_pdf(invoice_id: str):
    invoice = await db.invoices.find_one({"id": invoice_id}, {"_id": 0})
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    file_path = invoice.get("file_path")
    if not file_path or not Path(file_path).exists():
        raise HTTPException(status_code=404, detail="PDF not found")
    return FileResponse(str(file_path), media_type="application/pdf", filename=invoice.get("file_name", "invoice.pdf"))


@api_router.delete("/invoices/{invoice_id}")
async def delete_invoice(invoice_id: str):
    result = await db.invoices.delete_one({"id": invoice_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return {"status": "deleted"}


@api_router.post("/invoices/migrate-numbers")
async def migrate_invoice_numbers():
    """One-time migration: re-number all invoices chronologically by deposit date, starting from WBM01101"""
    import random
    invoices = await db.invoices.find({}, {"_id": 0}).to_list(10000)
    
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
    return {"status": "ready", "enabled": True, "version": 1}


@api_router.post("/integrations/booking/invoices/sync")
async def sync_booking_invoice(payload: BookingInvoiceSync):
    """Idempotently mirror one booking-system invoice into accounts.

    This route never sends email, creates a client portal or changes the
    booking system. Imported invoices are tracking records and are excluded
    from income totals by default to avoid double-counting bank credits.
    """

    processed = await db.integration_events.find_one({"event_id": payload.event_id}, {"_id": 0})
    if processed:
        current = await db.invoices.find_one(
            {"source_system": "booking_system", "source_invoice_id": payload.source_invoice_id},
            {"_id": 0},
        )
        return {"status": "already_processed", "invoice": current}

    payments = [item.model_dump() for item in payload.payments]
    payments.sort(key=lambda item: (item.get("paid_date") or "", item.get("id") or ""))
    total_paid = round(sum(max(0, float(item.get("amount", 0))) for item in payments), 2)
    total_price = round(max(0, payload.total_price), 2)
    balance = round(max(0, total_price - total_paid), 2)
    first_payment = payments[0] if payments else None
    remaining_payments = payments[1:] if len(payments) > 1 else []
    interim_total = round(sum(float(item.get("amount", 0)) for item in remaining_payments), 2)
    paid_in_full = balance <= 0.009 and total_price > 0
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
        "couple_names": payload.couple_names,
        "client_address": payload.client_address,
        "client_email": payload.client_email,
        "client_phone": payload.client_phone,
        "wedding_date": wedding_date,
        "venue": payload.venue,
        "package_name": payload.package_name,
        "notes": payload.description,
        "total_price": total_price,
        "deposit_amount": round(float(first_payment.get("amount", 0)), 2) if first_payment else 0,
        "deposit_paid_date": format_date_uk(first_payment.get("paid_date")) if first_payment else None,
        "deposit_tax_year": calc_tax_year_from_date(format_date_uk(first_payment.get("paid_date"))) if first_payment else None,
        "interim_payment": interim_total,
        "interim_payment_date": format_date_uk(remaining_payments[-1].get("paid_date")) if remaining_payments else None,
        "interim_tax_year": calc_tax_year_from_date(format_date_uk(remaining_payments[-1].get("paid_date"))) if remaining_payments else None,
        "final_payment_due": due_date,
        "final_payment_paid_date": format_date_uk(payments[-1].get("paid_date")) if paid_in_full and payments else None,
        "final_tax_year": calc_tax_year_from_date(format_date_uk(payments[-1].get("paid_date"))) if paid_in_full and payments else (calc_tax_year_from_date(due_date) if due_date else None),
        "balance_remaining": balance,
        "amount_paid": total_paid,
        "payments": payments,
        "status": payload.status,
        "void_reason": payload.void_reason,
        "tax_year": calc_tax_year_from_date(format_date_uk(first_payment.get("paid_date"))) if first_payment else (calc_tax_year_from_date(wedding_date) if wedding_date else ""),
        "include_in_totals": False,
        "source_system": "booking_system",
        "source_invoice_id": payload.source_invoice_id,
        "source_updated_at": payload.updated_at,
        "updated_at": now_iso,
        "created_at": existing.get("created_at", now_iso) if existing else now_iso,
    }

    safe_number = re.sub(r"[^A-Za-z0-9_.-]", "_", payload.invoice_number)
    pdf_dir = UPLOAD_DIR / "invoices"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = pdf_dir / f"{safe_number}.pdf"
    generate_invoice_pdf(invoice_data, str(pdf_path))
    invoice_data["file_path"] = str(pdf_path)
    invoice_data["file_name"] = f"{safe_number}.pdf"

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
    invoice_data.pop("_id", None)
    return {"status": "synchronised", "invoice": invoice_data}


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
    result = await db.expenses.delete_one({"id": expense_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Expense not found")
    return {"status": "deleted"}


# Transaction endpoints
@api_router.get("/transactions")
async def get_transactions(tax_year: Optional[str] = None):
    query = {}
    if tax_year:
        query["tax_year"] = tax_year
    transactions = await db.transactions.find(query, {"_id": 0}).to_list(10000)
    return transactions


# Bank Statement endpoints
@api_router.delete("/bank-statements/all")
async def delete_all_bank_data():
    """Delete all bank statements and their associated transactions"""
    tx_result = await db.transactions.delete_many({"source": "bank_statement"})
    bs_result = await db.bank_statements.delete_many({})
    return {
        "status": "deleted",
        "transactions_deleted": tx_result.deleted_count,
        "statements_deleted": bs_result.deleted_count
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
    
    # Delete all transactions from this statement
    result = await db.transactions.delete_many({"bank_statement_id": statement_id})
    deleted_txns = result.deleted_count
    
    # Delete the statement itself
    await db.bank_statements.delete_one({"id": statement_id})
    
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
    """Get financial summary for a tax year — invoices are tracking only, not income"""
    
    # Get expenses
    expenses = await db.expenses.find({"tax_year": tax_year}, {"_id": 0}).to_list(10000)
    total_expenses = sum(exp.get("amount", 0) for exp in expenses)
    
    # Get mileage claims
    mileage_entries = await db.mileage.find({"tax_year": tax_year}, {"_id": 0}).to_list(10000)
    mileage_total = sum(e.get("amount", 0) for e in mileage_entries)
    total_expenses += mileage_total
    
    # Get bank transactions (excluding owner withdrawals)
    transactions = await db.transactions.find({
        "tax_year": tax_year,
        "excluded_from_totals": False
    }, {"_id": 0}).to_list(10000)
    
    bank_income = sum(tx.get("amount", 0) for tx in transactions if tx.get("transaction_type") == "income")
    bank_expenses = sum(tx.get("amount", 0) for tx in transactions if tx.get("transaction_type") == "expense")
    
    # Get excluded transactions
    excluded_transactions = await db.transactions.find({
        "tax_year": tax_year,
        "excluded_from_totals": True
    }, {"_id": 0}).to_list(10000)
    
    owner_withdrawals = sum(tx.get("amount", 0) for tx in excluded_transactions if tx.get("transaction_type") == "owner_withdrawal")
    tax_payments = sum(tx.get("amount", 0) for tx in excluded_transactions if tx.get("transaction_type") == "tax_payment")
    
    # Invoices are for tracking only — unless include_in_totals is set
    invoices = await db.invoices.find({"tax_year": tax_year}, {"_id": 0}).to_list(10000)
    
    # Sum income from invoices marked as "add to income"
    invoice_income = 0
    for inv in invoices:
        if inv.get("include_in_totals"):
            invoice_income += inv.get("total_price", 0)
    
    total_income = bank_income + invoice_income
    net_profit = total_income - (total_expenses + bank_expenses)
    
    return {
        "tax_year": tax_year,
        "total_income": total_income,
        "bank_income": bank_income,
        "invoice_income": invoice_income,
        "total_expenses": total_expenses + bank_expenses,
        "manual_expenses": total_expenses,
        "bank_expenses": bank_expenses,
        "net_profit": net_profit,
        "owner_withdrawals": owner_withdrawals,
        "tax_payments": tax_payments,
        "invoice_count": len(invoices),
        "expense_count": len(expenses),
        "transaction_count": len(transactions)
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

    transactions = await db.transactions.find({"tax_year": tax_year, "excluded_from_totals": False}, {"_id": 0}).to_list(10000)
    expenses = await db.expenses.find({"tax_year": tax_year}, {"_id": 0}).to_list(10000)
    invoices_income = await db.invoices.find({"tax_year": tax_year, "include_in_totals": True}, {"_id": 0}).to_list(10000)
    mileage_entries = await db.mileage.find({"tax_year": tax_year}, {"_id": 0}).to_list(10000)

    month_labels = ["Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar"]
    monthly_data = []
    for i, m in enumerate(months):
        m_income = 0
        m_expenses = 0
        for tx in transactions:
            dt = parse_date(tx.get("date", ""))
            if dt and dt.month == m["month"] and dt.year == m["year"]:
                if tx.get("transaction_type") == "income":
                    m_income += tx.get("amount", 0)
                elif tx.get("transaction_type") == "expense":
                    m_expenses += tx.get("amount", 0)
        for exp in expenses:
            dt = parse_date(exp.get("date", ""))
            if dt and dt.month == m["month"] and dt.year == m["year"]:
                m_expenses += exp.get("amount", 0)
        for inv in invoices_income:
            dep_dt = parse_date(inv.get("deposit_paid_date", ""))
            if dep_dt and dep_dt.month == m["month"] and dep_dt.year == m["year"]:
                m_income += inv.get("total_price", 0)
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
    category_totals = {}
    for tx in transactions:
        if tx.get("transaction_type") == "expense":
            cat = tx.get("category") or "Uncategorised"
            category_totals[cat] = category_totals.get(cat, 0) + tx.get("amount", 0)
    for exp in expenses:
        cat = exp.get("category") or "Uncategorised"
        category_totals[cat] = category_totals.get(cat, 0) + exp.get("amount", 0)
    mileage_total = sum(m.get("amount", 0) for m in mileage_entries)
    if mileage_total > 0:
        category_totals["Travel & Mileage"] = category_totals.get("Travel & Mileage", 0) + mileage_total
    categories = [{"name": k, "value": round(v, 2)} for k, v in sorted(category_totals.items(), key=lambda x: -x[1]) if v > 0]

    # Overdue invoices
    all_invoices = await db.invoices.find({}, {"_id": 0}).to_list(10000)
    today = datetime.now()
    overdue = []
    for inv in all_invoices:
        if inv.get("status") == "Paid in Full":
            continue
        due_date = parse_date(inv.get("final_payment_due", ""))
        if due_date and due_date < today:
            overdue.append({
                "id": inv.get("id"),
                "invoice_number": inv.get("invoice_number"),
                "couple_names": inv.get("couple_names"),
                "total_price": inv.get("total_price", 0),
                "balance": round((inv.get("total_price", 0) or 0) - (inv.get("deposit_amount", 0) or 0) - (inv.get("interim_payment", 0) or 0), 2),
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
    await db.mileage.delete_one({"id": entry_id})
    return {"status": "deleted"}


@api_router.post("/mileage/recalculate/{tax_year}")
async def recalculate_mileage(tax_year: str):
    """Recalculate all mileage amounts for a tax year using the correct HMRC rate"""
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
]
BACKUP_FILENAME_RE = re.compile(r"^weddings_by_mark_backup_\d{8}_\d{6}\.zip$")


async def _build_backup() -> tuple[str, Dict[str, int]]:
    backup_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"weddings_by_mark_backup_{backup_id}"
    backup_root = ROOT_DIR / "temp_backup"
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
            "version": 2,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "build": BUILD_ID,
            "collections": totals,
        }
        with open(temp_backup_dir / "manifest.json", "w", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2)

        if UPLOAD_DIR.exists():
            shutil.copytree(UPLOAD_DIR, temp_backup_dir / "uploads", dirs_exist_ok=True)

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
    backup_root = (ROOT_DIR / "temp_backup").resolve()
    file_path = (backup_root / filename).resolve()
    if file_path.parent != backup_root:
        raise HTTPException(status_code=400, detail="Invalid backup filename")
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Backup file not found")
    return FileResponse(file_path, filename=filename, media_type="application/zip")


@api_router.post("/restore")
async def restore_backup(file: UploadFile = File(...)):
    """Safely restore a complete backup after first taking a rollback backup."""
    restore_root = ROOT_DIR / "temp_restore"
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
        "ALLOWED_HOSTS", "accounts.weddingsbymark.co.uk,localhost,127.0.0.1"
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
    await db.integration_events.create_index("event_id", unique=True, name="unique_integration_event")


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
