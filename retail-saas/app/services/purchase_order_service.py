import csv
from datetime import date, datetime, timedelta
from decimal import Decimal
import io
import secrets
from typing import Optional

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AppException, ConflictException, NotFoundException
from app.models.purchase_order import (
    PurchaseOrder,
    PurchaseOrderItem,
)
from app.models.product import Product
from app.models.store import Store
from app.models.supplier import Supplier
from app.models.warehouse import Warehouse
from app.models.grn import GRN

from app.repositories.purchase_order_repo import (
    PurchaseOrderRepository,
)
from app.services.document_number_service import DocumentNumberService
from app.services.inventory_service import InventoryService
from app.schemas.inventory import StockInRequest

from app.schemas.purchase_order import (
    PurchaseOrderApproveRequest,
    PurchaseOrderCancelRequest,
    PurchaseOrderCreate,
    PurchaseOrderReceive,
    PurchaseOrderStatusUpdate,
    PurchaseOrderStatsResponse,
    PurchaseOrderUpdate,
)


class PurchaseOrderService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = PurchaseOrderRepository(db)

    def _resolve_receiving_store_id(
        self,
        tenant_id: int,
        po: PurchaseOrder,
    ) -> int:
        """Resolves target store_id for stock-in from PO's store or warehouse."""
        if po.store_id:
            store = (
                self.db.query(Store)
                .filter(Store.id == po.store_id, Store.tenant_id == tenant_id, Store.is_active == True)
                .first()
            )
            if store:
                return store.id

        if po.warehouse_id:
            warehouse = (
                self.db.query(Warehouse)
                .filter(Warehouse.id == po.warehouse_id, Warehouse.tenant_id == tenant_id)
                .first()
            )
            if warehouse:
                if warehouse.store_id:
                    return warehouse.store_id

                # Standalone warehouse without linked store: auto-provision backing store
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

        main_store = (
            self.db.query(Store)
            .filter(Store.tenant_id == tenant_id, Store.is_active == True)
            .order_by(Store.is_main.desc(), Store.id.asc())
            .first()
        )
        if main_store:
            return main_store.id

        raise AppException("No active store or warehouse found for inventory receiving")

    def create_purchase_order(
        self,
        tenant_id: int,
        data: PurchaseOrderCreate,
        user_id: Optional[int] = None,
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

        if not supplier.is_active:
            raise ConflictException(f"Supplier '{supplier.name}' is inactive or disabled")

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
            if not store.is_active:
                raise ConflictException(f"Store '{store.name}' is inactive or deleted")

        if data.warehouse_id is not None:
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
            if not warehouse.is_active:
                raise ConflictException(f"Warehouse '{warehouse.name}' is inactive or disabled")

        # 1. Enforce at least 1 item and duplicate line item check
        if not data.items or len(data.items) == 0:
            raise ConflictException("Purchase order must contain at least one line item")

        seen_product_ids = set()
        for it in data.items:
            if it.product_id in seen_product_ids:
                raise ConflictException(
                    f"Duplicate product ID {it.product_id} in purchase order items. Combine quantities into a single item line."
                )
            seen_product_ids.add(it.product_id)

            if it.quantity is None or it.quantity <= 0:
                raise ConflictException(f"Item quantity must be greater than 0 for product {it.product_id}")

            unit_cost = it.unit_cost if it.unit_cost is not None else it.unit_price
            if unit_cost is not None and unit_cost < Decimal("0.00"):
                raise ConflictException(f"Unit cost cannot be negative for product {it.product_id}")

        # 2. Duplicate invoice number check per supplier and tenant
        invoice_val = getattr(data, "invoice_number", None)
        if invoice_val and str(invoice_val).strip():
            clean_inv = str(invoice_val).strip()
            existing_po_inv = (
                self.db.query(PurchaseOrder)
                .filter(
                    PurchaseOrder.tenant_id == tenant_id,
                    PurchaseOrder.supplier_id == data.supplier_id,
                    PurchaseOrder.is_deleted == False,
                    func.lower(PurchaseOrder.invoice_number) == clean_inv.lower(),
                )
                .first()
            )
            if existing_po_inv:
                raise ConflictException(
                    f"Purchase order with invoice number '{clean_inv}' already exists for this supplier (Order: {existing_po_inv.order_number})"
                )
            invoice_val = clean_inv
        else:
            invoice_val = None

        # 3. Anti-double-click / duplicate PO submission protection (15 seconds window)
        recent_cutoff = datetime.utcnow() - timedelta(seconds=15)
        recent_po = (
            self.db.query(PurchaseOrder)
            .filter(
                PurchaseOrder.tenant_id == tenant_id,
                PurchaseOrder.supplier_id == data.supplier_id,
                PurchaseOrder.store_id == data.store_id,
                PurchaseOrder.warehouse_id == data.warehouse_id,
                PurchaseOrder.created_at >= recent_cutoff,
                PurchaseOrder.is_deleted == False,
            )
            .first()
        )
        if recent_po and len(recent_po.items) == len(data.items):
            recent_ids = {item.product_id for item in recent_po.items}
            if recent_ids == seen_product_ids:
                raise ConflictException(
                    f"Duplicate purchase order submission detected. Identical purchase order '{recent_po.order_number}' was just created."
                )

        po = PurchaseOrder(
            tenant_id=tenant_id,
            supplier_id=data.supplier_id,
            store_id=data.store_id,
            warehouse_id=data.warehouse_id,
            invoice_number=invoice_val,
            order_number=DocumentNumberService(self.db).generate_purchase_order_number(
                tenant_id=tenant_id, store_id=data.store_id
            ),
            status="draft",
            notes=data.notes,
            expected_delivery_date=data.expected_delivery_date,
            created_by_id=user_id,
        )

        subtotal = Decimal("0.00")
        total_tax = Decimal("0.00")

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
                    f"Product #{item.product_id} not found"
                )

            unit_cost = item.unit_cost if item.unit_cost is not None else item.unit_price
            if unit_cost is None:
                unit_cost = product.cost_price or Decimal("0.00")

            line_cost = Decimal(str(item.quantity)) * unit_cost
            tax_rate = item.tax_rate if item.tax_rate is not None else Decimal("0.00")
            line_tax = (line_cost * tax_rate / Decimal("100.00")).quantize(Decimal("0.01"))
            line_total = line_cost + line_tax

            po.items.append(
                PurchaseOrderItem(
                    product_id=item.product_id,
                    quantity=item.quantity,
                    unit_cost=unit_cost,
                    total_cost=line_total,
                    tax_rate=tax_rate,
                    tax_amount=line_tax,
                    hsn_code=item.hsn_code,
                    unit_of_measure=item.unit_of_measure or "pcs",
                )
            )

            subtotal += line_cost
            total_tax += line_tax

        discount = data.discount_amount or Decimal("0.00")
        shipping = data.shipping_charges or Decimal("0.00")
        total_amount = max(Decimal("0.00"), subtotal + total_tax + shipping - discount)

        po.subtotal = subtotal
        po.tax_amount = total_tax
        po.discount_amount = discount
        po.shipping_charges = shipping
        po.total_amount = total_amount

        return self.repo.create(po)

    def list_purchase_orders(
        self,
        tenant_id: int,
        page: int = 1,
        page_size: int = 20,
        status: Optional[str] = None,
        supplier_id: Optional[int] = None,
        store_id: Optional[int] = None,
        warehouse_id: Optional[int] = None,
        search: Optional[str] = None,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        delivery_from_date: Optional[date] = None,
        delivery_to_date: Optional[date] = None,
    ) -> list[PurchaseOrder]:
        skip = (page - 1) * page_size

        return self.repo.list_purchase_orders(
            tenant_id=tenant_id,
            skip=skip,
            limit=page_size,
            status=status,
            supplier_id=supplier_id,
            store_id=store_id,
            warehouse_id=warehouse_id,
            search=search,
            from_date=from_date,
            to_date=to_date,
            delivery_from_date=delivery_from_date,
            delivery_to_date=delivery_to_date,
        )

    def count_purchase_orders(
        self,
        tenant_id: int,
        status: Optional[str] = None,
        supplier_id: Optional[int] = None,
        store_id: Optional[int] = None,
        warehouse_id: Optional[int] = None,
        search: Optional[str] = None,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        delivery_from_date: Optional[date] = None,
        delivery_to_date: Optional[date] = None,
    ) -> int:
        return self.repo.count_purchase_orders(
            tenant_id=tenant_id,
            status=status,
            supplier_id=supplier_id,
            store_id=store_id,
            warehouse_id=warehouse_id,
            search=search,
            from_date=from_date,
            to_date=to_date,
            delivery_from_date=delivery_from_date,
            delivery_to_date=delivery_to_date,
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
            raise ConflictException(
                f"Purchase order '{purchase_order.order_number}' is in '{purchase_order.status}' status and cannot be modified. Only draft orders can be updated."
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
            if not supplier.is_active:
                raise ConflictException(f"Supplier '{supplier.name}' is inactive or disabled")
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
            if not store.is_active:
                raise ConflictException(f"Store '{store.name}' is inactive or deleted")
            purchase_order.store_id = data.store_id

        if data.warehouse_id is not None:
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
            if not warehouse.is_active:
                raise ConflictException(f"Warehouse '{warehouse.name}' is inactive or disabled")
            purchase_order.warehouse_id = data.warehouse_id

        if data.notes is not None:
            purchase_order.notes = data.notes

        inv_update = getattr(data, "invoice_number", None)
        if inv_update is not None:
            clean_inv = str(inv_update).strip() if inv_update else ""
            if clean_inv:
                existing_po_inv = (
                    self.db.query(PurchaseOrder)
                    .filter(
                        PurchaseOrder.tenant_id == tenant_id,
                        PurchaseOrder.supplier_id == purchase_order.supplier_id,
                        PurchaseOrder.is_deleted == False,
                        func.lower(PurchaseOrder.invoice_number) == clean_inv.lower(),
                        PurchaseOrder.id != purchase_order_id,
                    )
                    .first()
                )
                if existing_po_inv:
                    raise ConflictException(
                        f"Purchase order with invoice number '{clean_inv}' already exists for this supplier (Order: {existing_po_inv.order_number})"
                    )
                purchase_order.invoice_number = clean_inv
            else:
                purchase_order.invoice_number = None

        if data.expected_delivery_date is not None:
            purchase_order.expected_delivery_date = data.expected_delivery_date

        if data.discount_amount is not None:
            purchase_order.discount_amount = data.discount_amount

        if data.shipping_charges is not None:
            purchase_order.shipping_charges = data.shipping_charges

        # Update items if provided in draft state
        if data.items is not None:
            if len(data.items) == 0:
                raise ConflictException("Purchase order must contain at least one line item")

            seen_ids = set()
            for it in data.items:
                if it.product_id in seen_ids:
                    raise ConflictException(f"Duplicate product ID {it.product_id} in purchase order items")
                seen_ids.add(it.product_id)

            purchase_order.items.clear()
            self.db.flush()

            subtotal = Decimal("0.00")
            total_tax = Decimal("0.00")

            for item in data.items:
                prod = (
                    self.db.query(Product)
                    .filter(Product.id == item.product_id, Product.tenant_id == tenant_id)
                    .first()
                )
                if not prod:
                    raise NotFoundException(f"Product #{item.product_id} not found")

                cost = item.unit_cost if item.unit_cost is not None else item.unit_price
                if cost is None:
                    cost = prod.cost_price or Decimal("0.00")

                line_cost = Decimal(str(item.quantity)) * cost
                rate = item.tax_rate if item.tax_rate is not None else Decimal("0.00")
                line_tax = (line_cost * rate / Decimal("100.00")).quantize(Decimal("0.01"))
                line_tot = line_cost + line_tax

                purchase_order.items.append(
                    PurchaseOrderItem(
                        product_id=item.product_id,
                        quantity=item.quantity,
                        unit_cost=cost,
                        total_cost=line_tot,
                        tax_rate=rate,
                        tax_amount=line_tax,
                        hsn_code=item.hsn_code,
                        unit_of_measure=item.unit_of_measure or "pcs",
                    )
                )

                subtotal += line_cost
                total_tax += line_tax

            purchase_order.subtotal = subtotal
            purchase_order.tax_amount = total_tax
            discount = purchase_order.discount_amount or Decimal("0.00")
            shipping = purchase_order.shipping_charges or Decimal("0.00")
            purchase_order.total_amount = max(Decimal("0.00"), subtotal + total_tax + shipping - discount)

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
            raise ConflictException(
                f"Purchase order '{purchase_order.order_number}' has already been received in full"
            )

        if purchase_order.status == "cancelled":
            raise ConflictException(
                f"Cannot receive cancelled purchase order '{purchase_order.order_number}'"
            )

        if getattr(data, "invoice_number", None) is not None:
            purchase_order.invoice_number = data.invoice_number

        target_store_id = self._resolve_receiving_store_id(tenant_id, purchase_order)
        inventory_service = InventoryService(self.db)

        resolved_notes = getattr(data, "notes", None)

        # Partial receiving by specific item list vs receiving remaining balance
        if data.items:
            # Explicit item list provided
            item_map = {it.product_id: it for it in data.items}
            for po_item in purchase_order.items:
                if po_item.product_id not in item_map:
                    continue

                rec_item = item_map[po_item.product_id]
                already_received = po_item.received_quantity or 0
                remaining = max(0, po_item.quantity - already_received)

                if rec_item.quantity <= 0:
                    continue

                if rec_item.quantity > remaining:
                    raise ConflictException(
                        f"Receive quantity {rec_item.quantity} exceeds unreceived balance {remaining} for product #{po_item.product_id}"
                    )

                qty_to_receive = rec_item.quantity
                po_item.received_quantity = already_received + qty_to_receive

                batch_no = rec_item.batch_number or data.batch_number or f"PO-{purchase_order.order_number[-6:]}-{po_item.product_id}"
                cost = po_item.unit_price if po_item.unit_price and po_item.unit_price >= Decimal("1.00") else Decimal("10.00")

                stock_req_data = {
                    "store_id": target_store_id,
                    "product_id": po_item.product_id,
                    "quantity": qty_to_receive,
                    "supplier_id": purchase_order.supplier_id,
                    "unit_cost": cost,
                    "batch_number": batch_no,
                    "notes": resolved_notes or f"PO Received: {purchase_order.order_number}",
                }
                exp_date = rec_item.expiry_date or data.expiry_date
                if exp_date is not None:
                    stock_req_data["expiry_date"] = exp_date

                inventory_service.stock_in(
                    tenant_id,
                    StockInRequest(**stock_req_data),
                    commit=False,
                    movement_type="PO_RECEIVED",
                    reference_id=purchase_order.id,
                    reference_type=purchase_order.order_number,
                )
        else:
            # Receive all remaining unreceived quantities (fixes over-crediting bug!)
            for item in purchase_order.items:
                already_received = item.received_quantity or 0
                remaining = max(0, item.quantity - already_received)
                if remaining <= 0:
                    continue

                batch_no = data.batch_number or f"PO-{purchase_order.order_number[-6:]}-{item.product_id}"
                cost = item.unit_price if item.unit_price and item.unit_price >= Decimal("1.00") else Decimal("10.00")

                stock_req_data = {
                    "store_id": target_store_id,
                    "product_id": item.product_id,
                    "quantity": remaining,
                    "supplier_id": purchase_order.supplier_id,
                    "unit_cost": cost,
                    "batch_number": batch_no,
                    "notes": resolved_notes or f"PO Received: {purchase_order.order_number}",
                }
                if data.expiry_date is not None:
                    stock_req_data["expiry_date"] = data.expiry_date

                inventory_service.stock_in(
                    tenant_id,
                    StockInRequest(**stock_req_data),
                    commit=False,
                    movement_type="PO_RECEIVED",
                    reference_id=purchase_order.id,
                    reference_type=purchase_order.order_number,
                )
                item.received_quantity = item.quantity

        # Synchronize status based on actual receipts
        total_ordered = sum(it.quantity for it in purchase_order.items)
        total_received = sum(it.received_quantity or 0 for it in purchase_order.items)

        if total_received >= total_ordered:
            purchase_order.status = "received"
        elif total_received > 0:
            purchase_order.status = "partially_received"

        if resolved_notes:
            purchase_order.notes = resolved_notes

        self.db.commit()
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

        current_status = purchase_order.status
        new_status = data.status

        if current_status == "received" and new_status != "received":
            raise ConflictException(
                f"Cannot change status of purchase order '{purchase_order.order_number}' from 'received' to '{new_status}'. Inwarded inventory cannot be reverted via status update."
            )

        if current_status == "cancelled" and new_status != "cancelled":
            raise ConflictException(
                f"Cannot change status of cancelled purchase order '{purchase_order.order_number}'"
            )

        if current_status == "partially_received" and new_status in ("draft", "cancelled"):
            raise ConflictException(
                f"Cannot revert purchase order in '{current_status}' status back to '{new_status}' as partial stock has already been inwarded"
            )

        purchase_order.status = new_status
        return self.repo.update(purchase_order)

    def approve_purchase_order(
        self,
        tenant_id: int,
        purchase_order_id: int,
        data: PurchaseOrderApproveRequest,
        user_id: Optional[int] = None,
    ) -> PurchaseOrder:
        purchase_order = self.get_purchase_order(
            tenant_id,
            purchase_order_id,
        )

        if purchase_order.status != "draft":
            raise ConflictException(
                f"Cannot approve purchase order '{purchase_order.order_number}': current status is '{purchase_order.status}' (must be 'draft')"
            )

        purchase_order.status = "approved"
        purchase_order.approved_by_id = user_id
        purchase_order.approved_at = datetime.utcnow()

        if data.notes:
            existing_notes = purchase_order.notes or ""
            purchase_order.notes = f"{existing_notes}\n[Approved]: {data.notes}".strip()

        return self.repo.update(purchase_order)

    def cancel_purchase_order(
        self,
        tenant_id: int,
        purchase_order_id: int,
        data: PurchaseOrderCancelRequest,
    ) -> PurchaseOrder:
        purchase_order = self.get_purchase_order(
            tenant_id,
            purchase_order_id,
        )

        if purchase_order.status in ("received", "partially_received"):
            raise ConflictException(
                f"Cannot cancel purchase order in '{purchase_order.status}' status because stock has already been inwarded"
            )

        if purchase_order.status == "cancelled":
            raise ConflictException(
                f"Purchase order '{purchase_order.order_number}' is already cancelled"
            )

        # Check linked GRNs
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
                f"Cannot cancel purchase order: {grn_count} Goods Receipt Note(s) are linked to it"
            )

        purchase_order.status = "cancelled"
        purchase_order.cancelled_at = datetime.utcnow()
        purchase_order.cancellation_reason = data.reason

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

        if purchase_order.status in ("received", "partially_received"):
            raise ConflictException(
                "Cannot delete purchase order: order has already been received and inventory updated"
            )

        if purchase_order.status == "approved":
            raise ConflictException(
                "Cannot delete an approved purchase order. Please cancel the purchase order instead to preserve audit logs."
            )

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

    def get_stats(
        self,
        tenant_id: int,
        store_id: Optional[int] = None,
    ) -> PurchaseOrderStatsResponse:
        q = (
            self.db.query(PurchaseOrder)
            .filter(
                PurchaseOrder.tenant_id == tenant_id,
                PurchaseOrder.is_deleted == False,
            )
        )
        if store_id is not None:
            q = q.filter(PurchaseOrder.store_id == store_id)
        orders = q.all()

        total_orders = len(orders)
        draft_orders = sum(1 for o in orders if o.status == "draft")
        approved_orders = sum(1 for o in orders if o.status == "approved")
        partially_received_orders = sum(1 for o in orders if o.status == "partially_received")
        received_orders = sum(1 for o in orders if o.status == "received")
        cancelled_orders = sum(1 for o in orders if o.status == "cancelled")

        total_order_value = sum((o.total_amount for o in orders if o.status != "cancelled"), Decimal("0.00"))

        # Total value of received merchandise
        total_received_value = Decimal("0.00")
        for o in orders:
            for item in o.items:
                if item.received_quantity and item.received_quantity > 0:
                    total_received_value += Decimal(str(item.received_quantity)) * item.unit_cost

        # Expected deliveries this week
        now = datetime.utcnow().date()
        week_end = now + timedelta(days=7)
        expected_deliveries = sum(
            1 for o in orders
            if o.expected_delivery_date and now <= o.expected_delivery_date <= week_end and o.status in ("approved", "partially_received")
        )

        return PurchaseOrderStatsResponse(
            total_orders=total_orders,
            draft_orders=draft_orders,
            approved_orders=approved_orders,
            partially_received_orders=partially_received_orders,
            received_orders=received_orders,
            cancelled_orders=cancelled_orders,
            total_order_value=total_order_value,
            total_received_value=total_received_value,
            expected_deliveries_this_week=expected_deliveries,
        )

    def get_linked_grns(
        self,
        tenant_id: int,
        purchase_order_id: int,
    ) -> list:
        # Verify PO exists
        self.get_purchase_order(tenant_id, purchase_order_id)

        grns = (
            self.db.query(GRN)
            .filter(
                GRN.tenant_id == tenant_id,
                GRN.purchase_order_id == purchase_order_id,
            )
            .order_by(GRN.created_at.desc())
            .all()
        )
        return grns

    def export_csv(
        self,
        tenant_id: int,
        status: Optional[str] = None,
        supplier_id: Optional[int] = None,
        store_id: Optional[int] = None,
        warehouse_id: Optional[int] = None,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> str:
        orders = self.repo.list_purchase_orders(
            tenant_id=tenant_id,
            skip=0,
            limit=5000,
            status=status,
            supplier_id=supplier_id,
            store_id=store_id,
            warehouse_id=warehouse_id,
            from_date=from_date,
            to_date=to_date,
        )

        output = io.StringIO()
        writer = csv.writer(output)

        headers = [
            "PO Number",
            "Order Date",
            "Status",
            "Supplier",
            "Destination",
            "Invoice / DC Number",
            "Expected Delivery Date",
            "Total Quantity",
            "Received Quantity",
            "Subtotal (INR)",
            "Tax (INR)",
            "Discount (INR)",
            "Shipping (INR)",
            "Total Amount (INR)",
        ]
        writer.writerow(headers)

        for po in orders:
            destination = po.store.name if po.store else (po.warehouse.name if po.warehouse else "N/A")
            writer.writerow([
                po.order_number,
                po.created_at.strftime("%Y-%m-%d %H:%M") if po.created_at else "",
                po.status.upper(),
                po.supplier.name if po.supplier else "N/A",
                destination,
                po.invoice_number or "",
                po.expected_delivery_date.strftime("%Y-%m-%d") if po.expected_delivery_date else "",
                po.total_quantity,
                po.total_received_quantity,
                f"{po.subtotal:.2f}",
                f"{po.tax_amount:.2f}",
                f"{po.discount_amount:.2f}",
                f"{po.shipping_charges:.2f}",
                f"{po.total_amount:.2f}",
            ])

        return output.getvalue()

    def generate_pdf(self, tenant_id: int, purchase_order_id: int) -> bytes:
        from app.services.document_settings_service import DocumentSettingsService
        from app.services.document_renderer_service import DocumentRenderer

        po = self.get_purchase_order(tenant_id, purchase_order_id)
        supplier = po.supplier
        store_id = po.store_id

        branding = DocumentSettingsService(self.db).resolve_branding(
            tenant_id=tenant_id,
            store_id=store_id,
        )

        items_data = []
        for item in po.items:
            product_name = item.product.name if item.product else f"Product #{item.product_id}"
            sku = item.product.sku if item.product else ""
            items_data.append({
                "product_name": product_name,
                "sku": sku,
                "quantity": item.quantity,
                "unit_cost": float(item.unit_cost),
                "total_cost": float(item.total_cost),
                "tax_rate": float(item.tax_rate or 0),
                "tax_amount": float(item.tax_amount or 0),
                "unit_of_measure": item.unit_of_measure or "pcs",
            })

        data = {
            "order_number": po.order_number,
            "po_number": po.order_number,
            "order_date": po.created_at,
            "status": po.status,
            "notes": po.notes,
            "subtotal": float(po.subtotal or 0),
            "tax_amount": float(po.tax_amount or 0),
            "discount_amount": float(po.discount_amount or 0),
            "shipping_charges": float(po.shipping_charges or 0),
            "total_amount": float(po.total_amount),
            "supplier": {
                "name": supplier.name if supplier else "Vendor",
                "phone": supplier.phone if supplier else "",
                "email": supplier.email if supplier else "",
                "address": supplier.address if supplier else "",
                "gstin": getattr(supplier, "gstin", "") if supplier else "",
            } if supplier else None,
            "items": items_data,
        }

        renderer = DocumentRenderer()
        return renderer.render("purchase_order", data, branding)

    def generate_excel(self, tenant_id: int, purchase_order_id: int) -> bytes:
        from app.services.excel_export_service import ExcelExportService

        po = self.get_purchase_order(tenant_id, purchase_order_id)
        supplier_name = po.supplier.name if po.supplier else "N/A"
        destination = po.store.name if po.store else (po.warehouse.name if po.warehouse else "N/A")

        metadata = {
            "PO Number": po.order_number,
            "Supplier": supplier_name,
            "Destination": destination,
            "Status": po.status.upper(),
            "Order Date": po.created_at.strftime("%Y-%m-%d %H:%M") if po.created_at else "N/A",
            "Expected Delivery": po.expected_delivery_date.strftime("%Y-%m-%d") if po.expected_delivery_date else "N/A",
        }
        kpis = [
            {"label": "Total Quantity", "value": po.total_quantity},
            {"label": "Received Quantity", "value": po.total_received_quantity},
            {"label": "Subtotal", "value": float(po.subtotal or 0)},
            {"label": "Grand Total", "value": float(po.total_amount)},
        ]
        headers = [
            "S.No",
            "Product Name",
            "SKU",
            "Quantity",
            "Unit of Measure",
            "Unit Cost (INR)",
            "Tax Rate (%)",
            "Tax Amount (INR)",
            "Total Cost (INR)",
        ]
        rows = []
        for idx, item in enumerate(po.items, 1):
            p_name = item.product.name if item.product else f"Product #{item.product_id}"
            sku = item.product.sku if item.product else ""
            rows.append([
                idx,
                p_name,
                sku,
                item.quantity,
                item.unit_of_measure or "pcs",
                float(item.unit_cost),
                float(item.tax_rate or 0),
                float(item.tax_amount or 0),
                float(item.total_cost),
            ])

        rows.append([
            "Total",
            "",
            "",
            po.total_quantity,
            "",
            "",
            "",
            float(po.tax_amount or 0),
            float(po.total_amount),
        ])

        sheet_title = f"PO-{po.order_number[-12:]}"
        wb = ExcelExportService().create_report_workbook(
            sheet_title=sheet_title,
            headers=headers,
            rows=rows,
            metadata=metadata,
            kpis=kpis,
            report_type="purple",
        )
        stream = io.BytesIO()
        wb.save(stream)
        return stream.getvalue()

    def generate_single_csv(self, tenant_id: int, purchase_order_id: int) -> bytes:
        po = self.get_purchase_order(tenant_id, purchase_order_id)
        supplier_name = po.supplier.name if po.supplier else "N/A"
        destination = po.store.name if po.store else (po.warehouse.name if po.warehouse else "N/A")

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["PURCHASE ORDER"])
        writer.writerow(["PO Number", po.order_number])
        writer.writerow(["Supplier", supplier_name])
        writer.writerow(["Destination", destination])
        writer.writerow(["Status", po.status.upper()])
        writer.writerow(["Order Date", po.created_at.strftime("%Y-%m-%d %H:%M:%S") if po.created_at else ""])
        writer.writerow(["Expected Delivery", po.expected_delivery_date.strftime("%Y-%m-%d") if po.expected_delivery_date else ""])
        writer.writerow([])
        writer.writerow([
            "S.No",
            "Product Name",
            "SKU",
            "Quantity",
            "Unit of Measure",
            "Unit Cost (INR)",
            "Tax Rate (%)",
            "Tax Amount (INR)",
            "Total Cost (INR)",
        ])
        for idx, item in enumerate(po.items, 1):
            p_name = item.product.name if item.product else f"Product #{item.product_id}"
            sku = item.product.sku if item.product else ""
            writer.writerow([
                idx,
                p_name,
                sku,
                item.quantity,
                item.unit_of_measure or "pcs",
                f"{item.unit_cost:.2f}",
                f"{item.tax_rate or 0:.2f}",
                f"{item.tax_amount or 0:.2f}",
                f"{item.total_cost:.2f}",
            ])
        writer.writerow([])
        writer.writerow(["Subtotal", "", "", "", "", "", "", "", f"{po.subtotal:.2f}"])
        writer.writerow(["Tax Amount", "", "", "", "", "", "", "", f"{po.tax_amount:.2f}"])
        writer.writerow(["Grand Total", "", "", "", "", "", "", "", f"{po.total_amount:.2f}"])
        return output.getvalue().encode("utf-8")
