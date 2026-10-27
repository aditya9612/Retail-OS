from typing import Optional
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
        include_deleted: bool = False,
    ) -> Optional[Review]:
        query = self.db.query(Review).filter(
            Review.id == review_id,
            Review.tenant_id == tenant_id,
        )
        if not include_deleted:
            query = query.filter(Review.is_deleted.is_(False))
        return query.first()

    def find_existing_review(
        self,
        tenant_id: int,
        customer_id: int,
        product_id: Optional[int] = None,
        store_id: Optional[int] = None,
    ) -> Optional[Review]:
        query = self.db.query(Review).filter(
            Review.tenant_id == tenant_id,
            Review.customer_id == customer_id,
            Review.is_deleted.is_(False),
        )
        if product_id is not None:
            query = query.filter(Review.product_id == product_id)
        elif store_id is not None:
            query = query.filter(
                Review.store_id == store_id,
                Review.product_id.is_(None),
            )
        return query.first()

    def list_reviews(
        self,
        tenant_id: int,
        product_id: Optional[int] = None,
        store_id: Optional[int] = None,
        rating: Optional[int] = None,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[int, list[Review]]:
        query = self.db.query(Review).filter(
            Review.tenant_id == tenant_id,
            Review.is_deleted.is_(False),
        )

        if product_id is not None:
            query = query.filter(Review.product_id == product_id)

        if store_id is not None:
            query = query.filter(Review.store_id == store_id)

        if rating is not None:
            query = query.filter(Review.rating == rating)

        if status is not None:
            query = query.filter(Review.status == status)

        total = query.count()

        offset = max(0, (page - 1) * page_size)
        items = (
            query.order_by(Review.created_at.desc())
            .offset(offset)
            .limit(page_size)
            .all()
        )

        return total, items

    def get_summary(
        self,
        tenant_id: int,
        product_id: Optional[int] = None,
        store_id: Optional[int] = None,
    ) -> dict:
        query = self.db.query(Review).filter(
            Review.tenant_id == tenant_id,
            Review.is_deleted.is_(False),
            Review.status == "approved",
        )

        if product_id is not None:
            query = query.filter(Review.product_id == product_id)
        elif store_id is not None:
            query = query.filter(
                Review.store_id == store_id,
                Review.product_id.is_(None),
            )

        reviews = query.all()
        total = len(reviews)
        if total == 0:
            return {
                "total_reviews": 0,
                "average_rating": 0.0,
                "rating_breakdown": {
                    "star_1": 0,
                    "star_2": 0,
                    "star_3": 0,
                    "star_4": 0,
                    "star_5": 0,
                },
            }

        breakdown = {f"star_{i}": 0 for i in range(1, 6)}
        sum_rating = 0
        for r in reviews:
            sum_rating += r.rating
            if 1 <= r.rating <= 5:
                breakdown[f"star_{r.rating}"] += 1

        avg = round(sum_rating / total, 2)

        return {
            "total_reviews": total,
            "average_rating": avg,
            "rating_breakdown": breakdown,
        }

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

    def soft_delete(self, review: Review) -> None:
        review.is_deleted = True
        self.db.commit()
        self.db.refresh(review)

    def delete(self, review: Review) -> None:
        self.soft_delete(review)
