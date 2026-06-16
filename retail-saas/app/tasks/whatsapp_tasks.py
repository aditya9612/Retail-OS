import asyncio

from app.tasks.celery_worker import celery_app
from app.services.whatsapp_service import WhatsAppService


@celery_app.task(name="send_whatsapp_message")
def send_whatsapp_message_task(phone: str, message: str) -> dict:
    service = WhatsAppService()
    return asyncio.run(service.send_message(phone, message))


@celery_app.task(name="send_order_confirmation")
def send_order_confirmation_task(phone: str, order_number: str, total: str) -> dict:
    service = WhatsAppService()
    return asyncio.run(service.send_order_confirmation(phone, order_number, total))
