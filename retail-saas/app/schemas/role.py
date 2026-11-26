from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


AVAILABLE_PERMISSIONS: list[dict] = [
    {
        "module": "billing",
        "label": "Billing & Invoicing",
        "permissions": [
            {"code": "billing:create", "label": "Create Bills", "description": "Create invoices, checkout POS cart, and accept payments"},
            {"code": "billing:read", "label": "View Bills", "description": "View bills, invoices, and billing history"},
            {"code": "billing:update", "label": "Edit Bills", "description": "Modify cart items, apply discounts, and update billing notes"},
            {"code": "billing:delete", "label": "Void / Cancel Bills", "description": "Cancel or clear cart, remove items, and void invoices"},
            {"code": "billing:refund", "label": "Process Refunds", "description": "Process invoice returns and issue refunds"},
            {"code": "billing:price_override", "label": "Price Override", "description": "Override item prices or discounts during checkout"},
            {"code": "billing:gst_config", "label": "GST Configuration", "description": "Manage GST settings and tax slabs"},
            {"code": "invoices:read", "label": "View Invoices", "description": "View generated tax invoices"},
            {"code": "credit_notes:create", "label": "Issue Credit Notes", "description": "Generate and issue credit notes"},
            {"code": "credit_notes:read", "label": "View Credit Notes", "description": "View issued credit notes"},
            {"code": "credit_notes:update", "label": "Edit Credit Notes", "description": "Update or adjust credit note details"},
            {"code": "credit_notes:delete", "label": "Void Credit Notes", "description": "Cancel or void issued credit notes"},
            {"code": "payments:create", "label": "Collect Payments", "description": "Accept and record customer payments"},
            {"code": "payments:read", "label": "View Payments", "description": "View payment transactions and tender records"},
            {"code": "payments:update", "label": "Edit Payments", "description": "Modify payment records and reconcile tender"},
            {"code": "payments:delete", "label": "Void Payments", "description": "Void or delete payment transactions"},
        ],
    },
    {
        "module": "orders",
        "label": "Orders & POS Sales",
        "permissions": [
            {"code": "orders:create", "label": "Create Orders", "description": "Create new online and offline sales orders"},
            {"code": "orders:read", "label": "View Orders", "description": "View online and offline sales orders"},
            {"code": "orders:update", "label": "Update Orders", "description": "Update order status, delivery, or details"},
            {"code": "orders:delete", "label": "Cancel / Delete Orders", "description": "Cancel or delete sales orders"},
            {"code": "sales:create", "label": "Record Sales", "description": "Record sales transactions"},
            {"code": "sales:read", "label": "View Sales Records", "description": "View sales transactions"},
            {"code": "sales:update", "label": "Edit Sales", "description": "Modify recorded sales"},
            {"code": "sales:delete", "label": "Void Sales", "description": "Void sales transactions"},
            {"code": "pos:shift_manage", "label": "Manage POS Shifts", "description": "Open, reconcile, and close register shifts"},
        ],
    },
    {
        "module": "inventory",
        "label": "Inventory & Stock",
        "permissions": [
            {"code": "inventory:create", "label": "Add Stock Adjustments", "description": "Record stock-in and initiate store transfers"},
            {"code": "inventory:read", "label": "View Stock", "description": "View real-time stock levels across stores"},
            {"code": "inventory:update", "label": "Update Stock", "description": "Adjust stock quantities, approve/dispatch transfers"},
            {"code": "inventory:delete", "label": "Void Stock Adjustments", "description": "Cancel or delete stock adjustment entries"},
            {"code": "batches:create", "label": "Create Batches", "description": "Create new product batch records"},
            {"code": "batches:read", "label": "View Batches", "description": "View product batch allocations and expiry dates"},
            {"code": "batches:update", "label": "Edit Batches", "description": "Update batch quantities, MRP, and expiry dates"},
            {"code": "batches:delete", "label": "Delete Batches", "description": "Remove or archive expired batches"},
            {"code": "warehouses:create", "label": "Create Warehouses", "description": "Add new warehouse facilities and storage locations"},
            {"code": "warehouses:read", "label": "View Warehouses", "description": "View warehouse facilities and storage hub stock"},
            {"code": "warehouses:update", "label": "Edit Warehouses", "description": "Update warehouse facility details and status"},
            {"code": "warehouses:delete", "label": "Delete Warehouses", "description": "Remove or deactivate warehouse facilities"},
        ],
    },
    {
        "module": "products",
        "label": "Products & Categories",
        "permissions": [
            {"code": "products:create", "label": "Create Products", "description": "Add new products to the catalog"},
            {"code": "products:read", "label": "View Products", "description": "View product catalog, pricing, and barcodes"},
            {"code": "products:update", "label": "Edit Products", "description": "Update product details, pricing, barcodes, and variants"},
            {"code": "products:delete", "label": "Delete Products", "description": "Remove or deactivate products and variants"},
            {"code": "categories:create", "label": "Create Categories", "description": "Add new product categories"},
            {"code": "categories:read", "label": "View Categories", "description": "View product categories"},
            {"code": "categories:update", "label": "Edit Categories", "description": "Update product category details"},
            {"code": "categories:delete", "label": "Delete Categories", "description": "Remove product categories"},
        ],
    },
    {
        "module": "purchases",
        "label": "Purchases & Suppliers",
        "permissions": [
            {"code": "purchase_orders:create", "label": "Create Purchases", "description": "Create new vendor purchase orders"},
            {"code": "purchase_orders:read", "label": "View Purchases", "description": "View vendor purchase orders"},
            {"code": "purchase_orders:update", "label": "Edit Purchases", "description": "Approve, update, or edit purchase orders"},
            {"code": "purchase_orders:delete", "label": "Cancel / Delete Purchases", "description": "Cancel or delete purchase orders"},
            {"code": "grn:create", "label": "Create GRN Receipts", "description": "Create, inspect, and receive inward goods receipt notes"},
            {"code": "grn:read", "label": "View GRN Receipts", "description": "View inward goods receipt notes, shipments, and batch records"},
            {"code": "grn:update", "label": "Edit GRN Receipts", "description": "Update inspection and approval details for GRN"},
            {"code": "grn:delete", "label": "Delete GRN Receipts", "description": "Cancel or delete goods receipt notes"},
            {"code": "suppliers:create", "label": "Create Suppliers", "description": "Add new suppliers to the directory"},
            {"code": "suppliers:read", "label": "View Suppliers", "description": "View supplier contact directory"},
            {"code": "suppliers:update", "label": "Edit Suppliers", "description": "Update supplier contact information and status"},
            {"code": "suppliers:delete", "label": "Delete Suppliers", "description": "Remove or deactivate suppliers"},
        ],
    },
    {
        "module": "delivery",
        "label": "Delivery & Logistics",
        "permissions": [
            {"code": "delivery:create", "label": "Create Deliveries", "description": "Create delivery orders, methods, and zones"},
            {"code": "delivery:read", "label": "View Deliveries", "description": "View delivery orders, dispatch schedules, and tracking"},
            {"code": "delivery:update", "label": "Update Deliveries", "description": "Assign couriers, update delivery status, and reconcile COD"},
            {"code": "delivery:delete", "label": "Cancel / Delete Deliveries", "description": "Cancel deliveries, remove delivery methods and zones"},
        ],
    },
    {
        "module": "customers",
        "label": "Customers & Loyalty",
        "permissions": [
            {"code": "customers:create", "label": "Create Customers", "description": "Add customer profiles, referrals, notes, and loyalty records"},
            {"code": "customers:read", "label": "View Customers", "description": "View customer profiles and purchase history"},
            {"code": "customers:update", "label": "Edit Customers", "description": "Update customer details, credit limits, and status"},
            {"code": "customers:delete", "label": "Delete Customers", "description": "Remove customer profiles"},
            {"code": "coupons:create", "label": "Create Coupons", "description": "Create and bulk-generate promotional coupons"},
            {"code": "coupons:read", "label": "View Coupons", "description": "View discount coupons and promo codes"},
            {"code": "coupons:update", "label": "Edit Coupons", "description": "Update coupon rules, expiry, and status"},
            {"code": "coupons:delete", "label": "Delete Coupons", "description": "Remove promotional coupons"},
            {"code": "reviews:create", "label": "Create Reviews", "description": "Submit customer feedback and reviews"},
            {"code": "reviews:read", "label": "View Reviews", "description": "View customer feedback and product reviews"},
            {"code": "reviews:update", "label": "Moderate Reviews", "description": "Edit or moderate customer reviews"},
            {"code": "reviews:delete", "label": "Delete Reviews", "description": "Remove customer reviews"},
        ],
    },
    {
        "module": "ecommerce",
        "label": "E-Commerce Storefront",
        "permissions": [
            {"code": "ecommerce:create", "label": "Create Storefront Content", "description": "Create online products, banners, and collections"},
            {"code": "ecommerce:read", "label": "View E-Commerce", "description": "View online store catalog, web analytics, and storefront orders"},
            {"code": "ecommerce:update", "label": "Update Storefront", "description": "Configure digital storefront, theme, and website settings"},
            {"code": "ecommerce:delete", "label": "Delete Storefront Content", "description": "Remove storefront banners, collections, or settings"},
        ],
    },
    {
        "module": "whatsapp",
        "label": "WhatsApp Integration",
        "permissions": [
            {"code": "whatsapp:create", "label": "Configure WhatsApp", "description": "Set up WhatsApp Cloud API credentials and templates"},
            {"code": "whatsapp:read", "label": "View WhatsApp Settings", "description": "View WhatsApp Cloud API configuration and message logs"},
            {"code": "whatsapp:update", "label": "Update WhatsApp Settings", "description": "Update WhatsApp configuration, phone numbers, and webhooks"},
            {"code": "whatsapp:delete", "label": "Delete WhatsApp Config", "description": "Remove WhatsApp API connections and message templates"},
            {"code": "whatsapp:send", "label": "Send WhatsApp Messages", "description": "Dispatch digital invoices, receipts, and customer notifications"},
        ],
    },
    {
        "module": "ai",
        "label": "AI Assistant & Predictions",
        "permissions": [
            {"code": "ai:read", "label": "Access AI Assistant", "description": "Query AI assistant for stock reorder forecasts, churn analysis, and sales trends"},
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
        "module": "stores",
        "label": "Store Branches & Expenses",
        "permissions": [
            {"code": "stores:create", "label": "Create Stores", "description": "Add new store branches"},
            {"code": "stores:read", "label": "View Stores", "description": "View store branch details"},
            {"code": "stores:update", "label": "Edit Stores", "description": "Update store branch information and status"},
            {"code": "stores:delete", "label": "Delete Stores", "description": "Remove or close store branches"},
            {"code": "store_expenses:create", "label": "Record Store Expenses", "description": "Record new store operating expenses"},
            {"code": "store_expenses:read", "label": "View Store Expenses", "description": "View petty cash and daily store operating expenses"},
            {"code": "store_expenses:update", "label": "Edit Store Expenses", "description": "Update recorded store operating expenses"},
            {"code": "store_expenses:delete", "label": "Delete Store Expenses", "description": "Remove or void store operating expenses"},
        ],
    },
    {
        "module": "users",
        "label": "Staff Users & Roles",
        "permissions": [
            {"code": "users:create", "label": "Create Users", "description": "Add new staff user accounts"},
            {"code": "users:read", "label": "View Users", "description": "View staff profiles and role assignments"},
            {"code": "users:update", "label": "Edit Users", "description": "Update staff profiles, permissions, and status"},
            {"code": "users:delete", "label": "Delete Users", "description": "Deactivate or remove staff user accounts"},
        ],
    },
    {
        "module": "settings",
        "label": "Settings & Branding",
        "permissions": [
            {"code": "settings:create", "label": "Create Document Settings", "description": "Initialize document settings, print templates, and configurations"},
            {"code": "settings:read", "label": "View Document Settings", "description": "View invoice branding, print templates, and gateway settings"},
            {"code": "settings:update", "label": "Update Document Settings", "description": "Configure invoice headers, print styling, numbering rules, and payment gateways"},
            {"code": "settings:delete", "label": "Delete Document Settings", "description": "Reset or remove document templates and custom branding"},
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
    valid = {
        p["code"]
        for group in AVAILABLE_PERMISSIONS
        for p in group["permissions"]
    }
    # Allow wildcard for superadmin / owner administrative permissions
    valid.add("*")
    # Backward compatibility: accept broad :write permissions as valid codes
    for group in AVAILABLE_PERMISSIONS:
        for p in group["permissions"]:
            parts = p["code"].split(":")
            if len(parts) == 2:
                valid.add(f"{parts[0]}:write")
    return valid


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
        examples=["inventory_supervisor"],
    )
    description: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Optional human-readable description of this role",
        examples=["Oversees store inventory counts, stock adjustments, and product transfers"],
    )
    permissions: list[str] = Field(
        default_factory=list,
        max_length=200,
        description="List of permission strings assigned to this role (e.g., ['products:read', 'inventory:read'])",
        examples=[["products:read", "inventory:read", "inventory:write"]],
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "inventory_supervisor",
                "description": "Oversees store inventory counts, stock adjustments, and product transfers",
                "permissions": ["products:read", "inventory:read", "inventory:write"],
            }
        }
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
        examples=["senior_supervisor"],
    )
    description: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Updated role description",
        examples=["Updated responsibilities for store inventory management"],
    )
    permissions: Optional[list[str]] = Field(
        default=None,
        max_length=200,
        description="Updated list of permission strings (must be valid system permissions)",
        examples=[["products:read", "inventory:read", "inventory:write", "batches:read"]],
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "senior_supervisor",
                "description": "Updated responsibilities for store inventory management",
                "permissions": ["products:read", "inventory:read", "inventory:write", "batches:read"],
            }
        }
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
    id: int = Field(..., description="Role ID", examples=[1])
    tenant_id: Optional[int] = Field(None, description="Tenant ID", examples=[1])
    name: str = Field(..., description="Role name", examples=["cashier"])
    description: Optional[str] = Field(None, description="Role description", examples=["Handles POS checkout and customer billing"])
    is_system: bool = Field(False, description="Whether this is a core system role", examples=[True])
    permissions: list[str] = Field(default_factory=list, description="Assigned permissions", examples=[["products:read", "billing:write"]])
    user_count: int = Field(0, description="Number of active users assigned to this role", examples=[3])
    created_at: Optional[datetime] = Field(None, description="Role creation date")

    model_config = ConfigDict(
        from_attributes=True,
    )


