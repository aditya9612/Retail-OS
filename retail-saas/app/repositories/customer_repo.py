from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional
from app.core.exceptions import AppException
from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import case, func, or_

from app.models.customer import Customer
from app.models.order import Order
from app.utils.pagination import paginate_query


def _build_filtered_customers_query(
    db: Session,
    tenant_id: int,
    name: Optional[str] = None,
    mobile: Optional[str] = None,
    segment: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
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

    return query.order_by(Customer.id.desc())


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
    query = _build_filtered_customers_query(
        db=db,
        tenant_id=tenant_id,
        name=name,
        mobile=mobile,
        segment=segment,
        status=status,
        search=search,
    )

    if page is not None or page_size is not None:
        p = page if (page is not None and page >= 1) else 1
        ps = page_size if (page_size is not None and page_size >= 1) else 20
        skip = (p - 1) * ps
        query = query.offset(skip).limit(ps)

    return query.all()


def get_customer_counts(db: Session, tenant_id: int) -> dict[str, int]:
    """Return tenant-level customer status and segment counts in one query."""
    row = (
        db.query(
            func.count(Customer.id).label("total"),
            func.count(case((Customer.status == "active", 1))).label("active"),
            func.count(case((Customer.status == "inactive", 1))).label("inactive"),
            func.count(case((Customer.status == "blocked", 1))).label("blocked"),
            func.count(case(((Customer.segment == "new") & (Customer.total_spend <= 50000), 1))).label("new"),
            func.count(case(((Customer.segment == "regular") & (Customer.total_spend <= 50000), 1))).label("regular"),
            func.count(case((or_(Customer.segment == "vip", Customer.total_spend > 50000), 1))).label("vip"),
        )
        .filter(Customer.tenant_id == tenant_id)
        .one()
    )
    return {
        "total": int(row.total or 0),
        "active": int(row.active or 0),
        "inactive": int(row.inactive or 0),
        "blocked": int(row.blocked or 0),
        "new": int(row.new or 0),
        "regular": int(row.regular or 0),
        "vip": int(row.vip or 0),
    }


def get_filtered_customers_with_counts(
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
    query = _build_filtered_customers_query(
        db=db,
        tenant_id=tenant_id,
        name=name,
        mobile=mobile,
        segment=segment,
        status=status,
        search=search,
    )
    items, total, eff_page, eff_size, total_pages = paginate_query(
        query, page=page, page_size=page_size
    )
    counts = get_customer_counts(db, tenant_id)
    return items, total, eff_page, eff_size, total_pages, counts


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

    if customer.outstanding_balance and customer.outstanding_balance > Decimal("0.00"):
        raise AppException("Cannot deactivate customer with outstanding dues")

    customer.status = "inactive"

    db.commit()
    db.refresh(customer)

    return customer


def get_customer_stats(db: Session, tenant_id: int):
    counts = get_customer_counts(db, tenant_id)
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

    total_revenue = (
        db.query(func.coalesce(func.sum(Order.total_amount), 0))
        .filter(Order.tenant_id == tenant_id)
        .scalar()
    ) or 0

    return {
        "total_customers": counts["total"],
        "active_customers": counts["active"],
        "inactive_customers": counts["inactive"],
        "blocked_customers": counts["blocked"],
        "new_customers": counts["new"],
        "regular_customers": counts["regular"],
        "vip_customers": counts["vip"],
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
