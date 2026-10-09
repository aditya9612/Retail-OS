from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1.ai.router import router as ai_router
from app.api.v1.analytics.router import router as analytics_router
from app.api.v1.auth.router import router as auth_router
from app.api.v1.billing.router import router as billing_router

from app.api.v1.credit_notes.router import router as credit_notes_router
from app.api.v1.customers.router import router as customers_router
from app.api.v1.dashboard.router import router as dashboard_router
from app.api.v1.coupons.router import router as coupons_router
from app.api.v1.delivery.router import router as delivery_router
from app.api.v1.gst_rates.router import router as gst_rates_router
from app.api.v1.grn.router import router as grn_router
from app.api.v1.inventory.router import router as inventory_router
from app.api.v1.invoices.router import router as invoices_router
from app.api.v1.orders.router import router as orders_router
from app.api.v1.order_returns.router import router as order_returns_router
from app.api.v1.payments.router import router as payments_router
from app.api.v1.products.router import router as products_router
from app.api.v1.categories.router import router as categories_router
from app.api.v1.purchase_orders.router import router as purchase_orders_router
from app.api.v1.purchase_order_returns.router import router as purchase_order_returns_router
from app.api.v1.reviews.router import router as reviews_router
from app.api.v1.refunds.router import router as refunds_router
from app.api.v1.reports.router import router as reports_router
from app.api.v1.stores.router import router as stores_router
from app.api.v1.sales import router as sales_router
from app.api.v1.store_transfers import router as store_transfers_router
from app.api.v1.store_target import router as store_target_router
from app.api.store_expenses import router as store_expenses_router
from app.api.v1.suppliers.router import router as suppliers_router
from app.api.v1.users.router import router as users_router
from app.api.v1.roles.router import router as roles_router
from app.api.v1.warehouses.router import router as warehouses_router
from app.api.v1.whatsapp.router import router as whatsapp_router
from app.api.v1.super_admins.router import router as super_admin_router
from app.api.v1.saas_billing.router import router as saas_billing_router
from app.api.v1.saas.router import router as saas_router
from app.api.v1.multi_store.router import router as multi_store_router
from app.api.v1.document_settings.router import router as document_settings_router
from app.api.v1.pos.router import router as pos_router
from app.api.v1.variants.router import router as variants_router

from app.core.config import get_settings
from app.core.database import init_db
from app.core.logger import logger
from app.core.middleware import TenantMiddleware

from app.models import *


settings = get_settings()

