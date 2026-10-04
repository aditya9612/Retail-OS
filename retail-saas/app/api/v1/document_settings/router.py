import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import ForbiddenException, NotFoundException
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.document_setting import (
    BrandingContext,
    DocumentSettingResponse,
    DocumentSettingUpdate,
)
from app.services.document_settings_service import DocumentSettingsService

router = APIRouter(prefix="/document-settings", tags=["document-settings"])

ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}
ALLOWED_IMAGE_MIME_TYPES = {"image/png", "image/jpeg", "image/jpg"}
MAX_LOGO_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB


def require_settings_read(user: User = Depends(get_current_user)) -> User:
    perms = user.role.permissions if user.role else []
    if any(p in perms for p in ["*", "settings:read", "stores:read", "billing:read"]):
        return user
    raise ForbiddenException("Missing permission: settings:read, stores:read, or billing:read")


def require_settings_write(user: User = Depends(get_current_user)) -> User:
    perms = user.role.permissions if user.role else []
    if any(p in perms for p in ["*", "settings:write", "stores:write", "billing:write"]):
        return user
    raise ForbiddenException("Missing permission: settings:write, stores:write, or billing:write")


def _require_tenant_id(user: User) -> int:
    if user.tenant_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tenant context is required")
    return user.tenant_id


@router.get("", response_model=Optional[DocumentSettingResponse])
def get_document_setting(
    store_id: int | None = Query(default=None, gt=0),
    user: User = Depends(require_settings_read),
    db: Session = Depends(get_db),
):
    """
    Retrieves the raw DocumentSetting record for the authenticated tenant (and optional store).
    """
    tenant_id = _require_tenant_id(user)
    setting = DocumentSettingsService(db).get_setting(
        tenant_id=tenant_id,
        store_id=store_id,
    )
    return setting


@router.get("/effective", response_model=BrandingContext)
def get_effective_branding(
    store_id: int | None = Query(default=None, gt=0),
    user: User = Depends(require_settings_read),
    db: Session = Depends(get_db),
):
    """
    Retrieves the hierarchically resolved BrandingContext for documents.
    Hierarchy: Store DocumentSetting > Tenant DocumentSetting > Store model > Tenant model > Defaults.
    """
    tenant_id = _require_tenant_id(user)
    return DocumentSettingsService(db).resolve_branding(
        tenant_id=tenant_id,
        store_id=store_id,
    )


@router.put("", response_model=DocumentSettingResponse)
def update_document_setting(
    payload: DocumentSettingUpdate,
    store_id: int | None = Query(default=None, gt=0),
    user: User = Depends(require_settings_write),
    db: Session = Depends(get_db),
):
    """
    Creates or updates DocumentSetting branding and display flags for the tenant (and optional store).
    """
    tenant_id = _require_tenant_id(user)
    return DocumentSettingsService(db).create_or_update_setting(
        tenant_id=tenant_id,
        data=payload,
        store_id=store_id,
    )


@router.post("/logo")
async def upload_document_logo(
    file: UploadFile = File(...),
    store_id: int | None = Query(default=None, gt=0),
    user: User = Depends(require_settings_write),
    db: Session = Depends(get_db),
):
    """
    Uploads a store or tenant branding logo.
    Enforces security:
    - PNG / JPG / JPEG formats only
    - Validates file content length
    - Safe path containment in uploads/logos/
    - Prevents directory traversal attacks
    - Automatically updates DocumentSetting.logo_path
    """
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No filename provided for logo upload.",
        )

    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported image extension '{file_ext}'. Allowed: {', '.join(sorted(ALLOWED_IMAGE_EXTENSIONS))}",
        )

    content_type = (file.content_type or "").lower()
    if content_type not in ALLOWED_IMAGE_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported MIME type '{content_type}'. Must be PNG or JPEG.",
        )

    content = await file.read()
    if len(content) > MAX_LOGO_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Logo image size exceeds maximum allowed limit of 5 MB.",
        )

    logos_dir = Path("uploads") / "logos"
    logos_dir.mkdir(parents=True, exist_ok=True)

    scope_prefix = f"store_{store_id}" if store_id else "tenant"
    unique_filename = f"{user.tenant_id}_{scope_prefix}_{uuid.uuid4().hex[:8]}{file_ext}"
    target_path = (logos_dir / unique_filename).resolve()

    # Boundary safety check
    uploads_root = Path("uploads").resolve()
    try:
        if not target_path.is_relative_to(uploads_root):
            raise HTTPException(status_code=400, detail="Invalid destination path")
    except AttributeError:
        if not str(target_path).startswith(str(uploads_root)):
            raise HTTPException(status_code=400, detail="Invalid destination path")

    with open(target_path, "wb") as f:
        f.write(content)

    rel_logo_url = f"/uploads/logos/{unique_filename}"

    tenant_id = _require_tenant_id(user)
    setting = DocumentSettingsService(db).create_or_update_setting(
        tenant_id=tenant_id,
        data=DocumentSettingUpdate(logo_path=rel_logo_url),
        store_id=store_id,
    )

    return {
        "message": "Logo uploaded successfully",
        "logo_url": rel_logo_url,
        "setting": DocumentSettingResponse.model_validate(setting),
    }


@router.delete("/logo")
def delete_logo(
    store_id: int | None = Query(default=None, gt=0),
    user: User = Depends(require_settings_write),
    db: Session = Depends(get_db),
):
    """
    Deletes the configured logo for the tenant or store scope, removing the file
    from disk if it resides within the uploads directory.
    """
    tenant_id = _require_tenant_id(user)
    svc = DocumentSettingsService(db)
    setting = svc.get_setting(tenant_id=tenant_id, store_id=store_id)
    if not setting or not setting.logo_path:
        raise NotFoundException("No logo found for this scope")

    old_path_str = setting.logo_path
    if old_path_str.startswith("/"):
        old_path_str = old_path_str.lstrip("/")

    file_path = Path(old_path_str).resolve()
    uploads_root = Path("uploads").resolve()
    try:
        is_safe = file_path.is_relative_to(uploads_root)
    except AttributeError:
        is_safe = str(file_path).startswith(str(uploads_root))

    if is_safe and file_path.is_file():
        try:
            file_path.unlink()
        except OSError:
            pass

    setting.logo_path = None
    db.commit()
    db.refresh(setting)

    return {
        "message": "Logo deleted successfully",
        "setting": DocumentSettingResponse.model_validate(setting),
    }

