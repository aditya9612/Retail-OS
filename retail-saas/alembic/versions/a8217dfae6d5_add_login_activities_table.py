
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a8217dfae6d5"
down_revision: Union[str, Sequence[str], None] = "860afcdde201"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "login_activities",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("tenant_id", sa.Integer(), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("event_type", sa.String(length=30), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("device", sa.String(length=255), nullable=True),
        sa.Column("failure_reason", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_login_activities_user_id",
        "login_activities",
        ["user_id"],
        unique=False,
    )

    op.create_index(
        "ix_login_activities_tenant_id",
        "login_activities",
        ["tenant_id"],
        unique=False,
    )

    op.create_index(
        "ix_login_activities_email",
        "login_activities",
        ["email"],
        unique=False,
    )

    op.create_index(
        "ix_login_activities_event_type",
        "login_activities",
        ["event_type"],
        unique=False,
    )

    op.create_index(
        "ix_login_activities_created_at",
        "login_activities",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_login_activities_created_at",
        table_name="login_activities",
    )

    op.drop_index(
        "ix_login_activities_event_type",
        table_name="login_activities",
    )

    op.drop_index(
        "ix_login_activities_email",
        table_name="login_activities",
    )

    op.drop_index(
        "ix_login_activities_tenant_id",
        table_name="login_activities",
    )

    op.drop_index(
        "ix_login_activities_user_id",
        table_name="login_activities",
    )

    op.drop_table("login_activities")