# Production safety guard: Fixed OTP must be disabled in production
if settings.APP_ENV == "production" and getattr(settings, "AUTH_FIXED_OTP_ENABLED", False):
    raise RuntimeError("Fixed OTP must be disabled in production.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        init_db()
        logger.info("Database connected and tables verified")
    except Exception as exc:
        logger.error(
            "Database initialization failed: %s",
            exc,
        )
        raise

    yield


openapi_tags = [
    # --- Top: Core Operational Setup & Masters ---
    {
        "name": "auth",
        "description": "Authentication, user login, OTP verification, and JWT session tokens.",
    },
    {
        "name": "Users",
        "description": "User and employee accounts, credentials, and store assignments.",
    },
    {
        "name": "Roles",
        "description": "Role-based access control (RBAC) and permissions management.",
    },
    {
        "name": "Stores",
        "description": "Store outlets, retail branch locations, and store settings.",
    },
    {
        "name": "Store Targets",
        "description": "Store revenue and sales performance targets.",
    },
    {
        "name": "Store Transfers",
        "description": "Inter-store inventory transfer and stock allocation requests.",
    },
    {
        "name": "Store Expenses",
        "description": "Store-level daily operational expense logs and accounting.",
    },
    {
        "name": "products",
        "description": "Product catalog, SKU definitions, pricing, barcodes, and master records.",
    },
    {
        "name": "product-variants",
        "description": "Product size, color, and attribute variant matrices.",
    },
    {
        "name": "categories",
        "description": "Product categorization, hierarchy, and taxonomy.",
    },
    {
        "name": "inventory",
        "description": "Stock level tracking, adjustments, audits, and warehouse positions.",
    },
    {
        "name": "suppliers",
        "description": "Supplier directory, vendor contacts, and vendor terms.",
    },
    {
        "name": "warehouses",
        "description": "Warehouse facilities and physical inventory holding hubs.",
    },
    {
        "name": "grn",
        "description": "Goods Received Notes (GRN) for inbound supplier shipments.",
    },
    # --- Centre: Procurement, Orders, POS, Invoices & Documents ---
    {
        "name": "Purchase Orders",
        "description": "Supplier Purchase Order management, fulfillment tracking, and PO PDF exports.",
    },
    {
        "name": "purchase-order-returns",
        "description": "Purchase order return to vendor workflows.",
    },
    {
        "name": "delivery",
        "description": "Delivery tracking, dispatch schedules, and courier management.",
    },
    {
        "name": "Delivery Exports",
        "description": "Bulk export of delivery shipments, fulfillment logs, and tracking records in CSV or Excel format.",
    },
    {
        "name": "Coupons",
        "description": "Discount vouchers, promotional codes, and coupon redemption.",
    },
    {
        "name": "orders",
        "description": "Sales orders, cart checkout, and customer transactions.",
    },
    {
        "name": "Order Returns",
        "description": "Customer returns, exchange items, and restocking.",
    },
    {
        "name": "billing",
        "description": "POS billing engine, barcode scanning, and fast cashier checkout.",
    },
    {
        "name": "pos-shifts",
        "description": "POS cash registers, cashier drawer shifts, opening/closing floats.",
    },
    {
        "name": "POS Z-Reports",
        "description": "Cash register end-of-shift / end-of-day Z-Report JSON analytics, PDF downloads, and Excel spreadsheets.",
    },
    {
        "name": "invoices",
        "description": "Tax Invoices, invoice status, and billing history.",
    },
    {
        "name": "Invoice Documents",
        "description": "Tax Invoice document PDF generation, downloads, and print formatting.",
    },
    {
        "name": "Bill / Receipt",
        "description": "Compact POS thermal bill and customer payment receipt PDF generation.",
    },
    {
        "name": "gst-rates",
        "description": "GST tax slab definitions and HSN/SAC rate configurations.",
    },
    {
        "name": "refunds",
        "description": "Order refunds, returns, and payment reversals.",
    },
    {
        "name": "Credit Notes",
        "description": "Credit Note management, refund allocations, and Credit Note PDF exports.",
    },
    {
        "name": "payments",
        "description": "Customer payment processing, split tenders, and payment records.",
    },
    {
        "name": "customers",
        "description": "Customer directory, loyalty points, customer ledger, and credit limits.",
    },
    {
        "name": "Customer Exports",
        "description": "Bulk export of customer directory lists in CSV or Excel format.",
    },
    {
        "name": "Document Settings",
        "description": "Customizable branding, invoice prefix/padding sequence rules, terms, and visual document styling.",
    },
    # --- Centre-Lower: Reports & Business Analytics ---
    {
        "name": "Report Exports",
        "description": "Unified on-demand document export engine supporting 22 business reports in CSV, Excel (.xlsx), and PDF formats.",
    },
    {
        "name": "Sales Reports",
        "description": "Daily, monthly, and yearly sales analytics, turnover trends, and top selling products.",
    },
    {
        "name": "Inventory Reports",
        "description": "Live stock levels, low-stock reorder alerts, slow-moving items, and inventory valuation.",
    },
    {
        "name": "GST Reports",
        "description": "Tax compliance, GSTR sales registers, and tax liability breakdowns.",
    },
    {
        "name": "Customer Reports",
        "description": "Customer activity, retention cohorts, customer lifetime value (CLV), and RFM segmentation.",
    },
    {
        "name": "Payment Reports",
        "description": "Daily billing register, cashier reconciliation, and payment gateway/method distribution.",
    },
    {
        "name": "Profitability Reports",
        "description": "Product margin analysis and store-wide Profit & Loss financial statements.",
    },
    {
        "name": "Multi-Store Reports",
        "description": "Comparative cross-store analytics across revenue, profit, inventory, and customer growth.",
    },
    {
        "name": "Sales",
        "description": "General sales analytics.",
    },
    # --- End: Dashboards, AI, Integrations & Administration ---
    {
        "name": "Dashboard",
        "description": "Executive dashboard KPIs and summary metrics.",
    },
    {
        "name": "analytics",
        "description": "Advanced analytics and predictive retail business intelligence.",
    },
    {
        "name": "ai",
        "description": "Retail-OS AI assistant, inventory forecasts, and smart insights.",
    },
    {
        "name": "whatsapp",
        "description": "WhatsApp messaging notifications, billing receipts, and alerts.",
    },
    {
        "name": "reviews",
        "description": "Customer product and store feedback reviews.",
    },
    {
        "name": "Super Admins",
        "description": "Platform-wide super administrator controls.",
    },
    {
        "name": "SaaS Billing",
        "description": "Tenant SaaS subscription plans, billing cycle, and invoices.",
    },
    {
        "name": "SaaS Usage",
        "description": "Tenant plan quotas, resource usage limits, and metering.",
    },
]

app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    lifespan=lifespan,
    openapi_tags=openapi_tags,
)

