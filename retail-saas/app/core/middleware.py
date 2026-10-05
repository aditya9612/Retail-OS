from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.tenant import set_current_tenant_id


class TenantMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope.get("type") == "http":
            for name, val in scope.get("headers", []):
                if name.lower() == b"x-tenant-id":
                    header_str = val.decode("latin1", errors="ignore").strip()
                    if header_str.isdigit():
                        set_current_tenant_id(int(header_str))
                    break
        await self.app(scope, receive, send)

