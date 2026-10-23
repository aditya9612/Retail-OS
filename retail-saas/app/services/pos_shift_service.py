import io
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.exceptions import AppException, ConflictException, ForbiddenException, NotFoundException
from app.models.invoice import Invoice
from app.models.order import Order
from app.models.payment import Payment
from app.models.pos_cash_movement import POSCashMovement
from app.models.pos_held_cart import POSHeldCart
from app.models.pos_shift import POSShift
from app.models.refund import Refund
from app.models.store import Store
from app.models.user import User
from app.schemas.pos_shift import (
    POSCashMovementRequest,
    POSCashMovementResponse,
    POSForceCloseRequest,
    POSShiftCloseRequest,
    POSShiftCloseResponse,
    POSShiftOpenRequest,
    POSShiftResponse,
    POSShiftThermalMode,
    POSShiftThermalResponse,
    POSXReportResponse,
    POSZReportResponse,
)


class POSShiftService:
    def __init__(self, db: Session):
        self.db = db

    def open_shift(self, user: User, data: POSShiftOpenRequest, store_id: Optional[int] = None) -> POSShiftResponse:
        if user.tenant_id is None:
            raise AppException("Tenant context required")

        user_role_name = getattr(user.role, "name", "").lower() if user.role else ""
        is_admin_or_owner = user_role_name in ["admin", "owner", "superadmin"]

        effective_store_id = data.store_id or store_id or user.store_id
        if effective_store_id is None and is_admin_or_owner:
            first_store = (
                self.db.query(Store)
                .filter(
                    Store.tenant_id == user.tenant_id,
                    Store.is_active == True,
                )
                .order_by(Store.id.asc())
                .first()
            )
            if first_store:
                effective_store_id = first_store.id

        if effective_store_id is None:
            raise AppException("User must be assigned to a store to open a POS shift")

        if user.store_id is not None and effective_store_id != user.store_id:
            raise ForbiddenException("Access denied: cannot open shift for another store")

        if user.store_id is None and not is_admin_or_owner:
            raise AppException("User must be assigned to a store to open a POS shift")

        # Verify assigned store exists, is active and belongs to tenant
        store = (
            self.db.query(Store)
            .filter(
                Store.id == effective_store_id,
                Store.tenant_id == user.tenant_id,
                Store.is_active == True,
            )
            .first()
        )
        if not store:
            raise NotFoundException("Assigned store not found or is inactive")

        # If register_id specified, check if that physical register is already occupied
        if data.register_id:
            reg_existing = (
                self.db.query(POSShift)
                .filter(
                    POSShift.tenant_id == user.tenant_id,
                    POSShift.store_id == effective_store_id,
                    POSShift.register_id == data.register_id,
                    POSShift.status == "open",
                )
                .with_for_update()
                .first()
            )
            if reg_existing:
                raise ConflictException(f"Register '{data.register_id}' already has an active open shift")

        # Prevent concurrent or duplicate open shifts for this cashier
        existing = (
            self.db.query(POSShift)
            .filter(
                POSShift.tenant_id == user.tenant_id,
                POSShift.cashier_id == user.id,
                POSShift.status == "open",
            )
            .with_for_update()
            .first()
        )
        if existing:
            raise ConflictException("An active open shift already exists for this cashier")

        shift = POSShift(
            tenant_id=user.tenant_id,
            store_id=effective_store_id,
            cashier_id=user.id,
            register_id=data.register_id,
            opened_at=datetime.utcnow(),
            status="open",
            opening_cash_float=data.opening_cash_float,
            opening_denominations=data.denominations,
            notes=data.notes,
        )
        self.db.add(shift)
        self.db.commit()
        self.db.refresh(shift)

        return POSShiftResponse.model_validate(shift)

    def get_current_shift(self, user: User, store_id: Optional[int] = None) -> POSShiftResponse:
        user_role_name = getattr(user.role, "name", "").lower() if user.role else ""
        is_admin_or_owner = user_role_name in ["admin", "owner", "superadmin"]
        is_manager = user_role_name == "manager"

        if user.tenant_id is None:
            raise NotFoundException("No active open shift found for this cashier or store")

        # First check user's own active open shift
        shift = (
            self.db.query(POSShift)
            .filter(
                POSShift.tenant_id == user.tenant_id,
                POSShift.cashier_id == user.id,
                POSShift.status == "open",
            )
            .order_by(POSShift.opened_at.desc())
            .first()
        )
        if shift:
            return POSShiftResponse.model_validate(shift)

        # If user has no active shift and is admin/owner/manager searching by store_id
        if (is_admin_or_owner or is_manager) and (store_id is not None or user.store_id is not None):
            eff_store = store_id or user.store_id
            store_shift = (
                self.db.query(POSShift)
                .filter(
                    POSShift.tenant_id == user.tenant_id,
                    POSShift.store_id == eff_store,
                    POSShift.status == "open",
                )
                .order_by(POSShift.opened_at.desc())
                .first()
            )
            if store_shift:
                return POSShiftResponse.model_validate(store_shift)

        raise NotFoundException("No active open shift found for this cashier")

    def record_cash_movement(self, user: User, data: POSCashMovementRequest) -> POSCashMovementResponse:
        if user.tenant_id is None:
            raise NotFoundException("No active open shift found for this cashier")

        shift = (
            self.db.query(POSShift)
            .filter(
                POSShift.tenant_id == user.tenant_id,
                POSShift.cashier_id == user.id,
                POSShift.status == "open",
            )
            .with_for_update()
            .first()
        )
        if not shift:
            raise NotFoundException("No active open shift found for this cashier")

        # Validate drawer balance for drops and payouts to prevent negative cash
        if data.movement_type in ["CASH_DROP", "CASH_PAYOUT"]:
            financials = self._calculate_shift_financials(shift, end_time=datetime.utcnow())
            current_drawer_cash = (
                shift.opening_cash_float
                + financials["cash_sales"]
                + financials["cash_additions"]
                - financials["cash_drops"]
                - financials["cash_payouts"]
                - financials["cash_refunds"]
            )
            if data.amount > current_drawer_cash:
                raise AppException(
                    f"Insufficient drawer cash: available cash is ₹{current_drawer_cash:.2f}, requested {data.movement_type} is ₹{data.amount:.2f}"
                )

        reason_text = data.reason
        if data.authorized_by:
            reason_text = f"{reason_text} [Auth by User: {data.authorized_by}]"

        movement = POSCashMovement(
            tenant_id=user.tenant_id,
            shift_id=shift.id,
            movement_type=data.movement_type.upper(),
            amount=data.amount,
            reason=reason_text,
            created_by=user.id,
        )
        self.db.add(movement)
        self.db.commit()
        self.db.refresh(movement)

        return POSCashMovementResponse.model_validate(movement)

    def close_shift(self, user: User, data: POSShiftCloseRequest) -> POSShiftCloseResponse:
        if user.tenant_id is None:
            raise NotFoundException("No active open shift found to close")

        shift = (
            self.db.query(POSShift)
            .filter(
                POSShift.tenant_id == user.tenant_id,
                POSShift.cashier_id == user.id,
                POSShift.status == "open",
            )
            .with_for_update()
            .first()
        )
        if not shift:
            raise NotFoundException("No active open shift found to close")

        now_ts = datetime.utcnow()
        financials = self._calculate_shift_financials(shift, end_time=now_ts)

        cash_sales = financials["cash_sales"]
        cash_additions = financials["cash_additions"]
        cash_drops = financials["cash_drops"]
        cash_payouts = financials["cash_payouts"]
        cash_refunds = financials["cash_refunds"]

        # Expected cash formula
        expected_cash = (
            shift.opening_cash_float
            + cash_sales
            + cash_additions
            - cash_drops
            - cash_payouts
            - cash_refunds
        )
        cash_variance = data.closing_cash_counted - expected_cash

        variance_status = "exact" if cash_variance == Decimal("0.00") else ("over" if cash_variance > Decimal("0.00") else "short")

        shift.closed_at = now_ts
        shift.closed_by = user.id
        shift.status = "closed"
        shift.closing_cash_counted = data.closing_cash_counted
        shift.closing_denominations = data.denominations
        shift.expected_cash = expected_cash
        shift.cash_variance = cash_variance

        # Check for unfinalized held carts
        held_carts_count = (
            self.db.query(POSHeldCart)
            .filter(
                POSHeldCart.tenant_id == user.tenant_id,
                POSHeldCart.store_id == shift.store_id,
                POSHeldCart.user_id == user.id,
                POSHeldCart.status == "held",
            )
            .count()
        )

        notes_to_add = data.notes or ""
        if held_carts_count > 0:
            held_note = f"[Notice: {held_carts_count} held cart(s) remained unfinalized at shift close]"
            notes_to_add = f"{notes_to_add}\n{held_note}".strip() if notes_to_add else held_note

        if notes_to_add:
            shift.notes = (f"{shift.notes}\n{notes_to_add}").strip() if shift.notes else notes_to_add

        self.db.commit()
        self.db.refresh(shift)

        return POSShiftCloseResponse(
            shift=POSShiftResponse.model_validate(shift),
            expected_cash=expected_cash,
            closing_cash_counted=data.closing_cash_counted,
            cash_variance=cash_variance,
            variance_status=variance_status,
            opening_cash_float=shift.opening_cash_float,
            cash_sales=cash_sales,
            cash_additions=cash_additions,
            cash_drops=cash_drops,
            cash_payouts=cash_payouts,
            cash_refunds=cash_refunds,
            register_id=shift.register_id,
            closing_denominations=data.denominations,
            closed_by=user.id,
            held_carts_warning=held_carts_count if held_carts_count > 0 else None,
        )

    def force_close_shift(self, user: User, shift_id: int, data: POSForceCloseRequest) -> POSShiftCloseResponse:
        if user.tenant_id is None:
            raise AppException("Tenant context required")

        user_role_name = getattr(user.role, "name", "").lower() if user.role else ""
        is_admin_or_owner = user_role_name in ["admin", "owner", "superadmin"]
        is_manager = user_role_name == "manager"

        if not (is_admin_or_owner or is_manager):
            raise ForbiddenException("Only managers or administrators can force close a shift")

        shift = (
            self.db.query(POSShift)
            .filter(
                POSShift.id == shift_id,
                POSShift.tenant_id == user.tenant_id,
            )
            .with_for_update()
            .first()
        )
        if not shift:
            raise NotFoundException("Shift not found")

        if is_manager and shift.store_id != user.store_id:
            raise ForbiddenException("Managers can only force close shifts for their assigned store")

        if shift.status != "open":
            raise ConflictException(f"Cannot force close shift: shift is already {shift.status}")

        now_ts = datetime.utcnow()
        financials = self._calculate_shift_financials(shift, end_time=now_ts)

        cash_sales = financials["cash_sales"]
        cash_additions = financials["cash_additions"]
        cash_drops = financials["cash_drops"]
        cash_payouts = financials["cash_payouts"]
        cash_refunds = financials["cash_refunds"]

        expected_cash = (
            shift.opening_cash_float
            + cash_sales
            + cash_additions
            - cash_drops
            - cash_payouts
            - cash_refunds
        )
        cash_variance = data.closing_cash_counted - expected_cash
        variance_status = "exact" if cash_variance == Decimal("0.00") else ("over" if cash_variance > Decimal("0.00") else "short")

        shift.closed_at = now_ts
        shift.status = "closed"
        shift.closed_by = user.id
        shift.closing_cash_counted = data.closing_cash_counted
        shift.closing_denominations = data.denominations
        shift.expected_cash = expected_cash
        shift.cash_variance = cash_variance

        reason_note = f"[FORCE CLOSED by Manager {user.full_name} (ID: {user.id}): {data.reason}]"
        if data.notes:
            reason_note += f" - {data.notes}"
        shift.notes = (f"{shift.notes}\n{reason_note}").strip() if shift.notes else reason_note

        self.db.commit()
        self.db.refresh(shift)

        return POSShiftCloseResponse(
            shift=POSShiftResponse.model_validate(shift),
            expected_cash=expected_cash,
            closing_cash_counted=data.closing_cash_counted,
            cash_variance=cash_variance,
            variance_status=variance_status,
            opening_cash_float=shift.opening_cash_float,
            cash_sales=cash_sales,
            cash_additions=cash_additions,
            cash_drops=cash_drops,
            cash_payouts=cash_payouts,
            cash_refunds=cash_refunds,
            register_id=shift.register_id,
            closing_denominations=data.denominations,
            closed_by=user.id,
            held_carts_warning=None,
        )

    def get_x_report(self, user: User, shift_id: int) -> POSXReportResponse:
        if user.tenant_id is None:
            raise AppException("Tenant context required")

        shift = (
            self.db.query(POSShift)
            .filter(
                POSShift.id == shift_id,
                POSShift.tenant_id == user.tenant_id,
            )
            .first()
        )
        if not shift:
            raise NotFoundException("Shift not found")

        # Authorization checks
        user_role_name = getattr(user.role, "name", "").lower() if user.role else ""
        is_admin_or_owner = user_role_name in ["admin", "owner", "superadmin"]

        if not is_admin_or_owner:
            if user_role_name == "manager":
                if shift.store_id != user.store_id:
                    raise ForbiddenException("Managers can only view reports for their assigned store")
            else:
                if shift.store_id != user.store_id or shift.cashier_id != user.id:
                    raise ForbiddenException("Cashiers can only view their own shift reports")

        now_ts = datetime.utcnow()
        financials = self._calculate_shift_financials(shift, end_time=now_ts)

        store = self.db.query(Store).filter(Store.id == shift.store_id).first()
        cashier = self.db.query(User).filter(User.id == shift.cashier_id).first()

        current_drawer_cash = (
            shift.opening_cash_float
            + financials["cash_sales"]
            + financials["cash_additions"]
            - financials["cash_drops"]
            - financials["cash_payouts"]
            - financials["cash_refunds"]
        )

        movements = (
            self.db.query(POSCashMovement)
            .filter(POSCashMovement.shift_id == shift.id)
            .order_by(POSCashMovement.created_at.asc())
            .all()
        )

        return POSXReportResponse(
            shift_id=shift.id,
            status=shift.status,
            tenant_id=shift.tenant_id,
            store_id=shift.store_id,
            store_name=store.name if store else "Store",
            cashier_id=shift.cashier_id,
            cashier_name=cashier.full_name if cashier else "Cashier",
            register_id=shift.register_id,
            opened_at=shift.opened_at,
            current_time=now_ts,
            opening_cash_float=shift.opening_cash_float,
            cash_sales=financials["cash_sales"],
            cash_additions=financials["cash_additions"],
            cash_drops=financials["cash_drops"],
            cash_payouts=financials["cash_payouts"],
            cash_refunds=financials["cash_refunds"],
            current_drawer_cash=current_drawer_cash,
            total_transactions=financials["total_transactions"],
            total_sales_amount=financials["total_sales_amount"],
            payment_method_breakdown=financials["payment_method_breakdown"],
            movements=[POSCashMovementResponse.model_validate(m) for m in movements],
            notes=shift.notes,
        )

    def get_z_report(self, user: User, shift_id: int) -> POSZReportResponse:
        if user.tenant_id is None:
            raise AppException("Tenant context required")

        shift = (
            self.db.query(POSShift)
            .filter(
                POSShift.id == shift_id,
                POSShift.tenant_id == user.tenant_id,
            )
            .first()
        )
        if not shift:
            raise NotFoundException("Shift not found")

        # Authorization checks
        user_role_name = getattr(user.role, "name", "").lower() if user.role else ""
        is_admin_or_owner = user_role_name in ["admin", "owner", "superadmin"]

        if not is_admin_or_owner:
            if user_role_name == "manager":
                if shift.store_id != user.store_id:
                    raise ForbiddenException("Managers can only view Z-reports for their assigned store")
            else:
                # Cashier or staff
                if shift.store_id != user.store_id or shift.cashier_id != user.id:
                    raise ForbiddenException("Cashiers can only view their own shift Z-reports")

        end_time = shift.closed_at or datetime.utcnow()
        financials = self._calculate_shift_financials(shift, end_time=end_time)

        store = self.db.query(Store).filter(Store.id == shift.store_id).first()
        cashier = self.db.query(User).filter(User.id == shift.cashier_id).first()
        closer = self.db.query(User).filter(User.id == shift.closed_by).first() if shift.closed_by else None

        expected_cash = (
            shift.expected_cash
            if shift.expected_cash is not None
            else (
                shift.opening_cash_float
                + financials["cash_sales"]
                + financials["cash_additions"]
                - financials["cash_drops"]
                - financials["cash_payouts"]
                - financials["cash_refunds"]
            )
        )

        cash_variance = shift.cash_variance
        if cash_variance is not None:
            variance_status = "exact" if cash_variance == Decimal("0.00") else ("over" if cash_variance > Decimal("0.00") else "short")
        else:
            variance_status = "pending"

        movements = (
            self.db.query(POSCashMovement)
            .filter(POSCashMovement.shift_id == shift.id)
            .order_by(POSCashMovement.created_at.asc())
            .all()
        )

        return POSZReportResponse(
            shift_id=shift.id,
            status=shift.status,
            tenant_id=shift.tenant_id,
            store_id=shift.store_id,
            store_name=store.name if store else "Store",
            cashier_id=shift.cashier_id,
            cashier_name=cashier.full_name if cashier else "Cashier",
            register_id=shift.register_id,
            opened_at=shift.opened_at,
            closed_at=shift.closed_at,
            closed_by=shift.closed_by,
            closed_by_name=closer.full_name if closer else None,
            opening_cash_float=shift.opening_cash_float,
            opening_denominations=shift.opening_denominations,
            cash_sales=financials["cash_sales"],
            cash_additions=financials["cash_additions"],
            cash_drops=financials["cash_drops"],
            cash_payouts=financials["cash_payouts"],
            cash_refunds=financials["cash_refunds"],
            expected_cash=expected_cash,
            closing_cash_counted=shift.closing_cash_counted,
            closing_denominations=shift.closing_denominations,
            cash_variance=cash_variance,
            variance_status=variance_status,
            total_transactions=financials["total_transactions"],
            total_sales_amount=financials["total_sales_amount"],
            payment_method_breakdown=financials["payment_method_breakdown"],
            movements=[POSCashMovementResponse.model_validate(m) for m in movements],
            notes=shift.notes,
        )

    def _calculate_shift_financials(self, shift: POSShift, end_time: datetime) -> Dict[str, Any]:
        # Check payments linked directly to this shift, or fallback to Order.user_id matching shift.cashier_id
        shift_payments = (
            self.db.query(Payment)
            .filter(
                Payment.tenant_id == shift.tenant_id,
                Payment.shift_id == shift.id,
                Payment.status.in_(["completed", "success"]),
            )
            .all()
        )

        if shift_payments:
            payments = shift_payments
        else:
            payments = (
                self.db.query(Payment)
                .join(Order, Payment.order_id == Order.id)
                .filter(
                    Payment.tenant_id == shift.tenant_id,
                    Order.store_id == shift.store_id,
                    Order.user_id == shift.cashier_id,
                    Payment.status.in_(["completed", "success"]),
                    Payment.created_at >= shift.opened_at,
                    Payment.created_at <= end_time,
                    Order.status != "cancelled",
                )
                .all()
            )

        cash_sales = Decimal("0.00")
        total_sales_amount = Decimal("0.00")
        payment_method_breakdown = defaultdict(lambda: Decimal("0.00"))
        distinct_order_ids = set()

        for p in payments:
            method = (p.payment_method or "other").strip().lower()
            amt = Decimal(str(p.amount or 0))
            total_sales_amount += amt
            payment_method_breakdown[method] += amt
            distinct_order_ids.add(p.order_id)
            if method == "cash":
                cash_sales += amt

        # Query cash movements for this shift
        movements = (
            self.db.query(POSCashMovement)
            .filter(POSCashMovement.shift_id == shift.id)
            .all()
        )

        cash_drops = Decimal("0.00")
        cash_payouts = Decimal("0.00")
        cash_additions = Decimal("0.00")

        for m in movements:
            amt = Decimal(str(m.amount or 0))
            m_type = m.movement_type.upper()
            if m_type == "CASH_DROP":
                cash_drops += amt
            elif m_type == "CASH_PAYOUT":
                cash_payouts += amt
            elif m_type == "CASH_IN":
                cash_additions += amt

        # Query cash refunds linked to this shift, or fallback to refunds within shift window
        shift_refunds = (
            self.db.query(Refund)
            .filter(
                Refund.tenant_id == shift.tenant_id,
                Refund.shift_id == shift.id,
                func.lower(Refund.refund_method) == "cash",
                Refund.status.in_(["approved", "completed"]),
            )
            .all()
        )

        if shift_refunds:
            refunds = shift_refunds
        else:
            refunds = (
                self.db.query(Refund)
                .join(Invoice, Refund.invoice_id == Invoice.id)
                .join(Order, Invoice.order_id == Order.id)
                .filter(
                    Refund.tenant_id == shift.tenant_id,
                    Order.store_id == shift.store_id,
                    func.lower(Refund.refund_method) == "cash",
                    Refund.status.in_(["approved", "completed"]),
                    Refund.created_at >= shift.opened_at,
                    Refund.created_at <= end_time,
                )
                .all()
            )

        cash_refunds = sum((Decimal(str(r.refund_amount or 0)) for r in refunds), Decimal("0.00"))

        return {
            "cash_sales": cash_sales,
            "total_sales_amount": total_sales_amount,
            "total_transactions": len(distinct_order_ids),
            "payment_method_breakdown": dict(payment_method_breakdown),
            "cash_drops": cash_drops,
            "cash_payouts": cash_payouts,
            "cash_additions": cash_additions,
            "cash_refunds": cash_refunds,
        }

    def _generate_thermal_text(self, zrep: POSZReportResponse) -> str:
        lines = []
        lines.append("=" * 42)
        lines.append(f"{zrep.store_name.center(42)}")
        lines.append("POS SHIFT Z-REPORT".center(42))
        lines.append("=" * 42)
        lines.append(f"Shift ID    : #{zrep.shift_id}")
        if zrep.register_id:
            lines.append(f"Register    : {zrep.register_id}")
        lines.append(f"Cashier     : {zrep.cashier_name} (ID: {zrep.cashier_id})")
        lines.append(f"Status      : {zrep.status.upper()}")
        lines.append(f"Opened At   : {zrep.opened_at.strftime('%Y-%m-%d %H:%M:%S')}")
        closed_str = zrep.closed_at.strftime("%Y-%m-%d %H:%M:%S") if zrep.closed_at else "In Progress"
        lines.append(f"Closed At   : {closed_str}")
        if zrep.closed_by_name:
            lines.append(f"Closed By   : {zrep.closed_by_name}")
        lines.append("-" * 42)
        lines.append("CASH DRAWER RECONCILIATION".center(42))
        lines.append("-" * 42)
        lines.append(f"Opening Float        : Rs. {zrep.opening_cash_float:>12.2f}")
        lines.append(f"Cash Sales (+)       : Rs. {zrep.cash_sales:>12.2f}")
        lines.append(f"Cash In (+)          : Rs. {zrep.cash_additions:>12.2f}")
        lines.append(f"Cash Drops (-)       : Rs. {zrep.cash_drops:>12.2f}")
        lines.append(f"Cash Payouts (-)     : Rs. {zrep.cash_payouts:>12.2f}")
        lines.append(f"Cash Refunds (-)     : Rs. {zrep.cash_refunds:>12.2f}")
        lines.append("-" * 42)
        lines.append(f"EXPECTED CASH        : Rs. {zrep.expected_cash:>12.2f}")
        counted_str = f"Rs. {zrep.closing_cash_counted:>12.2f}" if zrep.closing_cash_counted is not None else "PENDING"
        lines.append(f"COUNTED CASH         : {counted_str}")
        variance_str = f"Rs. {zrep.cash_variance:>12.2f}" if zrep.cash_variance is not None else "PENDING"
        lines.append(f"CASH VARIANCE        : {variance_str}")
        lines.append(f"VARIANCE STATUS      : {zrep.variance_status.upper()}")
        lines.append("-" * 42)
        lines.append("SALES SUMMARY".center(42))
        lines.append("-" * 42)
        lines.append(f"Total Transactions   : {zrep.total_transactions:>16}")
        lines.append(f"Total Sales Amount   : Rs. {zrep.total_sales_amount:>12.2f}")
        if zrep.payment_method_breakdown:
            lines.append("Payment Breakdown:")
            for m, a in zrep.payment_method_breakdown.items():
                lines.append(f"  - {m.upper():<12}: Rs. {a:>12.2f}")
        if zrep.closing_denominations:
            lines.append("-" * 42)
            lines.append("CLOSING DENOMINATIONS".center(42))
            lines.append("-" * 42)
            for note, cnt in sorted(zrep.closing_denominations.items(), key=lambda x: Decimal(x[0]), reverse=True):
                subtot = Decimal(note) * Decimal(cnt)
                lines.append(f"  Rs. {note:>4} x {cnt:>3} = Rs. {subtot:>8.2f}")
        lines.append("=" * 42)
        lines.append("END OF Z-REPORT".center(42))
        lines.append("=" * 42)
        lines.append("\n\n\n\x1b\x69")  # ESC/POS cut paper command
        return "\n".join(lines)

    def _generate_thermal_html(self, zrep: POSZReportResponse, auto_print: bool = False) -> str:
        closed_str = zrep.closed_at.strftime("%Y-%m-%d %H:%M:%S") if zrep.closed_at else "In Progress"
        opened_str = zrep.opened_at.strftime("%Y-%m-%d %H:%M:%S")
        counted_str = f"Rs. {zrep.closing_cash_counted:.2f}" if zrep.closing_cash_counted is not None else "PENDING"
        variance_str = f"Rs. {zrep.cash_variance:.2f}" if zrep.cash_variance is not None else "PENDING"

        status_color = "#16a34a" if zrep.variance_status == "balanced" else ("#dc2626" if zrep.variance_status == "shortage" else "#2563eb")

        pm_rows = ""
        if zrep.payment_method_breakdown:
            pm_rows = '<div class="divider"></div><div class="section-title">PAYMENT BREAKDOWN</div><div class="divider"></div>'
            for m, a in zrep.payment_method_breakdown.items():
                pm_rows += f'<div class="line-row"><span class="line-label">{m.upper()}</span><span class="line-val">Rs. {a:.2f}</span></div>'

        denom_rows = ""
        if zrep.closing_denominations:
            denom_rows = '<div class="divider"></div><div class="section-title">CLOSING DENOMINATIONS</div><div class="divider"></div>'
            for note, cnt in sorted(zrep.closing_denominations.items(), key=lambda x: Decimal(x[0]), reverse=True):
                subtot = Decimal(note) * Decimal(cnt)
                denom_rows += f'<div class="line-row"><span class="line-label">Rs. {note} x {cnt}</span><span class="line-val">Rs. {subtot:.2f}</span></div>'

        register_html = f'<div class="line-row"><span class="line-label">Register</span><span class="line-val">{zrep.register_id}</span></div>' if zrep.register_id else ""
        closed_by_html = f'<div class="line-row"><span class="line-label">Closed By</span><span class="line-val">{zrep.closed_by_name}</span></div>' if zrep.closed_by_name else ""
        auto_print_script = "<script>window.onload = function() { window.print(); };</script>" if auto_print else ""

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Z-Report #{zrep.shift_id} - Thermal Slip</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: 'Courier New', Courier, monospace; }}
  body {{ background: #f1f5f9; display: flex; flex-direction: column; align-items: center; padding: 24px 12px; min-height: 100vh; }}
  .actions-bar {{ margin-bottom: 16px; display: flex; gap: 10px; }}
  .btn-print {{ background: #0f172a; color: #fff; border: none; padding: 8px 16px; border-radius: 6px; font-weight: bold; font-size: 13px; cursor: pointer; }}
  .btn-print:hover {{ background: #334155; }}
  .receipt-box {{ background: #ffffff; width: 340px; padding: 20px 18px; box-shadow: 0 4px 16px rgba(0,0,0,0.1); border-radius: 4px; color: #000; font-size: 12px; line-height: 1.4; }}
  .header {{ text-align: center; border-bottom: 2px dashed #000; padding-bottom: 10px; margin-bottom: 10px; }}
  .store-title {{ font-size: 16px; font-weight: 900; text-transform: uppercase; }}
  .report-title {{ font-size: 13px; font-weight: 800; margin-top: 2px; }}
  .divider {{ border-top: 1px dashed #444; margin: 8px 0; }}
  .line-row {{ display: flex; justify-content: space-between; margin-bottom: 3px; }}
  .line-label {{ color: #333; }}
  .line-val {{ font-weight: 700; text-align: right; }}
  .section-title {{ font-weight: 900; text-align: center; font-size: 11px; letter-spacing: 0.5px; margin: 6px 0 4px 0; }}
  .badge {{ display: inline-block; padding: 1px 6px; border-radius: 3px; font-weight: 800; font-size: 10px; color: #fff; background: {status_color}; text-transform: uppercase; }}
  .footer {{ text-align: center; border-top: 2px dashed #000; margin-top: 12px; padding-top: 8px; font-size: 11px; color: #555; }}
  @media print {{
    body {{ background: #fff; padding: 0; }}
    .actions-bar {{ display: none !important; }}
    .receipt-box {{ box-shadow: none; width: 100%; max-width: 300px; padding: 4px; margin: 0; border: none; }}
  }}
</style>
{auto_print_script}
</head>
<body>
<div class="actions-bar">
  <button class="btn-print" onclick="window.print()">🖨️ Print Slip</button>
</div>
<div class="receipt-box">
  <div class="header">
    <div class="store-title">{zrep.store_name}</div>
    <div class="report-title">POS SHIFT Z-REPORT</div>
    <div style="font-size: 11px; color: #666; margin-top: 2px;">Official Drawer Settlement Slip</div>
  </div>
  <div class="line-row"><span class="line-label">Shift ID</span><span class="line-val">#{zrep.shift_id}</span></div>
  {register_html}
  <div class="line-row"><span class="line-label">Cashier</span><span class="line-val">{zrep.cashier_name} (#{zrep.cashier_id})</span></div>
  <div class="line-row"><span class="line-label">Status</span><span class="line-val">{zrep.status.upper()}</span></div>
  <div class="line-row"><span class="line-label">Opened At</span><span class="line-val">{opened_str}</span></div>
  <div class="line-row"><span class="line-label">Closed At</span><span class="line-val">{closed_str}</span></div>
  {closed_by_html}
  
  <div class="divider"></div>
  <div class="section-title">CASH DRAWER RECONCILIATION</div>
  <div class="divider"></div>
  <div class="line-row"><span class="line-label">Opening Float</span><span class="line-val">Rs. {zrep.opening_cash_float:.2f}</span></div>
  <div class="line-row"><span class="line-label">Cash Sales (+)</span><span class="line-val">Rs. {zrep.cash_sales:.2f}</span></div>
  <div class="line-row"><span class="line-label">Cash In (+)</span><span class="line-val">Rs. {zrep.cash_additions:.2f}</span></div>
  <div class="line-row"><span class="line-label">Cash Drops (-)</span><span class="line-val">Rs. {zrep.cash_drops:.2f}</span></div>
  <div class="line-row"><span class="line-label">Cash Payouts (-)</span><span class="line-val">Rs. {zrep.cash_payouts:.2f}</span></div>
  <div class="line-row"><span class="line-label">Cash Refunds (-)</span><span class="line-val">Rs. {zrep.cash_refunds:.2f}</span></div>
  <div class="divider"></div>
  <div class="line-row" style="font-weight: bold;"><span class="line-label">EXPECTED CASH</span><span class="line-val">Rs. {zrep.expected_cash:.2f}</span></div>
  <div class="line-row" style="font-weight: bold;"><span class="line-label">COUNTED CASH</span><span class="line-val">{counted_str}</span></div>
  <div class="line-row" style="font-weight: bold;"><span class="line-label">CASH VARIANCE</span><span class="line-val">{variance_str}</span></div>
  <div class="line-row"><span class="line-label">Variance Status</span><span class="badge">{zrep.variance_status.upper()}</span></div>
  
  <div class="divider"></div>
  <div class="section-title">SALES SUMMARY</div>
  <div class="divider"></div>
  <div class="line-row"><span class="line-label">Total Transactions</span><span class="line-val">{zrep.total_transactions}</span></div>
  <div class="line-row"><span class="line-label">Total Sales Amount</span><span class="line-val">Rs. {zrep.total_sales_amount:.2f}</span></div>
  
  {pm_rows}
  {denom_rows}
  
  <div class="footer">
    *** END OF Z-REPORT ***<br>
    Retain for accounting & tax audit
  </div>
</div>
</body>
</html>"""

    def _generate_thermal_image(self, zrep: POSZReportResponse) -> bytes:
        from PIL import Image, ImageDraw, ImageFont

        width = 576  # Standard 80mm printable width at 203 DPI

        num_pm = len(zrep.payment_method_breakdown) if zrep.payment_method_breakdown else 0
        num_denom = len(zrep.closing_denominations) if zrep.closing_denominations else 0
        est_height = 700 + (num_pm * 24) + (num_denom * 24)
        if num_pm > 0:
            est_height += 30
        if num_denom > 0:
            est_height += 30

        img = Image.new("RGB", (width, est_height), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)

        try:
            font_title = ImageFont.truetype("arialbd.ttf", 22)
            font_head = ImageFont.truetype("arialbd.ttf", 16)
            font_bold = ImageFont.truetype("arialbd.ttf", 14)
            font_regular = ImageFont.truetype("arial.ttf", 13)
            font_small = ImageFont.truetype("arial.ttf", 11)
        except Exception:
            font_title = font_head = font_bold = font_regular = font_small = ImageFont.load_default()

        # Draw outer subtle border
        draw.rectangle([(6, 6), (width - 7, est_height - 7)], outline=(200, 200, 200), width=1)

        y = 20

        # Store Title centered
        store_txt = zrep.store_name.upper()
        bbox = draw.textbbox((0, 0), store_txt, font=font_title)
        draw.text(((width - (bbox[2] - bbox[0])) // 2, y), store_txt, font=font_title, fill=(0, 0, 0))
        y += 28

        # Report Header centered
        rep_txt = "POS SHIFT Z-REPORT"
        bbox = draw.textbbox((0, 0), rep_txt, font=font_head)
        draw.text(((width - (bbox[2] - bbox[0])) // 2, y), rep_txt, font=font_head, fill=(0, 0, 0))
        y += 24

        sub_txt = "OFFICIAL DRAWER SETTLEMENT SLIP"
        bbox = draw.textbbox((0, 0), sub_txt, font=font_small)
        draw.text(((width - (bbox[2] - bbox[0])) // 2, y), sub_txt, font=font_small, fill=(100, 100, 100))
        y += 24

        def draw_dashed_line(draw_ctx, cur_y, w):
            for x in range(20, w - 20, 10):
                draw_ctx.line([(x, cur_y), (x + 5, cur_y)], fill=(80, 80, 80), width=1)

        draw_dashed_line(draw, y, width)
        y += 12

        def draw_kv(label: str, val: str, font_l=font_regular, font_r=font_bold, fill_l=(70, 70, 70), fill_r=(0, 0, 0)):
            nonlocal y
            draw.text((24, y), label, font=font_l, fill=fill_l)
            r_bbox = draw.textbbox((0, 0), val, font=font_r)
            r_w = r_bbox[2] - r_bbox[0]
            draw.text((width - 24 - r_w, y), val, font=font_r, fill=fill_r)
            y += 22

        # Metadata
        draw_kv("Shift ID", f"#{zrep.shift_id}")
        if zrep.register_id:
            draw_kv("Register", str(zrep.register_id))
        draw_kv("Cashier", f"{zrep.cashier_name} (#{zrep.cashier_id})")
        draw_kv("Shift Status", zrep.status.upper())
        draw_kv("Opened At", zrep.opened_at.strftime("%Y-%m-%d %H:%M:%S"))
        closed_str = zrep.closed_at.strftime("%Y-%m-%d %H:%M:%S") if zrep.closed_at else "In Progress"
        draw_kv("Closed At", closed_str)
        if zrep.closed_by_name:
            draw_kv("Closed By", zrep.closed_by_name)

        y += 6
        draw_dashed_line(draw, y, width)
        y += 10

        # Section: DRAWER RECONCILIATION
        sec_txt = "CASH DRAWER RECONCILIATION"
        s_bbox = draw.textbbox((0, 0), sec_txt, font=font_head)
        draw.text(((width - (s_bbox[2] - s_bbox[0])) // 2, y), sec_txt, font=font_head, fill=(0, 0, 0))
        y += 24
        draw_dashed_line(draw, y, width)
        y += 10

        draw_kv("Opening Float", f"Rs. {zrep.opening_cash_float:.2f}")
        draw_kv("Cash Sales (+)", f"Rs. {zrep.cash_sales:.2f}")
        draw_kv("Cash In (+)", f"Rs. {zrep.cash_additions:.2f}")
        draw_kv("Cash Drops (-)", f"Rs. {zrep.cash_drops:.2f}")
        draw_kv("Cash Payouts (-)", f"Rs. {zrep.cash_payouts:.2f}")
        draw_kv("Cash Refunds (-)", f"Rs. {zrep.cash_refunds:.2f}")

        y += 4
        draw_dashed_line(draw, y, width)
        y += 10

        draw_kv("EXPECTED CASH", f"Rs. {zrep.expected_cash:.2f}", font_l=font_bold)
        counted_str = f"Rs. {zrep.closing_cash_counted:.2f}" if zrep.closing_cash_counted is not None else "PENDING"
        draw_kv("COUNTED CASH", counted_str, font_l=font_bold)
        variance_str = f"Rs. {zrep.cash_variance:.2f}" if zrep.cash_variance is not None else "PENDING"
        draw_kv("CASH VARIANCE", variance_str, font_l=font_bold)

        # Variance status badge
        v_color = (22, 101, 52) if zrep.variance_status == "balanced" else ((153, 27, 27) if zrep.variance_status == "shortage" else (30, 64, 175))
        draw_kv("Variance Status", zrep.variance_status.upper(), font_l=font_bold, fill_r=v_color)

        y += 6
        draw_dashed_line(draw, y, width)
        y += 10

        # Section: SALES SUMMARY
        sec2_txt = "SALES SUMMARY"
        s2_bbox = draw.textbbox((0, 0), sec2_txt, font=font_head)
        draw.text(((width - (s2_bbox[2] - s2_bbox[0])) // 2, y), sec2_txt, font=font_head, fill=(0, 0, 0))
        y += 24
        draw_dashed_line(draw, y, width)
        y += 10

        draw_kv("Total Transactions", str(zrep.total_transactions))
        draw_kv("Total Sales Amount", f"Rs. {zrep.total_sales_amount:.2f}")

        if zrep.payment_method_breakdown:
            y += 6
            draw.text((24, y), "Payment Breakdown:", font=font_bold, fill=(0, 0, 0))
            y += 20
            for m, a in zrep.payment_method_breakdown.items():
                draw_kv(f"  - {m.upper()}", f"Rs. {a:.2f}", font_l=font_regular)

        if zrep.closing_denominations:
            y += 6
            draw_dashed_line(draw, y, width)
            y += 10
            draw.text((24, y), "Closing Denominations:", font=font_bold, fill=(0, 0, 0))
            y += 20
            for note, cnt in sorted(zrep.closing_denominations.items(), key=lambda x: Decimal(x[0]), reverse=True):
                subtot = Decimal(note) * Decimal(cnt)
                draw_kv(f"  Rs. {note} x {cnt}", f"Rs. {subtot:.2f}", font_l=font_regular)

        y += 10
        draw_dashed_line(draw, y, width)
        y += 14

        end_txt = "*** END OF Z-REPORT ***"
        e_bbox = draw.textbbox((0, 0), end_txt, font=font_bold)
        draw.text(((width - (e_bbox[2] - e_bbox[0])) // 2, y), end_txt, font=font_bold, fill=(0, 0, 0))
        y += 20

        foot_txt = "Retain for accounting & tax audit"
        f_bbox = draw.textbbox((0, 0), foot_txt, font=font_small)
        draw.text(((width - (f_bbox[2] - f_bbox[0])) // 2, y), foot_txt, font=font_small, fill=(120, 120, 120))
        y += 28

        actual_height = y + 10
        cropped = img.crop((0, 0, width, actual_height))

        out = io.BytesIO()
        cropped.save(out, format="PNG")
        out.seek(0)
        return out.read()

    def _generate_thermal_pdf(self, zrep: POSZReportResponse) -> bytes:
        img_bytes = self._generate_thermal_image(zrep)
        from PIL import Image
        from reportlab.lib.utils import ImageReader
        from reportlab.pdfgen import canvas

        pil_img = Image.open(io.BytesIO(img_bytes))
        img_w, img_h = pil_img.size

        # 80mm in points = 80 / 25.4 * 72 = 226.77 points
        page_width = 80.0 / 25.4 * 72.0
        page_height = page_width * (img_h / img_w)

        pdf_buf = io.BytesIO()
        c = canvas.Canvas(pdf_buf, pagesize=(page_width, page_height))
        c.drawImage(ImageReader(io.BytesIO(img_bytes)), 0, 0, width=page_width, height=page_height)
        c.showPage()
        c.save()
        return pdf_buf.getvalue()

    def export_z_report_thermal(
        self,
        user: User,
        shift_id: int,
        mode: Any = "preview",
    ) -> Response:
        zrep = self.get_z_report(user, shift_id)

        mode_val = str(getattr(mode, "value", mode) or "preview").lower().strip()

        # 1. Preview mode (Default) -> Visual 80mm receipt PNG rendered directly in Swagger UI
        if mode_val == POSShiftThermalMode.preview.value:
            img_bytes = self._generate_thermal_image(zrep)
            return Response(
                content=img_bytes,
                media_type="image/png",
                headers={
                    "Content-Disposition": f"inline; filename=z_report_{shift_id}_thermal.png",
                    "X-POS-Print-Type": "80mm-PNG-Preview",
                },
            )

        # 2. View mode -> Inline styled HTML page with auto-print dialog
        if mode_val == POSShiftThermalMode.view.value:
            html_content = self._generate_thermal_html(zrep, auto_print=True)
            return HTMLResponse(
                content=html_content,
                status_code=200,
                headers={"Content-Disposition": f"inline; filename=z_report_{shift_id}_thermal.html"},
            )

        # 3. Download mode -> ESC/POS text file attachment download
        if mode_val == POSShiftThermalMode.download.value:
            text_payload = self._generate_thermal_text(zrep)
            return Response(
                content=text_payload.encode("utf-8"),
                media_type="text/plain; charset=utf-8",
                headers={
                    "Content-Disposition": f"attachment; filename=z_report_{shift_id}_thermal.txt",
                    "X-POS-Print-Type": "ESC/POS",
                },
            )

        # 4. PDF mode -> 80mm Thermal Receipt PDF download
        if mode_val == POSShiftThermalMode.pdf.value:
            pdf_bytes = self._generate_thermal_pdf(zrep)
            return Response(
                content=pdf_bytes,
                media_type="application/pdf",
                headers={
                    "Content-Disposition": f"attachment; filename=z_report_{shift_id}_thermal.pdf",
                    "X-POS-Print-Type": "80mm-PDF",
                },
            )

        # 5. HTML mode -> Styled raw HTML layout
        if mode_val == POSShiftThermalMode.html.value:
            html_content = self._generate_thermal_html(zrep, auto_print=False)
            return HTMLResponse(
                content=html_content,
                status_code=200,
                headers={"Content-Disposition": f"inline; filename=z_report_{shift_id}_thermal.html"},
            )

        # 6. JSON mode -> Structured JSON payload
        if mode_val == POSShiftThermalMode.json.value:
            text_payload = self._generate_thermal_text(zrep)
            html_content = self._generate_thermal_html(zrep, auto_print=False)
            response_data = POSShiftThermalResponse(
                success=True,
                message="POS Shift Z-Report thermal slip generated successfully",
                shift_id=zrep.shift_id,
                store_name=zrep.store_name,
                cashier_name=zrep.cashier_name,
                text_payload=text_payload,
                html=html_content,
            )
            return JSONResponse(content=response_data.model_dump())

        # 7. Text mode -> Raw ESC/POS text printer stream
        text_payload = self._generate_thermal_text(zrep)
        return Response(
            content=text_payload.encode("utf-8"),
            media_type="text/plain; charset=utf-8",
            headers={
                "Content-Disposition": f"inline; filename=z_report_{shift_id}_thermal.txt",
                "X-POS-Print-Type": "ESC/POS",
            },
        )

    def export_z_report(
        self,
        user: User,
        shift_id: int,
        format: str = "pdf",
        mode: str = "download",
    ) -> Response:
        fmt = (format or "pdf").lower().strip()
        disposition = "inline" if mode == "preview" else "attachment"

        zrep = self.get_z_report(user, shift_id)
        title = "POS Shift Z-Report"
        metadata = {
            "Shift ID": str(zrep.shift_id),
            "Store": zrep.store_name,
            "Cashier": zrep.cashier_name,
            "Register": zrep.register_id or "Default",
            "Status": zrep.status.upper(),
            "Opened At": zrep.opened_at.strftime("%Y-%m-%d %H:%M:%S") if zrep.opened_at else "N/A",
            "Closed At": zrep.closed_at.strftime("%Y-%m-%d %H:%M:%S") if zrep.closed_at else "N/A",
        }
        if zrep.closed_by_name:
            metadata["Closed By"] = zrep.closed_by_name

        kpis = [
            {"label": "Opening Float", "value": zrep.opening_cash_float},
            {"label": "Total Sales", "value": zrep.total_sales_amount},
            {"label": "Expected Cash", "value": zrep.expected_cash},
            {"label": "Cash Variance", "value": zrep.cash_variance if zrep.cash_variance is not None else "Pending"},
        ]
        headers = ["Financial Component", "Amount"]
        rows: List[List[Any]] = [
            ["Opening Cash Float", str(zrep.opening_cash_float)],
            ["Cash Sales", str(zrep.cash_sales)],
            ["Cash Additions (In)", str(zrep.cash_additions)],
            ["Cash Drops", str(zrep.cash_drops)],
            ["Cash Payouts", str(zrep.cash_payouts)],
            ["Cash Refunds", str(zrep.cash_refunds)],
            ["Expected Cash", str(zrep.expected_cash)],
            ["Counted Cash", str(zrep.closing_cash_counted if zrep.closing_cash_counted is not None else "N/A")],
            ["Variance", str(zrep.cash_variance if zrep.cash_variance is not None else "N/A")],
            ["Variance Status", zrep.variance_status],
            ["Total Transactions", zrep.total_transactions],
            ["Total Sales Amount", str(zrep.total_sales_amount)],
        ]
        if zrep.payment_method_breakdown:
            for method, amt in zrep.payment_method_breakdown.items():
                rows.append([f"Payment: {method.upper()}", str(amt)])

        if zrep.closing_denominations:
            for note, cnt in sorted(zrep.closing_denominations.items(), key=lambda x: Decimal(x[0]), reverse=True):
                rows.append([f"Closing Note Rs. {note} x {cnt}", str(Decimal(note) * Decimal(cnt))])

        if fmt == "pdf":
            from app.services.document_settings_service import DocumentSettingsService
            from app.services.document_renderer_service import DocumentRenderer

            branding = None
            try:
                branding = DocumentSettingsService(self.db).resolve_branding(
                    tenant_id=user.tenant_id,
                    store_id=zrep.store_id,
                )
            except Exception:
                branding = None

            pdf_bytes = DocumentRenderer().render_report_pdf(
                title=title,
                metadata=metadata,
                kpi_summary=kpis,
                headers=headers,
                rows=rows,
                branding=branding,
                report_type="pos_z_report",
            )
            return Response(
                content=pdf_bytes,
                media_type="application/pdf",
                headers={"Content-Disposition": f"{disposition}; filename=z_report_shift_{shift_id}.pdf"},
            )

        elif fmt == "excel":
            from app.services.document_settings_service import DocumentSettingsService
            from app.services.excel_export_service import ExcelExportService

            branding = None
            try:
                branding = DocumentSettingsService(self.db).resolve_branding(
                    tenant_id=user.tenant_id,
                    store_id=zrep.store_id,
                )
            except Exception:
                branding = None

            return ExcelExportService().create_report_streaming_response(
                sheet_title=title,
                headers=headers,
                rows=rows,
                filename=f"z_report_shift_{shift_id}",
                metadata=metadata,
                kpis=kpis,
                branding=branding,
                report_type="pos_z_report",
            )

        elif fmt == "csv":
            import csv
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["POS SHIFT Z-REPORT"])
            writer.writerow(["Shift ID", str(zrep.shift_id)])
            writer.writerow(["Store", zrep.store_name])
            writer.writerow(["Cashier", zrep.cashier_name])
            if zrep.register_id:
                writer.writerow(["Register", zrep.register_id])
            writer.writerow(["Status", zrep.status.upper()])
            writer.writerow(["Opened At", zrep.opened_at.strftime("%Y-%m-%d %H:%M:%S") if zrep.opened_at else "N/A"])
            writer.writerow(["Closed At", zrep.closed_at.strftime("%Y-%m-%d %H:%M:%S") if zrep.closed_at else "N/A"])
            if zrep.closed_by_name:
                writer.writerow(["Closed By", zrep.closed_by_name])
            writer.writerow([])
            writer.writerow(["KEY PERFORMANCE INDICATORS"])
            writer.writerow(["Opening Float", str(zrep.opening_cash_float)])
            writer.writerow(["Total Sales", str(zrep.total_sales_amount)])
            writer.writerow(["Expected Cash", str(zrep.expected_cash)])
            writer.writerow(["Cash Variance", str(zrep.cash_variance if zrep.cash_variance is not None else "Pending")])
            writer.writerow(["Variance Status", zrep.variance_status])
            writer.writerow([])
            writer.writerow(["Financial Component", "Amount"])
            for row in rows:
                writer.writerow(row)

            return Response(
                content=output.getvalue().encode("utf-8"),
                media_type="text/csv",
                headers={"Content-Disposition": f"attachment; filename=z_report_shift_{shift_id}.csv"},
            )
        else:
            raise AppException(f"Unsupported export format '{format}'. Choose from: pdf, excel, csv")

    def export_z_report_pdf(self, user: User, shift_id: int) -> Response:
        return self.export_z_report(user, shift_id, format="pdf", mode="download")

    def export_z_report_excel(self, user: User, shift_id: int) -> Response:
        return self.export_z_report(user, shift_id, format="excel", mode="download")
