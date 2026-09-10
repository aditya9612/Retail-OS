from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal, Optional
import json
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


PaymentStatusValue = Literal[
    "pending",
    "completed",
    "success",
    "failed",
    "cancelled",
    "refunded",
]

PaymentMethodValue = Literal[
    "cash",
    "upi",
    "card",
    "wallet",
    "qr",
]

GatewayEnvironment = Literal[
    "TEST",
    "LIVE",
]

GatewayStatus = Literal[
    "ACTIVE",
    "INACTIVE",
]

SettlementStatus = Literal[
    "pending",
    "processing",
    "completed",
    "failed",
]

WebhookStatus = Literal[
    "received",
    "processed",
    "failed",
]


TRANSACTION_ID_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$"
)

GATEWAY_NAME_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9 -]{1,99}$"
)

MERCHANT_ID_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]{2,254}$"
)

REFERENCE_NO_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_-]{1,99}$"
)

UPI_ID_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]{1,100}@[A-Za-z0-9][A-Za-z0-9.-]{1,100}$"
)


def validate_transaction_id(value: str) -> str:
    value = value.strip()

    if not value:
        raise ValueError("Transaction ID cannot be empty")

    if value.lstrip("0") == "":
        raise ValueError("Transaction ID cannot be zero")

    if not TRANSACTION_ID_PATTERN.fullmatch(value):
        raise ValueError(
            "Transaction ID may contain only letters, numbers, hyphens and underscores"
        )

    if not any(character.isdigit() for character in value):
        raise ValueError("Transaction ID must contain at least one digit")

    return value


def validate_upi_id(value: str) -> str:
    value = value.strip()

    if not UPI_ID_PATTERN.fullmatch(value):
        raise ValueError("Invalid UPI ID format")

    return value


