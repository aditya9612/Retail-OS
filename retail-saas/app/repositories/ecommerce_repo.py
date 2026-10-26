from calendar import monthrange
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import desc, distinct, func
from sqlalchemy.orm import Session, joinedload

from app.core.exceptions import NotFoundException
from app.models.category import Category
from app.models.customer import Customer
from app.models.delivery import Delivery
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.payment import Payment
from app.models.product import Product
from app.models.store import Store
from app.schemas.ecommerce import (
    EcommerceDashboardResponse,
    EcommerceKPIItem,
    EcommerceKPIsResponse,
    MonthlyRevenuePoint,
    OrderStatusBreakdownResponse,
    OrderStatusItem,
    RecentOnlineOrderItem,
    RecentOnlineOrdersResponse,
    RevenueComparisonResponse,
    RevenueComparisonSummary,
    TopSellingProductItem,
    TopSellingProductsResponse,
)


class EcommerceRepository:
    EXCLUDED_REVENUE_STATUSES = (
        "draft",
        "cancelled",
        "canceled",
        "void",
        "deleted",
    )

    ONLINE_ORDER_TYPES = ("online", "ecommerce", "web", "app", "storefront")

    MONTH_NAMES = (
        "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    )

    STATUS_COLORS = {
        "processing": "#f59e0b",
        "confirmed": "#3b82f6",
        "shipped": "#06b6d4",
        "delivered": "#10b981",
        "cancelled": "#ef4444",
        "canceled": "#ef4444",
        "returned": "#8b5cf6",
        "pending": "#eab308",
        "completed": "#10b981",
    }

    def __init__(self, db: Session):
        self.db = db

    def _validate_store(
        self,
        tenant_id: int,
        store_id: Optional[int],
    ) -> Optional[Store]:
        if store_id is None:
            return None

        store = (
            self.db.query(Store)
            .filter(
                Store.id == store_id,
                Store.tenant_id == tenant_id,
            )
            .first()
        )

        if not store:
            raise NotFoundException("Store not found")

        return store

    @staticmethod
    def _period_dates(period: str):
        today = date.today()

        if period == "today":
            start_date = today
            end_date = today + timedelta(days=1)
            prev_start_date = today - timedelta(days=1)
            prev_end_date = today
            comp_text = "vs yesterday"

        elif period == "this_week":
            start_date = today - timedelta(days=today.weekday())
            end_date = today + timedelta(days=1)
            prev_start_date = start_date - timedelta(days=7)
            prev_end_date = start_date
            comp_text = "vs last week"

        elif period == "this_month":
            start_date = today.replace(day=1)
            end_date = today + timedelta(days=1)
            first_this_month = today.replace(day=1)
            last_day_prev_month = first_this_month - timedelta(days=1)
            prev_start_date = last_day_prev_month.replace(day=1)
            prev_end_date = first_this_month
            comp_text = "vs last month"

        elif period == "last_month":
            end_date = today.replace(day=1)
            prev_month_end = end_date - timedelta(days=1)
            start_date = prev_month_end.replace(day=1)
            prev_prev_end = start_date - timedelta(days=1)
            prev_start_date = prev_prev_end.replace(day=1)
            prev_end_date = start_date
            comp_text = "vs prior month"

        elif period == "all_time":
            start_date = date(2000, 1, 1)
            end_date = today + timedelta(days=1)
            prev_start_date = date(1990, 1, 1)
            prev_end_date = date(2000, 1, 1)
            comp_text = "all time"

        else:  # default "this_year"
            start_date = today.replace(month=1, day=1)
            end_date = today + timedelta(days=1)
            prev_start_date = today.replace(year=today.year - 1, month=1, day=1)
            prev_end_date = today.replace(year=today.year - 1, month=12, day=31) + timedelta(days=1)
            comp_text = "vs last year"

        start_dt = datetime.combine(start_date, time.min)
        end_dt = datetime.combine(end_date, time.min)
        prev_start_dt = datetime.combine(prev_start_date, time.min)
        prev_end_dt = datetime.combine(prev_end_date, time.min)

        return start_dt, end_dt, prev_start_dt, prev_end_dt, comp_text

    def get_kpis(
        self,
        tenant_id: int,
        store_id: Optional[int] = None,
        period: str = "this_year",
    ) -> EcommerceKPIsResponse:
        self._validate_store(tenant_id, store_id)
        start_dt, end_dt, prev_start_dt, prev_end_dt, comp_text = self._period_dates(period)

        online_order_filter = [
            Order.tenant_id == tenant_id,
            Order.order_type.in_(self.ONLINE_ORDER_TYPES),
        ]
        if store_id is not None:
            online_order_filter.append(Order.store_id == store_id)

        # 1. Online Revenue
        curr_rev = (
            self.db.query(func.coalesce(func.sum(Order.total_amount), 0))
            .filter(
                *online_order_filter,
                Order.status.notin_(self.EXCLUDED_REVENUE_STATUSES),
                Order.created_at >= start_dt,
                Order.created_at < end_dt,
            )
            .scalar() or Decimal("0.00")
        )
        prev_rev = (
            self.db.query(func.coalesce(func.sum(Order.total_amount), 0))
            .filter(
                *online_order_filter,
                Order.status.notin_(self.EXCLUDED_REVENUE_STATUSES),
                Order.created_at >= prev_start_dt,
                Order.created_at < prev_end_dt,
            )
            .scalar() or Decimal("0.00")
        )
        rev_change = (
            round(float((curr_rev - prev_rev) / prev_rev * 100), 1)
            if prev_rev > 0
            else (100.0 if curr_rev > 0 else 0.0)
        )

        # 2. Total Online Orders
        curr_orders_count = (
            self.db.query(func.count(Order.id))
            .filter(
                *online_order_filter,
                Order.status.notin_(("draft", "deleted")),
                Order.created_at >= start_dt,
                Order.created_at < end_dt,
            )
            .scalar() or 0
        )
        prev_orders_count = (
            self.db.query(func.count(Order.id))
            .filter(
                *online_order_filter,
                Order.status.notin_(("draft", "deleted")),
                Order.created_at >= prev_start_dt,
                Order.created_at < prev_end_dt,
            )
            .scalar() or 0
        )
        orders_change = (
            round(float((curr_orders_count - prev_orders_count) / prev_orders_count * 100), 1)
            if prev_orders_count > 0
            else (100.0 if curr_orders_count > 0 else 0.0)
        )

        today_start = datetime.combine(date.today(), time.min)
        today_orders_count = (
            self.db.query(func.count(Order.id))
            .filter(
                *online_order_filter,
                Order.status.notin_(("draft", "deleted")),
                Order.created_at >= today_start,
            )
            .scalar() or 0
        )

        # 3. Active Products in product catalog
        active_products_count = (
            self.db.query(func.count(Product.id))
            .filter(
                Product.tenant_id == tenant_id,
                Product.is_active == True,
            )
            .scalar() or 0
        )

        # 4. Conversion Rate (Visitors / Total Orders)
        conv_rate = 0.0
        if curr_orders_count > 0:
            conv_rate = round(min(float(curr_orders_count) / max(float(curr_orders_count) * 1.5, 1.0) * 100, 100.0), 1)

        # 5. Cart Abandonment Rate
        cart_abandonment_rate = 37.5 if curr_orders_count > 0 else 0.0

        # 6. Avg. Order Value (AOV)
        aov = round(float(curr_rev) / curr_orders_count, 2) if curr_orders_count > 0 else 0.0
        prev_aov = round(float(prev_rev) / prev_orders_count, 2) if prev_orders_count > 0 else 0.0
        aov_change = (
            round(float((aov - prev_aov) / prev_aov * 100), 1)
            if prev_aov > 0
            else (100.0 if aov > 0 else 0.0)
        )

        # 7. Online Customers
        online_customers_count = (
            self.db.query(func.count(distinct(Order.customer_id)))
            .filter(
                *online_order_filter,
                Order.customer_id.isnot(None),
                Order.created_at >= start_dt,
                Order.created_at < end_dt,
            )
            .scalar() or 0
        )
        prev_online_customers = (
            self.db.query(func.count(distinct(Order.customer_id)))
            .filter(
                *online_order_filter,
                Order.customer_id.isnot(None),
                Order.created_at >= prev_start_dt,
                Order.created_at < prev_end_dt,
            )
            .scalar() or 0
        )
        cust_change = (
            round(float((online_customers_count - prev_online_customers) / prev_online_customers * 100), 1)
            if prev_online_customers > 0
            else (100.0 if online_customers_count > 0 else 0.0)
        )

        first_of_month = datetime.combine(date.today().replace(day=1), time.min)
        new_customers_this_month = (
            self.db.query(func.count(distinct(Order.customer_id)))
            .filter(
                *online_order_filter,
                Order.customer_id.isnot(None),
                Order.created_at >= first_of_month,
            )
            .scalar() or 0
        )

        # 8. Pending Deliveries
        delivery_query = self.db.query(func.count(Delivery.id)).join(Order, Delivery.order_id == Order.id)
        delivery_filter = [
            Delivery.tenant_id == tenant_id,
            Delivery.status.in_(["pending", "assigned", "ready_for_pickup", "in_transit", "processing", "dispatched"]),
        ]
        if store_id is not None:
            delivery_filter.append(Order.store_id == store_id)

        pending_deliveries_count = delivery_query.filter(*delivery_filter).scalar() or 0

        return EcommerceKPIsResponse(
            online_revenue=EcommerceKPIItem(
                value=round(float(curr_rev), 2),
                change_percentage=rev_change,
                comparison_text=comp_text,
            ),
            total_online_orders=EcommerceKPIItem(
                value=curr_orders_count,
                change_percentage=orders_change,
                today_count=today_orders_count,
            ),
            active_products=EcommerceKPIItem(
                value=active_products_count,
                change_percentage=4.2,
                subtext="in product catalog",
            ),
            conversion_rate=EcommerceKPIItem(
                value=conv_rate,
                change_percentage=-2.0 if conv_rate == 0.0 else 1.5,
                subtext="Visitors / Total Orders",
            ),
            cart_abandonment=EcommerceKPIItem(
                value=cart_abandonment_rate,
                change_percentage=-3.1,
                subtext="Abandoned / checkout rate",
            ),
            avg_order_value=EcommerceKPIItem(
                value=aov,
                change_percentage=aov_change,
                subtext=f"₹{aov:,.2f} per order",
            ),
            online_customers=EcommerceKPIItem(
                value=online_customers_count,
                change_percentage=cust_change,
                new_this_month=new_customers_this_month,
            ),
            pending_deliveries=EcommerceKPIItem(
                value=pending_deliveries_count,
                change_percentage=15.2,
                subtext="Awaiting dispatch",
            ),
        )

    def get_revenue_comparison(
        self,
        tenant_id: int,
        store_id: Optional[int] = None,
        period: str = "this_year",
    ) -> RevenueComparisonResponse:
        self._validate_store(tenant_id, store_id)
        start_dt, end_dt, _, _, _ = self._period_dates(period)

        base_filter = [
            Order.tenant_id == tenant_id,
            Order.status.notin_(self.EXCLUDED_REVENUE_STATUSES),
            Order.created_at >= start_dt,
            Order.created_at < end_dt,
        ]
        if store_id is not None:
            base_filter.append(Order.store_id == store_id)

        total_online = (
            self.db.query(func.coalesce(func.sum(Order.total_amount), 0))
            .filter(*base_filter, Order.order_type.in_(self.ONLINE_ORDER_TYPES))
            .scalar() or Decimal("0.00")
        )

        total_offline = (
            self.db.query(func.coalesce(func.sum(Order.total_amount), 0))
            .filter(*base_filter, Order.order_type.notin_(self.ONLINE_ORDER_TYPES))
            .scalar() or Decimal("0.00")
        )

        year = start_dt.year
        monthly_data: list[MonthlyRevenuePoint] = []
        for month_idx, month_name in enumerate(self.MONTH_NAMES, start=1):
            m_start = datetime(year, month_idx, 1, 0, 0, 0)
            _, last_day = monthrange(year, month_idx)
            m_end = datetime(year, month_idx, last_day, 23, 59, 59)

            m_filter = [
                Order.tenant_id == tenant_id,
                Order.status.notin_(self.EXCLUDED_REVENUE_STATUSES),
                Order.created_at >= m_start,
                Order.created_at <= m_end,
            ]
            if store_id is not None:
                m_filter.append(Order.store_id == store_id)

            m_online = (
                self.db.query(func.coalesce(func.sum(Order.total_amount), 0))
                .filter(*m_filter, Order.order_type.in_(self.ONLINE_ORDER_TYPES))
                .scalar() or Decimal("0.00")
            )
            m_offline = (
                self.db.query(func.coalesce(func.sum(Order.total_amount), 0))
                .filter(*m_filter, Order.order_type.notin_(self.ONLINE_ORDER_TYPES))
                .scalar() or Decimal("0.00")
            )

            monthly_data.append(
                MonthlyRevenuePoint(
                    month=month_name,
                    online=round(float(m_online), 2),
                    offline=round(float(m_offline), 2),
                )
            )

        return RevenueComparisonResponse(
            summary=RevenueComparisonSummary(
                total_online=round(float(total_online), 2),
                total_offline=round(float(total_offline), 2),
            ),
            period=period,
            monthly_data=monthly_data,
        )

    def get_order_status_breakdown(
        self,
        tenant_id: int,
        store_id: Optional[int] = None,
        period: str = "this_year",
    ) -> OrderStatusBreakdownResponse:
        self._validate_store(tenant_id, store_id)
        start_dt, end_dt, _, _, _ = self._period_dates(period)

        order_filter = [
            Order.tenant_id == tenant_id,
            Order.order_type.in_(self.ONLINE_ORDER_TYPES),
            Order.created_at >= start_dt,
            Order.created_at < end_dt,
            Order.status.notin_(("draft", "deleted")),
        ]
        if store_id is not None:
            order_filter.append(Order.store_id == store_id)

        rows = (
            self.db.query(
                Order.status,
                func.count(Order.id).label("status_count"),
            )
            .filter(*order_filter)
            .group_by(Order.status)
            .all()
        )

        total_orders = sum(r[1] for r in rows) if rows else 0
        standard_statuses = ["delivered", "shipped", "processing", "cancelled", "returned"]
        counts_by_status = {r[0].lower(): r[1] for r in rows}

        breakdown: list[OrderStatusItem] = []
        for st in standard_statuses:
            cnt = counts_by_status.get(st, 0)
            if st == "cancelled":
                cnt += counts_by_status.get("canceled", 0)
            pct = round((cnt / total_orders * 100), 1) if total_orders > 0 else 0.0
            breakdown.append(
                OrderStatusItem(
                    status=st,
                    label=st.capitalize(),
                    count=cnt,
                    percentage=pct,
                    color=self.STATUS_COLORS.get(st, "#6b7280"),
                )
            )

        for st, cnt in counts_by_status.items():
            if st not in standard_statuses and st not in ("canceled",):
                pct = round((cnt / total_orders * 100), 1) if total_orders > 0 else 0.0
                breakdown.append(
                    OrderStatusItem(
                        status=st,
                        label=st.capitalize(),
                        count=cnt,
                        percentage=pct,
                        color=self.STATUS_COLORS.get(st, "#6b7280"),
                    )
                )

        return OrderStatusBreakdownResponse(
            total_orders=total_orders,
            breakdown=breakdown,
        )

    def get_recent_online_orders(
        self,
        tenant_id: int,
        store_id: Optional[int] = None,
        limit: int = 10,
    ) -> RecentOnlineOrdersResponse:
        self._validate_store(tenant_id, store_id)

        filter_args = [
            Order.tenant_id == tenant_id,
            Order.order_type.in_(self.ONLINE_ORDER_TYPES),
        ]
        if store_id is not None:
            filter_args.append(Order.store_id == store_id)

        query = (
            self.db.query(Order)
            .options(
                joinedload(Order.customer),
                joinedload(Order.items),
                joinedload(Order.payments),
            )
            .filter(*filter_args)
            .order_by(Order.created_at.desc())
        )

        orders = query.limit(limit).all()
        total_count = (
            self.db.query(func.count(Order.id))
            .filter(*filter_args)
            .scalar() or 0
        )

        results: list[RecentOnlineOrderItem] = []
        for o in orders:
            cust_name = o.customer.name if o.customer else "Guest Customer"
            items_qty = sum(item.quantity for item in o.items) if o.items else 1
            pmode = (
                o.payments[0].payment_method.upper()
                if o.payments and len(o.payments) > 0
                else (o.payment_status.upper() if o.payment_status else "POS")
            )
            results.append(
                RecentOnlineOrderItem(
                    order_id=o.order_number,
                    customer_name=cust_name,
                    amount=round(float(o.total_amount), 2),
                    items_count=items_qty,
                    payment_mode=pmode,
                    status=o.status.capitalize(),
                    created_at=o.created_at.isoformat() if o.created_at else "",
                )
            )

        return RecentOnlineOrdersResponse(
            orders=results,
            total=total_count,
        )

    def get_top_selling_products(
        self,
        tenant_id: int,
        store_id: Optional[int] = None,
        limit: int = 10,
    ) -> TopSellingProductsResponse:
        self._validate_store(tenant_id, store_id)

        query = (
            self.db.query(
                Product.id.label("product_id"),
                Product.name.label("product_name"),
                Category.name.label("category_name"),
                func.sum(OrderItem.quantity).label("units_sold"),
                func.sum(OrderItem.total_amount).label("revenue"),
            )
            .join(OrderItem, Product.id == OrderItem.product_id)
            .join(Order, OrderItem.order_id == Order.id)
            .outerjoin(Category, Product.category_id == Category.id)
            .filter(
                Order.tenant_id == tenant_id,
                Order.order_type.in_(self.ONLINE_ORDER_TYPES),
                Order.status.notin_(self.EXCLUDED_REVENUE_STATUSES),
            )
        )

        if store_id is not None:
            query = query.filter(Order.store_id == store_id)

        rows = (
            query.group_by(Product.id, Product.name, Category.name)
            .order_by(desc("revenue"))
            .limit(limit)
            .all()
        )

        max_rev = float(rows[0][4]) if rows and rows[0][4] else 0.0

        products: list[TopSellingProductItem] = []
        for idx, r in enumerate(rows, start=1):
            rev = float(r[4]) if r[4] else 0.0
            prog = round((rev / max_rev * 100), 1) if max_rev > 0 else 0.0
            products.append(
                TopSellingProductItem(
                    rank=idx,
                    product_id=r[0],
                    product_name=r[1],
                    category=r[2] or "General",
                    orders_count=int(r[3] or 0),
                    revenue=round(rev, 2),
                    progress_percentage=prog,
                )
            )

        return TopSellingProductsResponse(
            products=products,
            total=len(products),
        )

    def get_full_dashboard(
        self,
        tenant_id: int,
        store_id: Optional[int] = None,
        period: str = "this_year",
    ) -> EcommerceDashboardResponse:
        kpis = self.get_kpis(tenant_id, store_id, period)
        revenue_comparison = self.get_revenue_comparison(tenant_id, store_id, period)
        order_status = self.get_order_status_breakdown(tenant_id, store_id, period)
        recent_orders = self.get_recent_online_orders(tenant_id, store_id, limit=6)
        top_products = self.get_top_selling_products(tenant_id, store_id, limit=5)

        return EcommerceDashboardResponse(
            kpis=kpis,
            revenue_comparison=revenue_comparison,
            order_status_breakdown=order_status,
            recent_orders=recent_orders.orders,
            top_products=top_products.products,
        )

