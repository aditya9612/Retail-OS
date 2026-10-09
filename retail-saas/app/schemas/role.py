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
            {"code": "payments:read", "label": "View Payments", "description": "View payment transactions and tender records"},
            {"code": "payments:write", "label": "Collect Payments", "description": "Accept and record customer payments"},
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
            {"code": "pos:shift_manage", "label": "Manage POS Shifts", "description": "Open, reconcile, and close register shifts"},
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
            {"code": "batches:read", "label": "View Batches", "description": "View product batch allocations and expiry dates"},
            {"code": "batches:write", "label": "Manage Batches", "description": "Create and manage product batch stock"},
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
            {"code": "reviews:read", "label": "View Reviews", "description": "View customer feedback and product reviews"},
            {"code": "reviews:write", "label": "Manage Reviews", "description": "Respond to and moderate customer reviews"},
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
            {"code": "store_expenses:read", "label": "View Store Expenses", "description": "View petty cash and daily store operating expenses"},
            {"code": "store_expenses:write", "label": "Manage Store Expenses", "description": "Record and manage store operating expenses"},
        ],
    },
    {
        "module": "dashboard",
        "label": "Dashboard Overview",
        "permissions": [
            {"code": "dashboard:view", "label": "View Dashboard", "description": "Access store dashboard overview metrics"},
            {"code": "dashboard:read", "label": "Read Dashboard Analytics", "description": "Read store analytics cards and KPIs"},
        ],
    },
]


def get_all_valid_permission_codes() -> set[str]:
    return {
        p["code"]
        for group in AVAILABLE_PERMISSIONS
        for p in group["permissions"]
    }


def validate_role_name_string(value: str) -> str:
    val = value.strip()
    if not val:
        raise ValueError("Role name cannot be empty")
    if len(val) < 2 or len(val) > 50:
        raise ValueError("Role name must be between 2 and 50 characters")

    # Allowed characters: alphanumeric, spaces, hyphens, and underscores
    if not all(c.isalnum() or c in ("_", "-", " ") for c in val):
        raise ValueError("Role name can only contain letters, numbers, spaces, hyphens, and underscores")

    # Cannot start or end with a hyphen or underscore
    if val.startswith(("-", "_")):
        raise ValueError("Role name cannot start with a hyphen or underscore")
    if val.endswith(("-", "_")):
        raise ValueError("Role name cannot end with a hyphen or underscore")

    # Must contain at least 2 alphabetic letters (cannot be purely numeric like '000', '123' or symbols like '---')
    alpha_count = sum(1 for c in val if c.isalpha())
    if alpha_count < 2:
        raise ValueError(
            "Role name must contain at least 2 alphabetic letters and cannot be purely numeric or special characters (e.g., 'cashier', 'inventory_supervisor')"
        )

    # Check reserved system role names
    normalized = val.lower().replace(" ", "_").replace("-", "_")
    reserved_system_names = {"superadmin", "admin", "owner"}
    if normalized in reserved_system_names or val.lower() in reserved_system_names:
        raise ValueError(f"'{val}' is a reserved system role name and cannot be used for custom roles")

    return val.lower()


def validate_permissions_list(value: list[str]) -> list[str]:
    if not isinstance(value, list):
        raise ValueError("Permissions must be a list of permission codes")

    valid_codes = get_all_valid_permission_codes()
    cleaned: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError("Permission code must be a string")
        code = item.strip()
        if not code:
            raise ValueError("Permission code cannot be empty")
        if code not in valid_codes:
            raise ValueError(
                f"Invalid permission '{code}'. Must be a valid system permission code. "
                "Use GET /api/v1/roles/permissions to view available permissions."
            )
        if code not in cleaned:
            cleaned.append(code)
    return cleaned


class RoleCreate(BaseModel):
    name: str = Field(
        ...,
        min_length=2,
        max_length=50,
        description="Role name (e.g., accountant, cashier, inventory_manager)",
    )
    permissions: list[str] = Field(
        default_factory=list,
        description="List of permission strings assigned to this role (e.g., ['products:read', 'inventory:read'])",
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return validate_role_name_string(value)

    @field_validator("permissions")
    @classmethod
    def validate_permissions(cls, value: list[str]) -> list[str]:
        return validate_permissions_list(value)


class RoleUpdate(BaseModel):
    name: Optional[str] = Field(
        default=None,
        min_length=2,
        max_length=50,
        description="New role name (e.g., store_supervisor, assistant_manager)",
    )
    permissions: Optional[list[str]] = Field(
        default=None,
        description="Updated list of permission strings (must be valid system permissions)",
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return validate_role_name_string(value)

    @field_validator("permissions")
    @classmethod
    def validate_permissions(cls, value: Optional[list[str]]) -> Optional[list[str]]:
        if value is None:
            return None
        return validate_permissions_list(value)


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
