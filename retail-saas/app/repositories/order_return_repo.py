from decimal import Decimal
from typing import Optional
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.customer import Customer
from app.models.order import Order
from app.models.order_return import OrderReturn, OrderReturnItem


class OrderReturnRepository:

    @staticmethod
    def create(
        db: Session,
        order_return: OrderReturn,
    ) -> OrderReturn:
        db.add(order_return)
        db.commit()
        db.refresh(order_return)
        return order_return

    @staticmethod
    def get_by_id(
        db: Session,
        return_id: int,
        tenant_id: int,
    ) -> OrderReturn | None:
        statement = (
            select(OrderReturn)
            .where(
                OrderReturn.id == return_id,
                OrderReturn.tenant_id == tenant_id,
            )
            .options(
                selectinload(OrderReturn.items).joinedload(OrderReturnItem.product),
                selectinload(OrderReturn.items).joinedload(OrderReturnItem.order_item),
                joinedload(OrderReturn.order),
                joinedload(OrderReturn.customer),
            )
        )
        return db.scalar(statement)

    @staticmethod
    def get_by_number(
        db: Session,
        return_number: str,
        tenant_id: int,
    ) -> OrderReturn | None:
        statement = (
            select(OrderReturn)
            .where(
                OrderReturn.return_number == return_number,
                OrderReturn.tenant_id == tenant_id,
            )
            .options(
                selectinload(OrderReturn.items).joinedload(OrderReturnItem.product),
                selectinload(OrderReturn.items).joinedload(OrderReturnItem.order_item),
                joinedload(OrderReturn.order),
                joinedload(OrderReturn.customer),
            )
        )
        return db.scalar(statement)

    @staticmethod
    def _apply_filters(
        query,
        tenant_id: int,
        store_id: Optional[int] = None,
        status: Optional[str] = None,
        customer_id: Optional[int] = None,
        order_id: Optional[int] = None,
        search: Optional[str] = None,
    ):
        query = query.where(OrderReturn.tenant_id == tenant_id)

        if store_id is not None:
            query = query.join(Order, OrderReturn.order_id == Order.id).where(Order.store_id == store_id)

        if status:
            query = query.where(OrderReturn.status == status.strip().lower())

        if customer_id is not None:
            query = query.where(OrderReturn.customer_id == customer_id)

        if order_id is not None:
            query = query.where(OrderReturn.order_id == order_id)

        if search:
            s = f"%{search.strip()}%"
            query = query.where(
                or_(
                    OrderReturn.return_number.ilike(s),
                    OrderReturn.reason.ilike(s),
                    OrderReturn.remarks.ilike(s),
                )
            )

        return query

    @staticmethod
    def list(
        db: Session,
        tenant_id: int,
        skip: int = 0,
        limit: int = 20,
        store_id: Optional[int] = None,
        status: Optional[str] = None,
        customer_id: Optional[int] = None,
        order_id: Optional[int] = None,
        search: Optional[str] = None,
    ) -> list[OrderReturn]:
        statement = select(OrderReturn)
        statement = OrderReturnRepository._apply_filters(
            statement,
            tenant_id=tenant_id,
            store_id=store_id,
            status=status,
            customer_id=customer_id,
            order_id=order_id,
            search=search,
        )
        statement = (
            statement
            .options(
                selectinload(OrderReturn.items).joinedload(OrderReturnItem.product),
                selectinload(OrderReturn.items).joinedload(OrderReturnItem.order_item),
                joinedload(OrderReturn.order),
                joinedload(OrderReturn.customer),
            )
            .order_by(OrderReturn.id.desc())
            .offset(skip)
            .limit(limit)
        )

        return list(db.scalars(statement).all())

    @staticmethod
    def count(
        db: Session,
        tenant_id: int,
        store_id: Optional[int] = None,
        status: Optional[str] = None,
        customer_id: Optional[int] = None,
        order_id: Optional[int] = None,
        search: Optional[str] = None,
    ) -> int:
        statement = select(func.count(OrderReturn.id))
        statement = OrderReturnRepository._apply_filters(
            statement,
            tenant_id=tenant_id,
            store_id=store_id,
            status=status,
            customer_id=customer_id,
            order_id=order_id,
            search=search,
        )
        return db.scalar(statement) or 0

    @staticmethod
    def get_stats(
        db: Session,
        tenant_id: int,
        store_id: Optional[int] = None,
    ) -> dict:
        query = select(
            OrderReturn.status,
            func.count(OrderReturn.id),
            func.sum(OrderReturn.refund_amount),
        ).where(OrderReturn.tenant_id == tenant_id)

        if store_id is not None:
            query = query.join(Order, OrderReturn.order_id == Order.id).where(Order.store_id == store_id)

        rows = db.execute(query.group_by(OrderReturn.status)).all()

        counts = {
            "requested": 0,
            "approved": 0,
            "completed": 0,
            "rejected": 0,
        }
        total_refund = Decimal("0.00")
        total_returns = 0

        for status_val, count_val, sum_val in rows:
            c = count_val or 0
            total_returns += c
            if status_val in counts:
                counts[status_val] = c
            if sum_val:
                total_refund += Decimal(str(sum_val))

        return {
            "total_returns": total_returns,
            "requested_count": counts["requested"],
            "approved_count": counts["approved"],
            "completed_count": counts["completed"],
            "rejected_count": counts["rejected"],
            "total_refund_amount": total_refund,
        }

    @staticmethod
    def update(
        db: Session,
        order_return: OrderReturn,
    ) -> OrderReturn:
        db.commit()
        db.refresh(order_return)
        return order_return

    @staticmethod
    def delete(
        db: Session,
        order_return: OrderReturn,
    ) -> None:
        db.delete(order_return)
        db.commit()
