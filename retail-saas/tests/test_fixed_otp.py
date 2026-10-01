import pytest
import secrets
from app.core.config import get_settings
from app.core.redis_client import get_redis
from app.services.auth_service import AuthService, OTPPurpose
from app.core.exceptions import UnauthorizedException

from app.core.database import SessionLocal

@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()

@pytest.fixture(autouse=True)
def clear_redis(fake_redis):
    fake_redis._store.clear()
    yield
    fake_redis._store.clear()

def _reset_settings_cache():
    # lru_cache reset for get_settings
    get_settings.cache_clear()

def test_fixed_otp_enabled(monkeypatch, db):
    # Enable fixed OTP via env vars
    monkeypatch.setenv("AUTH_FIXED_OTP_ENABLED", "true")
    monkeypatch.setenv("AUTH_FIXED_OTP", "123456")
    _reset_settings_cache()
    settings = get_settings()
    assert settings.AUTH_FIXED_OTP_ENABLED is True
    service = AuthService(db)
    otp = service.generate_and_store_otp(
        purpose=OTPPurpose.MOBILE_LOGIN,
        tenant_id=1,
        identifier="9876543210",
    )
    assert otp == "123456"
    # Verify that the OTP can be successfully validated
    assert service.verify_otp_code(
        purpose=OTPPurpose.MOBILE_LOGIN,
        tenant_id=1,
        identifier="9876543210",
        otp_code="123456",
    ) is True

def test_fixed_otp_disabled(monkeypatch, db):
    # Disable fixed OTP and mock secrets.randbelow to a deterministic value
    monkeypatch.setenv("AUTH_FIXED_OTP_ENABLED", "false")
    _reset_settings_cache()
    settings = get_settings()
    assert settings.AUTH_FIXED_OTP_ENABLED is False
    # Patch randbelow to return a known number
    monkeypatch.setattr(secrets, "randbelow", lambda _: 42)
    service = AuthService(db)
    otp = service.generate_and_store_otp(
        purpose=OTPPurpose.MOBILE_LOGIN,
        tenant_id=1,
        identifier="9876543210",
    )
    # Expected formatted as six digits
    assert otp == "000042"
    # Verify that the OTP can be validated
    assert service.verify_otp_code(
        purpose=OTPPurpose.MOBILE_LOGIN,
        tenant_id=1,
        identifier="9876543210",
        otp_code="000042",
    ) is True

def test_fixed_otp_attempt_limit(monkeypatch, db):
    monkeypatch.setenv("AUTH_FIXED_OTP_ENABLED", "true")
    monkeypatch.setenv("AUTH_FIXED_OTP", "123456")
    _reset_settings_cache()
    service = AuthService(db)
    service.generate_and_store_otp(
        purpose=OTPPurpose.PIN_RESET,
        tenant_id=2,
        identifier="9123456789",
    )
    # Five wrong attempts should exhaust the limit
    for i in range(5):
        with pytest.raises(UnauthorizedException) as exc:
            service.verify_otp_code(
                purpose=OTPPurpose.PIN_RESET,
                tenant_id=2,
                identifier="9123456789",
                otp_code="000000",
            )
        if i < 4:
            assert "Invalid OTP" in str(exc.value)
        else:
            assert "Too many invalid OTP attempts" in str(exc.value)

def test_fixed_otp_expiry(monkeypatch, db):
    monkeypatch.setenv("AUTH_FIXED_OTP_ENABLED", "true")
    monkeypatch.setenv("AUTH_FIXED_OTP", "123456")
    _reset_settings_cache()
    redis = get_redis()
    service = AuthService(db)
    service.generate_and_store_otp(
        purpose=OTPPurpose.PASSWORD_RESET,
        tenant_id=3,
        identifier="9988776655",
    )
    # Simulate expiry by deleting the OTP key
    otp_key = service._otp_key(OTPPurpose.PASSWORD_RESET, 3, "9988776655")
    service.redis.delete(otp_key)
    with pytest.raises(UnauthorizedException) as exc:
        service.verify_otp_code(
            purpose=OTPPurpose.PASSWORD_RESET,
            tenant_id=3,
            identifier="9988776655",
            otp_code="123456",
        )
    assert "OTP is invalid or expired" in str(exc.value)

def test_fixed_otp_purpose_and_tenant_scoping(monkeypatch, db):
    monkeypatch.setenv("AUTH_FIXED_OTP_ENABLED", "true")
    monkeypatch.setenv("AUTH_FIXED_OTP", "123456")
    _reset_settings_cache()
    service = AuthService(db)
    # Generate OTP for purpose PIN_RESET, tenant 10
    service.generate_and_store_otp(
        purpose=OTPPurpose.PIN_RESET,
        tenant_id=10,
        identifier="9090909090",
    )
    # Verify with wrong purpose should fail
    with pytest.raises(UnauthorizedException) as exc:
        service.verify_otp_code(
            purpose=OTPPurpose.PASSWORD_RESET,
            tenant_id=10,
            identifier="9090909090",
            otp_code="123456",
        )
    assert "OTP is invalid or expired" in str(exc.value)
    # Verify with wrong tenant should fail
    with pytest.raises(UnauthorizedException) as exc:
        service.verify_otp_code(
            purpose=OTPPurpose.PIN_RESET,
            tenant_id=11,
            identifier="9090909090",
            otp_code="123456",
        )
    assert "OTP is invalid or expired" in str(exc.value)
