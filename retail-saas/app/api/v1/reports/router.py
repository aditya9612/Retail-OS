from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_permission
from app.models.user import User
from app.services.report_service import ReportService
from app.tasks.report_tasks import generate_gst_report_task, generate_monthly_report_task

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/daily-sales")
def daily_sales(
    target_date: date | None = None,
    user: User = Depends(require_permission("reports:read")),
    db: Session = Depends(get_db),
):
    return ReportService(db).daily_sales(user.tenant_id, target_date)


@router.get("/monthly-sales")
def monthly_sales(
    year: int,
    month: int,
    user: User = Depends(require_permission("reports:read")),
    db: Session = Depends(get_db),
):
    return ReportService(db).monthly_sales(user.tenant_id, year, month)


@router.get("/profit-loss")
def profit_loss(
    start_date: date,
    end_date: date,
    user: User = Depends(require_permission("reports:read")),
    db: Session = Depends(get_db),
):
    return ReportService(db).profit_loss(user.tenant_id, start_date, end_date)


@router.get("/gst")
def gst_report(
    start_date: date,
    end_date: date,
    user: User = Depends(require_permission("reports:read")),
    db: Session = Depends(get_db),
):
    return ReportService(db).gst_report(user.tenant_id, start_date, end_date)


@router.post("/monthly/async")
def monthly_report_async(
    year: int,
    month: int,
    user: User = Depends(require_permission("reports:read")),
):
    task = generate_monthly_report_task.delay(user.tenant_id, year, month)
    return {"task_id": task.id}


@router.post("/gst/async")
def gst_report_async(
    start_date: date,
    end_date: date,
    user: User = Depends(require_permission("reports:read")),
):
    task = generate_gst_report_task.delay(user.tenant_id, start_date.isoformat(), end_date.isoformat())
    return {"task_id": task.id}
