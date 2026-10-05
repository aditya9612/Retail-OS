from typing import Annotated

from fastapi import APIRouter, Depends, Path, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import ForbiddenException
from app.core.security import require_permission
from app.models.user import User
from app.schemas.role import (
    PermissionGroup,
    RoleCreate,
    RoleDetailResponse,
    RoleUpdate,
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
    description="Lists all roles for the authenticated tenant, including user count per role.",
)
def list_roles(
    current_user: User = Depends(require_permission("users:read")),
    db: Session = Depends(get_db),
):
    return RoleService(db).list_roles(tenant_id=current_user.tenant_id)


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
    "/{role_id}",
    response_model=RoleDetailResponse,
    summary="Get Role Details",
    description="Gets detailed information about a specific role, including assigned user count and permissions.",
)
def get_role(
    role_id: Annotated[int, Path(gt=0, description="Role ID must be a positive integer")],
    current_user: User = Depends(require_permission("users:read")),
    db: Session = Depends(get_db),
):
    return RoleService(db).get_role(tenant_id=current_user.tenant_id, role_id=role_id)


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
    role_id: Annotated[int, Path(gt=0, description="Role ID must be a positive integer")],
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
    summary="Delete Role",
    description="Store Owner deletes a custom role. System/core roles and roles with active assigned users cannot be deleted.",
)
def delete_role(
    role_id: Annotated[int, Path(gt=0, description="Role ID must be a positive integer")],
    current_user: User = Depends(require_permission("users:write")),
    db: Session = Depends(get_db),
):
    if current_user.store_id is not None:
        raise ForbiddenException("Only Store Owner or Tenant Administrator can delete roles")

    return RoleService(db).delete_role(
        tenant_id=current_user.tenant_id,
        role_id=role_id,
    )
