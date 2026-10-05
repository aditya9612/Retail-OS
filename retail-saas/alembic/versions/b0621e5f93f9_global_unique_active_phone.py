"""global_unique_active_phone

Revision ID: b0621e5f93f9
Revises: 631e3011e13c
Create Date: 2026-10-01 18:11:31.189534

Replace tenant-scoped UNIQUE(tenant_id, active_phone) with
global UNIQUE(active_phone) to enforce:
  ONE mobile number = ONE active user across the entire platform.

Prerequisites:
  - No duplicate active_phone values exist across tenants.
  - active_phone is a VIRTUAL GENERATED column:
    IF(is_deleted = 0 AND phone IS NOT NULL AND phone != '', phone, NULL)
  - Soft-deleted users have active_phone = NULL and do not participate
    in the unique constraint.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b0621e5f93f9'
down_revision: Union[str, None] = '631e3011e13c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _constraint_or_index_exists(table_name: str, name: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    uq_names = {c["name"] for c in insp.get_unique_constraints(table_name) if c.get("name")}
    idx_names = {i["name"] for i in insp.get_indexes(table_name) if i.get("name")}
    return name in uq_names or name in idx_names


def _drop_constraint_or_index_if_exists(table_name: str, name: str) -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    uq_names = {c["name"] for c in insp.get_unique_constraints(table_name) if c.get("name")}
    idx_names = {i["name"] for i in insp.get_indexes(table_name) if i.get("name")}
    if name in uq_names:
        op.drop_constraint(name, table_name, type_="unique")
    elif name in idx_names:
        op.drop_index(name, table_name=table_name)


def upgrade() -> None:
    # 1. Drop the tenant-scoped unique constraint if it exists
    _drop_constraint_or_index_if_exists("users", "uq_users_tenant_active_phone")

    # 2. Create global unique constraint on active_phone only
    if not _constraint_or_index_exists("users", "uq_users_active_phone"):
        op.create_unique_constraint(
            "uq_users_active_phone",
            "users",
            ["active_phone"],
        )


def downgrade() -> None:
    # 1. Drop the global unique constraint if it exists
    _drop_constraint_or_index_if_exists("users", "uq_users_active_phone")

    # 2. Restore tenant-scoped unique constraint for down_revision 631e3011e13c
    if not _constraint_or_index_exists("users", "uq_users_tenant_active_phone"):
        op.create_unique_constraint(
            "uq_users_tenant_active_phone",
            "users",
            ["tenant_id", "active_phone"],
        )
