from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


AVAILABLE_PERMISSIONS: list[dict] = [
    {
        "module": "billing",
        "label": "Billing & Invoicing",
        "permissions": [
            {"code": "billing:read", "label": "View Bills", "description": "View bills, invoices, and billing history"},
            {"code": "billing:write", "label": "Create Bills", "description": "Create invoices, checkout POS cart, and accept payments"},
            {"code": "billing:refund", "label": "Process Refunds", "description": "Process invoice returns and issue refunds"},
            {"code": "billing:price_override", "label": "Price Override", "description": "Override item prices or discounts during checkout"},
            {"code": "billing:gst_config", "label": "GST Configuration", "description": "Manage GST settings and tax slabs"},
            {"code": "invoices:read", "label": "View Invoices", "description": "View generated tax invoices"},
            {"code": "credit_notes:read", "label": "View Credit Notes", "description": "View issued credit notes"},
            {"code": "credit_notes:write", "label": "Issue Credit Notes", "description": "Generate and issue credit notes"},
        ],
    },
    {
        "module": "orders",
        "label": "Orders & POS Sales",
        "permissions": [
            {"code": "orders:read", "label": "View Orders", "description": "View online and offline sales orders"},
            {"code": "orders:write", "label": "Manage Orders", "description": "Create, update, and cancel sales orders"},
            {"code": "sales:read", "label": "View Sales Records", "description": "View sales transactions"},
            {"code": "sales:write", "label": "Process Sales", "description": "Record sales transactions"},
        ],
    },
    {
        "module": "inventory",
        "label": "Inventory & Catalog",
        "permissions": [
            {"code": "products:read", "label": "View Products", "description": "View product catalog, pricing, and barcodes"},
            {"code": "products:write", "label": "Manage Products", "description": "Create, edit, or delete products and categories"},
            {"code": "categories:read", "label": "View Categories", "description": "View product categories"},
            {"code": "categories:write", "label": "Manage Categories", "description": "Create and edit product categories"},
            {"code": "inventory:read", "label": "View Stock", "description": "View real-time stock levels across stores"},
            {"code": "inventory:write", "label": "Manage Stock", "description": "Adjust inventory quantities and store transfers"},
        ],
    },
    {
        "module": "purchases",
        "label": "Purchases & Suppliers",
        "permissions": [
            {"code": "purchase_orders:read", "label": "View Purchases", "description": "View vendor purchase orders and GRN receipts"},
            {"code": "purchase_orders:write", "label": "Manage Purchases", "description": "Create purchase orders and record GRN receipts"},
            {"code": "suppliers:read", "label": "View Suppliers", "description": "View supplier contact directory"},
            {"code": "suppliers:write", "label": "Manage Suppliers", "description": "Add, edit, and deactivate suppliers"},
        ],
    },
    {
        "module": "customers",
        "label": "Customers & Loyalty",
        "permissions": [
            {"code": "customers:read", "label": "View Customers", "description": "View customer profiles and purchase history"},
            {"code": "customers:write", "label": "Manage Customers", "description": "Add or update customer profiles"},
            {"code": "coupons:read", "label": "View Coupons", "description": "View discount coupons and promo codes"},
            {"code": "coupons:write", "label": "Manage Coupons", "description": "Create and manage promotional coupons"},
        ],
    },
    {
        "module": "reports",
        "label": "Reports & Analytics",
        "permissions": [
            {"code": "reports:read", "label": "View Reports", "description": "Access sales, tax, and inventory reports"},
            {"code": "analytics:read", "label": "View Analytics", "description": "View business KPIs and multi-store analytics"},
        ],
    },
    {
        "module": "organization",
        "label": "Stores & Staff Management",
        "permissions": [
            {"code": "stores:read", "label": "View Stores", "description": "View store branch details"},
            {"code": "stores:write", "label": "Manage Stores", "description": "Create and edit store branches"},
            {"code": "users:read", "label": "View Users", "description": "View staff profiles and role assignments"},
            {"code": "users:write", "label": "Manage Users", "description": "Create, edit, assign, and deactivate staff users"},
        ],
    },
]


class RoleCreate(BaseModel):
    name: str = Field(
        ...,
        min_length=2,
        max_length=50,
        description="Role name (e.g., accountant, cashier, inventory_manager)",
    )
    permissions: list[str] = Field(
        default_factory=list,
        description="List of permission strings assigned to this role",
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        val = value.strip().lower()
        if not val:
            raise ValueError("Role name cannot be empty")
        if len(val) < 2 or len(val) > 50:
            raise ValueError("Role name must be between 2 and 50 characters")
        if not all(c.isalnum() or c in ("_", "-", " ") for c in val):
            raise ValueError("Role name can only contain letters, numbers, spaces, hyphens, and underscores")
        return val


class RoleUpdate(BaseModel):
    name: Optional[str] = Field(
        default=None,
        min_length=2,
        max_length=50,
        description="New role name",
    )
    permissions: Optional[list[str]] = Field(
        default=None,
        description="Updated list of permission strings",
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        val = value.strip().lower()
        if not val:
            raise ValueError("Role name cannot be empty")
        if len(val) < 2 or len(val) > 50:
            raise ValueError("Role name must be between 2 and 50 characters")
        if not all(c.isalnum() or c in ("_", "-", " ") for c in val):
            raise ValueError("Role name can only contain letters, numbers, spaces, hyphens, and underscores")
        return val


class RoleDetailResponse(BaseModel):
    id: int
    tenant_id: Optional[int] = None
    name: str
    is_system: bool = False
    permissions: list[str] = Field(default_factory=list)
    user_count: int = 0
    created_at: Optional[datetime] = None

    model_config = ConfigDict(
        from_attributes=True,
    )


class PermissionItem(BaseModel):
    code: str
    label: str
    description: str


class PermissionGroup(BaseModel):
    module: str
    label: str
    permissions: list[PermissionItem]
