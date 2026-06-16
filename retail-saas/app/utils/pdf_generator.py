import io
from decimal import Decimal
from typing import Any, Dict

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from app.models.invoice import Invoice
from app.models.order import Order


def generate_invoice_pdf(order: Order, invoice: Invoice, tenant_name: str = "Retail Store") -> bytes:
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    y = height - 30 * mm

    c.setFont("Helvetica-Bold", 16)
    c.drawString(30 * mm, y, f"TAX INVOICE - {invoice.invoice_number}")
    y -= 10 * mm
    c.setFont("Helvetica", 10)
    c.drawString(30 * mm, y, tenant_name)
    y -= 6 * mm
    c.drawString(30 * mm, y, f"Order: {order.order_number}")
    y -= 10 * mm

    c.setFont("Helvetica-Bold", 10)
    c.drawString(30 * mm, y, "Item")
    c.drawString(90 * mm, y, "Qty")
    c.drawString(110 * mm, y, "Rate")
    c.drawString(140 * mm, y, "Tax")
    c.drawString(170 * mm, y, "Total")
    y -= 6 * mm
    c.setFont("Helvetica", 9)

    for item in order.items:
        c.drawString(30 * mm, y, item.product_name[:30])
        c.drawString(90 * mm, y, str(item.quantity))
        c.drawString(110 * mm, y, str(item.unit_price))
        c.drawString(140 * mm, y, str(item.tax_amount))
        c.drawString(170 * mm, y, str(item.total))
        y -= 5 * mm

    y -= 10 * mm
    c.drawString(130 * mm, y, f"Subtotal: {invoice.subtotal}")
    y -= 5 * mm
    c.drawString(130 * mm, y, f"CGST: {invoice.cgst_amount}")
    y -= 5 * mm
    c.drawString(130 * mm, y, f"SGST: {invoice.sgst_amount}")
    y -= 5 * mm
    c.drawString(130 * mm, y, f"IGST: {invoice.igst_amount}")
    y -= 5 * mm
    c.setFont("Helvetica-Bold", 11)
    c.drawString(130 * mm, y, f"Total: {invoice.total_amount}")

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer.read()
