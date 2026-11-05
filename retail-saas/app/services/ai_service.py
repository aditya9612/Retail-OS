import json
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
from decimal import Decimal
import httpx

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import NotFoundException
from app.core.logger import logger
from app.models.category import Category
from app.models.customer import Customer
from app.models.inventory import Inventory
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product import Product
from app.models.purchase_order import PurchaseOrder, PurchaseOrderItem
from app.utils.constants import OrderStatus

settings = get_settings()

class AIService:
    def __init__(self, db: Session):
        self.db = db

    def reorder_prediction(self, tenant_id: int, store_id: Optional[int] = None) -> list[dict]:
        """
        Calculates smart reorder predictions using sales run rate, current stock,
        min/max thresholds, and in-transit purchase orders.
        """
        inv_q = (
            self.db.query(
                Inventory.product_id,
                Inventory.store_id,
                Inventory.quantity,
                Inventory.min_stock_level,
                Inventory.max_stock_level,
                Inventory.reorder_point,
                Product.name.label("product_name"),
                Product.sku.label("sku"),
            )
            .join(Product, Product.id == Inventory.product_id)
            .filter(
                Inventory.tenant_id == tenant_id,
                Inventory.quantity <= Inventory.min_stock_level,
            )
        )
        if store_id is not None:
            inv_q = inv_q.filter(Inventory.store_id == store_id)

        items = inv_q.all()
        if not items:
            return []

        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        product_ids = [i[0] for i in items]

        # Calculate sales velocity over last 30 days
        velocity_q = (
            self.db.query(
                OrderItem.product_id,
                func.coalesce(func.sum(OrderItem.quantity), 0).label("qty_sold"),
            )
            .join(Order, Order.id == OrderItem.order_id)
            .filter(
                Order.tenant_id == tenant_id,
                OrderItem.product_id.in_(product_ids),
                Order.status.in_([OrderStatus.CONFIRMED.value, OrderStatus.DELIVERED.value]),
                Order.created_at >= thirty_days_ago,
            )
        )
        if store_id is not None:
            velocity_q = velocity_q.filter(Order.store_id == store_id)

        velocity_map = {r[0]: float(r[1]) for r in velocity_q.group_by(OrderItem.product_id).all()}

        # Check in-transit / pending purchase orders
        po_q = (
            self.db.query(
                PurchaseOrderItem.product_id,
                func.coalesce(func.sum(PurchaseOrderItem.quantity), 0).label("pending_qty"),
            )
            .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderItem.po_id)
            .filter(
                PurchaseOrder.tenant_id == tenant_id,
                PurchaseOrderItem.product_id.in_(product_ids),
                PurchaseOrder.status.in_(["ordered", "partially_received"]),
            )
        )
        if store_id is not None:
            po_q = po_q.filter(PurchaseOrder.store_id == store_id)

        pending_po_map = {r[0]: int(r[1]) for r in po_q.group_by(PurchaseOrderItem.product_id).all()}

        results = []
        for i in items:
            p_id = i[0]
            st_id = i[1]
            curr_stock = int(i[2])
            min_level = int(i[3])
            max_level = int(i[4])
            reorder_pt = int(i[5])
            p_name = i[6]
            sku = i[7]

            sold_30 = velocity_map.get(p_id, 0.0)
            daily_run_rate = round(sold_30 / 30.0, 2)
            estimated_runout = (
                round(float(curr_stock) / daily_run_rate, 1) if daily_run_rate > 0 and curr_stock > 0 else (0.0 if curr_stock <= 0 else None)
            )

            pending_qty = pending_po_map.get(p_id, 0)
            target_stock = max_level if max_level > min_level else (min_level * 2 if min_level > 0 else 20)
            net_needed = max(target_stock - curr_stock - pending_qty, 0)
            recommended_order = max(net_needed, 10 if curr_stock <= 0 else 5) if net_needed > 0 else 0

            # Determine urgency based on stockout risk, runout days, and safety stock
            if curr_stock <= 0:
                urgency = "CRITICAL"
            elif estimated_runout is not None and estimated_runout <= 3:
                urgency = "CRITICAL"
            elif (estimated_runout is not None and estimated_runout <= 7) or (min_level > 0 and curr_stock <= min_level / 2):
                urgency = "HIGH"
            elif (estimated_runout is not None and estimated_runout <= 15) or curr_stock <= min_level:
                urgency = "MEDIUM"
            else:
                urgency = "LOW"

            results.append(
                {
                    "product_id": p_id,
                    "product_name": p_name,
                    "sku": sku,
                    "store_id": st_id,
                    "current_stock": curr_stock,
                    "min_stock_level": min_level,
                    "reorder_level": reorder_pt,
                    "daily_run_rate": daily_run_rate,
                    "estimated_runout_days": estimated_runout,
                    "pending_order_qty": pending_qty,
                    "recommended_order": recommended_order,
                    "urgency": urgency,
                }
            )

        urgency_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
        results.sort(key=lambda x: (urgency_order.get(x["urgency"], 4), x["estimated_runout_days"] or 999))
        return results

    def demand_forecast(
        self, tenant_id: int, product_id: int, days: int = 30, store_id: Optional[int] = None
    ) -> dict:
        """
        Accurately forecasts product demand over the specified historical window
        and projects future 7-day and 30-day demand with trend classification.
        """
        product = (
            self.db.query(Product)
            .filter(Product.id == product_id, Product.tenant_id == tenant_id)
            .first()
        )
        if not product:
            raise NotFoundException(f"Product {product_id} not found")

        effective_days = max(days, 1)
        window_start = datetime.utcnow() - timedelta(days=effective_days)
        midpoint = datetime.utcnow() - timedelta(days=effective_days // 2)

        df_q = (
            self.db.query(func.coalesce(func.sum(OrderItem.quantity), 0))
            .join(Order, Order.id == OrderItem.order_id)
            .filter(
                Order.tenant_id == tenant_id,
                OrderItem.product_id == product_id,
                Order.status.in_([OrderStatus.CONFIRMED.value, OrderStatus.DELIVERED.value]),
                Order.created_at >= window_start,
            )
        )
        if store_id is not None:
            df_q = df_q.filter(Order.store_id == store_id)

        total_sold = df_q.scalar() or 0

        # Dynamic daily average (fixed math bug that divided by 30.0 regardless of days)
        daily_avg = round(float(total_sold) / float(effective_days), 2)

        # Trend detection: compare older half vs recent half
        recent_q = (
            self.db.query(func.coalesce(func.sum(OrderItem.quantity), 0))
            .join(Order, Order.id == OrderItem.order_id)
            .filter(
                Order.tenant_id == tenant_id,
                OrderItem.product_id == product_id,
                Order.status.in_([OrderStatus.CONFIRMED.value, OrderStatus.DELIVERED.value]),
                Order.created_at >= midpoint,
            )
        )
        if store_id is not None:
            recent_q = recent_q.filter(Order.store_id == store_id)
        recent_sold = float(recent_q.scalar() or 0)
        older_sold = float(total_sold) - recent_sold

        if recent_sold > (older_sold * 1.2) and recent_sold > 2:
            trend = "increasing"
        elif recent_sold < (older_sold * 0.8) and older_sold > 2:
            trend = "decreasing"
        else:
            trend = "stable"

        return {
            "product_id": product_id,
            "product_name": product.name,
            "sku": product.sku,
            "period_days": effective_days,
            "total_sold": int(total_sold),
            "daily_average": daily_avg,
            "forecast_next_7_days": round(daily_avg * 7, 0),
            "forecast_next_30_days": round(daily_avg * 30, 0),
            "trend": trend,
        }

    def best_selling_products(
        self,
        tenant_id: int,
        limit: int = 10,
        store_id: Optional[int] = None,
        period: Optional[str] = "all_time",
        sort_by: Optional[str] = "quantity",
    ) -> list[dict]:
        """
        Returns top performing products sorted by quantity or revenue,
        with optional period and store filtering.
        """
        now = datetime.utcnow()
        bsp_q = (
            self.db.query(
                OrderItem.product_id,
                Product.name.label("product_name"),
                Product.sku.label("sku"),
                func.sum(OrderItem.quantity).label("qty"),
                func.sum(OrderItem.total_amount).label("revenue"),
            )
            .join(Order, Order.id == OrderItem.order_id)
            .join(Product, Product.id == OrderItem.product_id)
            .filter(
                Order.tenant_id == tenant_id,
                Order.status.in_([OrderStatus.CONFIRMED.value, OrderStatus.DELIVERED.value]),
            )
        )
        if store_id is not None:
            bsp_q = bsp_q.filter(Order.store_id == store_id)

        if period == "today":
            today_start = datetime(now.year, now.month, now.day)
            bsp_q = bsp_q.filter(Order.created_at >= today_start)
        elif period == "this_week":
            bsp_q = bsp_q.filter(Order.created_at >= now - timedelta(days=7))
        elif period in ("this_month", "last_30_days"):
            bsp_q = bsp_q.filter(Order.created_at >= now - timedelta(days=30))

        order_col = func.sum(OrderItem.total_amount).desc() if sort_by == "revenue" else func.sum(OrderItem.quantity).desc()
        rows = (
            bsp_q.group_by(OrderItem.product_id, Product.name, Product.sku)
            .order_by(order_col)
            .limit(limit)
            .all()
        )

        # Fetch current stock for these products
        p_ids = [r[0] for r in rows]
        stock_map = {}
        if p_ids:
            inv_stock_q = (
                self.db.query(
                    Inventory.product_id,
                    func.coalesce(func.sum(Inventory.quantity), 0),
                )
                .filter(Inventory.tenant_id == tenant_id, Inventory.product_id.in_(p_ids))
            )
            if store_id is not None:
                inv_stock_q = inv_stock_q.filter(Inventory.store_id == store_id)
            stock_map = {r[0]: int(r[1]) for r in inv_stock_q.group_by(Inventory.product_id).all()}

        return [
            {
                "product_id": r[0],
                "product_name": r[1],
                "sku": r[2],
                "quantity_sold": int(r[3]),
                "total_revenue": round(float(r[4] or 0), 2),
                "current_stock": stock_map.get(r[0], 0),
            }
            for r in rows
        ]

    def customer_purchase_patterns(self, tenant_id: int, customer_id: int) -> dict:
        """
        Analyzes customer purchasing behavior, RFM recency, preferred day,
        and preferred product category (excluding cancelled orders).
        """
        customer = (
            self.db.query(Customer)
            .filter(Customer.id == customer_id, Customer.tenant_id == tenant_id)
            .first()
        )
        if not customer:
            raise NotFoundException(f"Customer {customer_id} not found")

        orders = (
            self.db.query(Order)
            .filter(
                Order.tenant_id == tenant_id,
                Order.customer_id == customer_id,
                Order.status.in_([OrderStatus.CONFIRMED.value, OrderStatus.DELIVERED.value]),
            )
            .order_by(Order.created_at.desc())
            .all()
        )
        if not orders:
            return {
                "customer_id": customer_id,
                "customer_name": customer.name,
                "phone": customer.phone,
                "order_count": 0,
                "total_spent": 0.0,
                "average_order_value": 0.0,
                "preferred_day": None,
                "preferred_category": None,
                "last_purchase_date": None,
                "days_since_last_purchase": None,
            }

        total_spent = sum((Decimal(str(o.total_amount or 0)) for o in orders), Decimal("0"))
        avg_order = total_spent / Decimal(len(orders))
        last_purchase = max(o.created_at for o in orders)
        days_since = (datetime.utcnow() - last_purchase).days

        # Preferred day of week
        preferred_day = max(
            set(o.created_at.strftime("%A") for o in orders),
            key=lambda d: sum(1 for o in orders if o.created_at.strftime("%A") == d),
        )

        # Preferred category
        cat_q = (
            self.db.query(Category.name, func.count(OrderItem.id))
            .join(Product, Product.category_id == Category.id)
            .join(OrderItem, OrderItem.product_id == Product.id)
            .join(Order, Order.id == OrderItem.order_id)
            .filter(Order.customer_id == customer_id, Order.tenant_id == tenant_id)
            .group_by(Category.name)
            .order_by(func.count(OrderItem.id).desc())
            .first()
        )
        preferred_category = cat_q[0] if cat_q else None

        return {
            "customer_id": customer_id,
            "customer_name": customer.name,
            "phone": customer.phone,
            "order_count": len(orders),
            "total_spent": round(float(total_spent), 2),
            "average_order_value": round(float(avg_order), 2),
            "preferred_day": preferred_day,
            "preferred_category": preferred_category,
            "last_purchase_date": last_purchase,
            "days_since_last_purchase": days_since,
        }

    def smart_offer_recommendations(self, tenant_id: int, customer_id: int) -> list[dict]:
        """
        Generates actionable, personalized coupon and discount recommendations
        based on RFM analytics and purchase patterns.
        """
        patterns = self.customer_purchase_patterns(tenant_id, customer_id)
        offers = []

        days_inactive = patterns.get("days_since_last_purchase")
        order_count = patterns.get("order_count", 0)
        aov = patterns.get("average_order_value", 0.0)
        pref_cat = patterns.get("preferred_category")

        # 1. Winback offer for lapsed customers
        if days_inactive is not None and days_inactive >= 30:
            offers.append(
                {
                    "type": "winback",
                    "message": "We miss you! Enjoy 15% off your next purchase.",
                    "discount_type": "percentage",
                    "discount_value": 15.0,
                    "coupon_code": "COMEBACK15",
                }
            )

        # 2. Loyalty offer for frequent shoppers
        if order_count >= 5:
            offers.append(
                {
                    "type": "loyalty",
                    "message": "VIP Gold Reward: 10% off on your entire cart.",
                    "discount_type": "percentage",
                    "discount_value": 10.0,
                    "coupon_code": "LOYALTY10",
                }
            )

        # 3. High AOV upsell offer
        if aov >= 1000:
            offers.append(
                {
                    "type": "upsell",
                    "message": "Flat Rs. 150 discount on orders above Rs. 1,200.",
                    "discount_type": "fixed",
                    "discount_value": 150.0,
                    "coupon_code": "FLAT150",
                }
            )

        # 4. Category affinity offer
        if pref_cat:
            cat_code = "".join(c for c in pref_cat if c.isalnum()).upper()[:4]
            offers.append(
                {
                    "type": "category_affinity",
                    "message": f"Special 10% discount on your favorite category: {pref_cat}.",
                    "discount_type": "percentage",
                    "discount_value": 10.0,
                    "coupon_code": f"{cat_code}10",
                }
            )

        # 5. Welcome offer for new customers
        if order_count == 0:
            offers.append(
                {
                    "type": "welcome",
                    "message": "Welcome to our store! Enjoy 5% off on your first purchase.",
                    "discount_type": "percentage",
                    "discount_value": 5.0,
                    "coupon_code": "WELCOME5",
                }
            )

        return offers

    def frequently_bought_together(
        self, tenant_id: int, product_id: int, limit: int = 5, store_id: Optional[int] = None
    ) -> list[dict]:
        """
        Market Basket Analysis: Finds products frequently purchased in the same order
        with the given product_id.
        """
        product = (
            self.db.query(Product)
            .filter(Product.id == product_id, Product.tenant_id == tenant_id)
            .first()
        )
        if not product:
            raise NotFoundException(f"Product {product_id} not found")

        # Find orders containing target product
        base_order_q = (
            self.db.query(OrderItem.order_id)
            .join(Order, Order.id == OrderItem.order_id)
            .filter(
                Order.tenant_id == tenant_id,
                OrderItem.product_id == product_id,
                Order.status.in_([OrderStatus.CONFIRMED.value, OrderStatus.DELIVERED.value]),
            )
        )
        if store_id is not None:
            base_order_q = base_order_q.filter(Order.store_id == store_id)

        matching_order_ids = [r[0] for r in base_order_q.distinct().all()]
        if not matching_order_ids:
            return []

        total_base_orders = len(matching_order_ids)

        co_items = (
            self.db.query(
                OrderItem.product_id,
                Product.name.label("product_name"),
                Product.sku.label("sku"),
                func.count(OrderItem.order_id.distinct()).label("co_count"),
            )
            .join(Product, Product.id == OrderItem.product_id)
            .filter(
                OrderItem.order_id.in_(matching_order_ids),
                OrderItem.product_id != product_id,
            )
            .group_by(OrderItem.product_id, Product.name, Product.sku)
            .order_by(func.count(OrderItem.order_id.distinct()).desc())
            .limit(limit)
            .all()
        )

        return [
            {
                "product_id": r[0],
                "product_name": r[1],
                "sku": r[2],
                "co_occurrence_count": int(r[3]),
                "correlation_percentage": round((float(r[3]) / float(total_base_orders)) * 100.0, 1),
            }
            for r in co_items
        ]

    def customer_churn_risk(
        self, tenant_id: int, inactive_days: int = 45, limit: int = 50, store_id: Optional[int] = None
    ) -> list[dict]:
        """
        Identifies lapsed customers at risk of churn based on days of inactivity
        since their last purchase.
        """
        threshold_date = datetime.utcnow() - timedelta(days=inactive_days)

        q = (
            self.db.query(
                Customer.id,
                Customer.name,
                Customer.phone,
                Customer.email,
                func.max(Order.created_at).label("last_order_at"),
                func.count(Order.id).label("total_orders"),
                func.coalesce(func.sum(Order.total_amount), 0).label("total_spent"),
            )
            .join(Order, Order.customer_id == Customer.id)
            .filter(
                Customer.tenant_id == tenant_id,
                Order.status.in_([OrderStatus.CONFIRMED.value, OrderStatus.DELIVERED.value]),
            )
        )
        if store_id is not None:
            q = q.filter(Order.store_id == store_id)

        rows = (
            q.group_by(Customer.id, Customer.name, Customer.phone, Customer.email)
            .having(func.max(Order.created_at) <= threshold_date)
            .order_by(func.max(Order.created_at).asc())
            .limit(limit)
            .all()
        )

        now = datetime.utcnow()
        result = []
        for r in rows:
            last_date = r[4]
            days_inactive = (now - last_date).days if last_date else inactive_days
            if days_inactive >= 90:
                risk_level = "CRITICAL"
                action = "Urgent: Send 20% discount WhatsApp voucher or call directly"
            elif days_inactive >= 60:
                risk_level = "HIGH"
                action = "Send 15% Winback promotional SMS / WhatsApp"
            else:
                risk_level = "MEDIUM"
                action = "Send personalized product recommendation email"

            result.append(
                {
                    "customer_id": r[0],
                    "customer_name": r[1] or "Customer",
                    "phone": r[2],
                    "email": r[3],
                    "last_purchase_date": last_date,
                    "days_inactive": days_inactive,
                    "total_orders": int(r[5]),
                    "total_spent": round(float(r[6]), 2),
                    "risk_level": risk_level,
                    "recommended_action": action,
                }
            )
        return result

    def slow_moving_stock(
        self,
        tenant_id: int,
        days: int = 60,
        threshold_sales: int = 2,
        store_id: Optional[int] = None,
        limit: int = 50,
    ) -> list[dict]:
        """
        Detects dead stock and slow-moving items with high holding value and minimal sales.
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        inv_q = (
            self.db.query(
                Inventory.product_id,
                Inventory.store_id,
                Inventory.quantity,
                Product.name.label("product_name"),
                Product.sku.label("sku"),
                Product.cost_price,
                Product.selling_price,
            )
            .join(Product, Product.id == Inventory.product_id)
            .filter(
                Inventory.tenant_id == tenant_id,
                Inventory.quantity > 0,
            )
        )
        if store_id is not None:
            inv_q = inv_q.filter(Inventory.store_id == store_id)

        inv_items = inv_q.all()
        if not inv_items:
            return []

        sales_q = (
            self.db.query(
                OrderItem.product_id,
                func.coalesce(func.sum(OrderItem.quantity), 0).label("qty_sold"),
                func.max(Order.created_at).label("last_sold_at"),
            )
            .join(Order, Order.id == OrderItem.order_id)
            .filter(
                Order.tenant_id == tenant_id,
                Order.status.in_([OrderStatus.CONFIRMED.value, OrderStatus.DELIVERED.value]),
                Order.created_at >= cutoff_date,
            )
        )
        if store_id is not None:
            sales_q = sales_q.filter(Order.store_id == store_id)

        sales_map = {r[0]: (int(r[1]), r[2]) for r in sales_q.group_by(OrderItem.product_id).all()}

        slow_items = []
        now = datetime.utcnow()
        for i in inv_items:
            p_id = i[0]
            st_id = i[1]
            stock = int(i[2])
            p_name = i[3]
            sku = i[4]
            cost = float(i[5] or 0)
            selling = float(i[6] or 0)
            unit_val = cost if cost > 0 else (selling * 0.7 if selling > 0 else 0)

            sold_info = sales_map.get(p_id, (0, None))
            qty_sold = sold_info[0]
            last_sold = sold_info[1]

            if qty_sold <= threshold_sales:
                days_since = (now - last_sold).days if last_sold else days
                rec_discount = 30 if qty_sold == 0 and days_since >= 90 else (20 if qty_sold == 0 else 15)
                slow_items.append(
                    {
                        "product_id": p_id,
                        "product_name": p_name,
                        "sku": sku,
                        "store_id": st_id,
                        "current_stock": stock,
                        "stock_value": round(float(stock) * unit_val, 2),
                        "quantity_sold_in_period": qty_sold,
                        "days_since_last_sold": days_since,
                        "recommended_discount_percent": rec_discount,
                    }
                )

        slow_items.sort(key=lambda x: x["stock_value"], reverse=True)
        return slow_items[:limit]


    # --------------------------------------------------------------------------
    # Retail Copilot: Gemini GenAI & Rich Multilingual Intelligence
    # --------------------------------------------------------------------------

    def _get_copilot_context(self, tenant_id: int, store_id: Optional[int] = None) -> dict:
        now = datetime.utcnow()
        today_start = datetime(now.year, now.month, now.day)
        seven_days_ago = now - timedelta(days=7)
        fourteen_days_ago = now - timedelta(days=14)
        month_start = datetime(now.year, now.month, 1)

        def _get_sales(start_date, end_date=None):
            q = (
                self.db.query(
                    func.coalesce(func.sum(Order.total_amount), 0),
                    func.count(Order.id),
                )
                .filter(
                    Order.tenant_id == tenant_id,
                    Order.status.in_([OrderStatus.CONFIRMED.value, OrderStatus.DELIVERED.value]),
                    Order.created_at >= start_date,
                )
            )
            if end_date:
                q = q.filter(Order.created_at < end_date)
            if store_id is not None:
                q = q.filter(Order.store_id == store_id)
            row = q.first()
            return {"revenue": round(float(row[0]), 2), "orders": int(row[1])}

        sales_today = _get_sales(today_start)
        sales_this_week = _get_sales(seven_days_ago)
        sales_prev_week = _get_sales(fourteen_days_ago, seven_days_ago)
        sales_this_month = _get_sales(month_start)

        def _get_category_sales(start_date, end_date=None):
            q = (
                self.db.query(
                    Category.name,
                    func.coalesce(func.sum(OrderItem.total_amount), 0).label("cat_revenue"),
                    func.coalesce(func.sum(OrderItem.quantity), 0).label("cat_qty"),
                )
                .join(Product, Product.id == OrderItem.product_id)
                .join(Category, Category.id == Product.category_id)
                .join(Order, Order.id == OrderItem.order_id)
                .filter(
                    Order.tenant_id == tenant_id,
                    Order.status.in_([OrderStatus.CONFIRMED.value, OrderStatus.DELIVERED.value]),
                    Order.created_at >= start_date,
                )
            )
            if end_date:
                q = q.filter(Order.created_at < end_date)
            if store_id is not None:
                q = q.filter(Order.store_id == store_id)
            return {row[0]: {"revenue": round(float(row[1]), 2), "qty": int(row[2])} for row in q.group_by(Category.name).all()}

        cat_this_week = _get_category_sales(seven_days_ago)
        cat_prev_week = _get_category_sales(fourteen_days_ago, seven_days_ago)

        category_comparison = []
        all_cats = set(cat_this_week.keys()).union(set(cat_prev_week.keys()))
        for cname in all_cats:
            rev_curr = cat_this_week.get(cname, {}).get("revenue", 0.0)
            rev_prev = cat_prev_week.get(cname, {}).get("revenue", 0.0)
            diff = round(rev_curr - rev_prev, 2)
            pct_change = round(((diff / rev_prev) * 100), 1) if rev_prev > 0 else (100.0 if rev_curr > 0 else 0.0)
            category_comparison.append({
                "category_name": cname,
                "revenue_this_week": rev_curr,
                "revenue_prev_week": rev_prev,
                "diff": diff,
                "percent_change": pct_change,
                "status": "dropped" if diff < 0 else ("grown" if diff > 0 else "stable"),
            })
        category_comparison.sort(key=lambda x: x["diff"])

        top_products = self.best_selling_products(tenant_id, limit=5, store_id=store_id)

        low_stock_count = (
            self.db.query(func.count(Inventory.id))
            .filter(Inventory.tenant_id == tenant_id, Inventory.quantity <= Inventory.min_stock_level)
            .scalar() or 0
        )
        out_of_stock_count = (
            self.db.query(func.count(Inventory.id))
            .filter(Inventory.tenant_id == tenant_id, Inventory.quantity <= 0)
            .scalar() or 0
        )
        reorders = self.reorder_prediction(tenant_id, store_id)[:5]

        credit_cust_q = (
            self.db.query(
                Customer.id,
                Customer.name,
                Customer.phone,
                Customer.outstanding_balance,
                Customer.credit_limit,
            )
            .filter(
                Customer.tenant_id == tenant_id,
                Customer.outstanding_balance > 0,
            )
            .order_by(Customer.outstanding_balance.desc())
        )
        credit_customers = [
            {
                "id": c[0],
                "name": c[1],
                "phone": c[2],
                "outstanding_balance": float(c[3]),
                "credit_limit": float(c[4]),
            }
            for c in credit_cust_q.all()
        ]
        credit_over_1000 = [c for c in credit_customers if c["outstanding_balance"] >= 1000.0]

        total_customers = (
            self.db.query(func.count(Customer.id))
            .filter(Customer.tenant_id == tenant_id)
            .scalar() or 0
        )

        return {
            "sales_today": sales_today,
            "sales_this_week": sales_this_week,
            "sales_prev_week": sales_prev_week,
            "sales_this_month": sales_this_month,
            "category_comparison": category_comparison,
            "top_products": top_products,
            "low_stock_count": low_stock_count,
            "out_of_stock_count": out_of_stock_count,
            "reorders": reorders,
            "credit_customers": credit_customers,
            "credit_over_1000": credit_over_1000,
            "total_customers": total_customers,
        }

    def _call_gemini_copilot(self, query_str: str, context: dict) -> Optional[dict]:
        api_key = settings.GEMINI_API_KEY
        if not api_key:
            return None

        system_instruction = (
            "You are Retail-OS AI Copilot (स्मार्ट रिटेल असिस्टंट), an expert Indian retail business intelligence engine. "
            "Follow these rules:\n"
            "1. Language Matching: Detect user language (Marathi, Hindi, English) and answer in the SAME language.\n"
            "2. Ground all answers strictly in Live Retail Store Context data.\n"
            "3. When asked about dropping categories, explain which dropped, by how much (₹ and %), reasons (stockout/seasonal), and 2-3 corrective steps.\n"
            "4. When asked about festival/Diwali stocking, list the top 5 essential products to stock up, why, and recommend a 30-50% safety stock buffer.\n"
            "5. When asked about credit/khata > ₹1000, list customer names, phone numbers, and balances, and recommend sending WhatsApp payment reminders.\n"
            "6. Output MUST be valid JSON adhering to: {\"intent\": \"...\", \"answer\": \"markdown string\", \"data\": {}, \"suggested_actions\": []}"
        )

        user_content = f"User Question:\n\"{query_str}\"\n\nLive Retail Store Context Data:\n{json.dumps(context, indent=2, default=str)}"
        url = f"{settings.GEMINI_API_URL}/models/{settings.GEMINI_MODEL}:generateContent?key={api_key}"
        payload = {
            "contents": [{"parts": [{"text": user_content}]}],
            "systemInstruction": {"parts": [{"text": system_instruction}]},
            "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
        }

        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.post(url, json=payload)
                if resp.status_code == 200:
                    res_json = resp.json()
                    raw_text = res_json["candidates"][0]["content"]["parts"][0]["text"].strip()
                    parsed = json.loads(raw_text)
                    if isinstance(parsed, dict) and "answer" in parsed:
                        return {
                            "query": query_str,
                            "intent": parsed.get("intent", "copilot_insight"),
                            "answer": parsed["answer"],
                            "data": parsed.get("data", {}),
                            "suggested_actions": parsed.get("suggested_actions", []),
                        }
        except Exception as exc:
            logger.warning("Gemini Copilot API call failed, falling back to rule engine: %s", exc)

        return None

    def _rule_based_chat_query(self, tenant_id: int, query_str: str, store_id: Optional[int] = None, context: Optional[dict] = None) -> dict:
        q_clean = query_str.lower().strip()
        now = datetime.utcnow()
        today_start = datetime(now.year, now.month, now.day)
        month_start = datetime(now.year, now.month, 1)

        ctx = context or self._get_copilot_context(tenant_id, store_id)

        # 1. CATEGORY COMPARISON / DROP ANALYSIS (e.g. 'मागच्या आठवड्यापेक्षा या आठवड्यात कोणत्या कॅटेगरीचा सेल कमी झाला आणि का?')
        if any(w in q_clean for w in ["कॅटेगरी", "category", "कमी", "drop", "घट", "विक्री कमी", "sale down", "sales drop", "decreased"]):
            cat_drops = [c for c in ctx["category_comparison"] if c["diff"] < 0]
            intent = "category_drop_analysis"
            if cat_drops:
                lines = []
                for idx, c in enumerate(cat_drops[:3], 1):
                    lines.append(f"{idx}. *{c['category_name']}*: विक्रीत ₹{abs(c['diff']):,.2f} ({c['percent_change']}%) ची घट झाली आहे.")
                cat_summary = "\n".join(lines)
                answer = (
                    f"📊 *कॅटेगरी विक्री विश्लेषण (Category Performance)*\n\n"
                    f"मागच्या आठवड्याच्या तुलनेत या आठवड्यात खालील कॅटेगरींच्या विक्रीमध्ये घट (Drop) झाली आहे:\n\n"
                    f"{cat_summary}\n\n"
                    f"🔍 *संभाव्य कारणे:*\n"
                    f"१. संबंधित कॅटेगरीतील लोकप्रिय उत्पादनांचा स्टॉक संपणे (Stockout).\n"
                    f"२. ग्राहकांची आठवड्याची खरेदी प्राधान्ये बदलणे.\n\n"
                    f"💡 *उपाय व शिफारसी:*\n"
                    f"• कमी झालेल्या कॅटेगरीतील टॉप प्रॉडक्ट्सचा तातडीने री-ऑर्डर करा.\n"
                    f"• ग्राहकांना आकर्षित करण्यासाठी विशेष सवलत (Discount) किंवा कॉम्बो ऑफर्स सुरू करा."
                )
                data = {"dropped_categories": cat_drops, "all_categories": ctx["category_comparison"]}
            else:
                answer = (
                    "मागच्या आठवड्याशी तुलना करता सर्व कॅटेगरींची विक्री समाधानकारक व स्थिर आहे. "
                    "कोणत्याही मुख्य कॅटेगरीत लक्षणीय घट नोंदवली गेलेली नाही."
                )
                data = {"category_comparison": ctx["category_comparison"]}
            actions = ["Check category inventory", "Create promotional discount coupon", "Review supplier purchase orders"]
            return {"query": query_str, "intent": intent, "answer": answer, "data": data, "suggested_actions": actions}

        # 2. FESTIVAL / DIWALI STOCKING PREDICTIONS (e.g. 'दिवाळीसाठी मला कोणत्या ५ प्रॉडक्ट्सचा स्टॉक जास्त मागवावा लागेल?')
        elif any(w in q_clean for w in ["दिवाळी", "diwali", "festival", "सण", "जास्त स्टॉक", "stock जास्त", "फेस्टिव्हल", "तयारी"]):
            intent = "festival_reorder_recommendation"
            top_prods = ctx["top_products"]

            rec_list = []
            if top_prods:
                for idx, p in enumerate(top_prods[:5], 1):
                    sold = p.get("quantity_sold", 10)
                    rec_buffer = max(15, int(sold * 1.5))
                    rec_list.append(f"{idx}. *{p['product_name']}* — अपेक्षित मागणी: {rec_buffer} युनिट्स (सध्याची विक्री: {sold})")
            else:
                rec_list = [
                    "1. *साखर (Sugar)* — अपेक्षित सण मागणी: 100 kg",
                    "2. *खाद्यतेल (Cooking Oil)* — अपेक्षित सण मागणी: 50 Ltr",
                    "3. *बेसन व मैदा (Flour)* — अपेक्षित सण मागणी: 40 kg",
                    "4. *ड्रायफ्रूट्स (Dry Fruits)* — अपेक्षित सण मागणी: 25 Boxes",
                    "5. *दूध व दुग्धजन्य उत्पादने (Milk & Dairy)* — अपेक्षित सण मागणी: 80 Ltr",
                ]

            rec_text = "\n".join(rec_list)
            answer = (
                f"🪔 *दिवाळी / सण विशेष स्टॉक शिफारस (Festival Reorder Advisory)*\n\n"
                f"दिवाळी व सणासुदीच्या काळात किराणा आणि मिठाईच्या वस्तूंना ३०% ते ५०% जादा मागणी असते. "
                f"दुकानात स्टॉक तुटवडा टाळण्यासाठी खालील ५ प्रमुख उत्पादनांचा जास्तीचा स्टॉक आगाऊ मागवणे आवश्यक आहे:\n\n"
                f"{rec_text}\n\n"
                f"📦 *सल्ला:* सप्लायर्सकडून सणाच्या आधीच बल्क डिस्काउंट मिळवण्यासाठी आजच परचेस ऑर्डर (PO) जनरेट करा."
            )
            actions = ["Generate bulk purchase orders", "Contact primary FMCG distributors", "Create Diwali festive bundles"]
            data = {"recommended_festive_items": top_prods[:5] if top_prods else []}
            return {"query": query_str, "intent": intent, "answer": answer, "data": data, "suggested_actions": actions}

        # 3. CUSTOMER CREDIT / KHATA > 1000 (e.g. '१००० रुपयांपेक्षा जास्त उधारी बाकी असलेल्या ग्राहकांची यादी दाखव आणि त्यांना रिमाइंडर्स पाठव')
        elif any(w in q_clean for w in ["उधारी", "khata", "credit", "1000", "१०००", "बाकी", "थकीत", "remind", "रिमाइंडर"]):
            intent = "credit_khata_reminders"
            over_1000 = ctx["credit_over_1000"]
            total_pending = sum(c["outstanding_balance"] for c in over_1000)

            if over_1000:
                cust_lines = []
                for idx, c in enumerate(over_1000[:5], 1):
                    cust_lines.append(f"{idx}. *{c['name']}* — थकीत: ₹{c['outstanding_balance']:,.2f} (फोन: {c['phone']})")
                cust_str = "\n".join(cust_lines)
                answer = (
                    f"📋 *उधारी खातेदार अहवाल (Customer Credit Ledger)*\n\n"
                    f"तुमच्या दुकानात ₹१००० पेक्षा जास्त उधारी बाकी असलेले एकूण *{len(over_1000)} ग्राहक* आहेत.\n"
                    f"एकूण थकीत रक्कम: *₹{total_pending:,.2f}*\n\n"
                    f"प्रमुख ग्राहकांची यादी:\n"
                    f"{cust_str}\n\n"
                    f"📲 *कृती:* तुम्ही खालील बटण वापरून या सर्व ग्राहकांना त्यांच्या व्हॉट्सॲपवर अधिकृत पेमेंट रिमाइंडर व UPI लिंक पाठवू शकता."
                )
                data = {"credit_over_1000_customers": over_1000, "total_outstanding": total_pending}
            else:
                answer = (
                    "🎉 उत्कृष्ट! तुमच्या दुकानात सध्या कोणत्याही ग्राहकाकडे ₹१००० पेक्षा जास्त उधारी बाकी नाही. "
                    "सर्व उधारी खाती नियंत्रणात आहेत."
                )
                data = {"credit_over_1000_customers": []}

            actions = ["Send WhatsApp payment reminders to all", "View customer credit ledger", "Set customer credit limits"]
            return {"query": query_str, "intent": intent, "answer": answer, "data": data, "suggested_actions": actions}

        # 4. TODAY'S SALES
        elif any(w in q_clean for w in ["today", "aaj"]) and any(w in q_clean for w in ["sale", "revenue", "collection", "turnover", "income"]):
            tot = ctx["sales_today"]["revenue"]
            cnt = ctx["sales_today"]["orders"]
            intent = "today_sales"
            answer = f"Today's total sales are ₹{tot:,.2f} across {cnt} completed orders."
            data = {"sales_amount": tot, "order_count": cnt, "date": today_start.strftime("%Y-%m-%d")}
            actions = ["View daily sales report", "Check cashier drawer closing status", "View active shifts"]
            return {"query": query_str, "intent": intent, "answer": answer, "data": data, "suggested_actions": actions}

        # 5. MONTHLY SALES
        elif any(w in q_clean for w in ["month", "monthly", "this month"]):
            tot = ctx["sales_this_month"]["revenue"]
            cnt = ctx["sales_this_month"]["orders"]
            intent = "monthly_sales"
            answer = f"This month's revenue is ₹{tot:,.2f} from {cnt} orders."
            data = {"month": month_start.strftime("%B %Y"), "revenue": tot, "orders": cnt}
            actions = ["View monthly P&L", "Export tax report", "Check best sellers"]
            return {"query": query_str, "intent": intent, "answer": answer, "data": data, "suggested_actions": actions}

        # 6. BEST SELLERS
        elif any(w in q_clean for w in ["best seller", "top product", "most sold", "popular"]):
            top = ctx["top_products"][:3]
            intent = "best_sellers"
            if top:
                names = ", ".join([f"'{p['product_name']}' ({p['quantity_sold']} units)" for p in top])
                answer = f"Your top selling products are: {names}."
                data = {"top_products": top}
            else:
                answer = "No sales recorded yet to determine best sellers."
                data = {}
            actions = ["View inventory for top sellers", "Generate purchase orders", "Create promotional bundle"]
            return {"query": query_str, "intent": intent, "answer": answer, "data": data, "suggested_actions": actions}

        # 7. STOCK ALERTS
        elif any(w in q_clean for w in ["stock", "out of stock", "low stock", "inventory"]):
            low_cnt = ctx["low_stock_count"]
            out_cnt = ctx["out_of_stock_count"]
            intent = "stock_alerts"
            answer = f"You have {low_cnt} items running below minimum stock level, including {out_cnt} completely out of stock."
            data = {"low_stock_count": low_cnt, "out_of_stock_count": out_cnt}
            actions = ["Open reorder prediction", "Create purchase order", "Check supplier catalog"]
            return {"query": query_str, "intent": intent, "answer": answer, "data": data, "suggested_actions": actions}

        # 8. CUSTOMER STATS
        elif any(w in q_clean for w in ["customer", "clients", "members"]):
            cust_cnt = ctx["total_customers"]
            intent = "customer_stats"
            answer = f"Your store has {cust_cnt} registered customers."
            data = {"total_customers": cust_cnt}
            actions = ["View customer churn risk", "Launch promotional offer campaign", "Send loyalty points update"]
            return {"query": query_str, "intent": intent, "answer": answer, "data": data, "suggested_actions": actions}

        # 9. GENERAL SUMMARY
        else:
            intent = "general_summary"
            answer = (
                "I am Retail-OS AI Assistant (स्मार्ट रिटेल सल्लागार). I can help you with sales figures, category trends, "
                "festival stocking, customer khata balances, inventory alerts, and best sellers. "
                "Try asking:\n"
                "• 'मागच्या आठवड्यापेक्षा या आठवड्यात कोणत्या कॅटेगरीचा सेल कमी झाला आणि का?'\n"
                "• 'दिवाळीसाठी मला कोणत्या ५ प्रॉडक्ट्सचा स्टॉक जास्त मागवावा लागेल?'\n"
                "• '१००० रुपयांपेक्षा जास्त उधारी बाकी असलेल्या ग्राहकांची यादी दाखव आणि त्यांना रिमाइंडर्स पाठव.'\n"
                "• 'What are today\'s sales?' or 'Show best sellers'"
            )
            actions = ["Check today's sales", "Check low stock alerts", "View top selling products", "Customer credit analysis"]
            return {"query": query_str, "intent": intent, "answer": answer, "data": {}, "suggested_actions": actions}

    def chat_query(self, tenant_id: int, query_str: str, store_id: Optional[int] = None) -> dict:
        """
        AI Natural Language Retail Assistant: interprets natural language business questions
        using Gemini 1.5 GenAI with robust contextual rule-based fallback.
        """
        context = self._get_copilot_context(tenant_id, store_id)

        # Attempt Gemini GenAI Copilot
        if settings.GEMINI_API_KEY:
            ai_res = self._call_gemini_copilot(query_str, context)
            if ai_res:
                return ai_res

        # Fallback to enhanced multilingual deterministic engine
        return self._rule_based_chat_query(tenant_id, query_str, store_id, context)
