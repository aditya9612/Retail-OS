import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.exceptions import RequestValidationError
from pydantic import EmailStr, ValidationError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import ForbiddenException
from app.core.security import require_permission
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


router = APIRouter(
    prefix="/users",
    tags=["Users"],
)


async def _save_user_file(
    file: Optional[UploadFile],
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
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
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
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
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
    description="Create a new user with role, mandatory phone number, and KYC/profile details (pan_number, addhar_number, pancard, addhar card, profile photo) using multipart/form-data.",
)
async def create_user(
    email: EmailStr = Form(..., description="Valid email address is required"),
    full_name: str = Form(..., min_length=2, max_length=100, description="Full name of the user"),
    password: str = Form(..., min_length=8, max_length=100, description="Password (min 8 chars, 1 uppercase, 1 lowercase, 1 digit, 1 special char)"),
    phone: str = Form(..., description="Mandatory 10-digit Indian phone number"),
    role: str = Form("staff", description="Role name (e.g. staff, manager, cashier, admin, accountant)"),
    store_id: Optional[int] = Form(None, description="Store ID to assign the user to"),
    pan_number: Optional[str] = Form(None, description="PAN card number (e.g. ABCDE1234F)"),
    addhar_number: Optional[str] = Form(None, description="Aadhaar card 12-digit number (e.g. 987654321012)"),
    pancard: Optional[UploadFile] = File(None, description="PAN card document or image file (PDF/JPG/PNG, max 5MB)"),
    addhar_card: Optional[UploadFile] = File(None, description="Aadhaar card document or image file (PDF/JPG/PNG, max 5MB)"),
    profile_photo: Optional[UploadFile] = File(None, description="Profile photo image file (JPG/PNG/WEBP, max 2MB)"),
    current_user: User = Depends(require_permission("users:write")),
    db: Session = Depends(get_db),
):
    try:
        validated_email = validate_email_address(str(email), field_name="Email", required=True)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    try:
        validated_pan = validate_pan_number(pan_number)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    try:
        validated_aadhaar = validate_aadhaar_number(addhar_number)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    pancard_path = await _save_user_file(
        pancard, "pancard", max_size=5 * 1024 * 1024, allowed_exts={".pdf", ".jpg", ".jpeg", ".png"}
    )
    addhar_card_path = await _save_user_file(
        addhar_card, "addhar_card", max_size=5 * 1024 * 1024, allowed_exts={".pdf", ".jpg", ".jpeg", ".png"}
    )
    profile_photo_path = await _save_user_file(
        profile_photo, "profile_photo", max_size=2 * 1024 * 1024, allowed_exts={".jpg", ".jpeg", ".png", ".webp"}
    )

    effective_store_id = current_user.store_id if current_user.store_id is not None else store_id

    try:
        user_data = UserCreate(
            email=validated_email,
            full_name=full_name,
            password=password,
            role=role,
            role_id=None,
            phone=phone,
            pan_number=validated_pan,
            addhar_number=validated_aadhaar,
            pancard=pancard_path,
            addhar_card=addhar_card_path,
            profile_photo=profile_photo_path,
            store_id=effective_store_id,
        )
    except ValidationError as e:
        raise RequestValidationError(e.errors())

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
    current_user: User = Depends(require_permission("users:read")),
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
    current_user: User = Depends(require_permission("users:read")),
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

