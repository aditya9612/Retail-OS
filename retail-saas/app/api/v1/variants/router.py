from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_operational_write, require_permission
from app.models.user import User
from app.schemas.product_variant import (
    ProductVariantCreate,
    ProductVariantDirectCreate,
    ProductVariantResponse,
    ProductVariantUpdate,
)
from app.services.product_variant_service import ProductVariantService

router = APIRouter(
    prefix="/variants",
    tags=["product-variants"],
)


@router.post(
    "",
    response_model=ProductVariantResponse,
    status_code=201,
    dependencies=[Depends(require_operational_write)],
)
def create_variant(
    data: ProductVariantDirectCreate,
    user: User = Depends(require_permission("products:write")),
    db: Session = Depends(get_db),
):
    create_dto = ProductVariantCreate(
        variant_name=data.variant_name,
        sku=data.sku,
        barcode=data.barcode,
        size=data.size,
        color=data.color,
        attributes=data.attributes,
        selling_price=data.selling_price,
        cost_price=data.cost_price,
        is_active=data.is_active,
    )
    return ProductVariantService(db).create_variant(
        tenant_id=user.tenant_id,
        product_id=data.product_id,
        data=create_dto,
    )


@router.get(
    "/{variant_id}",
    response_model=ProductVariantResponse,
)
def get_variant(
    variant_id: int = Path(..., gt=0, description="Variant ID"),
    user: User = Depends(require_permission("products:read")),
    db: Session = Depends(get_db),
):
    return ProductVariantService(db).get_variant(
        tenant_id=user.tenant_id,
        variant_id=variant_id,
    )


@router.put(
    "/{variant_id}",
    response_model=ProductVariantResponse,
    dependencies=[Depends(require_operational_write)],
)
def update_variant(
    data: ProductVariantUpdate,
    variant_id: int = Path(..., gt=0, description="Variant ID"),
    user: User = Depends(require_permission("products:write")),
    db: Session = Depends(get_db),
):
    return ProductVariantService(db).update_variant(
        tenant_id=user.tenant_id,
        variant_id=variant_id,
        data=data,
    )


@router.patch(
    "/{variant_id}",
    response_model=ProductVariantResponse,
    dependencies=[Depends(require_operational_write)],
)
def patch_variant(
    data: ProductVariantUpdate,
    variant_id: int = Path(..., gt=0, description="Variant ID"),
    user: User = Depends(require_permission("products:write")),
    db: Session = Depends(get_db),
):
    return ProductVariantService(db).update_variant(
        tenant_id=user.tenant_id,
        variant_id=variant_id,
        data=data,
    )


@router.delete(
    "/{variant_id}",
    response_model=ProductVariantResponse,
    dependencies=[Depends(require_operational_write)],
)
def delete_variant(
    variant_id: int = Path(..., gt=0, description="Variant ID"),
    user: User = Depends(require_permission("products:write")),
    db: Session = Depends(get_db),
):
    return ProductVariantService(db).delete_variant(
        tenant_id=user.tenant_id,
        variant_id=variant_id,
    )
