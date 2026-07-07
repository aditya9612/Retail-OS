import uuid
from decimal import Decimal

from sqlalchemy.orm import Session

from sqlalchemy import extract

from app.core.exceptions import AppException, NotFoundException
from app.models.customer import Customer
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product   import Product
from app.repositories.order_repo import OrderRepository
from app.schemas.order import OrderCreate, OrderItemCreate, OrderUpdate
from app.services.inventory_service import InventoryService
from app.utils.constants import OrderStatus, OrderType, StockMovementType


class OrderService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = OrderRepository(db)
        self.inventory_service = InventoryService(db)

    def _generate_order_number(self) -> str:
        return f"ORD-{uuid.uuid4().hex[:8].upper()}"

    def _calculate_item_totals(self, product: Product, item: OrderItemCreate) -> OrderItem:
        unit_price = item.unit_price or product.price
        subtotal = unit_price * item.quantity - item.discount
        tax_rate = product.gst_rate
        tax_amount = (subtotal * tax_rate / Decimal("100")).quantize(Decimal("0.01"))
        total = subtotal + tax_amount
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

    def _recalculate_order(self, order: Order) -> None:
        subtotal = sum((i.unit_price * i.quantity - i.discount for i in order.items), Decimal("0"))
        tax_amount = sum((i.tax_amount for i in order.items), Decimal("0"))
        order.subtotal = subtotal
        order.tax_amount = tax_amount
        order.total_amount = subtotal + tax_amount - order.discount_amount

    def create_order(self, tenant_id: int, user_id: int, data: OrderCreate) -> Order:
        order = Order(
            tenant_id=tenant_id,
            store_id=data.store_id,
            customer_id=data.customer_id,
            user_id=user_id,
            order_number=self._generate_order_number(),
            order_type=data.order_type,
            status=OrderStatus.DRAFT.value,
            coupon_code=data.coupon_code,
            discount_amount=data.discount_amount,
            delivery_address=data.delivery_address,
            notes=data.notes,
        )
        for item_data in data.items:
            products= self.db.query(Product).filter(Product.id == item_data.product_id, Product.tenant_id == tenant_id).first()
            if not product:
                raise NotFoundException(f"products{item_data.product_id} not found")
            order.items.append(self._calculate_item_totals(product, item_data))
        self._recalculate_order(order)
        return self.repo.create(order)

    def get_order(self, tenant_id: int, order_id: int) -> Order:
        order = self.repo.get_by_id(order_id, tenant_id)
        if not order:
            raise NotFoundException("Order not found")
        return order

    def list_orders(self, tenant_id: int, store_id: int | None = None, page: int = 1, page_size: int = 20):
        skip = (page - 1) * page_size
        return self.repo.list_orders(tenant_id, store_id, skip, page_size)

    def update_order(self, tenant_id: int, order_id: int, data: OrderUpdate) -> Order:
        order = self.get_order(tenant_id, order_id)
        if order.status not in (OrderStatus.DRAFT.value, OrderStatus.CONFIRMED.value):
            raise AppException("Order cannot be updated in current status")
        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(order, key, value)
        self._recalculate_order(order)
        return self.repo.update(order)

    def confirm_order(self, tenant_id: int, order_id: int) -> Order:
        order = self.get_order(tenant_id, order_id)
        if order.status != OrderStatus.DRAFT.value:
            raise AppException("Only draft orders can be confirmed")
        for item in order.items:
            from app.schemas.inventory import StockOutRequest
            self.inventory_service.stock_out(
                tenant_id,
                StockOutRequest(store_id=order.store_id, product_id=item.product_id, quantity=item.quantity),
            )
        order.status = OrderStatus.CONFIRMED.value
        return self.repo.update(order)

    def cancel_order(self, tenant_id: int, order_id: int) -> Order:
        order = self.get_order(tenant_id, order_id)
        order.status = OrderStatus.CANCELLED.value
        return self.repo.update(order)

    def get_customer_history(self, tenant_id: int, customer_id: int) -> list[Order]:
        return (
            self.db.query(Order)
            .filter(Order.tenant_id == tenant_id, Order.customer_id == customer_id)
            .order_by(Order.created_at.desc())
            .all()
        )


class CustomerService:
    def __init__(self, db: Session):
        self.db = db

    def create_customer(self, tenant_id: int, data) -> Customer:
         customer = Customer(tenant_id=tenant_id,
         total_spend=0, 
         **data.model_dump())
         self.db.add(customer)
         self.db.commit()
         self.db.refresh(customer)
         return customer

    def get_customer(self, tenant_id: int, customer_id: int) -> Customer:
        customer = self.db.query(Customer).filter(Customer.id == customer_id, Customer.tenant_id == tenant_id).first()
        if not customer:
            raise NotFoundException("Customer not found")
        return customer

    def list_customers(self, tenant_id: int) -> list[Customer]:
        return self.db.query(Customer).filter(Customer.tenant_id == tenant_id).all()

    def update_customer(self, tenant_id: int, customer_id: int, data) -> Customer:
        customer = self.get_customer(tenant_id, customer_id)
        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(customer, key, value)
        self.db.commit()
        self.db.refresh(customer)
        return customer

    def delete_customer(self, tenant_id: int, customer_id: int):
        customer = self.get_customer(tenant_id, customer_id)

        customer.status = "inactive"

        self.db.commit()
        self.db.refresh(customer)

        return {
            "message": "Customer deleted successfully"
        }    

    def add_loyalty_points(self, tenant_id: int, customer_id: int, points: int) -> Customer:
        customer = self.get_customer(tenant_id, customer_id)
        customer.loyalty_points += points
        self.db.commit()
        self.db.refresh(customer)
        return customer

    def get_birthday_customers(self, tenant_id: int, month: int, day: int) -> list[Customer]:
        return (
            self.db.query(Customer)
            .filter(
                Customer.tenant_id == tenant_id,
                extract("month", Customer.birthday) == month,
                extract("day", Customer.birthday) == day,
            )
            .all()
        )
