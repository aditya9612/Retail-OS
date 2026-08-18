from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.exceptions import ForbiddenException, UnauthorizedException
from app.core.tenant import (
    set_current_store_id,
    set_current_tenant_id,
    set_current_user_id,
)
from app.models.user import User

settings = get_settings()

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
)

security_scheme = HTTPBearer(auto_error=False)


def verify_password(
    plain_password: str,
    hashed_password: str,
) -> bool:
    return pwd_context.verify(
        plain_password,
        hashed_password,
    )


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None,
) -> str:
    to_encode = data.copy()

    expire = datetime.now(timezone.utc) + (
        expires_delta
        or timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
    )

    to_encode.update(
        {
            "exp": expire,
            "type": "access",
        }
    )

    return jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def create_refresh_token(
    data: Dict[str, Any],
) -> str:
    to_encode = data.copy()

    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.REFRESH_TOKEN_EXPIRE_DAYS
    )

    to_encode.update(
        {
            "exp": expire,
            "type": "refresh",
        }
    )

    return jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def create_super_admin_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None,
) -> str:
    to_encode = data.copy()

    expire = datetime.now(timezone.utc) + (
        expires_delta
        or timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
    )

    to_encode.update(
        {
            "exp": expire,
            "type": "super_admin_access",
        }
    )

    return jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def create_super_admin_refresh_token(
    data: Dict[str, Any],
) -> str:
    to_encode = data.copy()

    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.REFRESH_TOKEN_EXPIRE_DAYS
    )

    to_encode.update(
        {
            "exp": expire,
            "type": "super_admin_refresh",
        }
    )

    return jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_token(
    token: str,
) -> Dict[str, Any]:
    try:
        return jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except JWTError as exc:
        raise UnauthorizedException(
            "Invalid or expired token"
        ) from exc


def get_current_user(
    credentials: Optional[
        HTTPAuthorizationCredentials
    ] = Depends(security_scheme),
    db: Session = Depends(get_db),
) -> User:
    if not credentials:
        raise UnauthorizedException()

    payload = decode_token(
        credentials.credentials
    )

    if payload.get("type") != "access":
        raise UnauthorizedException(
            "Invalid token type"
        )

    user_id = payload.get("sub")

    if not user_id:
        raise UnauthorizedException()

    try:
        user_id = int(user_id)
    except (TypeError, ValueError) as exc:
        raise UnauthorizedException(
            "Invalid user ID"
        ) from exc

    user = (
        db.query(User)
        .filter(
            User.id == user_id,
            User.is_active.is_(True),
        )
        .first()
    )

    if not user:
        raise UnauthorizedException(
            "User not found"
        )

    set_current_user_id(user.id)
    set_current_tenant_id(user.tenant_id)
    set_current_store_id(user.store_id)

    return user


def get_current_super_admin(
    credentials: Optional[
        HTTPAuthorizationCredentials
    ] = Depends(security_scheme),
    db: Session = Depends(get_db),
):
    from app.models.super_admin import SuperAdmin

    if not credentials:
        raise UnauthorizedException()

    payload = decode_token(
        credentials.credentials
    )

    if payload.get("type") != "super_admin_access":
        raise UnauthorizedException(
            "Invalid SuperAdmin token type"
        )

    super_admin_id = payload.get("sub")

    if not super_admin_id:
        raise UnauthorizedException()

    try:
        super_admin_id = int(super_admin_id)
    except (TypeError, ValueError) as exc:
        raise UnauthorizedException(
            "Invalid SuperAdmin ID"
        ) from exc

    super_admin = (
        db.query(SuperAdmin)
        .filter(
            SuperAdmin.id == super_admin_id,
            SuperAdmin.is_active.is_(True),
        )
        .first()
    )

    if not super_admin:
        raise UnauthorizedException(
            "SuperAdmin not found"
        )

    return super_admin


def require_permission(permission: str):
    def checker(
        user: User = Depends(get_current_user),
    ) -> User:
        perms = (
            user.role.permissions
            if user.role
            else []
        )

        if "*" in perms or permission in perms:
            return user

        raise ForbiddenException(
            f"Missing permission: {permission}"
        )

    return checker


def require_roles(*roles: str):
    def checker(
        user: User = Depends(get_current_user),
    ) -> User:
        if (
            user.role
            and user.role.name in roles
        ):
            return user

        raise ForbiddenException(
            "Insufficient role"
        )

    return checker