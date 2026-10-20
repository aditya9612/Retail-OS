from datetime import date, datetime, timezone
from decimal import Decimal
import re
from typing import Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class PurchaseOrderItemCreate(BaseModel):
    product_id: int = Field(
        gt=0,
        description="Product ID must be positive",
    )

    quantity: int = Field(
        gt=0,
        le=100000,
        description="Quantity must be between 1 and 100000",
    )

    unit_cost: Optional[Decimal] = Field(
        default=None,
        gt=0,
        le=Decimal("999999.99"),
        description="Unit cost must be greater than zero",
    )

    unit_price: Optional[Decimal] = Field(
        default=None,
        gt=0,
        le=Decimal("999999.99"),
        description="Unit price alias for unit_cost",
    )

    tax_rate: Optional[Decimal] = Field(
        default=Decimal("0.00"),
        ge=Decimal("0.00"),
        le=Decimal("100.00"),
        description="GST tax rate percentage (e.g. 5.0, 12.0, 18.0)",
    )

    hsn_code: Optional[str] = Field(
        default=None,
        max_length=50,
        description="Harmonized System Nomenclature code for Indian GST compliance",
    )

    unit_of_measure: Optional[str] = Field(
        default="pcs",
        max_length=30,
        description="Unit of measure (e.g. pcs, kg, box, litre)",
    )

    @model_validator(mode="before")
    @classmethod
    def reconcile_unit_cost(cls, data):
        if isinstance(data, dict):
            if data.get("unit_cost") is None and data.get("unit_price") is not None:
                data["unit_cost"] = data["unit_price"]
            elif data.get("unit_cost") is not None and data.get("unit_price") is None:
                data["unit_price"] = data["unit_cost"]
        return data


DISALLOWED_PO_PLACEHOLDERS = {
    "string",
    "test",
    "null",
    "none",
    "undefined",
    "n/a",
    "na",
    "unknown",
    "placeholder",
    "dummy",
    "sample",
    "null value",
    "notes",
    "remarks",
    "invoice",
}

DISALLOWED_INVOICE_PLACEHOLDERS = DISALLOWED_PO_PLACEHOLDERS


def validate_po_notes(value: Optional[str], field_name: str = "Notes") -> Optional[str]:
    if value is None:
        return None

    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")

    v = value.strip()
    if not v:
        raise ValueError(f"{field_name} cannot be empty or whitespace")

    if v.lower() in DISALLOWED_PO_PLACEHOLDERS:
        raise ValueError(f"Please provide a valid {field_name.lower()}")

    if len(v) < 2 or len(v) > 500:
        raise ValueError(f"{field_name} must be between 2 and 500 characters")

    if v.isdigit():
        raise ValueError(f"{field_name} cannot contain only numbers")

    if not re.search(r"[A-Za-z]", v):
        raise ValueError(f"{field_name} must contain at least one alphabetic character")

    alpha_chars = [c.lower() for c in v if c.isalpha()]
    if len(set(alpha_chars)) < 2:
        raise ValueError(f"{field_name} cannot consist of repeating characters")

    if not re.fullmatch(r"[A-Za-z0-9\s,./#&'()\-:;!?]+", v):
        raise ValueError(f"{field_name} contains invalid characters")

    return v


def validate_po_invoice(value: Optional[str], field_name: str = "Invoice ID") -> Optional[str]:
    if value is None:
        return None

    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")

    v = value.strip()
    if not v:
        raise ValueError(f"{field_name} cannot be empty or whitespace")

    if v.lower() in DISALLOWED_PO_PLACEHOLDERS:
        raise ValueError(f"Please provide a valid {field_name.lower()}")

    if len(v) < 2 or len(v) > 100:
        raise ValueError(f"{field_name} must be between 2 and 100 characters")

    alnum_chars = [c.lower() for c in v if c.isalnum()]
    if alnum_chars and len(set(alnum_chars)) < 2:
        raise ValueError(f"{field_name} cannot consist of repeating characters")

    if not any(c.isalnum() for c in v):
        raise ValueError(f"{field_name} must contain alphanumeric characters")

    if not re.fullmatch(r"[A-Za-z0-9/_\-\.]+", v):
        raise ValueError(f"{field_name} can contain only letters, numbers, '-', '_', '/', and '.'")

    return v


