import uuid
from typing import Any, Dict, List, Optional, Union
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from fastapi.responses import HTMLResponse, JSONResponse, Response

from sqlalchemy import extract, func

from app.services.excel_export_service import ExcelExportService
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import (
    AppException,
    ForbiddenException,
    NotFoundException,
    ConflictException,
)
from app.core.security import is_tenant_wide_authorized
from app.models.customer import (
    Customer,
    CustomerFeedback,
    CustomerWallet,
    WalletTransaction,
    LoyaltyPoint,
    CustomerCommunication,
    CustomerReferral,
    CustomerNote,
)
from app.models.invoice import Invoice
from app.models.store import Store
from app.models.user import User
from app.models.coupon import Coupon
from app.models.order import Order, OrderTracking
from app.models.order_item import OrderItem
from app.models.order_item_batch_allocation import OrderItemBatchAllocation
from app.models.product import Product
from app.models.product_batch import ProductBatch
from app.models.product_variant import ProductVariant
from app.models.delivery import Delivery
from app.repositories.order_repo import OrderRepository
from app.repositories.order_item_batch_allocation_repo import OrderItemBatchAllocationRepository
from app.repositories.customer_repo import get_customers_for_export
from app.schemas.order import OrderCreate, OrderItemCreate, OrderUpdate, OrderResponse, POSCheckoutRequest, POSPaymentData, OrderReceiptResponse, OrderThermalMode
from app.services.inventory_service import InventoryService
from app.services.batch_allocation_service import BatchAllocationService, InsufficientStockException
from app.utils.constants import OrderStatus, StockMovementType

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle


