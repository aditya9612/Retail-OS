from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional

from app.core.database import get_db
from app.core.security import require_permission
from app.models.user import User
from app.schemas.sale import SaleCreate, SaleResponse
from app.services.sale_service import SaleService

router = APIRouter(
    prefix="/sales",
    tags=["Sales"]
)


@router.post(
    "",
    response_model=SaleResponse,
    status_code=status.HTTP_201_CREATED
)
def create_sale(
    data: SaleCreate,
    user: User = Depends(require_permission("sales:write")),
    db: Session = Depends(get_db)
):
    try:
        return SaleService.create_sale(db, data)
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
    "",
    response_model=List[SaleResponse]
)
def get_sales(
    store_id: Optional[int] = None,
    user: User = Depends(require_permission("sales:read")),
    db: Session = Depends(get_db)
):
    try:
        return SaleService.get_sales(db, store_id)
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
    sale_id: int,
    user: User = Depends(require_permission("sales:read")),
    db: Session = Depends(get_db)
):
    try:
        return SaleService.get_sale(db, sale_id)
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


@router.put(
    "/{sale_id}",
    response_model=SaleResponse
)
def update_sale(
    sale_id: int,
    data: SaleCreate,
    user: User = Depends(require_permission("sales:write")),
    db: Session = Depends(get_db)
):
    try:
        return SaleService.update_sale(db, sale_id, data)
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


@router.delete(
    "/{sale_id}"
)
def delete_sale(
    sale_id: int,
    user: User = Depends(require_permission("sales:write")),
    db: Session = Depends(get_db)
):
    try:
        return SaleService.delete_sale(db, sale_id)
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