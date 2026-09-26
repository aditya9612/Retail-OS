from fastapi import APIRouter, Depends, Query, status
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
    SuperAdminListResponse,
    SuperAdminLogin,
    SuperAdminRefreshToken,
    SuperAdminResponse,
    SuperAdminStatusUpdate,
    SuperAdminStoreListResponse,
    SuperAdminTenantDetailResponse,
    SuperAdminTenantListResponse,
    SuperAdminTenantResponse,
    SuperAdminTenantUserListResponse,
    SuperAdminTenantUserResponse,
    SuperAdminTokenResponse,
    SuperAdminUpdate,
    TenantStatusUpdate,
)
from app.schemas.saas_plan import (
    SaaSPlanCreate,
    SaaSPlanListResponse,
    SaaSPlanResponse,
    SaaSPlanUpdate,
)
from app.schemas.saas_entitlement import (
    SaaSPlanEntitlementCreate,
    SaaSPlanEntitlementListResponse,
    SaaSPlanEntitlementResponse,
    SaaSPlanEntitlementUpdate,
)
from app.schemas.saas_subscription import SaaSSubscriptionLifecycleRunResponse
from app.schemas.saas_upi import (
    UPIAdminTransactionResponse,
    UPITransactionListResponse,
    UPIRejectRequest,
)
from app.services.saas_subscription_lifecycle_service import SaaSSubscriptionLifecycleService
from app.services.saas_upi_service import SaaSUPIService
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
    current_super_admin: SuperAdmin = Depends(
        get_current_super_admin
    ),
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
    data: SuperAdminRefreshToken,
    db: Session = Depends(get_db),
):
    refresh_token = data.refresh_token
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
    response_model=SuperAdminTenantListResponse,
    summary="List Tenants",
)
def list_tenants(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page (1-100)"),
    search: str | None = Query(None, description="Search by name, domain, or admin email"),
    is_active: bool | None = Query(None, description="Filter by active status"),
    plan: str | None = Query(None, description="Filter by plan name"),
    subscription_status: str | None = Query(None, description="Filter by subscription status"),
    current_super_admin: SuperAdmin = Depends(
        get_current_super_admin
    ),
    db: Session = Depends(get_db),
):
    return SuperAdminService(db).list_tenants(
        page=page,
        page_size=page_size,
        search=search,
        is_active=is_active,
        plan=plan,
        subscription_status=subscription_status,
    )


@router.get(
    "/tenants/{tenant_id}",
    response_model=SuperAdminTenantDetailResponse,
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
    response_model=SuperAdminTenantUserListResponse,
    summary="List Tenant Users",
)
def list_tenant_users(
    tenant_id: int,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page (1-100)"),
    search: str | None = Query(None, description="Search by full name, email, or phone"),
    role: str | None = Query(None, description="Filter by role name (e.g. admin, manager, staff)"),
    is_active: bool | None = Query(None, description="Filter by active status"),
    current_super_admin: SuperAdmin = Depends(
        get_current_super_admin
    ),
    db: Session = Depends(get_db),
):
    return SuperAdminService(db).list_tenant_users(
        tenant_id=tenant_id,
        page=page,
        page_size=page_size,
        search=search,
        role=role,
        is_active=is_active,
    )


@router.get(
    "/tenants/{tenant_id}/stores",
    response_model=SuperAdminStoreListResponse,
    summary="List Tenant Stores",
)
def list_tenant_stores(
    tenant_id: int,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page (1-100)"),
    search: str | None = Query(None, description="Search by name, code, city, phone, or email"),
    is_active: bool | None = Query(None, description="Filter by active status"),
    is_main: bool | None = Query(None, description="Filter by main store flag"),
    city: str | None = Query(None, description="Filter by city"),
    state: str | None = Query(None, description="Filter by state"),
    current_super_admin: SuperAdmin = Depends(
        get_current_super_admin
    ),
    db: Session = Depends(get_db),
):
    return SuperAdminService(db).list_tenant_stores(
        tenant_id=tenant_id,
        page=page,
        page_size=page_size,
        search=search,
        is_active=is_active,
        is_main=is_main,
        city=city,
        state=state,
    )


# =========================
# SAAS PLAN MANAGEMENT APIS
# =========================


