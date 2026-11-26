from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import AppException, ForbiddenException
from app.core.security import require_permission
from app.models.user import User
from app.schemas.common import ListWithCountsResponse
from app.schemas.role import (
    PermissionGroup,
    RoleCounts,
    RoleCreate,
    RoleDeleteResponse,
    RoleDetailResponse,
    RoleMatrixResponse,
    RoleReassignUsersRequest,
    RoleReassignUsersResponse,
    RoleUpdate,
    RoleUsersResponse,
)
from app.services.role_service import RoleService

router = APIRouter(
    prefix="/roles",
    tags=["Roles"],
)


def resolve_role_param(
    role_id: Annotated[
        str,
        Path(description="Role ID (positive integer up to 999999) or Role Name (e.g. 'cashier')"),
    ],
) -> str:
    cleaned = role_id.strip()
    try:
        val = int(cleaned)
        if val <= 0 or val > 999999:
            raise AppException(
                "Role ID must be a positive integer up to 999999",
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
    except ValueError:
        pass
    return cleaned


@router.get(
    "",
    response_model=ListWithCountsResponse[RoleDetailResponse, RoleCounts],
    summary="List Roles",
    description="Lists all roles for the authenticated tenant, with optional search, exact name match, and system/custom filtering.",
)
def list_roles(
    search: Optional[str] = Query(None, description="Search roles by name or role ID"),
    name: Optional[str] = Query(None, description="Exact match filter by role name (e.g. 'cashier')"),
    role_id: Optional[int] = Query(None, description="Direct filter by numeric Role ID"),
    is_system: Optional[bool] = Query(None, description="Filter system roles (true) or custom roles (false)"),
    skip: int = Query(0, ge=0, description="Offset for pagination"),
    limit: int = Query(100, ge=1, le=100, description="Limit items returned"),
    current_user: User = Depends(require_permission("users:read")),
    db: Session = Depends(get_db),
):
    return RoleService(db).list_roles_with_counts(
        tenant_id=current_user.tenant_id,
        search=search,
        name=name,
        role_id=role_id,
        is_system=is_system,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/permissions",
    response_model=list[PermissionGroup] | dict[str, list[str]],
    summary="List Available Permissions",
    description="Returns all system permissions organized by module. Defaults to full metadata group list ('detailed'), or clean {module: [codes]} map ('simple').",
)
def list_permissions(
    format: Optional[str] = Query(
        default="detailed",
        pattern="^(detailed|simple)$",
        description="Format: 'detailed' (default) returns full metadata group list, 'simple' returns clean {module: [permissions]} dictionary",
    ),
    module: Optional[str] = Query(None, description="Filter permissions for a specific module (e.g. 'billing', 'inventory')"),
    current_user: User = Depends(require_permission("users:read")),
):
    if format == "simple":
        return RoleService.get_simple_permissions_map(module=module)
    return RoleService.get_available_permissions(module=module)


@router.get(
    "/matrix",
    response_model=RoleMatrixResponse,
    summary="Get RBAC Permissions Matrix",
    description="Returns a structured grid matrix of all roles and permissions, designed for rendering access-control table views in frontend dashboards.",
)
def get_roles_matrix(
    current_user: User = Depends(require_permission("users:read")),
    db: Session = Depends(get_db),
):
    return RoleService(db).get_roles_matrix(tenant_id=current_user.tenant_id)


@router.get(
    "/{role_id}",
    response_model=RoleDetailResponse,
    summary="Get Role Details",
    description="Gets detailed information about a specific role by Role ID or Role Name, including assigned user count and permissions.",
)
def get_role(
    role_id: Annotated[str, Depends(resolve_role_param)],
    current_user: User = Depends(require_permission("users:read")),
    db: Session = Depends(get_db),
):
    return RoleService(db).get_role(tenant_id=current_user.tenant_id, role_id=role_id)


@router.get(
    "/{role_id}/users",
    response_model=RoleUsersResponse,
    summary="List Users Assigned to Role",
    description="Returns a paginated list of all active users currently assigned to this role, with optional store and status filtering.",
)
def list_role_users(
    role_id: Annotated[str, Depends(resolve_role_param)],
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    store_id: Optional[str] = Query(None, description="Filter users by assigned store ID (e.g. 1), or 'null'/'unassigned' for users without a store"),
    is_active: Optional[bool] = Query(None, description="Filter active (true) or inactive (false) users"),
    current_user: User = Depends(require_permission("users:read")),
    db: Session = Depends(get_db),
):
    return RoleService(db).get_role_users(
        tenant_id=current_user.tenant_id,
        role_id=role_id,
        page=page,
        page_size=page_size,
        store_id=store_id,
        is_active=is_active,
        current_user_store_id=current_user.store_id,
    )


@router.post(
    "",
    response_model=RoleDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Custom Role",
    description="Store Owner creates a new role with specific permissions for their organization.",
)
def create_role(
    data: RoleCreate,
    current_user: User = Depends(require_permission("users:create")),
    db: Session = Depends(get_db),
):
    if current_user.store_id is not None:
        raise ForbiddenException("Only Store Owner or Tenant Administrator can create new roles")

    return RoleService(db).create_role(tenant_id=current_user.tenant_id, data=data)


@router.post(
    "/{role_id}/reassign-users",
    response_model=RoleReassignUsersResponse,
    summary="Bulk Reassign Users",
    description="Reassigns all active users from this role to a target role in one atomic operation. Useful before deleting or deprecating a role.",
)
def reassign_role_users(
    role_id: Annotated[str, Depends(resolve_role_param)],
    data: RoleReassignUsersRequest,
    current_user: User = Depends(require_permission("users:create")),
    db: Session = Depends(get_db),
):
    if current_user.store_id is not None:
        raise ForbiddenException("Only Store Owner or Tenant Administrator can reassign roles in bulk")

    return RoleService(db).reassign_users(
        tenant_id=current_user.tenant_id,
        role_id=role_id,
        target_role_id=data.target_role_id,
    )


@router.post(
    "/{role_id}/reset-default",
    response_model=RoleDetailResponse,
    summary="Reset Role to System Defaults",
    description="Resets an official system role (manager, cashier, accountant, etc.) back to factory default permissions.",
)
def reset_role_to_default(
    role_id: Annotated[str, Depends(resolve_role_param)],
    current_user: User = Depends(require_permission("users:create")),
    db: Session = Depends(get_db),
):
    if current_user.store_id is not None:
        raise ForbiddenException("Only Store Owner or Tenant Administrator can reset roles")

    return RoleService(db).reset_default_role(
        tenant_id=current_user.tenant_id,
        role_id=role_id,
    )


@router.patch(
    "/{role_id}",
    response_model=RoleDetailResponse,
    summary="Update Role",
    description="Store Owner updates the name or permissions of an existing role.",
)
@router.put(
    "/{role_id}",
    response_model=RoleDetailResponse,
    include_in_schema=False,
)
def update_role(
    role_id: Annotated[str, Depends(resolve_role_param)],
    data: RoleUpdate,
    current_user: User = Depends(require_permission("users:update")),
    db: Session = Depends(get_db),
):
    if current_user.store_id is not None:
        raise ForbiddenException("Only Store Owner or Tenant Administrator can update roles")

    return RoleService(db).update_role(
        tenant_id=current_user.tenant_id,
        role_id=role_id,
        data=data,
    )


@router.delete(
    "/{role_id}",
    response_model=RoleDeleteResponse,
    summary="Delete Role",
    description="Store Owner deletes a custom role. System/core roles and roles with active assigned users cannot be deleted.",
)
def delete_role(
    role_id: Annotated[str, Depends(resolve_role_param)],
    current_user: User = Depends(require_permission("users:delete")),
    db: Session = Depends(get_db),
):
    if current_user.store_id is not None:
        raise ForbiddenException("Only Store Owner or Tenant Administrator can delete roles")

    return RoleService(db).delete_role(
        tenant_id=current_user.tenant_id,
        role_id=role_id,
    )
