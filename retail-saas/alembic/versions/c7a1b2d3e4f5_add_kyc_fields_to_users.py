"""add_kyc_fields_to_users

Revision ID: c7a1b2d3e4f5
Revises: ec215d5db1fa
Create Date: 2026-09-30 16:52:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7a1b2d3e4f5'
down_revision: Union[str, None] = 'ec215d5db1fa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_cols = [c['name'] for c in inspector.get_columns('users')]
    if 'pancard' not in existing_cols:
        op.add_column('users', sa.Column('pancard', sa.String(255), nullable=True))
    if 'pan_number' not in existing_cols:
        op.add_column('users', sa.Column('pan_number', sa.String(20), nullable=True))
    if 'addhar_card' not in existing_cols:
        op.add_column('users', sa.Column('addhar_card', sa.String(255), nullable=True))
    if 'addhar_number' not in existing_cols:
        op.add_column('users', sa.Column('addhar_number', sa.String(20), nullable=True))
    if 'profile_photo' not in existing_cols:
        op.add_column('users', sa.Column('profile_photo', sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'profile_photo')
    op.drop_column('users', 'addhar_number')
    op.drop_column('users', 'addhar_card')
    op.drop_column('users', 'pan_number')
    op.drop_column('users', 'pancard')
