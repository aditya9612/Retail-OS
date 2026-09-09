from datetime import datetime, timedelta
from typing import Optional
from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, or_

from app.models.customer import Customer
from app.models.order import Order


def get_filtered_customers(
    db: Session,
    tenant_id: int,
    name: Optional[str] = None,
    mobile: Optional[str] = None,
    segment: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    page: Optional[int] = None,
    page_size: Optional[int] = None,
):
    query = db.query(Customer).filter(Customer.tenant_id == tenant_id)

    if status:
        query = query.filter(Customer.status == status)

    if name:
        name_clean = name.strip()
        if name_clean:
            query = query.filter(Customer.name.ilike(f"%{name_clean}%"))

    if mobile:
        mobile_clean = mobile.strip()
        if mobile_clean:
            query = query.filter(Customer.phone.ilike(f"%{mobile_clean}%"))

    if search:
        search_clean = search.strip()
        if search_clean:
            query = query.filter(
                or_(
                    Customer.name.ilike(f"%{search_clean}%"),
                    Customer.phone.ilike(f"%{search_clean}%"),
                    Customer.email.ilike(f"%{search_clean}%"),
                )
            )

    if segment:
        if segment == "vip":
            query = query.filter(Customer.total_spend > 50000)
        elif segment == "active":
            query = query.filter(Customer.status == "active")
        elif segment == "inactive":
            query = query.filter(Customer.status == "inactive")
        elif segment == "new":
            last_30_days = datetime.utcnow() - timedelta(days=30)
            query = query.filter(Customer.created_at >= last_30_days)
        elif segment == "regular":
            query = query.filter(Customer.segment == "regular")

    query = query.order_by(Customer.id.desc())

    if page is not None and page_size is not None and page > 0 and page_size > 0:
        skip = (page - 1) * page_size
        query = query.offset(skip).limit(page_size)

    return query.all()


def delete_customer(db: Session, tenant_id: int, customer_id: int):
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
    ) or 0

    active_customers = (
        db.query(func.count(Customer.id))
        .filter(
            Customer.tenant_id == tenant_id,
            Customer.status == "active"
        )
        .scalar()
    ) or 0

    now = datetime.utcnow()
    start_of_month = datetime(now.year, now.month, 1)

    new_this_month = (
        db.query(func.count(Customer.id))
        .filter(
            Customer.tenant_id == tenant_id,
            Customer.created_at >= start_of_month,
        )
        .scalar()
    ) or 0

    vip_customers = (
        db.query(func.count(Customer.id))
        .filter(
            Customer.tenant_id == tenant_id,
            Customer.total_spend > 50000,
        )
        .scalar()
    ) or 0

    total_revenue = (
        db.query(func.coalesce(func.sum(Order.total_amount), 0))
        .filter(Order.tenant_id == tenant_id)
        .scalar()
    ) or 0

    return {
        "total_customers": int(total_customers),
        "active_customers": int(active_customers),
        "total_revenue": int(total_revenue),
        "new_this_month": int(new_this_month),
        "vip_customers": int(vip_customers),
    }


def get_customers_for_export(db: Session, tenant_id: int, status="all"):
    query = db.query(Customer).filter(
        Customer.tenant_id == tenant_id
    )

    if status and status != "all":
        query = query.filter(Customer.status == status)

    return query.order_by(Customer.id.asc()).all()