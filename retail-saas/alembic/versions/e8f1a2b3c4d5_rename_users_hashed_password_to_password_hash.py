"""rename users hashed_password to password_hash

Revision ID: e8f1a2b3c4d5
Revises: d164abefdf3c
Create Date: 2026-10-06 17:20:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = 'e8f1a2b3c4d5'
down_revision = 'd164abefdf3c'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {c["name"] for c in inspector.get_columns("users")}

    if "hashed_password" in columns and "password_hash" not in columns:
        if bind.dialect.name == "mysql":
            op.execute(
                "ALTER TABLE users CHANGE COLUMN hashed_password password_hash VARCHAR(255) NOT NULL"
            )
        else:
            op.alter_column(
                "users",
                "hashed_password",
                new_column_name="password_hash",
                existing_type=sa.String(255),
                existing_nullable=False,
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {c["name"] for c in inspector.get_columns("users")}

    if "password_hash" in columns and "hashed_password" not in columns:
        if bind.dialect.name == "mysql":
            op.execute(
                "ALTER TABLE users CHANGE COLUMN password_hash hashed_password VARCHAR(255) NOT NULL"
            )
        else:
            op.alter_column(
                "users",
                "password_hash",
                new_column_name="hashed_password",
                existing_type=sa.String(255),
                existing_nullable=False,
            )
