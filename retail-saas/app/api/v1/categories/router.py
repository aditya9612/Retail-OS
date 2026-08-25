from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_permission
from app.models.category import Category
from app.models.user import User
from app.schemas.product import CategoryCreate, CategoryResponse
from app.services.category_service import CategoryService


router = APIRouter(prefix="/categories", tags=["categories"])


@router.post(
    "",
    response_model=CategoryResponse,
    status_code=201,
)
def create_category(
    data: CategoryCreate,
    user: User = Depends(require_permission("products:write")),
    db: Session = Depends(get_db),
):
    category = Category(
        tenant_id=user.tenant_id,
        **data.model_dump(),
    )

    db.add(category)
    db.commit()
    db.refresh(category)

    return category


@router.get(
    "",
    response_model=list[CategoryResponse],
)
def list_categories(
    user: User = Depends(require_permission("products:read")),
    db: Session = Depends(get_db),
):
    return (
        db.query(Category)
        .filter(Category.tenant_id == user.tenant_id)
        .all()
    )

@router.get("/{category_id}", response_model=CategoryResponse)
def get_category(
    category_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("categories:read")),
):
    return CategoryService(db).get_category(
        tenant_id=user.tenant_id,
        category_id=category_id,
    )