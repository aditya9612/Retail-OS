from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.billing import (
    InvoiceReprintRequest,
    PaymentSplit,
    ReturnItemRequest,
)
from app.schemas.gst_rate import GstRateCreate
from app.utils.validators import validate_aadhaar_number


def test_gst_rate_rejects_all_zero_hsn_code():
    with pytest.raises(ValidationError, match="HSN code cannot consist only of zeroes"):
        GstRateCreate(hsn_code="0000", gst_rate=Decimal("18"))


def test_aadhaar_checksum_is_validated():
    assert validate_aadhaar_number("200000000009") == "200000000009"

    with pytest.raises(ValueError, match="checksum is invalid"):
        validate_aadhaar_number("234567890123")


@pytest.mark.parametrize(
    "payload",
    [
        {"condition": "unknown"},
        {"idempotency_key": "  "},
        {"refund_method": ""},
    ],
)
def test_return_request_rejects_invalid_values(payload):
    with pytest.raises(ValidationError):
        ReturnItemRequest(
            invoice_id=1,
            product_id=1,
            return_quantity=Decimal("1"),
            **payload,
        )


def test_return_request_accepts_notes_alias():
    request = ReturnItemRequest(
        invoice_id=1,
        product_id=1,
        return_quantity=Decimal("1"),
        notes="Damaged packaging",
    )

    assert request.reason == "Damaged packaging"


def test_payment_reference_and_printer_type_reject_invalid_values():
    with pytest.raises(ValidationError, match="transaction_reference"):
        PaymentSplit(
            payment_mode="upi",
            amount=Decimal("10.00"),
            transaction_reference=" ",
        )

    with pytest.raises(ValidationError, match="printer_type"):
        InvoiceReprintRequest(printer_type="00")

    assert InvoiceReprintRequest(printer_type="tvs").printer_type == "tvs"
