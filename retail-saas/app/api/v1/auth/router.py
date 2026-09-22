from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import (
    get_current_user,
    security_scheme,
)
from app.models.user import User
from app.schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    RegisterResponse,
    ResetPasswordRequest,
    TokenResponse,
    VerifyOTPRequest,
)
from app.services.auth_service import AuthService


router = APIRouter(
    prefix="/auth",
    tags=["auth"],
)


def _get_client_ip(
    request: Request,
) -> str | None:
    forwarded_for = request.headers.get(
        "x-forwarded-for"
    )

    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    real_ip = request.headers.get(
        "x-real-ip"
    )

    if real_ip:
        return real_ip.strip()

    if request.client:
        return request.client.host

    return None


def _get_user_agent(
    request: Request,
) -> str | None:
    return request.headers.get(
        "user-agent"
    )


@router.post(
    "/login",
    response_model=TokenResponse,
)
def login(
    data: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    return AuthService(db).login(
        data,
        ip_address=_get_client_ip(request),
        user_agent=_get_user_agent(request),
    )


@router.post(
    "/refresh",
    response_model=TokenResponse,
)
def refresh(
    data: RefreshRequest,
    db: Session = Depends(get_db),
):
    return AuthService(db).refresh(
        data.refresh_token
    )


@router.post(
    "/refresh-token",
    response_model=TokenResponse,
)
def refresh_token(
    data: RefreshRequest,
    db: Session = Depends(get_db),
):
    return AuthService(db).refresh(
        data.refresh_token
    )


@router.post("/logout")
def logout(
    credentials: HTTPAuthorizationCredentials | None = Depends(
        security_scheme
    ),
    db: Session = Depends(get_db),
):
    token = (
        credentials.credentials
        if credentials
        else None
    )

    return AuthService(db).logout(
        token
    )


@router.post("/register", response_model=RegisterResponse, status_code=200)
def register(
    data: Optional[RegisterRequest] = Body(None),
    tenant_name: Optional[str] = Query(None, include_in_schema=False),
    slug: Optional[str] = Query(None, include_in_schema=False),
    domain: Optional[str] = Query(None, include_in_schema=False),
    email: Optional[str] = Query(None, include_in_schema=False),
    admin_name: Optional[str] = Query(None, include_in_schema=False),
    password: Optional[str] = Query(None, include_in_schema=False),
    phone: Optional[str] = Query(None, include_in_schema=False),
    db: Session = Depends(get_db),
):
    if data is None:
        if not tenant_name or not (domain or slug) or not email or not admin_name or not password:
            raise HTTPException(status_code=422, detail="Missing required registration fields")
        data = RegisterRequest(
            tenant_name=tenant_name,
            domain=domain or slug,
            email=email,
            admin_name=admin_name,
            password=password,
            phone=phone,
        )

    user = AuthService(db).register_tenant(data)

    return {
        "message": "Tenant registered",
        "user_id": user.id,
        "tenant_id": user.tenant_id,
    }


@router.post("/forgot-password")
def forgot_password(
    data: ForgotPasswordRequest,
    db: Session = Depends(get_db),
):
    otp = AuthService(db).forgot_password(
        data
    )

    return {
        "success": True,
        "message": "OTP generated successfully.",
        "otp": otp,
        "expires_in": 300,
    }


@router.post("/verify-otp")
def verify_otp(
    data: VerifyOTPRequest,
    db: Session = Depends(get_db),
):
    reset_token = AuthService(db).verify_otp(
        data
    )

    return {
        "success": True,
        "message": "OTP verified successfully.",
        "reset_token": reset_token,
        "expires_in": 600,
    }


@router.post("/reset-password")
def reset_password(
    data: ResetPasswordRequest,
    db: Session = Depends(get_db),
):
    message = AuthService(db).reset_password(
        data
    )

    return {
        "success": True,
        "message": message,
    }


@router.post("/change-password")
def change_password(
    data: ChangePasswordRequest,
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(
        security_scheme
    ),
    current_user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    current_token = (
        credentials.credentials
        if credentials
        else None
    )

    message = AuthService(
        db
    ).change_password(
        current_user,
        data,
        current_token,
    )

    return {
        "success": True,
        "message": message,
    }