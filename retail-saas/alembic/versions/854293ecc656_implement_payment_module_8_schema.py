"""implement payment module 8 schema

Revision ID: 854293ecc656
Revises: 2c654f7aecd9
Create Date: 2026-09-07 17:48:17.865790

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "854293ecc656"
down_revision: Union[str, None] = "2c654f7aecd9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "payments",
        sa.Column(
            "invoice_id",
            sa.Integer(),
            sa.ForeignKey("invoices.id"),
            nullable=True,
        ),
    )

    op.add_column(
        "payments",
        sa.Column(
            "customer_id",
            sa.Integer(),
            sa.ForeignKey("customers.id"),
            nullable=True,
        ),
    )

    op.add_column(
        "payments",
        sa.Column(
            "gateway_id",
            sa.Integer(),
            sa.ForeignKey("payment_gateways.id"),
            nullable=True,
        ),
    )

    op.add_column(
        "payments",
        sa.Column(
            "gateway_transaction_id",
            sa.String(length=100),
            nullable=True,
        ),
    )

    op.add_column(
        "payments",
        sa.Column(
            "paid_at",
            sa.DateTime(),
            nullable=True,
        ),
    )

    op.create_index(
        "ix_payments_invoice_id",
        "payments",
        ["invoice_id"],
    )

    op.create_index(
        "ix_payments_customer_id",
        "payments",
        ["customer_id"],
    )

    op.create_index(
        "ix_payments_gateway_id",
        "payments",
        ["gateway_id"],
    )

    op.create_index(
        "ix_payments_gateway_transaction_id",
        "payments",
        ["gateway_transaction_id"],
    )

    op.add_column(
        "payment_webhook_logs",
        sa.Column(
            "gateway_name",
            sa.String(length=100),
            nullable=True,
        ),
    )

    op.create_index(
        "ix_payment_webhook_logs_gateway_name",
        "payment_webhook_logs",
        ["gateway_name"],
    )

    op.add_column(
        "settlements",
        sa.Column(
            "settlement_reference",
            sa.String(length=100),
            nullable=True,
        ),
    )

    op.add_column(
        "settlements",
        sa.Column(
            "charges",
            sa.Numeric(12, 2),
            nullable=True,
        ),
    )

    op.add_column(
        "settlements",
        sa.Column(
            "settled_at",
            sa.DateTime(),
            nullable=True,
        ),
    )

    op.create_index(
        "ix_settlements_settlement_reference",
        "settlements",
        ["settlement_reference"],
    )

    op.add_column(
        "refunds",
        sa.Column(
            "transaction_id",
            sa.Integer(),
            sa.ForeignKey("payments.id"),
            nullable=True,
        ),
    )

    op.add_column(
        "refunds",
        sa.Column(
            "refund_reference",
            sa.String(length=100),
            nullable=True,
        ),
    )

    op.add_column(
        "refunds",
        sa.Column(
            "refund_status",
            sa.String(length=30),
            nullable=True,
        ),
    )

    op.add_column(
        "refunds",
        sa.Column(
            "initiated_at",
            sa.DateTime(),
            nullable=True,
        ),
    )

    op.create_index(
        "ix_refunds_transaction_id",
        "refunds",
        ["transaction_id"],
    )

    op.create_index(
        "ix_refunds_refund_reference",
        "refunds",
        ["refund_reference"],
    )

    op.create_index(
        "ix_refunds_refund_status",
        "refunds",
        ["refund_status"],
    )

    connection = op.get_bind()

    connection.execute(
        sa.text(
            """
            UPDATE payments p
            INNER JOIN orders o ON o.id = p.order_id
            SET p.customer_id = o.customer_id
            WHERE p.customer_id IS NULL
            """
        )
    )

    connection.execute(
        sa.text(
            """
            UPDATE payments p
            INNER JOIN invoices i ON i.order_id = p.order_id
            SET p.invoice_id = i.id
            WHERE p.invoice_id IS NULL
            """
        )
    )

    connection.execute(
        sa.text(
            """
            UPDATE payments
            SET gateway_transaction_id = transaction_id
            WHERE transaction_id IS NOT NULL
              AND transaction_id <> ''
              AND payment_method <> 'cash'
              AND gateway_transaction_id IS NULL
            """
        )
    )

    connection.execute(
        sa.text(
            """
            UPDATE refunds
            SET refund_status = status
            WHERE refund_status IS NULL
            """
        )
    )

    connection.execute(
        sa.text(
            """
            UPDATE settlements
            SET settlement_reference = reference_no
            WHERE reference_no IS NOT NULL
              AND reference_no <> ''
              AND settlement_reference IS NULL
            """
        )
    )


def downgrade() -> None:
    op.drop_index(
        "ix_refunds_refund_status",
        table_name="refunds",
    )

    op.drop_index(
        "ix_refunds_refund_reference",
        table_name="refunds",
    )

    op.drop_index(
        "ix_refunds_transaction_id",
        table_name="refunds",
    )

    op.drop_column(
        "refunds",
        "initiated_at",
    )

    op.drop_column(
        "refunds",
        "refund_status",
    )

    op.drop_column(
        "refunds",
        "refund_reference",
    )

    op.drop_column(
        "refunds",
        "transaction_id",
    )

    op.drop_index(
        "ix_settlements_settlement_reference",
        table_name="settlements",
    )

    op.drop_column(
        "settlements",
        "settled_at",
    )

    op.drop_column(
        "settlements",
        "charges",
    )

    op.drop_column(
        "settlements",
        "settlement_reference",
    )

    op.drop_index(
        "ix_payment_webhook_logs_gateway_name",
        table_name="payment_webhook_logs",
    )

    op.drop_column(
        "payment_webhook_logs",
        "gateway_name",
    )

    op.drop_index(
        "ix_payments_gateway_transaction_id",
        table_name="payments",
    )

    op.drop_index(
        "ix_payments_gateway_id",
        table_name="payments",
    )

    op.drop_index(
        "ix_payments_customer_id",
        table_name="payments",
    )

    op.drop_index(
        "ix_payments_invoice_id",
        table_name="payments",
    )

    op.drop_column(
        "payments",
        "paid_at",
    )

    op.drop_column(
        "payments",
        "gateway_transaction_id",
    )

    op.drop_column(
        "payments",
        "gateway_id",
    )

    op.drop_column(
        "payments",
        "customer_id",
    )

    op.drop_column(
        "payments",
        "invoice_id",
    )