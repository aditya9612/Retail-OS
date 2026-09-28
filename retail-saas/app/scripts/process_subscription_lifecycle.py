"""
CLI runner for SaaS subscription lifecycle transitions.
Executes trial expiration, scheduled cancellations, period ends,
grace-period expirations, and proactive renewal invoice generation.

Usage:
    python -m app.scripts.process_subscription_lifecycle
"""

import logging
import sys

from app.core.database import SessionLocal
from app.core.redis_lock import RedisDistributedLock, SAAS_LIFECYCLE_LOCK_KEY
from app.services.saas_subscription_lifecycle_service import (
    SaaSSubscriptionLifecycleService,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("process_subscription_lifecycle")


def main() -> int:
    """
    Orchestrates the SaaS subscription lifecycle run.
    Returns:
        0 on success, 1 on failure.
    """
    lock = RedisDistributedLock(SAAS_LIFECYCLE_LOCK_KEY, ttl_seconds=600)
    if not lock.acquire():
        logger.warning(
            "SaaS subscription lifecycle run aborted: lock '%s' is currently held by another execution.",
            SAAS_LIFECYCLE_LOCK_KEY,
        )
        print("Lifecycle run aborted: another lifecycle run is currently in progress.", file=sys.stderr)
        return 1

    db = SessionLocal()
    try:
        logger.info("Starting SaaS subscription lifecycle run...")
        svc = SaaSSubscriptionLifecycleService(db)
        summary = svc.run_all()

        if not lock.is_valid() or not lock.renew():
            raise RuntimeError(
                f"Distributed lock '{lock.lock_key}' was lost during lifecycle execution: {lock.lock_lost_reason}"
            )

        db.commit()
        logger.info("SaaS subscription lifecycle run completed successfully: %s", summary)
        print(f"Lifecycle run completed: {summary}")
        return 0
    except Exception as e:
        db.rollback()
        logger.exception("SaaS subscription lifecycle run failed: %s", e)
        print(f"Lifecycle run failed: {e}", file=sys.stderr)
        return 1
    finally:
        try:
            lock.release()
        except Exception as lock_err:
            logger.error("Failed to release lock '%s': %s", SAAS_LIFECYCLE_LOCK_KEY, lock_err)
        db.close()


if __name__ == "__main__":
    sys.exit(main())
