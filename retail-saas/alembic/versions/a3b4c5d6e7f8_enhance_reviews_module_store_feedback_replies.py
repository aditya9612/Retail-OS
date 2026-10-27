"""enhance reviews module store feedback replies

Revision ID: a3b4c5d6e7f8
Revises: e1a2b3c4d5e6
Create Date: 2026-10-27 11:35:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a3b4c5d6e7f8"
down_revision: Union[str, None] = "e1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    if "reviews" in existing_tables:
        existing_cols = {c["name"] for c in inspector.get_columns("reviews")}

        with op.batch_alter_table("reviews", schema=None) as batch_op:
            if "product_id" in existing_cols:
                batch_op.alter_column(
                    "product_id",
                    existing_type=sa.Integer(),
                    nullable=True,
                )

            if "store_id" not in existing_cols:
                batch_op.add_column(
                    sa.Column("store_id", sa.Integer(), nullable=True)
                )
                batch_op.create_foreign_key(
                    "fk_reviews_store_id_stores",
                    "stores",
                    ["store_id"],
                    ["id"],
                )
                batch_op.create_index(
                    "ix_reviews_store_id",
                    ["store_id"],
                    unique=False,
                )

            if "order_id" not in existing_cols:
                batch_op.add_column(
                    sa.Column("order_id", sa.Integer(), nullable=True)
                )
                batch_op.create_foreign_key(
                    "fk_reviews_order_id_orders",
                    "orders",
                    ["order_id"],
                    ["id"],
                )
                batch_op.create_index(
                    "ix_reviews_order_id",
                    ["order_id"],
                    unique=False,
                )

            if "is_verified_purchase" not in existing_cols:
                batch_op.add_column(
                    sa.Column(
                        "is_verified_purchase",
                        sa.Boolean(),
                        nullable=False,
                        server_default="0",
                    )
                )

            if "status" not in existing_cols:
                batch_op.add_column(
                    sa.Column(
                        "status",
                        sa.String(length=20),
                        nullable=False,
                        server_default="approved",
                    )
                )
                batch_op.create_index(
                    "ix_reviews_status",
                    ["status"],
                    unique=False,
                )

            if "is_edited" not in existing_cols:
                batch_op.add_column(
                    sa.Column(
                        "is_edited",
                        sa.Boolean(),
                        nullable=False,
                        server_default="0",
                    )
                )

            if "merchant_reply" not in existing_cols:
                batch_op.add_column(
                    sa.Column("merchant_reply", sa.Text(), nullable=True)
                )

            if "replied_at" not in existing_cols:
                batch_op.add_column(
                    sa.Column(
                        "replied_at",
                        sa.DateTime(timezone=True),
                        nullable=True,
                    )
                )

            if "replied_by" not in existing_cols:
                batch_op.add_column(
                    sa.Column("replied_by", sa.Integer(), nullable=True)
                )
                batch_op.create_foreign_key(
                    "fk_reviews_replied_by_users",
                    "users",
                    ["replied_by"],
                    ["id"],
                )

            if "is_deleted" not in existing_cols:
                batch_op.add_column(
                    sa.Column(
                        "is_deleted",
                        sa.Boolean(),
                        nullable=False,
                        server_default="0",
                    )
                )
                batch_op.create_index(
                    "ix_reviews_is_deleted",
                    ["is_deleted"],
                    unique=False,
                )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    if "reviews" in existing_tables:
        existing_cols = {c["name"] for c in inspector.get_columns("reviews")}

        with op.batch_alter_table("reviews", schema=None) as batch_op:
            for col in [
                "is_deleted",
                "replied_by",
                "replied_at",
                "merchant_reply",
                "is_edited",
                "status",
                "is_verified_purchase",
                "order_id",
                "store_id",
            ]:
                if col in existing_cols:
                    batch_op.drop_column(col)

