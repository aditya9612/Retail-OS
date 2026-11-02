"""add whatsapp settings and logs tables

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-11-02 18:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b4c5d6e7f8a9"
down_revision: Union[str, None] = "a3b4c5d6e7f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    if "whatsapp_settings" not in existing_tables:
        op.create_table(
            "whatsapp_settings",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.id"), nullable=True),
            sa.Column("phone_number_id", sa.String(50), nullable=True),
            sa.Column("business_account_id", sa.String(50), nullable=True),
            sa.Column("access_token", sa.Text(), nullable=True),
            sa.Column("webhook_verify_token", sa.String(100), nullable=True),
            sa.Column("is_enabled", sa.Boolean(), server_default=sa.text("1"), nullable=False),
            sa.Column("auto_send_invoice", sa.Boolean(), server_default=sa.text("1"), nullable=False),
            sa.Column("auto_send_order_confirm", sa.Boolean(), server_default=sa.text("1"), nullable=False),
            sa.Column("template_invoice", sa.String(100), server_default="pos_invoice_receipt", nullable=False),
            sa.Column("template_order_confirm", sa.String(100), server_default="order_confirmation", nullable=False),
            sa.Column("template_language", sa.String(20), server_default="en_US", nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
            sa.UniqueConstraint("tenant_id", "store_id", name="uq_whatsapp_settings_tenant_store"),
        )
        op.create_index("ix_whatsapp_settings_tenant_id", "whatsapp_settings", ["tenant_id"], unique=False)
        op.create_index("ix_whatsapp_settings_store_id", "whatsapp_settings", ["store_id"], unique=False)

    if "whatsapp_logs" not in existing_tables:
        op.create_table(
            "whatsapp_logs",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.id"), nullable=True),
            sa.Column("recipient_phone", sa.String(30), nullable=False),
            sa.Column("message_type", sa.String(50), server_default="invoice", nullable=False),
            sa.Column("template_name", sa.String(100), nullable=True),
            sa.Column("meta_message_id", sa.String(100), nullable=True),
            sa.Column("status", sa.String(30), server_default="queued", nullable=False),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("payload_snapshot", sa.JSON(), nullable=True),
            sa.Column("invoice_id", sa.Integer(), sa.ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True),
            sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        )
        op.create_index("ix_whatsapp_logs_tenant_id", "whatsapp_logs", ["tenant_id"], unique=False)
        op.create_index("ix_whatsapp_logs_store_id", "whatsapp_logs", ["store_id"], unique=False)
        op.create_index("ix_whatsapp_logs_recipient_phone", "whatsapp_logs", ["recipient_phone"], unique=False)
        op.create_index("ix_whatsapp_logs_message_type", "whatsapp_logs", ["message_type"], unique=False)
        op.create_index("ix_whatsapp_logs_meta_message_id", "whatsapp_logs", ["meta_message_id"], unique=False)
        op.create_index("ix_whatsapp_logs_status", "whatsapp_logs", ["status"], unique=False)
        op.create_index("ix_whatsapp_logs_invoice_id", "whatsapp_logs", ["invoice_id"], unique=False)
        op.create_index("ix_whatsapp_logs_order_id", "whatsapp_logs", ["order_id"], unique=False)


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    if "whatsapp_logs" in existing_tables:
        op.drop_table("whatsapp_logs")

    if "whatsapp_settings" in existing_tables:
        op.drop_table("whatsapp_settings")

