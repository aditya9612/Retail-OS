from fastapi import HTTPException

from app.models.employee import Employee
from app.models.store import Store

from app.repositories.employee_repo import (
    create_employee,
    get_employees,
    get_employee_by_id,
    update_employee,
    delete_employee
)


def create_employee_service(
    db,
    store_id,
    data
):

    # -------------------------
    # Check store exists
    # -------------------------
    store = db.query(Store).filter(
        Store.id == store_id
    ).first()

    if not store:
        raise HTTPException(
            status_code=404,
            detail="Store not found"
        )

    # -------------------------
    # Check duplicate email
    # -------------------------
    existing = db.query(Employee).filter(
        Employee.email == data.email
    ).first()

    if existing:
        raise HTTPException(
            status_code=400,
            detail="Employee email already exists"
        )

    # -------------------------
    # Create employee
    # -------------------------
    data_dict = data.model_dump()

    data_dict["store_id"] = store_id

    from app.schemas.employee import EmployeeCreate

    employee_data = EmployeeCreate(
        **data_dict
    )

    return create_employee(
        db,
        employee_data
    )


def list_employee_service(
    db,
    store_id
):

    # Check store exists
    store = db.query(Store).filter(
        Store.id == store_id
    ).first()

    if not store:
        raise HTTPException(
            status_code=404,
            detail="Store not found"
        )

    return get_employees(
        db,
        store_id
    )


def get_employee_service(
    db,
    store_id,
    employee_id
):

    employee = get_employee_by_id(
        db,
        employee_id,
        store_id
    )

    if not employee:
        raise HTTPException(
            status_code=404,
            detail="Employee not found in this store"
        )

    return employee


def update_employee_service(
    db,
    store_id,
    employee_id,
    data
):

    employee = get_employee_by_id(
        db,
        employee_id,
        store_id
    )

    if not employee:
        raise HTTPException(
            status_code=404,
            detail="Employee not found in this store"
        )

    # -------------------------
    # Duplicate email check
    # -------------------------
    if data.email is not None:

        existing = db.query(Employee).filter(
            Employee.email == data.email,
            Employee.id != employee_id
        ).first()

        if existing:
            raise HTTPException(
                status_code=400,
                detail="Employee email already exists"
            )

    return update_employee(
        db,
        employee,
        data
    )


def delete_employee_service(
    db,
    store_id,
    employee_id
):

    employee = get_employee_by_id(
        db,
        employee_id,
        store_id
    )

    if not employee:
        raise HTTPException(
            status_code=404,
            detail="Employee not found in this store"
        )

    delete_employee(
        db,
        employee
    )

    return {
        "message": "Employee deleted successfully"
    }