class RoleDeleteResponse(BaseModel):
    message: str = Field(..., description="Success message", examples=["Role 'inventory_supervisor' deleted successfully"])
    deleted_role_id: int = Field(..., description="ID of deleted role", examples=[5])


class RoleUserItem(BaseModel):
    id: int = Field(..., description="User ID", examples=[10])
    full_name: str = Field(..., description="Full Name", examples=["Rohan Deshmukh"])
    email: str = Field(..., description="Email Address", examples=["rohan@retailstore.com"])
    phone: Optional[str] = Field(None, description="Phone Number", examples=["9876543210"])
    store_id: Optional[int] = Field(None, description="Assigned Store ID", examples=[1])
    store_name: Optional[str] = Field(None, description="Assigned Store Name", examples=["Downtown Branch"])
    is_active: bool = Field(True, description="Account active status", examples=[True])
    created_at: Optional[datetime] = Field(None, description="User creation date")

    model_config = ConfigDict(
        from_attributes=True,
    )


class RoleUsersResponse(BaseModel):
    role_id: int = Field(..., description="Role ID", examples=[3])
    role_name: str = Field(..., description="Role Name", examples=["cashier"])
    total_users: int = Field(..., description="Total users assigned to this role", examples=[5])
    page: int = Field(1, description="Current page", examples=[1])
    page_size: int = Field(20, description="Items per page", examples=[20])
    users: list[RoleUserItem] = Field(default_factory=list)

    model_config = ConfigDict(
        from_attributes=True,
    )


