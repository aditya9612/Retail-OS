import html
import io
from datetime import datetime
from decimal import Decimal
import logging
import threading
from typing import Any, Dict, List, Optional
from fastapi.responses import HTMLResponse, JSONResponse, Response

import boto3
from sqlalchemy import func, text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.core.config import get_settings
from app.core.exceptions import AppException, ForbiddenException, NotFoundException
from app.core.security import is_tenant_wide_authorized
from app.models.credit_note import CreditNote
from app.models.customer import Customer
from app.models.document_sequence import DocumentSequence
from app.models.invoice import Invoice
from app.models.invoice_item import InvoiceItem
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.payment import Payment
from app.models.product import Product
from app.models.invoice_item_return import InvoiceItemReturn
from app.models.inventory import StockMovement
from app.models.order_item_batch_allocation import OrderItemBatchAllocation
from app.models.refund import Refund
from app.models.store import Store
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.billing import (
    CreditNoteThermalMode,
    CreditNoteThermalResponse,
    InvoiceCreate,
    InvoiceThermalMode,
    InvoiceThermalResponse,
    RefundThermalMode,
    RefundReceiptPdfMode,
    RefundThermalResponse,
)
from app.schemas.order import OrderCreate, OrderItemCreate
from app.services.audit_service import AuditService
from app.services.batch_allocation_service import BatchAllocationService
from app.services.cart_service import CartService
from app.services.inventory_service import InventoryService
from app.services.order_service import OrderService
from app.utils.constants import InvoiceStatus, OrderStatus, PaymentStatus, RefundStatus, StockMovementType
from app.utils.gst_engine import calculate_line_tax, resolve_gst_rate
from app.utils.pdf_generator import generate_invoice_pdf
from app.utils.thermal_printer import generate_thermal_payload

settings = get_settings()

