from sqlalchemy.orm import Session
from app.repositories.customer_repo import get_filtered_customers ,  get_customer_stats

def fetch_customers(
    db: Session,
    tenant_id: int,
    name=None,
    mobile=None,
    segment=None,
):
    return get_filtered_customers(
        db=db,
        tenant_id=tenant_id,
        name=name,
        mobile=mobile,
        segment=segment,
    )

def fetch_customer_stats(
    db: Session,
    tenant_id: int,
):
    return get_customer_stats(
        db=db,
        tenant_id=tenant_id,
    )    

  