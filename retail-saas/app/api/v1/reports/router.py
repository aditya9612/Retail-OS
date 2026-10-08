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
    ExportFormat,
    GSTSalesResponse,
    GSTSummaryResponse,
    InventoryValuationResponse,
    LowStockResponse,
    MonthlySalesResponse,
    ProductProfitabilityResponse,
    ProfitLossResponse,
    ReportExportRequest,
    ReportType,
    SlowMovingProductsResponse,
    TopSellingProductsResponse,
    YearlySalesResponse,
)
from app.services.report_service import ReportService
from app.tasks.report_tasks import generate_gst_report_task, generate_monthly_report_task

router = APIRouter(prefix="/reports")


class MonthlyReportAsyncRequest(BaseModel):
    year: int = Field(..., ge=2000, le=2100)
    month: int = Field(..., ge=1, le=12)


class GSTReportAsyncRequest(BaseModel):
    start_date: date
    end_date: date


# ============================================================================
# CORE SALES REPORTS (BRD FR-1, FR-2, FR-3, FR-4)
# ============================================================================

@router.get(
    "/sales/daily",
    response_model=DailySalesResponse,
    tags=["Sales Reports"],
    summary="Daily Sales Report",
    description="Retrieve daily sales analytics, turnover, tax, payments, and hour-by-hour sales trend for a specific date or today.",
)
def get_daily_sales(
    target_date: Optional[date] = None,
    store_id: Optional[int] = None,
    user: User = Depends(require_permission("reports:read")),
    db: Session = Depends(get_db),
):
    return ReportService(db).daily_sales(
        user_or_tenant=user, target_date=target_date, store_id=store_id
    )


@router.get(
    "/sales/monthly",
    response_model=MonthlySalesResponse,
    tags=["Sales Reports"],
    summary="Monthly Sales Report",
    description="Retrieve monthly sales breakdown, daily trend curve, discount totals, and day-by-day revenue.",
)
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


@router.get(
    "/sales/yearly",
    response_model=YearlySalesResponse,
    tags=["Sales Reports"],
    summary="Yearly Sales Report",
    description="Retrieve full-year annual sales performance, month-by-month revenue, and quarterly aggregates.",
)
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

@router.get(
    "/gst/sales",
    response_model=GSTSalesResponse,
    tags=["GST Reports"],
    summary="GST Sales Register Report",
    description="Retrieve invoice-level GST sales register including taxable amount, CGST, SGST, IGST, and customer GSTINs.",
)
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


@router.get(
    "/gst/summary",
    response_model=GSTSummaryResponse,
    tags=["GST Reports"],
    summary="GST Tax Summary Report",
    description="Retrieve aggregated GST summary grouped by tax rate tier (0%, 5%, 12%, 18%, 28%) with CGST, SGST, and IGST breakdowns.",
)
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

@router.get(
    "/inventory/current-stock",
    response_model=CurrentStockResponse,
    tags=["Inventory Reports"],
    summary="Current Stock Report",
    description="Live inventory stock position across all products and variants with reorder levels and unit values.",
)
def get_current_stock(
    store_id: Optional[int] = None,
    user: User = Depends(require_permission("reports:read")),
    db: Session = Depends(get_db),
):
    return ReportService(db).current_stock(user_or_tenant=user, store_id=store_id)


@router.get(
    "/inventory/low-stock",
    response_model=LowStockResponse,
    tags=["Inventory Reports"],
    summary="Low Stock Alert Report",
    description="Real-time list of products and variants whose current inventory quantity has fallen below minimum reorder thresholds.",
)
def get_low_stock(
    store_id: Optional[int] = None,
    user: User = Depends(require_permission("reports:read")),
    db: Session = Depends(get_db),
):
    return ReportService(db).low_stock(user_or_tenant=user, store_id=store_id)


@router.get(
    "/inventory/valuation",
    response_model=InventoryValuationResponse,
    tags=["Inventory Reports"],
    summary="Inventory Valuation Report",
    description="Comprehensive valuation of warehouse and store inventory computed at purchase cost and retail price.",
)
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

@router.get(
    "/products/top-selling",
    response_model=TopSellingProductsResponse,
    tags=["Sales Reports"],
    summary="Top Selling Products Report",
    description="Rank products by sales volume and generated revenue within the selected date window.",
)
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


