import uuid
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.exceptions import RequestValidationError
from pydantic import EmailStr, ValidationError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import ForbiddenException
from app.core.security import get_current_user, require_permission
from app.models.user import User
from app.schemas.user import (
    MyProfileUpdate,
    RoleResponse,
    UserCreate,
    UserResponse,
    UserUpdate,
    AssignStoreRequest,
    AssignStoreResponse,
    RemoveStoreRequest,
    RemoveStoreResponse,
    UsersByStoreResponse,
)
from app.services.user_service import UserService
from app.utils.validators import validate_pan_number, validate_aadhaar_number, validate_email_address
from app.utils.constants import RoleEnum, OFFICIAL_ROLES


router = APIRouter(
    prefix="/users",
    tags=["Users"],
)


USER_CREATE_OPENAPI_EXTRA = {
    "requestBody": {
        "required": True,
        "content": {
            "application/json": {
                "schema": UserCreate.model_json_schema(),
                "example": {
                    "email": "cashier@retailmart.com",
                    "full_name": "Amit Sharma",
                    "password": "SecurePassword@123",
                    "phone": "9876543210",
                    "role": "cashier",
                    "store_id": 1,
                    "pan_number": "ABCDE1234F",
                    "addhar_number": "987654321012",
                },
            },
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "title": "UserCreateFormData",
                    "required": ["email", "full_name", "password", "phone"],
                    "properties": {
                        "email": {
                            "type": "string",
                            "format": "email",
                            "title": "Email Address",
                            "description": "Valid email address is required",
                            "example": "cashier@retailmart.com",
                        },
                        "full_name": {
                            "type": "string",
                            "title": "Full Name",
                            "description": "Full name of the user (2 to 100 characters)",
                            "example": "Amit Sharma",
                        },
                        "password": {
                            "type": "string",
                            "format": "password",
                            "title": "Password",
                            "description": "Password (min 8 chars, 1 uppercase, 1 lowercase, 1 digit, 1 special char)",
                            "example": "SecurePass@123",
                        },
                        "phone": {
                            "type": "string",
                            "title": "Phone Number",
                            "description": "Mandatory 10-digit Indian phone number",
                            "example": "9876543210",
                        },
                        "role": {
                            "type": "string",
                            "title": "Role Name",
                            "description": "Role name from GET /api/v1/roles (e.g. cashier, manager, or custom roles created by Owner). Alternatively, provide 'role_id'.",
                            "default": "cashier",
                            "example": "cashier",
                        },
                        "role_id": {
                            "type": "integer",
                            "title": "Role ID",
                            "description": "Role ID from GET /api/v1/roles (optional if role name is provided)",
                            "example": 2,
                        },
                        "store_id": {
                            "type": "integer",
                            "title": "Store ID",
                            "description": "Store ID to assign the user to",
                            "example": 1,
                        },
                        "pan_number": {
                            "type": "string",
                            "title": "PAN Number",
                            "description": "PAN card number (e.g. ABCDE1234F)",
                            "example": "ABCDE1234F",
                        },
                        "addhar_number": {
                            "type": "string",
                            "title": "Aadhaar Number",
                            "description": "Aadhaar card 12-digit number (e.g. 987654321012)",
                            "example": "987654321012",
                        },
                        "pancard": {
                            "type": "string",
                            "format": "binary",
                            "title": "PAN Card File",
                            "description": "PAN card document or image file (PDF/JPG/PNG, max 5MB)",
                        },
                        "addhar_card": {
                            "type": "string",
                            "format": "binary",
                            "title": "Aadhaar Card File",
                            "description": "Aadhaar card document or image file (PDF/JPG/PNG, max 5MB)",
                        },
                        "profile_photo": {
                            "type": "string",
                            "format": "binary",
                            "title": "Profile Photo File",
                            "description": "Profile photo image file (JPG/PNG/WEBP, max 2MB)",
                        },
                    },
                }
            },
        },
    }
}


