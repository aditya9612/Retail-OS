from decimal import Decimal
import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictException, NotFoundException
from app.models.purchase_order import (
    PurchaseOrder,
    PurchaseOrderItem,
)
from app.models.product import Product
from app.models.store import Store
from app.models.supplier import Supplier

from app.repositories.purchase_order_repo import (
    PurchaseOrderRepository,
)

from app.schemas.purchase_order import (
    PurchaseOrderCreate,
    PurchaseOrderUpdate,
    PurchaseOrderReceive,
    PurchaseOrderStatusUpdate,
)

from app.services.inventory_service import InventoryService
from app.schemas.inventory import StockInRequest


class PurchaseOrderService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = PurchaseOrderRepository(db)
        
    def create_purchase_order(
        self,
        tenant_id: int,
        data: PurchaseOrderCreate,
    ) -> PurchaseOrder:

        supplier = (
            self.db.query(Supplier)
            .filter(
                Supplier.id == data.supplier_id,
                Supplier.tenant_id == tenant_id,
            )
            .first()
        )

        if not supplier:
            raise NotFoundException("Supplier not found")

        if data.store_id is not None:
            store = (
                self.db.query(Store)
                .filter(
                    Store.id == data.store_id,
                    Store.tenant_id == tenant_id,
                )
                .first()
            )
            if not store:
                raise NotFoundException("Store not found")

        invoice_val = getattr(data, "invoice_number", None) or getattr(data, "invoice_id", None)
        po = PurchaseOrder(
            tenant_id=tenant_id,
            supplier_id=data.supplier_id,
            store_id=data.store_id,
            invoice_number=invoice_val,
            order_number=f"PO-{uuid.uuid4().hex[:8].upper()}",
            status="draft",
            notes=data.notes or data.remarks,
            expected_delivery_date=data.expected_delivery_date,
        )

        total_amount = Decimal("0.00")

        for item in data.items:

            product = (
                self.db.query(Product)
                .filter(
                    Product.id == item.product_id,
                    Product.tenant_id == tenant_id,
                )
                .first()
            )

            if not product:
                raise NotFoundException(
                    f"Product {item.product_id} not found"
                )

            unit_cost = item.unit_cost if item.unit_cost is not None else item.unit_price
            total_cost = item.quantity * unit_cost

            po.items.append(
                PurchaseOrderItem(
                    product_id=item.product_id,
                    quantity=item.quantity,
                    unit_cost=unit_cost,
                    total_cost=total_cost,
                )
            )

            total_amount += total_cost

        po.total_amount = total_amount

        return self.repo.create(po)
    
    def list_purchase_orders(
        self,
        tenant_id: int,
        page: int = 1,
        page_size: int = 20,
    ):
        skip = (page - 1) * page_size

        return self.repo.list_purchase_orders(
            tenant_id=tenant_id,
            skip=skip,
            limit=page_size,
        )
        
    def get_purchase_order(
        self,
        tenant_id: int,
        purchase_order_id: int,
    ) -> PurchaseOrder:

        purchase_order = self.repo.get_by_id(
            purchase_order_id,
            tenant_id,
        )

        if not purchase_order:
            raise NotFoundException(
                "Purchase Order not found"
            )

        return purchase_order
    
    def update_purchase_order(
        self,
        tenant_id: int,
        purchase_order_id: int,
        data: PurchaseOrderUpdate,
    ) -> PurchaseOrder:

        purchase_order = self.get_purchase_order(
            tenant_id,
            purchase_order_id,
        )

        if purchase_order.status != "draft":
            raise NotFoundException(
                "This purchase order is already received and can't be updated"
            )

        if data.supplier_id is not None:
            supplier = (
                self.db.query(Supplier)
                .filter(
                    Supplier.id == data.supplier_id,
                    Supplier.tenant_id == tenant_id,
                )
                .first()
            )
            if not supplier:
                raise NotFoundException("Supplier not found")
            purchase_order.supplier_id = data.supplier_id

        if data.store_id is not None:
            store = (
                self.db.query(Store)
                .filter(
                    Store.id == data.store_id,
                    Store.tenant_id == tenant_id,
                )
                .first()
            )
            if not store:
                raise NotFoundException("Store not found")
            purchase_order.store_id = data.store_id

        if data.remarks is not None:
            purchase_order.remarks = data.remarks
        if data.notes is not None:
            purchase_order.notes = data.notes

        if getattr(data, "invoice_number", None) is not None:
            purchase_order.invoice_number = data.invoice_number
        elif getattr(data, "invoice_id", None) is not None:
            purchase_order.invoice_number = data.invoice_id

        if data.expected_delivery_date is not None:
            purchase_order.expected_delivery_date = data.expected_delivery_date

        return self.repo.update(purchase_order)
    
    def receive_purchase_order(
        self,
        tenant_id: int,
        purchase_order_id: int,
        data: PurchaseOrderReceive,
    ) -> PurchaseOrder:

        purchase_order = self.get_purchase_order(
            tenant_id,
            purchase_order_id,
        )

        if purchase_order.status == "received":
            raise NotFoundException(
                "Purchase Order already received"
            )

        if getattr(data, "invoice_number", None) is not None:
            purchase_order.invoice_number = data.invoice_number
        elif getattr(data, "invoice_id", None) is not None:
            purchase_order.invoice_number = data.invoice_id

        inventory_service = InventoryService(self.db)

        for item in purchase_order.items:
            inventory_service.stock_in(
                tenant_id,
                StockInRequest(
                    store_id=purchase_order.store_id,
                    product_id=item.product_id,
                    quantity=item.quantity,
                    supplier_id=purchase_order.supplier_id,
                    unit_cost=item.unit_price,
                    reference=purchase_order.po_number,
                    notes=data.remarks,
                ),
            )

        purchase_order.status = "received"

        if data.remarks:
            purchase_order.remarks = data.remarks

        return self.repo.update(purchase_order)
    
    def update_purchase_order_status(
        self,
        tenant_id: int,
        purchase_order_id: int,
        data: PurchaseOrderStatusUpdate,
    ) -> PurchaseOrder:

        purchase_order = self.get_purchase_order(
            tenant_id,
            purchase_order_id,
        )

        purchase_order.status = data.status

        return self.repo.update(purchase_order)

    def delete_purchase_order(
        self,
        tenant_id: int,
        purchase_order_id: int,
    ) -> dict:
        purchase_order = self.get_purchase_order(
            tenant_id,
            purchase_order_id,
        )

        if purchase_order.status == "received":
            raise ConflictException(
                "Cannot delete purchase order: order has already been received and inventory updated"
            )

        from app.models.grn import GRN
        grn_count = (
            self.db.query(GRN)
            .filter(
                GRN.tenant_id == tenant_id,
                GRN.purchase_order_id == purchase_order_id,
            )
            .count()
        )
        if grn_count > 0:
            raise ConflictException(
                f"Cannot delete purchase order: {grn_count} Goods Receipt Note(s) are linked to it"
            )

        order_number = purchase_order.order_number
        try:
            self.repo.delete(purchase_order)
            return {
                "id": purchase_order_id,
                "order_number": order_number,
            }
        except IntegrityError:
            self.db.rollback()
            raise ConflictException(
                "Cannot delete purchase order due to database constraints"
            )
        except Exception as exc:
            self.db.rollback()
            raise ConflictException(
                f"Cannot delete purchase order: {str(exc)}"
            )
