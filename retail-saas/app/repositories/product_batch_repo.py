from typing import List, Optional
from sqlalchemy import select, update, delete
from sqlalchemy.orm import Session
from app.models.product_batch import ProductBatch


class ProductBatchRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, batch_id: int) -> Optional[ProductBatch]:
        return self.db.get(ProductBatch, batch_id)

    def get_by_number(
        self,
        tenant_id: int,
        store_id: int,
        product_id: int,
        batch_number: str,
        variant_id: Optional[int] = None,
    ) -> Optional[ProductBatch]:
        stmt = select(ProductBatch).where(
            ProductBatch.tenant_id == tenant_id,
            ProductBatch.store_id == store_id,
            ProductBatch.product_id == product_id,
            ProductBatch.batch_number == batch_number,
        )
        if variant_id is None:
            stmt = stmt.where(ProductBatch.variant_id.is_(None))
        else:
            stmt = stmt.where(ProductBatch.variant_id == variant_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def list(
        self,
        tenant_id: int,
        store_id: int,
        product_id: Optional[int] = None,
        variant_id: Optional[int] = None,
        batch_number: Optional[str] = None,
        offset: int = 0,
        limit: int = 100,
    ) -> List[ProductBatch]:
        stmt = select(ProductBatch).where(
            ProductBatch.tenant_id == tenant_id,
            ProductBatch.store_id == store_id,
        )
        if product_id:
            stmt = stmt.where(ProductBatch.product_id == product_id)
        if variant_id is not None:
            stmt = stmt.where(ProductBatch.variant_id == variant_id)
        if batch_number:
            stmt = stmt.where(ProductBatch.batch_number == batch_number)
        return self.db.execute(stmt.offset(offset).limit(limit)).scalars().all()

    def create(self, batch: ProductBatch) -> ProductBatch:
        self.db.add(batch)
        self.db.flush()
        return batch

    def update(self, batch: ProductBatch, data: dict) -> ProductBatch:
        for key, value in data.items():
            setattr(batch, key, value)
        self.db.flush()
        return batch

    def soft_delete(self, batch: ProductBatch) -> None:
        batch.is_active = False
        self.db.flush()
