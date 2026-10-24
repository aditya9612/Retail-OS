from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Union
from fastapi.responses import HTMLResponse, JSONResponse, Response
import uuid

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.sale import Sale, SaleItem
from app.models.inventory import Inventory
from app.models.product import Product
from app.models.store import Store
from app.repositories.sale_repo import SaleRepository
from app.schemas.sale import SaleCreate, SaleUpdate, SaleResponse, SaleThermalMode


class SaleService:

    @staticmethod
    def create_sale(
        db: Session,
        data: SaleCreate,
        current_user=None,
    ):
        if not data.items:
            raise ValueError("Sale must contain at least one item")

        store_exists = (
            db.query(Store)
            .filter(Store.id == data.store_id)
            .first()
        )

        if not store_exists:
            raise ValueError(f"Store with id {data.store_id} not found")

        if current_user and getattr(current_user, "tenant_id", None) is not None:
            if store_exists.tenant_id != current_user.tenant_id:
                raise ValueError("Store does not belong to the user's tenant")
            tenant_id = current_user.tenant_id
        else:
            if not store_exists.tenant_id:
                raise ValueError(f"Store with id {data.store_id} is not associated with any tenant")
            tenant_id = store_exists.tenant_id

        if data.customer_id is not None:
            from app.models.customer import Customer
            customer = (
                db.query(Customer)
                .filter(Customer.id == data.customer_id)
                .first()
            )
            if not customer:
                raise ValueError(f"Customer with id {data.customer_id} not found")
            if customer.tenant_id != tenant_id:
                raise ValueError("Customer does not belong to the user's tenant")

        subtotal = Decimal("0.00")
        total_discount = Decimal("0.00")
        tax_amount = Decimal("0.00")

        sale_items = []

        try:
            for item in data.items:
                qty = item.stock if item.stock is not None else item.quantity
                if qty is None or qty <= 0:
                    raise ValueError(f"Quantity must be greater than 0 for product {item.product_id}")

                product = (
                    db.query(Product)
                    .filter(Product.id == item.product_id)
                    .first()
                )

                if not product:
                    raise ValueError(f"Product {item.product_id} not found")

                if product.tenant_id != tenant_id:
                    raise ValueError(f"Product {item.product_id} does not belong to the user's tenant")

                if not product.is_active:
                    raise ValueError(f"Product {item.product_id} is inactive")

                inventory = (
                    db.query(Inventory)
                    .filter(
                        Inventory.store_id == data.store_id,
                        Inventory.product_id == item.product_id,
                        Inventory.tenant_id == tenant_id
                    )
                    .first()
                )

                if not inventory:
                    raise ValueError(
                        f"Product {item.product_id} is not available in this store inventory"
                    )

                if qty > inventory.quantity:
                    raise ValueError(
                        f"Insufficient stock for product {item.product_id}. Available stock: {inventory.quantity}"
                    )

                unit_price = Decimal(str(item.unit_price)) if (item.unit_price is not None and item.unit_price > 0) else Decimal(str(product.selling_price))
                item_gross = (unit_price * Decimal(str(qty))).quantize(Decimal("0.01"))
                item_discount = Decimal(str(item.discount or 0)).quantize(Decimal("0.01"))

                if item_discount < 0:
                    raise ValueError(f"Discount cannot be negative for product {item.product_id}")

                if item_discount > item_gross:
                    raise ValueError(f"Discount cannot exceed item value for product {item.product_id}")

                taxable_amount = item_gross - item_discount
                gst_rate = Decimal(str(product.gst_rate or 0))
                item_tax = (taxable_amount * gst_rate / Decimal("100")).quantize(Decimal("0.01"))
                item_total = taxable_amount + item_tax

                subtotal += taxable_amount
                total_discount += item_discount
                tax_amount += item_tax

                sale_items.append(
                    SaleItem(
                        product_id=item.product_id,
                        quantity=qty,
                        unit_price=unit_price,
                        tax_rate=gst_rate,
                        tax_amount=item_tax,
                        total_price=item_total
                    )
                )

                inventory.quantity -= qty

            sale_num = getattr(data, "sale_number", None) or getattr(data, "invoice_number", None)
            if sale_num:
                sale_num = str(sale_num).strip()
                existing = db.query(Sale).filter(Sale.sale_number == sale_num, Sale.tenant_id == tenant_id).first()
                if existing:
                    raise ValueError(f"Sale with number '{sale_num}' already exists")
            else:
                sale_num = f"INV-{data.store_id}-{datetime.utcnow().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

            sale = Sale(
                tenant_id=tenant_id,
                store_id=data.store_id,
                sale_number=sale_num,
                subtotal=subtotal,
                tax_amount=tax_amount,
                total_amount=subtotal + tax_amount,
                payment_method=data.payment_method,
                payment_status=getattr(data, "payment_status", "paid") or "paid",
            )

            sale.items = sale_items

            return SaleRepository.create(db, sale)
        except Exception:
            db.rollback()
            raise

    @staticmethod
    def get_sales(
        db: Session,
        tenant_id: int,
        store_id: Optional[int] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        payment_method: Optional[str] = None,
        payment_status: Optional[str] = None,
        search: Optional[str] = None,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
    ):
        if store_id is not None:
            store = db.query(Store).filter(Store.id == store_id, Store.tenant_id == tenant_id).first()
            if not store:
                return []
        return SaleRepository.get_all(
            db,
            tenant_id=tenant_id,
            store_id=store_id,
            start_date=start_date,
            end_date=end_date,
            payment_method=payment_method,
            payment_status=payment_status,
            search=search,
            page=page,
            page_size=page_size,
        )

    @staticmethod
    def get_sale(
        db: Session,
        sale_id: int,
        tenant_id: int
    ):
        sale = SaleRepository.get_by_id(db, sale_id=sale_id, tenant_id=tenant_id)
        if not sale:
            raise ValueError(f"Sale with id {sale_id} not found")
        return sale

    @staticmethod
    def update_sale(
        db: Session,
        sale_id: int,
        data: Union[SaleCreate, SaleUpdate],
        tenant_id: int
    ):
        sale = SaleRepository.get_by_id(db, sale_id=sale_id, tenant_id=tenant_id)
        if not sale:
            raise ValueError(f"Sale with id {sale_id} not found")

        target_store_id = sale.store_id
        if getattr(data, "store_id", None) is not None:
            store_exists = db.query(Store).filter(Store.id == data.store_id).first()
            if not store_exists:
                raise ValueError(f"Store with id {data.store_id} not found")
            if store_exists.tenant_id != tenant_id:
                raise ValueError("Store does not belong to the user's tenant")
            target_store_id = data.store_id

        if getattr(data, "customer_id", None) is not None:
            from app.models.customer import Customer
            customer = db.query(Customer).filter(Customer.id == data.customer_id).first()
            if not customer:
                raise ValueError(f"Customer with id {data.customer_id} not found")
            if customer.tenant_id != tenant_id:
                raise ValueError("Customer does not belong to the user's tenant")

        try:
            if getattr(data, "items", None) is not None:
                if not data.items:
                    raise ValueError("Sale must contain at least one item")

                # Restore previous inventory
                for old_item in sale.items:
                    old_inventory = (
                        db.query(Inventory)
                        .filter(
                            Inventory.store_id == sale.store_id,
                            Inventory.product_id == old_item.product_id,
                            Inventory.tenant_id == tenant_id
                        )
                        .first()
                    )
                    if old_inventory:
                        old_inventory.quantity += old_item.quantity

                sale.items.clear()

                subtotal = Decimal("0.00")
                total_discount = Decimal("0.00")
                tax_amount = Decimal("0.00")

                for item in data.items:
                    qty = item.stock if item.stock is not None else item.quantity
                    if qty is None or qty <= 0:
                        raise ValueError(f"Quantity must be greater than 0 for product {item.product_id}")

                    product = db.query(Product).filter(Product.id == item.product_id).first()
                    if not product:
                        raise ValueError(f"Product {item.product_id} not found")
                    if product.tenant_id != tenant_id:
                        raise ValueError(f"Product {item.product_id} does not belong to the user's tenant")

                    if not product.is_active:
                        raise ValueError(f"Product {item.product_id} is inactive")

                    inventory = (
                        db.query(Inventory)
                        .filter(
                            Inventory.store_id == target_store_id,
                            Inventory.product_id == item.product_id,
                            Inventory.tenant_id == tenant_id
                        )
                        .first()
                    )

                    if not inventory:
                        raise ValueError(f"Product {item.product_id} is not available in this store inventory")

                    if qty > inventory.quantity:
                        raise ValueError(
                            f"Insufficient stock for product {item.product_id}. Available stock: {inventory.quantity}"
                        )

                    unit_price = Decimal(str(item.unit_price)) if (item.unit_price is not None and item.unit_price > 0) else Decimal(str(product.selling_price))
                    item_gross = (unit_price * Decimal(str(qty))).quantize(Decimal("0.01"))
                    item_discount = Decimal(str(item.discount or 0)).quantize(Decimal("0.01"))

                    if item_discount < 0:
                        raise ValueError(f"Discount cannot be negative for product {item.product_id}")

                    if item_discount > item_gross:
                        raise ValueError(f"Discount cannot exceed item value for product {item.product_id}")

                    taxable_amount = item_gross - item_discount
                    gst_rate = Decimal(str(product.gst_rate or 0))
                    item_tax = (taxable_amount * gst_rate / Decimal("100")).quantize(Decimal("0.01"))
                    item_total = taxable_amount + item_tax

                    subtotal += taxable_amount
                    total_discount += item_discount
                    tax_amount += item_tax

                    sale_item = SaleItem(
                        product_id=item.product_id,
                        quantity=qty,
                        unit_price=unit_price,
                        tax_rate=gst_rate,
                        tax_amount=item_tax,
                        total_price=item_total
                    )

                    sale.items.append(sale_item)
                    inventory.quantity -= qty

                sale.subtotal = subtotal
                sale.tax_amount = tax_amount
                sale.total_amount = subtotal + tax_amount

            if target_store_id != sale.store_id:
                sale.store_id = target_store_id
            if getattr(data, "customer_id", None) is not None:
                sale.customer_id = data.customer_id
            if getattr(data, "payment_method", None):
                sale.payment_method = data.payment_method
            if getattr(data, "payment_status", None):
                sale.payment_status = data.payment_status
            elif getattr(data, "status", None):
                sale.payment_status = data.status
            sale.updated_at = datetime.utcnow()

            return SaleRepository.update(db, sale)
        except Exception:
            db.rollback()
            raise

    @staticmethod
    def delete_sale(
        db: Session,
        sale_id: int,
        tenant_id: int
    ):
        sale = SaleRepository.get_by_id(db, sale_id=sale_id, tenant_id=tenant_id)
        if not sale:
            raise ValueError(f"Sale with id {sale_id} not found")

        try:
            for item in sale.items:
                inventory = (
                    db.query(Inventory)
                    .filter(
                        Inventory.store_id == sale.store_id,
                        Inventory.product_id == item.product_id,
                        Inventory.tenant_id == tenant_id
                    )
                    .first()
                )
                if inventory:
                    inventory.quantity += item.quantity
                else:
                    new_inv = Inventory(
                        tenant_id=tenant_id,
                        store_id=sale.store_id,
                        product_id=item.product_id,
                        quantity=item.quantity,
                    )
                    db.add(new_inv)

            SaleRepository.delete(db, sale)

            return {
                "message": "Sale deleted successfully",
                "sale_id": sale_id
            }
        except Exception:
            db.rollback()
            raise

    @staticmethod
    def get_sale_receipt_data(db: Session, sale_id: int, tenant_id: int) -> dict:
        sale = SaleService.get_sale(db, sale_id, tenant_id=tenant_id)
        store = db.query(Store).filter(Store.id == sale.store_id).first()
        store_name = store.name if store else "Retail Store"
        store_address = f"{store.city or ''}, {store.state or ''} {store.pincode or ''}".strip(", ") if store else None

        items_data = []
        for it in (sale.items or []):
            prod = db.query(Product).filter(Product.id == it.product_id).first()
            p_name = prod.name if prod else f"Product #{it.product_id}"
            line_tot = Decimal(str(it.unit_price)) * Decimal(str(it.quantity))
            items_data.append({
                "name": p_name,
                "quantity": it.quantity,
                "unit_price": Decimal(str(it.unit_price)),
                "total_amount": line_tot,
            })

        lines = [
            "=" * 36,
            store_name.center(36),
        ]
        if store_address:
            lines.append(store_address.center(36))
        lines.extend([
            "-" * 36,
            f"Sale #: {sale.sale_number or sale.id}",
            f"Date  : {sale.created_at.strftime('%Y-%m-%d %H:%M:%S') if sale.created_at else ''}",
            "-" * 36,
            f"{'Item':<16} {'Qty':>3} {'Price':>7} {'Total':>7}",
            "-" * 36,
        ])
        for it in items_data:
            lines.append(f"{it['name'][:16]:<16} {it['quantity']:>3} {it['unit_price']:>7.2f} {it['total_amount']:>7.2f}")
        lines.extend([
            "-" * 36,
            f"{'Subtotal:':<22} {Decimal(str(sale.subtotal)):>13.2f}",
            f"{'Tax:':<22} {Decimal(str(sale.tax_amount or 0)):>13.2f}",
            "=" * 36,
            f"{'TOTAL:':<22} INR {Decimal(str(sale.total_amount)):>9.2f}",
            f"Payment Status: {str(sale.payment_status).upper()}",
            f"Payment Method: {str(sale.payment_method).upper()}",
            "=" * 36,
            "Thank you for your purchase!".center(36),
            "=" * 36,
        ])

        formatted_receipt = "\n".join(lines)
        return {
            "sale_id": sale.id,
            "sale_number": sale.sale_number or f"SALE-{sale.id}",
            "store_name": store_name,
            "store_address": store_address,
            "items": items_data,
            "subtotal": Decimal(str(sale.subtotal)),
            "tax_amount": Decimal(str(sale.tax_amount or 0)),
            "total_amount": Decimal(str(sale.total_amount)),
            "payment_status": sale.payment_status,
            "payment_method": sale.payment_method,
            "created_at": sale.created_at,
            "formatted_receipt": formatted_receipt,
            "sale_model": sale,
        }

    @staticmethod
    def _generate_sale_thermal_image(ctx: dict) -> bytes:
        import io
        from PIL import Image, ImageDraw, ImageFont

        width = 576  # Standard 80mm printable width at 203 DPI
        items = ctx.get("items", [])
        est_height = 550 + max(len(items), 1) * 32

        img = Image.new("RGB", (width, est_height), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)

        try:
            font_title = ImageFont.truetype("arialbd.ttf", 22)
            font_head = ImageFont.truetype("arialbd.ttf", 16)
            font_bold = ImageFont.truetype("arialbd.ttf", 14)
            font_regular = ImageFont.truetype("arial.ttf", 13)
            font_small = ImageFont.truetype("arial.ttf", 11)
            font_big = ImageFont.truetype("arialbd.ttf", 18)
        except Exception:
            font_title = font_head = font_bold = font_regular = font_small = font_big = ImageFont.load_default()

        # Outer subtle border
        draw.rectangle([(6, 6), (width - 7, est_height - 7)], outline=(200, 200, 200), width=1)

        y = 20

        # Store Title centered
        store_txt = str(ctx.get("store_name", "RETAIL STORE")).upper()
        bbox = draw.textbbox((0, 0), store_txt, font=font_title)
        draw.text(((width - (bbox[2] - bbox[0])) // 2, y), store_txt, font=font_title, fill=(0, 0, 0))
        y += 28

        if ctx.get("store_address"):
            addr_txt = str(ctx.get("store_address"))[:65]
            abbox = draw.textbbox((0, 0), addr_txt, font=font_small)
            draw.text(((width - (abbox[2] - abbox[0])) // 2, y), addr_txt, font=font_small, fill=(100, 100, 100))
            y += 18

        # Header centered
        rep_txt = "SALES TRANSACTION RECEIPT"
        bbox = draw.textbbox((0, 0), rep_txt, font=font_head)
        draw.text(((width - (bbox[2] - bbox[0])) // 2, y), rep_txt, font=font_head, fill=(22, 101, 52))
        y += 24

        def draw_dashed_line(draw_ctx, cur_y, w):
            for x in range(20, w - 20, 10):
                draw_ctx.line([(x, cur_y), (x + 5, cur_y)], fill=(120, 120, 120), width=1)

        draw_dashed_line(draw, y, width)
        y += 12

        def draw_kv(label: str, val: str, font_l=font_regular, font_r=font_bold, fill_l=(70, 70, 70), fill_r=(0, 0, 0)):
            nonlocal y
            draw.text((24, y), label, font=font_l, fill=fill_l)
            r_bbox = draw.textbbox((0, 0), str(val), font=font_r)
            r_w = r_bbox[2] - r_bbox[0]
            draw.text((width - 24 - r_w, y), str(val), font=font_r, fill=fill_r)
            y += 22

        draw_kv("Sale Number", str(ctx.get("sale_number", "")))
        created_at = ctx.get("created_at")
        dt_str = created_at.strftime("%Y-%m-%d %H:%M") if isinstance(created_at, datetime) else str(created_at or "")
        draw_kv("Date & Time", dt_str)

        y += 4
        draw_dashed_line(draw, y, width)
        y += 10

        # Items Header
        draw.text((24, y), "ITEM", font=font_bold, fill=(50, 50, 50))
        draw.text((260, y), "QTY", font=font_bold, fill=(50, 50, 50))
        draw.text((360, y), "PRICE", font=font_bold, fill=(50, 50, 50))
        tot_hdr = "TOTAL"
        tot_bbox = draw.textbbox((0, 0), tot_hdr, font=font_bold)
        draw.text((width - 24 - (tot_bbox[2] - tot_bbox[0]), y), tot_hdr, font=font_bold, fill=(50, 50, 50))
        y += 20
        draw_dashed_line(draw, y, width)
        y += 10

        for it in items:
            name_txt = str(it.get("name", "Item"))[:22]
            draw.text((24, y), name_txt, font=font_regular, fill=(20, 20, 20))
            draw.text((265, y), str(it.get("quantity", 1)), font=font_regular, fill=(20, 20, 20))
            draw.text((360, y), f"{Decimal(str(it.get('unit_price', 0))):.2f}", font=font_regular, fill=(20, 20, 20))
            t_str = f"{Decimal(str(it.get('total_amount', 0))):.2f}"
            t_bbox = draw.textbbox((0, 0), t_str, font=font_bold)
            draw.text((width - 24 - (t_bbox[2] - t_bbox[0]), y), t_str, font=font_bold, fill=(0, 0, 0))
            y += 22

        y += 4
        draw_dashed_line(draw, y, width)
        y += 12

        draw_kv("Subtotal", f"Rs. {Decimal(str(ctx.get('subtotal', 0))):.2f}")
        if ctx.get("tax_amount") and Decimal(str(ctx.get("tax_amount"))) > 0:
            draw_kv("Tax", f"Rs. {Decimal(str(ctx.get('tax_amount'))):.2f}")

        y += 6

        # Total Box
        tot_box_top = y
        draw.rectangle([(20, tot_box_top), (width - 20, tot_box_top + 42)], fill=(240, 253, 244), outline=(34, 197, 94), width=1)
        draw.text((32, tot_box_top + 10), "TOTAL AMOUNT", font=font_bold, fill=(22, 101, 52))
        amt_str = f"Rs. {Decimal(str(ctx.get('total_amount', 0))):.2f}"
        amt_bbox = draw.textbbox((0, 0), amt_str, font=font_big)
        amt_w = amt_bbox[2] - amt_bbox[0]
        draw.text((width - 32 - amt_w, tot_box_top + 10), amt_str, font=font_big, fill=(22, 101, 52))
        y += 54

        draw_kv("Payment Status", str(ctx.get("payment_status", "PAID")).upper(), fill_r=(22, 101, 52))
        if ctx.get("payment_method"):
            draw_kv("Payment Method", str(ctx.get("payment_method")).upper())

        y += 4
        draw_dashed_line(draw, y, width)
        y += 20

        ty_txt = "Thank you for shopping with us!"
        ty_bbox = draw.textbbox((0, 0), ty_txt, font=font_small)
        draw.text(((width - (ty_bbox[2] - ty_bbox[0])) // 2, y), ty_txt, font=font_small, fill=(100, 100, 100))
        y += 26

        final_height = y + 15
        final_img = img.crop((0, 0, width, final_height))
        draw_final = ImageDraw.Draw(final_img)
        draw_final.rectangle([(6, 6), (width - 7, final_height - 7)], outline=(200, 200, 200), width=1)

        buf = io.BytesIO()
        final_img.save(buf, format="PNG")
        return buf.getvalue()

    @staticmethod
    def _generate_sale_thermal_html(ctx: dict, auto_print: bool = False) -> str:
        created_at = ctx.get("created_at")
        dt_str = created_at.strftime("%Y-%m-%d %H:%M") if isinstance(created_at, datetime) else str(created_at or "")
        items = ctx.get("items", [])
        auto_print_script = "<script>window.onload = function() { window.print(); };</script>" if auto_print else ""

        items_rows = ""
        for it in items:
            items_rows += f'''
            <div class="row">
                <span class="lbl">{it.get("name", "Item")} x{it.get("quantity", 1)}</span>
                <span class="val">Rs. {Decimal(str(it.get("total_amount", 0))):.2f}</span>
            </div>'''

        store_addr_html = f'<div class="store-sub">{ctx["store_address"]}</div>' if ctx.get("store_address") else ""

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Sale Receipt {ctx.get('sale_number')}</title>
<style>
  body {{
    font-family: 'Courier New', Courier, monospace, system-ui;
    background-color: #f3f4f6;
    margin: 0;
    padding: 20px;
    display: flex;
    justify-content: center;
  }}
  .ticket {{
    width: 320px;
    background: #ffffff;
    border: 1px solid #e5e7eb;
    padding: 16px 14px;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    font-size: 13px;
    color: #111827;
    line-height: 1.35;
  }}
  .center {{ text-align: center; }}
  .store-title {{ font-size: 16px; font-weight: bold; text-transform: uppercase; margin-bottom: 2px; }}
  .store-sub {{ font-size: 11px; color: #4b5563; }}
  .doc-title {{
    font-size: 14px;
    font-weight: bold;
    color: #15803d;
    margin: 8px 0 2px 0;
    letter-spacing: 0.5px;
  }}
  .divider {{
    border-top: 1px dashed #9ca3af;
    margin: 8px 0;
  }}
  .row {{
    display: flex;
    justify-content: space-between;
    margin-bottom: 3px;
  }}
  .lbl {{ color: #4b5563; }}
  .val {{ font-weight: 600; text-align: right; }}
  .highlight-box {{
    background: #f0fdf4;
    border: 1px solid #22c55e;
    padding: 8px 10px;
    margin: 8px 0;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }}
  .hl-title {{ font-size: 12px; font-weight: bold; color: #166534; }}
  .hl-val {{ font-size: 16px; font-weight: bold; color: #166534; }}
  @media print {{
    body {{ background: transparent; padding: 0; }}
    .ticket {{ box-shadow: none; border: none; width: 100%; padding: 0; }}
  }}
</style>
{auto_print_script}
</head>
<body>
<div class="ticket">
  <div class="center">
    <div class="store-title">{ctx.get('store_name', 'Retail Store')}</div>
    {store_addr_html}
    <div class="doc-title">SALES RECEIPT</div>
  </div>

  <div class="divider"></div>

  <div class="row"><span class="lbl">Sale Number</span><span class="val">{ctx.get('sale_number')}</span></div>
  <div class="row"><span class="lbl">Date</span><span class="val">{dt_str}</span></div>

  <div class="divider"></div>

  {items_rows}

  <div class="divider"></div>

  <div class="row"><span class="lbl">Subtotal</span><span class="val">Rs. {Decimal(str(ctx.get('subtotal', 0))):.2f}</span></div>
  {f'<div class="row"><span class="lbl">Tax</span><span class="val">Rs. {Decimal(str(ctx.get("tax_amount"))):.2f}</span></div>' if ctx.get("tax_amount") and Decimal(str(ctx.get("tax_amount"))) > 0 else ''}

  <div class="highlight-box">
    <span class="hl-title">TOTAL AMOUNT</span>
    <span class="hl-val">Rs. {Decimal(str(ctx.get('total_amount', 0))):.2f}</span>
  </div>

  <div class="row"><span class="lbl">Status</span><span class="val">{str(ctx.get('payment_status', 'PAID')).upper()}</span></div>
  {f'<div class="row"><span class="lbl">Method</span><span class="val">{str(ctx.get("payment_method")).upper()}</span></div>' if ctx.get("payment_method") else ''}

  <div class="divider"></div>

  <div class="center store-sub" style="margin-top: 10px;">
    Thank you for your purchase!
  </div>
</div>
</body>
</html>"""

    @staticmethod
    def _generate_sale_thermal_pdf(ctx: dict) -> bytes:
        import io
        from PIL import Image
        from reportlab.lib.utils import ImageReader
        from reportlab.pdfgen import canvas

        img_bytes = SaleService._generate_sale_thermal_image(ctx)
        pil_img = Image.open(io.BytesIO(img_bytes))
        img_w, img_h = pil_img.size

        # 80mm roll in points: 80 / 25.4 * 72 = 226.77 points
        page_width = 80.0 / 25.4 * 72.0
        page_height = page_width * (img_h / img_w)

        pdf_buf = io.BytesIO()
        c = canvas.Canvas(pdf_buf, pagesize=(page_width, page_height))
        c.drawImage(ImageReader(io.BytesIO(img_bytes)), 0, 0, width=page_width, height=page_height)
        c.showPage()
        c.save()
        return pdf_buf.getvalue()

    @staticmethod
    def export_sale_thermal(
        db: Session,
        sale_id: int,
        tenant_id: int,
        mode: Any = "preview",
        user: Optional[Any] = None,
    ) -> Response:
        data = SaleService.get_sale_receipt_data(db, sale_id, tenant_id=tenant_id)
        mode_val = str(getattr(mode, "value", mode) or "preview").lower().strip()
        sale_num = data.get("sale_number", f"SALE-{sale_id}")

        # 1. Preview mode (Default) -> Visual 80mm receipt PNG rendered directly in Swagger UI
        if mode_val == SaleThermalMode.preview.value:
            img_bytes = SaleService._generate_sale_thermal_image(data)
            return Response(
                content=img_bytes,
                media_type="image/png",
                headers={
                    "Content-Disposition": f"inline; filename=sale_{sale_num}_thermal.png",
                    "X-Sale-Print-Type": "80mm-PNG-Preview",
                },
            )

        # 2. View mode -> Inline styled HTML page with auto-print dialog
        if mode_val == SaleThermalMode.view.value:
            html_content = SaleService._generate_sale_thermal_html(data, auto_print=True)
            return HTMLResponse(
                content=html_content,
                status_code=200,
                headers={"Content-Disposition": f"inline; filename=sale_{sale_num}_thermal.html"},
            )

        # 3. Download mode -> ESC/POS text file attachment download
        if mode_val == SaleThermalMode.download.value:
            text_payload = data["formatted_receipt"]
            return Response(
                content=text_payload.encode("utf-8"),
                media_type="text/plain; charset=utf-8",
                headers={
                    "Content-Disposition": f"attachment; filename=sale_{sale_num}_thermal.txt",
                    "X-Sale-Print-Type": "ESC/POS",
                },
            )

        # 4. PDF mode -> 80mm Thermal Receipt PDF download
        if mode_val == SaleThermalMode.pdf.value:
            pdf_bytes = SaleService._generate_sale_thermal_pdf(data)
            return Response(
                content=pdf_bytes,
                media_type="application/pdf",
                headers={
                    "Content-Disposition": f"attachment; filename=sale_{sale_num}_thermal.pdf",
                    "X-Sale-Print-Type": "80mm-PDF",
                },
            )

        # 5. HTML mode -> Styled raw HTML layout
        if mode_val == SaleThermalMode.html.value:
            html_content = SaleService._generate_sale_thermal_html(data, auto_print=False)
            return HTMLResponse(
                content=html_content,
                status_code=200,
                headers={"Content-Disposition": f"inline; filename=sale_{sale_num}_thermal.html"},
            )

        # 6. JSON mode -> Structured JSON payload
        if mode_val == SaleThermalMode.json.value:
            return JSONResponse(content=SaleResponse.model_validate(data["sale_model"]).model_dump(mode="json"))

        # 7. Text mode -> Raw ESC/POS text stream
        if mode_val == SaleThermalMode.text.value:
            return Response(
                content=data["formatted_receipt"].encode("utf-8"),
                media_type="text/plain; charset=utf-8",
                headers={
                    "Content-Disposition": f"inline; filename=sale_{sale_num}_thermal.txt",
                    "X-Sale-Print-Type": "ESC/POS",
                },
            )

        raise ValueError(f"Unsupported delivery mode: '{mode_val}'")
