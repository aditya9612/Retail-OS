"""add reviews table

Revision ID: 2c654f7aecd9
Revises: c053a70ef335
Create Date: 2026-09-03 18:00:01.178570

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "2c654f7aecd9"
down_revision: Union[str, None] = "c053a70ef335"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "reviews",

        sa.Column(
            "id",
            sa.Integer(),
            autoincrement=True,
            nullable=False,
        ),

        sa.Column(
            "tenant_id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "product_id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "customer_id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "rating",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "comment",
            sa.Text(),
            nullable=True,
        ),

        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
        ),

        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
        ),

        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
        ),

        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
        ),

        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
        ),

        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_reviews_tenant_id",
        "reviews",
        ["tenant_id"],
    )

    op.create_index(
        "ix_reviews_product_id",
        "reviews",
        ["product_id"],
    )

    op.create_index(
        "ix_reviews_customer_id",
        "reviews",
        ["customer_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_reviews_customer_id",
        table_name="reviews",
    )

    op.drop_index(
        "ix_reviews_product_id",
        table_name="reviews",
    )

    op.drop_index(
        "ix_reviews_tenant_id",
        table_name="reviews",
    )

    op.drop_table("reviews")