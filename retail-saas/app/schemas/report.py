from datetime import date
from decimal import Decimal
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

class ReportExportRequest(BaseModel):
    report_type: str = Field(
        ...,
        description="Type of report: 'sales_daily', 'sales_monthly', 'sales_yearly', "
                    "'gst_sales', 'gst_summary', 'inventory_stock', 'inventory_low', "
                    "'inventory_valuation', 'products_top_selling', 'products_profitability', "
                    "'profit_loss', 'customers_overview', 'customers_retention', 'customers_segments'"
    )
    format: Literal["csv", "excel", "pdf"] = "csv"
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    target_date: Optional[date] = None
    year: Optional[int] = None
    month: Optional[int] = None
    store_id: Optional[int] = None
    threshold: Optional[int] = None
    limit: Optional[int] = None
