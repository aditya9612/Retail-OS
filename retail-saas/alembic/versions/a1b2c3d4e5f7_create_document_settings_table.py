"""create_document_settings_table

Revision ID: a1b2c3d4e5f7
Revises: f2a3b4c5d6e7
Create Date: 2026-10-04 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f7'
down_revision: Union[str, None] = 'f2a3b4c5d6e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "document_settings" not in tables:
        op.create_table(
            "document_settings",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
            sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.id"), nullable=True, index=True),
            sa.Column("business_name", sa.String(255), nullable=True),
            sa.Column("address", sa.String(500), nullable=True),
            sa.Column("phone", sa.String(20), nullable=True),
            sa.Column("email", sa.String(255), nullable=True),
            sa.Column("website", sa.String(255), nullable=True),
            sa.Column("gstin", sa.String(30), nullable=True),
            sa.Column("footer_text", sa.String(500), nullable=True),
            sa.Column("invoice_prefix", sa.String(20), nullable=True),
            sa.Column("bill_prefix", sa.String(20), nullable=True),
            sa.Column("show_gstin", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("show_qr", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("show_signature", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("show_payment_details", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("logo_path", sa.String(500), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("tenant_id", "store_id", name="uq_document_setting_tenant_store"),
        )


def downgrade() -> None:
    op.drop_table("document_settings")
