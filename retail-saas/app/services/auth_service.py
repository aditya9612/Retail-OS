from sqlalchemy.orm import Session

from app.core.exceptions import UnauthorizedException
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_password_hash,
    verify_password,
)
from app.models.role import Role
from app.models.tenant import Tenant
from app.models.user import User
from app.repositories.user_repo import UserRepository
from app.schemas.auth import LoginRequest, TokenResponse
from app.utils.constants import DEFAULT_ROLE_PERMISSIONS, UserRole


class AuthService:
    def __init__(self, db: Session):
        self.db = db
        self.user_repo = UserRepository(db)

    def login(self, data: LoginRequest) -> TokenResponse:
        user = self.user_repo.get_by_email(data.email)
        if not user or not verify_password(data.password, user.hashed_password):
            raise UnauthorizedException("Invalid email or password")
        if not user.is_active:
            raise UnauthorizedException("Account is disabled")
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

    def refresh(self, refresh_token: str) -> TokenResponse:
        payload = decode_token(refresh_token)
        if payload.get("type") != "refresh":
            raise UnauthorizedException("Invalid refresh token")
        user = self.user_repo.get_by_id(int(payload["sub"]), payload["tenant_id"])
        if not user or not user.is_active:
            raise UnauthorizedException("User not found")
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
        existing = self.db.query(Tenant).filter(Tenant.slug == slug).first()
        if existing:
            from app.core.exceptions import ConflictException
            raise ConflictException("Tenant slug already exists")

        tenant = Tenant(name=tenant_name, slug=slug, email=email, phone=phone)
        self.db.add(tenant)
        self.db.flush()

        for role_name in UserRole:
            role = Role(
                tenant_id=tenant.id,
                name=role_name.value,
                permissions=DEFAULT_ROLE_PERMISSIONS[role_name],
            )
            self.db.add(role)
        self.db.flush()

        admin_role = (
            self.db.query(Role)
            .filter(Role.tenant_id == tenant.id, Role.name == UserRole.ADMIN.value)
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