@router.post(
    "/saas-plans",
    response_model=SaaSPlanResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create SaaS Plan",
)
def create_saas_plan(
    data: SaaSPlanCreate,
    current_super_admin: SuperAdmin = Depends(
        get_current_super_admin
    ),
    db: Session = Depends(get_db),
):
    return SuperAdminService(db).create_plan(data)


@router.get(
    "/saas-plans",
    response_model=SaaSPlanListResponse,
    summary="List SaaS Plans",
)
def list_saas_plans(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page (1-100)"),
    search: str | None = Query(None, description="Search by plan name or code"),
    is_active: bool | None = Query(None, description="Filter by active status"),
    current_super_admin: SuperAdmin = Depends(
        get_current_super_admin
    ),
    db: Session = Depends(get_db),
):
    return SuperAdminService(db).list_plans(
        page=page,
        page_size=page_size,
        search=search,
        is_active=is_active,
    )


@router.get(
    "/saas-plans/{plan_id}",
    response_model=SaaSPlanResponse,
    summary="Get SaaS Plan Details",
)
def get_saas_plan(
    plan_id: int,
    current_super_admin: SuperAdmin = Depends(
        get_current_super_admin
    ),
    db: Session = Depends(get_db),
):
    return SuperAdminService(db).get_plan(plan_id)


@router.patch(
    "/saas-plans/{plan_id}",
    response_model=SaaSPlanResponse,
    summary="Update SaaS Plan",
)
def update_saas_plan(
    plan_id: int,
    data: SaaSPlanUpdate,
    current_super_admin: SuperAdmin = Depends(
        get_current_super_admin
    ),
    db: Session = Depends(get_db),
):
    return SuperAdminService(db).update_plan(
        plan_id,
        data,
    )


@router.patch(
    "/saas-plans/{plan_id}/activate",
    response_model=SaaSPlanResponse,
    summary="Activate SaaS Plan",
)
def activate_saas_plan(
    plan_id: int,
    current_super_admin: SuperAdmin = Depends(
        get_current_super_admin
    ),
    db: Session = Depends(get_db),
):
    return SuperAdminService(db).activate_plan(plan_id)


@router.patch(
    "/saas-plans/{plan_id}/deactivate",
    response_model=SaaSPlanResponse,
    summary="Deactivate SaaS Plan",
)
def deactivate_saas_plan(
    plan_id: int,
    current_super_admin: SuperAdmin = Depends(
        get_current_super_admin
    ),
    db: Session = Depends(get_db),
):
    return SuperAdminService(db).deactivate_plan(plan_id)


# ===============================
# SAAS PLAN ENTITLEMENT APIS
# ===============================


@router.get(
    "/saas-plans/{plan_id}/entitlements",
    response_model=SaaSPlanEntitlementListResponse,
    summary="List SaaS Plan Entitlements",
)
def list_plan_entitlements(
    plan_id: int,
    current_super_admin: SuperAdmin = Depends(get_current_super_admin),
    db: Session = Depends(get_db),
):
    return SuperAdminService(db).list_plan_entitlements(plan_id)


@router.post(
    "/saas-plans/{plan_id}/entitlements",
    response_model=SaaSPlanEntitlementResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create SaaS Plan Entitlement",
)
def create_plan_entitlement(
    plan_id: int,
    data: SaaSPlanEntitlementCreate,
    current_super_admin: SuperAdmin = Depends(get_current_super_admin),
    db: Session = Depends(get_db),
):
    return SuperAdminService(db).create_plan_entitlement(plan_id, data)


@router.put(
    "/saas-plans/{plan_id}/entitlements/{dimension}",
    response_model=SaaSPlanEntitlementResponse,
    summary="Update SaaS Plan Entitlement",
)
def update_plan_entitlement(
    plan_id: int,
    dimension: str,
    data: SaaSPlanEntitlementUpdate,
    current_super_admin: SuperAdmin = Depends(get_current_super_admin),
    db: Session = Depends(get_db),
):
    return SuperAdminService(db).update_plan_entitlement(plan_id, dimension, data)


@router.delete(
    "/saas-plans/{plan_id}/entitlements/{dimension}",
    status_code=status.HTTP_200_OK,
    summary="Delete SaaS Plan Entitlement",
)
def delete_plan_entitlement(
    plan_id: int,
    dimension: str,
    current_super_admin: SuperAdmin = Depends(get_current_super_admin),
    db: Session = Depends(get_db),
):
    SuperAdminService(db).delete_plan_entitlement(plan_id, dimension)
    return {"success": True, "message": f"Entitlement '{dimension}' deleted for plan {plan_id}"}



