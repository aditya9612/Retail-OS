import json
import re
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
from app.models.role import Role
from app.models.store import Store
from app.models.supplier import Supplier
from app.models.tenant import Tenant
from app.models.user import User
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

        tenant_obj = self.db.query(Tenant).filter(Tenant.id == tenant_id).first()

        # Multi-Store & Branch Hierarchy (dynamically queried from database)
        stores_q = (
            self.db.query(Store)
            .filter(Store.tenant_id == tenant_id, Store.is_active.is_(True))
            .order_by(Store.is_main.desc(), Store.id.asc())
            .all()
        )

        all_stores = []
        for s in stores_q:
            all_stores.append({
                "id": s.id,
                "name": s.name,
                "code": s.code,
                "city": s.city,
                "state": s.state,
                "pincode": s.pincode,
                "address": s.address,
                "phone": s.phone,
                "email": s.email,
                "is_main": bool(s.is_main),
                "is_warehouse": bool(s.is_warehouse),
                "reference_number": s.reference_number,
            })

        # Selected Primary Store
        if store_id:
            store_obj = next((s for s in stores_q if s.id == store_id), None)
        else:
            store_obj = next((s for s in stores_q if s.is_main), None) or (stores_q[0] if stores_q else None)

        store_info = {
            "store_name": getattr(store_obj, "name", None) if store_obj else (getattr(tenant_obj, "name", None) if tenant_obj else "Retail Store"),
            "store_code": getattr(store_obj, "code", None) if store_obj else None,
            "city": getattr(store_obj, "city", None) if store_obj else None,
            "state": getattr(store_obj, "state", None) if store_obj else None,
            "pincode": getattr(store_obj, "pincode", None) if store_obj else None,
            "address": getattr(store_obj, "address", None) if store_obj else None,
            "phone": getattr(store_obj, "phone", None) if store_obj else None,
            "email": getattr(store_obj, "email", None) if store_obj else None,
            "is_main": bool(getattr(store_obj, "is_main", False)),
            "is_warehouse": bool(getattr(store_obj, "is_warehouse", False)),
        }

        # Per-store sales today breakdown
        store_sales_today = {}
        for s in stores_q:
            sq = (
                self.db.query(
                    func.coalesce(func.sum(Order.total_amount), 0),
                    func.count(Order.id),
                )
                .filter(
                    Order.tenant_id == tenant_id,
                    Order.store_id == s.id,
                    Order.status.in_([OrderStatus.CONFIRMED.value, OrderStatus.DELIVERED.value]),
                    Order.created_at >= today_start,
                )
                .first()
            )
            store_sales_today[s.name] = {
                "store_id": s.id,
                "name": s.name,
                "city": s.city,
                "revenue": round(float(sq[0]), 2),
                "orders": int(sq[1]),
                "is_main": bool(s.is_main),
                "is_warehouse": bool(s.is_warehouse),
            }

        # Products & Catalog Dynamic Aggregation
        total_products = (
            self.db.query(func.count(Product.id))
            .filter(Product.tenant_id == tenant_id, Product.is_active.is_(True))
            .scalar() or 0
        )
        most_exp = (
            self.db.query(Product.name, Product.selling_price, Product.mrp)
            .filter(Product.tenant_id == tenant_id, Product.is_active.is_(True))
            .order_by(Product.selling_price.desc())
            .first()
        )
        cheapest = (
            self.db.query(Product.name, Product.selling_price, Product.mrp)
            .filter(Product.tenant_id == tenant_id, Product.is_active.is_(True), Product.selling_price > 0)
            .order_by(Product.selling_price.asc())
            .first()
        )
        categories_q = (
            self.db.query(Category.id, Category.name, func.count(Product.id))
            .outerjoin(Product, (Product.category_id == Category.id) & (Product.tenant_id == tenant_id))
            .filter(Category.tenant_id == tenant_id)
            .group_by(Category.id, Category.name)
            .all()
        )
        categories_list = [{"id": c[0], "name": c[1], "product_count": c[2]} for c in categories_q]

        prods_sample_q = (
            self.db.query(Product.id, Product.name, Product.sku, Product.selling_price, Product.mrp)
            .filter(Product.tenant_id == tenant_id, Product.is_active.is_(True))
            .order_by(Product.selling_price.desc())
            .limit(20)
            .all()
        )
        products_sample = [
            {"id": p[0], "name": p[1], "sku": p[2], "selling_price": float(p[3] or 0), "mrp": float(p[4] or 0)}
            for p in prods_sample_q
        ]

        # Suppliers Dynamic Aggregation
        suppliers_q = (
            self.db.query(Supplier.id, Supplier.name, Supplier.contact_person, Supplier.phone, Supplier.email)
            .filter(Supplier.tenant_id == tenant_id)
            .all()
        )
        suppliers_list = [
            {"id": sp[0], "name": sp[1], "contact_person": sp[2], "phone": sp[3], "email": sp[4]}
            for sp in suppliers_q
        ]

        # Staff & Users Dynamic Aggregation
        users_q = (
            self.db.query(User.id, User.full_name, User.email, User.phone, User.role_id, User.store_id)
            .filter(User.tenant_id == tenant_id, User.is_active.is_(True), User.is_deleted.is_(False))
            .all()
        )
        roles_dict = {r.id: r.name for r in self.db.query(Role).filter(Role.tenant_id == tenant_id).all()}
        stores_dict = {s.id: s.name for s in stores_q}
        staff_list = [
            {
                "id": u[0],
                "name": u[1],
                "email": u[2],
                "phone": u[3],
                "role": roles_dict.get(u[4], "Staff"),
                "assigned_store": stores_dict.get(u[5], "सर्व शाखा / मुख्य कार्यालय"),
            }
            for u in users_q
        ]

        # Purchase Orders Dynamic Aggregation
        pos_count = (
            self.db.query(func.count(PurchaseOrder.id))
            .filter(PurchaseOrder.tenant_id == tenant_id)
            .scalar() or 0
        )
        pending_pos_count = (
            self.db.query(func.count(PurchaseOrder.id))
            .filter(PurchaseOrder.tenant_id == tenant_id, PurchaseOrder.status.in_(["PENDING", "ORDERED"]))
            .scalar() or 0
        )

        total_outstanding_amount = sum(c["outstanding_balance"] for c in credit_customers)

        admin_user = (
            self.db.query(User).filter(User.tenant_id == tenant_id).order_by(User.id.asc()).first()
        )
        admin_name = "Admin"
        if admin_user:
            admin_name = getattr(admin_user, "full_name", None) or getattr(admin_user, "name", None) or "Admin"
        elif tenant_obj:
            admin_name = getattr(tenant_obj, "name", "Admin")

        admin_info = {
            "admin_name": admin_name,
            "admin_email": getattr(admin_user, "email", None) if admin_user else None,
        }

        return {
            "tenant_info": {
                "tenant_name": tenant_obj.name if tenant_obj else "Retail-OS Enterprise",
                "domain": getattr(tenant_obj, "domain", ""),
            },
            "store_info": store_info,
            "all_stores": all_stores,
            "store_sales_today": store_sales_today,
            "total_stores_count": len(all_stores),
            "admin_info": admin_info,
            "catalog": {
                "total_products_count": total_products,
                "most_expensive_product": {
                    "name": most_exp[0] if most_exp else None,
                    "selling_price": float(most_exp[1]) if most_exp else 0.0,
                    "mrp": float(most_exp[2]) if most_exp else 0.0,
                } if most_exp else None,
                "cheapest_product": {
                    "name": cheapest[0] if cheapest else None,
                    "selling_price": float(cheapest[1]) if cheapest else 0.0,
                    "mrp": float(cheapest[2]) if cheapest else 0.0,
                } if cheapest else None,
                "categories": categories_list,
                "top_products_catalog": products_sample,
            },
            "inventory_details": {
                "low_stock_count": low_stock_count,
                "out_of_stock_count": out_of_stock_count,
                "reorder_predictions": reorders,
            },
            "customers_details": {
                "total_customers": total_customers,
                "total_outstanding_credit": total_outstanding_amount,
                "customers_with_dues": credit_customers,
            },
            "suppliers_details": {
                "total_suppliers": len(suppliers_list),
                "suppliers_list": suppliers_list,
                "total_purchase_orders": pos_count,
                "pending_purchase_orders": pending_pos_count,
            },
            "staff_details": {
                "total_staff_count": len(staff_list),
                "staff_members": staff_list,
            },
            # Backward-compatibility keys for existing rules & tests:
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

    @staticmethod
    def _clean_for_speech(text: str) -> str:
        """
        Strips markdown formatting, symbols, emojis, and creates a clean,
        fluent spoken sentence for Text-to-Speech (TTS) engines in Marathi/Hindi/English.
        """
        if not text:
            return ""
        cleaned = re.sub(r"```[\s\S]*?```", "", text)
        cleaned = re.sub(r"`[^`]+`", "", cleaned)
        cleaned = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", cleaned)
        cleaned = re.sub(r"[#*_~|•\-–—]+", " ", cleaned)
        cleaned = re.sub(r"^\s*\d+\.\s*", "", cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r"[\U00010000-\U0010ffff]", "", cleaned)
        cleaned = re.sub(r"\n+", ". ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    @staticmethod
    def _transliterate_devanagari(text: str) -> str:
        """
        Generic phonetic transliteration from Devanagari script to Latin characters
        to allow natural multilingual matching against database entities without any hardcoded city/name lists.
        """
        if not text:
            return ""
        char_map = {
            'क': 'k', 'ख': 'kh', 'ग': 'g', 'घ': 'gh', 'ङ': 'ng',
            'च': 'ch', 'छ': 'chh', 'ज': 'j', 'झ': 'jh', 'ञ': 'ny',
            'ट': 't', 'ठ': 'th', 'ड': 'd', 'ढ': 'dh', 'ण': 'n',
            'त': 't', 'थ': 'th', 'द': 'd', 'ध': 'dh', 'न': 'n',
            'प': 'p', 'फ': 'ph', 'ब': 'b', 'भ': 'bh', 'म': 'm',
            'य': 'y', 'र': 'r', 'ल': 'l', 'व': 'v', 'श': 'sh',
            'ष': 'sh', 'स': 's', 'ह': 'h', 'ळ': 'l',
            'ा': 'a', 'ि': 'i', 'ी': 'i', 'ु': 'u', 'ू': 'u',
            'े': 'e', 'ै': 'ai', 'ो': 'o', 'ौ': 'au', 'ं': 'm',
            '्': '', 'अ': 'a', 'आ': 'a', 'इ': 'i', 'ई': 'i',
            'उ': 'u', 'ऊ': 'u', 'ए': 'e', 'ऐ': 'ai', 'ओ': 'o', 'औ': 'au'
        }
        res = []
        for ch in text:
            res.append(char_map.get(ch, ch))
        return "".join(res).lower()

    def _call_gemini_copilot(self, query_str: str, context: dict) -> Optional[dict]:
        api_key = settings.GEMINI_API_KEY
        if not api_key:
            return None

        system_instruction = (
            "You are Retail-OS AI Voice Copilot (स्मार्ट रिटेल व्हॉईस असिस्टंट), an expert real-time retail business intelligence engine.\n"
            "You have direct real-time access to the store's full database state via `Live Retail Store Context Data`.\n"
            "Rules:\n"
            "1. Language Matching: Detect user language. If Marathi, reply in Marathi. If English, reply in English. If Hindi, reply in Hindi.\n"
            "2. Ground ALL answers strictly in the provided Live Context without hardcoding or making assumptions:\n"
            "   - Stores & Branches: use `all_stores`, `store_info`, and `store_sales_today` (all addresses, phones, cities, warehouse status).\n"
            "   - Products & Prices: use `catalog` (total_products_count, most_expensive_product, cheapest_product, categories, top_products_catalog).\n"
            "   - Suppliers & Vendors: use `suppliers_details` (total_suppliers, suppliers_list, pending_purchase_orders).\n"
            "   - Employees & Staff: use `staff_details` (total_staff_count, staff_members with assigned branches and roles).\n"
            "   - Customers & Udhaari: use `customers_details` (total_customers, total_outstanding_credit, customers_with_dues).\n"
            "   - Sales & Galla: use `sales_today`, `sales_this_month`, and `store_sales_today`.\n"
            "   - Inventory & Stock: use `inventory_details` (low_stock_count, out_of_stock_count, reorders).\n"
            "3. If asked about ANY entity (store, branch, product, price, supplier, employee, customer, sale, or stock), look up the real data in context and answer with exact facts and figures.\n"
            "4. Keep answers clear, natural, helpful, and concise.\n"
            "5. Choose an appropriate intent: 'today_sales', 'monthly_sales', 'best_sellers', 'stock_alerts', 'credit_khata_reminders', 'category_drop_analysis', 'festival_reorder_recommendation', 'customer_stats', 'admin_store_info', 'store_list_info', 'product_catalog_info', 'supplier_info', 'staff_info', 'copilot_insight'.\n"
            "6. Output MUST be valid JSON adhering to: "
            "{\"intent\": \"...\", \"answer\": \"markdown string\", \"speech_text\": \"clean spoken answer for Text-to-Speech speaker without any markdown asterisks, emojis or bullet symbols\", \"data\": {}, \"suggested_actions\": []}"
        )

        user_content = f"User Question:\n\"{query_str}\"\n\nLive Retail Store Context Data:\n{json.dumps(context, indent=2, default=str)}"

        configured_model = getattr(settings, "GEMINI_MODEL", "gemini-3.5-flash-lite") or "gemini-3.5-flash-lite"
        candidate_models = [configured_model, "gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3-flash-preview"]
        seen_models = set()

        for model_name in candidate_models:
            if not model_name or model_name in seen_models:
                continue
            seen_models.add(model_name)

            url = f"{settings.GEMINI_API_URL}/models/{model_name}:generateContent?key={api_key}"
            payload = {
                "contents": [{"parts": [{"text": user_content}]}],
                "systemInstruction": {"parts": [{"text": system_instruction}]},
                "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
            }

            try:
                with httpx.Client(timeout=12.0) as client:
                    resp = client.post(url, json=payload)
                    if resp.status_code == 200:
                        res_json = resp.json()
                        raw_text = res_json["candidates"][0]["content"]["parts"][0]["text"].strip()
                        if raw_text.startswith("```"):
                            raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
                            raw_text = re.sub(r"\s*```$", "", raw_text)
                        try:
                            parsed = json.loads(raw_text)
                            if isinstance(parsed, dict) and "answer" in parsed:
                                sp_text = parsed.get("speech_text") or self._clean_for_speech(parsed["answer"])
                                raw_intent = str(parsed.get("intent", "copilot_insight")).lower().strip()
                                norm_map = {
                                    "sales_today": "today_sales",
                                    "today_sale": "today_sales",
                                    "todays_sales": "today_sales",
                                    "daily_sales": "today_sales",
                                    "best_seller": "best_sellers",
                                    "top_products": "best_sellers",
                                    "top_product": "best_sellers",
                                    "low_stock": "stock_alerts",
                                    "stock_alert": "stock_alerts",
                                    "inventory_alert": "stock_alerts",
                                    "customer_count": "customer_stats",
                                    "total_customers": "customer_stats",
                                }
                                intent = norm_map.get(raw_intent, raw_intent)
                                return {
                                    "query": query_str,
                                    "intent": intent,
                                    "answer": parsed["answer"],
                                    "speech_text": sp_text,
                                    "data": parsed.get("data", {}),
                                    "suggested_actions": parsed.get("suggested_actions", []),
                                }
                        except Exception:
                            sp_text = self._clean_for_speech(raw_text)
                            return {
                                "query": query_str,
                                "intent": "copilot_insight",
                                "answer": raw_text,
                                "speech_text": sp_text,
                                "data": {},
                                "suggested_actions": [],
                            }
                    else:
                        logger.warning("Gemini model %s returned status %s: %s", model_name, resp.status_code, resp.text[:120])
            except Exception as exc:
                logger.warning("Gemini model %s request exception: %s", model_name, exc)

        return None

    def _call_gemini_audio_copilot(
        self,
        audio_base64: str,
        mime_type: str,
        context: dict,
        language: str = "mr-IN",
    ) -> Optional[dict]:
        api_key = settings.GEMINI_API_KEY
        if not api_key:
            return None

        system_instruction = (
            "You are Retail-OS AI Voice Copilot (स्मार्ट रिटेल व्हॉईस असिस्टंट).\n"
            "The user has spoken a business question in audio.\n"
            "1. Listen to the user's speech audio, transcribe it accurately in the original language (Marathi, Hindi, or English).\n"
            "2. Answer the question using the provided Live Retail Store Context data (sales, stock, credit, store_info, admin_info).\n"
            "3. Generate a clean speech_text designed to be spoken aloud via speaker (TTS) with NO markdown asterisks, bullet points or emojis.\n"
            "4. Output MUST be valid JSON strictly adhering to: "
            "{\"transcription\": \"user spoken words\", \"intent\": \"...\", \"answer\": \"formatted markdown answer\", \"speech_text\": \"clean spoken answer for speaker playback\", \"data\": {}, \"suggested_actions\": []}"
        )

        user_content = f"Live Retail Store Context Data:\n{json.dumps(context, indent=2, default=str)}"
        configured_model = getattr(settings, "GEMINI_MODEL", "gemini-3.5-flash-lite") or "gemini-3.5-flash-lite"
        candidate_models = [configured_model, "gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3-flash-preview"]
        seen_models = set()

        for model_name in candidate_models:
            if not model_name or model_name in seen_models:
                continue
            seen_models.add(model_name)

            url = f"{settings.GEMINI_API_URL}/models/{model_name}:generateContent?key={api_key}"
            payload = {
                "contents": [
                    {
                        "parts": [
                            {
                                "inlineData": {
                                    "mimeType": mime_type,
                                    "data": audio_base64,
                                }
                            },
                            {"text": user_content},
                        ]
                    }
                ],
                "systemInstruction": {"parts": [{"text": system_instruction}]},
                "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
            }

            try:
                with httpx.Client(timeout=25.0) as client:
                    resp = client.post(url, json=payload)
                    if resp.status_code == 200:
                        res_json = resp.json()
                        raw_text = res_json["candidates"][0]["content"]["parts"][0]["text"].strip()
                        if raw_text.startswith("```"):
                            raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
                            raw_text = re.sub(r"\s*```$", "", raw_text)
                        try:
                            parsed = json.loads(raw_text)
                            if isinstance(parsed, dict) and ("answer" in parsed or "speech_text" in parsed):
                                transcription = parsed.get("transcription") or "व्हॉईस प्रश्न"
                                ans = parsed.get("answer") or parsed.get("speech_text")
                                sp_text = parsed.get("speech_text") or self._clean_for_speech(ans)
                                return {
                                    "query": transcription,
                                    "intent": parsed.get("intent", "voice_query"),
                                    "answer": ans,
                                    "speech_text": sp_text,
                                    "data": parsed.get("data", {}),
                                    "suggested_actions": parsed.get("suggested_actions", []),
                                }
                        except Exception:
                            sp_text = self._clean_for_speech(raw_text)
                            return {
                                "query": "व्हॉईस प्रश्न",
                                "intent": "voice_query",
                                "answer": raw_text,
                                "speech_text": sp_text,
                                "data": {},
                                "suggested_actions": [],
                            }
            except Exception as exc:
                logger.warning("Gemini Audio model %s call failed: %s", model_name, exc)

        return None

    def _rule_based_chat_query(self, tenant_id: int, query_str: str, store_id: Optional[int] = None, context: Optional[dict] = None) -> dict:
        q_clean = query_str.lower().strip()
        now = datetime.utcnow()
        today_start = datetime(now.year, now.month, now.day)
        month_start = datetime(now.year, now.month, 1)

        ctx = context or self._get_copilot_context(tenant_id, store_id)
        all_stores = ctx.get("all_stores", [])
        store_sales_today = ctx.get("store_sales_today", {})

        # Dynamic store matching using database store attributes and generic phonetic transliteration
        q_translit = self._transliterate_devanagari(q_clean)
        matching_stores = []
        for s in all_stores:
            s_name = (s.get("name") or "").lower()
            s_city = (s.get("city") or "").lower()
            s_code = (s.get("code") or "").lower()
            s_addr = (s.get("address") or "").lower()

            if (s_city and (s_city in q_clean or s_city in q_translit)):
                matching_stores.append(s)
            elif (s_name and (s_name in q_clean or s_name in q_translit)):
                matching_stores.append(s)
            elif (s_code and s_code in q_clean):
                matching_stores.append(s)
            elif any(part in q_clean or part in q_translit for part in s_name.split() if len(part) > 3):
                matching_stores.append(s)

        # A. SPECIFIC BRANCH QUERY (e.g. 'कोल्हापूर शॉपबद्दलची सर्व डीटेल सांग', 'कोल्हापूर स्टोअरचा गल्ला सांग')
        if matching_stores:
            if len(matching_stores) == 1:
                target_store = matching_stores[0]
                st_name = target_store["name"]
                st_city = target_store.get("city") or ""
                is_wh = target_store.get("is_warehouse", False)
                is_mn = target_store.get("is_main", False)
                branch_type = "गोदाम (Warehouse)" if is_wh else ("मुख्य स्टोअर (Main Branch)" if is_mn else "रिटेल शाखा")

                # Sales / Galla for specific branch
                if any(w in q_clean for w in ["गल्ला", "विक्री", "सेल", "कमाई", "sale", "revenue", "turnover", "ऑर्डर"]):
                    st_data = store_sales_today.get(st_name, {})
                    rev = st_data.get("revenue", 0.0)
                    ords = st_data.get("orders", 0)
                    answer = (
                        f"🏪 **{st_name} ({st_city}) विक्री अहवाल**\n\n"
                        f"• **आजचा एकूण गल्ला (विक्री):** ₹{rev:,.2f}\n"
                        f"• **आजच्या पूर्ण झालेल्या ऑर्डर्स:** {ords} ऑर्डर्स\n"
                        f"• **शाखा प्रकार:** {branch_type}\n"
                        f"• **ठिकाण:** {target_store.get('address') or st_city}"
                    )
                    speech_text = f"{st_name} चा आजचा एकूण गल्ला {int(rev)} रुपये असून आज {ords} ऑर्डर्स पूर्ण झाल्या आहेत."
                    return {"query": query_str, "intent": "today_sales", "answer": answer, "speech_text": speech_text, "data": st_data, "suggested_actions": ["View branch sales report", "Check stock at branch"]}

                # Address / Contact for specific branch
                else:
                    addr = target_store.get("address") or "पत्ता उपलब्ध नाही"
                    state = target_store.get("state") or "महाराष्ट्र"
                    pin = target_store.get("pincode") or ""
                    phone = target_store.get("phone") or "उपलब्ध नाही"
                    full_addr = f"{addr}, {st_city}, {state} - {pin}" if pin else f"{addr}, {st_city}, {state}"
                    answer = (
                        f"🏪 **{st_name} शाखेची माहिती**\n\n"
                        f"• **पूर्ण पत्ता:** {full_addr}\n"
                        f"• **संपर्क फोन:** {phone}\n"
                        f"• **शाखा प्रकार:** {branch_type}\n"
                        f"• **कोड:** {target_store.get('code') or 'MAIN'}"
                    )
                    speech_text = f"{st_name} चा पूर्ण पत्ता {addr}, {st_city} असा असून फोन नंबर {phone} आहे."
                    return {"query": query_str, "intent": "admin_store_info", "answer": answer, "speech_text": speech_text, "data": {"store": target_store}, "suggested_actions": ["View store profile", "Check branch inventory"]}
            else:
                # Multiple stores in this location/city (e.g. Kolhapur has Main Store + Warehouse)
                city_name = matching_stores[0].get("city") or "या शहरात"
                lines = []
                for idx, s in enumerate(matching_stores, 1):
                    b_type = "सेंट्रल वेअरहाउस (Warehouse)" if s.get("is_warehouse") else ("मुख्य स्टोअर (Main Store)" if s.get("is_main") else "रिटेल शाखा")
                    addr = s.get("address") or "पत्ता उपलब्ध नाही"
                    phone = s.get("phone") or "उपलब्ध नाही"
                    lines.append(f"{idx}. **{s['name']}**\n   • **प्रकार:** {b_type}\n   • **पत्ता:** {addr}\n   • **फोन:** {phone}\n   • **कोड:** {s.get('code') or 'N/A'}")

                details_text = "\n\n".join(lines)
                answer = f"🏪 **{city_name} शाखेची माहिती (एकूण {len(matching_stores)} ठिकाणे):**\n\n{details_text}"
                speech_text = f"{city_name} येथे तुमच्याकडे {len(matching_stores)} शाखा असून त्यात {', '.join([s['name'] for s in matching_stores])} यांचा समावेश आहे."
                return {"query": query_str, "intent": "admin_store_info", "answer": answer, "speech_text": speech_text, "data": {"matching_stores": matching_stores}, "suggested_actions": ["View store profile", "Check branch inventory"]}

        # B. ALL STORES / BRANCHES LIST (e.g. 'माझ्याकडे किती दुकाने आहेत?', 'सर्व स्टोअर्सची यादी दाखव', 'इतर दुकानांची नावे सांग')
        if any(w in q_clean for w in ["सर्व दुकान", "सर्व स्टोअर", "किती दुकान", "किती स्टोअर", "सर्व शाखा", "स्टोअर्सची यादी", "stores list", "all stores", "दुकानांची यादी", "इतर दुकान", "इतर शाखा"]):
            intent = "store_list_info"
            lines = []
            for idx, s in enumerate(all_stores, 1):
                b_type = "गोदाम (Warehouse)" if s.get("is_warehouse") else ("मुख्य स्टोअर" if s.get("is_main") else "शाखा")
                lines.append(f"{idx}. **{s['name']}** ({s.get('city') or ''}) — {b_type} (फोन: {s.get('phone') or 'N/A'})")
            stores_text = "\n".join(lines) if lines else "कोणतेही स्टोअर नोंदणीकृत नाही."
            answer = (
                f"🏢 **तुमच्या एकूण स्टोअर्सची यादी (Total Branches: {len(all_stores)})**\n\n"
                f"{stores_text}\n\n"
                f"ℹ️ तुम्ही कोणत्याही शाखेचा पत्ता किंवा आजचा गल्ला जाणून घेण्यासाठी त्या शहराचे किंवा शाखेचे नाव विचारू शकता."
            )
            speech_text = f"तुमच्याकडे एकूण {len(all_stores)} स्टोअर्स असून त्यात सर्व शाखांची नोंद उपलब्ध आहे."
            return {"query": query_str, "intent": intent, "answer": answer, "speech_text": speech_text, "data": {"stores": all_stores}, "suggested_actions": ["Add new store", "Manage branches", "Inventory distribution"]}

        # C. SUPPLIERS QUERY (e.g. 'माझ्याकडे कोणते सप्लायर्स आहेत?', 'सप्लायरचे नाव काय?')
        if any(w in q_clean for w in ["सप्लायर", "supplier", "विक्रेता", "डिस्ट्रिब्युटर"]):
            supp_info = ctx.get("suppliers_details", {})
            supp_list = supp_info.get("suppliers_list", [])
            lines = [f"{idx}. **{s['name']}** (संपर्क: {s.get('contact_person') or 'N/A'}, फोन: {s.get('phone') or 'N/A'})" for idx, s in enumerate(supp_list, 1)]
            s_text = "\n".join(lines) if lines else "कोणताही सप्लायर नोंदणीकृत नाही."
            answer = f"🤝 **सप्लायर यादी (Total Suppliers: {len(supp_list)})**\n\n{s_text}"
            speech_text = f"तुमच्याकडे एकूण {len(supp_list)} सप्लायर्स नोंदणीकृत आहेत."
            return {"query": query_str, "intent": "supplier_info", "answer": answer, "speech_text": speech_text, "data": supp_info, "suggested_actions": ["Create purchase order", "Add new supplier"]}

        # D. STAFF / EMPLOYEES QUERY (e.g. 'माझ्याकडे किती कर्मचारी आहेत?', 'स्टाफची नावे काय?')
        if any(w in q_clean for w in ["कर्मचारी", "स्टाफ", "staff", "employee", "कामगार", "सेल्समन", "कॅशियर"]):
            staff_info = ctx.get("staff_details", {})
            members = staff_info.get("staff_members", [])
            lines = [f"{idx}. **{m['name']}** ({m.get('role') or 'Staff'}) — शाखा: {m.get('assigned_store_name') or 'सर्व'}" for idx, m in enumerate(members[:10], 1)]
            m_text = "\n".join(lines) if lines else "कोणताही कर्मचारी नोंदणीकृत नाही."
            tot_st = staff_info.get("total_staff_count", len(members))
            answer = f"👥 **कर्मचारी / स्टाफ यादी (Total Staff: {tot_st})**\n\n{m_text}"
            speech_text = f"तुमच्याकडे एकूण {tot_st} कर्मचारी कार्यरत आहेत."
            return {"query": query_str, "intent": "staff_info", "answer": answer, "speech_text": speech_text, "data": staff_info, "suggested_actions": ["Manage staff", "View attendance"]}

        # E. PRODUCTS / CATALOG / MOST EXPENSIVE PRODUCT (e.g. 'सर्वात महाग वस्तू कोणती?', 'माझ्याकडे किती प्रॉडक्ट्स आहेत?')
        if any(w in q_clean for w in ["महाग", "expensive", "स्वस्त", "cheapest", "प्रॉडक्ट", "वस्तू", "catalog", "आयटम"]):
            cat_data = ctx.get("catalog", {})
            most_exp = cat_data.get("most_expensive_product")
            cheapest = cat_data.get("cheapest_product")
            tot_p = cat_data.get("total_products_count", 0)

            if any(w in q_clean for w in ["महाग", "expensive"]):
                if most_exp:
                    answer = f"💎 **सर्वात महाग उत्पादन (Most Expensive Product):**\n\n• **नाव:** {most_exp['name']}\n• **विक्री किंमत:** ₹{most_exp['selling_price']:,.2f}"
                    speech_text = f"तुमच्या दुकानातील सर्वात महाग उत्पादन {most_exp['name']} असून त्याची किंमत {int(most_exp['selling_price'])} रुपये आहे."
                else:
                    answer = "उत्पादनांची माहिती उपलब्ध नाही."
                    speech_text = "उत्पादने उपलब्ध नाहीत."
                return {"query": query_str, "intent": "catalog_info", "answer": answer, "speech_text": speech_text, "data": cat_data, "suggested_actions": ["View catalog", "Update pricing"]}
            elif any(w in q_clean for w in ["स्वस्त", "cheapest"]):
                if cheapest:
                    answer = f"🏷️ **सर्वात स्वस्त उत्पादन (Cheapest Product):**\n\n• **नाव:** {cheapest['name']}\n• **विक्री किंमत:** ₹{cheapest['selling_price']:,.2f}"
                    speech_text = f"तुमच्या दुकानातील सर्वात स्वस्त उत्पादन {cheapest['name']} असून किंमत {int(cheapest['selling_price'])} रुपये आहे."
                else:
                    answer = "उत्पादनांची माहिती उपलब्ध नाही."
                    speech_text = "उत्पादने उपलब्ध नाहीत."
                return {"query": query_str, "intent": "catalog_info", "answer": answer, "speech_text": speech_text, "data": cat_data, "suggested_actions": ["View catalog"]}
            else:
                answer = f"📦 **उत्पादन कॅटलॉग माहिती (Total Products: {tot_p})**\n\nतुमच्याकडे एकूण {tot_p} सक्रिय उत्पादने आहेत."
                if most_exp:
                    answer += f"\n• **सर्वात महाग उत्पादन:** {most_exp['name']} (₹{most_exp['selling_price']:,.2f})"
                speech_text = f"तुमच्या दुकानात एकूण {tot_p} उत्पादने नोंदणीकृत आहेत."
                return {"query": query_str, "intent": "catalog_info", "answer": answer, "speech_text": speech_text, "data": cat_data, "suggested_actions": ["View catalog"]}

        # F. CATEGORIES
        if any(w in q_clean for w in ["कॅटेगरी", "प्रकार", "categories"]):
            cat_list = ctx.get("catalog", {}).get("categories", [])
            lines = [f"{idx}. **{c['name']}** ({c['product_count']} उत्पादने)" for idx, c in enumerate(cat_list, 1)]
            c_text = "\n".join(lines) if lines else "कोणतीही कॅटेगरी उपलब्ध नाही."
            answer = f"📂 **उत्पादन कॅटेगरी यादी (Total Categories: {len(cat_list)})**\n\n{c_text}"
            speech_text = f"तुमच्याकडे एकूण {len(cat_list)} कॅटेगरी उपलब्ध आहेत."
            return {"query": query_str, "intent": "categories_info", "answer": answer, "speech_text": speech_text, "data": {"categories": cat_list}, "suggested_actions": ["Manage categories"]}

        # 1. ADMIN, OWNER & STORE DETAILS (e.g. 'ॲडमिनचे नाव काय आहे?', 'दुकान आणि मालकाचे नाव सांगा', 'पूर्ण ॲड्रेस सांग')
        if any(w in q_clean for w in ["ॲडमिन", "एडमिन", "admin", "मालक", "owner"]) or (
            any(w in q_clean for w in ["नाव", "पत्ता", "ॲड्रेस", "address", "दुकान", "स्टोअर"]) and not any(w in q_clean for w in ["गल्ला", "सेल", "विक्री"])
        ):
            intent = "admin_store_info"
            store_name = ctx.get("store_info", {}).get("store_name", "Retail-OS Store")
            admin_name = ctx.get("admin_info", {}).get("admin_name", "मुख्य ॲडमिन")
            admin_email = ctx.get("admin_info", {}).get("admin_email", "")
            city = ctx.get("store_info", {}).get("city") or "महाराष्ट्र"
            addr = ctx.get("store_info", {}).get("address") or ""
            pin = ctx.get("store_info", {}).get("pincode") or ""
            phone = ctx.get("store_info", {}).get("phone") or ""

            full_addr_str = f"{addr}, {city}" + (f" - {pin}" if pin else "") if addr else city

            answer = (
                f"👤 **स्टोअर व ॲडमिन तपशील (Store & Admin Details)**\n\n"
                f"• **मुख्य स्टोअर:** {store_name}\n"
                f"• **मुख्य ॲडमिन / मालक:** {admin_name}\n"
                f"• **पूर्ण पत्ता:** {full_addr_str}\n"
            )
            if phone:
                answer += f"• **फोन:** {phone}\n"
            if admin_email:
                answer += f"• **ईमेल:** {admin_email}\n"

            speech_text = f"तुमच्या मुख्य स्टोअरचे नाव {store_name} असून पत्ता {full_addr_str} आहे आणि मालक {admin_name} आहेत."
            actions = ["View store profile", "Manage staff permissions", "Update store settings"]
            return {"query": query_str, "intent": intent, "answer": answer, "speech_text": speech_text, "data": {"store_info": ctx.get("store_info"), "admin_info": ctx.get("admin_info")}, "suggested_actions": actions}

        # 2. STOCK ALERTS / LOW STOCK (e.g. 'कमी स्टॉक अलर्ट?', 'कोणत्या वस्तूंचा स्टॉक संपत आला आहे?')
        elif (
            any(w in q_clean for w in ["स्टॉक", "stock", "माल", "inventory", "गोदाम", "शिल्लक"])
            and not any(w in q_clean for w in ["दिवाळी", "diwali", "festival", "सण"])
        ):
            low_cnt = ctx["low_stock_count"]
            out_cnt = ctx["out_of_stock_count"]
            intent = "stock_alerts"
            reorders = ctx.get("reorders", [])

            if low_cnt > 0 or out_cnt > 0:
                answer = (
                    f"📦 **स्टॉक अलर्ट अहवाल (Inventory Alerts)**\n\n"
                    f"सध्या दुकानात **{low_cnt} वस्तू** कमी स्टॉक लेव्हलवर आहेत, ज्यामध्ये **{out_cnt} वस्तूंचा स्टॉक पूर्णपणे संपलेला आहे**.\n\n"
                )
                if reorders:
                    answer += "तातडीने मागवावयाच्या वस्तू (Reorder Suggestions):\n"
                    for idx, r in enumerate(reorders[:3], 1):
                        answer += f"{idx}. **{r.get('product_name', 'उत्पादन')}** — सध्या शिल्लक: {r.get('current_stock', 0)}, शिफारस: {r.get('recommended_reorder_qty', 10)} नग\n"
                speech_text = f"लक्ष द्या, दुकानात सध्या {low_cnt} वस्तूंचा स्टॉक कमी झाला असून, {out_cnt} वस्तूंचा स्टॉक पूर्ण संपला आहे. कृपया तातडीने माल मागवून घ्या."
            else:
                answer = "✅ **सर्व स्टॉक उत्तम आहे!** दुकानात सध्या कोणतीही वस्तू कमी किंवा संपलेली नाही. सर्व इन्व्हेंटरी पुरेशी आहे."
                speech_text = "उत्कृष्ट! तुमच्या दुकानातील सर्व वस्तूंचा स्टॉक पुरेसा असून कोणतीही वस्तू कमी नाही."

            data = {"low_stock_count": low_cnt, "out_of_stock_count": out_cnt, "reorders": reorders}
            actions = ["Open reorder prediction", "Create purchase order", "Check supplier catalog"]
            return {"query": query_str, "intent": intent, "answer": answer, "speech_text": speech_text, "data": data, "suggested_actions": actions}

        # 3. TODAY'S SALES & GALLA (e.g. 'आजचा एकूण गल्ला किती झाला?', 'आजची विक्री किती आहे?')
        elif (
            "गल्ला" in q_clean
            or ("आज" in q_clean and any(w in q_clean for w in ["विक्री", "सेल", "कमाई", "कलेक्शन", "टर्नओव्हर", "sale", "turnover"]))
            or (any(w in q_clean for w in ["today", "aaj"]) and any(w in q_clean for w in ["sale", "revenue", "collection", "turnover", "income"]))
        ):
            tot = ctx["sales_today"]["revenue"]
            cnt = ctx["sales_today"]["orders"]
            intent = "today_sales"
            answer = (
                f"💸 **आजचा गल्ला व विक्री अहवाल (Today's Sales)**\n\n"
                f"आजचा एकूण गल्ला: **₹{tot:,.2f}**\n"
                f"एकूण पूर्ण झालेल्या ऑर्डर्स: **{cnt} ऑर्डर्स**\n\n"
                f"तारीख: {today_start.strftime('%d %B %Y')}"
            )
            speech_text = f"आजचा एकूण गल्ला {int(tot)} रुपये झाला असून एकूण {cnt} ऑर्डर्स पूर्ण झाल्या आहेत."
            data = {"sales_amount": tot, "order_count": cnt, "date": today_start.strftime("%Y-%m-%d")}
            actions = ["View daily sales report", "Check cashier drawer closing status", "View active shifts"]
            return {"query": query_str, "intent": intent, "answer": answer, "speech_text": speech_text, "data": data, "suggested_actions": actions}

        # 4. CUSTOMER CREDIT / KHATA (e.g. 'उधारी बाकी खातेदार?', '१००० रुपयांपेक्षा जास्त उधारी बाकी कोणाची आहे?')
        elif any(w in q_clean for w in ["उधारी", "khata", "credit", "खातेदार", "बाकी", "थकीत", "उधार", "remind", "रिमाइंडर"]):
            intent = "credit_khata_reminders"
            over_1000 = ctx.get("credit_over_1000", [])
            all_credit = ctx.get("credit_customers", [])
            total_pending = sum(c["outstanding_balance"] for c in all_credit)

            if all_credit:
                cust_lines = []
                for idx, c in enumerate(all_credit[:5], 1):
                    cust_lines.append(f"{idx}. **{c['name']}** — थकीत: ₹{c['outstanding_balance']:,.2f} (फोन: {c['phone']})")
                cust_str = "\n".join(cust_lines)
                answer = (
                    f"📋 **उधारी खातेदार अहवाल (Customer Credit Ledger)**\n\n"
                    f"तुमच्या दुकानात एकूण **{len(all_credit)} ग्राहकांकडे** उधारी बाकी आहे.\n"
                    f"एकूण थकीत येणेबाकी: **₹{total_pending:,.2f}**\n\n"
                    f"प्रमुख खातेदार ग्राहक:\n"
                    f"{cust_str}\n\n"
                    f"📲 तुम्ही ग्राहकांना व्हॉट्सॲपवर पेमेंट रिमाइंडर व UPI लिंक पाठवू शकता."
                )
                speech_text = f"दुकानात एकूण {len(all_credit)} ग्राहकांकडे एकूण {int(total_pending)} रुपयांची उधारी बाकी आहे."
                data = {"credit_customers": all_credit[:5], "total_outstanding": total_pending, "credit_over_1000": over_1000}
            else:
                answer = "🎉 **उत्कृष्ट!** दुकानात सध्या कोणत्याही ग्राहकाकडे उधारी शिल्लक नाही. सर्व खाती क्लिअर आहेत."
                speech_text = "उत्कृष्ट! तुमच्या दुकानात सध्या कोणाकडेही उधारी बाकी नाही."
                data = {"credit_customers": [], "total_outstanding": 0}

            actions = ["Send WhatsApp payment reminders to all", "View customer credit ledger", "Set customer credit limits"]
            return {"query": query_str, "intent": intent, "answer": answer, "speech_text": speech_text, "data": data, "suggested_actions": actions}

        # 5. FESTIVAL / DIWALI STOCKING PREDICTIONS
        elif any(w in q_clean for w in ["दिवाळी", "diwali", "festival", "सण", "जास्त स्टॉक", "stock जास्त", "फेस्टिव्हल", "तयारी"]):
            intent = "festival_reorder_recommendation"
            top_prods = ctx.get("top_products", [])
            catalog_prods = ctx.get("catalog", {}).get("top_products_catalog", [])

            rec_list = []
            if top_prods:
                for idx, p in enumerate(top_prods[:5], 1):
                    sold = p.get("quantity_sold", 0)
                    rec_buffer = max(10, int(sold * 1.5)) if sold else 10
                    rec_list.append(f"{idx}. **{p['product_name']}** — अपेक्षित मागणी: {rec_buffer} युनिट्स")
            elif catalog_prods:
                for idx, p in enumerate(catalog_prods[:5], 1):
                    rec_list.append(f"{idx}. **{p['name']}** — सणासुदीच्या काळात अतिरिक्त २५% स्टॉक ठेवण्याची शिफारस")

            if rec_list:
                rec_text = "\n".join(rec_list)
                answer = (
                    f"🪔 **सण व विशेष मागणी स्टॉक शिफारस (Festival Reorder Advisory)**\n\n"
                    f"सणासुदीच्या काळात मागणी वाढण्याची शक्यता लक्षात घेता तुमच्या डेटाबेसमधील खालील उत्पादनांचा जास्तीचा स्टॉक ठेवण्याची शिफारस केली जाते:\n\n"
                    f"{rec_text}\n\n"
                    f"📦 **सल्ला:** स्टॉक तुटवडा टाळण्यासाठी सप्लायर्सकडे वेळेत परचेस ऑर्डर (PO) नोंदवा."
                )
                speech_text = "सणांसाठी तुमच्या दुकानातील उत्पादनांचा जास्तीचा स्टॉक मागवून ठेवण्याची शिफारस केली जाते."
            else:
                answer = "सध्या सणांसाठी शिफारस करण्यासाठी डेटाबेसमध्ये उत्पादने उपलब्ध नाहीत."
                speech_text = "सध्या उत्पादने उपलब्ध नाहीत."

            actions = ["Generate bulk purchase orders", "Contact suppliers", "Review inventory levels"]
            data = {"recommended_festive_items": top_prods[:5] if top_prods else catalog_prods[:5]}
            return {"query": query_str, "intent": intent, "answer": answer, "speech_text": speech_text, "data": data, "suggested_actions": actions}

        # 6. CATEGORY COMPARISON / DROP ANALYSIS
        elif any(w in q_clean for w in ["कॅटेगरी", "category"]) and any(w in q_clean for w in ["drop", "घट", "विक्री कमी", "sale down", "sales drop", "decreased", "कमी", "तुलना"]):
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
                speech_text = f"मागच्या आठवड्याच्या तुलनेत काही कॅटेगरींच्या विक्रीमध्ये घट झाली आहे. कृपया त्यांचा स्टॉक आणि ऑफर्स तपासा."
                data = {"dropped_categories": cat_drops, "all_categories": ctx["category_comparison"]}
            else:
                answer = (
                    "मागच्या आठवड्याशी तुलना करता सर्व कॅटेगरींची विक्री समाधानकारक व स्थिर आहे. "
                    "कोणत्याही मुख्य कॅटेगरीत लक्षणीय घट नोंदवली गेलेली नाही."
                )
                speech_text = "सर्व कॅटेगरींची विक्री स्थिर असून कोणत्याही मुख्य कॅटेगरीत विक्री घटलेली नाही."
                data = {"category_comparison": ctx["category_comparison"]}
            actions = ["Check category inventory", "Create promotional discount coupon", "Review supplier purchase orders"]
            return {"query": query_str, "intent": intent, "answer": answer, "speech_text": speech_text, "data": data, "suggested_actions": actions}

        # 7. MONTHLY SALES
        elif any(w in q_clean for w in ["महिना", "महिन्याची", "month", "monthly", "this month"]):
            tot = ctx["sales_this_month"]["revenue"]
            cnt = ctx["sales_this_month"]["orders"]
            intent = "monthly_sales"
            answer = (
                f"📅 **चालू महिन्याचा विक्री अहवाल (Monthly Sales)**\n\n"
                f"या महिन्याची एकूण विक्री: **₹{tot:,.2f}**\n"
                f"एकूण पूर्ण ऑर्डर्स: **{cnt} ऑर्डर्स**\n"
                f"महिना: {month_start.strftime('%B %Y')}"
            )
            speech_text = f"या महिन्यात आतापर्यंत एकूण {int(tot)} रुपयांची विक्री झाली असून {cnt} ऑर्डर्स पूर्ण झाल्या आहेत."
            data = {"month": month_start.strftime("%B %Y"), "revenue": tot, "orders": cnt}
            actions = ["View monthly P&L", "Export tax report", "Check best sellers"]
            return {"query": query_str, "intent": intent, "answer": answer, "speech_text": speech_text, "data": data, "suggested_actions": actions}

        # 8. BEST SELLERS
        elif any(w in q_clean for w in ["बेस्ट सेलर", "जास्त खप", "विकला", "टॉप प्रॉडक्ट", "लोकप्रिय", "best seller", "top product", "most sold", "popular"]):
            top = ctx["top_products"][:3]
            intent = "best_sellers"
            if top:
                names = ", ".join([f"**{p['product_name']}** ({p['quantity_sold']} नग)" for p in top])
                answer = f"🏆 **सर्वाधिक विक्री होणारी उत्पादने (Best Sellers):**\n\n{names}"
                speech_text = f"तुमच्या दुकानात सर्वाधिक विकली जाणारी उत्पादने {', '.join([p['product_name'] for p in top])} ही आहेत."
                data = {"top_products": top}
            else:
                answer = "सध्या बेस्ट सेलर निश्चित करण्यासाठी विक्री डेटा उपलब्ध नाही."
                speech_text = "सध्या सर्वाधिक विकल्या जाणाऱ्या वस्तूंचा डेटा उपलब्ध नाही."
                data = {}
            actions = ["View inventory for top sellers", "Generate purchase orders", "Create promotional bundle"]
            return {"query": query_str, "intent": intent, "answer": answer, "speech_text": speech_text, "data": data, "suggested_actions": actions}

        # 9. CUSTOMER STATS
        elif any(w in q_clean for w in ["ग्राहक", "कस्टमर", "customer", "clients", "members"]):
            cust_cnt = ctx["total_customers"]
            intent = "customer_stats"
            answer = f"👥 तुमच्या दुकानात सध्या एकूण **{cust_cnt} नोंदणीकृत ग्राहक** आहेत."
            speech_text = f"तुमच्या दुकानात एकूण {cust_cnt} ग्राहक नोंदणीकृत आहेत."
            data = {"total_customers": cust_cnt}
            actions = ["View customer churn risk", "Launch promotional offer campaign", "Send loyalty points update"]
            return {"query": query_str, "intent": intent, "answer": answer, "speech_text": speech_text, "data": data, "suggested_actions": actions}

        # 10. GENERAL SUMMARY & GUIDANCE
        else:
            intent = "general_summary"
            answer = (
                "🤖 **नमस्कार! मी Retail-OS AI व्हॉईस असिस्टंट (स्मार्ट सल्लागार) आहे.**\n\n"
                "मी तुमच्या दुकानाचा थेट डेटा तपासून अचूक उत्तरे देतो. तुम्ही मला पुढील प्रश्न विचारू शकता:\n"
                "• **आजचा एकूण गल्ला किती झाला?**\n"
                "• **कमी स्टॉक अलर्ट किंवा कोणता माल संपला आहे?**\n"
                "• **उधारी बाकी खातेदारांची यादी दाखवा.**\n"
                "• **ॲडमिन किंवा दुकानाचे नाव काय आहे?**\n"
                "• **दिवाळीसाठी कोणत्या वस्तूंचा स्टॉक जास्त लागेल?**"
            )
            speech_text = "नमस्कार! मी तुमचा रिटेल असिस्टंट आहे. तुम्ही मला आजचा गल्ला, कमी स्टॉक, उधारी किंवा ॲडमिनचे नाव याबद्दल प्रश्न विचारू शकता."
            actions = ["Check today's sales", "Check low stock alerts", "View top selling products", "Customer credit analysis"]
            return {"query": query_str, "intent": intent, "answer": answer, "speech_text": speech_text, "data": {}, "suggested_actions": actions}

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
                if "speech_text" not in ai_res or not ai_res["speech_text"]:
                    ai_res["speech_text"] = self._clean_for_speech(ai_res.get("answer", ""))
                return ai_res

        # Fallback to enhanced multilingual deterministic engine
        res = self._rule_based_chat_query(tenant_id, query_str, store_id, context)
        if "speech_text" not in res or not res["speech_text"]:
            res["speech_text"] = self._clean_for_speech(res.get("answer", ""))
        return res

    def voice_query(
        self,
        tenant_id: int,
        query_str: Optional[str] = None,
        audio_base64: Optional[str] = None,
        audio_mime_type: Optional[str] = "audio/webm",
        store_id: Optional[int] = None,
        language: Optional[str] = "mr-IN",
    ) -> dict:
        """
        Voice AI Copilot: accepts either recognized speech text or raw base64 audio recorded
        from the microphone, executes business intelligence reasoning with Gemini 1.5 Flash,
        and returns both rich visual answer and clean, natural spoken speech_text.
        """
        context = self._get_copilot_context(tenant_id, store_id)

        # 1. Direct Multimodal Audio Input via Gemini (if raw audio bytes provided)
        if audio_base64:
            audio_res = self._call_gemini_audio_copilot(
                audio_base64=audio_base64,
                mime_type=audio_mime_type or "audio/webm",
                context=context,
                language=language or "mr-IN",
            )
            if audio_res:
                audio_res["language"] = language or "mr-IN"
                if not audio_res.get("query"):
                    audio_res["query"] = audio_res.get("transcription") or "Voice query"
                return audio_res

        # 2. Text-based query from browser SpeechRecognition or fallback
        effective_query = (query_str or "").strip()
        if not effective_query:
            effective_query = "आजचा एकूण गल्ला किती झाला?"

        base_res = self.chat_query(tenant_id, effective_query, store_id=store_id)
        speech_text = base_res.get("speech_text")
        if not speech_text:
            speech_text = self._clean_for_speech(base_res.get("answer", ""))

        base_res["speech_text"] = speech_text
        detected_lang = language or ("mr-IN" if any(0x0900 <= ord(c) <= 0x097F for c in effective_query) else "en-IN")
        base_res["language"] = detected_lang
        return base_res
