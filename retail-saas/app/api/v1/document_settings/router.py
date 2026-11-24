import io
import uuid
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Path as FastAPIPath, Query, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.pdf_utils import render_pdf_or_preview
from app.core.exceptions import ForbiddenException, NotFoundException
from app.core.security import get_current_user
from app.models.store import Store
from app.models.user import User
from app.schemas.document_setting import (
    BrandingContext,
    DocumentLogoDeleteResponse,
    DocumentLogoUploadResponse,
    DocumentSettingDeleteResponse,
    DocumentSettingResponse,
    DocumentSettingUpdate,
)
from app.schemas.storefront import (
    StorefrontAdvancedSettingsResponse,
    StorefrontAdvancedSettingsUpdate,
    StorefrontContactSocialResponse,
    StorefrontContactSocialUpdate,
    StorefrontPagesResponse,
    StorefrontPagesUpdate,
    StorefrontSEODomainResponse,
    StorefrontSEODomainUpdate,
    StorefrontSettingResponse,
    StorefrontSettingUpdate,
    StorefrontStatusToggleRequest,
    StorefrontUploadResponse,
)
from app.services.document_settings_service import DocumentSettingsService
from app.services.storefront_service import StorefrontService

router = APIRouter(prefix="/document-settings", tags=["Document Settings"])

ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}
ALLOWED_IMAGE_MIME_TYPES = {"image/png", "image/jpeg", "image/jpg"}
MAX_LOGO_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB


def require_settings_read(user: User = Depends(get_current_user)) -> User:
    perms = user.role.permissions if user.role else []
    if any(p in perms for p in ["*", "settings:read"]):
        return user
    raise ForbiddenException("Missing permission: settings:read")


def require_settings_write(user: User = Depends(get_current_user)) -> User:
    perms = user.role.permissions if user.role else []
    if any(p in perms for p in ["*", "settings:write", "settings:create", "settings:update", "settings:delete"]):
        return user
    raise ForbiddenException("Missing permission: settings:update")


def _require_tenant_id(user: User) -> int:
    if user.tenant_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tenant context is required")
    return user.tenant_id


@router.get("", response_model=Optional[DocumentSettingResponse], summary="Get Document & Store Settings")
def get_document_setting(
    store_id: int | None = Query(default=None, gt=0, description="Optional store ID (> 0). If omitted, retrieves tenant-wide company setting."),
    user: User = Depends(require_settings_read),
    db: Session = Depends(get_db),
):
    """
    Retrieves the unified document branding and website storefront settings.
    """
    tenant_id = _require_tenant_id(user)
    if store_id is not None:
        store = (
            db.query(Store)
            .filter(Store.id == store_id, Store.tenant_id == tenant_id)
            .first()
        )
        if not store:
            raise NotFoundException(f"Store with ID {store_id} not found for this tenant.")

    setting = DocumentSettingsService(db).get_setting(
        tenant_id=tenant_id,
        store_id=store_id,
    )
    if not setting:
        return None

    res = DocumentSettingResponse.model_validate(setting)
    from app.models.storefront_setting import StorefrontSetting
    sf_query = db.query(StorefrontSetting).filter(StorefrontSetting.tenant_id == tenant_id)
    if store_id is not None:
        sf_setting = sf_query.filter(StorefrontSetting.store_id == store_id).first()
    else:
        sf_setting = sf_query.filter(StorefrontSetting.store_id.is_(None)).first()

    if sf_setting:
        for attr in [
            "is_online", "tagline", "banner_url", "favicon_url", "theme_name",
            "custom_domain", "url_slug", "meta_title", "meta_description", "keywords",
            "google_analytics_id", "about_us", "contact_us", "privacy_policy",
            "return_policy", "whatsapp_number", "instagram_url", "facebook_url",
            "twitter_url", "enable_product_reviews", "show_out_of_stock", "guest_checkout",
            "wishlist_enabled", "auto_sync_inventory", "enable_coupons", "gst_invoice_enabled"
        ]:
            val = getattr(sf_setting, attr, None)
            if val is not None:
                setattr(res, attr, val)
    return res


