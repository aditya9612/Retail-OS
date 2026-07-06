from datetime import datetime, timedelta
from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.models.customer import Customer


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
