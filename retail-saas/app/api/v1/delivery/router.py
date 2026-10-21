from enum import Enum
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Body, Depends, File, Path, Query, Response, UploadFile, status
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import AppException
from app.core.security import require_permission
from app.models.user import User
from app.schemas.delivery import (
    CODCollectRequest,
    CODDeliveryItem,
    CODReconciliationResponse,
    CODReconciliationSummary,
    DeliveryAddressUpdateRequest,
    DeliveryCancelRequest,
    DeliveryCreate,
    DeliveryFailedAttemptRequest,
    DeliveryHistoryItem,
    DeliveryHistoryResponse,
    DeliveryLabelResponse,
    DeliveryListResponse,
    DeliveryMessageResponse,
    DeliveryMethodCreate,
    DeliveryMethodListResponse,
    DeliveryMethodResponse,
    DeliveryMethodUpdate,
    DeliveryPartnerAssignRequest,
    DeliveryResponse,
    DeliveryStatsResponse,
    DeliveryStatusUpdate,
    DeliveryThermalLabelResponse,
    DeliveryTrackingResponse,
    ThermalLabelMode,
    SingleDeliveryMethodResponse,
    SingleDeliveryResponse,
    SingleDeliveryZoneResponse,
    DeliveryZoneCreate,
    DeliveryZoneListResponse,
    DeliveryZoneResponse,
    DeliveryZoneUpdate,
    DeliveryPartnerConnect,
    DeliveryPartnerListResponse,
    DeliveryPartnerResponse,
    DeliveryPartnerUpdate,
    SingleDeliveryPartnerResponse,
    ServiceabilityResponse,
    ServiceabilityUploadResponse,
)
from app.services.delivery_service import DeliveryService

router = APIRouter(
    prefix="/delivery",
    tags=["delivery"],
)


@router.post(
    "",
    response_model=SingleDeliveryResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_delivery(
    data: DeliveryCreate,
    user: User = Depends(require_permission("orders:write")),
    db: Session = Depends(get_db),
):
    try:
        delivery = DeliveryService(db).create_delivery(
            tenant_id=user.tenant_id,
            order_id=data.order_id,
            delivery_person=data.delivery_person,
            tracking_number=data.tracking_number,
            partner_id=data.partner_id,
            delivery_method_id=data.delivery_method_id,
            zone_id=data.zone_id,
            is_cod=data.is_cod,
            cod_amount=data.cod_amount,
            delivery_slot=data.delivery_slot,
            estimated_delivery_time=data.estimated_delivery_time,
            dispatched_at=data.dispatched_at,
        )
        return SingleDeliveryResponse(
            success=True,
            message="Delivery created successfully",
            data=DeliveryResponse.model_validate(delivery),
        )
    except AppException as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.detail,
        )


