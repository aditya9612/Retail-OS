from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundException
from app.models.category import Category
from app.models.customer import Customer
from app.models.inventory import Inventory
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product import Product
from app.models.purchase_order import PurchaseOrder, PurchaseOrderItem
from app.utils.constants import OrderStatus


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

    def chat_query(self, tenant_id: int, query_str: str, store_id: Optional[int] = None) -> dict:
        """
        AI Natural Language Retail Assistant: interprets questions about sales,
        inventory, products, and customers to provide instant live insights.
        """
        q_clean = query_str.lower().strip()
        now = datetime.utcnow()
        today_start = datetime(now.year, now.month, now.day)
        actions = []
        data = {}

        if any(w in q_clean for w in ["today", "aaj"]) and any(w in q_clean for w in ["sale", "revenue", "collection", "turnover", "income"]):
            sales_q = (
                self.db.query(
                    func.coalesce(func.sum(Order.total_amount), 0),
                    func.count(Order.id),
                )
                .filter(
                    Order.tenant_id == tenant_id,
                    Order.status.in_([OrderStatus.CONFIRMED.value, OrderStatus.DELIVERED.value]),
                    Order.created_at >= today_start,
                )
            )
            if store_id is not None:
                sales_q = sales_q.filter(Order.store_id == store_id)
            row = sales_q.first()
            total_rev = round(float(row[0]), 2)
            orders_cnt = int(row[1])
            intent = "today_sales"
            answer = f"Today's total sales are ₹{total_rev:,.2f} across {orders_cnt} completed orders."
            data = {"sales_amount": total_rev, "order_count": orders_cnt, "date": today_start.strftime("%Y-%m-%d")}
            actions = ["View daily sales report", "Check cashier drawer closing status", "View active shifts"]

        elif any(w in q_clean for w in ["month", "monthly", "this month"]):
            month_start = datetime(now.year, now.month, 1)
            sales_q = (
                self.db.query(
                    func.coalesce(func.sum(Order.total_amount), 0),
                    func.count(Order.id),
                )
                .filter(
                    Order.tenant_id == tenant_id,
                    Order.status.in_([OrderStatus.CONFIRMED.value, OrderStatus.DELIVERED.value]),
                    Order.created_at >= month_start,
                )
            )
            if store_id is not None:
                sales_q = sales_q.filter(Order.store_id == store_id)
            row = sales_q.first()
            total_rev = round(float(row[0]), 2)
            orders_cnt = int(row[1])
            intent = "monthly_sales"
            answer = f"This month's revenue is ₹{total_rev:,.2f} from {orders_cnt} orders."
            data = {"month": month_start.strftime("%B %Y"), "revenue": total_rev, "orders": orders_cnt}
            actions = ["View monthly P&L", "Export tax report", "Check best sellers"]

        elif any(w in q_clean for w in ["best seller", "top product", "most sold", "popular"]):
            top = self.best_selling_products(tenant_id, limit=3, store_id=store_id)
            intent = "best_sellers"
            if top:
                names = ", ".join([f"'{p['product_name']}' ({p['quantity_sold']} units)" for p in top])
                answer = f"Your top selling products are: {names}."
                data = {"top_products": top}
            else:
                answer = "No sales recorded yet to determine best sellers."
            actions = ["View inventory for top sellers", "Generate purchase orders", "Create promotional bundle"]

        elif any(w in q_clean for w in ["stock", "out of stock", "low stock", "inventory"]):
            low_q = (
                self.db.query(func.count(Inventory.id))
                .filter(Inventory.tenant_id == tenant_id, Inventory.quantity <= Inventory.min_stock_level)
            )
            out_q = (
                self.db.query(func.count(Inventory.id))
                .filter(Inventory.tenant_id == tenant_id, Inventory.quantity <= 0)
            )
            if store_id is not None:
                low_q = low_q.filter(Inventory.store_id == store_id)
                out_q = out_q.filter(Inventory.store_id == store_id)
            low_cnt = low_q.scalar() or 0
            out_cnt = out_q.scalar() or 0
            intent = "stock_alerts"
            answer = f"You have {low_cnt} items running below minimum stock level, including {out_cnt} completely out of stock."
            data = {"low_stock_count": low_cnt, "out_of_stock_count": out_cnt}
            actions = ["Open reorder prediction", "Create purchase order", "Check supplier catalog"]

        elif any(w in q_clean for w in ["customer", "clients", "members"]):
            cust_cnt = self.db.query(func.count(Customer.id)).filter(Customer.tenant_id == tenant_id).scalar() or 0
            intent = "customer_stats"
            answer = f"Your store has {cust_cnt} registered customers."
            data = {"total_customers": cust_cnt}
            actions = ["View customer churn risk", "Launch promotional offer campaign", "Send loyalty points update"]

        else:
            intent = "general_summary"
            answer = (
                "I am Retail-OS AI Assistant. I can help you with sales figures, inventory alerts, best sellers, "
                "customer insights, and reorders. Try asking: 'What are today's sales?', 'Show best sellers', "
                "'How many items are low on stock?', or 'Which customers are at churn risk?'"
            )
            actions = ["Check today's sales", "Check low stock alerts", "View top selling products", "Customer churn analysis"]

        return {
            "query": query_str,
            "intent": intent,
            "answer": answer,
            "data": data,
            "suggested_actions": actions,
        }
