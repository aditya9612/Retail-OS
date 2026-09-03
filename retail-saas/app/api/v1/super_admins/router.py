from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import UnauthorizedException
from app.core.security import (
    create_super_admin_access_token,
    create_super_admin_refresh_token,
    decode_token,
    get_current_super_admin,
)
from app.models.super_admin import SuperAdmin
from app.schemas.super_admin import (
    SuperAdminChangePassword,
    SuperAdminCreate,
    SuperAdminDashboardResponse,
    SuperAdminLogin,
    SuperAdminResponse,
    SuperAdminStatusUpdate,
    SuperAdminTenantResponse,
    SuperAdminTenantUserResponse,
    SuperAdminTokenResponse,
    SuperAdminUpdate,
    TenantStatusUpdate,
)
from app.services.super_admin_service import SuperAdminService


router = APIRouter(
    prefix="/super-admins",
    tags=["Super Admins"],
)


@router.post(
    "",
    response_model=SuperAdminResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Super Admin",
)
def create_super_admin(
    data: SuperAdminCreate,
    db: Session = Depends(get_db),
):
    return SuperAdminService(db).create_super_admin(data)


@router.post(
    "/login",
    response_model=SuperAdminTokenResponse,
    summary="Super Admin Login",
)
def super_admin_login(
    data: SuperAdminLogin,
    db: Session = Depends(get_db),
):
    return SuperAdminService(db).login(data)


@router.post(
    "/refresh",
    response_model=SuperAdminTokenResponse,
    summary="Refresh Super Admin Token",
)
def refresh_super_admin_token(
    refresh_token: str,
    db: Session = Depends(get_db),
):
    payload = decode_token(refresh_token)

    if payload.get("type") != "super_admin_refresh":
        raise UnauthorizedException(
            "Invalid Super Admin refresh token"
        )

    if payload.get("role") != "SUPERADMIN":
        raise UnauthorizedException(
            "Invalid Super Admin refresh token"
        )

    super_admin_id = payload.get("sub")

    if not super_admin_id:
        raise UnauthorizedException(
            "Invalid Super Admin refresh token"
        )

    try:
        super_admin_id = int(super_admin_id)
    except (TypeError, ValueError) as exc:
        raise UnauthorizedException(
            "Invalid Super Admin ID"
        ) from exc

    service = SuperAdminService(db)

    super_admin = service.get_by_id(
        super_admin_id
    )

    if not super_admin.is_active:
        raise UnauthorizedException(
            "Super Admin account is disabled"
        )

    token_data = {
        "sub": str(super_admin.id),
        "role": "SUPERADMIN",
    }

    return {
        "access_token": create_super_admin_access_token(
            token_data
        ),
        "refresh_token": create_super_admin_refresh_token(
            token_data
        ),
        "token_type": "bearer",
    }


@router.get(
    "/me",
    response_model=SuperAdminResponse,
    summary="Get Current Super Admin",
)
def get_current_super_admin_profile(
    current_super_admin: SuperAdmin = Depends(
        get_current_super_admin
    ),
):
    return current_super_admin


@router.get(
    "/dashboard",
    response_model=SuperAdminDashboardResponse,
    summary="Super Admin Dashboard",
)
def super_admin_dashboard(
    current_super_admin: SuperAdmin = Depends(
        get_current_super_admin
    ),
    db: Session = Depends(get_db),
):
    return SuperAdminService(db).dashboard()


@router.get(
    "/tenants",
    response_model=list[SuperAdminTenantResponse],
    summary="List All Tenants",
)
def list_tenants(
    current_super_admin: SuperAdmin = Depends(
        get_current_super_admin
    ),
    db: Session = Depends(get_db),
):
    return SuperAdminService(db).list_tenants()


@router.get(
    "/tenants/{tenant_id}",
    response_model=SuperAdminTenantResponse,
    summary="Get Tenant",
)
def get_tenant(
    tenant_id: int,
    current_super_admin: SuperAdmin = Depends(
        get_current_super_admin
    ),
    db: Session = Depends(get_db),
):
    return SuperAdminService(db).get_tenant(
        tenant_id
    )


@router.patch(
    "/tenants/{tenant_id}/status",
    response_model=SuperAdminTenantResponse,
    summary="Activate or Deactivate Tenant",
)
def update_tenant_status(
    tenant_id: int,
    data: TenantStatusUpdate,
    current_super_admin: SuperAdmin = Depends(
        get_current_super_admin
    ),
    db: Session = Depends(get_db),
):
    return SuperAdminService(db).update_tenant_status(
        tenant_id,
        data.is_active,
    )


@router.get(
    "/tenants/{tenant_id}/users",
    response_model=list[SuperAdminTenantUserResponse],
    summary="List Tenant Users",
)
def list_tenant_users(
    tenant_id: int,
    current_super_admin: SuperAdmin = Depends(
        get_current_super_admin
    ),
    db: Session = Depends(get_db),
):
    return SuperAdminService(db).list_tenant_users(
        tenant_id
    )


@router.get(
    "",
    response_model=list[SuperAdminResponse],
    summary="List Super Admins",
)
def list_super_admins(
    current_super_admin: SuperAdmin = Depends(
        get_current_super_admin
    ),
    db: Session = Depends(get_db),
):
    return SuperAdminService(db).list_super_admins()


@router.get(
    "/{super_admin_id}",
    response_model=SuperAdminResponse,
    summary="Get Super Admin",
)
def get_super_admin(
    super_admin_id: int,
    current_super_admin: SuperAdmin = Depends(
        get_current_super_admin
    ),
    db: Session = Depends(get_db),
):
    return SuperAdminService(db).get_by_id(
        super_admin_id
    )


@router.patch(
    "/{super_admin_id}",
    response_model=SuperAdminResponse,
    summary="Update Super Admin",
)
def update_super_admin(
    super_admin_id: int,
    data: SuperAdminUpdate,
    current_super_admin: SuperAdmin = Depends(
        get_current_super_admin
    ),
    db: Session = Depends(get_db),
):
    return SuperAdminService(db).update_super_admin(
        super_admin_id,
        data,
    )


@router.patch(
    "/{super_admin_id}/status",
    response_model=SuperAdminResponse,
    summary="Activate or Deactivate Super Admin",
)
def update_super_admin_status(
    super_admin_id: int,
    data: SuperAdminStatusUpdate,
    current_super_admin: SuperAdmin = Depends(
        get_current_super_admin
    ),
    db: Session = Depends(get_db),
):
    if (
        super_admin_id == current_super_admin.id
        and not data.is_active
    ):
        raise UnauthorizedException(
            "You cannot deactivate your own account"
        )

    return SuperAdminService(db).update_status(
        super_admin_id,
        data.is_active,
    )


@router.delete(
    "/{super_admin_id}",
    summary="Delete Super Admin",
)
def delete_super_admin(
    super_admin_id: int,
    current_super_admin: SuperAdmin = Depends(
        get_current_super_admin
    ),
    db: Session = Depends(get_db),
):
    return SuperAdminService(db).delete_super_admin(
        super_admin_id,
        current_super_admin.id,
    )


@router.post(
    "/change-password",
    summary="Change Super Admin Password",
)
def change_password(
    data: SuperAdminChangePassword,
    current_super_admin: SuperAdmin = Depends(
        get_current_super_admin
    ),
    db: Session = Depends(get_db),
):
    return SuperAdminService(db).change_password(
        current_super_admin.id,
        data,
    )