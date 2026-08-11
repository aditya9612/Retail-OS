from sqlalchemy.orm import Session
from app.models.payment import Payment, PaymentGateway ,PaymentSplit
from app.schemas.payment import (
    PaymentGatewayCreate,
    PaymentGatewayUpdate
)

def verify_payment(db, payment_id: int, verify_data):
    payment = (
        db.query(Payment)
        .filter(Payment.id == payment_id)
        .first()
    )

    if not payment:
        return None

    payment.transaction_id = verify_data.transaction_id
    payment.status = verify_data.status
    payment.gateway_response = verify_data.gateway_response

    db.commit()
    db.refresh(payment)

    return payment

def create_gateway(
    db: Session,
    tenant_id: int,
    data: PaymentGatewayCreate,
):
    gateway = PaymentGateway(
        tenant_id=tenant_id,
        gateway_name=data.gateway_name,
        merchant_id=data.merchant_id,
        api_key=data.api_key,
        secret_key=data.secret_key,
        webhook_secret=data.webhook_secret,
        environment=data.environment,
        status=data.status,
    )

    db.add(gateway)
    db.commit()
    db.refresh(gateway)
    return gateway


def get_gateway(
    db: Session,
    tenant_id: int,
    gateway_id: int,
):
    return (
        db.query(PaymentGateway)
        .filter(
            PaymentGateway.id == gateway_id,
            PaymentGateway.tenant_id == tenant_id,
        )
        .first()
    )


def list_gateways(
    db: Session,
    tenant_id: int,
):
    return (
        db.query(PaymentGateway)
        .filter(PaymentGateway.tenant_id == tenant_id)
        .all()
    )


def update_gateway(
    db: Session,
    gateway: PaymentGateway,
    data: PaymentGatewayUpdate,
):
    update_data = data.model_dump(exclude_unset=True)

    for key, value in update_data.items():
        setattr(gateway, key, value)

    db.commit()
    db.refresh(gateway)

    return gateway


def delete_gateway(
    db: Session,
    gateway: PaymentGateway,
):
    db.delete(gateway)
    db.commit()    

def create_payment_split(db, split):
    db.add(split)
    db.commit()
    db.refresh(split)
    return split


def list_payment_splits(db):
    return db.query(PaymentSplit).all()


def get_payment_split(db, split_id):
    return (
        db.query(PaymentSplit)
        .filter(PaymentSplit.id == split_id)
        .first()
    )