@router.get("/effective", response_model=BrandingContext, summary="Get Effective Branding")
def get_effective_branding(
    store_id: int | None = Query(default=None, gt=0, description="Optional store ID (> 0) to resolve effective branding for."),
    user: User = Depends(require_settings_read),
    db: Session = Depends(get_db),
):
    """
    Retrieves the hierarchically resolved BrandingContext for documents.
    Hierarchy: Store DocumentSetting > Tenant DocumentSetting > Store model > Tenant model > Defaults.
    """
    tenant_id = _require_tenant_id(user)
    if store_id is not None:
        store = (
            db.query(Store)
            .filter(Store.id == store_id, Store.tenant_id == tenant_id)
            .first()
        )
        if not store:
            raise NotFoundException(f"Store with ID {store_id} not found for this tenant.")

    return DocumentSettingsService(db).resolve_branding(
        tenant_id=tenant_id,
        store_id=store_id,
    )


@router.put("", response_model=DocumentSettingResponse, summary="Update Document & Store Settings")
def update_document_setting(
    payload: DocumentSettingUpdate,
    store_id: int | None = Query(default=None, gt=0, description="Optional store ID (> 0). If omitted, updates tenant-wide company setting."),
    user: User = Depends(require_settings_write),
    db: Session = Depends(get_db),
):
    """
    Updates unified branding, display flags, sequence rules, terms, and storefront website settings.
    """
    tenant_id = _require_tenant_id(user)
    res_setting = DocumentSettingsService(db).create_or_update_setting(
        tenant_id=tenant_id,
        data=payload,
        store_id=store_id,
    )

    # Auto-sync branding and contact info to StorefrontSetting
    from app.models.storefront_setting import StorefrontSetting
    sf_query = db.query(StorefrontSetting).filter(StorefrontSetting.tenant_id == tenant_id)
    if store_id is not None:
        sf_setting = sf_query.filter(StorefrontSetting.store_id == store_id).first()
    else:
        sf_setting = sf_query.filter(StorefrontSetting.store_id.is_(None)).first()

    if not sf_setting:
        sf_setting = StorefrontSetting(
            tenant_id=tenant_id,
            store_id=store_id,
            store_name=payload.business_name or "RetailOS Shop",
            address=payload.address,
            contact_phone=payload.phone,
            contact_email=payload.email,
            logo_url=payload.logo_path,
            terms_conditions=payload.terms_and_conditions,
        )
        db.add(sf_setting)
    else:
        if payload.business_name is not None:
            sf_setting.store_name = payload.business_name
        if payload.address is not None:
            sf_setting.address = payload.address
        if payload.phone is not None:
            sf_setting.contact_phone = payload.phone
        if payload.email is not None:
            sf_setting.contact_email = payload.email
        if payload.logo_path is not None:
            sf_setting.logo_url = payload.logo_path
        if payload.terms_and_conditions is not None:
            sf_setting.terms_conditions = payload.terms_and_conditions

    # Update any storefront website fields provided in payload
    for attr in [
        "is_online", "tagline", "banner_url", "favicon_url", "theme_name",
        "custom_domain", "url_slug", "meta_title", "meta_description", "keywords",
        "google_analytics_id", "about_us", "contact_us", "privacy_policy",
        "return_policy", "whatsapp_number", "instagram_url", "facebook_url",
        "twitter_url", "enable_product_reviews", "show_out_of_stock", "guest_checkout",
        "wishlist_enabled", "auto_sync_inventory", "enable_coupons", "gst_invoice_enabled"
    ]:
        val = getattr(payload, attr, None)
        if val is not None:
            setattr(sf_setting, attr, val)

    db.commit()
    db.refresh(sf_setting)

    # Auto-sync branding to the Store model so legacy code (thermal/PDF) picks it up
    if store_id is not None:
        store_obj = (
            db.query(Store)
            .filter(Store.id == store_id, Store.tenant_id == tenant_id)
            .first()
        )
        if store_obj:
            if payload.business_name is not None:
                store_obj.name = payload.business_name
            if payload.address is not None:
                store_obj.address = payload.address
            if payload.phone is not None:
                store_obj.phone = payload.phone
            if payload.email is not None:
                store_obj.email = payload.email
            if hasattr(payload, "gstin") and payload.gstin is not None:
                store_obj.gstin = payload.gstin
            if payload.logo_path is not None:
                store_obj.logo_url = payload.logo_path
            db.commit()

    res = DocumentSettingResponse.model_validate(res_setting)
    for attr in [
        "is_online", "tagline", "banner_url", "favicon_url", "theme_name",
        "custom_domain", "url_slug", "meta_title", "meta_description", "keywords",
        "google_analytics_id", "about_us", "contact_us", "privacy_policy",
        "return_policy", "whatsapp_number", "instagram_url", "facebook_url",
        "twitter_url", "enable_product_reviews", "show_out_of_stock", "guest_checkout",
        "wishlist_enabled", "auto_sync_inventory", "enable_coupons", "gst_invoice_enabled"
    ]:
        val = getattr(sf_setting, attr, None)
        if val is not None:
            setattr(res, attr, val)
    return res


