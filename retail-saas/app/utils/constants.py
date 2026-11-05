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
        "*",
    ],
    UserRole.MANAGER: [],
    UserRole.ACCOUNTANT: [],
    UserRole.CASHIER: [],
    UserRole.INVENTORY_MANAGER: [],
    UserRole.WAREHOUSE_STAFF: [],
    UserRole.PURCHASE_MANAGER: [],
    UserRole.SALES_EXECUTIVE: [],
    UserRole.CRM_SUPPORT: [],
    UserRole.STAFF: [],
}

# Ensure DEFAULT_ROLE_PERMISSIONS is also indexable by string role name
for _r, _p in list(DEFAULT_ROLE_PERMISSIONS.items()):
    if isinstance(_r, UserRole):
        DEFAULT_ROLE_PERMISSIONS[_r.value] = _p
