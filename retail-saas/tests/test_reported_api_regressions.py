from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.billing import (
    InvoiceReprintRequest,
    PaymentSplit,
    ReturnItemRequest,
)
from app.schemas.customer import CustomerNoteCreate
from app.schemas.gst_rate import GstRateCreate, GstRateUpdate
from app.schemas.user import UserUpdate
from app.utils.validators import validate_aadhaar_number


def test_gst_rate_rejects_all_zero_hsn_code():
    with pytest.raises(ValidationError, match="HSN code cannot consist only of zeroes"):
        GstRateCreate(hsn_code="0000", gst_rate=Decimal("18"))

    with pytest.raises(ValidationError, match="HSN code cannot consist only of zeroes"):
        GstRateUpdate(hsn_code="0000")


def test_customer_notes_reject_numeric_only_but_allow_normal_text():
    for note in ("123456789", "12.34", "." * 20, "x" * 5001):
        with pytest.raises(ValidationError):
            CustomerNoteCreate(note=note)

    assert CustomerNoteCreate(note="Follow up with the customer tomorrow.").note == (
        "Follow up with the customer tomorrow."
    )


def test_user_update_validates_profile_photo_values():
    for value in ("00", "photo.txt", "javascript:alert(1)", "//example.com/photo.jpg"):
        with pytest.raises(ValidationError):
            UserUpdate(profile_photo=value)

    assert UserUpdate(profile_photo="/uploads/users/photo_123.jpg").profile_photo == (
        "/uploads/users/photo_123.jpg"
    )
    assert UserUpdate(profile_photo="https://example.com/photo.webp").profile_photo == (
        "https://example.com/photo.webp"
    )

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