def validate_po_delivery_date(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    now_date = datetime.now(timezone.utc).date() if value.tzinfo else datetime.now().date()
    if value.date() < now_date:
        raise ValueError("Expected delivery date cannot be in the past")
    return value


def _clean_str_field(val: object) -> Optional[str]:
    if val is None:
        return None
    s = str(val).strip()
    if not s or s.lower() in DISALLOWED_PO_PLACEHOLDERS:
        return None
    return s


def _reconcile_aliases(
    data: dict,
    primary_key: str,
    alias_key: str,
) -> None:
    has_primary = primary_key in data
    has_alias = alias_key in data

    if not has_primary and not has_alias:
        return

    raw_primary = data.get(primary_key)
    raw_alias = data.get(alias_key)

    clean_primary = _clean_str_field(raw_primary)
    clean_alias = _clean_str_field(raw_alias)

    if clean_primary is not None and clean_alias is not None:
        if clean_primary != clean_alias:
            raise ValueError(
                f"{primary_key} and {alias_key} cannot have conflicting values"
            )
        resolved = clean_primary
    elif clean_primary is not None:
        resolved = clean_primary
    elif clean_alias is not None:
        resolved = clean_alias
    else:
        resolved = None

    data[primary_key] = resolved
    data[alias_key] = resolved


class PurchaseOrderCreate(BaseModel):
    supplier_id: int = Field(
        gt=0,
        description="Supplier ID must be positive",
    )

    store_id: Optional[int] = Field(
        default=None,
        gt=0,
        description="Store ID destination (optional if warehouse_id provided)",
    )

    warehouse_id: Optional[int] = Field(
        default=None,
        gt=0,
        description="Warehouse ID destination (optional if store_id provided)",
    )

    invoice_number: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Invoice or Delivery Challan number",
    )

    invoice_id: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Alias for invoice_number",
    )

    notes: Optional[str] = Field(
        default=None,
        max_length=1000,
        description="Notes for the purchase order",
    )

    remarks: Optional[str] = Field(
        default=None,
        max_length=1000,
        description="Alias for notes",
    )

    expected_delivery_date: Optional[datetime] = Field(
        default=None,
        description="Expected delivery date",
    )

    discount_amount: Optional[Decimal] = Field(
        default=Decimal("0.00"),
        ge=Decimal("0.00"),
        description="Discount amount applied to purchase order",
    )

    shipping_charges: Optional[Decimal] = Field(
        default=Decimal("0.00"),
        ge=Decimal("0.00"),
        description="Shipping / Freight charges applied to purchase order",
    )

    items: list[PurchaseOrderItemCreate]

    @field_validator("invoice_number")
    @classmethod
    def validate_invoice_number(cls, value: Optional[str]) -> Optional[str]:
        return validate_po_invoice(value, "Invoice number")

    @field_validator("invoice_id")
    @classmethod
    def validate_invoice_id(cls, value: Optional[str]) -> Optional[str]:
        return validate_po_invoice(value, "Invoice ID")

    @field_validator("notes")
    @classmethod
    def validate_notes(cls, value: Optional[str]) -> Optional[str]:
        return validate_po_notes(value, "Notes")

    @field_validator("remarks")
    @classmethod
    def validate_remarks(cls, value: Optional[str]) -> Optional[str]:
        return validate_po_notes(value, "Remarks")

    @field_validator("expected_delivery_date")
    @classmethod
    def validate_delivery_date(cls, value: Optional[datetime]) -> Optional[datetime]:
        return validate_po_delivery_date(value)

    @model_validator(mode="before")
    @classmethod
    def reconcile_notes_and_invoices(cls, data):
        if isinstance(data, dict):
            if "invoice_number" in data and data["invoice_number"] is not None:
                validate_po_invoice(data["invoice_number"], "Invoice number")
            if "invoice_id" in data and data["invoice_id"] is not None:
                validate_po_invoice(data["invoice_id"], "Invoice ID")

            if "notes" in data and data["notes"] is not None:
                validate_po_notes(data["notes"], "Notes")
            if "remarks" in data and data["remarks"] is not None:
                validate_po_notes(data["remarks"], "Remarks")

            _reconcile_aliases(data, "notes", "remarks")
            _reconcile_aliases(data, "invoice_number", "invoice_id")
        return data

    @field_validator("items")
    @classmethod
    def validate_items(cls, value):
        if not value:
            raise ValueError(
                "Purchase order must contain at least one item"
            )
        return value


