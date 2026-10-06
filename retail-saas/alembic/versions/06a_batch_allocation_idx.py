"""add batch allocation fifo and fefo indexes

Revision ID: 06a_batch_allocation_idx
Revises: aff441ad6053
Create Date: 2026-10-06 10:35:00.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '06a_batch_allocation_idx'
down_revision = 'aff441ad6053'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ### create indexes on product_batches for FIFO and FEFO allocation ###
    op.create_index(
        'ix_batch_fifo',
        'product_batches',
        ['tenant_id', 'store_id', 'product_id', 'is_active', 'created_at', 'id'],
        unique=False,
    )
    op.create_index(
        'ix_batch_fefo',
        'product_batches',
        ['tenant_id', 'store_id', 'product_id', 'is_active', 'expiry_date', 'created_at'],
        unique=False,
    )


def downgrade() -> None:
    # ### drop indexes on product_batches ###
    op.drop_index('ix_batch_fefo', table_name='product_batches')
    op.drop_index('ix_batch_fifo', table_name='product_batches')