from app.core.exceptions import register_exception_handlers

register_exception_handlers(app)

from fastapi.openapi.utils import get_openapi


def custom_openapi():
    if not app.openapi_schema:
        openapi_schema = get_openapi(
            title=app.title,
            version=app.version,
            openapi_version=app.openapi_version,
            description=app.description,
            routes=app.routes,
            tags=app.openapi_tags,
            servers=app.servers,
            terms_of_service=app.terms_of_service,
            contact=app.contact,
            license_info=app.license_info,
        )
        app.openapi_schema = openapi_schema

    try:
        from app.core.database import SessionLocal
        from app.models.role import Role
        with SessionLocal() as db_session:
            db_roles = [
                r[0] for r in (
                    db_session.query(Role.name)
                    .distinct()
                    .all()
                )
                if r[0] and r[0].strip().lower() != "superadmin"
            ]
            standard_order = ["admin", "manager", "cashier", "staff", "accountant"]
            sorted_roles = [role for role in standard_order if role in db_roles]
            for r in db_roles:
                if r not in sorted_roles:
                    sorted_roles.append(r)
            if not sorted_roles:
                sorted_roles = standard_order
    except Exception:
        sorted_roles = ["admin", "manager", "cashier", "staff", "accountant"]

    schemas = app.openapi_schema.get("components", {}).get("schemas", {})
    body_schema = schemas.get("Body_create_user_api_v1_users_post")
    if body_schema and "properties" in body_schema and "role" in body_schema["properties"]:
        body_schema["properties"]["role"]["enum"] = sorted_roles
        body_schema["properties"]["role"]["description"] = (
            f"Role name saved in database ({', '.join(sorted_roles)})"
        )
        if "staff" in sorted_roles:
            body_schema["properties"]["role"]["default"] = "staff"

    return app.openapi_schema


app.openapi = custom_openapi


import json
from starlette.types import ASGIApp, Receive, Scope, Send

UPLOAD_DIR = Path("uploads")
PRODUCT_UPLOAD_DIR = UPLOAD_DIR / "products"
USER_UPLOAD_DIR = UPLOAD_DIR / "users"

PRODUCT_UPLOAD_DIR.mkdir(
    parents=True,
    exist_ok=True,
)
USER_UPLOAD_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


class UserJsonToFormMiddleware:
    """Seamlessly adapts JSON payloads on POST /api/v1/users to multipart form-data."""
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if (
            scope.get("type") == "http"
            and scope.get("path", "").rstrip("/") == "/api/v1/users"
            and scope.get("method") == "POST"
        ):
            headers_dict = dict(scope.get("headers", []))
            ct = headers_dict.get(b"content-type", b"").decode("latin1")
            if "application/json" in ct:
                body = bytearray()
                while True:
                    message = await receive()
                    body.extend(message.get("body", b""))
                    if not message.get("more_body", False):
                        break

                try:
                    data = json.loads(body.decode("utf-8")) if body else {}
                except Exception:
                    data = {}

                # Map legacy role_id to role name if role string was omitted
                if "role_id" in data:
                    if not data.get("role"):
                        try:
                            from app.core.database import SessionLocal
                            from app.models.role import Role
                            with SessionLocal() as db_session:
                                r = db_session.query(Role).filter(Role.id == data["role_id"]).first()
                                if r:
                                    data["role"] = r.name
                        except Exception:
                            pass
                    data.pop("role_id", None)

                boundary = "----RetailOSFormBoundaryXyZ12345"
                body_parts = []
                for k, v in data.items():
                    if v is not None:
                        body_parts.append(
                            f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'
                        )
                body_parts.append(f'--{boundary}--\r\n')
                new_body = "".join(body_parts).encode("utf-8")

                new_headers = []
                for k, v in scope.get("headers", []):
                    if k.lower() == b"content-type":
                        new_headers.append(
                            (b"content-type", f"multipart/form-data; boundary={boundary}".encode("ascii"))
                        )
                    elif k.lower() == b"content-length":
                        new_headers.append((b"content-length", str(len(new_body)).encode("ascii")))
                    else:
                        new_headers.append((k, v))
                scope["headers"] = new_headers

                async def new_receive():
                    return {"type": "http.request", "body": new_body, "more_body": False}

                return await self.app(scope, new_receive, send)

        return await self.app(scope, receive, send)


