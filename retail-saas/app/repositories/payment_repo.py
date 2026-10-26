from sqlalchemy.orm import Session

from app.models.payment import (
    Payment,
    PaymentGateway,
    PaymentSplit,
)
from app.schemas.payment import (
    PaymentGatewayCreate,
    PaymentGatewayUpdate,
)


def get_payment_by_transaction_id(
    db: Session,
    tenant_id: int,
    transaction_id: str,
):
    from sqlalchemy import or_
    return (
        db.query(Payment)
        .filter(
            Payment.tenant_id == tenant_id,
            or_(
                Payment.transaction_id == transaction_id,
                Payment.gateway_transaction_id == transaction_id,
            ),
        )
        .first()
    )


def verify_payment(
    db: Session,
    tenant_id: int,
    payment_id: int,
    verify_data,
):
    payment = (
        db.query(Payment)
        .filter(
            Payment.id == payment_id,
            Payment.tenant_id == tenant_id,
        )
        .first()
    )

    if payment is None:
        return None

    payment.transaction_id = verify_data.transaction_id
    payment.status = verify_data.status
    payment.gateway_response = verify_data.gateway_response

    db.commit()
    db.refresh(payment)

    return payment


def gateway_name_exists(
    db: Session,
    tenant_id: int,
    gateway_name: str,
    exclude_id: int | None = None,
) -> bool:
    query = db.query(PaymentGateway).filter(
        PaymentGateway.tenant_id == tenant_id,
        PaymentGateway.gateway_name == gateway_name,
    )

    if exclude_id is not None:
        query = query.filter(
            PaymentGateway.id != exclude_id
        )

    return query.first() is not None


def merchant_id_exists(
    db: Session,
    tenant_id: int,
    merchant_id: str,
    exclude_id: int | None = None,
) -> bool:
    query = db.query(PaymentGateway).filter(
        PaymentGateway.tenant_id == tenant_id,
        PaymentGateway.merchant_id == merchant_id,
    )

    if exclude_id is not None:
        query = query.filter(
            PaymentGateway.id != exclude_id
        )

    return query.first() is not None


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
        .filter(
            PaymentGateway.tenant_id == tenant_id,
        )
        .order_by(PaymentGateway.id.desc())
        .all()
    )


def update_gateway(
    db: Session,
    tenant_id: int,
    gateway_id: int,
    data: PaymentGatewayUpdate,
):
    gateway = get_gateway(
        db,
        tenant_id,
        gateway_id,
    )

    if gateway is None:
        return None

    update_data = data.model_dump(
        exclude_unset=True,
        exclude_none=True,
    )

    if "merchant_id" in update_data:
        gateway.api_key = update_data.pop("merchant_id")

    for key, value in update_data.items():
        setattr(gateway, key, value)

    db.commit()
    db.refresh(gateway)

    return gateway


def delete_gateway(
    db: Session,
    tenant_id: int,
    gateway_id: int,
):
    gateway = get_gateway(
        db,
        tenant_id,
        gateway_id,
    )

    if gateway is None:
        return None

    from app.models.payment import Settlement
    has_payments = db.query(Payment).filter(Payment.gateway_id == gateway_id, Payment.tenant_id == tenant_id).first()
    has_settlements = db.query(Settlement).filter(Settlement.gateway_id == gateway_id, Settlement.tenant_id == tenant_id).first()

    if has_payments or has_settlements:
        gateway.is_active = False
        db.commit()
        db.refresh(gateway)
        return gateway

    db.delete(gateway)
    db.commit()

    return gateway


def get_payment_for_split(
    db: Session,
    tenant_id: int,
    payment_id: int,
):
    return (
        db.query(Payment)
        .filter(
            Payment.id == payment_id,
            Payment.tenant_id == tenant_id,
        )
        .first()
    )


def create_payment_split(
    db: Session,
    tenant_id: int,
    data,
):
    payment = get_payment_for_split(
        db,
        tenant_id,
        data.transaction_id,
    )

    if payment is None:
        return None

    split = PaymentSplit(
        transaction_id=payment.id,
        payment_method=data.payment_method,
        amount=data.amount,
    )

    db.add(split)
    db.commit()
    db.refresh(split)

    return split


def list_payment_splits(
    db: Session,
    tenant_id: int,
):
    return (
        db.query(PaymentSplit)
        .join(
            Payment,
            Payment.id == PaymentSplit.payment_id,
        )
        .filter(
            Payment.tenant_id == tenant_id,
        )
        .order_by(PaymentSplit.id.desc())
        .all()
    )


def get_payment_split(
    db: Session,
    tenant_id: int,
    split_id: int,
):
    return (
        db.query(PaymentSplit)
        .join(
            Payment,
            Payment.id == PaymentSplit.payment_id,
        )
        .filter(
            PaymentSplit.id == split_id,
            Payment.tenant_id == tenant_id,
        )
        .first()
    )