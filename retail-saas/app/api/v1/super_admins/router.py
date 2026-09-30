from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import UnauthorizedException
from app.core.security import (
    blacklist_token,
    create_super_admin_access_token,
    create_super_admin_refresh_token,
    decode_token,
    get_current_super_admin,
    super_admin_security_scheme,
)
from app.models.super_admin import SuperAdmin
from app.schemas.super_admin import (
    SuperAdminChangePassword,
    SuperAdminCreate,
    SuperAdminDashboardResponse,
    SuperAdminInvoiceDetailResponse,
    SuperAdminInvoiceListResponse,
    SuperAdminListResponse,
    SuperAdminLogin,
    SuperAdminRefreshToken,
    SuperAdminResponse,
    SuperAdminStatusUpdate,
    SuperAdminStoreListResponse,
    SuperAdminStoreOwnerCreate,
    SuperAdminStoreOwnerUpdate,
    SuperAdminSubscriptionListResponse,
    SuperAdminTenantDeleteResponse,
    SuperAdminTenantDetailResponse,
    SuperAdminTenantListResponse,
    SuperAdminTenantResponse,
    SuperAdminTenantSubscriptionDetailResponse,
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
    PlanLimitsConfigureRequest,
    PlanLimitsConfigureResponse,
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
from app.core.redis_lock import RedisDistributedLock, SAAS_LIFECYCLE_LOCK_KEY
from app.services.saas_subscription_lifecycle_service import SaaSSubscriptionLifecycleService
from app.services.saas_upi_service import SaaSUPIService
from app.services.super_admin_service import SuperAdminService


router = APIRouter(
    prefix="/super-admins",
    tags=["Super Admins"],
)


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


@router.patch(
    "/me",
    response_model=SuperAdminResponse,
    summary="Update Current Super Admin Profile",
)
def update_current_super_admin_profile(
    data: SuperAdminUpdate,
    current_super_admin: SuperAdmin = Depends(
        get_current_super_admin
    ),
    db: Session = Depends(get_db),
):
    """
    Updates the logged-in Super Admin's own profile information (full_name, phone, email).
    """
    return SuperAdminService(db).update_super_admin(
        current_super_admin.id,
        data,
    )


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


@router.post(
    "/tenants",
    response_model=SuperAdminTenantDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Store Owner (Tenant)",
    description="Creates a new Store Owner (Tenant) account with initial store, admin credentials, and SaaS subscription.",
)
@router.post(
    "/store-owners",
    response_model=SuperAdminTenantDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Store Owner",
    description="Alias endpoint for creating a Store Owner (Tenant).",
    include_in_schema=False,
)
def create_tenant(
    data: SuperAdminStoreOwnerCreate,
    current_super_admin: SuperAdmin = Depends(
        get_current_super_admin
    ),
    db: Session = Depends(get_db),
):
    return SuperAdminService(db).create_tenant(data)


@router.get(
    "/tenants",
    response_model=SuperAdminTenantListResponse,
    summary="List Store Owners (Tenants)",
)
@router.get(
    "/store-owners",
    response_model=SuperAdminTenantListResponse,
    summary="List Store Owners",
    include_in_schema=False,
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
    summary="Get Store Owner (Tenant)",
)
@router.get(
    "/store-owners/{tenant_id}",
    response_model=SuperAdminTenantDetailResponse,
    summary="Get Store Owner",
    include_in_schema=False,
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
    "/tenants/{tenant_id}",
    response_model=SuperAdminTenantDetailResponse,
    summary="Update Store Owner (Tenant)",
    description="Updates Store Owner (Tenant) information such as store name, address, owner contact, and status.",
)
@router.patch(
    "/store-owners/{tenant_id}",
    response_model=SuperAdminTenantDetailResponse,
    summary="Update Store Owner",
    description="Alias endpoint for updating a Store Owner (Tenant).",
    include_in_schema=False,
)
def update_tenant(
    tenant_id: int,
    data: SuperAdminStoreOwnerUpdate,
    current_super_admin: SuperAdmin = Depends(
        get_current_super_admin
    ),
    db: Session = Depends(get_db),
):
    return SuperAdminService(db).update_tenant(
        tenant_id,
        data,
    )


@router.delete(
    "/tenants/{tenant_id}",
    response_model=SuperAdminTenantDeleteResponse,
    summary="Delete Store Owner (Tenant)",
    description="Deactivates a Store Owner (Tenant) account and disables all associated stores and user logins.",
)
@router.delete(
    "/store-owners/{tenant_id}",
    response_model=SuperAdminTenantDeleteResponse,
    summary="Delete Store Owner",
    description="Alias endpoint for deleting a Store Owner (Tenant).",
    include_in_schema=False,
)
def delete_tenant(
    tenant_id: int,
    current_super_admin: SuperAdmin = Depends(
        get_current_super_admin
    ),
    db: Session = Depends(get_db),
):
    return SuperAdminService(db).delete_tenant(
        tenant_id
    )


@router.patch(
    "/tenants/{tenant_id}/status",
    response_model=SuperAdminTenantResponse,
    summary="Activate or Deactivate Store Owner (Tenant)",
)
@router.patch(
    "/store-owners/{tenant_id}/status",
    response_model=SuperAdminTenantResponse,
    summary="Activate or Deactivate Store Owner",
    include_in_schema=False,
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
    summary="List Store Owner Users",
)
@router.get(
    "/store-owners/{tenant_id}/users",
    response_model=SuperAdminTenantUserListResponse,
    summary="List Store Owner Users",
    include_in_schema=False,
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
    summary="List Store Owner Stores",
)
@router.get(
    "/store-owners/{tenant_id}/stores",
    response_model=SuperAdminStoreListResponse,
    summary="List Store Owner Stores",
    include_in_schema=False,
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


@router.get(
    "/tenants/{tenant_id}/subscription",
    response_model=SuperAdminTenantSubscriptionDetailResponse,
    summary="Get Store Owner Subscription Detail",
)
@router.get(
    "/store-owners/{tenant_id}/subscription",
    response_model=SuperAdminTenantSubscriptionDetailResponse,
    summary="Get Store Owner Subscription Detail",
    include_in_schema=False,
)
def get_tenant_subscription(
    tenant_id: int,
    current_super_admin: SuperAdmin = Depends(get_current_super_admin),
    db: Session = Depends(get_db),
):
    """
    Retrieves deep subscription and entitlement detail for a specific Store Owner (tenant):
    - Authoritative current subscription and SaaS plan
    - Pending upgrade plan (if any)
    - Scheduled downgrade plan (if any)
    - Real-time resource usage vs limit summary (stores, users, products)
    - Recent SaaS invoices (latest 5)
    - Latest unpaid invoice
    Super Admin authorization required.
    """
    return SuperAdminService(db).get_tenant_subscription(tenant_id)


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


@router.put(
    "/saas-plans/{plan_id}/configure-limits",
    response_model=PlanLimitsConfigureResponse,
    summary="Configure All Plan Limits/Entitlements in a Single API",
)
def configure_plan_limits_by_path(
    plan_id: str,
    data: PlanLimitsConfigureRequest,
    current_super_admin: SuperAdmin = Depends(get_current_super_admin),
    db: Session = Depends(get_db),
):
    """
    Authoritative single API to configure all limits (users, stores, products, monthly_orders, etc.) for a plan in one request.
    Can set numbers or unlimited (is_unlimited=True / null).
    plan_id can be an ID (e.g. 1, 2, 3) or code (e.g. 'basic', 'pro', 'enterprise').
    """
    return SuperAdminService(db).configure_plan_limits(plan_id, data)


@router.post(
    "/saas-plans/{plan_id}/configure-limits",
    response_model=PlanLimitsConfigureResponse,
    summary="Configure Plan Limits (Deprecated POST alias)",
    deprecated=True,
    description="Deprecated: Use PUT /api/v1/super-admins/saas-plans/{plan_id}/configure-limits instead.",
)
def configure_plan_limits_by_path_post_deprecated(
    plan_id: str,
    data: PlanLimitsConfigureRequest,
    current_super_admin: SuperAdmin = Depends(get_current_super_admin),
    db: Session = Depends(get_db),
):
    return SuperAdminService(db).configure_plan_limits(plan_id, data)


@router.post(
    "/saas-plans/configure-limits",
    response_model=PlanLimitsConfigureResponse,
    summary="Configure All Plan Limits (Deprecated Body alias)",
    deprecated=True,
    description="Deprecated: Use PUT /api/v1/super-admins/saas-plans/{plan_id}/configure-limits instead.",
)
def configure_plan_limits_by_body(
    data: PlanLimitsConfigureRequest,
    current_super_admin: SuperAdmin = Depends(get_current_super_admin),
    db: Session = Depends(get_db),
):
    """
    Deprecated: select a plan (by plan_id or plan_code in request body) and configure all its limits.
    Use PUT /api/v1/super-admins/saas-plans/{plan_id}/configure-limits instead.
    """
    return SuperAdminService(db).configure_plan_limits(None, data)



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


# ==========================================
# P2 TASK 10: SAAS SUBSCRIPTION & BILLING OVERSIGHT
# ==========================================


@router.get(
    "/subscriptions",
    response_model=SuperAdminSubscriptionListResponse,
    summary="List SaaS Subscriptions (Super Admin)",
)
def list_subscriptions(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page (1-100)"),
    status: str | None = Query(None, description="Filter by status (trialing, active, past_due, cancelled, expired)"),
    plan_id: int | None = Query(None, ge=1, description="Filter by SaaS plan ID"),
    tenant_id: int | None = Query(None, ge=1, description="Filter by tenant ID"),
    has_pending_plan: bool | None = Query(None, description="Filter subscriptions with pending upgrade"),
    has_scheduled_plan: bool | None = Query(None, description="Filter subscriptions with scheduled downgrade"),
    current_super_admin: SuperAdmin = Depends(get_current_super_admin),
    db: Session = Depends(get_db),
):
    """
    Platform-wide paginated SaaS subscription oversight.
    Super Admin authorization required.
    """
    return SuperAdminService(db).list_subscriptions(
        page=page,
        page_size=page_size,
        status=status,
        plan_id=plan_id,
        tenant_id=tenant_id,
        has_pending_plan=has_pending_plan,
        has_scheduled_plan=has_scheduled_plan,
    )


@router.get(
    "/invoices",
    response_model=SuperAdminInvoiceListResponse,
    summary="List SaaS Invoices (Super Admin)",
)
def list_invoices(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page (1-100)"),
    status: str | None = Query(None, description="Filter by invoice status (unpaid, paid, cancelled)"),
    billing_reason: str | None = Query(None, description="Filter by billing reason (trial_conversion, subscription_cycle, plan_upgrade, manual_renewal)"),
    tenant_id: int | None = Query(None, ge=1, description="Filter by tenant ID"),
    search: str | None = Query(None, description="Search by invoice number"),
    current_super_admin: SuperAdmin = Depends(get_current_super_admin),
    db: Session = Depends(get_db),
):
    """
    Platform-wide paginated SaaS invoice oversight.
    Super Admin authorization required.
    """
    return SuperAdminService(db).list_invoices(
        page=page,
        page_size=page_size,
        status=status,
        billing_reason=billing_reason,
        tenant_id=tenant_id,
        search=search,
    )


@router.get(
    "/invoices/{invoice_id}",
    response_model=SuperAdminInvoiceDetailResponse,
    summary="Get SaaS Invoice Detail (Super Admin)",
)
def get_invoice(
    invoice_id: int,
    current_super_admin: SuperAdmin = Depends(get_current_super_admin),
    db: Session = Depends(get_db),
):
    """
    Retrieves deep detail for a specific SaaS invoice:
    - Authoritative invoice fields
    - Associated tenant and subscription
    - SaaS plan details
    - Complete history of associated UPI payment attempts
    Super Admin authorization required.
    """
    return SuperAdminService(db).get_invoice(invoice_id)


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


@router.post(
    "/change-password",
    summary="Change Super Admin Password",
)
def change_password(
    data: SuperAdminChangePassword,
    current_super_admin: SuperAdmin = Depends(
        get_current_super_admin
    ),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(
        super_admin_security_scheme
    ),
    db: Session = Depends(get_db),
):
    result = SuperAdminService(db).change_password(
        current_super_admin.id,
        data,
    )
    if credentials and credentials.credentials:
        blacklist_token(credentials.credentials)
    return result


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
    Protected by Redis distributed lock against concurrent automated or manual runs.
    """
    lock = RedisDistributedLock(SAAS_LIFECYCLE_LOCK_KEY, ttl_seconds=600)
    if not lock.acquire():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="SaaS subscription lifecycle execution is already in progress. Please retry shortly.",
        )
    try:
        svc = SaaSSubscriptionLifecycleService(db)
        result = svc.run_all()
        if not lock.is_valid() or not lock.renew():
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Distributed lock was lost during lifecycle execution: {lock.lock_lost_reason}",
            )
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise
    finally:
        lock.release()
