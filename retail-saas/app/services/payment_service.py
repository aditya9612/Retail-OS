import uuid
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.exceptions import AppException, NotFoundException
from app.models.order import Order
from app.models.payment import Payment
from app.schemas.order import PaymentCreate
from app.utils.constants import PaymentMethod, PaymentStatus


class PaymentService:
    def __init__(self, db: Session):
        self.db = db

    def record_payment(self, tenant_id: int, data: PaymentCreate) -> Payment:
        order = self.db.query(Order).filter(Order.id == data.order_id, Order.tenant_id == tenant_id).first()
        if not order:
            raise NotFoundException("Order not found")
        payment = Payment(
            tenant_id=tenant_id,
            order_id=data.order_id,
            payment_method=data.payment_method,
            amount=data.amount,
            transaction_id=data.transaction_id,
            status=PaymentStatus.COMPLETED.value,
        )
        self.db.add(payment)
        self.db.commit()
        self.db.refresh(payment)
        return payment

    def get_payment(self, tenant_id: int, payment_id: int) -> Payment:
        payment = self.db.query(Payment).filter(Payment.id == payment_id, Payment.tenant_id == tenant_id).first()
        if not payment:
            raise NotFoundException("Payment not found")
        return payment

    def list_payments(self, tenant_id: int, order_id: int | None = None) -> list[Payment]:
        query = self.db.query(Payment).filter(Payment.tenant_id == tenant_id)
        if order_id:
            query = query.filter(Payment.order_id == order_id)
        return query.order_by(Payment.created_at.desc()).all()

    def refund_payment(self, tenant_id: int, payment_id: int) -> Payment:
        payment = self.get_payment(tenant_id, payment_id)
        if payment.status == PaymentStatus.REFUNDED.value:
            raise AppException("Payment already refunded")
        payment.status = PaymentStatus.REFUNDED.value
        self.db.commit()
        self.db.refresh(payment)
        return payment

    def generate_qr_payload(self, tenant_id: int, order_id: int, upi_id: str = "merchant@upi") -> dict:
        order = self.db.query(Order).filter(Order.id == order_id, Order.tenant_id == tenant_id).first()
        if not order:
            raise NotFoundException("Order not found")
        amount = str(order.total_amount)
        payload = f"upi://pay?pa={upi_id}&pn=RetailStore&am={amount}&tn=Order{order.order_number}"
        return {"qr_payload": payload, "amount": amount, "order_number": order.order_number}

    def webhook_handler(self, payload: dict) -> dict:
        return {"status": "received", "payload": payload}
