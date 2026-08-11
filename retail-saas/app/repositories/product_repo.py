from datetime import date
from typing import List, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.inventory import Inventory
from app.models.product import Product


class ProductRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, product_id: int, tenant_id: int) -> Optional[Product]:
        return (
            self.db.query(Product)
            .filter(Product.id == product_id, Product.tenant_id == tenant_id)
            .first()
        )

    def get_by_sku(self, sku: str, tenant_id: int) -> Optional[Product]:
        return (
            self.db.query(Product)
            .filter(Product.sku == sku, Product.tenant_id == tenant_id)
            .first()
        )

    def get_by_barcode(self, barcode: str, tenant_id: int) -> Optional[Product]:
        return (
            self.db.query(Product)
            .filter(Product.barcode == barcode, Product.tenant_id == tenant_id)
            .first()
        )

    def search_products(
        self,
        tenant_id: int,
        query: str,
        skip: int = 0,
        limit: int = 20,
    ) -> List[Product]:
        return (
            self.db.query(Product)
            .filter(
                Product.tenant_id == tenant_id,
                Product.is_active.is_(True),
                or_(
                    Product.name.ilike(f"%{query}%"),
                    Product.sku.ilike(f"%{query}%"),
                    Product.barcode.ilike(f"%{query}%"),
                    Product.hsn_code.ilike(f"%{query}%"),
                ),
            )
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
        query = self.db.query(Product).filter(Product.tenant_id == tenant_id)
        if not include_inactive:
            query = query.filter(Product.is_active.is_(True))
        return query.offset(skip).limit(limit).all()

    def list_low_stock(
        self,
        tenant_id: int,
        store_id: int,
        threshold: int = 10,
    ) -> List[Product]:
        return (
            self.db.query(Product)
            .join(Inventory, Product.id == Inventory.product_id)
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
        from datetime import timedelta
        expiry_cutoff = date.today() + timedelta(days=days)
        return (
            self.db.query(Product)
            .join(Inventory, Product.id == Inventory.product_id)
            .filter(
                Product.tenant_id == tenant_id,
                Product.is_active.is_(True),
                Product.track_expiry.is_(True),
                Inventory.store_id == store_id,
                Inventory.expiry_date != None,
                Inventory.expiry_date <= expiry_cutoff,
            )
            .all()
        )

    def create(self, product: Product) -> Product:
        self.db.add(product)
        self.db.commit()
        self.db.refresh(product)
        return product

    def update(self, product: Product) -> Product:
        self.db.commit()
        self.db.refresh(product)
        return product

    def delete(self, product: Product) -> None:
        product.is_active = False
        self.db.commit()