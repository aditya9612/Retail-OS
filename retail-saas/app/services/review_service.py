from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.product import Product
from app.models.review import Review
from app.repositories.review_repo import ReviewRepository
from app.schemas.review import ReviewCreate, ReviewUpdate


class ReviewService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = ReviewRepository(db)

    def _get_product(
        self,
        product_id: int,
        tenant_id: int,
    ) -> Product:
        product = (
            self.db.query(Product)
            .filter(
                Product.id == product_id,
                Product.tenant_id == tenant_id,
            )
            .first()
        )

        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found",
            )

        if not product.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot create review for inactive product",
            )

        return product

    def _get_customer(
        self,
        customer_id: int,
        tenant_id: int,
    ) -> Customer:
        customer = (
            self.db.query(Customer)
            .filter(
                Customer.id == customer_id,
                Customer.tenant_id == tenant_id,
            )
            .first()
        )

        if not customer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Customer not found",
            )

        return customer

    def create(
        self,
        data: ReviewCreate,
        tenant_id: int,
    ) -> Review:

        self._get_product(
            data.product_id,
            tenant_id,
        )

        self._get_customer(
            data.customer_id,
            tenant_id,
        )

        review = Review(
            tenant_id=tenant_id,
            product_id=data.product_id,
            customer_id=data.customer_id,
            rating=data.rating,
            comment=data.comment,
        )

        return self.repo.create(review)

    def get_by_id(
        self,
        review_id: int,
        tenant_id: int,
    ) -> Review:

        if review_id <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Review ID must be a positive integer",
            )

        review = self.repo.get_by_id(
            review_id,
            tenant_id,
        )

        if not review:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Review not found",
            )

        return review

    def get_by_product(
        self,
        product_id: int,
        tenant_id: int,
    ) -> list[Review]:

        if product_id <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Product ID must be a positive integer",
            )

        self._get_product(
            product_id,
            tenant_id,
        )

        return self.repo.get_by_product(
            product_id,
            tenant_id,
        )

    def update(
        self,
        review_id: int,
        data: ReviewUpdate,
        tenant_id: int,
    ) -> Review:

        review = self.get_by_id(
            review_id,
            tenant_id,
        )

        update_data = data.model_dump(
            exclude_unset=True
        )

        if not update_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least one field must be provided for update",
            )

        return self.repo.update(
            review,
            update_data,
        )

    def delete(
        self,
        review_id: int,
        tenant_id: int,
    ) -> None:

        review = self.get_by_id(
            review_id,
            tenant_id,
        )

        self.repo.delete(review)