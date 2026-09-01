from fastapi import APIRouter, Depends, Body

from sqlalchemy.orm import Session

from app.core.database import get_db

from app.core.security import require_permission

from app.models.user import User

from app.schemas.store import (

      StoreCreate,

      StoreResponse,

      StoreUpdate,

)

from app.schemas.staff import (

      StaffCreate,

      StaffUpdate,

      StaffResponse,

)

from app.services.store_service import StoreService
from app.services.staff_service import (
    create_staff_service,
    list_staff_service,
    get_staff_service,
    update_staff_service,
    delete_staff_service,
    assign_staff_service,
    transfer_staff_service,
    list_all_staff_service,
)

router = APIRouter(
    prefix="/stores",
    tags=["Stores"],
)


def get_store_service(
    db: Session = Depends(get_db),
):
    return StoreService(db)


# ============================================================
# STORE APIs
# ============================================================

@router.get(
    "/",
    response_model=list[StoreResponse],
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
    status_code=201,
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
        data,
    )


@router.get(
    "/{store_id}",
    response_model=StoreResponse,
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
        store_id,
    )


@router.patch(
    "/{store_id}",
    response_model=StoreResponse,
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
        data,
    )


@router.delete(
    "/{store_id}",
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
        store_id,
    )

    return {
        "message": "Store deleted successfully"
    }

# ============================================================
# STAFF APIs
# ============================================================

@router.post(
    "/{store_id}/staff",
    response_model=StaffResponse,
    status_code=201,
)
def create_staff(
    store_id: int,
    data: StaffCreate,
    user: User = Depends(
        require_permission("employees:write")
    ),
    db: Session = Depends(get_db),
):
    return create_employee_service(
        db,
        store_id,
        data,
    )


@router.get(
    "/{store_id}/staff",
    response_model=list[StaffResponse],
)
def list_staff(
    store_id: int,
    user: User = Depends(
        require_permission("employees:read")
    ),
    db: Session = Depends(get_db),
):
    return list_employee_service(
        db,
        store_id,
    )


@router.get(
    "/{store_id}/staff/{staff_id}",
    response_model=StaffResponse,
)
def get_staff(
    store_id: int,
    staff_id: int,
    user: User = Depends(
        require_permission("employees:read")
    ),
    db: Session = Depends(get_db),
):
    return get_employee_service(
        db,
        store_id,
        staff_id,
    )


@router.patch(
    "/{store_id}/staff/{staff_id}",
    response_model=StaffResponse,
)
def patch_staff(
    store_id: int,
    staff_id: int,
    data: StaffUpdate,
    user: User = Depends(
        require_permission("employees:write")
    ),
    db: Session = Depends(get_db),
):
    return update_employee_service(
        db,
        store_id,
        staff_id,
        data,
    )


@router.delete(
    "/{store_id}/staff/{staff_id}",
)
def delete_staff(
    store_id: int,
    staff_id: int,
    user: User = Depends(
        require_permission("employees:write")
    ),
    db: Session = Depends(get_db),
):
    return delete_employee_service(
        db,
        store_id,
        staff_id,
    )

# ============================================================
# STAFF ASSIGN / TRANSFER / ALL
# ============================================================

@router.patch("/assign/{staff_id}/{store_id}")
def assign_staff(
    staff_id: int,
    store_id: int,
    user: User = Depends(
        require_permission("employees:write")
    ),
    db: Session = Depends(get_db),
):
    return assign_staff_service(
        db,
        staff_id,
        store_id,
    )


@router.patch("/transfer/{staff_id}/{store_id}")
def transfer_staff(
    staff_id: int,
    store_id: int,
    user: User = Depends(
        require_permission("employees:write")
    ),
    db: Session = Depends(get_db),
):
    return transfer_staff_service(
        db,
        staff_id,
        store_id,
    )


@router.get("/all")
def list_all_staff(
    user: User = Depends(
        require_permission("employees:read")
    ),
    db: Session = Depends(get_db),
):
    return list_all_staff_service(db)
