from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_permission
from app.models.user import User
from app.schemas.review import (
    ReviewCreate,
    ReviewListResponse,
    ReviewReplyRequest,
    ReviewResponse,
    ReviewStatusUpdate,
    ReviewSummaryResponse,
    ReviewUpdate,
)
from app.services.review_service import ReviewService


router = APIRouter(
    prefix="/reviews",
    tags=["reviews"],
)


@router.post(
    "",
    response_model=ReviewResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Review",
    description="Customer leaves a rating and review for a product or store.",
)
def create_review(
    data: ReviewCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("reviews:write")),
):
    service = ReviewService(db)
    return service.create(
        data=data,
        tenant_id=user.tenant_id,
        current_user=user,
    )


@router.get(
    "",
    response_model=ReviewListResponse,
    summary="List Reviews",
    description="List all customer reviews across products and stores with optional filters and pagination.",
)
def list_reviews(
    product_id: Optional[int] = Query(None, description="Filter by product ID"),
    store_id: Optional[int] = Query(None, description="Filter by store ID"),
    rating: Optional[int] = Query(None, ge=1, le=5, description="Filter by star rating (1-5)"),
    status: Optional[str] = Query(None, description="Filter by review status (approved, pending, rejected, hidden)"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("reviews:read")),
):
    service = ReviewService(db)
    return service.list_reviews(
        tenant_id=user.tenant_id,
        product_id=product_id,
        store_id=store_id,
        rating=rating,
        status_filter=status,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/product/{product_id}",
    response_model=ReviewListResponse,
    summary="Get Product Reviews",
    description="Get paginated customer reviews and ratings for a specific product with optional star filter.",
)
def get_product_reviews(
    product_id: int,
    rating: Optional[int] = Query(None, ge=1, le=5, description="Filter by star rating (1-5)"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("reviews:read")),
):
    service = ReviewService(db)
    return service.get_by_product(
        product_id=product_id,
        tenant_id=user.tenant_id,
        rating=rating,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/product/{product_id}/summary",
    response_model=ReviewSummaryResponse,
    summary="Get Product Review Summary",
    description="Get product review statistics including average rating and star breakdown (1 to 5 stars).",
)
def get_product_review_summary(
    product_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("reviews:read")),
):
    service = ReviewService(db)
    return service.get_summary(
        target_type="product",
        target_id=product_id,
        tenant_id=user.tenant_id,
    )


@router.get(
    "/store/{store_id}",
    response_model=ReviewListResponse,
    summary="Get Store Reviews",
    description="Get paginated customer reviews and ratings for a specific retail store.",
)
def get_store_reviews(
    store_id: int,
    rating: Optional[int] = Query(None, ge=1, le=5, description="Filter by star rating (1-5)"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("reviews:read")),
):
    service = ReviewService(db)
    return service.get_by_store(
        store_id=store_id,
        tenant_id=user.tenant_id,
        rating=rating,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/store/{store_id}/summary",
    response_model=ReviewSummaryResponse,
    summary="Get Store Review Summary",
    description="Get store review statistics including average rating and star breakdown (1 to 5 stars).",
)
def get_store_review_summary(
    store_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("reviews:read")),
):
    service = ReviewService(db)
    return service.get_summary(
        target_type="store",
        target_id=store_id,
        tenant_id=user.tenant_id,
    )


@router.get(
    "/{review_id}",
    response_model=ReviewResponse,
    summary="Get Review",
    description="Get a single review by ID with customer, product, store, and reply details.",
)
def get_review(
    review_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("reviews:read")),
):
    service = ReviewService(db)
    return service.get_by_id(
        review_id=review_id,
        tenant_id=user.tenant_id,
    )


@router.patch(
    "/{review_id}",
    response_model=ReviewResponse,
    summary="Update Review",
    description="Update review rating or comment. Sets is_edited flag to true.",
)
def update_review(
    review_id: int,
    data: ReviewUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("reviews:write")),
):
    service = ReviewService(db)
    return service.update(
        review_id=review_id,
        data=data,
        tenant_id=user.tenant_id,
        current_user=user,
    )


@router.delete(
    "/{review_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Review",
    description="Soft-delete a customer review.",
)
def delete_review(
    review_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("reviews:write")),
):
    service = ReviewService(db)
    service.delete(
        review_id=review_id,
        tenant_id=user.tenant_id,
        current_user=user,
    )
    return None


@router.post(
    "/{review_id}/reply",
    response_model=ReviewResponse,
    summary="Reply to Review",
    description="Merchant or store admin responds to a customer review.",
)
def reply_to_review(
    review_id: int,
    data: ReviewReplyRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("reviews:write")),
):
    service = ReviewService(db)
    return service.reply(
        review_id=review_id,
        data=data,
        tenant_id=user.tenant_id,
        current_user=user,
    )


@router.patch(
    "/{review_id}/status",
    response_model=ReviewResponse,
    summary="Update Review Status",
    description="Moderate a review by changing its status (approved, pending, rejected, hidden).",
)
def update_review_status(
    review_id: int,
    data: ReviewStatusUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("reviews:write")),
):
    service = ReviewService(db)
    return service.update_status(
        review_id=review_id,
        data=data,
        tenant_id=user.tenant_id,
        current_user=user,
    )