async def _save_user_file(
    file: Any,
    prefix: str,
    max_size: int = 5 * 1024 * 1024,
    allowed_exts: Optional[set[str]] = None,
) -> Optional[str]:
    if not file:
        return None
    content = await file.read()
    if not content:
        return None

    filename = getattr(file, "filename", None)
    if not filename:
        text_val = content.decode("utf-8", errors="ignore").strip()
        return text_val if text_val else None

    if len(content) > max_size:
        max_mb = max_size // (1024 * 1024)
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"{prefix.replace('_', ' ').title()} file exceeds maximum allowed size of {max_mb}MB",
        )

    ext = Path(filename).suffix.lower()
    if not ext:
        content_type = getattr(file, "content_type", "")
        if "pdf" in content_type:
            ext = ".pdf"
        elif "png" in content_type:
            ext = ".png"
        elif "jpeg" in content_type or "jpg" in content_type:
            ext = ".jpg"
        elif "webp" in content_type:
            ext = ".webp"
        else:
            ext = ".bin"

    if allowed_exts and ext not in allowed_exts:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid file type '{ext}' for {prefix.replace('_', ' ')}. Allowed: {', '.join(sorted(allowed_exts))}",
        )

    unique_filename = f"{prefix}_{uuid.uuid4().hex[:12]}{ext}"
    user_upload_dir = Path("uploads") / "users"
    user_upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = user_upload_dir / unique_filename
    with open(file_path, "wb") as f:
        f.write(content)
    return f"/uploads/users/{unique_filename}"


@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create User",
    description="Create a new user with role, mandatory phone number, and KYC/profile details. Supports both application/json and multipart/form-data with file uploads.",
    openapi_extra=USER_CREATE_OPENAPI_EXTRA,
)
async def create_user(
    request: Request,
    current_user: User = Depends(require_permission("users:write")),
    db: Session = Depends(get_db),
):
    ct = request.headers.get("content-type", "")

    # 1. JSON Request handling
    if "application/json" in ct:
        try:
            body = await request.json()
        except Exception as e:
            raise HTTPException(status_code=400, detail="Invalid JSON body") from e

        if not isinstance(body, dict):
            raise HTTPException(status_code=422, detail="Request body must be a JSON object")

        try:
            user_data = UserCreate.model_validate(body)
        except ValidationError as e:
            raise RequestValidationError(e.errors())

        effective_store_id = current_user.store_id if current_user.store_id is not None else user_data.store_id
        if effective_store_id != user_data.store_id:
            user_data = user_data.model_copy(update={"store_id": effective_store_id})

        return UserService(db).create_user(
            current_user.tenant_id,
            user_data,
            current_user_store_id=current_user.store_id,
        )

    # 2. Multipart/Form-data and URL-encoded handling
    form = await request.form()

    email_raw = form.get("email")
    full_name_raw = form.get("full_name")
    password_raw = form.get("password")
    phone_raw = form.get("phone")
    role_raw = form.get("role")
    role_id_raw = form.get("role_id")
    store_id_raw = form.get("store_id")
    pan_number_raw = form.get("pan_number")
    addhar_number_raw = form.get("addhar_number")

    pancard_val = form.get("pancard")
    addhar_card_val = form.get("addhar_card")
    profile_photo_val = form.get("profile_photo")

    # Save uploaded files if present
    pancard_path = None
    if hasattr(pancard_val, "filename") and hasattr(pancard_val, "read") and getattr(pancard_val, "filename", None):
        pancard_path = await _save_user_file(
            pancard_val, "pancard", max_size=5 * 1024 * 1024, allowed_exts={".pdf", ".jpg", ".jpeg", ".png"}
        )
    elif isinstance(pancard_val, str) and pancard_val.strip():
        pancard_path = pancard_val.strip()

    addhar_card_path = None
    if hasattr(addhar_card_val, "filename") and hasattr(addhar_card_val, "read") and getattr(addhar_card_val, "filename", None):
        addhar_card_path = await _save_user_file(
            addhar_card_val, "addhar_card", max_size=5 * 1024 * 1024, allowed_exts={".pdf", ".jpg", ".jpeg", ".png"}
        )
    elif isinstance(addhar_card_val, str) and addhar_card_val.strip():
        addhar_card_path = addhar_card_val.strip()

    profile_photo_path = None
    if hasattr(profile_photo_val, "filename") and hasattr(profile_photo_val, "read") and getattr(profile_photo_val, "filename", None):
        profile_photo_path = await _save_user_file(
            profile_photo_val, "profile_photo", max_size=2 * 1024 * 1024, allowed_exts={".jpg", ".jpeg", ".png", ".webp"}
        )
    elif isinstance(profile_photo_val, str) and profile_photo_val.strip():
        profile_photo_path = profile_photo_val.strip()

    # Convert store_id and role_id if numeric strings
    parsed_store_id = None
    if store_id_raw is not None and str(store_id_raw).strip() != "":
        try:
            parsed_store_id = int(str(store_id_raw).strip())
        except ValueError:
            raise HTTPException(status_code=422, detail="store_id must be an integer")

    parsed_role_id = None
    if role_id_raw is not None and str(role_id_raw).strip() != "":
        try:
            parsed_role_id = int(str(role_id_raw).strip())
        except ValueError:
            raise HTTPException(status_code=422, detail="role_id must be an integer")

    clean_role_raw = role_raw.strip() if (role_raw and isinstance(role_raw, str) and role_raw.strip()) else None
    if not clean_role_raw and not parsed_role_id:
        clean_role_raw = "cashier"

    payload = {
        "email": email_raw,
        "full_name": full_name_raw,
        "password": password_raw,
        "phone": phone_raw,
        "role": clean_role_raw,
        "role_id": parsed_role_id,
        "store_id": parsed_store_id,
        "pan_number": pan_number_raw or None,
        "addhar_number": addhar_number_raw or None,
        "pancard": pancard_path,
        "addhar_card": addhar_card_path,
        "profile_photo": profile_photo_path,
    }

    try:
        user_data = UserCreate.model_validate(payload)
    except ValidationError as e:
        raise RequestValidationError(e.errors())

    effective_store_id = current_user.store_id if current_user.store_id is not None else user_data.store_id
    if effective_store_id != user_data.store_id:
        user_data = user_data.model_copy(update={"store_id": effective_store_id})

    return UserService(db).create_user(
        current_user.tenant_id,
        user_data,
        current_user_store_id=current_user.store_id,
    )