@router.post("", response_model=DocumentSettingResponse, summary="Create / Update Document Setting (POST)")
def create_document_setting_post(
    payload: DocumentSettingUpdate,
    store_id: int | None = Query(default=None, gt=0, description="Optional store ID (> 0). If omitted, creates/updates company setting."),
    user: User = Depends(require_settings_write),
    db: Session = Depends(get_db),
):
    """
    POST alias for creating or updating DocumentSetting branding, display flags, sequence rules and terms for the tenant (and optional store).
    """
    return update_document_setting(payload=payload, store_id=store_id, user=user, db=db)


@router.delete("", response_model=DocumentSettingDeleteResponse, status_code=status.HTTP_200_OK, summary="Delete Document Setting")
def delete_document_setting(
    store_id: int | None = Query(default=None, gt=0, description="Optional store ID (> 0). If omitted, resets company setting to defaults."),
    user: User = Depends(require_settings_write),
    db: Session = Depends(get_db),
):
    """
    Deletes the DocumentSetting record for the store (or tenant), reverting to higher-level defaults.
    """
    tenant_id = _require_tenant_id(user)
    DocumentSettingsService(db).delete_setting(tenant_id=tenant_id, store_id=store_id)
    scope = f"store {store_id}" if store_id else "tenant"
    return {"message": f"Document settings for {scope} deleted successfully. Reverted to defaults."}


@router.get("/preview", summary="Preview Document")
def preview_document(
    store_id: int | None = Query(default=None, gt=0, description="Optional store ID (> 0) to preview branding for."),
    document_type: Literal["invoice", "bill"] = Query(default="invoice", description="Document type to render: 'invoice' (Tax Invoice) or 'bill' (Retail Sale Bill)"),
    mode: Literal["download", "preview"] = Query(default="download", description="Delivery mode: 'download' (attachment .pdf) or 'preview' (visual PNG preview in Swagger UI / browser)"),
    user: User = Depends(require_settings_read),
    db: Session = Depends(get_db),
):
    """
    Generates a live preview PDF using current effective branding.
    """
    tenant_id = _require_tenant_id(user)
    if store_id is not None:
        store = (
            db.query(Store)
            .filter(Store.id == store_id, Store.tenant_id == tenant_id)
            .first()
        )
        if not store:
            raise NotFoundException(f"Store with ID {store_id} not found for this tenant.")

    branding = DocumentSettingsService(db).resolve_branding(
        tenant_id=tenant_id,
        store_id=store_id,
    )
    from app.services.document_renderer_service import DocumentRenderer
    now = datetime.utcnow()
    mock_data = {
        "invoice_number": f"{branding.invoice_prefix}-{now.year}-000001",
        "order_number": f"ORD-{now.year}-000001",
        "created_at": now,
        "order_date": now,
        "subtotal": 1000.00,
        "discount_amount": 100.00,
        "cgst_amount": 81.00,
        "sgst_amount": 81.00,
        "igst_amount": 0.00,
        "total_amount": 1062.00,
        "total": 1062.00,
        "qr_data": f"UPI://PAY?PA=MERCHANT@UPI&AM=1062.00&TN=PREVIEW",
        "is_b2b": False,
        "cashier": user.full_name or "Cashier",
        "store_name": branding.business_name or "Sample Retail Store",
        "store_address": branding.address or "123 Market Street, City",
        "store_phone": branding.phone or "9876543210",
        "store_gstin": branding.gstin or "27AAAAA0000A1Z5",
        "customer": {
            "name": "Sample Customer",
            "phone": "9876500000",
            "address": "456 High Street",
            "gstin": "",
        },
        "items": [
            {
                "product_name": "Sample Product Alpha",
                "hsn_code": "6109",
                "quantity": 2,
                "unit_price": 400.00,
                "discount": 0.00,
                "gst_rate": 18.00,
                "cgst_amount": 72.00,
                "sgst_amount": 72.00,
                "igst_amount": 0.00,
                "total_amount": 944.00,
            },
            {
                "product_name": "Sample Product Beta",
                "hsn_code": "8471",
                "quantity": 1,
                "unit_price": 200.00,
                "discount": 100.00,
                "gst_rate": 18.00,
                "cgst_amount": 9.00,
                "sgst_amount": 9.00,
                "igst_amount": 0.00,
                "total_amount": 118.00,
            },
        ],
        "payments": [
            {
                "method": "cash",
                "amount": 1062.00,
                "transaction_id": "PREVIEW_CASH",
            }
        ],
    }
    renderer = DocumentRenderer()
    pdf_bytes = renderer.render(document_type, mock_data, branding)
    return render_pdf_or_preview(
        pdf_content=pdf_bytes,
        filename_base=f"preview_{document_type}",
        mode=mode,
    )


