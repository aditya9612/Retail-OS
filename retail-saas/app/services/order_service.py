import uuid
from decimal import Decimal

from sqlalchemy.orm import Session

from sqlalchemy import extract

from app.core.exceptions import AppException, NotFoundException
from app.models.customer import Customer ,CustomerFeedback,CustomerWallet, WalletTransaction ,LoyaltyPoint,CustomerCommunication,CustomerReferral,CustomerNote
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
    
    def create_feedback(self, data):
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


    def get_feedback(self, customer_id: int | None = None):
        query = self.db.query(CustomerFeedback)

        if customer_id is not None:
            query = query.filter(
                CustomerFeedback.customer_id == customer_id
            )

        return query.all()
    

    def get_wallet(self, tenant_id: int, customer_id: int):
        customer = self.get_customer(tenant_id, customer_id)

        wallet = (
            self.db.query(CustomerWallet)
            .filter(CustomerWallet.customer_id == customer.id)
            .first()
        )
        if not wallet:
            wallet = CustomerWallet(
                customer_id=customer.id,
                current_balance=0
            )
            self.db.add(wallet)
            self.db.commit()
            self.db.refresh(wallet)

        return wallet
    
    
    def credit_wallet(self, tenant_id: int, data):
        wallet = self.get_wallet(tenant_id, data.customer_id)

        wallet.current_balance += data.amount

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

        return wallet
    

    def debit_wallet(self, tenant_id: int, data):
        wallet = self.get_wallet(tenant_id, data.customer_id)

        if wallet.current_balance < data.amount:
            raise AppException("Insufficient wallet balance")

        wallet.current_balance -= data.amount

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

        return wallet
    

    def get_wallet_transactions(self, tenant_id: int, customer_id: int):
        wallet = self.get_wallet(tenant_id, customer_id)

        return (
            self.db.query(WalletTransaction)
            .filter(WalletTransaction.wallet_id == wallet.id)
            .order_by(WalletTransaction.created_at.desc())
            .all()
        )
    
    def earn_loyalty_points(self, tenant_id: int, data):
        customer = self.get_customer(tenant_id, data.customer_id)

        loyalty = LoyaltyPoint(
            customer_id=data.customer_id,
            invoice_id=data.invoice_id,
            points_earned=data.points,
            points_redeemed=0,
            balance_points=customer.loyalty_points + data.points,
        )

        customer.loyalty_points += data.points

        self.db.add(loyalty)
        self.db.commit()
        self.db.refresh(loyalty)

        return loyalty
    
    def redeem_loyalty_points(self, tenant_id: int, data):
        customer = self.get_customer(tenant_id, data.customer_id)

        if customer.loyalty_points < data.points:
            raise AppException("Insufficient loyalty points")

        customer.loyalty_points -= data.points

        loyalty = LoyaltyPoint(
            customer_id=data.customer_id,
            points_earned=0,
            points_redeemed=data.points,
            balance_points=customer.loyalty_points,
        )

        self.db.add(loyalty)
        self.db.commit()
        self.db.refresh(loyalty)

        return loyalty
    
    def get_loyalty(self, tenant_id: int, customer_id: int):
        self.get_customer(tenant_id, customer_id)

        loyalty = (
            self.db.query(LoyaltyPoint)
            .filter(LoyaltyPoint.customer_id == customer_id)
            .order_by(LoyaltyPoint.created_at.desc())
            .first()
        )

        if loyalty is None:
            raise NotFoundException("No loyalty record found")

        return loyalty
    
    def get_loyalty_history(self, tenant_id: int, customer_id: int):
        self.get_customer(tenant_id, customer_id)

        return (
            self.db.query(LoyaltyPoint)
            .filter(LoyaltyPoint.customer_id == customer_id)
            .order_by(LoyaltyPoint.created_at.desc())
            .all()
        )

    def send_communication(self, tenant_id: int, data):
    # Customer exists ka check kara
        self.get_customer(tenant_id, data.customer_id)

        communication = CustomerCommunication(
            customer_id=data.customer_id,
            communication_type=data.communication_type,
            message=data.message,
            delivery_status="SENT"
        )

        self.db.add(communication)
        self.db.commit()
        self.db.refresh(communication)

        return communication

    def get_communications(self, tenant_id: int):
        return (
            self.db.query(CustomerCommunication)
            .join(
                Customer,
                Customer.id == CustomerCommunication.customer_id
            )
            .filter(Customer.tenant_id == tenant_id)
            .order_by(CustomerCommunication.sent_at.desc())
            .all()
        )    

    def create_referral(self, tenant_id: int, data):
        self.get_customer(tenant_id, data.customer_id)

        referral = CustomerReferral(
            customer_id=data.customer_id,
            referred_customer_id=data.referred_customer_id,
            referral_code=str(uuid.uuid4())[:8].upper(),
            reward_amount=100 if data.referred_customer_id else 0,
        )

        self.db.add(referral)
        self.db.commit()
        self.db.refresh(referral)

        return referral


    def get_referrals(self, tenant_id: int):
        return (
            self.db.query(CustomerReferral)
            .join(Customer, Customer.id == CustomerReferral.customer_id)
            .filter(Customer.tenant_id == tenant_id)
            .all()
        )

    def create_note(self, tenant_id: int, data):
        self.get_customer(tenant_id, data.customer_id)

        note = CustomerNote(
            customer_id=data.customer_id,
            note=data.note,
            created_by=None,
        )

        self.db.add(note)
        self.db.commit()
        self.db.refresh(note)

        return note 

    def get_notes(self, tenant_id: int, customer_id: int | None = None):

        query = (
            self.db.query(CustomerNote)
            .join(Customer, Customer.id == CustomerNote.customer_id)
            .filter(Customer.tenant_id == tenant_id)
        )

        if customer_id is not None:
            query = query.filter(CustomerNote.customer_id == customer_id)

        return (
            query
            .order_by(CustomerNote.created_at.desc())
            .all()
        ) 

    def send_campaign(self, tenant_id: int, data):
        for customer_id in data.customer_ids:

            self.get_customer(tenant_id, customer_id)

            communication = CustomerCommunication(
                customer_id=customer_id,
                communication_type=data.communication_type,
                message=data.message,
                delivery_status="SENT",
            )

            self.db.add(communication)

        self.db.commit()

        return {
            "message": "Campaign sent successfully",
            "total_customers": len(data.customer_ids),
        }

    def get_top_customers(self, tenant_id: int):
        return (
            self.db.query(Customer)
            .filter(Customer.tenant_id == tenant_id)
            .order_by(Customer.total_spend.desc())
            .limit(10)
            .all()
        )

    def get_retention_report(self, tenant_id: int):

        total = (
            self.db.query(Customer)
            .filter(Customer.tenant_id == tenant_id)
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
            retention_rate = round((active / total) * 100, 2)

        return {
            "total_customers": total,
            "active_customers": active,
            "inactive_customers": inactive,
            "retention_rate": retention_rate,
        } 

    def get_lifetime_value(self, tenant_id: int):

        customers = (
            self.db.query(Customer)
            .filter(Customer.tenant_id == tenant_id)
            .order_by(Customer.total_spend.desc())
            .all()
        )

        result = []

        for customer in customers:
            result.append({
                "customer_id": customer.id,
                "customer_name": customer.name,
                "total_spend": customer.total_spend,
                "loyalty_points": customer.loyalty_points,
            })

        return result 

    def get_loyalty_report(self, tenant_id: int):

        loyalty = (
            self.db.query(LoyaltyPoint)
            .join(
                Customer,
                Customer.id == LoyaltyPoint.customer_id
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



     


