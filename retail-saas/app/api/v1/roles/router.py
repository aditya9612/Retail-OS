from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import ForbiddenException
from app.core.security import require_permission
from app.models.user import User
from app.schemas.role import (
    PermissionGroup,
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


@router.get(
    "",
    response_model=list[RoleDetailResponse],
    summary="List Roles",
    description="Lists all roles for the authenticated tenant, with optional search and system/custom filtering.",
)
def list_roles(
    search: Optional[str] = Query(None, description="Search roles by name"),
    is_system: Optional[bool] = Query(None, description="Filter system roles (true) or custom roles (false)"),
    current_user: User = Depends(require_permission("users:read")),
    db: Session = Depends(get_db),
):
    return RoleService(db).list_roles(
        tenant_id=current_user.tenant_id,
        search=search,
        is_system=is_system,
    )


@router.get(
    "/permissions",
    response_model=list[PermissionGroup],
    summary="List Available Permissions",
    description="Returns all system permissions organized by module to help Store Owners configure custom roles.",
)
def list_permissions(
    current_user: User = Depends(require_permission("users:read")),
):
    return RoleService.get_available_permissions()


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
    description="Gets detailed information about a specific role, including assigned user count and permissions.",
)
def get_role(
    role_id: Annotated[int, Path(gt=0, le=999999, description="Role ID must be a positive integer up to 999999")],
    current_user: User = Depends(require_permission("users:read")),
    db: Session = Depends(get_db),
):
    return RoleService(db).get_role(tenant_id=current_user.tenant_id, role_id=role_id)


@router.get(
    "/{role_id}/users",
    response_model=RoleUsersResponse,
    summary="List Users Assigned to Role",
    description="Returns a paginated list of all active users currently assigned to this role, with optional store filtering.",
)
def list_role_users(
    role_id: Annotated[int, Path(gt=0, le=999999, description="Role ID must be a positive integer up to 999999")],
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    store_id: Optional[int] = Query(None, description="Filter users by assigned store ID"),
    current_user: User = Depends(require_permission("users:read")),
    db: Session = Depends(get_db),
):
    return RoleService(db).get_role_users(
        tenant_id=current_user.tenant_id,
        role_id=role_id,
        page=page,
        page_size=page_size,
        store_id=store_id,
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
    current_user: User = Depends(require_permission("users:write")),
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
    role_id: Annotated[int, Path(gt=0, le=999999, description="Source Role ID")],
    data: RoleReassignUsersRequest,
    current_user: User = Depends(require_permission("users:write")),
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
    role_id: Annotated[int, Path(gt=0, le=999999, description="Role ID to reset")],
    current_user: User = Depends(require_permission("users:write")),
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
    role_id: Annotated[int, Path(gt=0, le=999999, description="Role ID must be a positive integer up to 999999")],
    data: RoleUpdate,
    current_user: User = Depends(require_permission("users:write")),
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
    role_id: Annotated[int, Path(gt=0, le=999999, description="Role ID must be a positive integer up to 999999")],
    current_user: User = Depends(require_permission("users:write")),
    db: Session = Depends(get_db),
):
    if current_user.store_id is not None:
        raise ForbiddenException("Only Store Owner or Tenant Administrator can delete roles")

    return RoleService(db).delete_role(
        tenant_id=current_user.tenant_id,
        role_id=role_id,
    )
