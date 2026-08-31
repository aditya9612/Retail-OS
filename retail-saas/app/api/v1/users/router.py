from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_permission
from app.models.user import User
from app.schemas.user import UserCreate, UserResponse, UserUpdate
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
    current_user: User = Depends(require_permission("users:read")),
    db: Session = Depends(get_db),
):
    skip = (page - 1) * page_size

    return UserService(db).list_users(
        tenant_id=current_user.tenant_id,
        skip=skip,
        limit=page_size,
        include_inactive=include_inactive,
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
def update_my_profile(
    data: UserUpdate,
    current_user: User = Depends(require_permission("users:read")),
    db: Session = Depends(get_db),
):
    return UserService(db).update_user(
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
    return UserService(db).get_user(
        current_user.tenant_id,
        user_id,
    )


@router.put(
    "/{user_id}",
    response_model=UserResponse,
)
def update_user(
    user_id: int,
    data: UserUpdate,
    current_user: User = Depends(require_permission("users:write")),
    db: Session = Depends(get_db),
):
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
    UserService(db).delete_user(
        current_user.tenant_id,
        user_id,
        current_user.id,
    )