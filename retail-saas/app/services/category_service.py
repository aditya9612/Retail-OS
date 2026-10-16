from typing import Optional
from fastapi import status
from sqlalchemy import func
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

        # Check duplicate category name within the same tenant
        if self.repository.get_by_name(tenant_id=tenant_id, name=data.name):
            raise ConflictException(f"Category with name '{data.name.strip()}' already exists")

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
        search: Optional[str] = None,
        is_active: Optional[bool] = None,
        root_only: bool = False,
        parent_id: Optional[int] = None,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
    ) -> tuple[list[Category], int]:
        items = self.repository.get_all(
            tenant_id=tenant_id,
            search=search,
            is_active=is_active,
            root_only=root_only,
            parent_id=parent_id,
            page=page,
            page_size=page_size,
        )
        total = self.repository.count(
            tenant_id=tenant_id,
            search=search,
            is_active=is_active,
            root_only=root_only,
            parent_id=parent_id,
        )
        return items, total

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

        parent_name = None
        if category.parent_id:
            parent = self.repository.get_by_id(
                tenant_id=tenant_id,
                category_id=category.parent_id,
            )
            if parent:
                parent_name = parent.name

        product_count = (
            self.db.query(Product)
            .filter(
                Product.tenant_id == tenant_id,
                Product.category_id == category_id,
            )
            .count()
        )

        subcategory_count = (
            self.db.query(Category)
            .filter(
                Category.tenant_id == tenant_id,
                Category.parent_id == category_id,
            )
            .count()
        )

        category.parent_name = parent_name
        category.product_count = product_count
        category.subcategory_count = subcategory_count
        return category

    def get_category_details(
        self,
        tenant_id: int,
        category_id: int,
    ) -> Category:
        return self.get_category(tenant_id, category_id)

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

        update_parent_id = "parent_id" in data.model_fields_set
        update_description = "description" in data.model_fields_set

        if update_parent_id and data.parent_id is not None:
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

            # Circular reference check: ensure parent is not a descendant of category_id
            curr = parent
            visited = {category_id}
            while curr is not None and curr.parent_id is not None:
                if curr.parent_id in visited:
                    raise AppException(
                        detail="Category cannot have a descendant as its parent (circular reference detected)",
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    )
                visited.add(curr.id)
                curr = self.repository.get_by_id(
                    tenant_id=tenant_id,
                    category_id=curr.parent_id,
                )

        if data.name is not None:
            existing = self.repository.get_by_name(tenant_id=tenant_id, name=data.name)
            if existing and existing.id != category_id:
                raise ConflictException(f"Category with name '{data.name.strip()}' already exists")

        try:
            return self.repository.update(
                category=category,
                name=data.name,
                description=data.description,
                parent_id=data.parent_id,
                is_active=getattr(data, "is_active", None),
                update_parent_id=update_parent_id,
                update_description=update_description,
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

        # Check for associated products globally to prevent FK constraint failures
        product_count = (
            self.db.query(Product)
            .filter(Product.category_id == category_id)
            .count()
        )
        if product_count > 0:
            raise ConflictException(
                f"Cannot delete category: {product_count} product(s) are associated with it"
            )

        # Check for child subcategories
        child_count = (
            self.db.query(Category)
            .filter(Category.parent_id == category_id)
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
        except Exception as exc:
            self.db.rollback()
            raise ConflictException(
                f"Cannot delete category: {str(exc)}"
            )

    def get_category_tree(self, tenant_id: int) -> list[dict]:
        categories = self.repository.get_all(tenant_id=tenant_id)
        if not categories:
            return []

        # Product count per category
        prod_counts = dict(
            self.db.query(Product.category_id, func.count(Product.id))
            .filter(Product.tenant_id == tenant_id, Product.category_id.is_not(None))
            .group_by(Product.category_id)
            .all()
        )

        nodes: dict[int, dict] = {}
        for cat in categories:
            nodes[cat.id] = {
                "id": cat.id,
                "tenant_id": cat.tenant_id,
                "parent_id": cat.parent_id,
                "name": cat.name,
                "is_active": cat.is_active,
                "description": cat.description,
                "product_count": prod_counts.get(cat.id, 0),
                "children": [],
                "created_at": cat.created_at,
                "updated_at": cat.updated_at,
            }

        root_nodes: list[dict] = []
        for cat in categories:
            node = nodes[cat.id]
            if cat.parent_id is not None and cat.parent_id in nodes:
                nodes[cat.parent_id]["children"].append(node)
            else:
                root_nodes.append(node)

        return root_nodes

    def get_subcategories(
        self,
        tenant_id: int,
        category_id: int,
    ) -> list[Category]:
        parent = self.repository.get_by_id(tenant_id=tenant_id, category_id=category_id)
        if not parent:
            raise NotFoundException("Category not found")

        subcats = self.repository.get_subcategories(tenant_id=tenant_id, category_id=category_id)
        for subcat in subcats:
            subcat.parent_name = parent.name
            subcat.product_count = (
                self.db.query(Product)
                .filter(Product.tenant_id == tenant_id, Product.category_id == subcat.id)
                .count()
            )
            subcat.subcategory_count = (
                self.db.query(Category)
                .filter(Category.tenant_id == tenant_id, Category.parent_id == subcat.id)
                .count()
            )

        return subcats

    def get_category_products(
        self,
        tenant_id: int,
        category_id: int,
        search: Optional[str] = None,
        is_active: Optional[bool] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict:
        category = self.repository.get_by_id(tenant_id=tenant_id, category_id=category_id)
        if not category:
            raise NotFoundException("Category not found")

        products, total = self.repository.get_products_by_category(
            tenant_id=tenant_id,
            category_id=category_id,
            search=search,
            is_active=is_active,
            page=page,
            page_size=page_size,
        )

        return {
            "success": True,
            "message": "Category products retrieved successfully",
            "total": total,
            "page": page,
            "page_size": page_size,
            "category_id": category.id,
            "category_name": category.name,
            "data": products,
        }

    def set_category_active(
        self,
        tenant_id: int,
        category_id: int,
        is_active: bool,
    ) -> Category:
        category = self.repository.get_by_id(tenant_id=tenant_id, category_id=category_id)
        if not category:
            raise NotFoundException("Category not found")

        return self.repository.set_active_status(category, is_active)