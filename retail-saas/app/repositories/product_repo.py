from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.product   import Product


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

    def list_products(self, tenant_id: int, skip: int = 0, limit: int = 20) -> List[Product]:
        return (
            self.db.query(Product)
            .filter(Product.tenant_id == tenant_id, Product.is_active.is_(True))
            .offset(skip)
            .limit(limit)
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