@router.get("", response_model=DeliveryListResponse)
def list_deliveries(
    page: Optional[int] = Query(None, ge=1, description="Page number (1-based)"),
    page_size: Optional[int] = Query(None, ge=1, le=1000, description="Items per page"),
    status: Optional[str] = Query(None, description="Filter by delivery status: pending, assigned, out_for_delivery, delivered, cancelled"),
    delivery_person: Optional[str] = Query(None, description="Filter by delivery person name"),
    partner_id: Optional[int] = Query(None, gt=0, description="Filter by delivery partner ID"),
    order_id: Optional[int] = Query(None, gt=0, description="Filter by order ID"),
    is_cod: Optional[bool] = Query(None, description="Filter by COD flag"),
    date_from: Optional[datetime] = Query(None, description="Filter deliveries created on or after datetime"),
    date_to: Optional[datetime] = Query(None, description="Filter deliveries created on or before datetime"),
    search: Optional[str] = Query(None, description="Search term for tracking number, rider, or order number"),
    store_id: Optional[int] = Query(None, gt=0, description="Filter deliveries by store ID"),
    user: User = Depends(
        require_permission("orders:read")
    ),
    db: Session = Depends(get_db),
):
    deliveries, total = DeliveryService(db).list_deliveries(
        tenant_id=user.tenant_id,
        page=page,
        page_size=page_size,
        status=status,
        delivery_person=delivery_person,
        partner_id=partner_id,
        order_id=order_id,
        is_cod=is_cod,
        date_from=date_from,
        date_to=date_to,
        search=search,
        store_id=store_id,
    )
    if not deliveries:
        return DeliveryListResponse(
            success=True,
            message="No deliveries found",
            data=[],
            total=0,
            page=page,
            page_size=page_size,
            total_pages=0 if page is not None else None,
        )

    total_pages = ((total + page_size - 1) // page_size) if page_size else 1
    return DeliveryListResponse(
        success=True,
        message="Deliveries retrieved successfully",
        data=[DeliveryResponse.model_validate(d) for d in deliveries],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages if page is not None else None,
    )


@router.get("/stats", response_model=DeliveryStatsResponse)
def get_delivery_stats(
    store_id: Optional[int] = Query(None, gt=0, description="Filter delivery stats by store ID"),
    user: User = Depends(
        require_permission("orders:read")
    ),
    db: Session = Depends(get_db),
):
    try:
        return DeliveryService(db).get_stats(tenant_id=user.tenant_id, store_id=store_id)
    except AppException as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.detail,
        )


@router.get(
    "/export",
    summary="Export Deliveries to Excel, CSV, or PDF",
    description=(
        "Exports tenant delivery and shipment dispatch records as an analytical Excel workbook (.xlsx), "
        "raw machine-readable CSV, or professional PDF report. Supports filtering by delivery status ('pending', "
        "'assigned', 'out_for_delivery', 'delivered', 'cancelled'). Requires 'orders:read' permission."
    ),
    responses={
        200: {
            "content": {
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {},
                "text/csv": {},
                "application/pdf": {},
            },
            "description": "Exported Deliveries data stream (Excel, CSV, or PDF).",
        }
    },
)
def export_deliveries(
    format: str = Query(..., description="Export format: excel, csv, or pdf (required)"),
    status: Optional[str] = Query(None, description="Optional status filter"),
    store_id: Optional[int] = Query(None, gt=0, description="Filter exported deliveries by store ID"),
    user: User = Depends(
        require_permission("orders:read")
    ),
    db: Session = Depends(get_db),
):
    allowed_formats = {"excel", "csv", "pdf"}
    if not isinstance(format, str):
        raise AppException("Format must be a string", status_code=422)
    f_clean = format.strip().lower()
    if not f_clean:
        raise AppException("Format cannot be empty or whitespace", status_code=422)
    if f_clean not in allowed_formats:
        raise AppException(
            f"Invalid format: '{format}'. Supported formats are: {', '.join(sorted(allowed_formats))}",
            status_code=422,
        )
    export_format = f_clean

    allowed_statuses = {"all", "pending", "assigned", "out_for_delivery", "delivered", "cancelled"}
    if status is not None:
        if not isinstance(status, str):
            raise AppException("Status must be a string", status_code=422)
        s_clean = status.strip().lower()
        if not s_clean:
            raise AppException("Status cannot be empty or whitespace", status_code=422)
        if s_clean not in allowed_statuses:
            raise AppException(
                f"Invalid status: '{status}'. Allowed statuses are: {', '.join(sorted(allowed_statuses))}",
                status_code=422,
            )
        filter_status = None if s_clean == "all" else s_clean
    else:
        filter_status = None

    try:
        buffer, media_type, filename = DeliveryService(db).export_deliveries(
            tenant_id=user.tenant_id,
            status=filter_status,
            format=export_format,
            store_id=store_id,
        )
        return StreamingResponse(
            buffer,
            media_type=media_type,
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            },
        )
    except AppException as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.detail,
        )


