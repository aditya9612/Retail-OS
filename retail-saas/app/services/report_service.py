from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.invoice import Invoice
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product   import Product
from app.utils.constants import OrderStatus


class ReportService:
    def __init__(self, db: Session):
        self.db = db

    def _confirmed_filter(self, query, tenant_id: int):
        return query.filter(
            Order.tenant_id == tenant_id,
            Order.status.in_([OrderStatus.CONFIRMED.value, OrderStatus.DELIVERED.value]),
        )

    def daily_sales(self, tenant_id: int, target_date: date | None = None) -> dict:
        target_date = target_date or date.today()
        start = datetime.combine(target_date, datetime.min.time())
        end = start + timedelta(days=1)
        result = (
            self.db.query(func.count(Order.id), func.coalesce(func.sum(Order.total_amount), 0))
            .filter(
                Order.tenant_id == tenant_id,
                Order.created_at >= start,
                Order.created_at < end,
                Order.status.in_([OrderStatus.CONFIRMED.value, OrderStatus.DELIVERED.value]),
            )
            .first()
        )
        return {"date": str(target_date), "order_count": result[0], "total_sales": float(result[1])}

    def monthly_sales(self, tenant_id: int, year: int, month: int) -> dict:
        start = datetime(year, month, 1)
        end = datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)
        result = (
            self.db.query(func.count(Order.id), func.coalesce(func.sum(Order.total_amount), 0))
            .filter(
                Order.tenant_id == tenant_id,
                Order.created_at >= start,
                Order.created_at < end,
                Order.status.in_([OrderStatus.CONFIRMED.value, OrderStatus.DELIVERED.value]),
            )
            .first()
        )
        return {"year": year, "month": month, "order_count": result[0], "total_sales": float(result[1])}

    def profit_loss(self, tenant_id: int, start_date: date, end_date: date) -> dict:
        orders = (
            self.db.query(Order)
            .filter(
                Order.tenant_id == tenant_id,
                Order.created_at >= datetime.combine(start_date, datetime.min.time()),
                Order.created_at <= datetime.combine(end_date, datetime.max.time()),
                Order.status.in_([OrderStatus.CONFIRMED.value, OrderStatus.DELIVERED.value]),
            )
            .all()
        )
        revenue = sum((o.total_amount for o in orders), Decimal("0"))
        cost = Decimal("0")
        for order in orders:
            for item in order.items:
                products= self.db.query(Product).filter(Product.id == item.product_id).first()
                if product:
                    cost += product.cost_price * item.quantity
        return {
            "revenue": float(revenue),
            "cost": float(cost),
            "profit": float(revenue - cost),
            "start_date": str(start_date),
            "end_date": str(end_date),
        }

    def gst_report(self, tenant_id: int, start_date: date, end_date: date) -> dict:
        invoices = (
            self.db.query(Invoice)
            .filter(
                Invoice.tenant_id == tenant_id,
                Invoice.created_at >= datetime.combine(start_date, datetime.min.time()),
                Invoice.created_at <= datetime.combine(end_date, datetime.max.time()),
            )
            .all()
        )
        return {
            "invoice_count": len(invoices),
            "total_cgst": float(sum((i.cgst_amount for i in invoices), Decimal("0"))),
            "total_sgst": float(sum((i.sgst_amount for i in invoices), Decimal("0"))),
            "total_igst": float(sum((i.igst_amount for i in invoices), Decimal("0"))),
            "total_amount": float(sum((i.total_amount for i in invoices), Decimal("0"))),
        }

    def product_performance(self, tenant_id: int, limit: int = 10) -> list[dict]:
        rows = (
            self.db.query(
                OrderItem.product_id,
                OrderItem.product_name,
                func.sum(OrderItem.quantity).label("qty"),
                func.sum(OrderItem.total).label("revenue"),
            )
            .join(Order)
            .filter(Order.tenant_id == tenant_id, Order.status.in_([OrderStatus.CONFIRMED.value, OrderStatus.DELIVERED.value]))
            .group_by(OrderItem.product_id, OrderItem.product_name)
            .order_by(func.sum(OrderItem.total).desc())
            .limit(limit)
            .all()
        )
        return [{"product_id": r[0], "product_name": r[1], "quantity_sold": int(r[2]), "revenue": float(r[3])} for r in rows]

    def customer_analytics(self, tenant_id: int) -> dict:
        from app.models.customer import Customer
        total_customers = self.db.query(func.count(Customer.id)).filter(Customer.tenant_id == tenant_id).scalar()
        repeat = (
            self.db.query(Order.customer_id)
            .filter(Order.tenant_id == tenant_id, Order.customer_id.isnot(None))
            .group_by(Order.customer_id)
            .having(func.count(Order.id) > 1)
            .count()
        )
        return {"total_customers": total_customers, "repeat_customers": repeat}

    def log_audit(self, tenant_id: int, user_id: int | None, action: str, resource: str, resource_id: int | None = None, details: dict | None = None) -> AuditLog:
        log = AuditLog(
            tenant_id=tenant_id,
            user_id=user_id,
            action=action,
            resource=resource,
            resource_id=resource_id,
            details=details,
        )
        self.db.add(log)
        self.db.commit()
        self.db.refresh(log)
        return log
