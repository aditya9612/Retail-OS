from datetime import date, datetime
from decimal import Decimal
import json
import re
from urllib.parse import urlencode

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.order import Order
from app.models.payment import (
    Payment,
    PaymentGateway,
    PaymentSplit,
    PaymentWebhookLog,
    Settlement,
)
from app.repositories.payment_repo import (
    create_gateway,
    create_payment_split,
    delete_gateway,
    get_gateway,
    get_payment_by_transaction_id,
    get_payment_split,
    list_gateways,
    list_payment_splits,
    update_gateway,
    verify_payment,
)
from app.schemas.payment import (
    PaymentCreate,
    PaymentGatewayCreate,
    PaymentGatewayUpdate,
    PaymentSplitCreate,
    PaymentVerify,
    SettlementCreate,
    PaymentWebhookLogCreate,
    PaymentWebhookRequest,
)


class PaymentService:
    def __init__(self, db: Session, tenant_id: int):
        self.db = db
        self.tenant_id = tenant_id

    def record_payment(self, data: PaymentCreate):
        order = (
            self.db.query(Order)
            .filter(
                Order.id == data.order_id,
                Order.tenant_id == self.tenant_id,
            )
            .first()
        )

        if order is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Order not found",
            )

        if data.amount < Decimal("1.00"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Payment amount must be at least 1.00",
            )

        if data.payment_method == "cash" and data.transaction_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cash payment must not contain a transaction ID",
            )

        if data.payment_method != "cash" and not data.transaction_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Transaction ID is required for non-cash payments",
            )

        if data.transaction_id:
            existing = get_payment_by_transaction_id(
                self.db,
                self.tenant_id,
                data.transaction_id,
            )

            if existing is not None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Transaction ID already exists",
                )

        order_total = Decimal(str(order.total_amount))

        if data.amount > order_total:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Payment amount cannot exceed order total",
            )

        payment = Payment(
            tenant_id=self.tenant_id,
            order_id=data.order_id,
            payment_method=data.payment_method,
            status="completed",
            amount=data.amount,
            transaction_id=data.transaction_id,
            paid_at=datetime.utcnow(),
        )

        self.db.add(payment)

        try:
            self.db.commit()
            self.db.refresh(payment)
        except IntegrityError:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Payment could not be created because the transaction already exists",
            )

        return payment

    def get_payment(self, payment_id: int):
        return (
            self.db.query(Payment)
            .filter(
                Payment.id == payment_id,
                Payment.tenant_id == self.tenant_id,
            )
            .first()
        )

    def list_payments(self, order_id=None, status=None, method=None):
        query = self.db.query(Payment).filter(
            Payment.tenant_id == self.tenant_id
        )

        if order_id is not None:
            order = (
                self.db.query(Order)
                .filter(
                    Order.id == order_id,
                    Order.tenant_id == self.tenant_id,
                )
                .first()
            )

            if order is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Order not found",
                )

            query = query.filter(Payment.order_id == order_id)

        if status is not None:
            normalized_status = (
                "completed" if status == "success" else status
            )
            query = query.filter(Payment.status == normalized_status)

        if method is not None:
            query = query.filter(Payment.payment_method == method)

        return query.order_by(Payment.id.desc()).all()

    def refund_payment(self, payment_id: int):
        payment = self.get_payment(payment_id)

        if payment is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Payment not found",
            )

        if payment.status == "refunded":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Payment is already refunded",
            )

        if payment.status != "completed":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only completed payments can be refunded",
            )

        payment.status = "refunded"

        self.db.commit()
        self.db.refresh(payment)

        return payment

    def payment_history(self, status=None, method=None):
        return self.list_payments(
            status=status,
            method=method,
        )

    def generate_qr_payload(
        self,
        order_id,
        upi_id,
        amount=None,
    ):
        order = (
            self.db.query(Order)
            .filter(
                Order.id == order_id,
                Order.tenant_id == self.tenant_id,
            )
            .first()
        )

        if order is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Order not found",
            )

        upi_id = upi_id.strip()

        if not re.fullmatch(
            r"^[A-Za-z0-9][A-Za-z0-9._-]{1,100}@[A-Za-z0-9][A-Za-z0-9.-]{1,100}$",
            upi_id,
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid UPI ID",
            )

        qr_amount = (
            Decimal(str(amount))
            if amount is not None
            else Decimal(str(order.total_amount))
        )

        if qr_amount < Decimal("1.00"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="QR payment amount must be at least 1.00",
            )

        params = {
            "pa": upi_id,
            "pn": "Retail Store",
            "am": f"{qr_amount:.2f}",
            "cu": "INR",
            "tn": f"Order {order_id}",
        }

        return {
            "order_id": order_id,
            "upi_id": upi_id,
            "amount": qr_amount,
            "qr_payload": "upi://pay?" + urlencode(params),
        }

    def verify_payment_service(
        self,
        payment_id,
        data: PaymentVerify,
    ):
        payment = self.get_payment(payment_id)

        if payment is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Payment not found",
            )

        transaction_id = data.transaction_id.strip()

        if not transaction_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Transaction ID is required",
            )

        gateway_response = data.gateway_response.strip()

        if not gateway_response:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Gateway response is required",
            )

        existing = get_payment_by_transaction_id(
            self.db,
            self.tenant_id,
            transaction_id,
        )

        if existing is not None and existing.id != payment.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Transaction ID already belongs to another payment",
            )

        result = verify_payment(
            self.db,
            self.tenant_id,
            payment_id,
            data,
        )

        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Payment not found",
            )

        if result.status == "completed":
            result.paid_at = result.paid_at or datetime.utcnow()
            self.db.commit()
            self.db.refresh(result)

        return result

    def create_payment_split(
        self,
        data: PaymentSplitCreate,
    ):
        payment = (
            self.db.query(Payment)
            .filter(
                Payment.id == data.transaction_id,
                Payment.tenant_id == self.tenant_id,
            )
            .first()
        )

        if payment is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Payment not found",
            )

        existing_method = (
            self.db.query(PaymentSplit)
            .filter(
                PaymentSplit.transaction_id == payment.id,
                PaymentSplit.payment_method == data.payment_method,
            )
            .first()
        )

        if existing_method is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Payment method already exists in this split",
            )

        existing_total = (
            self.db.query(PaymentSplit)
            .filter(
                PaymentSplit.transaction_id == payment.id,
            )
            .all()
        )

        split_total = sum(
            (
                Decimal(str(item.amount))
                for item in existing_total
            ),
            Decimal("0.00"),
        )

        if split_total + data.amount > Decimal(str(payment.amount)):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Split payment total cannot exceed payment amount",
            )

        if data.amount < Decimal("1.00"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Split payment amount must be at least 1.00",
            )

        try:
            result = create_payment_split(
                self.db,
                self.tenant_id,
                data,
            )
        except IntegrityError:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Payment split could not be created",
            )

        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Payment not found",
            )

        return result

    def list_payment_splits(self, transaction_id=None):
        if transaction_id is not None:
            payment = (
                self.db.query(Payment)
                .filter(
                    Payment.id == transaction_id,
                    Payment.tenant_id == self.tenant_id,
                )
                .first()
            )

            if payment is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Payment not found",
                )

            return (
                self.db.query(PaymentSplit)
                .filter(
                    PaymentSplit.transaction_id == transaction_id,
                )
                .order_by(PaymentSplit.id.desc())
                .all()
            )

        return list_payment_splits(
            self.db,
            self.tenant_id,
        )

    def get_payment_split(self, split_id):
        result = get_payment_split(
            self.db,
            self.tenant_id,
            split_id,
        )

        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Payment split not found",
            )

        return result

    def create_settlement(
        self,
        data: SettlementCreate,
    ):
        if data.settlement_date < date.today():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Settlement date cannot be in the past",
            )

        gateway = get_gateway(
            self.db,
            self.tenant_id,
            data.gateway_id,
        )

        if gateway is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Payment gateway not found",
            )

        existing = (
            self.db.query(Settlement)
            .filter(
                Settlement.tenant_id == self.tenant_id,
                Settlement.reference_no == data.reference_no,
            )
            .first()
        )

        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Settlement reference number already exists",
            )

        if data.total_amount < Decimal("1.00"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Settlement amount must be at least 1.00",
            )

        settlement = Settlement(
            tenant_id=self.tenant_id,
            gateway_id=data.gateway_id,
            settlement_date=data.settlement_date,
            total_amount=data.total_amount,
            status=data.status,
            reference_no=data.reference_no,
            settlement_reference=data.reference_no,
            settled_at=(
                datetime.utcnow()
                if data.status == "completed"
                else None
            ),
        )

        self.db.add(settlement)

        try:
            self.db.commit()
            self.db.refresh(settlement)
        except IntegrityError:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Settlement could not be created",
            )

        return settlement

    def list_settlements(self):
        return (
            self.db.query(Settlement)
            .filter(
                Settlement.tenant_id == self.tenant_id,
            )
            .order_by(Settlement.id.desc())
            .all()
        )

    def get_settlement(self, settlement_id):
        result = (
            self.db.query(Settlement)
            .filter(
                Settlement.id == settlement_id,
                Settlement.tenant_id == self.tenant_id,
            )
            .first()
        )

        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Settlement not found",
            )

        return result

    def create_webhook_log(
        self,
        data: PaymentWebhookLogCreate,
    ):
        payment = get_payment_by_transaction_id(
            self.db,
            self.tenant_id,
            data.transaction_id,
        )

        if payment is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Payment transaction not found",
            )

        existing = (
            self.db.query(PaymentWebhookLog)
            .filter(
                PaymentWebhookLog.tenant_id == self.tenant_id,
                PaymentWebhookLog.event_type == data.event_type,
                PaymentWebhookLog.transaction_id == data.transaction_id,
            )
            .first()
        )

        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Webhook event already exists for this transaction",
            )

        try:
            payload = json.loads(data.payload)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Webhook payload must contain valid JSON",
            )

        if payload in ({}, [], "", None):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Webhook payload cannot be empty",
            )

        webhook = PaymentWebhookLog(
            tenant_id=self.tenant_id,
            event_type=data.event_type,
            transaction_id=data.transaction_id,
            payload=data.payload,
            status=data.status,
        )

        self.db.add(webhook)

        try:
            self.db.commit()
            self.db.refresh(webhook)
        except IntegrityError:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Webhook log could not be created",
            )

        return webhook

    def list_webhook_logs(self):
        return (
            self.db.query(PaymentWebhookLog)
            .filter(
                PaymentWebhookLog.tenant_id == self.tenant_id,
            )
            .order_by(PaymentWebhookLog.id.desc())
            .all()
        )

    def get_webhook_log(self, log_id):
        result = (
            self.db.query(PaymentWebhookLog)
            .filter(
                PaymentWebhookLog.id == log_id,
                PaymentWebhookLog.tenant_id == self.tenant_id,
            )
            .first()
        )

        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Webhook log not found",
            )

        return result

    def webhook_handler(
        self,
        data: PaymentWebhookRequest,
    ):
        payment = get_payment_by_transaction_id(
            self.db,
            self.tenant_id,
            data.transaction_id,
        )

        if payment is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Payment transaction not found",
            )

        existing = (
            self.db.query(PaymentWebhookLog)
            .filter(
                PaymentWebhookLog.tenant_id == self.tenant_id,
                PaymentWebhookLog.event_type == data.event_type,
                PaymentWebhookLog.transaction_id == data.transaction_id,
            )
            .first()
        )

        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Webhook event already processed",
            )

        webhook = PaymentWebhookLog(
            tenant_id=self.tenant_id,
            event_type=data.event_type,
            transaction_id=data.transaction_id,
            payload=json.dumps(data.payload),
            status=data.status,
        )

        normalized_status = (
            "completed"
            if data.status == "success"
            else data.status
        )

        payment.status = normalized_status

        if normalized_status == "completed":
            payment.paid_at = payment.paid_at or datetime.utcnow()

        self.db.add(webhook)

        try:
            self.db.commit()
            self.db.refresh(webhook)
            self.db.refresh(payment)
        except IntegrityError:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Webhook could not be processed",
            )

        return {
            "message": "Webhook processed successfully",
            "webhook_id": webhook.id,
            "payment_id": payment.id,
            "transaction_id": payment.transaction_id,
            "status": payment.status,
        }

    def create_gateway(
        self,
        data: PaymentGatewayCreate,
    ):
        existing_name = (
            self.db.query(PaymentGateway)
            .filter(
                PaymentGateway.tenant_id == self.tenant_id,
                PaymentGateway.gateway_name == data.gateway_name,
            )
            .first()
        )

        if existing_name is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Gateway name already exists",
            )

        existing_merchant = (
            self.db.query(PaymentGateway)
            .filter(
                PaymentGateway.tenant_id == self.tenant_id,
                PaymentGateway.merchant_id == data.merchant_id,
            )
            .first()
        )

        if existing_merchant is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Merchant ID already exists",
            )

        try:
            return create_gateway(
                self.db,
                self.tenant_id,
                data,
            )
        except IntegrityError:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Payment gateway could not be created",
            )

    def list_gateways(self):
        return list_gateways(
            self.db,
            self.tenant_id,
        )

    def get_gateway(self, gateway_id):
        result = get_gateway(
            self.db,
            self.tenant_id,
            gateway_id,
        )

        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Payment gateway not found",
            )

        return result

    def update_gateway(
        self,
        gateway_id,
        data: PaymentGatewayUpdate,
    ):
        gateway = get_gateway(
            self.db,
            self.tenant_id,
            gateway_id,
        )

        if gateway is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Payment gateway not found",
            )

        if data.gateway_name is not None:
            duplicate_name = (
                self.db.query(PaymentGateway)
                .filter(
                    PaymentGateway.tenant_id == self.tenant_id,
                    PaymentGateway.gateway_name == data.gateway_name,
                    PaymentGateway.id != gateway_id,
                )
                .first()
            )

            if duplicate_name is not None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Gateway name already exists",
                )

        if data.merchant_id is not None:
            duplicate_merchant = (
                self.db.query(PaymentGateway)
                .filter(
                    PaymentGateway.tenant_id == self.tenant_id,
                    PaymentGateway.merchant_id == data.merchant_id,
                    PaymentGateway.id != gateway_id,
                )
                .first()
            )

            if duplicate_merchant is not None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Merchant ID already exists",
                )

        try:
            result = update_gateway(
                self.db,
                self.tenant_id,
                gateway_id,
                data,
            )
        except IntegrityError:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Payment gateway could not be updated",
            )

        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Payment gateway not found",
            )

        return result

    def delete_gateway(self, gateway_id):
        gateway = get_gateway(
            self.db,
            self.tenant_id,
            gateway_id,
        )

        if gateway is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Payment gateway not found",
            )

        return delete_gateway(
            self.db,
            self.tenant_id,
            gateway_id,
        )