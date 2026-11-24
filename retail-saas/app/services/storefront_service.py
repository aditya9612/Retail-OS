from datetime import datetime
from decimal import Decimal
import json
from pathlib import Path
import uuid
from typing import Dict, List, Optional
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.exceptions import AppException, NotFoundException
from app.core.logger import logger
from app.core.redis_client import get_redis
from app.models.category import Category
from app.models.customer import Customer
from app.models.inventory import Inventory
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product import Product
from app.models.store import Store
from app.repositories.storefront_repo import StorefrontRepository
from app.schemas.storefront import (
    StorefrontAdvancedSettingsResponse,
    StorefrontAdvancedSettingsUpdate,
    StorefrontCartItemResponse,
    StorefrontCartResponse,
    StorefrontCategoryItem,
    StorefrontCheckoutRequest,
    StorefrontCheckoutResponse,
    StorefrontContactSocialResponse,
    StorefrontContactSocialUpdate,
    StorefrontCustomerProfileResponse,
    StorefrontCustomerProfileUpdate,
    StorefrontFeedbackRequest,
    StorefrontNotificationItem,
    StorefrontNotificationListResponse,
    StorefrontOrderCancelRequest,
    StorefrontOrderCancelResponse,
    StorefrontOrderDetailResponse,
    StorefrontOrderSummary,
    StorefrontOrderTrackingItem,
    StorefrontPagesResponse,
    StorefrontPagesUpdate,
    StorefrontProductDetailResponse,
    StorefrontProductItem,
    StorefrontProductListResponse,
    StorefrontReferralRequest,
    StorefrontSEODomainResponse,
    StorefrontSEODomainUpdate,
    StorefrontSettingResponse,
    StorefrontSettingUpdate,
    StorefrontUploadResponse,
)

ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".svg", ".ico", ".webp"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
UPLOAD_DIR = Path("uploads/storefront")


