from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.product import Product
from app.models.review import Review
from app.models.store import Store
from app.models.storefront_setting import StorefrontSetting
from app.models.user import User
from app.repositories.review_repo import ReviewRepository
from app.schemas.review import (
    RatingBreakdown,
    ReviewCreate,
    ReviewListResponse,
    ReviewReplyRequest,
    ReviewResponse,
    ReviewStatusUpdate,
    ReviewSummaryResponse,
    ReviewUpdate,
)


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

        if customer.status != "active":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Customer account is inactive",
            )

        return customer

    def _get_store(
        self,
        store_id: int,
        tenant_id: int,
    ) -> Store:
        store = (
            self.db.query(Store)
            .filter(
                Store.id == store_id,
                Store.tenant_id == tenant_id,
            )
            .first()
        )

        if not store:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Store not found",
            )

        if not store.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Store is inactive",
            )

        return store

    def _check_storefront_reviews_enabled(
        self,
        tenant_id: int,
        store_id: Optional[int] = None,
    ) -> None:
        query = self.db.query(StorefrontSetting).filter(
            StorefrontSetting.tenant_id == tenant_id
        )
        if store_id is not None:
            setting = query.filter(StorefrontSetting.store_id == store_id).first()
            if not setting:
                setting = (
                    self.db.query(StorefrontSetting)
                    .filter(
                        StorefrontSetting.tenant_id == tenant_id,
                        StorefrontSetting.store_id.is_(None),
                    )
                    .first()
                )
        else:
            setting = query.first()

        if setting and not setting.enable_product_reviews:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Product reviews are disabled for this store/organization",
            )

    def _check_verified_purchase(
        self,
        tenant_id: int,
        customer_id: int,
        product_id: Optional[int],
        store_id: Optional[int],
        order_id: Optional[int],
    ) -> tuple[bool, Optional[int]]:
        valid_statuses = ["completed", "delivered", "paid"]

        # 1. If explicit order_id was provided
        if order_id:
            order = (
                self.db.query(Order)
                .filter(
                    Order.id == order_id,
                    Order.tenant_id == tenant_id,
                    Order.customer_id == customer_id,
                )
                .first()
            )
            if not order:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Order {order_id} does not belong to this customer or tenant",
                )

            if order.status.lower() not in valid_statuses:
                return False, order_id

            if product_id:
                has_item = (
                    self.db.query(OrderItem)
                    .filter(
                        OrderItem.order_id == order.id,
                        OrderItem.product_id == product_id,
                    )
                    .first()
                )
                if not has_item:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Order {order_id} does not contain product {product_id}",
                    )

            return True, order_id

        # 2. Auto-detect verified purchase if order_id was not provided
        if product_id:
            matched_order = (
                self.db.query(Order)
                .join(OrderItem, OrderItem.order_id == Order.id)
                .filter(
                    Order.tenant_id == tenant_id,
                    Order.customer_id == customer_id,
                    Order.status.in_(valid_statuses),
                    OrderItem.product_id == product_id,
                )
                .first()
            )
            if matched_order:
                return True, matched_order.id

        if store_id:
            matched_order = (
                self.db.query(Order)
                .filter(
                    Order.tenant_id == tenant_id,
                    Order.customer_id == customer_id,
                    Order.store_id == store_id,
                    Order.status.in_(valid_statuses),
                )
                .first()
            )
            if matched_order:
                return True, matched_order.id

        return False, None

    def create(
        self,
        data: ReviewCreate,
        tenant_id: int,
        current_user: Optional[User] = None,
    ) -> Review:
        # Validate Customer
        self._get_customer(
            data.customer_id,
            tenant_id,
        )

        # Validate Target (Product or Store)
        if data.product_id:
            self._get_product(
                data.product_id,
                tenant_id,
            )
            # Check storefront reviews toggle
            self._check_storefront_reviews_enabled(
                tenant_id,
                data.store_id,
            )
            # Duplicate check
            existing = self.repo.find_existing_review(
                tenant_id=tenant_id,
                customer_id=data.customer_id,
                product_id=data.product_id,
            )
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Customer has already submitted a review for this product",
                )

        if data.store_id:
            self._get_store(
                data.store_id,
                tenant_id,
            )
            if not data.product_id:
                # Store-level feedback duplicate check
                existing = self.repo.find_existing_review(
                    tenant_id=tenant_id,
                    customer_id=data.customer_id,
                    store_id=data.store_id,
                )
                if existing:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Customer has already submitted a review for this store",
                    )

        # Verified purchase check
        is_verified, linked_order_id = self._check_verified_purchase(
            tenant_id=tenant_id,
            customer_id=data.customer_id,
            product_id=data.product_id,
            store_id=data.store_id,
            order_id=data.order_id,
        )

        review = Review(
            tenant_id=tenant_id,
            product_id=data.product_id,
            store_id=data.store_id,
            customer_id=data.customer_id,
            order_id=data.order_id or linked_order_id,
            rating=data.rating,
            comment=data.comment,
            is_verified_purchase=is_verified,
            status="approved",
            is_edited=False,
            is_deleted=False,
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

    def list_reviews(
        self,
        tenant_id: int,
        product_id: Optional[int] = None,
        store_id: Optional[int] = None,
        rating: Optional[int] = None,
        status_filter: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> ReviewListResponse:
        if rating is not None and (rating < 1 or rating > 5):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Rating must be between 1 and 5",
            )

        page = max(1, page)
        page_size = min(max(1, page_size), 100)

        total, items = self.repo.list_reviews(
            tenant_id=tenant_id,
            product_id=product_id,
            store_id=store_id,
            rating=rating,
            status=status_filter,
            page=page,
            page_size=page_size,
        )

        return ReviewListResponse(
            total=total,
            page=page,
            page_size=page_size,
            items=[ReviewResponse.model_validate(r) for r in items],
        )

    def get_by_product(
        self,
        product_id: int,
        tenant_id: int,
        rating: Optional[int] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> ReviewListResponse:
        if product_id <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Product ID must be a positive integer",
            )

        self._get_product(
            product_id,
            tenant_id,
        )

        return self.list_reviews(
            tenant_id=tenant_id,
            product_id=product_id,
            rating=rating,
            page=page,
            page_size=page_size,
        )

    def get_by_store(
        self,
        store_id: int,
        tenant_id: int,
        rating: Optional[int] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> ReviewListResponse:
        if store_id <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Store ID must be a positive integer",
            )

        self._get_store(
            store_id,
            tenant_id,
        )

        return self.list_reviews(
            tenant_id=tenant_id,
            store_id=store_id,
            rating=rating,
            page=page,
            page_size=page_size,
        )

    def get_summary(
        self,
        target_type: str,
        target_id: int,
        tenant_id: int,
    ) -> ReviewSummaryResponse:
        if target_id <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Target ID must be a positive integer",
            )

        target_type_clean = target_type.strip().lower()

        if target_type_clean == "product":
            self._get_product(target_id, tenant_id)
            res = self.repo.get_summary(
                tenant_id=tenant_id,
                product_id=target_id,
            )
        elif target_type_clean == "store":
            self._get_store(target_id, tenant_id)
            res = self.repo.get_summary(
                tenant_id=tenant_id,
                store_id=target_id,
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Target type must be either 'product' or 'store'",
            )

        return ReviewSummaryResponse(
            target_type=target_type_clean,
            target_id=target_id,
            total_reviews=res["total_reviews"],
            average_rating=res["average_rating"],
            rating_breakdown=RatingBreakdown(**res["rating_breakdown"]),
        )

    def update(
        self,
        review_id: int,
        data: ReviewUpdate,
        tenant_id: int,
        current_user: Optional[User] = None,
    ) -> Review:
        review = self.get_by_id(
            review_id,
            tenant_id,
        )

        update_data = data.model_dump(
            exclude_unset=True,
        )

        if not update_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least one field must be provided for update",
            )

        update_data["is_edited"] = True

        return self.repo.update(
            review,
            update_data,
        )

    def delete(
        self,
        review_id: int,
        tenant_id: int,
        current_user: Optional[User] = None,
    ) -> None:
        review = self.get_by_id(
            review_id,
            tenant_id,
        )

        self.repo.soft_delete(review)

    def reply(
        self,
        review_id: int,
        data: ReviewReplyRequest,
        tenant_id: int,
        current_user: User,
    ) -> Review:
        review = self.get_by_id(
            review_id,
            tenant_id,
        )

        review.merchant_reply = data.merchant_reply
        review.replied_at = datetime.now(timezone.utc)
        review.replied_by = current_user.id

        self.db.commit()
        self.db.refresh(review)
        return review

    def update_status(
        self,
        review_id: int,
        data: ReviewStatusUpdate,
        tenant_id: int,
        current_user: Optional[User] = None,
    ) -> Review:
        review = self.get_by_id(
            review_id,
            tenant_id,
        )

        review.status = data.status

        self.db.commit()
        self.db.refresh(review)
        return review
