from datetime import date
from typing import List, Optional, Tuple

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, selectinload

from app.models.inventory import Inventory
from app.models.product import Product, ProductImage


class ProductRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(
        self,
        product_id: int,
        tenant_id: int,
    ) -> Optional[Product]:
        return (
            self.db.query(Product)
            .options(selectinload(Product.images))
            .filter(
                Product.id == product_id,
                Product.tenant_id == tenant_id,
            )
            .first()
        )

    def get_by_sku(
        self,
        sku: str,
        tenant_id: int,
    ) -> Optional[Product]:
        return (
            self.db.query(Product)
            .filter(
                func.upper(Product.sku) == sku.strip().upper(),
                Product.tenant_id == tenant_id,
            )
            .first()
        )

    def get_by_barcode(
        self,
        barcode: str,
        tenant_id: int,
    ) -> Optional[Product]:
        return (
            self.db.query(Product)
            .filter(
                Product.barcode == barcode.strip(),
                Product.tenant_id == tenant_id,
            )
            .first()
        )

    def search_products(
        self,
        tenant_id: int,
        query: str,
        skip: int = 0,
        limit: int = 20,
    ) -> List[Product]:
        q = query.strip()
        conditions = [
            Product.name.ilike(f"%{q}%"),
            Product.sku.ilike(f"%{q}%"),
        ]

        if q.isdigit():
            conditions.append(Product.barcode.ilike(f"%{q}%"))
            # Prefix or exact match for HSN code to avoid matching irrelevant codes
            conditions.append(Product.hsn_code.like(f"{q}%"))
        else:
            conditions.append(Product.barcode.ilike(f"%{q}%"))
            conditions.append(Product.brand.ilike(f"%{q}%"))

        return (
            self.db.query(Product)
            .options(selectinload(Product.images))
            .filter(
                Product.tenant_id == tenant_id,
                Product.is_active.is_(True),
                or_(*conditions),
            )
            .distinct()
            .offset(skip)
            .limit(limit)
            .all()
        )

    def list_products(
        self,
        tenant_id: int,
        skip: int = 0,
        limit: int = 20,
        include_inactive: bool = False,
    ) -> List[Product]:
        query = (
            self.db.query(Product)
            .options(selectinload(Product.images))
            .filter(Product.tenant_id == tenant_id)
        )

        if not include_inactive:
            query = query.filter(Product.is_active.is_(True))

        return (
            query
            .order_by(Product.id.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def list_low_stock(
        self,
        tenant_id: int,
        store_id: int,
        threshold: int = 10,
    ) -> List[Tuple[Product, int]]:
        return (
            self.db.query(Product, Inventory.quantity)
            .options(selectinload(Product.images))
            .join(
                Inventory,
                Product.id == Inventory.product_id,
            )
            .filter(
                Product.tenant_id == tenant_id,
                Product.is_active.is_(True),
                Inventory.store_id == store_id,
                Inventory.quantity <= threshold,
            )
            .all()
        )

    def list_expiring_soon(
        self,
        tenant_id: int,
        store_id: int,
        days: int = 30,
    ) -> List[Product]:
        return []

    def create(self, product: Product) -> Product:
        self.db.add(product)
        self.db.flush()
        return product

    def update(self, product: Product) -> Product:
        self.db.commit()
        self.db.refresh(product)
        return product

    def delete(self, product: Product) -> None:
        self.db.query(ProductImage).filter(ProductImage.product_id == product.id).delete()
        self.db.query(Inventory).filter(Inventory.product_id == product.id).delete()
        self.db.delete(product)
        self.db.commit()