@router.get(
    "",
    response_model=list[UserResponse],
)
def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    include_inactive: bool = Query(False),
    store_id: Optional[int] = Query(None, description="Filter users by store ID"),
    current_user: User = Depends(require_permission("users:read")),
    db: Session = Depends(get_db),
):
    effective_store_id = store_id
    if current_user.store_id is not None:
        if store_id is not None and store_id != current_user.store_id:
            raise ForbiddenException("Access denied to users of this store")
        effective_store_id = current_user.store_id

    skip = (page - 1) * page_size

    return UserService(db).list_users(
        tenant_id=current_user.tenant_id,
        skip=skip,
        limit=page_size,
        include_inactive=include_inactive,
        store_id=effective_store_id,
    )



@router.get(
    "/me",
    response_model=UserResponse,
)
def get_my_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return UserService(db).get_user(
        current_user.tenant_id,
        current_user.id,
    )


@router.put(
    "/me",
    response_model=UserResponse,
)
@router.patch(
    "/me",
    response_model=UserResponse,
    include_in_schema=False,
)
def update_my_profile(
    data: MyProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return UserService(db).update_my_profile(
        current_user.tenant_id,
        current_user.id,
        data,
    )


@router.get(
    "/by-store",
    response_model=UsersByStoreResponse,
    summary="List Users Grouped By Store",
    description="Shows how many and which users are assigned to each store with store, role, active status, and search filters.",
)
def get_users_by_store(
    store_id: Optional[int] = Query(None, description="Filter by a specific Store ID"),
    role: Optional[str] = Query(None, description="Filter users by Role name (e.g. staff, manager, accountant, cashier)"),
    role_id: Optional[int] = Query(None, description="Filter users by Role ID"),
    is_active: Optional[bool] = Query(None, description="Filter users by active status (true/false)"),
    search: Optional[str] = Query(None, description="Search users by name, email, or phone number"),
    include_unassigned: bool = Query(True, description="Include unassigned/head office users (store_id=null)"),
    current_user: User = Depends(require_permission("users:read")),
    db: Session = Depends(get_db),
):
    return UserService(db).get_users_by_store(
        tenant_id=current_user.tenant_id,
        current_user_store_id=current_user.store_id,
        store_id=store_id,
        role=role,
        role_id=role_id,
        is_active=is_active,
        search=search,
        include_unassigned=include_unassigned,
    )


@router.get(
    "/{user_id}",
    response_model=UserResponse,
)
def get_user(
    user_id: int,
    current_user: User = Depends(require_permission("users:read")),
    db: Session = Depends(get_db),
):
    user = UserService(db).get_user(
        current_user.tenant_id,
        user_id,
    )
    if current_user.store_id is not None and user.store_id != current_user.store_id:
        raise ForbiddenException("Access denied to user of another store")
    return user


@router.put(
    "/{user_id}",
    response_model=UserResponse,
)
@router.patch(
    "/{user_id}",
    response_model=UserResponse,
    include_in_schema=False,
)
def update_user(
    user_id: int,
    data: UserUpdate,
    current_user: User = Depends(require_permission("users:write")),
    db: Session = Depends(get_db),
):
    target_user = UserService(db).get_user(
        current_user.tenant_id,
        user_id,
    )
    if current_user.store_id is not None:
        if target_user.store_id != current_user.store_id:
            raise ForbiddenException("Access denied to user of another store")
        if data.store_id is not None and data.store_id != current_user.store_id:
            raise ForbiddenException("Cannot reassign user to another store")
    return UserService(db).update_user(
        current_user.tenant_id,
        user_id,
        data,
        current_user_store_id=current_user.store_id,
        current_user_id=current_user.id,
    )


@router.patch(
    "/{user_id}/activate",
    response_model=UserResponse,
)
def activate_user(
    user_id: int,
    current_user: User = Depends(require_permission("users:write")),
    db: Session = Depends(get_db),
):
    target_user = UserService(db).get_user(
        current_user.tenant_id,
        user_id,
    )
    if current_user.store_id is not None and target_user.store_id != current_user.store_id:
        raise ForbiddenException("Access denied to user of another store")
    return UserService(db).activate_user(
        current_user.tenant_id,
        user_id,
    )


@router.patch(
    "/{user_id}/deactivate",
    response_model=UserResponse,
)
def deactivate_user(
    user_id: int,
    current_user: User = Depends(require_permission("users:write")),
    db: Session = Depends(get_db),
):
    target_user = UserService(db).get_user(
        current_user.tenant_id,
        user_id,
    )
    if current_user.store_id is not None and target_user.store_id != current_user.store_id:
        raise ForbiddenException("Access denied to user of another store")
    return UserService(db).deactivate_user(
        current_user.tenant_id,
        user_id,
        current_user.id,
    )


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    description="Deletes the user successfully and returns no response body.",
)
def delete_user(
    user_id: int,
    current_user: User = Depends(require_permission("users:write")),
    db: Session = Depends(get_db),
):
    target_user = UserService(db).get_user(
        current_user.tenant_id,
        user_id,
    )
    if current_user.store_id is not None and target_user.store_id != current_user.store_id:
        raise ForbiddenException("Access denied to user of another store")
    UserService(db).delete_user(
        current_user.tenant_id,
        user_id,
        current_user.id,
    )


