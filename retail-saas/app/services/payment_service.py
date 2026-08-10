import uuid
from decimal import Decimal
from datetime import datetime

from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.repositories.payment_repo import (
    create_gateway,
    get_gateway,
    list_gateways,
    update_gateway,
    delete_gateway,
    verify_payment,
    
)
from app.core.exceptions import AppException, NotFoundException
from app.models.order import Order
from app.models.payment import Payment,PaymentGateway, PaymentSplit,Settlement,PaymentWebhookLog
from app.schemas.order import PaymentCreate
from app.schemas.payment import (
    PaymentGatewayCreate,
    PaymentGatewayUpdate,
    PaymentGatewayResponse,
    PaymentVerify,
    PaymentSplitCreate,
    SettlementCreate,
    PaymentWebhookLogCreate,
    PaymentWebhookLogResponse,
)
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

    def verify_payment_service(self, payment_id, verify_data):
        payment = verify_payment(self.db, payment_id, verify_data)

        if not payment:
            raise HTTPException(
                status_code=404,
                detail="Payment not found"
            )

        return payment

    def payment_history(
        self,
        tenant_id: int,
        status: str = None,
        payment_method: str = None,
    ):
        query = self.db.query(Payment).filter(
            Payment.tenant_id == tenant_id
        )

        if status:
            query = query.filter(Payment.status == status)

        if payment_method:
            query = query.filter(
                Payment.payment_method == payment_method
            )

        return query.order_by(
            Payment.created_at.desc()
        ).all()   

    def create_payment_split(
        self,
        tenant_id: int,
        data: PaymentSplitCreate,
    ):
        split = PaymentSplit(
            transaction_id=data.transaction_id,
            payment_method=data.payment_method,
            amount=data.amount,
        )

        self.db.add(split)
        self.db.commit()
        self.db.refresh(split)

        return split

    def list_payment_splits(self):
        return self.db.query(PaymentSplit).all()

    def get_payment_split(self, split_id: int):
        split = (
            self.db.query(PaymentSplit)
            .filter(PaymentSplit.id == split_id)
            .first()
        )

        if not split:
            raise NotFoundException("Payment Split not found")

        return split 

    def create_settlement(
        self,
        tenant_id: int,
        data: SettlementCreate,
    ):
        settlement = Settlement(
           tenant_id=tenant_id,
           gateway_id=data.gateway_id,
           settlement_date=data.settlement_date,
           total_amount=data.total_amount,
           status=data.status,
           reference_no=data.reference_no,
        )

        self.db.add(settlement)
        self.db.commit()
        self.db.refresh(settlement)

        return settlement


    def list_settlements(self):
        return self.db.query(Settlement).all()


    def get_settlement(self, settlement_id: int):
        settlement = (
            self.db.query(Settlement)
            .filter(Settlement.id == settlement_id)
            .first()
        )

        if not settlement:
            raise NotFoundException("Settlement not found")

        return settlement

    def create_webhook_log(
        self,
        tenant_id: int,
        data: PaymentWebhookLogCreate,
    ):
        log = PaymentWebhookLog(
            tenant_id=tenant_id,
            event_type=data.event_type,
            transaction_id=data.transaction_id,
            payload=data.payload,
            status=data.status,
        )

        self.db.add(log)
        self.db.commit()
        self.db.refresh(log)

        return log


    def list_webhook_logs(self):
        return (
            self.db.query(PaymentWebhookLog)
            .order_by(PaymentWebhookLog.created_at.desc())
            .all()
        )


    def get_webhook_log(self, webhook_id: int):
        log = (
            self.db.query(PaymentWebhookLog)
            .filter(PaymentWebhookLog.id == webhook_id)
            .first()
        )

        if not log:
            raise NotFoundException("Webhook Log not found")

        return log 

    def create_payment_gateway(
        self,
        tenant_id: int,
        data: PaymentGatewayCreate,
    ):
        return create_gateway(
            self.db,
            tenant_id,
            data,
        )

    def list_payment_gateways(
        self,
        tenant_id: int,
    ):
        return list_gateways(
            self.db,
            tenant_id,
        )

    def get_payment_gateway(
        self,
        tenant_id: int,
        gateway_id: int,
    ):
        gateway = get_gateway(
            self.db,
            tenant_id,
            gateway_id,
        )

        if not gateway:
            raise NotFoundException("Payment Gateway not found")

        return gateway

    def update_payment_gateway(
        self,
        tenant_id: int,
        gateway_id: int,
        data: PaymentGatewayUpdate,
    ):
        gateway = get_gateway(
            self.db,
            tenant_id,
            gateway_id,
        )

        if not gateway:
            raise NotFoundException("Payment Gateway not found")

        return update_gateway(
            self.db,
            gateway,
            data,
        )

    def delete_payment_gateway(
        self,
        tenant_id: int,
        gateway_id: int,
    ):
        gateway = get_gateway(
            self.db,
            tenant_id,
            gateway_id,
        )

        if not gateway:
            raise NotFoundException("Payment Gateway not found")

        delete_gateway(
            self.db,
            gateway,
        )

        return True       
