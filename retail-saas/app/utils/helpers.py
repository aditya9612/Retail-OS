from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def to_decimal(value: Any, default: str = "0") -> Decimal:
    if value is None:
        return Decimal(default)
    return Decimal(str(value))


def paginate(query, page: int = 1, page_size: int = 20):
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size if page_size else 0,
    }


def apply_tenant_filter(query, model, tenant_id: Optional[int]):
    if tenant_id is not None and hasattr(model, "tenant_id"):
        return query.filter(model.tenant_id == tenant_id)
    return query


def get_redis_client():
    import redis

    from app.core.config import get_settings

    return redis.from_url(get_settings().REDIS_URL, decode_responses=True)


def cache_delete_pattern(pattern: str) -> None:
    try:
        client = get_redis_client()
        for key in client.scan_iter(match=pattern):
            client.delete(key)
    except Exception:
        pass

