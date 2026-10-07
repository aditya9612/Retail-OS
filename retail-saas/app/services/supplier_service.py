from typing import Union
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import func

from app.core.exceptions import AppException, NotFoundException
from app.models.purchase_order import PurchaseOrder
from app.models.supplier import Supplier
from app.schemas.purchase_order import PurchaseOrderResponse
from app.schemas.supplier import (
    SupplierCreate,
    SupplierEmptyResponse,
    SupplierPurchaseHistoryResponse,
    SupplierResponse,
    SupplierUpdate,
)


class SupplierService:

    def __init__(self, db: Session):
        self.db = db

    def create_supplier(
        self,
        tenant_id: int,
        data: SupplierCreate,
    ) -> Supplier:

        supplier = Supplier(
            tenant_id=tenant_id,
            name=data.name,
            contact_person=data.contact_person,
            email=str(data.email) if data.email else None,
            phone=data.phone,
            address=data.address,
            gstin=data.gstin,
            is_active=True,
        )

        try:
            self.db.add(supplier)
            self.db.commit()
            self.db.refresh(supplier)

        except Exception:
            self.db.rollback()
            raise

        return supplier

    def list_suppliers(
        self,
        tenant_id: int,
    ) -> Union[list[SupplierResponse], SupplierEmptyResponse]:

        suppliers = (
            self.db.query(Supplier)
            .filter(
                Supplier.tenant_id == tenant_id
            )
            .order_by(Supplier.created_at.desc())
            .all()
        )

        if not suppliers:
            return SupplierEmptyResponse(
                success=True,
                message="No suppliers found",
                data=[],
            )

        return [SupplierResponse.model_validate(s) for s in suppliers]

    def get_supplier(
        self,
        tenant_id: int,
        supplier_id: int,
    ) -> Supplier:

        supplier = (
            self.db.query(Supplier)
            .filter(
                Supplier.id == supplier_id,
                Supplier.tenant_id == tenant_id,
            )
            .first()
        )

        if not supplier:
            raise NotFoundException(
                "Supplier not found"
            )

        return supplier

    def update_supplier(
        self,
        tenant_id: int,
        supplier_id: int,
        data: SupplierUpdate,
    ) -> Supplier:

        supplier = self.get_supplier(
            tenant_id,
            supplier_id,
        )

        update_data = data.model_dump(
            exclude_unset=True
        )

        for key, value in update_data.items():

            if key == "email" and value is not None:
                value = str(value)

            setattr(
                supplier,
                key,
                value
            )

        try:
            self.db.commit()
            self.db.refresh(supplier)

        except Exception:
            self.db.rollback()
            raise

        return supplier

    def update_supplier_status(
        self,
        tenant_id: int,
        supplier_id: int,
        is_active: bool,
    ) -> Supplier:

        supplier = self.get_supplier(
            tenant_id,
            supplier_id,
        )

        supplier.is_active = is_active

        try:
            self.db.commit()
            self.db.refresh(supplier)

        except Exception:
            self.db.rollback()
            raise

        return supplier

    def search_suppliers(
        self,
        tenant_id: int,
        search: str,
    ) -> Union[list[SupplierResponse], SupplierEmptyResponse]:

        search = search.strip()

        if not search:
            raise AppException(
                "Search term cannot be empty"
            )

        suppliers = (
            self.db.query(Supplier)
            .filter(
                Supplier.tenant_id == tenant_id,
                func.lower(Supplier.name) == search.lower(),
            )
            .order_by(Supplier.name.asc())
            .all()
        )

        if not suppliers:
            return SupplierEmptyResponse(
                success=True,
                message="No suppliers found matching the search",
                data=[],
            )

        return [SupplierResponse.model_validate(s) for s in suppliers]

    def supplier_stats(
        self,
        tenant_id: int,
    ) -> dict:

        total_suppliers = (
            self.db.query(Supplier)
            .filter(
                Supplier.tenant_id == tenant_id
            )
            .count()
        )

        active_suppliers = (
            self.db.query(Supplier)
            .filter(
                Supplier.tenant_id == tenant_id,
                Supplier.is_active.is_(True),
            )
            .count()
        )

        inactive_suppliers = (
            self.db.query(Supplier)
            .filter(
                Supplier.tenant_id == tenant_id,
                Supplier.is_active.is_(False),
            )
            .count()
        )

        return {
            "total_suppliers": total_suppliers,
            "active_suppliers": active_suppliers,
            "inactive_suppliers": inactive_suppliers,
        }
        
    def get_purchase_history(
        self,
        tenant_id: int,
        supplier_id: int,
    ) -> SupplierPurchaseHistoryResponse:

        supplier = self.get_supplier(
            tenant_id,
            supplier_id,
        )

        purchases = (
            self.db.query(PurchaseOrder)
            .options(selectinload(PurchaseOrder.items))
            .filter(
                PurchaseOrder.tenant_id == tenant_id,
                PurchaseOrder.supplier_id == supplier_id,
            )
            .order_by(
               PurchaseOrder.created_at.desc()
            )
            .all()
        )

        serialized_purchases = [
            PurchaseOrderResponse.model_validate(p)
            for p in purchases
        ]

        return SupplierPurchaseHistoryResponse(
            supplier_id=supplier.id,
            supplier_name=supplier.name,
            total_purchases=len(serialized_purchases),
            purchase_history=serialized_purchases,
            message=(
                "No purchase history found for this supplier"
                if not serialized_purchases
                else "Purchase history retrieved successfully"
            ),
        )