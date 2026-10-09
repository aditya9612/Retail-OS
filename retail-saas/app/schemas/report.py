from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


# ============================================================================
# SALES REPORTS
# ============================================================================

class DailySalesResponse(BaseModel):
    date: str
    order_count: int
    gross_sales: Decimal
    discount_amount: Decimal
    tax_amount: Decimal
    total_sales: Decimal
    refund_amount: Decimal
    net_sales: Decimal
    average_order_value: Decimal
    payment_methods: Dict[str, Decimal] = Field(default_factory=dict)
    store_id: Optional[int] = None


class MonthlySalesTopProduct(BaseModel):
    product_id: int
    product_name: str
    quantity_sold: int
    revenue: Decimal


class MonthlySalesResponse(BaseModel):
    year: int
    month: int
    order_count: int
    gross_sales: Decimal
    discount_amount: Decimal
    tax_amount: Decimal
    total_sales: Decimal
    refund_amount: Decimal
    net_sales: Decimal
    growth_rate_pct: Optional[float] = None
    top_products: List[MonthlySalesTopProduct] = Field(default_factory=list)
    store_id: Optional[int] = None


class YearlySalesMonthItem(BaseModel):
    month: int
    month_name: str
    order_count: int
    gross_sales: Decimal
    total_sales: Decimal
    net_sales: Decimal


class YearlySalesResponse(BaseModel):
    year: int
    total_orders: int
    gross_sales: Decimal
    total_sales: Decimal
    net_sales: Decimal
    monthly_breakdown: List[YearlySalesMonthItem] = Field(default_factory=list)
    store_id: Optional[int] = None


# ============================================================================
# GST REPORTS
# ============================================================================

class GSTSalesResponse(BaseModel):
    start_date: str
    end_date: str
    invoice_count: int
    taxable_amount: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    igst_amount: Decimal
    total_tax: Decimal
    total_amount: Decimal
    rate_breakdown: Dict[str, Dict[str, Decimal]] = Field(default_factory=dict)
    store_id: Optional[int] = None


class GSTSummaryResponse(BaseModel):
    start_date: str
    end_date: str
    invoice_count: int
    output_cgst: Decimal
    output_sgst: Decimal
    output_igst: Decimal
    total_output_tax: Decimal
    input_tax_credit: Decimal = Decimal("0.00")
    net_tax_liability: Decimal
    store_id: Optional[int] = None
    note: Optional[str] = None


# ============================================================================
# INVENTORY REPORTS
# ============================================================================

class CurrentStockItem(BaseModel):
    product_id: int
    product_name: str
    sku: str
    store_id: int
    quantity: int
    min_stock_level: int
    reorder_point: int
    stock_status: str


class CurrentStockResponse(BaseModel):
    total_items: int
    total_quantity: int
    items: List[CurrentStockItem] = Field(default_factory=list)
    store_id: Optional[int] = None


class LowStockItem(BaseModel):
    product_id: int
    product_name: str
    sku: str
    store_id: int
    quantity: int
    min_stock_level: int
    reorder_point: int
    deficit: int


class LowStockResponse(BaseModel):
    total_low_stock_products: int
    items: List[LowStockItem] = Field(default_factory=list)
    store_id: Optional[int] = None


class InventoryValuationResponse(BaseModel):
    total_products: int
    total_units: int
    cost_valuation: Decimal
    retail_valuation: Decimal
    store_id: Optional[int] = None
    data_limitation_note: str = (
        "Valuation reflects current product cost_price; historical cost fluctuations are not tracked."
    )


# ============================================================================
# PRODUCT ANALYTICS
# ============================================================================

class ProductVelocityItem(BaseModel):
    product_id: int
    product_name: str
    sku: str
    quantity_sold: int
    revenue: Decimal
    orders_count: int


class TopSellingProductsResponse(BaseModel):
    limit: int
    products: List[ProductVelocityItem] = Field(default_factory=list)
    store_id: Optional[int] = None


class SlowMovingProductsResponse(BaseModel):
    threshold: int
    products: List[ProductVelocityItem] = Field(default_factory=list)
    store_id: Optional[int] = None


class ProductProfitabilityItem(BaseModel):
    product_id: int
    product_name: str
    sku: str
    quantity_sold: int
    revenue: Decimal
    estimated_cost: Decimal
    estimated_gross_profit: Decimal
    margin_pct: Optional[float] = None


class ProductProfitabilityResponse(BaseModel):
    total_revenue: Decimal
    total_estimated_cost: Decimal
    total_estimated_profit: Decimal
    products: List[ProductProfitabilityItem] = Field(default_factory=list)
    store_id: Optional[int] = None
    data_limitation_note: str = (
        "Estimated cost is computed using current Product.cost_price * quantity sold."
    )


# ============================================================================
# CUSTOMER ANALYTICS
# ============================================================================

