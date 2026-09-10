import uuid
from datetime import date
from decimal import Decimal
from io import BytesIO

from openpyxl import Workbook
from sqlalchemy import extract, func
from sqlalchemy.orm import Session

from app.core.exceptions import (
    AppException,
    NotFoundException,
    ConflictException,
)
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
from app.models.coupon import Coupon
from app.models.order import Order, OrderTracking
from app.models.order_item import OrderItem
from app.models.product import Product
from app.models.delivery import Delivery
from app.repositories.order_repo import OrderRepository
from app.repositories.customer_repo import get_customers_for_export
from app.schemas.order import OrderCreate, OrderItemCreate, OrderUpdate
from app.services.inventory_service import InventoryService
from app.utils.constants import OrderStatus, StockMovementType

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle


class OrderService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = OrderRepository(db)
        self.inventory_service = InventoryService(db)

    def _generate_order_number(self) -> str:
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
    ) -> OrderItem:

        unit_price = (
            item.unit_price
            if item.unit_price is not None
            else product.price
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

        subtotal = (
            gross_amount - item.discount
        )

        tax_rate = product.gst_rate

        tax_amount = (
            subtotal
            * tax_rate
            / Decimal("100")
        ).quantize(
            Decimal("0.01")
        )

        total = (
            subtotal + tax_amount
        ).quantize(
            Decimal("0.01")
        )

        return OrderItem(
            product_id=product.id,
            product_name=product.name,
            sku=product.sku,
            quantity=item.quantity,
            unit_price=unit_price,
            discount=item.discount,
            tax_rate=tax_rate,
            tax_amount=tax_amount,
            total=total,
            variant=item.variant,
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

        order.subtotal = subtotal
        order.tax_amount = tax_amount

        order.total_amount = (
            subtotal
            + tax_amount
            - order.discount_amount
        ).quantize(
            Decimal("0.01")
        )

        if order.total_amount < 0:
            order.total_amount = Decimal("0.00")

    def create_order(
        self,
        tenant_id: int,
        user_id: int,
        data: OrderCreate,
    ) -> Order:

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
            order_number=self._generate_order_number(),
            order_type=data.order_type,
            status=OrderStatus.DRAFT.value,
            coupon_code=data.coupon_code,
            discount_amount=Decimal("0.00"),
            delivery_address=data.delivery_address,
            notes=data.notes,
        )

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

            order.items.append(
                self._calculate_item_totals(
                    product,
                    item_data,
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

        created_order = self.repo.create(order)

        if data.coupon_code:

            coupon.used_count += 1
            self.db.commit()
            self.db.refresh(created_order)

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
            tenant_id,
            store_id,
            skip,
            page_size,
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

        for item in order.items:

            self.inventory_service.stock_out(
                tenant_id,
                StockOutRequest(
                    store_id=order.store_id,
                    product_id=item.product_id,
                    quantity=item.quantity,
                ),
            )

        order.status = OrderStatus.CONFIRMED.value

        delivery = Delivery(
            tenant_id=tenant_id,
            order_id=order.id,
            status="pending",
        )

        self.db.add(delivery)

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

            customer.total_spend = (
                customer.total_spend
                + order.total_amount
            )

        return self.repo.update(order)

    def cancel_order(
        self,
        tenant_id: int,
        order_id: int,
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

        order.status = OrderStatus.CANCELLED.value

        tracking = OrderTracking(
            order_id=order.id,
            status=OrderStatus.CANCELLED.value,
            remarks="Order cancelled",
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
                OrderTracking.updated_at.desc()
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
                "data": [],
            }
        return orders


class CustomerService:

    def __init__(self, db: Session):
        self.db = db

    def create_customer(
        self,
        tenant_id: int,
        data,
    ) -> Customer:

        if data.email:

            email_val = (
                str(data.email)
                .strip()
                .lower()
            )

            existing_email = (
                self.db.query(Customer)
                .filter(
                    Customer.email == email_val,
                    Customer.tenant_id == tenant_id,
                )
                .first()
            )

            if existing_email:
                raise ConflictException(
                    "Email already exists"
                )

        existing_phone = (
            self.db.query(Customer)
            .filter(
                Customer.phone == data.phone,
                Customer.tenant_id == tenant_id,
            )
            .first()
        )

        if existing_phone:
            raise ConflictException(
                "Phone number already exists"
            )

        if data.gstin:

            existing_gstin = (
                self.db.query(Customer)
                .filter(
                    Customer.gstin == data.gstin,
                    Customer.tenant_id == tenant_id,
                )
                .first()
            )

            if existing_gstin:
                raise ConflictException(
                    "GSTIN already exists"
                )

        customer_data = data.model_dump()

        if customer_data.get("email"):
            customer_data["email"] = (
                str(customer_data["email"])
                .strip()
                .lower()
            )

        customer = Customer(
            tenant_id=tenant_id,
            total_spend=0,
            loyalty_points=0,
            **customer_data,
        )

        self.db.add(customer)
        self.db.commit()
        self.db.refresh(customer)

        return customer

    def get_customer(
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
                "Customer not found"
            )

        return customer

    def list_customers(
        self,
        tenant_id: int,
    ) -> list[Customer]:

        return (
            self.db.query(Customer)
            .filter(
                Customer.tenant_id == tenant_id
            )
            .all()
        )

    def update_customer(
        self,
        tenant_id: int,
        customer_id: int,
        data,
    ) -> Customer:

        customer = self.get_customer(
            tenant_id,
            customer_id,
        )

        dump_data = data.model_dump(
            exclude_unset=True
        )

        if "email" in dump_data and dump_data["email"]:

            email_val = (
                str(dump_data["email"])
                .strip()
                .lower()
            )

            existing_email = (
                self.db.query(Customer)
                .filter(
                    Customer.email == email_val,
                    Customer.tenant_id == tenant_id,
                    Customer.id != customer_id,
                )
                .first()
            )

            if existing_email:
                raise ConflictException(
                    "Email already exists"
                )

            dump_data["email"] = email_val

        if "phone" in dump_data and dump_data["phone"]:

            existing_phone = (
                self.db.query(Customer)
                .filter(
                    Customer.phone == dump_data["phone"],
                    Customer.tenant_id == tenant_id,
                    Customer.id != customer_id,
                )
                .first()
            )

            if existing_phone:
                raise ConflictException(
                    "Phone number already exists"
                )

        if "gstin" in dump_data and dump_data["gstin"]:

            existing_gstin = (
                self.db.query(Customer)
                .filter(
                    Customer.gstin == dump_data["gstin"],
                    Customer.tenant_id == tenant_id,
                    Customer.id != customer_id,
                )
                .first()
            )

            if existing_gstin:
                raise ConflictException(
                    "GSTIN already exists"
                )

        for key, value in dump_data.items():
            setattr(
                customer,
                key,
                value,
            )

        self.db.commit()
        self.db.refresh(customer)

        return customer

    def update_customer_status(
        self,
        tenant_id: int,
        customer_id: int,
        status: str,
    ):

        customer = self.get_customer(
            tenant_id,
            customer_id,
        )

        customer.status = status

        self.db.commit()
        self.db.refresh(customer)

        return customer

    def add_loyalty_points(
        self,
        tenant_id: int,
        customer_id: int,
        points: int,
    ):

        customer = self.get_customer(
            tenant_id,
            customer_id,
        )

        current_points = (
            customer.loyalty_points or 0
        )

        new_balance = (
            current_points + points
        )

        customer.loyalty_points = new_balance

        loyalty = LoyaltyPoint(
            customer_id=customer_id,
            points_earned=points,
            points_redeemed=0,
            balance_points=new_balance,
        )

        self.db.add(loyalty)
        self.db.commit()
        self.db.refresh(loyalty)

        return loyalty

    def get_birthday_customers(
        self,
        tenant_id: int,
        month: int,
        day: int,
    ):

        customers = (
            self.db.query(Customer)
            .filter(
                Customer.tenant_id == tenant_id,
                Customer.birthday.isnot(None),
                func.extract(
                    "month",
                    Customer.birthday,
                ) == month,
                func.extract(
                    "day",
                    Customer.birthday,
                ) == day,
            )
            .all()
        )
        if not customers:
            return {
                "success": True,
                "message": "No customers with birthdays found",
                "data": [],
            }
        return customers

    def create_feedback(
        self,
        tenant_id: int,
        data,
    ):

        self.get_customer(
            tenant_id,
            data.customer_id,
        )

        if data.invoice_id is not None:

            invoice = (
                self.db.query(Invoice)
                .filter(
                    Invoice.id == data.invoice_id,
                    Invoice.tenant_id == tenant_id,
                )
                .first()
            )

            if not invoice:
                raise NotFoundException(
                    "Invoice not found"
                )

        feedback = CustomerFeedback(
            customer_id=data.customer_id,
            invoice_id=data.invoice_id,
            rating=data.rating,
            comments=data.comments,
            suggestions=data.suggestions,
        )

        self.db.add(feedback)
        self.db.commit()
        self.db.refresh(feedback)

        return feedback

    def get_feedback(
        self,
        tenant_id: int,
        customer_id: int | None = None,
    ):

        if customer_id is not None:
            self.get_customer(
                tenant_id,
                customer_id,
            )

        query = (
            self.db.query(CustomerFeedback)
            .join(
                Customer,
                Customer.id
                == CustomerFeedback.customer_id,
            )
            .filter(
                Customer.tenant_id == tenant_id
            )
        )

        if customer_id is not None:

            query = query.filter(
                CustomerFeedback.customer_id
                == customer_id
            )

        feedbacks = (
            query
            .order_by(
                CustomerFeedback.created_at.desc()
            )
            .all()
        )

        if customer_id is not None and not feedbacks:
            return {
                "success": True,
                "message": "No feedback found for this customer",
                "data": [],
            }

        return feedbacks

    def get_wallet(
        self,
        tenant_id: int,
        customer_id: int,
    ):

        customer = self.get_customer(
            tenant_id,
            customer_id,
        )

        wallet = (
            self.db.query(CustomerWallet)
            .filter(
                CustomerWallet.customer_id
                == customer.id
            )
            .first()
        )

        if not wallet:

            wallet = CustomerWallet(
                customer_id=customer.id,
                current_balance=Decimal("0.00"),
            )

            self.db.add(wallet)
            self.db.commit()
            self.db.refresh(wallet)

        return wallet

    def credit_wallet(
        self,
        tenant_id: int,
        data,
    ):

        wallet = self.get_wallet(
            tenant_id,
            data.customer_id,
        )

        existing_tx = (
            self.db.query(WalletTransaction)
            .join(
                CustomerWallet,
                CustomerWallet.id
                == WalletTransaction.wallet_id,
            )
            .join(
                Customer,
                Customer.id
                == CustomerWallet.customer_id,
            )
            .filter(
                Customer.tenant_id == tenant_id,
                WalletTransaction.reference_no
                == data.reference_no,
            )
            .first()
        )

        if existing_tx:
            raise ConflictException(
                "Reference number already exists"
            )

        current_balance = (
            Decimal(
                str(
                    wallet.current_balance or 0
                )
            )
            + Decimal(
                str(data.amount)
            )
        )

        wallet.current_balance = current_balance

        transaction = WalletTransaction(
            wallet_id=wallet.id,
            transaction_type="CREDIT",
            amount=data.amount,
            reference_no=data.reference_no,
            remarks=data.remarks,
        )

        self.db.add(transaction)
        self.db.commit()

        self.db.refresh(wallet)
        self.db.refresh(transaction)

        return {
            "id": transaction.id,
            "customer_id": data.customer_id,
            "amount": float(data.amount),
            "reference_no": data.reference_no,
            "remarks": data.remarks,
            "balance": float(
                wallet.current_balance
            ),
            "current_balance": float(
                wallet.current_balance
            ),
        }

    def debit_wallet(
        self,
        tenant_id: int,
        data,
    ):

        wallet = self.get_wallet(
            tenant_id,
            data.customer_id,
        )

        existing_tx = (
            self.db.query(WalletTransaction)
            .join(
                CustomerWallet,
                CustomerWallet.id
                == WalletTransaction.wallet_id,
            )
            .join(
                Customer,
                Customer.id
                == CustomerWallet.customer_id,
            )
            .filter(
                Customer.tenant_id == tenant_id,
                WalletTransaction.reference_no
                == data.reference_no,
            )
            .first()
        )

        if existing_tx:
            raise ConflictException(
                "Reference number already exists"
            )

        current_balance = Decimal(
            str(
                wallet.current_balance or 0
            )
        )

        debit_amount = Decimal(
            str(data.amount)
        )

        if current_balance < debit_amount:
            raise AppException(
                "Insufficient wallet balance"
            )

        wallet.current_balance = (
            current_balance
            - debit_amount
        )

        transaction = WalletTransaction(
            wallet_id=wallet.id,
            transaction_type="DEBIT",
            amount=data.amount,
            reference_no=data.reference_no,
            remarks=data.remarks,
        )

        self.db.add(transaction)
        self.db.commit()

        self.db.refresh(wallet)
        self.db.refresh(transaction)

        return {
            "id": transaction.id,
            "customer_id": data.customer_id,
            "amount": float(data.amount),
            "reference_no": data.reference_no,
            "remarks": data.remarks,
            "balance": float(
                wallet.current_balance
            ),
            "current_balance": float(
                wallet.current_balance
            ),
        }

    def get_wallet_transactions(
        self,
        tenant_id: int,
        customer_id: int,
    ):

        wallet = self.get_wallet(
            tenant_id,
            customer_id,
        )

        transactions = (
            self.db.query(WalletTransaction)
            .filter(
                WalletTransaction.wallet_id
                == wallet.id
            )
            .order_by(
                WalletTransaction.created_at.desc()
            )
            .all()
        )
        if not transactions:
            return {
                "success": True,
                "message": "No wallet transactions found for this customer",
                "data": [],
            }
        return transactions

    def earn_loyalty_points(
        self,
        tenant_id: int,
        data,
    ):

        customer = self.get_customer(
            tenant_id,
            data.customer_id,
        )

        if data.invoice_id is not None:

            invoice = (
                self.db.query(Invoice)
                .join(Order, Order.id == Invoice.order_id)
                .filter(
                    Invoice.id == data.invoice_id,
                    Invoice.tenant_id == tenant_id,
                )
                .first()
            )

            if not invoice:
                raise NotFoundException(
                    "Invoice not found"
                )

            if invoice.order and invoice.order.customer_id is not None and invoice.order.customer_id != data.customer_id:
                raise AppException(
                    "Invoice belongs to a different customer",
                    status_code=422,
                )

        current_points = (
            customer.loyalty_points or 0
        )

        new_balance = (
            current_points + data.points
        )

        customer.loyalty_points = new_balance

        loyalty = LoyaltyPoint(
            customer_id=data.customer_id,
            invoice_id=data.invoice_id,
            points_earned=data.points,
            points_redeemed=0,
            balance_points=new_balance,
        )

        self.db.add(loyalty)
        self.db.commit()
        self.db.refresh(loyalty)

        return loyalty

    def redeem_loyalty_points(
        self,
        tenant_id: int,
        data,
    ):

        customer = self.get_customer(
            tenant_id,
            data.customer_id,
        )

        current_points = (
            customer.loyalty_points or 0
        )

        if current_points < data.points:
            raise AppException(
                "Insufficient loyalty points"
            )

        new_balance = (
            current_points - data.points
        )

        customer.loyalty_points = new_balance

        loyalty = LoyaltyPoint(
            customer_id=data.customer_id,
            points_earned=0,
            points_redeemed=data.points,
            balance_points=new_balance,
        )

        self.db.add(loyalty)
        self.db.commit()
        self.db.refresh(loyalty)

        return loyalty

    def get_loyalty(
        self,
        tenant_id: int,
        customer_id: int,
    ):

        self.get_customer(
            tenant_id,
            customer_id,
        )

        loyalty = (
            self.db.query(LoyaltyPoint)
            .filter(
                LoyaltyPoint.customer_id
                == customer_id
            )
            .order_by(
                LoyaltyPoint.created_at.desc()
            )
            .first()
        )

        if loyalty is None:
            raise NotFoundException(
                "No loyalty record found"
            )

        return loyalty

    def get_loyalty_history(
        self,
        tenant_id: int,
        customer_id: int,
    ):

        self.get_customer(
            tenant_id,
            customer_id,
        )

        history = (
            self.db.query(LoyaltyPoint)
            .filter(
                LoyaltyPoint.customer_id
                == customer_id
            )
            .order_by(
                LoyaltyPoint.created_at.desc()
            )
            .all()
        )

        if not history:
            return {
                "success": True,
                "message": "No loyalty history found for this customer",
                "data": [],
            }

        return history

    def send_communication(
        self,
        tenant_id: int,
        data,
    ):

        self.get_customer(
            tenant_id,
            data.customer_id,
        )

        comm_type = (
            data.communication_type
            .strip()
            .upper()
        )

        communication = CustomerCommunication(
            customer_id=data.customer_id,
            communication_type=comm_type,
            message=data.message.strip(),
            delivery_status="SENT",
        )

        self.db.add(communication)
        self.db.commit()
        self.db.refresh(communication)

        return communication

    def get_communications(
        self,
        tenant_id: int,
    ):

        return (
            self.db.query(CustomerCommunication)
            .join(
                Customer,
                Customer.id
                == CustomerCommunication.customer_id,
            )
            .filter(
                Customer.tenant_id == tenant_id
            )
            .order_by(
                CustomerCommunication.sent_at.desc()
            )
            .all()
        )

    def get_communications_by_type(
        self,
        tenant_id: int,
        communication_type: str,
    ):

        return (
            self.db.query(CustomerCommunication)
            .join(
                Customer,
                Customer.id
                == CustomerCommunication.customer_id,
            )
            .filter(
                Customer.tenant_id == tenant_id,
                CustomerCommunication.communication_type
                == communication_type.strip().upper(),
            )
            .order_by(
                CustomerCommunication.sent_at.desc()
            )
            .all()
        )

    def create_referral(
        self,
        tenant_id: int,
        data,
    ):

        self.get_customer(
            tenant_id,
            data.customer_id,
        )

        if data.referred_customer_id:

            if (
                data.referred_customer_id
                == data.customer_id
            ):
                raise AppException(
                    "Customer cannot refer themselves",
                    status_code=422,
                )

            self.get_customer(
                tenant_id,
                data.referred_customer_id,
            )

            existing = (
                self.db.query(CustomerReferral)
                .filter(
                    CustomerReferral.customer_id
                    == data.customer_id,
                    CustomerReferral.referred_customer_id
                    == data.referred_customer_id,
                )
                .first()
            )

            if existing:
                raise ConflictException(
                    "Referral already exists for this customer"
                )

        code = (
            f"REF-{uuid.uuid4().hex[:8].upper()}"
        )

        for _ in range(5):

            existing_code = (
                self.db.query(CustomerReferral)
                .filter(
                    CustomerReferral.referral_code
                    == code
                )
                .first()
            )

            if not existing_code:
                break

            code = (
                f"REF-{uuid.uuid4().hex[:8].upper()}"
            )

        referral = CustomerReferral(
            customer_id=data.customer_id,
            referred_customer_id=data.referred_customer_id,
            referral_code=code,
            reward_amount=(
                100
                if data.referred_customer_id
                else 0
            ),
        )

        self.db.add(referral)
        self.db.commit()
        self.db.refresh(referral)

        return referral

    def get_referrals(
        self,
        tenant_id: int,
    ):

        return (
            self.db.query(CustomerReferral)
            .join(
                Customer,
                Customer.id
                == CustomerReferral.customer_id,
            )
            .filter(
                Customer.tenant_id == tenant_id
            )
            .all()
        )

    def create_note(
        self,
        tenant_id: int,
        data,
        user_id: int | None = None,
    ):

        self.get_customer(
            tenant_id,
            data.customer_id,
        )

        note = CustomerNote(
            customer_id=data.customer_id,
            note=data.note.strip(),
            created_by=user_id,
        )

        self.db.add(note)
        self.db.commit()
        self.db.refresh(note)

        return note

    def get_notes(
        self,
        tenant_id: int,
        customer_id: int | None = None,
    ):

        if customer_id is not None:
            self.get_customer(
                tenant_id,
                customer_id,
            )

        query = (
            self.db.query(CustomerNote)
            .join(
                Customer,
                Customer.id
                == CustomerNote.customer_id,
            )
            .filter(
                Customer.tenant_id == tenant_id
            )
        )

        if customer_id is not None:
            query = query.filter(
                CustomerNote.customer_id
                == customer_id
            )

        notes = (
            query
            .order_by(
                CustomerNote.created_at.desc()
            )
            .all()
        )

        if customer_id is not None and not notes:
            return {
                "success": True,
                "message": "No notes found for this customer",
                "data": [],
            }

        return notes

    def send_campaign(
        self,
        tenant_id: int,
        data,
    ):

        if not data.customer_ids:
            raise AppException(
                "customer_ids cannot be empty"
            )

        comm_type = (
            data.communication_type
            .strip()
            .upper()
        )

        if comm_type not in (
            "SMS",
            "WHATSAPP",
            "EMAIL",
        ):
            raise AppException(
                "Invalid communication type"
            )

        for customer_id in data.customer_ids:
            self.get_customer(
                tenant_id,
                customer_id,
            )

        for customer_id in data.customer_ids:

            communication = CustomerCommunication(
                customer_id=customer_id,
                communication_type=comm_type,
                message=data.message.strip(),
                delivery_status="SENT",
            )

            self.db.add(communication)

        self.db.commit()

        return {
            "message": "Campaign sent successfully",
            "total_customers": len(
                data.customer_ids
            ),
        }

    def get_top_customers(
        self,
        tenant_id: int,
    ):

        return (
            self.db.query(Customer)
            .filter(
                Customer.tenant_id == tenant_id
            )
            .order_by(
                Customer.total_spend.desc()
            )
            .limit(10)
            .all()
        )

    def get_retention_report(
        self,
        tenant_id: int,
    ):

        total = (
            self.db.query(Customer)
            .filter(
                Customer.tenant_id == tenant_id
            )
            .count()
        )

        active = (
            self.db.query(Customer)
            .filter(
                Customer.tenant_id == tenant_id,
                Customer.status == "active",
            )
            .count()
        )

        inactive = (
            self.db.query(Customer)
            .filter(
                Customer.tenant_id == tenant_id,
                Customer.status == "inactive",
            )
            .count()
        )

        retention_rate = 0

        if total > 0:
            retention_rate = round(
                (active / total) * 100,
                2,
            )

        return {
            "total_customers": total,
            "active_customers": active,
            "inactive_customers": inactive,
            "retention_rate": retention_rate,
        }

    def get_lifetime_value(
        self,
        tenant_id: int,
    ):

        customers = (
            self.db.query(Customer)
            .filter(
                Customer.tenant_id == tenant_id
            )
            .order_by(
                Customer.total_spend.desc()
            )
            .all()
        )

        result = []

        for customer in customers:

            result.append({
                "customer_id": customer.id,
                "customer_name": customer.name,
                "total_spend": customer.total_spend,
                "loyalty_points": (
                    customer.loyalty_points
                ),
            })

        return result

    def get_loyalty_report(
        self,
        tenant_id: int,
    ):

        loyalty = (
            self.db.query(LoyaltyPoint)
            .join(
                Customer,
                Customer.id
                == LoyaltyPoint.customer_id,
            )
            .filter(
                Customer.tenant_id == tenant_id
            )
            .all()
        )

        result = []

        for item in loyalty:

            result.append({
                "customer_id": item.customer_id,
                "customer_name": item.customer.name,
                "points_earned": item.points_earned,
                "points_redeemed": item.points_redeemed,
                "balance_points": item.balance_points,
            })

        return result

    def export_directory(
        self,
        tenant_id: int,
        status="all",
        format="excel",
    ):

        customers = get_customers_for_export(
            self.db,
            tenant_id,
            status,
        )

        if format == "excel":
            return self._create_excel(
                customers
            )

        elif format == "pdf":
            return self._create_pdf(
                customers
            )

        raise ValueError(
            "Invalid format"
        )

    def _create_excel(
        self,
        customers,
    ):

        workbook = Workbook()

        worksheet = workbook.active
        worksheet.title = "Customer Directory"

        worksheet.append([
            "ID",
            "Name",
            "Email",
            "Phone",
            "Status",
            "Loyalty Points",
        ])

        for customer in customers:

            worksheet.append([
                customer.id,
                customer.name,
                customer.email or "",
                customer.phone or "",
                customer.status,
                customer.loyalty_points or 0,
            ])

        output = BytesIO()

        workbook.save(output)
        output.seek(0)

        return output

    def _create_pdf(
        self,
        customers,
    ):

        output = BytesIO()

        document = SimpleDocTemplate(
            output,
            pagesize=A4,
        )

        data = [
            [
                "ID",
                "Name",
                "Email",
                "Phone",
                "Status",
                "Points",
            ]
        ]

        for customer in customers:

            data.append([
                customer.id,
                customer.name,
                customer.email or "",
                customer.phone or "",
                customer.status,
                customer.loyalty_points or 0,
            ])

        table = Table(data)

        table.setStyle(
            TableStyle([
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, 0),
                    colors.grey,
                ),
                (
                    "TEXTCOLOR",
                    (0, 0),
                    (-1, 0),
                    colors.white,
                ),
                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    1,
                    colors.black,
                ),
                (
                    "PADDING",
                    (0, 0),
                    (-1, -1),
                    5,
                ),
            ])
        )

        document.build([table])

        output.seek(0)

        return output