@router.get(
    "/products/slow-moving",
    response_model=SlowMovingProductsResponse,
    tags=["Inventory Reports"],
    summary="Slow Moving Products Report",
    description="Identify stagnant inventory items whose sales volume fell below the specified threshold over the observation period.",
)
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


@router.get(
    "/products/profitability",
    response_model=ProductProfitabilityResponse,
    tags=["Profitability Reports"],
    summary="Product Profitability Report",
    description="Analyze profit margins per product line comparing unit selling price against supplier purchase cost.",
)
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

@router.get(
    "/customers/overview",
    response_model=CustomerOverviewResponse,
    tags=["Customer Reports"],
    summary="Customer Overview Analytics",
    description="High-level customer demographic and purchasing summary including total customers, active vs inactive ratios.",
)
def get_customers_overview(
    user: User = Depends(require_permission("reports:read")),
    db: Session = Depends(get_db),
):
    return ReportService(db).customers_overview(user_or_tenant=user)


@router.get(
    "/customers/retention",
    response_model=CustomerRetentionResponse,
    tags=["Customer Reports"],
    summary="Customer Retention Analytics",
    description="Customer retention rates, churn risk metrics, and repeat purchase cohort behavior over time.",
)
def get_customers_retention(
    user: User = Depends(require_permission("reports:read")),
    db: Session = Depends(get_db),
):
    return ReportService(db).customers_retention(user_or_tenant=user)


@router.get(
    "/customers/lifetime-value",
    response_model=CustomerLifetimeValueResponse,
    tags=["Customer Reports"],
    summary="Customer Lifetime Value (CLV)",
    description="Rank top customers by lifetime value, historical order counts, and average transaction size.",
)
def get_customers_lifetime_value(
    limit: int = Query(default=10, ge=1, le=100),
    user: User = Depends(require_permission("reports:read")),
    db: Session = Depends(get_db),
):
    return ReportService(db).customers_lifetime_value(
        user_or_tenant=user, limit=limit
    )


@router.get(
    "/customers/segments",
    response_model=CustomerSegmentsResponse,
    tags=["Customer Reports"],
    summary="Customer Segmentation Analytics",
    description="RFM (Recency, Frequency, Monetary) customer segmentation distributions: Champions, Loyal, At Risk, Lost.",
)
def get_customers_segments(
    user: User = Depends(require_permission("reports:read")),
    db: Session = Depends(get_db),
):
    return ReportService(db).customers_segments(user_or_tenant=user)


# ============================================================================
# CORE PROFIT & LOSS REPORT (BRD FR-19)
# ============================================================================

@router.get(
    "/profit-loss",
    response_model=ProfitLossResponse,
    tags=["Profitability Reports"],
    summary="Profit & Loss Statement",
    description="Store or enterprise-level financial Profit & Loss statement detailing gross revenue, COGS, operational expenses, and net profit margins.",
)
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

@router.post(
    "/export",
    tags=["Report Exports"],
    summary="Export Any Report (POST)",
    description="Generate and export any business report in CSV, Excel (.xlsx), or PDF format with granular filters and parameters.",
    responses={
        200: {
            "description": "Report file stream (CSV, Excel spreadsheet, or PDF document)",
            "content": {
                "text/csv": {"schema": {"type": "string", "format": "binary"}},
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {
                    "schema": {"type": "string", "format": "binary"}
                },
                "application/pdf": {"schema": {"type": "string", "format": "binary"}},
            },
        }
    },
)
def export_report(
    data: ReportExportRequest,
    user: User = Depends(require_permission("reports:read")),
    db: Session = Depends(get_db),
):
    return ReportService(db).export_report(user=user, data=data)


