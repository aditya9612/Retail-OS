from datetime import date
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class StoreRevenueComparisonItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    store_id: int
    store_name: str
    store_code: Optional[str] = None
    city: Optional[str] = None
    is_main: bool = False
    gross_sales: Decimal = Field(default=Decimal("0.00"))
    discount_amount: Decimal = Field(default=Decimal("0.00"))
    tax_amount: Decimal = Field(default=Decimal("0.00"))
    total_sales: Decimal = Field(default=Decimal("0.00"))
    refund_amount: Decimal = Field(default=Decimal("0.00"))
    net_sales: Decimal = Field(default=Decimal("0.00"))
    order_count: int = 0
    average_order_value: Decimal = Field(default=Decimal("0.00"))
    share_of_total_revenue_pct: float = 0.0


class StoreRevenueComparisonResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    start_date: date
    end_date: date
    total_tenant_gross_sales: Decimal = Field(default=Decimal("0.00"))
    total_tenant_net_sales: Decimal = Field(default=Decimal("0.00"))
    total_tenant_orders: int = 0
    store_count: int = 0
    stores: List[StoreRevenueComparisonItem] = Field(default_factory=list)


class StoreProfitComparisonItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    store_id: int
    store_name: str
    store_code: Optional[str] = None
    city: Optional[str] = None
    is_main: bool = False
    gross_sales: Decimal = Field(default=Decimal("0.00"))
    discounts: Decimal = Field(default=Decimal("0.00"))
    net_revenue: Decimal = Field(default=Decimal("0.00"))
    cogs: Decimal = Field(default=Decimal("0.00"))
    operating_expenses: Decimal = Field(default=Decimal("0.00"))
    refund_amount: Decimal = Field(default=Decimal("0.00"))
    gross_profit: Decimal = Field(default=Decimal("0.00"))
    net_profit: Decimal = Field(default=Decimal("0.00"))
    net_profit_margin_pct: float = 0.0
    cogs_data_limitation: str = "COGS is estimated as sum(OrderItem.quantity * current Product.cost_price)."


class StoreProfitComparisonResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    start_date: date
    end_date: date
    total_tenant_net_revenue: Decimal = Field(default=Decimal("0.00"))
    total_tenant_cogs: Decimal = Field(default=Decimal("0.00"))
    total_tenant_expenses: Decimal = Field(default=Decimal("0.00"))
    total_tenant_gross_profit: Decimal = Field(default=Decimal("0.00"))
    total_tenant_net_profit: Decimal = Field(default=Decimal("0.00"))
    store_count: int = 0
    stores: List[StoreProfitComparisonItem] = Field(default_factory=list)


class StoreInventoryComparisonItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    store_id: int
    store_name: str
    store_code: Optional[str] = None
    city: Optional[str] = None
    is_main: bool = False
    total_products: int = 0
    total_units: int = 0
    cost_valuation: Decimal = Field(default=Decimal("0.00"))
    retail_valuation: Decimal = Field(default=Decimal("0.00"))
    low_stock_count: int = 0
    out_of_stock_count: int = 0


class StoreInventoryComparisonResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    as_of_date: date
    total_tenant_units: int = 0
    total_tenant_cost_valuation: Decimal = Field(default=Decimal("0.00"))
    total_tenant_retail_valuation: Decimal = Field(default=Decimal("0.00"))
    store_count: int = 0
    stores: List[StoreInventoryComparisonItem] = Field(default_factory=list)
    valuation_limitation_note: str = (
        "Valuation reflects current product cost_price; historical cost fluctuations are not tracked."
    )


class StoreCustomerComparisonItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    store_id: int
    store_name: str
    store_code: Optional[str] = None
    city: Optional[str] = None
    is_main: bool = False
    unique_customers: int = 0
    guest_orders: int = 0
    total_orders: int = 0
    total_spend: Decimal = Field(default=Decimal("0.00"))
    average_bill_size: Decimal = Field(default=Decimal("0.00"))
    share_of_total_orders_pct: float = 0.0


class StoreCustomerComparisonResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    start_date: date
    end_date: date
    total_tenant_orders: int = 0
    total_tenant_unique_customers: int = 0
    total_tenant_spend: Decimal = Field(default=Decimal("0.00"))
    store_count: int = 0
    stores: List[StoreCustomerComparisonItem] = Field(default_factory=list)
    footfall_data_note: str = (
        "Retail-OS has no physical sensor model; total_orders is used as transaction-volume proxy."
    )
