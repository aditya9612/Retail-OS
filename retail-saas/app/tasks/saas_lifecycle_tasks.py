import logging
import time
from datetime import datetime
from typing import Any, Dict

from app.core.database import SessionLocal
from app.core.redis_lock import RedisDistributedLock, SAAS_LIFECYCLE_LOCK_KEY
from app.services.saas_subscription_lifecycle_service import (
    SaaSSubscriptionLifecycleService,
)
from app.tasks.celery_worker import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="process_saas_subscription_lifecycle",
    bind=True,
    max_retries=0,
)
def process_saas_subscription_lifecycle_task(self) -> Dict[str, Any]:
    """
    Automated Celery task executing the SaaS subscription lifecycle run.
    Guarded by a distributed Redis lock to prevent concurrent executions
    across multiple Celery workers, API instances, or containers.
    """
    logger.info("Initiating automated SaaS subscription lifecycle task...")
    start_time = time.time()
    iso_start = datetime.utcnow().isoformat()

    lock = RedisDistributedLock(SAAS_LIFECYCLE_LOCK_KEY, ttl_seconds=600)
    if not lock.acquire():
        logger.warning(
            "SaaS subscription lifecycle task skipped: lock '%s' is already held by another execution.",
            SAAS_LIFECYCLE_LOCK_KEY,
        )
        return {
            "status": "skipped",
            "reason": "Lock already held by another lifecycle process",
            "lock_key": SAAS_LIFECYCLE_LOCK_KEY,
            "started_at": iso_start,
            "duration_seconds": round(time.time() - start_time, 4),
        }

    db = SessionLocal()
    try:
        logger.info(
            "Distributed lock acquired. Executing SaaSSubscriptionLifecycleService.run_all()..."
        )
        svc = SaaSSubscriptionLifecycleService(db)
        summary = svc.run_all()

        if not lock.is_valid() or not lock.renew():
            raise RuntimeError(
                f"Distributed lock '{lock.lock_key}' was lost during lifecycle execution: {lock.lock_lost_reason}"
            )

        db.commit()

        elapsed = round(time.time() - start_time, 4)
        logger.info(
            "SaaS subscription lifecycle task completed successfully in %s seconds: %s",
            elapsed,
            summary,
        )
        return {
            "status": "success",
            "summary": summary,
            "started_at": iso_start,
            "duration_seconds": elapsed,
        }
    except Exception as exc:
        db.rollback()
        elapsed = round(time.time() - start_time, 4)
        logger.exception(
            "SaaS subscription lifecycle task failed after %s seconds: %s",
            elapsed,
            exc,
        )
        raise
    finally:
        try:
            lock.release()
        except Exception as lock_err:
            logger.error(
                "Failed to release distributed lock '%s': %s",
                SAAS_LIFECYCLE_LOCK_KEY,
                lock_err,
            )
        db.close()
