import hashlib
import pytest
from app.core.exceptions import UnauthorizedException
from app.services.auth_service import AuthService, OTPPurpose, canonicalize_otp_identifier
from app.core.database import SessionLocal


@pytest.fixture
def auth_svc():
    db = SessionLocal()
    try:
        svc = AuthService(db)
        yield svc
    finally:
        db.close()


class TestOTPCore:
    """Comprehensive test suite for Phase 2-D1 Unified OTP Core."""

    def test_generate_valid_6_digit_otp(self, auth_svc):
        otp = auth_svc.generate_and_store_otp(
            purpose=OTPPurpose.MOBILE_LOGIN,
            tenant_id=1,
            identifier="9876543210",
            enforce_cooldown=False,
        )
        assert len(otp) == 6
        assert otp.isdigit()

    def test_leading_zero_otp_supported(self, auth_svc, monkeypatch):
        # Force randbelow to return 123 -> "000123"
        monkeypatch.setattr("app.services.auth_service.secrets.randbelow", lambda _: 123)
        otp = auth_svc.generate_and_store_otp(
            purpose=OTPPurpose.MOBILE_LOGIN,
            tenant_id=1,
            identifier="9876543210",
            enforce_cooldown=False,
        )
        assert otp == "000123"
        assert len(otp) == 6
        assert auth_svc.verify_otp_code(
            purpose=OTPPurpose.MOBILE_LOGIN,
            tenant_id=1,
            identifier="9876543210",
            otp_code="000123",
        ) is True

    def test_otp_stored_hashed_never_plaintext(self, auth_svc, monkeypatch):
        monkeypatch.setattr("app.services.auth_service.secrets.randbelow", lambda _: 654321)
        otp = auth_svc.generate_and_store_otp(
            purpose=OTPPurpose.PASSWORD_RESET,
            tenant_id=1,
            identifier="9876543210",
            enforce_cooldown=False,
        )
        assert otp == "654321"

        otp_key = auth_svc._otp_key(OTPPurpose.PASSWORD_RESET, 1, "9876543210")
        stored_val = auth_svc.redis.get(otp_key)

        # Stored value must be the SHA-256 hash, NEVER plaintext "654321"
        assert stored_val != "654321"
        assert stored_val == hashlib.sha256(b"654321").hexdigest()

    def test_correct_otp_verification_succeeds(self, auth_svc, monkeypatch):
        monkeypatch.setattr("app.services.auth_service.secrets.randbelow", lambda _: 778899)
        otp = auth_svc.generate_and_store_otp(
            purpose=OTPPurpose.PIN_SETUP,
            tenant_id=2,
            identifier="8123456789",
            enforce_cooldown=False,
        )
        result = auth_svc.verify_otp_code(
            purpose=OTPPurpose.PIN_SETUP,
            tenant_id=2,
            identifier="8123456789",
            otp_code=otp,
        )
        assert result is True

    def test_wrong_otp_fails(self, auth_svc, monkeypatch):
        monkeypatch.setattr("app.services.auth_service.secrets.randbelow", lambda _: 112233)
        auth_svc.generate_and_store_otp(
            purpose=OTPPurpose.PIN_RESET,
            tenant_id=1,
            identifier="9876543210",
            enforce_cooldown=False,
        )
        with pytest.raises(UnauthorizedException, match="Invalid OTP"):
            auth_svc.verify_otp_code(
                purpose=OTPPurpose.PIN_RESET,
                tenant_id=1,
                identifier="9876543210",
                otp_code="999999",
            )

    def test_five_wrong_attempts_invalidate_otp(self, auth_svc, monkeypatch):
        monkeypatch.setattr("app.services.auth_service.secrets.randbelow", lambda _: 445566)
        auth_svc.generate_and_store_otp(
            purpose=OTPPurpose.MOBILE_LOGIN,
            tenant_id=1,
            identifier="9876543210",
            enforce_cooldown=False,
        )

        # 4 wrong attempts raise "Invalid OTP"
        for _ in range(4):
            with pytest.raises(UnauthorizedException, match="Invalid OTP"):
                auth_svc.verify_otp_code(
                    purpose=OTPPurpose.MOBILE_LOGIN,
                    tenant_id=1,
                    identifier="9876543210",
                    otp_code="000000",
                )

        # 5th wrong attempt invalidates the OTP and raises "Too many invalid OTP attempts"
        with pytest.raises(UnauthorizedException, match="Too many invalid OTP attempts"):
            auth_svc.verify_otp_code(
                purpose=OTPPurpose.MOBILE_LOGIN,
                tenant_id=1,
                identifier="9876543210",
                otp_code="000000",
            )

        # Now even if the user enters the CORRECT OTP, it must fail because it was invalidated
        with pytest.raises(UnauthorizedException, match="Too many invalid OTP attempts"):
            auth_svc.verify_otp_code(
                purpose=OTPPurpose.MOBILE_LOGIN,
                tenant_id=1,
                identifier="9876543210",
                otp_code="445566",
            )

    def test_expired_or_nonexistent_otp_fails(self, auth_svc):
        with pytest.raises(UnauthorizedException, match="OTP is invalid or expired"):
            auth_svc.verify_otp_code(
                purpose=OTPPurpose.MOBILE_LOGIN,
                tenant_id=1,
                identifier="9876543210",
                otp_code="123456",
            )

    def test_successful_verification_deletes_otp_and_prevents_replay(self, auth_svc, monkeypatch):
        monkeypatch.setattr("app.services.auth_service.secrets.randbelow", lambda _: 334455)
        otp = auth_svc.generate_and_store_otp(
            purpose=OTPPurpose.MOBILE_VERIFICATION,
            tenant_id=1,
            identifier="9876543210",
            enforce_cooldown=False,
        )

        # First verification succeeds
        assert auth_svc.verify_otp_code(
            purpose=OTPPurpose.MOBILE_VERIFICATION,
            tenant_id=1,
            identifier="9876543210",
            otp_code=otp,
        ) is True

        # Replay must fail immediately because key was deleted
        with pytest.raises(UnauthorizedException, match="OTP is invalid or expired"):
            auth_svc.verify_otp_code(
                purpose=OTPPurpose.MOBILE_VERIFICATION,
                tenant_id=1,
                identifier="9876543210",
                otp_code=otp,
            )

    def test_new_otp_invalidates_previous_otp(self, auth_svc, monkeypatch):
        # Generate OTP 1: 111111
        monkeypatch.setattr("app.services.auth_service.secrets.randbelow", lambda _: 111111)
        otp1 = auth_svc.generate_and_store_otp(
            purpose=OTPPurpose.PASSWORD_RESET,
            tenant_id=1,
            identifier="user@example.com",
            enforce_cooldown=False,
        )

        # Generate OTP 2: 222222
        monkeypatch.setattr("app.services.auth_service.secrets.randbelow", lambda _: 222222)
        otp2 = auth_svc.generate_and_store_otp(
            purpose=OTPPurpose.PASSWORD_RESET,
            tenant_id=1,
            identifier="user@example.com",
            enforce_cooldown=False,
        )

        # Old OTP must fail
        with pytest.raises(UnauthorizedException, match="Invalid OTP"):
            auth_svc.verify_otp_code(
                purpose=OTPPurpose.PASSWORD_RESET,
                tenant_id=1,
                identifier="user@example.com",
                otp_code=otp1,
            )

        # New OTP succeeds
        assert auth_svc.verify_otp_code(
            purpose=OTPPurpose.PASSWORD_RESET,
            tenant_id=1,
            identifier="user@example.com",
            otp_code=otp2,
        ) is True

    def test_purpose_separation(self, auth_svc, monkeypatch):
        """Verify an OTP for one purpose cannot be verified for another purpose."""
        monkeypatch.setattr("app.services.auth_service.secrets.randbelow", lambda _: 556677)
        otp = auth_svc.generate_and_store_otp(
            purpose=OTPPurpose.MOBILE_LOGIN,
            tenant_id=1,
            identifier="9876543210",
            enforce_cooldown=False,
        )

        # Cannot verify as PASSWORD_RESET
        with pytest.raises(UnauthorizedException, match="OTP is invalid or expired"):
            auth_svc.verify_otp_code(
                purpose=OTPPurpose.PASSWORD_RESET,
                tenant_id=1,
                identifier="9876543210",
                otp_code=otp,
            )

        # Cannot verify as PIN_RESET
        with pytest.raises(UnauthorizedException, match="OTP is invalid or expired"):
            auth_svc.verify_otp_code(
                purpose=OTPPurpose.PIN_RESET,
                tenant_id=1,
                identifier="9876543210",
                otp_code=otp,
            )

        # Successfully verifies under original purpose MOBILE_LOGIN
        assert auth_svc.verify_otp_code(
            purpose=OTPPurpose.MOBILE_LOGIN,
            tenant_id=1,
            identifier="9876543210",
            otp_code=otp,
        ) is True

    def test_tenant_separation(self, auth_svc, monkeypatch):
        """Verify OTP generated for Tenant 1 cannot be verified for Tenant 2."""
        monkeypatch.setattr("app.services.auth_service.secrets.randbelow", lambda _: 998877)
        otp = auth_svc.generate_and_store_otp(
            purpose=OTPPurpose.MOBILE_LOGIN,
            tenant_id=1,
            identifier="9876543210",
            enforce_cooldown=False,
        )

        # Verification on Tenant 2 must fail
        with pytest.raises(UnauthorizedException, match="OTP is invalid or expired"):
            auth_svc.verify_otp_code(
                purpose=OTPPurpose.MOBILE_LOGIN,
                tenant_id=2,
                identifier="9876543210",
                otp_code=otp,
            )

        # Verification on Tenant 1 succeeds
        assert auth_svc.verify_otp_code(
            purpose=OTPPurpose.MOBILE_LOGIN,
            tenant_id=1,
            identifier="9876543210",
            otp_code=otp,
        ) is True

    def test_phone_canonicalization_in_redis_key(self, auth_svc, monkeypatch):
        """Verify non-canonical phone formats map to the same canonical Redis key."""
        monkeypatch.setattr("app.services.auth_service.secrets.randbelow", lambda _: 123123)
        otp = auth_svc.generate_and_store_otp(
            purpose=OTPPurpose.MOBILE_LOGIN,
            tenant_id=1,
            identifier="+91 (987) 654-3210",
            enforce_cooldown=False,
        )

        # Key should use canonical 10-digit number
        expected_key = "auth:otp:mobile_login:1:9876543210"
        assert auth_svc.redis.exists(expected_key)

        # Verification using clean 10-digit format succeeds
        assert auth_svc.verify_otp_code(
            purpose=OTPPurpose.MOBILE_LOGIN,
            tenant_id=1,
            identifier="9876543210",
            otp_code=otp,
        ) is True

    def test_request_rate_limiting_after_3_requests(self, auth_svc):
        phone = "9876543210"
        # 1st request -> OK
        auth_svc.generate_and_store_otp(OTPPurpose.MOBILE_LOGIN, 1, phone, enforce_cooldown=False)
        # 2nd request -> OK
        auth_svc.generate_and_store_otp(OTPPurpose.MOBILE_LOGIN, 1, phone, enforce_cooldown=False)
        # 3rd request -> OK
        auth_svc.generate_and_store_otp(OTPPurpose.MOBILE_LOGIN, 1, phone, enforce_cooldown=False)

        # 4th request -> Rate limited
        with pytest.raises(UnauthorizedException, match="Too many OTP requests"):
            auth_svc.generate_and_store_otp(OTPPurpose.MOBILE_LOGIN, 1, phone, enforce_cooldown=False)

    def test_resend_cooldown_60_seconds(self, auth_svc):
        phone = "9812345678"
        # 1st request with cooldown enabled
        auth_svc.generate_and_store_otp(OTPPurpose.MOBILE_LOGIN, 1, phone, enforce_cooldown=True)

        # Immediate 2nd request must fail due to cooldown
        with pytest.raises(UnauthorizedException, match="Please wait 60 seconds"):
            auth_svc.generate_and_store_otp(OTPPurpose.MOBILE_LOGIN, 1, phone, enforce_cooldown=True)

    def test_invalid_otp_format_rejected(self, auth_svc):
        for bad_code in ["", "12345", "1234567", "abcdef", "12345a", "   "]:
            with pytest.raises(UnauthorizedException, match="OTP must contain 6 digits"):
                auth_svc.verify_otp_code(
                    purpose=OTPPurpose.MOBILE_LOGIN,
                    tenant_id=1,
                    identifier="9876543210",
                    otp_code=bad_code,
                )

