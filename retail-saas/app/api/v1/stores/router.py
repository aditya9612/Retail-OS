from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user, require_permission
from app.models.user import User
from app.schemas.user import StoreCreate, StoreResponse, StoreUpdate
from app.services.product_service import StoreService

router = APIRouter(prefix="/stores", tags=["stores"])


@router.get("", response_model=list[StoreResponse])
def list_stores(
    user: User = Depends(require_permission("stores:read")),
    db: Session = Depends(get_db),
):
    return StoreService(db).list_stores(user.tenant_id)


@router.post("", response_model=StoreResponse, status_code=201)
def create_store(
    data: StoreCreate,
    user: User = Depends(require_permission("stores:write")),
    db: Session = Depends(get_db),
):
    return StoreService(db).create_store(user.tenant_id, data)


@router.get("/{store_id}", response_model=StoreResponse)
def get_store(
    store_id: int,
    user: User = Depends(require_permission("stores:read")),
    db: Session = Depends(get_db),
):
    return StoreService(db).get_store(user.tenant_id, store_id)


@router.patch("/{store_id}", response_model=StoreResponse)
def update_store(
    store_id: int,
    data: StoreUpdate,
    user: User = Depends(require_permission("stores:write")),
    db: Session = Depends(get_db),
):
    return StoreService(db).update_store(user.tenant_id, store_id, data)
