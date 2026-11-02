from datetime import date
from decimal import Decimal
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
            .options(
                selectinload(Product.images),
                joinedload(Product.category),
            )
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
            .options(
                selectinload(Product.images),
                joinedload(Product.category),
            )
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
        b = barcode.strip()
        # 1. Search in Product table
        product = (
            self.db.query(Product)
            .options(
                selectinload(Product.images),
                joinedload(Product.category),
            )
            .filter(
                Product.barcode == b,
                Product.tenant_id == tenant_id,
            )
            .first()
        )
        if product:
            return product

        # 2. Search in ProductVariant table for barcode scanning at POS
        variant = (
            self.db.query(ProductVariant)
            .filter(
                ProductVariant.barcode == b,
                ProductVariant.tenant_id == tenant_id,
            )
            .first()
        )
        if variant and variant.product_id:
            return (
                self.db.query(Product)
                .options(
                    selectinload(Product.images),
                    joinedload(Product.category),
                )
                .filter(
                    Product.id == variant.product_id,
                    Product.tenant_id == tenant_id,
                )
                .first()
            )

        return None

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

        from datetime import date
        today = date.today()
        return (
            self.db.query(Product)
            .options(
                selectinload(Product.images),
                joinedload(Product.category),
            )
            .filter(
                Product.tenant_id == tenant_id,
                Product.is_active.is_(True),
                or_(Product.expiry_date.is_(None), Product.expiry_date >= today),
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
        category_id: Optional[int] = None,
        brand: Optional[str] = None,
        stock_status: Optional[str] = None,
        min_price: Optional[Decimal] = None,
        max_price: Optional[Decimal] = None,
        sort_by: Optional[str] = None,
    ) -> List[Product]:
        query = (
            self.db.query(Product)
            .options(
                selectinload(Product.images),
                joinedload(Product.category),
            )
            .filter(Product.tenant_id == tenant_id)
        )

        if not include_inactive:
            from datetime import date
            today = date.today()
            query = query.filter(
                Product.is_active.is_(True),
                or_(Product.expiry_date.is_(None), Product.expiry_date >= today),
            )

        if category_id is not None:
            query = query.filter(Product.category_id == category_id)

        if brand:
            query = query.filter(Product.brand.ilike(f"%{brand.strip()}%"))

        if stock_status:
            query = query.filter(Product.stock_status == stock_status.strip().lower())

        if min_price is not None:
            query = query.filter(Product.selling_price >= min_price)

        if max_price is not None:
            query = query.filter(Product.selling_price <= max_price)

        if sort_by == "name_asc":
            query = query.order_by(Product.name.asc())
        elif sort_by == "name_desc":
            query = query.order_by(Product.name.desc())
        elif sort_by == "price_asc":
            query = query.order_by(Product.selling_price.asc())
        elif sort_by == "price_desc":
            query = query.order_by(Product.selling_price.desc())
        elif sort_by == "created_asc":
            query = query.order_by(Product.id.asc())
        else:
            query = query.order_by(Product.id.desc())

        return (
            query
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
        from sqlalchemy import cast, Integer as SqlInteger
        # Outer join Inventory so that products with 0 quantity also appear in low-stock
        rows = (
            self.db.query(Product, func.coalesce(Inventory.quantity, 0))
            .options(
                selectinload(Product.images),
                joinedload(Product.category),
            )
            .outerjoin(
                Inventory,
                (Product.id == Inventory.product_id) & (Inventory.store_id == store_id),
            )
            .filter(
                Product.tenant_id == tenant_id,
                Product.is_active.is_(True),
                or_(
                    Inventory.id.is_(None),
                    Inventory.quantity <= threshold,
                    Inventory.quantity <= Product.min_stock_alert,
                ),
            )
            .order_by(func.coalesce(Inventory.quantity, 0).asc(), Product.id.asc())
            .all()
        )
        return [(p, int(qty)) for p, qty in rows]

    def list_expiring_soon(
        self,
        tenant_id: int,
        store_id: int,
        days: int = 30,
    ) -> List[Product]:
        from datetime import date, timedelta
        from app.models.product_batch import ProductBatch

        today = date.today()
        cutoff_date = today + timedelta(days=days)

        # 1. Direct product expiry
        direct_exp = (
            self.db.query(Product)
            .options(
                selectinload(Product.images),
                joinedload(Product.category),
            )
            .outerjoin(
                Inventory,
                (Product.id == Inventory.product_id) & (Inventory.store_id == store_id),
            )
            .filter(
                Product.tenant_id == tenant_id,
                Product.is_active.is_(True),
                Product.expiry_date.isnot(None),
                Product.expiry_date >= today,
                Product.expiry_date <= cutoff_date,
            )
            .all()
        )
        found_ids = {p.id for p in direct_exp}

        # 2. Batch-based expiry in the store
        batch_exp = (
            self.db.query(Product)
            .options(
                selectinload(Product.images),
                joinedload(Product.category),
            )
            .join(ProductBatch, Product.id == ProductBatch.product_id)
            .filter(
                ProductBatch.tenant_id == tenant_id,
                ProductBatch.store_id == store_id,
                ProductBatch.is_active.is_(True),
                ProductBatch.remaining_quantity > 0,
                ProductBatch.expiry_date.isnot(None),
                ProductBatch.expiry_date >= today,
                ProductBatch.expiry_date <= cutoff_date,
                Product.id.notin_(found_ids) if found_ids else True,
            )
            .distinct()
            .all()
        )

        return direct_exp + batch_exp

    def has_transactions(self, product_id: int) -> bool:
        """Check if product has any sales, purchase, or transfer records preventing hard delete."""
        from app.models.sale import SaleItem
        from app.models.invoice_item import InvoiceItem
        from app.models.purchase_order import PurchaseOrderItem
        from app.models.store_transfer_item import StoreTransferItem
        from app.models.grn import GRNItem

        for model in (SaleItem, InvoiceItem, PurchaseOrderItem, StoreTransferItem, GRNItem):
            try:
                if self.db.query(model.id).filter(model.product_id == product_id).first() is not None:
                    return True
            except Exception:
                continue
        return False

    def get_catalog_summary(
        self,
        tenant_id: int,
        store_id: Optional[int] = None,
    ) -> dict:
        from datetime import date, timedelta
        from app.models.category import Category

        # 1. Total, active, inactive, missing barcodes
        base_query = self.db.query(Product).filter(Product.tenant_id == tenant_id)
        total_products = base_query.count()
        active_products = base_query.filter(Product.is_active.is_(True)).count()
        inactive_products = total_products - active_products
        missing_barcodes_count = base_query.filter(
            or_(Product.barcode.is_(None), Product.barcode == "")
        ).count()

        # 2. Inventory Valuation
        val_query = (
            self.db.query(
                func.coalesce(func.sum(Inventory.quantity * Product.cost_price), 0),
                func.coalesce(func.sum(Inventory.quantity * Product.selling_price), 0),
            )
            .join(Product, Inventory.product_id == Product.id)
            .filter(Product.tenant_id == tenant_id)
        )
        if store_id is not None:
            val_query = val_query.filter(Inventory.store_id == store_id)
        total_cost_val, total_retail_val = val_query.first() or (Decimal("0"), Decimal("0"))

        # 3. Stock counts
        inv_subquery = self.db.query(
            Inventory.product_id,
            func.coalesce(func.sum(Inventory.quantity), 0).label("tot_qty"),
        ).filter(Inventory.tenant_id == tenant_id)
        if store_id is not None:
            inv_subquery = inv_subquery.filter(Inventory.store_id == store_id)
        inv_sub = inv_subquery.group_by(Inventory.product_id).subquery()

        active_prods = (
            self.db.query(
                Product.id,
                Product.min_stock_alert,
                func.coalesce(inv_sub.c.tot_qty, 0).label("stock"),
            )
            .outerjoin(inv_sub, Product.id == inv_sub.c.product_id)
            .filter(Product.tenant_id == tenant_id, Product.is_active.is_(True))
            .all()
        )

        out_of_stock_count = 0
        low_stock_count = 0
        for p_id, alert, stock in active_prods:
            if stock <= 0:
                out_of_stock_count += 1
            elif stock <= alert:
                low_stock_count += 1

        # 4. Expiring soon (within 30 days)
        cutoff_date = date.today() + timedelta(days=30)
        expiring_soon_count = base_query.filter(
            Product.is_active.is_(True),
            Product.expiry_date.isnot(None),
            Product.expiry_date <= cutoff_date,
        ).count()

        # 5. Category breakdown
        cat_counts = (
            self.db.query(
                Product.category_id,
                func.count(Product.id).label("count"),
            )
            .filter(Product.tenant_id == tenant_id, Product.is_active.is_(True))
            .group_by(Product.category_id)
            .all()
        )
        all_cats = {
            c.id: c.name
            for c in self.db.query(Category).filter(Category.tenant_id == tenant_id).all()
        }
        category_breakdown = [
            {
                "category_id": cid,
                "category_name": all_cats.get(cid, "Uncategorized" if cid is None else f"Category {cid}"),
                "product_count": cnt,
            }
            for cid, cnt in cat_counts
        ]

        return {
            "total_products": total_products,
            "active_products": active_products,
            "inactive_products": inactive_products,
            "total_inventory_cost_value": Decimal(str(total_cost_val)),
            "total_inventory_retail_value": Decimal(str(total_retail_val)),
            "out_of_stock_count": out_of_stock_count,
            "low_stock_count": low_stock_count,
            "expiring_soon_count": expiring_soon_count,
            "missing_barcodes_count": missing_barcodes_count,
            "category_breakdown": category_breakdown,
        }

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

    def list_all_variants(
        self,
        tenant_id: int,
        product_id: Optional[int] = None,
        search: Optional[str] = None,
        size: Optional[str] = None,
        color: Optional[str] = None,
        is_active: Optional[bool] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> List[ProductVariant]:
        from sqlalchemy import func, or_

        query = (
            self.db.query(ProductVariant)
            .options(joinedload(ProductVariant.product))
            .filter(ProductVariant.tenant_id == tenant_id)
        )

        if product_id is not None:
            query = query.filter(ProductVariant.product_id == product_id)

        if is_active is not None:
            query = query.filter(ProductVariant.is_active.is_(is_active))

        if size is not None:
            query = query.filter(func.lower(ProductVariant.size) == size.strip().lower())

        if color is not None:
            query = query.filter(func.lower(ProductVariant.color) == color.strip().lower())

        if search:
            search_pattern = f"%{search.strip()}%"
            query = query.filter(
                or_(
                    ProductVariant.variant_name.ilike(search_pattern),
                    ProductVariant.sku.ilike(search_pattern),
                    ProductVariant.barcode.ilike(search_pattern),
                )
            )

        return query.order_by(ProductVariant.id.desc()).offset(skip).limit(limit).all()

    def count_all_variants(
        self,
        tenant_id: int,
        product_id: Optional[int] = None,
        search: Optional[str] = None,
        size: Optional[str] = None,
        color: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> int:
        from sqlalchemy import func, or_

        query = self.db.query(ProductVariant).filter(ProductVariant.tenant_id == tenant_id)

        if product_id is not None:
            query = query.filter(ProductVariant.product_id == product_id)

        if is_active is not None:
            query = query.filter(ProductVariant.is_active.is_(is_active))

        if size is not None:
            query = query.filter(func.lower(ProductVariant.size) == size.strip().lower())

        if color is not None:
            query = query.filter(func.lower(ProductVariant.color) == color.strip().lower())

        if search:
            search_pattern = f"%{search.strip()}%"
            query = query.filter(
                or_(
                    ProductVariant.variant_name.ilike(search_pattern),
                    ProductVariant.sku.ilike(search_pattern),
                    ProductVariant.barcode.ilike(search_pattern),
                )
            )

        return query.count()
