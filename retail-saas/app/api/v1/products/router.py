from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user, require_permission
from app.models.user import User
from app.schemas.product import CategoryCreate, CategoryResponse, ProductCreate, ProductResponse, ProductUpdate
from app.models.category import Category
from app.services.product_service import ProductService

router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=list[ProductResponse])
def list_products(
    page: int = 1,
    page_size: int = 20,
    user: User = Depends(require_permission("products:read")),
    db: Session = Depends(get_db),
):
    return ProductService(db).list_products(user.tenant_id, page, page_size)


@router.post("", response_model=ProductResponse, status_code=201)
def create_product(
    data: ProductCreate,
    user: User = Depends(require_permission("products:write")),
    db: Session = Depends(get_db),
):
    return ProductService(db).create_product(user.tenant_id, data)


@router.get("/barcode/{barcode}", response_model=ProductResponse)
def lookup_barcode(
    barcode: str,
    user: User = Depends(require_permission("products:read")),
    db: Session = Depends(get_db),
):
    return ProductService(db).get_by_barcode(user.tenant_id, barcode)


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
    return db.query(Category).filter(Category.tenant_id == user.tenant_id).all()
