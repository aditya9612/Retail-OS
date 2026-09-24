from fastapi import APIRouter, Depends, Path, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_permission
from app.models.user import User
from app.schemas.category import (
    CategoryCreate,
    CategoryDeleteResponse,
    CategoryListResponse,
    CategoryResponse,
    CategoryUpdate,
)
from app.services.category_service import CategoryService


router = APIRouter(prefix="/categories", tags=["categories"])


@router.post(
    "",
    response_model=CategoryResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_category(
    data: CategoryCreate,
    user: User = Depends(require_permission("products:write")),
    db: Session = Depends(get_db),
):
    return CategoryService(db).create_category(
        tenant_id=user.tenant_id,
        data=data,
    )


@router.get(
    "",
    response_model=CategoryListResponse,
)
def list_categories(
    user: User = Depends(require_permission("products:read")),
    db: Session = Depends(get_db),
):
    categories = CategoryService(db).list_categories(user.tenant_id)
    return {
        "success": True,
        "message": (
            "Categories retrieved successfully"
            if categories
            else "No categories found"
        ),
        "data": categories,
    }


@router.get(
    "/{category_id}",
    response_model=CategoryResponse,
)
def get_category(
    category_id: int = Path(
        ...,
        gt=0,
        description="Category ID must be greater than 0",
    ),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("products:read")),
):
    return CategoryService(db).get_category(
        tenant_id=user.tenant_id,
        category_id=category_id,
    )


@router.put(
    "/{category_id}",
    response_model=CategoryResponse,
)
def update_category(
    data: CategoryUpdate,
    category_id: int = Path(
        ...,
        gt=0,
        description="Category ID must be greater than 0",
    ),
    user: User = Depends(require_permission("products:write")),
    db: Session = Depends(get_db),
):
    return CategoryService(db).update_category(
        tenant_id=user.tenant_id,
        category_id=category_id,
        data=data,
    )


@router.delete(
    "/{category_id}",
    response_model=CategoryDeleteResponse,
)
def delete_category(
    category_id: int = Path(
        ...,
        gt=0,
        description="Category ID must be greater than 0",
    ),
    user: User = Depends(require_permission("products:write")),
    db: Session = Depends(get_db),
):
    result = CategoryService(db).delete_category(
        tenant_id=user.tenant_id,
        category_id=category_id,
    )
    return {
        "success": True,
        "message": "Category deleted successfully",
        "data": result,
    }