class PaymentCreate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    order_id: int = Field(
        ...,
        gt=0,
    )

    payment_method: PaymentMethodValue

    amount: Decimal = Field(
        ...,
        ge=Decimal("1.00"),
        max_digits=12,
        decimal_places=2,
    )

    transaction_id: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=100,
    )

    @field_validator("payment_method", mode="before")
    @classmethod
    def normalize_payment_method(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value

        value = value.strip().lower()

        if not value:
            raise ValueError("Payment method cannot be empty")

        return value

    @field_validator("transaction_id")
    @classmethod
    def validate_transaction(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None

        return validate_transaction_id(value)

    @model_validator(mode="after")
    def validate_transaction_requirement(self):
        if self.payment_method == "cash":
            if self.transaction_id is not None:
                raise ValueError(
                    "Transaction ID must not be provided for cash payments"
                )
        else:
            if self.transaction_id is None:
                raise ValueError(
                    "Transaction ID is required for non-cash payments"
                )

        return self


class PaymentVerify(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    transaction_id: str = Field(
        ...,
        min_length=1,
        max_length=100,
    )

    status: PaymentStatusValue

    gateway_response: str = Field(
        ...,
        min_length=1,
        max_length=1000,
    )

    @field_validator("transaction_id")
    @classmethod
    def validate_transaction(cls, value: str) -> str:
        return validate_transaction_id(value)

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value

        value = value.strip().lower()

        if not value:
            raise ValueError("Payment status cannot be empty")

        return value

    @field_validator("status")
    @classmethod
    def normalize_success_status(
        cls,
        value: PaymentStatusValue,
    ) -> PaymentStatusValue:
        if value == "success":
            return "completed"

        return value

    @field_validator("gateway_response")
    @classmethod
    def validate_gateway_response(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("Gateway response cannot be empty")

        return value


class PaymentGatewayCreate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    gateway_name: str = Field(
        ...,
        min_length=2,
        max_length=100,
    )

    merchant_id: str = Field(
        ...,
        min_length=3,
        max_length=255,
    )

    api_key: str = Field(
        ...,
        min_length=1,
        max_length=2000,
    )

    secret_key: str = Field(
        ...,
        min_length=1,
        max_length=2000,
    )

    webhook_secret: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=2000,
    )

    environment: GatewayEnvironment = "TEST"

    status: GatewayStatus = "ACTIVE"

    @field_validator("gateway_name")
    @classmethod
    def validate_gateway_name(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("Gateway name cannot be empty")

        if not GATEWAY_NAME_PATTERN.fullmatch(value):
            raise ValueError(
                "Gateway name may contain only letters, numbers, spaces and hyphens"
            )

        return value

    @field_validator("merchant_id")
    @classmethod
    def validate_merchant_id(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("Merchant ID cannot be empty")

        if not MERCHANT_ID_PATTERN.fullmatch(value):
            raise ValueError(
                "Invalid merchant ID format"
            )

        return value

    @field_validator("api_key", "secret_key", "webhook_secret")
    @classmethod
    def validate_credentials(
        cls,
        value: Optional[str],
    ) -> Optional[str]:
        if value is None:
            return None

        value = value.strip()

        if not value:
            raise ValueError("Credential cannot be empty")

        return value

    @field_validator("environment", mode="before")
    @classmethod
    def validate_environment(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value

        value = value.strip().upper()

        if not value:
            raise ValueError("Environment cannot be empty")

        return value

    @field_validator("status", mode="before")
    @classmethod
    def validate_gateway_status(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value

        value = value.strip().upper()

        if not value:
            raise ValueError("Gateway status cannot be empty")

        return value


class PaymentGatewayUpdate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    gateway_name: Optional[str] = Field(
        default=None,
        min_length=2,
        max_length=100,
    )

    merchant_id: Optional[str] = Field(
        default=None,
        min_length=3,
        max_length=255,
    )

    api_key: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=2000,
    )

    secret_key: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=2000,
    )

    webhook_secret: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=2000,
    )

    environment: Optional[GatewayEnvironment] = None

    status: Optional[GatewayStatus] = None

    @field_validator("gateway_name")
    @classmethod
    def validate_gateway_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None

        value = value.strip()

        if not GATEWAY_NAME_PATTERN.fullmatch(value):
            raise ValueError(
                "Gateway name may contain only letters, numbers, spaces and hyphens"
            )

        return value

    @field_validator("merchant_id")
    @classmethod
    def validate_merchant_id(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None

        value = value.strip()

        if not MERCHANT_ID_PATTERN.fullmatch(value):
            raise ValueError("Invalid merchant ID format")

        return value

    @field_validator("api_key", "secret_key", "webhook_secret")
    @classmethod
    def validate_credentials(
        cls,
        value: Optional[str],
    ) -> Optional[str]:
        if value is None:
            return None

        value = value.strip()

        if not value:
            raise ValueError("Credential cannot be empty")

        return value

    @field_validator("environment", mode="before")
    @classmethod
    def validate_environment(cls, value: Any) -> Any:
        if value is None:
            return None

        if not isinstance(value, str):
            return value

        value = value.strip().upper()

        if not value:
            raise ValueError("Environment cannot be empty")

        return value

    @field_validator("status", mode="before")
    @classmethod
    def validate_status(cls, value: Any) -> Any:
        if value is None:
            return None

        if not isinstance(value, str):
            return value

        value = value.strip().upper()

        if not value:
            raise ValueError("Gateway status cannot be empty")

        return value


class PaymentGatewayResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int
    tenant_id: int
    gateway_name: str
    merchant_id: str
    environment: str
    status: str
    created_at: datetime
    updated_at: datetime


class PaymentSplitCreate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    transaction_id: int = Field(
        ...,
        gt=0,
    )

    payment_method: PaymentMethodValue

    amount: Decimal = Field(
        ...,
        ge=Decimal("1.00"),
        max_digits=12,
        decimal_places=2,
    )

    @field_validator("payment_method", mode="before")
    @classmethod
    def normalize_payment_method(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value

        value = value.strip().lower()

        if not value:
            raise ValueError("Payment method cannot be empty")

        return value


class PaymentSplitResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int
    transaction_id: int
    payment_method: str
    amount: Decimal


class SettlementCreate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    gateway_id: int = Field(
        ...,
        gt=0,
    )

    settlement_date: date

    total_amount: Decimal = Field(
        ...,
        ge=Decimal("1.00"),
        max_digits=12,
        decimal_places=2,
    )

    status: SettlementStatus

    reference_no: str = Field(
        ...,
        min_length=2,
        max_length=100,
    )

    @field_validator("settlement_date")
    @classmethod
    def validate_settlement_date(cls, value: date) -> date:
        if value < date.today():
            raise ValueError(
                "Settlement date cannot be in the past"
            )

        return value

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value

        value = value.strip().lower()

        if not value:
            raise ValueError("Settlement status cannot be empty")

        return value

    @field_validator("reference_no")
    @classmethod
    def validate_reference_no(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("Reference number cannot be empty")

        if not REFERENCE_NO_PATTERN.fullmatch(value):
            raise ValueError("Invalid reference number format")

        return value


class SettlementResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int
    tenant_id: int
    gateway_id: int
    settlement_date: date
    total_amount: Decimal
    status: str
    reference_no: Optional[str] = None


class PaymentWebhookRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    event_type: str = Field(
        ...,
        min_length=1,
        max_length=100,
    )

    transaction_id: str = Field(
        ...,
        min_length=1,
        max_length=100,
    )

    payload: dict[str, Any] = Field(
        ...,
        min_length=1,
    )

    status: WebhookStatus

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("Event type cannot be empty")

        if value not in {
            "payment.completed",
            "payment.failed",
            "payment.refunded",
        }:
            raise ValueError("Unsupported payment event type")

        return value

    @field_validator("transaction_id")
    @classmethod
    def validate_transaction(cls, value: str) -> str:
        return validate_transaction_id(value)

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value

        value = value.strip().lower()

        if not value:
            raise ValueError("Webhook status cannot be empty")

        return value


class PaymentWebhookLogCreate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    event_type: str = Field(
        ...,
        min_length=1,
        max_length=100,
    )

    transaction_id: str = Field(
        ...,
        min_length=1,
        max_length=100,
    )

    payload: str = Field(
        ...,
        min_length=2,
        max_length=100000,
    )

    status: WebhookStatus = "received"

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("Event type cannot be empty")

        return value

    @field_validator("transaction_id")
    @classmethod
    def validate_transaction(cls, value: str) -> str:
        return validate_transaction_id(value)

    @field_validator("payload")
    @classmethod
    def validate_payload(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("Webhook payload cannot be empty")

        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            parsed = None

        if parsed in (None, {}, [], ""):
            raise ValueError("Webhook payload cannot be empty")

        return value

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value

        value = value.strip().lower()

        if not value:
            raise ValueError("Webhook status cannot be empty")

        return value


class PaymentWebhookLogResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int
    tenant_id: int
    event_type: str
    transaction_id: str
    payload: str
    status: str
    created_at: datetime
    updated_at: datetime