class OrderService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = OrderRepository(db)
        self.inventory_service = InventoryService(db)
        self.batch_allocation_service = BatchAllocationService(db)
        self.batch_allocation_repo = OrderItemBatchAllocationRepository(db)

    def _is_batch_managed(
        self, product: Product, store_id: int, variant_id: int | None = None
    ) -> bool:
        if getattr(product, "track_batch", False):
            return True
        query = self.db.query(ProductBatch.id).filter(
            ProductBatch.tenant_id == product.tenant_id,
            ProductBatch.store_id == store_id,
            ProductBatch.product_id == product.id,
            ProductBatch.is_active.is_(True),
        )
        if variant_id is not None:
            query = query.filter(ProductBatch.variant_id == variant_id)
        return query.first() is not None

    def _generate_order_number(
        self,
        tenant_id: Optional[int] = None,
        store_id: Optional[int] = None,
        pos_id: Optional[int] = None,
    ) -> str:
        if tenant_id:
            try:
                from app.services.document_number_service import DocumentNumberService
                return DocumentNumberService(self.db).generate_order_number(
                    tenant_id=tenant_id, store_id=store_id, pos_id=pos_id
                )
            except Exception:
                pass
        return f"ORD-{uuid.uuid4().hex[:8].upper()}"

    def _get_store(
        self,
        tenant_id: int,
        store_id: int,
    ) -> Store:

        store = (
            self.db.query(Store)
            .filter(
                Store.id == store_id,
                Store.tenant_id == tenant_id,
            )
            .first()
        )

        if not store:
            raise NotFoundException(f"Store {store_id} not found")

        return store

    def _get_customer(
        self,
        tenant_id: int,
        customer_id: int,
    ) -> Customer:

        customer = (
            self.db.query(Customer)
            .filter(
                Customer.id == customer_id,
                Customer.tenant_id == tenant_id,
            )
            .first()
        )

        if not customer:
            raise NotFoundException(
                f"Customer {customer_id} not found"
            )

        return customer

    def _get_coupon(
        self,
        tenant_id: int,
        coupon_code: str,
    ) -> Coupon:

        code = coupon_code.strip().upper()

        coupon = (
            self.db.query(Coupon)
            .filter(
                Coupon.code == code,
                Coupon.tenant_id == tenant_id,
            )
            .first()
        )

        if not coupon:
            raise NotFoundException("Coupon not found")

        return coupon

    def _validate_coupon(
        self,
        tenant_id: int,
        coupon_code: str,
        order_amount: Decimal,
    ) -> Coupon:

        coupon = self._get_coupon(
            tenant_id,
            coupon_code,
        )

        today = date.today()

        if not coupon.is_active:
            raise AppException("Coupon is inactive")

        if today < coupon.start_date:
            raise AppException("Coupon is not started yet")

        if today > coupon.end_date:
            raise AppException("Coupon expired")

        if order_amount < coupon.minimum_order_amount:
            raise AppException(
                f"Minimum order amount is "
                f"{coupon.minimum_order_amount}"
            )

        if coupon.used_count >= coupon.usage_limit:
            raise AppException("Coupon usage limit exceeded")

        if coupon.discount_type not in (
            "percentage",
            "fixed",
        ):
            raise AppException(
                "Invalid coupon discount type"
            )

        if coupon.discount_value <= 0:
            raise AppException(
                "Coupon discount value must be greater than 0"
            )

        return coupon

    def _calculate_coupon_discount(
        self,
        coupon: Coupon,
        order_amount: Decimal,
    ) -> Decimal:

        if order_amount <= 0:
            return Decimal("0.00")

        if coupon.discount_type == "percentage":

            discount = (
                order_amount
                * coupon.discount_value
                / Decimal("100")
            ).quantize(
                Decimal("0.01")
            )

            if coupon.maximum_discount is not None:
                discount = min(
                    discount,
                    coupon.maximum_discount,
                )

        elif coupon.discount_type == "fixed":

            discount = coupon.discount_value

            if coupon.maximum_discount is not None:
                discount = min(
                    discount,
                    coupon.maximum_discount,
                )

        else:
            raise AppException(
                "Invalid coupon discount type"
            )

        return min(
            discount,
            order_amount,
        ).quantize(
            Decimal("0.01")
        )

    def _calculate_item_totals(
        self,
        product: Product,
        item: OrderItemCreate,
        same_state: bool = True,
    ) -> OrderItem:

        unit_price = (
            item.unit_price
            if item.unit_price is not None
            else product.selling_price
        )

        gross_amount = (
            unit_price * item.quantity
        )

        if item.discount > gross_amount:
            raise AppException(
                f"Discount for product {product.id} "
                f"cannot be greater than item amount "
                f"{gross_amount}"
            )

        from app.utils.gst_engine import calculate_line_tax, resolve_gst_rate

        gst_rate = resolve_gst_rate(self.db, product.tenant_id, product)
        tax = calculate_line_tax(
            quantity=Decimal(str(item.quantity)),
            unit_price=unit_price,
            discount=item.discount,
            gst_rate=gst_rate,
            same_state=same_state,
        )

        return OrderItem(
            product_id=product.id,
            product_name=product.name,
            sku=product.sku,
            quantity=item.quantity,
            unit_price=unit_price,
            discount=item.discount,
            tax_rate=tax["gst_rate"],
            tax_amount=tax["gst_amount"],
            total=tax["total_amount"],
            cgst_amount=tax["cgst_amount"],
            sgst_amount=tax["sgst_amount"],
            igst_amount=tax["igst_amount"],
            variant=item.variant,
            variant_id=getattr(item, "variant_id", None),
        )

    def _calculate_order_discount(
        self,
        subtotal: Decimal,
        discount_percentage: Decimal,
    ) -> Decimal:

        if discount_percentage < 0:
            raise AppException(
                "Discount percentage cannot be negative"
            )

        if discount_percentage > 100:
            raise AppException(
                "Discount percentage cannot be greater than 100"
            )

        discount_amount = (
            subtotal
            * discount_percentage
            / Decimal("100")
        ).quantize(
            Decimal("0.01")
        )

        return min(
            discount_amount,
            subtotal,
        )

    def _recalculate_order(
        self,
        order: Order,
    ) -> None:

        subtotal = sum(
            (
                item.unit_price * item.quantity
                - item.discount
                for item in order.items
            ),
            Decimal("0.00"),
        ).quantize(
            Decimal("0.01")
        )

        tax_amount = sum(
            (
                item.tax_amount
                for item in order.items
            ),
            Decimal("0.00"),
        ).quantize(
            Decimal("0.01")
        )

        if order.discount_amount < 0:
            raise AppException(
                "Order discount cannot be negative"
            )

        if order.discount_amount > subtotal:
            raise AppException(
                "Order discount cannot be greater "
                "than order subtotal"
            )

        cgst_amount = sum(
            (
                getattr(item, "cgst_amount", Decimal("0.00")) or Decimal("0.00")
                for item in order.items
            ),
            Decimal("0.00"),
        ).quantize(
            Decimal("0.01")
        )

        sgst_amount = sum(
            (
                getattr(item, "sgst_amount", Decimal("0.00")) or Decimal("0.00")
                for item in order.items
            ),
            Decimal("0.00"),
        ).quantize(
            Decimal("0.01")
        )

        igst_amount = sum(
            (
                getattr(item, "igst_amount", Decimal("0.00")) or Decimal("0.00")
                for item in order.items
            ),
            Decimal("0.00"),
        ).quantize(
            Decimal("0.01")
        )

        order.subtotal = subtotal
        order.tax_amount = tax_amount
        order.cgst_amount = cgst_amount
        order.sgst_amount = sgst_amount
        order.igst_amount = igst_amount

        raw_total = (
            subtotal
            + tax_amount
            - order.discount_amount
        ).quantize(
            Decimal("0.01")
        )

        if raw_total < 0:
            raw_total = Decimal("0.00")

        order.total_amount = raw_total
        order.round_off = (round(raw_total) - raw_total).quantize(Decimal("0.01"))

    def create_order(
        self,
        tenant_id: int,
        user_id: int,
        data: OrderCreate,
        commit: bool = True,
    ) -> Order:

        user = (
            self.db.query(User)
            .filter(
                User.id == user_id,
                User.tenant_id == tenant_id,
            )
            .first()
        )
        if not user:
            raise ForbiddenException("Access denied: user context required")

        if user.store_id is not None and data.store_id != user.store_id:
            raise ForbiddenException("Access denied: cannot create order for another store")

        if user.store_id is None and not is_tenant_wide_authorized(user, self.db):
            raise ForbiddenException("Access denied: user has no assigned store")

        self._get_store(
            tenant_id,
            data.store_id,
        )

        if data.customer_id is not None:
            self._get_customer(
                tenant_id,
                data.customer_id,
            )

        order = Order(
            tenant_id=tenant_id,
            store_id=data.store_id,
            customer_id=data.customer_id,
            user_id=user_id,
            order_number=self._generate_order_number(
                tenant_id=tenant_id, store_id=data.store_id
            ),
            order_type=data.order_type,
            status=OrderStatus.DRAFT.value,
            coupon_code=data.coupon_code,
            discount_amount=Decimal("0.00"),
            delivery_address=data.delivery_address,
            notes=data.notes,
        )

        same_state = getattr(data, "same_state", True)

        for item_data in data.items:

            product = (
                self.db.query(Product)
                .filter(
                    Product.id == item_data.product_id,
                    Product.tenant_id == tenant_id,
                )
                .first()
            )

            if not product:
                raise NotFoundException(
                    f"Product {item_data.product_id} not found"
                )

            variant_id = getattr(item_data, "variant_id", None)
            if variant_id is not None:
                variant = (
                    self.db.query(ProductVariant)
                    .filter(
                        ProductVariant.id == variant_id,
                        ProductVariant.tenant_id == tenant_id,
                    )
                    .first()
                )
                if not variant:
                    raise NotFoundException(
                        f"ProductVariant {variant_id} not found"
                    )
                if variant.product_id != product.id:
                    raise AppException(
                        f"ProductVariant {variant_id} does not belong to product {product.id}"
                    )

            order.items.append(
                self._calculate_item_totals(
                    product,
                    item_data,
                    same_state=same_state,
                )
            )

        subtotal = sum(
            (
                item.unit_price * item.quantity
                - item.discount
                for item in order.items
            ),
            Decimal("0.00"),
        ).quantize(
            Decimal("0.01")
        )

        if data.coupon_code:

            coupon = self._validate_coupon(
                tenant_id=tenant_id,
                coupon_code=data.coupon_code,
                order_amount=subtotal,
            )

            coupon_discount = (
                self._calculate_coupon_discount(
                    coupon,
                    subtotal,
                )
            )

            order.coupon_code = coupon.code
            order.discount_amount = coupon_discount

        else:

            order.discount_amount = (
                self._calculate_order_discount(
                    subtotal,
                    data.discount_amount,
                )
            )

        self._recalculate_order(order)

        created_order = self.repo.create(order, commit=commit)

        if data.coupon_code:

            coupon.used_count += 1
            try:
                from app.models.coupon import CouponRedemption
                redemption = CouponRedemption(
                    tenant_id=tenant_id,
                    coupon_id=coupon.id,
                    order_id=created_order.id,
                    customer_id=created_order.customer_id,
                    discount_amount=getattr(order, 'discount_amount', Decimal('0.00')) or Decimal('0.00'),
                    order_amount=getattr(order, 'total_amount', Decimal('0.00')) or Decimal('0.00'),
                )
                self.db.add(redemption)
            except Exception:
                pass
            if commit:
                self.db.commit()
                self.db.refresh(created_order)
            else:
                self.db.flush()

        return created_order

    def get_order(
        self,
        tenant_id: int,
        order_id: int,
    ) -> Order:

        order = self.repo.get_by_id(
            order_id,
            tenant_id,
        )

        if not order:
            raise NotFoundException(
                "Order not found"
            )

        return order

    def list_orders(
        self,
        tenant_id: int,
        store_id: int | None = None,
        status: str | None = None,
        customer_id: int | None = None,
        order_type: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        search: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ):

        if page < 1:
            raise AppException(
                "Page must be greater than 0"
            )

        if page_size < 1:
            raise AppException(
                "Page size must be greater than 0"
            )

        if store_id is not None:
            self._get_store(
                tenant_id,
                store_id,
            )

        skip = (
            page - 1
        ) * page_size

        return self.repo.list_orders(
            tenant_id=tenant_id,
            store_id=store_id,
            status=status,
            customer_id=customer_id,
            order_type=order_type,
            date_from=date_from,
            date_to=date_to,
            search=search,
            skip=skip,
            limit=page_size,
        )

    def update_order(
        self,
        tenant_id: int,
        order_id: int,
        data: OrderUpdate,
    ) -> Order:

        order = self.get_order(
            tenant_id,
            order_id,
        )

        if order.status not in (
            OrderStatus.DRAFT.value,
            OrderStatus.CONFIRMED.value,
        ):
            raise AppException(
                "Order cannot be updated in current status"
            )

        update_data = data.model_dump(
            exclude_unset=True
        )

        if not update_data:
            raise AppException(
                "At least one field is required for update"
            )

        if "status" in update_data:
            raise AppException(
                "Order status must be updated "
                "using the order status endpoint"
            )

        if "items" in update_data and update_data["items"] is not None:
            if order.status != OrderStatus.DRAFT.value:
                raise AppException("Line items can only be modified for draft orders")
            order.items.clear()
            same_state = True
            for item_data in data.items:
                product = (
                    self.db.query(Product)
                    .filter(
                        Product.id == item_data.product_id,
                        Product.tenant_id == tenant_id,
                    )
                    .first()
                )
                if not product:
                    raise NotFoundException(f"Product {item_data.product_id} not found")
                variant_id = getattr(item_data, "variant_id", None)
                if variant_id is not None:
                    variant = (
                        self.db.query(ProductVariant)
                        .filter(
                            ProductVariant.id == variant_id,
                            ProductVariant.tenant_id == tenant_id,
                        )
                        .first()
                    )
                    if not variant or variant.product_id != product.id:
                        raise AppException(f"ProductVariant {variant_id} does not belong to product {product.id}")
                order.items.append(
                    self._calculate_item_totals(product, item_data, same_state=same_state)
                )
            del update_data["items"]

        if "customer_id" in update_data:

            customer_id = update_data["customer_id"]

            if customer_id is not None:
                self._get_customer(
                    tenant_id,
                    customer_id,
                )

        if "coupon_code" in update_data:

            coupon_code = update_data["coupon_code"]

            if coupon_code is None:

                discount_percentage = (
                    update_data.get(
                        "discount_amount",
                        Decimal("0.00"),
                    )
                )

                update_data["discount_amount"] = (
                    self._calculate_order_discount(
                        order.subtotal,
                        discount_percentage,
                    )
                )

            else:

                coupon = self._validate_coupon(
                    tenant_id=tenant_id,
                    coupon_code=coupon_code,
                    order_amount=order.subtotal,
                )

                update_data["coupon_code"] = coupon.code

                update_data["discount_amount"] = (
                    self._calculate_coupon_discount(
                        coupon,
                        order.subtotal,
                    )
                )

        elif "discount_amount" in update_data:

            if order.coupon_code:

                coupon = self._validate_coupon(
                    tenant_id=tenant_id,
                    coupon_code=order.coupon_code,
                    order_amount=order.subtotal,
                )

                update_data["discount_amount"] = (
                    self._calculate_coupon_discount(
                        coupon,
                        order.subtotal,
                    )
                )

            else:

                update_data["discount_amount"] = (
                    self._calculate_order_discount(
                        order.subtotal,
                        update_data["discount_amount"],
                    )
                )

        for key, value in update_data.items():
            setattr(
                order,
                key,
                value,
            )

        self._recalculate_order(order)

        return self.repo.update(order)

    def confirm_order(
        self,
        tenant_id: int,
        order_id: int,
        commit: bool = True,
    ) -> Order:

        order = self.get_order(
            tenant_id,
            order_id,
        )

        if order.status != OrderStatus.DRAFT.value:
            raise AppException(
                "Only draft orders can be confirmed"
            )

        self._get_store(
            tenant_id,
            order.store_id,
        )

        if order.customer_id is not None:
            self._get_customer(
                tenant_id,
                order.customer_id,
            )

        from app.schemas.inventory import StockOutRequest

        try:
            with self.db.begin_nested():
                for item in order.items:
                    product = (
                        self.db.query(Product)
                        .filter(
                            Product.id == item.product_id,
                            Product.tenant_id == tenant_id,
                        )
                        .first()
                    )
                    if not product:
                        raise NotFoundException(f"Product {item.product_id} not found")

                    variant_id = getattr(item, "variant_id", None)

                    if self._is_batch_managed(product, order.store_id, variant_id=variant_id):
                        # Batch allocation path:
                        alloc_result = self.batch_allocation_service.allocate(
                            tenant_id=tenant_id,
                            store_id=order.store_id,
                            product_id=item.product_id,
                            requested_quantity=Decimal(str(item.quantity)),
                            variant_id=variant_id,
                            strategy="AUTO",
                            reference_id=order.id,
                            reference_type="ORDER",
                            notes=f"Order {order.order_number} confirmation",
                            commit=False,
                        )

                        # Persist OrderItemBatchAllocation rows
                        for alloc in alloc_result.allocations:
                            allocation_row = OrderItemBatchAllocation(
                                order_item_id=item.id,
                                batch_id=alloc.batch_id,
                                quantity=alloc.allocated_quantity,
                                unit_cost=alloc.unit_cost,
                            )
                            self.db.add(allocation_row)
                    else:
                        # Non-batch product path:
                        self.inventory_service.stock_out(
                            tenant_id,
                            StockOutRequest(
                                store_id=order.store_id,
                                product_id=item.product_id,
                                quantity=item.quantity,
                            ),
                            commit=False,
                        )

                order.status = OrderStatus.CONFIRMED.value

                if order.order_type == "ecommerce" or order.delivery_address:
                    delivery = Delivery(
                        tenant_id=tenant_id,
                        order_id=order.id,
                        status="pending",
                    )
                    self.db.add(delivery)

                    delivery_tracking = OrderTracking(
                        order_id=order.id,
                        status="pending",
                        remarks="Delivery created with status 'pending'",
                    )
                    self.db.add(delivery_tracking)

                tracking = OrderTracking(
                    order_id=order.id,
                    status=OrderStatus.CONFIRMED.value,
                    remarks="Order confirmed",
                )
                self.db.add(tracking)

                if order.customer_id is not None:
                    customer = self._get_customer(
                        tenant_id,
                        order.customer_id,
                    )
                    customer.total_spend = int(
                        (customer.total_spend or 0)
                        + round(order.total_amount)
                    )

                self.db.flush()

            if commit:
                self.db.commit()
                self.db.refresh(order)
            else:
                self.db.flush()
            return order
        except Exception:
            if commit:
                self.db.rollback()
            raise

    def cancel_order(
        self,
        tenant_id: int,
        order_id: int,
        restore_stock: bool = False,
    ) -> Order:

        order = self.get_order(
            tenant_id,
            order_id,
        )

        if order.status not in (
            OrderStatus.DRAFT.value,
            OrderStatus.CONFIRMED.value,
            OrderStatus.PROCESSING.value,
        ):
            raise AppException(
                "Order cannot be cancelled in current status"
            )

        previous_status = order.status
        order.status = OrderStatus.CANCELLED.value

        if restore_stock and previous_status in (
            OrderStatus.CONFIRMED.value,
            OrderStatus.PROCESSING.value,
        ):
            from app.schemas.inventory import StockInRequest
            from app.models.product_batch import ProductBatch
            for item in order.items:
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

                variant_id = getattr(item, "variant_id", None)
                if self._is_batch_managed(product, order.store_id, variant_id=variant_id):
                    allocations = (
                        self.db.query(OrderItemBatchAllocation)
                        .filter(OrderItemBatchAllocation.order_item_id == item.id)
                        .all()
                    )
                    if allocations:
                        for alloc in allocations:
                            b = (
                                self.db.query(ProductBatch)
                                .filter(
                                    ProductBatch.id == alloc.batch_id,
                                    ProductBatch.tenant_id == tenant_id,
                                )
                                .first()
                            )
                            if b:
                                b.remaining_quantity += alloc.quantity
                    else:
                        self.inventory_service.stock_in(
                            tenant_id,
                            StockInRequest(
                                store_id=order.store_id,
                                product_id=item.product_id,
                                quantity=item.quantity,
                            ),
                            commit=False,
                        )
                else:
                    self.inventory_service.stock_in(
                        tenant_id,
                        StockInRequest(
                            store_id=order.store_id,
                            product_id=item.product_id,
                            quantity=item.quantity,
                        ),
                        commit=False,
                    )

        tracking = OrderTracking(
            order_id=order.id,
            status=OrderStatus.CANCELLED.value,
            remarks="Order cancelled" + (" (stock restored)" if restore_stock else ""),
        )

        self.db.add(tracking)

        return self.repo.update(order)

    def update_order_status(
        self,
        tenant_id: int,
        order_id: int,
        status: str,
        remarks: str | None = None,
    ):

        order = self.get_order(
            tenant_id,
            order_id,
        )

        current_status = order.status

        allowed_transitions = {
            OrderStatus.DRAFT.value: {
                OrderStatus.CONFIRMED.value,
                OrderStatus.CANCELLED.value,
            },
            OrderStatus.CONFIRMED.value: {
                OrderStatus.PROCESSING.value,
                OrderStatus.SHIPPED.value,
                OrderStatus.CANCELLED.value,
            },
            OrderStatus.PROCESSING.value: {
                OrderStatus.SHIPPED.value,
                OrderStatus.CANCELLED.value,
            },
            OrderStatus.SHIPPED.value: {
                OrderStatus.DELIVERED.value,
                OrderStatus.RETURNED.value,
            },
            OrderStatus.DELIVERED.value: {
                OrderStatus.RETURNED.value,
                OrderStatus.REFUNDED.value,
            },
            OrderStatus.RETURNED.value: {
                OrderStatus.REFUNDED.value,
            },
            OrderStatus.CANCELLED.value: set(),
            OrderStatus.REFUNDED.value: set(),
        }

        if status == current_status:
            raise AppException(
                f"Order is already {current_status}"
            )

        if status not in allowed_transitions.get(
            current_status,
            set(),
        ):
            raise AppException(
                f"Cannot change order status "
                f"from '{current_status}' to '{status}'"
            )

        order.status = status

        tracking = OrderTracking(
            order_id=order.id,
            status=status,
            remarks=remarks,
        )

        self.db.add(tracking)

        return self.repo.update(order)

    def get_order_tracking(
        self,
        tenant_id: int,
        order_id: int,
    ):

        order = self.get_order(
            tenant_id,
            order_id,
        )

        return (
            self.db.query(OrderTracking)
            .filter(
                OrderTracking.order_id == order.id
            )
            .order_by(
                OrderTracking.created_at.desc(),
                OrderTracking.id.desc(),
            )
            .all()
        )

    def get_customer_history(
        self,
        tenant_id: int,
        customer_id: int,
    ):

        self._get_customer(
            tenant_id,
            customer_id,
        )

        orders = (
            self.db.query(Order)
            .filter(
                Order.tenant_id == tenant_id,
                Order.customer_id == customer_id,
            )
            .order_by(
                Order.created_at.desc()
            )
            .all()
        )
        if not orders:
            return {
                "success": True,
                "message": "No orders found for this customer",
                "customer_id": customer_id,
                "orders": [],
                "data": [],
            }
        return {
            "success": True,
            "message": "Orders retrieved successfully",
            "customer_id": customer_id,
            "orders": [OrderResponse.model_validate(o) for o in orders],
            "data": [OrderResponse.model_validate(o) for o in orders],
        }


    def add_order_items(
        self,
        tenant_id: int,
        order_id: int,
        items: list[OrderItemCreate],
    ) -> Order:
        order = self.get_order(tenant_id, order_id)
        if order.status != OrderStatus.DRAFT.value:
            raise AppException("Line items can only be added to draft orders")

        existing_keys = {
            (item.product_id, getattr(item, "variant_id", None))
            for item in order.items
        }

        for item_data in items:
            key = (item_data.product_id, getattr(item_data, "variant_id", None))
            if key in existing_keys:
                raise AppException(f"Product {item_data.product_id} already exists in order")
            existing_keys.add(key)

            product = (
                self.db.query(Product)
                .filter(
                    Product.id == item_data.product_id,
                    Product.tenant_id == tenant_id,
                )
                .first()
            )
            if not product:
                raise NotFoundException(f"Product {item_data.product_id} not found")

            variant_id = getattr(item_data, "variant_id", None)
            if variant_id is not None:
                variant = (
                    self.db.query(ProductVariant)
                    .filter(
                        ProductVariant.id == variant_id,
                        ProductVariant.tenant_id == tenant_id,
                    )
                    .first()
                )
                if not variant or variant.product_id != product.id:
                    raise AppException(f"ProductVariant {variant_id} does not belong to product {product.id}")

            order.items.append(
                self._calculate_item_totals(product, item_data, same_state=True)
            )

        self._recalculate_order(order)
        tracking = OrderTracking(
            order_id=order.id,
            status=OrderStatus.DRAFT.value,
            remarks=f"Added {len(items)} line item(s)",
        )
        self.db.add(tracking)
        return self.repo.update(order)

    def pos_checkout(
        self,
        tenant_id: int,
        user_id: int,
        data: POSCheckoutRequest,
    ) -> dict:
        user = (
            self.db.query(User)
            .filter(
                User.id == user_id,
                User.tenant_id == tenant_id,
            )
            .first()
        )
        if not user:
            raise ForbiddenException("Access denied: user context required")

        if user.store_id is not None and data.store_id != user.store_id:
            raise ForbiddenException("Access denied: cannot create order for another store")

        if user.store_id is None and not is_tenant_wide_authorized(user, self.db):
            raise ForbiddenException("Access denied: user has no assigned store")

        store = self._get_store(tenant_id, data.store_id)
        if data.customer_id is not None:
            self._get_customer(tenant_id, data.customer_id)

        try:
            with self.db.begin_nested():
                order = Order(
                    tenant_id=tenant_id,
                    store_id=data.store_id,
                    customer_id=data.customer_id,
                    user_id=user_id,
                    order_number=self._generate_order_number(
                        tenant_id=tenant_id, store_id=data.store_id
                    ),
                    order_type="pos",
                    status=OrderStatus.CONFIRMED.value,
                    coupon_code=data.coupon_code,
                    payment_method=data.payment.payment_method,
                    payment_status="paid",
                    discount_amount=Decimal("0.00"),
                    notes=data.notes,
                )

                same_state = data.same_state
                for item_data in data.items:
                    product = (
                        self.db.query(Product)
                        .filter(
                            Product.id == item_data.product_id,
                            Product.tenant_id == tenant_id,
                        )
                        .first()
                    )
                    if not product:
                        raise NotFoundException(f"Product {item_data.product_id} not found")

                    variant_id = getattr(item_data, "variant_id", None)
                    if variant_id is not None:
                        variant = (
                            self.db.query(ProductVariant)
                            .filter(
                                ProductVariant.id == variant_id,
                                ProductVariant.tenant_id == tenant_id,
                            )
                            .first()
                        )
                        if not variant or variant.product_id != product.id:
                            raise AppException(f"ProductVariant {variant_id} does not belong to product {product.id}")

                    order.items.append(
                        self._calculate_item_totals(product, item_data, same_state=same_state)
                    )

                subtotal = sum(
                    (item.unit_price * item.quantity - item.discount for item in order.items),
                    Decimal("0.00")
                ).quantize(Decimal("0.01"))

                coupon = None
                if data.coupon_code:
                    coupon = self._validate_coupon(
                        tenant_id=tenant_id,
                        coupon_code=data.coupon_code,
                        order_amount=subtotal,
                    )
                    coupon_discount = self._calculate_coupon_discount(coupon, subtotal)
                    order.coupon_code = coupon.code
                    order.discount_amount = coupon_discount
                else:
                    order.discount_amount = self._calculate_order_discount(subtotal, data.discount_amount)

                self._recalculate_order(order)
                self.db.add(order)
                self.db.flush()

                # Deduct inventory immediately
                from app.schemas.inventory import StockOutRequest
                for item in order.items:
                    product = (
                        self.db.query(Product)
                        .filter(Product.id == item.product_id, Product.tenant_id == tenant_id)
                        .first()
                    )
                    variant_id = getattr(item, "variant_id", None)
                    if self._is_batch_managed(product, order.store_id, variant_id=variant_id):
                        alloc_result = self.batch_allocation_service.allocate(
                            tenant_id=tenant_id,
                            store_id=order.store_id,
                            product_id=item.product_id,
                            requested_quantity=Decimal(str(item.quantity)),
                            variant_id=variant_id,
                            strategy="AUTO",
                            reference_id=order.id,
                            reference_type="ORDER",
                            notes=f"POS Order {order.order_number}",
                            commit=False,
                        )
                        for alloc in alloc_result.allocations:
                            allocation_row = OrderItemBatchAllocation(
                                order_item_id=item.id,
                                batch_id=alloc.batch_id,
                                quantity=alloc.allocated_quantity,
                                unit_cost=alloc.unit_cost,
                            )
                            self.db.add(allocation_row)
                    else:
                        self.inventory_service.stock_out(
                            tenant_id,
                            StockOutRequest(
                                store_id=order.store_id,
                                product_id=item.product_id,
                                quantity=item.quantity,
                            ),
                            commit=False,
                        )

                # Coupon redemption increment
                if coupon:
                    coupon.used_count += 1
                    try:
                        from app.models.coupon import CouponRedemption
                        redemption = CouponRedemption(
                            tenant_id=tenant_id,
                            coupon_id=coupon.id,
                            order_id=order.id,
                            customer_id=order.customer_id,
                            discount_amount=order.discount_amount,
                            order_amount=order.total_amount,
                        )
                        self.db.add(redemption)
                    except Exception:
                        pass

                # Customer spend increment
                if order.customer_id is not None:
                    customer = self._get_customer(tenant_id, order.customer_id)
                    customer.total_spend = int((customer.total_spend or 0) + round(order.total_amount))

                # Payments
                tendered_amount = data.payment.amount if data.payment.amount is not None else order.total_amount
                if tendered_amount < order.total_amount:
                    raise AppException(f"Tendered amount ({tendered_amount}) is less than total amount ({order.total_amount})")
                change_due = (tendered_amount - order.total_amount).quantize(Decimal("0.01"))

                from app.models.payment import Payment
                payment = Payment(
                    tenant_id=tenant_id,
                    order_id=order.id,
                    customer_id=order.customer_id,
                    payment_method=data.payment.payment_method,
                    status="completed",
                    amount=order.total_amount,
                    amount_tendered=tendered_amount,
                    change_due=change_due,
                    transaction_id=data.payment.transaction_id or f"TXN-{uuid.uuid4().hex[:10].upper()}",
                    paid_at=datetime.utcnow(),
                )
                self.db.add(payment)
                self.db.flush()

                # Invoice generation
                invoice = None
                if data.generate_invoice:
                    from app.models.invoice_item import InvoiceItem
                    invoice_number = f"INV-{order.order_number}"
                    invoice = Invoice(
                        tenant_id=tenant_id,
                        store_id=order.store_id,
                        order_id=order.id,
                        invoice_number=invoice_number,
                        status="issued",
                        subtotal=order.subtotal,
                        discount_amount=order.discount_amount,
                        tax_amount=order.tax_amount,
                        cgst_amount=order.cgst_amount,
                        sgst_amount=order.sgst_amount,
                        igst_amount=order.igst_amount,
                        total_amount=order.total_amount,
                    )
                    self.db.add(invoice)
                    self.db.flush()

                    for item in order.items:
                        inv_item = InvoiceItem(
                            invoice_id=invoice.id,
                            product_id=item.product_id,
                            quantity=Decimal(str(item.quantity)),
                            unit_price=item.unit_price,
                            discount_amount=item.discount_amount,
                            gst_rate=Decimal("18.00"),
                            gst_amount=item.tax_amount,
                            total_amount=item.total_amount,
                        )
                        self.db.add(inv_item)

                    payment.invoice_id = invoice.id

                # Tracking
                tracking = OrderTracking(
                    order_id=order.id,
                    status=OrderStatus.CONFIRMED.value,
                    remarks="Instant POS checkout and payment settlement completed",
                )
                self.db.add(tracking)

            self.db.commit()
            self.db.refresh(order)
            if invoice:
                self.db.refresh(invoice)
            if payment:
                self.db.refresh(payment)

            return {
                "order": order,
                "payment": payment,
                "invoice": invoice,
                "change_due": change_due,
            }
        except Exception:
            self.db.rollback()
            raise

    def get_order_stats(
        self,
        tenant_id: int,
        store_id: Optional[int] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> dict:
        query = self.db.query(Order).filter(Order.tenant_id == tenant_id)
        if store_id is not None:
            query = query.filter(Order.store_id == store_id)
        if date_from is not None:
            query = query.filter(Order.created_at >= date_from)
        if date_to is not None:
            query = query.filter(Order.created_at <= date_to)

        orders = query.all()
        total_orders = len(orders)
        draft_orders = sum(1 for o in orders if o.status == OrderStatus.DRAFT.value)
        confirmed_orders = sum(1 for o in orders if o.status == OrderStatus.CONFIRMED.value)
        completed_orders = sum(1 for o in orders if o.status in (OrderStatus.DELIVERED.value, "completed"))
        cancelled_orders = sum(1 for o in orders if o.status == OrderStatus.CANCELLED.value)

        revenue_orders = [o for o in orders if o.status not in (OrderStatus.CANCELLED.value, OrderStatus.DRAFT.value)]
        total_revenue = sum((o.total_amount for o in revenue_orders), Decimal("0.00")).quantize(Decimal("0.01"))
        avg_order_value = (
            (total_revenue / Decimal(len(revenue_orders))).quantize(Decimal("0.01"))
            if revenue_orders
            else Decimal("0.00")
        )

        return {
            "total_orders": total_orders,
            "total_revenue": total_revenue,
            "draft_orders": draft_orders,
            "confirmed_orders": confirmed_orders,
            "completed_orders": completed_orders,
            "cancelled_orders": cancelled_orders,
            "average_order_value": avg_order_value,
        }

    def get_order_receipt(
        self,
        tenant_id: int,
        order_id: int,
    ) -> dict:
        order = self.get_order(tenant_id, order_id)
        store = self.db.query(Store).filter(Store.id == order.store_id, Store.tenant_id == tenant_id).first()
        store_name = store.name if store else "Retail Store"
        store_code = store.code if store else None
        store_address = f"{store.city or ''}, {store.state or ''} {store.pincode or ''}".strip(", ") if store else None

        customer_name = None
        customer_phone = None
        if order.customer:
            customer_name = order.customer.name
            customer_phone = order.customer.phone

        items_receipt = []
        for it in order.items:
            p_name = it.product_name or (it.product.name if it.product else f"Product #{it.product_id}")
            items_receipt.append({
                "name": p_name,
                "quantity": it.quantity,
                "unit_price": it.unit_price,
                "tax_amount": it.tax_amount,
                "discount_amount": it.discount_amount,
                "total_amount": it.total_amount,
            })

        lines = []
        lines.append("=" * 40)
        lines.append(store_name.center(40))
        if store_code:
            lines.append(f"Store Code: {store_code}".center(40))
        if store_address:
            lines.append(store_address.center(40))
        lines.append("-" * 40)
        lines.append(f"Order #: {order.order_number}")
        created_str = order.created_at.strftime("%Y-%m-%d %H:%M:%S") if order.created_at else ""
        lines.append(f"Date:    {created_str}")
        if customer_name:
            lines.append(f"Cust:    {customer_name} ({customer_phone or 'N/A'})")
        lines.append("-" * 40)
        lines.append(f"{'Item':<18} {'Qty':>3} {'Price':>8} {'Total':>8}")
        lines.append("-" * 40)
        for it in items_receipt:
            name_cut = it["name"][:18]
            lines.append(f"{name_cut:<18} {it['quantity']:>3} {it['unit_price']:>8.2f} {it['total_amount']:>8.2f}")
        lines.append("-" * 40)
        lines.append(f"{'Subtotal:':<24} {order.subtotal:>15.2f}")
        if order.discount_amount > 0:
            lines.append(f"{'Discount:':<24} -{order.discount_amount:>14.2f}")
        if order.cgst_amount > 0:
            lines.append(f"{'CGST:':<24} {order.cgst_amount:>15.2f}")
        if order.sgst_amount > 0:
            lines.append(f"{'SGST:':<24} {order.sgst_amount:>15.2f}")
        if order.igst_amount > 0:
            lines.append(f"{'IGST:':<24} {order.igst_amount:>15.2f}")
        if order.round_off != 0:
            lines.append(f"{'Round Off:':<24} {order.round_off:>15.2f}")
        lines.append("-" * 40)
        lines.append(f"{'TOTAL AMOUNT:':<20} INR {order.total_amount:>15.2f}")
        lines.append(f"Payment Status: {order.payment_status.upper()}")
        if order.payment_method:
            lines.append(f"Payment Method: {order.payment_method.upper()}")
        lines.append("=" * 40)
        lines.append("Thank you for shopping with us!".center(40))
        lines.append("=" * 40)

        formatted_receipt = "\n".join(lines)

        return {
            "order_id": order.id,
            "order_number": order.order_number,
            "store_name": store_name,
            "store_code": store_code,
            "store_address": store_address,
            "customer_name": customer_name,
            "customer_phone": customer_phone,
            "items": items_receipt,
            "subtotal": order.subtotal,
            "discount_amount": order.discount_amount,
            "cgst_amount": order.cgst_amount,
            "sgst_amount": order.sgst_amount,
            "igst_amount": order.igst_amount,
            "tax_amount": order.tax_amount,
            "round_off": order.round_off,
            "total_amount": order.total_amount,
            "payment_status": order.payment_status,
            "payment_method": order.payment_method,
            "created_at": order.created_at,
            "formatted_receipt": formatted_receipt,
        }

    def _generate_order_thermal_image(self, ctx: dict) -> bytes:
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
        if ctx.get("store_code"):
            sc_txt = f"Store Code: {ctx.get('store_code')}"
            scbbox = draw.textbbox((0, 0), sc_txt, font=font_small)
            draw.text(((width - (scbbox[2] - scbbox[0])) // 2, y), sc_txt, font=font_small, fill=(100, 100, 100))
            y += 18

        # Header centered
        rep_txt = "SALES ORDER RECEIPT"
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

        # Order Details
        draw_kv("Order Number", str(ctx.get("order_number", "")))
        created_at = ctx.get("created_at")
        dt_str = created_at.strftime("%Y-%m-%d %H:%M") if isinstance(created_at, datetime) else str(created_at or "")
        draw_kv("Date & Time", dt_str)
        if ctx.get("customer_name"):
            draw_kv("Customer", f"{ctx.get('customer_name')} ({ctx.get('customer_phone') or 'N/A'})")

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

        # Item Rows
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

        # Subtotals & Tax
        draw_kv("Subtotal", f"Rs. {Decimal(str(ctx.get('subtotal', 0))):.2f}")
        if ctx.get("discount_amount") and Decimal(str(ctx.get("discount_amount"))) > 0:
            draw_kv("Discount", f"-Rs. {Decimal(str(ctx.get('discount_amount'))):.2f}", fill_r=(185, 28, 28))
        if ctx.get("cgst_amount") and Decimal(str(ctx.get("cgst_amount"))) > 0:
            draw_kv("CGST", f"Rs. {Decimal(str(ctx.get('cgst_amount'))):.2f}")
        if ctx.get("sgst_amount") and Decimal(str(ctx.get("sgst_amount"))) > 0:
            draw_kv("SGST", f"Rs. {Decimal(str(ctx.get('sgst_amount'))):.2f}")
        if ctx.get("igst_amount") and Decimal(str(ctx.get("igst_amount"))) > 0:
            draw_kv("IGST", f"Rs. {Decimal(str(ctx.get('igst_amount'))):.2f}")

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

        # Final crop to actual height
        final_height = y + 15
        final_img = img.crop((0, 0, width, final_height))
        draw_final = ImageDraw.Draw(final_img)
        draw_final.rectangle([(6, 6), (width - 7, final_height - 7)], outline=(200, 200, 200), width=1)

        buf = io.BytesIO()
        final_img.save(buf, format="PNG")
        return buf.getvalue()

    def _generate_order_thermal_html(self, ctx: dict, auto_print: bool = False) -> str:
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
        store_code_html = f'<div class="store-sub">Store: {ctx["store_code"]}</div>' if ctx.get("store_code") else ""

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Order Receipt {ctx.get('order_number')}</title>
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
    {store_code_html}
    <div class="doc-title">SALES ORDER RECEIPT</div>
  </div>

  <div class="divider"></div>

  <div class="row"><span class="lbl">Order Number</span><span class="val">{ctx.get('order_number')}</span></div>
  <div class="row"><span class="lbl">Date</span><span class="val">{dt_str}</span></div>
  {f'<div class="row"><span class="lbl">Customer</span><span class="val">{ctx.get("customer_name")}</span></div>' if ctx.get("customer_name") else ''}

  <div class="divider"></div>

  {items_rows}

  <div class="divider"></div>

  <div class="row"><span class="lbl">Subtotal</span><span class="val">Rs. {Decimal(str(ctx.get('subtotal', 0))):.2f}</span></div>
  {f'<div class="row"><span class="lbl">Discount</span><span class="val" style="color:#b91c1c">-Rs. {Decimal(str(ctx.get("discount_amount"))):.2f}</span></div>' if ctx.get("discount_amount") and Decimal(str(ctx.get("discount_amount"))) > 0 else ''}
  {f'<div class="row"><span class="lbl">CGST</span><span class="val">Rs. {Decimal(str(ctx.get("cgst_amount"))):.2f}</span></div>' if ctx.get("cgst_amount") and Decimal(str(ctx.get("cgst_amount"))) > 0 else ''}
  {f'<div class="row"><span class="lbl">SGST</span><span class="val">Rs. {Decimal(str(ctx.get("sgst_amount"))):.2f}</span></div>' if ctx.get("sgst_amount") and Decimal(str(ctx.get("sgst_amount"))) > 0 else ''}
  {f'<div class="row"><span class="lbl">IGST</span><span class="val">Rs. {Decimal(str(ctx.get("igst_amount"))):.2f}</span></div>' if ctx.get("igst_amount") and Decimal(str(ctx.get("igst_amount"))) > 0 else ''}

  <div class="highlight-box">
    <span class="hl-title">TOTAL AMOUNT</span>
    <span class="hl-val">Rs. {Decimal(str(ctx.get('total_amount', 0))):.2f}</span>
  </div>

  <div class="row"><span class="lbl">Status</span><span class="val">{str(ctx.get('payment_status', 'PAID')).upper()}</span></div>
  {f'<div class="row"><span class="lbl">Method</span><span class="val">{str(ctx.get("payment_method")).upper()}</span></div>' if ctx.get("payment_method") else ''}

  <div class="divider"></div>

  <div class="center store-sub" style="margin-top: 10px;">
    Thank you for shopping with us!
  </div>
</div>
</body>
</html>"""

    def _generate_order_thermal_pdf(self, ctx: dict) -> bytes:
        import io
        from PIL import Image
        from reportlab.lib.utils import ImageReader
        from reportlab.pdfgen import canvas

        img_bytes = self._generate_order_thermal_image(ctx)
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

    def export_order_thermal(
        self,
        tenant_id: int,
        order_id: int,
        mode: Any = "preview",
        user: Optional[User] = None,
    ) -> Response:
        data = self.get_order_receipt(tenant_id, order_id)
        mode_val = str(getattr(mode, "value", mode) or "preview").lower().strip()
        ord_num = data.get("order_number", f"ORD-{order_id}")

        # 1. Preview mode (Default) -> Visual 80mm receipt PNG rendered directly in Swagger UI
        if mode_val == OrderThermalMode.preview.value:
            img_bytes = self._generate_order_thermal_image(data)
            return Response(
                content=img_bytes,
                media_type="image/png",
                headers={
                    "Content-Disposition": f"inline; filename=order_{ord_num}_thermal.png",
                    "X-Order-Print-Type": "80mm-PNG-Preview",
                },
            )

        # 2. View mode -> Inline styled HTML page with auto-print dialog
        if mode_val == OrderThermalMode.view.value:
            html_content = self._generate_order_thermal_html(data, auto_print=True)
            return HTMLResponse(
                content=html_content,
                status_code=200,
                headers={"Content-Disposition": f"inline; filename=order_{ord_num}_thermal.html"},
            )

        # 3. Download mode -> ESC/POS text file attachment download
        if mode_val == OrderThermalMode.download.value:
            text_payload = data["formatted_receipt"]
            return Response(
                content=text_payload.encode("utf-8"),
                media_type="text/plain; charset=utf-8",
                headers={
                    "Content-Disposition": f"attachment; filename=order_{ord_num}_thermal.txt",
                    "X-Order-Print-Type": "ESC/POS",
                },
            )

        # 4. PDF mode -> 80mm Thermal Receipt PDF download
        if mode_val == OrderThermalMode.pdf.value:
            pdf_bytes = self._generate_order_thermal_pdf(data)
            return Response(
                content=pdf_bytes,
                media_type="application/pdf",
                headers={
                    "Content-Disposition": f"attachment; filename=order_{ord_num}_thermal.pdf",
                    "X-Order-Print-Type": "80mm-PDF",
                },
            )

        # 5. HTML mode -> Styled raw HTML layout
        if mode_val == OrderThermalMode.html.value:
            html_content = self._generate_order_thermal_html(data, auto_print=False)
            return HTMLResponse(
                content=html_content,
                status_code=200,
                headers={"Content-Disposition": f"inline; filename=order_{ord_num}_thermal.html"},
            )

        # 6. JSON mode -> Structured JSON payload
        if mode_val == OrderThermalMode.json.value:
            return JSONResponse(content=OrderReceiptResponse.model_validate(data).model_dump(mode="json"))

        # 7. Text mode -> Raw ESC/POS text stream
        if mode_val == OrderThermalMode.text.value:
            return Response(
                content=data["formatted_receipt"].encode("utf-8"),
                media_type="text/plain; charset=utf-8",
                headers={
                    "Content-Disposition": f"inline; filename=order_{ord_num}_thermal.txt",
                    "X-Order-Print-Type": "ESC/POS",
                },
            )

        raise AppException(f"Unsupported delivery mode: '{mode_val}'")

    def export_orders(
        self,
        tenant_id: int,
        format: str = "excel",
        store_id: Optional[int] = None,
        status: Optional[str] = None,
        order_type: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> tuple[BytesIO, str, str]:
        orders = self.repo.list_orders(
            tenant_id=tenant_id,
            store_id=store_id,
            status=status,
            order_type=order_type,
            date_from=date_from,
            date_to=date_to,
            skip=0,
            limit=10000,
        )

        headers = [
            "Order ID",
            "Order Number",
            "Store ID",
            "Order Type",
            "Status",
            "Payment Status",
            "Payment Method",
            "Items Count",
            "Subtotal",
            "Discount Amount",
            "Tax Amount",
            "Total Amount",
            "Created At",
        ]

        rows = []
        for o in orders:
            rows.append([
                o.id,
                o.order_number,
                o.store_id,
                o.order_type,
                o.status,
                o.payment_status,
                o.payment_method or "",
                len(o.items),
                float(o.subtotal),
                float(o.discount_amount),
                float(o.tax_amount),
                float(o.total_amount),
                o.created_at.strftime("%Y-%m-%d %H:%M:%S") if o.created_at else "",
            ])

        if format == "excel":
            output = ExcelExportService().export_to_stream(
                sheet_title="Orders",
                headers=headers,
                rows=rows,
            )
            return (
                output,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "orders.xlsx",
            )
        elif format == "csv":
            import csv
            from io import StringIO
            str_output = StringIO()
            writer = csv.writer(str_output)
            writer.writerow(headers)
            writer.writerows(rows)
            bytes_output = BytesIO(str_output.getvalue().encode("utf-8"))
            bytes_output.seek(0)
            return (
                bytes_output,
                "text/csv",
                "orders.csv",
            )
        else:
            raise AppException("Unsupported export format", status_code=400)

from app.services.customer_service import CustomerService
