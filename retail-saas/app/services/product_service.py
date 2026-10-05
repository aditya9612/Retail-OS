from datetime import date
from typing import List

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictException, NotFoundException
from app.models.product import Product
from app.models.saas_plan_entitlement import EntitlementDimension
from app.models.store import Store
from app.repositories.product_repo import ProductRepository
from app.schemas.product import (
    ProductCreate,
    ProductLowStockResponse,
    ProductUpdate,
)
from app.services.saas_entitlement_service import SaaSEntitlementService
from app.utils.barcode_generator import generate_barcode_image


class ProductService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = ProductRepository(db)

    def create_product(
        self,
        tenant_id: int,
        data: ProductCreate,
    ) -> Product:
        sku = data.sku.strip().upper()
        barcode = data.barcode.strip() if data.barcode else None

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

            if self.repo.get_by_barcode(
                barcode,
                tenant_id,
            ):
                raise ConflictException(
                    "Barcode already exists"
                )

        if self.repo.get_by_sku(
            sku,
            tenant_id,
        ):
            raise ConflictException(
                "SKU already exists"
            )

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

        product_data["sku"] = sku
        product_data["barcode"] = barcode

        batch_num = product_data.pop(
            "batch_number",
            None,
        )

        exp_date = product_data.pop(
            "expiry_date",
            None,
        )

        product = Product(
            tenant_id=tenant_id,
            **product_data,
        )

        if batch_num is not None:
            product.batch_number = batch_num

        if exp_date is not None:
            product.expiry_date = exp_date

        product = self.repo.create(product)

        self.db.commit()
        self.db.refresh(product)

        return product

    def get_product(
        self,
        tenant_id: int,
        product_id: int,
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

        return product

    def get_by_barcode(
        self,
        tenant_id: int,
        barcode: str,
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

        return product

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

        if not products:
            raise NotFoundException(
                f"No products found matching '{query}'"
            )

        return products

    def list_products(
        self,
        tenant_id: int,
        page: int = 1,
        page_size: int = 20,
        include_inactive: bool = False,
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
        )

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

                existing = self.repo.get_by_barcode(
                    barcode,
                    tenant_id,
                )

                if (
                    existing
                    and existing.id != product.id
                ):
                    raise ConflictException(
                        "Barcode already exists"
                    )

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

        return self.repo.update(product)

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

        if not product.is_active:
            raise ConflictException(
                "Inactive product cannot be toggled. Activate it using product update."
            )

        product.is_active = False

        return self.repo.update(product)

    def delete_product(
        self,
        tenant_id: int,
        product_id: int,
    ) -> None:
        product = self.get_product(
            tenant_id,
            product_id,
        )

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