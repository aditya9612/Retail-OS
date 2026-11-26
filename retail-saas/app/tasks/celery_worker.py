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
        "app.tasks.store_target_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    broker_connection_retry=False,
    broker_connection_retry_on_startup=False,
    broker_connection_max_retries=0,
    task_publish_retry=False,
    task_publish_retry_policy={
        "max_retries": 0,
    },
    broker_transport_options={
        "max_retries": 0,
        "socket_connect_timeout": 1,
        "socket_timeout": 1,
    },
    beat_schedule={
        "saas-subscription-lifecycle-hourly": {
            "task": "process_saas_subscription_lifecycle",
            "schedule": crontab(minute=0, hour="*"),
        },
        "store-target-expiration-hourly": {
            "task": "process_expired_store_targets",
            "schedule": crontab(minute=15, hour="*"),
        },
    },
)