class PurchaseOrderUpdate(BaseModel):
    supplier_id: Optional[int] = Field(
        default=None,
        gt=0,
    )

    store_id: Optional[int] = Field(
        default=None,
        gt=0,
    )

    warehouse_id: Optional[int] = Field(
        default=None,
        gt=0,
    )

    invoice_number: Optional[str] = Field(
        default=None,
        max_length=100,
    )

    invoice_id: Optional[str] = Field(
        default=None,
        max_length=100,
    )

    notes: Optional[str] = Field(
        default=None,
        max_length=1000,
    )

    remarks: Optional[str] = Field(
        default=None,
        max_length=1000,
    )

    expected_delivery_date: Optional[datetime] = None

    discount_amount: Optional[Decimal] = Field(
        default=None,
        ge=Decimal("0.00"),
    )

    shipping_charges: Optional[Decimal] = Field(
        default=None,
        ge=Decimal("0.00"),
    )

    items: Optional[list[PurchaseOrderItemCreate]] = Field(
        default=None,
        description="Optional updated list of items (allowed for draft purchase orders)",
    )

    @field_validator("invoice_number")
    @classmethod
    def validate_invoice_number(cls, value: Optional[str]) -> Optional[str]:
        return validate_po_invoice(value, "Invoice number")

    @field_validator("invoice_id")
    @classmethod
    def validate_invoice_id(cls, value: Optional[str]) -> Optional[str]:
        return validate_po_invoice(value, "Invoice ID")

    @field_validator("notes")
    @classmethod
    def validate_notes(cls, value: Optional[str]) -> Optional[str]:
        return validate_po_notes(value, "Notes")

    @field_validator("remarks")
    @classmethod
    def validate_remarks(cls, value: Optional[str]) -> Optional[str]:
        return validate_po_notes(value, "Remarks")

    @field_validator("expected_delivery_date")
    @classmethod
    def validate_delivery_date(cls, value: Optional[datetime]) -> Optional[datetime]:
        return validate_po_delivery_date(value)

    @model_validator(mode="before")
    @classmethod
    def reconcile_notes_and_invoices(cls, data):
        if isinstance(data, dict):
            if "invoice_number" in data and data["invoice_number"] is not None:
                validate_po_invoice(data["invoice_number"], "Invoice number")
            if "invoice_id" in data and data["invoice_id"] is not None:
                validate_po_invoice(data["invoice_id"], "Invoice ID")

            if "notes" in data and data["notes"] is not None:
                validate_po_notes(data["notes"], "Notes")
            if "remarks" in data and data["remarks"] is not None:
                validate_po_notes(data["remarks"], "Remarks")

            _reconcile_aliases(data, "notes", "remarks")
            _reconcile_aliases(data, "invoice_number", "invoice_id")
        return data


class PurchaseOrderReceiveItem(BaseModel):
    product_id: int = Field(gt=0, description="Product ID being received")
    quantity: int = Field(gt=0, description="Quantity being received")
    batch_number: Optional[str] = Field(default=None, max_length=100)
    expiry_date: Optional[date] = None


class PurchaseOrderReceive(BaseModel):
    invoice_number: Optional[str] = Field(
        default=None,
        max_length=100,
    )
    invoice_id: Optional[str] = Field(
        default=None,
        max_length=100,
    )
    remarks: Optional[str] = Field(
        default=None,
        max_length=500,
    )
    notes: Optional[str] = Field(
        default=None,
        max_length=500,
    )
    batch_number: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Optional batch number for received items",
    )
    expiry_date: Optional[date] = Field(
        default=None,
        description="Optional expiry date for received items",
    )
    items: Optional[list[PurchaseOrderReceiveItem]] = Field(
        default=None,
        description="Optional item-level receive details for partial deliveries",
    )

    @field_validator("invoice_number")
    @classmethod
    def validate_invoice_number(cls, value: Optional[str]) -> Optional[str]:
        return validate_po_invoice(value, "Invoice number")

    @field_validator("invoice_id")
    @classmethod
    def validate_invoice_id(cls, value: Optional[str]) -> Optional[str]:
        return validate_po_invoice(value, "Invoice ID")

    @field_validator("notes")
    @classmethod
    def validate_notes(cls, value: Optional[str]) -> Optional[str]:
        return validate_po_notes(value, "Notes")

    @field_validator("remarks")
    @classmethod
    def validate_remarks(cls, value: Optional[str]) -> Optional[str]:
        return validate_po_notes(value, "Remarks")

    @model_validator(mode="before")
    @classmethod
    def reconcile_notes_and_invoices(cls, data):
        if isinstance(data, dict):
            if "invoice_number" in data and data["invoice_number"] is not None:
                validate_po_invoice(data["invoice_number"], "Invoice number")
            if "invoice_id" in data and data["invoice_id"] is not None:
                validate_po_invoice(data["invoice_id"], "Invoice ID")

            if "notes" in data and data["notes"] is not None:
                validate_po_notes(data["notes"], "Notes")
            if "remarks" in data and data["remarks"] is not None:
                validate_po_notes(data["remarks"], "Remarks")

            _reconcile_aliases(data, "notes", "remarks")
            _reconcile_aliases(data, "invoice_number", "invoice_id")
        return data


