import pytest
from app.utils.phone import normalize_phone_number, mask_phone_number
from app.schemas.auth import RegisterRequest
from app.schemas.user import UserCreate, UserUpdate, MyProfileUpdate
from pydantic import ValidationError


class TestPhoneNormalization:
    """Unit tests for normalize_phone_number utility."""

    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("9876543210", "9876543210"),
            ("8123456789", "8123456789"),
            ("7123456789", "7123456789"),
            ("6123456789", "6123456789"),
            ("+919876543210", "9876543210"),
            ("+91 9876543210", "9876543210"),
            ("+91-98765-43210", "9876543210"),
            ("+91 (987) 654-3210", "9876543210"),
            ("+91.98765.43210", "9876543210"),
            ("919876543210", "9876543210"),
            ("09876543210", "9876543210"),
            ("  9876543210  ", "9876543210"),
            ("9876 543 210", "9876543210"),
            ("9876-543-210", "9876543210"),
        ],
    )
    def test_valid_phone_numbers(self, raw, expected):
        assert normalize_phone_number(raw) == expected

    @pytest.mark.parametrize(
        "invalid_phone",
        [
            "",
            "   ",
            None,
            "1234567890",      # Starts with 1
            "2345678901",      # Starts with 2
            "3456789012",      # Starts with 3
            "4567890123",      # Starts with 4
            "5678901234",      # Starts with 5
            "987654321",       # 9 digits
            "98765432101",     # 11 digits without valid prefix
            "+19876543210",    # US country code
            "+449876543210",   # UK country code
            "abcdefghij",      # Non-numeric
            "98765abcde",      # Mixed alphanumeric
            "+91",             # Prefix only
            "0",               # Single digit
            "+-().",           # Symbols only
        ],
    )
    def test_invalid_phone_numbers(self, invalid_phone):
        with pytest.raises(ValueError):
            normalize_phone_number(invalid_phone)


class TestPhoneSchemaIntegration:
    """Verify phone validation in Pydantic schemas."""

    def test_register_request_phone_normalization(self):
        req = RegisterRequest(
            tenant_name="Test Store",
            domain="test-store-domain",
            email="owner@test.com",
            admin_name="Owner Name",
            password="Password123!",
            phone="+91 98765 43210",
        )
        assert req.phone == "9876543210"

    def test_register_request_owner_phone_alias(self):
        req = RegisterRequest(
            store_name="Store Alias",
            domain="store-alias",
            owner_email="owner@alias.com",
            owner_name="Alias Owner",
            password="Password123!",
            owner_phone="+91-98765-43210",
        )
        assert req.phone == "9876543210"

    def test_register_request_invalid_phone(self):
        with pytest.raises(ValidationError):
            RegisterRequest(
                tenant_name="Invalid Phone Store",
                domain="invalid-phone-store",
                email="owner@test.com",
                admin_name="Owner",
                password="Password123!",
                phone="1234567890",
            )

    def test_user_create_phone_normalization(self):
        user = UserCreate(
            email="employee@test.com",
            full_name="Employee One",
            password="Password123!",
            role="staff",
            phone="+91 98765 43210",
        )
        assert user.phone == "9876543210"

    def test_user_update_phone_normalization(self):
        update = UserUpdate(phone="+91 98765 43210")
        assert update.phone == "9876543210"

    def test_user_update_invalid_phone(self):
        with pytest.raises(ValidationError):
            UserUpdate(phone="invalid-phone")

    def test_my_profile_update_phone_normalization(self):
        update = MyProfileUpdate(phone="09876543210")
        assert update.phone == "9876543210"


class TestPhoneMasking:
    """Unit tests for mask_phone_number utility ensuring PII protection."""

    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("9876543210", "******3210"),
            ("+919876543210", "*********3210"),
            ("09876543210", "*******3210"),
            ("3210", "3210"),
            ("210", "***"),
            ("", ""),
            (None, ""),
        ],
    )
    def test_mask_phone_number(self, raw, expected):
        assert mask_phone_number(raw) == expected

