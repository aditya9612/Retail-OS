
from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import (
    require_operational_write,
    require_permission,
)
from app.models.user import User
from app.schemas.product_variant import (
    ProductVariantCreate,
    ProductVariantDirectCreate,
    ProductVariantListResponse,
    ProductVariantResponse,
    ProductVariantUpdate,
)
from app.services.product_variant_service import ProductVariantService


router = APIRouter(tags=["product-variants"])


@router.post(
    "/variants",
    response_model=ProductVariantResponse,
    status_code=201,
    dependencies=[Depends(require_operational_write)],
)
def create_variant(
    data: ProductVariantDirectCreate,
    user: User = Depends(require_permission("products:write")),
    db: Session = Depends(get_db),
):
    return ProductVariantService(db).create_variant(
        tenant_id=user.tenant_id,
        product_id=data.product_id,
        data=data,
    )


@router.get(
    "/variants/{variant_id}",
    response_model=ProductVariantResponse,
)
def get_variant(
    variant_id: int = Path(
        ...,
        gt=0,
        description="Variant ID",
    ),
    user: User = Depends(require_permission("products:read")),
    db: Session = Depends(get_db),
):
    return ProductVariantService(db).get_variant(
        tenant_id=user.tenant_id,
        variant_id=variant_id,
    )


@router.put(
    "/variants/{variant_id}",
    response_model=ProductVariantResponse,
    dependencies=[Depends(require_operational_write)],
)
def update_variant(
    data: ProductVariantUpdate,
    variant_id: int = Path(
        ...,
        gt=0,
        description="Variant ID",
    ),
    user: User = Depends(require_permission("products:write")),
    db: Session = Depends(get_db),
):
    return ProductVariantService(db).update_variant(
        tenant_id=user.tenant_id,
        variant_id=variant_id,
        data=data,
    )


@router.patch(
    "/variants/{variant_id}",
    response_model=ProductVariantResponse,
    dependencies=[Depends(require_operational_write)],
)
def patch_variant(
    data: ProductVariantUpdate,
    variant_id: int = Path(
        ...,
        gt=0,
        description="Variant ID",
    ),
    user: User = Depends(require_permission("products:write")),
    db: Session = Depends(get_db),
):
    return ProductVariantService(db).update_variant(
        tenant_id=user.tenant_id,
        variant_id=variant_id,
        data=data,
    )


@router.delete(
    "/variants/{variant_id}",
    response_model=ProductVariantResponse,
    dependencies=[Depends(require_operational_write)],
)
def delete_variant(
    variant_id: int = Path(
        ...,
        gt=0,
        description="Variant ID",
    ),
    user: User = Depends(require_permission("products:write")),
    db: Session = Depends(get_db),
):
    return ProductVariantService(db).delete_variant(
        tenant_id=user.tenant_id,
        variant_id=variant_id,
    )


@router.post(
    "/products/{product_id}/variants",
    response_model=ProductVariantResponse,
    status_code=201,
    dependencies=[Depends(require_operational_write)],
)
def create_product_variant(
    data: ProductVariantCreate,
    product_id: int = Path(
        ...,
        gt=0,
        description="Parent product ID",
    ),
    user: User = Depends(require_permission("products:write")),
    db: Session = Depends(get_db),
):
    return ProductVariantService(db).create_variant(
        tenant_id=user.tenant_id,
        product_id=product_id,
        data=data,
    )


@router.get(
    "/products/{product_id}/variants",
    response_model=ProductVariantListResponse,
)
def list_product_variants(
    product_id: int = Path(
        ...,
        gt=0,
        description="Parent product ID",
    ),
    page: int = Query(1, gt=0),
    page_size: int = Query(20, gt=0, le=100),
    include_inactive: bool = Query(False),
    user: User = Depends(require_permission("products:read")),
    db: Session = Depends(get_db),
):
    return ProductVariantService(db).list_variants(
        tenant_id=user.tenant_id,
        product_id=product_id,
        page=page,
        page_size=page_size,
        include_inactive=include_inactive,
    )


@router.get(
    "/products/{product_id}/variants/{variant_id}",
    response_model=ProductVariantResponse,
)
def get_product_variant(
    product_id: int = Path(
        ...,
        gt=0,
        description="Parent product ID",
    ),
    variant_id: int = Path(
        ...,
        gt=0,
        description="Variant ID",
    ),
    user: User = Depends(require_permission("products:read")),
    db: Session = Depends(get_db),
):
    return ProductVariantService(db).get_variant(
        tenant_id=user.tenant_id,
        variant_id=variant_id,
        product_id=product_id,
    )
