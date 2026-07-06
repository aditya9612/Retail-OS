from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from fastapi import Path

from typing import Optional
from fastapi import Query
from app.services.customer_service import fetch_customers
from app.services.order_service import CustomerService, OrderService


from app.core.database import get_db
from app.core.security import require_permission
from app.models.user import User
from app.schemas.customer import CustomerCreate, CustomerResponse, CustomerUpdate , MessageResponse

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get("", response_model=list[CustomerResponse])
def list_customers(
    name: Optional[str] = Query(None, min_length=2, max_length=100),
    mobile: Optional[str] = Query(None, pattern=r"^[6-9]\d{9}$"),
    segment: Optional[str] = Query(
        None,
        pattern="^(new|regular|vip|inactive)$"
    ),
    user: User = Depends(require_permission("customers:read")),
    db: Session = Depends(get_db),
):
    return fetch_customers(
        db=db,
        tenant_id=user.tenant_id,
        name=name,
        mobile=mobile,
        segment=segment
    )


@router.post("", response_model=CustomerResponse, status_code=201)
def create_customer(
    data: CustomerCreate,
    user: User = Depends(require_permission("customers:write")),
    db: Session = Depends(get_db),
):
    return CustomerService(db).create_customer(user.tenant_id, data)


@router.get("/{customer_id}", response_model=CustomerResponse)
def get_customer(
    customer_id: int,
    user: User = Depends(require_permission("customers:read")),
    db: Session = Depends(get_db),
):
    return CustomerService(db).get_customer(user.tenant_id, customer_id)


@router.patch("/{customer_id}", response_model=CustomerResponse)
def update_customer(
    customer_id: int,
    data: CustomerUpdate,
    user: User = Depends(require_permission("customers:write")),
    db: Session = Depends(get_db),
):
    return CustomerService(db).update_customer(user.tenant_id, customer_id, data)


@router.get("/{customer_id}/orders")
def customer_orders(
    customer_id: int = Path(..., gt=0),
    user: User = Depends(require_permission("customers:read")),
    db: Session = Depends(get_db),
):
    return OrderService(db).get_customer_history(user.tenant_id, customer_id)


@router.post("/{customer_id}/loyalty")
def add_loyalty(
    customer_id: int = Path(..., gt=0),
    points: int = Query(..., gt=0, le=10000),
    user: User = Depends(require_permission("customers:write")),
    db: Session = Depends(get_db),
):
    return CustomerService(db).add_loyalty_points(user.tenant_id, customer_id, points)


@router.delete("/{customer_id}", response_model=MessageResponse)
def delete_customer(
    customer_id: int,
    user: User = Depends(require_permission("customers:write")),
    db: Session = Depends(get_db),
):
    return CustomerService(db).delete_customer(
        user.tenant_id,
        customer_id
    )




