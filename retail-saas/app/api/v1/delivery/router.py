from typing import Optional

from fastapi import APIRouter, Body, Depends, File, Path, Query, UploadFile, status
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import AppException
from app.core.security import require_permission
from app.models.user import User
from app.schemas.delivery import (
    DeliveryAddressUpdateRequest,
    DeliveryCancelRequest,
    DeliveryCreate,
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
    DeliveryTrackingResponse,
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
    user: User = Depends(
        require_permission("orders:read")
    ),
    db: Session = Depends(get_db),
):
    deliveries = DeliveryService(db).list_deliveries(
        tenant_id=user.tenant_id,
    )
    if not deliveries:
        return DeliveryListResponse(
            success=True,
            message="No deliveries found",
            data=[],
            total=0,
        )

    return DeliveryListResponse(
        success=True,
        message="Deliveries retrieved successfully",
        data=[DeliveryResponse.model_validate(d) for d in deliveries],
        total=len(deliveries),
    )


@router.get("/stats", response_model=DeliveryStatsResponse)
def get_delivery_stats(
    user: User = Depends(
        require_permission("orders:read")
    ),
    db: Session = Depends(get_db),
):
    try:
        return DeliveryService(db).get_stats(tenant_id=user.tenant_id)
    except AppException as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.detail,
        )


@router.get("/export")
def export_deliveries(
    format: str = Query(..., description="Export format: excel or csv (required)"),
    status: Optional[str] = Query(None, description="Optional status filter"),
    user: User = Depends(
        require_permission("orders:read")
    ),
    db: Session = Depends(get_db),
):
    allowed_formats = {"excel", "csv"}
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


@router.get("/methods", response_model=DeliveryMethodListResponse)
def list_delivery_methods(
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    user: User = Depends(
        require_permission("orders:read")
    ),
    db: Session = Depends(get_db),
):
    try:
        methods = DeliveryService(db).list_methods(
            tenant_id=user.tenant_id,
            is_active=is_active,
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
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    user: User = Depends(
        require_permission("orders:read")
    ),
    db: Session = Depends(get_db),
):
    try:
        zones = DeliveryService(db).list_zones(
            tenant_id=user.tenant_id,
            is_active=is_active,
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