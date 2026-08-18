from sqlalchemy.orm import Session

from app.models.staff import Staff


def create_staff(
    db: Session,
    data
):
    staff = Staff(
        **data.model_dump(),
    )

    db.add(staff)
    db.commit()
    db.refresh(staff)

    return staff


def get_staff(
    db: Session,
    store_id: int
):
    return db.query(Staff).filter(
        Staff.store_id == store_id
    ).all()


def get_staff_by_id(
    db: Session,
    staff_id: int,
    store_id: int
):
    return db.query(Staff).filter(
        Staff.id == staff_id,
        Staff.store_id == store_id
    ).first()


def update_staff(
    db: Session,
    staff: Staff,
    data
):
    for key, value in data.model_dump(
        exclude_unset=True
    ).items():
        setattr(staff, key, value)

    db.commit()
    db.refresh(staff)

    return staff


def delete_staff(
    db: Session,
    staff: Staff
):
    db.delete(staff)
    db.commit()
