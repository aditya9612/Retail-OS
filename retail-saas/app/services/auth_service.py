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
from app.models.tenant import Tenant
from app.models.user import User
from app.repositories.user_repo import UserRepository
from app.schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
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


_SLUG_PATTERN = re.compile(
    r"^[a-z0-9](?:[a-z0-9-]{1,98}[a-z0-9])?$"
)

_PHONE_PATTERN = re.compile(
    r"^\d{10,15}$"
)

OTP_TTL_SECONDS = 300
OTP_ATTEMPTS_TTL_SECONDS = 600
OTP_MAX_ATTEMPTS = 5

LOGIN_RATE_LIMIT = 5
LOGIN_RATE_WINDOW_SECONDS = 900

OTP_RATE_LIMIT = 3
OTP_RATE_WINDOW_SECONDS = 900

ACTIVITY_TTL_SECONDS = 30 * 24 * 60 * 60


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

        payload_exp = payload.get("exp")

        try:
            blacklist_token(
                refresh_token,
                payload_exp,
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
                payload.get("exp"),
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
        if hasattr(data_or_name, "tenant_name"):
            tenant_name = data_or_name.tenant_name
            domain_val = getattr(data_or_name, "domain", None) or getattr(data_or_name, "slug", None)
            email = data_or_name.email
            admin_name = data_or_name.admin_name
            password = data_or_name.password
            phone = data_or_name.phone
        elif isinstance(data_or_name, dict):
            tenant_name = data_or_name.get("tenant_name", "")
            domain_val = data_or_name.get("domain") or data_or_name.get("slug", "")
            email = data_or_name.get("email", "")
            admin_name = data_or_name.get("admin_name", "")
            password = data_or_name.get("password", "")
            phone = data_or_name.get("phone")
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
                plan="basic",
                subscription_status="trial",
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

    def forgot_password(
        self,
        data: ForgotPasswordRequest,
    ) -> str:

        email = normalize_email(
            data.email
        )

        rate_key = (
            f"auth:forgot-password:rate:{email}"
        )

        self._rate_limit(
            rate_key,
            OTP_RATE_LIMIT,
            OTP_RATE_WINDOW_SECONDS,
            "Too many password reset requests. Please try again later.",
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

        otp = f"{secrets.randbelow(1000000):06d}"

        otp_hash = hashlib.sha256(
            otp.encode("utf-8")
        ).hexdigest()

        otp_key = (
            f"auth:password-reset:otp:{email}"
        )

        attempts_key = (
            f"auth:password-reset:attempts:{email}"
        )

        try:
            self.redis.setex(
                otp_key,
                OTP_TTL_SECONDS,
                otp_hash,
            )

            self.redis.setex(
                attempts_key,
                OTP_ATTEMPTS_TTL_SECONDS,
                "0",
            )

        except Exception as exc:
            raise AppException(
                "Password reset service is temporarily unavailable"
            ) from exc

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

        otp_key = (
            f"auth:password-reset:otp:{email}"
        )

        attempts_key = (
            f"auth:password-reset:attempts:{email}"
        )

        try:
            attempts_value = self.redis.get(
                attempts_key
            )

            attempts = int(
                attempts_value or "0"
            )

            if attempts >= OTP_MAX_ATTEMPTS:
                raise UnauthorizedException(
                    "Too many invalid OTP attempts. Please request a new OTP."
                )

            stored_hash = self.redis.get(
                otp_key
            )

            if not stored_hash:
                raise UnauthorizedException(
                    "OTP is invalid or expired"
                )

            supplied_hash = hashlib.sha256(
                data.otp.encode("utf-8")
            ).hexdigest()

            if not secrets.compare_digest(
                stored_hash,
                supplied_hash,
            ):
                attempts += 1

                self.redis.setex(
                    attempts_key,
                    OTP_ATTEMPTS_TTL_SECONDS,
                    str(attempts),
                )

                raise UnauthorizedException(
                    "Invalid OTP"
                )

            self.redis.delete(
                otp_key,
                attempts_key,
            )

        except UnauthorizedException:
            raise

        except Exception as exc:
            raise AppException(
                "OTP verification service is temporarily unavailable"
            ) from exc

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
                payload = decode_token(
                    current_token
                )

                blacklist_token(
                    current_token,
                    payload.get("exp"),
                )
            except Exception:
                pass

        self._record_activity(
            user.id,
            "password_changed",
        )

        return "Password changed successfully"