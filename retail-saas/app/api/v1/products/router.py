from datetime import date
from decimal import Decimal
import json
import pathlib
from typing import Any, Dict, List, Optional, Union
import uuid

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Path,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, Response
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_operational_write, require_permission
from app.models.product import ProductImage
from app.models.user import User
from app.schemas.product import (
    BarcodeLabelMode,
    ProductBarcodeLabelResponse,
    ProductBulkCreateRequest,
    ProductBulkCreateResponse,
    ProductCatalogSummaryResponse,
    ProductCreate,
    ProductImageCreate,
    ProductImageResponse,
    ProductLowStockResponse,
    ProductResponse,
    ProductUpdate,
)
from app.schemas.product_variant import (
    ProductVariantCreate,
    ProductVariantListResponse,
    ProductVariantResponse,
)
from app.services.product_service import ProductService
from app.services.product_variant_service import ProductVariantService


router = APIRouter(
    prefix="/products",
    tags=["products"],
)


@router.get(
    "",
    response_model=list[ProductResponse],
)
def list_products(
    page: int = Query(
        default=1,
        gt=0,
    ),
    page_size: int = Query(
        default=20,
        gt=0,
        le=100,
    ),
    include_inactive: bool = Query(
        default=False,
    ),
    category_id: Optional[int] = Query(
        default=None,
        gt=0,
        description="Filter products by category ID",
    ),
    brand: Optional[str] = Query(
        default=None,
        description="Filter products by brand name",
    ),
    stock_status: Optional[str] = Query(
        default=None,
        description="Filter products by stock status (in_stock, out_of_stock)",
    ),
    min_price: Optional[Decimal] = Query(
        default=None,
        ge=0,
        description="Filter products by minimum selling price",
    ),
    max_price: Optional[Decimal] = Query(
        default=None,
        ge=0,
        description="Filter products by maximum selling price",
    ),
    sort_by: Optional[str] = Query(
        default=None,
        description="Sort products: name_asc, name_desc, price_asc, price_desc, created_asc, created_desc",
    ),
    user: User = Depends(
        require_permission("products:read")
    ),
    db: Session = Depends(get_db),
):
    return ProductService(db).list_products(
        user.tenant_id,
        page=page,
        page_size=page_size,
        include_inactive=include_inactive,
        category_id=category_id,
        brand=brand,
        stock_status=stock_status,
        min_price=min_price,
        max_price=max_price,
        sort_by=sort_by,
    )


@router.get(
    "/search",
    response_model=list[ProductResponse],
)
def search_products(
    search: str = Query(
        ...,
        min_length=2,
        max_length=100,
        description="Search by product name, SKU, barcode or HSN code",
    ),
    page: int = Query(
        default=1,
        gt=0,
    ),
    page_size: int = Query(
        default=20,
        gt=0,
        le=100,
    ),
    user: User = Depends(
        require_permission("products:read")
    ),
    db: Session = Depends(get_db),
):
    search = search.strip()

    if not search:
        raise HTTPException(
            status_code=422,
            detail="Search query cannot be empty or whitespace",
        )

    return ProductService(db).search_products(
        user.tenant_id,
        search,
        page,
        page_size,
    )


@router.get(
    "/low-stock",
    response_model=list[ProductLowStockResponse],
)
def list_low_stock(
    store_id: int = Query(
        ...,
        gt=0,
        description="Active store ID belonging to the current tenant",
    ),
    threshold: int = Query(
        default=10,
        gt=0,
        le=1000000,
        description="Low-stock threshold",
    ),
    days: Optional[str] = Query(
        default=None,
        description="Optional days of stock remaining threshold",
    ),
    user: User = Depends(
        require_permission("products:read")
    ),
    db: Session = Depends(get_db),
):
    if days is not None:
        days_str = days.strip()
        if not days_str:
            raise HTTPException(
                status_code=422,
                detail="Days parameter cannot be empty",
            )
        if not days_str.isdigit() or int(days_str) <= 0 or int(days_str) > 365:
            raise HTTPException(
                status_code=422,
                detail="Days must be an integer between 1 and 365",
            )

    return ProductService(db).list_low_stock(
        user.tenant_id,
        store_id,
        threshold,
    )


@router.get(
    "/expiring-soon",
    response_model=list[ProductResponse],
)
def list_expiring_soon(
    store_id: int = Query(
        ...,
        gt=0,
    ),
    days: Optional[str] = Query(
        default="30",
        description="Days until expiration (1-365)",
    ),
    user: User = Depends(
        require_permission("products:read")
    ),
    db: Session = Depends(get_db),
):
    if days is not None:
        days_str = days.strip()
        if not days_str:
            raise HTTPException(
                status_code=422,
                detail="Days parameter cannot be empty",
            )
        if not days_str.isdigit() or int(days_str) <= 0 or int(days_str) > 365:
            raise HTTPException(
                status_code=422,
                detail="Days must be an integer between 1 and 365",
            )
        days_val = int(days_str)
    else:
        days_val = 30

    return ProductService(db).list_expiring_soon(
        user.tenant_id,
        store_id,
        days_val,
    )


@router.get(
    "/barcode/{barcode}",
    response_model=ProductResponse,
)
def lookup_barcode(
    barcode: str,
    user: User = Depends(
        require_permission("products:read")
    ),
    db: Session = Depends(get_db),
):
    return ProductService(db).get_by_barcode(
        user.tenant_id,
        barcode,
    )


async def _save_product_image(
    file: Optional[UploadFile],
    max_size: int = 10 * 1024 * 1024,
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
            detail=f"Image file exceeds maximum allowed size of {max_mb}MB",
        )

    ext = pathlib.Path(filename).suffix.lower()
    if not ext:
        content_type = getattr(file, "content_type", "")
        if "png" in content_type:
            ext = ".png"
        elif "jpeg" in content_type or "jpg" in content_type:
            ext = ".jpg"
        elif "webp" in content_type:
            ext = ".webp"
        else:
            ext = ".png"

    allowed = {".jpg", ".jpeg", ".png", ".webp"}
    if ext not in allowed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid file type '{ext}' for image. Allowed: {', '.join(sorted(allowed))}",
        )

    unique_filename = f"prod_{uuid.uuid4().hex[:12]}{ext}"
    product_upload_dir = pathlib.Path("uploads") / "products"
    product_upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = product_upload_dir / unique_filename
    with open(file_path, "wb") as f:
        f.write(content)
    return f"/uploads/products/{unique_filename}"