@router.get("/cod-reconciliation", response_model=CODReconciliationResponse)
def get_cod_reconciliation(
    delivery_person: Optional[str] = Query(None, description="Filter by delivery person"),
    partner_id: Optional[int] = Query(None, gt=0, description="Filter by delivery partner ID"),
    status: Optional[str] = Query(None, description="Filter by COD status: collected, pending, all"),
    date_from: Optional[datetime] = Query(None, description="Start datetime"),
    date_to: Optional[datetime] = Query(None, description="End datetime"),
    store_id: Optional[int] = Query(None, gt=0, description="Filter COD reconciliation by store ID"),
    user: User = Depends(require_permission("orders:read")),
    db: Session = Depends(get_db),
):
    try:
        rec_data = DeliveryService(db).get_cod_reconciliation(
            tenant_id=user.tenant_id,
            delivery_person=delivery_person,
            partner_id=partner_id,
            status=status,
            date_from=date_from,
            date_to=date_to,
            store_id=store_id,
        )
        return CODReconciliationResponse(
            success=True,
            message="COD reconciliation data retrieved successfully",
            summary=CODReconciliationSummary(**rec_data["summary"]),
            deliveries=[CODDeliveryItem(**d) for d in rec_data["deliveries"]],
        )
    except AppException as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.detail,
        )


class ActiveStatusFilter(str, Enum):
    ALL = "all"
    TRUE = "true"
    FALSE = "false"

    @classmethod
    def _missing_(cls, value):
        if isinstance(value, str):
            val = value.strip().lower()
            if val in ("1", "yes", "true"):
                return cls.TRUE
            if val in ("0", "no", "false"):
                return cls.FALSE
            if val in ("all", "none", "", "--"):
                return cls.ALL
        return None


@router.get("/methods", response_model=DeliveryMethodListResponse)
def list_delivery_methods(
    is_active: ActiveStatusFilter = Query(
        default=ActiveStatusFilter.ALL,
        description="Filter by active status ('all' for both, 'true' for active only, 'false' for inactive only)",
    ),
    user: User = Depends(
        require_permission("orders:read")
    ),
    db: Session = Depends(get_db),
):
    try:
        active_bool: Optional[bool] = None
        if is_active == ActiveStatusFilter.TRUE:
            active_bool = True
        elif is_active == ActiveStatusFilter.FALSE:
            active_bool = False

        methods = DeliveryService(db).list_methods(
            tenant_id=user.tenant_id,
            is_active=active_bool,
        )
        if not methods:
            return DeliveryMethodListResponse(
                success=True,
                message="No delivery methods found",
                data=[],
                total=0,
            )
        return DeliveryMethodListResponse(
            success=True,
            message="Delivery methods retrieved successfully",
            data=[DeliveryMethodResponse.model_validate(m) for m in methods],
            total=len(methods),
        )
    except AppException as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.detail,
        )


@router.post(
    "/methods",
    response_model=SingleDeliveryMethodResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_delivery_method(
    data: DeliveryMethodCreate,
    user: User = Depends(
        require_permission("orders:write")
    ),
    db: Session = Depends(get_db),
):
    try:
        method = DeliveryService(db).create_method(
            tenant_id=user.tenant_id,
            data=data,
        )
        return SingleDeliveryMethodResponse(
            success=True,
            message="Delivery method created successfully",
            data=DeliveryMethodResponse.model_validate(method),
        )
    except AppException as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.detail,
        )


@router.put(
    "/methods/{method_id}",
    response_model=SingleDeliveryMethodResponse,
)
def update_delivery_method(
    data: DeliveryMethodUpdate,
    method_id: int = Path(
        ...,
        gt=0,
        description="Delivery method ID must be a positive integer",
    ),
    user: User = Depends(
        require_permission("orders:write")
    ),
    db: Session = Depends(get_db),
):
    try:
        method = DeliveryService(db).update_method(
            tenant_id=user.tenant_id,
            method_id=method_id,
            data=data,
        )
        return SingleDeliveryMethodResponse(
            success=True,
            message="Delivery method updated successfully",
            data=DeliveryMethodResponse.model_validate(method),
        )
    except AppException as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.detail,
        )


