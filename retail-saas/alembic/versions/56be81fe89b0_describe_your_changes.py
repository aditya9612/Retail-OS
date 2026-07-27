"""describe your changes

Revision ID: 56be81fe89b0
Revises: e3e6dac8ae04
Create Date: 2026-07-24 13:22:57.019243

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = '56be81fe89b0'
down_revision: Union[str, None] = 'e3e6dac8ae04'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())

    # --- Create missing tables (safe for DBs where create_all already ran) ---

    if "customer_feedback" not in existing_tables:
        op.create_table(
            "customer_feedback",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False),
            sa.Column("invoice_id", sa.Integer(), sa.ForeignKey("invoices.id"), nullable=True),
            sa.Column("rating", sa.Integer(), nullable=False),
            sa.Column("comments", sa.Text(), nullable=True),
            sa.Column("suggestions", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"), nullable=False),
        )

    if "loyalty_points" not in existing_tables:
        op.create_table(
            "loyalty_points",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False),
            sa.Column("invoice_id", sa.Integer(), sa.ForeignKey("invoices.id"), nullable=True),
            sa.Column("points_earned", sa.Integer(), server_default=sa.text("'0'"), nullable=False),
            sa.Column("points_redeemed", sa.Integer(), server_default=sa.text("'0'"), nullable=False),
            sa.Column("balance_points", sa.Integer(), server_default=sa.text("'0'"), nullable=False),
            sa.Column("expiry_date", sa.Date(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"), nullable=False),
        )

    if "customer_wallets" not in existing_tables:
        op.create_table(
            "customer_wallets",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False, unique=True),
            sa.Column("current_balance", sa.Numeric(precision=12, scale=2), server_default=sa.text("'0.00'"), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"), nullable=False),
        )

    if "wallet_transactions" not in existing_tables:
        op.create_table(
            "wallet_transactions",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("wallet_id", sa.Integer(), sa.ForeignKey("customer_wallets.id"), nullable=False),
            sa.Column("transaction_type", sa.Enum("CREDIT", "DEBIT", name="wallet_transaction_type"), nullable=False),
            sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
            sa.Column("reference_no", sa.String(100), nullable=True),
            sa.Column("remarks", sa.String(255), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        )

    if "customer_referrals" not in existing_tables:
        op.create_table(
            "customer_referrals",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False),
            sa.Column("referral_code", sa.String(50), unique=True, nullable=False),
            sa.Column("referred_customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=True),
            sa.Column("reward_amount", sa.Numeric(precision=12, scale=2), server_default=sa.text("'0.00'"), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"), nullable=False),
        )

    if "customer_notes" not in existing_tables:
        op.create_table(
            "customer_notes",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False),
            sa.Column("note", sa.Text(), nullable=False),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"), nullable=True),
        )

    if "customer_communications" not in existing_tables:
        op.create_table(
            "customer_communications",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False),
            sa.Column("communication_type", sa.Enum("SMS", "WHATSAPP", "EMAIL"), nullable=False),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("delivery_status", sa.Enum("PENDING", "SENT", "FAILED"), nullable=False, server_default=sa.text("'SENT'")),
            sa.Column("sent_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        )

    # --- Indexes (only if missing) ---
    # Refresh inspector after potential table creation
    inspector = inspect(bind)

    def _has_index(table, index_name):
        try:
            return index_name in {idx["name"] for idx in inspector.get_indexes(table)}
        except Exception:
            return False

    if not _has_index("customer_communications", op.f("ix_customer_communications_id")):
        op.create_index(op.f("ix_customer_communications_id"), "customer_communications", ["id"], unique=False)

    if not _has_index("customer_notes", op.f("ix_customer_notes_id")):
        op.create_index(op.f("ix_customer_notes_id"), "customer_notes", ["id"], unique=False)

    # --- Alter existing tables (only if they existed before this migration) ---
    # These alter/constraint ops only apply to DBs where the tables were created
    # by an older create_all with slightly different schema. For fresh DBs the
    # tables above already have the correct schema, so we skip.

    if "customer_feedback" in existing_tables:
        op.alter_column('customer_feedback', 'created_at',
                   existing_type=mysql.DATETIME(),
                   nullable=False,
                   existing_server_default=sa.text('CURRENT_TIMESTAMP'))
        op.alter_column('customer_feedback', 'updated_at',
                   existing_type=mysql.DATETIME(),
                   nullable=False,
                   existing_server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'))
        try:
            op.drop_constraint(op.f('fk_feedback_invoice'), 'customer_feedback', type_='foreignkey')
            op.drop_constraint(op.f('fk_feedback_customer'), 'customer_feedback', type_='foreignkey')
        except Exception:
            pass
        op.create_foreign_key(None, 'customer_feedback', 'customers', ['customer_id'], ['id'])
        op.create_foreign_key(None, 'customer_feedback', 'invoices', ['invoice_id'], ['id'])

    if "customer_notes" in existing_tables:
        op.alter_column('customer_notes', 'created_at',
                   existing_type=mysql.TIMESTAMP(),
                   type_=sa.DateTime(),
                   existing_nullable=True,
                   existing_server_default=sa.text('CURRENT_TIMESTAMP'))
        op.alter_column('customer_notes', 'updated_at',
                   existing_type=mysql.TIMESTAMP(),
                   type_=sa.DateTime(),
                   existing_nullable=True,
                   existing_server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'))

    if "customer_referrals" in existing_tables:
        op.alter_column('customer_referrals', 'reward_amount',
                   existing_type=mysql.DECIMAL(precision=12, scale=2),
                   nullable=False,
                   existing_server_default=sa.text("'0.00'"))
        op.alter_column('customer_referrals', 'created_at',
                   existing_type=mysql.TIMESTAMP(),
                   type_=sa.DateTime(),
                   nullable=False,
                   existing_server_default=sa.text('CURRENT_TIMESTAMP'))
        op.alter_column('customer_referrals', 'updated_at',
                   existing_type=mysql.TIMESTAMP(),
                   type_=sa.DateTime(),
                   nullable=False,
                   existing_server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'))

    if "customer_wallets" in existing_tables:
        op.alter_column('customer_wallets', 'current_balance',
                   existing_type=mysql.DECIMAL(precision=12, scale=2),
                   nullable=False,
                   existing_server_default=sa.text("'0.00'"))
        op.alter_column('customer_wallets', 'created_at',
                   existing_type=mysql.DATETIME(),
                   nullable=False,
                   existing_server_default=sa.text('CURRENT_TIMESTAMP'))
        op.alter_column('customer_wallets', 'updated_at',
                   existing_type=mysql.DATETIME(),
                   nullable=False,
                   existing_server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'))
        op.create_unique_constraint(None, 'customer_wallets', ['customer_id'])
        try:
            op.drop_constraint(op.f('fk_wallet_customer'), 'customer_wallets', type_='foreignkey')
        except Exception:
            pass
        op.create_foreign_key(None, 'customer_wallets', 'customers', ['customer_id'], ['id'])

    if "loyalty_points" in existing_tables:
        op.alter_column('loyalty_points', 'points_earned',
                   existing_type=mysql.INTEGER(),
                   nullable=False,
                   existing_server_default=sa.text("'0'"))
        op.alter_column('loyalty_points', 'points_redeemed',
                   existing_type=mysql.INTEGER(),
                   nullable=False,
                   existing_server_default=sa.text("'0'"))
        op.alter_column('loyalty_points', 'balance_points',
                   existing_type=mysql.INTEGER(),
                   nullable=False,
                   existing_server_default=sa.text("'0'"))
        op.alter_column('loyalty_points', 'created_at',
                   existing_type=mysql.DATETIME(),
                   nullable=False,
                   existing_server_default=sa.text('CURRENT_TIMESTAMP'))
        op.alter_column('loyalty_points', 'updated_at',
                   existing_type=mysql.DATETIME(),
                   nullable=False,
                   existing_server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'))

    if "wallet_transactions" in existing_tables:
        op.alter_column('wallet_transactions', 'created_at',
                   existing_type=mysql.DATETIME(),
                   nullable=False,
                   existing_server_default=sa.text('CURRENT_TIMESTAMP'))
        try:
            op.drop_constraint(op.f('fk_wallet_transaction'), 'wallet_transactions', type_='foreignkey')
        except Exception:
            pass
        op.create_foreign_key(None, 'wallet_transactions', 'customer_wallets', ['wallet_id'], ['id'])
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint(None, 'wallet_transactions', type_='foreignkey')
    op.create_foreign_key(op.f('fk_wallet_transaction'), 'wallet_transactions', 'customer_wallets', ['wallet_id'], ['id'], ondelete='CASCADE')
    op.alter_column('wallet_transactions', 'created_at',
               existing_type=mysql.DATETIME(),
               nullable=True,
               existing_server_default=sa.text('CURRENT_TIMESTAMP'))
    op.alter_column('loyalty_points', 'updated_at',
               existing_type=mysql.DATETIME(),
               nullable=True,
               existing_server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'))
    op.alter_column('loyalty_points', 'created_at',
               existing_type=mysql.DATETIME(),
               nullable=True,
               existing_server_default=sa.text('CURRENT_TIMESTAMP'))
    op.alter_column('loyalty_points', 'balance_points',
               existing_type=mysql.INTEGER(),
               nullable=True,
               existing_server_default=sa.text("'0'"))
    op.alter_column('loyalty_points', 'points_redeemed',
               existing_type=mysql.INTEGER(),
               nullable=True,
               existing_server_default=sa.text("'0'"))
    op.alter_column('loyalty_points', 'points_earned',
               existing_type=mysql.INTEGER(),
               nullable=True,
               existing_server_default=sa.text("'0'"))
    op.drop_constraint(None, 'customer_wallets', type_='foreignkey')
    op.create_foreign_key(op.f('fk_wallet_customer'), 'customer_wallets', 'customers', ['customer_id'], ['id'], ondelete='CASCADE')
    op.drop_constraint(None, 'customer_wallets', type_='unique')
    op.alter_column('customer_wallets', 'updated_at',
               existing_type=mysql.DATETIME(),
               nullable=True,
               existing_server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'))
    op.alter_column('customer_wallets', 'created_at',
               existing_type=mysql.DATETIME(),
               nullable=True,
               existing_server_default=sa.text('CURRENT_TIMESTAMP'))
    op.alter_column('customer_wallets', 'current_balance',
               existing_type=mysql.DECIMAL(precision=12, scale=2),
               nullable=True,
               existing_server_default=sa.text("'0.00'"))
    op.alter_column('customer_referrals', 'updated_at',
               existing_type=sa.DateTime(),
               type_=mysql.TIMESTAMP(),
               nullable=True,
               existing_server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'))
    op.alter_column('customer_referrals', 'created_at',
               existing_type=sa.DateTime(),
               type_=mysql.TIMESTAMP(),
               nullable=True,
               existing_server_default=sa.text('CURRENT_TIMESTAMP'))
    op.alter_column('customer_referrals', 'reward_amount',
               existing_type=mysql.DECIMAL(precision=12, scale=2),
               nullable=True,
               existing_server_default=sa.text("'0.00'"))
    op.drop_index(op.f('ix_customer_notes_id'), table_name='customer_notes')
    op.alter_column('customer_notes', 'updated_at',
               existing_type=sa.DateTime(),
               type_=mysql.TIMESTAMP(),
               existing_nullable=True,
               existing_server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'))
    op.alter_column('customer_notes', 'created_at',
               existing_type=sa.DateTime(),
               type_=mysql.TIMESTAMP(),
               existing_nullable=True,
               existing_server_default=sa.text('CURRENT_TIMESTAMP'))
    op.drop_constraint(None, 'customer_feedback', type_='foreignkey')
    op.drop_constraint(None, 'customer_feedback', type_='foreignkey')
    op.create_foreign_key(op.f('fk_feedback_customer'), 'customer_feedback', 'customers', ['customer_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key(op.f('fk_feedback_invoice'), 'customer_feedback', 'invoices', ['invoice_id'], ['id'], ondelete='SET NULL')
    op.alter_column('customer_feedback', 'updated_at',
               existing_type=mysql.DATETIME(),
               nullable=True,
               existing_server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'))
    op.alter_column('customer_feedback', 'created_at',
               existing_type=mysql.DATETIME(),
               nullable=True,
               existing_server_default=sa.text('CURRENT_TIMESTAMP'))
    op.drop_index(op.f('ix_customer_communications_id'), table_name='customer_communications')
    # ### end Alembic commands ###
