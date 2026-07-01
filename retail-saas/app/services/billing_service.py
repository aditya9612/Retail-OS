"""Billing service — invoice creation, refunds, credit notes, thermal print."""

from datetime import datetime
from decimal import Decimal

import boto3
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import AppException, NotFoundException
from app.models.credit_note import CreditNote
from app.models.customer import Customer
from app.models.invoice import Invoice
from app.models.invoice_item import InvoiceItem
from app.models.order import Order
from app.models.payment import Payment
from app.models.product import Product
from app.models.refund import Refund
from app.models.store import Store
from app.models.tenant import Tenant
from app.schemas.billing import InvoiceCreate
from app.schemas.order import OrderCreate, OrderItemCreate
from app.services.cart_service import CartService
from app.services.order_service import OrderService
from app.utils.constants import InvoiceStatus, OrderStatus, PaymentStatus, RefundStatus
from app.utils.gst_engine import calculate_line_tax, resolve_gst_rate
from app.utils.pdf_generator import generate_invoice_pdf
from app.utils.thermal_printer import generate_thermal_payload

settings = get_settings()


class BillingService:
    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------ helpers
    def _generate_invoice_number(self, tenant_id: int) -> str:
        max_num = (
            self.db.query(func.max(Invoice.id))
            .filter(Invoice.tenant_id == tenant_id)
            .scalar()
        ) or 0
        year = datetime.utcnow().year
        return f"INV-{year}-{max_num + 1:06d}"

    def _generate_credit_note_number(self, tenant_id: int) -> str:
        count = (
            self.db.query(func.count(CreditNote.id))
            .filter(CreditNote.tenant_id == tenant_id)
            .scalar()
        ) or 0
        year = datetime.utcnow().year
        return f"CN-{year}-{count + 1:06d}"

    def _gst_dict_serializable(self, gst: dict) -> dict:
        """Convert Decimal values to str so JSON column doesn't crash."""
        return {k: str(v) for k, v in gst.items()}

    # ---------------------------------------------------------- invoice items
    def _create_invoice_items_from_order(
        self, invoice: Invoice, order: Order, same_state: bool
    ) -> None:
        for order_item in order.items:
            product = (
                self.db.query(Product)
                .filter(Product.id == order_item.product_id)
                .first()
            )
            gst_rate = (
                resolve_gst_rate(self.db, invoice.tenant_id, product)
                if product
                else order_item.tax_rate
            )
            tax = calculate_line_tax(
                Decimal(str(order_item.quantity)),
                order_item.unit_price,
                order_item.discount,
                gst_rate,
                same_state,
            )
            invoice.items.append(
                InvoiceItem(
                    product_id=order_item.product_id,
                    quantity=Decimal(str(order_item.quantity)),
                    unit_price=order_item.unit_price,
                    discount_amount=order_item.discount,
                    gst_rate=gst_rate,
                    gst_amount=tax["gst_amount"],
                    total_amount=tax["total_amount"],
                )
            )

    # ---------------------------------------------------------- create invoice
    def create_invoice(
        self, tenant_id: int, order_id: int, same_state: bool = True
    ) -> Invoice:
        order = (
            self.db.query(Order)
            .filter(Order.id == order_id, Order.tenant_id == tenant_id)
            .first()
        )
        if not order:
            raise NotFoundException("Order not found")
        if order.status not in (
            OrderStatus.CONFIRMED.value,
            OrderStatus.DELIVERED.value,
        ):
            raise AppException("Invoice can only be generated for confirmed orders")

        existing = (
            self.db.query(Invoice).filter(Invoice.order_id == order_id).first()
        )
        if existing:
            return existing

        if same_state:
            half = (order.tax_amount / Decimal("2")).quantize(Decimal("0.01"))
            gst = {
                "cgst_amount": half,
                "sgst_amount": half,
                "igst_amount": Decimal("0.00"),
            }
        else:
            gst = {
                "cgst_amount": Decimal("0.00"),
                "sgst_amount": Decimal("0.00"),
                "igst_amount": order.tax_amount,
            }

        invoice = Invoice(
            tenant_id=tenant_id,
            order_id=order_id,
            invoice_number=self._generate_invoice_number(tenant_id),
            status=InvoiceStatus.ISSUED.value,
            subtotal=order.subtotal,
            discount_amount=order.discount_amount,
            total_amount=order.total_amount,
            tax_breakdown=self._gst_dict_serializable(gst),
            **gst,
        )
        self._create_invoice_items_from_order(invoice, order, same_state)
        self.db.add(invoice)
        self.db.commit()
        self.db.refresh(invoice)
        return invoice

    # ------------------------------------------------- create invoice from cart
    def create_invoice_from_cart(
        self,
        tenant_id: int,
        user_id: int,
        data: InvoiceCreate,
    ) -> Invoice:
        cart_svc = CartService(self.db)
        cart = cart_svc.get_cart(tenant_id, user_id)
        if not cart.get("items"):
            raise AppException("Cart is empty")
        if cart.get("store_id") != data.store_id:
            raise AppException("Cart store does not match request")

        order_svc = OrderService(self.db)
        items = [
            OrderItemCreate(
                product_id=item["product_id"],
                quantity=int(Decimal(item["quantity"])),
                unit_price=Decimal(item["unit_price"]),
                discount=Decimal(item.get("discount", "0")),
            )
            for item in cart["items"]
        ]
        order = order_svc.create_order(
            tenant_id,
            user_id,
            OrderCreate(
                store_id=data.store_id,
                customer_id=data.customer_id or cart.get("customer_id"),
                order_type="pos",
                discount_amount=Decimal(cart.get("discount_amount", "0")),
                coupon_code=cart.get("coupon_code"),
                items=items,
            ),
        )
        order = order_svc.confirm_order(tenant_id, order.id)

        if data.payments:
            total_paid = sum((p.amount for p in data.payments), Decimal("0"))
            if total_paid != order.total_amount:
                raise AppException(
                    "Payment total must match order total for split payments"
                )
            for payment in data.payments:
                self.db.add(
                    Payment(
                        tenant_id=tenant_id,
                        order_id=order.id,
                        payment_method=payment.payment_mode,
                        amount=payment.amount,
                        transaction_id=payment.transaction_reference,
                        status=PaymentStatus.COMPLETED.value,
                    )
                )
            self.db.flush()

        invoice = self.create_invoice(tenant_id, order.id, data.same_state)
        cart_svc.clear_cart(tenant_id, user_id)
        return invoice

    # ------------------------------------------------------------ get invoice
    def get_invoice(self, tenant_id: int, invoice_id: int) -> Invoice:
        invoice = (
            self.db.query(Invoice)
            .filter(Invoice.id == invoice_id, Invoice.tenant_id == tenant_id)
            .first()
        )
        if not invoice:
            raise NotFoundException("Invoice not found")
        return invoice

    # --------------------------------------------------------- search invoices
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
            query = query.filter(
                Invoice.invoice_number.ilike(f"%{invoice_number}%")
            )
        if date_from:
            query = query.filter(Invoice.created_at >= date_from)
        if date_to:
            query = query.filter(Invoice.created_at <= date_to)
        if customer_name or mobile:
            query = query.join(Order, Invoice.order_id == Order.id)
            query = query.join(Customer, Order.customer_id == Customer.id)
            if customer_name:
                query = query.filter(
                    Customer.name.ilike(f"%{customer_name}%")
                )
            if mobile:
                query = query.filter(Customer.phone.ilike(f"%{mobile}%"))
        return query.order_by(Invoice.created_at.desc()).all()

    # --------------------------------------------------------- reprint invoice
    def reprint_invoice(self, tenant_id: int, invoice_id: int) -> dict:
        invoice = self.get_invoice(tenant_id, invoice_id)
        thermal = self.get_thermal_payload(tenant_id, invoice_id)
        return {"invoice": invoice, "print_payload": thermal}

    # ------------------------------------------------------- thermal payload
    def get_thermal_payload(
        self,
        tenant_id: int,
        invoice_id: int,
        printer_type: str = "generic",
    ) -> dict:
        invoice = self.get_invoice(tenant_id, invoice_id)
        order = (
            self.db.query(Order).filter(Order.id == invoice.order_id).first()
        )
        tenant = (
            self.db.query(Tenant).filter(Tenant.id == tenant_id).first()
        )
        store = (
            self.db.query(Store).filter(Store.id == order.store_id).first()
            if order
            else None
        )
        customer = (
            self.db.query(Customer)
            .filter(Customer.id == order.customer_id)
            .first()
            if order and order.customer_id
            else None
        )
        payments = (
            self.db.query(Payment)
            .filter(Payment.order_id == invoice.order_id)
            .all()
        )
        items = invoice.items or []
        item_payload = [
            {
                "product_name": self.db.query(Product.name)
                .filter(Product.id == i.product_id)
                .scalar()
                or "Item",
                "quantity": i.quantity,
                "unit_price": i.unit_price,
                "total_amount": i.total_amount,
            }
            for i in items
        ]
        if not item_payload and order:
            item_payload = [
                {
                    "product_name": i.product_name,
                    "quantity": i.quantity,
                    "unit_price": i.unit_price,
                    "total_amount": i.total,
                }
                for i in order.items
            ]
        return generate_thermal_payload(
            invoice_number=invoice.invoice_number,
            store_name=store.name if store else (tenant.name if tenant else "Store"),
            items=item_payload,
            subtotal=invoice.subtotal,
            discount=invoice.discount_amount,
            cgst=invoice.cgst_amount,
            sgst=invoice.sgst_amount,
            igst=invoice.igst_amount,
            grand_total=invoice.total_amount,
            payment_modes=[p.payment_method for p in payments],
            customer_name=customer.name if customer else None,
            customer_mobile=customer.phone if customer else None,
            gstin=store.gstin if store else (tenant.gstin if hasattr(tenant, "gstin") else None),
            printer_type=printer_type,
        )

    # ---------------------------------------------------------- generate pdf
    def generate_pdf(self, tenant_id: int, invoice_id: int) -> bytes:
        invoice = self.get_invoice(tenant_id, invoice_id)
        order = (
            self.db.query(Order).filter(Order.id == invoice.order_id).first()
        )
        tenant = (
            self.db.query(Tenant).filter(Tenant.id == tenant_id).first()
        )
        pdf_bytes = generate_invoice_pdf(
            order, invoice, tenant.name if tenant else "Store"
        )
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
        s3.put_object(
            Bucket=settings.AWS_S3_BUCKET,
            Key=key,
            Body=pdf_bytes,
            ContentType="application/pdf",
        )
        url = f"https://{settings.AWS_S3_BUCKET}.s3.{settings.AWS_REGION}.amazonaws.com/{key}"
        invoice.pdf_url = url
        self.db.commit()
        return url

    # --------------------------------------------------------- process return
    def process_return(
        self,
        tenant_id: int,
        invoice_id: int,
        product_id: int,
        return_quantity: Decimal,
        reason: str | None = None,
    ) -> dict:
        invoice = self.get_invoice(tenant_id, invoice_id)
        order = (
            self.db.query(Order).filter(Order.id == invoice.order_id).first()
        )
        if not order:
            raise NotFoundException("Order not found")
        invoice_item = next(
            (i for i in invoice.items if i.product_id == product_id), None
        )
        if not invoice_item:
            raise NotFoundException("Product not found on invoice")
        if return_quantity > invoice_item.quantity:
            raise AppException("Return quantity exceeds invoiced quantity")
        order_item = next(
            (i for i in order.items if i.product_id == product_id), None
        )
        if order_item and return_quantity >= order_item.quantity:
            order.status = OrderStatus.RETURNED.value
        self.db.commit()
        return {
            "invoice_id": invoice_id,
            "product_id": product_id,
            "return_quantity": return_quantity,
            "reason": reason,
            "status": "return_processed",
        }

    # --------------------------------------------------------- create refund
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
        existing_refunds = (
            self.db.query(
                func.coalesce(func.sum(Refund.refund_amount), 0)
            )
            .filter(
                Refund.invoice_id == invoice_id,
                Refund.status.in_(
                    [RefundStatus.PENDING.value, RefundStatus.APPROVED.value]
                ),
            )
            .scalar()
        )
        if Decimal(str(existing_refunds)) + refund_amount > invoice.total_amount:
            raise AppException(
                "Cumulative refund amount cannot exceed invoice total"
            )
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

    # -------------------------------------------------------- approve refund
    def approve_refund(
        self, tenant_id: int, refund_id: int, approved_by_user_id: int
    ) -> Refund:
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
            credit_note_no=self._generate_credit_note_number(tenant_id),
            invoice_id=refund.invoice_id,
            refund_id=refund.id,
            refund_amount=refund.refund_amount,
        )
        self.db.add(credit_note)

        invoice = self.get_invoice(tenant_id, refund.invoice_id)
        order = (
            self.db.query(Order).filter(Order.id == invoice.order_id).first()
        )
        if order:
            order.status = OrderStatus.REFUNDED.value

        self.db.commit()
        self.db.refresh(refund)
        return refund

    # --------------------------------------------------------- reject refund
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

    # ---------------------------------------------------- create credit note
    def create_credit_note(
        self,
        tenant_id: int,
        invoice_id: int,
        refund_amount: Decimal,
        reason: str | None,
        approved_by_user_id: int,
    ) -> CreditNote:
        refund = self.create_refund(
            tenant_id, invoice_id, refund_amount, "cash", reason
        )
        self.approve_refund(tenant_id, refund.id, approved_by_user_id)
        credit_note = (
            self.db.query(CreditNote)
            .filter(
                CreditNote.refund_id == refund.id,
                CreditNote.tenant_id == tenant_id,
            )
            .first()
        )
        if not credit_note:
            raise NotFoundException("Credit note not created")
        return credit_note

    # -------------------------------------------------------------- get refund
    def get_refund(self, tenant_id: int, refund_id: int) -> Refund:
        refund = (
            self.db.query(Refund)
            .filter(Refund.id == refund_id, Refund.tenant_id == tenant_id)
            .first()
        )
        if not refund:
            raise NotFoundException("Refund not found")
        return refund

    # ------------------------------------------------------------- list refunds
    def list_refunds(
        self, tenant_id: int, invoice_id: int | None = None
    ) -> list[Refund]:
        query = self.db.query(Refund).filter(Refund.tenant_id == tenant_id)
        if invoice_id:
            query = query.filter(Refund.invoice_id == invoice_id)
        return query.order_by(Refund.created_at.desc()).all()

    # -------------------------------------------------------- list credit notes
    def list_credit_notes(
        self, tenant_id: int, invoice_id: int | None = None
    ) -> list[CreditNote]:
        query = self.db.query(CreditNote).filter(
            CreditNote.tenant_id == tenant_id
        )
        if invoice_id:
            query = query.filter(CreditNote.invoice_id == invoice_id)
        return query.order_by(CreditNote.created_at.desc()).all()

    # --------------------------------------------------------- get credit note
    def get_credit_note(self, tenant_id: int, credit_note_id: int) -> CreditNote:
        credit_note = (
            self.db.query(CreditNote)
            .filter(
                CreditNote.id == credit_note_id,
                CreditNote.tenant_id == tenant_id,
            )
            .first()
        )
        if not credit_note:
            raise NotFoundException("Credit note not found")
        return credit_note