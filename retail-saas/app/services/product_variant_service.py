
from typing import Any, Dict

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictException, NotFoundException
from app.models.product_variant import ProductVariant
from app.repositories.product_repo import ProductRepository
from app.schemas.product_variant import (
    ProductVariantCreate,
    ProductVariantUpdate,
)


class ProductVariantService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = ProductRepository(db)

    def create_variant(
        self,
        tenant_id: int,
        product_id: int,
        data: ProductVariantCreate,
    ) -> ProductVariant:
        if product_id <= 0:
            raise NotFoundException("Invalid product ID")

        product = self.repo.get_by_id(product_id, tenant_id)

        if not product:
            raise NotFoundException("Product not found")

        sku = data.sku.strip().upper()

        if self.repo.is_sku_taken(sku, tenant_id):
            raise ConflictException(
                f"SKU '{sku}' already exists"
            )

        barcode = data.barcode.strip() if data.barcode else None

        if barcode and self.repo.is_barcode_taken(
            barcode,
            tenant_id,
        ):
            raise ConflictException(
                f"Barcode '{barcode}' already exists"
            )

        variant_data = data.model_dump(exclude={"product_id"})
        variant_data["sku"] = sku
        variant_data["barcode"] = barcode

        variant = ProductVariant(
            tenant_id=tenant_id,
            product_id=product_id,
            **variant_data,
        )

        try:
            self.repo.create_variant(variant)
            self.db.commit()
            self.db.refresh(variant)
            return variant
        except Exception:
            self.db.rollback()
            raise

    def get_variant(
        self,
        tenant_id: int,
        variant_id: int,
        product_id: int | None = None,
    ) -> ProductVariant:
        if variant_id <= 0:
            raise NotFoundException("Invalid variant ID")

        variant = self.repo.get_variant_by_id(
            variant_id,
            tenant_id,
        )

        if not variant or not variant.is_active:
            raise NotFoundException(
                "Product variant not found"
            )

        if (
            product_id is not None
            and variant.product_id != product_id
        ):
            raise NotFoundException(
                "Product variant not found for this product"
            )

        return variant

    def list_variants(
        self,
        tenant_id: int,
        product_id: int,
        page: int = 1,
        page_size: int = 20,
        include_inactive: bool = False,
    ) -> Dict[str, Any]:
        if product_id <= 0:
            raise NotFoundException("Invalid product ID")

        product = self.repo.get_by_id(
            product_id,
            tenant_id,
        )

        if not product:
            raise NotFoundException("Product not found")

        if page <= 0:
            raise ConflictException(
                "Page must be greater than 0"
            )

        if page_size <= 0 or page_size > 100:
            raise ConflictException(
                "Page size must be between 1 and 100"
            )

        skip = (page - 1) * page_size

        items = self.repo.list_variants(
            product_id=product_id,
            tenant_id=tenant_id,
            include_inactive=include_inactive,
            skip=skip,
            limit=page_size,
        )

        total = self.repo.count_variants(
            product_id=product_id,
            tenant_id=tenant_id,
            include_inactive=include_inactive,
        )

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": items,
        }

    def update_variant(
        self,
        tenant_id: int,
        variant_id: int,
        data: ProductVariantUpdate,
    ) -> ProductVariant:
        variant = self.get_variant(
            tenant_id,
            variant_id,
        )

        update_data = data.model_dump(exclude_unset=True)

        if "sku" in update_data:
            new_sku = update_data["sku"].strip().upper()

            if self.repo.is_sku_taken(
                new_sku,
                tenant_id,
                exclude_variant_id=variant.id,
            ):
                raise ConflictException(
                    f"SKU '{new_sku}' already exists"
                )

            update_data["sku"] = new_sku

        if "barcode" in update_data:
            new_barcode = update_data["barcode"]

            if new_barcode is not None:
                new_barcode = new_barcode.strip() or None

            if new_barcode and self.repo.is_barcode_taken(
                new_barcode,
                tenant_id,
                exclude_variant_id=variant.id,
            ):
                raise ConflictException(
                    f"Barcode '{new_barcode}' already exists"
                )

            update_data["barcode"] = new_barcode

        for key, value in update_data.items():
            setattr(variant, key, value)

        try:
            return self.repo.update_variant(variant)
        except Exception:
            self.db.rollback()
            raise

    def delete_variant(
        self,
        tenant_id: int,
        variant_id: int,
    ) -> ProductVariant:
        variant = self.get_variant(
            tenant_id,
            variant_id,
        )

        try:
            self.repo.delete_variant(variant)
            return variant
        except Exception:
            self.db.rollback()
            raise
