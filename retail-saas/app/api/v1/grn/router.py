from typing import Literal

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_operational_write, require_permission
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
    dependencies=[Depends(require_operational_write)],
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
    dependencies=[Depends(require_operational_write)],
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
    dependencies=[Depends(require_operational_write)],
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
    summary="Download or Preview Goods Receipt Note (GRN) PDF",
    description="Rendered Goods Receipt Note (GRN) printable PDF document. Delivery mode can be `download` (attachment) or `preview` (inline).",
    responses={
        200: {
            "content": {"application/pdf": {}},
            "description": "Rendered Goods Receipt Note (GRN) printable PDF document.",
        }
    },
)
def print_grn(
    grn_id: int,
    mode: Literal["download", "preview"] = Query(default="download"),
    user: User = Depends(
        require_permission("inventory:read")
    ),
    db: Session = Depends(get_db),
):
    service = GRNService(db)
    grn = service.get(
        tenant_id=user.tenant_id,
        grn_id=grn_id,
    )
    pdf_bytes = service.generate_pdf(
        tenant_id=user.tenant_id,
        grn_id=grn_id,
    )

    disposition = "inline" if mode == "preview" else "attachment"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"{disposition}; filename={grn.grn_number}.pdf"
        },
    )
