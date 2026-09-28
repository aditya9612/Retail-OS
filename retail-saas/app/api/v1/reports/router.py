from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_permission
from app.models.user import User
from app.schemas.report import (
    CurrentStockResponse,
    CustomerLifetimeValueResponse,
    CustomerOverviewResponse,
    CustomerRetentionResponse,
    CustomerSegmentsResponse,
    DailySalesResponse,
    GSTSalesResponse,
    GSTSummaryResponse,
    InventoryValuationResponse,
    LowStockResponse,
    MonthlySalesResponse,
    ProductProfitabilityResponse,
    ProfitLossResponse,
    ReportExportRequest,
    SlowMovingProductsResponse,
    TopSellingProductsResponse,
    YearlySalesResponse,
)
from app.services.report_service import ReportService
from app.tasks.report_tasks import generate_gst_report_task, generate_monthly_report_task

router = APIRouter(prefix="/reports", tags=["reports"])


class MonthlyReportAsyncRequest(BaseModel):
    year: int = Field(..., ge=2000, le=2100)
    month: int = Field(..., ge=1, le=12)


class GSTReportAsyncRequest(BaseModel):
    start_date: date
    end_date: date


# ============================================================================
# CORE SALES REPORTS (BRD FR-1, FR-2, FR-3, FR-4)
# ============================================================================

@router.get("/sales/daily", response_model=DailySalesResponse)
def get_daily_sales(
    target_date: Optional[date] = None,
    store_id: Optional[int] = None,
    user: User = Depends(require_permission("reports:read")),
    db: Session = Depends(get_db),
):
    return ReportService(db).daily_sales(
        user_or_tenant=user, target_date=target_date, store_id=store_id
    )


@router.get("/sales/monthly", response_model=MonthlySalesResponse)
def get_monthly_sales(
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
    store_id: Optional[int] = None,
    user: User = Depends(require_permission("reports:read")),
    db: Session = Depends(get_db),
):
    return ReportService(db).monthly_sales(
        user_or_tenant=user, year=year, month=month, store_id=store_id
    )


@router.get("/sales/yearly", response_model=YearlySalesResponse)
def get_yearly_sales(
    year: int = Query(..., ge=2000, le=2100),
    store_id: Optional[int] = None,
    user: User = Depends(require_permission("reports:read")),
    db: Session = Depends(get_db),
):
    return ReportService(db).yearly_sales(
        user_or_tenant=user, year=year, store_id=store_id
    )


# ============================================================================
# CORE GST REPORTS (BRD FR-6, FR-7)
# ============================================================================

@router.get("/gst/sales", response_model=GSTSalesResponse)
def get_gst_sales(
    start_date: date = Query(...),
    end_date: date = Query(...),
    store_id: Optional[int] = None,
    user: User = Depends(require_permission("reports:read")),
    db: Session = Depends(get_db),
):
    return ReportService(db).gst_sales(
        user_or_tenant=user,
        start_date=start_date,
        end_date=end_date,
        store_id=store_id,
    )


@router.get("/gst/summary", response_model=GSTSummaryResponse)
def get_gst_summary(
    start_date: date = Query(...),
    end_date: date = Query(...),
    store_id: Optional[int] = None,
    user: User = Depends(require_permission("reports:read")),
    db: Session = Depends(get_db),
):
    return ReportService(db).gst_summary(
        user_or_tenant=user,
        start_date=start_date,
        end_date=end_date,
        store_id=store_id,
    )


# ============================================================================
# CORE INVENTORY REPORTS (BRD FR-8, FR-9, FR-11)
# ============================================================================

@router.get("/inventory/current-stock", response_model=CurrentStockResponse)
def get_current_stock(
    store_id: Optional[int] = None,
    user: User = Depends(require_permission("reports:read")),
    db: Session = Depends(get_db),
):
    return ReportService(db).current_stock(user_or_tenant=user, store_id=store_id)


@router.get("/inventory/low-stock", response_model=LowStockResponse)
def get_low_stock(
    store_id: Optional[int] = None,
    user: User = Depends(require_permission("reports:read")),
    db: Session = Depends(get_db),
):
    return ReportService(db).low_stock(user_or_tenant=user, store_id=store_id)


@router.get("/inventory/valuation", response_model=InventoryValuationResponse)
def get_inventory_valuation(
    store_id: Optional[int] = None,
    user: User = Depends(require_permission("reports:read")),
    db: Session = Depends(get_db),
):
    return ReportService(db).inventory_valuation(
        user_or_tenant=user, store_id=store_id
    )


# ============================================================================
# CORE PRODUCT ANALYTICS (BRD FR-12, FR-13, FR-14)
# ============================================================================

@router.get("/products/top-selling", response_model=TopSellingProductsResponse)
def get_top_selling_products(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    limit: int = Query(default=10, ge=1, le=100),
    store_id: Optional[int] = None,
    user: User = Depends(require_permission("reports:read")),
    db: Session = Depends(get_db),
):
    return ReportService(db).top_selling_products(
        user_or_tenant=user,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        store_id=store_id,
    )


