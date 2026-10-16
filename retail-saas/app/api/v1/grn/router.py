from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_operational_write, require_permission
from app.models.user import User
from app.schemas.grn import (
    GRNCreate,
    GRNDeleteResponse,
    GRNHistoryResponse,
    GRNPrintResponse,
    GRNResponse,
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
    dependencies=[Depends(require_operational_write)],
)
def create_grn(
    data: GRNCreate,
    user: User = Depends(require_permission("inventory:write")),
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
    purchase_order_id: Optional[int] = Query(None, description="Filter by purchase order ID"),
    warehouse_id: Optional[int] = Query(None, description="Filter by warehouse ID"),
    status: Optional[str] = Query(None, description="Filter by GRN status (pending, received, rejected)"),
    user: User = Depends(require_permission("inventory:read")),
    db: Session = Depends(get_db),
):
    return GRNService(db).list(
        tenant_id=user.tenant_id,
        purchase_order_id=purchase_order_id,
        warehouse_id=warehouse_id,
        status=status,
    )


@router.get(
    "/{grn_id}",
    response_model=GRNResponse,
)
def get_grn(
    grn_id: int,
    user: User = Depends(require_permission("inventory:read")),
    db: Session = Depends(get_db),
):
    return GRNService(db).get(
        tenant_id=user.tenant_id,
        grn_id=grn_id,
    )


@router.post(
    "/{grn_id}/receive",
    response_model=GRNResponse,
    dependencies=[Depends(require_operational_write)],
)
def receive_grn(
    grn_id: int,
    user: User = Depends(require_permission("inventory:write")),
    db: Session = Depends(get_db),
):
    return GRNService(db).receive(
        tenant_id=user.tenant_id,
        grn_id=grn_id,
    )


@router.post(
    "/{grn_id}/reject",
    response_model=GRNResponse,
    dependencies=[Depends(require_operational_write)],
)
def reject_grn(
    grn_id: int,
    user: User = Depends(require_permission("inventory:write")),
    db: Session = Depends(get_db),
):
    return GRNService(db).reject(
        tenant_id=user.tenant_id,
        grn_id=grn_id,
    )


@router.delete(
    "/{grn_id}",
    response_model=GRNDeleteResponse,
    dependencies=[Depends(require_operational_write)],
)
def delete_grn(
    grn_id: int,
    user: User = Depends(require_permission("inventory:write")),
    db: Session = Depends(get_db),
):
    return GRNService(db).delete(
        tenant_id=user.tenant_id,
        grn_id=grn_id,
    )


@router.get(
    "/{grn_id}/history",
    response_model=GRNHistoryResponse,
)
def grn_history(
    grn_id: int,
    user: User = Depends(require_permission("inventory:read")),
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
    user: User = Depends(require_permission("inventory:read")),
    db: Session = Depends(get_db),
):
    return GRNService(db).print_grn(
        tenant_id=user.tenant_id,
        grn_id=grn_id,
    )
