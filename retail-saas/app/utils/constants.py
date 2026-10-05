from enum import Enum


class UserRole(str, Enum):
    SUPERADMIN = "superadmin"
    ADMIN = "admin"
    OWNER = "owner"
    MANAGER = "manager"
    ACCOUNTANT = "accountant"
    CASHIER = "cashier"
    STAFF = "staff"


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