app.mount(
    "/uploads",
    StaticFiles(directory=str(UPLOAD_DIR)),
    name="uploads",
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(TenantMiddleware)
app.add_middleware(UserJsonToFormMiddleware)


API_PREFIX = "/api/v1"


# =========================
# API ROUTES
# =========================

app.include_router(auth_router, prefix=API_PREFIX)
app.include_router(users_router, prefix=API_PREFIX)
app.include_router(roles_router, prefix=API_PREFIX)
app.include_router(stores_router, prefix=API_PREFIX)
app.include_router(store_target_router, prefix=API_PREFIX)
app.include_router(store_transfers_router, prefix=API_PREFIX)
app.include_router(store_expenses_router, prefix=API_PREFIX)
app.include_router(sales_router, prefix=API_PREFIX)
app.include_router(products_router, prefix=API_PREFIX)
app.include_router(categories_router, prefix=API_PREFIX)
app.include_router(inventory_router, prefix=API_PREFIX)
app.include_router(suppliers_router, prefix=API_PREFIX)
app.include_router(purchase_orders_router, prefix=API_PREFIX)
app.include_router(purchase_order_returns_router, prefix=API_PREFIX)
app.include_router(reviews_router, prefix=API_PREFIX)
app.include_router(delivery_router, prefix=API_PREFIX)
app.include_router(warehouses_router, prefix=API_PREFIX)
app.include_router(coupons_router, prefix=API_PREFIX)
app.include_router(orders_router, prefix=API_PREFIX)
app.include_router(order_returns_router, prefix=API_PREFIX)
app.include_router(billing_router, prefix=API_PREFIX)
app.include_router(invoices_router, prefix=API_PREFIX)
app.include_router(gst_rates_router, prefix=API_PREFIX)
app.include_router(refunds_router, prefix=API_PREFIX)
app.include_router(credit_notes_router, prefix=API_PREFIX)
app.include_router(payments_router, prefix=API_PREFIX)
app.include_router(customers_router, prefix=API_PREFIX)
app.include_router(whatsapp_router, prefix=API_PREFIX)
app.include_router(reports_router, prefix=API_PREFIX)
app.include_router(dashboard_router, prefix=API_PREFIX)
app.include_router(analytics_router, prefix=API_PREFIX)
app.include_router(ai_router, prefix=API_PREFIX)
app.include_router(multi_store_router, prefix=API_PREFIX)

# GRN APIs
app.include_router(grn_router, prefix=API_PREFIX)

# Super Admin APIs
app.include_router(super_admin_router, prefix=API_PREFIX)

# SaaS Billing APIs (Tenant-facing)
app.include_router(saas_billing_router, prefix=API_PREFIX)
app.include_router(saas_router, prefix=API_PREFIX)

# Document Settings & Branding APIs
app.include_router(document_settings_router, prefix=API_PREFIX)

# POS Shift / Cash Register APIs
app.include_router(pos_router, prefix=API_PREFIX)

# Product Variants APIs
app.include_router(variants_router, prefix=API_PREFIX)


# =========================
# HEALTH CHECK
# =========================

@app.get("/health")
def health_check():
    from sqlalchemy import text

    from app.core.database import engine

    db_status = "ok"

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        db_status = "error"

    return {
        "status": "ok" if db_status == "ok" else "degraded",
        "app": settings.APP_NAME,
        "database": db_status,
    }
