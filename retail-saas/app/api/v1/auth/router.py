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
    MobileOTPRequestSchema,
    MobileOTPVerifySchema,
    MobilePINLoginRequest,
    PINChangeRequest,
    PINResetRequestSchema,
    PINResetVerifySchema,
    PINSetupRequest,
    RefreshRequest,
    RegisterRequest,
    RegisterResponse,
    ResetPasswordRequest,
    ResetPINRequest,
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


@router.post("/register", response_model=RegisterResponse, status_code=200, include_in_schema=False)
def register(
    data: Optional[RegisterRequest] = Body(None),
    tenant_name: Optional[str] = Query(None, include_in_schema=False),
    slug: Optional[str] = Query(None, include_in_schema=False),
    domain: Optional[str] = Query(None, include_in_schema=False),
    email: Optional[str] = Query(None, include_in_schema=False),
    admin_name: Optional[str] = Query(None, include_in_schema=False),
    password: Optional[str] = Query(None, include_in_schema=False),
    phone: Optional[str] = Query(None, include_in_schema=False),
    plan_id: Optional[int] = Query(None, include_in_schema=False),
    plan_code: Optional[str] = Query(None, include_in_schema=False),
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
            plan_id=plan_id,
            plan_code=plan_code,
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
    AuthService(db).forgot_password(
        data
    )

    return {
        "success": True,
        "message": "OTP sent successfully.",
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


@router.post(
    "/login/mobile-otp/request",
    summary="Request Mobile OTP Login",
    description=(
        "Generates a time-limited OTP for mobile number login. "
        "Returns a generic response regardless of whether the phone number "
        "is registered, to prevent phone enumeration attacks."
    ),
)
def mobile_otp_request(
    data: MobileOTPRequestSchema,
    db: Session = Depends(get_db),
):
    AuthService(db).mobile_otp_request(data)
    return {
        "success": True,
        "message": "If the account exists, an OTP has been sent.",
        "expires_in": 300,
    }


@router.post(
    "/login/mobile-otp/verify",
    response_model=TokenResponse,
    summary="Verify Mobile OTP and Login",
    description=(
        "Verifies the OTP for the given phone number. "
        "On success, marks the phone as verified and issues JWT access + refresh tokens."
    ),
)
def mobile_otp_verify(
    data: MobileOTPVerifySchema,
    db: Session = Depends(get_db),
):
    return AuthService(db).mobile_otp_verify(data)


@router.post(
    "/login/mobile-pin",
    response_model=TokenResponse,
    summary="Login with Mobile + PIN",
    description="Authenticates active user globally with canonical phone number and 4-digit PIN.",
)
def mobile_pin_login(
    data: MobilePINLoginRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    return AuthService(db).mobile_pin_login(
        data,
        ip_address=_get_client_ip(request),
        user_agent=_get_user_agent(request),
    )


@router.post(
    "/pin/setup",
    summary="Setup Initial Security PIN",
    description="Sets the initial 4-digit PIN for the authenticated user. Fails if PIN is already set.",
)
def pin_setup(
    data: PINSetupRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    message = AuthService(db).pin_setup(current_user, data)
    return {
        "success": True,
        "message": message,
    }


@router.post(
    "/pin/change",
    summary="Change Security PIN",
    description="Changes the 4-digit PIN for the authenticated user after verifying the current PIN.",
)
def pin_change(
    data: PINChangeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    message = AuthService(db).pin_change(current_user, data)
    return {
        "success": True,
        "message": message,
    }


@router.post(
    "/pin/reset/request",
    summary="Request PIN Reset OTP",
    description=(
        "Generates a time-limited OTP for resetting the security PIN. "
        "Returns a generic response regardless of whether the phone number "
        "is registered, to prevent phone enumeration attacks."
    ),
)
def pin_reset_request(
    data: PINResetRequestSchema,
    db: Session = Depends(get_db),
):
    AuthService(db).pin_reset_request(data)
    return {
        "success": True,
        "message": "If the account exists, an OTP has been sent.",
        "expires_in": 300,
    }


@router.post(
    "/pin/reset/verify",
    summary="Verify PIN Reset OTP",
    description="Verifies the OTP for PIN reset and issues a temporary single-use reset token.",
)
def pin_reset_verify(
    data: PINResetVerifySchema,
    db: Session = Depends(get_db),
):
    reset_token = AuthService(db).pin_reset_verify(data)
    return {
        "success": True,
        "message": "OTP verified successfully.",
        "reset_token": reset_token,
        "expires_in": 600,
    }


@router.post(
    "/pin/reset",
    summary="Reset Security PIN",
    description="Sets a new 4-digit security PIN using the authorization token from /pin/reset/verify.",
)
def pin_reset(
    data: ResetPINRequest,
    db: Session = Depends(get_db),
):
    message = AuthService(db).pin_reset(data)
    return {
        "success": True,
        "message": message,
    }
