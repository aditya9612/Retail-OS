"""initial schema

Revision ID: 001_initial
Revises:
Create Date: 2026-06-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())

    # 1. tenants
    if "tenants" not in existing_tables:
        op.create_table(
            "tenants",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("domain", sa.String(length=255), nullable=False),
            sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.Column("plan", sa.String(length=50), server_default=sa.text("'basic'"), nullable=False),
            sa.Column("subscription_status", sa.String(length=50), server_default=sa.text("'trial'"), nullable=False),
            sa.Column("subscription_end_date", sa.DateTime(), nullable=True),
            sa.Column("settings", sa.JSON(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("domain"),
        )

    # 2. roles
    # Historically, tenant_id was NOT NULL before migration 1365f19c2490 altered it to nullable.
    if "roles" not in existing_tables:
        op.create_table(
            "roles",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=100), nullable=False),
            sa.Column("permissions", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.Column("is_system", sa.Boolean(), server_default=sa.text("0"), nullable=False),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_roles_tenant_id", "roles", ["tenant_id"], unique=False)

    # 3. categories
    if "categories" not in existing_tables:
        op.create_table(
            "categories",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("parent_id", sa.Integer(), nullable=True),
            sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.ForeignKeyConstraint(["parent_id"], ["categories.id"]),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_categories_tenant_id", "categories", ["tenant_id"], unique=False)
        op.create_index("ix_categories_parent_id", "categories", ["parent_id"], unique=False)

    # 4. stores
    if "stores" not in existing_tables:
        op.create_table(
            "stores",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("address", sa.String(length=500), nullable=True),
            sa.Column("phone", sa.String(length=20), nullable=True),
            sa.Column("email", sa.String(length=255), nullable=True),
            sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.Column("is_main", sa.Boolean(), server_default=sa.text("0"), nullable=False),
            sa.Column("code", sa.String(length=50), nullable=True),
            sa.Column("city", sa.String(length=100), nullable=True),
            sa.Column("state", sa.String(length=100), nullable=True),
            sa.Column("pincode", sa.String(length=20), nullable=True),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_stores_tenant_id", "stores", ["tenant_id"], unique=False)
        op.create_index("ix_stores_code", "stores", ["code"], unique=False)

    # 5. warehouses
    # Historically, warehouses.code index was non-unique before 5d5148c6eff3 made it unique.
    if "warehouses" not in existing_tables:
        op.create_table(
            "warehouses",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("store_id", sa.Integer(), nullable=True),
            sa.Column("name", sa.String(length=100), nullable=False),
            sa.Column("code", sa.String(length=50), nullable=False),
            sa.Column("address", sa.Text(), nullable=True),
            sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.ForeignKeyConstraint(["store_id"], ["stores.id"]),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_warehouses_tenant_id", "warehouses", ["tenant_id"], unique=False)
        op.create_index("ix_warehouses_store_id", "warehouses", ["store_id"], unique=False)
        op.create_index("ix_warehouses_code", "warehouses", ["code"], unique=False)

    # 6. suppliers
    # Historically, is_active was NOT present until added by migration 85d54ffbe4d6.
    if "suppliers" not in existing_tables:
        op.create_table(
            "suppliers",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("contact_person", sa.String(length=255), nullable=True),
            sa.Column("email", sa.String(length=255), nullable=True),
            sa.Column("phone", sa.String(length=20), nullable=True),
            sa.Column("address", sa.String(length=500), nullable=True),
            sa.Column("gstin", sa.String(length=20), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_suppliers_tenant_id", "suppliers", ["tenant_id"], unique=False)

    # 7. coupons
    if "coupons" not in existing_tables:
        op.create_table(
            "coupons",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("code", sa.String(length=50), nullable=False),
            sa.Column("description", sa.String(length=255), nullable=True),
            sa.Column("discount_type", sa.String(length=20), nullable=False),
            sa.Column("discount_value", sa.Numeric(precision=10, scale=2), nullable=False),
            sa.Column("minimum_order_amount", sa.Numeric(precision=10, scale=2), server_default=sa.text("'0.00'"), nullable=False),
            sa.Column("maximum_discount", sa.Numeric(precision=10, scale=2), nullable=True),
            sa.Column("usage_limit", sa.Integer(), server_default=sa.text("'1'"), nullable=False),
            sa.Column("used_count", sa.Integer(), server_default=sa.text("'0'"), nullable=False),
            sa.Column("start_date", sa.Date(), nullable=False),
            sa.Column("end_date", sa.Date(), nullable=False),
            sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("code"),
        )
        op.create_index("ix_coupons_tenant_id", "coupons", ["tenant_id"], unique=False)

    # 8. customers
    # Historically:
    # - status, total_spend were added in 2e222a63103a
    # - segment was added in f520870f4226
    # - gstin was added in f1a2b3c4d5e6
    # - email and phone were non-unique indexes until bc7a49751a24
    if "customers" not in existing_tables:
        op.create_table(
            "customers",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("email", sa.String(length=255), nullable=True),
            sa.Column("phone", sa.String(length=20), nullable=False),
            sa.Column("address", sa.String(length=500), nullable=True),
            sa.Column("birthday", sa.Date(), nullable=True),
            sa.Column("loyalty_points", sa.Integer(), server_default=sa.text("'0'"), nullable=False),
            sa.Column("whatsapp_opt_in", sa.Boolean(), server_default=sa.text("1"), nullable=False),
            sa.Column("sms_opt_in", sa.Boolean(), server_default=sa.text("1"), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_customers_tenant_id", "customers", ["tenant_id"], unique=False)
        op.create_index("ix_customers_email", "customers", ["email"], unique=False)
        op.create_index("ix_customers_phone", "customers", ["phone"], unique=False)

    # 9. users
    # Historically, tenant_id was NOT NULL before migration 1365f19c2490 altered it to nullable.
    if "users" not in existing_tables:
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("role_id", sa.Integer(), nullable=False),
            sa.Column("store_id", sa.Integer(), nullable=True),
            sa.Column("email", sa.String(length=255), nullable=False),
            sa.Column("password_hash", sa.String(length=255), nullable=False),
            sa.Column("full_name", sa.String(length=255), nullable=False),
            sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.Column("phone", sa.String(length=20), nullable=True),
            sa.ForeignKeyConstraint(["role_id"], ["roles.id"]),
            sa.ForeignKeyConstraint(["store_id"], ["stores.id"]),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("email"),
        )
        op.create_index("ix_users_tenant_id", "users", ["tenant_id"], unique=False)
        op.create_index("ix_users_role_id", "users", ["role_id"], unique=False)
        op.create_index("ix_users_store_id", "users", ["store_id"], unique=False)

    # 10. audit_logs
    if "audit_logs" not in existing_tables:
        op.create_table(
            "audit_logs",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("action", sa.String(length=100), nullable=False),
            sa.Column("entity_type", sa.String(length=100), nullable=False),
            sa.Column("entity_id", sa.Integer(), nullable=True),
            sa.Column("old_values", sa.JSON(), nullable=True),
            sa.Column("new_values", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.Column("ip_address", sa.String(length=50), nullable=True),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_audit_logs_tenant_id", "audit_logs", ["tenant_id"], unique=False)
        op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"], unique=False)

    # 11. password_reset_tokens
    if "password_reset_tokens" not in existing_tables:
        op.create_table(
            "password_reset_tokens",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("token_hash", sa.String(length=255), nullable=False),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("used_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("token_hash"),
        )
        op.create_index("ix_password_reset_tokens_user_id", "password_reset_tokens", ["user_id"], unique=False)

    # 12. products
    if "products" not in existing_tables:
        op.create_table(
            "products",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("category_id", sa.Integer(), nullable=True),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("sku", sa.String(length=100), nullable=False),
            sa.Column("barcode", sa.String(length=100), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("cost_price", sa.Numeric(precision=10, scale=2), server_default=sa.text("'0.00'"), nullable=False),
            sa.Column("selling_price", sa.Numeric(precision=10, scale=2), server_default=sa.text("'0.00'"), nullable=False),
            sa.Column("tax_rate", sa.Numeric(precision=5, scale=2), server_default=sa.text("'0.00'"), nullable=False),
            sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.Column("hsn_code", sa.String(length=20), nullable=True),
            sa.Column("min_stock_alert", sa.Integer(), server_default=sa.text("'0'"), nullable=False),
            sa.Column("stock_status", sa.String(length=20), server_default=sa.text("'in_stock'"), nullable=False),
            sa.Column("brand", sa.String(length=100), nullable=True),
            sa.Column("unit", sa.String(length=20), server_default=sa.text("'piece'"), nullable=False),
            sa.ForeignKeyConstraint(["category_id"], ["categories.id"]),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("sku"),
        )
        op.create_index("ix_products_tenant_id", "products", ["tenant_id"], unique=False)
        op.create_index("ix_products_category_id", "products", ["category_id"], unique=False)
        op.create_index("ix_products_barcode", "products", ["barcode"], unique=False)

    # 13. product_images
    if "product_images" not in existing_tables:
        op.create_table(
            "product_images",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("product_id", sa.Integer(), nullable=False),
            sa.Column("image_url", sa.String(length=500), nullable=False),
            sa.Column("is_primary", sa.Boolean(), server_default=sa.text("0"), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_product_images_product_id", "product_images", ["product_id"], unique=False)

    # 14. inventory
    if "inventory" not in existing_tables:
        op.create_table(
            "inventory",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("store_id", sa.Integer(), nullable=False),
            sa.Column("product_id", sa.Integer(), nullable=False),
            sa.Column("quantity", sa.Integer(), server_default=sa.text("'0'"), nullable=False),
            sa.Column("min_stock_level", sa.Integer(), server_default=sa.text("'0'"), nullable=False),
            sa.Column("max_stock_level", sa.Integer(), server_default=sa.text("'0'"), nullable=False),
            sa.Column("reorder_point", sa.Integer(), server_default=sa.text("'0'"), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
            sa.ForeignKeyConstraint(["store_id"], ["stores.id"]),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_inventory_tenant_id", "inventory", ["tenant_id"], unique=False)
        op.create_index("ix_inventory_store_id", "inventory", ["store_id"], unique=False)
        op.create_index("ix_inventory_product_id", "inventory", ["product_id"], unique=False)

    # 15. purchase_orders
    if "purchase_orders" not in existing_tables:
        op.create_table(
            "purchase_orders",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("supplier_id", sa.Integer(), nullable=False),
            sa.Column("order_number", sa.String(length=100), nullable=False),
            sa.Column("status", sa.String(length=50), server_default=sa.text("'draft'"), nullable=False),
            sa.Column("total_amount", sa.Numeric(precision=12, scale=2), server_default=sa.text("'0.00'"), nullable=False),
            sa.Column("expected_delivery_date", sa.Date(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"]),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("order_number"),
        )
        op.create_index("ix_purchase_orders_tenant_id", "purchase_orders", ["tenant_id"], unique=False)
        op.create_index("ix_purchase_orders_supplier_id", "purchase_orders", ["supplier_id"], unique=False)

    # 16. purchase_order_items
    if "purchase_order_items" not in existing_tables:
        op.create_table(
            "purchase_order_items",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("po_id", sa.Integer(), nullable=False),
            sa.Column("product_id", sa.Integer(), nullable=False),
            sa.Column("quantity", sa.Integer(), nullable=False),
            sa.Column("unit_cost", sa.Numeric(precision=10, scale=2), nullable=False),
            sa.Column("total_cost", sa.Numeric(precision=12, scale=2), nullable=False),
            sa.Column("received_quantity", sa.Integer(), server_default=sa.text("'0'"), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.ForeignKeyConstraint(["po_id"], ["purchase_orders.id"]),
            sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_purchase_order_items_po_id", "purchase_order_items", ["po_id"], unique=False)
        op.create_index("ix_purchase_order_items_product_id", "purchase_order_items", ["product_id"], unique=False)

    # 17. orders
    if "orders" not in existing_tables:
        op.create_table(
            "orders",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("store_id", sa.Integer(), nullable=False),
            sa.Column("customer_id", sa.Integer(), nullable=True),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("order_number", sa.String(length=100), nullable=False),
            sa.Column("order_type", sa.String(length=20), server_default=sa.text("'pos'"), nullable=False),
            sa.Column("status", sa.String(length=20), server_default=sa.text("'completed'"), nullable=False),
            sa.Column("subtotal", sa.Numeric(precision=12, scale=2), server_default=sa.text("'0.00'"), nullable=False),
            sa.Column("discount_amount", sa.Numeric(precision=12, scale=2), server_default=sa.text("'0.00'"), nullable=False),
            sa.Column("tax_amount", sa.Numeric(precision=12, scale=2), server_default=sa.text("'0.00'"), nullable=False),
            sa.Column("total_amount", sa.Numeric(precision=12, scale=2), server_default=sa.text("'0.00'"), nullable=False),
            sa.Column("payment_status", sa.String(length=20), server_default=sa.text("'paid'"), nullable=False),
            sa.Column("notes", sa.String(length=500), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.Column("delivery_address", sa.String(length=500), nullable=True),
            sa.Column("delivery_pincode", sa.String(length=20), nullable=True),
            sa.ForeignKeyConstraint(["customer_id"], ["customers.id"]),
            sa.ForeignKeyConstraint(["store_id"], ["stores.id"]),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("order_number"),
        )
        op.create_index("ix_orders_tenant_id", "orders", ["tenant_id"], unique=False)
        op.create_index("ix_orders_store_id", "orders", ["store_id"], unique=False)
        op.create_index("ix_orders_customer_id", "orders", ["customer_id"], unique=False)
        op.create_index("ix_orders_user_id", "orders", ["user_id"], unique=False)

    # 18. order_items
    if "order_items" not in existing_tables:
        op.create_table(
            "order_items",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("order_id", sa.Integer(), nullable=False),
            sa.Column("product_id", sa.Integer(), nullable=False),
            sa.Column("quantity", sa.Integer(), nullable=False),
            sa.Column("unit_price", sa.Numeric(precision=10, scale=2), nullable=False),
            sa.Column("discount_amount", sa.Numeric(precision=10, scale=2), server_default=sa.text("'0.00'"), nullable=False),
            sa.Column("tax_amount", sa.Numeric(precision=10, scale=2), server_default=sa.text("'0.00'"), nullable=False),
            sa.Column("total_amount", sa.Numeric(precision=10, scale=2), nullable=False),
            sa.Column("notes", sa.String(length=255), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.Column("cgst_amount", sa.Numeric(precision=12, scale=2), server_default=sa.text("'0.00'"), nullable=False),
            sa.Column("sgst_amount", sa.Numeric(precision=12, scale=2), server_default=sa.text("'0.00'"), nullable=False),
            sa.Column("igst_amount", sa.Numeric(precision=12, scale=2), server_default=sa.text("'0.00'"), nullable=False),
            sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
            sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_order_items_order_id", "order_items", ["order_id"], unique=False)
        op.create_index("ix_order_items_product_id", "order_items", ["product_id"], unique=False)

    # 19. order_tracking
    if "order_tracking" not in existing_tables:
        op.create_table(
            "order_tracking",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("order_id", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=50), nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("updated_by", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_order_tracking_order_id", "order_tracking", ["order_id"], unique=False)

    # 20. invoices
    if "invoices" not in existing_tables:
        op.create_table(
            "invoices",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("order_id", sa.Integer(), nullable=False),
            sa.Column("invoice_number", sa.String(length=100), nullable=False),
            sa.Column("subtotal", sa.Numeric(precision=12, scale=2), server_default=sa.text("'0.00'"), nullable=False),
            sa.Column("discount_amount", sa.Numeric(precision=12, scale=2), server_default=sa.text("'0.00'"), nullable=False),
            sa.Column("tax_amount", sa.Numeric(precision=12, scale=2), server_default=sa.text("'0.00'"), nullable=False),
            sa.Column("total_amount", sa.Numeric(precision=12, scale=2), server_default=sa.text("'0.00'"), nullable=False),
            sa.Column("pdf_url", sa.String(length=500), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.Column("cgst_amount", sa.Numeric(precision=12, scale=2), server_default=sa.text("'0.00'"), nullable=False),
            sa.Column("sgst_amount", sa.Numeric(precision=12, scale=2), server_default=sa.text("'0.00'"), nullable=False),
            sa.Column("igst_amount", sa.Numeric(precision=12, scale=2), server_default=sa.text("'0.00'"), nullable=False),
            sa.Column("is_b2b", sa.Boolean(), server_default=sa.text("0"), nullable=False),
            sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("invoice_number"),
        )
        op.create_index("ix_invoices_tenant_id", "invoices", ["tenant_id"], unique=False)
        op.create_index("ix_invoices_order_id", "invoices", ["order_id"], unique=False)

    # 21. sales
    if "sales" not in existing_tables:
        op.create_table(
            "sales",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("store_id", sa.Integer(), nullable=False),
            sa.Column("sale_number", sa.String(length=100), nullable=False),
            sa.Column("subtotal", sa.Numeric(precision=12, scale=2), server_default=sa.text("'0.00'"), nullable=False),
            sa.Column("tax_amount", sa.Numeric(precision=12, scale=2), server_default=sa.text("'0.00'"), nullable=False),
            sa.Column("total_amount", sa.Numeric(precision=12, scale=2), server_default=sa.text("'0.00'"), nullable=False),
            sa.Column("payment_method", sa.String(length=50), nullable=False),
            sa.Column("payment_status", sa.String(length=50), server_default=sa.text("'paid'"), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.ForeignKeyConstraint(["store_id"], ["stores.id"]),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("sale_number"),
        )
        op.create_index("ix_sales_tenant_id", "sales", ["tenant_id"], unique=False)
        op.create_index("ix_sales_store_id", "sales", ["store_id"], unique=False)

    # 22. sale_items
    if "sale_items" not in existing_tables:
        op.create_table(
            "sale_items",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("sale_id", sa.Integer(), nullable=False),
            sa.Column("product_id", sa.Integer(), nullable=False),
            sa.Column("quantity", sa.Integer(), nullable=False),
            sa.Column("unit_price", sa.Numeric(precision=10, scale=2), nullable=False),
            sa.Column("tax_rate", sa.Numeric(precision=5, scale=2), server_default=sa.text("'0.00'"), nullable=False),
            sa.Column("tax_amount", sa.Numeric(precision=10, scale=2), server_default=sa.text("'0.00'"), nullable=False),
            sa.Column("total_price", sa.Numeric(precision=12, scale=2), nullable=False),
            sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
            sa.ForeignKeyConstraint(["sale_id"], ["sales.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_sale_items_sale_id", "sale_items", ["sale_id"], unique=False)
        op.create_index("ix_sale_items_product_id", "sale_items", ["product_id"], unique=False)

    # 23. payments
    # Historically: invoice_id, customer_id, gateway_id, gateway_transaction_id, paid_at
    # were added later in migration 854293ecc656.
    if "payments" not in existing_tables:
        op.create_table(
            "payments",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("order_id", sa.Integer(), nullable=False),
            sa.Column("payment_method", sa.String(length=30), nullable=False),
            sa.Column("status", sa.String(length=30), nullable=False),
            sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
            sa.Column("transaction_id", sa.String(length=100), nullable=True),
            sa.Column("gateway_response", sa.String(length=1000), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_payments_tenant_id", "payments", ["tenant_id"], unique=False)
        op.create_index("ix_payments_order_id", "payments", ["order_id"], unique=False)
        op.create_index("ix_payments_transaction_id", "payments", ["transaction_id"], unique=False)

    # 24. payment_gateways
    if "payment_gateways" not in existing_tables:
        op.create_table(
            "payment_gateways",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=50), nullable=False),
            sa.Column("provider", sa.String(length=50), nullable=False),
            sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
            sa.Column("api_key", sa.String(length=255), nullable=True),
            sa.Column("api_secret", sa.String(length=255), nullable=True),
            sa.Column("webhook_secret", sa.String(length=255), nullable=True),
            sa.Column("config", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_payment_gateways_tenant_id", "payment_gateways", ["tenant_id"], unique=False)

    # 25. payment_splits
    if "payment_splits" not in existing_tables:
        op.create_table(
            "payment_splits",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("payment_id", sa.Integer(), nullable=False),
            sa.Column("payment_method", sa.String(length=50), nullable=False),
            sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
            sa.Column("status", sa.String(length=20), server_default=sa.text("'COMPLETED'"), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.ForeignKeyConstraint(["payment_id"], ["payments.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_payment_splits_payment_id", "payment_splits", ["payment_id"], unique=False)

    # 26. payment_webhook_logs
    # Historically, gateway_name was added in migration 854293ecc656.
    if "payment_webhook_logs" not in existing_tables:
        op.create_table(
            "payment_webhook_logs",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("event_type", sa.String(length=100), nullable=False),
            sa.Column("transaction_id", sa.String(length=100), nullable=False),
            sa.Column("payload", sa.Text(), nullable=False),
            sa.Column("status", sa.String(length=20), server_default=sa.text("'PENDING'"), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_payment_webhook_logs_tenant_id", "payment_webhook_logs", ["tenant_id"], unique=False)
        op.create_index("ix_payment_webhook_logs_transaction_id", "payment_webhook_logs", ["transaction_id"], unique=False)

    # 27. settlements
    # Historically, settlement_reference, charges, settled_at were added in 854293ecc656.
    if "settlements" not in existing_tables:
        op.create_table(
            "settlements",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("gateway_id", sa.Integer(), nullable=False),
            sa.Column("settlement_date", sa.Date(), nullable=False),
            sa.Column("total_amount", sa.Numeric(precision=12, scale=2), nullable=False),
            sa.Column("status", sa.String(length=20), server_default=sa.text("'PENDING'"), nullable=False),
            sa.Column("reference_no", sa.String(length=100), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.ForeignKeyConstraint(["gateway_id"], ["payment_gateways.id"]),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_settlements_tenant_id", "settlements", ["tenant_id"], unique=False)
        op.create_index("ix_settlements_gateway_id", "settlements", ["gateway_id"], unique=False)

    # 28. stock_movements
    if "stock_movements" not in existing_tables:
        op.create_table(
            "stock_movements",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("product_id", sa.Integer(), nullable=False),
            sa.Column("store_id", sa.Integer(), nullable=False),
            sa.Column("movement_type", sa.String(length=50), nullable=False),
            sa.Column("quantity", sa.Integer(), nullable=False),
            sa.Column("previous_stock", sa.Integer(), nullable=False),
            sa.Column("new_stock", sa.Integer(), nullable=False),
            sa.Column("reference_id", sa.Integer(), nullable=True),
            sa.Column("reference_type", sa.String(length=50), nullable=True),
            sa.Column("notes", sa.String(length=255), nullable=True),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
            sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
            sa.ForeignKeyConstraint(["store_id"], ["stores.id"]),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_stock_movements_tenant_id", "stock_movements", ["tenant_id"], unique=False)
        op.create_index("ix_stock_movements_product_id", "stock_movements", ["product_id"], unique=False)
        op.create_index("ix_stock_movements_store_id", "stock_movements", ["store_id"], unique=False)


def downgrade() -> None:
    tables_in_reverse = [
        "stock_movements",
        "settlements",
        "payment_webhook_logs",
        "payment_splits",
        "payment_gateways",
        "payments",
        "sale_items",
        "sales",
        "invoices",
        "order_tracking",
        "order_items",
        "orders",
        "purchase_order_items",
        "purchase_orders",
        "inventory",
        "product_images",
        "products",
        "password_reset_tokens",
        "audit_logs",
        "users",
        "customers",
        "coupons",
        "suppliers",
        "warehouses",
        "stores",
        "categories",
        "roles",
        "tenants",
    ]
    bind = op.get_bind()
    inspector = inspect(bind)
    existing = set(inspector.get_table_names())
    for tbl in tables_in_reverse:
        if tbl in existing:
            op.drop_table(tbl)
