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
    ResetPasswordRequest,
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
            elif not _PHONE_PATTERN.fullmatch(phone):
                raise AppException(
                    "Phone must contain 10 to 15 digits"
                )

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

        # 3. Cryptographically secure 6-digit OTP
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
        the given domain + phone combination.

        Security:
        - Always returns a generic success message to prevent phone enumeration.
        - OTP is never returned in the API response.
        - Tenant must be active; otherwise, no OTP is generated.
        - If the phone is not found, the method returns silently (no-op) to
          prevent enumeration of registered phone numbers.
        - Rate limiting and resend cooldown are enforced by the OTP core.
        """
        # 1. Resolve tenant (generic failure — no tenant enumeration)
        tenant = self._resolve_tenant_by_domain(data.domain)

        # 2. Normalize phone (already done by Pydantic schema, but be explicit)
        normalized_phone = data.phone  # Pydantic already called normalize_phone_number

        # 3. Look up user — silently no-op on unknown phone (no enumeration)
        user = self._find_active_user_by_phone(tenant.id, normalized_phone)
        if not user:
            # Do not raise; return silently. Caller returns the generic response.
            return

        # 4. Validate store (if assigned)
        self._validate_user_store(user)

        # 5. Generate OTP via the unified D1 engine
        #    Rate limit + cooldown enforced inside generate_and_store_otp.
        #    Returns the plaintext OTP (not used here — no delivery yet).
        self.generate_and_store_otp(
            purpose=OTPPurpose.MOBILE_LOGIN,
            tenant_id=tenant.id,
            identifier=normalized_phone,
        )

        # NOTE: SMS delivery will be wired here in Phase 2-E (SMS provider phase).
        # The OTP is intentionally NOT returned; the caller returns a generic response.

    def mobile_otp_verify(
        self,
        data: MobileOTPVerifySchema,
    ) -> TokenResponse:
        """
        POST /api/v1/auth/login/mobile-otp/verify

        Full verification flow:
          1. Re-resolve tenant (state may have changed since OTP request).
          2. Normalize phone.
          3. Find active, non-deleted user.
          4. Validate store if assigned.
          5. Verify OTP via unified D1 engine (MOBILE_LOGIN purpose).
          6. Mark phone as verified (is_mobile_verified + mobile_verified_at).
          7. Issue JWT using the exact same token_data structure as email login.

        Security:
        - All checks (tenant, user, store) are re-verified at verify time.
        - Cross-tenant and cross-purpose OTP reuse is prevented by the D1 engine.
        - JWT structure is identical to email/password login.
        """
        # 1. Re-resolve tenant
        tenant = self._resolve_tenant_by_domain(data.domain)

        # 2. Normalize phone (already normalized by schema)
        normalized_phone = data.phone

        # 3. Find active, non-deleted user
        user = self._find_active_user_by_phone(tenant.id, normalized_phone)
        if not user:
            raise UnauthorizedException("Authentication failed")

        # 4. Validate store
        self._validate_user_store(user)

        # 5. Verify OTP (D1 engine: purpose-scoped, tenant-scoped, single-use)
        self.verify_otp_code(
            purpose=OTPPurpose.MOBILE_LOGIN,
            tenant_id=tenant.id,
            identifier=normalized_phone,
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
                # Non-fatal: verification flag update failure doesn't block login
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

        Authenticates user with tenant domain + normalized phone + 4-digit PIN.
        Security:
        - Brute-force lockout: 5 failed attempts -> 15 min lock
        - Generic errors: No disclosure of phone existence, wrong PIN, or inactive state
        - Multi-tenant isolated brute-force state
        - Never affects password or OTP login
        - Uses bcrypt verification via verify_password
        - Issues identical JWT access + refresh tokens
        """
        # 1. Resolve tenant (generic failure — no tenant enumeration)
        tenant = self._resolve_tenant_by_domain(data.domain)

        # 2. Normalize phone
        normalized_phone = data.phone

        # 3. Check brute-force lock
        if self._is_pin_locked(tenant.id, normalized_phone):
            raise UnauthorizedException(
                "Account is temporarily locked. Please try again later."
            )

        # 4. Lookup active, non-deleted user
        user = self._find_active_user_by_phone(tenant.id, normalized_phone)
        if not user:
            self._record_failed_pin_attempt(tenant.id, normalized_phone)
            raise UnauthorizedException("Authentication failed")

        # 5. Validate store if assigned
        if user.store_id is not None:
            store = (
                self.db.query(Store)
                .filter(Store.id == user.store_id)
                .first()
            )
            if not store or store.tenant_id != user.tenant_id or not store.is_active:
                self._record_failed_pin_attempt(tenant.id, normalized_phone)
                raise UnauthorizedException("Authentication failed")

        # 6. Verify PIN hash exists on user
        if not user.pin_hash:
            self._record_failed_pin_attempt(tenant.id, normalized_phone)
            raise UnauthorizedException("Authentication failed")

        # 7. Verify PIN using bcrypt
        try:
            pin_valid = verify_password(data.pin, user.pin_hash)
        except Exception:
            pin_valid = False

        if not pin_valid:
            self._record_failed_pin_attempt(tenant.id, normalized_phone)
            raise UnauthorizedException("Authentication failed")

        # 8. Clear brute-force state on successful login
        self._clear_pin_attempt_state(tenant.id, normalized_phone)

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