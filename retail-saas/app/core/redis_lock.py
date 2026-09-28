"""
Redis Distributed Lock implementation for coordinating operations across
multiple workers, containers, and replicas.

Uses the canonical token-based distributed locking pattern:
- Atomic acquisition via SET key token NX EX ttl
- Periodic TTL heartbeat renewal via Lua script verifying token ownership
- Safe ownership-aware release via Lua script (ensures a process only deletes its own lock)
- Explicit lock-loss recording and propagation if ownership check or renewal fails
"""

import logging
import threading
import time
import uuid
from typing import Optional

import redis

from app.core.redis_client import get_redis

logger = logging.getLogger(__name__)

SAAS_LIFECYCLE_LOCK_KEY = "lock:saas_subscription_lifecycle"
DEFAULT_LOCK_TTL_SECONDS = 600  # 10 minutes
DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 60  # 1 minute

LUA_RELEASE_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""

LUA_RENEW_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("expire", KEYS[1], ARGV[2])
else
    return 0
end
"""


class RedisDistributedLock:
    """
    Distributed lock backed by Redis with safe, ownership-aware release,
    background TTL heartbeat renewal, and lock-loss detection.
    """

    def __init__(
        self,
        lock_key: str = SAAS_LIFECYCLE_LOCK_KEY,
        ttl_seconds: int = DEFAULT_LOCK_TTL_SECONDS,
        heartbeat_interval: float = DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
        client: Optional[redis.Redis] = None,
        auto_heartbeat: bool = True,
    ):
        self.lock_key = lock_key
        self.ttl_seconds = ttl_seconds
        self.heartbeat_interval = heartbeat_interval
        self._client = client
        self.auto_heartbeat = auto_heartbeat
        self.token: Optional[str] = None
        self._acquired = False
        self._lock_lost = False
        self._lock_lost_reason: Optional[str] = None
        self._stop_event: Optional[threading.Event] = None
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._thread_lock = threading.Lock()

    @property
    def redis(self) -> redis.Redis:
        if self._client is None:
            self._client = get_redis()
        return self._client

    @property
    def lock_lost(self) -> bool:
        with self._thread_lock:
            return self._lock_lost

    @property
    def lock_lost_reason(self) -> Optional[str]:
        with self._thread_lock:
            return self._lock_lost_reason

    def is_valid(self) -> bool:
        """
        Returns True if the lock was acquired and has not been marked as lost.
        """
        with self._thread_lock:
            return self._acquired and not self._lock_lost

    def acquire(self, auto_heartbeat: Optional[bool] = None) -> bool:
        """
        Attempts to acquire the distributed lock atomically.
        Returns True if acquired, False if the lock is currently held by another worker.
        If acquired and auto_heartbeat is True, launches background TTL renewal.
        """
        if auto_heartbeat is None:
            auto_heartbeat = self.auto_heartbeat

        self.token = uuid.uuid4().hex
        with self._thread_lock:
            self._lock_lost = False
            self._lock_lost_reason = None

        try:
            acquired = self.redis.set(
                self.lock_key,
                self.token,
                nx=True,
                ex=self.ttl_seconds,
            )
            self._acquired = bool(acquired)
            if self._acquired:
                logger.debug(
                    "Acquired Redis distributed lock '%s' with token %s (TTL: %ds)",
                    self.lock_key,
                    self.token,
                    self.ttl_seconds,
                )
                if auto_heartbeat:
                    self.start_heartbeat()
            else:
                logger.debug(
                    "Failed to acquire Redis distributed lock '%s': already held",
                    self.lock_key,
                )
            return self._acquired
        except Exception as exc:
            logger.error(
                "Error acquiring Redis distributed lock '%s': %s",
                self.lock_key,
                exc,
            )
            self._acquired = False
            return False

    def renew(self, extend_ttl_seconds: Optional[int] = None) -> bool:
        """
        Safely renews the lock TTL using a Lua script that verifies the caller
        is still the active token owner. If renewal fails, records lock loss.
        """
        ttl = extend_ttl_seconds if extend_ttl_seconds is not None else self.ttl_seconds
        with self._thread_lock:
            if not self._acquired or not self.token:
                return False
            if self._lock_lost:
                return False
            current_token = self.token

        try:
            result = self.redis.eval(
                LUA_RENEW_SCRIPT,
                1,
                self.lock_key,
                current_token,
                int(ttl),
            )
            if result == 1:
                logger.debug(
                    "Renewed Redis distributed lock '%s' with token %s (TTL: %ds)",
                    self.lock_key,
                    current_token,
                    ttl,
                )
                return True
            else:
                self._record_lock_loss("Lock key disappeared or is no longer owned by current token")
                return False
        except Exception as exc:
            self._record_lock_loss(f"Redis renewal error: {exc}")
            return False

    def _record_lock_loss(self, reason: str) -> None:
        with self._thread_lock:
            self._lock_lost = True
            self._lock_lost_reason = reason
            if self._stop_event:
                self._stop_event.set()
        logger.critical(
            "DISTRIBUTED LOCK LOST: Lock '%s' with token %s lost: %s",
            self.lock_key,
            self.token,
            reason,
        )

    def start_heartbeat(self) -> None:
        """
        Spawns a single background daemon thread to renew the TTL periodically.
        """
        with self._thread_lock:
            if not self._acquired or self._lock_lost:
                return
            if self._heartbeat_thread and self._heartbeat_thread.is_alive():
                return
            self._stop_event = threading.Event()
            self._heartbeat_thread = threading.Thread(
                target=self._heartbeat_worker,
                name=f"redis-lock-heartbeat-{self.lock_key}",
                daemon=True,
            )
            self._heartbeat_thread.start()
            logger.debug(
                "Started heartbeat worker thread for lock '%s' (interval: %.1fs)",
                self.lock_key,
                self.heartbeat_interval,
            )

    def _heartbeat_worker(self) -> None:
        while self._stop_event and not self._stop_event.is_set():
            if self._stop_event.wait(timeout=self.heartbeat_interval):
                break
            if not self._acquired or self._lock_lost:
                break
            success = self.renew()
            if not success:
                logger.warning(
                    "Heartbeat renewal failed for lock '%s'. Terminating heartbeat.",
                    self.lock_key,
                )
                break

    def stop_heartbeat(self) -> None:
        """
        Stops and joins the heartbeat daemon thread deterministically.
        """
        with self._thread_lock:
            stop_evt = self._stop_event
            t = self._heartbeat_thread
            if stop_evt:
                stop_evt.set()
            self._heartbeat_thread = None
            self._stop_event = None

        if t and t.is_alive() and t != threading.current_thread():
            t.join(timeout=2.0)

    def release(self) -> bool:
        """
        Safely releases the distributed lock using a Lua script to ensure
        we only delete the lock if it is still owned by our token.
        Stops the heartbeat worker thread.
        If the lock was already lost, does NOT attempt to release (key may belong to another owner).
        """
        self.stop_heartbeat()

        with self._thread_lock:
            if self._lock_lost:
                logger.warning(
                    "Skipping release of Redis distributed lock '%s': lock was marked lost (%s)",
                    self.lock_key,
                    self._lock_lost_reason,
                )
                self._acquired = False
                self.token = None
                return False

            if not self._acquired or not self.token:
                return False

            current_token = self.token

        try:
            result = self.redis.eval(
                LUA_RELEASE_SCRIPT,
                1,
                self.lock_key,
                current_token,
            )
            released = bool(result == 1)
            if released:
                logger.debug(
                    "Safely released Redis distributed lock '%s' with token %s",
                    self.lock_key,
                    current_token,
                )
            else:
                logger.warning(
                    "Redis distributed lock '%s' was no longer owned by token %s (may have expired or been stolen)",
                    self.lock_key,
                    current_token,
                )
            with self._thread_lock:
                self._acquired = False
                self.token = None
            return released
        except Exception as exc:
            logger.error(
                "Error releasing Redis distributed lock '%s': %s",
                self.lock_key,
                exc,
            )
            with self._thread_lock:
                self._acquired = False
                self.token = None
            return False

    def is_locked(self) -> bool:
        """
        Checks whether the lock key currently exists in Redis.
        """
        try:
            return bool(self.redis.exists(self.lock_key))
        except Exception as exc:
            logger.error(
                "Error checking existence of lock '%s': %s",
                self.lock_key,
                exc,
            )
            return False

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
