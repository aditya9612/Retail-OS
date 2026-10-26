"""add storefront_settings and delivery enterprise fields

Revision ID: f124c4bb8654
Revises: d9e8f7a6b5c4
Create Date: 2026-10-21 15:45:29.571766

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = 'f124c4bb8654'
down_revision: Union[str, None] = 'd9e8f7a6b5c4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    # 1. Create storefront_settings table if it doesn't exist
    if "storefront_settings" not in existing_tables:
        op.create_table(
            "storefront_settings",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
            sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.id"), nullable=True, index=True),
            sa.Column("is_online", sa.Boolean(), default=True, nullable=False),
            # 1. Branding & Identity
            sa.Column("store_name", sa.String(255), default="RetailOS Shop", nullable=False),
            sa.Column("tagline", sa.String(500), default="Your trusted neighborhood store — now online", nullable=True),
            sa.Column("logo_url", sa.String(500), nullable=True),
            sa.Column("banner_url", sa.String(500), nullable=True),
            sa.Column("favicon_url", sa.String(500), nullable=True),
            sa.Column("primary_color", sa.String(20), default="#4f46e5", nullable=False),
            sa.Column("accent_color", sa.String(20), default="#10b981", nullable=False),
            sa.Column("theme_name", sa.String(50), default="modern_light", nullable=False),
            # 2. SEO & Domain Settings
            sa.Column("default_store_url", sa.String(255), default="retailos-shop.mystore.in", nullable=True),
            sa.Column("custom_domain", sa.String(255), nullable=True),
            sa.Column("url_slug", sa.String(100), default="retailos-shop", nullable=True),
            sa.Column("subdomain", sa.String(100), nullable=True),
            sa.Column("meta_title", sa.String(255), default="RetailOS Shop | Quality Products Online", nullable=True),
            sa.Column("meta_description", sa.Text(), nullable=True),
            sa.Column("meta_keywords", sa.String(500), default="retail, shop, online shopping, fresh goods", nullable=True),
            sa.Column("og_image_url", sa.String(500), nullable=True),
            sa.Column("canonical_url", sa.String(255), nullable=True),
            # 3. Custom Policy Pages
            sa.Column("about_us", sa.Text(), nullable=True),
            sa.Column("contact_us", sa.Text(), nullable=True),
            sa.Column("terms_and_conditions", sa.Text(), nullable=True),
            sa.Column("privacy_policy", sa.Text(), nullable=True),
            sa.Column("refund_policy", sa.Text(), nullable=True),
            sa.Column("shipping_policy", sa.Text(), nullable=True),
            sa.Column("faq", sa.Text(), nullable=True),
            # 4. Social Links & Analytics
            sa.Column("facebook_url", sa.String(255), nullable=True),
            sa.Column("instagram_url", sa.String(255), nullable=True),
            sa.Column("twitter_url", sa.String(255), nullable=True),
            sa.Column("youtube_url", sa.String(255), nullable=True),
            sa.Column("whatsapp_number", sa.String(20), nullable=True),
            sa.Column("google_analytics_id", sa.String(50), nullable=True),
            sa.Column("facebook_pixel_id", sa.String(50), nullable=True),
            # 5. Advanced eCommerce Feature Flags
            sa.Column("maintenance_mode", sa.Boolean(), default=False, nullable=False),
            sa.Column("maintenance_message", sa.String(500), default="We are currently performing maintenance. Please check back soon!", nullable=True),
            sa.Column("enable_product_reviews", sa.Boolean(), default=True, nullable=False),
            sa.Column("show_out_of_stock", sa.Boolean(), default=False, nullable=False),
            sa.Column("guest_checkout", sa.Boolean(), default=True, nullable=False),
            sa.Column("wishlist_enabled", sa.Boolean(), default=True, nullable=False),
            sa.Column("auto_sync_inventory", sa.Boolean(), default=True, nullable=False),
            sa.Column("enable_coupons", sa.Boolean(), default=True, nullable=False),
            sa.Column("gst_invoice_enabled", sa.Boolean(), default=True, nullable=False),
            # TimestampMixin
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"), nullable=False),
        )
        try:
            op.create_index("ix_storefront_tenant_store", "storefront_settings", ["tenant_id", "store_id"], unique=True)
        except Exception:
            pass

    # 2. Add delivery enterprise fields to deliveries table if missing
    if "deliveries" in existing_tables:
        del_columns = [c["name"] for c in inspector.get_columns("deliveries")]

        if "partner_id" not in del_columns:
            op.add_column("deliveries", sa.Column("partner_id", sa.Integer(), nullable=True))
            try:
                op.create_index("ix_deliveries_partner_id", "deliveries", ["partner_id"])
            except Exception:
                pass
            try:
                op.create_foreign_key("fk_deliveries_partner_id", "deliveries", "delivery_partners", ["partner_id"], ["id"])
            except Exception:
                pass

        if "delivery_method_id" not in del_columns:
            op.add_column("deliveries", sa.Column("delivery_method_id", sa.Integer(), nullable=True))
            try:
                op.create_index("ix_deliveries_delivery_method_id", "deliveries", ["delivery_method_id"])
            except Exception:
                pass
            try:
                op.create_foreign_key("fk_deliveries_delivery_method_id", "deliveries", "delivery_methods", ["delivery_method_id"], ["id"])
            except Exception:
                pass

        if "zone_id" not in del_columns:
            op.add_column("deliveries", sa.Column("zone_id", sa.Integer(), nullable=True))
            try:
                op.create_index("ix_deliveries_zone_id", "deliveries", ["zone_id"])
            except Exception:
                pass
            try:
                op.create_foreign_key("fk_deliveries_zone_id", "deliveries", "delivery_zones", ["zone_id"], ["id"])
            except Exception:
                pass

        if "is_cod" not in del_columns:
            op.add_column("deliveries", sa.Column("is_cod", sa.Boolean(), server_default=sa.text("0"), nullable=False))

        if "cod_amount" not in del_columns:
            op.add_column("deliveries", sa.Column("cod_amount", sa.Numeric(12, 2), server_default="0.00", nullable=False))

        if "cod_collected" not in del_columns:
            op.add_column("deliveries", sa.Column("cod_collected", sa.Boolean(), server_default=sa.text("0"), nullable=False))

        if "cod_collected_at" not in del_columns:
            op.add_column("deliveries", sa.Column("cod_collected_at", sa.DateTime(), nullable=True))

        if "dispatched_at" not in del_columns:
            op.add_column("deliveries", sa.Column("dispatched_at", sa.DateTime(), nullable=True))

        if "estimated_delivery_time" not in del_columns:
            op.add_column("deliveries", sa.Column("estimated_delivery_time", sa.DateTime(), nullable=True))

        if "delivery_slot" not in del_columns:
            op.add_column("deliveries", sa.Column("delivery_slot", sa.String(50), nullable=True))

        if "attempt_count" not in del_columns:
            op.add_column("deliveries", sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False))

        if "failure_reason" not in del_columns:
            op.add_column("deliveries", sa.Column("failure_reason", sa.String(255), nullable=True))

        if "delivery_otp" not in del_columns:
            op.add_column("deliveries", sa.Column("delivery_otp", sa.String(10), nullable=True))

        if "pod_image_url" not in del_columns:
            op.add_column("deliveries", sa.Column("pod_image_url", sa.String(255), nullable=True))

        if "recipient_signature" not in del_columns:
            op.add_column("deliveries", sa.Column("recipient_signature", sa.Text(), nullable=True))


def downgrade() -> None:
    # Downgrade drops storefront_settings
    op.drop_table("storefront_settings")
