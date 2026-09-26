from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import ForbiddenException
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.saas_entitlement import SaaSUsageResponse
from app.services.saas_entitlement_service import SaaSEntitlementService


router = APIRouter(
    prefix="/saas",
    tags=["SaaS Usage"],
)


@router.get(
    "/usage",
    response_model=SaaSUsageResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Tenant SaaS Usage",
)
def get_tenant_usage(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieves current resource usage and quota limits against plan entitlements
    for the authenticated tenant.
    Enforces strict tenant isolation: tenant identity is derived solely from current_user.tenant_id.
    Fails closed if subscription or entitlement configuration is missing or invalid.
    """
    if not current_user.tenant_id:
        raise ForbiddenException("User is not associated with any tenant")

    return SaaSEntitlementService(db).get_tenant_usage(current_user.tenant_id)