@router.get(
    "/export",
    tags=["Report Exports"],
    summary="Export Any Report (GET)",
    description="Download any business report in CSV, Excel (.xlsx), or PDF format via query parameters.",
    responses={
        200: {
            "description": "Report file stream (CSV, Excel spreadsheet, or PDF document)",
            "content": {
                "text/csv": {"schema": {"type": "string", "format": "binary"}},
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {
                    "schema": {"type": "string", "format": "binary"}
                },
                "application/pdf": {"schema": {"type": "string", "format": "binary"}},
            },
        }
    },
)
def export_report_get(
    report_type: ReportType = Query(..., description="Report type identifier (22 supported reports)"),
    format: ExportFormat = Query(default=ExportFormat.CSV, description="Export file format: csv, excel, or pdf"),
    start_date: Optional[date] = Query(default=None, description="Start date (YYYY-MM-DD) for date-filtered reports"),
    end_date: Optional[date] = Query(default=None, description="End date (YYYY-MM-DD) for date-filtered reports"),
    target_date: Optional[date] = Query(default=None, description="Single target date (YYYY-MM-DD) for daily reports"),
    year: Optional[int] = Query(default=None, ge=2000, le=2100, description="Calendar year for monthly/yearly reports"),
    month: Optional[int] = Query(default=None, ge=1, le=12, description="Month (1-12) for monthly reports"),
    store_id: Optional[int] = Query(default=None, description="Optional store filter for store-scoped reports"),
    threshold: Optional[int] = Query(default=None, ge=0, description="Quantity threshold for slow-moving products"),
    limit: Optional[int] = Query(default=None, ge=1, le=100, description="Max record count for ranked reports"),
    user: User = Depends(require_permission("reports:read")),
    db: Session = Depends(get_db),
):
    req = ReportExportRequest(
        report_type=report_type,
        format=format,
        start_date=start_date,
        end_date=end_date,
        target_date=target_date,
        year=year,
        month=month,
        store_id=store_id,
        threshold=threshold,
        limit=limit,
    )
    return ReportService(db).export_report(user=user, data=req)


# ============================================================================
# LEGACY COMPATIBILITY ROUTES (PRESERVED & DELEGATED)
# ============================================================================

@router.get(
    "/daily-sales",
    tags=["Sales Reports"],
    summary="Daily Sales Report (Legacy)",
    description="Legacy endpoint returning daily sales analytics.",
)
def legacy_daily_sales(
    target_date: Optional[date] = None,
    store_id: Optional[int] = None,
    user: User = Depends(require_permission("reports:read")),
    db: Session = Depends(get_db),
):
    return ReportService(db).daily_sales(
        user_or_tenant=user, target_date=target_date, store_id=store_id
    )


@router.get(
    "/monthly-sales",
    tags=["Sales Reports"],
    summary="Monthly Sales Report (Legacy)",
    description="Legacy endpoint returning monthly sales analytics.",
)
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


@router.get(
    "/gst",
    tags=["GST Reports"],
    summary="GST Sales Report (Legacy)",
    description="Legacy endpoint returning GST sales report.",
)
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


@router.get(
    "/daily-billing",
    tags=["Payment Reports"],
    summary="Daily Billing Closure Report",
    description="Daily billing closure report detailing cashier shifts, invoices, cash/UPI collections, and discrepancies.",
)
def daily_billing_closure(
    target_date: Optional[date] = None,
    user: User = Depends(require_permission("reports:read")),
    db: Session = Depends(get_db),
):
    return ReportService(db).daily_billing_closure(user.tenant_id, target_date)


@router.get(
    "/payment-summary",
    tags=["Payment Reports"],
    summary="Payment Method Summary Report",
    description="Aggregated payment summary across all payment modes (Cash, UPI, Card, Net Banking).",
)
def payment_summary(
    start_date: date,
    end_date: date,
    user: User = Depends(require_permission("reports:read")),
    db: Session = Depends(get_db),
):
    return ReportService(db).payment_summary(user.tenant_id, start_date, end_date)


@router.post(
    "/monthly/async",
    tags=["Sales Reports"],
    summary="Generate Monthly Sales Report Asynchronously",
    description="Enqueues background task for generating comprehensive monthly sales report.",
)
def monthly_report_async(
    data: MonthlyReportAsyncRequest,
    user: User = Depends(require_permission("reports:read")),
):
    task = generate_monthly_report_task.delay(user.tenant_id, data.year, data.month)
    return {"task_id": task.id}


@router.post(
    "/gst/async",
    tags=["GST Reports"],
    summary="Generate GST Report Asynchronously",
    description="Enqueues background task for generating comprehensive GST sales register.",
)
def gst_report_async(
    data: GSTReportAsyncRequest,
    user: User = Depends(require_permission("reports:read")),
):
    task = generate_gst_report_task.delay(
        user.tenant_id, data.start_date.isoformat(), data.end_date.isoformat()
    )
    return {"task_id": task.id}
