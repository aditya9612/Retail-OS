import os
import uuid
from unittest.mock import patch

import pytest

os.environ["DATABASE_URL"] = "sqlite:///./test_retail_saas.db"
os.environ["SECRET_KEY"] = "test-secret-key-for-pytest-only"

from app.core.config import get_settings

get_settings.cache_clear()


@pytest.fixture(scope="session", autouse=True)
def init_test_database():
    from decimal import Decimal
    from app.core.database import Base, engine, SessionLocal
    from app.models.saas_billing import SaaSPlan
    from sqlalchemy import event

    @event.listens_for(engine, "connect")
    def register_sqlite_functions(dbapi_connection, connection_record):
        if hasattr(dbapi_connection, "create_function"):
            dbapi_connection.create_function("binary", 1, lambda x: x)

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    session = SessionLocal()
    try:
        from app.models.saas_plan_entitlement import SaaSPlanEntitlement
        plans = [
            SaaSPlan(
                name="Basic",
                code="basic",
                description="Essential retail management for single store operations.",
                price=Decimal("999.00"),
                currency="INR",
                billing_interval="monthly",
                trial_days=14,
                is_active=True,
            ),
            SaaSPlan(
                name="Pro",
                code="pro",
                description="Advanced multi-store management, analytics, and delivery integrations.",
                price=Decimal("2499.00"),
                currency="INR",
                billing_interval="monthly",
                trial_days=14,
                is_active=True,
            ),
            SaaSPlan(
                name="Enterprise",
                code="enterprise",
                description="Full platform capabilities with custom store limits and dedicated support.",
                price=Decimal("4999.00"),
                currency="INR",
                billing_interval="monthly",
                trial_days=0,
                is_active=True,
            ),
        ]
        session.add_all(plans)
        session.flush()

        for plan in plans:
            dims = ["stores", "products"] if plan.code == "basic" else ["users", "stores", "products"]
            for dim in dims:
                session.add(
                    SaaSPlanEntitlement(
                        plan_id=plan.id,
                        dimension=dim,
                        value=0,
                        is_unlimited=True,
                    )
                )
        session.commit()
    finally:
        session.close()


class FakeRedis:
    def __init__(self):
        self._store: dict[str, str] = {}

    def get(self, key: str):
        return self._store.get(key)

    def setex(self, key: str, ttl: int, value: str):
        self._store[key] = value

    def delete(self, key: str):
        self._store.pop(key, None)


@pytest.fixture
def unique_slug():
    return f"test-{uuid.uuid4().hex[:8]}"


@pytest.fixture(autouse=True)
def fake_redis():
    from app.core.redis_client import get_redis

    get_redis.cache_clear()
    fake = FakeRedis()
    with (
        patch("app.services.cart_service.get_redis", return_value=fake),
        patch("app.utils.helpers.get_redis_client", return_value=fake),
        patch("app.utils.helpers.cache_delete_pattern"),
    ):
        yield fake
    get_redis.cache_clear()
