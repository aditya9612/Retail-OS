from fastapi import HTTPException, status
from fastapi.responses import JSONResponse
from fastapi import Request

class AppException(HTTPException):
    def __init__(self, detail: str, status_code: int = status.HTTP_400_BAD_REQUEST):
        super().__init__(
            status_code=status_code,
            detail={
                "success": False,
                "message": detail
            }
        )

class NotFoundException(AppException):
    def __init__(self, detail: str = "Resource not found"):
        super().__init__(
            detail=detail,
            status_code=status.HTTP_404_NOT_FOUND
        )

class UnauthorizedException(AppException):
    def __init__(self, detail: str = "Not authenticated"):
        super().__init__(
            detail=detail,
            status_code=status.HTTP_401_UNAUTHORIZED
        )

class ForbiddenException(AppException):
    def __init__(self, detail: str = "Permission denied"):
        super().__init__(
            detail=detail,
            status_code=status.HTTP_403_FORBIDDEN
        )
class ConflictException(AppException):
    def __init__(self, detail: str = "Resource already exists"):
        super().__init__(
            detail=detail,
            status_code=status.HTTP_409_CONFLICT
        )

def register_exception_handlers(app):
    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException):
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.detail
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "message": exc.detail
            }
        )