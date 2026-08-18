from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_permission
from app.models.user import User

from app.schemas.sale import SaleCreate, SaleResponse
from app.services.sale_service import SaleService


router = APIRouter(
    prefix="/sales",
    tags=["Sales"]
)


# 1. CREATE SALE
@router.post(
    "",
    response_model=SaleResponse
)
def create_sale(
    data: SaleCreate,
    user: User = Depends(
        require_permission("sales:write")
    ),
    db: Session = Depends(get_db)
):
    try:
        return SaleService.create_sale(
            db,
            data
        )
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )


# 2. GET ALL SALES
@router.get(
    "",
    response_model=list[SaleResponse]
)
def get_sales(
    store_id: int | None = None,
    user: User = Depends(
        require_permission("sales:read")
    ),
    db: Session = Depends(get_db)
):
    try:
        return SaleService.get_sales(
            db,
            store_id
        )
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )


# 3. GET SINGLE SALE
@router.get(
    "/{sale_id}",
    response_model=SaleResponse
)
def get_sale(
    sale_id: int,
    user: User = Depends(
        require_permission("sales:read")
    ),
    db: Session = Depends(get_db)
):
    try:
        return SaleService.get_sale(
            db,
            sale_id
        )
    except ValueError as e:
        raise HTTPException(
            status_code=404,
            detail=str(e)
        )


# 4. UPDATE SALE
@router.put(
    "/{sale_id}",
    response_model=SaleResponse
)
def update_sale(
    sale_id: int,
    data: SaleCreate,
    user: User = Depends(
        require_permission("sales:write")
    ),
    db: Session = Depends(get_db)
):
    try:
        return SaleService.update_sale(
            db,
            sale_id,
            data
        )
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )
# 5. DELETE SALE
@router.delete(
    "/{sale_id}"
)
def delete_sale(
    sale_id: int,
    user: User = Depends(
        require_permission("sales:write")
    ),
    db: Session = Depends(get_db)
):
    try:
        return SaleService.delete_sale(
            db,
            sale_id
        )
    except ValueError as e:
        raise HTTPException(
            status_code=404,
            detail=str(e)
        )
        