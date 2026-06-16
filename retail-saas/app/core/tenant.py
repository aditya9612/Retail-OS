from contextvars import ContextVar
from typing import Optional

tenant_id_ctx: ContextVar[Optional[int]] = ContextVar("tenant_id", default=None)
user_id_ctx: ContextVar[Optional[int]] = ContextVar("user_id", default=None)
store_id_ctx: ContextVar[Optional[int]] = ContextVar("store_id", default=None)


def get_current_tenant_id() -> Optional[int]:
    return tenant_id_ctx.get()


def set_current_tenant_id(tenant_id: Optional[int]) -> None:
    tenant_id_ctx.set(tenant_id)


def get_current_user_id() -> Optional[int]:
    return user_id_ctx.get()


def set_current_user_id(user_id: Optional[int]) -> None:
    user_id_ctx.set(user_id)


def get_current_store_id() -> Optional[int]:
    return store_id_ctx.get()


def set_current_store_id(store_id: Optional[int]) -> None:
    store_id_ctx.set(store_id)
