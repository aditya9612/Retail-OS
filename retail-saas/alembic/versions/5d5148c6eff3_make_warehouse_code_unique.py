"""make warehouse code unique

Revision ID: 5d5148c6eff3
Revises: 9764dd66e682
Create Date: 2026-08-11 18:37:57.472019

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5d5148c6eff3'
down_revision: Union[str, None] = '9764dd66e682'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    indexes = inspector.get_indexes("warehouses")

    code_index = next(
        (
            index
            for index in indexes
            if index["name"] == op.f("ix_warehouses_code")
        ),
        None,
    )

    if code_index is not None:
        if not code_index.get("unique", False):
            op.drop_index(
                op.f("ix_warehouses_code"),
                table_name="warehouses",
            )

            op.create_index(
                op.f("ix_warehouses_code"),
                "warehouses",
                ["code"],
                unique=True,
            )
    else:
        op.create_index(
            op.f("ix_warehouses_code"),
            "warehouses",
            ["code"],
            unique=True,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    indexes = inspector.get_indexes("warehouses")

    code_index = next(
        (
            index
            for index in indexes
            if index["name"] == op.f("ix_warehouses_code")
        ),
        None,
    )

    if code_index is not None and code_index.get("unique", False):
        op.drop_index(
            op.f("ix_warehouses_code"),
            table_name="warehouses",
        )

        op.create_index(
            op.f("ix_warehouses_code"),
            "warehouses",
            ["code"],
            unique=False,
        )