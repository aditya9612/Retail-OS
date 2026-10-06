
from calendar import monthrange
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import extract, func
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundException
from app.models.customer import Customer
from app.models.inventory import Inventory
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product import Product
from app.models.store import Store


class DashboardRepository:
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

    def get_dashboard(
        self,
        tenant_id: int,
        store_id: Optional[int] = None,
    ):
        store = self._validate_store(
            tenant_id=tenant_id,
            store_id=store_id,
        )

        today = date.today()
        tomorrow = today + timedelta(days=1)
        month_start = today.replace(day=1)

        today_query = (
            self.db.query(
                func.coalesce(
                    func.sum(Order.total_amount),
                    0,
                )
            )
            .filter(
                Order.tenant_id == tenant_id,
                Order.created_at >= today,
                Order.created_at < tomorrow,
            )
        )

        monthly_query = (
            self.db.query(
                func.coalesce(
                    func.sum(Order.total_amount),
                    0,
                )
            )
            .filter(
                Order.tenant_id == tenant_id,
                Order.created_at >= month_start,
                Order.created_at < tomorrow,
            )
        )

        total_revenue_query = (
            self.db.query(
                func.coalesce(
                    func.sum(Order.total_amount),
                    0,
                )
            )
            .filter(Order.tenant_id == tenant_id)
        )

        if store_id is not None:
            today_query = today_query.filter(Order.store_id == store_id)
            monthly_query = monthly_query.filter(Order.store_id == store_id)
            total_revenue_query = total_revenue_query.filter(Order.store_id == store_id)

            total_customers = (
                self.db.query(func.count(func.distinct(Order.customer_id)))
                .filter(
                    Order.tenant_id == tenant_id,
                    Order.store_id == store_id,
                    Order.customer_id.isnot(None),
                )
                .scalar() or 0
            )

            low_stock_products = (
                self.db.query(func.count(Inventory.id))
                .filter(
                    Inventory.tenant_id == tenant_id,
                    Inventory.store_id == store_id,
                    Inventory.quantity <= Inventory.min_stock_level,
                )
                .scalar() or 0
            )

            today_sales = float(today_query.scalar() or 0)
            monthly_sales = float(monthly_query.scalar() or 0)
            total_revenue = float(total_revenue_query.scalar() or 0)

            return {
                "mode": "single_store",
                "store_id": store.id,
                "store_name": store.name,
                "today_sales": today_sales,
                "monthly_sales": monthly_sales,
                "total_customers": int(total_customers),
                "total_revenue": total_revenue,
                "low_stock_products": int(low_stock_products),
                "stores_summary": None,
            }

        today_sales = float(today_query.scalar() or 0)
        monthly_sales = float(monthly_query.scalar() or 0)
        total_revenue = float(total_revenue_query.scalar() or 0)

        total_customers = (
            self.db.query(func.count(Customer.id))
            .filter(Customer.tenant_id == tenant_id)
            .scalar() or 0
        )

        low_stock_products = (
            self.db.query(func.count(Inventory.id))
            .filter(
                Inventory.tenant_id == tenant_id,
                Inventory.quantity <= Inventory.min_stock_level,
            )
            .scalar() or 0
        )

        stores = (
            self.db.query(Store)
            .filter(Store.tenant_id == tenant_id)
            .order_by(Store.id)
            .all()
        )

        today_rows = (
            self.db.query(
                Order.store_id,
                func.coalesce(func.sum(Order.total_amount), 0).label("sales"),
                func.count(Order.id).label("orders"),
            )
            .filter(
                Order.tenant_id == tenant_id,
                Order.created_at >= today,
                Order.created_at < tomorrow,
            )
            .group_by(Order.store_id)
            .all()
        )
        today_map = {row.store_id: (float(row.sales), int(row.orders)) for row in today_rows}

        month_rows = (
            self.db.query(
                Order.store_id,
                func.coalesce(func.sum(Order.total_amount), 0).label("sales"),
            )
            .filter(
                Order.tenant_id == tenant_id,
                Order.created_at >= month_start,
                Order.created_at < tomorrow,
            )
            .group_by(Order.store_id)
            .all()
        )
        month_map = {row.store_id: float(row.sales) for row in month_rows}

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
        low_stock_map = {row.store_id: int(row.low_count) for row in low_stock_rows}

        stores_summary = []
        for st in stores:
            t_sales, t_orders = today_map.get(st.id, (0.0, 0))
            m_sales = month_map.get(st.id, 0.0)
            ls_count = low_stock_map.get(st.id, 0)
            stores_summary.append({
                "store_id": st.id,
                "store_name": st.name,
                "today_sales": t_sales,
                "monthly_sales": m_sales,
                "orders_count": t_orders,
                "low_stock_count": ls_count,
                "is_active": st.is_active,
            })

        return {
            "mode": "all_stores",
            "store_id": None,
            "store_name": None,
            "today_sales": today_sales,
            "monthly_sales": monthly_sales,
            "total_customers": int(total_customers),
            "total_revenue": total_revenue,
            "low_stock_products": int(low_stock_products),
            "stores_summary": stores_summary,
        }

    def get_dashboard_overview(
        self,
        tenant_id: int,
        store_id: Optional[int] = None,
        period: str = "this_year",
    ):
        self._validate_store(
            tenant_id=tenant_id,
            store_id=store_id,
        )

        allowed_periods = {
            "this_month",
            "last_month",
            "this_year",
        }

        if period not in allowed_periods:
            raise ValueError(
                "Invalid period. Use this_month, last_month, or this_year."
            )

        today = date.today()

        query = self.db.query(
            Order.created_at,
            Order.total_amount,
        ).filter(
            Order.tenant_id == tenant_id,
        )

        if store_id is not None:
            query = query.filter(
                Order.store_id == store_id,
            )

        if period == "this_month":
            start_date = today.replace(day=1)
            end_date = today + timedelta(days=1)

            query = query.filter(
                Order.created_at >= start_date,
                Order.created_at < end_date,
            ).order_by(Order.created_at)

            rows = query.all()

            sales_by_day = {}

            for row in rows:
                created_at = row.created_at

                if isinstance(created_at, datetime):
                    day = created_at.date()
                elif isinstance(created_at, date):
                    day = created_at
                else:
                    day = datetime.fromisoformat(
                        str(created_at)
                    ).date()

                sales_by_day[day] = (
                    sales_by_day.get(day, 0.0)
                    + float(row.total_amount or 0)
                )

            overview = []

            current_day = start_date

            while current_day <= today:
                overview.append(
                    {
                        "month": current_day.strftime("%d %b"),
                        "sales": float(
                            sales_by_day.get(current_day, 0.0)
                        ),
                    }
                )

                current_day += timedelta(days=1)

            return {
                "period": period,
                "overview": overview,
            }

        if period == "last_month":
            first_day_this_month = today.replace(day=1)

            last_month_last_day = (
                first_day_this_month - timedelta(days=1)
            )

            start_date = last_month_last_day.replace(day=1)
            end_date = first_day_this_month

            query = query.filter(
                Order.created_at >= start_date,
                Order.created_at < end_date,
            ).order_by(Order.created_at)

            rows = query.all()

            sales_by_day = {}

            for row in rows:
                created_at = row.created_at

                if isinstance(created_at, datetime):
                    day = created_at.date()
                elif isinstance(created_at, date):
                    day = created_at
                else:
                    day = datetime.fromisoformat(
                        str(created_at)
                    ).date()

                sales_by_day[day] = (
                    sales_by_day.get(day, 0.0)
                    + float(row.total_amount or 0)
                )

            overview = []

            current_day = start_date

            while current_day < end_date:
                overview.append(
                    {
                        "month": current_day.strftime("%d %b"),
                        "sales": float(
                            sales_by_day.get(current_day, 0.0)
                        ),
                    }
                )

                current_day += timedelta(days=1)

            return {
                "period": period,
                "overview": overview,
            }

        start_date = today.replace(
            month=1,
            day=1,
        )

        end_date = today + timedelta(days=1)

        query = query.filter(
            Order.created_at >= start_date,
            Order.created_at < end_date,
        )

        rows = query.all()

        sales_by_month = {}

        for row in rows:
            created_at = row.created_at

            if isinstance(created_at, datetime):
                month = created_at.month
            elif isinstance(created_at, date):
                month = created_at.month
            else:
                month = datetime.fromisoformat(
                    str(created_at)
                ).month

            sales_by_month[month] = (
                sales_by_month.get(month, 0.0)
                + float(row.total_amount or 0)
            )

        months = [
            "Jan",
            "Feb",
            "Mar",
            "Apr",
            "May",
            "Jun",
            "Jul",
            "Aug",
            "Sep",
            "Oct",
            "Nov",
            "Dec",
        ]

        overview = []

        for month_number in range(1, 13):
            overview.append(
                {
                    "month": months[month_number - 1],
                    "sales": float(
                        sales_by_month.get(month_number, 0.0)
                    ),
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
        self._validate_store(
            tenant_id=tenant_id,
            store_id=store_id,
        )

        allowed_periods = {
            "this_month",
            "last_month",
            "this_year",
        }

        if period not in allowed_periods:
            raise ValueError(
                "Invalid period. Use this_month, last_month, or this_year."
            )

        today = date.today()

        if period == "this_month":
            start_date = today.replace(day=1)
            end_date = today + timedelta(days=1)

        elif period == "last_month":
            start_date = (
                today.replace(day=1)
                - timedelta(days=1)
            ).replace(day=1)

            end_date = today.replace(day=1)

        else:
            start_date = today.replace(
                month=1,
                day=1,
            )

            end_date = today + timedelta(days=1)

        revenue_query = (
            self.db.query(
                func.coalesce(
                    func.sum(Order.total_amount),
                    0,
                )
            )
            .filter(
                Order.tenant_id == tenant_id,
                Order.created_at >= start_date,
                Order.created_at < end_date,
            )
        )

        if store_id is not None:
            revenue_query = revenue_query.filter(
                Order.store_id == store_id
            )

        revenue = float(
            revenue_query.scalar() or 0
        )

        cost_query = (
            self.db.query(
                func.coalesce(
                    func.sum(
                        OrderItem.quantity
                        * Product.cost_price
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
                Order.created_at >= start_date,
                Order.created_at < end_date,
                Product.tenant_id == tenant_id,
            )
        )

        if store_id is not None:
            cost_query = cost_query.filter(
                Order.store_id == store_id
            )

        cost = float(
            cost_query.scalar() or 0
        )

        return {
            "period": period,
            "revenue": revenue,
            "cost": cost,
        }

    def get_top_products(
        self,
        tenant_id: int,
        store_id: Optional[int] = None,
        limit: int = 10,
    ):
        self._validate_store(
            tenant_id=tenant_id,
            store_id=store_id,
        )

        query = (
            self.db.query(
                Product.name.label("product_name"),
                func.coalesce(
                    func.sum(OrderItem.quantity),
                    0,
                ).label("quantity_sold"),
                func.coalesce(
                    func.sum(OrderItem.total_amount),
                    0,
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
            )
        )

        if store_id is not None:
            query = query.filter(
                Order.store_id == store_id
            )

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
                    "quantity_sold": int(
                        row.quantity_sold or 0
                    ),
                    "revenue": float(
                        row.revenue or 0
                    ),
                }
                for row in rows
            ]
        }
