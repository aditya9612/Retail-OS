from typing import Optional
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.category import Category
from app.models.product import Product


class CategoryRepository:

    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        tenant_id: int,
        name: str,
        description: str | None = None,
        parent_id: int | None = None,
        is_active: bool = True,
    ) -> Category:

        category = Category(
            tenant_id=tenant_id,
            name=name,
            description=description,
            parent_id=parent_id,
            is_active=is_active,
        )

        self.db.add(category)
        self.db.commit()
        self.db.refresh(category)

        return category

    def get_all(
        self,
        tenant_id: int,
        search: Optional[str] = None,
        is_active: Optional[bool] = None,
        root_only: bool = False,
        parent_id: Optional[int] = None,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
    ) -> list[Category]:
        query = self.db.query(Category).filter(Category.tenant_id == tenant_id)

        if search:
            query = query.filter(Category.name.ilike(f"%{search.strip()}%"))

        if is_active is not None:
            query = query.filter(Category.is_active == is_active)

        if root_only:
            query = query.filter(Category.parent_id.is_(None))
        elif parent_id is not None:
            query = query.filter(Category.parent_id == parent_id)

        query = query.order_by(Category.name.asc())

        if page is not None and page_size is not None:
            query = query.offset((page - 1) * page_size).limit(page_size)

        return query.all()

    def count(
        self,
        tenant_id: int,
        search: Optional[str] = None,
        is_active: Optional[bool] = None,
        root_only: bool = False,
        parent_id: Optional[int] = None,
    ) -> int:
        query = self.db.query(Category).filter(Category.tenant_id == tenant_id)

        if search:
            query = query.filter(Category.name.ilike(f"%{search.strip()}%"))

        if is_active is not None:
            query = query.filter(Category.is_active == is_active)

        if root_only:
            query = query.filter(Category.parent_id.is_(None))
        elif parent_id is not None:
            query = query.filter(Category.parent_id == parent_id)

        return query.count()

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

    def get_by_name(
        self,
        tenant_id: int,
        name: str,
    ) -> Category | None:
        if not name:
            return None
        return (
            self.db.query(Category)
            .filter(
                Category.tenant_id == tenant_id,
                func.lower(Category.name) == func.lower(name.strip()),
            )
            .first()
        )    

    def update(
        self,
        category: Category,
        name: str | None = None,
        description: str | None = None,
        parent_id: int | None = None,
        is_active: bool | None = None,
        update_parent_id: bool = False,
        update_description: bool = False,
    ) -> Category:

        if name is not None:
            category.name = name

        if update_description:
            category.description = description
        elif description is not None:
            category.description = description

        if update_parent_id:
            category.parent_id = parent_id
        elif parent_id is not None:
            category.parent_id = parent_id

        if is_active is not None:
            category.is_active = is_active

        self.db.commit()
        self.db.refresh(category)

        return category

    def delete(self, category: Category) -> None:
        self.db.delete(category)
        self.db.commit()

    def get_subcategories(
        self,
        tenant_id: int,
        category_id: int,
    ) -> list[Category]:
        return (
            self.db.query(Category)
            .filter(
                Category.tenant_id == tenant_id,
                Category.parent_id == category_id,
            )
            .order_by(Category.name.asc())
            .all()
        )

    def set_active_status(
        self,
        category: Category,
        is_active: bool,
    ) -> Category:
        category.is_active = is_active
        self.db.commit()
        self.db.refresh(category)
        return category

    def get_products_by_category(
        self,
        tenant_id: int,
        category_id: int,
        search: Optional[str] = None,
        is_active: Optional[bool] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[Product], int]:
        query = (
            self.db.query(Product)
            .filter(
                Product.tenant_id == tenant_id,
                Product.category_id == category_id,
            )
        )

        if search:
            query = query.filter(
                or_(
                    Product.name.ilike(f"%{search.strip()}%"),
                    Product.sku.ilike(f"%{search.strip()}%"),
                )
            )

        if is_active is not None:
            query = query.filter(Product.is_active == is_active)

        total = query.count()
        products = (
            query.order_by(Product.name.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        return products, total