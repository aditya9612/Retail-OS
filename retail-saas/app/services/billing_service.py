import uuid
from decimal import Decimal

import boto3
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import AppException, NotFoundException
from app.models.credit_note import CreditNote
from app.models.customer import Customer
from app.models.invoice import Invoice
from app.models.order import Order
from app.models.refund import Refund
from app.models.tenant import Tenant
from app.utils.constants import InvoiceStatus, OrderStatus, RefundStatus
from app.utils.pdf_generator import generate_invoice_pdf

settings = get_settings()


class BillingService:
    def __init__(self, db: Session):
        self.db = db

    def _generate_invoice_number(self) -> str:
        return f"INV-{uuid.uuid4().hex[:8].upper()}"

    def _generate_credit_note_number(self) -> str:
        return f"CN-{uuid.uuid4().hex[:8].upper()}"

    def _calculate_gst(self, order: Order, same_state: bool = True) -> dict:
        taxable = order.subtotal - order.discount_amount
        if same_state:
            half_rate = order.tax_amount / Decimal("2")
            return {
                "cgst_amount": half_rate,
                "sgst_amount": half_rate,
                "igst_amount": Decimal("0.00"),
            }
        return {
            "cgst_amount": Decimal("0.00"),
            "sgst_amount": Decimal("0.00"),
            "igst_amount": order.tax_amount,
        }

    def create_invoice(self, tenant_id: int, order_id: int, same_state: bool = True) -> Invoice:
        order = self.db.query(Order).filter(Order.id == order_id, Order.tenant_id == tenant_id).first()
        if not order:
            raise NotFoundException("Order not found")
        if order.status not in (OrderStatus.CONFIRMED.value, OrderStatus.DELIVERED.value):
            raise AppException("Invoice can only be generated for confirmed orders")
        existing = self.db.query(Invoice).filter(Invoice.order_id == order_id).first()
        if existing:
            return existing
        gst = self._calculate_gst(order, same_state)
        invoice = Invoice(
            tenant_id=tenant_id,
            order_id=order_id,
            invoice_number=self._generate_invoice_number(),
            status=InvoiceStatus.ISSUED.value,
            subtotal=order.subtotal,
            discount_amount=order.discount_amount,
            total_amount=order.total_amount,
            tax_breakdown=gst,
            **gst,
        )
        self.db.add(invoice)
        self.db.commit()
        self.db.refresh(invoice)
        return invoice

    def get_invoice(self, tenant_id: int, invoice_id: int) -> Invoice:
        invoice = self.db.query(Invoice).filter(Invoice.id == invoice_id, Invoice.tenant_id == tenant_id).first()
        if not invoice:
            raise NotFoundException("Invoice not found")
        return invoice

    def search_invoices(
        self,
        tenant_id: int,
        invoice_number: str | None = None,
        customer_name: str | None = None,
        mobile: str | None = None,
        date_from=None,
        date_to=None,
    ) -> list[Invoice]:
        query = self.db.query(Invoice).filter(Invoice.tenant_id == tenant_id)
        if invoice_number:
            query = query.filter(Invoice.invoice_number.ilike(f"%{invoice_number}%"))
        if date_from:
            query = query.filter(Invoice.created_at >= date_from)
        if date_to:
            query = query.filter(Invoice.created_at <= date_to)
        if customer_name or mobile:
            query = query.join(Order, Invoice.order_id == Order.id)
            query = query.join(Customer, Order.customer_id == Customer.id)
            if customer_name:
                query = query.filter(Customer.name.ilike(f"%{customer_name}%"))
            if mobile:
                query = query.filter(Customer.phone.ilike(f"%{mobile}%"))
        return query.order_by(Invoice.created_at.desc()).all()

    def reprint_invoice(self, tenant_id: int, invoice_id: int) -> Invoice:
        # Reprint reuses the existing invoice record; no new invoice number is generated.
        return self.get_invoice(tenant_id, invoice_id)

    def generate_pdf(self, tenant_id: int, invoice_id: int) -> bytes:
        invoice = self.get_invoice(tenant_id, invoice_id)
        order = self.db.query(Order).filter(Order.id == invoice.order_id).first()
        tenant = self.db.query(Tenant).filter(Tenant.id == tenant_id).first()
        pdf_bytes = generate_invoice_pdf(order, invoice, tenant.name if tenant else "Store")
        if settings.AWS_S3_BUCKET and settings.AWS_ACCESS_KEY_ID:
            self._upload_to_s3(invoice, pdf_bytes)
        return pdf_bytes

    def _upload_to_s3(self, invoice: Invoice, pdf_bytes: bytes) -> str:
        s3 = boto3.client(
            "s3",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION,
        )
        key = f"invoices/{invoice.tenant_id}/{invoice.invoice_number}.pdf"
        s3.put_object(Bucket=settings.AWS_S3_BUCKET, Key=key, Body=pdf_bytes, ContentType="application/pdf")
        url = f"https://{settings.AWS_S3_BUCKET}.s3.{settings.AWS_REGION}.amazonaws.com/{key}"
        invoice.pdf_url = url
        self.db.commit()
        return url

    def process_return(self, tenant_id: int, order_id: int) -> Order:
        order = self.db.query(Order).filter(Order.id == order_id, Order.tenant_id == tenant_id).first()
        if not order:
            raise NotFoundException("Order not found")
        order.status = OrderStatus.RETURNED.value
        self.db.commit()
        self.db.refresh(order)
        return order

    def create_refund(
        self,
        tenant_id: int,
        invoice_id: int,
        refund_amount: Decimal,
        refund_method: str,
        reason: str | None,
    ) -> Refund:
        invoice = self.get_invoice(tenant_id, invoice_id)
        if refund_amount <= 0:
            raise AppException("Refund amount must be greater than zero")
        if refund_amount > invoice.total_amount:
            raise AppException("Refund amount cannot exceed invoice total")
        refund = Refund(
            tenant_id=tenant_id,
            invoice_id=invoice_id,
            refund_amount=refund_amount,
            refund_method=refund_method,
            status=RefundStatus.PENDING.value,
            reason=reason,
        )
        self.db.add(refund)
        self.db.commit()
        self.db.refresh(refund)
        return refund

    def approve_refund(self, tenant_id: int, refund_id: int, approved_by_user_id: int) -> Refund:
        refund = (
            self.db.query(Refund)
            .filter(Refund.id == refund_id, Refund.tenant_id == tenant_id)
            .first()
        )
        if not refund:
            raise NotFoundException("Refund not found")
        if refund.status != RefundStatus.PENDING.value:
            raise AppException("Only pending refunds can be approved")

        refund.status = RefundStatus.APPROVED.value
        refund.approved_by = approved_by_user_id
        self.db.flush()

        credit_note = CreditNote(
            tenant_id=tenant_id,
            credit_note_no=self._generate_credit_note_number(),
            invoice_id=refund.invoice_id,
            refund_id=refund.id,
            refund_amount=refund.refund_amount,
        )
        self.db.add(credit_note)

        invoice = self.get_invoice(tenant_id, refund.invoice_id)
        order = self.db.query(Order).filter(Order.id == invoice.order_id).first()
        if order:
            order.status = OrderStatus.REFUNDED.value

        self.db.commit()
        self.db.refresh(refund)
        return refund

    def reject_refund(self, tenant_id: int, refund_id: int) -> Refund:
        refund = (
            self.db.query(Refund)
            .filter(Refund.id == refund_id, Refund.tenant_id == tenant_id)
            .first()
        )
        if not refund:
            raise NotFoundException("Refund not found")
        if refund.status != RefundStatus.PENDING.value:
            raise AppException("Only pending refunds can be rejected")
        refund.status = RefundStatus.REJECTED.value
        self.db.commit()
        self.db.refresh(refund)
        return refund

    def get_refund(self, tenant_id: int, refund_id: int) -> Refund:
        refund = (
            self.db.query(Refund)
            .filter(Refund.id == refund_id, Refund.tenant_id == tenant_id)
            .first()
        )
        if not refund:
            raise NotFoundException("Refund not found")
        return refund

    def list_refunds(self, tenant_id: int, invoice_id: int | None = None) -> list[Refund]:
        query = self.db.query(Refund).filter(Refund.tenant_id == tenant_id)
        if invoice_id:
            query = query.filter(Refund.invoice_id == invoice_id)
        return query.order_by(Refund.created_at.desc()).all()

    def list_credit_notes(self, tenant_id: int, invoice_id: int | None = None) -> list[CreditNote]:
        query = self.db.query(CreditNote).filter(CreditNote.tenant_id == tenant_id)
        if invoice_id:
            query = query.filter(CreditNote.invoice_id == invoice_id)
        return query.order_by(CreditNote.created_at.desc()).all()

    def get_credit_note(self, tenant_id: int, credit_note_id: int) -> CreditNote:
        credit_note = (
            self.db.query(CreditNote)
            .filter(CreditNote.id == credit_note_id, CreditNote.tenant_id == tenant_id)
            .first()
        )
        if not credit_note:
            raise NotFoundException("Credit note not found")
        return credit_note