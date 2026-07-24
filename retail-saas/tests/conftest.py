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
    from app.core.database import Base, engine

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


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
