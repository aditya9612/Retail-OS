import logging
import time
from datetime import datetime
from typing import Any, Dict

from app.core.database import SessionLocal
from app.services.store_target_service import StoreTargetService
from app.tasks.celery_worker import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="process_expired_store_targets",
    max_retries=0,
)
def process_expired_store_targets_task() -> Dict[str, Any]:
    """
    Automated background Celery task executing Store Targets expiration check.
    Transitions active targets whose end_date has passed to 'completed'.
    """
    logger.info("Initiating automated store targets expiration task...")
    start_time = time.time()
    iso_start = datetime.utcnow().isoformat()

    db = SessionLocal()
    try:
        summary = StoreTargetService.auto_complete_expired_targets(db)
        duration = round(time.time() - start_time, 4)
        logger.info(
            "Store targets expiration task completed in %ss: %d targets transitioned",
            duration,
            summary.get("transitioned_count", 0),
        )
        return {
            "status": "success",
            "started_at": iso_start,
            "duration_seconds": duration,
            **summary,
        }
    except Exception as exc:
        logger.error("Error executing store targets expiration task: %s", exc)
        db.rollback()
        raise
    finally:
        db.close()
