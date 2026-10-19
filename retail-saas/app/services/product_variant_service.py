from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictException, NotFoundException
from app.models.product_variant import ProductVariant
from app.repositories.product_repo import ProductRepository
from app.schemas.product_variant import (
    ProductVariantCreate,
    ProductVariantUpdate,
    VariantMatrixGenerateRequest,
)
from app.utils.barcode_generator import generate_ean13_barcode


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
        if not barcode and getattr(data, "auto_generate_barcode", False):
            for _ in range(10):
                candidate_bc = generate_ean13_barcode(tenant_id)
                if not self.repo.is_barcode_taken(candidate_bc, tenant_id):
                    barcode = candidate_bc
                    break

        if barcode:
            if not barcode.isdigit():
                raise ConflictException("Barcode must contain digits only")
            if len(barcode) < 8 or len(barcode) > 50:
                raise ConflictException("Barcode must contain between 8 and 50 digits")
            if self.repo.is_barcode_taken(barcode, tenant_id):
                raise ConflictException(f"Barcode '{barcode}' already exists")

        # Check duplicate variant attribute matrix or name for this parent product
        existing_variants = (
            self.db.query(ProductVariant)
            .filter(
                ProductVariant.tenant_id == tenant_id,
                ProductVariant.product_id == product_id,
                ProductVariant.is_active == True,
            )
            .all()
        )
        d_name = data.variant_name.strip().lower() if data.variant_name else None
        d_size = data.size.strip().lower() if data.size else None
        d_color = data.color.strip().lower() if data.color else None

        for ev in existing_variants:
            ev_name = ev.variant_name.strip().lower() if ev.variant_name else None
            ev_size = ev.size.strip().lower() if ev.size else None
            ev_color = ev.color.strip().lower() if ev.color else None

            if d_name and ev_name and d_name == ev_name:
                raise ConflictException(
                    f"Product variant with name '{data.variant_name.strip()}' already exists for this product"
                )
            if d_size and d_color and ev_size == d_size and ev_color == d_color:
                raise ConflictException(
                    f"Product variant with size '{data.size.strip()}' and color '{data.color.strip()}' already exists for this product"
                )

        variant_dict = data.model_dump()
        variant_dict.pop("auto_generate_barcode", None)
        variant_dict.pop("product_id", None)
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

        new_name = update_data.get("variant_name") or variant.variant_name
        new_size = update_data.get("size") if "size" in update_data else variant.size
        new_color = update_data.get("color") if "color" in update_data else variant.color

        if "variant_name" in update_data or "size" in update_data or "color" in update_data:
            existing_others = (
                self.db.query(ProductVariant)
                .filter(
                    ProductVariant.tenant_id == tenant_id,
                    ProductVariant.product_id == variant.product_id,
                    ProductVariant.id != variant_id,
                    ProductVariant.is_active == True,
                )
                .all()
            )
            d_name = new_name.strip().lower() if new_name else None
            d_size = new_size.strip().lower() if new_size else None
            d_color = new_color.strip().lower() if new_color else None

            for ev in existing_others:
                ev_name = ev.variant_name.strip().lower() if ev.variant_name else None
                ev_size = ev.size.strip().lower() if ev.size else None
                ev_color = ev.color.strip().lower() if ev.color else None

                if d_name and ev_name and d_name == ev_name:
                    raise ConflictException(
                        f"Product variant with name '{new_name.strip()}' already exists for this product"
                    )
                if d_size and d_color and ev_size == d_size and ev_color == d_color:
                    raise ConflictException(
                        f"Product variant with size '{new_size.strip()}' and color '{new_color.strip()}' already exists for this product"
                    )

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

    def list_all_variants(
        self,
        tenant_id: int,
        product_id: Optional[int] = None,
        search: Optional[str] = None,
        size: Optional[str] = None,
        color: Optional[str] = None,
        is_active: Optional[bool] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        if page <= 0:
            raise ConflictException("Page must be greater than 0")
        if page_size <= 0 or page_size > 100:
            raise ConflictException("Page size must be between 1 and 100")

        skip = (page - 1) * page_size
        items = self.repo.list_all_variants(
            tenant_id=tenant_id,
            product_id=product_id,
            search=search,
            size=size,
            color=color,
            is_active=is_active,
            skip=skip,
            limit=page_size,
        )
        total = self.repo.count_all_variants(
            tenant_id=tenant_id,
            product_id=product_id,
            search=search,
            size=size,
            color=color,
            is_active=is_active,
        )

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": items,
        }

    def get_variant_by_barcode(
        self,
        tenant_id: int,
        barcode: str,
    ) -> ProductVariant:
        barcode = barcode.strip() if barcode else ""
        if not barcode:
            raise NotFoundException("Barcode cannot be empty")

        variant = self.repo.get_variant_by_barcode(barcode, tenant_id)
        if not variant:
            raise NotFoundException(f"Product variant with barcode '{barcode}' not found")

        return variant

    def get_variant_by_sku(
        self,
        tenant_id: int,
        sku: str,
    ) -> ProductVariant:
        sku = sku.strip().upper() if sku else ""
        if not sku:
            raise NotFoundException("SKU cannot be empty")

        variant = self.repo.get_variant_by_sku(sku, tenant_id)
        if not variant:
            raise NotFoundException(f"Product variant with SKU '{sku}' not found")

        return variant

    def set_variant_active_status(
        self,
        tenant_id: int,
        variant_id: int,
        is_active: bool,
    ) -> ProductVariant:
        variant = self.get_variant(tenant_id, variant_id)
        variant.is_active = is_active
        self.db.commit()
        self.db.refresh(variant)
        return variant

    def generate_variant_matrix(
        self,
        tenant_id: int,
        data: VariantMatrixGenerateRequest,
    ) -> Dict[str, Any]:
        import re

        product = self.repo.get_by_id(data.product_id, tenant_id)
        if not product:
            raise NotFoundException(f"Product with ID {data.product_id} not found")

        sizes = [s for s in data.sizes if s]
        colors = [c for c in data.colors if c]

        if not sizes and not colors:
            raise ConflictException("At least one size or one color must be provided")

        base_prefix = data.sku_prefix or product.sku or f"PROD-{product.id}"
        base_prefix = base_prefix.strip().upper()

        combos: List[tuple[Optional[str], Optional[str]]] = []
        if sizes and colors:
            for s in sizes:
                for c in colors:
                    combos.append((s, c))
        elif sizes:
            for s in sizes:
                combos.append((s, None))
        else:
            for c in colors:
                combos.append((None, c))

        generated_variants = []

        def clean_token(val: str) -> str:
            return re.sub(r"[^A-Za-z0-9]", "", val).upper()

        for s, c in combos:
            if s and c:
                v_name = f"{product.name} - {s} / {c}"
                cand_sku = f"{base_prefix}-{clean_token(s)}-{clean_token(c)}"
            elif s:
                v_name = f"{product.name} - {s}"
                cand_sku = f"{base_prefix}-{clean_token(s)}"
            else:
                v_name = f"{product.name} - {c}"
                cand_sku = f"{base_prefix}-{clean_token(c)}"

            final_sku = cand_sku
            counter = 1
            while self.repo.is_sku_taken(final_sku, tenant_id):
                final_sku = f"{cand_sku}-{counter}"
                counter += 1

            var_barcode = None
            if getattr(data, "auto_generate_barcode", True):
                for _ in range(15):
                    candidate_bc = generate_ean13_barcode(tenant_id)
                    if not self.repo.is_barcode_taken(candidate_bc, tenant_id):
                        var_barcode = candidate_bc
                        break

            variant = ProductVariant(
                tenant_id=tenant_id,
                product_id=product.id,
                variant_name=v_name,
                sku=final_sku,
                barcode=var_barcode,
                size=s,
                color=c,
                attributes=data.attributes,
                selling_price=data.selling_price,
                cost_price=data.cost_price,
                is_active=True,
            )
            self.repo.create_variant(variant)
            generated_variants.append(variant)

        self.db.commit()
        for v in generated_variants:
            self.db.refresh(v)

        return {
            "product_id": product.id,
            "product_name": product.name,
            "generated_count": len(generated_variants),
            "variants": generated_variants,
        }

    def generate_barcode_for_variant(
        self,
        tenant_id: int,
        variant_id: int,
        overwrite: bool = False,
    ) -> ProductVariant:
        variant = self.get_variant(tenant_id, variant_id)
        if variant.barcode and not overwrite:
            raise ConflictException(
                f"Variant already has barcode '{variant.barcode}'. Pass overwrite=true to replace."
            )

        for _ in range(15):
            candidate = generate_ean13_barcode(tenant_id)
            if not self.repo.is_barcode_taken(candidate, tenant_id, exclude_variant_id=variant.id):
                variant.barcode = candidate
                self.db.commit()
                self.db.refresh(variant)
                return variant

        raise ConflictException("Failed to generate a unique barcode. Please try again.")

    def generate_missing_barcodes(
        self,
        tenant_id: int,
    ) -> Dict[str, Any]:
        variants_without_barcode = (
            self.db.query(ProductVariant)
            .filter(
                ProductVariant.tenant_id == tenant_id,
                (ProductVariant.barcode.is_(None)) | (ProductVariant.barcode == ""),
            )
            .all()
        )

        updated_count = 0
        updated_variants = []
        for v in variants_without_barcode:
            for _ in range(15):
                candidate = generate_ean13_barcode(tenant_id)
                if not self.repo.is_barcode_taken(candidate, tenant_id, exclude_variant_id=v.id):
                    v.barcode = candidate
                    updated_count += 1
                    updated_variants.append({
                        "id": v.id,
                        "variant_name": v.variant_name,
                        "sku": v.sku,
                        "barcode": candidate,
                    })
                    break

        if updated_count > 0:
            self.db.commit()

        return {
            "success": True,
            "message": f"Generated barcodes for {updated_count} variants",
            "updated_count": updated_count,
            "variants": updated_variants,
        }


