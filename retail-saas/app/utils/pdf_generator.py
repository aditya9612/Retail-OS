import io
import json
from datetime import datetime
from decimal import Decimal
from typing import Any

import qrcode
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from app.models.customer import Customer
from app.models.invoice import Invoice
from app.models.order import Order
from app.models.payment import Payment
from app.models.store import Store
from app.models.tenant import Tenant


def _fmt(value: Decimal | float | int | str) -> str:
    return f"{Decimal(str(value)):.2f}"


def _build_qr_payload(
    invoice: Invoice,
    store: Store | None,
    customer: Customer | None,
) -> str:
    payload = {
        "invoice_no": invoice.invoice_number,
        "date": invoice.created_at.strftime("%Y-%m-%d") if invoice.created_at else "",
        "seller_gstin": store.gstin if store and store.gstin else "",
        "buyer_gstin": customer.gstin if customer and customer.gstin else "",
        "total": _fmt(invoice.total_amount),
        "cgst": _fmt(invoice.cgst_amount),
        "sgst": _fmt(invoice.sgst_amount),
        "igst": _fmt(invoice.igst_amount),
    }
    return json.dumps(payload, separators=(",", ":"))


def _qr_image(qr_text: str) -> ImageReader:
    qr = qrcode.QRCode(version=1, box_size=4, border=2)
    qr.add_data(qr_text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return ImageReader(buf)


def generate_invoice_pdf(
    order: Order,
    invoice: Invoice,
    tenant: Tenant,
    store: Store | None = None,
    customer: Customer | None = None,
    items: list[dict[str, Any]] | None = None,
    payments: list[Payment] | None = None,
) -> bytes:
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    y = height - 25 * mm

    store_name = store.name if store else tenant.name
    c.setFont("Helvetica-Bold", 16)
    c.drawString(25 * mm, y, "TAX INVOICE")
    y -= 8 * mm
    c.setFont("Helvetica-Bold", 11)
    c.drawString(25 * mm, y, store_name)
    y -= 5 * mm
    c.setFont("Helvetica", 9)
    if store and store.address:
        c.drawString(25 * mm, y, store.address[:70])
        y -= 4 * mm
    if store and store.gstin:
        c.drawString(25 * mm, y, f"GSTIN: {store.gstin}")
        y -= 4 * mm
    elif tenant.gstin:
        c.drawString(25 * mm, y, f"GSTIN: {tenant.gstin}")
        y -= 4 * mm

    qr_text = _build_qr_payload(invoice, store, customer)
    c.drawImage(_qr_image(qr_text), width - 45 * mm, height - 45 * mm, 35 * mm, 35 * mm)

    y -= 6 * mm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(25 * mm, y, f"Invoice: {invoice.invoice_number}")
    c.drawString(120 * mm, y, f"Date: {invoice.created_at.strftime('%d-%m-%Y') if invoice.created_at else ''}")
    y -= 8 * mm

    c.setFont("Helvetica-Bold", 9)
    c.drawString(25 * mm, y, "Bill To:")
    y -= 5 * mm
    c.setFont("Helvetica", 9)
    if customer:
        c.drawString(25 * mm, y, customer.name)
        y -= 4 * mm
        c.drawString(25 * mm, y, f"Mobile: {customer.phone}")
        y -= 4 * mm
        if customer.gstin:
            c.drawString(25 * mm, y, f"GSTIN: {customer.gstin}")
            y -= 4 * mm
        if customer.address:
            c.drawString(25 * mm, y, customer.address[:70])
            y -= 4 * mm
    else:
        c.drawString(25 * mm, y, "Walk-in Customer")
        y -= 4 * mm

    y -= 6 * mm
    c.setFont("Helvetica-Bold", 8)
    c.drawString(25 * mm, y, "Item")
    c.drawString(75 * mm, y, "HSN")
    c.drawString(95 * mm, y, "Qty")
    c.drawString(108 * mm, y, "Rate")
    c.drawString(125 * mm, y, "Disc")
    c.drawString(140 * mm, y, "GST%")
    c.drawString(155 * mm, y, "Tax")
    c.drawString(175 * mm, y, "Total")
    y -= 5 * mm
    c.setFont("Helvetica", 8)

    line_items = items or []
    if not line_items and order:
        line_items = [
            {
                "product_name": i.product_name,
                "hsn_code": "",
                "quantity": i.quantity,
                "unit_price": i.unit_price,
                "discount_amount": i.discount,
                "gst_rate": i.tax_rate,
                "gst_amount": i.tax_amount,
                "total_amount": i.total,
            }
            for i in order.items
        ]

    for item in line_items:
        if y < 40 * mm:
            c.showPage()
            y = height - 25 * mm
        c.drawString(25 * mm, y, str(item.get("product_name", "Item"))[:28])
        c.drawString(75 * mm, y, str(item.get("hsn_code") or ""))
        c.drawString(95 * mm, y, str(item.get("quantity")))
        c.drawString(108 * mm, y, _fmt(item.get("unit_price", 0)))
        c.drawString(125 * mm, y, _fmt(item.get("discount_amount", 0)))
        c.drawString(140 * mm, y, _fmt(item.get("gst_rate", 0)))
        c.drawString(155 * mm, y, _fmt(item.get("gst_amount", 0)))
        c.drawString(175 * mm, y, _fmt(item.get("total_amount", 0)))
        y -= 4.5 * mm

    y -= 8 * mm
    c.setFont("Helvetica", 9)
    c.drawString(130 * mm, y, f"Subtotal: {_fmt(invoice.subtotal)}")
    y -= 5 * mm
    if invoice.discount_amount > 0:
        c.drawString(130 * mm, y, f"Discount: -{_fmt(invoice.discount_amount)}")
        y -= 5 * mm
    c.drawString(130 * mm, y, f"CGST: {_fmt(invoice.cgst_amount)}")
    y -= 5 * mm
    c.drawString(130 * mm, y, f"SGST: {_fmt(invoice.sgst_amount)}")
    y -= 5 * mm
    c.drawString(130 * mm, y, f"IGST: {_fmt(invoice.igst_amount)}")
    y -= 5 * mm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(130 * mm, y, f"Grand Total: {_fmt(invoice.total_amount)}")
    y -= 8 * mm

    if payments:
        c.setFont("Helvetica-Bold", 9)
        c.drawString(25 * mm, y, "Payment Details:")
        y -= 5 * mm
        c.setFont("Helvetica", 9)
        for payment in payments:
            ref = f" (Ref: {payment.transaction_id})" if payment.transaction_id else ""
            c.drawString(
                25 * mm,
                y,
                f"{payment.payment_method.upper()}: {_fmt(payment.amount)}{ref}",
            )
            y -= 4 * mm

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer.read()


def generate_saas_invoice_pdf(
    invoice: Any,
    tenant: Tenant,
    plan: Any = None,
) -> bytes:
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    y = height - 25 * mm

    # Title & Header
    c.setFont("Helvetica-Bold", 16)
    c.drawString(25 * mm, y, "TAX INVOICE - SAAS SUBSCRIPTION")
    y -= 8 * mm

    # Provider / Seller details
    c.setFont("Helvetica-Bold", 11)
    c.drawString(25 * mm, y, "RetailOS Technologies Private Limited")
    y -= 5 * mm
    c.setFont("Helvetica", 9)
    c.drawString(25 * mm, y, "Cloud Retail & POS Solutions | support@retailos.in")
    y -= 4 * mm
    c.drawString(25 * mm, y, "GSTIN: 27AABCR1234F1Z5 | PAN: AABCR1234F")
    y -= 4 * mm
    c.drawString(25 * mm, y, "SAC Code: 998313 (Information Technology Software Services)")
    y -= 6 * mm

    # Draw QR code
    tenant_title = tenant.name if tenant else "RetailOS"
    qr_data = f"INV:{invoice.invoice_number}|TENANT:{tenant_title}|AMT:{_fmt(invoice.total_amount)}|SAC:998313"
    c.drawImage(_qr_image(qr_data), width - 50 * mm, height - 48 * mm, 32 * mm, 32 * mm)

    # Invoice metadata
    c.setFont("Helvetica-Bold", 10)
    c.drawString(25 * mm, y, f"Invoice No: {invoice.invoice_number}")
    c.drawString(110 * mm, y, f"Date: {invoice.created_at.strftime('%d-%m-%Y') if invoice.created_at else ''}")
    y -= 5 * mm
    reason_label = getattr(invoice, "billing_reason", "subscription_cycle").replace("_", " ").title()
    c.drawString(25 * mm, y, f"Billing Reason: {reason_label}")
    c.drawString(110 * mm, y, f"Status: {invoice.status.upper()}")
    y -= 5 * mm
    due_str = invoice.due_date.strftime('%d-%m-%Y') if getattr(invoice, "due_date", None) else ''
    c.drawString(110 * mm, y, f"Due Date: {due_str}")
    y -= 8 * mm

    # Bill To (Subscriber / Tenant)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(25 * mm, y, "Billed To (Subscriber):")
    y -= 5 * mm
    c.setFont("Helvetica", 9)
    c.drawString(25 * mm, y, f"Tenant Name: {tenant_title}")
    y -= 4 * mm
    if tenant and getattr(tenant, "gstin", None):
        c.drawString(25 * mm, y, f"GSTIN: {tenant.gstin}")
        y -= 4 * mm
    else:
        c.drawString(25 * mm, y, "GSTIN: Unregistered / Consumer")
        y -= 4 * mm
    if tenant and getattr(tenant, "email", None):
        c.drawString(25 * mm, y, f"Email: {tenant.email}")
        y -= 4 * mm

    # Table Header
    y -= 8 * mm
    c.setFont("Helvetica-Bold", 9)
    c.drawString(25 * mm, y, "Description / Plan")
    c.drawString(100 * mm, y, "SAC")
    c.drawString(120 * mm, y, "Interval")
    c.drawString(145 * mm, y, "Rate (INR)")
    c.drawString(175 * mm, y, "Total (INR)")
    y -= 3 * mm
    c.setLineWidth(0.5)
    c.line(25 * mm, y, width - 25 * mm, y)
    y -= 5 * mm

    # Line Item
    c.setFont("Helvetica", 9)
    plan_name = getattr(plan, "name", "Subscription Plan") if plan else "Subscription Plan"
    billing_int = getattr(plan, "billing_interval", "Monthly") if plan else "Monthly"
    c.drawString(25 * mm, y, f"RetailOS SaaS - {plan_name}")
    c.drawString(100 * mm, y, "998313")
    c.drawString(120 * mm, y, str(billing_int).capitalize())
    c.drawString(145 * mm, y, _fmt(invoice.subtotal))
    c.drawString(175 * mm, y, _fmt(invoice.subtotal))
    y -= 6 * mm
    c.line(25 * mm, y, width - 25 * mm, y)
    y -= 6 * mm

    # Totals & Tax Summary
    c.setFont("Helvetica", 9)
    c.drawString(125 * mm, y, f"Subtotal (Taxable): INR {_fmt(invoice.subtotal)}")
    y -= 5 * mm
    if getattr(invoice, "tax_amount", 0) and invoice.tax_amount > 0:
        half_tax = (invoice.tax_amount / 2).quantize(Decimal("0.01"))
        c.drawString(125 * mm, y, f"CGST (9.0%): INR {_fmt(half_tax)}")
        y -= 5 * mm
        c.drawString(125 * mm, y, f"SGST (9.0%): INR {_fmt(half_tax)}")
        y -= 5 * mm
    else:
        c.drawString(125 * mm, y, "GST (18%): INR 0.00 (Inclusive/Nil)")
        y -= 5 * mm

    c.setFont("Helvetica-Bold", 11)
    c.drawString(125 * mm, y, f"Grand Total: INR {_fmt(invoice.total_amount)}")
    y -= 10 * mm

    # Footer note
    c.setFont("Helvetica-Oblique", 8)
    c.drawString(25 * mm, y, "Note: This is a computer-generated tax invoice for B2B SaaS software services. No signature required.")
    if getattr(invoice, "paid_at", None):
        y -= 4 * mm
        c.drawString(25 * mm, y, f"Payment Confirmed: Paid at {invoice.paid_at.strftime('%d-%m-%Y %H:%M:%S UTC')}")

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer.read()
