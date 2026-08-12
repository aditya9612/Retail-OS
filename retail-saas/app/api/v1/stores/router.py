from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_permission
from app.models.user import User

from app.schemas.store import (
    StoreCreate,
    StoreResponse,
    StoreUpdate
)

from app.schemas.employee import (
    EmployeeCreate,
    EmployeeUpdate,
    EmployeeResponse
)

from app.services.store_service import StoreService

from app.services.employee_service import (
    create_employee_service,
    list_employee_service,
    get_employee_service,
    update_employee_service,
    delete_employee_service
)


router = APIRouter(
    prefix="/stores",
    tags=["Stores"]
)


def get_store_service(
    db: Session = Depends(get_db)
):
    return StoreService(db)


# ==========================
# STORE APIs
# ==========================

@router.get(
    "/",
    response_model=list[StoreResponse]
)
def list_stores(
    user: User = Depends(
        require_permission("stores:read")
    ),
    service: StoreService = Depends(
        get_store_service
    ),
):
    return service.list_stores(
        user.tenant_id
    )


@router.post(
    "/",
    response_model=StoreResponse,
    status_code=201
)
def create_store(
    data: StoreCreate,
    user: User = Depends(
        require_permission("stores:write")
    ),
    service: StoreService = Depends(
        get_store_service
    ),
):
    return service.create_store(
        user.tenant_id,
        data
    )


@router.get(
    "/{store_id}",
    response_model=StoreResponse
)
def get_store(
    store_id: int,
    user: User = Depends(
        require_permission("stores:read")
    ),
    service: StoreService = Depends(
        get_store_service
    ),
):
    return service.get_store(
        user.tenant_id,
        store_id
    )


@router.patch(
    "/{store_id}",
    response_model=StoreResponse
)
def update_store(
    store_id: int,
    data: StoreUpdate,
    user: User = Depends(
        require_permission("stores:write")
    ),
    service: StoreService = Depends(
        get_store_service
    ),
):
    return service.update_store(
        user.tenant_id,
        store_id,
        data
    )


@router.delete(
    "/{store_id}"
)
def delete_store(
    store_id: int,
    user: User = Depends(
        require_permission("stores:write")
    ),
    service: StoreService = Depends(
        get_store_service
    ),
):
    service.delete_store(
        user.tenant_id,
        store_id
    )

    return {
        "message": "Store deleted successfully"
    }


# ==========================
# EMPLOYEE APIs
# ==========================

@router.post(
    "/{store_id}/employees",
    response_model=EmployeeResponse,
    status_code=201
)
def create_employee(
    store_id: int,
    data: EmployeeCreate,
    db: Session = Depends(get_db)
):
    # Always use store_id from URL
    data.store_id = store_id

    return create_employee_service(
        db,
        data
    )


@router.get(
    "/{store_id}/employees",
    response_model=list[EmployeeResponse]
)
def list_employees(
    store_id: int,
    db: Session = Depends(get_db)
):
    return list_employee_service(
        db,
        store_id
    )


@router.get(
    "/{store_id}/employees/{employee_id}",
    response_model=EmployeeResponse
)
def get_employee(
    store_id: int,
    employee_id: int,
    db: Session = Depends(get_db)
):
    return get_employee_service(
        db,
        employee_id,
        store_id
    )


@router.patch(
    "/{store_id}/employees/{employee_id}",
    response_model=EmployeeResponse
)
def patch_employee(
    store_id: int,
    employee_id: int,
    data: EmployeeUpdate,
    db: Session = Depends(get_db)
):
    return update_employee_service(
        db,
        employee_id,
        store_id,
        data
    )


@router.delete(
    "/{store_id}/employees/{employee_id}"
)
def delete_employee(
    store_id: int,
    employee_id: int,
    db: Session = Depends(get_db)
):
    return delete_employee_service(
        db,
        employee_id,
        store_id
    )