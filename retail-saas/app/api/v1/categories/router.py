from typing import Optional
from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_permission
from app.models.user import User
from app.schemas.category import (
    CategoryCreate,
    CategoryDeleteResponse,
    CategoryDetailResponse,
    CategoryListResponse,
    CategoryProductsResponse,
    CategoryResponse,
    CategorySubcategoryListResponse,
    CategoryTreeResponse,
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
    search: Optional[str] = Query(None, description="Search category name"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    root_only: bool = Query(False, description="Filter root categories only"),
    parent_id: Optional[int] = Query(None, gt=0, description="Filter by parent category ID"),
    page: Optional[int] = Query(None, ge=1, description="Page number"),
    page_size: Optional[int] = Query(None, ge=1, le=100, description="Items per page"),
    user: User = Depends(require_permission("products:read")),
    db: Session = Depends(get_db),
):
    categories, total = CategoryService(db).list_categories(
        tenant_id=user.tenant_id,
        search=search,
        is_active=is_active,
        root_only=root_only,
        parent_id=parent_id,
        page=page,
        page_size=page_size,
    )
    return {
        "success": True,
        "message": (
            "Categories retrieved successfully"
            if categories
            else "No categories found"
        ),
        "total": total,
        "page": page,
        "page_size": page_size,
        "data": categories,
    }


@router.get(
    "/tree",
    response_model=CategoryTreeResponse,
)
def get_category_tree(
    user: User = Depends(require_permission("products:read")),
    db: Session = Depends(get_db),
):
    tree = CategoryService(db).get_category_tree(user.tenant_id)
    return {
        "success": True,
        "message": (
            "Category tree retrieved successfully"
            if tree
            else "No categories found"
        ),
        "data": tree,
    }


@router.get(
    "/{category_id}",
    response_model=CategoryDetailResponse,
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


@router.get(
    "/{category_id}/subcategories",
    response_model=CategorySubcategoryListResponse,
)
def get_subcategories(
    category_id: int = Path(
        ...,
        gt=0,
        description="Category ID must be greater than 0",
    ),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("products:read")),
):
    subcats = CategoryService(db).get_subcategories(
        tenant_id=user.tenant_id,
        category_id=category_id,
    )
    return {
        "success": True,
        "message": (
            "Subcategories retrieved successfully"
            if subcats
            else "No subcategories found"
        ),
        "data": subcats,
    }


@router.get(
    "/{category_id}/products",
    response_model=CategoryProductsResponse,
)
def get_category_products(
    category_id: int = Path(
        ...,
        gt=0,
        description="Category ID must be greater than 0",
    ),
    search: Optional[str] = Query(None, description="Search product name or SKU"),
    is_active: Optional[bool] = Query(None, description="Filter product by active status"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("products:read")),
):
    return CategoryService(db).get_category_products(
        tenant_id=user.tenant_id,
        category_id=category_id,
        search=search,
        is_active=is_active,
        page=page,
        page_size=page_size,
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


@router.patch(
    "/{category_id}",
    response_model=CategoryResponse,
)
def patch_category(
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


@router.patch(
    "/{category_id}/activate",
    response_model=CategoryResponse,
)
def activate_category(
    category_id: int = Path(
        ...,
        gt=0,
        description="Category ID must be greater than 0",
    ),
    user: User = Depends(require_permission("products:write")),
    db: Session = Depends(get_db),
):
    return CategoryService(db).set_category_active(
        tenant_id=user.tenant_id,
        category_id=category_id,
        is_active=True,
    )


@router.patch(
    "/{category_id}/deactivate",
    response_model=CategoryResponse,
)
def deactivate_category(
    category_id: int = Path(
        ...,
        gt=0,
        description="Category ID must be greater than 0",
    ),
    user: User = Depends(require_permission("products:write")),
    db: Session = Depends(get_db),
):
    return CategoryService(db).set_category_active(
        tenant_id=user.tenant_id,
        category_id=category_id,
        is_active=False,
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