def _ensure_product_image_record(db: Session, product_id: int, image_url: str, is_primary: bool = True) -> None:
    existing = (
        db.query(ProductImage)
        .filter(
            ProductImage.product_id == product_id,
            ProductImage.image_url == image_url,
        )
        .first()
    )
    if not existing:
        img = ProductImage(
            product_id=product_id,
            image_url=image_url,
            is_primary=is_primary,
        )
        db.add(img)
        db.commit()


PRODUCT_CREATE_OPENAPI_EXTRA = {
    "requestBody": {
        "required": True,
        "content": {
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "title": "ProductCreateFormData",
                    "required": ["name", "sku", "selling_price"],
                    "properties": {
                        "name": {
                            "type": "string",
                            "title": "Product Name",
                            "description": "Full product name (2 to 255 chars, e.g. Fortune Sunflower Oil 1L)",
                        },
                        "sku": {
                            "type": "string",
                            "title": "Product SKU",
                            "description": "Unique SKU code in uppercase alphanumeric (e.g. OIL-SUN-001)",
                        },
                        "selling_price": {
                            "type": "number",
                            "title": "Selling Price (Rs.)",
                            "description": "Final retail selling price per unit (must be greater than 0)",
                        },
                        "mrp": {
                            "type": "number",
                            "title": "Maximum Retail Price (MRP Rs.)",
                            "description": "Printed MRP on pack (must be >= Selling Price, or 0 if unpriced)",
                        },
                        "category_id": {
                            "type": "integer",
                            "title": "Category ID",
                            "description": "ID of existing category (leave empty if not categorized)",
                        },
                        "brand": {
                            "type": "string",
                            "title": "Brand Name",
                            "description": "Brand / manufacturer name (e.g. Fortune, Nestle, Amul)",
                        },
                        "barcode": {
                            "type": "string",
                            "title": "Barcode / EAN",
                            "description": "Product barcode digits (8 to 50 numeric digits, e.g. 8901234567890)",
                        },
                        "unit": {
                            "type": "string",
                            "title": "Unit of Measurement",
                            "description": "Packaging unit (e.g. pcs, kg, g, ltr, ml, box, pack)",
                        },
                        "hsn_code": {
                            "type": "string",
                            "title": "HSN Code",
                            "description": "GST HSN code (must be exactly 4, 6, or 8 digits, e.g. 1512)",
                        },
                        "gst_rate": {
                            "type": "number",
                            "title": "GST Rate (%)",
                            "description": "Standard Indian GST slab: 0, 5, 12, 18, or 28",
                        },
                        "min_stock_alert": {
                            "type": "integer",
                            "title": "Low Stock Alert Threshold",
                            "description": "Alert threshold quantity when inventory gets low (e.g. 5 or 10)",
                        },
                        "stock_status": {
                            "type": "string",
                            "title": "Stock Status",
                            "description": "Current stock status: in_stock or out_of_stock",
                        },
                        "description": {
                            "type": "string",
                            "title": "Product Description",
                            "description": "Detailed product description, specifications, or notes",
                        },
                        "is_active": {
                            "type": "boolean",
                            "title": "Is Active",
                            "description": "Set to true to make product available for sale, or false to disable",
                        },
                        "track_batch": {
                            "type": "boolean",
                            "title": "Track Batch / Lot",
                            "description": "Set to true if tracking batch numbers (requires Batch Number)",
                        },
                        "track_expiry": {
                            "type": "boolean",
                            "title": "Track Expiry Date",
                            "description": "Set to true if product has expiry (requires Expiry Date)",
                        },
                        "batch_number": {
                            "type": "string",
                            "title": "Batch Number",
                            "description": "Batch / Lot identifier (required if Track Batch is true, e.g. BATCH-2026-A)",
                        },
                        "expiry_date": {
                            "type": "string",
                            "format": "date",
                            "title": "Expiry Date (YYYY-MM-DD)",
                            "description": "Expiration date YYYY-MM-DD (must be today or a future date)",
                        },
                        "image": {
                            "type": "string",
                            "format": "binary",
                            "title": "Product Photo File",
                            "description": "Upload product photo file (.jpg, .jpeg, .png, .webp - Max 10MB)",
                        },
                    },
                },
            },
            "application/json": {
                "schema": {
                    "type": "object",
                    "title": "ProductCreateJSON",
                    "required": ["name", "sku", "selling_price"],
                    "properties": {
                        "name": {
                            "type": "string",
                            "title": "Product Name",
                            "description": "Full product name (2 to 255 chars, e.g. Fortune Sunflower Oil 1L)",
                        },
                        "sku": {
                            "type": "string",
                            "title": "Product SKU",
                            "description": "Unique SKU code in uppercase alphanumeric (e.g. OIL-SUN-001)",
                        },
                        "selling_price": {
                            "type": "number",
                            "title": "Selling Price (Rs.)",
                            "description": "Final retail selling price per unit (must be greater than 0)",
                        },
                        "mrp": {
                            "type": "number",
                            "title": "Maximum Retail Price (MRP Rs.)",
                            "description": "Printed MRP on pack (must be >= Selling Price, or 0 if unpriced)",
                        },
                        "category_id": {
                            "type": "integer",
                            "title": "Category ID",
                            "description": "ID of existing category (leave empty if not categorized)",
                        },
                        "brand": {
                            "type": "string",
                            "title": "Brand Name",
                            "description": "Brand / manufacturer name (e.g. Fortune, Nestle, Amul)",
                        },
                        "barcode": {
                            "type": "string",
                            "title": "Barcode / EAN",
                            "description": "Product barcode digits (8 to 50 numeric digits, e.g. 8901234567890)",
                        },
                        "unit": {
                            "type": "string",
                            "title": "Unit of Measurement",
                            "description": "Packaging unit (e.g. pcs, kg, g, ltr, ml, box, pack)",
                        },
                        "hsn_code": {
                            "type": "string",
                            "title": "HSN Code",
                            "description": "GST HSN code (must be exactly 4, 6, or 8 digits, e.g. 1512)",
                        },
                        "gst_rate": {
                            "type": "number",
                            "title": "GST Rate (%)",
                            "description": "Standard Indian GST slab: 0, 5, 12, 18, or 28",
                        },
                        "min_stock_alert": {
                            "type": "integer",
                            "title": "Low Stock Alert Threshold",
                            "description": "Alert threshold quantity when inventory gets low (e.g. 5 or 10)",
                        },
                        "stock_status": {
                            "type": "string",
                            "title": "Stock Status",
                            "description": "Current stock status: in_stock or out_of_stock",
                        },
                        "description": {
                            "type": "string",
                            "title": "Product Description",
                            "description": "Detailed product description, specifications, or notes",
                        },
                        "is_active": {
                            "type": "boolean",
                            "title": "Is Active",
                            "description": "Set to true to make product available for sale, or false to disable",
                        },
                        "track_batch": {
                            "type": "boolean",
                            "title": "Track Batch / Lot",
                            "description": "Set to true if tracking batch numbers (requires Batch Number)",
                        },
                        "track_expiry": {
                            "type": "boolean",
                            "title": "Track Expiry Date",
                            "description": "Set to true if product has expiry (requires Expiry Date)",
                        },
                        "batch_number": {
                            "type": "string",
                            "title": "Batch Number",
                            "description": "Batch / Lot identifier (required if Track Batch is true, e.g. BATCH-2026-A)",
                        },
                        "expiry_date": {
                            "type": "string",
                            "format": "date",
                            "title": "Expiry Date (YYYY-MM-DD)",
                            "description": "Expiration date YYYY-MM-DD (must be today or a future date)",
                        },
                    },
                },
            },
        },
    },
}