@router.patch(
    "/methods/{method_id}/toggle",
    response_model=SingleDeliveryMethodResponse,
)
def toggle_delivery_method(
    method_id: int = Path(
        ...,
        gt=0,
        description="Delivery method ID must be a positive integer",
    ),
    user: User = Depends(
        require_permission("orders:write")
    ),
    db: Session = Depends(get_db),
):
    try:
        method = DeliveryService(db).toggle_method(
            tenant_id=user.tenant_id,
            method_id=method_id,
        )
        return SingleDeliveryMethodResponse(
            success=True,
            message="Delivery method status toggled successfully",
            data=DeliveryMethodResponse.model_validate(method),
        )
    except AppException as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.detail,
        )


@router.delete(
    "/methods/{method_id}",
    response_model=DeliveryMessageResponse,
)
def delete_delivery_method(
    method_id: int = Path(
        ...,
        gt=0,
        description="Delivery method ID must be a positive integer",
    ),
    user: User = Depends(
        require_permission("orders:write")
    ),
    db: Session = Depends(get_db),
):
    try:
        DeliveryService(db).delete_method(
            tenant_id=user.tenant_id,
            method_id=method_id,
        )
        return DeliveryMessageResponse(
            success=True,
            message="Delivery method deleted successfully",
        )
    except AppException as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.detail,
        )


@router.get("/zones", response_model=DeliveryZoneListResponse)
def list_delivery_zones(
    is_active: ActiveStatusFilter = Query(
        default=ActiveStatusFilter.ALL,
        description="Filter by active status ('all' for both, 'true' for active only, 'false' for inactive only)",
    ),
    user: User = Depends(
        require_permission("orders:read")
    ),
    db: Session = Depends(get_db),
):
    try:
        active_bool: Optional[bool] = None
        if is_active == ActiveStatusFilter.TRUE:
            active_bool = True
        elif is_active == ActiveStatusFilter.FALSE:
            active_bool = False

        zones = DeliveryService(db).list_zones(
            tenant_id=user.tenant_id,
            is_active=active_bool,
        )
        if not zones:
            return DeliveryZoneListResponse(
                success=True,
                message="No delivery zones found",
                data=[],
                total=0,
            )
        return DeliveryZoneListResponse(
            success=True,
            message="Delivery zones retrieved successfully",
            data=[DeliveryZoneResponse.model_validate(z) for z in zones],
            total=len(zones),
        )
    except AppException as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.detail,
        )


@router.post(
    "/zones",
    response_model=SingleDeliveryZoneResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_delivery_zone(
    data: DeliveryZoneCreate,
    user: User = Depends(
        require_permission("orders:write")
    ),
    db: Session = Depends(get_db),
):
    try:
        zone = DeliveryService(db).create_zone(
            tenant_id=user.tenant_id,
            data=data,
        )
        return SingleDeliveryZoneResponse(
            success=True,
            message="Delivery zone created successfully",
            data=DeliveryZoneResponse.model_validate(zone),
        )
    except AppException as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.detail,
        )


@router.put(
    "/zones/{zone_id}",
    response_model=SingleDeliveryZoneResponse,
)
def update_delivery_zone(
    data: DeliveryZoneUpdate,
    zone_id: int = Path(
        ...,
        gt=0,
        description="Delivery zone ID must be a positive integer",
    ),
    user: User = Depends(
        require_permission("orders:write")
    ),
    db: Session = Depends(get_db),
):
    try:
        zone = DeliveryService(db).update_zone(
            tenant_id=user.tenant_id,
            zone_id=zone_id,
            data=data,
        )
        return SingleDeliveryZoneResponse(
            success=True,
            message="Delivery zone updated successfully",
            data=DeliveryZoneResponse.model_validate(zone),
        )
    except AppException as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.detail,
        )


