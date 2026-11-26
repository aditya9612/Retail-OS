import re
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_permission
from app.models.user import User
from app.schemas.category import (
    PLACEHOLDER_VALUES,
    CategoryCreate,
    CategoryDeleteResponse,
    CategoryDetailResponse,
    CategoryExportFormat,
    CategoryExportIsActive,
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
    user: User = Depends(require_permission("products:create")),
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
    categories, total, counts = CategoryService(db).list_categories(
        tenant_id=user.tenant_id,
        search=search,
        is_active=is_active,
        root_only=root_only,
        parent_id=parent_id,
        page=page,
        page_size=page_size,
    )
    from app.utils.pagination import compute_total_pages
    total_pages = compute_total_pages(total, page_size) if page_size else (1 if total > 0 else 0)
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
        "total_pages": total_pages,
        "counts": counts,
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
    "/export",
    summary="Export categories report to Excel or CSV",
    description="Exports tenant categories with hierarchy, status, product counts, and timestamps.",
)
def export_categories(
    format: CategoryExportFormat = Query(..., description="Export format (required: 'excel', 'csv')"),
    is_active: CategoryExportIsActive = Query(..., description="Filter by active status: 'all', 'true', 'false'"),
    search: Optional[str] = Query(None, description="Optional search keyword in category name"),
    user: User = Depends(require_permission("products:read")),
    db: Session = Depends(get_db),
):
    cleaned_search = None
    if search is not None:
        s = search.strip()
        if not s or s.lower() in PLACEHOLDER_VALUES or (len(s) > 1 and len(set(s)) == 1 and s[0] in "-_.*!@#$%^&"):
            raise HTTPException(status_code=422, detail="Invalid search query parameter")
        if len(s) > 100:
            raise HTTPException(status_code=422, detail="Search query cannot exceed 100 characters")
        if not re.search(r"[a-zA-Z0-9]", s):
            raise HTTPException(status_code=422, detail="Search query must contain alphanumeric characters")
        cleaned_search = s

    is_active_val: Optional[bool] = None
    if is_active == CategoryExportIsActive.true or str(is_active).lower() == "true":
        is_active_val = True
    elif is_active == CategoryExportIsActive.false or str(is_active).lower() == "false":
        is_active_val = False

    buffer, media_type, filename = CategoryService(db).export_categories(
        tenant_id=user.tenant_id,
        is_active=is_active_val,
        search=cleaned_search,
        format=format.value,
    )
    return StreamingResponse(
        buffer,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


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
    user: User = Depends(require_permission("products:update")),
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
    user: User = Depends(require_permission("products:update")),
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
    user: User = Depends(require_permission("products:update")),
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
    user: User = Depends(require_permission("products:delete")),
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
