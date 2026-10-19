import csv
from datetime import date, datetime
from decimal import Decimal
import io
import secrets
from typing import Optional

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from sqlalchemy.orm import Session

from app.core.exceptions import AppException, ConflictException, NotFoundException
from app.models.grn import GRN, GRNItem
from app.models.product import Product
from app.models.purchase_order import PurchaseOrder
from app.models.store import Store
from app.models.warehouse import Warehouse
from app.repositories.grn_repo import GRNRepository
from app.schemas.grn import GRNCreate, GRNQualityCheckRequest
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
        1. Explicit store_id on GRN (Direct Store Delivery).
        2. Warehouse's store_id (auto-provisions backing store if standalone warehouse).
        3. Purchase Order's store_id.
        4. Main active store of the tenant.
        """
        # 1. From explicit GRN store_id
        if grn.store_id:
            store = (
                self.db.query(Store)
                .filter(
                    Store.id == grn.store_id,
                    Store.tenant_id == tenant_id,
                )
                .first()
            )
            if store:
                return store.id

        # 2. From warehouse
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

        # 3. From Purchase Order
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

        # 4. From Tenant Main Store
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
        user_id: Optional[int] = None,
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

            if po.status == "received":
                raise ConflictException(
                    f"Purchase Order #{po.order_number} has already been fully received. Cannot create another GRN."
                )

            # Prevent multiple simultaneous pending GRNs against the same PO
            pending_po_grn = (
                self.db.query(GRN)
                .filter(
                    GRN.tenant_id == tenant_id,
                    GRN.purchase_order_id == data.purchase_order_id,
                    GRN.status == "pending",
                )
                .first()
            )
            if pending_po_grn:
                raise ConflictException(
                    f"A pending GRN ({pending_po_grn.grn_number}) already exists for Purchase Order #{po.order_number}. Please receive or reject it before creating a new GRN."
                )

        # 2. Prevent duplicate Supplier Invoice / Delivery Challan
        if data.invoice_number and data.invoice_number.strip():
            cleaned_invoice = data.invoice_number.strip()
            existing_invoice_grn = (
                self.db.query(GRN)
                .filter(
                    GRN.tenant_id == tenant_id,
                    GRN.invoice_number == cleaned_invoice,
                    GRN.status.in_(["pending", "received"]),
                )
                .first()
            )
            if existing_invoice_grn:
                raise ConflictException(
                    f"A GRN with invoice number '{cleaned_invoice}' already exists ({existing_invoice_grn.grn_number}) with status '{existing_invoice_grn.status}'. Duplicate inwarding is not allowed."
                )

        # 3. Validate Warehouse if specified
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

        # 4. Validate Store if specified (Direct Store Delivery)
        if data.store_id:
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

        # 5. Prevent duplicate identical pending GRNs (anti-double click protection)
        if not data.invoice_number and not data.purchase_order_id and data.items:
            recent_pending = (
                self.db.query(GRN)
                .filter(
                    GRN.tenant_id == tenant_id,
                    GRN.warehouse_id == data.warehouse_id,
                    GRN.store_id == data.store_id,
                    GRN.status == "pending",
                )
                .order_by(GRN.created_at.desc())
                .first()
            )
            if recent_pending and recent_pending.items:
                recent_items = {(it.product_id, it.received_quantity) for it in recent_pending.items}
                incoming_items = {(it.product_id, it.received_quantity) for it in data.items}
                if recent_items == incoming_items:
                    raise ConflictException(
                        f"An identical pending GRN ({recent_pending.grn_number}) already exists for this destination. Please receive or discard it to avoid duplicate stock inwarding."
                    )

        # 6. Validate items list (no duplicate product lines in single request)
        if data.items:
            seen_products = set()
            for it in data.items:
                if it.product_id in seen_products:
                    raise ConflictException(f"Duplicate product #{it.product_id} found in item list. Please combine quantities into a single row.")
                seen_products.add(it.product_id)

        # 4. Generate unique GRN number
        unique_suffix = secrets.token_hex(3).upper()
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        grn_number = f"GRN-{timestamp}-{unique_suffix}"

        grn = GRN(
            tenant_id=tenant_id,
            purchase_order_id=data.purchase_order_id,
            warehouse_id=data.warehouse_id,
            store_id=data.store_id,
            grn_number=grn_number,
            status="pending",
            invoice_number=data.invoice_number,
            invoice_date=data.invoice_date,
            vehicle_number=data.vehicle_number,
            transporter_name=data.transporter_name,
            remarks=data.remarks,
            created_by_id=user_id,
        )

        # 5. Handle items
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
                accepted_qty = item.accepted_quantity if item.accepted_quantity is not None else item.received_quantity
                rejected_qty = item.rejected_quantity if item.rejected_quantity is not None else 0

                grn_item = GRNItem(
                    product_id=item.product_id,
                    ordered_quantity=ordered_qty,
                    received_quantity=item.received_quantity,
                    accepted_quantity=accepted_qty,
                    rejected_quantity=rejected_qty,
                    damage_reason=item.damage_reason,
                    batch_number=item.batch_number,
                    expiry_date=item.expiry_date,
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
                    qty = remaining if remaining > 0 else po_item.quantity
                    grn_item = GRNItem(
                        product_id=po_item.product_id,
                        ordered_quantity=po_item.quantity,
                        received_quantity=qty,
                        accepted_quantity=qty,
                        rejected_quantity=0,
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
        store_id: Optional[int] = None,
        supplier_id: Optional[int] = None,
        status: Optional[str] = None,
        search: Optional[str] = None,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
        skip: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> list[GRN]:
        return self.repo.list(
            tenant_id=tenant_id,
            purchase_order_id=purchase_order_id,
            warehouse_id=warehouse_id,
            store_id=store_id,
            supplier_id=supplier_id,
            status=status,
            search=search,
            from_date=from_date,
            to_date=to_date,
            page=page,
            page_size=page_size,
            skip=skip,
            limit=limit,
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

    def get_by_number(
        self,
        tenant_id: int,
        grn_number: str,
    ) -> GRN:
        grn = self.repo.get_by_number(
            grn_number=grn_number,
            tenant_id=tenant_id,
        )
        if not grn:
            raise NotFoundException(f"GRN with number '{grn_number}' not found")
        return grn

    def stats(
        self,
        tenant_id: int,
    ) -> dict:
        return self.repo.get_stats(tenant_id)

    def receive(
        self,
        tenant_id: int,
        grn_id: int,
        user_id: Optional[int] = None,
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

        # 3. Process stock-in for every accepted item
        for item in grn.items:
            qty_to_inward = item.accepted_quantity if item.accepted_quantity is not None else item.received_quantity
            if qty_to_inward <= 0:
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

            # Determine batch number: prioritize user/supplier batch, fallback to formatted GRN batch
            batch_number = item.batch_number or f"GRN-{grn.grn_number[-6:]}-{item.product_id}"

            stock_in_kwargs = {
                "store_id": target_store_id,
                "product_id": item.product_id,
                "quantity": qty_to_inward,
                "supplier_id": supplier_id,
                "unit_cost": cost,
                "batch_number": batch_number,
                "notes": f"GRN Inward: {grn.grn_number}" + (f" (PO: {po.order_number})" if po else ""),
            }
            if item.expiry_date is not None:
                stock_in_kwargs["expiry_date"] = item.expiry_date

            stock_in_req = StockInRequest(**stock_in_kwargs)

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
                po_item.received_quantity = (po_item.received_quantity or 0) + qty_to_inward

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
        if user_id:
            grn.received_by_id = user_id

        self.db.commit()
        self.db.refresh(grn)
        return grn

    def reject(
        self,
        tenant_id: int,
        grn_id: int,
        reason: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> GRN:
        grn = self.get(
            tenant_id=tenant_id,
            grn_id=grn_id,
        )

        if grn.status == "received":
            raise ConflictException("Cannot reject a GRN that has already been received into inventory")

        grn.status = "rejected"
        if reason:
            grn.rejection_reason = reason
        if user_id:
            grn.received_by_id = user_id

        return self.repo.update(grn)

    def quality_check(
        self,
        tenant_id: int,
        grn_id: int,
        data: GRNQualityCheckRequest,
    ) -> GRN:
        grn = self.get(
            tenant_id=tenant_id,
            grn_id=grn_id,
        )

        if grn.status != "pending":
            raise ConflictException("Quality inspection can only be performed on pending GRNs")

        item_map = {item.id: item for item in grn.items}
        for qc_item in data.items:
            if qc_item.item_id not in item_map:
                raise NotFoundException(f"Item #{qc_item.item_id} does not belong to this GRN")
            item = item_map[qc_item.item_id]
            item.accepted_quantity = qc_item.accepted_quantity
            item.rejected_quantity = qc_item.rejected_quantity
            if qc_item.damage_reason:
                item.damage_reason = qc_item.damage_reason
            if qc_item.batch_number:
                item.batch_number = qc_item.batch_number
            if qc_item.expiry_date:
                item.expiry_date = qc_item.expiry_date
            if qc_item.remarks:
                item.remarks = qc_item.remarks

        if data.remarks:
            grn.remarks = f"{grn.remarks}\nQC: {data.remarks}" if grn.remarks else f"QC: {data.remarks}"

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

        timeline = [
            {
                "event": "GRN Created",
                "timestamp": grn.created_at,
                "performed_by": grn.created_by_name or "System Operator",
                "details": f"GRN #{grn.grn_number} initialized in pending state with {grn.total_items_count} item(s)",
            }
        ]

        if grn.received_at:
            timeline.append({
                "event": "GRN Received & Stock Inwarded",
                "timestamp": grn.received_at,
                "performed_by": grn.received_by_name or "Warehouse Incharge",
                "details": f"Inwarded {grn.total_accepted_quantity} accepted units into inventory valuation",
            })
        elif grn.status == "rejected":
            timeline.append({
                "event": "GRN Rejected",
                "timestamp": grn.updated_at,
                "performed_by": grn.received_by_name or "Warehouse Inspector",
                "details": grn.rejection_reason or "Shipment rejected during receipt",
            })

        return {
            "grn_id": grn.id,
            "grn_number": grn.grn_number,
            "status": grn.status,
            "created_at": grn.created_at,
            "received_at": grn.received_at,
            "updated_at": grn.updated_at,
            "created_by_name": grn.created_by_name,
            "received_by_name": grn.received_by_name,
            "rejection_reason": grn.rejection_reason,
            "timeline": timeline,
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

    def generate_slip_html(
        self,
        tenant_id: int,
        grn_id: int,
    ) -> str:
        grn = self.get(tenant_id, grn_id)

        rows_html = ""
        for idx, item in enumerate(grn.items, start=1):
            batch_str = item.batch_number or "-"
            exp_str = item.expiry_date.strftime("%d-%m-%Y") if item.expiry_date else "-"
            cost_str = f"₹{item.unit_cost:.2f}" if item.unit_cost is not None else "-"
            accepted = item.accepted_quantity if item.accepted_quantity is not None else item.received_quantity
            rejected = item.rejected_quantity or 0
            rows_html += f"""
            <tr>
                <td style="border: 1px solid #ddd; padding: 8px; text-align: center;">{idx}</td>
                <td style="border: 1px solid #ddd; padding: 8px;"><strong>{item.product_name or 'N/A'}</strong><br><small style="color: #666;">SKU: {item.product_sku or '-'}</small></td>
                <td style="border: 1px solid #ddd; padding: 8px; text-align: center;">{batch_str}</td>
                <td style="border: 1px solid #ddd; padding: 8px; text-align: center;">{exp_str}</td>
                <td style="border: 1px solid #ddd; padding: 8px; text-align: right;">{item.ordered_quantity}</td>
                <td style="border: 1px solid #ddd; padding: 8px; text-align: right;">{item.received_quantity}</td>
                <td style="border: 1px solid #ddd; padding: 8px; text-align: right; color: green; font-weight: bold;">{accepted}</td>
                <td style="border: 1px solid #ddd; padding: 8px; text-align: right; color: red;">{rejected}</td>
                <td style="border: 1px solid #ddd; padding: 8px; text-align: right;">{cost_str}</td>
            </tr>
            """

        destination = grn.warehouse_name or grn.store_name or "Main Storage"
        status_color = "#28a745" if grn.status == "received" else ("#dc3545" if grn.status == "rejected" else "#ffc107")

        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Goods Received Note - {grn.grn_number}</title>
    <style>
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 20px; color: #333; }}
        @media print {{
            .no-print {{ display: none !important; }}
            body {{ margin: 0; padding: 10px; }}
            @page {{ size: A4; margin: 10mm; }}
        }}
        .action-bar {{
            position: sticky;
            top: 0;
            background: #1e293b;
            color: #f8fafc;
            padding: 12px 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-radius: 8px;
            margin-bottom: 24px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            z-index: 1000;
        }}
        .action-title {{ display: flex; align-items: center; gap: 10px; font-size: 14px; }}
        .action-badge {{ background: #3b82f6; color: white; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: bold; }}
        .action-buttons {{ display: flex; gap: 10px; align-items: center; }}
        .btn {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 7px 14px;
            border-radius: 6px;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            text-decoration: none;
            border: none;
            transition: all 0.2s;
        }}
        .btn-print {{ background: #3b82f6; color: white; }}
        .btn-print:hover {{ background: #2563eb; }}
        .btn-download {{ background: #10b981; color: white; }}
        .btn-download:hover {{ background: #059669; }}
        .btn-preview {{ background: #6366f1; color: white; }}
        .btn-preview:hover {{ background: #4f46e5; }}
        .btn-csv {{ background: #475569; color: white; }}
        .btn-csv:hover {{ background: #334155; }}

        .header {{ display: flex; justify-content: space-between; border-bottom: 2px solid #0056b3; padding-bottom: 10px; margin-bottom: 20px; }}
        .title {{ font-size: 24px; font-weight: bold; color: #0056b3; }}
        .badge {{ display: inline-block; padding: 4px 10px; border-radius: 4px; font-weight: bold; color: white; background: {status_color}; text-transform: uppercase; font-size: 12px; }}
        .meta-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-bottom: 20px; background: #f8f9fa; padding: 15px; border-radius: 6px; }}
        table {{ width: 100%; border-collapse: collapse; margin-bottom: 25px; }}
        th {{ background: #f1f3f5; border: 1px solid #ddd; padding: 10px; text-align: left; font-size: 13px; }}
        .signatures {{ display: flex; justify-content: space-between; margin-top: 50px; padding-top: 20px; }}
        .sign-box {{ width: 220px; border-top: 1px solid #333; text-align: center; font-size: 13px; padding-top: 5px; }}
        .barcode-box {{ font-family: monospace; font-size: 18px; letter-spacing: 4px; border: 1px dashed #666; padding: 6px; display: inline-block; background: #fff; }}
    </style>
</head>
<body>
    <div class="action-bar no-print">
        <div class="action-title">
            <span class="action-badge">PRINT PREVIEW</span>
            <span>Goods Received Note: <strong>{grn.grn_number}</strong></span>
        </div>
        <div class="action-buttons">
            <button onclick="window.print()" class="btn btn-print">
                🖨️ Print Slip
            </button>
            <a href="/api/v1/grn/{grn.id}/download-pdf" class="btn btn-download">
                ⬇️ Download PDF
            </a>
            <a href="/api/v1/grn/{grn.id}/download-pdf?mode=preview" target="_blank" class="btn btn-preview">
                👁️ PDF Preview
            </a>
            <a href="/api/v1/grn/export" class="btn btn-csv">
                📊 Export CSV
            </a>
        </div>
    </div>

    <div class="header">
        <div>
            <div class="title">GOODS RECEIVED NOTE (GRN)</div>
            <div class="barcode-box">*{grn.grn_number}*</div>
        </div>
        <div style="text-align: right;">
            <div><span class="badge">{grn.status}</span></div>
            <div style="margin-top: 5px; font-size: 13px; color: #666;">Date: {grn.created_at.strftime("%d-%m-%Y %H:%M")}</div>
        </div>
    </div>

    <div class="meta-grid">
        <div>
            <strong>Supplier / Vendor:</strong> {grn.supplier_name or 'Direct Inward'}<br>
            <strong>PO Number:</strong> {grn.purchase_order_number or 'N/A'}<br>
            <strong>Invoice / DC No:</strong> {grn.invoice_number or 'N/A'} {f"({grn.invoice_date.strftime('%d-%m-%Y')})" if grn.invoice_date else ''}<br>
        </div>
        <div>
            <strong>Destination Location:</strong> {destination}<br>
            <strong>Transporter / Vehicle:</strong> {grn.transporter_name or 'N/A'} {f"[{grn.vehicle_number}]" if grn.vehicle_number else ''}<br>
            <strong>Received By:</strong> {grn.received_by_name or 'Pending Inspection'}<br>
        </div>
    </div>

    <table>
        <thead>
            <tr>
                <th style="width: 40px; text-align: center;">#</th>
                <th>Product Description</th>
                <th style="text-align: center;">Batch</th>
                <th style="text-align: center;">Expiry</th>
                <th style="text-align: right;">Ordered</th>
                <th style="text-align: right;">Received</th>
                <th style="text-align: right;">Accepted</th>
                <th style="text-align: right;">Rejected</th>
                <th style="text-align: right;">Unit Cost</th>
            </tr>
        </thead>
        <tbody>
            {rows_html}
        </tbody>
        <tfoot>
            <tr style="background: #f8f9fa; font-weight: bold;">
                <td colspan="4" style="border: 1px solid #ddd; padding: 8px; text-align: right;">Total:</td>
                <td style="border: 1px solid #ddd; padding: 8px; text-align: right;">{grn.total_ordered_quantity}</td>
                <td style="border: 1px solid #ddd; padding: 8px; text-align: right;">{grn.total_received_quantity}</td>
                <td style="border: 1px solid #ddd; padding: 8px; text-align: right; color: green;">{grn.total_accepted_quantity}</td>
                <td style="border: 1px solid #ddd; padding: 8px; text-align: right; color: red;">{grn.total_rejected_quantity}</td>
                <td style="border: 1px solid #ddd; padding: 8px; text-align: right;">₹{grn.total_cost_value:.2f}</td>
            </tr>
        </tfoot>
    </table>

    <div class="signatures">
        <div class="sign-box">Transporter / Driver Signature</div>
        <div class="sign-box">QC Inspector Signature</div>
        <div class="sign-box">Warehouse Incharge Signature</div>
    </div>
</body>
</html>
"""
        return html

    def generate_pdf(
        self,
        tenant_id: int,
        grn_id: int,
    ) -> bytes:
        grn = self.get(tenant_id, grn_id)

        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4

        margin_left = 15 * mm
        margin_right = width - 15 * mm
        y = height - 20 * mm

        # Header Title
        c.setFont("Helvetica-Bold", 16)
        c.setFillColorRGB(0.0, 0.3, 0.7)
        c.drawString(margin_left, y, "GOODS RECEIVED NOTE (GRN)")

        # Status badge
        c.setFont("Helvetica-Bold", 10)
        status_text = grn.status.upper()
        if grn.status == "received":
            c.setFillColorRGB(0.1, 0.6, 0.2)
        elif grn.status == "rejected":
            c.setFillColorRGB(0.8, 0.1, 0.1)
        else:
            c.setFillColorRGB(0.8, 0.6, 0.0)
        c.drawRightString(margin_right, y, f"STATUS: {status_text}")

        # Subheader
        y -= 6 * mm
        c.setFillColorRGB(0.2, 0.2, 0.2)
        c.setFont("Helvetica", 9)
        c.drawString(margin_left, y, f"GRN Number: {grn.grn_number}")
        date_str = grn.created_at.strftime("%d-%m-%Y %H:%M") if grn.created_at else ""
        c.drawRightString(margin_right, y, f"Date: {date_str}")

        # Horizontal separator line
        y -= 4 * mm
        c.setStrokeColorRGB(0.8, 0.8, 0.8)
        c.setLineWidth(1)
        c.line(margin_left, y, margin_right, y)

        # Meta grid
        y -= 7 * mm
        c.setFont("Helvetica-Bold", 9)
        c.setFillColorRGB(0.1, 0.1, 0.1)
        c.drawString(margin_left, y, "Supplier / Vendor:")
        c.drawString(margin_left + 95 * mm, y, "Destination Location:")

        y -= 4 * mm
        c.setFont("Helvetica", 8.5)
        c.setFillColorRGB(0.3, 0.3, 0.3)
        c.drawString(margin_left, y, str(grn.supplier_name or "Direct Inward"))
        dest = grn.warehouse_name or grn.store_name or "Main Storage"
        c.drawString(margin_left + 95 * mm, y, str(dest))

        y -= 5 * mm
        c.setFont("Helvetica-Bold", 9)
        c.setFillColorRGB(0.1, 0.1, 0.1)
        c.drawString(margin_left, y, "PO Number / Invoice:")
        c.drawString(margin_left + 95 * mm, y, "Transporter / Vehicle:")

        y -= 4 * mm
        c.setFont("Helvetica", 8.5)
        c.setFillColorRGB(0.3, 0.3, 0.3)
        po_info = f"PO: {grn.purchase_order_number or 'N/A'}"
        if grn.invoice_number:
            po_info += f" | Inv: {grn.invoice_number}"
        c.drawString(margin_left, y, po_info)
        trans_info = f"{grn.transporter_name or 'N/A'}"
        if grn.vehicle_number:
            trans_info += f" [{grn.vehicle_number}]"
        c.drawString(margin_left + 95 * mm, y, trans_info)

        y -= 5 * mm
        c.setFont("Helvetica-Bold", 9)
        c.setFillColorRGB(0.1, 0.1, 0.1)
        c.drawString(margin_left, y, "Received By:")
        y -= 4 * mm
        c.setFont("Helvetica", 8.5)
        c.setFillColorRGB(0.3, 0.3, 0.3)
        c.drawString(margin_left, y, str(grn.received_by_name or "Pending Verification"))

        # Separator line
        y -= 6 * mm
        c.setStrokeColorRGB(0.8, 0.8, 0.8)
        c.line(margin_left, y, margin_right, y)

        # Table Header
        y -= 6 * mm
        c.setFillColorRGB(0.95, 0.96, 0.98)
        c.rect(margin_left, y - 2 * mm, margin_right - margin_left, 7 * mm, fill=1, stroke=0)

        c.setFont("Helvetica-Bold", 8)
        c.setFillColorRGB(0.1, 0.1, 0.1)
        c.drawString(margin_left + 2 * mm, y, "#")
        c.drawString(margin_left + 8 * mm, y, "Product / SKU")
        c.drawString(margin_left + 65 * mm, y, "Batch")
        c.drawString(margin_left + 95 * mm, y, "Expiry")
        c.drawRightString(margin_left + 120 * mm, y, "Ordered")
        c.drawRightString(margin_left + 138 * mm, y, "Accepted")
        c.drawRightString(margin_left + 155 * mm, y, "Rejected")
        c.drawRightString(margin_right - 2 * mm, y, "Cost (INR)")

        y -= 6 * mm
        c.setFont("Helvetica", 8)
        c.setFillColorRGB(0.2, 0.2, 0.2)

        for idx, item in enumerate(grn.items, start=1):
            if y < 35 * mm:
                c.showPage()
                y = height - 20 * mm
                c.setFont("Helvetica", 8)

            c.drawString(margin_left + 2 * mm, y, str(idx))
            p_desc = f"{item.product_name or 'Product'} ({item.product_sku or ''})"[:32]
            c.drawString(margin_left + 8 * mm, y, p_desc)
            c.drawString(margin_left + 65 * mm, y, str(item.batch_number or "-")[:15])
            exp_str = item.expiry_date.strftime("%d-%m-%Y") if item.expiry_date else "-"
            c.drawString(margin_left + 95 * mm, y, exp_str)
            c.drawRightString(margin_left + 120 * mm, y, str(item.ordered_quantity))
            accepted = item.accepted_quantity if item.accepted_quantity is not None else item.received_quantity
            c.drawRightString(margin_left + 138 * mm, y, str(accepted))
            c.drawRightString(margin_left + 155 * mm, y, str(item.rejected_quantity or 0))
            cost_str = f"{item.unit_cost:.2f}" if item.unit_cost is not None else "-"
            c.drawRightString(margin_right - 2 * mm, y, cost_str)
            y -= 5 * mm

        # Summary line
        y -= 2 * mm
        c.setStrokeColorRGB(0.7, 0.7, 0.7)
        c.line(margin_left, y, margin_right, y)
        y -= 5 * mm
        c.setFont("Helvetica-Bold", 8.5)
        c.drawString(margin_left + 8 * mm, y, "TOTALS:")
        c.drawRightString(margin_left + 120 * mm, y, str(grn.total_ordered_quantity))
        c.drawRightString(margin_left + 138 * mm, y, str(grn.total_accepted_quantity))
        c.drawRightString(margin_left + 155 * mm, y, str(grn.total_rejected_quantity))
        c.drawRightString(margin_right - 2 * mm, y, f"INR {grn.total_cost_value:.2f}")

        # Signatures
        sig_y = max(y - 25 * mm, 25 * mm)
        c.setStrokeColorRGB(0.3, 0.3, 0.3)
        c.setLineWidth(0.5)

        box_width = 45 * mm
        c.line(margin_left, sig_y, margin_left + box_width, sig_y)
        c.line(margin_left + 65 * mm, sig_y, margin_left + 65 * mm + box_width, sig_y)
        c.line(margin_right - box_width, sig_y, margin_right, sig_y)

        c.setFont("Helvetica", 7.5)
        c.setFillColorRGB(0.2, 0.2, 0.2)
        c.drawCentredString(margin_left + box_width / 2, sig_y - 4 * mm, "Driver / Carrier Signature")
        c.drawCentredString(margin_left + 65 * mm + box_width / 2, sig_y - 4 * mm, "QC Inspector Signature")
        c.drawCentredString(margin_right - box_width / 2, sig_y - 4 * mm, "Warehouse Incharge Signature")

        c.save()
        buffer.seek(0)
        return buffer.getvalue()

    def export_csv(
        self,
        tenant_id: int,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        status: Optional[str] = None,
    ) -> str:
        grns = self.list(
            tenant_id=tenant_id,
            from_date=from_date,
            to_date=to_date,
            status=status,
        )

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "GRN Number",
            "Date",
            "Status",
            "PO Number",
            "Supplier",
            "Destination",
            "Invoice Number",
            "Invoice Date",
            "Vehicle Number",
            "Transporter",
            "Total Items",
            "Total Ordered Qty",
            "Total Received Qty",
            "Total Accepted Qty",
            "Total Rejected Qty",
            "Total Cost Value (INR)",
            "Created By",
            "Received By",
        ])

        for g in grns:
            dest = g.warehouse_name or g.store_name or "Main"
            writer.writerow([
                g.grn_number,
                g.created_at.strftime("%Y-%m-%d %H:%M"),
                g.status,
                g.purchase_order_number or "",
                g.supplier_name or "",
                dest,
                g.invoice_number or "",
                g.invoice_date.strftime("%Y-%m-%d") if g.invoice_date else "",
                g.vehicle_number or "",
                g.transporter_name or "",
                g.total_items_count,
                g.total_ordered_quantity,
                g.total_received_quantity,
                g.total_accepted_quantity,
                g.total_rejected_quantity,
                f"{g.total_cost_value:.2f}",
                g.created_by_name or "",
                g.received_by_name or "",
            ])

        return output.getvalue()

    def generate_excel(self, tenant_id: int, grn_id: int) -> bytes:
        from app.services.excel_export_service import ExcelExportService

        grn = self.get(tenant_id, grn_id)
        supplier_name = grn.purchase_order.supplier.name if grn.purchase_order and grn.purchase_order.supplier else "N/A"
        destination = grn.warehouse.name if grn.warehouse else (grn.store.name if grn.store else "N/A")

        metadata = {
            "GRN Number": grn.grn_number,
            "PO Number": grn.purchase_order.order_number if grn.purchase_order else "N/A",
            "Supplier": supplier_name,
            "Destination": destination,
            "Status": grn.status.upper(),
            "Date": grn.created_at.strftime("%Y-%m-%d %H:%M") if grn.created_at else "N/A",
            "Invoice No": grn.invoice_number or "N/A",
            "Vehicle No": grn.vehicle_number or "N/A",
        }
        total_ordered = sum(it.ordered_quantity or 0 for it in grn.items)
        total_received = sum(it.received_quantity or 0 for it in grn.items)
        total_rejected = sum(it.rejected_quantity or 0 for it in grn.items)
        kpis = [
            {"label": "Ordered Qty", "value": total_ordered},
            {"label": "Received Qty", "value": total_received},
            {"label": "Rejected Qty", "value": total_rejected},
        ]
        headers = [
            "S.No",
            "Product Name",
            "SKU",
            "Batch Number",
            "Ordered Qty",
            "Received Qty",
            "Rejected Qty",
            "Unit Cost (INR)",
            "Total Cost (INR)",
        ]
        rows = []
        for idx, item in enumerate(grn.items, 1):
            p_name = item.product.name if item.product else f"Product #{item.product_id}"
            sku = item.product.sku if item.product else ""
            unit_cost = float(item.unit_cost or 0)
            total_cost = unit_cost * float(item.received_quantity or 0)
            rows.append([
                idx,
                p_name,
                sku,
                item.batch_number or "-",
                item.ordered_quantity or 0,
                item.received_quantity or 0,
                item.rejected_quantity or 0,
                unit_cost,
                total_cost,
            ])

        sheet_title = f"GRN-{grn.grn_number[-12:]}"
        wb = ExcelExportService().create_report_workbook(
            sheet_title=sheet_title,
            headers=headers,
            rows=rows,
            metadata=metadata,
            kpis=kpis,
            report_type="blue",
        )
        stream = io.BytesIO()
        wb.save(stream)
        return stream.getvalue()

    def generate_single_csv(self, tenant_id: int, grn_id: int) -> bytes:
        import csv
        grn = self.get(tenant_id, grn_id)
        supplier_name = grn.purchase_order.supplier.name if grn.purchase_order and grn.purchase_order.supplier else "N/A"
        destination = grn.warehouse.name if grn.warehouse else (grn.store.name if grn.store else "N/A")

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["GOODS RECEIVED NOTE (GRN)"])
        writer.writerow(["GRN Number", grn.grn_number])
        writer.writerow(["PO Number", grn.purchase_order.order_number if grn.purchase_order else "N/A"])
        writer.writerow(["Supplier", supplier_name])
        writer.writerow(["Destination", destination])
        writer.writerow(["Status", grn.status.upper()])
        writer.writerow(["Date", grn.created_at.strftime("%Y-%m-%d %H:%M:%S") if grn.created_at else ""])
        writer.writerow(["Invoice Number", grn.invoice_number or ""])
        writer.writerow(["Vehicle Number", grn.vehicle_number or ""])
        writer.writerow([])
        writer.writerow([
            "S.No",
            "Product Name",
            "SKU",
            "Batch Number",
            "Ordered Qty",
            "Received Qty",
            "Rejected Qty",
            "Unit Cost (INR)",
            "Total Cost (INR)",
        ])
        for idx, item in enumerate(grn.items, 1):
            p_name = item.product.name if item.product else f"Product #{item.product_id}"
            sku = item.product.sku if item.product else ""
            unit_cost = float(item.unit_cost or 0)
            total_cost = unit_cost * float(item.received_quantity or 0)
            writer.writerow([
                idx,
                p_name,
                sku,
                item.batch_number or "-",
                item.ordered_quantity or 0,
                item.received_quantity or 0,
                item.rejected_quantity or 0,
                f"{unit_cost:.2f}",
                f"{total_cost:.2f}",
            ])
        return output.getvalue().encode("utf-8")
