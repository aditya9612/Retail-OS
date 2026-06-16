from datetime import date

from app.core.database import SessionLocal
from app.services.report_service import ReportService
from app.tasks.celery_worker import celery_app


@celery_app.task(name="generate_monthly_report")
def generate_monthly_report_task(tenant_id: int, year: int, month: int) -> dict:
    db = SessionLocal()
    try:
        service = ReportService(db)
        return service.monthly_sales(tenant_id, year, month)
    finally:
        db.close()


@celery_app.task(name="generate_gst_report")
def generate_gst_report_task(tenant_id: int, start_date: str, end_date: str) -> dict:
    db = SessionLocal()
    try:
        service = ReportService(db)
        return service.gst_report(tenant_id, date.fromisoformat(start_date), date.fromisoformat(end_date))
    finally:
        db.close()
