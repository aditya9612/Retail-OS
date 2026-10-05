"""add product_batches and batch_id columns

Revision ID: aff441ad6053
Revises: d4e5f6a7b8c9
Create Date: 2026-10-05 18:33:45.547916
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = 'aff441ad6053'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # ### create product_batches table ###
    op.create_table(
        'product_batches',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('tenant_id', sa.Integer, nullable=False, index=True),
        sa.Column('store_id', sa.Integer, nullable=False, index=True),
        sa.Column('product_id', sa.Integer, sa.ForeignKey('products.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('variant_id', sa.Integer, sa.ForeignKey('product_variants.id', ondelete='SET NULL'), nullable=True, index=True),
        sa.Column('batch_number', sa.String(64), nullable=False),
        sa.Column('manufacturing_date', sa.Date, nullable=True),
        sa.Column('expiry_date', sa.Date, nullable=True),
        sa.Column('unit_cost', sa.Numeric(12, 4), nullable=False, server_default='0'),
        sa.Column('quantity', sa.Numeric(12, 4), nullable=False, server_default='0'),
        sa.Column('remaining_quantity', sa.Numeric(12, 4), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default=sa.text('1')),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
    )
    # Unique indexes – MySQL treats NULL as distinct, so two indexes work.
    op.create_index('uq_product_batches_variant', 'product_batches', ['tenant_id', 'store_id', 'product_id', 'variant_id', 'batch_number'], unique=True)
    op.create_index('uq_product_batches_product', 'product_batches', ['tenant_id', 'store_id', 'product_id', 'batch_number'], unique=True)
    # Check constraints
    op.create_check_constraint('ck_batch_quantity_nonneg', 'product_batches', 'quantity >= 0')
    op.create_check_constraint('ck_batch_remaining_nonneg', 'product_batches', 'remaining_quantity >= 0')
    op.create_check_constraint('ck_batch_remaining_le_quantity', 'product_batches', 'remaining_quantity <= quantity')
    # ### add batch_id to inventory ###
    op.add_column('inventory', sa.Column('batch_id', sa.Integer, sa.ForeignKey('product_batches.id', ondelete='SET NULL'), nullable=True, index=True))
    # ### add batch_id to stock_movement ###
    op.add_column('stock_movements', sa.Column('batch_id', sa.Integer, sa.ForeignKey('product_batches.id', ondelete='SET NULL'), nullable=True, index=True))

def downgrade() -> None:
    # ### drop batch_id columns using batch operation (automatically handles FK constraints) ###
    with op.batch_alter_table('stock_movements') as batch:
        batch.drop_column('batch_id')
    with op.batch_alter_table('inventory') as batch:
        batch.drop_column('batch_id')
    # ### drop product_batches table and indexes/constraints ###
    op.drop_index('uq_product_batches_product', table_name='product_batches')
    op.drop_index('uq_product_batches_variant', table_name='product_batches')
    op.drop_constraint('ck_batch_remaining_le_quantity', 'product_batches', type_='check')
    op.drop_constraint('ck_batch_remaining_nonneg', 'product_batches', type_='check')
    op.drop_constraint('ck_batch_quantity_nonneg', 'product_batches', type_='check')
    op.drop_table('product_batches')
