from datetime import date
from typing import List, Optional, Tuple

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.inventory import Inventory
from app.models.product import Product, ProductImage
from app.models.product_variant import ProductVariant


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

    # Product Variant Repository Methods
    def get_variant_by_id(
        self,
        variant_id: int,
        tenant_id: int,
    ) -> Optional[ProductVariant]:
        return (
            self.db.query(ProductVariant)
            .options(joinedload(ProductVariant.product))
            .filter(
                ProductVariant.id == variant_id,
                ProductVariant.tenant_id == tenant_id,
            )
            .first()
        )

    def get_variant_by_sku(
        self,
        sku: str,
        tenant_id: int,
    ) -> Optional[ProductVariant]:
        return (
            self.db.query(ProductVariant)
            .options(joinedload(ProductVariant.product))
            .filter(
                ProductVariant.sku == sku,
                ProductVariant.tenant_id == tenant_id,
            )
            .first()
        )

    def get_variant_by_barcode(
        self,
        barcode: str,
        tenant_id: int,
    ) -> Optional[ProductVariant]:
        return (
            self.db.query(ProductVariant)
            .options(joinedload(ProductVariant.product))
            .filter(
                ProductVariant.barcode == barcode,
                ProductVariant.tenant_id == tenant_id,
            )
            .first()
        )

    def is_sku_taken(
        self,
        sku: str,
        tenant_id: int,
        exclude_product_id: Optional[int] = None,
        exclude_variant_id: Optional[int] = None,
    ) -> bool:
        if not sku:
            return False
        # Check Product table
        p_query = self.db.query(Product.id).filter(
            Product.tenant_id == tenant_id,
            Product.sku == sku,
        )
        if exclude_product_id:
            p_query = p_query.filter(Product.id != exclude_product_id)
        if p_query.first() is not None:
            return True

        # Check ProductVariant table
        v_query = self.db.query(ProductVariant.id).filter(
            ProductVariant.tenant_id == tenant_id,
            ProductVariant.sku == sku,
        )
        if exclude_variant_id:
            v_query = v_query.filter(ProductVariant.id != exclude_variant_id)
        if v_query.first() is not None:
            return True

        return False

    def is_barcode_taken(
        self,
        barcode: Optional[str],
        tenant_id: int,
        exclude_product_id: Optional[int] = None,
        exclude_variant_id: Optional[int] = None,
    ) -> bool:
        if not barcode:
            return False
        # Check Product table
        p_query = self.db.query(Product.id).filter(
            Product.tenant_id == tenant_id,
            Product.barcode == barcode,
        )
        if exclude_product_id:
            p_query = p_query.filter(Product.id != exclude_product_id)
        if p_query.first() is not None:
            return True

        # Check ProductVariant table
        v_query = self.db.query(ProductVariant.id).filter(
            ProductVariant.tenant_id == tenant_id,
            ProductVariant.barcode == barcode,
        )
        if exclude_variant_id:
            v_query = v_query.filter(ProductVariant.id != exclude_variant_id)
        if v_query.first() is not None:
            return True

        return False

    def create_variant(self, variant: ProductVariant) -> ProductVariant:
        self.db.add(variant)
        self.db.flush()
        return variant

    def update_variant(self, variant: ProductVariant) -> ProductVariant:
        self.db.commit()
        self.db.refresh(variant)
        return variant

    def delete_variant(self, variant: ProductVariant) -> None:
        variant.is_active = False
        self.db.commit()

    def list_variants(
        self,
        product_id: int,
        tenant_id: int,
        include_inactive: bool = False,
        skip: int = 0,
        limit: int = 50,
    ) -> List[ProductVariant]:
        query = (
            self.db.query(ProductVariant)
            .options(joinedload(ProductVariant.product))
            .filter(
                ProductVariant.product_id == product_id,
                ProductVariant.tenant_id == tenant_id,
            )
        )
        if not include_inactive:
            query = query.filter(ProductVariant.is_active.is_(True))
        return query.order_by(ProductVariant.id.asc()).offset(skip).limit(limit).all()

    def count_variants(
        self,
        product_id: int,
        tenant_id: int,
        include_inactive: bool = False,
    ) -> int:
        query = self.db.query(ProductVariant).filter(
            ProductVariant.product_id == product_id,
            ProductVariant.tenant_id == tenant_id,
        )
        if not include_inactive:
            query = query.filter(ProductVariant.is_active.is_(True))
        return query.count()