def _clean_str(val: Any) -> Optional[str]:
    if val is None:
        return None
    s = str(val).strip()
    return s if s else None


def _clean_decimal(val: Any) -> Optional[Decimal]:
    s = _clean_str(val)
    if s is None:
        return None
    try:
        return Decimal(s)
    except Exception:
        return s


def _clean_int(val: Any) -> Optional[int]:
    s = _clean_str(val)
    if s is None:
        return None
    try:
        return int(s)
    except Exception:
        return s


def _clean_bool(val: Any, default: bool = False) -> bool:
    if val is None:
        return default
    s = str(val).strip().lower()
    if not s:
        return default
    return s in ("true", "1", "yes", "t")


def _clean_optional_bool(val: Any) -> Optional[bool]:
    if val is None:
        return None
    s = str(val).strip().lower()
    if not s:
        return None
    if s in ("true", "1", "yes", "t"):
        return True
    if s in ("false", "0", "no", "f"):
        return False
    return None


def _raise_validation_error(val_err: ValidationError) -> None:
    errors = []
    for err in val_err.errors():
        err_dict = dict(err)
        if not err_dict.get("loc"):
            msg = err_dict.get("msg", "").lower()
            if "mrp" in msg:
                err_dict["loc"] = ("mrp",)
            elif "barcode" in msg:
                err_dict["loc"] = ("barcode",)
            elif "batch" in msg:
                err_dict["loc"] = ("batch_number",)
            elif "expiry" in msg:
                err_dict["loc"] = ("expiry_date",)
            else:
                err_dict["loc"] = ("body",)
        errors.append(err_dict)
    raise RequestValidationError(errors)


@router.post(
    "",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Product",
    description="Creates a product. Supports both multipart/form-data (with direct image file upload) and application/json.",
    openapi_extra=PRODUCT_CREATE_OPENAPI_EXTRA,
    dependencies=[Depends(require_operational_write)],
)
async def create_product(
    request: Request,
    user: User = Depends(require_permission("products:write")),
    db: Session = Depends(get_db),
):
    ct = request.headers.get("content-type", "")

    # 1. Backward-compatible JSON Request handling
    if "application/json" in ct:
        try:
            body = await request.json()
        except Exception as e:
            raise HTTPException(status_code=400, detail="Invalid JSON body") from e

        try:
            create_data = ProductCreate.model_validate(body)
        except ValidationError as e:
            _raise_validation_error(e)

        product = ProductService(db).create_product(user.tenant_id, create_data)
        if product.image_url:
            _ensure_product_image_record(db, product.id, product.image_url)
        return product

    # 2. Multipart / Form-data Request handling
    form = await request.form()

    # Handle image file upload (supports single or multiple photos)
    upload_files = []
    for field_key in ("images", "image", "files", "file"):
        for f in form.getlist(field_key):
            if hasattr(f, "filename") and hasattr(f, "read") and getattr(f, "filename", None):
                upload_files.append(f)

    uploaded_urls = []
    for f in upload_files:
        u = await _save_product_image(f)
        if u:
            uploaded_urls.append(u)

    raw_img_url = _clean_str(form.get("image_url"))
    final_image_url = uploaded_urls[0] if uploaded_urls else raw_img_url

    parsed_variants = None
    raw_variants = _clean_str(form.get("variants"))
    if raw_variants:
        try:
            parsed_variants = json.loads(raw_variants)
        except Exception:
            parsed_variants = raw_variants

    payload: Dict[str, Any] = {}

    # Required & string fields
    name_val = _clean_str(form.get("name"))
    if name_val is not None:
        payload["name"] = name_val

    sku_val = _clean_str(form.get("sku"))
    if sku_val is not None:
        payload["sku"] = sku_val

    # Prices
    sp_val = _clean_decimal(form.get("selling_price"))
    if sp_val is not None:
        payload["selling_price"] = sp_val

    p_val = _clean_decimal(form.get("price"))
    if p_val is not None:
        payload["price"] = p_val

    mrp_val = _clean_decimal(form.get("mrp"))
    if mrp_val is not None:
        payload["mrp"] = mrp_val

    # Taxes
    gst_val = _clean_decimal(form.get("gst_rate"))
    if gst_val is not None:
        payload["gst_rate"] = gst_val

    tax_val = _clean_decimal(form.get("tax_rate"))
    if tax_val is not None:
        payload["tax_rate"] = tax_val

    # Category, Brand, Barcode, HSN, Description, Unit, Stock
    cat_id = _clean_int(form.get("category_id"))
    if cat_id is not None:
        payload["category_id"] = cat_id

    brand_val = _clean_str(form.get("brand"))
    if brand_val is not None:
        payload["brand"] = brand_val

    barcode_val = _clean_str(form.get("barcode"))
    if barcode_val is not None:
        payload["barcode"] = barcode_val

    hsn_val = _clean_str(form.get("hsn_code"))
    if hsn_val is not None:
        payload["hsn_code"] = hsn_val

    desc_val = _clean_str(form.get("description"))
    if desc_val is not None:
        payload["description"] = desc_val

    unit_val = _clean_str(form.get("unit"))
    if unit_val is not None:
        payload["unit"] = unit_val

    stock_val = _clean_str(form.get("stock_status"))
    if stock_val is not None:
        payload["stock_status"] = stock_val

    min_stock = _clean_int(form.get("min_stock_alert"))
    if min_stock is not None:
        payload["min_stock_alert"] = min_stock

    # Booleans
    if "is_active" in form:
        payload["is_active"] = _clean_bool(form.get("is_active"), default=True)

    if "track_batch" in form:
        payload["track_batch"] = _clean_bool(form.get("track_batch"), default=False)

    if "track_expiry" in form:
        payload["track_expiry"] = _clean_bool(form.get("track_expiry"), default=False)

    batch_val = _clean_str(form.get("batch_number"))
    if batch_val is not None:
        payload["batch_number"] = batch_val

    exp_val = _clean_str(form.get("expiry_date"))
    if exp_val is not None:
        payload["expiry_date"] = exp_val

    if final_image_url:
        payload["image_url"] = final_image_url

    if parsed_variants is not None:
        payload["variants"] = parsed_variants

    try:
        create_data = ProductCreate.model_validate(payload)
    except ValidationError as e:
        _raise_validation_error(e)

    product = ProductService(db).create_product(user.tenant_id, create_data)
    for idx, img_url in enumerate(uploaded_urls):
        _ensure_product_image_record(db, product.id, img_url, is_primary=(idx == 0))
    if not uploaded_urls and product.image_url:
        _ensure_product_image_record(db, product.id, product.image_url, is_primary=True)
    return product