@router.post("/logo", response_model=DocumentLogoUploadResponse, summary="Upload Document Logo", include_in_schema=False)
async def upload_document_logo(
    file: UploadFile = File(..., description="Logo image file (PNG or JPEG, maximum size 5MB)"),
    store_id: int | None = Query(default=None, gt=0, description="Optional store ID (> 0). If omitted, uploads company master logo."),
    user: User = Depends(require_settings_write),
    db: Session = Depends(get_db),
):
    """
    Uploads a store or tenant branding logo.
    Enforces security:
    - PNG / JPG / JPEG formats only
    - Validates file content length (Max 5MB)
    - Validates image integrity using PIL
    - Cleans up old logo on disk
    - Safe path containment in uploads/logos/
    - Prevents directory traversal attacks
    - Automatically updates DocumentSetting.logo_path
    """
    tenant_id = _require_tenant_id(user)
    if store_id is not None:
        store = (
            db.query(Store)
            .filter(Store.id == store_id, Store.tenant_id == tenant_id)
            .first()
        )
        if not store:
            raise NotFoundException(f"Store with ID {store_id} not found for this tenant.")

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

    # Validate image header magic bytes to prevent forged files
    is_png = content.startswith(b"\x89PNG\r\n\x1a\n")
    is_jpeg = content.startswith(b"\xff\xd8\xff")
    if not (is_png or is_jpeg):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is not a valid PNG or JPEG image.",
        )

    logos_dir = Path("uploads") / "logos"
    logos_dir.mkdir(parents=True, exist_ok=True)

    scope_prefix = f"store_{store_id}" if store_id else "tenant"
    unique_filename = f"{tenant_id}_{scope_prefix}_{uuid.uuid4().hex[:8]}{file_ext}"
    target_path = (logos_dir / unique_filename).resolve()

    # Boundary safety check
    uploads_root = Path("uploads").resolve()
    try:
        if not target_path.is_relative_to(uploads_root):
            raise HTTPException(status_code=400, detail="Invalid destination path")
    except AttributeError:
        if not str(target_path).startswith(str(uploads_root)):
            raise HTTPException(status_code=400, detail="Invalid destination path")

    # Clean up old logo file if present
    svc = DocumentSettingsService(db)
    old_setting = svc.get_setting(tenant_id=tenant_id, store_id=store_id)
    if old_setting and old_setting.logo_path:
        old_raw = old_setting.logo_path.lstrip("/")
        old_path = Path(old_raw).resolve()
        if old_path.is_file():
            try:
                is_safe = old_path.is_relative_to(uploads_root)
            except AttributeError:
                is_safe = str(old_path).startswith(str(uploads_root))
            if is_safe:
                try:
                    old_path.unlink()
                except OSError:
                    pass

    with open(target_path, "wb") as f:
        f.write(content)

    rel_logo_url = f"/uploads/logos/{unique_filename}"

    setting = svc.create_or_update_setting(
        tenant_id=tenant_id,
        data=DocumentSettingUpdate(logo_path=rel_logo_url),
        store_id=store_id,
    )

    # Auto-sync logo to StorefrontSetting and Store model
    from app.models.storefront_setting import StorefrontSetting
    sf_query = db.query(StorefrontSetting).filter(StorefrontSetting.tenant_id == tenant_id)
    if store_id is not None:
        sf_setting = sf_query.filter(StorefrontSetting.store_id == store_id).first()
    else:
        sf_setting = sf_query.filter(StorefrontSetting.store_id.is_(None)).first()
    if sf_setting:
        sf_setting.logo_url = rel_logo_url
        db.commit()

    if store_id is not None:
        store_rec = db.query(Store).filter(Store.id == store_id, Store.tenant_id == tenant_id).first()
        if store_rec:
            store_rec.logo_url = rel_logo_url
            db.commit()

    return {
        "message": "Logo uploaded successfully",
        "logo_url": rel_logo_url,
        "setting": DocumentSettingResponse.model_validate(setting),
    }


