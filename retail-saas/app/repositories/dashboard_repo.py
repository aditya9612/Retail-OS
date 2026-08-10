from datetime import datetime
from unittest import result

from sqlalchemy import func,extract,desc
from sqlalchemy.orm import Session

from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.customer import Customer
from app.models.payment import Payment
from app.models.inventory import Inventory
from app.models.product import Product


class DashboardRepository:

    def __init__(self, db: Session):
        self.db = db

    def get_dashboard(self, tenant_id: int):

        today = datetime.now().date()
        current_month = datetime.now().month
        current_year = datetime.now().year

        # Today's Sales
        today_sales = (
            self.db.query(func.coalesce(func.sum(Order.total_amount), 0))
            .filter(
                Order.tenant_id == tenant_id,
                func.date(Order.created_at) == today
            )
            .scalar()
        )

        # Monthly Sales
        monthly_sales = (
            self.db.query(func.coalesce(func.sum(Order.total_amount), 0))
            .filter(
                Order.tenant_id == tenant_id,
                func.extract("month", Order.created_at) == current_month,
                func.extract("year", Order.created_at) == current_year
            )
            .scalar()
        )

        # Total Customers
        total_customers = (
            self.db.query(Customer)
            .filter(Customer.tenant_id == tenant_id)
            .count()
        )

        # Total Revenue
        # Total Revenue
        total_revenue = (
            self.db.query(func.coalesce(func.sum(Order.total_amount), 0))
            .filter(
                Order.tenant_id == tenant_id
            )
        .scalar()
        )

        # Low Stock Products
        low_stock_products = (
            self.db.query(Inventory)
            .filter(
                Inventory.tenant_id == tenant_id,
                Inventory.quantity <= Inventory.low_stock_threshold
            )
            .count()
        )

        return {
            "today_sales": float(today_sales),
            "monthly_sales": float(monthly_sales),
            "total_customers": total_customers,
            "total_revenue": float(total_revenue),
            "low_stock_products": low_stock_products,
        }

    def get_dashboard_overview(self, tenant_id: int):

        result = (
            self.db.query(
                extract("month", Order.created_at).label("month"),
                func.sum(Order.total_amount).label("sales"),
            )
            .filter(Order.tenant_id == tenant_id)
            .group_by(extract("month", Order.created_at))
            .order_by(extract("month", Order.created_at))
            .all()
        )
        print("TENANT ID:", tenant_id)
        print("RESULT:", result)

        months = [
            "Jan", "Feb", "Mar", "Apr", "May", "Jun",
            "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
        ]

        overview = []

        for i in range(12):
            sales = 0

            for row in result:
                if int(row.month) == i + 1:
                    sales = float(row.sales)
                    break

            overview.append({
               "month": months[i],
               "sales": sales
            })

        return {"overview": overview}   

    def get_revenue_vs_cost(self, tenant_id: int):
        print("Tenant ID:", tenant_id)

        revenue = (
            self.db.query(func.coalesce(func.sum(Order.total_amount), 0))
            .filter(Order.tenant_id == tenant_id)
            .scalar()
        )
        print("Revenue:", revenue)

        cost = (
            self.db.query(func.coalesce(func.sum(Product.cost_price), 0))
            .filter(Product.tenant_id == tenant_id)
            .scalar()
        )
        print("Cost:", cost)

        return {
            "revenue": float(revenue),
            "cost": float(cost),
        }

    def get_top_products(self, tenant_id: int):

        result = (
            self.db.query(
                OrderItem.product_name.label("product_name"),
                func.sum(OrderItem.quantity).label("quantity_sold"),
                func.sum(OrderItem.total).label("revenue"),
            )
            .join(Order, Order.id == OrderItem.order_id)
            .filter(Order.tenant_id == tenant_id)
            .group_by(OrderItem.product_name)
            .order_by(desc(func.sum(OrderItem.quantity)))
            .limit(10)
            .all()
        )
        print("TENANT:", tenant_id)
        print("RESULT:", result)

        return {
            "top_products": [
                {
                    "product_name": row.product_name,
                    "quantity_sold": int(row.quantity_sold),
                     "revenue": float(row.revenue)
                }
                for row in result
            ]
        }