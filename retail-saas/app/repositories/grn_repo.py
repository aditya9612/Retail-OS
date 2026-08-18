from sqlalchemy.orm import Session

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
    ) -> list[GRN]:

        return (
            self.db.query(GRN)
            .filter(
                GRN.tenant_id == tenant_id,
            )
            .order_by(GRN.created_at.desc())
            .all()
        )

    def get_by_id(
        self,
        grn_id: int,
        tenant_id: int,
    ) -> GRN | None:

        return (
            self.db.query(GRN)
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
    
    