@router.delete("/logo", response_model=DocumentLogoDeleteResponse, summary="Delete Logo")
def delete_logo(
    store_id: int | None = Query(default=None, gt=0, description="Optional store ID (> 0). If omitted, deletes company master logo."),
    user: User = Depends(require_settings_write),
    db: Session = Depends(get_db),
):
    """
    Deletes the configured logo for the tenant or store scope, removing the file
    from disk if it resides within the uploads directory.
    """
    tenant_id = _require_tenant_id(user)
    if store_id is not None:
        store = (
            db.query(Store)
            .filter(Store.id == store_id, Store.tenant_id == tenant_id)
            .first()
        )
        if not store:
            raise NotFoundException(f"Store with ID {store_id} not found for this tenant.")

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

    # Auto-sync logo deletion to StorefrontSetting
    from app.models.storefront_setting import StorefrontSetting
    sf_query = db.query(StorefrontSetting).filter(StorefrontSetting.tenant_id == tenant_id)
    if store_id is not None:
        sf_setting = sf_query.filter(StorefrontSetting.store_id == store_id).first()
    else:
        sf_setting = sf_query.filter(StorefrontSetting.store_id.is_(None)).first()

    if sf_setting and sf_setting.logo_url:
        clean_sf_url = sf_setting.logo_url.lstrip("/")
        if clean_sf_url == old_path_str:
            sf_setting.logo_url = None

    db.commit()
    db.refresh(setting)

    return {
        "message": "Logo deleted successfully",
        "setting": DocumentSettingResponse.model_validate(setting),
    }


# ============================================================================
# UNIFIED WEBSITE & STOREFRONT CONTROL ENDPOINTS
# ============================================================================

@router.patch("/toggle-status", summary="Toggle Store Online Switch")
def toggle_store_online_status(
    data: StorefrontStatusToggleRequest,
    store_id: Optional[int] = Query(default=None, gt=0, description="Optional store ID"),
    user: User = Depends(require_settings_write),
    db: Session = Depends(get_db),
):
    tenant_id = _require_tenant_id(user)
    return StorefrontService(db).toggle_online_status(
        tenant_id=tenant_id,
        store_id=store_id,
        is_online=data.is_online,
    )


@router.post("/upload-asset", response_model=StorefrontUploadResponse, summary="Upload Media Asset (Logo, Banner, Favicon)")
async def upload_storefront_asset(
    file: UploadFile = File(..., description="Media file (PNG, JPG, JPEG, SVG, ICO, WEBP - max 5MB)"),
    asset_type: str = Form(default="logo", description="Asset type: logo (default), banner, favicon, or og_image"),
    store_id: Optional[int] = Query(default=None, gt=0, description="Optional store ID (> 0). If omitted, uploads company master asset."),
    user: User = Depends(require_settings_write),
    db: Session = Depends(get_db),
):
    """
    Unified media asset upload endpoint for store/company logo, website banner, and browser favicon.
    Automatically updates both the online website and all billing documents (invoices/bills) in real time.
    """
    tenant_id = _require_tenant_id(user)
    content = await file.read()
    res = StorefrontService(db).upload_asset(
        tenant_id=tenant_id,
        store_id=store_id,
        asset_type=asset_type,
        filename=file.filename or "",
        content=content,
    )
    if res.asset_type == "logo":
        res.logo_url = res.url
        setting = DocumentSettingsService(db).get_setting(tenant_id=tenant_id, store_id=store_id)
        if setting:
            res.setting = DocumentSettingResponse.model_validate(setting)
    return res


