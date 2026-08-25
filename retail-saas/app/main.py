from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
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
from app.api.v1.payments.router import router as payments_router
from app.api.v1.products.router import router as products_router
from app.api.v1.categories.router import router as categories_router
from app.api.v1.purchase_orders.router import router as purchase_orders_router
from app.api.v1.refunds.router import router as refunds_router
from app.api.v1.reports.router import router as reports_router
from app.api.v1.stores.router import router as stores_router
from app.api.v1.suppliers.router import router as suppliers_router
from app.api.v1.users.router import router as users_router
from app.api.v1.warehouses.router import router as warehouses_router
from app.api.v1.whatsapp.router import router as whatsapp_router
from app.api.v1.super_admins.router import router as super_admin_router

from app.core.config import get_settings
from app.core.database import init_db
from app.core.logger import logger
from app.core.middleware import TenantMiddleware

from app.models import *


settings = get_settings()


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


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    lifespan=lifespan,
)


UPLOAD_DIR = Path("uploads")
PRODUCT_UPLOAD_DIR = UPLOAD_DIR / "products"

PRODUCT_UPLOAD_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


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

app.add_middleware(TenantMiddleware)


API_PREFIX = "/api/v1"


# =========================
# API ROUTES
# =========================

app.include_router(auth_router, prefix=API_PREFIX)
app.include_router(users_router, prefix=API_PREFIX)
app.include_router(stores_router, prefix=API_PREFIX)
app.include_router(products_router, prefix=API_PREFIX)
app.include_router(categories_router, prefix=API_PREFIX)
app.include_router(inventory_router, prefix=API_PREFIX)
app.include_router(suppliers_router, prefix=API_PREFIX)
app.include_router(purchase_orders_router, prefix=API_PREFIX)
app.include_router(delivery_router, prefix=API_PREFIX)
app.include_router(warehouses_router, prefix=API_PREFIX)
app.include_router(coupons_router, prefix=API_PREFIX)
app.include_router(orders_router, prefix=API_PREFIX)
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

# GRN APIs
app.include_router(grn_router, prefix=API_PREFIX)

# Super Admin APIs
app.include_router(super_admin_router, prefix=API_PREFIX)


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