@router.post(
    "/generate-missing-barcodes",
    summary="Generate Missing Barcodes in Bulk",
    description="Automatically generates and assigns unique 13-digit EAN barcodes for all products belonging to this tenant that currently have no barcode.",
    dependencies=[Depends(require_operational_write)],
)
def generate_missing_barcodes(
    user: User = Depends(require_permission("products:write")),
    db: Session = Depends(get_db),
):
    return ProductService(db).generate_missing_barcodes(
        user.tenant_id,
    )


@router.get(
    "/summary",
    response_model=ProductCatalogSummaryResponse,
    summary="Catalog Overview & Stock Valuation Dashboard",
    description="Get comprehensive product catalog overview, stock valuation, alert counts, and category breakdown.",
)
def get_catalog_summary(
    store_id: Optional[int] = Query(
        default=None,
        gt=0,
        description="Filter summary and stock valuation for a specific store ID",
    ),
    user: User = Depends(require_permission("products:read")),
    db: Session = Depends(get_db),
):
    return ProductService(db).get_catalog_summary(
        tenant_id=user.tenant_id,
        store_id=store_id,
    )


@router.post(
    "/bulk",
    response_model=ProductBulkCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Bulk Product Creation / Import",
    description="Creates multiple products in bulk with validation and entitlement checks in a single atomic transaction.",
    dependencies=[Depends(require_operational_write)],
)
def bulk_create_products(
    payload: ProductBulkCreateRequest,
    user: User = Depends(require_permission("products:write")),
    db: Session = Depends(get_db),
):
    return ProductService(db).bulk_create_products(
        tenant_id=user.tenant_id,
        items=payload.products,
    )


@router.get(
    "/{product_id}",
    response_model=ProductResponse,
)
def get_product(
    product_id: int,
    user: User = Depends(
        require_permission("products:read")
    ),
    db: Session = Depends(get_db),
):
    return ProductService(db).get_product(
        user.tenant_id,
        product_id,
    )


