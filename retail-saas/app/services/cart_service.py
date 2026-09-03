import json
import time
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session

from app.core.exceptions import AppException, NotFoundException
from app.core.redis_client import get_redis
from app.models.product import Product
from app.services.audit_service import AuditService
from app.utils.gst_engine import aggregate_taxes, calculate_line_tax, resolve_gst_rate


CART_TTL_SECONDS = 3600
MONEY = Decimal("0.01")
ZERO = Decimal("0.00")
_MEMORY_CARTS: dict[str, tuple[float, str]] = {}


def _money(value: Decimal) -> Decimal:
    return Decimal(str(value)).quantize(MONEY, rounding=ROUND_HALF_UP)


def _empty_cart() -> dict:
    return {
        "store_id": None,
        "customer_id": None,
        "same_state": True,
        "discount_amount": "0.00",
        "coupon_code": None,
        "items": [],
    }


class CartService:
    def __init__(self, db: Session):
        self.db = db
        try:
            self.redis = get_redis()
        except Exception:
            self.redis = None

    def _cart_key(self, tenant_id: int, user_id: int) -> str:
        return f"cart:{tenant_id}:{user_id}"

    def _memory_get(self, key: str) -> str | None:
        entry = _MEMORY_CARTS.get(key)
        if not entry:
            return None

        expires_at, payload = entry

        if expires_at < time.time():
            _MEMORY_CARTS.pop(key, None)
            return None

        return payload

    def _memory_set(self, key: str, payload: str) -> None:
        _MEMORY_CARTS[key] = (
            time.time() + CART_TTL_SECONDS,
            payload,
        )

    def _load_cart(self, tenant_id: int, user_id: int) -> dict:
        key = self._cart_key(tenant_id, user_id)
        raw = None

        if self.redis is not None:
            try:
                raw = self.redis.get(key)
            except Exception:
                raw = None

        if not raw:
            raw = self._memory_get(key)

        if raw:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")

            cart = json.loads(raw)

            cart["items"] = [
                {
                    **item,
                    "product_id": int(item["product_id"]),
                }
                for item in cart.get("items", [])
            ]

            return cart

        return _empty_cart()

    def _save_cart(self, tenant_id: int, user_id: int, cart: dict) -> None:
        payload = json.dumps(cart)
        key = self._cart_key(tenant_id, user_id)
        saved = False

        if self.redis is not None:
            try:
                self.redis.setex(
                    key,
                    CART_TTL_SECONDS,
                    payload,
                )
                saved = True
            except Exception:
                saved = False

        if not saved:
            self._memory_set(key, payload)

    def _get_product(
        self,
        tenant_id: int,
        product_id: int,
    ) -> Product:
        product = (
            self.db.query(Product)
            .filter(
                Product.id == product_id,
                Product.tenant_id == tenant_id,
            )
            .first()
        )

        if not product:
            raise NotFoundException(
                f"Product {product_id} not found"
            )

        if hasattr(product, "is_active") and not product.is_active:
            raise AppException(
                f"Product {product_id} is inactive"
            )

        return product

    def _validate_item_values(
        self,
        quantity: Decimal,
        unit_price: Decimal,
        discount: Decimal,
    ) -> None:
        if quantity <= 0:
            raise AppException(
                "Quantity must be greater than zero"
            )

        if unit_price <= 0:
            raise AppException(
                "Unit price must be greater than zero"
            )

        if discount < 0:
            raise AppException(
                "Discount cannot be negative"
            )

        gross_amount = _money(quantity * unit_price)

        if discount > gross_amount:
            raise AppException(
                "Discount cannot exceed item amount"
            )

    def _compute_item(
        self,
        tenant_id: int,
        item: dict,
        same_state: bool,
    ) -> dict:
        product = self._get_product(
            tenant_id,
            int(item["product_id"]),
        )

        quantity = Decimal(str(item["quantity"]))

        raw_price = item.get("unit_price")

        if raw_price is None or raw_price == "":
            if product.price is None:
                raise AppException(
                    f"Product {product.id} does not have a valid price"
                )
            unit_price = Decimal(str(product.price))
        else:
            unit_price = Decimal(str(raw_price))

        discount = Decimal(
            str(item.get("discount", "0.00"))
        )

        self._validate_item_values(
            quantity,
            unit_price,
            discount,
        )

        gst_rate = resolve_gst_rate(
            self.db,
            tenant_id,
            product,
        )

        try:
            tax = calculate_line_tax(
                quantity,
                unit_price,
                discount,
                gst_rate,
                same_state,
            )
        except ValueError as exc:
            raise AppException(str(exc))

        return {
            "product_id": product.id,
            "product_name": product.name,
            "sku": product.sku or "",
            "hsn_code": product.hsn_code,
            "quantity": str(quantity),
            "unit_price": str(_money(unit_price)),
            "discount": str(_money(discount)),
            **{
                key: str(value)
                for key, value in tax.items()
            },
        }

    def _build_summary(self, cart: dict) -> dict:
        tenant_id = cart.get("_tenant_id")

        if not tenant_id:
            raise AppException(
                "Tenant context is required"
            )

        same_state = bool(
            cart.get("same_state", True)
        )

        items = [
            self._compute_item(
                tenant_id,
                item,
                same_state,
            )
            for item in cart.get("items", [])
        ]

        line_taxes = [
            {
                "taxable_amount": Decimal(
                    item["taxable_amount"]
                ),
                "gst_amount": Decimal(
                    item["gst_amount"]
                ),
                "cgst_amount": Decimal(
                    item["cgst_amount"]
                ),
                "sgst_amount": Decimal(
                    item["sgst_amount"]
                ),
                "igst_amount": Decimal(
                    item["igst_amount"]
                ),
                "total_amount": Decimal(
                    item["total_amount"]
                ),
            }
            for item in items
        ]

        totals = aggregate_taxes(line_taxes)

        invoice_discount = _money(
            Decimal(
                str(
                    cart.get(
                        "discount_amount",
                        "0.00",
                    )
                )
            )
        )

        if invoice_discount < ZERO:
            raise AppException(
                "Cart discount cannot be negative"
            )

        if invoice_discount > totals["subtotal"]:
            raise AppException(
                "Cart discount cannot exceed subtotal"
            )

        if same_state:
            if totals["igst_amount"] != ZERO:
                raise AppException(
                    "IGST must be zero for intra-state billing"
                )

            if _money(
                totals["cgst_amount"]
                + totals["sgst_amount"]
            ) != totals["gst_amount"]:
                raise AppException(
                    "Total GST amount does not match the sum of CGST and SGST amounts"
                )
        else:
            if (
                totals["cgst_amount"] != ZERO
                or totals["sgst_amount"] != ZERO
            ):
                raise AppException(
                    "CGST and SGST must be zero for inter-state billing"
                )

            if totals["igst_amount"] != totals["gst_amount"]:
                raise AppException(
                    "Total GST amount does not match IGST amount"
                )

        grand_total = _money(
            totals["grand_total"]
            - invoice_discount
        )

        if grand_total < ZERO:
            raise AppException(
                "Grand total cannot be negative"
            )

        return {
            "store_id": cart.get("store_id"),
            "customer_id": cart.get("customer_id"),
            "items": items,
            "subtotal": str(totals["subtotal"]),
            "discount_amount": str(invoice_discount),
            "gst_amount": str(totals["gst_amount"]),
            "cgst_amount": str(totals["cgst_amount"]),
            "sgst_amount": str(totals["sgst_amount"]),
            "igst_amount": str(totals["igst_amount"]),
            "grand_total": str(grand_total),
            "same_state": same_state,
            "coupon_code": cart.get("coupon_code"),
        }

    def add_item(
        self,
        tenant_id: int,
        user_id: int,
        store_id: int,
        product_id: int,
        quantity: Decimal,
        unit_price: Decimal | None = None,
        discount: Decimal = ZERO,
        same_state: bool = True,
    ) -> dict:
        if store_id <= 0:
            raise AppException(
                "Store ID must be greater than zero"
            )

        if product_id <= 0:
            raise AppException(
                "Product ID must be greater than zero"
            )

        quantity = Decimal(str(quantity))
        discount = Decimal(str(discount))

        product = self._get_product(
            tenant_id,
            product_id,
        )

        effective_price = (
            Decimal(str(unit_price))
            if unit_price is not None
            else Decimal(str(product.price))
        )

        self._validate_item_values(
            quantity,
            effective_price,
            discount,
        )

        cart = self._load_cart(
            tenant_id,
            user_id,
        )

        cart["_tenant_id"] = tenant_id
        cart["store_id"] = store_id
        cart["same_state"] = bool(same_state)

        existing = next(
            (
                item
                for item in cart["items"]
                if int(item["product_id"]) == int(product_id)
            ),
            None,
        )

        if existing:
            new_quantity = (
                Decimal(str(existing["quantity"]))
                + quantity
            )

            existing_price = (
                Decimal(str(existing["unit_price"]))
                if existing.get("unit_price") is not None
                else effective_price
            )

            new_discount = (
                Decimal(
                    str(existing.get("discount", "0.00"))
                )
                + discount
            )

            if unit_price is not None:
                existing_price = effective_price

            self._validate_item_values(
                new_quantity,
                existing_price,
                new_discount,
            )

            existing["quantity"] = str(
                new_quantity
            )
            existing["unit_price"] = str(
                existing_price
            )
            existing["discount"] = str(
                new_discount
            )
        else:
            cart["items"].append(
                {
                    "product_id": product_id,
                    "quantity": str(quantity),
                    "unit_price": (
                        str(effective_price)
                        if unit_price is not None
                        else None
                    ),
                    "discount": str(discount),
                }
            )

        self._log_price_or_item_discount(
            tenant_id,
            user_id,
            product,
            unit_price,
            discount,
        )

        self._build_summary(cart)
        self._save_cart(
            tenant_id,
            user_id,
            cart,
        )

        return self.get_cart(
            tenant_id,
            user_id,
        )

    def update_item(
        self,
        tenant_id: int,
        user_id: int,
        product_id: int,
        quantity: Decimal | None = None,
        unit_price: Decimal | None = None,
        discount: Decimal | None = None,
    ) -> dict:
        if product_id <= 0:
            raise AppException(
                "Product ID must be greater than zero"
            )

        cart = self._load_cart(
            tenant_id,
            user_id,
        )

        cart["_tenant_id"] = tenant_id

        item = next(
            (
                i
                for i in cart["items"]
                if int(i["product_id"]) == int(product_id)
            ),
            None,
        )

        if not item:
            raise NotFoundException(
                "Cart item not found"
            )

        product = self._get_product(
            tenant_id,
            product_id,
        )

        current_quantity = Decimal(
            str(item["quantity"])
        )

        current_price = (
            Decimal(str(item["unit_price"]))
            if item.get("unit_price") is not None
            else Decimal(str(product.price))
        )

        current_discount = Decimal(
            str(item.get("discount", "0.00"))
        )

        new_quantity = (
            Decimal(str(quantity))
            if quantity is not None
            else current_quantity
        )

        new_price = (
            Decimal(str(unit_price))
            if unit_price is not None
            else current_price
        )

        new_discount = (
            Decimal(str(discount))
            if discount is not None
            else current_discount
        )

        self._validate_item_values(
            new_quantity,
            new_price,
            new_discount,
        )

        item["quantity"] = str(new_quantity)
        item["unit_price"] = str(new_price)
        item["discount"] = str(new_discount)

        self._log_price_or_item_discount(
            tenant_id,
            user_id,
            product,
            unit_price,
            new_discount,
        )

        self._build_summary(cart)

        self._save_cart(
            tenant_id,
            user_id,
            cart,
        )

        return self.get_cart(
            tenant_id,
            user_id,
        )

    def remove_item(
        self,
        tenant_id: int,
        user_id: int,
        product_id: int,
    ) -> dict:
        if product_id <= 0:
            raise AppException(
                "Product ID must be greater than zero"
            )

        cart = self._load_cart(
            tenant_id,
            user_id,
        )

        cart["_tenant_id"] = tenant_id

        original_count = len(cart["items"])

        cart["items"] = [
            item
            for item in cart["items"]
            if int(item["product_id"]) != int(product_id)
        ]

        if len(cart["items"]) == original_count:
            raise NotFoundException(
                "Cart item not found"
            )

        if not cart["items"]:
            cart["discount_amount"] = "0.00"
            cart["coupon_code"] = None

        self._build_summary(cart)

        self._save_cart(
            tenant_id,
            user_id,
            cart,
        )

        return self.get_cart(
            tenant_id,
            user_id,
        )

    def apply_discount(
        self,
        tenant_id: int,
        user_id: int,
        discount_type: str,
        value: Decimal,
        coupon_code: str | None = None,
    ) -> dict:
        discount_type = discount_type.strip().lower()
        value = Decimal(str(value))

        if discount_type not in {
            "percentage",
            "fixed",
            "coupon",
            "store_wide",
        }:
            raise AppException(
                "Unknown discount type"
            )

        if value < ZERO:
            raise AppException(
                "Discount value cannot be negative"
            )

        cart = self._load_cart(
            tenant_id,
            user_id,
        )

        cart["_tenant_id"] = tenant_id

        summary = self._build_summary(cart)

        subtotal = Decimal(
            summary["subtotal"]
        )

        if discount_type == "percentage":
            if value > Decimal("100"):
                raise AppException(
                    "Percentage discount cannot exceed 100%"
                )

            discount_amount = _money(
                subtotal
                * value
                / Decimal("100")
            )
        else:
            discount_amount = _money(value)

        if discount_amount > subtotal:
            raise AppException(
                "Discount cannot exceed subtotal"
            )

        cart["discount_amount"] = str(
            discount_amount
        )

        if coupon_code:
            cart["coupon_code"] = coupon_code.strip()
        elif discount_type != "coupon":
            cart["coupon_code"] = None

        self._build_summary(cart)

        self._save_cart(
            tenant_id,
            user_id,
            cart,
        )

        AuditService(self.db).log(
            tenant_id,
            user_id,
            "cart_discount_applied",
            "cart",
            details={
                "discount_type": discount_type,
                "value": str(value),
                "discount_amount": str(
                    discount_amount
                ),
                "coupon_code": coupon_code,
            },
        )

        return self.get_cart(
            tenant_id,
            user_id,
        )

    def _log_price_or_item_discount(
        self,
        tenant_id: int,
        user_id: int,
        product: Product,
        unit_price: Decimal | None,
        discount: Decimal,
    ) -> None:
        audit = AuditService(self.db)

        if (
            unit_price is not None
            and Decimal(str(unit_price))
            != Decimal(str(product.price))
        ):
            audit.log(
                tenant_id,
                user_id,
                "price_override",
                "product",
                product.id,
                {
                    "product_name": product.name,
                    "catalog_price": str(product.price),
                    "override_price": str(unit_price),
                },
            )

        if discount is not None and discount > ZERO:
            audit.log(
                tenant_id,
                user_id,
                "item_discount_applied",
                "product",
                product.id,
                {
                    "product_name": product.name,
                    "discount": str(discount),
                },
            )

    def get_cart(
        self,
        tenant_id: int,
        user_id: int,
    ) -> dict:
        cart = self._load_cart(
            tenant_id,
            user_id,
        )

        cart["_tenant_id"] = tenant_id

        if not cart["items"]:
            return {
                "store_id": cart.get("store_id") or 0,
                "customer_id": cart.get("customer_id"),
                "items": [],
                "subtotal": "0.00",
                "discount_amount": str(
                    cart.get(
                        "discount_amount",
                        "0.00",
                    )
                ),
                "gst_amount": "0.00",
                "cgst_amount": "0.00",
                "sgst_amount": "0.00",
                "igst_amount": "0.00",
                "grand_total": "0.00",
                "same_state": bool(
                    cart.get("same_state", True)
                ),
                "coupon_code": cart.get(
                    "coupon_code"
                ),
            }

        return self._build_summary(cart)

    def clear_cart(
        self,
        tenant_id: int,
        user_id: int,
    ) -> None:
        key = self._cart_key(
            tenant_id,
            user_id,
        )

        if self.redis is not None:
            try:
                self.redis.delete(key)
            except Exception:
                pass

        _MEMORY_CARTS.pop(key, None)

    def set_customer(
        self,
        tenant_id: int,
        user_id: int,
        customer_id: int | None,
    ) -> dict:
        if customer_id is not None and customer_id <= 0:
            raise AppException(
                "Customer ID must be greater than zero"
            )

        cart = self._load_cart(
            tenant_id,
            user_id,
        )

        cart["_tenant_id"] = tenant_id
        cart["customer_id"] = customer_id

        self._save_cart(
            tenant_id,
            user_id,
            cart,
        )

        return self.get_cart(
            tenant_id,
            user_id,
        )