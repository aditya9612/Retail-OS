from typing import Optional
from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_operational_write, require_permission
from app.models.user import User
from app.schemas.product_variant import (
    ProductVariantCreate,
    ProductVariantDirectCreate,
    ProductVariantListResponse,
    ProductVariantResponse,
    ProductVariantUpdate,
    VariantBarcodeGenerateResponse,
    VariantMatrixGenerateRequest,
    VariantMatrixGenerateResponse,
    VariantMissingBarcodesResponse,
)
from app.services.product_variant_service import ProductVariantService

router = APIRouter(
    prefix="/variants",
    tags=["product-variants"],
)


@router.get(
    "",
    response_model=ProductVariantListResponse,
    description="List and filter all product variants across all products",
)
def list_variants(
    product_id: Optional[int] = Query(None, gt=0, description="Filter variants by parent product ID"),
    search: Optional[str] = Query(None, description="Search by variant name, SKU, or barcode"),
    size: Optional[str] = Query(None, description="Filter by size (e.g. S, M, L, XL)"),
    color: Optional[str] = Query(None, description="Filter by color (e.g. Red, Blue, Black)"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    page: int = Query(1, gt=0, description="Page number"),
    page_size: int = Query(20, gt=0, le=100, description="Items per page"),
    user: User = Depends(require_permission("products:read")),
    db: Session = Depends(get_db),
):
    return ProductVariantService(db).list_all_variants(
        tenant_id=user.tenant_id,
        product_id=product_id,
        search=search,
        size=size,
        color=color,
        is_active=is_active,
        page=page,
        page_size=page_size,
    )


@router.post(
    "",
    response_model=ProductVariantResponse,
    status_code=201,
    dependencies=[Depends(require_operational_write)],
    description="Create a single variant for a product directly",
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
        auto_generate_barcode=data.auto_generate_barcode,
    )
    return ProductVariantService(db).create_variant(
        tenant_id=user.tenant_id,
        product_id=data.product_id,
        data=create_dto,
    )


@router.post(
    "/matrix-generate",
    response_model=VariantMatrixGenerateResponse,
    status_code=201,
    dependencies=[Depends(require_operational_write)],
    description="Automatically generate and create a matrix of variants (Sizes x Colors) for a parent product",
)
def generate_variant_matrix(
    data: VariantMatrixGenerateRequest,
    user: User = Depends(require_permission("products:write")),
    db: Session = Depends(get_db),
):
    return ProductVariantService(db).generate_variant_matrix(
        tenant_id=user.tenant_id,
        data=data,
    )


@router.post(
    "/generate-missing-barcodes",
    response_model=VariantMissingBarcodesResponse,
    dependencies=[Depends(require_operational_write)],
    description="Auto-generate unique EAN-13 barcodes for all product variants that currently have no barcode",
)
def generate_missing_variant_barcodes(
    user: User = Depends(require_permission("products:write")),
    db: Session = Depends(get_db),
):
    return ProductVariantService(db).generate_missing_barcodes(
        tenant_id=user.tenant_id,
    )


@router.get(
    "/by-barcode/{barcode}",
    response_model=ProductVariantResponse,
    description="Scan and lookup a product variant by its barcode (POS scanner integration)",
)
def get_variant_by_barcode(
    barcode: str = Path(..., min_length=1, max_length=100, description="Barcode number to scan"),
    user: User = Depends(require_permission("products:read")),
    db: Session = Depends(get_db),
):
    return ProductVariantService(db).get_variant_by_barcode(
        tenant_id=user.tenant_id,
        barcode=barcode,
    )


@router.get(
    "/by-sku/{sku}",
    response_model=ProductVariantResponse,
    description="Lookup a product variant by its unique SKU (warehouse and logistics lookup)",
)
def get_variant_by_sku(
    sku: str = Path(..., min_length=1, max_length=100, description="Variant SKU to lookup"),
    user: User = Depends(require_permission("products:read")),
    db: Session = Depends(get_db),
):
    return ProductVariantService(db).get_variant_by_sku(
        tenant_id=user.tenant_id,
        sku=sku,
    )


@router.get(
    "/{variant_id}",
    response_model=ProductVariantResponse,
    description="Get details of a product variant by ID",
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
    description="Update a product variant by ID",
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
    description="Partially update a product variant by ID",
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
    description="Soft delete (deactivate) a product variant",
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


@router.patch(
    "/{variant_id}/activate",
    response_model=ProductVariantResponse,
    dependencies=[Depends(require_operational_write)],
    description="Reactivate a previously deactivated or deleted product variant",
)
def activate_variant(
    variant_id: int = Path(..., gt=0, description="Variant ID to activate"),
    user: User = Depends(require_permission("products:write")),
    db: Session = Depends(get_db),
):
    return ProductVariantService(db).set_variant_active_status(
        tenant_id=user.tenant_id,
        variant_id=variant_id,
        is_active=True,
    )


@router.patch(
    "/{variant_id}/deactivate",
    response_model=ProductVariantResponse,
    dependencies=[Depends(require_operational_write)],
    description="Deactivate a product variant",
)
def deactivate_variant(
    variant_id: int = Path(..., gt=0, description="Variant ID to deactivate"),
    user: User = Depends(require_permission("products:write")),
    db: Session = Depends(get_db),
):
    return ProductVariantService(db).set_variant_active_status(
        tenant_id=user.tenant_id,
        variant_id=variant_id,
        is_active=False,
    )


@router.post(
    "/{variant_id}/generate-barcode",
    response_model=VariantBarcodeGenerateResponse,
    dependencies=[Depends(require_operational_write)],
    description="Generate or regenerate a unique EAN-13 barcode for a specific variant",
)
def generate_barcode_for_variant(
    variant_id: int = Path(..., gt=0, description="Variant ID"),
    overwrite: bool = Query(False, description="Overwrite existing barcode if already set"),
    user: User = Depends(require_permission("products:write")),
    db: Session = Depends(get_db),
):
    variant = ProductVariantService(db).generate_barcode_for_variant(
        tenant_id=user.tenant_id,
        variant_id=variant_id,
        overwrite=overwrite,
    )
    return {
        "success": True,
        "message": f"Barcode successfully generated for variant '{variant.sku}'",
        "variant_id": variant.id,
        "sku": variant.sku,
        "barcode": variant.barcode,
    }