PRODUCT_UPDATE_OPENAPI_EXTRA = {
    "requestBody": {
        "required": False,
        "content": {
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "title": "ProductUpdateFormData",
                    "properties": {
                        "name": {
                            "type": "string",
                            "title": "Product Name",
                            "description": "Full product name (2 to 255 chars, e.g. Fortune Sunflower Oil 1L)",
                        },
                        "sku": {
                            "type": "string",
                            "title": "Product SKU",
                            "description": "Unique SKU code in uppercase alphanumeric (e.g. OIL-SUN-001)",
                        },
                        "selling_price": {
                            "type": "number",
                            "title": "Selling Price (Rs.)",
                            "description": "Final retail selling price per unit (must be greater than 0)",
                        },
                        "mrp": {
                            "type": "number",
                            "title": "Maximum Retail Price (MRP Rs.)",
                            "description": "Printed MRP on pack (must be >= Selling Price, or 0 if unpriced)",
                        },
                        "category_id": {
                            "type": "integer",
                            "title": "Category ID",
                            "description": "ID of existing category",
                        },
                        "brand": {
                            "type": "string",
                            "title": "Brand Name",
                            "description": "Brand / manufacturer name (e.g. Fortune, Nestle, Amul)",
                        },
                        "barcode": {
                            "type": "string",
                            "title": "Barcode / EAN",
                            "description": "Product barcode digits (8 to 50 numeric digits)",
                        },
                        "unit": {
                            "type": "string",
                            "title": "Unit of Measurement",
                            "description": "Packaging unit (e.g. pcs, kg, g, ltr, ml, box, pack)",
                        },
                        "hsn_code": {
                            "type": "string",
                            "title": "HSN Code",
                            "description": "4, 6, or 8 digits HSN code (e.g. 15121910)",
                        },
                        "gst_rate": {
                            "type": "number",
                            "title": "GST Rate (%)",
                            "description": "Standard Indian GST slab: 0, 5, 12, 18, or 28",
                        },
                        "min_stock_alert": {
                            "type": "integer",
                            "title": "Low Stock Alert Threshold",
                            "description": "Alert threshold quantity when inventory gets low (e.g. 5 or 10)",
                        },
                        "stock_status": {
                            "type": "string",
                            "title": "Stock Status",
                            "description": "Current stock status: in_stock or out_of_stock",
                        },
                        "description": {
                            "type": "string",
                            "title": "Product Description",
                            "description": "Detailed product description, specifications, or notes",
                        },
                        "is_active": {
                            "type": "boolean",
                            "title": "Is Active",
                            "description": "Set to true to make product available for sale, or false to disable",
                        },
                        "track_batch": {
                            "type": "boolean",
                            "title": "Track Batch / Lot",
                            "description": "Set to true if tracking batch numbers",
                        },
                        "track_expiry": {
                            "type": "boolean",
                            "title": "Track Expiry Date",
                            "description": "Set to true if product has expiry",
                        },
                        "batch_number": {
                            "type": "string",
                            "title": "Batch Number",
                            "description": "Batch / Lot identifier (e.g. BATCH-2026-A)",
                        },
                        "expiry_date": {
                            "type": "string",
                            "format": "date",
                            "title": "Expiry Date (YYYY-MM-DD)",
                            "description": "Expiration date YYYY-MM-DD (must be today or a future date)",
                        },
                        "image": {
                            "type": "string",
                            "format": "binary",
                            "title": "Product Photo File",
                            "description": "Upload new product photo file (.jpg, .jpeg, .png, .webp - Max 10MB)",
                        },
                    },
                },
            },
            "application/json": {
                "schema": {
                    "type": "object",
                    "title": "ProductUpdateJSON",
                    "properties": {
                        "name": {
                            "type": "string",
                            "title": "Product Name",
                            "description": "Full product name (2 to 255 chars, e.g. Fortune Sunflower Oil 1L)",
                        },
                        "sku": {
                            "type": "string",
                            "title": "Product SKU",
                            "description": "Unique SKU code in uppercase alphanumeric (e.g. OIL-SUN-001)",
                        },
                        "selling_price": {
                            "type": "number",
                            "title": "Selling Price (Rs.)",
                            "description": "Final retail selling price per unit (must be greater than 0)",
                        },
                        "mrp": {
                            "type": "number",
                            "title": "Maximum Retail Price (MRP Rs.)",
                            "description": "Printed MRP on pack (must be >= Selling Price, or 0 if unpriced)",
                        },
                        "category_id": {
                            "type": "integer",
                            "title": "Category ID",
                            "description": "ID of existing category",
                        },
                        "brand": {
                            "type": "string",
                            "title": "Brand Name",
                            "description": "Brand / manufacturer name (e.g. Fortune, Nestle, Amul)",
                        },
                        "barcode": {
                            "type": "string",
                            "title": "Barcode / EAN",
                            "description": "Product barcode digits (8 to 50 numeric digits)",
                        },
                        "unit": {
                            "type": "string",
                            "title": "Unit of Measurement",
                            "description": "Packaging unit (e.g. pcs, kg, g, ltr, ml, box, pack)",
                        },
                        "hsn_code": {
                            "type": "string",
                            "title": "HSN Code",
                            "description": "4, 6, or 8 digits HSN code (e.g. 15121910)",
                        },
                        "gst_rate": {
                            "type": "number",
                            "title": "GST Rate (%)",
                            "description": "Standard Indian GST slab: 0, 5, 12, 18, or 28",
                        },
                        "min_stock_alert": {
                            "type": "integer",
                            "title": "Low Stock Alert Threshold",
                            "description": "Alert threshold quantity when inventory gets low (e.g. 5 or 10)",
                        },
                        "stock_status": {
                            "type": "string",
                            "title": "Stock Status",
                            "description": "Current stock status: in_stock or out_of_stock",
                        },
                        "description": {
                            "type": "string",
                            "title": "Product Description",
                            "description": "Detailed product description, specifications, or notes",
                        },
                        "is_active": {
                            "type": "boolean",
                            "title": "Is Active",
                            "description": "Set to true to make product available for sale, or false to disable",
                        },
                        "track_batch": {
                            "type": "boolean",
                            "title": "Track Batch / Lot",
                            "description": "Set to true if tracking batch numbers",
                        },
                        "track_expiry": {
                            "type": "boolean",
                            "title": "Track Expiry Date",
                            "description": "Set to true if product has expiry",
                        },
                        "batch_number": {
                            "type": "string",
                            "title": "Batch Number",
                            "description": "Batch / Lot identifier",
                        },
                        "expiry_date": {
                            "type": "string",
                            "format": "date",
                            "title": "Expiry Date (YYYY-MM-DD)",
                            "description": "Expiration date YYYY-MM-DD (must be today or a future date)",
                        },
                    },
                },
            },
        },
    },
}


