from datetime import datetime
from decimal import Decimal
from typing import Optional, Union
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import AppException, ConflictException, NotFoundException
from app.models.product import Product
from app.models.purchase_order import PurchaseOrder, PurchaseOrderItem
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
        # Check duplicate supplier name within tenant
        existing_name = (
            self.db.query(Supplier)
            .filter(
                Supplier.tenant_id == tenant_id,
                func.lower(Supplier.name) == data.name.strip().lower(),
            )
            .first()
        )
        if existing_name:
            raise ConflictException(f"Supplier with name '{data.name.strip()}' already exists")

        # Check duplicate GSTIN within tenant if provided
        if data.gstin:
            existing_gstin = (
                self.db.query(Supplier)
                .filter(
                    Supplier.tenant_id == tenant_id,
                    func.upper(Supplier.gstin) == data.gstin.strip().upper(),
                )
                .first()
            )
            if existing_gstin:
                raise ConflictException(f"Supplier with GSTIN '{data.gstin.strip().upper()}' already exists")

        # Check duplicate phone within tenant if provided
        if data.phone and data.phone.strip():
            clean_phone = data.phone.strip()
            existing_phone = (
                self.db.query(Supplier)
                .filter(
                    Supplier.tenant_id == tenant_id,
                    Supplier.phone == clean_phone,
                )
                .first()
            )
            if existing_phone:
                raise ConflictException(f"Supplier with phone '{clean_phone}' already exists ({existing_phone.name})")

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
        search: Optional[str] = None,
        is_active: Optional[bool] = None,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
    ) -> Union[list[SupplierResponse], SupplierEmptyResponse]:

        query = self.db.query(Supplier).filter(
            Supplier.tenant_id == tenant_id
        )

        if is_active is not None:
            query = query.filter(Supplier.is_active == is_active)

        if search:
            clean_search = search.strip()
            if clean_search:
                term = f"%{clean_search}%"
                query = query.filter(
                    or_(
                        Supplier.name.ilike(term),
                        Supplier.phone.ilike(term),
                        Supplier.contact_person.ilike(term),
                        Supplier.gstin.ilike(term),
                    )
                )

        query = query.order_by(Supplier.created_at.desc())

        if page is not None and page_size is not None:
            offset = (page - 1) * page_size
            query = query.offset(offset).limit(page_size)

        suppliers = query.all()

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

        if "name" in update_data and update_data["name"] is not None:
            existing_name = (
                self.db.query(Supplier)
                .filter(
                    Supplier.tenant_id == tenant_id,
                    func.lower(Supplier.name) == update_data["name"].strip().lower(),
                    Supplier.id != supplier_id,
                )
                .first()
            )
            if existing_name:
                raise ConflictException(f"Supplier with name '{update_data['name'].strip()}' already exists")

        if "gstin" in update_data and update_data["gstin"] is not None:
            existing_gstin = (
                self.db.query(Supplier)
                .filter(
                    Supplier.tenant_id == tenant_id,
                    func.upper(Supplier.gstin) == update_data["gstin"].strip().upper(),
                    Supplier.id != supplier_id,
                )
                .first()
            )
            if existing_gstin:
                raise ConflictException(f"Supplier with GSTIN '{update_data['gstin'].strip().upper()}' already exists")

        if "phone" in update_data and update_data["phone"] is not None:
            clean_phone = str(update_data["phone"]).strip()
            if clean_phone:
                existing_phone = (
                    self.db.query(Supplier)
                    .filter(
                        Supplier.tenant_id == tenant_id,
                        Supplier.phone == clean_phone,
                        Supplier.id != supplier_id,
                    )
                    .first()
                )
                if existing_phone:
                    raise ConflictException(f"Supplier with phone '{clean_phone}' already exists ({existing_phone.name})")

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

    def delete_supplier(
        self,
        tenant_id: int,
        supplier_id: int,
    ) -> dict:
        supplier = self.get_supplier(tenant_id, supplier_id)

        # Check if supplier has associated Purchase Orders
        po_count = (
            self.db.query(PurchaseOrder)
            .filter(
                PurchaseOrder.tenant_id == tenant_id,
                PurchaseOrder.supplier_id == supplier_id,
            )
            .count()
        )
        if po_count > 0:
            raise ConflictException(
                f"Cannot delete supplier: {po_count} purchase order(s) are associated with this supplier. Consider deactivating the supplier instead."
            )

        try:
            self.db.delete(supplier)
            self.db.commit()
            return {
                "success": True,
                "message": "Supplier deleted successfully",
                "data": {"id": supplier_id},
            }
        except Exception:
            self.db.rollback()
            raise

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

        term = f"%{search}%"
        suppliers = (
            self.db.query(Supplier)
            .filter(
                Supplier.tenant_id == tenant_id,
                or_(
                    Supplier.name.ilike(term),
                    Supplier.phone.ilike(term),
                    Supplier.contact_person.ilike(term),
                    Supplier.gstin.ilike(term),
                ),
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

    def get_suppliers_summary(
        self,
        tenant_id: int,
    ) -> dict:
        total_suppliers = (
            self.db.query(Supplier)
            .filter(Supplier.tenant_id == tenant_id)
            .count()
        )
        active_suppliers = (
            self.db.query(Supplier)
            .filter(Supplier.tenant_id == tenant_id, Supplier.is_active.is_(True))
            .count()
        )
        inactive_suppliers = (
            self.db.query(Supplier)
            .filter(Supplier.tenant_id == tenant_id, Supplier.is_active.is_(False))
            .count()
        )

        total_spend = (
            self.db.query(func.coalesce(func.sum(PurchaseOrder.total_amount), 0))
            .filter(
                PurchaseOrder.tenant_id == tenant_id,
                PurchaseOrder.status.in_(["received", "completed"]),
            )
            .scalar()
            or Decimal("0.00")
        )

        pending_orders = (
            self.db.query(PurchaseOrder)
            .filter(
                PurchaseOrder.tenant_id == tenant_id,
                PurchaseOrder.status.in_(["draft", "pending", "ordered"]),
            )
            .count()
        )

        top_rows = (
            self.db.query(
                Supplier.id.label("supplier_id"),
                Supplier.name.label("supplier_name"),
                func.count(PurchaseOrder.id).label("total_orders"),
                func.coalesce(func.sum(PurchaseOrder.total_amount), 0).label("total_spend"),
            )
            .join(PurchaseOrder, PurchaseOrder.supplier_id == Supplier.id)
            .filter(
                Supplier.tenant_id == tenant_id,
                PurchaseOrder.status.in_(["received", "completed"]),
            )
            .group_by(Supplier.id, Supplier.name)
            .order_by(func.sum(PurchaseOrder.total_amount).desc())
            .limit(5)
            .all()
        )

        top_suppliers = [
            {
                "supplier_id": r.supplier_id,
                "supplier_name": r.supplier_name,
                "total_orders": r.total_orders,
                "total_spend": Decimal(str(r.total_spend)),
            }
            for r in top_rows
        ]

        return {
            "success": True,
            "total_suppliers": total_suppliers,
            "active_suppliers": active_suppliers,
            "inactive_suppliers": inactive_suppliers,
            "total_spend": Decimal(str(total_spend)),
            "pending_orders_count": pending_orders,
            "top_suppliers": top_suppliers,
        }

    def get_supplier_products(
        self,
        tenant_id: int,
        supplier_id: int,
    ) -> dict:
        supplier = self.get_supplier(tenant_id, supplier_id)

        rows = (
            self.db.query(
                Product.id.label("product_id"),
                Product.name.label("product_name"),
                Product.sku.label("sku"),
                func.sum(PurchaseOrderItem.quantity).label("total_quantity_purchased"),
                func.max(PurchaseOrderItem.unit_cost).label("last_purchase_price"),
                func.max(PurchaseOrder.created_at).label("last_purchased_at"),
            )
            .join(PurchaseOrderItem, PurchaseOrderItem.product_id == Product.id)
            .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderItem.po_id)
            .filter(
                PurchaseOrder.tenant_id == tenant_id,
                PurchaseOrder.supplier_id == supplier_id,
            )
            .group_by(Product.id, Product.name, Product.sku)
            .order_by(Product.name.asc())
            .all()
        )

        products_data = [
            {
                "product_id": r.product_id,
                "product_name": r.product_name,
                "sku": r.sku,
                "total_quantity_purchased": int(r.total_quantity_purchased or 0),
                "last_purchase_price": Decimal(str(r.last_purchase_price or 0)),
                "last_purchased_at": r.last_purchased_at,
            }
            for r in rows
        ]

        return {
            "success": True,
            "supplier_id": supplier.id,
            "supplier_name": supplier.name,
            "total_products": len(products_data),
            "data": products_data,
        }

    def get_purchase_history(
        self,
        tenant_id: int,
        supplier_id: int,
        status: Optional[str] = None,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
    ) -> SupplierPurchaseHistoryResponse:

        supplier = self.get_supplier(
            tenant_id,
            supplier_id,
        )

        query = (
            self.db.query(PurchaseOrder)
            .options(selectinload(PurchaseOrder.items))
            .filter(
                PurchaseOrder.tenant_id == tenant_id,
                PurchaseOrder.supplier_id == supplier_id,
            )
        )

        if status:
            query = query.filter(PurchaseOrder.status == status)

        query = query.order_by(
            PurchaseOrder.created_at.desc()
        )

        total_purchases_all = query.count()

        if page is not None and page_size is not None:
            offset = (page - 1) * page_size
            query = query.offset(offset).limit(page_size)

        purchases = query.all()

        serialized_purchases = [
            PurchaseOrderResponse.model_validate(p)
            for p in purchases
        ]

        total_amount_spent = sum(
            (Decimal(str(p.total_amount or 0)) for p in purchases),
            Decimal("0.00"),
        )

        return SupplierPurchaseHistoryResponse(
            supplier_id=supplier.id,
            supplier_name=supplier.name,
            total_purchases=total_purchases_all,
            total_amount_spent=total_amount_spent,
            purchase_history=serialized_purchases,
            message=(
                "No purchase history found for this supplier"
                if not serialized_purchases
                else "Purchase history retrieved successfully"
            ),
        )