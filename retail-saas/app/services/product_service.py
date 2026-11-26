import base64
from datetime import date
from decimal import Decimal
import os
from typing import Any, List, Optional

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictException, NotFoundException
from app.models.category import Category
from app.models.inventory import Inventory
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.saas_plan_entitlement import EntitlementDimension
from app.models.store import Store
from app.repositories.product_repo import ProductRepository
from app.schemas.inventory import StockInRequest
from app.schemas.product import (
    ProductCreate,
    ProductLowStockResponse,
    ProductUpdate,
)
from app.schemas.product_variant import ProductVariantCreate
from app.services.inventory_service import InventoryService
from app.services.saas_entitlement_service import SaaSEntitlementService
from app.utils.barcode_generator import (
    generate_barcode_image,
    generate_ean13_barcode,
    generate_thermal_sticker_image,
)
from app.utils.gst_engine import resolve_gst_rate


class ProductService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = ProductRepository(db)

    def _enrich_product_metadata(
        self,
        product: Product,
        tenant_id: int,
        store_id: Optional[int] = None,
    ) -> Product:
        try:
            product.effective_gst_rate = resolve_gst_rate(self.db, tenant_id, product)
        except Exception:
            product.effective_gst_rate = Decimal(str(getattr(product, "tax_rate", Decimal("0.00")) or Decimal("0.00")))

        if store_id is not None:
            stock_sum = (
                self.db.query(func.coalesce(func.sum(Inventory.quantity), Decimal("0.0000")))
                .filter(
                    Inventory.tenant_id == tenant_id,
                    Inventory.store_id == store_id,
                    Inventory.product_id == product.id,
                )
                .scalar()
            )
            product.available_stock = Decimal(str(stock_sum or Decimal("0.0000")))
        else:
            product.available_stock = None
        return product

    def create_product(
        self,
        tenant_id: int,
        data: ProductCreate,
        user_store_id: Optional[int] = None,
    ) -> Product:
        sku = data.sku.strip().upper()
        barcode = data.barcode.strip() if data.barcode else None

        if data.category_id is not None:
            cat = self.db.query(Category).filter(
                Category.id == data.category_id,
                Category.tenant_id == tenant_id,
            ).first()
            if not cat:
                raise ConflictException("Category not found or does not belong to this tenant")

        if not barcode:
            for _ in range(10):
                candidate = generate_ean13_barcode(tenant_id)
                if not self.repo.is_barcode_taken(candidate, tenant_id):
                    barcode = candidate
                    break

        if not sku:
            raise ConflictException(
                "SKU cannot be empty"
            )

        if barcode:
            if not barcode.isdigit():
                raise ConflictException(
                    "Barcode must contain digits only"
                )

            if len(barcode) < 8 or len(barcode) > 50:
                raise ConflictException(
                    "Barcode must contain between 8 and 50 digits"
                )

            if len(set(barcode)) == 1:
                raise ConflictException(
                    "Barcode cannot consist of a single repeated digit"
                )

            if sku == barcode:
                raise ConflictException(
                    "SKU and Barcode cannot have the same value"
                )

            if self.repo.is_barcode_taken(barcode, tenant_id):
                raise ConflictException("Barcode already exists")

        if self.repo.is_sku_taken(sku, tenant_id):
            raise ConflictException("SKU already exists")

        if (
            data.mrp is not None
            and data.mrp > 0
            and data.mrp < data.selling_price
        ):
            raise ConflictException(
                "MRP cannot be lower than selling price"
            )

        if data.track_batch:
            if (
                not data.batch_number
                or not str(data.batch_number).strip()
            ):
                raise ConflictException(
                    "batch_number is required when track_batch is true"
                )

            batch_value = str(
                data.batch_number
            ).strip()

            if batch_value.lower() in {
                "string",
                "null",
                "none",
                "undefined",
                "test",
                "sample",
                "temp",
                "n/a",
                "na",
            }:
                raise ConflictException(
                    f"Batch number cannot be placeholder '{batch_value}'"
                )

        if data.track_expiry:
            if data.expiry_date is None:
                raise ConflictException(
                    "expiry_date is required when track_expiry is true"
                )

            if data.expiry_date < date.today():
                raise ConflictException(
                    "expiry_date cannot be in the past"
                )

        entitlement_svc = SaaSEntitlementService(
            self.db
        )

        entitlement_svc.require_limit(
            tenant_id=tenant_id,
            dimension=EntitlementDimension.PRODUCTS,
            requested_amount=1,
            lock_tenant=True,
        )

        product_data = data.model_dump()
        store_id = product_data.pop("store_id", None)
        opening_stock = product_data.pop("opening_stock", None)
        raw_variants = product_data.pop("variants", None)

        effective_store_id: Optional[int] = None
        if store_id is not None:
            store = (
                self.db.query(Store)
                .filter(
                    Store.id == store_id,
                    Store.tenant_id == tenant_id,
                    Store.is_active.is_(True),
                )
                .first()
            )
            if not store:
                raise NotFoundException(f"Store with ID {store_id} not found or inactive")
            effective_store_id = store.id
        elif opening_stock is not None and opening_stock > 0:
            if user_store_id is not None:
                effective_store_id = user_store_id
            else:
                raise ConflictException("store_id is required when opening_stock is provided")

        product_data["sku"] = sku
        product_data["barcode"] = barcode

        product = Product(
            tenant_id=tenant_id,
            **product_data,
        )

        product = self.repo.create(product)

        # Persist variants in product_variants table when supplied on product creation
        if raw_variants is not None:
            if not isinstance(raw_variants, list):
                raise ConflictException("variants must be a JSON array of variant objects")
            seen_variant_skus: set[str] = {sku}
            seen_variant_barcodes: set[str] = {barcode} if barcode else set()
            for idx, v_raw in enumerate(raw_variants):
                try:
                    v_schema = ProductVariantCreate.model_validate(v_raw)
                except Exception as exc:
                    raise ConflictException(f"Invalid variant at index {idx}: {exc}") from exc

                v_sku = v_schema.sku.strip().upper()
                if v_sku in seen_variant_skus or self.repo.is_sku_taken(v_sku, tenant_id):
                    raise ConflictException(f"Variant SKU '{v_sku}' already exists")
                seen_variant_skus.add(v_sku)

                v_barcode = v_schema.barcode.strip() if v_schema.barcode else None
                if not v_barcode and v_schema.auto_generate_barcode:
                    for _ in range(10):
                        cand = generate_ean13_barcode(tenant_id)
                        if cand not in seen_variant_barcodes and not self.repo.is_barcode_taken(cand, tenant_id):
                            v_barcode = cand
                            break
                if v_barcode:
                    if v_barcode in seen_variant_barcodes or self.repo.is_barcode_taken(v_barcode, tenant_id):
                        raise ConflictException(f"Variant barcode '{v_barcode}' already exists")
                    seen_variant_barcodes.add(v_barcode)

                variant = ProductVariant(
                    tenant_id=tenant_id,
                    product_id=product.id,
                    variant_name=v_schema.variant_name,
                    sku=v_sku,
                    barcode=v_barcode,
                    size=v_schema.size,
                    color=v_schema.color,
                    attributes=v_schema.attributes,
                    selling_price=v_schema.selling_price,
                    cost_price=v_schema.cost_price,
                    is_active=v_schema.is_active,
                )
                self.db.add(variant)
            self.db.flush()
            product._variants = None

        # Seed opening store stock (and batch record if applicable) atomically
        if opening_stock is not None and opening_stock > 0 and effective_store_id is not None:
            stock_in_kwargs: dict[str, Any] = {
                "store_id": effective_store_id,
                "product_id": product.id,
                "quantity": opening_stock,
                "notes": f"Opening stock on product creation ({product.sku})",
            }
            if product.batch_number:
                stock_in_kwargs["batch_number"] = product.batch_number
            elif product.track_batch:
                stock_in_kwargs["batch_number"] = f"OPEN-{product.sku[:20]}"
            if product.expiry_date and product.expiry_date > date.today():
                stock_in_kwargs["expiry_date"] = product.expiry_date
            if product.cost_price and product.cost_price >= Decimal("1.00"):
                stock_in_kwargs["unit_cost"] = product.cost_price

            InventoryService(self.db).stock_in(
                tenant_id=tenant_id,
                data=StockInRequest(**stock_in_kwargs),
                commit=False,
            )

        self.db.commit()
        self.db.expire(product)

        loaded = self.repo.get_by_id(product.id, tenant_id) or product
        return self._enrich_product_metadata(loaded, tenant_id, store_id=effective_store_id)

    def get_product(
        self,
        tenant_id: int,
        product_id: int,
        store_id: Optional[int] = None,
    ) -> Product:
        if product_id <= 0:
            raise NotFoundException(
                "Invalid product ID"
            )

        product = self.repo.get_by_id(
            product_id,
            tenant_id,
        )

        if not product:
            raise NotFoundException(
                "Product not found"
            )

        return self._enrich_product_metadata(product, tenant_id, store_id=store_id)

    def get_by_barcode(
        self,
        tenant_id: int,
        barcode: str,
        store_id: Optional[int] = None,
    ) -> Product:
        barcode = barcode.strip()

        if not barcode:
            raise NotFoundException(
                "Barcode cannot be empty"
            )

        if not barcode.isdigit():
            raise NotFoundException(
                "Invalid barcode"
            )

        if len(barcode) < 8 or len(barcode) > 50:
            raise NotFoundException(
                "Barcode must contain between 8 and 50 digits"
            )

        if len(set(barcode)) == 1:
            raise NotFoundException(
                "Invalid barcode"
            )

        product = self.repo.get_by_barcode(
            barcode,
            tenant_id,
        )

        if not product:
            raise NotFoundException(
                "Product not found for barcode"
            )

        return self._enrich_product_metadata(product, tenant_id, store_id=store_id)

    def search_products(
        self,
        tenant_id: int,
        query: str,
        page: int = 1,
        page_size: int = 20,
    ) -> list[Product]:
        if page <= 0:
            raise ConflictException(
                "Page must be greater than 0"
            )

        if page_size <= 0 or page_size > 100:
            raise ConflictException(
                "Page size must be between 1 and 100"
            )

        query = query.strip()

        if not query:
            raise ConflictException(
                "Search query cannot be empty"
            )

        if len(query) < 2:
            raise ConflictException(
                "Search query must contain at least 2 characters"
            )

        skip = (page - 1) * page_size

        products = self.repo.search_products(
            tenant_id,
            query,
            skip,
            page_size,
        )
        return products or []
    def list_products(
        self,
        tenant_id: int,
        page: int = 1,
        page_size: int = 20,
        include_inactive: bool = False,
        category_id: Optional[int] = None,
        brand: Optional[str] = None,
        stock_status: Optional[str] = None,
        min_price: Optional[Decimal] = None,
        max_price: Optional[Decimal] = None,
        sort_by: Optional[str] = None,
    ) -> list[Product]:
        if page <= 0:
            raise ConflictException(
                "Page must be greater than 0"
            )

        if page_size <= 0 or page_size > 100:
            raise ConflictException(
                "Page size must be between 1 and 100"
            )

        skip = (page - 1) * page_size

        return self.repo.list_products(
            tenant_id,
            skip,
            page_size,
            include_inactive,
            category_id=category_id,
            brand=brand,
            stock_status=stock_status,
            min_price=min_price,
            max_price=max_price,
            sort_by=sort_by,
        )

    def search_products_with_counts(
        self,
        tenant_id: int,
        query: str,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        from app.utils.pagination import compute_total_pages
        if page <= 0:
            raise ConflictException("Page must be greater than 0")
        if page_size <= 0 or page_size > 100:
            raise ConflictException("Page size must be between 1 and 100")
        query = query.strip()
        if not query:
            raise ConflictException("Search query cannot be empty")
        if len(query) < 2:
            raise ConflictException("Search query must contain at least 2 characters")

        skip = (page - 1) * page_size
        items, total, counts = self.repo.search_products_with_meta(tenant_id, query, skip, page_size)
        return {
            "success": True,
            "message": "Products retrieved successfully" if items else "No products found",
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": compute_total_pages(total, page_size),
            "counts": counts,
        }

    def list_products_with_counts(
        self,
        tenant_id: int,
        page: int = 1,
        page_size: int = 20,
        include_inactive: bool = False,
        category_id: Optional[int] = None,
        brand: Optional[str] = None,
        stock_status: Optional[str] = None,
        min_price: Optional[Decimal] = None,
        max_price: Optional[Decimal] = None,
        sort_by: Optional[str] = None,
    ) -> dict:
        from app.utils.pagination import compute_total_pages
        if page <= 0:
            raise ConflictException("Page must be greater than 0")
        if page_size <= 0 or page_size > 100:
            raise ConflictException("Page size must be between 1 and 100")

        skip = (page - 1) * page_size
        items, total, counts = self.repo.list_products_with_meta(
            tenant_id=tenant_id,
            skip=skip,
            limit=page_size,
            include_inactive=include_inactive,
            category_id=category_id,
            brand=brand,
            stock_status=stock_status,
            min_price=min_price,
            max_price=max_price,
            sort_by=sort_by,
        )
        return {
            "success": True,
            "message": "Products retrieved successfully" if items else "No products found",
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": compute_total_pages(total, page_size),
            "counts": counts,
        }

    def update_product(
        self,
        tenant_id: int,
        product_id: int,
        data: ProductUpdate,
    ) -> Product:
        product = self.get_product(
            tenant_id,
            product_id,
        )

        update_data = data.model_dump(
            exclude_unset=True
        )

        if "category_id" in update_data and update_data["category_id"] is not None:
            cat = self.db.query(Category).filter(
                Category.id == update_data["category_id"],
                Category.tenant_id == tenant_id,
            ).first()
            if not cat:
                raise ConflictException("Category not found or does not belong to this tenant")

        if "sku" in update_data:
            sku = update_data["sku"]

            if sku is not None:
                sku = sku.strip().upper()

                if not sku:
                    raise ConflictException(
                        "SKU cannot be empty"
                    )

                existing_sku = self.repo.get_by_sku(
                    sku,
                    tenant_id,
                )

                if (
                    existing_sku
                    and existing_sku.id != product.id
                ):
                    raise ConflictException(
                        "SKU already exists"
                    )

                update_data["sku"] = sku

        if "barcode" in update_data:
            barcode = update_data["barcode"]

            if barcode is not None:
                barcode = barcode.strip()

                if not barcode:
                    raise ConflictException(
                        "Barcode cannot be empty"
                    )

                if not barcode.isdigit():
                    raise ConflictException(
                        "Barcode must contain digits only"
                    )

                if len(barcode) < 8 or len(barcode) > 50:
                    raise ConflictException(
                        "Barcode must contain between 8 and 50 digits"
                    )

                if len(set(barcode)) == 1:
                    raise ConflictException(
                        "Barcode cannot consist of a single repeated digit"
                    )

                if self.repo.is_barcode_taken(
                    barcode,
                    tenant_id,
                    exclude_product_id=product.id,
                ):
                    raise ConflictException("Barcode already exists")

                update_data["barcode"] = barcode

        effective_sku = update_data.get(
            "sku",
            product.sku,
        )

        effective_barcode = update_data.get(
            "barcode",
            product.barcode,
        )

        if (
            effective_barcode
            and effective_sku == effective_barcode
        ):
            raise ConflictException(
                "SKU and Barcode cannot have the same value"
            )

        effective_mrp = update_data.get(
            "mrp",
            product.mrp,
        )

        effective_price = update_data.get(
            "selling_price",
            product.selling_price,
        )

        if (
            effective_mrp is not None
            and effective_price is not None
            and effective_mrp > 0
            and effective_mrp < effective_price
        ):
            raise ConflictException(
                "MRP cannot be lower than selling price"
            )

        effective_track_batch = update_data.get(
            "track_batch",
            product.track_batch,
        )

        effective_track_expiry = update_data.get(
            "track_expiry",
            product.track_expiry,
        )

        effective_batch_number = update_data.get(
            "batch_number",
            product.batch_number,
        )

        effective_expiry_date = update_data.get(
            "expiry_date",
            product.expiry_date,
        )

        if effective_track_batch:
            if (
                not effective_batch_number
                or not str(effective_batch_number).strip()
            ):
                raise ConflictException(
                    "batch_number is required when track_batch is true"
                )

            batch_value = str(
                effective_batch_number
            ).strip()

            if batch_value.lower() in {
                "string",
                "null",
                "none",
                "undefined",
                "test",
                "sample",
                "temp",
                "n/a",
                "na",
            }:
                raise ConflictException(
                    f"Batch number cannot be placeholder '{batch_value}'"
                )

        if effective_track_expiry:
            if effective_expiry_date is None:
                raise ConflictException(
                    "expiry_date is required when track_expiry is true"
                )

            if effective_expiry_date < date.today():
                raise ConflictException(
                    "expiry_date cannot be in the past"
                )

        if (
            "is_active" in update_data
            and not product.is_active
            and update_data["is_active"] is True
        ):
            if effective_expiry_date and effective_expiry_date < date.today():
                raise ConflictException("Cannot activate an expired product")
            entitlement_svc = SaaSEntitlementService(
                self.db
            )

            entitlement_svc.require_limit(
                tenant_id=tenant_id,
                dimension=EntitlementDimension.PRODUCTS,
                requested_amount=1,
                lock_tenant=True,
            )

        for key, value in update_data.items():
            setattr(
                product,
                key,
                value,
            )

        updated = self.repo.update(product)
        return self.repo.get_by_id(product.id, tenant_id) or updated

    def toggle_status(
        self,
        tenant_id: int,
        product_id: int,
    ) -> Product:
        product = self.repo.get_by_id(
            product_id,
            tenant_id,
        )

        if not product:
            raise NotFoundException(
                "Product not found"
            )

        # Quota check only when toggling inactive -> active
        if not product.is_active:
            from datetime import date
            if product.expiry_date and product.expiry_date < date.today():
                raise ConflictException("Cannot activate an expired product")
            entitlement_svc = SaaSEntitlementService(self.db)
            entitlement_svc.require_limit(
                tenant_id=tenant_id,
                dimension=EntitlementDimension.PRODUCTS,
                requested_amount=1,
                lock_tenant=True,
            )

        product.is_active = not product.is_active

        updated = self.repo.update(product)
        return self.repo.get_by_id(product.id, tenant_id) or updated

    def delete_product(
        self,
        tenant_id: int,
        product_id: int,
    ) -> None:
        product = self.get_product(
            tenant_id,
            product_id,
        )

        if self.repo.has_transactions(product.id):
            raise HTTPException(
                status_code=400,
                detail="Cannot delete product with existing sales, purchase, or transfer records. Deactivate it instead.",
            )

        # Delete image files on disk
        for img in product.images:
            if img.image_url and img.image_url.startswith("/uploads/products/"):
                rel_path = img.image_url.lstrip("/")
                try:
                    if os.path.exists(rel_path):
                        os.remove(rel_path)
                except Exception:
                    pass

        self.repo.delete(product)

    def get_barcode_image(
        self,
        tenant_id: int,
        product_id: int,
    ) -> bytes:
        product = self.get_product(
            tenant_id,
            product_id,
        )

        if not product.barcode:
            raise NotFoundException(
                "Product has no barcode"
            )

        return generate_barcode_image(
            product.barcode,
            product.name,
        )

    def list_low_stock(
        self,
        tenant_id: int,
        store_id: int,
        threshold: int = 10,
    ) -> List[ProductLowStockResponse]:
        if store_id <= 0:
            raise ConflictException(
                "Store ID must be greater than 0"
            )

        if threshold <= 0:
            raise ConflictException(
                "Threshold must be greater than 0"
            )

        if threshold > 1000000:
            raise ConflictException(
                "Threshold must not exceed 1000000"
            )

        store = (
            self.db.query(Store)
            .filter(
                Store.id == store_id,
                Store.tenant_id == tenant_id,
                Store.is_active.is_(True),
            )
            .first()
        )

        if not store:
            raise NotFoundException(
                "Store not found"
            )

        rows = self.repo.list_low_stock(
            tenant_id,
            store_id,
            threshold,
        )

        result = []

        for product, qty in rows:
            response = ProductLowStockResponse.model_validate(
                product
            )

            response.store_id = store_id
            response.current_stock = qty
            response.quantity = qty
            response.threshold = threshold

            result.append(response)

        return result

    def list_low_stock_with_counts(
        self,
        tenant_id: int,
        store_id: int,
        threshold: int = 10,
    ) -> dict:
        items = self.list_low_stock(tenant_id, store_id, threshold)
        total = len(items)
        return {
            "success": True,
            "message": "Low stock products retrieved successfully" if items else "No low stock products found",
            "items": items,
            "total": total,
            "page": 1,
            "page_size": total,
            "total_pages": 1 if total > 0 else 0,
            "counts": {"total": total},
        }

    def list_expiring_soon(
        self,
        tenant_id: int,
        store_id: int,
        days: int = 30,
    ) -> list[Product]:
        if store_id <= 0:
            raise ConflictException(
                "Store ID must be greater than 0"
            )

        if days <= 0 or days > 365:
            raise ConflictException(
                "Days must be between 1 and 365"
            )

        store = (
            self.db.query(Store)
            .filter(
                Store.id == store_id,
                Store.tenant_id == tenant_id,
                Store.is_active.is_(True),
            )
            .first()
        )

        if not store:
            raise NotFoundException(
                "Store not found"
            )

        return self.repo.list_expiring_soon(
            tenant_id,
            store_id,
            days,
        )

    def list_expiring_soon_with_counts(
        self,
        tenant_id: int,
        store_id: int,
        days: int = 30,
    ) -> dict:
        items = self.list_expiring_soon(tenant_id, store_id, days)
        total = len(items)
        return {
            "success": True,
            "message": "Expiring products retrieved successfully" if items else "No expiring products found",
            "items": items,
            "total": total,
            "page": 1,
            "page_size": total,
            "total_pages": 1 if total > 0 else 0,
            "counts": {"total": total},
        }

    def generate_barcode_for_product(
        self,
        tenant_id: int,
        product_id: int,
        overwrite: bool = False,
    ) -> Product:
        product = self.get_product(
            tenant_id,
            product_id,
        )

        # If product already has a barcode and overwrite is false,
        # safely and idempotently return the existing barcode instead of raising 409
        if product.barcode and not overwrite:
            return product

        for _ in range(15):
            candidate = generate_ean13_barcode(tenant_id)
            if not self.repo.is_barcode_taken(candidate, tenant_id, exclude_product_id=product.id):
                product.barcode = candidate
                self.db.commit()
                self.db.refresh(product)
                return product

        raise ConflictException("Failed to generate a unique barcode. Please try again.")

    def generate_missing_barcodes(
        self,
        tenant_id: int,
    ) -> dict:
        products_without_barcode = (
            self.db.query(Product)
            .filter(
                Product.tenant_id == tenant_id,
                (Product.barcode.is_(None) | (Product.barcode == "")),
            )
            .all()
        )

        updated_count = 0
        for p in products_without_barcode:
            for _ in range(10):
                candidate = generate_ean13_barcode(tenant_id)
                if not self.repo.is_barcode_taken(candidate, tenant_id):
                    p.barcode = candidate
                    updated_count += 1
                    break

        if updated_count > 0:
            self.db.commit()

        return {
            "success": True,
            "total_checked": len(products_without_barcode),
            "updated_count": updated_count,
            "message": f"Successfully generated barcodes for {updated_count} products",
        }

    def get_catalog_summary(
        self,
        tenant_id: int,
        store_id: Optional[int] = None,
    ) -> dict:
        if store_id is not None:
            store = (
                self.db.query(Store)
                .filter(
                    Store.id == store_id,
                    Store.tenant_id == tenant_id,
                )
                .first()
            )
            if not store:
                raise NotFoundException("Store not found")

        return self.repo.get_catalog_summary(
            tenant_id=tenant_id,
            store_id=store_id,
        )

    def get_barcode_label(
        self,
        tenant_id: int,
        product_id: int,
        store_id: Optional[int] = None,
    ) -> dict:
        product = self.get_product(tenant_id, product_id)

        # If product has no barcode, auto-generate one
        if not product.barcode:
            product = self.generate_barcode_for_product(tenant_id, product_id)

        store_name = None
        if store_id is not None:
            store = (
                self.db.query(Store)
                .filter(
                    Store.id == store_id,
                    Store.tenant_id == tenant_id,
                )
                .first()
            )
            if store:
                store_name = store.name

        if not store_name:
            main_store = (
                self.db.query(Store)
                .filter(Store.tenant_id == tenant_id, Store.is_active.is_(True))
                .order_by(Store.is_main.desc(), Store.id.asc())
                .first()
            )
            if main_store:
                store_name = main_store.name

        sticker_bytes = generate_thermal_sticker_image(
            barcode_value=product.barcode,
            product_name=product.name,
            selling_price=product.selling_price,
            mrp=product.mrp,
            store_name=store_name,
            sku=product.sku,
        )
        b64_str = base64.b64encode(sticker_bytes).decode("ascii")

        return {
            "product_id": product.id,
            "product_name": product.name,
            "sku": product.sku,
            "barcode": product.barcode,
            "mrp": product.mrp,
            "selling_price": product.selling_price,
            "store_name": store_name,
            "currency_symbol": "₹",
            "barcode_image_base64": f"data:image/png;base64,{b64_str}",
            "label_format": "50x25mm",
        }

    def get_barcode_sticker_image(
        self,
        tenant_id: int,
        product_id: int,
        store_id: Optional[int] = None,
    ) -> bytes:
        product = self.get_product(tenant_id, product_id)
        if not product.barcode:
            product = self.generate_barcode_for_product(tenant_id, product_id)

        store_name = None
        if store_id is not None:
            store = (
                self.db.query(Store)
                .filter(
                    Store.id == store_id,
                    Store.tenant_id == tenant_id,
                )
                .first()
            )
            if store:
                store_name = store.name

        if not store_name:
            main_store = (
                self.db.query(Store)
                .filter(Store.tenant_id == tenant_id, Store.is_active.is_(True))
                .order_by(Store.is_main.desc(), Store.id.asc())
                .first()
            )
            if main_store:
                store_name = main_store.name

        return generate_thermal_sticker_image(
            barcode_value=product.barcode,
            product_name=product.name,
            selling_price=product.selling_price,
            mrp=product.mrp,
            store_name=store_name,
            sku=product.sku,
        )