@router.patch(
    "/{product_id}",
    response_model=ProductResponse,
    summary="Update Product",
    description="Updates a product. Supports both multipart/form-data (with direct image file upload) and application/json.",
    openapi_extra=PRODUCT_UPDATE_OPENAPI_EXTRA,
    dependencies=[Depends(require_operational_write)],
)
async def update_product(
    product_id: int,
    request: Request,
    user: User = Depends(
        require_permission("products:write")
    ),
    db: Session = Depends(get_db),
):
    content_type = request.headers.get("content-type", "").lower()

    if "application/json" in content_type:
        try:
            body = await request.json()
        except Exception as e:
            raise HTTPException(status_code=400, detail="Invalid JSON body") from e

        if isinstance(body, dict):
            if "gst_rate" in body and "tax_rate" not in body:
                body["tax_rate"] = body["gst_rate"]

        try:
            update_data = ProductUpdate.model_validate(body)
        except ValidationError as e:
            _raise_validation_error(e)

        return ProductService(db).update_product(
            user.tenant_id,
            product_id,
            update_data,
        )

    # 2. Multipart / Form-data handling
    form = await request.form()

    upload_file: Any = None
    for field_key in ("image", "file"):
        val = form.get(field_key)
        if hasattr(val, "filename") and hasattr(val, "read") and getattr(val, "filename", None):
            upload_file = val
            break

    uploaded_url = await _save_product_image(upload_file)

    payload: Dict[str, Any] = {}

    name_val = _clean_str(form.get("name"))
    if name_val is not None:
        payload["name"] = name_val

    sku_val = _clean_str(form.get("sku"))
    if sku_val is not None:
        payload["sku"] = sku_val

    sp_val = _clean_decimal(form.get("selling_price"))
    if sp_val is not None:
        payload["selling_price"] = sp_val

    mrp_val = _clean_decimal(form.get("mrp"))
    if mrp_val is not None:
        payload["mrp"] = mrp_val

    cat_id = _clean_int(form.get("category_id"))
    if cat_id is not None:
        payload["category_id"] = cat_id

    brand_val = _clean_str(form.get("brand"))
    if brand_val is not None:
        payload["brand"] = brand_val

    barcode_val = _clean_str(form.get("barcode"))
    if barcode_val is not None:
        payload["barcode"] = barcode_val

    unit_val = _clean_str(form.get("unit"))
    if unit_val is not None:
        payload["unit"] = unit_val

    hsn_val = _clean_str(form.get("hsn_code"))
    if hsn_val is not None:
        payload["hsn_code"] = hsn_val

    gst_val = _clean_decimal(form.get("gst_rate"))
    if gst_val is not None:
        payload["gst_rate"] = gst_val
        payload["tax_rate"] = gst_val

    min_stock = _clean_int(form.get("min_stock_alert"))
    if min_stock is not None:
        payload["min_stock_alert"] = min_stock

    stock_val = _clean_str(form.get("stock_status"))
    if stock_val is not None:
        payload["stock_status"] = stock_val

    desc_val = _clean_str(form.get("description"))
    if desc_val is not None:
        payload["description"] = desc_val

    if "is_active" in form:
        b = _clean_optional_bool(form.get("is_active"))
        if b is not None:
            payload["is_active"] = b

    if "track_batch" in form:
        b = _clean_optional_bool(form.get("track_batch"))
        if b is not None:
            payload["track_batch"] = b

    if "track_expiry" in form:
        b = _clean_optional_bool(form.get("track_expiry"))
        if b is not None:
            payload["track_expiry"] = b

    batch_val = _clean_str(form.get("batch_number"))
    if batch_val is not None:
        payload["batch_number"] = batch_val

    exp_val = _clean_str(form.get("expiry_date"))
    if exp_val is not None:
        payload["expiry_date"] = exp_val

    if uploaded_url:
        payload["image_url"] = uploaded_url

    try:
        update_data = ProductUpdate.model_validate(payload)
    except ValidationError as e:
        _raise_validation_error(e)

    product = ProductService(db).update_product(
        user.tenant_id,
        product_id,
        update_data,
    )
    if uploaded_url:
        _ensure_product_image_record(db, product.id, uploaded_url)
    return product


@router.patch(
    "/{product_id}/toggle-status",
    response_model=ProductResponse,
    dependencies=[Depends(require_operational_write)],
)
def toggle_product_status(
    product_id: int,
    user: User = Depends(
        require_permission("products:write")
    ),
    db: Session = Depends(get_db),
):
    return ProductService(db).toggle_status(
        user.tenant_id,
        product_id,
    )




@router.get(
    "/{product_id}/barcode-label",
    response_model=ProductBarcodeLabelResponse,
    summary="Printable Barcode Sticker",
    description="Generates print-ready thermal barcode sticker data (50x25mm). Select mode: 'preview' (display barcode image directly in Swagger/browser), 'download' (download PNG file), 'html' (printable web page), or 'json' (raw sticker data).",
)
def get_barcode_label(
    product_id: int,
    mode: BarcodeLabelMode = Query(
        default=BarcodeLabelMode.JSON,
        description="Select output mode: json, preview (direct barcode image in Swagger), html (printable sticker page), or download",
    ),
    store_id: Optional[int] = Query(
        default=None,
        gt=0,
        description="Optional store ID to include store name on label",
    ),
    format: Optional[str] = Query(
        default=None,
        description="Deprecated alias for mode ('json', 'html', 'preview', 'download')",
        include_in_schema=False,
    ),
    user: User = Depends(require_permission("products:read")),
    db: Session = Depends(get_db),
):
    label_data = ProductService(db).get_barcode_label(
        tenant_id=user.tenant_id,
        product_id=product_id,
        store_id=store_id,
    )
    label = ProductBarcodeLabelResponse.model_validate(label_data) if isinstance(label_data, dict) else label_data

    selected_mode = (format or mode.value).lower()

    if selected_mode in ("preview", "download"):
        sticker_bytes = ProductService(db).get_barcode_sticker_image(
            tenant_id=user.tenant_id,
            product_id=product_id,
            store_id=store_id,
        )
        disposition = "inline" if selected_mode == "preview" else "attachment"
        return Response(
            content=sticker_bytes,
            media_type="image/png",
            headers={
                "Content-Disposition": f"{disposition}; filename=sticker-{label.barcode}.png"
            },
        )

    if selected_mode == "html":
        store_title = label.store_name or "RETAIL STORE"
        curr = label.currency_symbol or "₹"
        mrp_val = float(label.mrp) if label.mrp is not None else 0.0
        price_val = float(label.selling_price) if label.selling_price is not None else 0.0
        mrp_line = f'<span class="mrp">MRP: {curr}{mrp_val:.2f}</span>' if mrp_val > 0 else '<span></span>'
        price_line = f'<span class="price">OUR PRICE: {curr}{price_val:.2f}</span>'
        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Barcode Sticker - {label.product_name}</title>
    <style>
        @page {{
            size: 50mm 25mm;
            margin: 0;
        }}
        body {{
            margin: 0;
            padding: 24px;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
            background: #f8fafc;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            min-height: 80vh;
        }}
        .controls {{
            margin-bottom: 24px;
            display: flex;
            gap: 12px;
        }}
        .btn {{
            background: #2563eb;
            color: #ffffff;
            border: none;
            padding: 10px 20px;
            border-radius: 8px;
            cursor: pointer;
            font-weight: 600;
            font-size: 15px;
            box-shadow: 0 2px 4px rgba(37, 99, 235, 0.2);
            transition: all 0.2s;
        }}
        .btn:hover {{
            background: #1d4ed8;
            transform: translateY(-1px);
        }}
        .preview-wrapper {{
            padding: 16px;
            background: #ffffff;
            border-radius: 12px;
            box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.1), 0 8px 10px -6px rgba(0, 0, 0, 0.1);
        }}
        .sticker {{
            width: 50mm;
            height: 25mm;
            box-sizing: border-box;
            background: #ffffff;
            border: 1px dashed #94a3b8;
            padding: 1.5mm 2mm;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            align-items: center;
            text-align: center;
        }}
        .store-name {{
            font-size: 7.5pt;
            font-weight: 800;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            line-height: 1;
            margin: 0;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            max-width: 46mm;
            color: #0f172a;
        }}
        .prod-name {{
            font-size: 7pt;
            font-weight: 600;
            line-height: 1.1;
            margin: 0;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            max-width: 46mm;
            color: #1e293b;
        }}
        .barcode-img {{
            height: 11mm;
            max-width: 46mm;
            object-fit: contain;
            margin: 0;
        }}
        .pricing {{
            width: 100%;
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 6.5pt;
            line-height: 1;
            margin: 0;
            padding: 0 0.5mm;
            box-sizing: border-box;
        }}
        .mrp {{
            color: #64748b;
            text-decoration: line-through;
            font-weight: 500;
        }}
        .price {{
            font-weight: 800;
            font-size: 7.5pt;
            color: #000000;
        }}
        @media print {{
            body {{
                background: none;
                padding: 0;
                display: block;
            }}
            .controls, .preview-wrapper {{
                background: none;
                padding: 0;
                box-shadow: none;
                border-radius: 0;
            }}
            .controls {{
                display: none !important;
            }}
            .sticker {{
                border: none;
                margin: 0;
                page-break-after: always;
            }}
        }}
    </style>
