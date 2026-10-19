"""Add status and store_id to invoices with tenant unique constraint.

Revision ID: d7e8f9a0b1c2
Revises: c6d7e8f9a0b1
Create Date: 2026-10-09 13:45:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "d7e8f9a0b1c2"
down_revision: Union[str, None] = "c6d7e8f9a0b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()

    if "invoices" in tables:
        columns = {c["name"] for c in inspector.get_columns("invoices")}
        indexes = {i["name"] for i in inspector.get_indexes("invoices")}
        fks = {fk["name"] for fk in inspector.get_foreign_keys("invoices")}
        existing_uqs = {uq["name"] for uq in inspector.get_unique_constraints("invoices")}

        # 1. Add status column if not present
        if "status" not in columns:
            op.add_column(
                "invoices",
                sa.Column(
                    "status",
                    sa.String(30),
                    server_default=sa.text("'issued'"),
                    nullable=False,
                ),
            )
        if "ix_invoices_status" not in indexes:
            op.create_index("ix_invoices_status", "invoices", ["status"], unique=False)

        # 2. Add store_id column if not present
        if "store_id" not in columns:
            op.add_column(
                "invoices",
                sa.Column("store_id", sa.Integer(), nullable=True),
            )
        if "ix_invoices_store_id" not in indexes:
            op.create_index("ix_invoices_store_id", "invoices", ["store_id"], unique=False)
        if "fk_invoices_store_id" not in fks:
            op.create_foreign_key(
                "fk_invoices_store_id",
                "invoices",
                "stores",
                ["store_id"],
                ["id"],
            )

        # 3. Backfill status and store_id
        bind.execute(
            sa.text("UPDATE invoices SET status = 'issued' WHERE status IS NULL")
        )
        bind.execute(
            sa.text(
                "UPDATE invoices SET store_id = ("
                "SELECT store_id FROM orders WHERE orders.id = invoices.order_id"
                ") WHERE store_id IS NULL"
            )
        )

        # 4. Add tenant-scoped unique constraint for invoice numbers
        if "uq_invoices_tenant_invoice_number" not in existing_uqs:
            op.create_unique_constraint(
                "uq_invoices_tenant_invoice_number",
                "invoices",
                ["tenant_id", "invoice_number"],
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()

    if "invoices" in tables:
        columns = {c["name"] for c in inspector.get_columns("invoices")}
        indexes = {i["name"] for i in inspector.get_indexes("invoices")}
        fks = {fk["name"] for fk in inspector.get_foreign_keys("invoices")}
        existing_uqs = {uq["name"] for uq in inspector.get_unique_constraints("invoices")}

        if "uq_invoices_tenant_invoice_number" in existing_uqs:
            op.drop_constraint("uq_invoices_tenant_invoice_number", "invoices", type_="unique")

        if "fk_invoices_store_id" in fks:
            op.drop_constraint("fk_invoices_store_id", "invoices", type_="foreignkey")

        if "ix_invoices_store_id" in indexes:
            op.drop_index("ix_invoices_store_id", table_name="invoices")

        if "store_id" in columns:
            op.drop_column("invoices", "store_id")

        if "ix_invoices_status" in indexes:
            op.drop_index("ix_invoices_status", table_name="invoices")

        if "status" in columns:
            op.drop_column("invoices", "status")
