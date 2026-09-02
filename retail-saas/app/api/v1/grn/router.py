from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_permission
from app.models.user import User
from app.schemas.grn import (
    GRNCreate,
    GRNResponse,
    GRNHistoryResponse,
    GRNPrintResponse,
)
from app.services.grn_service import GRNService


router = APIRouter(
    prefix="/grn",
    tags=["grn"],
)


@router.post(
    "",
    response_model=GRNResponse,
    status_code=201,
)
def create_grn(
    data: GRNCreate,
    user: User = Depends(
        require_permission("inventory:write")
    ),
    db: Session = Depends(get_db),
):

    return GRNService(db).create(
        tenant_id=user.tenant_id,
        data=data,
    )


@router.get(
    "",
    response_model=list[GRNResponse],
)
def list_grn(
    user: User = Depends(
        require_permission("inventory:read")
    ),
    db: Session = Depends(get_db),
):

    return GRNService(db).list(
        tenant_id=user.tenant_id,
    )


@router.get(
    "/{grn_id}",
    response_model=GRNResponse,
)
def get_grn(
    grn_id: int,
    user: User = Depends(
        require_permission("inventory:read")
    ),
    db: Session = Depends(get_db),
):

    return GRNService(db).get(
        tenant_id=user.tenant_id,
        grn_id=grn_id,
    )


@router.post(
    "/{grn_id}/receive",
    response_model=GRNResponse,
)
def receive_grn(
    grn_id: int,
    user: User = Depends(
        require_permission("inventory:write")
    ),
    db: Session = Depends(get_db),
):

    return GRNService(db).receive(
        tenant_id=user.tenant_id,
        grn_id=grn_id,
    )


@router.post(
    "/{grn_id}/reject",
    response_model=GRNResponse,
)
def reject_grn(
    grn_id: int,
    user: User = Depends(
        require_permission("inventory:write")
    ),
    db: Session = Depends(get_db),
):

    return GRNService(db).reject(
        tenant_id=user.tenant_id,
        grn_id=grn_id,
    )


@router.get(
    "/{grn_id}/history",
    response_model=GRNHistoryResponse,
)
def grn_history(
    grn_id: int,
    user: User = Depends(
        require_permission("inventory:read")
    ),
    db: Session = Depends(get_db),
):

    return GRNService(db).history(
        tenant_id=user.tenant_id,
        grn_id=grn_id,
    )


@router.get(
    "/{grn_id}/print",
    response_model=GRNPrintResponse,
)
def print_grn(
    grn_id: int,
    user: User = Depends(
        require_permission("inventory:read")
    ),
    db: Session = Depends(get_db),
):

    return GRNService(db).print_grn(
        tenant_id=user.tenant_id,
        grn_id=grn_id,
    )
