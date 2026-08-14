import hashlib
import secrets
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.core.exceptions import UnauthorizedException
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
            return ""

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