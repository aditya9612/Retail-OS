from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_permission
from app.models.user import User
from app.schemas.store import StoreCreate, StoreResponse, StoreUpdate
from app.services.store_service import StoreService


router = APIRouter(prefix="/stores", tags=["stores"])

def get_store_service(db: Session = Depends(get_db)):
    return StoreService(db) 

@router.get("/", response_model=list[StoreResponse])
def list_stores(
    user: User = Depends(require_permission("stores:read")),
    service: StoreService = Depends(get_store_service),
):
    return service.list_stores(user.tenant_id) 

@router.post("/", response_model=StoreResponse, status_code=201)
def create_store(
    data: StoreCreate,
    user: User = Depends(require_permission("stores:write")),
    service: StoreService = Depends(get_store_service),
):
    return service.create_store(user.tenant_id, data) 

@router.get("/{store_id}", response_model=StoreResponse)
def get_store(
    store_id: int,
    user: User = Depends(require_permission("stores:read")),
    service: StoreService = Depends(get_store_service),
):
    return service.get_store(user.tenant_id, store_id) 

@router.patch("/{store_id}", response_model=StoreResponse)
def update_store(
    store_id: int,
    data: StoreUpdate,
    user: User = Depends(require_permission("stores:write")),
    service: StoreService = Depends(get_store_service),
):
    return service.update_store(user.tenant_id, store_id, data) 

@router.delete("/{store_id}")
def delete_store(
    store_id: int,
    user: User = Depends(require_permission("stores:write")),
    service: StoreService = Depends(get_store_service),
):
    service.delete_store(user.tenant_id, store_id)
    return {"message": "Store deleted successfully"} 