class PurchaseOrderStatusUpdate(BaseModel):
    status: str = Field(
        description="Purchase order status",
    )

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str):
        allowed = {
            "draft",
            "approved",
            "partially_received",
            "received",
            "cancelled",
        }

        if value not in allowed:
            raise ValueError(
                "Status must be draft, approved, partially_received, received or cancelled"
            )

        return value


class PurchaseOrderApproveRequest(BaseModel):
    notes: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Approval notes or vendor dispatch authorization comments",
    )


class PurchaseOrderCancelRequest(BaseModel):
    reason: str = Field(
        min_length=3,
        max_length=500,
        description="Mandatory reason for cancelling the purchase order",
    )


class PurchaseOrderItemResponse(BaseModel):
    id: int
    po_id: Optional[int] = None
    purchase_order_id: Optional[int] = None
    product_id: int
    product_name: Optional[str] = None
    product_sku: Optional[str] = None
    quantity: int
    unit_cost: Decimal = Decimal("0.00")
    unit_price: Optional[Decimal] = None
    total_cost: Decimal = Decimal("0.00")
    total: Optional[Decimal] = None
    tax_rate: Decimal = Decimal("0.00")
    tax_amount: Decimal = Decimal("0.00")
    hsn_code: Optional[str] = None
    unit_of_measure: Optional[str] = "pcs"
    received_quantity: int = 0
    remaining_quantity: int = 0

    @model_validator(mode="after")
    def sync_aliases(self):
        if self.po_id is not None and self.purchase_order_id is None:
            self.purchase_order_id = self.po_id
        if self.unit_cost is not None and self.unit_price is None:
            self.unit_price = self.unit_cost
        if self.total_cost is not None and self.total is None:
            self.total = self.total_cost
        if self.quantity is not None and self.received_quantity is not None:
            self.remaining_quantity = max(0, self.quantity - self.received_quantity)
        return self

    model_config = ConfigDict(from_attributes=True)


class PurchaseOrderResponse(BaseModel):
    id: int
    tenant_id: int
    supplier_id: int
    supplier_name: Optional[str] = None
    supplier_email: Optional[str] = None
    supplier_phone: Optional[str] = None
    supplier_gstin: Optional[str] = None
    store_id: Optional[int] = None
    store_name: Optional[str] = None
    warehouse_id: Optional[int] = None
    warehouse_name: Optional[str] = None
    order_number: str
    po_number: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_id: Optional[str] = None
    status: str
    subtotal: Decimal = Decimal("0.00")
    tax_amount: Decimal = Decimal("0.00")
    discount_amount: Decimal = Decimal("0.00")
    shipping_charges: Decimal = Decimal("0.00")
    total_amount: Decimal = Decimal("0.00")
    notes: Optional[str] = None
    remarks: Optional[str] = None
    expected_delivery_date: Optional[datetime] = None
    created_by_id: Optional[int] = None
    created_by_name: Optional[str] = None
    approved_by_id: Optional[int] = None
    approved_by_name: Optional[str] = None
    approved_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    cancellation_reason: Optional[str] = None
    total_quantity: int = 0
    total_received_quantity: int = 0
    remaining_quantity: int = 0
    created_at: datetime
    updated_at: Optional[datetime] = None

    items: list[PurchaseOrderItemResponse] = []

    @model_validator(mode="after")
    def sync_aliases(self):
        if self.order_number and not self.po_number:
            self.po_number = self.order_number
        if self.notes is not None and self.remarks is None:
            self.remarks = self.notes
        elif self.remarks is not None and self.notes is None:
            self.notes = self.remarks
        if self.invoice_number and not self.invoice_id:
            self.invoice_id = self.invoice_number
        elif self.invoice_id and not self.invoice_number:
            self.invoice_number = self.invoice_id
        if self.invoice_number and self.invoice_number.strip().lower() in DISALLOWED_PO_PLACEHOLDERS:
            self.invoice_number = None
            self.invoice_id = None
        if self.items:
            self.total_quantity = sum(it.quantity for it in self.items)
            self.total_received_quantity = sum(it.received_quantity or 0 for it in self.items)
            self.remaining_quantity = max(0, self.total_quantity - self.total_received_quantity)
        return self

    model_config = ConfigDict(from_attributes=True)


class PurchaseOrderStatsResponse(BaseModel):
    total_orders: int
    draft_orders: int
    approved_orders: int
    partially_received_orders: int
    received_orders: int
    cancelled_orders: int
    total_order_value: Decimal
    total_received_value: Decimal
    expected_deliveries_this_week: int


class PurchaseOrderDeleteData(BaseModel):
    id: int
    order_number: str


class PurchaseOrderDeleteResponse(BaseModel):
    success: bool = True
    message: str = "Purchase order deleted successfully"
    data: PurchaseOrderDeleteData
