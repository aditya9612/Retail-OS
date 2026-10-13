from enum import Enum


class RoleEnum(str, Enum):
    ADMIN = "admin"
    OWNER = "owner"
    MANAGER = "manager"
    CASHIER = "cashier"
    INVENTORY_MANAGER = "inventory_manager"
    WAREHOUSE_STAFF = "warehouse_staff"
    PURCHASE_MANAGER = "purchase_manager"
    SALES_EXECUTIVE = "sales_executive"
    CRM_SUPPORT = "crm_support"


class UserRole(str, Enum):
    SUPERADMIN = "superadmin"
    ADMIN = "admin"
    OWNER = "owner"
    MANAGER = "manager"
    CASHIER = "cashier"
    INVENTORY_MANAGER = "inventory_manager"
    WAREHOUSE_STAFF = "warehouse_staff"
    PURCHASE_MANAGER = "purchase_manager"
    SALES_EXECUTIVE = "sales_executive"
    CRM_SUPPORT = "crm_support"
    # Legacy roles for backward compatibility
    ACCOUNTANT = "accountant"
    STAFF = "staff"


OFFICIAL_ROLES = [r.value for r in RoleEnum]


class OrderStatus(str, Enum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    RETURNED = "returned"
    REFUNDED = "refunded"


class OrderType(str, Enum):
    POS = "pos"
    ECOMMERCE = "ecommerce"


class PaymentMethod(str, Enum):
    CASH = "cash"
    UPI = "upi"
    CARD = "card"
    WALLET = "wallet"
    QR = "qr"


class PaymentStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"


class StockMovementType(str, Enum):
    STOCK_IN = "stock_in"
    STOCK_OUT = "stock_out"
    TRANSFER = "transfer"
    ADJUSTMENT = "adjustment"
    RETURN = "return"
    ALLOCATION = "allocation"


class InvoiceStatus(str, Enum):
    DRAFT = "draft"
    ISSUED = "issued"
    CANCELLED = "cancelled"


class RefundMethod(str, Enum):
    CASH = "cash"
    UPI = "upi"
    STORE_CREDIT = "store_credit"


class RefundStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class POSShiftStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"


class POSCashMovementType(str, Enum):
    CASH_DROP = "CASH_DROP"
    CASH_PAYOUT = "CASH_PAYOUT"
    CASH_IN = "CASH_IN"


DEFAULT_ROLE_PERMISSIONS = {
    UserRole.SUPERADMIN: [
        "*",
    ],

    UserRole.ADMIN: [
        "*",
    ],

    UserRole.OWNER: [
        "dashboard:view",
        "dashboard:read",
        "users:read",
        "users:write",
        "stores:read",
        "stores:write",
        "products:read",
        "products:write",
        "inventory:read",
        "inventory:write",
        "orders:read",
        "orders:write",
        "billing:read",
        "billing:write",
        "billing:refund",
        "billing:gst_config",
        "billing:price_override",
        "payments:read",
        "payments:write",
        "customers:read",
        "customers:write",
        "reports:read",
        "analytics:read",
        "purchase_orders:read",
        "purchase_orders:write",
        "pos:shift_manage",
    ],

    UserRole.MANAGER: [
        "dashboard:view",
        "dashboard:read",
        "stores:read",
        "users:read",
        "products:read",
        "inventory:read",
        "orders:read",
        "orders:write",
        "billing:read",
        "billing:write",
        "payments:read",
        "customers:read",
        "reports:read",
        "purchase_orders:read",
        "purchase_orders:write",
        "pos:shift_manage",
    ],

    UserRole.ACCOUNTANT: [
        "billing:read",
        "billing:write",
        "billing:refund",
        "billing:gst_config",
        "payments:read",
        "payments:write",
        "reports:read",
        "analytics:read",
        "credit_notes:read",
        "credit_notes:write",
        "purchase_orders:read",
        "customers:read",
        "invoices:read",
    ],

    UserRole.CASHIER: [
        "products:read",
        "inventory:read",
        "orders:read",
        "orders:write",
        "billing:read",
        "billing:write",
        "payments:read",
        "payments:write",
        "customers:read",
        "customers:write",
        "sales:read",
        "sales:write",
        "pos:shift_manage",
    ],

    UserRole.INVENTORY_MANAGER: [
        "products:read",
        "products:write",
        "categories:read",
        "categories:write",
        "inventory:read",
        "inventory:write",
        "batches:read",
        "batches:write",
        "purchase_orders:read",
        "purchase_orders:write",
        "suppliers:read",
        "reports:read",
    ],

    UserRole.WAREHOUSE_STAFF: [
        "products:read",
        "inventory:read",
        "inventory:write",
        "batches:read",
        "batches:write",
        "orders:read",
    ],

    UserRole.PURCHASE_MANAGER: [
        "products:read",
        "inventory:read",
        "purchase_orders:read",
        "purchase_orders:write",
        "suppliers:read",
        "suppliers:write",
        "reports:read",
    ],

    UserRole.SALES_EXECUTIVE: [
        "products:read",
        "orders:read",
        "orders:write",
        "sales:read",
        "sales:write",
        "customers:read",
        "customers:write",
        "coupons:read",
        "billing:read",
    ],

    UserRole.CRM_SUPPORT: [
        "customers:read",
        "customers:write",
        "reviews:read",
        "reviews:write",
        "orders:read",
        "reports:read",
    ],

    UserRole.STAFF: [
        "products:read",
        "inventory:read",
        "orders:read",
        "orders:write",
        "billing:read",
        "billing:write",
        "payments:read",
        "payments:write",
        "customers:read",
        "purchase_orders:read",
    ],
}

# Ensure DEFAULT_ROLE_PERMISSIONS is also indexable by string role name
for _r, _p in list(DEFAULT_ROLE_PERMISSIONS.items()):
    if isinstance(_r, UserRole):
        DEFAULT_ROLE_PERMISSIONS[_r.value] = _p