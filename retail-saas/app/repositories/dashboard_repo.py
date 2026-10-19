
from calendar import monthrange
from datetime import date, datetime, time, timedelta
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundException
from app.models.customer import Customer
from app.models.inventory import Inventory
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product import Product
from app.models.store import Store
from app.models.store_target import StoreTarget


class DashboardRepository:
    EXCLUDED_ORDER_STATUSES = (
        "draft",
        "cancelled",
        "canceled",
        "void",
        "deleted",
    )

    TARGET_TYPES = {
        "sales": (
            "sales",
            "total_sales",
            "revenue",
            "sales_target",
            "sales_revenue",
        ),
        "cost": (
            "cost",
            "cogs",
            "total_cost",
            "total_cogs",
            "cost_of_goods_sold",
        ),
        "products": (
            "products_sold",
            "quantity",
            "quantity_sold",
            "units_sold",
            "product_quantity",
        ),
    }

    TARGET_PERIODS = {
        "day": ("day", "daily", "this_day"),
        "month": ("month", "monthly", "this_month"),
        "year": ("year", "yearly", "annual", "annually", "this_year"),
    }

    MONTH_NAMES = (
        "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    )

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

        if period == "this_month":
            start_date = today.replace(day=1)
            end_date = today + timedelta(days=1)

        elif period == "last_month":
            end_date = today.replace(day=1)
            start_date = (end_date - timedelta(days=1)).replace(day=1)

        elif period == "this_year":
            start_date = today.replace(month=1, day=1)
            end_date = today + timedelta(days=1)

        else:
            raise ValueError(
                "Invalid period. Use this_month, last_month, or this_year."
            )

        return start_date, end_date

    @staticmethod
    def _datetime_bounds(start_date: date, end_date: date):
        return (
            datetime.combine(start_date, time.min),
            datetime.combine(end_date, time.min),
        )

    def _sales_orders_query(self, tenant_id: int):
        return self.db.query(Order).filter(
            Order.tenant_id == tenant_id,
            func.lower(Order.status).notin_(
                self.EXCLUDED_ORDER_STATUSES
            ),
        )

    def _get_target_value(
        self,
        tenant_id: int,
        store_id: Optional[int],
        target_type: str,
        target_period: str,
        start_date: date,
        end_date: date,
    ) -> float:
        type_aliases = self.TARGET_TYPES[target_type]
        period_aliases = self.TARGET_PERIODS[target_period]
        start_dt, end_dt = self._datetime_bounds(
            start_date,
            end_date,
        )

        query = (
            self.db.query(
                func.coalesce(
                    func.sum(StoreTarget.target_value),
                    0,
                )
            )
            .join(
                Store,
                Store.id == StoreTarget.store_id,
            )
            .filter(
                Store.tenant_id == tenant_id,
                func.lower(StoreTarget.status) == "active",
                func.lower(StoreTarget.target_type).in_(type_aliases),
                func.lower(StoreTarget.period).in_(period_aliases),
                StoreTarget.start_date < end_dt,
                StoreTarget.end_date >= start_dt,
            )
        )

        if store_id is not None:
            query = query.filter(
                StoreTarget.store_id == store_id,
            )

        return float(query.scalar() or 0)

    @staticmethod
    def _achievement(actual: float, target: float) -> float:
        if target <= 0:
            return 0.0

        return round((actual / target) * 100, 2)

    def _get_sales_total(
        self,
        tenant_id: int,
        store_id: Optional[int],
        start_date: date,
        end_date: date,
    ) -> float:
        start_dt, end_dt = self._datetime_bounds(
            start_date,
            end_date,
        )

        query = (
            self.db.query(
                func.coalesce(func.sum(Order.total_amount), 0)
            )
            .filter(
                Order.tenant_id == tenant_id,
                func.lower(Order.status).notin_(
                    self.EXCLUDED_ORDER_STATUSES
                ),
                Order.created_at >= start_dt,
                Order.created_at < end_dt,
            )
        )

        if store_id is not None:
            query = query.filter(Order.store_id == store_id)

        return float(query.scalar() or 0)

    def _get_cost_total(
        self,
        tenant_id: int,
        store_id: Optional[int],
        start_date: date,
        end_date: date,
    ) -> float:
        start_dt, end_dt = self._datetime_bounds(
            start_date,
            end_date,
        )

        query = (
            self.db.query(
                func.coalesce(
                    func.sum(
                        OrderItem.quantity * Product.cost_price
                    ),
                    0,
                )
            )
            .join(
                Order,
                Order.id == OrderItem.order_id,
            )
            .join(
                Product,
                Product.id == OrderItem.product_id,
            )
            .filter(
                Order.tenant_id == tenant_id,
                Product.tenant_id == tenant_id,
                func.lower(Order.status).notin_(
                    self.EXCLUDED_ORDER_STATUSES
                ),
                Order.created_at >= start_dt,
                Order.created_at < end_dt,
            )
        )

        if store_id is not None:
            query = query.filter(Order.store_id == store_id)

        return float(query.scalar() or 0)

    def _get_products_sold(
        self,
        tenant_id: int,
        store_id: Optional[int],
        start_date: date,
        end_date: date,
    ) -> int:
        start_dt, end_dt = self._datetime_bounds(
            start_date,
            end_date,
        )

        query = (
            self.db.query(
                func.coalesce(func.sum(OrderItem.quantity), 0)
            )
            .join(
                Order,
                Order.id == OrderItem.order_id,
            )
            .join(
                Product,
                Product.id == OrderItem.product_id,
            )
            .filter(
                Order.tenant_id == tenant_id,
                Product.tenant_id == tenant_id,
                func.lower(Order.status).notin_(
                    self.EXCLUDED_ORDER_STATUSES
                ),
                Order.created_at >= start_dt,
                Order.created_at < end_dt,
            )
        )

        if store_id is not None:
            query = query.filter(Order.store_id == store_id)

        return int(query.scalar() or 0)

    def get_recent_transactions(
        self,
        tenant_id: int,
        store_id: Optional[int] = None,
        limit: int = 10,
    ):
        self._validate_store(tenant_id, store_id)

        query = self.db.query(Order).filter(
            Order.tenant_id == tenant_id,
        )

        if store_id is not None:
            query = query.filter(Order.store_id == store_id)

        rows = (
            query.order_by(
                Order.created_at.desc(),
                Order.id.desc(),
            )
            .limit(limit)
            .all()
        )

        return {
            "transactions": [
                {
                    "order_id": row.id,
                    "order_number": row.order_number,
                    "amount": float(row.total_amount or 0),
                    "order_status": row.status,
                    "payment_status": row.payment_status,
                    "created_at": row.created_at,
                }
                for row in rows
            ]
        }

    def get_dashboard(
        self,
        tenant_id: int,
        store_id: Optional[int] = None,
        period: str = "this_month",
    ):
        store = self._validate_store(tenant_id, store_id)

        today = date.today()
        tomorrow = today + timedelta(days=1)
        month_start = today.replace(day=1)

        today_sales = self._get_sales_total(
            tenant_id, store_id, today, tomorrow
        )
        monthly_sales = self._get_sales_total(
            tenant_id, store_id, month_start, tomorrow
        )
        total_revenue = self._get_sales_total(
            tenant_id,
            store_id,
            date(2000, 1, 1),
            tomorrow,
        )

        total_customers_query = self.db.query(
            func.count(func.distinct(Order.customer_id))
        ).filter(
            Order.tenant_id == tenant_id,
            Order.customer_id.isnot(None),
        )

        if store_id is not None:
            total_customers_query = total_customers_query.filter(
                Order.store_id == store_id
            )

        total_customers = int(total_customers_query.scalar() or 0)

        low_stock_query = self.db.query(
            func.count(Inventory.id)
        ).filter(
            Inventory.tenant_id == tenant_id,
            Inventory.quantity <= Inventory.min_stock_level,
        )

        if store_id is not None:
            low_stock_query = low_stock_query.filter(
                Inventory.store_id == store_id
            )

        low_stock_products = int(low_stock_query.scalar() or 0)

        start_date, end_date = self._period_dates(period)

        total_sales = self._get_sales_total(
            tenant_id, store_id, start_date, end_date
        )
        total_cost = self._get_cost_total(
            tenant_id, store_id, start_date, end_date
        )
        products_sold = self._get_products_sold(
            tenant_id, store_id, start_date, end_date
        )

        sales_target = self._get_target_value(
            tenant_id, store_id, "sales", "month",
            start_date, end_date,
        )
        cost_target = self._get_target_value(
            tenant_id, store_id, "cost", "month",
            start_date, end_date,
        )
        products_target = self._get_target_value(
            tenant_id, store_id, "products", "month",
            start_date, end_date,
        )

        stores_summary = None

        if store_id is None:
            stores = (
                self.db.query(Store)
                .filter(Store.tenant_id == tenant_id)
                .order_by(Store.id)
                .all()
            )

            today_rows = (
                self.db.query(
                    Order.store_id,
                    func.coalesce(
                        func.sum(Order.total_amount), 0
                    ).label("sales"),
                    func.count(Order.id).label("orders"),
                )
                .filter(
                    Order.tenant_id == tenant_id,
                    func.lower(Order.status).notin_(
                        self.EXCLUDED_ORDER_STATUSES
                    ),
                    Order.created_at >= datetime.combine(today, time.min),
                    Order.created_at < datetime.combine(tomorrow, time.min),
                )
                .group_by(Order.store_id)
                .all()
            )
            today_map = {
                row.store_id: (float(row.sales), int(row.orders))
                for row in today_rows
            }

            month_rows = (
                self.db.query(
                    Order.store_id,
                    func.coalesce(
                        func.sum(Order.total_amount), 0
                    ).label("sales"),
                )
                .filter(
                    Order.tenant_id == tenant_id,
                    func.lower(Order.status).notin_(
                        self.EXCLUDED_ORDER_STATUSES
                    ),
                    Order.created_at >= datetime.combine(month_start, time.min),
                    Order.created_at < datetime.combine(tomorrow, time.min),
                )
                .group_by(Order.store_id)
                .all()
            )
            month_map = {
                row.store_id: float(row.sales)
                for row in month_rows
            }

            low_stock_rows = (
                self.db.query(
                    Inventory.store_id,
                    func.count(Inventory.id).label("low_count"),
                )
                .filter(
                    Inventory.tenant_id == tenant_id,
                    Inventory.quantity <= Inventory.min_stock_level,
                )
                .group_by(Inventory.store_id)
                .all()
            )
            low_stock_map = {
                row.store_id: int(row.low_count)
                for row in low_stock_rows
            }

            stores_summary = []

            for current_store in stores:
                store_today_sales, store_orders = today_map.get(
                    current_store.id, (0.0, 0)
                )

                stores_summary.append(
                    {
                        "store_id": current_store.id,
                        "store_name": current_store.name,
                        "today_sales": store_today_sales,
                        "monthly_sales": month_map.get(
                            current_store.id, 0.0
                        ),
                        "orders_count": store_orders,
                        "low_stock_count": low_stock_map.get(
                            current_store.id, 0
                        ),
                        "is_active": current_store.is_active,
                    }
                )

        recent = self.get_recent_transactions(
            tenant_id=tenant_id,
            store_id=store_id,
            limit=10,
        )["transactions"]

        return {
            "mode": "single_store" if store else "all_stores",
            "store_id": store.id if store else None,
            "store_name": store.name if store else None,
            "today_sales": today_sales,
            "monthly_sales": monthly_sales,
            "total_customers": total_customers,
            "total_revenue": total_revenue,
            "low_stock_products": low_stock_products,
            "stores_summary": stores_summary,
            "total_sales": total_sales,
            "sales_target": sales_target,
            "sales_achievement_percentage": self._achievement(
                total_sales, sales_target
            ),
            "total_cost": total_cost,
            "cost_target": cost_target,
            "cost_achievement_percentage": self._achievement(
                total_cost, cost_target
            ),
            "products_sold": products_sold,
            "products_target": products_target,
            "products_achievement_percentage": self._achievement(
                products_sold, products_target
            ),
            "recent_transactions": recent,
        }

    def get_dashboard_overview(
        self,
        tenant_id: int,
        store_id: Optional[int] = None,
        period: str = "this_year",
    ):
        self._validate_store(tenant_id, store_id)

        start_date, end_date = self._period_dates(period)
        start_dt, end_dt = self._datetime_bounds(
            start_date, end_date
        )

        query = (
            self._sales_orders_query(tenant_id)
            .with_entities(Order.created_at, Order.total_amount)
            .filter(
                Order.created_at >= start_dt,
                Order.created_at < end_dt,
            )
        )

        if store_id is not None:
            query = query.filter(Order.store_id == store_id)

        rows = query.order_by(Order.created_at).all()
        sales_by_date = {}

        for row in rows:
            order_date = row.created_at.date()
            sales_by_date[order_date] = (
                sales_by_date.get(order_date, 0.0)
                + float(row.total_amount or 0)
            )

        overview = []

        if period in ("this_month", "last_month"):
            current_day = start_date
            total_days = (end_date - start_date).days

            monthly_target = self._get_target_value(
                tenant_id, store_id, "sales", "month",
                start_date, end_date,
            )

            while current_day < end_date:
                daily_target = self._get_target_value(
                    tenant_id, store_id, "sales", "day",
                    current_day,
                    current_day + timedelta(days=1),
                )

                if daily_target <= 0 and total_days > 0:
                    daily_target = monthly_target / total_days

                overview.append(
                    {
                        "month": current_day.strftime("%d %b"),
                        "sales": round(
                            sales_by_date.get(current_day, 0.0), 2
                        ),
                        "target": round(daily_target, 2),
                    }
                )

                current_day += timedelta(days=1)

        else:
            for month_number in range(1, 13):
                month_start = date(
                    start_date.year, month_number, 1
                )

                if month_number == 12:
                    month_end = date(start_date.year + 1, 1, 1)
                else:
                    month_end = date(
                        start_date.year, month_number + 1, 1
                    )

                month_sales = sum(
                    value
                    for sale_date, value in sales_by_date.items()
                    if month_start <= sale_date < month_end
                )

                month_target = self._get_target_value(
                    tenant_id, store_id, "sales", "month",
                    month_start, month_end,
                )

                if month_target <= 0:
                    annual_target = self._get_target_value(
                        tenant_id, store_id, "sales", "year",
                        start_date, end_date,
                    )
                    month_target = annual_target / 12

                overview.append(
                    {
                        "month": self.MONTH_NAMES[month_number - 1],
                        "sales": round(month_sales, 2),
                        "target": round(month_target, 2),
                    }
                )

        return {
            "period": period,
            "overview": overview,
        }

    def get_revenue_vs_cost(
        self,
        tenant_id: int,
        store_id: Optional[int] = None,
        period: str = "this_month",
    ):
        self._validate_store(tenant_id, store_id)

        start_date, end_date = self._period_dates(period)

        revenue = self._get_sales_total(
            tenant_id, store_id, start_date, end_date
        )
        cost = self._get_cost_total(
            tenant_id, store_id, start_date, end_date
        )

        gross_profit = revenue - cost
        gross_margin_percentage = (
            round((gross_profit / revenue) * 100, 2)
            if revenue > 0
            else 0.0
        )

        return {
            "period": period,
            "revenue": round(revenue, 2),
            "cost": round(cost, 2),
            "gross_profit": round(gross_profit, 2),
            "gross_margin_percentage": gross_margin_percentage,
        }

    def get_top_products(
        self,
        tenant_id: int,
        store_id: Optional[int] = None,
        limit: int = 10,
    ):
        self._validate_store(tenant_id, store_id)

        query = (
            self.db.query(
                Product.name.label("product_name"),
                func.coalesce(
                    func.sum(OrderItem.quantity), 0
                ).label("quantity_sold"),
                func.coalesce(
                    func.sum(OrderItem.total_amount), 0
                ).label("revenue"),
            )
            .join(
                OrderItem,
                Product.id == OrderItem.product_id,
            )
            .join(
                Order,
                Order.id == OrderItem.order_id,
            )
            .filter(
                Product.tenant_id == tenant_id,
                Order.tenant_id == tenant_id,
                func.lower(Order.status).notin_(
                    self.EXCLUDED_ORDER_STATUSES
                ),
            )
        )

        if store_id is not None:
            query = query.filter(Order.store_id == store_id)

        rows = (
            query.group_by(Product.id, Product.name)
            .order_by(
                func.sum(OrderItem.total_amount).desc()
            )
            .limit(limit)
            .all()
        )

        return {
            "top_products": [
                {
                    "product_name": row.product_name,
                    "quantity_sold": int(row.quantity_sold or 0),
                    "revenue": round(float(row.revenue or 0), 2),
                }
                for row in rows
            ]
        }