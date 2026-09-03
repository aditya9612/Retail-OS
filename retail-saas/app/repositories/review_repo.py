from sqlalchemy.orm import Session

from app.models.review import Review


class ReviewRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, review: Review) -> Review:
        self.db.add(review)
        self.db.commit()
        self.db.refresh(review)
        return review

    def get_by_id(
        self,
        review_id: int,
        tenant_id: int,
    ) -> Review | None:
        return (
            self.db.query(Review)
            .filter(
                Review.id == review_id,
                Review.tenant_id == tenant_id,
            )
            .first()
        )

    def get_by_product(
        self,
        product_id: int,
        tenant_id: int,
    ) -> list[Review]:
        return (
            self.db.query(Review)
            .filter(
                Review.product_id == product_id,
                Review.tenant_id == tenant_id,
            )
            .order_by(Review.created_at.desc())
            .all()
        )

    def update(
        self,
        review: Review,
        data: dict,
    ) -> Review:
        for key, value in data.items():
            setattr(review, key, value)

        self.db.commit()
        self.db.refresh(review)

        return review

    def delete(self, review: Review) -> None:
        self.db.delete(review)
        self.db.commit()