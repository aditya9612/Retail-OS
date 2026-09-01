from sqlalchemy.orm import Session

from app.models.category import Category


class CategoryRepository:

    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        tenant_id: int,
        name: str,
        description: str | None = None,
        parent_id: int | None = None,
    ) -> Category:

        category = Category(
            tenant_id=tenant_id,
            name=name,
            description=description,
            parent_id=parent_id,
        )

        self.db.add(category)
        self.db.commit()
        self.db.refresh(category)

        return category

    def get_all(self, tenant_id: int) -> list[Category]:
        return (
            self.db.query(Category)
            .filter(Category.tenant_id == tenant_id)
            .all()
        )

    def get_by_id(
        self,
        tenant_id: int,
        category_id: int,
    ) -> Category | None:

        return (
            self.db.query(Category)
            .filter(
                Category.id == category_id,
                Category.tenant_id == tenant_id,
            )
            .first()
        )    

    def update(
        self,
        category: Category,
        name: str | None = None,
        description: str | None = None,
        parent_id: int | None = None,
    ) -> Category:

        if name is not None:
            category.name = name

        if description is not None:
            category.description = description

        if parent_id is not None:
            category.parent_id = parent_id

        self.db.commit()
        self.db.refresh(category)

        return category    

    def delete(self, category: Category) -> None:
        self.db.delete(category)
        self.db.commit()    