"""register existing store_targets table

Revision ID: 6cffa3e2dd40
Revises: 42f1b7a88b10
Create Date: 2026-09-08
"""

from typing import Sequence, Union


revision: str = "6cffa3e2dd40"
down_revision: Union[str, None] = "42f1b7a88b10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


from alembic import op


def upgrade() -> None:
    # Ensure store_targets exists
    op.execute("""
    CREATE TABLE IF NOT EXISTS `store_targets` (
      `id` int NOT NULL AUTO_INCREMENT,
      `store_id` int NOT NULL,
      `target_type` varchar(30) NOT NULL,
      `target_value` decimal(12,2) NOT NULL,
      `period` varchar(20) NOT NULL,
      `start_date` datetime NOT NULL,
      `end_date` datetime NOT NULL,
      `status` varchar(20) NOT NULL DEFAULT 'active',
      `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
      `updated_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      PRIMARY KEY (`id`),
      KEY `ix_store_targets_store_id` (`store_id`),
      CONSTRAINT `fk_store_targets_store_id` FOREIGN KEY (`store_id`) REFERENCES `stores` (`id`) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    """)


def downgrade() -> None:
    pass