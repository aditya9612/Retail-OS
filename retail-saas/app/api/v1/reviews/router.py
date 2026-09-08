from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_permission
from app.models.user import User
from app.schemas.review import (
    ReviewCreate,
    ReviewResponse,
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
)
def create_review(
    data: ReviewCreate,
    db: Session = Depends(get_db),
    user: User = Depends(
        require_permission("reviews:write")
    ),
):
    service = ReviewService(db)

    return service.create(
        data,
        user.tenant_id,
    )


@router.get(
    "/product/{product_id}",
    response_model=list[ReviewResponse],
)
def get_product_reviews(
    product_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(
        require_permission("reviews:read")
    ),
):
    service = ReviewService(db)

    return service.get_by_product(
        product_id,
        user.tenant_id,
    )


@router.get(
    "/{review_id}",
    response_model=ReviewResponse,
)
def get_review(
    review_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(
        require_permission("reviews:read")
    ),
):
    service = ReviewService(db)

    return service.get_by_id(
        review_id,
        user.tenant_id,
    )


@router.patch(
    "/{review_id}",
    response_model=ReviewResponse,
)
def update_review(
    review_id: int,
    data: ReviewUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(
        require_permission("reviews:write")
    ),
):
    service = ReviewService(db)

    return service.update(
        review_id,
        data,
        user.tenant_id,
    )


@router.delete(
    "/{review_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_review(
    review_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(
        require_permission("reviews:write")
    ),
):
    service = ReviewService(db)

    service.delete(
        review_id,
        user.tenant_id,
    )

    return None