@router.get("/products/slow-moving", response_model=SlowMovingProductsResponse)
def get_slow_moving_products(
    threshold: int = Query(
        ...,
        ge=0,
        description="Caller-provided sales quantity threshold below which a product is considered slow-moving",
    ),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    store_id: Optional[int] = None,
    user: User = Depends(require_permission("reports:read")),
    db: Session = Depends(get_db),
):
    return ReportService(db).slow_moving_products(
        user_or_tenant=user,
        threshold=threshold,
        start_date=start_date,
        end_date=end_date,
        store_id=store_id,
    )


@router.get("/products/profitability", response_model=ProductProfitabilityResponse)
def get_product_profitability(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    store_id: Optional[int] = None,
    user: User = Depends(require_permission("reports:read")),
    db: Session = Depends(get_db),
):
    return ReportService(db).product_profitability(
        user_or_tenant=user,
        start_date=start_date,
        end_date=end_date,
        store_id=store_id,
    )


# ============================================================================
# CORE CUSTOMER ANALYTICS (BRD FR-15, FR-16, FR-17, FR-18)
# ============================================================================

@router.get("/customers/overview", response_model=CustomerOverviewResponse)
def get_customers_overview(
    user: User = Depends(require_permission("reports:read")),
    db: Session = Depends(get_db),
):
    return ReportService(db).customers_overview(user_or_tenant=user)


@router.get("/customers/retention", response_model=CustomerRetentionResponse)
def get_customers_retention(
    user: User = Depends(require_permission("reports:read")),
    db: Session = Depends(get_db),
):
    return ReportService(db).customers_retention(user_or_tenant=user)


@router.get("/customers/lifetime-value", response_model=CustomerLifetimeValueResponse)
def get_customers_lifetime_value(
    limit: int = Query(default=10, ge=1, le=100),
    user: User = Depends(require_permission("reports:read")),
    db: Session = Depends(get_db),
):
    return ReportService(db).customers_lifetime_value(
        user_or_tenant=user, limit=limit
    )


@router.get("/customers/segments", response_model=CustomerSegmentsResponse)
def get_customers_segments(
    user: User = Depends(require_permission("reports:read")),
    db: Session = Depends(get_db),
):
    return ReportService(db).customers_segments(user_or_tenant=user)


# ============================================================================
# CORE PROFIT & LOSS REPORT (BRD FR-19)
# ============================================================================

@router.get("/profit-loss", response_model=ProfitLossResponse)
def get_profit_loss(
    start_date: date = Query(...),
    end_date: date = Query(...),
    store_id: Optional[int] = None,
    user: User = Depends(require_permission("reports:read")),
    db: Session = Depends(get_db),
):
    return ReportService(db).profit_loss(
        user_or_tenant=user,
        start_date=start_date,
        end_date=end_date,
        store_id=store_id,
    )


# ============================================================================
# CORE EXPORT ROUTE (BRD Section 11)
# ============================================================================

@router.post("/export")
def export_report(
    data: ReportExportRequest,
    user: User = Depends(require_permission("reports:read")),
    db: Session = Depends(get_db),
):
    return ReportService(db).export_report(user=user, data=data)


# ============================================================================
# LEGACY COMPATIBILITY ROUTES (PRESERVED & DELEGATED)
# ============================================================================

@router.get("/daily-sales")
def legacy_daily_sales(
    target_date: Optional[date] = None,
    store_id: Optional[int] = None,
    user: User = Depends(require_permission("reports:read")),
    db: Session = Depends(get_db),
):
    return ReportService(db).daily_sales(
        user_or_tenant=user, target_date=target_date, store_id=store_id
    )


@router.get("/monthly-sales")
def legacy_monthly_sales(
    year: int = Query(...),
    month: int = Query(...),
    store_id: Optional[int] = None,
    user: User = Depends(require_permission("reports:read")),
    db: Session = Depends(get_db),
):
    return ReportService(db).monthly_sales(
        user_or_tenant=user, year=year, month=month, store_id=store_id
    )


@router.get("/gst")
def legacy_gst_report(
    start_date: date = Query(...),
    end_date: date = Query(...),
    store_id: Optional[int] = None,
    user: User = Depends(require_permission("reports:read")),
    db: Session = Depends(get_db),
):
    return ReportService(db).gst_sales(
        user_or_tenant=user,
        start_date=start_date,
        end_date=end_date,
        store_id=store_id,
    )


@router.get("/daily-billing")
def daily_billing_closure(
    target_date: Optional[date] = None,
    user: User = Depends(require_permission("reports:read")),
    db: Session = Depends(get_db),
):
    return ReportService(db).daily_billing_closure(user.tenant_id, target_date)


@router.get("/payment-summary")
def payment_summary(
    start_date: date,
    end_date: date,
    user: User = Depends(require_permission("reports:read")),
    db: Session = Depends(get_db),
):
    return ReportService(db).payment_summary(user.tenant_id, start_date, end_date)


@router.post("/monthly/async")
def monthly_report_async(
    data: MonthlyReportAsyncRequest,
    user: User = Depends(require_permission("reports:read")),
):
    task = generate_monthly_report_task.delay(user.tenant_id, data.year, data.month)
    return {"task_id": task.id}


@router.post("/gst/async")
def gst_report_async(
    data: GSTReportAsyncRequest,
    user: User = Depends(require_permission("reports:read")),
):
    task = generate_gst_report_task.delay(
        user.tenant_id, data.start_date.isoformat(), data.end_date.isoformat()
    )
    return {"task_id": task.id}
