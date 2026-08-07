from decimal import Decimal
import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundException
from app.models.purchase_order import (
    PurchaseOrder,
    PurchaseOrderItem,
)
from app.models.product import Product
from app.models.store import Store
from app.models.inventory import Supplier

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

        po = PurchaseOrder(
            tenant_id=tenant_id,
            supplier_id=data.supplier_id,
            store_id=data.store_id,
            po_number=f"PO-{uuid.uuid4().hex[:8].upper()}",
            status="draft",
            remarks=data.remarks,
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

            total = item.quantity * item.unit_price

            po.items.append(
                PurchaseOrderItem(
                    product_id=item.product_id,
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                    total=total,
                )
            )

            total_amount += total

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
               "Only draft purchase orders can be updated"
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