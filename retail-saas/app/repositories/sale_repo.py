from sqlalchemy.orm import Session, joinedload
from app.models.sale import Sale


class SaleRepository:

    @staticmethod
    def create(
        db: Session,
        sale: Sale
    ):
        db.add(sale)
        db.commit()
        db.refresh(sale)
        return sale

    @staticmethod
    def get_by_id(
        db: Session,
        sale_id: int
    ):
        return (
            db.query(Sale)
            .options(joinedload(Sale.items))
            .filter(Sale.id == sale_id)
            .first()
        )

    @staticmethod
    def get_all(
        db: Session,
        store_id: int = None
    ):
        query = (
            db.query(Sale)
            .options(joinedload(Sale.items))
        )

        if store_id is not None:
            query = query.filter(Sale.store_id == store_id)

        return (
            query
            .order_by(Sale.id.desc())
            .all()
        )

    @staticmethod
    def update(
        db: Session,
        sale: Sale
    ):
        db.commit()
        db.refresh(sale)
        return sale

    @staticmethod
    def delete(
        db: Session,
        sale: Sale
    ):
        db.delete(sale)
        db.commit()