</head>
<body>
    <div class="controls">
        <button class="btn" onclick="window.print()">🖨️ Print Barcode Sticker (50x25mm)</button>
    </div>
    <div class="preview-wrapper">
        <div class="sticker">
            <div class="store-name">{store_title}</div>
            <div class="prod-name">{label.product_name}</div>
            <img class="barcode-img" src="{label.barcode_image_base64}" alt="Barcode {label.barcode}" />
            <div class="pricing">
                {mrp_line}
                {price_line}
            </div>
        </div>
    </div>
</body>
</html>"""
        return HTMLResponse(content=html)
    return label


@router.post(
    "/{product_id}/generate-barcode",
    response_model=ProductResponse,
    summary="Generate Barcode for Product",
    description="Automatically generates and assigns a unique 13-digit EAN barcode for the specified product. If the product already has a barcode, it will be protected and rejected with 409 Conflict unless overwrite=true is provided.",
    dependencies=[Depends(require_operational_write)],
)
def generate_product_barcode(
    product_id: int,
    overwrite: bool = Query(
        default=False,
        description="Set to true to explicitly overwrite an existing barcode",
    ),
    user: User = Depends(require_permission("products:write")),
    db: Session = Depends(get_db),
):
    return ProductService(db).generate_barcode_for_product(
        user.tenant_id,
        product_id,
        overwrite=overwrite,
    )


@router.delete(
    "/{product_id}",
    status_code=204,
    responses={
        204: {
            "description": "Product deleted successfully",
        }
    },
    dependencies=[Depends(require_operational_write)],
)
def delete_product(
    product_id: int,
    user: User = Depends(
        require_permission("products:write")
    ),
    db: Session = Depends(get_db),
):
    ProductService(db).delete_product(
        user.tenant_id,
        product_id,
    )


ADD_IMAGE_OPENAPI_EXTRA = {
    "requestBody": {
        "required": True,
        "content": {
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "title": "AddProductImageFormData",
                    "properties": {
                        "images": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "format": "binary",
                            },
                            "title": "Product Photos (Multiple Files)",
                            "description": "Upload multiple product photo files (.jpg, .jpeg, .png, .webp - Max 10MB each)",
                        },
                        "image": {
                            "type": "string",
                            "format": "binary",
                            "title": "Single Photo File (Backward Compatible)",
                        },
                        "is_primary": {
                            "type": "boolean",
                            "title": "Set First Photo as Primary",
                            "description": "True to make first photo the primary cover photo",
                            "default": False,
                        },
                    },
                },
            },
            "application/json": {
                "schema": {
                    "type": "object",
                    "title": "AddProductImageJSON",
                    "properties": {
                        "image_url": {
                            "type": "string",
                            "title": "Photo URL / Path",
                            "description": "Public URL or relative path of the photo (e.g. /uploads/products/photo.png)",
                        },
                        "image_urls": {
                            "type": "array",
                            "items": {"type": "string"},
                            "title": "Multiple Photo URLs",
                            "description": "List of photo URLs to add",
                        },
                        "is_primary": {
                            "type": "boolean",
                            "title": "Set as Primary Photo",
                            "description": "True to make this the main product photo, or false for gallery photo",
                            "default": False,
                        },
                    },
                },
            },
        },
    },
}


@router.post(
    "/{product_id}/images",
    response_model=Union[list[ProductImageResponse], ProductImageResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Add Product Images",
    description="Uploads one or multiple photo files for a product gallery. Supports both multipart/form-data (multi-file upload) and application/json.",
    openapi_extra=ADD_IMAGE_OPENAPI_EXTRA,
    dependencies=[Depends(require_operational_write)],
)
async def add_product_image(
    product_id: int,
    request: Request,
    user: User = Depends(
        require_permission("products:write")
    ),
    db: Session = Depends(get_db),
):
    product = ProductService(db).get_product(
        user.tenant_id,
        product_id,
    )

    content_type = request.headers.get("content-type", "").lower()
    created_images: list[ProductImage] = []

    if "application/json" in content_type:
        try:
            body = await request.json()
        except Exception as e:
            raise HTTPException(status_code=400, detail="Invalid JSON body") from e

        is_primary = bool(body.get("is_primary", False))
        urls = []
        if body.get("image_urls") and isinstance(body.get("image_urls"), list):
            urls.extend(body.get("image_urls"))
        elif body.get("image_url"):
            urls.append(body.get("image_url"))

        if not urls:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="image_url or image_urls is required",
            )

        if is_primary:
            db.query(ProductImage).filter(
                ProductImage.product_id == product.id
            ).update({"is_primary": False})

        has_existing_primary = (
            db.query(ProductImage.id)
            .filter(ProductImage.product_id == product.id, ProductImage.is_primary.is_(True))
            .first()
            is not None
        )

        for idx, u in enumerate(urls):
            should_be_primary = False
            if is_primary and idx == 0:
                should_be_primary = True
            elif not has_existing_primary and idx == 0:
                should_be_primary = True

            img = ProductImage(product_id=product.id, image_url=u, is_primary=should_be_primary)
            db.add(img)
            created_images.append(img)

        db.commit()
        for img in created_images:
            db.refresh(img)

        return created_images if len(created_images) > 1 else created_images[0]

    # Multipart / Form-data handling (supports multi-file upload)
    form = await request.form()
    is_primary = _clean_bool(form.get("is_primary"), default=False)

    upload_files: list[Any] = []
    for field_key in ("images", "image", "files", "file"):
        for f in form.getlist(field_key):
            if hasattr(f, "filename") and hasattr(f, "read") and getattr(f, "filename", None):
                upload_files.append(f)

    uploaded_urls: list[str] = []
    for f in upload_files:
        u = await _save_product_image(f)
        if u:
            uploaded_urls.append(u)

    raw_single_url = _clean_str(form.get("image_url"))
    if raw_single_url and not uploaded_urls:
        uploaded_urls.append(raw_single_url)

    if not uploaded_urls:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one image file or image_url is required",
        )

    if is_primary:
        db.query(ProductImage).filter(
            ProductImage.product_id == product.id
        ).update({"is_primary": False})

    has_existing_primary = (
        db.query(ProductImage.id)
        .filter(ProductImage.product_id == product.id, ProductImage.is_primary.is_(True))
        .first()
        is not None
    )

    for idx, u in enumerate(uploaded_urls):
        should_be_primary = False
        if is_primary and idx == 0:
            should_be_primary = True
        elif not has_existing_primary and idx == 0:
            should_be_primary = True

        img = ProductImage(product_id=product.id, image_url=u, is_primary=should_be_primary)
        db.add(img)
        created_images.append(img)

    db.commit()
    for img in created_images:
        db.refresh(img)

    return created_images if len(created_images) > 1 else created_images[0]


@router.get(
    "/{product_id}/images",
    response_model=list[ProductImageResponse],
)
def list_product_images(
    product_id: int,
    user: User = Depends(
        require_permission("products:read")
    ),
    db: Session = Depends(get_db),
):
    product = ProductService(db).get_product(
        user.tenant_id,
        product_id,
    )

    return (
        db.query(ProductImage)
        .filter(
            ProductImage.product_id == product.id
        )
        .order_by(
            ProductImage.is_primary.desc(),
            ProductImage.id.asc(),
        )
        .all()
    )


@router.delete(
    "/{product_id}/images/{image_id}",
    status_code=204,
    responses={
        204: {
            "description": "Product image deleted successfully",
        }
    },
    dependencies=[Depends(require_operational_write)],
)
def delete_product_image(
    product_id: int,
    image_id: int,
    user: User = Depends(
        require_permission("products:write")
    ),
    db: Session = Depends(get_db),
):
    product = ProductService(db).get_product(
        user.tenant_id,
        product_id,
    )

    image = (
        db.query(ProductImage)
        .filter(
            ProductImage.id == image_id,
            ProductImage.product_id == product.id,
        )
        .first()
    )

    if not image:
        raise HTTPException(
            status_code=404,
            detail="Product image not found",
        )

    was_primary = image.is_primary
    img_url = image.image_url

    db.delete(image)
    db.commit()

    if was_primary:
        next_img = (
            db.query(ProductImage)
            .filter(ProductImage.product_id == product.id)
            .order_by(ProductImage.id.asc())
            .first()
        )
        if next_img:
            next_img.is_primary = True
            db.commit()

    if img_url and img_url.startswith("/uploads/products/"):
        import os
        rel_path = img_url.lstrip("/")
        try:
            if os.path.exists(rel_path):
                os.remove(rel_path)
        except Exception:
            pass


# ============================================================================
# PRODUCT VARIANT NESTED ROUTES
# ============================================================================


@router.post(
    "/{product_id}/variants",
    response_model=ProductVariantResponse,
    status_code=201,
    dependencies=[Depends(require_operational_write)],
    description="Create a new variant for a specific product",
)
def create_product_variant(
    product_id: int = Path(..., gt=0, description="Parent Product ID"),
    data: ProductVariantCreate = ...,
    user: User = Depends(require_permission("products:write")),
    db: Session = Depends(get_db),
):
    return ProductVariantService(db).create_variant(
        tenant_id=user.tenant_id,
        product_id=product_id,
        data=data,
    )


@router.get(
    "/{product_id}/variants",
    response_model=ProductVariantListResponse,
    description="List all variants belonging to a specific product with pagination",
)
def list_product_variants(
    product_id: int = Path(..., gt=0, description="Parent Product ID"),
    page: int = Query(default=1, gt=0, description="Page number"),
    page_size: int = Query(default=20, gt=0, le=100, description="Page size"),
    include_inactive: bool = Query(default=False, description="Include inactive/soft-deleted variants"),
    user: User = Depends(require_permission("products:read")),
    db: Session = Depends(get_db),
):
    return ProductVariantService(db).list_variants(
        tenant_id=user.tenant_id,
        product_id=product_id,
        page=page,
        page_size=page_size,
        include_inactive=include_inactive,
    )


@router.get(
    "/{product_id}/variants/{variant_id}",
    response_model=ProductVariantResponse,
    description="Get details of a specific variant belonging to a product",
)
def get_product_variant(
    product_id: int = Path(..., gt=0, description="Parent Product ID"),
    variant_id: int = Path(..., gt=0, description="Variant ID"),
    user: User = Depends(require_permission("products:read")),
    db: Session = Depends(get_db),
):
    from app.core.exceptions import NotFoundException

    variant = ProductVariantService(db).get_variant(
        tenant_id=user.tenant_id,
        variant_id=variant_id,
    )
    if variant.product_id != product_id:
        raise NotFoundException("Variant not found for this product")
    return variant