class RoleReassignUsersRequest(BaseModel):
    target_role_id: int | str = Field(
        ...,
        description="Target Role ID (e.g. 2) or Target Role Name (e.g. 'staff') to which all active users will be moved",
        examples=[2],
    )


class RoleReassignUsersResponse(BaseModel):
    message: str = Field(..., description="Status message", examples=["Successfully reassigned 3 user(s) to role 'staff'"])
    source_role_id: int = Field(..., description="Source Role ID", examples=[5])
    source_role_name: str = Field(..., description="Source Role Name", examples=["temp_cashier"])
    target_role_id: int = Field(..., description="Target Role ID", examples=[2])
    target_role_name: str = Field(..., description="Target Role Name", examples=["staff"])
    reassigned_count: int = Field(..., description="Number of users reassigned", examples=[3])


class RoleMatrixColumn(BaseModel):
    id: int = Field(..., description="Role ID", examples=[1])
    name: str = Field(..., description="Role name", examples=["cashier"])
    is_system: bool = Field(False, description="Whether this is a core system role", examples=[False])


class PermissionMatrixRow(BaseModel):
    code: str = Field(..., description="Permission code", examples=["billing:read"])
    label: str = Field(..., description="Human-readable label", examples=["View Bills"])
    description: str = Field(..., description="Permission description", examples=["View bills and billing history"])
    role_access: dict[str, bool] = Field(
        default_factory=dict,
        description="Map of role name to boolean indicating if the role has access",
        examples=[{"owner": True, "cashier": True, "staff": False}],
    )


class ModuleMatrixGroup(BaseModel):
    module: str = Field(..., description="Module identifier", examples=["billing"])
    label: str = Field(..., description="Module display name", examples=["Billing & Invoicing"])
    permissions: list[PermissionMatrixRow] = Field(default_factory=list)


class RoleMatrixResponse(BaseModel):
    roles: list[RoleMatrixColumn] = Field(default_factory=list)
    modules: list[ModuleMatrixGroup] = Field(default_factory=list)


class PermissionItem(BaseModel):
    code: str
    label: str
    description: str


class PermissionGroup(BaseModel):
    module: str
    label: str
    permissions: list[PermissionItem]


class RoleCounts(BaseModel):
    total: int = 0
    system_roles: int = 0
    custom_roles: int = 0
