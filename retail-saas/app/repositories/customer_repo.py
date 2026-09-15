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
        query = query.filter(func.lower(Customer.status) == status.strip().lower())

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
        seg_lower = segment.strip().lower()
        if seg_lower == "vip":
            query = query.filter(Customer.total_spend > 50000)
        elif seg_lower == "active":
            query = query.filter(func.lower(Customer.status) == "active")
        elif seg_lower == "inactive":
            query = query.filter(func.lower(Customer.status) == "inactive")
        elif seg_lower == "new":
            last_30_days = datetime.utcnow() - timedelta(days=30)
            query = query.filter(Customer.created_at >= last_30_days)
        elif seg_lower == "regular":
            query = query.filter(func.lower(Customer.segment) == "regular")

    query = query.order_by(Customer.id.desc())

    if page is not None or page_size is not None:
        p = page if (page is not None and page >= 1) else 1
        ps = page_size if (page_size is not None and page_size >= 1) else 20
        skip = (p - 1) * ps
        query = query.offset(skip).limit(ps)

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

    inactive_customers = (
        db.query(func.count(Customer.id))
        .filter(
            Customer.tenant_id == tenant_id,
            Customer.status == "inactive"
        )
        .scalar()
    ) or 0

    blocked_customers = (
        db.query(func.count(Customer.id))
        .filter(
            Customer.tenant_id == tenant_id,
            Customer.status == "blocked"
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
            or_(
                Customer.segment == "vip",
                Customer.total_spend > 50000,
            ),
        )
        .scalar()
    ) or 0

    regular_customers = (
        db.query(func.count(Customer.id))
        .filter(
            Customer.tenant_id == tenant_id,
            Customer.segment == "regular",
            Customer.total_spend <= 50000,
        )
        .scalar()
    ) or 0

    new_customers = (
        db.query(func.count(Customer.id))
        .filter(
            Customer.tenant_id == tenant_id,
            Customer.segment == "new",
            Customer.total_spend <= 50000,
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
        "inactive_customers": int(inactive_customers),
        "blocked_customers": int(blocked_customers),
        "new_customers": int(new_customers),
        "regular_customers": int(regular_customers),
        "vip_customers": int(vip_customers),
        "new_this_month": int(new_this_month),
        "total_revenue": int(total_revenue),
    }


def get_customers_for_export(db: Session, tenant_id: int, status="all"):
    query = db.query(Customer).filter(
        Customer.tenant_id == tenant_id
    )

    if status and status != "all":
        query = query.filter(Customer.status == status)

    return query.order_by(Customer.id.asc()).all()