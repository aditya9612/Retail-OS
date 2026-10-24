from datetime import date
from typing import List, Optional, Union
from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_operational_write, require_permission
from app.models.user import User
from app.schemas.sale import SaleCreate, SaleResponse, SaleUpdate, SaleThermalMode
from app.services.sale_service import SaleService


router = APIRouter(
    prefix="/sales",
    tags=["Sales"]
)


@router.post(
    "",
    response_model=SaleResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_operational_write)],
)
def create_sale(
    data: SaleCreate,
    user: User = Depends(require_permission("sales:write")),
    db: Session = Depends(get_db)
):
    try:
        return SaleService.create_sale(db, data, current_user=user)
    except HTTPException:
        raise
    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(e)
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal Server Error: {str(e)}"
        )


@router.get(
    "",
    response_model=List[SaleResponse]
)
def get_sales(
    store_id: Optional[int] = Query(
        default=None,
        gt=0,
        description="Store ID must be a positive whole number"
    ),
    start_date: Optional[date] = Query(
        default=None,
        description="Filter sales created on or after this date (YYYY-MM-DD)"
    ),
    end_date: Optional[date] = Query(
        default=None,
        description="Filter sales created on or before this date (YYYY-MM-DD)"
    ),
    payment_method: Optional[str] = Query(
        default=None,
        description="Filter by payment method (cash, card, upi, etc.)"
    ),
    payment_status: Optional[str] = Query(
        default=None,
        description="Filter by payment status (paid, pending, etc.)"
    ),
    search: Optional[str] = Query(
        default=None,
        description="Search by sale number or invoice number"
    ),
    page: Optional[int] = Query(
        default=None,
        ge=1,
        description="Page number for pagination"
    ),
    page_size: Optional[int] = Query(
        default=None,
        ge=1,
        le=100,
        description="Number of sales per page"
    ),
    user: User = Depends(require_permission("sales:read")),
    db: Session = Depends(get_db)
):
    try:
        return SaleService.get_sales(
            db,
            tenant_id=user.tenant_id,
            store_id=store_id,
            start_date=start_date,
            end_date=end_date,
            payment_method=payment_method,
            payment_status=payment_status,
            search=search,
            page=page,
            page_size=page_size,
        )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal Server Error: {str(e)}"
        )


@router.get(
    "/{sale_id}",
    response_model=SaleResponse
)
def get_sale(
    sale_id: int = Path(
        ...,
        gt=0,
        description="Sale ID must be a positive whole number"
    ),
    user: User = Depends(require_permission("sales:read")),
    db: Session = Depends(get_db)
):
    try:
        return SaleService.get_sale(db, sale_id, tenant_id=user.tenant_id)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal Server Error: {str(e)}"
        )


@router.get(
    "/{sale_id}/thermal",
    summary="Export Sale POS Thermal Receipt Slip (80mm ESC/POS)",
    description=(
        "Generates an 80mm ESC/POS thermal receipt slip for a sale. "
        "Supports 'preview' (visual receipt PNG image displayed directly in Swagger UI), "
        "'view' (inline browser view with auto-print dialog), "
        "'download' (raw ESC/POS text file attachment), "
        "'pdf' (80mm formatted PDF receipt download), "
        "'html' (styled HTML receipt layout), "
        "'json' (structured JSON response), or "
        "'text' (raw ESC/POS printer stream)."
    ),
    responses={
        200: {
            "model": SaleResponse,
            "description": "Thermal receipt preview (PNG), HTML render, PDF/Text download, or JSON payload.",
            "content": {
                "image/png": {
                    "schema": {"type": "string", "format": "binary"},
                    "description": "Visual 80mm thermal receipt PNG rendered directly in Swagger UI",
                },
                "text/html": {
                    "schema": {"type": "string"},
                    "description": "Styled 80mm thermal receipt HTML for browser preview or print",
                },
                "application/pdf": {
                    "schema": {"type": "string", "format": "binary"},
                    "description": "80mm thermal receipt PDF document",
                },
                "text/plain": {
                    "schema": {"type": "string"},
                    "description": "Raw 80mm ESC/POS thermal printer text stream",
                },
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/SaleResponse"},
                    "description": "Structured JSON receipt payload",
                },
            },
        }
    },
)
def export_sale_thermal(
    sale_id: int = Path(
        ...,
        gt=0,
        description="Sale ID must be a positive integer",
    ),
    mode: SaleThermalMode = Query(
        default=SaleThermalMode.preview,
        description="Thermal receipt output mode: preview (visual image in Swagger UI), view (browser preview with print), download (ESC/POS text file), pdf (80mm PDF), html (raw HTML), json (structured JSON), text (raw ESC/POS text)",
    ),
    user: User = Depends(require_permission("sales:read")),
    db: Session = Depends(get_db),
):
    try:
        return SaleService.export_sale_thermal(
            db=db,
            sale_id=sale_id,
            tenant_id=user.tenant_id,
            mode=mode,
            user=user,
        )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal Server Error: {str(e)}",
        )


@router.put(
    "/{sale_id}",
    response_model=SaleResponse,
    dependencies=[Depends(require_operational_write)],
)
def update_sale(
    data: Union[SaleCreate, SaleUpdate],
    sale_id: int = Path(
        ...,
        gt=0,
        description="Sale ID must be a positive whole number"
    ),
    user: User = Depends(require_permission("sales:write")),
    db: Session = Depends(get_db)
):
    try:
        return SaleService.update_sale(db, sale_id, data, tenant_id=user.tenant_id)
    except HTTPException:
        raise
    except ValueError as e:
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(e)
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal Server Error: {str(e)}"
        )


@router.delete(
    "/{sale_id}",
    dependencies=[Depends(require_operational_write)],
)
def delete_sale(
    sale_id: int = Path(
        ...,
        gt=0,
        description="Sale ID must be a positive whole number"
    ),
    user: User = Depends(require_permission("sales:write")),
    db: Session = Depends(get_db)
):
    try:
        return SaleService.delete_sale(db, sale_id, tenant_id=user.tenant_id)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal Server Error: {str(e)}"
        )