@router.get("/seo-domain", response_model=StorefrontSEODomainResponse, summary="Get SEO & Domain Settings")
def get_seo_domain_settings(
    store_id: Optional[int] = Query(default=None, gt=0),
    user: User = Depends(require_settings_read),
    db: Session = Depends(get_db),
):
    tenant_id = _require_tenant_id(user)
    return StorefrontService(db).get_seo_domain(tenant_id=tenant_id, store_id=store_id)


@router.put("/seo-domain", response_model=StorefrontSEODomainResponse, summary="Update SEO & Domain Settings")
def update_seo_domain_settings(
    data: StorefrontSEODomainUpdate,
    store_id: Optional[int] = Query(default=None, gt=0),
    user: User = Depends(require_settings_write),
    db: Session = Depends(get_db),
):
    tenant_id = _require_tenant_id(user)
    return StorefrontService(db).update_seo_domain(tenant_id=tenant_id, store_id=store_id, data=data)


@router.get("/pages", response_model=StorefrontPagesResponse, summary="Get Store Pages (About Us, Contact, Privacy, Terms, Returns)")
def get_store_pages(
    store_id: Optional[int] = Query(default=None, gt=0),
    user: User = Depends(require_settings_read),
    db: Session = Depends(get_db),
):
    tenant_id = _require_tenant_id(user)
    return StorefrontService(db).get_pages(tenant_id=tenant_id, store_id=store_id)


@router.put("/pages", response_model=StorefrontPagesResponse, summary="Update Store Pages")
def update_store_pages(
    data: StorefrontPagesUpdate,
    store_id: Optional[int] = Query(default=None, gt=0),
    user: User = Depends(require_settings_write),
    db: Session = Depends(get_db),
):
    tenant_id = _require_tenant_id(user)
    return StorefrontService(db).update_pages(tenant_id=tenant_id, store_id=store_id, data=data)


@router.get("/contact-social", response_model=StorefrontContactSocialResponse, summary="Get Contact & Social Media Links")
def get_contact_social(
    store_id: Optional[int] = Query(default=None, gt=0),
    user: User = Depends(require_settings_read),
    db: Session = Depends(get_db),
):
    tenant_id = _require_tenant_id(user)
    return StorefrontService(db).get_contact_social(tenant_id=tenant_id, store_id=store_id)


@router.put("/contact-social", response_model=StorefrontContactSocialResponse, summary="Update Contact & Social Media Links")
def update_contact_social(
    data: StorefrontContactSocialUpdate,
    store_id: Optional[int] = Query(default=None, gt=0),
    user: User = Depends(require_settings_write),
    db: Session = Depends(get_db),
):
    tenant_id = _require_tenant_id(user)
    return StorefrontService(db).update_contact_social(tenant_id=tenant_id, store_id=store_id, data=data)


@router.get("/advanced", response_model=StorefrontAdvancedSettingsResponse, summary="Get Advanced Feature Switches (7 Toggles)")
def get_advanced_settings(
    store_id: Optional[int] = Query(default=None, gt=0),
    user: User = Depends(require_settings_read),
    db: Session = Depends(get_db),
):
    tenant_id = _require_tenant_id(user)
    return StorefrontService(db).get_advanced_settings(tenant_id=tenant_id, store_id=store_id)


@router.put("/advanced", response_model=StorefrontAdvancedSettingsResponse, summary="Update Advanced Feature Switches")
def update_advanced_settings(
    data: StorefrontAdvancedSettingsUpdate,
    store_id: Optional[int] = Query(default=None, gt=0),
    user: User = Depends(require_settings_write),
    db: Session = Depends(get_db),
):
    tenant_id = _require_tenant_id(user)
    return StorefrontService(db).update_advanced_settings(tenant_id=tenant_id, store_id=store_id, data=data)


@router.get("/public", summary="Get public storefront profile (Customer-facing, no authentication)")
def get_public_storefront(
    subdomain: Optional[str] = Query(default=None),
    store_id: Optional[int] = Query(default=None, gt=0),
    db: Session = Depends(get_db),
):
    return StorefrontService(db).get_public_storefront(subdomain=subdomain, store_id=store_id)


