from typing import Optional
from sqlalchemy.orm import Session, joinedload
from app.models.grn import GRN


class GRNRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, grn: GRN) -> GRN:
        self.db.add(grn)
        self.db.commit()
        self.db.refresh(grn)
        return grn

    def list(
        self,
        tenant_id: int,
        purchase_order_id: Optional[int] = None,
        warehouse_id: Optional[int] = None,
        status: Optional[str] = None,
    ) -> list[GRN]:
        query = (
            self.db.query(GRN)
            .options(
                joinedload(GRN.items),
                joinedload(GRN.purchase_order),
                joinedload(GRN.warehouse),
            )
            .filter(GRN.tenant_id == tenant_id)
        )
        if purchase_order_id is not None:
            query = query.filter(GRN.purchase_order_id == purchase_order_id)
        if warehouse_id is not None:
            query = query.filter(GRN.warehouse_id == warehouse_id)
        if status:
            query = query.filter(GRN.status == status)

        return query.order_by(GRN.created_at.desc()).all()

    def get_by_id(
        self,
        grn_id: int,
        tenant_id: int,
    ) -> GRN | None:
        return (
            self.db.query(GRN)
            .options(
                joinedload(GRN.items),
                joinedload(GRN.purchase_order),
                joinedload(GRN.warehouse),
            )
            .filter(
                GRN.id == grn_id,
                GRN.tenant_id == tenant_id,
            )
            .first()
        )

    def update(
        self,
        grn: GRN,
    ) -> GRN:
        self.db.commit()
        self.db.refresh(grn)
        return grn

    def delete(
        self,
        grn: GRN,
    ) -> None:
        self.db.delete(grn)
        self.db.commit()
