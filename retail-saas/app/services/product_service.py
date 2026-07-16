from sqlalchemy.orm import Session

from app.core.exceptions import ConflictException, NotFoundException
from app.core.security import get_password_hash
from app.models.product import Product
from app.models.role import Role
from app.models.store import Store
from app.models.user import User
from app.repositories.product_repo import ProductRepository
from app.repositories.store_repo import StoreRepository
from app.repositories.user_repo import UserRepository
from app.schemas.product import ProductCreate, ProductUpdate
from app.schemas.user import StoreCreate, StoreUpdate, UserCreate, UserUpdate
from app.utils.barcode import generate_barcode


class ProductService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = ProductRepository(db)

    def create_product(self, tenant_id: int, data: ProductCreate) -> Product:
        if self.repo.get_by_sku(data.sku, tenant_id):
            raise ConflictException("SKU already exists")
        product = Product(tenant_id=tenant_id, **data.model_dump())
        if not product.barcode:
            product.barcode = generate_barcode(product.sku)
        return self.repo.create(product)

    def get_product(self, tenant_id: int, product_id: int) -> Product:
        product = self.repo.get_by_id(product_id, tenant_id)
        if not product:
            raise NotFoundException("Product not found")
        return product

    def get_by_barcode(self, tenant_id: int, barcode: str) -> Product:
        product = self.repo.get_by_barcode(barcode, tenant_id)
        if not product:
            raise NotFoundException("Product not found for barcode")
        return product

    def list_products(self, tenant_id: int, page: int = 1, page_size: int = 20):
        skip = (page - 1) * page_size
        return self.repo.list_products(tenant_id, skip, page_size)

    def update_product(self, tenant_id: int, product_id: int, data: ProductUpdate) -> Product:
        product = self.get_product(tenant_id, product_id)
        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(product, key, value)
        return self.repo.update(product)

    def delete_product(self, tenant_id: int, product_id: int) -> None:
        product = self.get_product(tenant_id, product_id)
        self.repo.delete(product)


class StoreService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = StoreRepository(db)

    def create_store(self, tenant_id: int, data: StoreCreate) -> Store:
        store = Store(tenant_id=tenant_id, **data.model_dump())
        return self.repo.create(store)

    def get_store(self, tenant_id: int, store_id: int) -> Store:
        store = self.db.query(Store).filter(
            Store.id == store_id,
            Store.tenant_id == tenant_id
        ).first()
        if not store:
            raise NotFoundException("Store not found")
        return store

    def list_stores(self, tenant_id: int) -> list[Store]:
        return self.db.query(Store).filter(
            Store.tenant_id == tenant_id,
            Store.is_active.is_(True)
        ).all()

    def update_store(self, tenant_id: int, store_id: int, data: StoreUpdate) -> Store:
        store = self.get_store(tenant_id, store_id)
        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(store, key, value)
        self.db.commit()
        self.db.refresh(store)
        return store


class UserService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = UserRepository(db)

    def create_user(self, tenant_id: int, data: UserCreate) -> User:
        if self.repo.get_by_email(data.email, tenant_id):
            raise ConflictException("Email already registered")
        role = self.db.query(Role).filter(
            Role.id == data.role_id,
            Role.tenant_id == tenant_id
        ).first()
        if not role:
            raise NotFoundException("Role not found")
        if data.store_id is not None:
            StoreService(self.db).get_store(tenant_id, data.store_id)
        user = User(
            tenant_id=tenant_id,
            email=data.email,
            full_name=data.full_name,
            phone=data.phone,
            store_id=data.store_id,
            role_id=data.role_id,
            hashed_password=get_password_hash(data.password),
        )
        return self.repo.create(user)

    def get_user(self, tenant_id: int, user_id: int) -> User:
        user = self.repo.get_by_id(user_id, tenant_id)
        if not user:
            raise NotFoundException("User not found")
        return user

    def list_users(self, tenant_id: int, page: int = 1, page_size: int = 20) -> list[User]:
        skip = (page - 1) * page_size
        return self.repo.list_users(tenant_id, skip, page_size)

    def update_user(self, tenant_id: int, user_id: int, data: UserUpdate) -> User:
        user = self.get_user(tenant_id, user_id)
        update_data = data.model_dump(exclude_unset=True)
        if "password" in update_data:
            password = update_data.pop("password")
            if password is not None:
                user.hashed_password = get_password_hash(password)
        if "store_id" in update_data and update_data["store_id"] is not None:
            StoreService(self.db).get_store(tenant_id, update_data["store_id"])
        for key, value in update_data.items():
            setattr(user, key, value)
        return self.repo.update(user)