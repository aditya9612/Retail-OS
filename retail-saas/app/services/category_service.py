from sqlalchemy.orm import Session

from app.repositories.category_repo import CategoryRepository
from app.schemas.category import CategoryCreate, CategoryUpdate


class CategoryService:

    def __init__(self, db: Session):
        self.repository = CategoryRepository(db)

    def create_category(
        self,
        tenant_id: int,
        data: CategoryCreate,
    ):
        return self.repository.create(
            tenant_id=tenant_id,
            name=data.name,
            description=data.description,
            parent_id=data.parent_id,
        )

    def list_categories(
        self,
        tenant_id: int,
    ):
        return self.repository.get_all(tenant_id)

    def get_category(
        self,
        tenant_id: int,
        category_id: int,
    ):
        return self.repository.get_by_id(
            tenant_id=tenant_id,
            category_id=category_id,
        )    

    def update_category(
        self,
        tenant_id: int,
        category_id: int,
        data: CategoryUpdate,
    ):
        category = self.repository.get_by_id(
            tenant_id=tenant_id,
            category_id=category_id,
        )

        if not category:
            return None

        return self.repository.update(
            category=category,
            name=data.name,
            description=data.description,
            parent_id=data.parent_id,
        )    

    def delete_category(
        self,
        tenant_id: int,
        category_id: int,
    ):
        category = self.repository.get_by_id(
            tenant_id=tenant_id,
            category_id=category_id,
        )

        if not category:
            return None

        self.repository.delete(category)

        return category    