@router.get(
    "/upi-transactions",
    response_model=UPITransactionListResponse,
    summary="List SaaS UPI Transactions (Super Admin)",
)
def list_upi_transactions(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page (1-100)"),
    status: str | None = Query(None, description="Filter by status (pending, submitted, verified, rejected)"),
    reference: str | None = Query(None, description="Filter by reference"),
    utr: str | None = Query(None, description="Filter by UTR"),
    tenant_id: int | None = Query(None, description="Filter by tenant ID"),
    current_super_admin: SuperAdmin = Depends(get_current_super_admin),
    db: Session = Depends(get_db),
):
    """
    Paginated list of all SaaS UPI transactions across tenants.
    Super Admin authorization required.
    """
    return SaaSUPIService(db).list_transactions_admin(
        page=page,
        page_size=page_size,
        status=status,
        reference=reference,
        utr=utr,
        tenant_id=tenant_id,
    )


@router.get(
    "/upi-transactions/{reference}",
    response_model=UPIAdminTransactionResponse,
    summary="Get SaaS UPI Transaction Detail (Super Admin)",
)
def get_upi_transaction(
    reference: str,
    current_super_admin: SuperAdmin = Depends(get_current_super_admin),
    db: Session = Depends(get_db),
):
    """
    Retrieves detail of any SaaS UPI transaction by reference.
    Super Admin authorization required.
    """
    return SaaSUPIService(db).get_transaction_admin(reference=reference)


@router.post(
    "/upi-transactions/{reference}/verify",
    response_model=UPIAdminTransactionResponse,
    summary="Verify SaaS UPI Transaction (Super Admin)",
)
def verify_upi_transaction(
    reference: str,
    current_super_admin: SuperAdmin = Depends(get_current_super_admin),
    db: Session = Depends(get_db),
):
    """
    Atomically verifies a submitted UPI transaction:
    - Transitions transaction submitted -> verified
    - Transitions invoice unpaid -> paid
    - Transitions subscription trialing/past_due -> active
    - Synchronizes tenant projection
    Super Admin authorization required.
    """
    return SaaSUPIService(db).verify_transaction(
        reference=reference,
        super_admin_id=current_super_admin.id,
    )


@router.post(
    "/upi-transactions/{reference}/reject",
    response_model=UPIAdminTransactionResponse,
    summary="Reject SaaS UPI Transaction (Super Admin)",
)
def reject_upi_transaction(
    reference: str,
    data: UPIRejectRequest,
    current_super_admin: SuperAdmin = Depends(get_current_super_admin),
    db: Session = Depends(get_db),
):
    """
    Atomically rejects a submitted UPI transaction:
    - Transitions transaction submitted -> rejected with reason
    - Invoice remains unpaid; subscription unchanged
    - Record preserved for audit/history
    Super Admin authorization required.
    """
    return SaaSUPIService(db).reject_transaction(
        reference=reference,
        super_admin_id=current_super_admin.id,
        rejection_reason=data.rejection_reason,
    )


@router.get(
    "",
    response_model=SuperAdminListResponse,
    summary="List Super Admins",
)
def list_super_admins(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page (1-100)"),
    search: str | None = Query(None, description="Search by full name, email, or phone"),
    is_active: bool | None = Query(None, description="Filter by active status"),
    current_super_admin: SuperAdmin = Depends(
        get_current_super_admin
    ),
    db: Session = Depends(get_db),
):
    return SuperAdminService(db).list_super_admins(
        page=page,
        page_size=page_size,
        search=search,
        is_active=is_active,
    )


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


@router.post(
    "/subscription-lifecycle/process",
    response_model=SaaSSubscriptionLifecycleRunResponse,
    summary="Process SaaS Subscription Lifecycle",
)
def process_subscription_lifecycle(
    current_super_admin: SuperAdmin = Depends(get_current_super_admin),
    db: Session = Depends(get_db),
):
    """
    Executes a complete SaaS subscription lifecycle run across all tenants.
    Super Admin access only.
    """
    svc = SaaSSubscriptionLifecycleService(db)
    result = svc.run_all()
    db.commit()
    return result