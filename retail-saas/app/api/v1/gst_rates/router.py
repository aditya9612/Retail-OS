from typing import Any, List, Literal, Optional, Union

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_operational_write, require_permission
from app.models.user import User
from app.schemas.gst_rate import (
    GstBulkImportRequest,
    GstBulkImportResponse,
    GstRateCreate,
    GstRateListResponse,
    GstRateResponse,
    GstRateUpdate,
    GstSeedResponse,
)
from app.services.gst_service import GstService


router = APIRouter(prefix="/gst-rates", tags=["gst-rates"])


@router.get(
    "",
    response_model=Union[GstRateListResponse, List[GstRateResponse]],
    summary="List GST Rates",
    description="Lists GST rates with optional filters (search, HSN code, status, code type, supply type) and optional pagination.",
)
def list_gst_rates(
    supply_type: Optional[Literal["intra_state", "inter_state"]] = Query(
        default=None,
        description="intra_state returns CGST+SGST only; inter_state returns IGST only",
    ),
    search: Optional[str] = Query(
        default=None,
        description="Search by HSN/SAC code or description keyword",
    ),
    hsn_code: Optional[str] = Query(
        default=None,
        description="Filter by specific HSN/SAC code",
    ),
    status_filter: Optional[bool] = Query(
        default=None,
        alias="status",
        description="Filter by active status (true/false)",
    ),
    code_type: Optional[Literal["HSN", "SAC"]] = Query(
        default=None,
        description="Filter by code type: HSN for goods, SAC for services",
    ),
    page: Optional[int] = Query(
        default=None,
        ge=1,
        description="Page number for pagination (optional)",
    ),
    page_size: Optional[int] = Query(
        default=None,
        ge=1,
        le=100,
        description="Items per page for pagination (optional)",
    ),
    user: User = Depends(require_permission("billing:read")),
    db: Session = Depends(get_db),
):
    return GstService(db).list_rate_views(
        user.tenant_id,
        supply_type=supply_type,
        search=search,
        hsn_code=hsn_code,
        status=status_filter,
        code_type=code_type,
        page=page,
        page_size=page_size,
    )


@router.post(
    "",
    response_model=GstRateResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_operational_write)],
    summary="Create GST Rate",
    description="Defines a new HSN/SAC tax slab rate with automatic CGST, SGST, and IGST calculation.",
)
def create_gst_rate(
    payload: GstRateCreate,
    user: User = Depends(require_permission("billing:gst_config")),
    db: Session = Depends(get_db),
):
    return GstService(db).create_rate(user.tenant_id, payload)


@router.post(
    "/seed-defaults",
    response_model=GstSeedResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_operational_write)],
    summary="Seed Standard Retail GST Slabs",
    description="Seeds default common Indian retail HSN/SAC codes (Groceries, Dairy, Apparel, Footwear, Gold, Computers, Electronics, Services) for this tenant.",
)
def seed_default_gst_rates(
    user: User = Depends(require_permission("billing:gst_config")),
    db: Session = Depends(get_db),
):
    return GstService(db).seed_default_rates(user.tenant_id)


@router.post(
    "/bulk-import",
    response_model=GstBulkImportResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_operational_write)],
    summary="Bulk Import HSN/SAC Rates",
    description="Bulk creates or updates multiple HSN/SAC tax slab rates in a single atomic request.",
)
def bulk_import_gst_rates(
    payload: GstBulkImportRequest,
    user: User = Depends(require_permission("billing:gst_config")),
    db: Session = Depends(get_db),
):
    return GstService(db).bulk_import_rates(user.tenant_id, payload.items)


@router.get(
    "/hsn/{hsn_code}",
    response_model=GstRateResponse,
    summary="Get GST Rate by HSN/SAC Code",
    description="Fast direct lookup of active GST tax rate by HSN/SAC code.",
)
def get_gst_rate_by_hsn(
    hsn_code: str,
    supply_type: Optional[Literal["intra_state", "inter_state"]] = Query(
        default=None,
        description="intra_state returns CGST+SGST only; inter_state returns IGST only",
    ),
    user: User = Depends(require_permission("billing:read")),
    db: Session = Depends(get_db),
):
    return GstService(db).get_rate_by_hsn(user.tenant_id, hsn_code, supply_type=supply_type)


@router.get(
    "/{rate_id}",
    response_model=GstRateResponse,
    summary="Get GST Rate by ID",
    description="Retrieves specific GST rate details by internal ID.",
)
def get_gst_rate(
    rate_id: int,
    supply_type: Optional[Literal["intra_state", "inter_state"]] = Query(
        default=None,
        description="intra_state returns CGST+SGST only; inter_state returns IGST only",
    ),
    user: User = Depends(require_permission("billing:read")),
    db: Session = Depends(get_db),
):
    return GstService(db).get_rate(user.tenant_id, rate_id, supply_type=supply_type)


@router.put(
    "/{rate_id}",
    response_model=GstRateResponse,
    dependencies=[Depends(require_operational_write)],
    summary="Update GST Rate",
    description="Updates existing GST rate, HSN code, description, or active status.",
)
@router.patch("/{rate_id}", response_model=GstRateResponse)
def update_gst_rate(
    rate_id: int,
    payload: GstRateUpdate,
    user: User = Depends(require_permission("billing:gst_config")),
    db: Session = Depends(get_db),
):
    return GstService(db).update_rate(user.tenant_id, rate_id, payload)


@router.delete(
    "/{rate_id}",
    dependencies=[Depends(require_operational_write)],
    summary="Delete GST Rate",
    description="Deletes an unused GST rate configuration. Fails safely if active products are associated with this HSN code.",
)
def delete_gst_rate(
    rate_id: int,
    user: User = Depends(require_permission("billing:gst_config")),
    db: Session = Depends(get_db),
):
    return GstService(db).delete_rate(user.tenant_id, rate_id)
