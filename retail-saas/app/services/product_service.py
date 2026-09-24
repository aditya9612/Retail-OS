from datetime import date
from decimal import Decimal
from typing import Optional, Dict, Any

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictException, NotFoundException
from app.models.product import Product
from app.models.saas_plan_entitlement import EntitlementDimension
from app.models.store import Store
from app.repositories.product_repo import ProductRepository
from app.schemas.product import ProductCreate, ProductUpdate
from app.services.saas_entitlement_service import SaaSEntitlementService
from app.utils.barcode_generator import generate_barcode_image


class ProductService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = ProductRepository(db)

    def create_product(self, tenant_id: int, data: ProductCreate) -> Product:
        sku = data.sku.strip().upper()
        barcode = data.barcode.strip() if data.barcode else None

        if not sku:
            raise ConflictException("SKU cannot be empty")

        if barcode:
            if not barcode.isdigit():
                raise ConflictException("Barcode must contain digits only")

            if len(barcode) < 8 or len(barcode) > 50:
                raise ConflictException(
                    "Barcode must contain between 8 and 50 digits"
                )

            if self.repo.get_by_barcode(barcode, tenant_id):
                raise ConflictException("Barcode already exists")

        if self.repo.get_by_sku(sku, tenant_id):
            raise ConflictException("SKU already exists")

        # Atomic tenant lock & quota check
        entitlement_svc = SaaSEntitlementService(self.db)
        entitlement_svc.require_limit(
            tenant_id=tenant_id,
            dimension=EntitlementDimension.PRODUCTS,
            requested_amount=1,
            lock_tenant=True,
        )

        product_data = data.model_dump()
        product_data["sku"] = sku
        product_data["barcode"] = barcode

        product = Product(
            tenant_id=tenant_id,
            **product_data,
        )

        product = self.repo.create(product)
        self.db.commit()
        self.db.refresh(product)
        return product

    def get_product(self, tenant_id: int, product_id: int) -> Product:
        if product_id <= 0:
            raise NotFoundException("Invalid product ID")

        product = self.repo.get_by_id(product_id, tenant_id)

        if not product:
            raise NotFoundException("Product not found")

        return product

    def get_by_barcode(self, tenant_id: int, barcode: str) -> Product:
        barcode = barcode.strip()

        if not barcode:
            raise NotFoundException("Barcode cannot be empty")

        if not barcode.isdigit():
            raise NotFoundException("Invalid barcode")

        product = self.repo.get_by_barcode(barcode, tenant_id)

        if not product:
            raise NotFoundException("Product not found for barcode")

        return product

    def search_products(
        self,
        tenant_id: int,
        query: str,
        page: int = 1,
        page_size: int = 20,
    ) -> list[Product]:
        if page <= 0:
            raise ConflictException("Page must be greater than 0")

        if page_size <= 0 or page_size > 100:
            raise ConflictException("Page size must be between 1 and 100")

        query = query.strip()

        if not query:
            raise ConflictException("Search query cannot be empty")

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
            raise ConflictException("Page must be greater than 0")

        if page_size <= 0 or page_size > 100:
            raise ConflictException("Page size must be between 1 and 100")

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
        product = self.get_product(tenant_id, product_id)

        update_data = data.model_dump(exclude_unset=True)

        if "barcode" in update_data:
            barcode = update_data["barcode"]

            if barcode is None or not barcode.strip():
                raise ConflictException("Barcode cannot be empty")

            barcode = barcode.strip()

            if not barcode.isdigit():
                raise ConflictException(
                    "Barcode must contain digits only"
                )

            if len(barcode) < 8 or len(barcode) > 50:
                raise ConflictException(
                    "Barcode must contain between 8 and 50 digits"
                )

            existing = self.repo.get_by_barcode(
                barcode,
                tenant_id,
            )

            if existing and existing.id != product.id:
                raise ConflictException("Barcode already exists")

            update_data["barcode"] = barcode

        # Quota check only when reactivating: False -> True
        if "is_active" in update_data and not product.is_active and update_data["is_active"] is True:
            entitlement_svc = SaaSEntitlementService(self.db)
            entitlement_svc.require_limit(
                tenant_id=tenant_id,
                dimension=EntitlementDimension.PRODUCTS,
                requested_amount=1,
                lock_tenant=True,
            )

        for key, value in update_data.items():
            setattr(product, key, value)

        return self.repo.update(product)

    def toggle_status(
        self,
        tenant_id: int,
        product_id: int,
    ) -> Product:
        product = self.repo.get_by_id(product_id, tenant_id)

        if not product:
            raise NotFoundException("Product not found")

        # Quota check only when toggling inactive -> active
        if not product.is_active:
            entitlement_svc = SaaSEntitlementService(self.db)
            entitlement_svc.require_limit(
                tenant_id=tenant_id,
                dimension=EntitlementDimension.PRODUCTS,
                requested_amount=1,
                lock_tenant=True,
            )

        product.is_active = not product.is_active

        return self.repo.update(product)

    def delete_product(
        self,
        tenant_id: int,
        product_id: int,
    ) -> None:
        product = self.get_product(tenant_id, product_id)
        self.repo.delete(product)

    def get_barcode_image(
        self,
        tenant_id: int,
        product_id: int,
    ) -> bytes:
        product = self.get_product(tenant_id, product_id)

        if not product.barcode:
            raise NotFoundException("Product has no barcode")

        return generate_barcode_image(
            product.barcode,
            product.name,
        )

    def list_low_stock(
        self,
        tenant_id: int,
        store_id: int,
        threshold: int = 10,
    ) -> list[Product]:
        if store_id <= 0:
            raise ConflictException("Store ID must be greater than 0")

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
            raise NotFoundException("Store not found")

        return self.repo.list_low_stock(
            tenant_id,
            store_id,
            threshold,
        )

    def list_expiring_soon(
        self,
        tenant_id: int,
        store_id: int,
        days: int = 30,
    ) -> list[Product]:
        if store_id <= 0:
            raise ConflictException("Store ID must be greater than 0")

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
            raise NotFoundException("Store not found")

        return self.repo.list_expiring_soon(
            tenant_id,
            store_id,
            days,
        )