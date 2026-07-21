from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_permission
from app.models.category import Category
from app.models.user import User
from app.schemas.product import (
    CategoryCreate,
    CategoryResponse,
    ProductCreate,
    ProductResponse,
    ProductUpdate,
)
from app.services.product_service import ProductService

router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=list[ProductResponse])
def list_products(
    page: int = Query(default=1, gt=0),
    page_size: int = Query(default=20, gt=0, le=100),
    include_inactive: bool = Query(default=False),
    user: User = Depends(require_permission("products:read")),
    db: Session = Depends(get_db),
):
    return ProductService(db).list_products(
        user.tenant_id, page, page_size, include_inactive
    )


@router.get("/search", response_model=list[ProductResponse])
def search_products(
    q: str = Query(min_length=1, description="Search by name, SKU or barcode"),
    page: int = Query(default=1, gt=0),
    page_size: int = Query(default=20, gt=0, le=100),
    user: User = Depends(require_permission("products:read")),
    db: Session = Depends(get_db),
):
    return ProductService(db).search_products(user.tenant_id, q, page, page_size)


@router.get("/low-stock", response_model=list[ProductResponse])
def list_low_stock(
    store_id: int = Query(..., gt=0),
    threshold: int = Query(default=10, gt=0),
    user: User = Depends(require_permission("products:read")),
    db: Session = Depends(get_db),
):
    return ProductService(db).list_low_stock(user.tenant_id, store_id, threshold)


@router.get("/expiring-soon", response_model=list[ProductResponse])
def list_expiring_soon(
    store_id: int = Query(..., gt=0),
    days: int = Query(default=30, gt=0, le=365),
    user: User = Depends(require_permission("products:read")),
    db: Session = Depends(get_db),
):
    return ProductService(db).list_expiring_soon(user.tenant_id, store_id, days)


@router.get("/barcode/{barcode}", response_model=ProductResponse)
def lookup_barcode(
    barcode: str,
    user: User = Depends(require_permission("products:read")),
    db: Session = Depends(get_db),
):
    return ProductService(db).get_by_barcode(user.tenant_id, barcode)


@router.post("", response_model=ProductResponse, status_code=201)
def create_product(
    data: ProductCreate,
    user: User = Depends(require_permission("products:write")),
    db: Session = Depends(get_db),
):
    return ProductService(db).create_product(user.tenant_id, data)


@router.get("/{product_id}", response_model=ProductResponse)
def get_product(
    product_id: int,
    user: User = Depends(require_permission("products:read")),
    db: Session = Depends(get_db),
):
    return ProductService(db).get_product(user.tenant_id, product_id)


@router.patch("/{product_id}", response_model=ProductResponse)
def update_product(
    product_id: int,
    data: ProductUpdate,
    user: User = Depends(require_permission("products:write")),
    db: Session = Depends(get_db),
):
    return ProductService(db).update_product(user.tenant_id, product_id, data)


@router.patch("/{product_id}/toggle-status", response_model=ProductResponse)
def toggle_product_status(
    product_id: int,
    user: User = Depends(require_permission("products:write")),
    db: Session = Depends(get_db),
):
    return ProductService(db).toggle_status(user.tenant_id, product_id)


@router.get("/{product_id}/barcode")
def barcode_image(
    product_id: int,
    mode: str = Query(default="download", description="download or preview"),
    user: User = Depends(require_permission("products:read")),
    db: Session = Depends(get_db),
):
   
    product = ProductService(db).get_product(user.tenant_id, product_id)
    image_bytes = ProductService(db).get_barcode_image(user.tenant_id, product_id)
    disposition = "inline" if mode == "preview" else "attachment"
    return Response(
        content=image_bytes,
        media_type="image/png",
        headers={
            "Content-Disposition": f"{disposition}; filename=barcode-{product.barcode}.png"
        }
    )


@router.delete("/{product_id}", status_code=204)
def delete_product(
    product_id: int,
    user: User = Depends(require_permission("products:write")),
    db: Session = Depends(get_db),
):
    ProductService(db).delete_product(user.tenant_id, product_id)


@router.post("/categories", response_model=CategoryResponse, status_code=201)
def create_category(
    data: CategoryCreate,
    user: User = Depends(require_permission("products:write")),
    db: Session = Depends(get_db),
):
    category = Category(tenant_id=user.tenant_id, **data.model_dump())
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


@router.get("/categories/list", response_model=list[CategoryResponse])
def list_categories(
    user: User = Depends(require_permission("products:read")),
    db: Session = Depends(get_db),
):
    return db.query(Category).filter(
        Category.tenant_id == user.tenant_id
    ).all()