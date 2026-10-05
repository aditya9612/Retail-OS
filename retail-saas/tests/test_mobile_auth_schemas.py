"""
Task 4: Focused schema tests for domain-less mobile authentication.

Verifies:
A. Mobile OTP request accepts phone-only.
B. Mobile OTP request does not require domain.
C. Mobile OTP verify accepts phone + OTP.
D. Mobile OTP verify does not require domain.
E. Mobile PIN accepts phone + PIN.
F. Mobile PIN does not require domain.
G. PIN reset request accepts phone-only.
H. PIN reset request does not require domain.
I. PIN reset verify accepts phone + OTP.
J. PIN reset verify does not require domain.
K. Invalid/missing phone is still rejected.
L. Invalid OTP is still rejected.
M. Invalid PIN is still rejected.
N. Email/password schema behavior remains unchanged.
"""

import pytest
from pydantic import ValidationError

from app.schemas.auth import (
    LoginRequest,
    MobileOTPRequestSchema,
    MobileOTPVerifySchema,
    MobilePINLoginRequest,
    PINResetRequestSchema,
    PINResetVerifySchema,
    RegisterRequest,
)


class TestMobileOTPRequestSchema:

    def test_accepts_phone_only(self):
        """A. Mobile OTP request accepts phone-only payload."""
        schema = MobileOTPRequestSchema(phone="9876543210")
        assert schema.phone == "9876543210"

    def test_does_not_require_domain(self):
        """B. Mobile OTP request does not require domain field."""
        fields = MobileOTPRequestSchema.model_fields
        assert "domain" not in fields
        assert "phone" in fields

    def test_canonicalizes_phone(self):
        """Phone normalization is applied (e.g. +91 stripped)."""
        schema = MobileOTPRequestSchema(phone="+919876543210")
        assert schema.phone == "9876543210"

    def test_rejects_missing_phone(self):
        """K. Missing phone raises ValidationError."""
        with pytest.raises(ValidationError):
            MobileOTPRequestSchema()

    def test_rejects_invalid_phone(self):
        """K. Invalid phone format raises ValidationError."""
        with pytest.raises(ValidationError):
            MobileOTPRequestSchema(phone="12345")


class TestMobileOTPVerifySchema:

    def test_accepts_phone_and_otp(self):
        """C. Mobile OTP verify accepts phone + OTP."""
        schema = MobileOTPVerifySchema(phone="9876543210", otp="123456")
        assert schema.phone == "9876543210"
        assert schema.otp == "123456"

    def test_does_not_require_domain(self):
        """D. Mobile OTP verify does not require domain field."""
        fields = MobileOTPVerifySchema.model_fields
        assert "domain" not in fields
        assert "phone" in fields
        assert "otp" in fields

    def test_rejects_missing_otp(self):
        """Missing OTP raises ValidationError."""
        with pytest.raises(ValidationError):
            MobileOTPVerifySchema(phone="9876543210")

    def test_rejects_invalid_otp(self):
        """L. Non-numeric or wrong length OTP raises ValidationError."""
        with pytest.raises(ValidationError):
            MobileOTPVerifySchema(phone="9876543210", otp="abc123")
        with pytest.raises(ValidationError):
            MobileOTPVerifySchema(phone="9876543210", otp="12345")  # 5 digits
        with pytest.raises(ValidationError):
            MobileOTPVerifySchema(phone="9876543210", otp="1234567")  # 7 digits


class TestMobilePINLoginRequestSchema:

    def test_accepts_phone_and_pin(self):
        """E. Mobile PIN accepts phone + PIN."""
        schema = MobilePINLoginRequest(phone="9876543210", pin="1234")
        assert schema.phone == "9876543210"
        assert schema.pin == "1234"

    def test_does_not_require_domain(self):
        """F. Mobile PIN does not require domain field."""
        fields = MobilePINLoginRequest.model_fields
        assert "domain" not in fields
        assert "phone" in fields
        assert "pin" in fields

    def test_rejects_missing_pin(self):
        """Missing PIN raises ValidationError."""
        with pytest.raises(ValidationError):
            MobilePINLoginRequest(phone="9876543210")

    def test_rejects_invalid_pin(self):
        """M. Non-numeric or wrong length PIN raises ValidationError."""
        with pytest.raises(ValidationError):
            MobilePINLoginRequest(phone="9876543210", pin="12a4")
        with pytest.raises(ValidationError):
            MobilePINLoginRequest(phone="9876543210", pin="123")  # 3 digits
        with pytest.raises(ValidationError):
            MobilePINLoginRequest(phone="9876543210", pin="12345")  # 5 digits


class TestPINResetRequestSchema:

    def test_accepts_phone_only(self):
        """G. PIN reset request accepts phone-only payload."""
        schema = PINResetRequestSchema(phone="9876543210")
        assert schema.phone == "9876543210"

    def test_does_not_require_domain(self):
        """H. PIN reset request does not require domain field."""
        fields = PINResetRequestSchema.model_fields
        assert "domain" not in fields
        assert "phone" in fields

    def test_rejects_missing_phone(self):
        """K. Missing phone raises ValidationError."""
        with pytest.raises(ValidationError):
            PINResetRequestSchema()


class TestPINResetVerifySchema:

    def test_accepts_phone_and_otp(self):
        """I. PIN reset verify accepts phone + OTP."""
        schema = PINResetVerifySchema(phone="9876543210", otp="123456")
        assert schema.phone == "9876543210"
        assert schema.otp == "123456"

    def test_does_not_require_domain(self):
        """J. PIN reset verify does not require domain field."""
        fields = PINResetVerifySchema.model_fields
        assert "domain" not in fields
        assert "phone" in fields
        assert "otp" in fields

    def test_rejects_invalid_otp(self):
        """L. Invalid OTP raises ValidationError."""
        with pytest.raises(ValidationError):
            PINResetVerifySchema(phone="9876543210", otp="123")


class TestUnrelatedSchemasPreserved:

    def test_email_password_login_schema_unchanged(self):
        """N. Email/password schema behavior remains unchanged."""
        schema = LoginRequest(email="user@example.com", password="password123")
        assert schema.email == "user@example.com"
        assert schema.password == "password123"

    def test_register_request_still_requires_domain(self):
        """Unrelated registration schema still requires domain (tenant slug)."""
        fields = RegisterRequest.model_fields
        assert "domain" in fields
        assert fields["domain"].is_required() is True

