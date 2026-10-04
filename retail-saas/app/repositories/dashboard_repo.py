from datetime import datetime
from typing import Optional

from sqlalchemy import desc, extract, func
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

    def get_dashboard(self, tenant_id: int, store_id: Optional[int] = None):
        today = datetime.now().date()
        current_month = datetime.now().month
        current_year = datetime.now().year

        if store_id is not None:
            # Validate store belongs to this tenant
            store = (
                self.db.query(Store)
                .filter(Store.id == store_id, Store.tenant_id == tenant_id)
                .first()
            )
            if not store:
                raise NotFoundException(f"Store with id {store_id} not found")

            # Today's Sales
            today_sales = (
                self.db.query(func.coalesce(func.sum(Order.total_amount), 0))
                .filter(
                    Order.tenant_id == tenant_id,
                    Order.store_id == store_id,
                    func.date(Order.created_at) == today,
                )
                .scalar()
            )

            # Monthly Sales
            monthly_sales = (
                self.db.query(func.coalesce(func.sum(Order.total_amount), 0))
                .filter(
                    Order.tenant_id == tenant_id,
                    Order.store_id == store_id,
                    func.extract("month", Order.created_at) == current_month,
                    func.extract("year", Order.created_at) == current_year,
                )
                .scalar()
            )

            # Store Unique Customers
            total_customers = (
                self.db.query(func.count(func.distinct(Order.customer_id)))
                .filter(
                    Order.tenant_id == tenant_id,
                    Order.store_id == store_id,
                    Order.customer_id.isnot(None),
                )
                .scalar()
            ) or 0

            # Store Total Revenue
            total_revenue = (
                self.db.query(func.coalesce(func.sum(Order.total_amount), 0))
                .filter(
                    Order.tenant_id == tenant_id,
                    Order.store_id == store_id,
                )
                .scalar()
            )

            # Store Low Stock Products
            low_stock_products = (
                self.db.query(Inventory)
                .filter(
                    Inventory.tenant_id == tenant_id,
                    Inventory.store_id == store_id,
                    Inventory.quantity <= Inventory.min_stock_level,
                )
                .count()
            )

            return {
                "mode": "single_store",
                "store_id": store.id,
                "store_name": store.name,
                "today_sales": float(today_sales),
                "monthly_sales": float(monthly_sales),
                "total_customers": int(total_customers),
                "total_revenue": float(total_revenue),
                "low_stock_products": int(low_stock_products),
                "stores_summary": None,
            }

        # All stores mode (consolidated across tenant)
        today_sales = (
            self.db.query(func.coalesce(func.sum(Order.total_amount), 0))
            .filter(
                Order.tenant_id == tenant_id,
                func.date(Order.created_at) == today,
            )
            .scalar()
        )

        monthly_sales = (
            self.db.query(func.coalesce(func.sum(Order.total_amount), 0))
            .filter(
                Order.tenant_id == tenant_id,
                func.extract("month", Order.created_at) == current_month,
                func.extract("year", Order.created_at) == current_year,
            )
            .scalar()
        )

        total_customers = (
            self.db.query(Customer)
            .filter(Customer.tenant_id == tenant_id)
            .count()
        )

        total_revenue = (
            self.db.query(func.coalesce(func.sum(Order.total_amount), 0))
            .filter(Order.tenant_id == tenant_id)
            .scalar()
        )

        low_stock_products = (
            self.db.query(Inventory)
            .filter(
                Inventory.tenant_id == tenant_id,
                Inventory.quantity <= Inventory.min_stock_level,
            )
            .count()
        )

        # Zero N+1 grouped summary for active stores
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
                func.date(Order.created_at) == today,
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
                func.extract("month", Order.created_at) == current_month,
                func.extract("year", Order.created_at) == current_year,
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
            "today_sales": float(today_sales),
            "monthly_sales": float(monthly_sales),
            "total_customers": total_customers,
            "total_revenue": float(total_revenue),
            "low_stock_products": low_stock_products,
            "stores_summary": stores_summary,
        }

    def get_dashboard_overview(self, tenant_id: int, store_id: Optional[int] = None):
        if store_id is not None:
            store = (
                self.db.query(Store)
                .filter(Store.id == store_id, Store.tenant_id == tenant_id)
                .first()
            )
            if not store:
                raise NotFoundException(f"Store with id {store_id} not found")

        query = (
            self.db.query(
                extract("month", Order.created_at).label("month"),
                func.sum(Order.total_amount).label("sales"),
            )
            .filter(Order.tenant_id == tenant_id)
        )
        if store_id is not None:
            query = query.filter(Order.store_id == store_id)

        result = (
            query.group_by(extract("month", Order.created_at))
            .order_by(extract("month", Order.created_at))
            .all()
        )

        months = [
            "Jan", "Feb", "Mar", "Apr", "May", "Jun",
            "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
        ]

        overview = []
        for i in range(12):
            sales = 0.0
            for row in result:
                if int(row.month) == i + 1:
                    sales = float(row.sales or 0)
                    break

            overview.append({
                "month": months[i],
                "sales": sales
            })

        return {"overview": overview}

    def get_revenue_vs_cost(self, tenant_id: int, store_id: Optional[int] = None):
        if store_id is not None:
            store = (
                self.db.query(Store)
                .filter(Store.id == store_id, Store.tenant_id == tenant_id)
                .first()
            )
            if not store:
                raise NotFoundException(f"Store with id {store_id} not found")

        rev_query = (
            self.db.query(func.coalesce(func.sum(Order.total_amount), 0))
            .filter(Order.tenant_id == tenant_id)
        )
        if store_id is not None:
            rev_query = rev_query.filter(Order.store_id == store_id)
        revenue = rev_query.scalar()

        if store_id is not None:
            cost = (
                self.db.query(func.coalesce(func.sum(Product.cost_price), 0))
                .select_from(Product)
                .join(Inventory, Inventory.product_id == Product.id)
                .filter(
                    Product.tenant_id == tenant_id,
                    Inventory.store_id == store_id,
                )
                .scalar()
            )
        else:
            cost = (
                self.db.query(func.coalesce(func.sum(Product.cost_price), 0))
                .filter(Product.tenant_id == tenant_id)
                .scalar()
            )

        return {
            "revenue": float(revenue),
            "cost": float(cost),
        }

    def get_top_products(self, tenant_id: int, store_id: Optional[int] = None):
        if store_id is not None:
            store = (
                self.db.query(Store)
                .filter(Store.id == store_id, Store.tenant_id == tenant_id)
                .first()
            )
            if not store:
                raise NotFoundException(f"Store with id {store_id} not found")

        query = (
            self.db.query(
                Product.name.label("product_name"),
                func.sum(OrderItem.quantity).label("quantity_sold"),
                func.sum(OrderItem.total_amount).label("revenue"),
            )
            .select_from(OrderItem)
            .join(Order, Order.id == OrderItem.order_id)
            .join(Product, Product.id == OrderItem.product_id)
            .filter(Order.tenant_id == tenant_id)
        )
        if store_id is not None:
            query = query.filter(Order.store_id == store_id)

        result = (
            query.group_by(Product.name)
            .order_by(desc(func.sum(OrderItem.quantity)))
            .limit(10)
            .all()
        )

        return {
            "top_products": [
                {
                    "product_name": row.product_name,
                    "quantity_sold": int(row.quantity_sold or 0),
                    "revenue": float(row.revenue or 0)
                }
                for row in result
            ]
        }
