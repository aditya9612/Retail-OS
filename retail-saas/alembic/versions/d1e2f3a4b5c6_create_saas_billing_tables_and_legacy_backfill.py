"""create saas billing tables and legacy backfill

Revision ID: d1e2f3a4b5c6
Revises: 9599f1c1ddd1
Create Date: 2026-09-23 10:35:00.000000

"""
from datetime import timedelta
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import text


# revision identifiers, used by Alembic.
revision: str = 'd1e2f3a4b5c6'
down_revision: Union[str, None] = '9599f1c1ddd1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create saas_plans table
    op.create_table(
        "saas_plans",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("price", sa.Numeric(precision=10, scale=2), server_default="0.00", nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="INR", nullable=False),
        sa.Column("billing_interval", sa.String(length=20), server_default="monthly", nullable=False),
        sa.Column("trial_days", sa.Integer(), server_default="14", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_saas_plans_code"),
    )
    op.create_index("ix_saas_plans_is_active", "saas_plans", ["is_active"], unique=False)

    # 2. Create saas_subscriptions table
    op.create_table(
        "saas_subscriptions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), server_default="trialing", nullable=False),
        sa.Column("billing_interval", sa.String(length=20), server_default="monthly", nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="INR", nullable=False),
        sa.Column("start_date", sa.DateTime(), nullable=False),
        sa.Column("current_period_start", sa.DateTime(), nullable=False),
        sa.Column("current_period_end", sa.DateTime(), nullable=False),
        sa.Column("trial_end_date", sa.DateTime(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(), nullable=True),
        sa.Column("cancel_at_period_end", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["saas_plans.id"], name="fk_saas_sub_plan", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_saas_sub_tenant", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_saas_sub_tenant", "saas_subscriptions", ["tenant_id"], unique=False)
    op.create_index("ix_saas_sub_plan", "saas_subscriptions", ["plan_id"], unique=False)
    op.create_index("ix_saas_sub_status", "saas_subscriptions", ["status"], unique=False)
    op.create_index("ix_saas_sub_period_end", "saas_subscriptions", ["current_period_end"], unique=False)

    # 3. Create saas_invoices table
    op.create_table(
        "saas_invoices",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("subscription_id", sa.Integer(), nullable=False),
        sa.Column("invoice_number", sa.String(length=50), nullable=False),
        sa.Column("billing_reason", sa.String(length=30), server_default="subscription_cycle", nullable=False),
        sa.Column("subtotal", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("tax_amount", sa.Numeric(precision=10, scale=2), server_default="0.00", nullable=False),
        sa.Column("total_amount", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="INR", nullable=False),
        sa.Column("status", sa.String(length=30), server_default="unpaid", nullable=False),
        sa.Column("due_date", sa.DateTime(), nullable=False),
        sa.Column("paid_at", sa.DateTime(), nullable=True),
        sa.Column("pdf_url", sa.String(length=500), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["subscription_id"], ["saas_subscriptions.id"], name="fk_saas_inv_sub", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_saas_inv_tenant", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("invoice_number", name="uq_saas_inv_number"),
    )
    op.create_index("ix_saas_inv_tenant", "saas_invoices", ["tenant_id"], unique=False)
    op.create_index("ix_saas_inv_sub", "saas_invoices", ["subscription_id"], unique=False)
    op.create_index("ix_saas_inv_status", "saas_invoices", ["status"], unique=False)
    op.create_index("ix_saas_inv_due_date", "saas_invoices", ["due_date"], unique=False)

    # 4. Create saas_upi_transactions table
    op.create_table(
        "saas_upi_transactions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("subscription_id", sa.Integer(), nullable=False),
        sa.Column("invoice_id", sa.Integer(), nullable=False),
        sa.Column("reference", sa.String(length=64), nullable=False),
        sa.Column("utr", sa.String(length=50), nullable=True),
        sa.Column("amount", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="INR", nullable=False),
        sa.Column("status", sa.String(length=30), server_default="pending", nullable=False),
        sa.Column("upi_id", sa.String(length=100), nullable=False),
        sa.Column("payer_vpa", sa.String(length=100), nullable=True),
        sa.Column("submitted_at", sa.DateTime(), nullable=True),
        sa.Column("verified_at", sa.DateTime(), nullable=True),
        sa.Column("verified_by_super_admin_id", sa.Integer(), nullable=True),
        sa.Column("rejection_reason", sa.String(length=255), nullable=True),
        sa.Column("proof_image_url", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["invoice_id"], ["saas_invoices.id"], name="fk_saas_upi_inv", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["subscription_id"], ["saas_subscriptions.id"], name="fk_saas_upi_sub", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_saas_upi_tenant", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["verified_by_super_admin_id"], ["super_admins.id"], name="fk_saas_upi_admin", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("reference", name="uq_saas_upi_reference"),
    )
    op.create_index("ix_saas_upi_tenant", "saas_upi_transactions", ["tenant_id"], unique=False)
    op.create_index("ix_saas_upi_invoice", "saas_upi_transactions", ["invoice_id"], unique=False)
    op.create_index("ix_saas_upi_status", "saas_upi_transactions", ["status"], unique=False)
    op.create_index("ix_saas_upi_utr", "saas_upi_transactions", ["utr"], unique=False)

    # 5. Seed baseline plans
    bind = op.get_bind()
    plans_meta = sa.Table(
        "saas_plans",
        sa.MetaData(),
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String()),
        sa.Column("code", sa.String()),
        sa.Column("description", sa.Text()),
        sa.Column("price", sa.Numeric()),
        sa.Column("currency", sa.String()),
        sa.Column("billing_interval", sa.String()),
        sa.Column("trial_days", sa.Integer()),
        sa.Column("is_active", sa.Boolean()),
    )
    op.bulk_insert(
        plans_meta,
        [
            {
                "name": "Basic",
                "code": "basic",
                "description": "Essential retail management for single store operations.",
                "price": 999.00,
                "currency": "INR",
                "billing_interval": "monthly",
                "trial_days": 14,
                "is_active": True,
            },
            {
                "name": "Pro",
                "code": "pro",
                "description": "Advanced multi-store management, analytics, and delivery integrations.",
                "price": 2499.00,
                "currency": "INR",
                "billing_interval": "monthly",
                "trial_days": 14,
                "is_active": True,
            },
            {
                "name": "Enterprise",
                "code": "enterprise",
                "description": "Full platform capabilities with custom store limits and dedicated support.",
                "price": 4999.00,
                "currency": "INR",
                "billing_interval": "monthly",
                "trial_days": 0,
                "is_active": True,
            },
        ],
    )

    # Fetch inserted plan IDs
    plan_rows = bind.execute(text("SELECT id, code FROM saas_plans")).fetchall()
    plan_id_map = {row[1]: row[0] for row in plan_rows}

    # 6. Backfill existing legacy tenants into saas_subscriptions
    tenants = bind.execute(text("SELECT id, plan, subscription_status, created_at FROM tenants")).fetchall()
    subscriptions_to_insert = []
    projection_updates = []

    for t in tenants:
        t_id, t_plan, t_status, t_created_at = t[0], t[1], t[2], t[3]
        if t_status == "trial" or t_plan == "basic":
            # Map legacy trial / basic tenant
            p_id = plan_id_map.get("basic", 1)
            sub_status = "trialing"
            u_price = 0.00
            s_date = t_created_at
            period_start = t_created_at
            t_end_date = t_created_at + timedelta(days=14)
            period_end = t_end_date
        else:
            # Map pro / active tenant
            p_id = plan_id_map.get(t_plan, plan_id_map.get("pro", 2))
            sub_status = "active"
            u_price = 2499.00
            s_date = t_created_at
            period_start = t_created_at
            t_end_date = None
            period_end = t_created_at + timedelta(days=30)

        subscriptions_to_insert.append(
            {
                "tenant_id": t_id,
                "plan_id": p_id,
                "status": sub_status,
                "billing_interval": "monthly",
                "unit_price": u_price,
                "currency": "INR",
                "start_date": s_date,
                "current_period_start": period_start,
                "current_period_end": period_end,
                "trial_end_date": t_end_date,
                "cancelled_at": None,
                "cancel_at_period_end": False,
            }
        )
        projection_updates.append((period_end, t_id))

    if subscriptions_to_insert:
        subs_meta = sa.Table(
            "saas_subscriptions",
            sa.MetaData(),
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer()),
            sa.Column("plan_id", sa.Integer()),
            sa.Column("status", sa.String()),
            sa.Column("billing_interval", sa.String()),
            sa.Column("unit_price", sa.Numeric()),
            sa.Column("currency", sa.String()),
            sa.Column("start_date", sa.DateTime()),
            sa.Column("current_period_start", sa.DateTime()),
            sa.Column("current_period_end", sa.DateTime()),
            sa.Column("trial_end_date", sa.DateTime()),
            sa.Column("cancelled_at", sa.DateTime()),
            sa.Column("cancel_at_period_end", sa.Boolean()),
        )
        op.bulk_insert(subs_meta, subscriptions_to_insert)

    # 7. Synchronize tenant backward-compatibility projection: subscription_end_date
    for period_end, t_id in projection_updates:
        bind.execute(
            text("UPDATE tenants SET subscription_end_date = :end_date WHERE id = :t_id"),
            {"end_date": period_end, "t_id": t_id},
        )


def downgrade() -> None:
    # Drop tables in reverse dependency order
    op.drop_table("saas_upi_transactions")
    op.drop_table("saas_invoices")
    op.drop_table("saas_subscriptions")
    op.drop_table("saas_plans")
