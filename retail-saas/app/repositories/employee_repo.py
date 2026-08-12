from sqlalchemy.orm import Session

from app.models.employee import Employee


def create_employee(
    db: Session,
    data
):
    employee = Employee(
        **data.model_dump(),
    )

    db.add(employee)
    db.commit()
    db.refresh(employee)

    return employee


def get_employees(
    db: Session,
    store_id: int
):
    return db.query(Employee).filter(
        Employee.store_id == store_id
    ).all()


def get_employee_by_id(
    db: Session,
    employee_id: int,
    store_id: int
):
    return db.query(Employee).filter(
        Employee.id == employee_id,
        Employee.store_id == store_id
    ).first()


def update_employee(
    db: Session,
    employee: Employee,
    data
):
    for key, value in data.model_dump(
        exclude_unset=True
    ).items():
        setattr(employee, key, value)

    db.commit()
    db.refresh(employee)

    return employee


def delete_employee(
    db: Session,
    employee: Employee
):
    db.delete(employee)
    db.commit()