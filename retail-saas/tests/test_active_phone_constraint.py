import pytest
from sqlalchemy.exc import IntegrityError
from app.models.user import User
from app.models.tenant import Tenant
from app.models.role import Role
from app.core.database import SessionLocal


def test_active_phone_unique_constraint():
    db = SessionLocal()
    try:
        # Create test tenant 1 & 2
        t1 = Tenant(name="Tenant 1", domain="tenant-1-phone-test", is_active=True)
        t2 = Tenant(name="Tenant 2", domain="tenant-2-phone-test", is_active=True)
        db.add_all([t1, t2])
        db.commit()
        db.refresh(t1)
        db.refresh(t2)

        # Get or create role with admin permissions so no global state pollution occurs
        role = db.query(Role).first()
        created_role = False
        if not role:
            role = Role(name="admin", tenant_id=None, is_system=True, permissions=["*"])
            db.add(role)
            db.commit()
            db.refresh(role)
            created_role = True

        phone_num = "9876543210"

        # 1. User A in Tenant 1 with phone_num
        user_a = User(
            tenant_id=t1.id,
            role_id=role.id,
            email="usera@test1.com",
            password_hash="fakehash",
            full_name="User A",
            phone=phone_num,
            is_deleted=False,
            is_active=True,
        )
        db.add(user_a)
        db.commit()
        db.refresh(user_a)
        assert user_a.active_phone == phone_num

        # 2. User B in Tenant 2 with SAME phone_num -> Must SUCCEED (cross-tenant allowed)
        user_b = User(
            tenant_id=t2.id,
            role_id=role.id,
            email="userb@test2.com",
            password_hash="fakehash",
            full_name="User B",
            phone=phone_num,
            is_deleted=False,
            is_active=True,
        )
        db.add(user_b)
        db.commit()
        db.refresh(user_b)
        assert user_b.active_phone == phone_num

        # 3. User C in Tenant 1 with SAME phone_num -> Must FAIL with IntegrityError (duplicate active phone in same tenant)
        user_c = User(
            tenant_id=t1.id,
            role_id=role.id,
            email="userc@test1.com",
            password_hash="fakehash",
            full_name="User C",
            phone=phone_num,
            is_deleted=False,
            is_active=True,
        )
        db.add(user_c)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

        # 4. Soft-delete User A (is_deleted = True)
        user_a = db.query(User).filter(User.id == user_a.id).first()
        user_a.is_deleted = True
        db.commit()
        db.refresh(user_a)
        assert user_a.active_phone is None

        # 5. Now create User D in Tenant 1 with SAME phone_num -> Must SUCCEED because User A is deleted
        user_d = User(
            tenant_id=t1.id,
            role_id=role.id,
            email="userd@test1.com",
            password_hash="fakehash",
            full_name="User D",
            phone=phone_num,
            is_deleted=False,
            is_active=True,
        )
        db.add(user_d)
        db.commit()
        db.refresh(user_d)
        assert user_d.active_phone == phone_num

        # 6. Attempt to restore User A (is_deleted = False) while User D is active with same phone -> Must FAIL
        user_a = db.query(User).filter(User.id == user_a.id).first()
        user_a.is_deleted = False
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

        # 7. Multiple users with phone=None in same tenant -> Must SUCCEED (NULLs do not collide)
        user_none1 = User(
            tenant_id=t1.id,
            role_id=role.id,
            email="none1@test1.com",
            password_hash="fakehash",
            full_name="User None 1",
            phone=None,
            is_deleted=False,
            is_active=True,
        )
        user_none2 = User(
            tenant_id=t1.id,
            role_id=role.id,
            email="none2@test1.com",
            password_hash="fakehash",
            full_name="User None 2",
            phone=None,
            is_deleted=False,
            is_active=True,
        )
        db.add_all([user_none1, user_none2])
        db.commit()

    finally:
        db.rollback()
        # Clean up
        db.query(User).filter(User.email.in_([
            "usera@test1.com", "userb@test2.com", "userc@test1.com",
            "userd@test1.com", "none1@test1.com", "none2@test1.com"
        ])).delete(synchronize_session=False)
        db.query(Tenant).filter(Tenant.domain.in_(["tenant-1-phone-test", "tenant-2-phone-test"])).delete(synchronize_session=False)
        if created_role:
            db.query(Role).filter(Role.id == role.id).delete(synchronize_session=False)
        db.commit()
        db.close()
