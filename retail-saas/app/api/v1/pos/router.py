from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_operational_write, require_permission
from app.models.pos_shift import POSShift
from app.models.user import User
from app.schemas.pos_shift import (
    POSCashMovementRequest,
    POSCashMovementResponse,
    POSShiftCloseRequest,
    POSShiftCloseResponse,
    POSShiftOpenRequest,
    POSShiftResponse,
    POSZReportResponse,
)
from app.services.pos_shift_service import POSShiftService

router = APIRouter(
    prefix="/pos/shifts",
    tags=["pos-shifts"],
)


@router.post(
    "/open",
    response_model=POSShiftResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_operational_write)],
)
def open_shift(
    payload: POSShiftOpenRequest,
    user: User = Depends(require_permission("pos:shift_manage")),
    db: Session = Depends(get_db),
):
    """
    Opens a new POS shift session for the authenticated cashier at their assigned store.
    Records opening float cash in drawer.
    """
    return POSShiftService(db).open_shift(user, payload)


@router.get(
    "/current",
    response_model=POSShiftResponse,
)
def get_current_shift(
    user: User = Depends(require_permission("pos:shift_manage")),
    db: Session = Depends(get_db),
):
    """
    Retrieves the currently active open shift for the authenticated cashier.
    """
    return POSShiftService(db).get_current_shift(user)


@router.post(
    "/cash-movement",
    response_model=POSCashMovementResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_operational_write)],
)
def record_cash_movement(
    payload: POSCashMovementRequest,
    user: User = Depends(require_permission("pos:shift_manage")),
    db: Session = Depends(get_db),
):
    """
    Records a mid-shift cash drop (deposit to safe), cash payout (petty cash), or cash addition.
    Only permitted against the cashier's active open shift.
    """
    return POSShiftService(db).record_cash_movement(user, payload)


@router.post(
    "/close",
    response_model=POSShiftCloseResponse,
    dependencies=[Depends(require_operational_write)],
)
def close_shift(
    payload: POSShiftCloseRequest,
    user: User = Depends(require_permission("pos:shift_manage")),
    db: Session = Depends(get_db),
):
    """
    Closes the authenticated cashier's active shift.
    Reconciles expected cash against counted cash and calculates variance (over/short/exact).
    """
    return POSShiftService(db).close_shift(user, payload)


@router.get(
    "/{shift_id}/z-report",
    response_model=POSZReportResponse,
)
def get_z_report(
    shift_id: int,
    user: User = Depends(require_permission("pos:shift_manage")),
    db: Session = Depends(get_db),
):
    """
    Generates a comprehensive Z-Report summary for the specified shift.
    Includes opening float, cash sales, cash drops, cash payouts, expected cash, counted cash,
    variance status, transaction volume, and breakdown by payment method.
    """
    return POSShiftService(db).get_z_report(user, shift_id)


@router.get(
    "",
    response_model=List[POSShiftResponse],
)
def list_shifts(
    store_id: Optional[int] = Query(default=None, gt=0),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(require_permission("pos:shift_manage")),
    db: Session = Depends(get_db),
):
    """
    Lists historical POS shifts with optional store and status filtering.
    """
    user_role_name = getattr(user.role, "name", "").lower() if user.role else ""
    query = db.query(POSShift).filter(POSShift.tenant_id == user.tenant_id)

    if user_role_name in ["admin", "owner", "superadmin"]:
        if store_id:
            query = query.filter(POSShift.store_id == store_id)
    elif user_role_name == "manager":
        query = query.filter(POSShift.store_id == user.store_id)
    else:
        # Cashier
        query = query.filter(POSShift.store_id == user.store_id, POSShift.cashier_id == user.id)

    if status_filter:
        query = query.filter(POSShift.status == status_filter)

    query = query.order_by(POSShift.opened_at.desc())
    shifts = query.offset((page - 1) * page_size).limit(page_size).all()
    return [POSShiftResponse.model_validate(s) for s in shifts]

