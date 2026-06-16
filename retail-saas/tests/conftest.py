import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_retail_saas.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest-only")

from app.core.config import get_settings

get_settings.cache_clear()
