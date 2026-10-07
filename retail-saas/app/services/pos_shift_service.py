import io
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from fastapi.responses import StreamingResponse

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.exceptions import AppException, ConflictException, ForbiddenException, NotFoundException
from app.models.invoice import Invoice
from app.models.order import Order
from app.models.payment import Payment
from app.models.pos_cash_movement import POSCashMovement
from app.models.pos_shift import POSShift
from app.models.refund import Refund
from app.models.store import Store
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


class POSShiftService:
    def __init__(self, db: Session):
        self.db = db

    def open_shift(self, user: User, data: POSShiftOpenRequest) -> POSShiftResponse:
        if user.tenant_id is None:
            raise AppException("Tenant context required")

        if user.store_id is None:
            raise AppException("User must be assigned to a store to open a POS shift")

        # Verify assigned store exists, is active and belongs to tenant
        store = (
            self.db.query(Store)
            .filter(
                Store.id == user.store_id,
                Store.tenant_id == user.tenant_id,
                Store.is_active == True,
            )
            .first()
        )
        if not store:
            raise NotFoundException("Assigned store not found or is inactive")

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
            store_id=user.store_id,
            cashier_id=user.id,
            opened_at=datetime.utcnow(),
            status="open",
            opening_cash_float=data.opening_cash_float,
            notes=data.notes,
        )
        self.db.add(shift)
        self.db.commit()
        self.db.refresh(shift)

        return POSShiftResponse.model_validate(shift)

    def get_current_shift(self, user: User) -> POSShiftResponse:
        if user.tenant_id is None or user.store_id is None:
            raise NotFoundException("No active open shift found for this cashier")

        shift = (
            self.db.query(POSShift)
            .filter(
                POSShift.tenant_id == user.tenant_id,
                POSShift.store_id == user.store_id,
                POSShift.cashier_id == user.id,
                POSShift.status == "open",
            )
            .first()
        )
        if not shift:
            raise NotFoundException("No active open shift found for this cashier")

        return POSShiftResponse.model_validate(shift)

    def record_cash_movement(self, user: User, data: POSCashMovementRequest) -> POSCashMovementResponse:
        if user.tenant_id is None or user.store_id is None:
            raise NotFoundException("No active open shift found for this cashier")

        shift = (
            self.db.query(POSShift)
            .filter(
                POSShift.tenant_id == user.tenant_id,
                POSShift.store_id == user.store_id,
                POSShift.cashier_id == user.id,
                POSShift.status == "open",
            )
            .with_for_update()
            .first()
        )
        if not shift:
            raise NotFoundException("No active open shift found for this cashier")

        movement = POSCashMovement(
            tenant_id=user.tenant_id,
            shift_id=shift.id,
            movement_type=data.movement_type.upper(),
            amount=data.amount,
            reason=data.reason,
            created_by=user.id,
        )
        self.db.add(movement)
        self.db.commit()
        self.db.refresh(movement)

        return POSCashMovementResponse.model_validate(movement)

    def close_shift(self, user: User, data: POSShiftCloseRequest) -> POSShiftCloseResponse:
        if user.tenant_id is None or user.store_id is None:
            raise NotFoundException("No active open shift found to close")

        shift = (
            self.db.query(POSShift)
            .filter(
                POSShift.tenant_id == user.tenant_id,
                POSShift.store_id == user.store_id,
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
        shift.status = "closed"
        shift.closing_cash_counted = data.closing_cash_counted
        shift.expected_cash = expected_cash
        shift.cash_variance = cash_variance

        if data.notes:
            shift.notes = (f"{shift.notes}\n{data.notes}").strip() if shift.notes else data.notes

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
            opened_at=shift.opened_at,
            closed_at=shift.closed_at,
            opening_cash_float=shift.opening_cash_float,
            cash_sales=financials["cash_sales"],
            cash_additions=financials["cash_additions"],
            cash_drops=financials["cash_drops"],
            cash_payouts=financials["cash_payouts"],
            cash_refunds=financials["cash_refunds"],
            expected_cash=expected_cash,
            closing_cash_counted=shift.closing_cash_counted,
            cash_variance=cash_variance,
            variance_status=variance_status,
            total_transactions=financials["total_transactions"],
            total_sales_amount=financials["total_sales_amount"],
            payment_method_breakdown=financials["payment_method_breakdown"],
            movements=[POSCashMovementResponse.model_validate(m) for m in movements],
            notes=shift.notes,
        )

    def _calculate_shift_financials(self, shift: POSShift, end_time: datetime) -> Dict[str, Any]:
        # Query completed payments for orders created by this cashier at this store in the shift window
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

        # Query approved/completed cash refunds in this window
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

    def export_z_report_pdf(self, user: User, shift_id: int) -> StreamingResponse:
        from app.services.document_settings_service import DocumentSettingsService
        from app.services.document_renderer_service import DocumentRenderer

        zrep = self.get_z_report(user, shift_id)
        title = "POS Shift Z-Report"
        metadata = {
            "Shift ID": str(zrep.shift_id),
            "Store": zrep.store_name,
            "Cashier": zrep.cashier_name,
            "Status": zrep.status.upper(),
            "Opened At": zrep.opened_at.strftime("%Y-%m-%d %H:%M:%S") if zrep.opened_at else "N/A",
            "Closed At": zrep.closed_at.strftime("%Y-%m-%d %H:%M:%S") if zrep.closed_at else "N/A",
        }
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
        )
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=z_report_shift_{shift_id}.pdf"},
        )

    def export_z_report_excel(self, user: User, shift_id: int) -> StreamingResponse:
        from app.services.document_settings_service import DocumentSettingsService
        from app.services.excel_export_service import ExcelExportService

        zrep = self.get_z_report(user, shift_id)
        title = "POS Shift Z-Report"
        metadata = {
            "Shift ID": str(zrep.shift_id),
            "Store": zrep.store_name,
            "Cashier": zrep.cashier_name,
            "Status": zrep.status.upper(),
            "Opened At": zrep.opened_at.strftime("%Y-%m-%d %H:%M:%S") if zrep.opened_at else "N/A",
            "Closed At": zrep.closed_at.strftime("%Y-%m-%d %H:%M:%S") if zrep.closed_at else "N/A",
        }
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
        )