@router.delete(
    "/zones/{zone_id}",
    response_model=DeliveryMessageResponse,
)
def delete_delivery_zone(
    zone_id: int = Path(
        ...,
        gt=0,
        description="Delivery zone ID must be a positive integer",
    ),
    user: User = Depends(
        require_permission("orders:write")
    ),
    db: Session = Depends(get_db),
):
    try:
        DeliveryService(db).delete_zone(
            tenant_id=user.tenant_id,
            zone_id=zone_id,
        )
        return DeliveryMessageResponse(
            success=True,
            message="Delivery zone deleted successfully",
        )
    except AppException as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.detail,
        )


def _parse_strict_bool(val: Optional[str]) -> Optional[bool]:
    if val is None:
        return None
    v = str(val).strip().lower()
    if v == "true":
        return True
    if v == "false":
        return False
    raise AppException(
        "Invalid boolean value for is_active. Allowed values: true, false",
        status_code=422,
    )


@router.get("/partners", response_model=DeliveryPartnerListResponse)
def list_delivery_partners(
    is_active: Optional[str] = Query(None, description="Filter by active status (true/false)"),
    user: User = Depends(require_permission("orders:read")),
    db: Session = Depends(get_db),
):
    try:
        active_filter = _parse_strict_bool(is_active)
        partners = DeliveryService(db).list_partners(
            tenant_id=user.tenant_id,
            is_active=active_filter,
        )
        if not partners:
            return DeliveryPartnerListResponse(
                success=True,
                message="No delivery partners found",
                data=[],
                total=0,
            )
        return DeliveryPartnerListResponse(
            success=True,
            message="Delivery partners retrieved successfully",
            data=[DeliveryPartnerResponse.model_validate(p) for p in partners],
            total=len(partners),
        )
    except AppException as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.detail,
        )


@router.post(
    "/partners/connect",
    response_model=SingleDeliveryPartnerResponse,
    status_code=status.HTTP_201_CREATED,
)
def connect_delivery_partner(
    data: DeliveryPartnerConnect,
    user: User = Depends(require_permission("orders:write")),
    db: Session = Depends(get_db),
):
    try:
        partner = DeliveryService(db).create_partner(
            tenant_id=user.tenant_id,
            data=data,
        )
        return SingleDeliveryPartnerResponse(
            success=True,
            message="Delivery partner connected successfully",
            data=DeliveryPartnerResponse.model_validate(partner),
        )
    except AppException as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.detail,
        )


@router.put(
    "/partners/{partner_id}",
    response_model=SingleDeliveryPartnerResponse,
)
def update_delivery_partner(
    data: DeliveryPartnerUpdate,
    partner_id: int = Path(
        ...,
        gt=0,
        description="Delivery partner ID must be a positive integer",
    ),
    user: User = Depends(require_permission("orders:write")),
    db: Session = Depends(get_db),
):
    try:
        partner = DeliveryService(db).update_partner(
            tenant_id=user.tenant_id,
            partner_id=partner_id,
            data=data,
        )
        return SingleDeliveryPartnerResponse(
            success=True,
            message="Delivery partner updated successfully",
            data=DeliveryPartnerResponse.model_validate(partner),
        )
    except AppException as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.detail,
        )


@router.delete(
    "/partners/{partner_id}",
    response_model=DeliveryMessageResponse,
)
def delete_delivery_partner(
    partner_id: int = Path(
        ...,
        gt=0,
        description="Delivery partner ID must be a positive integer",
    ),
    user: User = Depends(require_permission("orders:write")),
    db: Session = Depends(get_db),
):
    try:
        DeliveryService(db).delete_partner(
            tenant_id=user.tenant_id,
            partner_id=partner_id,
        )
        return DeliveryMessageResponse(
            success=True,
            message="Delivery partner deleted successfully",
        )
    except AppException as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.detail,
        )


@router.post(
    "/serviceability/upload",
    response_model=ServiceabilityUploadResponse,
)
async def upload_serviceability(
    file: UploadFile = File(..., description="CSV or XLSX file containing pincode serviceability data"),
    user: User = Depends(require_permission("orders:write")),
    db: Session = Depends(get_db),
):
    try:
        if not file or not file.filename:
            raise AppException("File must be provided", status_code=422)
        contents = await file.read()
        result = DeliveryService(db).upload_serviceability(
            tenant_id=user.tenant_id,
            filename=file.filename,
            contents=contents,
        )
        return ServiceabilityUploadResponse(
            success=True,
            message="Pincodes uploaded successfully",
            data=result,
        )
    except AppException as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.detail,
        )


