from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.order_return import OrderReturn


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

        statement = select(OrderReturn).where(
            OrderReturn.id == return_id,
            OrderReturn.tenant_id == tenant_id,
        )

        return db.scalar(statement)

    @staticmethod
    def list(
        db: Session,
        tenant_id: int,
        skip: int = 0,
        limit: int = 20,
    ) -> list[OrderReturn]:

        statement = (
            select(OrderReturn)
            .where(OrderReturn.tenant_id == tenant_id)
            .order_by(OrderReturn.id.desc())
            .offset(skip)
            .limit(limit)
        )

        return list(db.scalars(statement).all())

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