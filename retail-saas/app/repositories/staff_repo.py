from sqlalchemy.orm import Session

from app.models.staff import Staff


def create_staff(
    db: Session,
    data
):
    from app.models.role import Role

    data_dict = data.model_dump() if hasattr(data, "model_dump") else dict(data)
    role_name = data_dict.pop("role", None)

    if role_name and not data_dict.get("role_id"):
        role_obj = db.query(Role).filter(Role.name.ilike(role_name)).first()
        if role_obj:
            data_dict["role_id"] = role_obj.id

    staff = Staff(**data_dict)

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
    from app.models.role import Role

    data_dict = data.model_dump(exclude_unset=True) if hasattr(data, "model_dump") else dict(data)
    role_name = data_dict.pop("role", None)

    if role_name is not None:
        role_obj = db.query(Role).filter(Role.name.ilike(role_name)).first()
        if role_obj:
            staff.role_id = role_obj.id

    for key, value in data_dict.items():
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
