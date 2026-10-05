"""create_product_variants_table

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b9
Create Date: 2026-10-05 17:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'c3d4e5f6a7b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "product_variants" not in tables:
        op.create_table(
            "product_variants",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False, index=True),
            sa.Column(
                "product_id",
                sa.Integer(),
                sa.ForeignKey("products.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column("variant_name", sa.String(255), nullable=False),
            sa.Column("sku", sa.String(100), nullable=False, index=True),
            sa.Column("barcode", sa.String(100), nullable=True, index=True),
            sa.Column("size", sa.String(50), nullable=True),
            sa.Column("color", sa.String(50), nullable=True),
            sa.Column("attributes", sa.JSON(), nullable=True),
            sa.Column("selling_price", sa.Numeric(12, 2), nullable=True),
            sa.Column("cost_price", sa.Numeric(10, 2), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index(
            "ix_product_variants_tenant_sku",
            "product_variants",
            ["tenant_id", "sku"],
            unique=True,
        )
        op.create_index(
            "ix_product_variants_tenant_barcode",
            "product_variants",
            ["tenant_id", "barcode"],
        )
        op.create_index(
            "ix_product_variants_product_active",
            "product_variants",
            ["product_id", "is_active"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "product_variants" in tables:
        try:
            op.drop_index("ix_product_variants_product_active", table_name="product_variants")
            op.drop_index("ix_product_variants_tenant_barcode", table_name="product_variants")
            op.drop_index("ix_product_variants_tenant_sku", table_name="product_variants")
        except Exception:
            pass
        op.drop_table("product_variants")

