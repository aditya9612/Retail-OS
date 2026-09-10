import hashlib
import secrets
import re
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.core.exceptions import AppException, NotFoundException, UnauthorizedException
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_password_hash,
    verify_password,
)
from app.models.password_reset_token import PasswordResetToken
from app.models.role import Role
from app.models.tenant import Tenant
from app.models.user import User
from app.repositories.user_repo import UserRepository
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    ResetPasswordRequest,
    TokenResponse,
)
from app.utils.constants import (
    DEFAULT_ROLE_PERMISSIONS,
    UserRole,
)

_SLUG_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{1,98}[a-z0-9])?$")
_PHONE_PATTERN = re.compile(r"^\d{10,15}$")


def _validate_password(password: str) -> str:
    if len(password) < 8 or len(password) > 100:
        raise AppException("Password must be between 8 and 100 characters")
    if not all(
        (
            any(character.isupper() for character in password),
            any(character.islower() for character in password),
            any(character.isdigit() for character in password),
            any(not character.isalnum() for character in password),
        )
    ):
        raise AppException(
            "Password must contain uppercase, lowercase, number, and special character"
        )
    return password


class AuthService:

    def __init__(self, db: Session):
        self.db = db
        self.user_repo = UserRepository(db)

    def login(self, data: LoginRequest) -> TokenResponse:
        user = self.user_repo.get_by_email(data.email)

        if not user or not verify_password(
            data.password,
            user.hashed_password,
        ):
            raise UnauthorizedException(
                "Invalid email or password"
            )

        if not user.is_active:
            raise UnauthorizedException(
                "Account is disabled"
            )

        token_data = {
            "sub": str(user.id),
            "tenant_id": user.tenant_id,
            "role": user.role.name if user.role else "",
            "store_id": user.store_id,
        }

        return TokenResponse(
            access_token=create_access_token(token_data),
            refresh_token=create_refresh_token(token_data),
        )

    def refresh(
        self,
        refresh_token: str,
    ) -> TokenResponse:

        payload = decode_token(refresh_token)

        if payload.get("type") != "refresh":
            raise UnauthorizedException(
                "Invalid refresh token"
            )

        user = self.user_repo.get_by_id(
            int(payload["sub"]),
            payload["tenant_id"],
        )

        if not user or not user.is_active:
            raise UnauthorizedException(
                "User not found"
            )

        token_data = {
            "sub": str(user.id),
            "tenant_id": user.tenant_id,
            "role": user.role.name if user.role else "",
            "store_id": user.store_id,
        }

        return TokenResponse(
            access_token=create_access_token(token_data),
            refresh_token=create_refresh_token(token_data),
        )

    def register_tenant(
        self,
        tenant_name: str,
        slug: str,
        email: str,
        admin_name: str,
        password: str,
        phone: str | None = None,
    ) -> User:

        tenant_name = tenant_name.strip()
        slug = slug.strip().lower()
        email = email.strip().lower()
        admin_name = admin_name.strip()
        if len(tenant_name) < 2 or len(tenant_name) > 255:
            raise AppException("Tenant name must be between 2 and 255 characters")
        if not _SLUG_PATTERN.fullmatch(slug):
            raise AppException("Slug must contain lowercase letters, numbers, and hyphens")
        if not admin_name or len(admin_name) > 255:
            raise AppException("Admin name is required and must be at most 255 characters")
        if phone is not None:
            phone = phone.strip()
            if not _PHONE_PATTERN.fullmatch(phone):
                raise AppException("Phone must contain 10 to 15 digits")
        _validate_password(password)

        existing = (
            self.db.query(Tenant)
            .filter(Tenant.slug == slug)
            .first()
        )

        if existing:
            from app.core.exceptions import ConflictException

            raise ConflictException(
                "Tenant slug already exists"
            )

        tenant = Tenant(
            name=tenant_name,
            slug=slug,
            email=email,
            phone=phone,
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

        user = User(
            tenant_id=tenant.id,
            role_id=admin_role.id,
            email=email,
            hashed_password=get_password_hash(password),
            full_name=admin_name,
            phone=phone,
        )

        return self.user_repo.create(user)

    def forgot_password(
        self,
        data: ForgotPasswordRequest,
    ) -> str:

        user = self.user_repo.get_by_email(data.email)

        if not user:
            raise NotFoundException(
                "Email address is not registered"
            )

        (
            self.db.query(PasswordResetToken)
            .filter(
                PasswordResetToken.user_id == user.id,
                PasswordResetToken.used.is_(False),
            )
            .update(
                {"used": True},
                synchronize_session=False,
            )
        )

        raw_token = secrets.token_urlsafe(32)

        token_hash = hashlib.sha256(
            raw_token.encode("utf-8")
        ).hexdigest()

        expires_at = datetime.utcnow() + timedelta(
            minutes=30
        )

        reset_token = PasswordResetToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=expires_at,
            used=False,
        )

        self.db.add(reset_token)
        self.db.commit()

        return raw_token

    def reset_password(
        self,
        data: ResetPasswordRequest,
    ) -> str:
        _validate_password(data.new_password)

        token_hash = hashlib.sha256(
            data.token.encode("utf-8")
        ).hexdigest()

        reset_token = (
            self.db.query(PasswordResetToken)
            .filter(
                PasswordResetToken.token_hash == token_hash,
                PasswordResetToken.used.is_(False),
            )
            .first()
        )

        if not reset_token:
            raise UnauthorizedException(
                "Invalid or expired reset token"
            )

        if reset_token.expires_at < datetime.utcnow():

            reset_token.used = True
            self.db.commit()

            raise UnauthorizedException(
                "Invalid or expired reset token"
            )

        user = (
            self.db.query(User)
            .filter(
                User.id == reset_token.user_id
            )
            .first()
        )

        if not user:
            raise UnauthorizedException(
                "Invalid or expired reset token"
            )

        if not user.is_active:
            raise UnauthorizedException(
                "Account is disabled"
            )

        user.hashed_password = get_password_hash(
            data.new_password
        )

        reset_token.used = True

        self.db.commit()

        return "Password reset successfully"