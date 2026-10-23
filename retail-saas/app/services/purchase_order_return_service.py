import csv
from datetime import date, datetime
from decimal import Decimal
import io
import secrets
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.exceptions import AppException, ConflictException, NotFoundException
from app.models.purchase_order import (
    PurchaseOrder,
    PurchaseOrderItem,
)
from app.models.purchase_order_return import (
    PurchaseOrderReturn,
    PurchaseOrderReturnItem,
)
from app.models.store import Store
from app.models.supplier import Supplier
from app.models.warehouse import Warehouse
from app.repositories.purchase_order_return_repo import (
    PurchaseOrderReturnRepository,
)
from app.schemas.inventory import StockOutRequest
from app.schemas.purchase_order_return import (
    PurchaseOrderReturnCreate,
    PurchaseOrderReturnRejectRequest,
    PurchaseOrderReturnStatusUpdate,
    PurchaseOrderReturnUpdate,
)
from app.services.inventory_service import InventoryService


class PurchaseOrderReturnService:

    def __init__(self, db: Session):
        self.db = db
        self.repo = PurchaseOrderReturnRepository(db)

    def _get_return(
        self,
        tenant_id: int,
        return_id: int,
    ) -> PurchaseOrderReturn:
        if return_id <= 0:
            raise NotFoundException("Purchase Order Return not found")

        purchase_order_return = self.repo.get_by_id(
            return_id,
            tenant_id,
        )

        if not purchase_order_return:
            raise NotFoundException("Purchase Order Return not found")

        return purchase_order_return

    def _get_purchase_order(
        self,
        tenant_id: int,
        purchase_order_id: int,
    ) -> PurchaseOrder:
        if purchase_order_id <= 0:
            raise NotFoundException("Purchase Order not found")

        purchase_order = (
            self.db.query(PurchaseOrder)
            .filter(
                PurchaseOrder.id == purchase_order_id,
                PurchaseOrder.tenant_id == tenant_id,
            )
            .first()
        )

        if not purchase_order:
            raise NotFoundException("Purchase Order not found")

        return purchase_order

    def _resolve_target_store_id(
        self,
        tenant_id: int,
        por: PurchaseOrderReturn,
        po: PurchaseOrder,
    ) -> int:
        """Determines origin store_id for stock-out deduction."""
        if por.store_id:
            return por.store_id

        if po.store_id:
            return po.store_id

        target_wh_id = por.warehouse_id or getattr(po, "warehouse_id", None)
        if target_wh_id:
            wh = (
                self.db.query(Warehouse)
                .filter(Warehouse.id == target_wh_id, Warehouse.tenant_id == tenant_id)
                .first()
            )
            if wh and wh.store_id:
                return wh.store_id

        main_store = (
            self.db.query(Store)
            .filter(Store.tenant_id == tenant_id, Store.is_active == True)
            .order_by(Store.is_main.desc(), Store.id.asc())
            .first()
        )
        if main_store:
            return main_store.id

        raise ConflictException("No active store or warehouse facility found for inventory deduction")

    def create_return(
        self,
        tenant_id: int,
        data: PurchaseOrderReturnCreate,
        user_id: Optional[int] = None,
    ) -> PurchaseOrderReturn:
        purchase_order = self._get_purchase_order(
            tenant_id,
            data.purchase_order_id,
        )

        # 1. Allow returning from received OR partially_received purchase orders
        if purchase_order.status not in {"received", "partially_received"}:
            raise ConflictException(
                f"Cannot create return for purchase order #{purchase_order.order_number} in '{purchase_order.status}' status. "
                "Only received or partially received purchase orders can have returns initiated."
            )

        return_item_ids = {
            item.purchase_order_item_id
            for item in data.items
        }

        po_items = (
            self.db.query(PurchaseOrderItem)
            .filter(
                PurchaseOrderItem.po_id == purchase_order.id,
                PurchaseOrderItem.id.in_(return_item_ids),
            )
            .all()
        )

        if len(po_items) != len(return_item_ids):
            raise NotFoundException("One or more Purchase Order Items not found")

        po_item_map = {item.id: item for item in po_items}

        # 2. Calculate quantities already returned across non-rejected returns
        existing_return_items = (
            self.db.query(PurchaseOrderReturnItem)
            .join(
                PurchaseOrderReturn,
                PurchaseOrderReturn.id == PurchaseOrderReturnItem.purchase_order_return_id,
            )
            .filter(
                PurchaseOrderReturn.tenant_id == tenant_id,
                PurchaseOrderReturn.purchase_order_id == purchase_order.id,
                PurchaseOrderReturn.status.in_({"requested", "approved", "completed"}),
                PurchaseOrderReturnItem.purchase_order_item_id.in_(return_item_ids),
            )
            .all()
        )

        already_returned = {}
        for return_item in existing_return_items:
            already_returned[return_item.purchase_order_item_id] = (
                already_returned.get(return_item.purchase_order_item_id, 0) + return_item.quantity
            )

        # 3. Generate unique return number and debit note number
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        suffix = secrets.token_hex(2).upper()
        return_number = f"POR-{timestamp}-{suffix}"
        debit_note = data.debit_note_number or f"DN-{timestamp}-{suffix}"

        # Resolve location
        target_store_id = data.store_id or purchase_order.store_id
        target_wh_id = data.warehouse_id or getattr(purchase_order, "warehouse_id", None)

        purchase_order_return = PurchaseOrderReturn(
            tenant_id=tenant_id,
            return_number=return_number,
            debit_note_number=debit_note,
            purchase_order_id=purchase_order.id,
            supplier_id=purchase_order.supplier_id,
            store_id=target_store_id,
            warehouse_id=target_wh_id,
            reason=data.reason,
            remarks=getattr(data, "remarks", None),
            status="requested",
            total_amount=Decimal("0.00"),
            created_by_id=user_id,
        )

        total_amount = Decimal("0.00")

        # 4. Check return quantities against received_quantity (NEVER unreceived order quantity)
        for data_item in data.items:
            po_item = po_item_map[data_item.purchase_order_item_id]

            already_ret = already_returned.get(po_item.id, 0)
            received_qty = po_item.received_quantity or 0

            remaining_returnable = max(0, received_qty - already_ret)

            if remaining_returnable <= 0:
                raise ConflictException(
                    f"Item #{po_item.id} (Product #{po_item.product_id}) has no returnable stock remaining. "
                    f"Total Received: {received_qty}, Already Returned: {already_ret}."
                )

            if data_item.quantity > remaining_returnable:
                raise ConflictException(
                    f"Return quantity ({data_item.quantity}) for Purchase Order Item #{po_item.id} "
                    f"cannot exceed remaining returnable quantity ({remaining_returnable})."
                )

            unit_cost = po_item.unit_price or po_item.unit_cost or Decimal("0.00")
            item_total = Decimal(data_item.quantity) * unit_cost

            purchase_order_return.items.append(
                PurchaseOrderReturnItem(
                    purchase_order_item_id=po_item.id,
                    product_id=po_item.product_id,
                    quantity=data_item.quantity,
                    unit_price=unit_cost,
                    total=item_total,
                    batch_number=data_item.batch_number,
                    item_reason=data_item.item_reason or data.reason,
                )
            )

            total_amount += item_total

        if total_amount <= Decimal("0.00"):
            raise ConflictException("Return amount must be greater than zero")

        purchase_order_return.total_amount = total_amount

        return self.repo.create(purchase_order_return)

    def list_returns(
        self,
        tenant_id: int,
        page: int = 1,
        page_size: int = 20,
        purchase_order_id: Optional[int] = None,
        supplier_id: Optional[int] = None,
        store_id: Optional[int] = None,
        warehouse_id: Optional[int] = None,
        status: Optional[str] = None,
        from_date: Optional[date | datetime] = None,
        to_date: Optional[date | datetime] = None,
        search: Optional[str] = None,
    ) -> list[PurchaseOrderReturn]:
        if page < 1:
            page = 1
        if page_size < 1:
            page_size = 20
        if page_size > 100:
            page_size = 100

        skip = (page - 1) * page_size

        return self.repo.list_returns(
            tenant_id=tenant_id,
            skip=skip,
            limit=page_size,
            purchase_order_id=purchase_order_id,
            supplier_id=supplier_id,
            store_id=store_id,
            warehouse_id=warehouse_id,
            status=status,
            from_date=from_date,
            to_date=to_date,
            search=search,
        )

    def count_returns(
        self,
        tenant_id: int,
        purchase_order_id: Optional[int] = None,
        supplier_id: Optional[int] = None,
        store_id: Optional[int] = None,
        warehouse_id: Optional[int] = None,
        status: Optional[str] = None,
        from_date: Optional[date | datetime] = None,
        to_date: Optional[date | datetime] = None,
        search: Optional[str] = None,
    ) -> int:
        return self.repo.count_returns(
            tenant_id=tenant_id,
            purchase_order_id=purchase_order_id,
            supplier_id=supplier_id,
            store_id=store_id,
            warehouse_id=warehouse_id,
            status=status,
            from_date=from_date,
            to_date=to_date,
            search=search,
        )

    def get_return(
        self,
        tenant_id: int,
        return_id: int,
    ) -> PurchaseOrderReturn:
        return self._get_return(
            tenant_id,
            return_id,
        )

    def get_by_number(
        self,
        tenant_id: int,
        return_number: str,
    ) -> PurchaseOrderReturn:
        por = self.repo.get_by_number(
            return_number=return_number,
            tenant_id=tenant_id,
        )
        if not por:
            raise NotFoundException(f"Purchase order return '{return_number}' not found")
        return por

    def update_return(
        self,
        tenant_id: int,
        return_id: int,
        data: PurchaseOrderReturnUpdate,
    ) -> PurchaseOrderReturn:
        purchase_order_return = self._get_return(
            tenant_id,
            return_id,
        )

        if purchase_order_return.status != "requested":
            raise ConflictException("Only requested returns can be updated")

        if data.reason is not None:
            purchase_order_return.reason = data.reason

        if getattr(data, "remarks", None) is not None:
            purchase_order_return.remarks = data.remarks

        if data.debit_note_number is not None:
            purchase_order_return.debit_note_number = data.debit_note_number

        # Update items if provided in requested state
        if data.items is not None:
            po = purchase_order_return.purchase_order
            po_items = {it.id: it for it in po.items}
            purchase_order_return.items.clear()
            total_amount = Decimal("0.00")

            for data_item in data.items:
                if data_item.purchase_order_item_id not in po_items:
                    raise NotFoundException(f"PO item #{data_item.purchase_order_item_id} not in original order")

                po_it = po_items[data_item.purchase_order_item_id]
                received_qty = po_it.received_quantity or 0
                if data_item.quantity > received_qty:
                    raise ConflictException(f"Return quantity exceeds received quantity for item #{po_it.id}")

                unit_cost = po_it.unit_price or po_it.unit_cost or Decimal("0.00")
                item_tot = Decimal(data_item.quantity) * unit_cost

                purchase_order_return.items.append(
                    PurchaseOrderReturnItem(
                        purchase_order_item_id=po_it.id,
                        product_id=po_it.product_id,
                        quantity=data_item.quantity,
                        unit_price=unit_cost,
                        total=item_tot,
                        batch_number=data_item.batch_number,
                        item_reason=data_item.item_reason or purchase_order_return.reason,
                    )
                )
                total_amount += item_tot

            purchase_order_return.total_amount = total_amount

        return self.repo.update(purchase_order_return)

    def _process_stock_out(
        self,
        tenant_id: int,
        por: PurchaseOrderReturn,
    ) -> None:
        """Executes inventory stock-out deduction for completed vendor return."""
        po = por.purchase_order
        target_store_id = self._resolve_target_store_id(tenant_id, por, po)
        inventory_service = InventoryService(self.db)

        for item in por.items:
            inventory_service.stock_out(
                tenant_id,
                StockOutRequest(
                    store_id=target_store_id,
                    product_id=item.product_id,
                    quantity=item.quantity,
                    notes=(
                        f"Vendor Return #{por.return_number} (Ref: {por.debit_note_number or 'N/A'}, "
                        f"PO: {po.order_number})"
                    ),
                ),
                commit=False,
            )

    def update_status(
        self,
        tenant_id: int,
        return_id: int,
        data: PurchaseOrderReturnStatusUpdate,
        user_id: Optional[int] = None,
    ) -> PurchaseOrderReturn:
        purchase_order_return = self._get_return(
            tenant_id,
            return_id,
        )

        current_status = purchase_order_return.status
        new_status = data.status

        allowed_transitions = {
            "requested": {"approved", "rejected"},
            "approved": {"completed"},
            "rejected": set(),
            "completed": set(),
        }

        if new_status == current_status:
            raise ConflictException(f"Purchase Order Return is already in '{current_status}' status")

        if new_status not in allowed_transitions.get(current_status, set()):
            raise ConflictException(
                f"Cannot change return status from '{current_status}' to '{new_status}'"
            )

        # Enforce inventory synchronization if transitioning to completed
        if new_status == "completed":
            self._process_stock_out(tenant_id, purchase_order_return)
            purchase_order_return.completed_at = datetime.utcnow()
        elif new_status == "approved":
            purchase_order_return.approved_at = datetime.utcnow()
            if user_id:
                purchase_order_return.approved_by_id = user_id
        elif new_status == "rejected":
            purchase_order_return.rejected_at = datetime.utcnow()
            if user_id:
                purchase_order_return.rejected_by_id = user_id

        purchase_order_return.status = new_status
        return self.repo.update(purchase_order_return)

    def approve_return(
        self,
        tenant_id: int,
        return_id: int,
        user_id: Optional[int] = None,
    ) -> PurchaseOrderReturn:
        por = self._get_return(tenant_id, return_id)
        if por.status != "requested":
            raise ConflictException(f"Cannot approve return in '{por.status}' status (must be 'requested')")

        por.status = "approved"
        por.approved_at = datetime.utcnow()
        if user_id:
            por.approved_by_id = user_id

        return self.repo.update(por)

    def reject_return(
        self,
        tenant_id: int,
        return_id: int,
        data: Optional[PurchaseOrderReturnRejectRequest] = None,
        user_id: Optional[int] = None,
    ) -> PurchaseOrderReturn:
        por = self._get_return(tenant_id, return_id)
        if por.status != "requested":
            raise ConflictException(f"Cannot reject return in '{por.status}' status (must be 'requested')")

        por.status = "rejected"
        por.rejected_at = datetime.utcnow()
        if data and data.rejection_reason:
            por.rejection_reason = data.rejection_reason
        if user_id:
            por.rejected_by_id = user_id

        return self.repo.update(por)

    def complete_return(
        self,
        tenant_id: int,
        return_id: int,
    ) -> PurchaseOrderReturn:
        por = self._get_return(tenant_id, return_id)
        if por.status != "approved":
            raise ConflictException(f"Only approved returns can be completed (Current status: '{por.status}')")

        # Execute stock-out deduction
        self._process_stock_out(tenant_id, por)
        por.status = "completed"
        por.completed_at = datetime.utcnow()

        return self.repo.update(por)

    def get_stats(self, tenant_id: int) -> dict:
        """Computes summary statistics and KPIs for vendor returns."""
        total_returns = (
            self.db.query(PurchaseOrderReturn)
            .filter(PurchaseOrderReturn.tenant_id == tenant_id)
            .count()
        )

        requested_count = (
            self.db.query(PurchaseOrderReturn)
            .filter(PurchaseOrderReturn.tenant_id == tenant_id, PurchaseOrderReturn.status == "requested")
            .count()
        )

        approved_count = (
            self.db.query(PurchaseOrderReturn)
            .filter(PurchaseOrderReturn.tenant_id == tenant_id, PurchaseOrderReturn.status == "approved")
            .count()
        )

        completed_count = (
            self.db.query(PurchaseOrderReturn)
            .filter(PurchaseOrderReturn.tenant_id == tenant_id, PurchaseOrderReturn.status == "completed")
            .count()
        )

        rejected_count = (
            self.db.query(PurchaseOrderReturn)
            .filter(PurchaseOrderReturn.tenant_id == tenant_id, PurchaseOrderReturn.status == "rejected")
            .count()
        )

        total_debit_amount = (
            self.db.query(func.coalesce(func.sum(PurchaseOrderReturn.total_amount), Decimal("0.00")))
            .filter(
                PurchaseOrderReturn.tenant_id == tenant_id,
                PurchaseOrderReturn.status.in_({"requested", "approved", "completed"}),
            )
            .scalar()
            or Decimal("0.00")
        )

        # Top return reasons
        reason_rows = (
            self.db.query(
                PurchaseOrderReturn.reason,
                func.count(PurchaseOrderReturn.id).label("count"),
                func.coalesce(func.sum(PurchaseOrderReturn.total_amount), Decimal("0.00")).label("total_amount"),
            )
            .filter(PurchaseOrderReturn.tenant_id == tenant_id)
            .group_by(PurchaseOrderReturn.reason)
            .order_by(func.count(PurchaseOrderReturn.id).desc())
            .limit(5)
            .all()
        )

        top_reasons = [
            {"reason": r[0], "count": r[1], "total_amount": r[2]}
            for r in reason_rows
        ]

        return {
            "total_returns": total_returns,
            "requested_count": requested_count,
            "approved_count": approved_count,
            "completed_count": completed_count,
            "rejected_count": rejected_count,
            "total_debit_amount": total_debit_amount,
            "top_reasons": top_reasons,
        }

    def export_returns(
        self,
        tenant_id: int,
        format: str = "csv",
        purchase_order_id: Optional[int] = None,
        supplier_id: Optional[int] = None,
        status: Optional[str] = None,
        from_date: Optional[date | datetime] = None,
        to_date: Optional[date | datetime] = None,
        search: Optional[str] = None,
    ) -> bytes:
        """Exports filtered purchase order returns to CSV format."""
        returns = self.repo.list_returns(
            tenant_id=tenant_id,
            skip=0,
            limit=5000,
            purchase_order_id=purchase_order_id,
            supplier_id=supplier_id,
            status=status,
            from_date=from_date,
            to_date=to_date,
            search=search,
        )

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Return Number",
            "Debit Note Ref",
            "PO Number",
            "Supplier Name",
            "Facility / Store",
            "Status",
            "Total Amount (INR)",
            "Reason",
            "Created Date",
            "Completed Date",
        ])

        for r in returns:
            po_num = r.purchase_order_number or f"PO #{r.purchase_order_id}"
            supp_name = r.supplier_name or "N/A"
            loc = r.store_name or r.warehouse_name or "Main Facility"
            created_str = r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else ""
            completed_str = r.completed_at.strftime("%Y-%m-%d %H:%M:%S") if r.completed_at else ""

            writer.writerow([
                r.return_number,
                r.debit_note_number or "",
                po_num,
                supp_name,
                loc,
                r.status.upper(),
                f"{r.total_amount:.2f}",
                r.reason,
                created_str,
                completed_str,
            ])

        return output.getvalue().encode("utf-8")

    def generate_csv(self, tenant_id: int, return_id: int) -> bytes:
        """Exports a single Debit Note / Return Slip to CSV format."""
        por = self.get_return(tenant_id, return_id)
        po = por.purchase_order
        supplier_name = por.supplier_name or (po.supplier.name if po and getattr(po, "supplier", None) else "N/A")

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["DEBIT NOTE / VENDOR RETURN SLIP"])
        writer.writerow(["Return Number", por.return_number])
        writer.writerow(["Debit Note Ref", por.debit_note_number or por.return_number])
        writer.writerow(["PO Number", po.order_number if po else f"PO #{por.purchase_order_id}"])
        writer.writerow(["Supplier", supplier_name])
        writer.writerow(["Status", por.status.upper()])
        writer.writerow(["Date", por.created_at.strftime("%Y-%m-%d %H:%M:%S") if por.created_at else ""])
        writer.writerow([])
        writer.writerow([
            "S.No",
            "Product Name",
            "SKU",
            "Batch Number",
            "Reason",
            "Quantity",
            "Unit Price (INR)",
            "Total Amount (INR)",
        ])

        for idx, item in enumerate(por.items, 1):
            p_name = item.product_name or f"Product #{item.product_id}"
            sku = item.product_sku or ""
            batch = item.batch_number or "-"
            reason = item.item_reason or por.reason
            writer.writerow([
                idx,
                p_name,
                sku,
                batch,
                reason,
                item.quantity,
                f"{item.unit_price:.2f}",
                f"{item.total:.2f}",
            ])

        writer.writerow([])
        writer.writerow(["Total Amount", "", "", "", "", "", "", f"{por.total_amount:.2f}"])
        return output.getvalue().encode("utf-8")

    def generate_excel(self, tenant_id: int, return_id: int) -> bytes:
        """Exports a single Debit Note / Return Slip to formatted Excel (.xlsx) spreadsheet."""
        from app.services.excel_export_service import ExcelExportService

        por = self.get_return(tenant_id, return_id)

        headers = [
            "S.No",
            "Product Name",
            "SKU",
            "Batch Number",
            "Reason",
            "Quantity",
            "Unit Price (INR)",
            "Total Amount (INR)",
        ]

        rows = []
        for idx, item in enumerate(por.items, 1):
            p_name = item.product_name or f"Product #{item.product_id}"
            sku = item.product_sku or ""
            batch = item.batch_number or "-"
            reason = item.item_reason or por.reason
            rows.append([
                idx,
                p_name,
                sku,
                batch,
                reason,
                item.quantity,
                float(item.unit_price),
                float(item.total),
            ])

        rows.append([
            "Total",
            "",
            "",
            "",
            "",
            sum(it.quantity for it in por.items),
            "",
            float(por.total_amount),
        ])

        sheet_title = f"DN-{por.return_number[-12:]}"
        stream = ExcelExportService().export_to_stream(
            sheet_title=sheet_title,
            headers=headers,
            rows=rows,
            report_type="amber",
        )
        return stream.getvalue()

    def generate_pdf(
        self,
        tenant_id: int,
        return_id: int,
    ) -> bytes:
        """Generates formal A4 Debit Note / Vendor Return Slip PDF."""
        from app.services.document_settings_service import DocumentSettingsService
        from app.services.document_renderer_service import DocumentRenderer

        por = self.get_return(tenant_id, return_id)
        po = por.purchase_order
        supplier = por.supplier or (po.supplier if po else None)
        store_id = por.store_id or (po.store_id if po else None)

        branding = DocumentSettingsService(self.db).resolve_branding(
            tenant_id=tenant_id,
            store_id=store_id,
        )

        items_data = []
        for it in por.items:
            p_name = it.product_name or f"Product #{it.product_id}"
            sku = it.product_sku or ""
            items_data.append({
                "product_id": it.product_id,
                "product_name": p_name,
                "product_sku": sku,
                "batch_number": it.batch_number or "-",
                "item_reason": it.item_reason or por.reason,
                "quantity": it.quantity,
                "unit_price": float(it.unit_price),
                "total": float(it.total),
            })

        data = {
            "id": por.id,
            "return_number": por.return_number,
            "debit_note_number": por.debit_note_number or por.return_number,
            "purchase_order_id": por.purchase_order_id,
            "purchase_order_number": por.purchase_order_number or (po.order_number if po else ""),
            "created_at": por.created_at,
            "status": por.status,
            "reason": por.reason,
            "remarks": por.remarks,
            "total_amount": float(por.total_amount),
            "store_name": por.store_name,
            "warehouse_name": por.warehouse_name,
            "supplier_name": por.supplier_name or (supplier.name if supplier else ""),
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
        return renderer.render("debit_note", data, branding)