from datetime import datetime

from app.core.exceptions import AppException, NotFoundException
from app.models.grn import GRN, GRNItem
from app.repositories.grn_repo import GRNRepository
from app.schemas.grn import GRNCreate


class GRNService:

    def __init__(self, db):
        self.repo = GRNRepository(db)

    def create(
        self,
        tenant_id: int,
        data: GRNCreate,
    ):
        if data.warehouse_id is not None:
            from app.repositories.warehouse_repo import WarehouseRepository
            warehouse = WarehouseRepository(self.repo.db).get_by_id(
                data.warehouse_id,
                tenant_id,
            )
            if not warehouse:
                raise NotFoundException(
                    f"Warehouse with ID {data.warehouse_id} not found"
                )

        if data.purchase_order_id is not None:
            from app.repositories.purchase_order_repo import PurchaseOrderRepository
            po = PurchaseOrderRepository(self.repo.db).get_by_id(
                data.purchase_order_id,
                tenant_id,
            )
            if not po:
                raise NotFoundException(
                    f"Purchase order with ID {data.purchase_order_id} not found"
                )

            po_items_map = {item.product_id: item for item in po.items}
            for item in data.items:
                if item.product_id not in po_items_map:
                    raise AppException(
                        f"Product ID {item.product_id} does not exist in Purchase Order {po.order_number or po.id}"
                    )
                po_item = po_items_map[item.product_id]
                if item.ordered_quantity > po_item.quantity:
                    raise AppException(
                        f"Ordered quantity ({item.ordered_quantity}) for product ID {item.product_id} cannot exceed Purchase Order quantity ({po_item.quantity})"
                    )
        else:
            from app.models.product import Product
            for item in data.items:
                product = (
                    self.repo.db.query(Product)
                    .filter(
                        Product.id == item.product_id,
                        Product.tenant_id == tenant_id,
                    )
                    .first()
                )
                if not product:
                    raise NotFoundException(
                        f"Product with ID {item.product_id} not found"
                    )

        total_received = sum(item.received_quantity for item in data.items)
        if total_received > 0:
            status = "received"
            received_at = datetime.utcnow()
        else:
            status = "pending"
            received_at = None

        import uuid

        grn_number = (
            f"GRN-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"
        )

        grn = GRN(
            tenant_id=tenant_id,
            purchase_order_id=data.purchase_order_id,
            warehouse_id=data.warehouse_id,
            grn_number=grn_number,
            status=status,
            remarks=data.remarks,
            received_at=received_at,
        )

        for item in data.items:

            grn.items.append(
                GRNItem(
                    product_id=item.product_id,
                    ordered_quantity=item.ordered_quantity,
                    received_quantity=item.received_quantity,
                    remarks=item.remarks,
                )
            )

        return self.repo.create(grn)

    def list(
        self,
        tenant_id: int,
    ):

        return self.repo.list(tenant_id)

    def get(
        self,
        tenant_id: int,
        grn_id: int,
    ):

        grn = self.repo.get_by_id(
            grn_id,
            tenant_id,
        )

        if not grn:
            raise NotFoundException(
                "GRN not found"
            )

        return grn

    def receive(
        self,
        tenant_id: int,
        grn_id: int,
    ):

        grn = self.get(
            tenant_id,
            grn_id,
        )

        grn.status = "received"
        grn.received_at = datetime.utcnow()

        return self.repo.update(grn)

    def reject(
        self,
        tenant_id: int,
        grn_id: int,
    ):

        grn = self.get(
            tenant_id,
            grn_id,
        )

        grn.status = "rejected"

        return self.repo.update(grn)

    def history(
        self,
        tenant_id: int,
        grn_id: int,
    ):
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

    def generate_pdf(
        self,
        tenant_id: int,
        grn_id: int,
    ) -> bytes:
        import io
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        from app.models.product import Product
        from app.models.purchase_order import PurchaseOrder
        from app.models.warehouse import Warehouse
        from app.services.document_settings_service import DocumentSettingsService

        grn = self.get(tenant_id=tenant_id, grn_id=grn_id)

        branding = DocumentSettingsService(self.repo.db).resolve_branding(
            tenant_id=tenant_id,
        )

        warehouse = None
        if grn.warehouse_id:
            warehouse = (
                self.repo.db.query(Warehouse)
                .filter(Warehouse.id == grn.warehouse_id, Warehouse.tenant_id == tenant_id)
                .first()
            )

        po = None
        supplier = None
        if grn.purchase_order_id:
            po = (
                self.repo.db.query(PurchaseOrder)
                .filter(PurchaseOrder.id == grn.purchase_order_id, PurchaseOrder.tenant_id == tenant_id)
                .first()
            )
            if po and po.supplier:
                supplier = po.supplier

        items_data = []
        for item in grn.items:
            product = (
                self.repo.db.query(Product)
                .filter(Product.id == item.product_id, Product.tenant_id == tenant_id)
                .first()
            )
            product_name = product.name if product else f"Product #{item.product_id}"
            sku = product.sku if product and product.sku else "-"
            diff = item.received_quantity - item.ordered_quantity
            if diff == 0:
                diff_status = "Exact"
            elif diff < 0:
                diff_status = f"Short ({abs(diff)})"
            else:
                diff_status = f"Excess (+{diff})"

            items_data.append({
                "product_name": product_name,
                "sku": sku,
                "ordered_quantity": item.ordered_quantity,
                "received_quantity": item.received_quantity,
                "diff_status": diff_status,
                "remarks": item.remarks or "",
            })

        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4, pageCompression=0)
        width, height = A4
        margin = 36.0
        usable_width = width - 2 * margin
        y = height - margin

        primary_color = colors.HexColor("#0F766E")   # Professional Teal
        header_dark = colors.HexColor("#134E4A")
        box_bg = colors.HexColor("#F0FDFA")         # Light teal tint
        border_color = colors.HexColor("#CBD5E1")
        text_dark = colors.HexColor("#0F172A")
        text_muted = colors.HexColor("#64748B")

        # 1. Top Header: Store / Business info
        biz_name = branding.business_name or "Retail Store"
        c.setFont("Helvetica-Bold", 16)
        c.setFillColor(primary_color)
        c.drawString(margin, y, biz_name[:50])
        y -= 16

        c.setFont("Helvetica", 9)
        c.setFillColor(text_dark)
        if branding.address:
            c.drawString(margin, y, branding.address[:75])
            y -= 13

        contact_parts = []
        if branding.phone:
            contact_parts.append(f"Phone: {branding.phone}")
        if branding.email:
            contact_parts.append(f"Email: {branding.email}")
        if contact_parts:
            c.setFont("Helvetica", 8.5)
            c.setFillColor(text_muted)
            c.drawString(margin, y, " | ".join(contact_parts)[:90])
            y -= 13

        if branding.show_gstin and branding.gstin:
            c.setFont("Helvetica-Bold", 8.5)
            c.setFillColor(primary_color)
            c.drawString(margin, y, f"GSTIN: {branding.gstin}")
            y -= 15

        y -= 6

        # 2. Document Title Banner
        banner_h = 24.0
        c.setFillColor(primary_color)
        c.rect(margin, y - banner_h, usable_width, banner_h, fill=1, stroke=0)
        c.setFont("Helvetica-Bold", 12)
        c.setFillColor(colors.white)
        c.drawCentredString(width / 2.0, y - banner_h + 7, "GOODS RECEIPT NOTE (GRN)")
        y -= (banner_h + 12)

        # 3. Metadata Bar (Box)
        meta_h = 44.0
        c.setFillColor(box_bg)
        c.setStrokeColor(border_color)
        c.rect(margin, y - meta_h, usable_width, meta_h, fill=1, stroke=1)

        c.setFillColor(text_dark)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(margin + 10, y - 14, f"GRN No: {grn.grn_number}")

        c.setFont("Helvetica", 8.5)
        created_str = grn.created_at.strftime("%d-%m-%Y %H:%M") if hasattr(grn.created_at, "strftime") else str(grn.created_at)[:16]
        c.drawString(margin + 10, y - 30, f"Created At: {created_str}")

        po_num = po.order_number if po else (f"PO #{grn.purchase_order_id}" if grn.purchase_order_id else "Direct (No PO)")
        c.drawString(margin + 200, y - 14, f"PO Ref: {po_num}")

        recv_str = grn.received_at.strftime("%d-%m-%Y %H:%M") if grn.received_at and hasattr(grn.received_at, "strftime") else (str(grn.received_at)[:16] if grn.received_at else "Pending")
        c.drawString(margin + 200, y - 30, f"Received At: {recv_str}")

        # Status badge
        status_raw = (grn.status or "PENDING").upper()
        if status_raw == "RECEIVED":
            badge_color = colors.HexColor("#15803D")
        elif status_raw == "REJECTED":
            badge_color = colors.HexColor("#DC2626")
        else:
            badge_color = colors.HexColor("#D97706")

        badge_w, badge_h = 80.0, 20.0
        badge_x = width - margin - badge_w - 10
        badge_y = y - 32.0
        c.setFillColor(badge_color)
        c.rect(badge_x, badge_y, badge_w, badge_h, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 8.5)
        c.drawCentredString(badge_x + badge_w / 2.0, badge_y + 6.0, status_raw)

        y -= (meta_h + 12)

        # 4. Warehouse & Supplier Cards
        card_w = (usable_width - 12.0) / 2.0
        card_h = 58.0

        # Warehouse card (left)
        c.setFillColor(colors.HexColor("#FAFAFA"))
        c.setStrokeColor(border_color)
        c.rect(margin, y - card_h, card_w, card_h, fill=1, stroke=1)
        c.setFillColor(header_dark)
        c.setFont("Helvetica-Bold", 8.5)
        c.drawString(margin + 8, y - 14, "RECEIVING WAREHOUSE / LOCATION")
        c.setFillColor(text_dark)
        c.setFont("Helvetica", 8)
        wh_name = f"{warehouse.name} ({warehouse.code})" if warehouse and warehouse.code else (warehouse.name if warehouse else "Main Facility")
        c.drawString(margin + 8, y - 27, wh_name[:36])
        wh_addr = warehouse.address if warehouse and warehouse.address else "Central Warehouse Storage"
        c.drawString(margin + 8, y - 39, wh_addr[:40])
        wh_status = f"Status: {'Active' if not warehouse or warehouse.is_active else 'Inactive'}"
        c.drawString(margin + 8, y - 50, wh_status)

        # Supplier card (right)
        card2_x = margin + card_w + 12.0
        c.setFillColor(colors.HexColor("#FAFAFA"))
        c.setStrokeColor(border_color)
        c.rect(card2_x, y - card_h, card_w, card_h, fill=1, stroke=1)
        c.setFillColor(header_dark)
        c.setFont("Helvetica-Bold", 8.5)
        c.drawString(card2_x + 8, y - 14, "SUPPLIER / VENDOR DETAILS")
        c.setFillColor(text_dark)
        c.setFont("Helvetica", 8)
        supp_name = supplier.name if supplier else "Direct Procurement / Stock-In"
        c.drawString(card2_x + 8, y - 27, supp_name[:36])
        supp_contact = f"Contact: {supplier.contact_person}" if supplier and supplier.contact_person else "-"
        c.drawString(card2_x + 8, y - 39, supp_contact[:40])
        supp_phone = f"Phone: {supplier.phone}" if supplier and supplier.phone else "-"
        c.drawString(card2_x + 8, y - 50, supp_phone[:40])

        y -= (card_h + 14)

        # 5. Items Table
        col_w = [25.0, 210.0, 70.0, 70.0, 148.27]
        th_h = 20.0
        c.setFillColor(primary_color)
        c.rect(margin, y - th_h, usable_width, th_h, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 8.5)

        x_curr = margin
        c.drawString(x_curr + 4, y - 14, "#")
        x_curr += col_w[0]
        c.drawString(x_curr + 4, y - 14, "Product Description & SKU")
        x_curr += col_w[1]
        c.drawRightString(x_curr + col_w[2] - 8, y - 14, "Ordered Qty")
        x_curr += col_w[2]
        c.drawRightString(x_curr + col_w[3] - 8, y - 14, "Received Qty")
        x_curr += col_w[3]
        c.drawString(x_curr + 4, y - 14, "Variance / Remarks")

        y -= th_h

        # Table rows
        row_h = 20.0
        c.setFont("Helvetica", 8)
        for idx, itm in enumerate(items_data):
            bg = colors.white if idx % 2 == 0 else colors.HexColor("#F8FAFC")
            c.setFillColor(bg)
            c.rect(margin, y - row_h, usable_width, row_h, fill=1, stroke=0)

            c.setStrokeColor(colors.HexColor("#E2E8F0"))
            c.setLineWidth(0.5)
            c.line(margin, y - row_h, margin + usable_width, y - row_h)

            c.setFillColor(text_dark)
            x_curr = margin
            c.drawString(x_curr + 6, y - 13, str(idx + 1))
            x_curr += col_w[0]

            item_title = itm["product_name"]
            if itm["sku"] and itm["sku"] != "-":
                item_title += f" ({itm['sku']})"
            c.drawString(x_curr + 4, y - 13, item_title[:45])
            x_curr += col_w[1]

            c.drawRightString(x_curr + col_w[2] - 8, y - 13, str(itm["ordered_quantity"]))
            x_curr += col_w[2]

            c.drawRightString(x_curr + col_w[3] - 8, y - 13, str(itm["received_quantity"]))
            x_curr += col_w[3]

            rem_text = itm["diff_status"]
            if itm["remarks"]:
                rem_text += f" - {itm['remarks']}"
            c.drawString(x_curr + 4, y - 13, rem_text[:30])

            y -= row_h

        # Total summary row
        total_ordered = sum(i["ordered_quantity"] for i in items_data)
        total_received = sum(i["received_quantity"] for i in items_data)

        tot_h = 22.0
        c.setFillColor(colors.HexColor("#F1F5F9"))
        c.rect(margin, y - tot_h, usable_width, tot_h, fill=1, stroke=0)
        c.setStrokeColor(border_color)
        c.line(margin, y - tot_h, margin + usable_width, y - tot_h)

        c.setFillColor(text_dark)
        c.setFont("Helvetica-Bold", 8.5)
        c.drawString(margin + col_w[0] + 4, y - 15, "TOTAL")
        c.drawRightString(margin + col_w[0] + col_w[1] + col_w[2] - 8, y - 15, str(total_ordered))
        c.drawRightString(margin + col_w[0] + col_w[1] + col_w[2] + col_w[3] - 8, y - 15, str(total_received))

        y -= (tot_h + 16)

        # 6. Remarks / Special Instructions Box if any
        if grn.remarks:
            c.setFillColor(box_bg)
            c.setStrokeColor(border_color)
            rem_h = 32.0
            c.rect(margin, y - rem_h, usable_width, rem_h, fill=1, stroke=1)
            c.setFillColor(header_dark)
            c.setFont("Helvetica-Bold", 8)
            c.drawString(margin + 8, y - 12, "GRN NOTES / REMARKS:")
            c.setFillColor(text_dark)
            c.setFont("Helvetica", 8)
            c.drawString(margin + 8, y - 24, grn.remarks[:90])
            y -= (rem_h + 20)
        else:
            y -= 10

        # 7. Signature Blocks
        sig_y = max(y - 20, 90.0)
        sig_col_w = usable_width / 3.0

        c.setStrokeColor(colors.HexColor("#94A3B8"))
        c.setLineWidth(0.8)

        # Line 1: Received By
        c.line(margin + 10, sig_y, margin + sig_col_w - 20, sig_y)
        c.setFont("Helvetica-Bold", 8)
        c.setFillColor(text_dark)
        c.drawCentredString(margin + (sig_col_w / 2.0), sig_y - 12, "STORE IN-CHARGE")
        c.setFont("Helvetica", 7)
        c.setFillColor(text_muted)
        c.drawCentredString(margin + (sig_col_w / 2.0), sig_y - 22, "(Goods Received By)")

        # Line 2: Quality Checked
        c.line(margin + sig_col_w + 10, sig_y, margin + 2 * sig_col_w - 20, sig_y)
        c.setFont("Helvetica-Bold", 8)
        c.setFillColor(text_dark)
        c.drawCentredString(margin + 1.5 * sig_col_w, sig_y - 12, "QUALITY VERIFIED")
        c.setFont("Helvetica", 7)
        c.setFillColor(text_muted)
        c.drawCentredString(margin + 1.5 * sig_col_w, sig_y - 22, "(Inspection & Count Check)")

        # Line 3: Authorized Signatory
        c.line(margin + 2 * sig_col_w + 10, sig_y, margin + 3 * sig_col_w - 10, sig_y)
        c.setFont("Helvetica-Bold", 8)
        c.setFillColor(text_dark)
        c.drawCentredString(margin + 2.5 * sig_col_w, sig_y - 12, "AUTHORIZED SIGNATORY")
        c.setFont("Helvetica", 7)
        c.setFillColor(text_muted)
        c.drawCentredString(margin + 2.5 * sig_col_w, sig_y - 22, f"For {biz_name[:25]}")

        # 8. Bottom Footer
        c.setFont("Helvetica", 7)
        c.setFillColor(text_muted)
        c.drawString(margin, 25.0, "This is a computer-generated Goods Receipt Note (GRN) from Retail-OS.")
        c.drawRightString(width - margin, 25.0, "Page 1 of 1")

        c.save()
        buffer.seek(0)
        return buffer.getvalue()

    def print_grn(
        self,
        tenant_id: int,
        grn_id: int,
    ) -> bytes:
        return self.generate_pdf(
            tenant_id=tenant_id,
            grn_id=grn_id,
        )
