from datetime import datetime
from decimal import Decimal
import secrets
from typing import Optional

from sqlalchemy.orm import Session

from app.core.exceptions import AppException, ConflictException, NotFoundException
from app.models.grn import GRN, GRNItem
from app.models.product import Product
from app.models.purchase_order import PurchaseOrder
from app.models.store import Store
from app.models.warehouse import Warehouse
from app.repositories.grn_repo import GRNRepository
from app.schemas.grn import GRNCreate
from app.schemas.inventory import StockInRequest
from app.services.inventory_service import InventoryService
from app.utils.constants import StockMovementType


class GRNService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = GRNRepository(db)

    def _resolve_target_store_id(
        self,
        tenant_id: int,
        grn: GRN,
    ) -> int:
        """
        Determines the target store_id for stock-in.
        Priority:
        1. Warehouse's store_id (auto-provisions backing store if standalone warehouse).
        2. Purchase Order's store_id.
        3. Main active store of the tenant.
        """
        # 1. From warehouse
        if grn.warehouse_id:
            warehouse = (
                self.db.query(Warehouse)
                .filter(
                    Warehouse.id == grn.warehouse_id,
                    Warehouse.tenant_id == tenant_id,
                )
                .first()
            )
            if not warehouse:
                raise NotFoundException("Warehouse not found")

            if warehouse.store_id:
                return warehouse.store_id

            # Standalone warehouse without linked store: auto-provision a backing storage location
            suffix = secrets.token_hex(2).upper()
            store = Store(
                tenant_id=tenant_id,
                name=f"{warehouse.name} Storage",
                code=warehouse.code or f"WH-{warehouse.id}-{suffix}",
                address=warehouse.address,
                is_active=True,
                is_main=False,
            )
            self.db.add(store)
            self.db.flush()
            warehouse.store_id = store.id
            self.db.flush()
            return store.id

        # 2. From Purchase Order
        if grn.purchase_order_id:
            po = (
                self.db.query(PurchaseOrder)
                .filter(
                    PurchaseOrder.id == grn.purchase_order_id,
                    PurchaseOrder.tenant_id == tenant_id,
                )
                .first()
            )
            if po and po.store_id:
                return po.store_id

        # 3. From Tenant Main Store
        main_store = (
            self.db.query(Store)
            .filter(
                Store.tenant_id == tenant_id,
                Store.is_active == True,
            )
            .order_by(Store.is_main.desc(), Store.id.asc())
            .first()
        )
        if main_store:
            return main_store.id

        raise AppException("No active store or warehouse found for inventory receiving")

    def create(
        self,
        tenant_id: int,
        data: GRNCreate,
    ) -> GRN:
        # 1. Validate PO if specified
        po = None
        if data.purchase_order_id:
            po = (
                self.db.query(PurchaseOrder)
                .filter(
                    PurchaseOrder.id == data.purchase_order_id,
                    PurchaseOrder.tenant_id == tenant_id,
                )
                .first()
            )
            if not po:
                raise NotFoundException("Purchase Order not found")

        # 2. Validate Warehouse if specified
        if data.warehouse_id:
            warehouse = (
                self.db.query(Warehouse)
                .filter(
                    Warehouse.id == data.warehouse_id,
                    Warehouse.tenant_id == tenant_id,
                )
                .first()
            )
            if not warehouse:
                raise NotFoundException("Warehouse not found")

        # 3. Generate unique GRN number
        unique_suffix = secrets.token_hex(3).upper()
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        grn_number = f"GRN-{timestamp}-{unique_suffix}"

        grn = GRN(
            tenant_id=tenant_id,
            purchase_order_id=data.purchase_order_id,
            warehouse_id=data.warehouse_id,
            grn_number=grn_number,
            status="pending",
            remarks=data.remarks,
        )

        # 4. Handle items
        if data.items:
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
                    raise NotFoundException(f"Product #{item.product_id} not found")

                ordered_qty = item.ordered_quantity if item.ordered_quantity is not None else item.received_quantity
                grn_item = GRNItem(
                    product_id=item.product_id,
                    ordered_quantity=ordered_qty,
                    received_quantity=item.received_quantity,
                    remarks=item.remarks,
                )
                if item.unit_cost is not None:
                    grn_item.unit_cost = item.unit_cost
                grn.items.append(grn_item)

        elif po and po.items:
            # Auto-populate items from purchase order where unreceived balance remains
            for po_item in po.items:
                already_received = po_item.received_quantity or 0
                remaining = max(0, po_item.quantity - already_received)
                if remaining > 0 or not already_received:
                    grn_item = GRNItem(
                        product_id=po_item.product_id,
                        ordered_quantity=po_item.quantity,
                        received_quantity=remaining if remaining > 0 else po_item.quantity,
                        remarks=f"Auto-generated from PO #{po.order_number}",
                    )
                    grn_item.unit_cost = po_item.unit_cost
                    grn.items.append(grn_item)

        if not grn.items:
            raise AppException("GRN must contain at least one item")

        return self.repo.create(grn)

    def list(
        self,
        tenant_id: int,
        purchase_order_id: Optional[int] = None,
        warehouse_id: Optional[int] = None,
        status: Optional[str] = None,
    ) -> list[GRN]:
        return self.repo.list(
            tenant_id=tenant_id,
            purchase_order_id=purchase_order_id,
            warehouse_id=warehouse_id,
            status=status,
        )

    def get(
        self,
        tenant_id: int,
        grn_id: int,
    ) -> GRN:
        grn = self.repo.get_by_id(
            grn_id=grn_id,
            tenant_id=tenant_id,
        )
        if not grn:
            raise NotFoundException("GRN not found")
        return grn

    def receive(
        self,
        tenant_id: int,
        grn_id: int,
    ) -> GRN:
        grn = self.get(
            tenant_id=tenant_id,
            grn_id=grn_id,
        )

        if grn.status == "received":
            raise ConflictException("GRN has already been received and inventory updated")

        if grn.status == "rejected":
            raise ConflictException("Cannot receive a rejected GRN")

        # 1. Resolve destination store
        target_store_id = self._resolve_target_store_id(tenant_id, grn)

        # 2. Get linked PO if available
        po = None
        if grn.purchase_order_id:
            po = (
                self.db.query(PurchaseOrder)
                .filter(
                    PurchaseOrder.id == grn.purchase_order_id,
                    PurchaseOrder.tenant_id == tenant_id,
                )
                .first()
            )

        supplier_id = po.supplier_id if po else None
        inventory_service = InventoryService(self.db)

        # 3. Process stock-in for every received item
        for item in grn.items:
            if item.received_quantity <= 0:
                continue

            product = (
                self.db.query(Product)
                .filter(
                    Product.id == item.product_id,
                    Product.tenant_id == tenant_id,
                )
                .first()
            )
            if not product:
                continue

            # Determine unit cost
            po_item = None
            if po and po.items:
                po_item = next((pi for pi in po.items if pi.product_id == item.product_id), None)

            cost = None
            if getattr(item, "unit_cost", None) and item.unit_cost >= Decimal("1.00"):
                cost = item.unit_cost
            elif po_item and po_item.unit_cost and po_item.unit_cost >= Decimal("1.00"):
                cost = po_item.unit_cost
            elif product.cost_price and product.cost_price >= Decimal("1.00"):
                cost = product.cost_price
            else:
                cost = Decimal("10.00")

            batch_number = f"GRN-{grn.grn_number[-6:]}-{item.product_id}"

            stock_in_req = StockInRequest(
                store_id=target_store_id,
                product_id=item.product_id,
                quantity=item.received_quantity,
                supplier_id=supplier_id,
                unit_cost=cost,
                batch_number=batch_number,
                notes=f"GRN Inward: {grn.grn_number}" + (f" (PO: {po.order_number})" if po else ""),
            )

            # Atomically increment stock and record movement
            inventory_service.stock_in(
                tenant_id=tenant_id,
                data=stock_in_req,
                commit=False,
                movement_type=StockMovementType.STOCK_IN.value,
                reference_id=grn.id,
                reference_type=grn.grn_number,
            )

            # Update PO item received quantity
            if po_item:
                po_item.received_quantity = (po_item.received_quantity or 0) + item.received_quantity

        # 4. If linked to PO, sync PO status
        if po and po.items:
            total_ordered = sum(pi.quantity for pi in po.items)
            total_received = sum(pi.received_quantity or 0 for pi in po.items)
            if total_received >= total_ordered:
                po.status = "received"
            elif total_received > 0:
                po.status = "partially_received"
            self.db.add(po)

        # 5. Finalize GRN state
        grn.status = "received"
        grn.received_at = datetime.utcnow()

        self.db.commit()
        self.db.refresh(grn)
        return grn

    def reject(
        self,
        tenant_id: int,
        grn_id: int,
    ) -> GRN:
        grn = self.get(
            tenant_id=tenant_id,
            grn_id=grn_id,
        )

        if grn.status == "received":
            raise ConflictException("Cannot reject a GRN that has already been received into inventory")

        grn.status = "rejected"
        return self.repo.update(grn)

    def delete(
        self,
        tenant_id: int,
        grn_id: int,
    ) -> dict:
        grn = self.get(
            tenant_id=tenant_id,
            grn_id=grn_id,
        )

        if grn.status == "received":
            raise ConflictException("Cannot delete a GRN that has already been received into inventory")

        self.repo.delete(grn)
        return {
            "success": True,
            "message": "GRN deleted successfully",
            "id": grn_id,
        }

    def history(
        self,
        tenant_id: int,
        grn_id: int,
    ) -> dict:
        grn = self.get(
            tenant_id=tenant_id,
            grn_id=grn_id,
        )

        return {
            "grn_id": grn.id,
            "grn_number": grn.grn_number,
            "status": grn.status,
            "created_at": grn.created_at,
            "received_at": grn.received_at,
            "updated_at": grn.updated_at,
        }

    def print_grn(
        self,
        tenant_id: int,
        grn_id: int,
    ) -> GRN:
        return self.get(
            tenant_id=tenant_id,
            grn_id=grn_id,
        )