class CustomerOverviewResponse(BaseModel):
    total_customers: int
    active_customers: int
    inactive_customers: int
    total_loyalty_points: int
    total_spend_all_customers: Decimal


class CustomerRetentionResponse(BaseModel):
    total_customers: int
    active_customers: int
    repeat_customers: int
    repeat_purchase_rate: float
    retention_rate: float


class CustomerLifetimeValueItem(BaseModel):
    customer_id: int
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    total_spend: Decimal
    orders_count: int


class CustomerLifetimeValueResponse(BaseModel):
    average_lifetime_value: Decimal
    top_customers: List[CustomerLifetimeValueItem] = Field(default_factory=list)


class CustomerSegmentsResponse(BaseModel):
    segment_counts: Dict[str, int] = Field(default_factory=dict)
    total_categorized: int


# ============================================================================
# PROFIT & LOSS REPORT
# ============================================================================

class ProfitLossResponse(BaseModel):
    start_date: str
    end_date: str
    store_id: Optional[int] = None
    gross_sales: Decimal
    discounts: Decimal
    tax_amount: Decimal
    invoiced_revenue: Decimal
    net_revenue_tax_exclusive: Decimal
    refund_amount: Decimal
    cogs: Decimal
    operating_expenses: Decimal
    gross_profit: Decimal
    net_profit: Decimal
    cogs_data_limitation: str = (
        "COGS is estimated as sum(OrderItem.quantity * current Product.cost_price)."
    )


# ============================================================================
# EXPORT REQUEST
# ============================================================================

class ReportType(str, Enum):
    SALES_DAILY = "sales_daily"
    SALES_MONTHLY = "sales_monthly"
    SALES_YEARLY = "sales_yearly"
    GST_SALES = "gst_sales"
    GST_SUMMARY = "gst_summary"
    INVENTORY_STOCK = "inventory_stock"
    INVENTORY_LOW = "inventory_low"
    INVENTORY_VALUATION = "inventory_valuation"
    PRODUCTS_TOP_SELLING = "products_top_selling"
    PRODUCTS_SLOW_MOVING = "products_slow_moving"
    PRODUCTS_PROFITABILITY = "products_profitability"
    PROFIT_LOSS = "profit_loss"
    CUSTOMERS_OVERVIEW = "customers_overview"
    CUSTOMERS_RETENTION = "customers_retention"
    CUSTOMERS_LIFETIME_VALUE = "customers_lifetime_value"
    CUSTOMERS_SEGMENTS = "customers_segments"
    DAILY_BILLING = "daily_billing"
    DAILY_BILLING_CLOSURE = "daily_billing_closure"
    PAYMENT_SUMMARY = "payment_summary"
    MULTI_STORE_REVENUE = "multi_store_revenue"
    MULTI_STORE_PROFIT = "multi_store_profit"
    MULTI_STORE_INVENTORY = "multi_store_inventory"
    MULTI_STORE_CUSTOMER = "multi_store_customer"


class ExportFormat(str, Enum):
    CSV = "csv"
    EXCEL = "excel"
    PDF = "pdf"


class ReportExportRequest(BaseModel):
    report_type: ReportType = Field(
        ...,
        description="Supported report type identifier: 'sales_daily', 'sales_monthly', 'sales_yearly', "
                    "'gst_sales', 'gst_summary', 'inventory_stock', 'inventory_low', 'inventory_valuation', "
                    "'products_top_selling', 'products_slow_moving', 'products_profitability', 'profit_loss', "
                    "'customers_overview', 'customers_retention', 'customers_lifetime_value', 'customers_segments', "
                    "'daily_billing', 'payment_summary', 'multi_store_revenue', 'multi_store_profit', "
                    "'multi_store_inventory', 'multi_store_customer'."
    )
    format: ExportFormat = Field(
        default=ExportFormat.CSV,
        description="Target export file format ('csv', 'excel', 'pdf'). Default: 'csv'."
    )
    start_date: Optional[date] = Field(None, description="Start date for date-range reports (YYYY-MM-DD).")
    end_date: Optional[date] = Field(None, description="End date for date-range reports (YYYY-MM-DD).")
    target_date: Optional[date] = Field(None, description="Target date for daily reports (YYYY-MM-DD).")
    year: Optional[int] = Field(None, ge=2000, le=2100, description="Calendar year for monthly or yearly reports.")
    month: Optional[int] = Field(None, ge=1, le=12, description="Month number (1-12) for monthly reports.")
    store_id: Optional[int] = Field(None, gt=0, description="Optional store filter ID.")
    threshold: Optional[int] = Field(None, ge=0, description="Stock threshold for slow-moving products.")
    limit: Optional[int] = Field(None, gt=0, le=500, description="Maximum number of items/ranking rows to return.")
