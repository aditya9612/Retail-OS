from typing import Literal, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.customer_support import (
    CustomerInvoiceDownloadResponse,
    CustomerOrderTrackResponse,
    CustomerReturnInitiateRequest,
    CustomerReturnResponse,
    CustomerSupportQueryRequest,
    CustomerSupportQueryResponse,
    StoreFAQResponse,
)
from app.api.v1.customer_support.widget_ui import get_customer_support_widget_html
from app.models.store import Store
from app.services.customer_support_service import CustomerSupportService

router = APIRouter(prefix="/support", tags=["Customer Support AI Bot"])


@router.get(
    "/stores",
    summary="List active stores for customer support widget",
    description="Returns public list of active retail stores/branches for customers to choose their location.",
)
def list_support_stores(
    tenant_id: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
):
    q = db.query(Store).filter(Store.is_active.is_(True))
    if tenant_id:
        q = q.filter(Store.tenant_id == tenant_id)
    stores = q.order_by(Store.is_main.desc(), Store.id.asc()).all()
    return [
        {
            "id": s.id,
            "name": s.name,
            "city": s.city,
            "address": s.address,
            "phone": s.phone,
            "tenant_id": s.tenant_id,
            "is_main": s.is_main,
        }
        for s in stores
    ]


@router.post(
    "/chat",
    response_model=CustomerSupportQueryResponse,
    summary="24/7 AI Customer Support Chat Query",
    description=(
        "Processes customer support inquiries in Marathi, Hindi, or English. "
        "Intelligently routes and answers order tracking, invoice download links, "
        "self-service returns, store timings, and FAQ."
    ),
)
def customer_support_chat(
    payload: CustomerSupportQueryRequest,
    db: Session = Depends(get_db),
):
    service = CustomerSupportService(
        db=db,
        tenant_id=payload.tenant_id or 1,
        store_id=payload.store_id,
    )
    return service.process_query(
        query=payload.query,
        customer_phone=payload.customer_phone,
        order_number=payload.order_number,
        language=payload.language or "mr",
    )


@router.get(
    "/track-order/{order_number}",
    response_model=CustomerOrderTrackResponse,
    summary="Direct Customer Live Order Tracking",
    description="Tracks an order's fulfillment state, delivery partner, tracking number, and items.",
)
def track_order_direct(
    order_number: str,
    phone: Optional[str] = Query(default=None, description="Optional phone number for security check"),
    tenant_id: int = Query(default=1, description="Tenant organization ID"),
    db: Session = Depends(get_db),
):
    service = CustomerSupportService(db=db, tenant_id=tenant_id)
    return service.track_order(order_number=order_number, customer_phone=phone)


@router.get(
    "/invoice/{order_or_invoice_number}",
    response_model=CustomerInvoiceDownloadResponse,
    summary="Lookup and Download Customer Tax Invoice",
    description="Finds issued sales invoice and generates direct PDF preview / download link.",
)
def get_invoice_direct(
    order_or_invoice_number: str,
    phone: Optional[str] = Query(default=None, description="Optional phone number"),
    tenant_id: int = Query(default=1, description="Tenant organization ID"),
    db: Session = Depends(get_db),
):
    service = CustomerSupportService(db=db, tenant_id=tenant_id)
    return service.get_invoice_download(order_or_invoice=order_or_invoice_number, customer_phone=phone)


@router.post(
    "/returns/initiate",
    response_model=CustomerReturnResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Customer Self-Service Order Return Request",
    description="Validates the 14-day return eligibility window and initiates an official OrderReturn request.",
)
def initiate_return_direct(
    payload: CustomerReturnInitiateRequest,
    tenant_id: int = Query(default=1, description="Tenant organization ID"),
    db: Session = Depends(get_db),
):
    service = CustomerSupportService(db=db, tenant_id=tenant_id)
    return service.initiate_customer_return(
        order_number=payload.order_number,
        customer_phone=payload.customer_phone,
        reason=payload.reason,
        items=payload.items,
        remarks=payload.remarks,
        refund_preference=payload.refund_preference,
    )


@router.get(
    "/faq",
    response_model=StoreFAQResponse,
    summary="Store Support FAQ & Operating Information",
    description="Returns store timings, address, phone, WhatsApp order number, payment modes, and return policy.",
)
def store_faq(
    tenant_id: int = Query(default=1),
    store_id: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
):
    service = CustomerSupportService(db=db, tenant_id=tenant_id, store_id=store_id)
    return service.get_store_faq()


@router.get(
    "/widget",
    summary="Interactive 24/7 AI Customer Support Chat Widget",
    description=(
        "⚠️ **IMPORTANT NOTE:** This endpoint serves a **Full Interactive Web Chat Application**.\n\n"
        "Executing with default settings in Swagger displays raw HTML.\n\n"
        "👉 **To open and test the 24/7 AI Customer Support Bot, open this link directly in your browser:**\n\n"
        "🔗 **[http://127.0.0.1:8000/api/v1/support/widget](http://127.0.0.1:8000/api/v1/support/widget)**\n\n"
        "*(or use the short URL: 🔗 **[http://127.0.0.1:8000/support-widget](http://127.0.0.1:8000/support-widget)**)*\n\n"
        "---\n\n"
        "💡 **JSON Mode:** Select `mode=json` to retrieve direct links and ready-to-use website `iframe_embed_code` in JSON format."
    ),
    responses={
        200: {
            "content": {
                "text/html": {"schema": {"type": "string"}},
                "application/json": {
                    "example": {
                        "status": "active",
                        "widget_url": "http://127.0.0.1:8000/api/v1/support/widget",
                        "short_url": "http://127.0.0.1:8000/support-widget",
                        "iframe_embed_code": '<iframe src="http://127.0.0.1:8000/api/v1/support/widget" style="width:420px;height:620px;"></iframe>',
                    }
                },
            },
            "description": "Interactive HTML Web Widget or JSON URLs.",
        }
    },
)
def support_widget_page(
    mode: Literal["html", "json"] = Query(
        default="html",
        description="Delivery mode: 'html' for full interactive web chat widget or 'json' for direct widget URLs & iframe embed code",
    ),
    request: Request = None,
):
    if mode == "json":
        base_url = str(request.base_url).rstrip("/") if request else "http://127.0.0.1:8000"
        widget_url = f"{base_url}/api/v1/support/widget"
        short_url = f"{base_url}/support-widget"
        return JSONResponse(
            content={
                "status": "active",
                "title": "Retail-OS 24/7 AI Customer Support & Returns Bot",
                "widget_url": widget_url,
                "short_url": short_url,
                "browser_launch_instruction": f"Open {short_url} directly in your browser tab to use the full AI chat interface.",
                "iframe_embed_code": (
                    f'<iframe src="{widget_url}" '
                    f'style="position:fixed;bottom:20px;right:20px;width:420px;height:620px;border:none;'
                    f'border-radius:16px;box-shadow:0 12px 30px rgba(0,0,0,0.35);z-index:99999;" '
                    f'allow="microphone; speech-synthesis" title="Retail-OS 24/7 AI Support"></iframe>'
                ),
            }
        )
    return HTMLResponse(content=get_customer_support_widget_html())
