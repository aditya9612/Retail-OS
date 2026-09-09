from typing import Optional
from sqlalchemy.orm import Session
from app.repositories.customer_repo import get_filtered_customers, get_customer_stats


def fetch_customers(
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
    return get_filtered_customers(
        db=db,
        tenant_id=tenant_id,
        name=name,
        mobile=mobile,
        segment=segment,
        status=status,
        search=search,
        page=page,
        page_size=page_size,
    )


def fetch_customer_stats(
    db: Session,
    tenant_id: int,
):
    return get_customer_stats(
        db=db,
        tenant_id=tenant_id,
    )