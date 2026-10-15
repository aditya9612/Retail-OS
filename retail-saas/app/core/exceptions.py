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

class QuotaExceededException(AppException):
    def __init__(
        self,
        dimension: str,
        current_usage: int,
        limit: int,
        requested: int = 1,
        detail: str = None,
    ):
        message = (
            detail
            or f"Plan quota exceeded for '{dimension}'. Current usage: {current_usage}, Limit: {limit}, Requested: {requested}."
        )
        super().__init__(
            detail=message,
            status_code=status.HTTP_403_FORBIDDEN,
        )
        self.dimension = dimension
        self.current_usage = current_usage
        self.limit = limit
        self.requested = requested
        self.detail = {
            "success": False,
            "error_code": "QUOTA_EXCEEDED",
            "message": message,
            "dimension": dimension,
            "current_usage": current_usage,
            "limit": limit,
            "requested": requested,
        }


import logging
import re
from typing import Any, Dict, List, Optional, Union

from fastapi import HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.exc import DataError, DatabaseError, IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("app.exceptions")


def _format_pydantic_errors(errors_raw: List[Dict[str, Any]]) -> Dict[str, Any]:
    encoded_raw = jsonable_encoder(errors_raw)
    errors = []
    error_summaries = []
    for err in encoded_raw:
        loc = err.get("loc", [])
        field_parts = [str(x) for x in loc]
        field_str = ".".join(field_parts) if field_parts else "input"
        clean_field = (
            ".".join(
                [str(x) for x in loc if str(x) not in ("body", "query", "path", "header")]
            )
            or field_str
        )
        msg = err.get("msg", "Invalid value")
        if msg.startswith("Value error, "):
            msg = msg[len("Value error, ") :]
        errors.append(
            {
                "field": clean_field,
                "message": msg,
                "type": err.get("type", "validation_error"),
                "loc": list(loc),
            }
        )
        error_summaries.append(f"'{clean_field}': {msg}")

    summary = (
        "; ".join(error_summaries)
        if error_summaries
        else "Validation failed for provided input"
    )
    return {
        "success": False,
        "message": f"Validation failed: {summary}",
        "detail": encoded_raw,
        "errors": errors,
    }