_refund_mutex = threading.Lock()
_return_mutex = threading.Lock()


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
                if (
                    self.db.query(Invoice)
                    .filter(
                        Invoice.tenant_id == tenant_id,
                        Invoice.invoice_number == num,
                    )
                    .first()
                ):
                    continue
            self.db.flush()
            return num

    def _generate_invoice_number(self, tenant_id: int, store_id: Optional[int] = None) -> str:
        from app.services.document_number_service import DocumentNumberService
        return DocumentNumberService(self.db).generate_invoice_number(
            tenant_id=tenant_id, store_id=store_id
        )

    def _generate_credit_note_number(self, tenant_id: int, store_id: Optional[int] = None) -> str:
        from app.services.document_number_service import DocumentNumberService
        return DocumentNumberService(self.db).generate_credit_note_number(
            tenant_id=tenant_id, store_id=store_id
        )

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

    def _invoice_pdf_items(self, invoice: Invoice, order: Optional[Order] = None) -> list[dict]:
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

        if not items and order and getattr(order, "items", None):
            for oi in order.items:
                product = (
                    self.db.query(Product)
                    .filter(Product.id == oi.product_id)
                    .first()
                )
                items.append(
                    {
                        "product_name": product.name if product else "Item",
                        "hsn_code": product.hsn_code if product else "",
                        "quantity": oi.quantity,
                        "unit_price": oi.unit_price,
                        "discount_amount": getattr(oi, "discount_amount", 0.0),
                        "gst_rate": getattr(oi, "tax_rate", 0.0),
                        "gst_amount": getattr(oi, "tax_amount", 0.0),
                        "total_amount": getattr(oi, "total_amount", oi.unit_price * oi.quantity),
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
        self,
        tenant_id: int,
        order_id: int,
        same_state: bool = True,
        commit: bool = True,
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
            if not existing.pdf_url:
                existing.pdf_url = f"/api/v1/invoices/{existing.id}/pdf"
            return existing

        from decimal import ROUND_HALF_UP

        if same_state:
            cgst_half = (order.tax_amount / Decimal("2")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            sgst_half = order.tax_amount - cgst_half

            gst = {
                "cgst_amount": cgst_half,
                "sgst_amount": sgst_half,
                "igst_amount": Decimal("0.00"),
            }
        else:
            gst = {
                "cgst_amount": Decimal("0.00"),
                "sgst_amount": Decimal("0.00"),
                "igst_amount": order.tax_amount,
            }

        initial_status = InvoiceStatus.ISSUED.value
        if getattr(order, "payment_status", None) == "paid":
            initial_status = "paid"

        invoice_number = self._generate_invoice_number(tenant_id, store_id=order.store_id)

        invoice = Invoice(
            tenant_id=tenant_id,
            store_id=order.store_id,
            order_id=order.id,
            invoice_number=invoice_number,
            status=initial_status,
            subtotal=order.subtotal,
            discount_amount=order.discount_amount,
            total_amount=order.total_amount,
            tax_breakdown=self._gst_dict_serializable(gst),
            **gst,
        )
        invoice._same_state = same_state

        self._create_invoice_items_from_order(
            invoice,
            order,
            same_state,
        )

        self.db.add(invoice)
        self.db.flush()
        if not invoice.pdf_url:
            invoice.pdf_url = f"/api/v1/invoices/{invoice.id}/pdf"
        if commit:
            self.db.commit()
            self.db.refresh(invoice)

        return invoice

    def create_invoice_from_cart(
        self,
        tenant_id: int,
        user_id: int,
        data: InvoiceCreate,
        user: Optional[User] = None,
    ) -> Invoice:
        if user is None:
            user = (
                self.db.query(User)
                .filter(User.id == user_id, User.tenant_id == tenant_id)
                .first()
            )

        if not user:
            raise ForbiddenException("Access denied: user context required")

        if user.store_id is not None and data.store_id != user.store_id:
            raise ForbiddenException("Access denied: cannot create invoice for another store")

        if user.store_id is None:
            if not is_tenant_wide_authorized(user, self.db):
                raise ForbiddenException("Access denied: user has no assigned store")
            store = (
                self.db.query(Store)
                .filter(
                    Store.id == data.store_id,
                    Store.tenant_id == tenant_id,
                    Store.is_active.is_(True),
                )
                .first()
            )
            if not store:
                raise NotFoundException(f"Store {data.store_id} not found")

        # Step 0: Check idempotency key if provided
        idempotency_key = getattr(data, "idempotency_key", None)
        redis_client = None
        if idempotency_key:
            try:
                from app.core.redis_client import get_redis
                redis_client = get_redis()
                if redis_client:
                    cached_inv_id = redis_client.get(f"idempotency:invoice:{tenant_id}:{idempotency_key}")
                    if cached_inv_id:
                        if isinstance(cached_inv_id, bytes):
                            cached_inv_id = cached_inv_id.decode("utf-8")
                        existing = (
                            self.db.query(Invoice)
                            .filter(Invoice.id == int(cached_inv_id), Invoice.tenant_id == tenant_id)
                            .first()
                        )
                        if existing:
                            return existing
            except Exception:
                pass

        effective_shift_id = getattr(data, "shift_id", None)
        if not effective_shift_id and user:
            try:
                from app.models.pos_shift import POSShift
                active_shift = (
                    self.db.query(POSShift)
                    .filter(
                        POSShift.tenant_id == tenant_id,
                        POSShift.cashier_id == user.id,
                        POSShift.status == "open",
                    )
                    .first()
                )
                if active_shift:
                    effective_shift_id = active_shift.id
            except Exception:
                effective_shift_id = None

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

            order_create_payload = OrderCreate(
                store_id=data.store_id,
                customer_id=data.customer_id,
                order_type="pos",
                discount_amount=Decimal("0.00"),
                coupon_code=None,
                same_state=data.same_state,
                items=items,
            )
            is_cart_checkout = False
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

            order_create_payload = OrderCreate(
                store_id=data.store_id,
                customer_id=data.customer_id or cart.get("customer_id"),
                order_type="pos",
                discount_amount=Decimal(cart.get("discount_amount", "0")),
                coupon_code=cart.get("coupon_code"),
                same_state=data.same_state,
                items=items,
            )
            is_cart_checkout = True

        try:
            # Step 1: Create draft order with commit=False (calculates line taxes & totals)
            order = order_svc.create_order(
                tenant_id,
                user_id,
                order_create_payload,
                commit=False,
            )

            # Step 2: Validate payment tender BEFORE irreversible inventory mutations!
            payment_records: list[Payment] = []
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

                    payment_records.append(
                        Payment(
                            tenant_id=tenant_id,
                            order_id=order.id,
                            customer_id=order.customer_id,
                            payment_method=payment.payment_mode,
                            amount=payment.amount,
                            amount_tendered=amount_tendered,
                            change_due=change_due,
                            transaction_id=payment.transaction_reference,
                            status=PaymentStatus.COMPLETED.value,
                            paid_at=datetime.utcnow(),
                        )
                    )

            # Step 3: Confirm order (allocates batches & deducts inventory) with commit=False
            order = order_svc.confirm_order(
                tenant_id,
                order.id,
                commit=False,
            )

            # Step 4: Create invoice with commit=False
            invoice = self.create_invoice(
                tenant_id,
                order.id,
                data.same_state,
                commit=False,
            )

            # Step 5: Update invoice status and link payments to invoice
            if data.payments:
                invoice.status = "paid"
                for p_rec in payment_records:
                    p_rec.invoice_id = invoice.id
                    self.db.add(p_rec)
                    if p_rec.payment_method and p_rec.payment_method.lower() in ("credit", "khata", "customer_credit"):
                        if not order.customer_id:
                            raise AppException("Customer must be selected for credit purchases")
                        from app.services.customer_service import CustomerService
                        CustomerService(self.db).record_credit_purchase(
                            tenant_id=tenant_id,
                            customer_id=order.customer_id,
                            amount=p_rec.amount,
                            invoice_number=invoice.invoice_number,
                            commit=False,
                        )
                self.db.flush()

            # Step 6: Audit log
            audit_meta = {
                "invoice_number": invoice.invoice_number,
                "order_id": order.id,
                "total_amount": str(invoice.total_amount),
            }
            if effective_shift_id:
                audit_meta["shift_id"] = effective_shift_id
            if idempotency_key:
                audit_meta["idempotency_key"] = idempotency_key

            AuditService(self.db).log(
                tenant_id,
                user_id,
                "invoice_created",
                "invoice",
                invoice.id,
                audit_meta,
            )

            # Step 7: Clear cart if cart checkout
            if is_cart_checkout:
                CartService(self.db).clear_cart(
                    tenant_id,
                    user_id,
                )

            # Step 8: Single, atomic commit of all changes
            self.db.commit()
            self.db.refresh(invoice)

            if idempotency_key and redis_client:
                try:
                    redis_client.setex(f"idempotency:invoice:{tenant_id}:{idempotency_key}", 86400, str(invoice.id))
                except Exception:
                    pass

            return invoice

        except Exception:
            self.db.rollback()
            raise

    def get_invoice(
        self,
        tenant_id: int,
        invoice_id: int,
        user: Optional[User] = None,
        system_context: bool = False,
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

        if not invoice.pdf_url:
            invoice.pdf_url = f"/api/v1/invoices/{invoice.id}/pdf"

        if not system_context:
            if user is None:
                raise ForbiddenException("Access denied: user context required")

            if user.store_id is not None:
                if invoice.store_id is None or invoice.store_id != user.store_id:
                    raise ForbiddenException("Access denied: invoice belongs to another store")
            elif not is_tenant_wide_authorized(user, self.db):
                raise ForbiddenException("Access denied: user has no assigned store")

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
        store_id: int | None = None,
        user: Optional[User] = None,
        system_context: bool = False,
        page: int = 1,
        page_size: int = 50,
    ) -> list[Invoice]:
        query = self.db.query(Invoice).filter(
            Invoice.tenant_id == tenant_id
        )

        effective_store_id = store_id
        if not system_context:
            if user is None:
                raise ForbiddenException("Access denied: user context required")

            if user.store_id is not None:
                if store_id is not None and store_id != user.store_id:
                    raise ForbiddenException("Access denied: store staff cannot query other stores' invoices")
                effective_store_id = user.store_id
            elif not is_tenant_wide_authorized(user, self.db):
                raise ForbiddenException("Access denied: user has no assigned store")
            elif store_id is not None:
                store = (
                    self.db.query(Store)
                    .filter(Store.id == store_id, Store.tenant_id == tenant_id)
                    .first()
                )
                if not store:
                    raise NotFoundException(f"Store {store_id} not found")
                effective_store_id = store_id

        if effective_store_id is not None:
            query = query.filter(Invoice.store_id == effective_store_id)

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
            ps_lower = payment_status.strip().lower()
            if not needs_order:
                query = query.join(
                    Order,
                    Invoice.order_id == Order.id,
                )

            query = query.join(
                Payment,
                Payment.order_id == Order.id,
            )

            from sqlalchemy import or_
            if ps_lower in ["paid", "completed", "success"]:
                query = query.filter(
                    or_(
                        Payment.status.in_(["completed", "success", "paid"]),
                        Invoice.status == "paid",
                    )
                )
            elif ps_lower == "cancelled":
                query = query.filter(
                    or_(
                        Payment.status == "cancelled",
                        Invoice.status == "cancelled",
                    )
                )
            else:
                query = query.filter(Payment.status == payment_status)

        offset = max(0, (page - 1) * page_size)
        return (
            query.distinct()
            .order_by(Invoice.created_at.desc())
            .offset(offset)
            .limit(page_size)
            .all()
        )

    def reprint_invoice(
        self,
        tenant_id: int,
        invoice_id: int,
        printer_type: str = "generic",
        user: Optional[User] = None,
        system_context: bool = False,
    ) -> dict:
        invoice = self.get_invoice(
            tenant_id,
            invoice_id,
            user=user,
            system_context=system_context,
        )

        thermal = self.get_thermal_payload(
            tenant_id,
            invoice_id,
            printer_type=printer_type,
            user=user,
            system_context=system_context,
            is_reprint=True,
        )

        AuditService(self.db).log(
            tenant_id,
            user.id if user else 0,
            "invoice_reprinted",
            "invoice",
            invoice.id,
            {
                "invoice_number": invoice.invoice_number,
                "printer_type": printer_type,
                "reprinted_at": datetime.utcnow().isoformat(),
            },
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
        user: Optional[User] = None,
        system_context: bool = False,
        is_reprint: bool = False,
    ) -> dict:
        invoice = self.get_invoice(
            tenant_id,
            invoice_id,
            user=user,
            system_context=system_context,
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
                "total_amount": i.total_amount - i.gst_amount,
            }
            for i in items
        ]

        if not item_payload and order:
            item_payload = [
                {
                    "product_name": i.product_name,
                    "quantity": i.quantity,
                    "unit_price": i.unit_price,
                    "total_amount": i.total_amount - i.tax_amount,
                }
                for i in order.items
            ]

        # Resolve branding from DocumentSettings hierarchy
        from app.services.document_settings_service import DocumentSettingsService
        _store_id = store.id if store else (order.store_id if order else None)
        branding = DocumentSettingsService(self.db).resolve_branding(
            tenant_id=tenant_id,
            store_id=_store_id,
        )

        return generate_thermal_payload(
            invoice_number=invoice.invoice_number,
            store_name=(
                branding.business_name
                or (store.name if store else (tenant.name if tenant else "Store"))
            ),
            items=item_payload,
            subtotal=invoice.subtotal,
            discount=invoice.discount_amount,
            cgst=invoice.cgst_amount,
            sgst=invoice.sgst_amount,
            igst=invoice.igst_amount,
            grand_total=invoice.total_amount,
            payment_modes=(
                ["Refunded"]
                if invoice.status.lower() == "refunded"
                else [p.payment_method for p in payments]
            ),
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
                (branding.gstin if branding.show_gstin else None)
                or (store.gstin if store else (tenant.gstin if hasattr(tenant, "gstin") else None))
            ),
            printer_type=printer_type,
            is_reprint=is_reprint,
        )

    def _find_logo_file(self, logo_url: Optional[str]):
        if not logo_url:
            return None
        from pathlib import Path as _Path
        raw = str(logo_url).strip().lstrip("/")
        if raw.startswith("uploads/"):
            sub = raw[len("uploads/"):]
        elif raw.startswith("/uploads/"):
            sub = raw[len("/uploads/"):]
        else:
            sub = raw

        candidates = [
            _Path(raw).resolve(),
            (_Path("retail-saas") / raw).resolve(),
            (_Path(__file__).resolve().parents[2] / "uploads" / sub).resolve(),
            (_Path(__file__).resolve().parents[3] / "uploads" / sub).resolve(),
            (_Path(__file__).resolve().parents[1] / "uploads" / sub).resolve(),
        ]
        for c in candidates:
            if c.is_file():
                return c
        return None

    def _generate_thermal_image(self, ctx: Dict[str, Any]) -> bytes:
        from PIL import Image, ImageDraw, ImageFont

        width = 576  # Standard 80mm printable width at 203 DPI
        items = ctx.get("items", [])
        num_items = len(items)

        est_height = 680 + (num_items * 40)
        if ctx.get("is_reprint"):
            est_height += 40
        if ctx.get("store_address"):
            est_height += 24
        if ctx.get("store_phone"):
            est_height += 24
        if ctx.get("gstin"):
            est_height += 24
        if ctx.get("customer_name"):
            est_height += 24
        if ctx.get("customer_mobile"):
            est_height += 24

        img = Image.new("RGB", (width, est_height), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)

        try:
            font_title = ImageFont.truetype("arialbd.ttf", 22)
            font_head = ImageFont.truetype("arialbd.ttf", 16)
            font_bold = ImageFont.truetype("arialbd.ttf", 14)
            font_regular = ImageFont.truetype("arial.ttf", 13)
            font_small = ImageFont.truetype("arial.ttf", 11)
        except Exception:
            font_title = font_head = font_bold = font_regular = font_small = ImageFont.load_default()

        # Outer subtle border
        draw.rectangle([(6, 6), (width - 7, est_height - 7)], outline=(200, 200, 200), width=1)

        y = 20

        # Logo rendering from DocumentSettings
        logo_url = ctx.get("logo_url")
        if logo_url:
            try:
                logo_file = self._find_logo_file(logo_url)
                if logo_file and logo_file.is_file():
                    raw_logo = Image.open(str(logo_file))
                    if raw_logo.mode in ("RGBA", "LA") or (raw_logo.mode == "P" and "transparency" in raw_logo.info):
                        rgba = raw_logo.convert("RGBA")
                        bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
                        flat = Image.alpha_composite(bg, rgba).convert("RGB")
                    else:
                        flat = raw_logo.convert("RGB")
                    max_w, max_h = 240.0, 60.0
                    aspect = flat.width / float(flat.height)
                    if (max_w / aspect) <= max_h:
                        logo_draw_w = int(max_w)
                        logo_draw_h = int(max_w / aspect)
                    else:
                        logo_draw_h = int(max_h)
                        logo_draw_w = int(max_h * aspect)
                    logo_img = flat.resize((logo_draw_w, logo_draw_h), Image.LANCZOS)
                    logo_x = (width - logo_draw_w) // 2
                    img.paste(logo_img, (logo_x, y))
                    y += logo_draw_h + 8
            except Exception:
                pass  # Gracefully skip logo on error

        # Store Title centered
        store_txt = str(ctx.get("store_name", "RETAIL STORE")).upper()
        bbox = draw.textbbox((0, 0), store_txt, font=font_title)
        draw.text(((width - (bbox[2] - bbox[0])) // 2, y), store_txt, font=font_title, fill=(0, 0, 0))
        y += 28

        # Store Address & Contact
        if ctx.get("store_address"):
            addr_txt = str(ctx.get("store_address"))[:65]
            abbox = draw.textbbox((0, 0), addr_txt, font=font_small)
            draw.text(((width - (abbox[2] - abbox[0])) // 2, y), addr_txt, font=font_small, fill=(100, 100, 100))
            y += 18
        if ctx.get("store_phone"):
            phone_txt = f"Tel: {ctx.get('store_phone')}"
            pbbox = draw.textbbox((0, 0), phone_txt, font=font_small)
            draw.text(((width - (pbbox[2] - pbbox[0])) // 2, y), phone_txt, font=font_small, fill=(100, 100, 100))
            y += 18
        if ctx.get("gstin"):
            gst_txt = f"GSTIN: {ctx.get('gstin')}"
            gbbox = draw.textbbox((0, 0), gst_txt, font=font_small)
            draw.text(((width - (gbbox[2] - gbbox[0])) // 2, y), gst_txt, font=font_small, fill=(50, 50, 50))
            y += 18

        # DUPLICATE / REPRINT banner
        if ctx.get("is_reprint"):
            y += 4
            rep_banner = "*** DUPLICATE / REPRINT ***"
            rep_bbox = draw.textbbox((0, 0), rep_banner, font=font_bold)
            banner_w = rep_bbox[2] - rep_bbox[0] + 20
            bx0 = (width - banner_w) // 2
            draw.rectangle([(bx0, y), (bx0 + banner_w, y + 22)], fill=(254, 226, 226), outline=(153, 27, 27), width=1)
            draw.text(((width - (rep_bbox[2] - rep_bbox[0])) // 2, y + 3), rep_banner, font=font_bold, fill=(153, 27, 27))
            y += 30

        def draw_dashed_line(draw_ctx, cur_y, w):
            for x in range(20, w - 20, 10):
                draw_ctx.line([(x, cur_y), (x + 5, cur_y)], fill=(80, 80, 80), width=1)

        draw_dashed_line(draw, y, width)
        y += 12

        def draw_kv(label: str, val: str, font_l=font_regular, font_r=font_bold, fill_l=(70, 70, 70), fill_r=(0, 0, 0)):
            nonlocal y
            draw.text((24, y), label, font=font_l, fill=fill_l)
            r_bbox = draw.textbbox((0, 0), val, font=font_r)
            r_w = r_bbox[2] - r_bbox[0]
            draw.text((width - 24 - r_w, y), val, font=font_r, fill=fill_r)
            y += 22

        # Invoice details
        draw_kv("Invoice No", str(ctx.get("invoice_number", "")))
        created_at = ctx.get("created_at")
        dt_str = created_at.strftime("%Y-%m-%d %H:%M:%S") if isinstance(created_at, datetime) else str(created_at or "")
        draw_kv("Date & Time", dt_str)
        if ctx.get("cashier_name"):
            draw_kv("Cashier", str(ctx.get("cashier_name")))
        if ctx.get("customer_name"):
            draw_kv("Customer", str(ctx.get("customer_name")))
        if ctx.get("customer_mobile"):
            draw_kv("Mobile", str(ctx.get("customer_mobile")))

        y += 6
        draw_dashed_line(draw, y, width)
        y += 10

        # Items Table Header
        draw.text((24, y), "ITEM", font=font_bold, fill=(0, 0, 0))
        h_qty = "QTY x PRICE"
        draw.text((300, y), h_qty, font=font_bold, fill=(0, 0, 0))
        h_tot = "TOTAL"
        h_tbbox = draw.textbbox((0, 0), h_tot, font=font_bold)
        draw.text((width - 24 - (h_tbbox[2] - h_tbbox[0]), y), h_tot, font=font_bold, fill=(0, 0, 0))
        y += 20
        draw_dashed_line(draw, y, width)
        y += 10

        # Items Table Rows
        for itm in items:
            p_name = str(itm.get("product_name", "Item"))
            qty = itm.get("quantity", 1)
            u_price = Decimal(str(itm.get("unit_price", 0)))
            t_amt = Decimal(str(itm.get("total_amount", 0)))

            draw.text((24, y), p_name[:36], font=font_bold, fill=(20, 20, 20))
            y += 18
            qty_price_str = f"  {qty} x Rs. {u_price:.2f}"
            draw.text((24, y), qty_price_str, font=font_regular, fill=(80, 80, 80))
            tot_str = f"Rs. {t_amt:.2f}"
            t_bbox = draw.textbbox((0, 0), tot_str, font=font_bold)
            draw.text((width - 24 - (t_bbox[2] - t_bbox[0]), y), tot_str, font=font_bold, fill=(0, 0, 0))
            y += 20

        y += 4
        draw_dashed_line(draw, y, width)
        y += 10

        # Financial Summary
        subtotal = Decimal(str(ctx.get("subtotal", 0)))
        draw_kv("Subtotal", f"Rs. {subtotal:.2f}")

        discount = Decimal(str(ctx.get("discount_amount", 0)))
        if discount > 0:
            draw_kv("Discount (-)", f"-Rs. {discount:.2f}", fill_r=(180, 0, 0))

        cgst = Decimal(str(ctx.get("cgst_amount", 0)))
        if cgst > 0:
            draw_kv("CGST (+)", f"Rs. {cgst:.2f}")

        sgst = Decimal(str(ctx.get("sgst_amount", 0)))
        if sgst > 0:
            draw_kv("SGST (+)", f"Rs. {sgst:.2f}")

        igst = Decimal(str(ctx.get("igst_amount", 0)))
        if igst > 0:
            draw_kv("IGST (+)", f"Rs. {igst:.2f}")

        y += 4
        draw.line([(24, y), (width - 24, y)], fill=(0, 0, 0), width=2)
        y += 10

        grand_total = Decimal(str(ctx.get("total_amount", 0)))
        draw_kv("NET PAYABLE", f"Rs. {grand_total:.2f}", font_l=font_head, font_r=font_head, fill_r=(22, 101, 52))
        y += 4
        draw.line([(24, y), (width - 24, y)], fill=(0, 0, 0), width=2)
        y += 12

        # Payment details
        p_modes = ctx.get("payment_modes", [])
        if p_modes:
            pm_str = ", ".join([str(p).upper() for p in p_modes])
            draw_kv("Paid via", pm_str, font_r=font_regular)

        y += 6
        draw_dashed_line(draw, y, width)
        y += 16

        # Footer - Dynamic from DocumentSettings or defaults
        _footer = ctx.get("footer_text") or "*** THANK YOU FOR YOUR VISIT ***"
        _terms = ctx.get("terms_and_conditions") or "Retain this bill for exchange / returns\nExchange within 7 days in original condition"

        foot1 = _footer
        f1_bbox = draw.textbbox((0, 0), foot1, font=font_bold)
        draw.text(((width - (f1_bbox[2] - f1_bbox[0])) // 2, y), foot1, font=font_bold, fill=(0, 0, 0))
        y += 20

        for _term_line in _terms.split("\n"):
            _term_line = _term_line.strip()
            if not _term_line:
                continue
            _tl_bbox = draw.textbbox((0, 0), _term_line, font=font_small)
            draw.text(((width - (_tl_bbox[2] - _tl_bbox[0])) // 2, y), _term_line[:65], font=font_small, fill=(100, 100, 100))
            y += 18

        y += 10

        actual_height = y + 10
        cropped = img.crop((0, 0, width, actual_height))

        out = io.BytesIO()
        cropped.save(out, format="PNG")
        out.seek(0)
        return out.read()

    def _generate_thermal_html(self, ctx: Dict[str, Any], auto_print: bool = False) -> str:
        created_at = ctx.get("created_at")
        dt_str = created_at.strftime("%Y-%m-%d %H:%M:%S") if isinstance(created_at, datetime) else str(created_at or "")
        
        auto_print_script = "<script>window.onload = function() { window.print(); };</script>" if auto_print else ""
        
        reprint_html = '<div class="reprint-badge">*** DUPLICATE / REPRINT ***</div>' if ctx.get("is_reprint") else ""
        
        addr_html = f'<div class="store-meta">{ctx["store_address"]}</div>' if ctx.get("store_address") else ""
        phone_html = f'<div class="store-meta">Tel: {ctx["store_phone"]}</div>' if ctx.get("store_phone") else ""
        gstin_html = f'<div class="store-meta">GSTIN: {ctx["gstin"]}</div>' if ctx.get("gstin") else ""
        cust_name_html = f'<div class="line-row"><span class="line-label">Customer</span><span class="line-val">{ctx["customer_name"]}</span></div>' if ctx.get("customer_name") else ""
        cust_phone_html = f'<div class="line-row"><span class="line-label">Mobile</span><span class="line-val">{ctx["customer_mobile"]}</span></div>' if ctx.get("customer_mobile") else ""
        cashier_html = f'<div class="line-row"><span class="line-label">Cashier</span><span class="line-val">{ctx["cashier_name"]}</span></div>' if ctx.get("cashier_name") else ""

        logo_html = ""
        logo_url = ctx.get("logo_url")
        if logo_url:
            logo_file = self._find_logo_file(logo_url)
            if logo_file and logo_file.is_file():
                try:
                    import base64
                    ext = logo_file.suffix.lower().replace(".", "")
                    mime = "image/png" if ext == "png" else "image/jpeg"
                    with open(logo_file, "rb") as _f:
                        b64_data = base64.b64encode(_f.read()).decode("utf-8")
                    logo_html = f'<div style="text-align: center; margin-bottom: 8px;"><img src="data:{mime};base64,{b64_data}" alt="Logo" style="max-height: 55px; max-width: 200px; object-fit: contain; " /></div>'
                except Exception:
                    logo_html = f'<div style="text-align: center; margin-bottom: 8px;"><img src="{logo_url}" alt="Logo" style="max-height: 55px; max-width: 200px; object-fit: contain; " /></div>'
            else:
                logo_html = f'<div style="text-align: center; margin-bottom: 8px;"><img src="{logo_url}" alt="Logo" style="max-height: 55px; max-width: 200px; object-fit: contain; " /></div>'

        footer_val = html.escape(str(ctx.get("footer_text") or "*** THANK YOU FOR SHOPPING! ***"))
        raw_terms = ctx.get("terms_and_conditions") or "Retain this bill for returns / exchange\nExchange within 7 days in original condition"
        terms_html = "<br>".join([html.escape(t.strip()) for t in str(raw_terms).split("\n") if t.strip()])

        items_html = ""
        for itm in ctx.get("items", []):
            p_name = itm.get("product_name", "Item")
            qty = itm.get("quantity", 1)
            u_price = Decimal(str(itm.get("unit_price", 0)))
            t_amt = Decimal(str(itm.get("total_amount", 0)))
            items_html += f"""
            <div class="item-row">
                <div class="item-name">{p_name}</div>
                <div class="item-sub">
                    <span>{qty} x Rs. {u_price:.2f}</span>
                    <span class="item-total">Rs. {t_amt:.2f}</span>
                </div>
            </div>"""

        subtotal = Decimal(str(ctx.get("subtotal", 0)))
        discount = Decimal(str(ctx.get("discount_amount", 0)))
        cgst = Decimal(str(ctx.get("cgst_amount", 0)))
        sgst = Decimal(str(ctx.get("sgst_amount", 0)))
        igst = Decimal(str(ctx.get("igst_amount", 0)))
        grand_total = Decimal(str(ctx.get("total_amount", 0)))

        discount_html = f'<div class="line-row" style="color: #dc2626;"><span class="line-label">Discount (-)</span><span class="line-val">-Rs. {discount:.2f}</span></div>' if discount > 0 else ""
        cgst_html = f'<div class="line-row"><span class="line-label">CGST (+)</span><span class="line-val">Rs. {cgst:.2f}</span></div>' if cgst > 0 else ""
        sgst_html = f'<div class="line-row"><span class="line-label">SGST (+)</span><span class="line-val">Rs. {sgst:.2f}</span></div>' if sgst > 0 else ""
        igst_html = f'<div class="line-row"><span class="line-label">IGST (+)</span><span class="line-val">Rs. {igst:.2f}</span></div>' if igst > 0 else ""

        pm_list = ctx.get("payment_modes", [])
        pm_str = ", ".join([str(p).upper() for p in pm_list]) if pm_list else "CASH"

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Tax Invoice #{ctx.get("invoice_number", "")} - Thermal Receipt</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: 'Courier New', Courier, monospace; }}
  body {{ background: #f1f5f9; display: flex; flex-direction: column; align-items: center; padding: 24px 12px; min-height: 100vh; }}
  .actions-bar {{ margin-bottom: 16px; display: flex; gap: 10px; }}
  .btn-print {{ background: #0f172a; color: #fff; border: none; padding: 8px 16px; border-radius: 6px; font-weight: bold; font-size: 13px; cursor: pointer; }}
  .btn-print:hover {{ background: #334155; }}
  .receipt-box {{ background: #ffffff; width: 340px; padding: 20px 18px; box-shadow: 0 4px 16px rgba(0,0,0,0.1); border-radius: 4px; color: #000; font-size: 12px; line-height: 1.4; }}
  .header {{ text-align: center; border-bottom: 2px dashed #000; padding-bottom: 10px; margin-bottom: 10px; }}
  .store-title {{ font-size: 16px; font-weight: 900; text-transform: uppercase; }}
  .store-meta {{ font-size: 11px; color: #555; margin-top: 1px; }}
  .reprint-badge {{ display: inline-block; margin-top: 6px; padding: 2px 8px; border: 1px solid #000; font-weight: 800; font-size: 11px; background: #fee2e2; color: #991b1b; text-transform: uppercase; }}
  .receipt-type {{ font-size: 12px; font-weight: 800; margin-top: 4px; letter-spacing: 0.5px; }}
  .divider {{ border-top: 1px dashed #444; margin: 8px 0; }}
  .solid-divider {{ border-top: 2px solid #000; margin: 8px 0; }}
  .line-row {{ display: flex; justify-content: space-between; margin-bottom: 3px; }}
  .line-label {{ color: #333; }}
  .line-val {{ font-weight: 700; text-align: right; }}
  .item-row {{ margin-bottom: 6px; }}
  .item-name {{ font-weight: 700; color: #111; }}
  .item-sub {{ display: flex; justify-content: space-between; color: #555; font-size: 11px; padding-left: 8px; }}
  .item-total {{ font-weight: 700; color: #000; }}
  .total-row {{ display: flex; justify-content: space-between; font-size: 14px; font-weight: 900; margin: 6px 0; }}
  .footer {{ text-align: center; border-top: 2px dashed #000; margin-top: 12px; padding-top: 8px; font-size: 11px; color: #555; }}
  @media print {{
    body {{ background: #fff; padding: 0; }}
    .actions-bar {{ display: none !important; }}
    .receipt-box {{ box-shadow: none; width: 100%; max-width: 300px; padding: 4px; margin: 0; border: none; }}
  }}
</style>
{auto_print_script}
</head>
<body>
<div class="actions-bar">
  <button class="btn-print" onclick="window.print()">Print Receipt</button>
</div>
<div class="receipt-box">
  <div class="header">
    {logo_html}
    <div class="store-title">{ctx.get("store_name", "RETAIL STORE")}</div>
    {addr_html}
    {phone_html}
    {gstin_html}
    {reprint_html}
    <div class="receipt-type">TAX INVOICE / CASH BILL</div>
  </div>
  
  <div class="line-row"><span class="line-label">Invoice No</span><span class="line-val">{ctx.get("invoice_number", "")}</span></div>
  <div class="line-row"><span class="line-label">Date & Time</span><span class="line-val">{dt_str}</span></div>
  {cashier_html}
  {cust_name_html}
  {cust_phone_html}

  <div class="divider"></div>
  <div class="line-row" style="font-weight: 800; font-size: 11px;">
    <span>ITEM</span>
    <span>QTY x PRICE &nbsp;&nbsp;&nbsp; TOTAL</span>
  </div>
  <div class="divider"></div>

  {items_html}

  <div class="divider"></div>
  <div class="line-row"><span class="line-label">Subtotal</span><span class="line-val">Rs. {subtotal:.2f}</span></div>
  {discount_html}
  {cgst_html}
  {sgst_html}
  {igst_html}

  <div class="solid-divider"></div>
  <div class="total-row">
    <span>NET PAYABLE</span>
    <span style="color: #15803d;">Rs. {grand_total:.2f}</span>
  </div>
  <div class="solid-divider"></div>

  <div class="line-row"><span class="line-label">Paid via</span><span class="line-val">{pm_str}</span></div>

  <div class="footer">
    {footer_val}<br>
    {terms_html}
  </div>
</div>
</body>
</html>"""

    def _generate_thermal_text(self, ctx: Dict[str, Any], printer_type: str = "generic") -> str:
        width = 42 if printer_type == "tvs" else 32
        lines: list[str] = []
        if ctx.get("is_reprint"):
            lines.append("*** DUPLICATE / REPRINT ***".center(width))
        lines.append(str(ctx.get("store_name", "RETAIL STORE")).upper().center(width))
        if ctx.get("store_address"):
            lines.append(str(ctx.get("store_address"))[:width].center(width))
        if ctx.get("gstin"):
            lines.append(f"GSTIN: {ctx.get('gstin')}".center(width))
        lines.append("=" * width)
        lines.append(f"Invoice : {ctx.get('invoice_number', '')}")
        created_at = ctx.get("created_at")
        dt_str = created_at.strftime("%Y-%m-%d %H:%M:%S") if isinstance(created_at, datetime) else str(created_at or "")
        lines.append(f"Date    : {dt_str}")
        if ctx.get("customer_name"):
            lines.append(f"Customer: {ctx.get('customer_name')}")
        if ctx.get("customer_mobile"):
            lines.append(f"Mobile  : {ctx.get('customer_mobile')}")
        lines.append("-" * width)
        lines.append(f"{'ITEM':<16}{'QTY':>4} {'TOTAL':>10}")
        lines.append("-" * width)
        for itm in ctx.get("items", []):
            name = str(itm.get("product_name", "Item"))[:width]
            lines.append(name)
            qty = itm.get("quantity", 1)
            price = Decimal(str(itm.get("unit_price", 0)))
            total = Decimal(str(itm.get("total_amount", 0)))
            lines.append(f"  {qty} x {price:.2f}{'':>{max(1, width - 20)}}Rs. {total:.2f}")

        lines.append("-" * width)
        subtotal = Decimal(str(ctx.get("subtotal", 0)))
        lines.append(f"Subtotal:{'':>{max(1, width - 20)}}Rs. {subtotal:>8.2f}")
        discount = Decimal(str(ctx.get("discount_amount", 0)))
        if discount > 0:
            lines.append(f"Discount:{'':>{max(1, width - 20)}}-Rs.{discount:>8.2f}")
        cgst = Decimal(str(ctx.get("cgst_amount", 0)))
        if cgst > 0:
            lines.append(f"CGST:{'':>{max(1, width - 16)}}Rs. {cgst:>8.2f}")
        sgst = Decimal(str(ctx.get("sgst_amount", 0)))
        if sgst > 0:
            lines.append(f"SGST:{'':>{max(1, width - 16)}}Rs. {sgst:>8.2f}")
        igst = Decimal(str(ctx.get("igst_amount", 0)))
        if igst > 0:
            lines.append(f"IGST:{'':>{max(1, width - 16)}}Rs. {igst:>8.2f}")
        lines.append("=" * width)
        grand_total = Decimal(str(ctx.get("total_amount", 0)))
        lines.append(f"TOTAL AMOUNT:{'':>{max(1, width - 24)}}Rs. {grand_total:>8.2f}")
        lines.append("=" * width)
        p_modes = ctx.get("payment_modes", [])
        if p_modes:
            lines.append(f"Paid via: {', '.join([str(p).upper() for p in p_modes])}")
        _footer = ctx.get("footer_text") or "THANK YOU FOR YOUR VISIT!"
        _terms = ctx.get("terms_and_conditions")
        lines.append("-" * width)
        lines.append(_footer[:width].center(width))
        if _terms:
            for _tl in _terms.split("\n"):
                _tl = _tl.strip()
                if _tl:
                    lines.append(_tl[:width].center(width))
        lines.append("=" * width)
        lines.append("\n\n\n\x1b\x69")  # ESC/POS cut paper
        return "\n".join(lines)

    def _generate_thermal_pdf(self, ctx: Dict[str, Any]) -> bytes:
        img_bytes = self._generate_thermal_image(ctx)
        from PIL import Image
        from reportlab.lib.utils import ImageReader
        from reportlab.pdfgen import canvas

        pil_img = Image.open(io.BytesIO(img_bytes))
        img_w, img_h = pil_img.size

        # 80mm in points = 80 / 25.4 * 72 = 226.77 points
        page_width = 80.0 / 25.4 * 72.0
        page_height = page_width * (img_h / img_w)

        pdf_buf = io.BytesIO()
        c = canvas.Canvas(pdf_buf, pagesize=(page_width, page_height))
        c.drawImage(ImageReader(io.BytesIO(img_bytes)), 0, 0, width=page_width, height=page_height)
        c.showPage()
        c.save()
        return pdf_buf.getvalue()

    def export_invoice_thermal(
        self,
        user: User,
        invoice_id: int,
        mode: Any = "preview",
        printer_type: str = "generic",
        is_reprint: bool = False,
    ) -> Response:
        invoice = self.get_invoice(
            user.tenant_id,
            invoice_id,
            user=user,
        )

        order = self.db.query(Order).filter(Order.id == invoice.order_id).first() if invoice.order_id else None
        tenant = self.db.query(Tenant).filter(Tenant.id == user.tenant_id).first()
        store = self.db.query(Store).filter(Store.id == order.store_id).first() if order and order.store_id else None
        customer = self.db.query(Customer).filter(Customer.id == order.customer_id).first() if order and order.customer_id else None
        payments = self.db.query(Payment).filter(Payment.order_id == invoice.order_id).all() if invoice.order_id else []
        cashier = self.db.query(User).filter(User.id == order.user_id).first() if order and order.user_id else user

        item_list = []
        for itm in (invoice.items or []):
            p_name = self.db.query(Product.name).filter(Product.id == itm.product_id).scalar() or "Item"
            item_list.append({
                "product_name": p_name,
                "quantity": itm.quantity,
                "unit_price": itm.unit_price,
                "total_amount": itm.total_amount,
            })
        if not item_list and order and order.items:
            for itm in order.items:
                item_list.append({
                    "product_name": itm.product_name,
                    "quantity": itm.quantity,
                    "unit_price": itm.unit_price,
                    "total_amount": itm.total,
                })

        # Resolve branding from DocumentSettings hierarchy
        from app.services.document_settings_service import DocumentSettingsService
        _store_id = store.id if store else getattr(invoice, "store_id", None)
        branding = DocumentSettingsService(self.db).resolve_branding(
            tenant_id=user.tenant_id,
            store_id=_store_id,
        )

        receipt_context = {
            "invoice_id": invoice.id,
            "invoice_number": invoice.invoice_number,
            "store_name": branding.business_name or (store.name if store else (tenant.name if tenant else "Retail Store")),
            "store_address": branding.address or (store.address if store and store.address else (tenant.address if tenant else None)),
            "store_phone": branding.phone or (store.phone if store and store.phone else (tenant.phone if tenant else None)),
            "gstin": (branding.gstin if branding.show_gstin else None) or (store.gstin if store and store.gstin else (tenant.gstin if hasattr(tenant, "gstin") else None)),
            "logo_url": branding.logo_url,
            "footer_text": branding.footer_text,
            "terms_and_conditions": branding.terms_and_conditions,
            "created_at": invoice.created_at,
            "cashier_name": cashier.full_name if cashier and hasattr(cashier, "full_name") and cashier.full_name else (cashier.username if cashier else "Staff"),
            "customer_name": customer.name if customer else None,
            "customer_mobile": customer.phone if customer else None,
            "items": item_list,
            "subtotal": invoice.subtotal,
            "discount_amount": invoice.discount_amount or Decimal("0.00"),
            "cgst_amount": invoice.cgst_amount or Decimal("0.00"),
            "sgst_amount": invoice.sgst_amount or Decimal("0.00"),
            "igst_amount": invoice.igst_amount or Decimal("0.00"),
            "total_amount": invoice.total_amount,
            "payment_modes": [p.payment_method for p in payments] if payments else ["CASH"],
            "is_reprint": is_reprint,
        }

        if is_reprint:
            AuditService(self.db).log(
                user.tenant_id,
                user.id,
                "invoice_reprinted",
                "invoice",
                invoice.id,
                {
                    "invoice_number": invoice.invoice_number,
                    "printer_type": printer_type,
                    "mode": str(mode),
                    "reprinted_at": datetime.utcnow().isoformat(),
                },
            )

        mode_val = str(getattr(mode, "value", mode) or "preview").lower().strip()

        # 1. Preview mode (Default) -> Visual 80mm receipt PNG rendered directly in Swagger UI
        if mode_val == InvoiceThermalMode.preview.value:
            img_bytes = self._generate_thermal_image(receipt_context)
            return Response(
                content=img_bytes,
                media_type="image/png",
                headers={
                    "Content-Disposition": f"inline; filename=invoice_{invoice.invoice_number}_thermal.png",
                    "X-Invoice-Print-Type": "80mm-PNG-Preview",
                },
            )

        # 2. View mode -> Inline styled HTML page with auto-print dialog
        if mode_val == InvoiceThermalMode.view.value:
            html_content = self._generate_thermal_html(receipt_context, auto_print=True)
            return HTMLResponse(
                content=html_content,
                status_code=200,
                headers={"Content-Disposition": f"inline; filename=invoice_{invoice.invoice_number}_thermal.html"},
            )

        # 3. Download mode -> ESC/POS text file attachment download
        if mode_val == InvoiceThermalMode.download.value:
            text_payload = self._generate_thermal_text(receipt_context, printer_type=printer_type)
            return Response(
                content=text_payload.encode("utf-8"),
                media_type="text/plain; charset=utf-8",
                headers={
                    "Content-Disposition": f"attachment; filename=invoice_{invoice.invoice_number}_thermal.txt",
                    "X-Invoice-Print-Type": "ESC/POS",
                },
            )

        # 4. PDF mode -> 80mm Thermal Receipt PDF download
        if mode_val == InvoiceThermalMode.pdf.value:
            pdf_bytes = self._generate_thermal_pdf(receipt_context)
            return Response(
                content=pdf_bytes,
                media_type="application/pdf",
                headers={
                    "Content-Disposition": f"attachment; filename=invoice_{invoice.invoice_number}_thermal.pdf",
                    "X-Invoice-Print-Type": "80mm-PDF",
                },
            )

        # 5. HTML mode -> Styled raw HTML layout
        if mode_val == InvoiceThermalMode.html.value:
            html_content = self._generate_thermal_html(receipt_context, auto_print=False)
            return HTMLResponse(
                content=html_content,
                status_code=200,
                headers={"Content-Disposition": f"inline; filename=invoice_{invoice.invoice_number}_thermal.html"},
            )

        # 6. JSON mode -> Structured JSON payload
        if mode_val == InvoiceThermalMode.json.value:
            text_payload = self._generate_thermal_text(receipt_context, printer_type=printer_type)
            html_content = self._generate_thermal_html(receipt_context, auto_print=False)
            response_data = InvoiceThermalResponse(
                success=True,
                message="Invoice thermal receipt generated successfully",
                invoice_id=invoice.id,
                invoice_number=invoice.invoice_number,
                store_name=receipt_context["store_name"],
                grand_total=invoice.total_amount,
                is_reprint=is_reprint,
                text_payload=text_payload,
                html=html_content,
            )
            return JSONResponse(content=response_data.model_dump(mode="json"))

        # 7. Text mode -> Raw ESC/POS text printer stream
        text_payload = self._generate_thermal_text(receipt_context, printer_type=printer_type)
        return Response(
            content=text_payload.encode("utf-8"),
            media_type="text/plain; charset=utf-8",
            headers={
                "Content-Disposition": f"inline; filename=invoice_{invoice.invoice_number}_thermal.txt",
                "X-Invoice-Print-Type": "ESC/POS",
            },
        )


    def generate_pdf(
        self,
        tenant_id: int,
        invoice_id: int,
        document_type: str = "invoice",
        user: Optional[User] = None,
        system_context: bool = False,
    ) -> bytes:
        invoice = self.get_invoice(
            tenant_id,
            invoice_id,
            user=user,
            system_context=system_context,
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

        cashier_name = ""
        if order and order.user_id:
            cashier_user = self.db.query(User).filter(User.id == order.user_id).first()
            if cashier_user:
                cashier_name = cashier_user.full_name or cashier_user.email or ""

        data = {
            "invoice_number": invoice.invoice_number,
            "order_number": order.order_number if order else getattr(invoice, "invoice_number", ""),
            "created_at": invoice.created_at,
            "order_date": order.created_at if order else invoice.created_at,
            "subtotal": float(invoice.subtotal),
            "discount_amount": float(invoice.discount_amount),
            "cgst_amount": float(invoice.cgst_amount),
            "sgst_amount": float(invoice.sgst_amount),
            "igst_amount": float(invoice.igst_amount),
            "total_amount": float(invoice.total_amount),
            "total": float(invoice.total_amount),
            "qr_data": qr_data,
            "is_b2b": bool(customer and customer.gstin),
            "cashier": cashier_name,
            "store_name": (branding.business_name if branding and branding.business_name else "") or (store.name if store else ""),
            "store_address": (branding.address if branding and branding.address else "") or (store.address if store else ""),
            "store_phone": (branding.phone if branding and branding.phone else "") or (store.phone if store else ""),
            "store_gstin": (branding.gstin if branding and branding.gstin else "") or (store.gstin if store else ""),
            "customer": {
                "name": customer.name if customer else "Walk-in Customer",
                "phone": customer.phone if customer else "",
                "address": customer.address if customer else "",
                "gstin": customer.gstin if customer else "",
            } if customer else None,
            "items": self._invoice_pdf_items(invoice, order),
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
            try:
                self._upload_to_s3(
                    invoice,
                    pdf_bytes,
                )
            except Exception as exc:
                logger.warning(
                    "Failed to upload invoice %s PDF to S3: %s",
                    invoice.invoice_number,
                    exc,
                )

        return pdf_bytes

    def generate_credit_note_pdf(
        self,
        tenant_id: int,
        credit_note_id: int,
        user: Optional[User] = None,
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

        invoice = self.get_invoice(tenant_id, credit_note.invoice_id, user=user)
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
        user: Optional[User] = None,
        condition: str = "sellable",
        idempotency_key: str | None = None,
        issue_credit_note: bool = False,
        refund_method: str = "cash",
    ) -> dict:
        self.get_invoice(
            tenant_id,
            invoice_id,
            user=user,
        )

        if not isinstance(return_quantity, Decimal):
            return_quantity = Decimal(str(return_quantity))

        if return_quantity <= Decimal("0"):
            raise AppException("Return quantity must be greater than zero")

        cond = condition.strip().lower() if condition else ""
        if cond not in ("sellable", "damaged", "expired"):
            raise AppException(
                "Condition must be one of: sellable, damaged, expired"
            )

        if idempotency_key is not None:
            idempotency_key = idempotency_key.strip()
            if (
                not idempotency_key
                or any(character.isspace() for character in idempotency_key)
            ):
                raise AppException(
                    "Idempotency key must be a non-empty token without spaces"
                )

        refund_method = refund_method.strip().lower()
        if refund_method not in {"cash", "upi", "store_credit"}:
            raise AppException(
                "Refund method must be one of: cash, upi, store_credit"
            )

        if idempotency_key:
            existing_return = (
                self.db.query(InvoiceItemReturn)
                .filter(
                    InvoiceItemReturn.tenant_id == tenant_id,
                    InvoiceItemReturn.idempotency_key == idempotency_key,
                )
                .first()
            )
            if existing_return:
                if (
                    existing_return.invoice_id != invoice_id
                    or existing_return.product_id != product_id
                    or existing_return.quantity != return_quantity
                    or existing_return.condition != cond
                    or bool(existing_return.refund_id) != issue_credit_note
                ):
                    raise AppException("Idempotency key collision: request payload does not match existing return")

                inv_item = (
                    self.db.query(InvoiceItem)
                    .filter(InvoiceItem.id == existing_return.invoice_item_id)
                    .first()
                )
                cn = (
                    self.db.query(CreditNote)
                    .filter(CreditNote.id == existing_return.credit_note_id)
                    .first()
                    if existing_return.credit_note_id
                    else None
                )
                existing_refund = (
                    self.db.query(Refund)
                    .filter(Refund.id == existing_return.refund_id)
                    .first()
                    if existing_return.refund_id
                    else None
                )
                if (
                    existing_refund
                    and existing_refund.refund_method != refund_method
                ):
                    raise AppException(
                        "Idempotency key collision: request payload does not match existing return"
                    )
                return {
                    "return_id": existing_return.id,
                    "invoice_id": existing_return.invoice_id,
                    "product_id": existing_return.product_id,
                    "return_quantity": existing_return.quantity,
                    "condition": existing_return.condition,
                    "returned_quantity_total": inv_item.returned_quantity if inv_item else existing_return.quantity,
                    "remaining_returnable_quantity": (inv_item.quantity - inv_item.returned_quantity) if inv_item else Decimal("0"),
                    "reason": existing_return.reason,
                    "status": "return_processed",
                    "credit_note_id": cn.id if cn else None,
                    "credit_note_no": cn.credit_note_no if cn else None,
                    "refund_id": existing_return.refund_id,
                    "refund_method": (
                        existing_refund.refund_method if existing_refund else None
                    ),
                    "issue_credit_note": bool(cn or existing_refund),
                }

        _return_mutex.acquire()
        try:
            invoice = (
                self.db.query(Invoice)
                .filter(
                    Invoice.id == invoice_id,
                    Invoice.tenant_id == tenant_id,
                )
                .with_for_update()
                .first()
            )
            if not invoice:
                raise NotFoundException("Invoice not found")

            invoice_item = (
                self.db.query(InvoiceItem)
                .filter(
                    InvoiceItem.invoice_id == invoice.id,
                    InvoiceItem.product_id == product_id,
                )
                .with_for_update()
                .first()
            )
            if not invoice_item:
                raise NotFoundException("Product not found on invoice")

            current_returned = getattr(invoice_item, "returned_quantity", None) or Decimal("0.00")
            remaining_returnable = invoice_item.quantity - current_returned

            if return_quantity > remaining_returnable:
                raise AppException(
                    f"Return quantity ({return_quantity}) exceeds remaining returnable quantity ({remaining_returnable})"
                )

            order = (
                self.db.query(Order)
                .filter(Order.id == invoice.order_id)
                .with_for_update()
                .first()
            )
            order_item = None
            if order:
                order_item = (
                    self.db.query(OrderItem)
                    .filter(
                        OrderItem.order_id == order.id,
                        OrderItem.product_id == product_id,
                    )
                    .with_for_update()
                    .first()
                )

            store_id = invoice.store_id or (order.store_id if order else None)
            if not store_id:
                raise AppException("Invoice has no associated store")

            invoice_item.returned_quantity = current_returned + return_quantity

            from app.schemas.inventory import StockInRequest

            batch_allocations = []
            if order_item:
                batch_allocations = (
                    self.db.query(OrderItemBatchAllocation)
                    .filter(OrderItemBatchAllocation.order_item_id == order_item.id)
                    .all()
                )

            restored_batches = []
            if batch_allocations:
                restored_batches = BatchAllocationService(self.db, user=user).restore_batch_allocation(
                    tenant_id=tenant_id,
                    store_id=store_id,
                    order_item_id=order_item.id,
                    quantity_to_restore=return_quantity,
                    condition=cond,
                    reference_id=invoice.id,
                    reference_type="INVOICE_RETURN",
                    notes=reason or f"Return for invoice {invoice.invoice_number}",
                    commit=False,
                )
            else:
                product = self.db.query(Product).filter(Product.id == product_id).first()
                is_batch_tracked = product and getattr(product, "track_batch", False)

                if cond == "sellable":
                    InventoryService(self.db).stock_in(
                        tenant_id,
                        StockInRequest(
                            store_id=store_id,
                            product_id=product_id,
                            quantity=return_quantity,
                            notes=reason or f"Return for invoice {invoice.invoice_number}" + (" (historical unbatched)" if is_batch_tracked else ""),
                        ),
                        commit=False,
                        movement_type=StockMovementType.RETURN.value,
                        reference_id=invoice.id,
                        reference_type="INVOICE_RETURN",
                    )
                else:
                    inv = InventoryService(self.db)._get_or_create_inventory(tenant_id, store_id, product_id)
                    movement = StockMovement(
                        tenant_id=tenant_id,
                        store_id=store_id,
                        product_id=product_id,
                        movement_type=StockMovementType.ADJUSTMENT.value,
                        quantity=Decimal("0.0000"),
                        previous_stock=inv.quantity,
                        new_stock=inv.quantity,
                        reference_id=invoice.id,
                        reference_type="RETURN_DAMAGED",
                        notes=reason or f"Return of {cond} goods for invoice {invoice.invoice_number} - zero saleable stock added",
                        created_by=getattr(user, "id", None) if user else None,
                    )
                    self.db.add(movement)

            item_ratio = return_quantity / invoice_item.quantity if invoice_item.quantity > Decimal("0") else Decimal("0")
            line_unit_price = invoice_item.unit_price
            line_tax = (invoice_item.gst_amount * item_ratio).quantize(Decimal("0.01"))
            line_total = (invoice_item.total_amount * item_ratio).quantize(Decimal("0.01"))

            canonical_return = InvoiceItemReturn(
                tenant_id=tenant_id,
                store_id=store_id,
                invoice_id=invoice.id,
                invoice_item_id=invoice_item.id,
                order_item_id=order_item.id if order_item else None,
                product_id=product_id,
                batch_id=int(restored_batches[0]["batch_id"]) if restored_batches else None,
                quantity=return_quantity,
                unit_price=line_unit_price,
                tax_amount=line_tax,
                total_amount=line_total,
                condition=cond,
                reason=reason,
                idempotency_key=idempotency_key,
                user_id=getattr(user, "id", None) if user else None,
            )
            self.db.add(canonical_return)
            self.db.flush()

            total_invoiced = sum((i.quantity for i in invoice.items), Decimal("0"))
            total_returned = sum(((getattr(i, "returned_quantity", None) or Decimal("0")) for i in invoice.items), Decimal("0"))
            if total_returned >= total_invoiced:
                invoice.status = "refunded"
                if order:
                    order.status = OrderStatus.RETURNED.value

            created_credit_note = None
            created_refund = None
            if issue_credit_note:
                created_refund = self.create_refund(
                    tenant_id=tenant_id,
                    invoice_id=invoice.id,
                    refund_amount=line_total,
                    refund_method=refund_method or "cash",
                    reason=reason or f"Return for item {product_id}",
                    user=user,
                    commit=False,
                )
                created_credit_note = self._approve_refund_internal(
                    tenant_id=tenant_id,
                    refund=created_refund,
                    approved_by_user_id=getattr(user, "id", 1) if user else 1,
                    user=user,
                    return_id=canonical_return.id,
                    commit=False,
                )
                canonical_return.refund_id = created_refund.id
                canonical_return.credit_note_id = created_credit_note.id

            self.db.commit()

            return {
                "return_id": canonical_return.id,
                "invoice_id": invoice_id,
                "product_id": product_id,
                "return_quantity": return_quantity,
                "condition": cond,
                "returned_quantity_total": invoice_item.returned_quantity,
                "remaining_returnable_quantity": invoice_item.quantity - invoice_item.returned_quantity,
                "reason": reason,
                "status": "return_processed",
                "restored_batches": restored_batches,
                "credit_note_id": created_credit_note.id if created_credit_note else None,
                "credit_note_no": created_credit_note.credit_note_no if created_credit_note else None,
                "refund_id": created_refund.id if created_refund else None,
                "refund_method": (
                    created_refund.refund_method if created_refund else None
                ),
                "issue_credit_note": bool(created_credit_note),
            }
        except Exception:
            self.db.rollback()
            raise
        finally:
            _return_mutex.release()

    def create_refund(
        self,
        tenant_id: int,
        invoice_id: int,
        refund_amount: Decimal,
        refund_method: str,
        reason: str | None,
        user: Optional[User] = None,
        idempotency_key: Optional[str] = None,
        commit: bool = True,
        approved_by: Optional[int] = None,
    ) -> Refund:
        self.get_invoice(
            tenant_id,
            invoice_id,
            user=user,
        )

        if not isinstance(refund_amount, Decimal):
            refund_amount = Decimal(str(refund_amount))

        if refund_amount <= 0:
            raise AppException(
                "Refund amount must be greater than zero"
            )

        if idempotency_key:
            existing_idemp = (
                self.db.query(Refund)
                .filter(
                    Refund.tenant_id == tenant_id,
                    Refund.refund_reference == idempotency_key,
                )
                .first()
            )
            if existing_idemp:
                if (
                    existing_idemp.invoice_id != invoice_id
                    or existing_idemp.refund_amount != refund_amount
                    or existing_idemp.refund_method != refund_method
                ):
                    raise AppException("Idempotency key collision: refund request payload does not match existing refund")
                return existing_idemp

        _refund_mutex.acquire()
        try:
            invoice = (
                self.db.query(Invoice)
                .filter(
                    Invoice.id == invoice_id,
                    Invoice.tenant_id == tenant_id,
                )
                .with_for_update()
                .first()
            )
            if not invoice:
                raise NotFoundException("Invoice not found")

            if (refund_method or "").strip().lower() in ("store_credit", "wallet"):
                order = self.db.query(Order).filter(Order.id == invoice.order_id).first()
                customer_id = (order.customer_id if order else None) or getattr(invoice, "customer_id", None)
                if not customer_id:
                    raise AppException("Store credit refund requires a registered customer on the invoice/order")


            completed_payments = (
                self.db.query(func.coalesce(func.sum(Payment.amount), 0))
                .filter(
                    Payment.invoice_id == invoice_id,
                    Payment.status == PaymentStatus.COMPLETED.value,
                )
                .scalar()
            )
            paid_amount = Decimal(str(completed_payments))
            eligible_paid_amount = (
                invoice.total_amount
                if (paid_amount <= Decimal("0") and invoice.status == "paid")
                else (min(paid_amount, invoice.total_amount) if paid_amount > Decimal("0") else invoice.total_amount)
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
                .with_for_update()
                .scalar()
            )
            total_active = Decimal(str(existing_refunds))

            if total_active + refund_amount > eligible_paid_amount:
                raise AppException(
                    f"Cumulative refund amount ({total_active + refund_amount}) cannot exceed eligible paid amount ({eligible_paid_amount})"
                )

            approver_user_id = approved_by
            if approver_user_id is not None:
                approver = (
                    self.db.query(User)
                    .filter(
                        User.id == approver_user_id,
                        User.tenant_id == tenant_id,
                    )
                    .first()
                )
                if not approver:
                    raise AppException(
                        f"Approver user {approver_user_id} not found in this tenant"
                    )
            elif user and getattr(user, "id", None):
                approver_user_id = user.id

            refund = Refund(
                tenant_id=tenant_id,
                invoice_id=invoice_id,
                refund_amount=refund_amount,
                refund_method=refund_method,
                status=RefundStatus.PENDING.value,
                reason=reason,
                refund_reference=idempotency_key,
                approved_by=approver_user_id,
            )

            self.db.add(refund)
            if commit:
                self.db.commit()
                self.db.refresh(refund)
            else:
                self.db.flush()

            return refund
        except Exception:
            if commit:
                self.db.rollback()
            raise
        finally:
            _refund_mutex.release()

    def approve_refund(
        self,
        tenant_id: int,
        refund_id: int,
        approved_by_user_id: int,
        user: Optional[User] = None,
    ) -> Refund:
        refund = (
            self.db.query(Refund)
            .filter(
                Refund.id == refund_id,
                Refund.tenant_id == tenant_id,
            )
            .with_for_update()
            .first()
        )

        if not refund:
            raise NotFoundException("Refund not found")

        self._approve_refund_internal(
            tenant_id=tenant_id,
            refund=refund,
            approved_by_user_id=approved_by_user_id,
            user=user,
            commit=True,
        )
        self.db.refresh(refund)
        return refund

    def _approve_refund_internal(
        self,
        tenant_id: int,
        refund: Refund,
        approved_by_user_id: int,
        user: Optional[User] = None,
        return_id: Optional[int] = None,
        commit: bool = True,
    ) -> CreditNote:
        if refund.status != RefundStatus.PENDING.value:
            raise AppException(
                "Only pending refunds can be approved"
            )

        invoice = (
            self.db.query(Invoice)
            .filter(
                Invoice.id == refund.invoice_id,
                Invoice.tenant_id == tenant_id,
            )
            .with_for_update()
            .first()
        )
        if not invoice:
            raise NotFoundException("Invoice not found")

        self.get_invoice(
            tenant_id,
            refund.invoice_id,
            user=user,
        )

        prior_approved = (
            self.db.query(func.coalesce(func.sum(Refund.refund_amount), 0))
            .filter(
                Refund.invoice_id == refund.invoice_id,
                Refund.id != refund.id,
                Refund.status == RefundStatus.APPROVED.value,
            )
            .scalar()
        )
        if Decimal(str(prior_approved)) + refund.refund_amount > invoice.total_amount:
            raise AppException("Approved refund exceeds invoice total")

        refund.status = RefundStatus.APPROVED.value
        refund.approved_by = approved_by_user_id
        self.db.flush()

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
            commit=commit,
        )

        gst = self._credit_note_gst_breakdown(
            invoice,
            refund.refund_amount,
        )

        from datetime import timedelta
        order = self.db.query(Order).filter(Order.id == invoice.order_id).first() if invoice.order_id else None
        customer_id = order.customer_id if order else None

        credit_note = CreditNote(
            tenant_id=tenant_id,
            credit_note_no=self._generate_credit_note_number(
                tenant_id, store_id=invoice.store_id
            ),
            invoice_id=refund.invoice_id,
            refund_id=refund.id,
            refund_amount=refund.refund_amount,
            balance_amount=refund.refund_amount,
            status="issued",
            customer_id=customer_id,
            valid_until=datetime.utcnow() + timedelta(days=90),
            cgst_amount=gst["cgst_amount"],
            sgst_amount=gst["sgst_amount"],
            igst_amount=gst["igst_amount"],
            return_id=return_id,
        )

        self.db.add(credit_note)

        total_approved = Decimal(str(prior_approved)) + refund.refund_amount
        if total_approved >= invoice.total_amount:
            invoice.status = "refunded"
            order = (
                self.db.query(Order)
                .filter(Order.id == invoice.order_id)
                .with_for_update()
                .first()
            )
            if order:
                order.status = OrderStatus.REFUNDED.value

        # Credit customer wallet if refund method is store_credit / wallet
        if refund.refund_method and refund.refund_method.lower() in ("store_credit", "wallet"):
            from app.models.customer import CustomerWallet, WalletTransaction
            order = self.db.query(Order).filter(Order.id == invoice.order_id).first()
            customer_id = order.customer_id if order else getattr(invoice, "customer_id", None)
            if customer_id:
                wallet = (
                    self.db.query(CustomerWallet)
                    .filter(CustomerWallet.customer_id == customer_id)
                    .with_for_update()
                    .first()
                )
                if not wallet:
                    wallet = CustomerWallet(
                        customer_id=customer_id,
                        current_balance=Decimal("0.00"),
                    )
                    self.db.add(wallet)
                    self.db.flush()
                wallet.current_balance = Decimal(str(wallet.current_balance or 0)) + refund.refund_amount
                tx = WalletTransaction(
                    wallet_id=wallet.id,
                    amount=refund.refund_amount,
                    transaction_type="CREDIT",
                    reference_no=credit_note.credit_note_no,
                    remarks=f"Store credit refund for invoice {invoice.invoice_number}"[:255],
                )
                self.db.add(tx)

        if commit:
            self.db.commit()
        else:
            self.db.flush()

        return credit_note

    def reject_refund(
        self,
        tenant_id: int,
        refund_id: int,
        reason: Optional[str] = None,
        user: Optional[User] = None,
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

        self.get_invoice(tenant_id, refund.invoice_id, user=user)

        if refund.status != RefundStatus.PENDING.value:
            raise AppException(
                "Only pending refunds can be rejected"
            )

        refund.status = RefundStatus.REJECTED.value
        if reason:
            cleaned_reason = reason.strip()
            if cleaned_reason:
                refund.reason = (f"{refund.reason} [Rejected: {cleaned_reason}]").strip() if refund.reason else f"[Rejected: {cleaned_reason}]"

        AuditService(self.db).log(
            tenant_id,
            user.id if user else None,
            "refund_rejected",
            "refund",
            refund.id,
            {
                "invoice_id": refund.invoice_id,
                "refund_amount": str(refund.refund_amount),
                "rejection_reason": reason,
            },
        )

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
        refund_method: str = "store_credit",
        valid_days: int = 90,
        notes: Optional[str] = None,
        user: Optional[User] = None,
    ) -> CreditNote:
        from datetime import timedelta

        refund = self.create_refund(
            tenant_id,
            invoice_id,
            refund_amount,
            refund_method,
            reason,
            user=user,
        )

        self.approve_refund(
            tenant_id,
            refund.id,
            approved_by_user_id,
            user=user,
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

        if notes:
            credit_note.notes = notes
        if valid_days:
            credit_note.valid_until = datetime.utcnow() + timedelta(days=valid_days)
        self.db.commit()
        self.db.refresh(credit_note)

        return credit_note

    def get_refund(
        self,
        tenant_id: int,
        refund_id: int,
        user: Optional[User] = None,
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

        self.get_invoice(tenant_id, refund.invoice_id, user=user)

        return refund

    def list_refunds(
        self,
        tenant_id: int,
        invoice_id: int | None = None,
        store_id: int | None = None,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        user: Optional[User] = None,
        system_context: bool = False,
    ) -> list[Refund]:
        query = self.db.query(Refund).filter(
            Refund.tenant_id == tenant_id
        )

        if invoice_id is not None:
            self.get_invoice(tenant_id, invoice_id, user=user, system_context=system_context)
            query = query.filter(
                Refund.invoice_id == invoice_id
            )
        elif not system_context:
            if user is None:
                raise ForbiddenException("Access denied: user context required")
            effective_store_id = user.store_id if user.store_id is not None else store_id
            if effective_store_id is not None:
                query = query.join(
                    Invoice,
                    Refund.invoice_id == Invoice.id,
                ).filter(Invoice.store_id == effective_store_id)
            elif not is_tenant_wide_authorized(user, self.db):
                raise ForbiddenException("Access denied: user has no assigned store")

        if status:
            query = query.filter(func.lower(Refund.status) == status.strip().lower())

        if date_from:
            query = query.filter(Refund.created_at >= date_from)

        if date_to:
            query = query.filter(Refund.created_at <= date_to)

        query = query.order_by(
            Refund.created_at.desc()
        )

        if page is not None and page_size is not None and page > 0 and page_size > 0:
            query = query.offset((page - 1) * page_size).limit(page_size)

        return query.all()

    def get_refund_receipt(
        self,
        tenant_id: int,
        refund_id: int,
        user: Optional[User] = None,
    ) -> dict:
        refund = self.get_refund(tenant_id, refund_id, user=user)
        invoice = self.get_invoice(tenant_id, refund.invoice_id, user=user)

        order = self.db.query(Order).filter(Order.id == invoice.order_id).first()
        store = self.db.query(Store).filter(Store.id == invoice.store_id).first() if invoice.store_id else None
        customer = self.db.query(Customer).filter(Customer.id == order.customer_id).first() if order and order.customer_id else None
        credit_note = self.db.query(CreditNote).filter(CreditNote.refund_id == refund.id).first()
        approver = self.db.query(User).filter(User.id == refund.approved_by).first() if refund.approved_by else None

        tenant = self.db.query(Tenant).filter(Tenant.id == tenant_id).first()

        from app.services.document_settings_service import DocumentSettingsService
        _ref_store_id = store.id if store else (getattr(invoice, "store_id", None) if invoice else None)
        ref_branding = DocumentSettingsService(self.db).resolve_branding(
            tenant_id=tenant_id,
            store_id=_ref_store_id,
        )
        store_name = ref_branding.business_name or (store.name if store else "Retail Store")
        store_address = ref_branding.address or (store.address if store and store.address else (tenant.address if tenant else None))
        store_phone = ref_branding.phone or (store.phone if store and store.phone else (tenant.phone if tenant else None))
        gstin = (ref_branding.gstin if ref_branding.show_gstin else None) or (store.gstin if store and store.gstin else (tenant.gstin if hasattr(tenant, "gstin") else None))

        cust_name = customer.name if customer else "Walk-in Customer"
        cust_phone = customer.phone if customer else "N/A"
        approver_name = approver.full_name if approver else "System"
        cn_no = credit_note.credit_note_no if credit_note else "N/A"

        sep = "=" * 32
        dashes = "-" * 32
        created_str = refund.created_at.strftime("%Y-%m-%d %H:%M:%S") if refund.created_at else ""

        status_str = (refund.status or "APPROVED").upper()
        method_str = (refund.refund_method or "CASH").upper()

        thermal_lines = [
            sep,
            f"{store_name.center(32)}",
            "REFUND PAYMENT VOUCHER".center(32),
            sep,
            f"Voucher No   : REF-{refund.id}",
            f"Invoice No   : {invoice.invoice_number}",
            f"Credit Note  : {cn_no}",
            f"Date         : {created_str}",
            f"Status       : {status_str}",
            dashes,
            f"Customer     : {cust_name}",
            f"Phone        : {cust_phone}",
            dashes,
            f"Refund Mode  : {method_str}",
            f"REFUND TOTAL : Rs. {refund.refund_amount:.2f}",
            dashes,
            f"Reason       : {refund.reason or 'Customer return'}",
            f"Approved By  : {approver_name}",
            sep,
            "Customer Signature: ____________".center(32),
            "Thank You!".center(32),
            sep,
        ]
        thermal_text = "\n".join(thermal_lines)

        return {
            "refund_id": refund.id,
            "invoice_id": invoice.id,
            "invoice_number": invoice.invoice_number,
            "credit_note_no": cn_no if credit_note else None,
            "refund_amount": refund.refund_amount,
            "refund_method": refund.refund_method,
            "status": refund.status,
            "reason": refund.reason,
            "customer_name": cust_name,
            "customer_phone": cust_phone,
            "store_name": store_name,
            "store_address": store_address,
            "store_phone": store_phone,
            "gstin": gstin,
            "logo_url": ref_branding.logo_url,
            "approved_by_name": approver_name,
            "created_at": refund.created_at,
            "thermal_text": thermal_text,
        }

    def _generate_refund_receipt_image(self, ctx: Dict[str, Any]) -> bytes:
        from PIL import Image, ImageDraw, ImageFont

        width = 576  # Standard 80mm printable width at 203 DPI
        est_height = 680

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

        # Logo rendering from DocumentSettings
        logo_url = ctx.get("logo_url")
        if logo_url:
            try:
                logo_file = self._find_logo_file(logo_url)
                if logo_file and logo_file.is_file():
                    raw_logo = Image.open(str(logo_file))
                    if raw_logo.mode in ("RGBA", "LA") or (raw_logo.mode == "P" and "transparency" in raw_logo.info):
                        rgba = raw_logo.convert("RGBA")
                        bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
                        flat = Image.alpha_composite(bg, rgba).convert("RGB")
                    else:
                        flat = raw_logo.convert("RGB")
                    max_w, max_h = 240.0, 55.0
                    aspect = flat.width / float(flat.height)
                    if (max_w / aspect) <= max_h:
                        logo_draw_w = int(max_w)
                        logo_draw_h = int(max_w / aspect)
                    else:
                        logo_draw_h = int(max_h)
                        logo_draw_w = int(max_h * aspect)
                    logo_img = flat.resize((logo_draw_w, logo_draw_h), Image.LANCZOS)
                    logo_x = (width - logo_draw_w) // 2
                    img.paste(logo_img, (logo_x, y))
                    y += logo_draw_h + 8
            except Exception:
                pass

        # Store Title centered
        store_txt = str(ctx.get("store_name", "RETAIL STORE")).upper()
        bbox = draw.textbbox((0, 0), store_txt, font=font_title)
        draw.text(((width - (bbox[2] - bbox[0])) // 2, y), store_txt, font=font_title, fill=(0, 0, 0))
        y += 28

        # Store address / phone / gstin if available
        if ctx.get("store_address"):
            addr_txt = str(ctx.get("store_address"))[:65]
            abbox = draw.textbbox((0, 0), addr_txt, font=font_small)
            draw.text(((width - (abbox[2] - abbox[0])) // 2, y), addr_txt, font=font_small, fill=(100, 100, 100))
            y += 18
        if ctx.get("store_phone"):
            p_txt = f"Tel: {ctx.get('store_phone')}"
            pbbox = draw.textbbox((0, 0), p_txt, font=font_small)
            draw.text(((width - (pbbox[2] - pbbox[0])) // 2, y), p_txt, font=font_small, fill=(100, 100, 100))
            y += 18
        if ctx.get("gstin"):
            g_txt = f"GSTIN: {ctx.get('gstin')}"
            gbbox = draw.textbbox((0, 0), g_txt, font=font_small)
            draw.text(((width - (gbbox[2] - gbbox[0])) // 2, y), g_txt, font=font_small, fill=(50, 50, 50))
            y += 18

        # Voucher Header centered
        rep_txt = "REFUND PAYMENT VOUCHER"
        bbox = draw.textbbox((0, 0), rep_txt, font=font_head)
        draw.text(((width - (bbox[2] - bbox[0])) // 2, y), rep_txt, font=font_head, fill=(185, 28, 28))
        y += 24

        sub_txt = "OFFICIAL REFUND SETTLEMENT SLIP"
        bbox = draw.textbbox((0, 0), sub_txt, font=font_small)
        draw.text(((width - (bbox[2] - bbox[0])) // 2, y), sub_txt, font=font_small, fill=(100, 100, 100))
        y += 22

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

        # Voucher Details
        draw_kv("Voucher No", f"REF-{ctx.get('refund_id')}")
        draw_kv("Invoice No", str(ctx.get("invoice_number", "")))
        if ctx.get("credit_note_no"):
            draw_kv("Credit Note", str(ctx.get("credit_note_no")))
        created_at = ctx.get("created_at")
        dt_str = created_at.strftime("%Y-%m-%d %H:%M:%S") if isinstance(created_at, datetime) else str(created_at or "")
        draw_kv("Date & Time", dt_str)
        status_val = str(ctx.get("status", "APPROVED")).upper()
        draw_kv("Status", status_val, fill_r=(22, 101, 52) if status_val == "APPROVED" else (185, 28, 28))

        y += 4
        draw_dashed_line(draw, y, width)
        y += 12

        # Customer Details
        draw_kv("Customer", str(ctx.get("customer_name", "Walk-in Customer")))
        draw_kv("Phone", str(ctx.get("customer_phone", "N/A")))

        y += 4
        draw_dashed_line(draw, y, width)
        y += 12

        # Payment & Amount Banner Box
        draw_kv("Refund Mode", str(ctx.get("refund_method", "CASH")).upper())
        y += 6

        # Refund Total Box
        tot_box_top = y
        draw.rectangle([(20, tot_box_top), (width - 20, tot_box_top + 42)], fill=(254, 242, 242), outline=(239, 68, 68), width=1)
        draw.text((32, tot_box_top + 10), "REFUND TOTAL", font=font_bold, fill=(153, 27, 27))
        amt_str = f"Rs. {Decimal(str(ctx.get('refund_amount', 0))):.2f}"
        amt_bbox = draw.textbbox((0, 0), amt_str, font=font_big)
        amt_w = amt_bbox[2] - amt_bbox[0]
        draw.text((width - 32 - amt_w, tot_box_top + 10), amt_str, font=font_big, fill=(185, 28, 28))
        y += 54

        draw_dashed_line(draw, y, width)
        y += 12

        # Audit & Reason
        reason_txt = str(ctx.get("reason") or "Customer return")[:45]
        draw_kv("Reason", reason_txt, font_r=font_regular)
        draw_kv("Approved By", str(ctx.get("approved_by_name", "System")))

        y += 4
        draw_dashed_line(draw, y, width)
        y += 24

        # Signatures
        draw.text((24, y), "Customer Signature: ____________", font=font_small, fill=(60, 60, 60))
        y += 30
        ty_txt = "Thank You! Please visit again."
        ty_bbox = draw.textbbox((0, 0), ty_txt, font=font_small)
        draw.text(((width - (ty_bbox[2] - ty_bbox[0])) // 2, y), ty_txt, font=font_small, fill=(100, 100, 100))
        y += 26

        # Final crop to actual height
        final_height = y + 15
        final_img = img.crop((0, 0, width, final_height))
        draw_final = ImageDraw.Draw(final_img)
        draw_final.rectangle([(6, 6), (width - 7, final_height - 7)], outline=(200, 200, 200), width=1)

        buf = io.BytesIO()
        final_img.save(buf, format="PNG")
        return buf.getvalue()

    def _generate_refund_receipt_html(self, ctx: Dict[str, Any], auto_print: bool = False) -> str:
        created_at = ctx.get("created_at")
        dt_str = created_at.strftime("%Y-%m-%d %H:%M:%S") if isinstance(created_at, datetime) else str(created_at or "")
        status_str = str(ctx.get("status", "APPROVED")).upper()
        amt_str = f"{Decimal(str(ctx.get('refund_amount', 0))):.2f}"
        auto_print_script = "<script>window.onload = function() { window.print(); };</script>" if auto_print else ""

        store_addr_html = f'<div class="store-sub">{ctx["store_address"]}</div>' if ctx.get("store_address") else ""
        store_phone_html = f'<div class="store-sub">Tel: {ctx["store_phone"]}</div>' if ctx.get("store_phone") else ""
        gstin_html = f'<div class="store-sub">GSTIN: {ctx["gstin"]}</div>' if ctx.get("gstin") else ""
        cn_html = f'<div class="row"><span class="lbl">Credit Note</span><span class="val">{ctx["credit_note_no"]}</span></div>' if ctx.get("credit_note_no") else ""

        logo_html = ""
        logo_url = ctx.get("logo_url")
        if logo_url:
            logo_file = self._find_logo_file(logo_url)
            if logo_file and logo_file.is_file():
                try:
                    import base64
                    ext = logo_file.suffix.lower().replace(".", "")
                    mime = "image/png" if ext == "png" else "image/jpeg"
                    with open(logo_file, "rb") as _f:
                        b64_data = base64.b64encode(_f.read()).decode("utf-8")
                    logo_html = f'<div style="text-align: center; margin-bottom: 8px;"><img src="data:{mime};base64,{b64_data}" alt="Logo" style="max-height: 50px; max-width: 180px; object-fit: contain; " /></div>'
                except Exception:
                    logo_html = f'<div style="text-align: center; margin-bottom: 8px;"><img src="{logo_url}" alt="Logo" style="max-height: 50px; max-width: 180px; object-fit: contain; " /></div>'
            else:
                logo_html = f'<div style="text-align: center; margin-bottom: 8px;"><img src="{logo_url}" alt="Logo" style="max-height: 50px; max-width: 180px; object-fit: contain; " /></div>'

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Refund Voucher REF-{ctx.get('refund_id')}</title>
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
    border-radius: 8px;
    padding: 16px;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    color: #111827;
    font-size: 13px;
    line-height: 1.4;
  }}
  .store-name {{
    font-size: 18px;
    font-weight: 800;
    text-align: center;
    text-transform: uppercase;
    margin-bottom: 2px;
  }}
  .store-sub {{
    font-size: 11px;
    text-align: center;
    color: #6b7280;
  }}
  .voucher-title {{
    font-size: 14px;
    font-weight: 700;
    text-align: center;
    color: #b91c1c;
    margin-top: 8px;
    letter-spacing: 0.5px;
  }}
  .voucher-subtitle {{
    font-size: 10px;
    text-align: center;
    color: #6b7280;
    margin-bottom: 10px;
  }}
  .divider {{
    border-top: 1px dashed #9ca3af;
    margin: 10px 0;
  }}
  .row {{
    display: flex;
    justify-content: space-between;
    margin: 4px 0;
  }}
  .lbl {{
    color: #4b5563;
  }}
  .val {{
    font-weight: 600;
    color: #111827;
  }}
  .status-badge {{
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: bold;
    background: #dcfce7;
    color: #15803d;
  }}
  .amount-card {{
    background: #fef2f2;
    border: 1px solid #fecaca;
    border-radius: 6px;
    padding: 8px 12px;
    margin: 10px 0;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }}
  .amount-lbl {{
    font-weight: bold;
    color: #991b1b;
  }}
  .amount-val {{
    font-size: 16px;
    font-weight: 800;
    color: #b91c1c;
  }}
  .signature-box {{
    margin-top: 18px;
    font-size: 11px;
    color: #4b5563;
  }}
  .footer-msg {{
    text-align: center;
    font-size: 11px;
    color: #6b7280;
    margin-top: 12px;
  }}
  @media print {{
    body {{
      background: none;
      padding: 0;
    }}
    .ticket {{
      box-shadow: none;
      border: none;
      width: 100%;
    }}
  }}
</style>
</head>
<body>
<div class="ticket">
  {logo_html}
  <div class="store-name">{ctx.get('store_name', 'Retail Store')}</div>
  {store_addr_html}
  {store_phone_html}
  {gstin_html}
  <div class="voucher-title">REFUND PAYMENT VOUCHER</div>
  <div class="voucher-subtitle">OFFICIAL REFUND SETTLEMENT SLIP</div>
  <div class="divider"></div>
  <div class="row"><span class="lbl">Voucher No</span><span class="val">REF-{ctx.get('refund_id')}</span></div>
  <div class="row"><span class="lbl">Invoice No</span><span class="val">{ctx.get('invoice_number')}</span></div>
  {cn_html}
  <div class="row"><span class="lbl">Date & Time</span><span class="val">{dt_str}</span></div>
  <div class="row"><span class="lbl">Status</span><span class="status-badge">{status_str}</span></div>
  <div class="divider"></div>
  <div class="row"><span class="lbl">Customer</span><span class="val">{ctx.get('customer_name', 'Walk-in Customer')}</span></div>
  <div class="row"><span class="lbl">Phone</span><span class="val">{ctx.get('customer_phone', 'N/A')}</span></div>
  <div class="divider"></div>
  <div class="row"><span class="lbl">Refund Mode</span><span class="val">{str(ctx.get('refund_method', 'CASH')).upper()}</span></div>
  <div class="amount-card">
    <span class="amount-lbl">REFUND TOTAL</span>
    <span class="amount-val">Rs. {amt_str}</span>
  </div>
  <div class="divider"></div>
  <div class="row"><span class="lbl">Reason</span><span class="val">{ctx.get('reason') or 'Customer return'}</span></div>
  <div class="row"><span class="lbl">Approved By</span><span class="val">{ctx.get('approved_by_name', 'System')}</span></div>
  <div class="divider"></div>
  <div class="signature-box">Customer Signature: __________________</div>
  <div class="footer-msg">Thank You! Please visit again.</div>
</div>
{auto_print_script}
</body>
</html>"""

    def _generate_refund_receipt_pdf(self, ctx: Dict[str, Any]) -> bytes:
        from PIL import Image
        from reportlab.lib.utils import ImageReader
        from reportlab.pdfgen import canvas

        img_bytes = self._generate_refund_receipt_image(ctx)
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

    def export_refund_receipt_thermal(
        self,
        user: User,
        refund_id: int,
        mode: Any = "preview",
        request: Optional[Any] = None,
    ) -> Response:
        receipt_data = self.get_refund_receipt(user.tenant_id, refund_id, user=user)

        mode_val = str(getattr(mode, "value", mode) or "preview").lower().strip()

        # Check if caller wants JSON (e.g. Accept: application/json without explicit query param)
        if request is not None and hasattr(request, "query_params") and hasattr(request, "headers"):
            if "mode" not in request.query_params and "application/json" in request.headers.get("accept", ""):
                mode_val = "json"

        # 1. Preview mode (Default) -> Visual 80mm receipt PNG rendered directly in Swagger UI
        if mode_val == RefundThermalMode.preview.value:
            img_bytes = self._generate_refund_receipt_image(receipt_data)
            return Response(
                content=img_bytes,
                media_type="image/png",
                headers={
                    "Content-Disposition": f"inline; filename=refund_receipt_{refund_id}_thermal.png",
                    "X-Refund-Print-Type": "80mm-PNG-Preview",
                },
            )

        # 2. View mode -> Inline styled HTML page with auto-print dialog
        if mode_val == RefundThermalMode.view.value:
            html_content = self._generate_refund_receipt_html(receipt_data, auto_print=True)
            return HTMLResponse(
                content=html_content,
                status_code=200,
                headers={"Content-Disposition": f"inline; filename=refund_receipt_{refund_id}_thermal.html"},
            )

        # 3. Download mode -> ESC/POS text file attachment download
        if mode_val == RefundThermalMode.download.value:
            text_payload = receipt_data["thermal_text"]
            return Response(
                content=text_payload.encode("utf-8"),
                media_type="text/plain; charset=utf-8",
                headers={
                    "Content-Disposition": f"attachment; filename=refund_receipt_{refund_id}_thermal.txt",
                    "X-Refund-Print-Type": "ESC/POS",
                },
            )

        # 4. PDF mode -> 80mm Thermal Receipt PDF download
        if mode_val == RefundThermalMode.pdf.value:
            pdf_bytes = self._generate_refund_receipt_pdf(receipt_data)
            return Response(
                content=pdf_bytes,
                media_type="application/pdf",
                headers={
                    "Content-Disposition": f"attachment; filename=refund_receipt_{refund_id}_thermal.pdf",
                    "X-Refund-Print-Type": "80mm-PDF",
                },
            )

        # 5. HTML mode -> Styled raw HTML layout
        if mode_val == RefundThermalMode.html.value:
            html_content = self._generate_refund_receipt_html(receipt_data, auto_print=False)
            return HTMLResponse(
                content=html_content,
                status_code=200,
                headers={"Content-Disposition": f"inline; filename=refund_receipt_{refund_id}_thermal.html"},
            )

        # 6. JSON mode -> Structured JSON payload
        if mode_val == RefundThermalMode.json.value:
            html_content = self._generate_refund_receipt_html(receipt_data, auto_print=False)
            response_data = RefundThermalResponse(
                success=True,
                message="Refund receipt voucher generated successfully",
                refund_id=receipt_data["refund_id"],
                invoice_id=receipt_data["invoice_id"],
                invoice_number=receipt_data["invoice_number"],
                credit_note_no=receipt_data.get("credit_note_no"),
                refund_amount=receipt_data["refund_amount"],
                refund_method=receipt_data["refund_method"],
                status=receipt_data["status"],
                reason=receipt_data.get("reason"),
                customer_name=receipt_data["customer_name"],
                customer_phone=receipt_data["customer_phone"],
                store_name=receipt_data["store_name"],
                approved_by_name=receipt_data["approved_by_name"],
                created_at=receipt_data["created_at"],
                thermal_text=receipt_data["thermal_text"],
                html=html_content,
            )
            return JSONResponse(content=response_data.model_dump(mode="json"))

        # 7. Text mode -> Raw ESC/POS text printer stream
        text_payload = receipt_data["thermal_text"]
        return Response(
            content=text_payload.encode("utf-8"),
            media_type="text/plain; charset=utf-8",
            headers={
                "Content-Disposition": f"inline; filename=refund_receipt_{refund_id}_thermal.txt",
                "X-Refund-Print-Type": "ESC/POS",
            },
        )

    def list_credit_notes(
        self,
        tenant_id: int,
        invoice_id: int | None = None,
        store_id: int | None = None,
        credit_note_no: Optional[str] = None,
        status: Optional[str] = None,
        customer_id: Optional[int] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
        user: Optional[User] = None,
        system_context: bool = False,
    ) -> list[CreditNote]:
        query = self.db.query(CreditNote).filter(
            CreditNote.tenant_id == tenant_id
        )

        if invoice_id is not None:
            self.get_invoice(tenant_id, invoice_id, user=user, system_context=system_context)
            query = query.filter(
                CreditNote.invoice_id == invoice_id
            )
        elif not system_context:
            if user is None:
                raise ForbiddenException("Access denied: user context required")
            effective_store_id = user.store_id if user.store_id is not None else store_id
            if effective_store_id is not None:
                query = query.join(
                    Invoice,
                    CreditNote.invoice_id == Invoice.id,
                ).filter(Invoice.store_id == effective_store_id)
            elif not is_tenant_wide_authorized(user, self.db):
                raise ForbiddenException("Access denied: user has no assigned store")

        if credit_note_no:
            query = query.filter(CreditNote.credit_note_no.ilike(f"%{credit_note_no.strip()}%"))

        if status:
            query = query.filter(func.lower(CreditNote.status) == status.strip().lower())

        if customer_id is not None:
            query = query.filter(CreditNote.customer_id == customer_id)

        if date_from:
            query = query.filter(CreditNote.created_at >= date_from)

        if date_to:
            query = query.filter(CreditNote.created_at <= date_to)

        query = query.order_by(
            CreditNote.created_at.desc()
        )

        if page is not None and page_size is not None and page > 0 and page_size > 0:
            query = query.offset((page - 1) * page_size).limit(page_size)

        return query.all()

    def get_credit_note(
        self,
        tenant_id: int,
        credit_note_id: int,
        user: Optional[User] = None,
        system_context: bool = False,
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

        self.get_invoice(tenant_id, credit_note.invoice_id, user=user, system_context=system_context)

        return credit_note

    def get_credit_note_by_number(
        self,
        tenant_id: int,
        credit_note_no: str,
        user: Optional[User] = None,
        system_context: bool = False,
    ) -> CreditNote:
        cn_num = credit_note_no.strip() if credit_note_no else ""
        if not cn_num:
            raise NotFoundException("Credit note number cannot be empty")

        credit_note = (
            self.db.query(CreditNote)
            .filter(
                CreditNote.tenant_id == tenant_id,
                CreditNote.credit_note_no == cn_num,
            )
            .first()
        )
        if not credit_note:
            raise NotFoundException(f"Credit note '{cn_num}' not found")

        self.get_invoice(tenant_id, credit_note.invoice_id, user=user, system_context=system_context)
        return credit_note

    def validate_credit_note(
        self,
        tenant_id: int,
        credit_note_no: str,
        bill_amount: Optional[Decimal] = None,
        user: Optional[User] = None,
    ) -> dict:
        cn = self.get_credit_note_by_number(tenant_id, credit_note_no, user=user)

        now_ts = datetime.utcnow()
        is_expired = False
        if cn.valid_until and cn.valid_until < now_ts:
            is_expired = True

        balance = cn.balance_amount if cn.balance_amount is not None else cn.refund_amount
        status = cn.status or "issued"

        is_valid = True
        msg = "Credit note is valid and available for redemption"

        if status not in ("issued", "partially_redeemed"):
            is_valid = False
            msg = f"Credit note cannot be redeemed: current status is '{status}'"
        elif is_expired:
            is_valid = False
            msg = f"Credit note expired on {cn.valid_until.strftime('%Y-%m-%d')}"
        elif balance <= Decimal("0.00"):
            is_valid = False
            msg = "Credit note has zero remaining balance"

        applicable_amt = Decimal("0.00")
        if is_valid and balance > Decimal("0.00"):
            if bill_amount is not None and bill_amount > Decimal("0.00"):
                applicable_amt = min(balance, bill_amount)
            else:
                applicable_amt = balance

        invoice = self.db.query(Invoice).filter(Invoice.id == cn.invoice_id).first()
        order = self.db.query(Order).filter(Order.id == invoice.order_id).first() if invoice and invoice.order_id else None
        customer = self.db.query(Customer).filter(Customer.id == (cn.customer_id or (order.customer_id if order else None))).first()

        return {
            "valid": is_valid,
            "credit_note_id": cn.id,
            "credit_note_no": cn.credit_note_no,
            "status": status,
            "total_amount": cn.refund_amount,
            "balance_amount": balance,
            "applicable_amount": applicable_amt,
            "customer_id": customer.id if customer else None,
            "customer_name": customer.name if customer else None,
            "customer_phone": customer.phone if customer else None,
            "valid_until": cn.valid_until,
            "is_expired": is_expired,
            "message": msg,
        }

    def redeem_credit_note(
        self,
        tenant_id: int,
        credit_note_no: str,
        amount_to_redeem: Decimal,
        invoice_id: Optional[int] = None,
        order_id: Optional[int] = None,
        notes: Optional[str] = None,
        user: Optional[User] = None,
    ) -> dict:
        from app.models.credit_note_redemption import CreditNoteRedemption

        if amount_to_redeem <= Decimal("0.00"):
            raise AppException("Redemption amount must be greater than zero")

        cn = (
            self.db.query(CreditNote)
            .filter(
                CreditNote.tenant_id == tenant_id,
                CreditNote.credit_note_no == credit_note_no.strip(),
            )
            .with_for_update()
            .first()
        )
        if not cn:
            raise NotFoundException(f"Credit note '{credit_note_no}' not found")

        self.get_invoice(tenant_id, cn.invoice_id, user=user)

        now_ts = datetime.utcnow()
        if cn.valid_until and cn.valid_until < now_ts:
            raise AppException(f"Cannot redeem: Credit note expired on {cn.valid_until.strftime('%Y-%m-%d')}")

        current_status = cn.status or "issued"
        if current_status not in ("issued", "partially_redeemed"):
            raise AppException(f"Cannot redeem credit note with status '{current_status}'")

        current_balance = cn.balance_amount if cn.balance_amount is not None else cn.refund_amount
        if amount_to_redeem > current_balance:
            raise AppException(
                f"Requested redemption amount ({amount_to_redeem}) exceeds available balance ({current_balance})"
            )

        new_balance = current_balance - amount_to_redeem
        cn.balance_amount = new_balance
        if new_balance == Decimal("0.00"):
            cn.status = "redeemed"
        else:
            cn.status = "partially_redeemed"

        redemption = CreditNoteRedemption(
            tenant_id=tenant_id,
            credit_note_id=cn.id,
            invoice_id=invoice_id,
            order_id=order_id,
            amount_redeemed=amount_to_redeem,
            notes=notes,
            created_by=user.id if user else None,
        )
        self.db.add(redemption)
        self.db.flush()

        AuditService(self.db).log(
            tenant_id,
            user.id if user else 0,
            "credit_note_redeemed",
            "credit_note",
            cn.id,
            {
                "credit_note_no": cn.credit_note_no,
                "amount_redeemed": str(amount_to_redeem),
                "remaining_balance": str(new_balance),
                "status": cn.status,
                "invoice_id": invoice_id,
            },
        )

        self.db.commit()
        self.db.refresh(cn)

        return {
            "success": True,
            "credit_note_id": cn.id,
            "credit_note_no": cn.credit_note_no,
            "amount_redeemed": amount_to_redeem,
            "remaining_balance": new_balance,
            "status": cn.status,
            "redemption_id": redemption.id,
            "message": f"Successfully redeemed Rs. {amount_to_redeem:.2f} from credit note {cn.credit_note_no}",
        }

    def get_credit_note_thermal_receipt(
        self,
        tenant_id: int,
        credit_note_id: int,
        user: Optional[User] = None,
    ) -> dict:
        credit_note = self.get_credit_note(tenant_id, credit_note_id, user=user)
        invoice = self.get_invoice(tenant_id, credit_note.invoice_id, user=user)

        order = self.db.query(Order).filter(Order.id == invoice.order_id).first() if invoice.order_id else None
        store = self.db.query(Store).filter(Store.id == invoice.store_id).first() if invoice.store_id else None
        customer = self.db.query(Customer).filter(Customer.id == (credit_note.customer_id or (order.customer_id if order else None))).first()

        tenant = self.db.query(Tenant).filter(Tenant.id == tenant_id).first()

        # Resolve branding from DocumentSettings hierarchy
        from app.services.document_settings_service import DocumentSettingsService
        _cn_store_id = store.id if store else (getattr(invoice, "store_id", None) if invoice else None)
        cn_branding = DocumentSettingsService(self.db).resolve_branding(
            tenant_id=tenant_id,
            store_id=_cn_store_id,
        )
        store_name = cn_branding.business_name or (store.name if store else "Retail Store")
        store_address = cn_branding.address or (store.address if store and store.address else (tenant.address if tenant else None))
        store_phone = cn_branding.phone or (store.phone if store and store.phone else (tenant.phone if tenant else None))
        gstin = (cn_branding.gstin if cn_branding.show_gstin else None) or (store.gstin if store and store.gstin else (tenant.gstin if hasattr(tenant, "gstin") else None))

        cust_name = customer.name if customer else "Walk-in Customer"
        cust_phone = customer.phone if customer else "N/A"
        valid_until_str = credit_note.valid_until.strftime("%Y-%m-%d") if credit_note.valid_until else "No Expiry"
        created_str = credit_note.created_at.strftime("%Y-%m-%d %H:%M") if credit_note.created_at else ""

        bal = credit_note.balance_amount if credit_note.balance_amount is not None else credit_note.refund_amount
        stat = (credit_note.status or "ISSUED").upper()

        sep = "=" * 32
        dashes = "-" * 32

        thermal_lines = [
            sep,
            f"{store_name.center(32)}",
            "CREDIT NOTE VOUCHER".center(32),
            sep,
            f"Credit Note No: {credit_note.credit_note_no}",
            f"Ref Invoice   : {invoice.invoice_number}",
            f"Date Issued   : {created_str}",
            f"Valid Until   : {valid_until_str}",
            f"Status        : {stat}",
            dashes,
            f"Customer      : {cust_name}",
            f"Phone         : {cust_phone}",
            dashes,
            f"CREDIT AMOUNT : Rs. {credit_note.refund_amount:.2f}",
            f"CGST Amount   : Rs. {credit_note.cgst_amount:.2f}",
            f"SGST Amount   : Rs. {credit_note.sgst_amount:.2f}",
            f"IGST Amount   : Rs. {credit_note.igst_amount:.2f}",
            dashes,
            f"BALANCE DUE   : Rs. {bal:.2f}",
            sep,
            "Use this note for future store".center(32),
            "purchases before expiry date.".center(32),
            sep,
            "Customer Signature: ____________".center(32),
            "Authorized Signature: __________".center(32),
            sep,
        ]
        thermal_text = "\n".join(thermal_lines)

        return {
            "credit_note_id": credit_note.id,
            "credit_note_no": credit_note.credit_note_no,
            "invoice_id": invoice.id,
            "invoice_number": invoice.invoice_number,
            "refund_amount": credit_note.refund_amount,
            "balance_amount": bal,
            "cgst_amount": credit_note.cgst_amount or Decimal("0.00"),
            "sgst_amount": credit_note.sgst_amount or Decimal("0.00"),
            "igst_amount": credit_note.igst_amount or Decimal("0.00"),
            "status": credit_note.status or "issued",
            "customer_name": cust_name,
            "customer_phone": cust_phone,
            "store_name": store_name,
            "store_address": store_address,
            "store_phone": store_phone,
            "gstin": gstin,
            "valid_until": valid_until_str,
            "created_at": credit_note.created_at,
            "thermal_text": thermal_text,
            "logo_url": cn_branding.logo_url,
        }

    def _generate_credit_note_thermal_image(self, ctx: Dict[str, Any]) -> bytes:
        from PIL import Image, ImageDraw, ImageFont

        width = 576  # Standard 80mm printable width at 203 DPI
        est_height = 680

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

        # Logo rendering from DocumentSettings
        logo_url = ctx.get("logo_url")
        if logo_url:
            try:
                logo_file = self._find_logo_file(logo_url)
                if logo_file and logo_file.is_file():
                    raw_logo = Image.open(str(logo_file))
                    if raw_logo.mode in ("RGBA", "LA") or (raw_logo.mode == "P" and "transparency" in raw_logo.info):
                        rgba = raw_logo.convert("RGBA")
                        bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
                        flat = Image.alpha_composite(bg, rgba).convert("RGB")
                    else:
                        flat = raw_logo.convert("RGB")
                    max_w, max_h = 240.0, 55.0
                    aspect = flat.width / float(flat.height)
                    if (max_w / aspect) <= max_h:
                        logo_draw_w = int(max_w)
                        logo_draw_h = int(max_w / aspect)
                    else:
                        logo_draw_h = int(max_h)
                        logo_draw_w = int(max_h * aspect)
                    logo_img = flat.resize((logo_draw_w, logo_draw_h), Image.LANCZOS)
                    logo_x = (width - logo_draw_w) // 2
                    img.paste(logo_img, (logo_x, y))
                    y += logo_draw_h + 8
            except Exception:
                pass

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
        if ctx.get("store_phone"):
            p_txt = f"Tel: {ctx.get('store_phone')}"
            pbbox = draw.textbbox((0, 0), p_txt, font=font_small)
            draw.text(((width - (pbbox[2] - pbbox[0])) // 2, y), p_txt, font=font_small, fill=(100, 100, 100))
            y += 18
        if ctx.get("gstin"):
            g_txt = f"GSTIN: {ctx.get('gstin')}"
            gbbox = draw.textbbox((0, 0), g_txt, font=font_small)
            draw.text(((width - (gbbox[2] - gbbox[0])) // 2, y), g_txt, font=font_small, fill=(50, 50, 50))
            y += 18

        # Header centered
        rep_txt = "CREDIT NOTE VOUCHER"
        bbox = draw.textbbox((0, 0), rep_txt, font=font_head)
        draw.text(((width - (bbox[2] - bbox[0])) // 2, y), rep_txt, font=font_head, fill=(30, 64, 175))
        y += 24

        sub_txt = "OFFICIAL STORE CREDIT SLIP"
        bbox = draw.textbbox((0, 0), sub_txt, font=font_small)
        draw.text(((width - (bbox[2] - bbox[0])) // 2, y), sub_txt, font=font_small, fill=(100, 100, 100))
        y += 22

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

        # Voucher Details
        draw_kv("Credit Note No", str(ctx.get("credit_note_no", "")))
        draw_kv("Ref Invoice No", str(ctx.get("invoice_number", "")))
        created_at = ctx.get("created_at")
        dt_str = created_at.strftime("%Y-%m-%d %H:%M") if isinstance(created_at, datetime) else str(created_at or "")
        draw_kv("Date Issued", dt_str)
        draw_kv("Valid Until", str(ctx.get("valid_until", "No Expiry")))
        status_val = str(ctx.get("status", "ISSUED")).upper()
        draw_kv("Status", status_val, fill_r=(22, 101, 52) if status_val in ("ISSUED", "ACTIVE") else (185, 28, 28))

        y += 4
        draw_dashed_line(draw, y, width)
        y += 12

        # Customer Details
        draw_kv("Customer", str(ctx.get("customer_name", "Walk-in Customer")))
        draw_kv("Phone", str(ctx.get("customer_phone", "N/A")))

        y += 4
        draw_dashed_line(draw, y, width)
        y += 12

        # Credit Amount Highlight Box
        tot_box_top = y
        draw.rectangle([(20, tot_box_top), (width - 20, tot_box_top + 42)], fill=(239, 246, 255), outline=(59, 130, 246), width=1)
        draw.text((32, tot_box_top + 10), "CREDIT AMOUNT", font=font_bold, fill=(30, 64, 175))
        amt_str = f"Rs. {Decimal(str(ctx.get('refund_amount', 0))):.2f}"
        amt_bbox = draw.textbbox((0, 0), amt_str, font=font_big)
        amt_w = amt_bbox[2] - amt_bbox[0]
        draw.text((width - 32 - amt_w, tot_box_top + 10), amt_str, font=font_big, fill=(30, 64, 175))
        y += 54

        bal_str = f"Rs. {Decimal(str(ctx.get('balance_amount', ctx.get('refund_amount', 0)))):.2f}"
        draw_kv("BALANCE DUE", bal_str, font_l=font_bold, font_r=font_bold, fill_l=(0, 0, 0), fill_r=(22, 101, 52))

        y += 4
        draw_dashed_line(draw, y, width)
        y += 14

        # Notice & Signatures
        note_txt1 = "Use this note for future store"
        n1_bbox = draw.textbbox((0, 0), note_txt1, font=font_small)
        draw.text(((width - (n1_bbox[2] - n1_bbox[0])) // 2, y), note_txt1, font=font_small, fill=(90, 90, 90))
        y += 18
        note_txt2 = "purchases before expiry date."
        n2_bbox = draw.textbbox((0, 0), note_txt2, font=font_small)
        draw.text(((width - (n2_bbox[2] - n2_bbox[0])) // 2, y), note_txt2, font=font_small, fill=(90, 90, 90))
        y += 24

        draw.text((24, y), "Customer Signature: ____________", font=font_small, fill=(60, 60, 60))
        y += 22
        draw.text((24, y), "Authorized Signature: __________", font=font_small, fill=(60, 60, 60))
        y += 28

        ty_txt = "Thank You! Please visit again."
        ty_bbox = draw.textbbox((0, 0), ty_txt, font=font_small)
        draw.text(((width - (ty_bbox[2] - ty_bbox[0])) // 2, y), ty_txt, font=font_small, fill=(100, 100, 100))
        y += 26

        # Final crop to actual height
        final_height = y + 15
        final_img = img.crop((0, 0, width, final_height))
        draw_final = ImageDraw.Draw(final_img)
        draw_final.rectangle([(6, 6), (width - 7, final_height - 7)], outline=(200, 200, 200), width=1)

        buf = io.BytesIO()
        final_img.save(buf, format="PNG")
        return buf.getvalue()

    def _generate_credit_note_thermal_html(self, ctx: Dict[str, Any], auto_print: bool = False) -> str:
        created_at = ctx.get("created_at")
        dt_str = created_at.strftime("%Y-%m-%d %H:%M") if isinstance(created_at, datetime) else str(created_at or "")
        status_str = str(ctx.get("status", "ISSUED")).upper()
        amt_str = f"{Decimal(str(ctx.get('refund_amount', 0))):.2f}"
        bal_str = f"{Decimal(str(ctx.get('balance_amount', ctx.get('refund_amount', 0)))):.2f}"
        auto_print_script = "<script>window.onload = function() { window.print(); };</script>" if auto_print else ""

        store_addr_html = f'<div class="store-sub">{ctx["store_address"]}</div>' if ctx.get("store_address") else ""
        store_phone_html = f'<div class="store-sub">Tel: {ctx["store_phone"]}</div>' if ctx.get("store_phone") else ""
        gstin_html = f'<div class="store-sub">GSTIN: {ctx["gstin"]}</div>' if ctx.get("gstin") else ""

        status_color = '#166534' if status_str in ('ISSUED', 'ACTIVE') else '#b91c1c'

        logo_html = ""
        logo_url = ctx.get("logo_url")
        if logo_url:
            logo_file = self._find_logo_file(logo_url)
            if logo_file and logo_file.is_file():
                try:
                    import base64
                    ext = logo_file.suffix.lower().replace(".", "")
                    mime = "image/png" if ext == "png" else "image/jpeg"
                    with open(logo_file, "rb") as _f:
                        b64_data = base64.b64encode(_f.read()).decode("utf-8")
                    logo_html = f'<div style="text-align: center; margin-bottom: 8px;"><img src="data:{mime};base64,{b64_data}" alt="Logo" style="max-height: 50px; max-width: 180px; object-fit: contain; " /></div>'
                except Exception:
                    logo_html = f'<div style="text-align: center; margin-bottom: 8px;"><img src="{logo_url}" alt="Logo" style="max-height: 50px; max-width: 180px; object-fit: contain; " /></div>'
            else:
                logo_html = f'<div style="text-align: center; margin-bottom: 8px;"><img src="{logo_url}" alt="Logo" style="max-height: 50px; max-width: 180px; object-fit: contain; " /></div>'

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Credit Note Voucher {ctx.get('credit_note_no')}</title>
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
    color: #1e40af;
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
  .val-status {{
    color: {status_color};
    font-weight: bold;
  }}
  .highlight-box {{
    background: #eff6ff;
    border: 1px solid #3b82f6;
    padding: 8px 10px;
    margin: 8px 0;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }}
  .hl-title {{ font-size: 12px; font-weight: bold; color: #1e40af; }}
  .hl-val {{ font-size: 16px; font-weight: bold; color: #1e40af; }}
  .notice {{
    font-size: 11px;
    color: #6b7280;
    text-align: center;
    margin: 8px 0;
  }}
  .sig {{
    font-size: 11px;
    color: #4b5563;
    margin: 10px 0 4px 0;
  }}
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
    {logo_html}
    <div class="store-title">{ctx.get('store_name', 'Retail Store')}</div>
    {store_addr_html}
    {store_phone_html}
    {gstin_html}
    <div class="doc-title">CREDIT NOTE VOUCHER</div>
    <div class="store-sub">OFFICIAL STORE CREDIT SLIP</div>
  </div>

  <div class="divider"></div>

  <div class="row"><span class="lbl">Credit Note No</span><span class="val">{ctx.get('credit_note_no')}</span></div>
  <div class="row"><span class="lbl">Ref Invoice</span><span class="val">{ctx.get('invoice_number')}</span></div>
  <div class="row"><span class="lbl">Date Issued</span><span class="val">{dt_str}</span></div>
  <div class="row"><span class="lbl">Valid Until</span><span class="val">{ctx.get('valid_until', 'No Expiry')}</span></div>
  <div class="row"><span class="lbl">Status</span><span class="val val-status">{status_str}</span></div>

  <div class="divider"></div>

  <div class="row"><span class="lbl">Customer</span><span class="val">{ctx.get('customer_name', 'Walk-in Customer')}</span></div>
  <div class="row"><span class="lbl">Phone</span><span class="val">{ctx.get('customer_phone', 'N/A')}</span></div>

  <div class="divider"></div>

  <div class="highlight-box">
    <span class="hl-title">CREDIT AMOUNT</span>
    <span class="hl-val">Rs. {amt_str}</span>
  </div>

  <div class="row"><span class="lbl" style="font-weight: bold; color: #111;">BALANCE DUE</span><span class="val" style="color: #166534; font-size: 14px;">Rs. {bal_str}</span></div>

  <div class="divider"></div>

  <div class="notice">
    Use this note for future store<br>purchases before expiry date.
  </div>

  <div class="sig">Customer Signature: __________________</div>
  <div class="sig">Authorized Signature: ________________</div>

  <div class="center store-sub" style="margin-top: 12px;">
    Thank You! Please visit again.
  </div>
</div>
</body>
</html>"""

    def _generate_credit_note_thermal_pdf(self, ctx: Dict[str, Any]) -> bytes:
        from PIL import Image
        from reportlab.lib.utils import ImageReader
        from reportlab.pdfgen import canvas

        img_bytes = self._generate_credit_note_thermal_image(ctx)
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

    def export_credit_note_thermal(
        self,
        user: User,
        credit_note_id: int,
        mode: Any = "preview",
        request: Optional[Any] = None,
    ) -> Response:
        data = self.get_credit_note_thermal_receipt(user.tenant_id, credit_note_id, user=user)
        mode_val = str(getattr(mode, "value", mode) or "preview").lower().strip()

        # Check if caller wants JSON (e.g. Accept: application/json without explicit query param)
        if request is not None and hasattr(request, "query_params") and hasattr(request, "headers"):
            if "mode" not in request.query_params and "application/json" in request.headers.get("accept", ""):
                mode_val = "json"

        cn_no = data.get("credit_note_no", f"CN-{credit_note_id}")

        # 1. Preview mode (Default) -> Visual 80mm receipt PNG rendered directly in Swagger UI
        if mode_val == CreditNoteThermalMode.preview.value:
            img_bytes = self._generate_credit_note_thermal_image(data)
            return Response(
                content=img_bytes,
                media_type="image/png",
                headers={
                    "Content-Disposition": f"inline; filename=credit_note_{cn_no}_thermal.png",
                    "X-CreditNote-Print-Type": "80mm-PNG-Preview",
                },
            )

        # 2. View mode -> Inline styled HTML page with auto-print dialog
        if mode_val == CreditNoteThermalMode.view.value:
            html_content = self._generate_credit_note_thermal_html(data, auto_print=True)
            return HTMLResponse(
                content=html_content,
                status_code=200,
                headers={"Content-Disposition": f"inline; filename=credit_note_{cn_no}_thermal.html"},
            )

        # 3. Download mode -> ESC/POS text file attachment download
        if mode_val == CreditNoteThermalMode.download.value:
            text_payload = data["thermal_text"]
            return Response(
                content=text_payload.encode("utf-8"),
                media_type="text/plain; charset=utf-8",
                headers={
                    "Content-Disposition": f"attachment; filename=credit_note_{cn_no}_thermal.txt",
                    "X-CreditNote-Print-Type": "ESC/POS",
                },
            )

        # 4. PDF mode -> 80mm Thermal Receipt PDF download
        if mode_val == CreditNoteThermalMode.pdf.value:
            pdf_bytes = self._generate_credit_note_thermal_pdf(data)
            return Response(
                content=pdf_bytes,
                media_type="application/pdf",
                headers={
                    "Content-Disposition": f"attachment; filename=credit_note_{cn_no}_thermal.pdf",
                    "X-CreditNote-Print-Type": "80mm-PDF",
                },
            )

        # 5. HTML mode -> Styled raw HTML layout
        if mode_val == CreditNoteThermalMode.html.value:
            html_content = self._generate_credit_note_thermal_html(data, auto_print=False)
            return HTMLResponse(
                content=html_content,
                status_code=200,
                headers={"Content-Disposition": f"inline; filename=credit_note_{cn_no}_thermal.html"},
            )

        # 6. JSON mode -> Structured JSON payload
        if mode_val == CreditNoteThermalMode.json.value:
            html_content = self._generate_credit_note_thermal_html(data, auto_print=False)
            resp = CreditNoteThermalResponse(
                success=True,
                message="Credit note thermal voucher generated successfully",
                credit_note_id=data["credit_note_id"],
                credit_note_no=data["credit_note_no"],
                invoice_id=data["invoice_id"],
                invoice_number=data["invoice_number"],
                refund_amount=data["refund_amount"],
                balance_amount=data["balance_amount"],
                status=data["status"],
                customer_name=data["customer_name"],
                customer_phone=data["customer_phone"],
                store_name=data["store_name"],
                valid_until=data["valid_until"],
                created_at=data["created_at"],
                thermal_text=data["thermal_text"],
                html=html_content,
            )
            return JSONResponse(content=resp.model_dump(mode="json"))

        # 7. Text mode -> Raw ESC/POS text stream
        if mode_val == CreditNoteThermalMode.text.value:
            return Response(
                content=data["thermal_text"].encode("utf-8"),
                media_type="text/plain; charset=utf-8",
                headers={
                    "Content-Disposition": f"inline; filename=credit_note_{cn_no}_thermal.txt",
                    "X-CreditNote-Print-Type": "ESC/POS",
                },
            )

        raise AppException(f"Unsupported delivery mode: '{mode_val}'")
    def get_invoice_by_number(
        self,
        tenant_id: int,
        invoice_number: str,
        user: Optional[User] = None,
        system_context: bool = False,
    ) -> Invoice:
        inv_num = invoice_number.strip() if invoice_number else ""
        if not inv_num:
            raise AppException("Invoice number cannot be empty")

        invoice = (
            self.db.query(Invoice)
            .filter(
                Invoice.tenant_id == tenant_id,
                Invoice.invoice_number == inv_num,
            )
            .first()
        )
        if not invoice:
            raise NotFoundException(f"Invoice '{inv_num}' not found")

        if not system_context and user is not None:
            if user.store_id is not None:
                if invoice.store_id is not None and invoice.store_id != user.store_id:
                    raise ForbiddenException("Access denied: store staff cannot access other stores' invoices")
            elif not is_tenant_wide_authorized(user, self.db):
                raise ForbiddenException("Access denied: user has no assigned store")

        return invoice

    def void_invoice(
        self,
        tenant_id: int,
        invoice_id: int,
        reason: Optional[str] = None,
        user: Optional[User] = None,
    ) -> Invoice:
        invoice = self.get_invoice(
            tenant_id,
            invoice_id,
            user=user,
        )

        if user and user.store_id is not None:
            if invoice.store_id is not None and invoice.store_id != user.store_id:
                raise ForbiddenException("Access denied: cannot void invoice for another store")

        invoice = (
            self.db.query(Invoice)
            .filter(
                Invoice.id == invoice_id,
                Invoice.tenant_id == tenant_id,
            )
            .with_for_update()
            .first()
        )
        if not invoice:
            raise NotFoundException("Invoice not found")

        from app.core.exceptions import ConflictException
        if invoice.status in ["void", "cancelled"]:
            raise ConflictException(f"Invoice {invoice.invoice_number} is already {invoice.status}")

        if invoice.credit_notes:
            raise ConflictException("Cannot void invoice with existing credit notes; process via refunds")

        from app.models.invoice_item_return import InvoiceItemReturn
        existing_returns = (
            self.db.query(InvoiceItemReturn)
            .filter(InvoiceItemReturn.invoice_id == invoice.id)
            .first()
        )
        if existing_returns:
            raise ConflictException("Cannot void invoice with existing item returns")

        order = (
            self.db.query(Order)
            .filter(Order.id == invoice.order_id)
            .with_for_update()
            .first()
        )
        store_id = invoice.store_id or (order.store_id if order else None)
        if not store_id:
            raise AppException("Invoice has no associated store")

        from app.models.inventory import Inventory, StockMovement
        from app.models.order_item import OrderItem
        from app.models.order_item_batch_allocation import OrderItemBatchAllocation

        for item in invoice.items:
            order_item = None
            if order:
                order_item = (
                    self.db.query(OrderItem)
                    .filter(
                        OrderItem.order_id == order.id,
                        OrderItem.product_id == item.product_id,
                    )
                    .first()
                )

            batch_allocs = []
            if order_item:
                batch_allocs = (
                    self.db.query(OrderItemBatchAllocation)
                    .filter(OrderItemBatchAllocation.order_item_id == order_item.id)
                    .all()
                )

            restored_via_batch = False
            if batch_allocs:
                try:
                    BatchAllocationService(self.db, user=user).restore_batch_allocation(
                        tenant_id=tenant_id,
                        store_id=store_id,
                        order_item_id=order_item.id,
                        quantity_to_restore=Decimal(str(item.quantity)),
                        condition="sellable",
                        reference_id=invoice.id,
                        reference_type="INVOICE_VOID",
                        notes=reason or f"Restored from voided invoice {invoice.invoice_number}",
                        commit=False,
                    )
                    restored_via_batch = True
                except Exception:
                    restored_via_batch = False

            if not restored_via_batch:
                inv = (
                    self.db.query(Inventory)
                    .filter(
                        Inventory.tenant_id == tenant_id,
                        Inventory.store_id == store_id,
                        Inventory.product_id == item.product_id,
                    )
                    .with_for_update()
                    .first()
                )
                if inv:
                    prev_stock = inv.quantity
                    inv.quantity += int(item.quantity)
                    new_stock = inv.quantity
                    mv = StockMovement(
                        tenant_id=tenant_id,
                        store_id=store_id,
                        product_id=item.product_id,
                        quantity=Decimal(str(item.quantity)),
                        previous_stock=Decimal(str(prev_stock)),
                        new_stock=Decimal(str(new_stock)),
                        movement_type="RETURN",
                        reference_id=invoice.id,
                        reference_type="INVOICE_VOID",
                        notes=reason or f"Voided invoice {invoice.invoice_number}",
                        created_by=user.id if user else None,
                    )
                    self.db.add(mv)

        if order:
            order.status = "cancelled"

        payments = (
            self.db.query(Payment)
            .filter(
                Payment.tenant_id == tenant_id,
                Payment.invoice_id == invoice.id,
            )
            .all()
        )
        for p in payments:
            p.status = "cancelled"

        invoice.status = "cancelled"

        AuditService(self.db).log(
            tenant_id,
            user.id if user else 0,
            "invoice_voided",
            "invoice",
            invoice.id,
            {
                "invoice_number": invoice.invoice_number,
                "reason": reason or "Voided at counter",
                "total_amount": str(invoice.total_amount),
            },
        )

        self.db.commit()
        self.db.refresh(invoice)
        return invoice