@router.get(
    "/serviceability/{pincode}",
    response_model=ServiceabilityResponse,
)
def check_pincode_serviceability(
    pincode: str = Path(..., description="6-digit postal pincode"),
    user: User = Depends(require_permission("orders:read")),
    db: Session = Depends(get_db),
):
    try:
        result = DeliveryService(db).check_serviceability(
            tenant_id=user.tenant_id,
            pincode=pincode,
        )
        msg = "Pincode is serviceable" if result.is_serviceable else "Pincode is not serviceable"
        return ServiceabilityResponse(
            success=True,
            message=msg,
            data=result,
        )
    except AppException as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.detail,
        )


@router.get("/{delivery_id}/label", response_model=DeliveryLabelResponse)
def get_delivery_label(
    delivery_id: int = Path(
        ...,
        gt=0,
        description="Delivery ID must be a positive integer",
    ),
    user: User = Depends(
        require_permission("orders:read")
    ),
    db: Session = Depends(get_db),
):
    try:
        label = DeliveryService(db).get_label(
            tenant_id=user.tenant_id,
            delivery_id=delivery_id,
        )
        return DeliveryLabelResponse(
            success=True,
            message="Delivery label generated successfully",
            data=label,
        )
    except AppException as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.detail,
        )


@router.get("/{delivery_id}/tracking", response_model=DeliveryTrackingResponse)
def get_delivery_tracking(
    delivery_id: int = Path(
        ...,
        gt=0,
        description="Delivery ID must be a positive integer",
    ),
    user: User = Depends(
        require_permission("orders:read")
    ),
    db: Session = Depends(get_db),
):
    try:
        tracking_data = DeliveryService(db).get_tracking(
            tenant_id=user.tenant_id,
            delivery_id=delivery_id,
        )
        return DeliveryTrackingResponse(
            success=True,
            message="Delivery tracking retrieved successfully",
            data=tracking_data,
        )
    except AppException as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.detail,
        )


@router.get("/{delivery_id}/history", response_model=DeliveryHistoryResponse)
def get_delivery_history(
    delivery_id: int = Path(
        ...,
        gt=0,
        description="Delivery ID must be a positive integer",
    ),
    user: User = Depends(
        require_permission("orders:read")
    ),
    db: Session = Depends(get_db),
):
    try:
        history = DeliveryService(db).get_history(
            tenant_id=user.tenant_id,
            delivery_id=delivery_id,
        )
        if not history:
            return DeliveryHistoryResponse(
                success=True,
                message="No history found for delivery",
                data=[],
                total=0,
            )

        return DeliveryHistoryResponse(
            success=True,
            message="Delivery history retrieved successfully",
            data=[DeliveryHistoryItem.model_validate(h) for h in history],
            total=len(history),
        )
    except AppException as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.detail,
        )


@router.get("/{delivery_id}", response_model=SingleDeliveryResponse)
def get_delivery(
    delivery_id: int = Path(
        ...,
        gt=0,
        description="Delivery ID must be a positive integer",
    ),
    user: User = Depends(
        require_permission("orders:read")
    ),
    db: Session = Depends(get_db),
):
    try:
        delivery = DeliveryService(db).get_delivery(
            tenant_id=user.tenant_id,
            delivery_id=delivery_id,
        )
        return SingleDeliveryResponse(
            success=True,
            message="Delivery retrieved successfully",
            data=DeliveryResponse.model_validate(delivery),
        )
    except AppException as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.detail,
        )


