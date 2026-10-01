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

This migration does NOT alter:
  - The active_phone generated expression
  - The phone column type or definition
  - tenant_id, is_deleted, or any unrelated columns/indexes
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b0621e5f93f9'
down_revision: Union[str, None] = '631e3011e13c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Drop the tenant-scoped unique constraint
    op.drop_constraint("uq_users_tenant_active_phone", "users", type_="unique")

    # 2. Create global unique constraint on active_phone only
    op.create_unique_constraint(
        "uq_users_active_phone",
        "users",
        ["active_phone"],
    )


def downgrade() -> None:
    # 1. Drop the global unique constraint
    op.drop_constraint("uq_users_active_phone", "users", type_="unique")

    # 2. Restore tenant-scoped unique constraint
    op.create_unique_constraint(
        "uq_users_tenant_active_phone",
        "users",
        ["tenant_id", "active_phone"],
    )
