from fastapi import HTTPException

from app.models.staff import Staff
from app.models.store import Store

from app.repositories.staff_repo import (
    create_staff,
    get_staff,
    get_staff_by_id,
    update_staff,
    delete_staff
)


# ============================================================
# EXISTING STAFF SERVICES
# ============================================================

def create_staff_service(db, store_id, data):

    store = db.query(Store).filter(
        Store.id == store_id
    ).first()

    if not store:
        raise HTTPException(
            status_code=404,
            detail="Store not found"
        )

    existing = db.query(Staff).filter(
        Staff.email == data.email
    ).first()

    if existing:
        raise HTTPException(
            status_code=400,
            detail="Staff email already exists"
        )

    data_dict = data.model_dump()
    data_dict["store_id"] = store_id

    from app.schemas.staff import StaffCreate

    staff_data = StaffCreate(**data_dict)

    return create_staff(
        db,
        staff_data
    )


def list_staff_service(db, store_id):

    store = db.query(Store).filter(
        Store.id == store_id
    ).first()

    if not store:
        raise HTTPException(
            status_code=404,
            detail="Store not found"
        )

    return get_staff(
        db,
        store_id
    )


def get_staff_service(
    db,
    store_id,
    employee_id
):

    staff = get_staff_by_id(
        db,
        employee_id,
        store_id
    )

    if not staff:
        raise HTTPException(
            status_code=404,
            detail="Staff not found in this store"
        )

    return staff


def update_staff_service(
    db,
    store_id,
    employee_id,
    data
):

    staff = get_staff_by_id(
        db,
        employee_id,
        store_id
    )

    if not staff:
        raise HTTPException(
            status_code=404,
            detail="Staff not found in this store"
        )

    # Duplicate email check
    if data.email is not None:

        existing = db.query(Staff).filter(
            Staff.email == data.email,
            Staff.id != employee_id
        ).first()

        if existing:
            raise HTTPException(
                status_code=400,
                detail="Staff email already exists"
            )

    return update_staff(
        db,
        staff,
        data
    )


def delete_staff_service(
    db,
    store_id,
    employee_id
):

    staff = get_staff_by_id(
        db,
        employee_id,
        store_id
    )

    if not staff:
        raise HTTPException(
            status_code=404,
            detail="Staff not found in this store"
        )

    delete_staff(
        db,
        staff
    )

    return {
        "message": "Staff deleted successfully"
    }


# ============================================================
# NEW CENTRALIZED STAFF SERVICES
# ============================================================

def assign_staff_service(
    db,
    staff_id,
    store_id
):

    # Check staff exists
    staff = db.query(Staff).filter(
        Staff.id == staff_id
    ).first()

    if not staff:
        raise HTTPException(
            status_code=404,
            detail="Staff not found"
        )

    # Check store exists
    store = db.query(Store).filter(
        Store.id == store_id
    ).first()

    if not store:
        raise HTTPException(
            status_code=404,
            detail="Store not found"
        )

    # Already assigned
    if staff.store_id == store_id:
        raise HTTPException(
            status_code=400,
            detail="Staff is already assigned to this store"
        )

    # Assign staff
    staff.store_id = store_id

    db.commit()
    db.refresh(staff)

    return staff

def transfer_staff_service(
    db,
    staff_id,
    store_id
):
    staff = db.query(Staff).filter(
        Staff.id == staff_id
    ).first()

    if not staff:
        raise HTTPException(
            status_code=404,
            detail="Staff not found"
        )

    store = db.query(Store).filter(
        Store.id == store_id
    ).first()

    if not store:
        raise HTTPException(
            status_code=404,
            detail="Store not found"
        )

    if staff.store_id == store_id:
        raise HTTPException(
            status_code=400,
            detail="Staff is already assigned to this store"
        )

    staff.store_id = store_id

    db.commit()
    db.refresh(staff)

    return staff

def list_all_staff_service(db):
    return db.query(Staff).all()




