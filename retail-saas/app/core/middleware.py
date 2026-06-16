from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import get_settings
from app.core.tenant import set_current_tenant_id

settings = get_settings()


class TenantMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        tenant_header = request.headers.get("X-Tenant-ID")
        if tenant_header and tenant_header.isdigit():
            set_current_tenant_id(int(tenant_header))
        response = await call_next(request)
        return response