class StorefrontService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = StorefrontRepository(db)
        try:
            self.redis = get_redis()
        except Exception:
            self.redis = None
        self._local_cart_store: Dict[str, dict] = {}

    # --- Master All-in-One Settings ---
    def get_settings(
        self,
        tenant_id: int,
        store_id: Optional[int] = None,
    ) -> StorefrontSettingResponse:
        setting = self.repo.get_settings(tenant_id, store_id)
        res = StorefrontSettingResponse.model_validate(setting)
        if setting.meta_keywords:
            res.keywords = setting.meta_keywords
        return res

    def update_settings(
        self,
        tenant_id: int,
        store_id: Optional[int],
        data: StorefrontSettingUpdate,
    ) -> StorefrontSettingResponse:
        setting = self.repo.update_settings(tenant_id, store_id, data)
        res = StorefrontSettingResponse.model_validate(setting)
        if setting.meta_keywords:
            res.keywords = setting.meta_keywords
        return res

    def toggle_online_status(
        self,
        tenant_id: int,
        store_id: Optional[int],
        is_online: bool,
    ) -> StorefrontSettingResponse:
        setting = self.repo.toggle_online_status(tenant_id, store_id, is_online)
        return StorefrontSettingResponse.model_validate(setting)

    # --- Tab 2: SEO & Domain ---
    def get_seo_domain(
        self,
        tenant_id: int,
        store_id: Optional[int] = None,
    ) -> StorefrontSEODomainResponse:
        setting = self.repo.get_settings(tenant_id, store_id)
        return StorefrontSEODomainResponse(
            default_store_url=setting.default_store_url or f"{setting.url_slug or 'retailos-shop'}.mystore.in",
            custom_domain=setting.custom_domain,
            url_slug=setting.url_slug,
            meta_title=setting.meta_title,
            meta_description=setting.meta_description,
            keywords=setting.meta_keywords,
            google_analytics_id=setting.google_analytics_id,
        )

    def update_seo_domain(
        self,
        tenant_id: int,
        store_id: Optional[int],
        data: StorefrontSEODomainUpdate,
    ) -> StorefrontSEODomainResponse:
        update_data = StorefrontSettingUpdate(
            custom_domain=data.custom_domain,
            url_slug=data.url_slug,
            meta_title=data.meta_title,
            meta_description=data.meta_description,
            meta_keywords=data.keywords,
            google_analytics_id=data.google_analytics_id,
        )
        setting = self.repo.update_settings(tenant_id, store_id, update_data)
        return StorefrontSEODomainResponse(
            default_store_url=setting.default_store_url,
            custom_domain=setting.custom_domain,
            url_slug=setting.url_slug,
            meta_title=setting.meta_title,
            meta_description=setting.meta_description,
            keywords=setting.meta_keywords,
            google_analytics_id=setting.google_analytics_id,
        )

    # --- Tab 3: Store Pages ---
    def get_pages(
        self,
        tenant_id: int,
        store_id: Optional[int] = None,
    ) -> StorefrontPagesResponse:
        setting = self.repo.get_settings(tenant_id, store_id)
        return StorefrontPagesResponse.model_validate(setting)

    def update_pages(
        self,
        tenant_id: int,
        store_id: Optional[int],
        data: StorefrontPagesUpdate,
    ) -> StorefrontPagesResponse:
        update_data = StorefrontSettingUpdate(
            about_us=data.about_us,
            contact_us=data.contact_us,
            privacy_policy=data.privacy_policy,
            terms_conditions=data.terms_conditions if data.terms_conditions is not None else data.terms_and_conditions,
            return_policy=data.return_policy if data.return_policy is not None else data.refund_policy,
        )
        setting = self.repo.update_settings(tenant_id, store_id, update_data)
        return StorefrontPagesResponse.model_validate(setting)

    # --- Tab 4: Contact & Social ---
    def get_contact_social(
        self,
        tenant_id: int,
        store_id: Optional[int] = None,
    ) -> StorefrontContactSocialResponse:
        setting = self.repo.get_settings(tenant_id, store_id)
        return StorefrontContactSocialResponse.model_validate(setting)

    def update_contact_social(
        self,
        tenant_id: int,
        store_id: Optional[int],
        data: StorefrontContactSocialUpdate,
    ) -> StorefrontContactSocialResponse:
        update_data = StorefrontSettingUpdate(
            contact_email=data.contact_email,
            contact_phone=data.contact_phone,
            whatsapp_number=data.whatsapp_number,
            address=data.address,
            instagram_url=data.instagram_url,
            facebook_url=data.facebook_url,
            twitter_url=data.twitter_url,
        )
        setting = self.repo.update_settings(tenant_id, store_id, update_data)
        return StorefrontContactSocialResponse.model_validate(setting)

    # --- Tab 5: Advanced Settings ---
    def get_advanced_settings(
        self,
        tenant_id: int,
        store_id: Optional[int] = None,
    ) -> StorefrontAdvancedSettingsResponse:
        setting = self.repo.get_settings(tenant_id, store_id)
        return StorefrontAdvancedSettingsResponse.model_validate(setting)

    def update_advanced_settings(
        self,
        tenant_id: int,
        store_id: Optional[int],
        data: StorefrontAdvancedSettingsUpdate,
    ) -> StorefrontAdvancedSettingsResponse:
        m_mode = data.is_maintenance_mode if data.is_maintenance_mode is not None else data.maintenance_mode
        update_data = StorefrontSettingUpdate(
            enable_product_reviews=data.enable_product_reviews,
            show_out_of_stock=data.show_out_of_stock,
            guest_checkout=data.guest_checkout,
            wishlist_enabled=data.wishlist_enabled,
            auto_sync_inventory=data.auto_sync_inventory,
            enable_coupons=data.enable_coupons,
            gst_invoice_enabled=data.gst_invoice_enabled,
            is_maintenance_mode=m_mode,
        )
        setting = self.repo.update_settings(tenant_id, store_id, update_data)
        return StorefrontAdvancedSettingsResponse.model_validate(setting)

    # --- Asset Upload ---
    def upload_asset(
        self,
        tenant_id: int,
        store_id: Optional[int],
        asset_type: str,
        filename: str,
        content: bytes,
    ) -> StorefrontUploadResponse:
        clean_type = asset_type.strip().lower()
        if clean_type not in {"logo", "banner", "favicon", "og_image"}:
            raise AppException("Invalid asset_type. Allowed: logo, banner, favicon, og_image")

        if not filename:
            raise AppException("Filename cannot be empty")

        ext = Path(filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise AppException(f"Unsupported file format '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}")

        if len(content) > MAX_FILE_SIZE:
            raise AppException("File size exceeds 5MB limit")

        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        safe_filename = f"{clean_type}_{tenant_id}_{uuid.uuid4().hex[:8]}{ext}"
        target_path = UPLOAD_DIR / safe_filename

        with open(target_path, "wb") as f:
            f.write(content)

        file_url = f"/uploads/storefront/{safe_filename}"
        self.repo.update_asset(tenant_id, store_id, clean_type, file_url)

        return StorefrontUploadResponse(
            asset_type=clean_type,
            url=file_url,
            message=f"{clean_type.capitalize()} uploaded and updated successfully",
        )

    # --- Public Storefront Profile ---
    def get_public_storefront(
        self,
        tenant_id: Optional[int] = None,
        subdomain: Optional[str] = None,
        store_id: Optional[int] = None,
    ) -> StorefrontSettingResponse:
        setting = self.repo.get_public_storefront(tenant_id, subdomain, store_id)
        if not setting:
            raise NotFoundException("Storefront not found")
        return StorefrontSettingResponse.model_validate(setting)

    def _cart_key(self, tenant_id: int, customer_id: int) -> str:
        return f"storefront:cart:{tenant_id}:{customer_id}"

    def _load_cart_data(self, tenant_id: int, customer_id: int) -> dict:
        key = self._cart_key(tenant_id, customer_id)
        if self.redis:
            try:
                raw = self.redis.get(key)
                if raw:
                    return json.loads(raw)
            except Exception:
                pass
        return self._local_cart_store.get(key, {"items": {}})

    def _save_cart_data(self, tenant_id: int, customer_id: int, cart: dict) -> None:
        key = self._cart_key(tenant_id, customer_id)
        if self.redis:
            try:
                self.redis.setex(key, 86400 * 7, json.dumps(cart))
            except Exception:
                pass
        self._local_cart_store[key] = cart

    # --------------------------------------------------------------------------
    # 1. Catalog & Categories
    # --------------------------------------------------------------------------

    def get_categories(self, tenant_id: int) -> List[StorefrontCategoryItem]:
        categories = (
            self.db.query(Category)
            .filter(Category.tenant_id == tenant_id, Category.is_active.is_(True))
            .order_by(Category.name.asc())
            .all()
        )
        return [
            StorefrontCategoryItem(
                id=c.id,
                name=c.name,
                description=c.description,
            )
            for c in categories
        ]

    def get_products(
        self,
        tenant_id: int,
        store_id: Optional[int] = None,
        category_id: Optional[int] = None,
        search: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> StorefrontProductListResponse:
        query = self.db.query(Product).filter(
            Product.tenant_id == tenant_id,
            Product.is_active.is_(True),
        )

        if category_id:
            query = query.filter(Product.category_id == category_id)

        if search:
            search_clean = search.strip()
            query = query.filter(
                (Product.name.ilike(f"%{search_clean}%"))
                | (Product.barcode == search_clean)
                | (Product.sku.ilike(f"%{search_clean}%"))
            )

        total = query.count()
        products = (
            query.order_by(Product.name.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        # Map inventory stock if store_id provided
        stock_map = {}
        if store_id:
            p_ids = [p.id for p in products]
            if p_ids:
                inv_records = (
                    self.db.query(Inventory)
                    .filter(
                        Inventory.tenant_id == tenant_id,
                        Inventory.store_id == store_id,
                        Inventory.product_id.in_(p_ids),
                    )
                    .all()
                )
                for inv in inv_records:
                    stock_map[inv.product_id] = inv.quantity

        items = []
        for p in products:
            curr_stock = stock_map.get(p.id, 999) if store_id else 999
            selling_price = getattr(p, "selling_price", getattr(p, "price", Decimal("0.00")))
            mrp_val = getattr(p, "mrp", selling_price) or selling_price
            items.append(
                StorefrontProductItem(
                    id=p.id,
                    name=p.name,
                    sku=p.sku,
                    price=Decimal(str(selling_price)),
                    mrp=Decimal(str(mrp_val)),
                    unit=getattr(p, "unit", "pcs"),
                    category_id=p.category_id,
                    category_name=p.category.name if p.category else None,
                    in_stock=(curr_stock > 0),
                    stock_quantity=max(0, curr_stock),
                    image_url=p.image_url,
                )
            )

        return StorefrontProductListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        )

    def get_product_detail(
        self,
        tenant_id: int,
        product_id: int,
        store_id: Optional[int] = None,
    ) -> StorefrontProductDetailResponse:
        product = (
            self.db.query(Product)
            .filter(
                Product.id == product_id,
                Product.tenant_id == tenant_id,
                Product.is_active.is_(True),
            )
            .first()
        )
        if not product:
            raise NotFoundException(f"Product #{product_id} not found or inactive")

        curr_stock = 999
        if store_id:
            inv = (
                self.db.query(Inventory)
                .filter(
                    Inventory.tenant_id == tenant_id,
                    Inventory.store_id == store_id,
                    Inventory.product_id == product.id,
                )
                .first()
            )
            if inv is not None:
                curr_stock = inv.quantity

        selling_price = getattr(product, "selling_price", getattr(product, "price", Decimal("0.00")))
        mrp_val = getattr(product, "mrp", selling_price) or selling_price

        image_urls = []
        if hasattr(product, "images") and product.images:
            image_urls = [img.image_url for img in product.images if getattr(img, "image_url", None)]
        if not image_urls and product.image_url:
            image_urls = [product.image_url]

        return StorefrontProductDetailResponse(
            id=product.id,
            name=product.name,
            sku=product.sku,
            barcode=getattr(product, "barcode", None),
            description=getattr(product, "description", None),
            price=Decimal(str(selling_price)),
            mrp=Decimal(str(mrp_val)),
            unit=getattr(product, "unit", "pcs"),
            category_id=product.category_id,
            category_name=product.category.name if product.category else None,
            in_stock=(curr_stock > 0),
            stock_quantity=max(0, curr_stock),
            image_url=product.image_url,
            images=image_urls,
        )

    # --------------------------------------------------------------------------
    # 2. Shopping Cart
    # --------------------------------------------------------------------------

    def get_cart(self, tenant_id: int, customer_id: int) -> StorefrontCartResponse:
        cart_data = self._load_cart_data(tenant_id, customer_id)
        raw_items = cart_data.get("items", {})

        cart_items: List[StorefrontCartItemResponse] = []
        subtotal = Decimal("0.00")
        total_items = 0

        if raw_items:
            product_ids = [int(pid) for pid in raw_items.keys()]
            products = (
                self.db.query(Product)
                .filter(Product.tenant_id == tenant_id, Product.id.in_(product_ids))
                .all()
            )
            prod_dict = {p.id: p for p in products}

            for pid_str, item_info in raw_items.items():
                pid = int(pid_str)
                product = prod_dict.get(pid)
                if not product or not product.is_active:
                    continue

                qty = int(item_info.get("quantity", 1))
                price = Decimal(str(product.selling_price))
                item_total = price * qty

                cart_items.append(
                    StorefrontCartItemResponse(
                        product_id=product.id,
                        name=product.name,
                        unit_price=price,
                        quantity=qty,
                        total_price=item_total,
                        unit=getattr(product, "unit", "pcs"),
                        image_url=product.image_url,
                    )
                )
                subtotal += item_total
                total_items += qty

        # Estimated Tax (Intra-state GST approximation)
        tax_amount = (subtotal * Decimal("0.05")).quantize(Decimal("0.01"))
        total_amount = subtotal + tax_amount

        return StorefrontCartResponse(
            items=cart_items,
            subtotal=subtotal,
            discount_amount=Decimal("0.00"),
            tax_amount=tax_amount,
            total_amount=total_amount,
            total_items=total_items,
        )

    def add_to_cart(
        self,
        tenant_id: int,
        customer_id: int,
        product_id: int,
        quantity: int = 1,
    ) -> StorefrontCartResponse:
        product = (
            self.db.query(Product)
            .filter(
                Product.id == product_id,
                Product.tenant_id == tenant_id,
                Product.is_active.is_(True),
            )
            .first()
        )
        if not product:
            raise NotFoundException(f"Product {product_id} not found or inactive")

        cart_data = self._load_cart_data(tenant_id, customer_id)
        items = cart_data.setdefault("items", {})

        pid_str = str(product_id)
        current_qty = items.get(pid_str, {}).get("quantity", 0)
        new_qty = current_qty + quantity
        items[pid_str] = {"quantity": new_qty}

        self._save_cart_data(tenant_id, customer_id, cart_data)
        return self.get_cart(tenant_id, customer_id)

    def update_cart_item(
        self,
        tenant_id: int,
        customer_id: int,
        product_id: int,
        quantity: int,
    ) -> StorefrontCartResponse:
        cart_data = self._load_cart_data(tenant_id, customer_id)
        items = cart_data.setdefault("items", {})

        pid_str = str(product_id)
        if quantity <= 0:
            items.pop(pid_str, None)
        else:
            items[pid_str] = {"quantity": quantity}

        self._save_cart_data(tenant_id, customer_id, cart_data)
        return self.get_cart(tenant_id, customer_id)

    def remove_from_cart(
        self,
        tenant_id: int,
        customer_id: int,
        product_id: int,
    ) -> StorefrontCartResponse:
        return self.update_cart_item(tenant_id, customer_id, product_id, quantity=0)

    def clear_cart(self, tenant_id: int, customer_id: int) -> None:
        key = self._cart_key(tenant_id, customer_id)
        if self.redis:
            try:
                self.redis.delete(key)
            except Exception:
                pass
        self._local_cart_store.pop(key, None)

    # --------------------------------------------------------------------------
    # 3. Checkout & Order Placement
    # --------------------------------------------------------------------------

    def checkout(
        self,
        tenant_id: int,
        customer: Customer,
        payload: StorefrontCheckoutRequest,
    ) -> StorefrontCheckoutResponse:
        cart = self.get_cart(tenant_id, customer.id)
        if not cart.items:
            raise AppException("Your cart is empty. Please add items before checkout.")

        # Find store for this tenant (specified in payload, or main store, or first active store)
        store = None
        if getattr(payload, "store_id", None):
            store = (
                self.db.query(Store)
                .filter(Store.id == payload.store_id, Store.tenant_id == tenant_id, Store.is_active.is_(True))
                .first()
            )
        if not store:
            store = (
                self.db.query(Store)
                .filter(Store.tenant_id == tenant_id, Store.is_active.is_(True))
                .order_by(Store.is_main.desc(), Store.id.asc())
                .first()
            )
        if not store:
            raise NotFoundException("Store outlet not available for checkout")

        # Validate stock availability in the store before placing order
        for item in cart.items:
            inv = (
                self.db.query(Inventory)
                .filter(
                    Inventory.tenant_id == tenant_id,
                    Inventory.store_id == store.id,
                    Inventory.product_id == item.product_id,
                )
                .first()
            )
            if inv is not None and inv.quantity < item.quantity:
                raise AppException(
                    f"Product '{item.name}' has insufficient stock in {store.name} (Available: {inv.quantity}, Requested: {item.quantity})"
                )

        # Resolve delivery address
        final_address = payload.delivery_address or customer.address or "Store Pickup Counter"

        # Check wallet balance if payment_method is wallet
        wallet_obj = None
        if payload.payment_method == "wallet":
            from app.models.customer import CustomerWallet
            wallet_obj = self.db.query(CustomerWallet).filter(CustomerWallet.customer_id == customer.id).first()
            wallet_bal = Decimal(str(getattr(wallet_obj, "current_balance", getattr(wallet_obj, "balance", 0)) or 0))
            if wallet_bal < cart.total_amount:
                raise AppException(f"Insufficient wallet balance (Available: Rs.{wallet_bal}, Required: Rs.{cart.total_amount})")
            new_bal = wallet_bal - cart.total_amount
            if hasattr(wallet_obj, "current_balance"):
                wallet_obj.current_balance = new_bal
            if hasattr(wallet_obj, "balance"):
                wallet_obj.balance = new_bal

        # Generate unique order number
        order_uid = uuid.uuid4().hex[:6].upper()
        timestamp_str = datetime.utcnow().strftime("%y%m%d%H%M")
        order_number = f"ORD-ONL-{timestamp_str}-{order_uid}"

        # Intra-state tax splitting (half CGST, half SGST)
        half_tax = (cart.tax_amount / Decimal("2")).quantize(Decimal("0.01"))

        # Create Order
        order = Order(
            tenant_id=tenant_id,
            store_id=store.id,
            customer_id=customer.id,
            order_number=order_number,
            order_type="online",
            status="pending",
            subtotal=cart.subtotal,
            discount_amount=cart.discount_amount,
            cgst_amount=half_tax,
            sgst_amount=half_tax,
            igst_amount=Decimal("0.00"),
            tax_amount=cart.tax_amount,
            round_off=Decimal("0.00"),
            total_amount=cart.total_amount,
            payment_method=payload.payment_method.upper(),
            payment_status="paid" if payload.payment_method == "wallet" else "pending",
            delivery_address=final_address,
            notes=f"Mode: {payload.delivery_type.capitalize()} | Address: {final_address} | {payload.notes or ''}".strip(),
        )
        self.db.add(order)
        self.db.flush()

        # Log debit transaction if wallet was used
        if payload.payment_method == "wallet" and wallet_obj:
            try:
                from app.models.customer import WalletTransaction
                wallet_tx = WalletTransaction(
                    wallet_id=wallet_obj.id,
                    transaction_type="DEBIT",
                    amount=cart.total_amount,
                    reference_no=order_number,
                    remarks=f"Payment for online order #{order_number}",
                )
                self.db.add(wallet_tx)
            except Exception as e:
                logger.warning(f"Wallet transaction logging failed: {e}")

        # Create OrderItems
        for item in cart.items:
            half_item_tax = ((item.total_price * Decimal("0.05")) / Decimal("2")).quantize(Decimal("0.01"))
            order_item = OrderItem(
                order_id=order.id,
                product_id=item.product_id,
                quantity=item.quantity,
                unit_price=item.unit_price,
                discount_amount=Decimal("0.00"),
                cgst_amount=half_item_tax,
                sgst_amount=half_item_tax,
                igst_amount=Decimal("0.00"),
                tax_amount=half_item_tax * Decimal("2"),
                total_amount=item.total_price + (half_item_tax * Decimal("2")),
                notes=f"Online item: {item.name}",
            )
            self.db.add(order_item)

        # Create Delivery and Tracking records
        try:
            from app.models.delivery import Delivery
            from app.models.order import OrderTracking
            delivery = Delivery(
                tenant_id=tenant_id,
                order_id=order.id,
                status="pending",
            )
            self.db.add(delivery)

            tracking = OrderTracking(
                order_id=order.id,
                status="pending",
                remarks=f"Online order placed via Storefront ({payload.delivery_type.capitalize()})",
            )
            self.db.add(tracking)
        except Exception as e:
            logger.warning(f"Delivery/Tracking record creation skipped: {e}")

        # Deduct inventory stock for the store
        try:
            from app.schemas.inventory import StockOutRequest
            from app.services.inventory_service import InventoryService
            inv_service = InventoryService(self.db)
            for item in cart.items:
                inv_service.stock_out(
                    tenant_id=tenant_id,
                    data=StockOutRequest(
                        store_id=store.id,
                        product_id=item.product_id,
                        quantity=item.quantity,
                    ),
                    commit=False,
                )
        except Exception as e:
            logger.warning(f"Stock deduction skipped or unmanaged for storefront items: {e}")

        # Clear cart upon order creation
        self.clear_cart(tenant_id, customer.id)

        self.db.commit()
        self.db.refresh(order)

        # Asynchronously send WhatsApp confirmation if configured
        try:
            from app.tasks.whatsapp_tasks import send_order_confirmation_task
            send_order_confirmation_task.delay(
                phone=customer.phone,
                order_number=order.order_number,
                total=str(order.total_amount),
                tenant_id=tenant_id,
                store_id=store.id,
                store_name=store.name,
            )
        except Exception as exc:
            logger.info("WhatsApp order confirmation queued/skipped: %s", exc)

        return StorefrontCheckoutResponse(
            order_id=order.id,
            order_number=order.order_number,
            status=order.status,
            total_amount=order.total_amount,
            delivery_type=payload.delivery_type,
            payment_method=payload.payment_method,
            payment_status=order.payment_status,
            message="Order placed successfully! The store has received your order.",
            created_at=order.created_at or datetime.utcnow(),
        )

    # --------------------------------------------------------------------------
    # 4. Customer Orders & Self-Service
    # --------------------------------------------------------------------------

    def get_my_orders(
        self,
        tenant_id: int,
        customer_id: int,
    ) -> List[StorefrontOrderSummary]:
        orders = (
            self.db.query(Order)
            .filter(
                Order.tenant_id == tenant_id,
                Order.customer_id == customer_id,
            )
            .order_by(Order.id.desc())
            .all()
        )
        return [
            StorefrontOrderSummary(
                id=o.id,
                order_number=o.order_number,
                status=o.status,
                order_type=o.order_type,
                total_amount=o.total_amount,
                payment_method=o.payment_method,
                payment_status=o.payment_status,
                items_count=len(o.items) if o.items else 0,
                created_at=o.created_at or datetime.utcnow(),
            )
            for o in orders
        ]

    def get_order_details(
        self,
        tenant_id: int,
        customer_id: int,
        order_id: int,
    ) -> StorefrontOrderDetailResponse:
        order = (
            self.db.query(Order)
            .filter(
                Order.id == order_id,
                Order.tenant_id == tenant_id,
                Order.customer_id == customer_id,
            )
            .first()
        )
        if not order:
            raise NotFoundException(f"Order #{order_id} not found")

        items_list = []
        for it in order.items:
            items_list.append(
                {
                    "product_id": it.product_id,
                    "product_name": it.product.name if it.product else f"Product #{it.product_id}",
                    "quantity": it.quantity,
                    "unit_price": float(it.unit_price),
                    "total_amount": float(it.total_amount),
                    "image_url": it.product.image_url if (it.product and hasattr(it.product, "image_url")) else None,
                }
            )

        invoice_url = None
        if order.invoice:
            invoice_url = f"/api/v1/invoices/{order.invoice.id}/pdf"

        # Tracking timeline milestones
        tracking_items = []
        if hasattr(order, "tracking") and order.tracking:
            for t in order.tracking:
                tracking_items.append(
                    StorefrontOrderTrackingItem(
                        id=t.id,
                        status=t.status,
                        remarks=getattr(t, "notes", None) or getattr(t, "remarks", None),
                        created_at=t.created_at or order.created_at or datetime.utcnow(),
                    )
                )
        if not tracking_items:
            tracking_items.append(
                StorefrontOrderTrackingItem(
                    id=None,
                    status=order.status,
                    remarks=f"Order placed via Storefront ({order.payment_method or 'COD'})",
                    created_at=order.created_at or datetime.utcnow(),
                )
            )

        return StorefrontOrderDetailResponse(
            id=order.id,
            order_number=order.order_number,
            status=order.status,
            subtotal=order.subtotal,
            tax_amount=order.tax_amount,
            discount_amount=order.discount_amount,
            total_amount=order.total_amount,
            payment_method=order.payment_method,
            payment_status=order.payment_status,
            notes=order.notes,
            delivery_address=order.delivery_address or (order.notes if (order.notes and "Address:" in order.notes) else None),
            created_at=order.created_at or datetime.utcnow(),
            items=items_list,
            tracking=tracking_items,
            invoice_url=invoice_url,
        )

    def cancel_order(
        self,
        tenant_id: int,
        customer_id: int,
        order_id: int,
        payload: Optional[StorefrontOrderCancelRequest] = None,
    ) -> StorefrontOrderCancelResponse:
        order = (
            self.db.query(Order)
            .filter(
                Order.id == order_id,
                Order.tenant_id == tenant_id,
                Order.customer_id == customer_id,
            )
            .first()
        )
        if not order:
            raise NotFoundException(f"Order #{order_id} not found")

        if order.status.lower() in ["cancelled", "canceled"]:
            raise AppException("This order has already been cancelled.")

        non_cancellable = ["confirmed", "processing", "packed", "dispatched", "out_for_delivery", "delivered", "completed"]
        if order.status.lower() in non_cancellable:
            raise AppException(
                f"Cannot cancel order #{order.order_number} in '{order.status}' status. "
                "The store has already started processing or dispatching your order. Please contact store support."
            )

        # 1. Restore inventory stock
        for it in order.items:
            try:
                inv = (
                    self.db.query(Inventory)
                    .filter(
                        Inventory.tenant_id == tenant_id,
                        Inventory.store_id == order.store_id,
                        Inventory.product_id == it.product_id,
                    )
                    .first()
                )
                if inv:
                    inv.quantity += it.quantity
            except Exception as e:
                logger.warning(f"Stock restore skipped for item #{it.product_id}: {e}")

        # 2. Refund wallet if paid with wallet
        refunded_to_wallet = False
        refund_amount = None
        if str(order.payment_method).upper() == "WALLET" and order.payment_status.lower() == "paid":
            from app.models.customer import CustomerWallet, WalletTransaction
            wallet = self.db.query(CustomerWallet).filter(CustomerWallet.customer_id == customer_id).first()
            if not wallet:
                wallet = CustomerWallet(customer_id=customer_id, current_balance=Decimal("0.00"))
                self.db.add(wallet)
                self.db.flush()

            cur_bal = Decimal(str(getattr(wallet, "current_balance", getattr(wallet, "balance", 0)) or 0))
            new_bal = cur_bal + order.total_amount
            if hasattr(wallet, "current_balance"):
                wallet.current_balance = new_bal
            if hasattr(wallet, "balance"):
                wallet.balance = new_bal

            try:
                tx = WalletTransaction(
                    wallet_id=wallet.id,
                    transaction_type="CREDIT",
                    amount=order.total_amount,
                    reference_no=f"REFUND-{order.order_number}",
                    remarks=f"Refund for cancelled order #{order.order_number}",
                )
                self.db.add(tx)
            except Exception as e:
                logger.warning(f"Wallet refund transaction record failed: {e}")

            refunded_to_wallet = True
            refund_amount = order.total_amount
            order.payment_status = "refunded"
        else:
            order.payment_status = "cancelled"

        # 3. Mark status as cancelled
        order.status = "cancelled"

        # 4. Add tracking entry
        reason_text = payload.reason.strip() if payload and payload.reason else "Customer cancelled via Storefront"
        try:
            from app.models.order import OrderTracking
            tracking = OrderTracking(
                order_id=order.id,
                status="cancelled",
                remarks=f"Cancelled by customer: {reason_text}",
                notes=f"Cancelled by customer: {reason_text}",
            )
            self.db.add(tracking)
        except Exception as e:
            logger.warning(f"Tracking cancellation entry failed: {e}")

        # 5. Cancel delivery record if present
        if hasattr(order, "delivery") and order.delivery:
            order.delivery.status = "cancelled"

        self.db.commit()
        self.db.refresh(order)

        msg = f"Order #{order.order_number} has been cancelled successfully."
        if refunded_to_wallet and refund_amount:
            msg += f" Rs.{refund_amount} has been refunded to your wallet."

        return StorefrontOrderCancelResponse(
            order_id=order.id,
            order_number=order.order_number,
            status="cancelled",
            message=msg,
            refunded_to_wallet=refunded_to_wallet,
            refund_amount=refund_amount,
            cancelled_at=datetime.utcnow(),
        )

    def get_customer_profile(
        self,
        tenant_id: int,
        customer_id: int,
    ) -> StorefrontCustomerProfileResponse:
        customer = (
            self.db.query(Customer)
            .filter(Customer.id == customer_id, Customer.tenant_id == tenant_id)
            .first()
        )
        if not customer:
            raise NotFoundException(f"Customer #{customer_id} not found")

        from app.models.customer import CustomerWallet
        wallet = self.db.query(CustomerWallet).filter(CustomerWallet.customer_id == customer.id).first()
        wallet_balance = wallet.balance if wallet else Decimal("0.00")

        return StorefrontCustomerProfileResponse(
            customer_id=customer.id,
            name=customer.name,
            phone=customer.phone,
            email=customer.email,
            address=customer.address,
            birthday=customer.birthday,
            loyalty_points=customer.loyalty_points or 0,
            wallet_balance=wallet_balance,
            outstanding_balance=customer.outstanding_balance or Decimal("0.00"),
            credit_limit=customer.credit_limit or Decimal("0.00"),
            status=customer.status,
        )

    def update_customer_profile(
        self,
        tenant_id: int,
        customer_id: int,
        data: StorefrontCustomerProfileUpdate,
    ) -> StorefrontCustomerProfileResponse:
        customer = (
            self.db.query(Customer)
            .filter(Customer.id == customer_id, Customer.tenant_id == tenant_id)
            .first()
        )
        if not customer:
            raise NotFoundException(f"Customer #{customer_id} not found")

        if data.name is not None and data.name.strip():
            customer.name = data.name.strip()
        if data.email is not None:
            customer.email = data.email.strip() if data.email.strip() else None
        if data.address is not None:
            customer.address = data.address.strip() if data.address.strip() else None
        if data.birthday is not None:
            customer.birthday = data.birthday

        self.db.commit()
        self.db.refresh(customer)
        return self.get_customer_profile(tenant_id, customer_id)

    def get_wallet(self, tenant_id: int, customer_id: int):
        from app.services.customer_service import CustomerService
        return CustomerService(self.db).get_wallet(tenant_id, customer_id)

    def get_wallet_transactions(
        self,
        tenant_id: int,
        customer_id: int,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
    ):
        from app.services.customer_service import CustomerService
        return CustomerService(self.db).get_wallet_transactions(
            tenant_id, customer_id, page=page, page_size=page_size
        )

    def get_loyalty_history(
        self,
        tenant_id: int,
        customer_id: int,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
    ):
        from app.services.customer_service import CustomerService
        return CustomerService(self.db).get_loyalty_history(
            tenant_id, customer_id, page=page, page_size=page_size
        )

    def get_customer_ledger(
        self,
        tenant_id: int,
        customer_id: int,
        from_date=None,
        to_date=None,
    ):
        from app.services.customer_service import CustomerService
        return CustomerService(self.db).get_customer_ledger(
            tenant_id, customer_id, from_date=from_date, to_date=to_date
        )

    def export_ledger_pdf(
        self,
        tenant_id: int,
        customer_id: int,
        from_date=None,
        to_date=None,
    ):
        from app.services.customer_service import CustomerService
        return CustomerService(self.db).export_ledger_pdf(
            tenant_id, customer_id, from_date=from_date, to_date=to_date
        )

    def create_feedback(
        self,
        tenant_id: int,
        customer_id: int,
        data: StorefrontFeedbackRequest,
    ):
        from app.schemas.customer import CustomerFeedbackCreate
        from app.services.customer_service import CustomerService

        feedback_create = CustomerFeedbackCreate(
            customer_id=customer_id,
            invoice_id=data.invoice_id,
            rating=data.rating,
            comments=data.feedback,
            feedback=data.feedback,
        )
        return CustomerService(self.db).create_feedback(tenant_id, feedback_create)

    def create_referral(
        self,
        tenant_id: int,
        customer_id: int,
        data: StorefrontReferralRequest,
    ):
        from app.schemas.customer import ReferralCreate
        from app.services.customer_service import CustomerService

        ref_code = f"REF-{customer_id}-{uuid.uuid4().hex[:6].upper()}"
        ref_create = ReferralCreate(
            customer_id=customer_id,
            referral_code=ref_code,
        )
        return CustomerService(self.db).create_referral(tenant_id, ref_create)

    def get_my_referrals(
        self,
        tenant_id: int,
        customer_id: int,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
    ):
        from app.models.customer import CustomerReferral
        query = (
            self.db.query(CustomerReferral)
            .filter(CustomerReferral.customer_id == customer_id)
            .order_by(CustomerReferral.created_at.desc())
        )
        if page is not None and page_size is not None:
            query = query.offset((page - 1) * page_size).limit(page_size)
        elif page_size is not None:
            query = query.limit(page_size)
        referrals = query.all()
        return {
            "success": True,
            "message": "Referrals retrieved successfully" if referrals else "No referrals found",
            "data": referrals,
            "page": page or 1,
            "page_size": page_size or len(referrals),
            "total": len(referrals),
        }

    def get_my_notifications(
        self,
        tenant_id: int,
        customer_id: int,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
    ):
        from app.models.customer import CustomerCommunication
        query = (
            self.db.query(CustomerCommunication)
            .filter(CustomerCommunication.customer_id == customer_id)
            .order_by(CustomerCommunication.sent_at.desc())
        )
        total = query.count()
        if page is not None and page_size is not None:
            query = query.offset((page - 1) * page_size).limit(page_size)
        elif page_size is not None:
            query = query.limit(page_size)

        comms = query.all()
        items = [
            StorefrontNotificationItem(
                id=c.id,
                type=str(c.communication_type),
                message=c.message,
                status=str(c.delivery_status),
                created_at=c.sent_at or datetime.utcnow(),
            )
            for c in comms
        ]
        return StorefrontNotificationListResponse(items=items, total=total)