def register_exception_handlers(app):
    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException):
        detail = exc.detail
        if isinstance(detail, dict):
            content = {
                "success": False,
                "message": detail.get("message", "Request failed"),
                "detail": detail,
                **detail,
            }
        else:
            content = {
                "success": False,
                "message": str(detail),
                "detail": detail,
            }
        return JSONResponse(
            status_code=exc.status_code,
            content=content,
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(StarletteHTTPException)
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: Union[HTTPException, StarletteHTTPException]):
        detail = exc.detail
        if isinstance(detail, dict):
            content = {
                "success": False,
                "message": detail.get("message", str(detail)),
                "detail": detail,
                **detail,
            }
        elif isinstance(detail, list):
            content = {
                "success": False,
                "message": "Multiple errors occurred",
                "detail": detail,
            }
        else:
            content = {
                "success": False,
                "message": str(detail),
                "detail": detail,
            }
        return JSONResponse(
            status_code=exc.status_code,
            content=content,
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation_exception_handler(request: Request, exc: RequestValidationError):
        logger.warning(
            "Request validation error on %s %s: %s",
            request.method,
            request.url.path,
            exc.errors(),
        )
        errors = exc.errors()
        if request.method == "POST" and request.url.path.rstrip("/").endswith("/inventory/transfer"):
            has_json_invalid = any(err.get("type") == "json_invalid" for err in errors)
            if has_json_invalid:
                try:
                    raw_body = await request.body()
                    body_text = raw_body.decode("utf-8", errors="replace")
                except Exception:
                    body_text = ""

                is_quantity_err = False
                for err in errors:
                    if err.get("type") == "json_invalid":
                        loc = err.get("loc", ())
                        pos = loc[1] if len(loc) > 1 and isinstance(loc[1], int) else None
                        before_pos = body_text[:pos] if pos is not None else body_text
                        if re.search(r'["\']quantity["\']\s*:\s*$', before_pos.rstrip()):
                            is_quantity_err = True
                            break

                if not is_quantity_err and re.search(r'["\']quantity["\']\s*:\s*[^0-9"\s{\[\]-]', body_text):
                    is_quantity_err = True

                if is_quantity_err:
                    formatted = {
                        "success": False,
                        "message": "Validation failed: 'quantity': Invalid value for quantity. Expected a positive integer.",
                        "detail": [
                            {
                                "type": "int_parsing",
                                "loc": ["body", "quantity"],
                                "msg": "Invalid value for quantity. Expected a positive integer.",
                                "input": None,
                                "ctx": {"error": "Expected a positive integer"},
                            }
                        ],
                        "errors": [
                            {
                                "field": "quantity",
                                "message": "Invalid value for quantity. Expected a positive integer.",
                                "type": "int_parsing",
                                "loc": ["body", "quantity"],
                            }
                        ],
                    }
                    return JSONResponse(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        content=formatted,
                    )

        clean_path = request.url.path.rstrip("/")
        if (
            request.method == "PATCH"
            and ("/coupons/" in clean_path or "/suppliers/" in clean_path or clean_path.endswith("/status"))
            and clean_path.endswith("/status")
        ):
            has_json_invalid = any(err.get("type") == "json_invalid" for err in errors)
            if has_json_invalid:
                try:
                    raw_body = await request.body()
                    body_text = raw_body.decode("utf-8", errors="replace")
                except Exception:
                    body_text = ""

                field_name = "status" if ('"status"' in body_text or "'status'" in body_text) else "is_active"
                if field_name == "status":
                    msg = "Invalid JSON format. Expected 'active' or 'inactive' for 'status'."
                    err_type = "string_type"
                    ctx_err = "Expected 'active' or 'inactive' for 'status'."
                else:
                    msg = "Invalid JSON format. Expected a boolean: true or false for 'is_active'."
                    err_type = "bool_parsing"
                    ctx_err = "Expected a boolean: true or false for 'is_active'."

                formatted = {
                    "success": False,
                    "message": f"Validation failed: '{field_name}': {msg}",
                    "detail": [
                        {
                            "type": err_type,
                            "loc": ["body", field_name],
                            "msg": msg,
                            "input": None,
                            "ctx": {"error": ctx_err},
                        }
                    ],
                    "errors": [
                        {
                            "field": field_name,
                            "message": msg,
                            "type": err_type,
                            "loc": ["body", field_name],
                        }
                    ],
                }
                return JSONResponse(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    content=formatted,
                )

        if (
            request.method in ("POST", "PUT", "PATCH")
            and "/categories" in clean_path
        ):
            has_json_invalid = any(err.get("type") == "json_invalid" for err in errors)
            if has_json_invalid:
                try:
                    raw_body = await request.body()
                    body_text = raw_body.decode("utf-8", errors="replace")
                except Exception:
                    body_text = ""

                detected_field = None
                for err in errors:
                    if err.get("type") == "json_invalid":
                        loc = err.get("loc", ())
                        pos = loc[1] if len(loc) > 1 and isinstance(loc[1], int) else None
                        before_pos = body_text[:pos] if pos is not None else body_text
                        m = re.findall(r'["\']([a-zA-Z0-9_]+)["\']\s*:\s*$', before_pos.rstrip())
                        if m:
                            detected_field = m[-1]
                            break

                if not detected_field:
                    if re.search(r'["\']parent_id["\']\s*:\s*[^0-9"\s{\[\]-]', body_text):
                        detected_field = "parent_id"
                    elif re.search(r'["\']name["\']\s*:\s*[^"{\[\w\s]', body_text):
                        detected_field = "name"
                    elif re.search(r'["\']description["\']\s*:\s*[^"{\[\w\s]', body_text):
                        detected_field = "description"
                    elif re.search(r'["\']is_active["\']\s*:\s*[^"{\[\w\s]', body_text):
                        detected_field = "is_active"

                field_expected = {
                    "parent_id": ("int_parsing", "Expected an integer (positive category ID) or null"),
                    "name": ("string_type", "Expected a string"),
                    "description": ("string_type", "Expected a string or null"),
                    "is_active": ("bool_parsing", "Expected a boolean: true or false"),
                }

                if detected_field in field_expected:
                    err_type, expected_desc = field_expected[detected_field]
                    error_msg = f"Invalid value for {detected_field}. {expected_desc}."
                    formatted = {
                        "success": False,
                        "message": f"Validation failed: '{detected_field}': {error_msg}",
                        "detail": [
                            {
                                "type": err_type,
                                "loc": ["body", detected_field],
                                "msg": error_msg,
                                "input": None,
                                "ctx": {"error": expected_desc},
                            }
                        ],
                        "errors": [
                            {
                                "field": detected_field,
                                "message": error_msg,
                                "type": err_type,
                                "loc": ["body", detected_field],
                            }
                        ],
                    }
                    return JSONResponse(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        content=formatted,
                    )

        if (
            request.method in ("POST", "PUT", "PATCH")
            and "/warehouses" in clean_path
        ):
            has_json_invalid = any(err.get("type") == "json_invalid" for err in errors)
            if has_json_invalid:
                try:
                    raw_body = await request.body()
                    body_text = raw_body.decode("utf-8", errors="replace")
                except Exception:
                    body_text = ""

                detected_field = None
                for err in errors:
                    if err.get("type") == "json_invalid":
                        loc = err.get("loc", ())
                        pos = loc[1] if len(loc) > 1 and isinstance(loc[1], int) else None
                        before_pos = body_text[:pos] if pos is not None else body_text
                        m = re.findall(r'["\']([a-zA-Z0-9_]+)["\']\s*:\s*$', before_pos.rstrip())
                        if m:
                            detected_field = m[-1]
                            break

                if not detected_field:
                    if re.search(r'["\']is_active["\']\s*:\s*[^"{\[\w\s]', body_text) or re.search(r'["\']is_active["\']\s*:\s*$', body_text.strip().rstrip("}")):
                        detected_field = "is_active"
                    elif re.search(r'["\']store_id["\']\s*:\s*[^0-9"\s{\[\]-]', body_text):
                        detected_field = "store_id"
                    elif re.search(r'["\']name["\']\s*:\s*[^"{\[\w\s]', body_text):
                        detected_field = "name"
                    elif re.search(r'["\']code["\']\s*:\s*[^"{\[\w\s]', body_text):
                        detected_field = "code"
                    elif re.search(r'["\']address["\']\s*:\s*[^"{\[\w\s]', body_text):
                        detected_field = "address"

                field_expected = {
                    "is_active": ("bool_parsing", "Expected a boolean: true or false for 'is_active'"),
                    "store_id": ("int_parsing", "Expected a positive integer (store ID) or null"),
                    "name": ("string_type", "Expected a string for warehouse name"),
                    "code": ("string_type", "Expected a string for warehouse code"),
                    "address": ("string_type", "Expected a string for warehouse address"),
                }

                if detected_field in field_expected:
                    err_type, expected_desc = field_expected[detected_field]
                    error_msg = f"Invalid value for {detected_field}. {expected_desc}."
                    formatted = {
                        "success": False,
                        "message": f"Validation failed: '{detected_field}': {error_msg}",
                        "detail": [
                            {
                                "type": err_type,
                                "loc": ["body", detected_field],
                                "msg": error_msg,
                                "input": None,
                                "ctx": {"error": expected_desc},
                            }
                        ],
                        "errors": [
                            {
                                "field": detected_field,
                                "message": error_msg,
                                "type": err_type,
                                "loc": ["body", detected_field],
                            }
                        ],
                    }
                    return JSONResponse(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        content=formatted,
                    )

        formatted = _format_pydantic_errors(errors)
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=formatted,
        )

    @app.exception_handler(ValidationError)
    async def pydantic_validation_exception_handler(request: Request, exc: ValidationError):
        logger.warning(
            "Pydantic validation error on %s %s: %s",
            request.method,
            request.url.path,
            exc.errors(),
        )
        formatted = _format_pydantic_errors(exc.errors())
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=formatted,
        )

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError):
        err_msg = str(exc)
        logger.warning(
            "Value error on %s %s: %s",
            request.method,
            request.url.path,
            err_msg,
        )
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "success": False,
                "message": err_msg,
                "detail": err_msg,
            },
        )

    @app.exception_handler(TypeError)
    async def type_error_handler(request: Request, exc: TypeError):
        err_msg = f"Data type mismatch: {str(exc)}"
        logger.warning(
            "Type error on %s %s: %s",
            request.method,
            request.url.path,
            err_msg,
        )
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "success": False,
                "message": err_msg,
                "detail": err_msg,
            },
        )

    @app.exception_handler(IntegrityError)
    async def integrity_error_handler(request: Request, exc: IntegrityError):
        orig = str(exc.orig) if hasattr(exc, "orig") else str(exc)
        orig_lower = orig.lower()
        logger.error(
            "Database IntegrityError on %s %s: %s",
            request.method,
            request.url.path,
            orig,
        )
        if "unique" in orig_lower or "duplicate" in orig_lower:
            status_code = status.HTTP_409_CONFLICT
            msg = "Duplicate record conflict: A record with this unique identifier or value already exists in the system."
        elif "foreign key" in orig_lower or "foreignkey" in orig_lower:
            status_code = status.HTTP_400_BAD_REQUEST
            msg = "Invalid reference mismatch: A referenced entity ID (store, role, user, product, or category) does not exist."
        elif "not null" in orig_lower:
            status_code = status.HTTP_400_BAD_REQUEST
            msg = "Missing required database field."
        elif "check constraint" in orig_lower:
            status_code = status.HTTP_400_BAD_REQUEST
            msg = "Database constraint check failed."
        else:
            status_code = status.HTTP_400_BAD_REQUEST
            msg = f"Database constraint violation: {orig}"

        return JSONResponse(
            status_code=status_code,
            content={
                "success": False,
                "message": msg,
                "detail": msg,
            },
        )

    @app.exception_handler(DataError)
    async def data_error_handler(request: Request, exc: DataError):
        orig = str(exc.orig) if hasattr(exc, "orig") else str(exc)
        logger.error(
            "Database DataError on %s %s: %s",
            request.method,
            request.url.path,
            orig,
        )
        msg = "Data length or range mismatch: One or more fields exceed allowed database column bounds."
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "success": False,
                "message": msg,
                "detail": msg,
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception(
            "Unhandled internal exception on %s %s: %s",
            request.method,
            request.url.path,
            exc,
        )
        err_msg = f"An unexpected server error occurred: {str(exc) or type(exc).__name__}"
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "success": False,
                "message": err_msg,
                "detail": err_msg,
                "error_type": type(exc).__name__,
            },
        )