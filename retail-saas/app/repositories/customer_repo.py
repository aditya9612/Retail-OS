from datetime import datetime, timedelta
from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.models.customer import Customer
from sqlalchemy import func
from datetime import datetime
from app.models.order import Order

def get_filtered_customers(db, tenant_id, name=None, mobile=None, segment=None):
    query = db.query(Customer).filter(Customer.tenant_id == tenant_id)

    if name:
        query = query.filter(Customer.name.ilike(f"%{name}%"))

    if mobile:
        query = query.filter(Customer.phone.ilike(f"%{mobile}%"))

    if segment:
        if segment == "vip":
            query = query.filter(Customer.total_spend > 50000)

        elif segment == "active":
            query = query.filter(Customer.status == "active")

        elif segment == "inactive":
            query = query.filter(Customer.status == "inactive")

        elif segment == "new":
            last_30_days = datetime.now() - timedelta(days=30)
            query = query.filter(Customer.created_at >= last_30_days)

    return query.all()

def delete_customer(db, tenant_id: int, customer_id: int):
    customer = (
        db.query(Customer)
        .filter(
            Customer.id == customer_id,
            Customer.tenant_id == tenant_id
        )
        .first()
    )

    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    customer.status = "inactive"

    db.commit()
    db.refresh(customer)

    return customer

def get_customer_stats(db: Session, tenant_id: int):
    total_customers = (
        db.query(func.count(Customer.id))
        .filter(Customer.tenant_id == tenant_id)
        .scalar()
    )

    active_customers = (
        db.query(func.count(Customer.id))
        .filter(
            Customer.tenant_id == tenant_id,
            Customer.status == "active"
        )
        .scalar()
    )

    current_month = datetime.now().month
    current_year = datetime.now().year

    vip_customers = (
    db.query(Customer)
    .filter(
        Customer.tenant_id == tenant_id,
        Customer.total_spend > 50000
    )
    .count()
)

    new_this_month = (
        db.query(func.count(Customer.id))
        .filter(
            Customer.tenant_id == tenant_id,
            func.extract("month", Customer.created_at) == current_month,
            func.extract("year", Customer.created_at) == current_year,
        )
        .scalar()
    )

    total_revenue = (
        db.query(func.coalesce(func.sum(Order.total_amount), 0))
        .filter(Order.tenant_id == tenant_id)
        .scalar()
    )

    return {
        "total_customers": total_customers,
        "active_customers": active_customers,
        "total_revenue": int(total_revenue),
        "new_this_month": new_this_month,
        "vip_customers": vip_customers
    }

def get_customers_for_export(db: Session, tenant_id: int, status="all"):
    query = db.query(Customer).filter(
        Customer.tenant_id == tenant_id
    )

    if status == "active":
        query = query.filter(Customer.status == "active")

    elif status == "inactive":
        query = query.filter(Customer.status == "inactive")

    return query.all()