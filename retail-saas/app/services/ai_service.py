from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.inventory import Inventory
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product import Product
from app.utils.constants import OrderStatus


class AIService:
    def __init__(self, db: Session):
        self.db = db

    def reorder_prediction(self, tenant_id: int, store_id: int | None = None) -> list[dict]:
        query = self.db.query(Inventory).filter(
            Inventory.tenant_id == tenant_id,
            Inventory.quantity <= Inventory.min_stock_level,
        )
        if store_id:
            query = query.filter(Inventory.store_id == store_id)
        items = query.all()
        return [
            {
                "product_id": i.product_id,
                "store_id": i.store_id,
                "current_stock": i.quantity,
                "reorder_level": i.reorder_point,
                "recommended_order": max(i.max_stock_level - i.quantity, 10),
            }
            for i in items
        ]

    def demand_forecast(self, tenant_id: int, product_id: int) -> dict:
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        total_sold = (
            self.db.query(func.coalesce(func.sum(OrderItem.quantity), 0))
            .join(Order)
            .filter(
                Order.tenant_id == tenant_id,
                OrderItem.product_id == product_id,
                Order.status.in_([OrderStatus.CONFIRMED.value, OrderStatus.DELIVERED.value]),
                Order.created_at >= thirty_days_ago,
            )
            .scalar()
        )
        daily_avg = float(total_sold) / 30.0
        return {
            "product_id": product_id,
            "period_days": 30,
            "total_sold": int(total_sold),
            "daily_average": round(daily_avg, 2),
            "forecast_next_7_days": round(daily_avg * 7, 0),
            "forecast_next_30_days": round(daily_avg * 30, 0),
        }

    def best_selling_products(self, tenant_id: int, limit: int = 10) -> list[dict]:
        rows = (
            self.db.query(
                OrderItem.product_id,
                Product.name.label("product_name"),
                func.sum(OrderItem.quantity).label("qty"),
            )
            .join(Order, Order.id == OrderItem.order_id)
            .join(Product, Product.id == OrderItem.product_id)
            .filter(Order.tenant_id == tenant_id, Order.status.in_([OrderStatus.CONFIRMED.value, OrderStatus.DELIVERED.value]))
            .group_by(OrderItem.product_id, Product.name)
            .order_by(func.sum(OrderItem.quantity).desc())
            .limit(limit)
            .all()
        )
        return [{"product_id": r[0], "product_name": r[1], "quantity_sold": int(r[2])} for r in rows]

    def customer_purchase_patterns(self, tenant_id: int, customer_id: int) -> dict:
        orders = (
            self.db.query(Order)
            .filter(Order.tenant_id == tenant_id, Order.customer_id == customer_id)
            .order_by(Order.created_at.desc())
            .limit(20)
            .all()
        )
        if not orders:
            return {"customer_id": customer_id, "pattern": "no_data"}
        avg_order = sum((o.total_amount for o in orders), Decimal("0")) / len(orders)
        preferred_day = max(
            set(o.created_at.strftime("%A") for o in orders),
            key=lambda d: sum(1 for o in orders if o.created_at.strftime("%A") == d),
        )
        return {
            "customer_id": customer_id,
            "order_count": len(orders),
            "average_order_value": float(avg_order),
            "preferred_day": preferred_day,
        }

    def smart_offer_recommendations(self, tenant_id: int, customer_id: int) -> list[dict]:
        patterns = self.customer_purchase_patterns(tenant_id, customer_id)
        offers = []
        if patterns.get("order_count", 0) >= 5:
            offers.append({"type": "loyalty", "message": "10% off on next purchase for loyal customer"})
        if patterns.get("average_order_value", 0) > 1000:
            offers.append({"type": "upsell", "message": "Free delivery on orders above Rs.1500"})
        if not offers:
            offers.append({"type": "welcome", "message": "5% off on first purchase"})
        return offers
