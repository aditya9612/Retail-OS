from enum import Enum
import hashlib
import json
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import (
    AppException,
    ConflictException,
    NotFoundException,
    UnauthorizedException,
)
from app.core.redis_client import get_redis
from app.core.security import (
    blacklist_token,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_password_hash,
    is_token_blacklisted,
    verify_password,
)
from app.models.password_reset_token import PasswordResetToken
from app.models.role import Role
from app.models.store import Store
from app.models.tenant import Tenant
from app.models.user import User
from app.repositories.user_repo import UserRepository
from app.services.saas_subscription_service import SaaSSubscriptionService
from app.schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    MobileOTPRequestSchema,
    MobileOTPVerifySchema,
    MobilePINLoginRequest,
    PINChangeRequest,
    PINResetRequestSchema,
    PINResetVerifySchema,
    PINSetupRequest,
    ResetPasswordRequest,
    ResetPINRequest,
    TokenResponse,
    VerifyOTPRequest,
    normalize_email,
    validate_password_value,
)
from app.utils.constants import (
    DEFAULT_ROLE_PERMISSIONS,
    UserRole,
)
from app.utils.phone import normalize_phone_number


class OTPPurpose(str, Enum):
    PASSWORD_RESET = "password_reset"
    MOBILE_LOGIN = "mobile_login"
    MOBILE_VERIFICATION = "mobile_verification"
    PIN_SETUP = "pin_setup"
    PIN_RESET = "pin_reset"


_SLUG_PATTERN = re.compile(
    r"^[a-z0-9](?:[a-z0-9-]{1,98}[a-z0-9])?$"
)

_PHONE_PATTERN = re.compile(
    r"^\d{10,15}$"
)

OTP_TTL_SECONDS = 300
OTP_ATTEMPTS_TTL_SECONDS = 600
OTP_MAX_ATTEMPTS = 5
OTP_COOLDOWN_SECONDS = 60

LOGIN_RATE_LIMIT = 5
LOGIN_RATE_WINDOW_SECONDS = 900

OTP_RATE_LIMIT = 3
OTP_RATE_WINDOW_SECONDS = 900

PIN_MAX_FAILED_ATTEMPTS = 5
PIN_LOCK_DURATION_SECONDS = 900
PIN_ATTEMPTS_WINDOW_SECONDS = 900

ACTIVITY_TTL_SECONDS = 30 * 24 * 60 * 60


def canonicalize_otp_identifier(identifier: str) -> str:
    cleaned = str(identifier).strip()
    if "@" in cleaned:
        return cleaned.lower()
    try:
        return normalize_phone_number(cleaned)
    except ValueError:
        return cleaned.lower()


def _validate_password(password: str) -> str:
    return validate_password_value(password)