@router.patch("/{delivery_id}/status", response_model=SingleDeliveryResponse)
def update_delivery_status(
    delivery_id: int = Path(
        ...,
        gt=0,
        description="Delivery ID must be a positive integer",
    ),
    data: DeliveryStatusUpdate = ...,
    user: User = Depends(
        require_permission("orders:write")
    ),
    db: Session = Depends(get_db),
):
    try:
        delivery = DeliveryService(db).update_status(
            tenant_id=user.tenant_id,
            delivery_id=delivery_id,
            status=data.status,
        )
        return SingleDeliveryResponse(
            success=True,
            message="Delivery status updated successfully",
            data=DeliveryResponse.model_validate(delivery),
        )
    except AppException as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.detail,
        )


@router.patch("/{delivery_id}/cancel", response_model=SingleDeliveryResponse)
def cancel_delivery(
    delivery_id: int = Path(
        ...,
        gt=0,
        description="Delivery ID must be a positive integer",
    ),
    data: DeliveryCancelRequest = ...,
    user: User = Depends(
        require_permission("orders:write")
    ),
    db: Session = Depends(get_db),
):
    try:
        delivery = DeliveryService(db).cancel_delivery(
            tenant_id=user.tenant_id,
            delivery_id=delivery_id,
            reason=data.reason,
        )
        return SingleDeliveryResponse(
            success=True,
            message="Delivery cancelled successfully",
            data=DeliveryResponse.model_validate(delivery),
        )
    except AppException as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.detail,
        )


@router.patch("/{delivery_id}/partner", response_model=SingleDeliveryResponse)
def assign_delivery_partner(
    delivery_id: int = Path(
        ...,
        gt=0,
        description="Delivery ID must be a positive integer",
    ),
    data: DeliveryPartnerAssignRequest = ...,
    user: User = Depends(
        require_permission("orders:write")
    ),
    db: Session = Depends(get_db),
):
    try:
        delivery = DeliveryService(db).assign_partner(
            tenant_id=user.tenant_id,
            delivery_id=delivery_id,
            delivery_person=data.delivery_person,
            tracking_number=data.tracking_number,
            partner_id=data.partner_id,
        )
        return SingleDeliveryResponse(
            success=True,
            message="Delivery partner assigned successfully",
            data=DeliveryResponse.model_validate(delivery),
        )
    except AppException as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.detail,
        )


@router.patch("/{delivery_id}/address", response_model=SingleDeliveryResponse)
def update_delivery_address(
    delivery_id: int = Path(
        ...,
        gt=0,
        description="Delivery ID must be a positive integer",
    ),
    data: DeliveryAddressUpdateRequest = ...,
    user: User = Depends(
        require_permission("orders:write")
    ),
    db: Session = Depends(get_db),
):
    try:
        delivery = DeliveryService(db).update_address(
            tenant_id=user.tenant_id,
            delivery_id=delivery_id,
            delivery_address=data.delivery_address,
        )
        return SingleDeliveryResponse(
            success=True,
            message="Delivery address updated successfully",
            data=DeliveryResponse.model_validate(delivery),
        )
    except AppException as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.detail,
        )


