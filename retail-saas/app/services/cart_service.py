import json
import time
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.exceptions import AppException, NotFoundException
from app.core.redis_client import get_redis
from app.models.product import Product
from app.services.audit_service import AuditService
from app.utils.gst_engine import aggregate_taxes, calculate_line_tax, resolve_gst_rate

CART_TTL_SECONDS = 3600
_MEMORY_CARTS: dict[str, tuple[float, str]] = {}


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
        _MEMORY_CARTS[key] = (time.time() + CART_TTL_SECONDS, payload)

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
            cart = json.loads(raw)
            cart["items"] = [
                {**item, "product_id": int(item["product_id"])}
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
                self.redis.setex(key, CART_TTL_SECONDS, payload)
                saved = True
            except Exception:
                saved = False
        if not saved:
            self._memory_set(key, payload)

    def _compute_item(self, tenant_id: int, item: dict, same_state: bool) -> dict:
        product = (
            self.db.query(Product)
            .filter(Product.id == item["product_id"], Product.tenant_id == tenant_id)
            .first()
        )
        if not product:
            raise NotFoundException(f"Product {item['product_id']} not found")
        qty = Decimal(str(item["quantity"]))
        unit_price = Decimal(str(item.get("unit_price") or product.price))
        discount = Decimal(str(item.get("discount", "0")))
        gst_rate = resolve_gst_rate(self.db, tenant_id, product)
        tax = calculate_line_tax(qty, unit_price, discount, gst_rate, same_state)
        return {
            "product_id": product.id,
            "product_name": product.name,
            "sku": product.sku or "",
            "hsn_code": product.hsn_code,
            "quantity": str(qty),
            "unit_price": str(unit_price),
            "discount": str(discount),
            "gst_rate": str(gst_rate),
            **{k: str(v) for k, v in tax.items()},
        }

    def _build_summary(self, cart: dict) -> dict:
        same_state = cart.get("same_state", True)
        items = [self._compute_item(cart.get("_tenant_id"), i, same_state) for i in cart["items"]]
        line_taxes = [
            {
                "taxable_amount": Decimal(i["taxable_amount"]),
                "gst_amount": Decimal(i["gst_amount"]),
                "cgst_amount": Decimal(i["cgst_amount"]),
                "sgst_amount": Decimal(i["sgst_amount"]),
                "igst_amount": Decimal(i["igst_amount"]),
                "total_amount": Decimal(i["total_amount"]),
            }
            for i in items
        ]
        totals = aggregate_taxes(line_taxes)
        invoice_discount = Decimal(str(cart.get("discount_amount", "0")))
        grand_total = totals["grand_total"] - invoice_discount
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
        discount: Decimal = Decimal("0"),
        same_state: bool = True,
    ) -> dict:
        cart = self._load_cart(tenant_id, user_id)
        cart["_tenant_id"] = tenant_id
        cart["store_id"] = store_id
        cart["same_state"] = same_state
        existing = next(
            (i for i in cart["items"] if int(i["product_id"]) == int(product_id)),
            None,
        )
        if existing:
            existing["quantity"] = str(Decimal(str(existing["quantity"])) + quantity)
            if unit_price is not None:
                existing["unit_price"] = str(unit_price)
            existing["discount"] = str(Decimal(str(existing.get("discount", "0"))) + discount)
            product = (
                self.db.query(Product)
                .filter(Product.id == product_id, Product.tenant_id == tenant_id)
                .first()
            )
            if product:
                self._log_price_or_item_discount(
                    tenant_id,
                    user_id,
                    product,
                    unit_price,
                    discount,
                )
        else:
            cart["items"].append(
                {
                    "product_id": product_id,
                    "quantity": str(quantity),
                    "unit_price": str(unit_price) if unit_price is not None else None,
                    "discount": str(discount),
                }
            )
        product = (
            self.db.query(Product)
            .filter(Product.id == product_id, Product.tenant_id == tenant_id)
            .first()
        )
        if product:
            self._log_price_or_item_discount(
                tenant_id, user_id, product, unit_price, discount
            )
        self._save_cart(tenant_id, user_id, cart)
        return self.get_cart(tenant_id, user_id)

    def update_item(
        self,
        tenant_id: int,
        user_id: int,
        product_id: int,
        quantity: Decimal | None = None,
        unit_price: Decimal | None = None,
        discount: Decimal | None = None,
    ) -> dict:
        cart = self._load_cart(tenant_id, user_id)
        cart["_tenant_id"] = tenant_id
        item = next(
            (i for i in cart["items"] if int(i["product_id"]) == int(product_id)),
            None,
        )
        if not item:
            raise NotFoundException("Cart item not found")
        if quantity is not None:
            item["quantity"] = str(quantity)
        if unit_price is not None:
            item["unit_price"] = str(unit_price)
        if discount is not None:
            item["discount"] = str(discount)
        product = (
            self.db.query(Product)
            .filter(Product.id == product_id, Product.tenant_id == tenant_id)
            .first()
        )
        if product:
            self._log_price_or_item_discount(
                tenant_id,
                user_id,
                product,
                unit_price,
                Decimal(str(item.get("discount", "0"))),
            )
        self._save_cart(tenant_id, user_id, cart)
        return self.get_cart(tenant_id, user_id)

    def remove_item(self, tenant_id: int, user_id: int, product_id: int) -> dict:
        cart = self._load_cart(tenant_id, user_id)
        cart["_tenant_id"] = tenant_id
        cart["items"] = [
            i for i in cart["items"] if int(i["product_id"]) != int(product_id)
        ]
        self._save_cart(tenant_id, user_id, cart)
        return self.get_cart(tenant_id, user_id)

    def apply_discount(
        self,
        tenant_id: int,
        user_id: int,
        discount_type: str,
        value: Decimal,
        coupon_code: str | None = None,
    ) -> dict:
        cart = self._load_cart(tenant_id, user_id)
        cart["_tenant_id"] = tenant_id
        summary = self._build_summary(cart)
        subtotal = Decimal(summary["subtotal"])

        if discount_type == "percentage":
            cart["discount_amount"] = str((subtotal * value / Decimal("100")).quantize(Decimal("0.01")))
        elif discount_type in ("fixed", "coupon", "store_wide"):
            cart["discount_amount"] = str(value)
        else:
            raise AppException(f"Unknown discount type: {discount_type}")

        if coupon_code:
            cart["coupon_code"] = coupon_code
        self._save_cart(tenant_id, user_id, cart)
        AuditService(self.db).log(
            tenant_id,
            user_id,
            "cart_discount_applied",
            "cart",
            details={
                "discount_type": discount_type,
                "value": str(value),
                "discount_amount": cart["discount_amount"],
                "coupon_code": coupon_code,
            },
        )
        return self.get_cart(tenant_id, user_id)

    def _log_price_or_item_discount(
        self,
        tenant_id: int,
        user_id: int,
        product: Product,
        unit_price: Decimal | None,
        discount: Decimal,
    ) -> None:
        audit = AuditService(self.db)
        if unit_price is not None and unit_price != product.price:
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
        if discount is not None and discount > 0:
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

    def get_cart(self, tenant_id: int, user_id: int) -> dict:
        cart = self._load_cart(tenant_id, user_id)
        cart["_tenant_id"] = tenant_id
        if not cart["items"]:
            return {
                "store_id": cart.get("store_id"),
                "customer_id": cart.get("customer_id"),
                "items": [],
                "subtotal": "0.00",
                "discount_amount": str(cart.get("discount_amount", "0.00")),
                "gst_amount": "0.00",
                "cgst_amount": "0.00",
                "sgst_amount": "0.00",
                "igst_amount": "0.00",
                "grand_total": "0.00",
                "same_state": cart.get("same_state", True),
                "coupon_code": cart.get("coupon_code"),
            }
        return self._build_summary(cart)

    def clear_cart(self, tenant_id: int, user_id: int) -> None:
        key = self._cart_key(tenant_id, user_id)
        if self.redis is not None:
            try:
                self.redis.delete(key)
            except Exception:
                pass
        _MEMORY_CARTS.pop(key, None)

    def set_customer(self, tenant_id: int, user_id: int, customer_id: int | None) -> dict:
        cart = self._load_cart(tenant_id, user_id)
        cart["customer_id"] = customer_id
        self._save_cart(tenant_id, user_id, cart)
        return self.get_cart(tenant_id, user_id)
