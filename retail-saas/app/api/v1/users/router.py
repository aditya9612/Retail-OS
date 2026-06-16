from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user, require_permission
from app.models.user import User
from app.schemas.user import UserCreate, UserResponse, UserUpdate
from app.services.product_service import UserService

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserResponse)
def get_me(user: User = Depends(get_current_user)):
    return user


@router.get("", response_model=list[UserResponse])
def list_users(
    page: int = 1,
    page_size: int = 20,
    user: User = Depends(require_permission("users:read")),
    db: Session = Depends(get_db),
):
    return UserService(db).list_users(user.tenant_id, page, page_size)


@router.post("", response_model=UserResponse, status_code=201)
def create_user(
    data: UserCreate,
    user: User = Depends(require_permission("users:write")),
    db: Session = Depends(get_db),
):
    return UserService(db).create_user(user.tenant_id, data)


@router.get("/{user_id}", response_model=UserResponse)
def get_user(
    user_id: int,
    user: User = Depends(require_permission("users:read")),
    db: Session = Depends(get_db),
):
    return UserService(db).get_user(user.tenant_id, user_id)


@router.patch("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    data: UserUpdate,
    user: User = Depends(require_permission("users:write")),
    db: Session = Depends(get_db),
):
    return UserService(db).update_user(user.tenant_id, user_id, data)
