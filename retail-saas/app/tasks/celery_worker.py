from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "retail_saas",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.tasks.invoice_tasks",
        "app.tasks.whatsapp_tasks",
        "app.tasks.report_tasks",
        "app.tasks.saas_lifecycle_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "saas-subscription-lifecycle-hourly": {
            "task": "process_saas_subscription_lifecycle",
            "schedule": crontab(minute=0, hour="*"),
        },
    },
)