@router.get(
    "/{delivery_id}/label/thermal",
    summary="Get Thermal Delivery Label",
    description=(
        "Generate a standard 4x6 inch thermal shipping label. "
        "Supports 'preview' (visual image rendered directly in Swagger UI), 'download' or 'pdf' (4x6 inch PDF file download), "
        "'view' (inline browser preview with print trigger), "
        "'download' (HTML attachment file), "
        "'html' (direct print raw HTML), or 'json' (structured payload)."
    ),
    responses={
        200: {
            "model": DeliveryThermalLabelResponse,
            "description": "Label visual preview (PNG), HTML render, file download, or JSON payload.",
            "content": {
                "image/png": {
                    "schema": {"type": "string", "format": "binary"},
                    "description": "Visual 4x6 inch thermal shipping label PNG rendered directly in Swagger UI",
                },
                "text/html": {
                    "schema": {"type": "string"},
                    "description": "HTML shipping label for browser viewing or thermal printing",
                },
            },
        }
    },
)
def get_thermal_delivery_label(
    delivery_id: int = Path(
        ...,
        gt=0,
        description="Delivery ID must be a positive integer",
    ),
    mode: ThermalLabelMode = Query(
        default=ThermalLabelMode.preview,
        description="Output mode: 'preview' (visual image rendered directly in Swagger UI), 'view' (inline browser preview with print trigger), 'download' (HTML file download), 'html' (raw HTML), or 'json' (structured payload)",
    ),
    user: User = Depends(require_permission("orders:read")),
    db: Session = Depends(get_db),
):
    try:
        service = DeliveryService(db)

        if mode == ThermalLabelMode.preview:
            image_bytes = service.get_thermal_label_image(
                tenant_id=user.tenant_id,
                delivery_id=delivery_id,
            )
            return Response(
                content=image_bytes,
                media_type="image/png",
                headers={"Content-Disposition": "inline"},
            )

        delivery = service.get_delivery(user.tenant_id, delivery_id)
        order = delivery.order
        if not order and delivery.order_id:
            from app.models.order import Order

            order = (
                db.query(Order)
                .filter(Order.id == delivery.order_id, Order.tenant_id == user.tenant_id)
                .first()
            )
        order_number = (
            order.order_number
            if order and order.order_number
            else f"ORD-{delivery.order_id}"
        )

        # Mode 'download' or 'pdf': Generates standard 4x6 inch PDF thermal shipping label
        if mode in (ThermalLabelMode.download, ThermalLabelMode.pdf):
            pdf_bytes = service.get_thermal_label_pdf(
                tenant_id=user.tenant_id,
                delivery_id=delivery_id,
            )
            filename = f"shipping_label_{order_number}.pdf"
            return Response(
                content=pdf_bytes,
                media_type="application/pdf",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )

        html_content = service.get_thermal_label_html(
            tenant_id=user.tenant_id,
            delivery_id=delivery_id,
            auto_print=(mode == ThermalLabelMode.view),
        )

        if mode == ThermalLabelMode.json:
            return DeliveryThermalLabelResponse(
                success=True,
                message="Thermal delivery label generated successfully",
                html=html_content,
                delivery_id=delivery.id,
                order_number=order_number,
            )

        # ThermalLabelMode.view and ThermalLabelMode.html
        return HTMLResponse(
            content=html_content,
            status_code=200,
            headers={"Content-Disposition": "inline"},
        )
    except AppException as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.detail,
        )


@router.post("/{delivery_id}/failed-attempt", response_model=SingleDeliveryResponse)
def record_failed_delivery_attempt(
    delivery_id: int = Path(
        ...,
        gt=0,
        description="Delivery ID must be a positive integer",
    ),
    data: DeliveryFailedAttemptRequest = ...,
    user: User = Depends(require_permission("orders:write")),
    db: Session = Depends(get_db),
):
    try:
        delivery = DeliveryService(db).record_failed_attempt(
            tenant_id=user.tenant_id,
            delivery_id=delivery_id,
            reason=data.reason,
            remarks=data.remarks,
            reschedule_date=data.reschedule_date,
        )
        return SingleDeliveryResponse(
            success=True,
            message=f"Delivery attempt #{delivery.attempt_count} recorded successfully",
            data=DeliveryResponse.model_validate(delivery),
        )
    except AppException as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.detail,
        )


@router.patch("/{delivery_id}/collect-cod", response_model=SingleDeliveryResponse)
def collect_delivery_cod(
    delivery_id: int = Path(
        ...,
        gt=0,
        description="Delivery ID must be a positive integer",
    ),
    data: Optional[CODCollectRequest] = None,
    user: User = Depends(require_permission("orders:write")),
    db: Session = Depends(get_db),
):
    try:
        amount = data.amount if data else None
        delivery = DeliveryService(db).collect_cod(
            tenant_id=user.tenant_id,
            delivery_id=delivery_id,
            amount_collected=amount,
        )
        return SingleDeliveryResponse(
            success=True,
            message="COD payment collected successfully",
            data=DeliveryResponse.model_validate(delivery),
        )
    except AppException as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.detail,
        )

