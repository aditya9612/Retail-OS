from fastapi import status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AppException, ConflictException, NotFoundException
from app.models.category import Category
from app.models.product import Product
from app.repositories.category_repo import CategoryRepository
from app.schemas.category import CategoryCreate, CategoryUpdate


class CategoryService:

    def __init__(self, db: Session):
        self.db = db
        self.repository = CategoryRepository(db)

    def create_category(
        self,
        tenant_id: int,
        data: CategoryCreate,
    ) -> Category:
        if data.parent_id is not None:
            parent = self.repository.get_by_id(
                tenant_id=tenant_id,
                category_id=data.parent_id,
            )
            if not parent:
                raise NotFoundException("Parent category not found")

        try:
            return self.repository.create(
                tenant_id=tenant_id,
                name=data.name,
                description=data.description,
                parent_id=data.parent_id,
                is_active=getattr(data, "is_active", True),
            )
        except IntegrityError:
            self.db.rollback()
            raise ConflictException("Category could not be created due to database conflict")

    def list_categories(
        self,
        tenant_id: int,
    ) -> list[Category]:
        return self.repository.get_all(tenant_id)

    def get_category(
        self,
        tenant_id: int,
        category_id: int,
    ) -> Category:
        category = self.repository.get_by_id(
            tenant_id=tenant_id,
            category_id=category_id,
        )
        if not category:
            raise NotFoundException("Category not found")
        return category

    def update_category(
        self,
        tenant_id: int,
        category_id: int,
        data: CategoryUpdate,
    ) -> Category:
        category = self.repository.get_by_id(
            tenant_id=tenant_id,
            category_id=category_id,
        )
        if not category:
            raise NotFoundException("Category not found")

        if data.parent_id is not None:
            if data.parent_id == category_id:
                raise AppException(
                    detail="Category cannot be its own parent",
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                )
            parent = self.repository.get_by_id(
                tenant_id=tenant_id,
                category_id=data.parent_id,
            )
            if not parent:
                raise NotFoundException("Parent category not found")

        try:
            return self.repository.update(
                category=category,
                name=data.name,
                description=data.description,
                parent_id=data.parent_id,
                is_active=getattr(data, "is_active", None),
            )
        except IntegrityError:
            self.db.rollback()
            raise ConflictException("Category update conflict")

    def delete_category(
        self,
        tenant_id: int,
        category_id: int,
    ) -> dict:
        category = self.repository.get_by_id(
            tenant_id=tenant_id,
            category_id=category_id,
        )
        if not category:
            raise NotFoundException("Category not found")

        # Check for associated products
        product_count = (
            self.db.query(Product)
            .filter(
                Product.tenant_id == tenant_id,
                Product.category_id == category_id,
            )
            .count()
        )
        if product_count > 0:
            raise ConflictException(
                f"Cannot delete category: {product_count} product(s) are associated with it"
            )

        # Check for child subcategories
        child_count = (
            self.db.query(Category)
            .filter(
                Category.tenant_id == tenant_id,
                Category.parent_id == category_id,
            )
            .count()
        )
        if child_count > 0:
            raise ConflictException(
                f"Cannot delete category: {child_count} subcategory(ies) are associated with it"
            )

        try:
            self.repository.delete(category)
            return {"id": category_id}
        except IntegrityError:
            self.db.rollback()
            raise ConflictException(
                "Cannot delete category due to database constraints"
            )