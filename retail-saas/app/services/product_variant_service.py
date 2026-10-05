from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictException, NotFoundException
from app.models.product_variant import ProductVariant
from app.repositories.product_repo import ProductRepository
from app.schemas.product_variant import ProductVariantCreate, ProductVariantUpdate


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

        # Verify parent product exists and belongs to tenant
        product = self.repo.get_by_id(product_id, tenant_id)
        if not product:
            raise NotFoundException("Product not found")

        sku = data.sku.strip().upper()
        if not sku:
            raise ConflictException("SKU cannot be empty")

        if self.repo.is_sku_taken(sku, tenant_id):
            raise ConflictException(f"SKU '{sku}' already exists")

        barcode = data.barcode.strip() if data.barcode else None
        if barcode:
            if not barcode.isdigit():
                raise ConflictException("Barcode must contain digits only")
            if len(barcode) < 8 or len(barcode) > 50:
                raise ConflictException("Barcode must contain between 8 and 50 digits")
            if self.repo.is_barcode_taken(barcode, tenant_id):
                raise ConflictException(f"Barcode '{barcode}' already exists")

        variant_dict = data.model_dump()
        variant_dict["sku"] = sku
        variant_dict["barcode"] = barcode

        variant = ProductVariant(
            tenant_id=tenant_id,
            product_id=product_id,
            **variant_dict,
        )

        variant = self.repo.create_variant(variant)
        self.db.commit()
        self.db.refresh(variant)
        return variant

    def get_variant(
        self,
        tenant_id: int,
        variant_id: int,
    ) -> ProductVariant:
        if variant_id <= 0:
            raise NotFoundException("Invalid variant ID")

        variant = self.repo.get_variant_by_id(variant_id, tenant_id)
        if not variant:
            raise NotFoundException("Product variant not found")

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

        product = self.repo.get_by_id(product_id, tenant_id)
        if not product:
            raise NotFoundException("Product not found")

        if page <= 0:
            raise ConflictException("Page must be greater than 0")
        if page_size <= 0 or page_size > 100:
            raise ConflictException("Page size must be between 1 and 100")

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
        variant = self.get_variant(tenant_id, variant_id)
        update_data = data.model_dump(exclude_unset=True)

        if "sku" in update_data and update_data["sku"]:
            new_sku = update_data["sku"].strip().upper()
            if not new_sku:
                raise ConflictException("SKU cannot be empty")
            if new_sku != variant.sku and self.repo.is_sku_taken(
                new_sku, tenant_id, exclude_variant_id=variant.id
            ):
                raise ConflictException(f"SKU '{new_sku}' already exists")
            update_data["sku"] = new_sku

        if "barcode" in update_data:
            new_barcode = (
                update_data["barcode"].strip() if update_data["barcode"] else None
            )
            if new_barcode:
                if not new_barcode.isdigit():
                    raise ConflictException("Barcode must contain digits only")
                if len(new_barcode) < 8 or len(new_barcode) > 50:
                    raise ConflictException(
                        "Barcode must contain between 8 and 50 digits"
                    )
                if new_barcode != variant.barcode and self.repo.is_barcode_taken(
                    new_barcode, tenant_id, exclude_variant_id=variant.id
                ):
                    raise ConflictException(f"Barcode '{new_barcode}' already exists")
            update_data["barcode"] = new_barcode

        for key, value in update_data.items():
            setattr(variant, key, value)

        return self.repo.update_variant(variant)

    def delete_variant(
        self,
        tenant_id: int,
        variant_id: int,
    ) -> ProductVariant:
        variant = self.get_variant(tenant_id, variant_id)
        self.repo.delete_variant(variant)
        return variant