class AuthService:

    def __init__(self, db: Session):
        self.db = db
        self.user_repo = UserRepository(db)
        self.redis = get_redis()

    def _rate_limit(
        self,
        key: str,
        maximum: int,
        window_seconds: int,
        message: str,
    ) -> None:
        try:
            current = self.redis.get(key)

            if current is None:
                self.redis.setex(
                    key,
                    window_seconds,
                    "1",
                )
                return

            count = int(current)

            if count >= maximum:
                raise UnauthorizedException(
                    message
                )

            self.redis.incr(key)

        except UnauthorizedException:
            raise

        except Exception:
            return

    def _record_activity(
        self,
        user_id: int,
        event: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        key = (
            f"auth:activity:user:{user_id}"
        )

        activity = {
            "event": event,
            "user_id": user_id,
            "ip_address": ip_address,
            "user_agent": user_agent,
            "timestamp": datetime.now(
                timezone.utc
            ).isoformat(),
        }

        try:
            self.redis.lpush(
                key,
                json.dumps(activity),
            )

            self.redis.ltrim(
                key,
                0,
                99,
            )

            self.redis.expire(
                key,
                ACTIVITY_TTL_SECONDS,
            )

        except Exception:
            return

    def login(
        self,
        data: LoginRequest,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> TokenResponse:

        email = normalize_email(data.email)

        rate_key = (
            f"auth:login:rate:{email}"
        )

        self._rate_limit(
            rate_key,
            LOGIN_RATE_LIMIT,
            LOGIN_RATE_WINDOW_SECONDS,
            "Too many login attempts. Please try again later.",
        )

        user = self.user_repo.get_by_email(
            email
        )

        if not user:
            raise UnauthorizedException(
                "Invalid email or password"
            )

        try:
            password_valid = verify_password(
                data.password,
                user.hashed_password,
            )
        except Exception:
            password_valid = False

        if not password_valid:
            raise UnauthorizedException(
                "Invalid email or password"
            )

        if not user.is_active:
            raise UnauthorizedException(
                "Account is disabled"
            )

        if user.tenant_id is None:
            raise UnauthorizedException(
                "Invalid tenant user account"
            )

        tenant = (
            self.db.query(Tenant)
            .filter(
                Tenant.id == user.tenant_id
            )
            .first()
        )

        if not tenant:
            raise UnauthorizedException(
                "Tenant not found"
            )

        if not tenant.is_active:
            raise UnauthorizedException(
                "Tenant account is disabled"
            )

        token_data = {
            "sub": str(user.id),
            "tenant_id": user.tenant_id,
            "role": (
                user.role.name
                if user.role
                else ""
            ),
            "store_id": user.store_id,
        }

        tokens = TokenResponse(
            access_token=create_access_token(
                token_data
            ),
            refresh_token=create_refresh_token(
                token_data
            ),
        )

        try:
            self.redis.delete(rate_key)
        except Exception:
            pass

        self._record_activity(
            user.id,
            "login",
            ip_address,
            user_agent,
        )

        return tokens

    def refresh(
        self,
        refresh_token: str,
    ) -> TokenResponse:

        refresh_token = refresh_token.strip()

        if not refresh_token:
            raise UnauthorizedException(
                "Refresh token is required"
            )

        if is_token_blacklisted(
            refresh_token
        ):
            raise UnauthorizedException(
                "Refresh token has been revoked"
            )

        payload = decode_token(
            refresh_token
        )

        if payload.get("type") != "refresh":
            raise UnauthorizedException(
                "Invalid refresh token"
            )

        user_id = payload.get("sub")
        tenant_id = payload.get("tenant_id")

        if not user_id or tenant_id is None:
            raise UnauthorizedException(
                "Invalid refresh token"
            )

        try:
            user_id = int(user_id)
            tenant_id = int(tenant_id)
        except (TypeError, ValueError) as exc:
            raise UnauthorizedException(
                "Invalid refresh token"
            ) from exc

        user = self.user_repo.get_by_id(
            user_id,
            tenant_id,
        )

        if not user:
            raise UnauthorizedException(
                "User not found"
            )

        if not user.is_active:
            raise UnauthorizedException(
                "Account is disabled"
            )

        tenant = (
            self.db.query(Tenant)
            .filter(
                Tenant.id == tenant_id
            )
            .first()
        )

        if not tenant:
            raise UnauthorizedException(
                "Tenant not found"
            )

        if not tenant.is_active:
            raise UnauthorizedException(
                "Tenant account is disabled"
            )

        token_data = {
            "sub": str(user.id),
            "tenant_id": user.tenant_id,
            "role": (
                user.role.name
                if user.role
                else ""
            ),
            "store_id": user.store_id,
        }

        new_tokens = TokenResponse(
            access_token=create_access_token(
                token_data
            ),
            refresh_token=create_refresh_token(
                token_data
            ),
        )

        try:
            blacklist_token(
                refresh_token,
            )
        except Exception:
            pass

        return new_tokens

    def logout(
        self,
        token: str | None,
    ) -> dict:

        if not token:
            return {
                "success": True,
                "message": "Logout successful",
            }

        try:
            payload = decode_token(token)

            if is_token_blacklisted(token):
                return {
                    "success": True,
                    "message": "Logout successful",
                }

            blacklist_token(
                token,
            )

            user_id = payload.get("sub")

            if user_id:
                try:
                    user_id = int(user_id)
                    self._record_activity(
                        user_id,
                        "logout",
                    )
                except (TypeError, ValueError):
                    pass

        except Exception:
            pass

        return {
            "success": True,
            "message": "Logout successful",
        }

    def register_tenant(
        self,
        data_or_name: Any,
        domain: str | None = None,
        email: str | None = None,
        admin_name: str | None = None,
        password: str | None = None,
        phone: str | None = None,
    ) -> User:
        plan_id = None
        plan_code = None
        if hasattr(data_or_name, "tenant_name"):
            tenant_name = data_or_name.tenant_name
            domain_val = getattr(data_or_name, "domain", None) or getattr(data_or_name, "slug", None)
            email = data_or_name.email
            admin_name = data_or_name.admin_name
            password = data_or_name.password
            phone = data_or_name.phone
            plan_id = getattr(data_or_name, "plan_id", None)
            plan_code = getattr(data_or_name, "plan_code", None)
        elif isinstance(data_or_name, dict):
            tenant_name = data_or_name.get("tenant_name", "")
            domain_val = data_or_name.get("domain") or data_or_name.get("slug", "")
            email = data_or_name.get("email", "")
            admin_name = data_or_name.get("admin_name", "")
            password = data_or_name.get("password", "")
            phone = data_or_name.get("phone")
            plan_id = data_or_name.get("plan_id")
            plan_code = data_or_name.get("plan_code")
        else:
            tenant_name = data_or_name
            domain_val = domain

        tenant_name = (tenant_name or "").strip()
        domain_val = (domain_val or "").strip().lower()
        email = normalize_email(email or "")
        admin_name = (admin_name or "").strip()

        if len(tenant_name) < 2:
            raise AppException(
                "Tenant name must be at least 2 characters"
            )

        if len(tenant_name) > 255:
            raise AppException(
                "Tenant name must not exceed 255 characters"
            )

        if not domain_val or not re.match(r"^[a-z0-9-]+$", domain_val):
            raise AppException(
                "Domain must contain lowercase alphanumeric characters and hyphens"
            )

        if not admin_name:
            raise AppException(
                "Admin name is required"
            )

        if len(admin_name) > 255:
            raise AppException(
                "Admin name must not exceed 255 characters"
            )

        if phone is not None:
            phone = phone.strip()

            if not phone:
                phone = None
            else:
                try:
                    phone = normalize_phone_number(phone)
                except ValueError as err:
                    raise AppException(str(err)) from err

                existing_phone_user = self.user_repo.get_active_user_by_phone(phone)
                if existing_phone_user:
                    raise ConflictException("Phone number is already registered")

        _validate_password(password)

        existing_tenant = (
            self.db.query(Tenant)
            .filter(
                Tenant.domain == domain_val
            )
            .first()
        )

        if existing_tenant:
            raise ConflictException(
                "Tenant domain already exists"
            )

        existing_user = (
            self.db.query(User)
            .filter(
                User.email == email
            )
            .first()
        )

        if existing_user:
            raise ConflictException(
                "Email address is already registered"
            )

        try:
            tenant = Tenant(
                name=tenant_name,
                domain=domain_val,
                is_active=True,
            )

            self.db.add(tenant)
            self.db.flush()

            for role_name in UserRole:
                if role_name == UserRole.SUPERADMIN:
                    continue

                role = Role(
                    tenant_id=tenant.id,
                    name=role_name.value,
                    permissions=DEFAULT_ROLE_PERMISSIONS[
                        role_name
                    ],
                    is_system=False,
                )

                self.db.add(role)

            self.db.flush()

            admin_role = (
                self.db.query(Role)
                .filter(
                    Role.tenant_id == tenant.id,
                    Role.name == UserRole.ADMIN.value,
                )
                .first()
            )

            if not admin_role:
                self.db.rollback()

                raise AppException(
                    "Admin role could not be created"
                )

            user = User(
                tenant_id=tenant.id,
                role_id=admin_role.id,
                email=email,
                password_hash=get_password_hash(
                    password
                ),
                full_name=admin_name,
                phone=phone,
                is_active=True,
            )

            self.db.add(user)
            self.db.flush()

            # Create initial SaaSSubscription and synchronize legacy tenant projection
            SaaSSubscriptionService(self.db).create_initial_subscription(
                tenant_id=tenant.id,
                plan_id=plan_id,
                plan_code=plan_code,
            )

            self.db.commit()
            self.db.refresh(user)

            return user

        except ConflictException:
            self.db.rollback()
            raise

        except IntegrityError as exc:
            self.db.rollback()
            if "uq_users_active_phone" in str(exc) or "active_phone" in str(exc).lower():
                raise ConflictException("Phone number is already registered") from exc
            raise ConflictException(
                "Tenant or user information already exists"
            ) from exc

        except Exception:
            self.db.rollback()
            raise

    def _canonicalize_identifier(self, identifier: str) -> str:
        return canonicalize_otp_identifier(identifier)

    def _otp_key(self, purpose: OTPPurpose | str, tenant_id: Any, identifier: str) -> str:
        p_val = purpose.value if isinstance(purpose, Enum) else str(purpose).lower()
        t_val = str(tenant_id) if tenant_id is not None else "0"
        canon_id = self._canonicalize_identifier(identifier)
        return f"auth:otp:{p_val}:{t_val}:{canon_id}"

    def _otp_attempts_key(self, purpose: OTPPurpose | str, tenant_id: Any, identifier: str) -> str:
        p_val = purpose.value if isinstance(purpose, Enum) else str(purpose).lower()
        t_val = str(tenant_id) if tenant_id is not None else "0"
        canon_id = self._canonicalize_identifier(identifier)
        return f"auth:otp:attempts:{p_val}:{t_val}:{canon_id}"

    def _otp_cooldown_key(self, purpose: OTPPurpose | str, tenant_id: Any, identifier: str) -> str:
        p_val = purpose.value if isinstance(purpose, Enum) else str(purpose).lower()
        t_val = str(tenant_id) if tenant_id is not None else "0"
        canon_id = self._canonicalize_identifier(identifier)
        return f"auth:otp:cooldown:{p_val}:{t_val}:{canon_id}"

    def _otp_rate_key(self, purpose: OTPPurpose | str, tenant_id: Any, identifier: str) -> str:
        p_val = purpose.value if isinstance(purpose, Enum) else str(purpose).lower()
        t_val = str(tenant_id) if tenant_id is not None else "0"
        canon_id = self._canonicalize_identifier(identifier)
        return f"auth:otp:rate:{p_val}:{t_val}:{canon_id}"

    def generate_and_store_otp(
        self,
        purpose: OTPPurpose | str,
        tenant_id: Any,
        identifier: str,
        enforce_cooldown: bool = True,
    ) -> str:
        canon_id = self._canonicalize_identifier(identifier)
        cooldown_key = self._otp_cooldown_key(purpose, tenant_id, canon_id)
        rate_key = self._otp_rate_key(purpose, tenant_id, canon_id)

        # 1. Enforce 60-second cooldown
        if enforce_cooldown:
            try:
                if self.redis.get(cooldown_key):
                    raise UnauthorizedException(
                        "Please wait 60 seconds before requesting another OTP."
                    )
            except UnauthorizedException:
                raise
            except Exception:
                pass

        # 2. Enforce request rate limit (max 3 requests per 15 minutes)
        try:
            current_rate = self.redis.get(rate_key)
            if current_rate is not None:
                count = int(current_rate)
                if count >= OTP_RATE_LIMIT:
                    raise UnauthorizedException(
                        "Too many OTP requests. Please try again later."
                    )
                try:
                    self.redis.incr(rate_key)
                except Exception:
                    self.redis.setex(rate_key, OTP_RATE_WINDOW_SECONDS, str(count + 1))
            else:
                self.redis.setex(rate_key, OTP_RATE_WINDOW_SECONDS, "1")
        except UnauthorizedException:
            raise
        except Exception:
            pass

        # 3. Generate OTP (fixed for development when enabled)
        from app.core.config import get_settings
        _settings = get_settings()
        if getattr(_settings, "AUTH_FIXED_OTP_ENABLED", False):
            otp = str(_settings.AUTH_FIXED_OTP)
        else:
            otp = f"{secrets.randbelow(1_000_000):06d}"
        otp_hash = hashlib.sha256(otp.encode("utf-8")).hexdigest()

        otp_key = self._otp_key(purpose, tenant_id, canon_id)
        attempts_key = self._otp_attempts_key(purpose, tenant_id, canon_id)

        try:
            # Overwrites/invalidates previous OTP for same purpose+tenant+identifier
            self.redis.setex(otp_key, OTP_TTL_SECONDS, otp_hash)
            self.redis.setex(attempts_key, OTP_ATTEMPTS_TTL_SECONDS, "0")
            if enforce_cooldown:
                self.redis.setex(cooldown_key, OTP_COOLDOWN_SECONDS, "1")
        except Exception as exc:
            raise AppException("OTP service is temporarily unavailable") from exc

        # 4. Send OTP via configured SMS provider
        from app.services.sms_provider import get_sms_provider
        sms_provider = get_sms_provider()
        try:
            # phone number must be canonicalized identifier (already normalized)
            sms_provider.send_otp(canon_id, otp, purpose.value if isinstance(purpose, OTPPurpose) else str(purpose))
        except Exception as exc:
            # Cleanup stored OTP to avoid blocking future attempts
            try:
                self.redis.delete(otp_key)
                self.redis.delete(attempts_key)
                if enforce_cooldown:
                    self.redis.delete(cooldown_key)
            except Exception:
                pass
            raise AppException("Failed to send OTP via SMS provider") from exc

        return otp

    def verify_otp_code(
        self,
        purpose: OTPPurpose | str,
        tenant_id: Any,
        identifier: str,
        otp_code: str,
    ) -> bool:
        canon_id = self._canonicalize_identifier(identifier)
        code = str(otp_code).strip()

        if not code or len(code) != 6 or not code.isdigit():
            raise UnauthorizedException("OTP must contain 6 digits")

        otp_key = self._otp_key(purpose, tenant_id, canon_id)
        attempts_key = self._otp_attempts_key(purpose, tenant_id, canon_id)

        try:
            attempts_val = self.redis.get(attempts_key)
            attempts = int(attempts_val or "0")

            if attempts >= OTP_MAX_ATTEMPTS:
                try:
                    self.redis.delete(otp_key)
                except Exception:
                    pass
                raise UnauthorizedException(
                    "Too many invalid OTP attempts. Please request a new OTP."
                )

            stored_hash = self.redis.get(otp_key)
            if not stored_hash:
                raise UnauthorizedException("OTP is invalid or expired")

            supplied_hash = hashlib.sha256(code.encode("utf-8")).hexdigest()

            if not secrets.compare_digest(stored_hash, supplied_hash):
                attempts += 1
                try:
                    self.redis.setex(attempts_key, OTP_ATTEMPTS_TTL_SECONDS, str(attempts))
                except Exception:
                    pass

                if attempts >= OTP_MAX_ATTEMPTS:
                    try:
                        self.redis.delete(otp_key)
                    except Exception:
                        pass
                    raise UnauthorizedException(
                        "Too many invalid OTP attempts. Please request a new OTP."
                    )

                raise UnauthorizedException("Invalid OTP")

            # Single use: delete OTP immediately
            try:
                self.redis.delete(otp_key)
                self.redis.delete(attempts_key)
            except Exception:
                pass

            return True

        except UnauthorizedException:
            raise
        except Exception as exc:
            raise AppException("OTP verification service is temporarily unavailable") from exc

    def forgot_password(
        self,
        data: ForgotPasswordRequest,
    ) -> str:
        email = normalize_email(
            data.email
        )

        user = self.user_repo.get_by_email(
            email
        )

        if not user:
            raise NotFoundException(
                "Email address is not registered"
            )

        if not user.is_active:
            raise UnauthorizedException(
                "Account is disabled"
            )

        if user.tenant_id is not None:
            tenant = (
                self.db.query(Tenant)
                .filter(Tenant.id == user.tenant_id)
                .first()
            )
            if not tenant or not tenant.is_active:
                raise UnauthorizedException(
                    "Tenant account is disabled"
                )

        otp = self.generate_and_store_otp(
            purpose=OTPPurpose.PASSWORD_RESET,
            tenant_id=user.tenant_id,
            identifier=email,
        )

        return otp

    def verify_otp(
        self,
        data: VerifyOTPRequest,
    ) -> str:
        email = normalize_email(
            data.email
        )

        user = self.user_repo.get_by_email(
            email
        )

        if not user:
            raise NotFoundException(
                "Email address is not registered"
            )

        if not user.is_active:
            raise UnauthorizedException(
                "Account is disabled"
            )

        if user.tenant_id is not None:
            tenant = (
                self.db.query(Tenant)
                .filter(Tenant.id == user.tenant_id)
                .first()
            )
            if not tenant or not tenant.is_active:
                raise UnauthorizedException(
                    "Tenant account is disabled"
                )

        self.verify_otp_code(
            purpose=OTPPurpose.PASSWORD_RESET,
            tenant_id=user.tenant_id,
            identifier=email,
            otp_code=data.otp,
        )

        raw_token = secrets.token_urlsafe(
            32
        )

        token_hash = hashlib.sha256(
            raw_token.encode("utf-8")
        ).hexdigest()

        expires_at = (
            datetime.utcnow()
            + timedelta(minutes=10)
        )

        (
            self.db.query(PasswordResetToken)
            .filter(
                PasswordResetToken.user_id
                == user.id,
                PasswordResetToken.used_at.is_(None),
            )
            .update(
                {"used_at": datetime.utcnow()},
                synchronize_session=False,
            )
        )

        reset_token = PasswordResetToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=expires_at,
            used_at=None,
        )

        self.db.add(reset_token)
        self.db.commit()

        return raw_token

    def reset_password(
        self,
        data: ResetPasswordRequest,
    ) -> str:

        _validate_password(
            data.new_password
        )

        token = data.token.strip()

        token_hash = hashlib.sha256(
            token.encode("utf-8")
        ).hexdigest()

        reset_token = (
            self.db.query(PasswordResetToken)
            .filter(
                PasswordResetToken.token_hash
                == token_hash,
                PasswordResetToken.used_at.is_(None),
            )
            .first()
        )

        if not reset_token:
            raise UnauthorizedException(
                "Invalid or expired reset token"
            )

        if reset_token.expires_at < datetime.utcnow():
            reset_token.used_at = datetime.utcnow()
            self.db.commit()

            raise UnauthorizedException(
                "Invalid or expired reset token"
            )

        user = (
            self.db.query(User)
            .filter(
                User.id
                == reset_token.user_id
            )
            .first()
        )

        if not user:
            reset_token.used_at = datetime.utcnow()
            self.db.commit()

            raise UnauthorizedException(
                "Invalid or expired reset token"
            )

        if not user.is_active:
            raise UnauthorizedException(
                "Account is disabled"
            )

        if user.tenant_id is not None:
            tenant = (
                self.db.query(Tenant)
                .filter(Tenant.id == user.tenant_id)
                .first()
            )
            if not tenant or not tenant.is_active:
                raise UnauthorizedException(
                    "Tenant account is disabled"
                )

        user.password_hash = (
            get_password_hash(
                data.new_password
            )
        )

        reset_token.used_at = datetime.utcnow()

        self.db.commit()

        return "Password reset successfully"

    def change_password(
        self,
        user: User,
        data: ChangePasswordRequest,
        current_token: str | None = None,
    ) -> str:

        if not user.is_active:
            raise UnauthorizedException(
                "Account is disabled"
            )

        if user.tenant_id is None:
            raise UnauthorizedException(
                "Invalid tenant user account"
            )

        tenant = (
            self.db.query(Tenant)
            .filter(
                Tenant.id == user.tenant_id
            )
            .first()
        )

        if not tenant or not tenant.is_active:
            raise UnauthorizedException(
                "Tenant account is disabled"
            )

        if not verify_password(
            data.old_password,
            user.hashed_password,
        ):
            raise UnauthorizedException(
                "Current password is incorrect"
            )

        if (
            data.new_password
            != data.confirm_password
        ):
            raise AppException(
                "New password and confirm password do not match"
            )

        if (
            data.old_password
            == data.new_password
        ):
            raise AppException(
                "New password must be different from current password"
            )

        _validate_password(
            data.new_password
        )

        user.password_hash = (
            get_password_hash(
                data.new_password
            )
        )

        self.db.commit()

        if current_token:
            try:
                blacklist_token(
                    current_token,
                )
            except Exception:
                pass

        self._record_activity(
            user.id,
            "password_changed",
        )

        return "Password changed successfully"

    # ------------------------------------------------------------------
    # Phase 2-D2 — Mobile + OTP Login
    # ------------------------------------------------------------------

    def _resolve_tenant_by_domain(self, domain: str) -> Tenant:
        """
        Resolve an active Tenant from its domain identifier.
        Raises UnauthorizedException if the tenant does not exist or is inactive.
        Uses generic messages to avoid tenant enumeration.
        """
        domain = domain.strip().lower()
        tenant = (
            self.db.query(Tenant)
            .filter(Tenant.domain == domain)
            .first()
        )
        if not tenant or not tenant.is_active:
            raise UnauthorizedException("Authentication failed")
        return tenant

    def _find_active_user_by_phone(
        self,
        tenant_id: int,
        normalized_phone: str,
    ) -> User | None:
        """
        Find the active, non-deleted user for a tenant and normalized phone.
        Returns None if not found (caller decides how to handle enumeration).
        """
        return (
            self.db.query(User)
            .filter(
                User.tenant_id == tenant_id,
                User.phone == normalized_phone,
                User.is_active.is_(True),
                User.is_deleted.is_(False),
            )
            .first()
        )

    def _validate_user_store(self, user: User) -> None:
        """
        If the user is assigned to a store, ensure that store belongs to the
        same tenant and is active. Raises UnauthorizedException otherwise.
        Users with store_id = NULL are allowed (tenant-level users).
        """
        if user.store_id is None:
            return

        store = (
            self.db.query(Store)
            .filter(Store.id == user.store_id)
            .first()
        )

        if not store or store.tenant_id != user.tenant_id or not store.is_active:
            raise UnauthorizedException("Account access is restricted")

    def mobile_otp_request(
        self,
        data: MobileOTPRequestSchema,
    ) -> None:
        """
        POST /api/v1/auth/login/mobile-otp/request

        Generates and stores (via the unified OTP core) a MOBILE_LOGIN OTP for
        the given phone number.

        Security:
        - Resolves user globally via get_active_user_by_phone (no domain input).
        - Derives tenant_id from user.tenant_id.
        - Always returns a generic success message to prevent phone enumeration.
        - OTP is never returned in the API response.
        - Tenant must be active; otherwise, no OTP is generated.
        - If the phone is not found or inactive, returns silently (no-op) to
          prevent enumeration of registered phone numbers.
        - Rate limiting and resend cooldown are enforced by the OTP core.
        """
        # 1. Normalize phone
        canonical_phone = normalize_phone_number(data.phone)

        # 2. Look up user globally (no tenant filter, active/non-deleted only)
        user = self.user_repo.get_active_user_by_phone(canonical_phone)
        if not user or not user.is_active:
            # Silently return — generic response to caller prevents enumeration
            return

        # 3. Derive tenant from user and validate
        if user.tenant_id is None:
            return

        tenant = (
            self.db.query(Tenant)
            .filter(Tenant.id == user.tenant_id)
            .first()
        )
        if not tenant or not tenant.is_active:
            # Inactive tenant: silent return (generic enumeration-safe behavior)
            return

        # 4. Validate store (if assigned)
        self._validate_user_store(user)

        # 5. Generate OTP via the unified D1 engine
        #    Rate limit + cooldown enforced inside generate_and_store_otp.
        #    SMS provider delivery is executed inside generate_and_store_otp.
        self.generate_and_store_otp(
            purpose=OTPPurpose.MOBILE_LOGIN,
            tenant_id=tenant.id,
            identifier=canonical_phone,
        )

    def mobile_otp_verify(
        self,
        data: MobileOTPVerifySchema,
    ) -> TokenResponse:
        """
        POST /api/v1/auth/login/mobile-otp/verify

        Full verification flow:
          1. Normalize phone.
          2. Resolve active, non-deleted user globally via get_active_user_by_phone.
          3. Derive tenant from user.tenant_id and validate tenant active.
          4. Validate store if assigned.
          5. Verify OTP via unified D1 engine (MOBILE_LOGIN purpose).
          6. Mark phone as verified (is_mobile_verified + mobile_verified_at).
          7. Issue JWT using the exact same token_data structure as email login.

        Security:
        - Resolves tenant strictly from the authenticated user, NOT from client input.
        - Cross-tenant and cross-purpose OTP reuse is prevented by the D1 engine.
        - JWT structure is identical to email/password login.
        """
        # 1. Normalize phone
        canonical_phone = normalize_phone_number(data.phone)

        # 2. Resolve active, non-deleted user globally
        user = self.user_repo.get_active_user_by_phone(canonical_phone)
        if not user or not user.is_active:
            raise UnauthorizedException("Authentication failed")

        # 3. Derive tenant from user and validate
        if user.tenant_id is None:
            raise UnauthorizedException("Authentication failed")

        tenant = (
            self.db.query(Tenant)
            .filter(Tenant.id == user.tenant_id)
            .first()
        )
        if not tenant or not tenant.is_active:
            raise UnauthorizedException("Authentication failed")

        # 4. Validate store
        self._validate_user_store(user)

        # 5. Verify OTP (D1 engine: purpose-scoped, tenant-scoped, single-use)
        self.verify_otp_code(
            purpose=OTPPurpose.MOBILE_LOGIN,
            tenant_id=tenant.id,
            identifier=canonical_phone,
            otp_code=data.otp,
        )

        # 6. Mark phone as verified on first successful mobile login
        if not user.is_mobile_verified:
            user.is_mobile_verified = True
            user.mobile_verified_at = datetime.now(timezone.utc)
            try:
                self.db.commit()
                self.db.refresh(user)
            except Exception:
                self.db.rollback()
                pass

        # 7. Issue JWT — exact same token_data structure as email/password login
        token_data = {
            "sub": str(user.id),
            "tenant_id": user.tenant_id,
            "role": (
                user.role.name
                if user.role
                else ""
            ),
            "store_id": user.store_id,
        }

        return TokenResponse(
            access_token=create_access_token(token_data),
            refresh_token=create_refresh_token(token_data),
        )

    # ------------------------------------------------------------------
    # Phase 2-D3 — Mobile + PIN Login
    # ------------------------------------------------------------------

    def _pin_attempts_key(self, tenant_id: int, normalized_phone: str) -> str:
        return f"auth:pin:attempts:{tenant_id}:{normalized_phone}"

    def _pin_lock_key(self, tenant_id: int, normalized_phone: str) -> str:
        return f"auth:pin:lock:{tenant_id}:{normalized_phone}"

    def _is_pin_locked(self, tenant_id: int, normalized_phone: str) -> bool:
        lock_key = self._pin_lock_key(tenant_id, normalized_phone)
        try:
            return bool(self.redis.get(lock_key))
        except Exception:
            return False

    def _record_failed_pin_attempt(self, tenant_id: int, normalized_phone: str) -> None:
        attempts_key = self._pin_attempts_key(tenant_id, normalized_phone)
        lock_key = self._pin_lock_key(tenant_id, normalized_phone)
        try:
            current = self.redis.get(attempts_key)
            if current is None or (int(current) >= PIN_MAX_FAILED_ATTEMPTS and not self.redis.get(lock_key)):
                attempts = 1
            else:
                attempts = int(current) + 1

            self.redis.setex(attempts_key, PIN_ATTEMPTS_WINDOW_SECONDS, str(attempts))

            if attempts >= PIN_MAX_FAILED_ATTEMPTS:
                self.redis.setex(lock_key, PIN_LOCK_DURATION_SECONDS, "1")
        except Exception:
            pass

    def _clear_pin_attempt_state(self, tenant_id: int, normalized_phone: str) -> None:
        attempts_key = self._pin_attempts_key(tenant_id, normalized_phone)
        lock_key = self._pin_lock_key(tenant_id, normalized_phone)
        try:
            self.redis.delete(attempts_key, lock_key)
        except Exception:
            pass

    def mobile_pin_login(
        self,
        data: MobilePINLoginRequest,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> TokenResponse:
        """
        POST /api/v1/auth/login/mobile-pin

        Authenticates user with normalized phone + 4-digit PIN.
        Security:
        - Resolves tenant from user.tenant_id globally (no domain input).
        - Brute-force lockout: 5 failed attempts -> 15 min lock
        - Generic errors: No disclosure of phone existence, wrong PIN, or inactive state
        - Tenant-isolated brute-force state using (tenant_id, canonical_phone)
        - Never affects password or OTP login
        - Uses bcrypt verification via verify_password
        - Issues identical JWT access + refresh tokens
        """
        # 1. Normalize phone
        canonical_phone = normalize_phone_number(data.phone)

        # 2. Lookup active, non-deleted user globally
        user = self.user_repo.get_active_user_by_phone(canonical_phone)
        if not user or not user.is_active:
            raise UnauthorizedException("Authentication failed")

        # 3. Derive tenant from user and validate
        if user.tenant_id is None:
            raise UnauthorizedException("Authentication failed")

        tenant = (
            self.db.query(Tenant)
            .filter(Tenant.id == user.tenant_id)
            .first()
        )
        if not tenant or not tenant.is_active:
            raise UnauthorizedException("Authentication failed")

        # 4. Check brute-force lock using tenant_id + canonical_phone
        if self._is_pin_locked(tenant.id, canonical_phone):
            raise UnauthorizedException(
                "Account is temporarily locked. Please try again later."
            )

        # 5. Validate store if assigned
        if user.store_id is not None:
            store = (
                self.db.query(Store)
                .filter(Store.id == user.store_id)
                .first()
            )
            if not store or store.tenant_id != user.tenant_id or not store.is_active:
                self._record_failed_pin_attempt(tenant.id, canonical_phone)
                raise UnauthorizedException("Authentication failed")

        # 6. Verify PIN hash exists on user
        if not user.pin_hash:
            self._record_failed_pin_attempt(tenant.id, canonical_phone)
            raise UnauthorizedException("Authentication failed")

        # 7. Verify PIN using bcrypt
        try:
            pin_valid = verify_password(data.pin, user.pin_hash)
        except Exception:
            pin_valid = False

        if not pin_valid:
            self._record_failed_pin_attempt(tenant.id, canonical_phone)
            raise UnauthorizedException("Authentication failed")

        # 8. Clear brute-force state on successful login
        self._clear_pin_attempt_state(tenant.id, canonical_phone)

        # 9. Issue JWT — exact same token_data structure as email/password login
        token_data = {
            "sub": str(user.id),
            "tenant_id": user.tenant_id,
            "role": (
                user.role.name
                if user.role
                else ""
            ),
            "store_id": user.store_id,
        }

        self._record_activity(
            user.id,
            "mobile_pin_login",
            ip_address,
            user_agent,
        )

        return TokenResponse(
            access_token=create_access_token(token_data),
            refresh_token=create_refresh_token(token_data),
        )

    # ------------------------------------------------------------------
    # PIN Reset & Management Flow
    # ------------------------------------------------------------------

    def pin_reset_request(
        self,
        data: PINResetRequestSchema,
    ) -> None:
        """
        POST /api/v1/auth/pin/reset/request

        Generates and stores a PIN_RESET OTP for the user associated with the phone.
        Security:
        - Resolves user globally via get_active_user_by_phone (no domain input).
        - Silent return (enumeration protection) if user not found, inactive, or tenant inactive.
        - Rate limiting and cooldown enforced by the OTP core.
        """
        # 1. Normalize phone
        canonical_phone = normalize_phone_number(data.phone)

        # 2. Resolve user globally
        user = self.user_repo.get_active_user_by_phone(canonical_phone)
        if not user or not user.is_active:
            return

        # 3. Derive tenant from user and validate
        if user.tenant_id is None:
            return

        tenant = (
            self.db.query(Tenant)
            .filter(Tenant.id == user.tenant_id)
            .first()
        )
        if not tenant or not tenant.is_active:
            return

        # 4. Validate store if assigned
        self._validate_user_store(user)

        # 5. Generate PIN_RESET OTP using existing OTP infrastructure
        self.generate_and_store_otp(
            purpose=OTPPurpose.PIN_RESET,
            tenant_id=tenant.id,
            identifier=canonical_phone,
        )

    def pin_reset_verify(
        self,
        data: PINResetVerifySchema,
    ) -> str:
        """
        POST /api/v1/auth/pin/reset/verify

        Verifies the PIN_RESET OTP and issues a single-use 256-bit reset token.
        Security:
        - Resolves user globally via get_active_user_by_phone (no domain input).
        - Validates tenant active.
        - Verifies OTPPurpose.PIN_RESET.
        - Generates 256-bit secure reset token with 10-minute expiry.
        - Stores SHA-256 hash in password_reset_tokens table.
        - Returns raw reset token.
        """
        # 1. Normalize phone
        canonical_phone = normalize_phone_number(data.phone)

        # 2. Resolve active user globally
        user = self.user_repo.get_active_user_by_phone(canonical_phone)
        if not user or not user.is_active:
            raise UnauthorizedException("Authentication failed")

        # 3. Derive tenant from user and validate
        if user.tenant_id is None:
            raise UnauthorizedException("Authentication failed")

        tenant = (
            self.db.query(Tenant)
            .filter(Tenant.id == user.tenant_id)
            .first()
        )
        if not tenant or not tenant.is_active:
            raise UnauthorizedException("Authentication failed")

        # 4. Validate store if assigned
        self._validate_user_store(user)

        # 5. Verify OTP (purpose=PIN_RESET)
        self.verify_otp_code(
            purpose=OTPPurpose.PIN_RESET,
            tenant_id=tenant.id,
            identifier=canonical_phone,
            otp_code=data.otp,
        )

        # 6. Issue secure reset token
        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        expires_at = datetime.utcnow() + timedelta(minutes=10)

        # Invalidate any previous unused reset tokens for this user
        (
            self.db.query(PasswordResetToken)
            .filter(
                PasswordResetToken.user_id == user.id,
                PasswordResetToken.used_at.is_(None),
            )
            .update(
                {"used_at": datetime.utcnow()},
                synchronize_session=False,
            )
        )

        reset_token = PasswordResetToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=expires_at,
            used_at=None,
        )
        self.db.add(reset_token)
        self.db.commit()

        return raw_token

    def pin_setup(
        self,
        user: User,
        data: PINSetupRequest,
    ) -> str:
        """
        POST /api/v1/auth/pin/setup

        Sets the user's 4-digit PIN for the first time.
        Requires authenticated user.
        """
        if not user.is_active or user.is_deleted:
            raise UnauthorizedException("Account is disabled")

        if user.pin_hash:
            raise ConflictException("PIN is already set. Use change PIN instead.")

        user.pin_hash = get_password_hash(data.pin)
        user.pin_set_at = datetime.now(timezone.utc)
        self.db.commit()
        return "PIN set successfully"

    def _pin_change_attempts_key(self, tenant_id: int, user_id: int) -> str:
        return f"auth:pin_change:attempts:{tenant_id}:{user_id}"

    def _pin_change_lock_key(self, tenant_id: int, user_id: int) -> str:
        return f"auth:pin_change:lock:{tenant_id}:{user_id}"

    def _is_pin_change_locked(self, tenant_id: int, user_id: int) -> bool:
        lock_key = self._pin_change_lock_key(tenant_id, user_id)
        try:
            return bool(self.redis.get(lock_key))
        except Exception:
            return False

    def _record_failed_pin_change_attempt(self, tenant_id: int, user_id: int) -> None:
        attempts_key = self._pin_change_attempts_key(tenant_id, user_id)
        lock_key = self._pin_change_lock_key(tenant_id, user_id)
        try:
            current = self.redis.get(attempts_key)
            if current is None or (int(current) >= PIN_MAX_FAILED_ATTEMPTS and not self.redis.get(lock_key)):
                attempts = 1
            else:
                attempts = int(current) + 1

            self.redis.setex(attempts_key, PIN_ATTEMPTS_WINDOW_SECONDS, str(attempts))

            if attempts >= PIN_MAX_FAILED_ATTEMPTS:
                self.redis.setex(lock_key, PIN_LOCK_DURATION_SECONDS, "1")
        except Exception:
            pass

    def _clear_pin_change_attempt_state(self, tenant_id: int, user_id: int) -> None:
        attempts_key = self._pin_change_attempts_key(tenant_id, user_id)
        lock_key = self._pin_change_lock_key(tenant_id, user_id)
        try:
            self.redis.delete(attempts_key, lock_key)
        except Exception:
            pass

    def pin_change(
        self,
        user: User,
        data: PINChangeRequest,
    ) -> str:
        """
        POST /api/v1/auth/pin/change

        Changes user's PIN after validating current PIN.
        Requires authenticated user.
        Brute-force protection:
        - 5 failed current-PIN attempts -> 15 min lockout
        - Keyed by (user.tenant_id, user.id)
        """
        if not user.is_active or user.is_deleted:
            raise UnauthorizedException("Account is disabled")

        if not user.pin_hash:
            raise UnauthorizedException("PIN has not been set yet")

        tenant_id = user.tenant_id or 0
        if self._is_pin_change_locked(tenant_id, user.id):
            raise UnauthorizedException(
                "Account is temporarily locked. Please try again later."
            )

        try:
            pin_valid = verify_password(data.current_pin, user.pin_hash)
        except Exception:
            pin_valid = False

        if not pin_valid:
            self._record_failed_pin_change_attempt(tenant_id, user.id)
            raise UnauthorizedException("Current PIN is incorrect")

        self._clear_pin_change_attempt_state(tenant_id, user.id)

        if data.current_pin == data.new_pin:
            raise AppException("New PIN must be different from current PIN")

        user.pin_hash = get_password_hash(data.new_pin)
        user.pin_set_at = datetime.now(timezone.utc)

        if user.phone and user.tenant_id:
            try:
                canonical_phone = normalize_phone_number(user.phone)
                self._clear_pin_attempt_state(user.tenant_id, canonical_phone)
            except Exception:
                pass

        self.db.commit()
        return "PIN changed successfully"

    def pin_reset(
        self,
        data: ResetPINRequest,
    ) -> str:
        """
        POST /api/v1/auth/pin/reset

        Consumes the reset token issued by pin_reset_verify and sets a new 4-digit PIN.
        """
        token = data.token.strip()
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()

        reset_token = (
            self.db.query(PasswordResetToken)
            .filter(
                PasswordResetToken.token_hash == token_hash,
                PasswordResetToken.used_at.is_(None),
            )
            .first()
        )

        if not reset_token:
            raise UnauthorizedException("Invalid or expired reset token")

        if reset_token.expires_at < datetime.utcnow():
            reset_token.used_at = datetime.utcnow()
            self.db.commit()
            raise UnauthorizedException("Invalid or expired reset token")

        user = (
            self.db.query(User)
            .filter(User.id == reset_token.user_id)
            .first()
        )

        if not user or not user.is_active or user.is_deleted:
            reset_token.used_at = datetime.utcnow()
            self.db.commit()
            raise UnauthorizedException("Invalid or expired reset token")

        if user.tenant_id is not None:
            tenant = (
                self.db.query(Tenant)
                .filter(Tenant.id == user.tenant_id)
                .first()
            )
            if not tenant or not tenant.is_active:
                raise UnauthorizedException("Tenant account is disabled")

        user.pin_hash = get_password_hash(data.new_pin)
        user.pin_set_at = datetime.now(timezone.utc)
        reset_token.used_at = datetime.utcnow()

        if user.phone and user.tenant_id:
            try:
                canonical_phone = normalize_phone_number(user.phone)
                self._clear_pin_attempt_state(user.tenant_id, canonical_phone)
            except Exception:
                pass

        self.db.commit()
        return "PIN reset successfully"