from datetime import datetime
from decimal import Decimal

import boto3
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import AppException, NotFoundException
from app.models.credit_note import CreditNote
from app.models.customer import Customer
from app.models.document_sequence import DocumentSequence
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
from app.services.audit_service import AuditService
from app.services.cart_service import CartService
from app.services.inventory_service import InventoryService
from app.services.order_service import OrderService
from app.utils.constants import InvoiceStatus, OrderStatus, PaymentStatus, RefundStatus
from app.utils.gst_engine import calculate_line_tax, resolve_gst_rate
from app.utils.pdf_generator import generate_invoice_pdf
from app.utils.thermal_printer import generate_thermal_payload

settings = get_settings()


class BillingService:
    def __init__(self, db: Session):
        self.db = db

    def _next_document_number(self, tenant_id: int, doc_type: str, prefix: str) -> str:
        year = datetime.utcnow().year
        bind = self.db.get_bind()
        if bind.dialect.name == "mysql":
            self.db.execute(
                text(
                    "INSERT INTO document_sequences (tenant_id, doc_type, year, last_number, created_at, updated_at) "
                    "VALUES (:tenant_id, :doc_type, :year, 0, NOW(), NOW()) "
                    "ON DUPLICATE KEY UPDATE id=id"
                ),
                {"tenant_id": tenant_id, "doc_type": doc_type, "year": year},
            )
            self.db.flush()
        else:
            self.db.execute(
                text(
                    "INSERT OR IGNORE INTO document_sequences (tenant_id, doc_type, year, last_number, created_at, updated_at) "
                    "VALUES (:tenant_id, :doc_type, :year, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ),
                {"tenant_id": tenant_id, "doc_type": doc_type, "year": year},
            )
            self.db.flush()

        row = (
            self.db.query(DocumentSequence)
            .filter(
                DocumentSequence.tenant_id == tenant_id,
                DocumentSequence.doc_type == doc_type,
                DocumentSequence.year == year,
            )
            .with_for_update()
            .first()
        )
        if not row:
            row = DocumentSequence(
                tenant_id=tenant_id,
                doc_type=doc_type,
                year=year,
                last_number=0,
            )
            self.db.add(row)
            self.db.flush()

        while True:
            row.last_number += 1
            num = f"{prefix}-{year}-{row.last_number:06d}"
            if doc_type == "credit_note":
                from app.models.credit_note import CreditNote
                if self.db.query(CreditNote).filter(CreditNote.credit_note_no == num).first():
                    continue
            elif doc_type == "invoice":
                if self.db.query(Invoice).filter(Invoice.invoice_number == num).first():
                    continue
            self.db.flush()
            return num

    def _generate_invoice_number(self, tenant_id: int) -> str:
        return self._next_document_number(tenant_id, "invoice", "INV")

    def _generate_credit_note_number(self, tenant_id: int) -> str:
        return self._next_document_number(tenant_id, "credit_note", "CN")

    def _credit_note_gst_breakdown(
        self, invoice: Invoice, refund_amount: Decimal
    ) -> dict[str, Decimal]:
        if invoice.total_amount <= 0:
            return {
                "cgst_amount": Decimal("0.00"),
                "sgst_amount": Decimal("0.00"),
                "igst_amount": Decimal("0.00"),
            }

        ratio = refund_amount / invoice.total_amount

        return {
            "cgst_amount": (invoice.cgst_amount * ratio).quantize(Decimal("0.01")),
            "sgst_amount": (invoice.sgst_amount * ratio).quantize(Decimal("0.01")),
            "igst_amount": (invoice.igst_amount * ratio).quantize(Decimal("0.01")),
        }

    def _gst_dict_serializable(self, gst: dict) -> dict:
        return {k: str(v) for k, v in gst.items()}

    def _invoice_pdf_items(self, invoice: Invoice) -> list[dict]:
        items = []

        for item in invoice.items or []:
            product = (
                self.db.query(Product)
                .filter(Product.id == item.product_id)
                .first()
            )

            items.append(
                {
                    "product_name": product.name if product else "Item",
                    "hsn_code": product.hsn_code if product else "",
                    "quantity": item.quantity,
                    "unit_price": item.unit_price,
                    "discount_amount": item.discount_amount,
                    "gst_rate": item.gst_rate,
                    "gst_amount": item.gst_amount,
                    "total_amount": item.total_amount,
                }
            )

        return items

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

    def create_invoice(
        self, tenant_id: int, order_id: int, same_state: bool = True
    ) -> Invoice:
        order = (
            self.db.query(Order)
            .filter(
                Order.id == order_id,
                Order.tenant_id == tenant_id,
            )
            .first()
        )

        if not order:
            raise NotFoundException("Order not found")

        if order.status not in (
            OrderStatus.CONFIRMED.value,
            OrderStatus.DELIVERED.value,
        ):
            raise AppException(
                "Invoice can only be generated for confirmed orders"
            )

        existing = (
            self.db.query(Invoice)
            .filter(Invoice.order_id == order_id)
            .first()
        )

        if existing:
            return existing

        if same_state:
            half = (order.tax_amount / Decimal("2")).quantize(
                Decimal("0.01")
            )

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
            order_id=order.id,
            invoice_number=self._generate_invoice_number(tenant_id),
            status=InvoiceStatus.ISSUED.value,
            subtotal=order.subtotal,
            discount_amount=order.discount_amount,
            total_amount=order.total_amount,
            tax_breakdown=self._gst_dict_serializable(gst),
            **gst,
        )

        self._create_invoice_items_from_order(
            invoice,
            order,
            same_state,
        )

        self.db.add(invoice)
        self.db.commit()
        self.db.refresh(invoice)

        return invoice

    def create_invoice_from_cart(
        self,
        tenant_id: int,
        user_id: int,
        data: InvoiceCreate,
    ) -> Invoice:
        order_svc = OrderService(self.db)

        if data.items:
            items = []
            for item in data.items:
                unit_price = item.unit_price
                if unit_price is None:
                    prod = (
                        self.db.query(Product)
                        .filter(
                            Product.id == item.product_id,
                            Product.tenant_id == tenant_id,
                        )
                        .first()
                    )
                    if not prod:
                        raise NotFoundException(f"Product ID {item.product_id} not found")
                    unit_price = getattr(prod, "selling_price", None) or getattr(prod, "price", Decimal("0.00"))

                items.append(
                    OrderItemCreate(
                        product_id=item.product_id,
                        quantity=item.quantity,
                        unit_price=unit_price,
                        discount=item.discount or Decimal("0.00"),
                    )
                )

            order = order_svc.create_order(
                tenant_id,
                user_id,
                OrderCreate(
                    store_id=data.store_id,
                    customer_id=data.customer_id,
                    order_type="pos",
                    discount_amount=Decimal("0.00"),
                    coupon_code=None,
                    items=items,
                ),
            )
        else:
            cart_svc = CartService(self.db)
            cart = cart_svc.get_cart(tenant_id, user_id)

            if not cart.get("items"):
                raise AppException("Cart is empty. Provide 'items' in request body or add items to cart.")

            if cart.get("store_id") != data.store_id:
                raise AppException("Cart store does not match request")

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
                    discount_amount=Decimal(
                        cart.get("discount_amount", "0")
                    ),
                    coupon_code=cart.get("coupon_code"),
                    items=items,
                ),
            )

        order = order_svc.confirm_order(
            tenant_id,
            order.id,
        )

        if data.payments:
            total_paid = sum(
                (p.amount for p in data.payments),
                Decimal("0"),
            )

            if total_paid != order.total_amount:
                raise AppException(
                    f"Payment total ({total_paid}) must match order total ({order.total_amount})"
                )

            for payment in data.payments:
                amount_tendered = payment.amount_tendered
                change_due = payment.change_due
                if payment.payment_mode.lower() == "cash" and amount_tendered is not None:
                    if amount_tendered < payment.amount:
                        raise AppException(
                            f"Cash tendered ({amount_tendered}) cannot be less than payable amount ({payment.amount})"
                        )
                    computed_change = (amount_tendered - payment.amount).quantize(Decimal("0.01"))
                    if change_due is not None and change_due != computed_change:
                        raise AppException(
                            f"Provided change_due ({change_due}) does not match calculated change ({computed_change})"
                        )
                    change_due = computed_change

                self.db.add(
                    Payment(
                        tenant_id=tenant_id,
                        order_id=order.id,
                        payment_method=payment.payment_mode,
                        amount=payment.amount,
                        amount_tendered=amount_tendered,
                        change_due=change_due,
                        transaction_id=payment.transaction_reference,
                        status=PaymentStatus.COMPLETED.value,
                    )
                )

            self.db.flush()

        invoice = self.create_invoice(
            tenant_id,
            order.id,
            data.same_state,
        )

        AuditService(self.db).log(
            tenant_id,
            user_id,
            "invoice_created",
            "invoice",
            invoice.id,
            {
                "invoice_number": invoice.invoice_number,
                "order_id": order.id,
                "total_amount": str(invoice.total_amount),
            },
        )

        if not data.items:
            CartService(self.db).clear_cart(
                tenant_id,
                user_id,
            )

        return invoice

    def get_invoice(
        self,
        tenant_id: int,
        invoice_id: int,
    ) -> Invoice:
        invoice = (
            self.db.query(Invoice)
            .filter(
                Invoice.id == invoice_id,
                Invoice.tenant_id == tenant_id,
            )
            .first()
        )

        if not invoice:
            raise NotFoundException("Invoice not found")

        return invoice

    def search_invoices(
        self,
        tenant_id: int,
        invoice_number: str | None = None,
        customer_name: str | None = None,
        mobile: str | None = None,
        gstin: str | None = None,
        payment_status: str | None = None,
        date_from=None,
        date_to=None,
    ) -> list[Invoice]:
        query = self.db.query(Invoice).filter(
            Invoice.tenant_id == tenant_id
        )

        if invoice_number:
            query = query.filter(
                Invoice.invoice_number.ilike(
                    f"%{invoice_number}%"
                )
            )

        if date_from:
            query = query.filter(
                Invoice.created_at >= date_from
            )

        if date_to:
            query = query.filter(
                Invoice.created_at <= date_to
            )

        needs_order = (
            customer_name
            or mobile
            or gstin
            or payment_status
        )

        if needs_order:
            query = query.join(
                Order,
                Invoice.order_id == Order.id,
            )

        if customer_name or mobile or gstin:
            query = query.outerjoin(
                Customer,
                Order.customer_id == Customer.id,
            )

            if customer_name:
                query = query.filter(
                    Customer.name.ilike(
                        f"%{customer_name}%"
                    )
                )

            if mobile:
                query = query.filter(
                    Customer.phone.ilike(
                        f"%{mobile}%"
                    )
                )

            if gstin:
                query = query.filter(
                    Customer.gstin.ilike(
                        f"%{gstin}%"
                    )
                )

        if payment_status:
            if not needs_order:
                query = query.join(
                    Order,
                    Invoice.order_id == Order.id,
                )

            query = query.join(
                Payment,
                Payment.order_id == Order.id,
            )

            query = query.filter(
                Payment.status == payment_status
            )

        return (
            query.distinct()
            .order_by(Invoice.created_at.desc())
            .all()
        )

    def reprint_invoice(
        self,
        tenant_id: int,
        invoice_id: int,
    ) -> dict:
        invoice = self.get_invoice(
            tenant_id,
            invoice_id,
        )

        thermal = self.get_thermal_payload(
            tenant_id,
            invoice_id,
        )

        return {
            "invoice": invoice,
            "print_payload": thermal,
        }

    def get_thermal_payload(
        self,
        tenant_id: int,
        invoice_id: int,
        printer_type: str = "generic",
    ) -> dict:
        invoice = self.get_invoice(
            tenant_id,
            invoice_id,
        )

        order = (
            self.db.query(Order)
            .filter(Order.id == invoice.order_id)
            .first()
        )

        tenant = (
            self.db.query(Tenant)
            .filter(Tenant.id == tenant_id)
            .first()
        )

        store = (
            self.db.query(Store)
            .filter(Store.id == order.store_id)
            .first()
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
            store_name=(
                store.name
                if store
                else (tenant.name if tenant else "Store")
            ),
            items=item_payload,
            subtotal=invoice.subtotal,
            discount=invoice.discount_amount,
            cgst=invoice.cgst_amount,
            sgst=invoice.sgst_amount,
            igst=invoice.igst_amount,
            grand_total=invoice.total_amount,
            payment_modes=[
                p.payment_method
                for p in payments
            ],
            customer_name=(
                customer.name
                if customer
                else None
            ),
            customer_mobile=(
                customer.phone
                if customer
                else None
            ),
            gstin=(
                store.gstin
                if store
                else (
                    tenant.gstin
                    if hasattr(tenant, "gstin")
                    else None
                )
            ),
            printer_type=printer_type,
        )

    def generate_pdf(
        self,
        tenant_id: int,
        invoice_id: int,
        document_type: str = "invoice",
    ) -> bytes:
        invoice = self.get_invoice(
            tenant_id,
            invoice_id,
        )

        order = (
            self.db.query(Order)
            .filter(Order.id == invoice.order_id)
            .first()
        )

        tenant = (
            self.db.query(Tenant)
            .filter(Tenant.id == tenant_id)
            .first()
        )

        store = (
            self.db.query(Store)
            .filter(Store.id == order.store_id)
            .first()
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

        # Use DocumentSettingsService and DocumentRenderer for PDF generation
        from app.services.document_settings_service import DocumentSettingsService
        from app.services.document_renderer_service import DocumentRenderer
        from app.utils.pdf_generator import _build_qr_payload

        store_id = getattr(invoice, "store_id", None) or (store.id if store else None)
        branding = DocumentSettingsService(self.db).resolve_branding(
            tenant_id=tenant.id,
            store_id=store_id,
        )

        qr_data = _build_qr_payload(invoice, store, customer)

        data = {
            "invoice_number": invoice.invoice_number,
            "created_at": invoice.created_at,
            "subtotal": float(invoice.subtotal),
            "discount_amount": float(invoice.discount_amount),
            "cgst_amount": float(invoice.cgst_amount),
            "sgst_amount": float(invoice.sgst_amount),
            "igst_amount": float(invoice.igst_amount),
            "total_amount": float(invoice.total_amount),
            "total": float(invoice.total_amount),
            "qr_data": qr_data,
            "customer": {
                "name": customer.name if customer else "Walk-in Customer",
                "phone": customer.phone if customer else "",
                "address": customer.address if customer else "",
                "gstin": customer.gstin if customer else "",
            } if customer else None,
            "items": self._invoice_pdf_items(invoice),
            "payments": [
                {
                    "method": p.payment_method,
                    "amount": float(p.amount),
                    "transaction_id": p.transaction_id,
                }
                for p in payments
            ],
        }
        renderer = DocumentRenderer()
        pdf_bytes = renderer.render(document_type, data, branding)

        if (
            settings.AWS_S3_BUCKET
            and settings.AWS_ACCESS_KEY_ID
        ):
            self._upload_to_s3(
                invoice,
                pdf_bytes,
            )

        return pdf_bytes

    def generate_credit_note_pdf(
        self,
        tenant_id: int,
        credit_note_id: int,
    ) -> bytes:
        from app.models.credit_note import CreditNote
        from app.services.document_settings_service import DocumentSettingsService
        from app.services.document_renderer_service import DocumentRenderer

        credit_note = (
            self.db.query(CreditNote)
            .filter(CreditNote.id == credit_note_id, CreditNote.tenant_id == tenant_id)
            .first()
        )
        if not credit_note:
            raise NotFoundException("Credit note not found")

        invoice = (
            self.db.query(Invoice)
            .filter(Invoice.id == credit_note.invoice_id, Invoice.tenant_id == tenant_id)
            .first()
        )
        order = (
            self.db.query(Order).filter(Order.id == invoice.order_id).first()
            if invoice
            else None
        )
        store = (
            self.db.query(Store).filter(Store.id == order.store_id).first()
            if order and order.store_id
            else None
        )
        customer = (
            self.db.query(Customer).filter(Customer.id == order.customer_id).first()
            if order and order.customer_id
            else None
        )

        store_id = store.id if store else (getattr(invoice, "store_id", None) if invoice else None)
        branding = DocumentSettingsService(self.db).resolve_branding(
            tenant_id=tenant_id,
            store_id=store_id,
        )

        data = {
            "credit_note_no": credit_note.credit_note_no,
            "invoice_number": invoice.invoice_number if invoice else "",
            "created_at": credit_note.created_at,
            "refund_amount": float(credit_note.refund_amount),
            "cgst_amount": float(credit_note.cgst_amount) if credit_note.cgst_amount else 0.0,
            "sgst_amount": float(credit_note.sgst_amount) if credit_note.sgst_amount else 0.0,
            "igst_amount": float(credit_note.igst_amount) if credit_note.igst_amount else 0.0,
            "reason": getattr(credit_note.refund, "reason", None) or "Returned goods / adjustment",
            "customer": {
                "name": customer.name if customer else "Customer",
                "phone": customer.phone if customer else "",
                "address": customer.address if customer else "",
                "gstin": customer.gstin if customer else "",
            } if customer else None,
        }

        renderer = DocumentRenderer()
        return renderer.render("credit_note", data, branding)

    def _upload_to_s3(
        self,
        invoice: Invoice,
        pdf_bytes: bytes,
    ) -> str:
        s3 = boto3.client(
            "s3",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION,
        )

        key = (
            f"invoices/"
            f"{invoice.tenant_id}/"
            f"{invoice.invoice_number}.pdf"
        )

        s3.put_object(
            Bucket=settings.AWS_S3_BUCKET,
            Key=key,
            Body=pdf_bytes,
            ContentType="application/pdf",
        )

        url = (
            f"https://{settings.AWS_S3_BUCKET}.s3."
            f"{settings.AWS_REGION}.amazonaws.com/{key}"
        )

        invoice.pdf_url = url
        self.db.commit()

        return url

    def process_return(
        self,
        tenant_id: int,
        invoice_id: int,
        product_id: int,
        return_quantity: Decimal,
        reason: str | None = None,
    ) -> dict:
        invoice = self.get_invoice(
            tenant_id,
            invoice_id,
        )

        order = (
            self.db.query(Order)
            .filter(Order.id == invoice.order_id)
            .first()
        )

        if not order:
            raise NotFoundException("Order not found")

        invoice_item = next(
            (
                i
                for i in invoice.items
                if i.product_id == product_id
            ),
            None,
        )

        if not invoice_item:
            raise NotFoundException(
                "Product not found on invoice"
            )

        if return_quantity > invoice_item.quantity:
            raise AppException(
                "Return quantity exceeds invoiced quantity"
            )

        from app.schemas.inventory import StockInRequest

        InventoryService(self.db).stock_in(
            tenant_id,
            StockInRequest(
                store_id=order.store_id,
                product_id=product_id,
                quantity=int(return_quantity),
                notes=(
                    reason
                    or f"Return for invoice "
                    f"{invoice.invoice_number}"
                ),
            ),
        )

        order_item = next(
            (
                i
                for i in order.items
                if i.product_id == product_id
            ),
            None,
        )

        if (
            order_item
            and return_quantity >= order_item.quantity
        ):
            order.status = OrderStatus.RETURNED.value

        self.db.commit()

        return {
            "invoice_id": invoice_id,
            "product_id": product_id,
            "return_quantity": return_quantity,
            "reason": reason,
            "status": "return_processed",
        }

    def create_refund(
        self,
        tenant_id: int,
        invoice_id: int,
        refund_amount: Decimal,
        refund_method: str,
        reason: str | None,
    ) -> Refund:
        invoice = self.get_invoice(
            tenant_id,
            invoice_id,
        )

        if refund_amount <= 0:
            raise AppException(
                "Refund amount must be greater than zero"
            )

        existing_refunds = (
            self.db.query(
                func.coalesce(
                    func.sum(Refund.refund_amount),
                    0,
                )
            )
            .filter(
                Refund.invoice_id == invoice_id,
                Refund.status.in_(
                    [
                        RefundStatus.PENDING.value,
                        RefundStatus.APPROVED.value,
                    ]
                ),
            )
            .scalar()
        )

        if (
            Decimal(str(existing_refunds))
            + refund_amount
            > invoice.total_amount
        ):
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

    def approve_refund(
        self,
        tenant_id: int,
        refund_id: int,
        approved_by_user_id: int,
    ) -> Refund:
        refund = (
            self.db.query(Refund)
            .filter(
                Refund.id == refund_id,
                Refund.tenant_id == tenant_id,
            )
            .first()
        )

        if not refund:
            raise NotFoundException("Refund not found")

        if refund.status != RefundStatus.PENDING.value:
            raise AppException(
                "Only pending refunds can be approved"
            )

        refund.status = RefundStatus.APPROVED.value
        refund.approved_by = approved_by_user_id

        self.db.flush()

        invoice = self.get_invoice(
            tenant_id,
            refund.invoice_id,
        )

        AuditService(self.db).log(
            tenant_id,
            approved_by_user_id,
            "refund_approved",
            "refund",
            refund.id,
            {
                "invoice_id": refund.invoice_id,
                "refund_amount": str(
                    refund.refund_amount
                ),
                "refund_method": refund.refund_method,
            },
        )

        gst = self._credit_note_gst_breakdown(
            invoice,
            refund.refund_amount,
        )

        credit_note = CreditNote(
            tenant_id=tenant_id,
            credit_note_no=self._generate_credit_note_number(
                tenant_id
            ),
            invoice_id=refund.invoice_id,
            refund_id=refund.id,
            refund_amount=refund.refund_amount,
            cgst_amount=gst["cgst_amount"],
            sgst_amount=gst["sgst_amount"],
            igst_amount=gst["igst_amount"],
        )

        self.db.add(credit_note)

        order = (
            self.db.query(Order)
            .filter(Order.id == invoice.order_id)
            .first()
        )

        if order:
            order.status = OrderStatus.REFUNDED.value

        self.db.commit()
        self.db.refresh(refund)

        return refund

    def reject_refund(
        self,
        tenant_id: int,
        refund_id: int,
    ) -> Refund:
        refund = (
            self.db.query(Refund)
            .filter(
                Refund.id == refund_id,
                Refund.tenant_id == tenant_id,
            )
            .first()
        )

        if not refund:
            raise NotFoundException("Refund not found")

        if refund.status != RefundStatus.PENDING.value:
            raise AppException(
                "Only pending refunds can be rejected"
            )

        refund.status = RefundStatus.REJECTED.value

        self.db.commit()
        self.db.refresh(refund)

        return refund

    def create_credit_note(
        self,
        tenant_id: int,
        invoice_id: int,
        refund_amount: Decimal,
        reason: str | None,
        approved_by_user_id: int,
    ) -> CreditNote:
        refund = self.create_refund(
            tenant_id,
            invoice_id,
            refund_amount,
            "cash",
            reason,
        )

        self.approve_refund(
            tenant_id,
            refund.id,
            approved_by_user_id,
        )

        credit_note = (
            self.db.query(CreditNote)
            .filter(
                CreditNote.refund_id == refund.id,
                CreditNote.tenant_id == tenant_id,
            )
            .first()
        )

        if not credit_note:
            raise NotFoundException(
                "Credit note not created"
            )

        return credit_note

    def get_refund(
        self,
        tenant_id: int,
        refund_id: int,
    ) -> Refund:
        refund = (
            self.db.query(Refund)
            .filter(
                Refund.id == refund_id,
                Refund.tenant_id == tenant_id,
            )
            .first()
        )

        if not refund:
            raise NotFoundException("Refund not found")

        return refund

    def list_refunds(
        self,
        tenant_id: int,
        invoice_id: int | None = None,
    ) -> list[Refund]:
        query = self.db.query(Refund).filter(
            Refund.tenant_id == tenant_id
        )

        if invoice_id is not None:
            invoice = (
                self.db.query(Invoice)
                .filter(
                    Invoice.id == invoice_id,
                    Invoice.tenant_id == tenant_id,
                )
                .first()
            )

            if not invoice:
                raise NotFoundException(
                    "Invoice not found"
                )

            query = query.filter(
                Refund.invoice_id == invoice_id
            )

        return (
            query.order_by(
                Refund.created_at.desc()
            )
            .all()
        )

    def list_credit_notes(
        self,
        tenant_id: int,
        invoice_id: int | None = None,
    ) -> list[CreditNote]:
        query = self.db.query(CreditNote).filter(
            CreditNote.tenant_id == tenant_id
        )

        if invoice_id is not None:
            invoice = (
                self.db.query(Invoice)
                .filter(
                    Invoice.id == invoice_id,
                    Invoice.tenant_id == tenant_id,
                )
                .first()
            )

            if not invoice:
                raise NotFoundException(
                    "Invoice not found"
                )

            query = query.filter(
                CreditNote.invoice_id == invoice_id
            )

        return (
            query.order_by(
                CreditNote.created_at.desc()
            )
            .all()
        )

    def get_credit_note(
        self,
        tenant_id: int,
        credit_note_id: int,
    ) -> CreditNote:
        credit_note = (
            self.db.query(CreditNote)
            .filter(
                CreditNote.id == credit_note_id,
                CreditNote.tenant_id == tenant_id,
            )
            .first()
        )

        if not credit_note:
            raise NotFoundException(
                "Credit note not found"
            )

        return credit_note