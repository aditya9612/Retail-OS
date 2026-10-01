from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import ForbiddenException
from app.core.security import require_permission
from app.models.user import User
from app.schemas.user import (
    MyProfileUpdate,
    RoleResponse,
    UserCreate,
    UserResponse,
    UserUpdate,
    AssignStoreRequest,
    AssignStoreResponse,
)
from app.services.user_service import UserService


router = APIRouter(
    prefix="/users",
    tags=["Users"],
)


@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_user(
    data: UserCreate,
    current_user: User = Depends(require_permission("users:write")),
    db: Session = Depends(get_db),
):
    # Store-level user (manager/staff) may only create users for their assigned store
    if current_user.store_id is not None:
        if data.store_id is not None and data.store_id != current_user.store_id:
            raise ForbiddenException("You can only create users for your assigned store")
        if data.store_id is None:
            data.store_id = current_user.store_id

    return UserService(db).create_user(
        current_user.tenant_id,
        data,
    )


@router.get(
    "",
    response_model=list[UserResponse],
)
def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    include_inactive: bool = Query(False),
    store_id: Optional[int] = Query(None, description="Filter users by store ID"),
    current_user: User = Depends(require_permission("users:read")),
    db: Session = Depends(get_db),
):
    effective_store_id = store_id
    if current_user.store_id is not None:
        if store_id is not None and store_id != current_user.store_id:
            raise ForbiddenException("Access denied to users of this store")
        effective_store_id = current_user.store_id

    skip = (page - 1) * page_size

    return UserService(db).list_users(
        tenant_id=current_user.tenant_id,
        skip=skip,
        limit=page_size,
        include_inactive=include_inactive,
        store_id=effective_store_id,
    )


@router.get(
    "/roles",
    response_model=list[RoleResponse],
)
def list_roles(
    current_user: User = Depends(require_permission("users:write")),
    db: Session = Depends(get_db),
):
    return UserService(db).list_roles(
        tenant_id=current_user.tenant_id,
    )


@router.get(
    "/me",
    response_model=UserResponse,
)
def get_my_profile(
    current_user: User = Depends(require_permission("users:read")),
    db: Session = Depends(get_db),
):
    return UserService(db).get_user(
        current_user.tenant_id,
        current_user.id,
    )


@router.put(
    "/me",
    response_model=UserResponse,
)
@router.patch(
    "/me",
    response_model=UserResponse,
    include_in_schema=False,
)
def update_my_profile(
    data: MyProfileUpdate,
    current_user: User = Depends(require_permission("users:read")),
    db: Session = Depends(get_db),
):
    return UserService(db).update_my_profile(
        current_user.tenant_id,
        current_user.id,
        data,
    )


@router.get(
    "/{user_id}",
    response_model=UserResponse,
)
def get_user(
    user_id: int,
    current_user: User = Depends(require_permission("users:read")),
    db: Session = Depends(get_db),
):
    user = UserService(db).get_user(
        current_user.tenant_id,
        user_id,
    )
    if current_user.store_id is not None and user.store_id != current_user.store_id:
        raise ForbiddenException("Access denied to user of another store")
    return user


@router.put(
    "/{user_id}",
    response_model=UserResponse,
)
@router.patch(
    "/{user_id}",
    response_model=UserResponse,
    include_in_schema=False,
)
def update_user(
    user_id: int,
    data: UserUpdate,
    current_user: User = Depends(require_permission("users:write")),
    db: Session = Depends(get_db),
):
    target_user = UserService(db).get_user(
        current_user.tenant_id,
        user_id,
    )
    if current_user.store_id is not None:
        if target_user.store_id != current_user.store_id:
            raise ForbiddenException("Access denied to user of another store")
        if data.store_id is not None and data.store_id != current_user.store_id:
            raise ForbiddenException("Cannot reassign user to another store")
    return UserService(db).update_user(
        current_user.tenant_id,
        user_id,
        data,
    )


@router.patch(
    "/{user_id}/activate",
    response_model=UserResponse,
)
def activate_user(
    user_id: int,
    current_user: User = Depends(require_permission("users:write")),
    db: Session = Depends(get_db),
):
    target_user = UserService(db).get_user(
        current_user.tenant_id,
        user_id,
    )
    if current_user.store_id is not None and target_user.store_id != current_user.store_id:
        raise ForbiddenException("Access denied to user of another store")
    return UserService(db).activate_user(
        current_user.tenant_id,
        user_id,
    )


@router.patch(
    "/{user_id}/deactivate",
    response_model=UserResponse,
)
def deactivate_user(
    user_id: int,
    current_user: User = Depends(require_permission("users:write")),
    db: Session = Depends(get_db),
):
    target_user = UserService(db).get_user(
        current_user.tenant_id,
        user_id,
    )
    if current_user.store_id is not None and target_user.store_id != current_user.store_id:
        raise ForbiddenException("Access denied to user of another store")
    return UserService(db).deactivate_user(
        current_user.tenant_id,
        user_id,
        current_user.id,
    )


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_user(
    user_id: int,
    current_user: User = Depends(require_permission("users:write")),
    db: Session = Depends(get_db),
):
    target_user = UserService(db).get_user(
        current_user.tenant_id,
        user_id,
    )
    if current_user.store_id is not None and target_user.store_id != current_user.store_id:
        raise ForbiddenException("Access denied to user of another store")
    UserService(db).delete_user(
        current_user.tenant_id,
        user_id,
        current_user.id,
    )


@router.post(
    "/{user_id}/assign-store",
    response_model=AssignStoreResponse,
    summary="Assign Store to User",
    description="Assigns or moves a user to a specific store within the tenant organization.",
)
def assign_store(
    user_id: int,
    data: AssignStoreRequest,
    current_user: User = Depends(require_permission("users:write")),
    db: Session = Depends(get_db),
):
    if current_user.store_id is not None:
        raise ForbiddenException("Only Store Owner or Tenant Admin can assign users to stores")

    user = UserService(db).assign_store(
        tenant_id=current_user.tenant_id,
        user_id=user_id,
        store_id=data.store_id,
    )

    store_name = user.store.name if getattr(user, "store", None) else None
    role_name = user.role.name if getattr(user, "role", None) else None

    return AssignStoreResponse(
        message="Store assigned successfully",
        user_id=user.id,
        store_id=user.store_id,
        store_name=store_name,
        role=role_name,
    )
