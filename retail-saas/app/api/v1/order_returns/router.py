from typing import Literal, Optional
from fastapi import APIRouter, Depends, Path, Query, Response, status
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user, require_operational_write
from app.models.user import User
from app.schemas.order_return import (
    OrderReturnCreate,
    OrderReturnExchangeRequest,
    OrderReturnRejectRequest,
    OrderReturnResponse,
    OrderReturnSlipResponse,
    OrderReturnStatsResponse,
    OrderReturnStatusUpdate,
    OrderReturnUpdate,
)
from app.services.order_return_service import OrderReturnService


router = APIRouter(
    prefix="/order-returns",
    tags=["Order Returns"],
)


@router.post(
    "",
    response_model=OrderReturnResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_operational_write)],
    summary="Create Return",
)
def create_return(
    data: OrderReturnCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return OrderReturnService.create_return(
        db=db,
        data=data,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
    )


@router.get(
    "",
    response_model=list[OrderReturnResponse],
    summary="List Returns",
)
def list_returns(
    skip: int = Query(
        0,
        ge=0,
        description="Number of records to skip",
    ),
    limit: int = Query(
        20,
        ge=1,
        le=100,
        description="Maximum records to return",
    ),
    store_id: Optional[int] = Query(None, gt=0, description="Filter order returns by store ID"),
    status: Optional[str] = Query(None, description="Filter by status (requested, approved, completed, rejected)"),
    customer_id: Optional[int] = Query(None, gt=0, description="Filter by customer ID"),
    order_id: Optional[int] = Query(None, gt=0, description="Filter by order ID"),
    search: Optional[str] = Query(None, description="Search by RMA number, reason, remarks"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return OrderReturnService.list_returns(
        db=db,
        tenant_id=current_user.tenant_id,
        skip=skip,
        limit=limit,
        store_id=store_id,
        status=status,
        customer_id=customer_id,
        order_id=order_id,
        search=search,
    )


@router.get(
    "/stats",
    response_model=OrderReturnStatsResponse,
    summary="Order Returns Dashboard Stats & Metrics",
)
def get_order_returns_stats(
    store_id: Optional[int] = Query(None, gt=0, description="Filter stats by store ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return OrderReturnService.get_stats(
        db=db,
        tenant_id=current_user.tenant_id,
        store_id=store_id,
    )


@router.get(
    "/{return_id}",
    response_model=OrderReturnResponse,
    summary="Get Return",
)
def get_return(
    return_id: int = Path(
        ...,
        gt=0,
        description="Return ID must be a positive integer",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return OrderReturnService.get_return(
        db=db,
        return_id=return_id,
        tenant_id=current_user.tenant_id,
    )


@router.patch(
    "/{return_id}",
    response_model=OrderReturnResponse,
    dependencies=[Depends(require_operational_write)],
    summary="Update Return",
)
def update_return(
    data: OrderReturnUpdate,
    return_id: int = Path(
        ...,
        gt=0,
        description="Return ID must be a positive integer",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return OrderReturnService.update_return(
        db=db,
        return_id=return_id,
        data=data,
        tenant_id=current_user.tenant_id,
    )


@router.patch(
    "/{return_id}/status",
    response_model=OrderReturnResponse,
    dependencies=[Depends(require_operational_write)],
    summary="Update Return Status",
)
def update_return_status(
    data: OrderReturnStatusUpdate,
    return_id: int = Path(
        ...,
        gt=0,
        description="Return ID must be a positive integer",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return OrderReturnService.update_status(
        db=db,
        return_id=return_id,
        data=data,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
    )


@router.post(
    "/{return_id}/approve",
    response_model=OrderReturnResponse,
    dependencies=[Depends(require_operational_write)],
    summary="Approve Return",
)
def approve_return(
    return_id: int = Path(
        ...,
        gt=0,
        description="Return ID must be a positive integer",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return OrderReturnService.approve_return(
        db=db,
        return_id=return_id,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
    )


@router.post(
    "/{return_id}/reject",
    response_model=OrderReturnResponse,
    dependencies=[Depends(require_operational_write)],
    summary="Reject Return",
)
def reject_return(
    data: OrderReturnRejectRequest,
    return_id: int = Path(
        ...,
        gt=0,
        description="Return ID must be a positive integer",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return OrderReturnService.reject_return(
        db=db,
        return_id=return_id,
        tenant_id=current_user.tenant_id,
        remarks=data.remarks,
        user_id=current_user.id,
    )


@router.post(
    "/{return_id}/complete",
    response_model=OrderReturnResponse,
    dependencies=[Depends(require_operational_write)],
    summary="Complete Return & Restock Inventory",
)
def complete_return(
    return_id: int = Path(
        ...,
        gt=0,
        description="Return ID must be a positive integer",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return OrderReturnService.complete_return(
        db=db,
        return_id=return_id,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
    )


@router.post(
    "/{return_id}/exchange",
    response_model=OrderReturnResponse,
    dependencies=[Depends(require_operational_write)],
    summary="Create Exchange Order for Returned Items",
)
def exchange_return(
    data: OrderReturnExchangeRequest,
    return_id: int = Path(
        ...,
        gt=0,
        description="Return ID must be a positive integer",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return OrderReturnService.process_exchange(
        db=db,
        return_id=return_id,
        data=data,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
    )


@router.get(
    "/{return_id}/slip",
    summary="Printable RMA / Return Slip (JSON or Printable HTML)",
)
def get_return_slip(
    return_id: int = Path(
        ...,
        gt=0,
        description="Return ID must be a positive integer",
    ),
    format: Literal["json", "html"] = Query(
        "json",
        description="Output format: json or html",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    slip = OrderReturnService.get_return_slip(
        db=db,
        return_id=return_id,
        tenant_id=current_user.tenant_id,
    )

    if format == "html":
        rows_html = "".join([
            f"""<tr>
                <td style="padding: 8px; border-bottom: 1px solid #e2e8f0;">{item.product_name}</td>
                <td style="padding: 8px; border-bottom: 1px solid #e2e8f0;">{item.sku or '-'}</td>
                <td style="padding: 8px; border-bottom: 1px solid #e2e8f0; text-align: center;">{item.quantity}</td>
                <td style="padding: 8px; border-bottom: 1px solid #e2e8f0; text-align: right;">₹{item.unit_price:.2f}</td>
                <td style="padding: 8px; border-bottom: 1px solid #e2e8f0; text-align: right;">₹{item.total_amount:.2f}</td>
                <td style="padding: 8px; border-bottom: 1px solid #e2e8f0; text-align: center;">{item.condition}</td>
            </tr>"""
            for item in slip.items
        ])

        html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Return Slip - {slip.return_number}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 40px; color: #1e293b; }}
        .header {{ border-bottom: 2px solid #0f172a; padding-bottom: 16px; margin-bottom: 24px; display: flex; justify-content: space-between; align-items: flex-start; }}
        .badge {{ background-color: #e2e8f0; padding: 4px 10px; border-radius: 9999px; font-size: 12px; font-weight: 600; text-transform: uppercase; }}
        .grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; margin-bottom: 24px; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 16px; }}
        th {{ background: #f8fafc; padding: 10px 8px; border-bottom: 2px solid #cbd5e1; text-align: left; font-size: 13px; }}
        .total-box {{ margin-top: 24px; text-align: right; }}
        .btn-print {{ background: #2563eb; color: white; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; }}
        @media print {{ .no-print {{ display: none; }} }}
    </style>
</head>
<body>
    <div class="no-print" style="margin-bottom: 20px; text-align: right;">
        <button class="btn-print" onclick="window.print()">Print RMA Slip</button>
    </div>
    <div class="header">
        <div>
            <h1 style="margin: 0 0 8px 0; font-size: 24px; font-weight: 700;">RETURN SLIP / RMA</h1>
            <div style="font-size: 14px; color: #64748b;">RMA No: <strong>{slip.return_number}</strong></div>
            <div style="font-size: 14px; color: #64748b;">Date: {slip.created_at.strftime('%Y-%m-%d %H:%M')}</div>
        </div>
        <div style="text-align: right;">
            <span class="badge">{slip.status}</span>
            <div style="margin-top: 8px; font-size: 13px; color: #64748b;">Type: {slip.return_type}</div>
        </div>
    </div>

    <div class="grid">
        <div style="background: #f8fafc; padding: 16px; border-radius: 8px;">
            <h4 style="margin: 0 0 8px 0; color: #475569;">Customer Details</h4>
            <div>Name: <strong>{slip.customer_name or 'N/A'}</strong></div>
            <div>Phone: {slip.customer_phone or 'N/A'}</div>
            <div>Customer ID: #{slip.customer_id}</div>
        </div>
        <div style="background: #f8fafc; padding: 16px; border-radius: 8px;">
            <h4 style="margin: 0 0 8px 0; color: #475569;">Order Information</h4>
            <div>Order ID: #{slip.order_id} ({slip.order_number or ''})</div>
            <div>Store: {slip.store_name or 'Main Store'}</div>
            <div>Reason: <em>{slip.reason}</em></div>
        </div>
    </div>

    <h3 style="margin-top: 24px; margin-bottom: 8px;">Returned Items</h3>
    <table>
        <thead>
            <tr>
                <th>Product</th>
                <th>SKU</th>
                <th style="text-align: center;">Qty</th>
                <th style="text-align: right;">Unit Price</th>
                <th style="text-align: right;">Total</th>
                <th style="text-align: center;">Condition</th>
            </tr>
        </thead>
        <tbody>
            {rows_html}
        </tbody>
    </table>

    <div class="total-box">
        <div style="font-size: 16px; margin-bottom: 4px;">Return Value: <strong>₹{slip.total_amount:.2f}</strong></div>
        <div style="font-size: 18px; color: #16a34a;">Refund / Credit Amount: <strong>₹{slip.refund_amount:.2f}</strong></div>
    </div>
</body>
</html>"""
        return HTMLResponse(content=html_content)

    return slip
