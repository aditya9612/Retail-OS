"""Add customer GSTIN and backfill manager role.

Revision ID: f1a2b3c4d5e6
Revises: e7f8a9b0c1d2
Create Date: 2026-07-21
"""

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, None] = "e7f8a9b0c1d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MANAGER_PERMISSIONS = [
    "products:read",
    "inventory:read",
    "orders:read",
    "orders:write",
    "billing:read",
    "billing:write",
    "payments:read",
    "customers:read",
    "reports:read",
]


def upgrade() -> None:
    op.add_column("customers", sa.Column("gstin", sa.String(length=20), nullable=True))
    op.create_index(op.f("ix_customers_gstin"), "customers", ["gstin"], unique=False)

    conn = op.get_bind()
    tenants = conn.execute(sa.text("SELECT id FROM tenants")).fetchall()
    for (tenant_id,) in tenants:
        existing = conn.execute(
            sa.text("SELECT id FROM roles WHERE tenant_id = :tid AND name = 'manager'"),
            {"tid": tenant_id},
        ).first()
        if existing:
            continue
        conn.execute(
            sa.text(
                "INSERT INTO roles (tenant_id, name, description, permissions, created_at, updated_at) "
                "VALUES (:tid, 'manager', 'Store manager', :perms, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            {"tid": tenant_id, "perms": json.dumps(MANAGER_PERMISSIONS)},
        )


def downgrade() -> None:
    op.drop_index(op.f("ix_customers_gstin"), table_name="customers")
    op.drop_column("customers", "gstin")
    op.execute(sa.text("DELETE FROM roles WHERE name = 'manager'"))