@router.post(
    "/{user_id}/assign-store",
    response_model=AssignStoreResponse,
    summary="Assign Store to User",
    description="Assigns or moves a user to a specific store within the tenant organization.",
)
@router.patch(
    "/{user_id}/assign-store",
    response_model=AssignStoreResponse,
    include_in_schema=False,
)
def assign_store(
    user_id: int,
    data: AssignStoreRequest,
    current_user: User = Depends(require_permission("users:write")),
    db: Session = Depends(get_db),
):
    if current_user.store_id is not None:
        raise ForbiddenException("Only Store Owner or Tenant Admin can assign users to stores")

    user = UserService(db).assign_store(
        tenant_id=current_user.tenant_id,
        user_id=user_id,
        store_id=data.store_id,
    )

    store_name = user.store.name if getattr(user, "store", None) else None
    role_name = user.role.name if getattr(user, "role", None) else None

    return AssignStoreResponse(
        message="Store assigned successfully",
        user_id=user.id,
        store_id=user.store_id,
        store_name=store_name,
        role=role_name,
    )


@router.post(
    "/{user_id}/remove-store",
    response_model=RemoveStoreResponse,
    summary="Remove User from Store",
    description="Removes/unassigns a user from their currently assigned store, setting store_id to null.",
)
@router.patch(
    "/{user_id}/remove-store",
    response_model=RemoveStoreResponse,
    include_in_schema=False,
)
def remove_store(
    user_id: int,
    data: Optional[RemoveStoreRequest] = None,
    current_user: User = Depends(require_permission("users:write")),
    db: Session = Depends(get_db),
):
    target_user = UserService(db).get_user(
        current_user.tenant_id,
        user_id,
    )

    effective_store_id = data.store_id if data else None

    if current_user.store_id is not None:
        if target_user.store_id != current_user.store_id:
            raise ForbiddenException("Access denied to user of another store")
        if effective_store_id is not None and effective_store_id != current_user.store_id:
            raise ForbiddenException("You can only remove users from your assigned store")
        effective_store_id = current_user.store_id

    user, previous_store_id = UserService(db).remove_store(
        tenant_id=current_user.tenant_id,
        user_id=user_id,
        store_id=effective_store_id,
    )

    role_name = user.role.name if getattr(user, "role", None) else None

    return RemoveStoreResponse(
        message="User removed from store successfully",
        user_id=user.id,
        store_id=user.store_id,
        previous_store_id=previous_store_id,
        role=role_name,
    )
